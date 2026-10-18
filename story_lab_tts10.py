"""
story_lab_tts10.py  —  Story Lab v10  //  Kokoro voice layer, SENTENCE-STREAMED

RUNS ON THE CPU. The LLM owns the GPU (engine10 NUM_GPU = 99); Kokoro-82M is
82 million parameters and synthesises faster than real time on a CPU core, so
the two lanes never compete for the same silicon.

WHAT IS NEW IN v10 (and why)
============================
v5's voice layer took a WHOLE PARAGRAPH, called Kokoro once, wrote a WAV, then
played it. Three costs, all of which the player felt:

  1. TIME TO FIRST SOUND was the synthesis time of the entire paragraph. A
     120-word resolution is ~9 s of audio and took seconds to build before a
     single syllable came out. The feed sat silent, then dumped everything.
  2. PEAK LOAD was one long torch forward pass holding the whole waveform,
     with a file write in the playback path.
  3. NOTHING COULD BE SYNCHRONISED. One WAV per paragraph means the GUI knows
     exactly one thing: "this block is playing". It cannot highlight a
     sentence, because it has no idea which sentence is sounding.

v10 splits every utterance into SENTENCE-SIZED CHUNKS before synthesis. The
voice worker synthesises chunk N+1 while the presenter plays chunk N, so:

     paragraph model :  [========== synth ==========][===== play =====]
     v10 chunk model :  [s1][s2][s3][s4][s5]...
                            [p1][p2][p3][p4][p5]...
                        ^ sound starts here, ~0.3-0.6 s in

Time to first sound becomes the synthesis time of ONE SENTENCE, peak memory
becomes ONE SENTENCE of float32, and - the reason this matters for the GUI -
each chunk carries its own duration, so the story screen can light up exactly
the words being spoken.

SEGMENT-AWARE SPLITTING
=======================
Chunking is not blind sentence splitting. story_lab_metrics.segments() (the
same instrument engine10's v9.2 history-view normaliser uses) tells us which
part of a line is *marked action*, which is "quoted speech", and which is
bare prose the Tier-2 classifier has to judge. That buys three things at once:

  - the GUI can render beats in italic and speech upright;
  - beats can optionally be read by the NARRATOR instead of the character,
    or simply at a lower gain, so stage directions sit under the dialogue;
  - a chunk never straddles the boundary between a beat and a line of speech,
    which is where a naive splitter produces its ugliest reads.

AUDIO STAYS IN MEMORY
=====================
Synthesis returns a numpy array that goes straight into the Chunk. Playback
never touches the disk, so a chunk starts the instant the presenter reaches
it. The WAV is still written - the run directory keeps a replayable artifact
per chunk - but the write happens on the voice worker AFTER the array is
handed over, never in the playback path.

WHAT IS UNCHANGED
=================
Voice SELECTION is v5's, imported wholesale from story_lab_tts5 (which stays
frozen): the trait-blend selector in kokoro_voices.py, the deterministic
name-hash so a character sounds the same across runs, the narrator
woman/man/random + posh/rough options, and the collision rule. That code was
measured and works; only the delivery changed.

Install once:  pip install kokoro soundfile sounddevice numpy
"""

from __future__ import annotations

import os
import re
import time
import dataclasses

# --- guarded numeric/audio imports (mirrors tts5's contract) -----------------
_LOCAL_STATUS = "ok"
try:
    import numpy as np
except ImportError:
    np = None
    _LOCAL_STATUS = "numpy not installed"
try:
    import soundfile as sf
except ImportError:
    sf = None
    if _LOCAL_STATUS == "ok":
        _LOCAL_STATUS = "soundfile not installed"
try:
    import sounddevice as sd
except Exception:
    sd = None
    if _LOCAL_STATUS == "ok":
        _LOCAL_STATUS = "sounddevice unavailable"

