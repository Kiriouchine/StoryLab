"""
story_lab_tts5.py  —  Story Lab v5  //  Kokoro voice layer

PURPOSE
=======
Turn text into spoken WAV files on the CPU, using the parent project's
proven trait-blend selector (kokoro_voices.py — ship that file alongside
this one). Three jobs:

  1. SELECTION  — map a StoryCharacter's passthrough demographics
                  (gender, age_group) + a deterministic name hash onto a
                  kokoro_voices.CharacterProfile, and build the narrator's
                  profile from the GUI options (woman / man / random,
                  posh / rough).
  2. SYNTHESIS  — text + ResolvedVoice -> 24 kHz WAV file in the run dir.
  3. PLAYBACK   — blocking, skippable WAV playback for the presenter thread.

WHY GENDER + AGE_GROUP WERE ALWAYS PASSTHROUGH
==============================================
The extractor never touches them because they are VOICE inputs, not story
inputs. YoungAdult / MiddleAged / Elder maps to the selector's age axis
(which drives speaking speed) and to an authority baseline (which picks the
position inside the voice pool). female / male map straight through;
nonbinary picks a hash-stable base gender and pushes masculinity deep into
the cross-blend zone, so the existing selector math produces a heavy
cross-gender blend — an androgynous voice with zero new mechanisms.

NARRATOR OPTIONS  (the GUI exposes these)
=========================================
  gender:  "woman" | "man" | "random"   — random is drawn once per session
  accent:  "posh"  | "rough"            — posh  = formality True  -> the
                                          selector picks a BRITISH primary
                                          voice (bf_/bm_ pools);
                                          rough = formality False -> an
                                          AMERICAN primary (af_/am_ pools).
This maps the player's words onto existing selector math — no new pools.

DETERMINISM FOR RESEARCH
========================
Character voices are seeded by a hash of the character NAME, so the same
character gets the same voice across runs — a controlled variable. Only the
narrator's "random" option uses true randomness, by request.

CPU PIN
=======
KOKORO_DEVICE = "cpu". Kokoro-82M synthesises faster than real time on a
CPU and must never compete with ComfyUI for VRAM. All heavy imports are
guarded: if kokoro / soundfile / sounddevice / numpy are missing, the
module degrades to "unavailable" and the director runs the game text-only.

Install once:  pip install kokoro soundfile sounddevice numpy
"""

import os
import time
import random
import hashlib

# =============================================================================
#  SECTION 1 — GUARDED IMPORTS
#
#  Every third-party dependency is optional at import time. _TTS_STATUS
#  records the first missing piece so the GUI status strip can say WHY
#  voice is off instead of just failing silently.
# =============================================================================

_TTS_STATUS = "ok"                     # human-readable reason if degraded

try:
    import numpy as np                 # kokoro_voices needs numpy at import time
except ImportError:
    np = None
    _TTS_STATUS = "numpy not installed"

try:
    import soundfile as sf             # WAV read/write
except ImportError:
    sf = None
    if _TTS_STATUS == "ok":
        _TTS_STATUS = "soundfile not installed"

try:
    import sounddevice as sd           # playback (PortAudio)
except Exception:                      # ImportError OR missing PortAudio lib
    sd = None
    if _TTS_STATUS == "ok":
        _TTS_STATUS = "sounddevice unavailable"

try:
    # The parent project's selector — pure math, ships next to this file.
    from kokoro_voices import (CharacterProfile, ResolvedVoice,
                               build_tensor, NARRATOR)
    _VOICES_OK = True
except Exception as _e:
    CharacterProfile = ResolvedVoice = build_tensor = NARRATOR = None
    _VOICES_OK = False
    if _TTS_STATUS == "ok":
        _TTS_STATUS = f"kokoro_voices.py not importable ({_e})"

_KPipeline = None                      # imported lazily in _get_pipeline() —
                                       # `import kokoro` pulls in torch, which
                                       # is slow; defer it to first actual use.

# =============================================================================
#  SECTION 2 — CONSTANTS
# =============================================================================

KOKORO_DEVICE = "cpu"    # NEVER the GPU — ComfyUI owns all 12 GB of VRAM.
                         # Kokoro-82M is faster than real time on CPU anyway.
SAMPLE_RATE   = 24000    # Kokoro's native output rate
KOKORO_REPO   = "hexgrad/Kokoro-82M"   # ~330 MB one-time download on first use
AUDIO_SUBDIR  = "audio"  # WAVs land in run_dir/audio/ — replayable artifacts

# StoryCharacter.age_group -> the selector's age axis (drives speaking speed:
# young = 1.1x, old = 0.9x) — see kokoro_voices SPEED DERIVATION.
_AGE_AXIS = {
    "YoungAdult": 0.15,
    "MiddleAged": 0.50,
    "Elder":      0.85,
    "unspecified": 0.40,               # neutral-ish adult default
}

# age_group -> authority BASELINE (position inside the voice pool: light and
# young at 0.0, heavy and commanding at 1.0). A name-hash jitter of ±0.15 is
# added so two same-demographic characters land on different pool entries.
_AUTHORITY_BASE = {
    "YoungAdult": 0.30,
    "MiddleAged": 0.55,
    "Elder":      0.80,
    "unspecified": 0.50,
}

_AUTHORITY_JITTER = 0.15               # ± range added from the name hash
_MASCULINITY_JITTER = 0.08             # small voice-texture variety

# =============================================================================
#  SECTION 3 — DETERMINISTIC NAME HASH
# =============================================================================