# --- v5 selection layer, reused verbatim (that file is frozen) ---------------
import story_lab_tts5 as _tts5
from story_lab_tts5 import (               # re-exported: the director imports
    profile_for_character,                 # everything voice-related from here
    narrator_profile,
    resolve_cast,
    cast_summary,
    SAMPLE_RATE,
    AUDIO_SUBDIR,
)

_get_pipeline = _tts5._get_pipeline         # private by name only - it is the
                                            # shared, CPU-pinned pipeline cache
                                            # and MUST NOT be duplicated here

# --- the segment classifier (optional; degrades to whole-line chunks) --------
try:
    import story_lab_metrics as _METRICS
except Exception:
    _METRICS = None

# =============================================================================
#  SECTION 1 - TUNABLES
# =============================================================================

MAX_CHUNK_WORDS = 26     # above this a sentence is split again at a comma or
                         # dash. 26 words is ~10 s of speech: long enough to
                         # keep prosody, short enough that the highlight band
                         # never sits still long enough to feel stuck.
MIN_CHUNK_WORDS = 4      # below this a fragment is merged into its neighbour
                         # ("Right." on its own is a 0.4 s clip whose device
                         # start-up cost exceeds its content).

BEAT_GAIN       = 0.82   # *action beats* play slightly under the dialogue, so
                         # stage direction sits behind speech the way it reads
                         # on the page. Pure amplitude - no new voice.

TRIM_SILENCE    = True   # Kokoro pads ~100 ms of near-silence at each end;
TRIM_THRESHOLD  = 0.004  # trimming it closes the gap between chunks so the
TRIM_KEEP_MS    = 30     # sentence stream sounds continuous, not stuttered.

PLAY_POLL_S     = 0.01   # 100 Hz stop-check during playback. The old layer
                         # polled at 20 Hz with a 1.0 s grace period, which
                         # added an audible pause to every single item.

# =============================================================================
#  SECTION 2 - THE CHUNK
# =============================================================================

@dataclasses.dataclass
class Chunk:
    """
    One sentence-sized unit of speech, and the atom of GUI synchronisation.

      idx        position within the parent item, 0-based
      text       DISPLAY text - markup preserved, this is what the feed shows
      speech     what Kokoro is actually given (asterisks stripped, collapsed)
      mode       "speech" | "narration" - drives italics in the feed and gain
      voice_key  "narrator" | "a" | "b" | "" (unvoiced)
      audio      numpy float32 mono @ 24 kHz, filled by the voice worker
      seconds    duration of `audio`, or 0.0 when unvoiced - the GUI uses it
                 to pace a word-level highlight inside the chunk
      wav_name   basename of the archived WAV, "" if none was written
      para_break True if a blank line preceded this chunk in the generated
                 text. Chunks are joined with single spaces when displayed,
                 so without this flag a multi-paragraph opener would be
                 flattened into one block on screen.
    """
    idx:       int
    text:      str
    speech:    str
    mode:      str = "speech"
    voice_key: str = ""
    audio:     object = None
    seconds:   float = 0.0
    wav_name:  str = ""
    para_break: bool = False

    @property
    def words(self) -> int:
        return len(self.text.split())

# =============================================================================
#  SECTION 3 - SENTENCE SPLITTING
# =============================================================================

# Abbreviations whose full stop is NOT a sentence end. Small on purpose: this
# cast talks, it does not write academic prose, and every entry here is a
# chance to miss a real boundary.
_ABBREV = frozenset("mr mrs ms dr st prof sgt capt lt col gen sr jr vs etc no".split())

# A terminator, any closing quote/bracket that belongs to it, then whitespace.
_BOUNDARY = re.compile(r'([.!?…]+["”\'\)\]]*)(\s+)')

# Secondary break points, used only to cut an over-long sentence.
_SOFT_BREAK = re.compile(r'(,|;|:|\s—\s|\s--\s)\s*')