def _hash01(name: str, salt: str = "") -> float:
    """
    Map a name (+salt) to a stable float in [0, 1).
    md5 is used for STABILITY across Python processes — the built-in hash()
    is randomised per interpreter run, which would break run-to-run voice
    determinism (a research requirement).
    """
    digest = hashlib.md5((salt + name).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF

# =============================================================================
#  SECTION 4 — PROFILE BUILDERS  (pure math — no Kokoro needed)
# =============================================================================

def profile_for_character(char) -> "CharacterProfile":
    """
    StoryCharacter -> kokoro_voices.CharacterProfile.

    gender:
      female / male  -> passed straight to the selector
      nonbinary      -> hash-stable base gender with masculinity pushed deep
                        into the cross-blend zone (0.15 on a male base or
                        0.85 on a female base). The selector's existing
                        cross-gender rule then blends ~0.35 of the opposite
                        pool — an androgynous voice from proven math.
    age_group        -> age axis (speed) + authority baseline (pool position)
    name hash        -> ±0.15 authority jitter, ±0.08 masculinity jitter, so
                        same-demographic characters still sound different,
                        deterministically.
    """
    if not _VOICES_OK:
        return None

    gender = getattr(char, "gender", "unspecified")
    age_gr = getattr(char, "age_group", "unspecified")
    name   = getattr(char, "name", "Unknown")

    jitter_a = (_hash01(name, "authority")   - 0.5) * 2 * _AUTHORITY_JITTER
    jitter_m = (_hash01(name, "masculinity") - 0.5) * 2 * _MASCULINITY_JITTER

    if gender == "male":
        base_gender, masculinity = "male", 0.80 + jitter_m
    elif gender == "female":
        base_gender, masculinity = "female", 0.20 + jitter_m
    else:                                   # nonbinary / unspecified
        # Hash-stable base gender pick, then push masculinity toward the
        # far cross-blend zone so the secondary weight lands near its cap.
        if _hash01(name, "base_gender") < 0.5:
            base_gender, masculinity = "male", 0.15 + jitter_m      # heavy female blend
        else:
            base_gender, masculinity = "female", 0.85 + jitter_m    # heavy male blend

    authority = _AUTHORITY_BASE.get(age_gr, 0.50) + jitter_a

    return CharacterProfile(
        name           = name,
        gender         = base_gender,
        masculinity    = round(min(1.0, max(0.0, masculinity)), 3),
        authority      = round(min(1.0, max(0.0, authority)), 3),
        age            = _AGE_AXIS.get(age_gr, 0.40),
        emotional_base = 0.0,               # neutral baseline; a future lever
        formality      = False,             # characters default American/rough
    )


def narrator_profile(gender_choice: str = "woman",
                     accent_choice: str = "rough") -> "CharacterProfile":
    """
    Build the narrator's profile from the two GUI options.

      gender_choice: "woman" | "man" | "random"
      accent_choice: "posh" (British primary) | "rough" (American primary)

    "random" is drawn HERE, once per call — the director calls this once at
    session start, so the pick holds for the whole session. Base trait
    numbers come from the parent project's NARRATOR preset (measured,
    mid-authority storyteller), with gender/masculinity swapped to match
    the choice.
    """
    if not _VOICES_OK:
        return None

    choice = gender_choice.lower()
    if choice == "random":
        choice = random.choice(["woman", "man"])        # true randomness, by request
        print(f"  Narrator gender rolled: {choice}", flush=True)

    if choice == "man":
        gender, masculinity = "male", 0.75
    else:                                               # "woman" and any fallback
        gender, masculinity = "female", 0.35

    return CharacterProfile(
        name           = "Narrator",
        gender         = gender,
        masculinity    = masculinity,
        authority      = 0.6,                           # measured, storyteller weight
        age            = 0.4,                           # adult, unhurried
        emotional_base = 0.0,
        formality      = (accent_choice.lower() == "posh"),   # posh -> BRITISH primary
    )

# =============================================================================
#  SECTION 5 — CAST RESOLUTION  (selection + collision rule + tensors)
# =============================================================================

def resolve_cast(char_a, char_b,
                 narrator_gender: str = "woman",
                 narrator_accent: str = "rough") -> dict:
    """
    Resolve all three voices for a session and build their blend tensors.
    Returns {"a": ResolvedVoice, "b": ResolvedVoice, "narrator": ResolvedVoice}
    with voice_tensor populated — or {} if the voice stack is unavailable
    (the director then runs text-only).

    COLLISION RULE: if both characters resolve to the same PRIMARY voice
    (possible for same-gender, same-age casts), character B's authority is
    bumped one tier away and re-resolved, so the two voices stay tellable
    apart. Deterministic: the bump depends only on B's own authority.
    """
    if not tts_available():
        print(f"  \u26a0 Voice stack unavailable ({_TTS_STATUS}) — text-only.", flush=True)
        return {}

    prof_a = profile_for_character(char_a)
    prof_b = profile_for_character(char_b)
    prof_n = narrator_profile(narrator_gender, narrator_accent)

    res_a = prof_a.resolve(mood="neutral")
    res_b = prof_b.resolve(mood="neutral")

    if res_b.primary_voice == res_a.primary_voice:      # same pool entry — separate them
        bump = 0.2 if prof_b.authority <= 0.5 else -0.2
        prof_b.authority = round(min(1.0, max(0.0, prof_b.authority + bump)), 3)
        res_b = prof_b.resolve(mood="neutral")
        print(f"  Voice collision — bumped {char_b.name}'s authority to "
              f"{prof_b.authority}.", flush=True)

    res_n = prof_n.resolve(mood="neutral")

    cast = {}
    for key, resolved in (("a", res_a), ("b", res_b), ("narrator", res_n)):
        try:
            pipeline = _get_pipeline(resolved.lang_code)
            cast[key] = build_tensor(resolved, pipeline)     # loads + blends tensors
            print(f"  \u2713 {cast[key].describe()}", flush=True)
        except Exception as e:
            print(f"  \u2717 Voice tensor failed [{key}]: {e}", flush=True)
            return {}                                        # all-or-nothing: keep lanes simple
    return cast


def cast_summary(cast: dict) -> str:
    """One line per resolved voice — shown in the observation drawer."""
    if not cast:
        return f"Voice: unavailable ({_TTS_STATUS})"
    return "\n".join(cast[k].describe() for k in ("narrator", "a", "b") if k in cast)

# =============================================================================
#  SECTION 6 — PIPELINE CACHE  (lazy, CPU-pinned)
# =============================================================================

_pipelines: dict = {}                  # lang_code -> KPipeline, built on demand


def _get_pipeline(lang_code: str):
    """
    Return (building if needed) the KPipeline for a language code.
    Lazy: `import kokoro` pulls in torch, so it happens on first use, not at
    module import. Device is pinned to CPU; older kokoro versions without a
    device parameter fall back to the default constructor (still CPU-safe on
    a machine where torch sees the GPU busy, but the explicit pin is the
    contract).
    """
    global _KPipeline
    if _KPipeline is None:
        from kokoro import KPipeline as _KP        # heavy import, deferred
        _KPipeline = _KP

    if lang_code not in _pipelines:
        print(f"  \u21bb Building Kokoro pipeline [{lang_code}] on {KOKORO_DEVICE}...", flush=True)
        try:
            _pipelines[lang_code] = _KPipeline(lang_code=lang_code,
                                               repo_id=KOKORO_REPO,
                                               device=KOKORO_DEVICE)
        except TypeError:
            # Older kokoro: no device kwarg. Accept default construction.
            _pipelines[lang_code] = _KPipeline(lang_code=lang_code,
                                               repo_id=KOKORO_REPO)
    return _pipelines[lang_code]

# =============================================================================
#  SECTION 7 — SYNTHESIS
# =============================================================================

def _clean_for_tts(text: str) -> str:
    """
    Text hygiene before synthesis: drop markdown-ish asterisks/underscores
    and collapse whitespace. Quotes, em-dashes and ellipses stay — Kokoro
    voices them naturally as pauses and emphasis.
    """
    text = text.replace("*", "").replace("_", " ")
    return " ".join(text.split())


def synthesize(text: str, resolved, out_path: str) -> str | None:
    """
    Text + ResolvedVoice (tensor built) -> WAV at out_path.
    Returns out_path on success, None on any failure — the voice worker
    forwards the item with wav=None and the presenter falls back to timed
    text reveal for that one item. One bad line never stalls the lane.
    """
    if not tts_available() or resolved is None or resolved.voice_tensor is None:
        return None
    text = _clean_for_tts(text)
    if not text:
        return None
    try:
        pipeline = _get_pipeline(resolved.lang_code)
        chunks = []
        # KPipeline yields (graphemes, phonemes, audio) per text chunk —
        # long narration comes out as several chunks to concatenate.
        for _, _, audio in pipeline(text, voice=resolved.voice_tensor,
                                    speed=resolved.final_speed):
            chunks.append(audio)
        if not chunks:
            return None
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        sf.write(out_path, np.concatenate(chunks), SAMPLE_RATE)
        return out_path
    except Exception as e:
        print(f"  \u2717 TTS failed ({e}) — item plays as text.", flush=True)
        return None

# =============================================================================
#  SECTION 8 — PLAYBACK  (blocking, skippable — presenter thread only)
# =============================================================================

def play_wav(path: str, stop_event=None) -> bool:
    """
    Play a WAV and block until it finishes OR stop_event is set (Skip button,
    session shutdown). Safe to call from the presenter thread — sounddevice
    is PortAudio-callback based and does not need the main thread.
    Returns True if playback completed naturally.
    """
    if sd is None or sf is None or not path or not os.path.isfile(path):
        return False
    try:
        data, sr = sf.read(path, dtype="float32")
        sd.play(data, sr)
        duration = len(data) / float(sr)
        deadline = time.time() + duration + 1.0       # small grace over exact length
        while time.time() < deadline:
            if stop_event is not None and stop_event.is_set():
                sd.stop()                             # skip: cut audio immediately
                return False
            stream = None
            try:
                stream = sd.get_stream()              # raises if nothing ever played
            except Exception:
                pass
            if stream is not None and not stream.active:
                return True                           # finished naturally
            time.sleep(0.05)                          # 20 Hz poll — cheap and responsive
        return True
    except Exception as e:
        print(f"  \u2717 Playback failed: {e}", flush=True)
        return False


def stop_audio() -> None:
    """Hard-stop any playing audio (shutdown path)."""
    if sd is not None:
        try:
            sd.stop()
        except Exception:
            pass

# =============================================================================
#  SECTION 9 — AVAILABILITY
# =============================================================================

def tts_available() -> bool:
    """True if the full voice stack (numpy, soundfile, sounddevice,
    kokoro_voices) imported. The kokoro package itself is checked lazily on
    first pipeline build — a missing kokoro fails resolve_cast() cleanly."""
    return _VOICES_OK and np is not None and sf is not None and sd is not None


def tts_status() -> str:
    """Human-readable availability reason for the GUI status strip."""
    return _TTS_STATUS if not tts_available() else "ok"