def _sentences(text: str) -> list:
    """Split prose into sentences, keeping terminators and closing quotes."""
    out, start = [], 0
    for m in _BOUNDARY.finditer(text):
        head = text[start:m.end(1)]
        tail_word = re.search(r'([A-Za-z]+)\.["”\'\)\]]*$', head)
        if tail_word and tail_word.group(1).lower() in _ABBREV:
            continue                                   # "Mr. Kestrel" is one sentence
        piece = head.strip()
        if piece:
            out.append(piece)
        start = m.end(2)
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def _split_long(sentence: str, limit: int) -> list:
    """
    Cut an over-long sentence at the soft break nearest its middle, then
    recurse. Splitting at the MIDDLE (not the first comma) keeps both halves
    substantial - a 30-word sentence broken after three words produces one
    stub chunk and one still-too-long chunk.
    """
    words = sentence.split()
    if len(words) <= limit:
        return [sentence]
    breaks = [m.end() for m in _SOFT_BREAK.finditer(sentence)]
    breaks = [b for b in breaks if 0 < b < len(sentence)]
    if not breaks:
        mid = len(words) // 2                          # no punctuation: split on words
        return [" ".join(words[:mid]), " ".join(words[mid:])]
    target = len(sentence) // 2
    cut = min(breaks, key=lambda b: abs(b - target))
    left, right = sentence[:cut].strip(), sentence[cut:].strip()
    if not left or not right:
        return [sentence]
    return _split_long(left, limit) + _split_long(right, limit)


def clean_for_tts(text: str) -> str:
    """Strip display markup Kokoro should not pronounce; collapse whitespace."""
    text = text.replace("*", " ").replace("_", " ")
    text = text.replace("—", " — ")          # em-dash gets breathing room
    return " ".join(text.split())


def _segment_mode(kind: str, text: str) -> str:
    """metrics segment kind -> "speech" | "narration"."""
    if _METRICS is None:
        return "speech"
    if kind == _METRICS.MARKED:
        return "narration"
    if kind == _METRICS.QUOTED:
        return "speech"
    body = text.strip()
    if _METRICS.wc(body) < MIN_CHUNK_WORDS:            # too short to classify
        return "speech"
    return "narration" if _METRICS.classify_bare(body) == "NARRATION" else "speech"


def split_utterance(text: str,
                    voice_key: str = "",
                    beats_voice_key=None,
                    max_words: int = MAX_CHUNK_WORDS,
                    min_words: int = MIN_CHUNK_WORDS) -> list:
    """
    One block of generated prose -> the chunk list the whole pipeline uses.

    `beats_voice_key` reads *action beats* in a different voice (pass
    "narrator" to have the storyteller describe what the character does while
    the character only speaks the quoted words). None keeps everything in the
    speaker's own voice, which is v5's behaviour and the default.

    The chunk list is produced by the STORY thread, before any synthesis, so
    the GUI can lay out and dim the whole utterance the moment it appears and
    the voice worker only has to fill in audio.
    """
    text = (text or "").strip()
    if not text:
        return []

    chunks = []
    # Paragraphs are split off FIRST and never merged across, so a blank line
    # in the generated prose survives into the feed as a blank line.
    for p_i, para in enumerate(re.split(r"\n\s*\n+", text)):
        para = para.strip()
        if not para:
            continue

        # ---- 1. mode-tagged segments (beat / speech / bare-classified) -----
        if _METRICS is not None:
            raw = [(_segment_mode(k, t), t) for k, t in _METRICS.segments(para)]
        else:
            raw = [("speech", para)]

        # ---- 2. sentence split inside each segment, mode carried through ---
        pieces = []
        for mode, seg in raw:
            seg = seg.strip()
            if not seg:
                continue
            for sent in _sentences(seg) or [seg]:
                for part in _split_long(sent, max_words):
                    part = part.strip()
                    if part:
                        pieces.append((mode, part))

        # ---- 3. merge runt fragments into the neighbour of the same mode ---
        merged = []
        for mode, part in pieces:
            if (merged and merged[-1][0] == mode
                    and (len(part.split()) < min_words
                         or len(merged[-1][1].split()) < min_words)
                    and len(merged[-1][1].split()) + len(part.split()) <= max_words):
                merged[-1] = (mode, merged[-1][1] + " " + part)
            else:
                merged.append((mode, part))

        # ---- 4. build chunks -----------------------------------------------
        for i, (mode, part) in enumerate(merged):
            speech = clean_for_tts(part)
            if not speech:
                continue
            key = voice_key
            if mode == "narration" and beats_voice_key:
                key = beats_voice_key
            chunks.append(Chunk(idx=len(chunks), text=part, speech=speech,
                                mode=mode, voice_key=key,
                                para_break=(p_i > 0 and i == 0 and bool(chunks))))
    return chunks

# =============================================================================
#  SECTION 4 - SYNTHESIS  (one chunk at a time, into memory)
# =============================================================================

def _trim_silence(audio):
    """
    Drop the near-silent head and tail Kokoro pads onto every clip, keeping a
    short cushion. Without this, five chunks in a row stack five pairs of
    padding into an audibly stuttered paragraph.
    """
    if not TRIM_SILENCE or np is None or audio is None or len(audio) == 0:
        return audio
    loud = np.nonzero(np.abs(audio) > TRIM_THRESHOLD)[0]
    if len(loud) == 0:
        return audio
    keep = int(SAMPLE_RATE * TRIM_KEEP_MS / 1000)
    return audio[max(0, loud[0] - keep): min(len(audio), loud[-1] + keep)]


def synthesize_chunk(chunk, resolved, run_dir=None, prefix: str = "") -> bool:
    """
    Fill chunk.audio / chunk.seconds from chunk.speech.

    Returns True on success. On ANY failure the chunk simply stays unvoiced -
    the presenter falls back to a timed reveal for that one sentence and the
    stream never stalls. One bad chunk must not cost the round.
    """
    if not tts_available() or resolved is None or resolved.voice_tensor is None:
        return False
    if not chunk.speech:
        return False
    try:
        pipeline = _get_pipeline(resolved.lang_code)
        parts = [a for _, _, a in pipeline(chunk.speech,
                                           voice=resolved.voice_tensor,
                                           speed=resolved.final_speed)]
        if not parts:
            return False
        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        audio = np.asarray(audio, dtype="float32")
        audio = _trim_silence(audio)
        if chunk.mode == "narration" and BEAT_GAIN != 1.0:
            audio = audio * BEAT_GAIN                  # beats sit under speech
        chunk.audio = audio
        chunk.seconds = len(audio) / float(SAMPLE_RATE)
    except Exception as e:
        print(f"  x TTS failed ({e}) - chunk plays as text.", flush=True)
        return False

    # Archive AFTER the array exists: the write is off the playback path.
    if run_dir and sf is not None:
        try:
            name = f"{prefix}_{chunk.idx:02d}.wav"
            out = os.path.join(run_dir, AUDIO_SUBDIR, name)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            sf.write(out, chunk.audio, SAMPLE_RATE)
            chunk.wav_name = name
        except Exception:
            pass                                       # archiving is never load-bearing
    return True


def warmup(cast: dict) -> None:
    """
    Force the first (slow) Kokoro forward pass during SETUP, while the LLM is
    still writing the setting. `import kokoro` pulls in torch and the first
    synthesis allocates its graph - several seconds that would otherwise land
    on the player as silence before the very first spoken line.
    """
    if not cast:
        return
    voice = cast.get("narrator") or next(iter(cast.values()))
    try:
        t0 = time.time()
        c = Chunk(idx=0, text="Ready.", speech="Ready.")
        synthesize_chunk(c, voice)
        print(f"  ok Kokoro warm ({time.time() - t0:.1f}s).", flush=True)
    except Exception:
        pass

# =============================================================================
#  SECTION 5 - PLAYBACK  (blocking per chunk, tight, interruptible)
# =============================================================================

def play_audio(audio, stop_event=None) -> bool:
    """
    Play one in-memory chunk and block for exactly its duration.

    Returns True if it finished naturally, False if stop_event cut it short.
    Safe on the presenter thread - sounddevice is PortAudio-callback driven.
    """
    if sd is None or audio is None or len(audio) == 0:
        return False
    try:
        sd.play(audio, SAMPLE_RATE)
        deadline = time.perf_counter() + len(audio) / float(SAMPLE_RATE)
        while time.perf_counter() < deadline:
            if stop_event is not None and stop_event.is_set():
                sd.stop()
                return False
            time.sleep(PLAY_POLL_S)
        return True
    except Exception as e:
        print(f"  x Playback failed: {e}", flush=True)
        return False


def stop_audio() -> None:
    """Hard-stop whatever is sounding (skip / shutdown)."""
    if sd is not None:
        try:
            sd.stop()
        except Exception:
            pass

# =============================================================================
#  SECTION 6 - AVAILABILITY + ONE-OFF PREVIEW  (used by the setup screen)
# =============================================================================

def tts_available() -> bool:
    return _tts5.tts_available() and np is not None and sf is not None and sd is not None


def tts_status() -> str:
    if _LOCAL_STATUS != "ok":
        return _LOCAL_STATUS
    return _tts5.tts_status()


class _Duck:
    """Minimal stand-in for StoryCharacter - the selector only reads three
    attributes, so the setup screen can audition a voice BEFORE the extractor
    has ever run (no LLM call, no waiting)."""
    def __init__(self, name, gender, age_group):
        self.name, self.gender, self.age_group = name, gender, age_group


def resolve_preview(name: str, gender: str, age_group: str):
    """Resolve + build one character voice from raw setup-screen values."""
    if not tts_available():
        return None
    prof = profile_for_character(_Duck(name or "Unknown", gender, age_group))
    resolved = prof.resolve(mood="neutral")
    from kokoro_voices import build_tensor
    return build_tensor(resolved, _get_pipeline(resolved.lang_code))


def resolve_narrator_preview(gender_choice: str, accent_choice: str):
    """Resolve + build the narrator voice from the two setup-screen options."""
    if not tts_available():
        return None
    prof = narrator_profile(gender_choice, accent_choice)
    resolved = prof.resolve(mood="neutral")
    from kokoro_voices import build_tensor
    return build_tensor(resolved, _get_pipeline(resolved.lang_code))


def speak_now(text: str, resolved, stop_event=None) -> None:
    """Synthesise and play one short line immediately (voice preview only)."""
    if resolved is None:
        return
    for chunk in split_utterance(text, voice_key="preview"):
        if stop_event is not None and stop_event.is_set():
            return
        if synthesize_chunk(chunk, resolved):
            play_audio(chunk.audio, stop_event)


# =============================================================================
#  SECTION 7 - SELF TEST   (python story_lab_tts10.py)
#
#  Splitting is pure text: it is checked with no model, no audio and no GPU.
#  Pass --speak to also synthesise and play the demo line.
# =============================================================================

if __name__ == "__main__":
    import sys

    DEMO = ('*She sets the cutter down, slow enough that he sees her do it.* '
            '"You came a long way for a name I already sold." '
            'Her jaw works once. The station hums under them, a low complaint '
            'in the deck plates, and somewhere aft a seal lets go with a bang '
            'that neither of them acknowledges. "So ask me properly, or leave."')

    print(f"metrics: {'loaded' if _METRICS else 'ABSENT (whole-line chunks)'}")
    print(f"voice stack: {tts_status()}\n")
    for c in split_utterance(DEMO, voice_key="a"):
        print(f"  [{c.idx:02d}] {c.mode:9} {c.words:2}w  {c.text}")

    if "--speak" in sys.argv:
        v = resolve_preview("Vess", "female", "MiddleAged")
        print("\n" + (v.describe() if v else "no voice"))
        speak_now(DEMO, v)
