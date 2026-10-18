"""
story_lab_director12.py  —  Story Lab v12  //  The conductor

PURPOSE
=======
Own the session: four worker threads, three queues, all pacing. GUI-free -
story_lab_gui12.py drives this through an `updaters` dict of callbacks, and
the module runs HEADLESS from a console for pipeline testing
(python story_lab_director12.py).

WHAT CHANGED FROM THE v11 DIRECTOR
==================================
1. ENGINE 12 (engine v11.6 promoted verbatim). Same call signatures, so no
   text call on the story thread moved, and with images off (the default
   when the config does not ask for them) this director runs v11's story
   thread line for line - test_engine12 drives it through the same checks.
2. AN IMAGE LANE IS BACK (it left in v10). story_lab_images12 renders:
     - two PORTRAITS at setup, from each character's extracted fp_image,
       through Workflow_portrait_api3.json;
     - one WIDE SCENE per round, from the round's opener via the engine's
       scene prompter, through Workflow_wide_api_3.json;
     - re-rolls on request (GUI buttons), and optional per-round portrait
       refreshes keyed to the resolution's mood (off by default).
   ComfyUI is found, or started headless, on the image thread itself, so a
   15-30 s server start never delays the story.
3. THE GPU IS HANDED OVER, NEVER SHARED. Measured 2026-10-16 on this 12 GB
   card: Rocinante resident at num_ctx 16384 holds 10.18 GB and the SDXL
   checkpoint 6.5 GB. Left side by side, Windows pages VRAM and both slow
   (portrait 9.4 -> 13.6 s, the next LLM call 1.4 -> 6.2 s); run truly at the
   same time they would thrash each other. So the image lane renders ONLY
   while the story thread has LENT it the card, at two fixed points:
       Y1  each round, after the opener, its scene prompt and the first
           IMAGE_YIELD_AFTER_TURN dialogue lines. Those lines are the buffer:
           the presenter is still reading the opener (and, in round 1, the
           world) while the batch renders, so the handoff hides in listening
           time. Round 1's batch is scene first, then the two portraits -
           the scene matters during the opener, the portraits only once the
           characters speak.
       Y2  while waiting for the player's event, if anything is queued (a
           re-roll). It ends when the queue drains, so the next round's first
           call finds the model warm.
   A lend = unload Ollama (1.2 s) -> render -> free ComfyUI (1.7 s) -> reload
   Ollama (7.7 s). The reload is done here, explicitly, with the engine's own
   num_ctx and num_gpu, so it is timed as "gpu -> text" instead of hiding
   inside the next dialogue line. GPU_HANDOFF = False skips both unloads and
   lets the driver page (cheaper per batch, measured above, but dependent on
   the driver's sysmem-fallback setting - a different machine may OOM).
4. SCENES ARE TAGGED WITH THEIR ROUND. Generation runs ahead of the presenter,
   so round 3's scene can finish while round 2 is still being read. The GUI
   holds it until the presenter reaches round 3's opener (scene_image carries
   the round number for exactly this).

5. v12.3 CINEMATIC SCENES (config scene_style = "cinematic"; default
   "classical" = everything above, unchanged). Both leads are drawn IN the
   round's scene by the Anima workflow (images12.WORKFLOW_CINEMATIC_FILE):
     - game start: the engine's cinematographer reads each lead's LOOKS
       (no clothes); the first portraits wait for round 1's clothes;
     - each round: the scene painter's three layers right after the opener
       (PLACE sees the setting in round 1 only, so it follows the player's
       event); at the Y1 lend point (so the moment includes the first
       dialogue lines) per lead WEARING (carried over, the player's own
       words last) and RIGHT NOW + OTHERS in view, cleaned and laid out by
       images12.build_cinematic_prompt. Y1 renders the scene alone (~40 s);
       portraits - the first pair, and any lead whose clothes really changed
       - are queued after it and render at the gate (Y2), which in a
       Cinematic game keeps rendering after the event is in while the
       presenter still has GATE_BACKLOG_S to play. Portraits are drawn by
       Anima too (WORKFLOW_CINE_PORTRAIT_FILE), in front of the round's place;
     - a server that cannot load the Anima workflow (images12.missing_models,
       checked once ComfyUI is up) turns the session back to Classical, with
       the reason in the status line.
   Measured choice of model and layout: loop_reports/v12_3_cinematic/.

6. v12.4 MUSIC (config music_enabled; default False = everything above,
   unchanged). Instrumental background music for each round, by ACE-Step
   1.5 in ComfyUI (story_lab_music12, the user's workflow JSON):
     - once per game the engine's composer names the SOUNDTRACK (one word
       from a closed list - or the player picked a style on the setup
       screen; if the composer names none, the world's own keywords pick);
     - each round, LAST - after all the round's text (opener, lines,
       resolution, memories) - the composer names the MOOD from the round's
       opener and resolution and the player's event, music12 writes the
       caption, bpm and key, and an END-OF-ROUND lend renders any pictures
       still queued and then the music (priority "music", after portraits).
       That lend is not cut short by the player's event: a round's music is
       always made. The track is put through the user's equaliser (always -
       no toggle) and only then handed to the GUI to play. Kokoro keeps
       playing the round meanwhile; then the game waits for the event. (The
       user's design, 2026-10-17 22:50: "the music comes last".)
     - the image lane is the ComfyUI lane: it starts when pictures OR music
       are on; a server that cannot load the music workflow turns music off
       (music_off) and leaves the pictures alone, and vice versa;
     - a music render may outlive a lend: it is allowed MUSIC_JOB_GRACE_S
       to finish (a picture gets IMAGE_JOB_GRACE_S) before the lane is
       declared wedged;
     - request_music_reroll(round) re-renders a round's music with the same
       caption and a new seed, like a scene re-roll.
   Playback (loop, cross-fade, volume, pause, EQ, ducking) is the GUI's,
   with music12.MusicPlayer. Study: loop_reports/v12_4_music/.

THE LANES
=========
  Story thread ──► voice queue ──► Voice worker ──► present queue ──► Presenter
  (Ollama, GPU)      (items)       (Kokoro, CPU)   (item + chunks)    (paced)
     │   ▲                                                               │
     │   └────────────────── injection event ◄───────────────────────────┘
     │
     └──► image jobs ──► Image worker (ComfyUI, GPU - only while LENT) ──► GUI
               ▲
               └── re-roll requests from the GUI

GENERATION RUNS AHEAD, PRESENTATION SETS THE PACE (v10/v11, unchanged). The
present queue is bounded (PREFETCH_CHUNKS) and carries three record kinds in
order: ("item", item), ("chunk", item, chunk), ("item_end", item).

THE INJECTION IS ALWAYS ARMED. The input unlocks when a round STARTS playing.

UPDATERS CONTRACT  (every callback is delivered on the GUI main thread via
app.after(0, ...); a missing key is simply skipped):
  status(text)                     one-line global status
  lane(name, state)                "story" | "voice" | "image" | "gpu"
  character_ready(slot, char)      slot "a"/"b", StoryCharacter extracted
  session_ready(char_a, char_b, setting)
  voices(summary_text)             resolved cast, one line per voice
  item(PresentationItem)           the item's text should appear NOW
  speak_start(seq, chunk_idx, seconds)   this sentence is sounding
  speak_end(seq, chunk_idx)              it has finished
  item_done(seq)                   all chunks of the item are done
  memories(round_num, mem_a, mem_b)  the keeper outputs (observation drawer)
  staged(round_num, raw, staged, kept_raw, sent)  the conditioner's rewrite
  timing(label, seconds)           per-call durations (observation drawer)
  await_injection(round_num)       input armed; event will shape round_num+1
  injection_accepted(text)         event locked in for the next round
  images_ready(summary)            v12: ComfyUI up, workflows usable
  images_off(reason)               v12: no images this session, and why
  portrait(slot, path, prompt)     v12: slot "a"/"b", a finished portrait
  scene_image(round_num, path, prompt, take)   v12: a finished wide scene;
                                   take 0 = first render, 1+ = re-rolls
  scene_prompt(round_num, prompt)  v12: the scene was QUEUED (GUI shows
                                   "rendering round N")
  music_prompt(round_num, body)    v12.4: a round's music was QUEUED
  music(round_num, path, body, take)  v12.4: a finished track (FLAC); take
                                   0 = first render, 1+ = regenerated
  music_off(reason)                v12.4: no music this session, and why
  error(message)
  done()                           presenter drained after stop

CONFIG DICT  (built by the GUI's setup screen):
  world_desc, char_a_inputs, char_b_inputs, prior_history, narrator_gender,
  narrator_accent, voice_enabled, beats_to_narrator, turns_per_round, rounds,
  show_staging                     all as v11
  images_enabled      bool   v12: the image lane (default False - a config
                             that does not ask for images gets v11's story)
  auto_launch_comfyui bool   v12: start ComfyUI headless if none is running
                             (default True)
  portrait_refresh    bool   v12: re-render both portraits each round with
                             the resolution's mood (default False)
  music_enabled       bool   v12.4: background music (default False)
  music_style         str    v12.4: "auto" (the composer picks from the
                             story) or a story_lab_music12.PALETTES key
  music_seconds       float  v12.4: track length (default music12.MUSIC_SECONDS)
  music_codes         bool   v12.4: ACE-Step's audio-code LM (default True,
                             as the user's workflow; False is much faster)

THREAD SAFETY RULES (proven in v3/v5, kept):
  - Widgets are touched ONLY via app.after(0, ...) - _emit() enforces this.
  - Ollama has exactly ONE consumer (the story thread).
  - ComfyUI has exactly ONE consumer (the image worker), and it renders only
    while _lent is True. _lent is set and cleared only by the story thread,
    under _jobs_cv, so the GPU has one owner at every instant.
  - The voice worker is a SINGLE thread, so item and chunk order is preserved.
"""

import os
import time
import queue
import random
import threading
import traceback
import dataclasses
from datetime import datetime

import requests

import story_lab_engine12 as engine
from story_lab_engine12 import (
    StoryCharacter,
    start_ollama,
    extract_character, generate_setting, generate_opener,
    generate_dialogue_turn, generate_resolution, condition_event,
    generate_character_memory, frame_injection, compose_event,
    generate_scene_layers, SCENE_EXAMPLE,
    generate_music_field,
    make_run_dir, write_run_file, append_log, save_characters_json,
)
import story_lab_tts10 as tts
import story_lab_images12 as images
import story_lab_music12 as music
import story_lab_saves12 as saves

# =============================================================================
#  SECTION 1 - TUNABLES
# =============================================================================

TURNS_PER_ROUND = 6            # dialogue lines per round (3 exchanges)

READ_SECONDS_PER_WORD = 0.32   # unvoiced pacing (~185 wpm), per chunk
READ_SECONDS_MIN      = 0.9

PREFETCH_CHUNKS = 12           # how far the voice worker may run ahead

# v12 image lane
IMAGE_YIELD_AFTER_TURN = 2     # Y1: lend the GPU after this many lines. Two
                               # lines (~16 s of speech) on top of the opener
                               # cover a three-image batch plus the handoff.
IMAGE_LEND_MAX_S  = 90         # a lend ends after this even with jobs left
IMAGE_JOB_GRACE_S = 45         # then wait this long for the job in flight
MUSIC_JOB_GRACE_S = 240        # v12.4: a music render may take longer (70 s of
                               # music: ~25 s on this card at full clock, ~2 min
                               # when the laptop caps the GPU - measured
                               # 2026-10-17); it is allowed to finish
MUSIC_LEND_MAX_S = 900         # v12.4: the end-of-round lend runs until the
                               # music is made (pictures first); this only
                               # bounds a machine that never finishes
SLOW_ALIVE_CHECK_S = 10        # v12.4: past its grace, a job on a server that
                               # still answers /queue is SLOW, not hung - the
                               # lend waits for it, asking again this often
SLOW_JOB_MAX_S = 660           # ...but never longer than this from its start
                               # (the music submit gives up at 600 s, pictures
                               # at 300 s - the job then ends by itself)
SLOW_RENDER_S = {"scene": 60, "portrait": 60, "music": 90}   # usually 10-30 s
                               # (pictures), ~25 s (70 s of music); past these
                               # the player is told once that the machine is slow
VOICE_RTF_MIN = 1.0            # Kokoro slower than real time stutters: warn once
VOICE_RTF_AFTER_S = 20.0       # ...after this much speech has been made
GATE_BACKLOG_S    = 30         # v12.3 Cinematic: the gate keeps rendering while
                               # the presenter has this much left to play (one
                               # Anima portrait ~25 s; the hand-back ~7 s)
GPU_HANDOFF       = True       # unload the other model at every handover
OLLAMA_URL        = "http://127.0.0.1:11434"   # 127.0.0.1, not localhost:
                               # ~2 s per request on this machine otherwise

STALL_REPORT_S    = 1.0        # presenter waits longer than this for content
                               # (story NOT at the event gate) are written to
                               # timings.txt as "presenter starved"

_PRIORITY = {"reroll": 0, "scene": 1, "portrait": 2, "music": 3}   # v12.4: music last

_SENTINEL = object()           # shutdown marker, rippled down the lanes

# =============================================================================
#  SECTION 2 - PRESENTATION ITEM  (unchanged from v11)
# =============================================================================

@dataclasses.dataclass
class PresentationItem:
    """
    One unit of the feed - a narration block, a dialogue line, or the
    player's event echoed back.

      kind:      "narration" (setting/opener/resolution), "line" (dialogue),
                 "event" (the player's injection), "staged" (the
                 conditioner's rewrite of it, unvoiced - v11), "system"
      voice_key: which cast voice speaks it - "narrator", "a", "b", or ""
      phase:     "setting" | "opener" | "resolution" | "" - and for a
                 "staged" item, "staged" or "kept_raw" (the fallback)
      chunks:    the sentence split, produced at push time
    """
    seq:       int
    kind:      str
    round_num: int
    speaker:   str
    text:      str
    phase:     str = ""
    voice_key: str = ""
    chunks:    list = dataclasses.field(default_factory=list)

# =============================================================================
#  SECTION 3 - GPU HANDOVER HELPERS  (Ollama side; ComfyUI side is images12)
# =============================================================================

def ollama_unload(timeout: float = 20.0) -> float:
    """
    Evict every loaded Ollama model and wait until /api/ps is empty. Reads
    the names from /api/ps, because keep_alive=0 with the namespaced MODEL
    string is silently a no-op (the engine's own unload_ollama() learned
    that; this is the same rule over 127.0.0.1 and without the `ollama ps`
    subprocess). Returns seconds taken.
    """
    t0 = time.time()
    try:
        models = requests.get(f"{OLLAMA_URL}/api/ps", timeout=3).json().get("models", [])
        for m in models:
            requests.post(f"{OLLAMA_URL}/api/generate",
                          json={"model": m["name"], "keep_alive": 0}, timeout=15)
        while models and time.time() - t0 < timeout:
            if not requests.get(f"{OLLAMA_URL}/api/ps", timeout=3).json().get("models"):
                break
            time.sleep(0.2)
    except Exception as e:
        print(f"  ⚠ Ollama unload: {e}", flush=True)
    return time.time() - t0


def ollama_prewarm() -> float:
    """
    Load the engine's model back onto the GPU with the engine's num_ctx and
    num_gpu - the runner is reused only if those match, so a bare load would
    be thrown away by the next real call. Empty prompt = load only.
    """
    t0 = time.time()
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": engine.MODEL, "prompt": "",
                            "options": {"num_ctx": engine.NUM_CTX,
                                        "num_gpu": engine.NUM_GPU}},
                      timeout=180)
    except Exception as e:
        print(f"  ⚠ Ollama prewarm: {e}", flush=True)
    return time.time() - t0

# =============================================================================
#  SECTION 4 - DIRECTOR
# =============================================================================

class Director:
    """One instance per session. Construct, then start(); stop() to end."""

    def __init__(self, app_ref, updaters: dict, config: dict, resume: dict = None):
        self.app      = app_ref            # anything with .after(ms, fn)
        self.updaters = updaters
        self.cfg      = config
        # v12.2: resume = {"run_dir", "snapshot"} from story_lab_saves12 -
        # the game continues at the gate after the snapshot's round.
        self.resume   = resume
        seed = (resume["snapshot"].get("game_seed") if resume else None) \
            or config.get("game_seed")
        self.game_seed = int(seed) if seed not in (None, "") else random.randint(1, 999_999_999)
        self.round_done = 0                # last round whose memories are written
        self._ckpt_lock = threading.Lock()
        self._rounds = []                  # per-round record (the save's history)
        self._scene_log = {}               # round -> {positive, negative, body, takes}
        self._portrait_log = []            # [{slot, file, seed, interact, round, body}]
        self._state = {}                   # memories + resolution at the last gate
        self._calls_at_gate = 0            # seed stream position at the last gate
        self._chars, self._setting = None, ""
        self._voice_summary = ""
        self._current_job = None
        try:
            _api = images.load_workflow(images.WORKFLOW_SCENE_FILE)
            self._ckpt_name = next((n["inputs"]["ckpt_name"] for n in _api.values()
                                    if "ckpt_name" in n["inputs"]), None)
        except Exception:
            self._ckpt_name = None

        # --- lanes and queues ---
        self._voice_q   = queue.Queue()                       # story -> voice
        self._present_q = queue.Queue(maxsize=PREFETCH_CHUNKS)  # voice -> presenter

        # --- coordination events ---
        self._stop      = threading.Event()
        self._injection = threading.Event()
        self._skip      = threading.Event()
        self._advance   = threading.Event()
        self._pause     = threading.Event()   # SET = running; cleared = paused
        self._pause.set()

        # --- v12 image lane ---
        self.images_wanted = bool(config.get("images_enabled", False))
        self.server        = None              # ComfyUI URL once it is up
        self._jobs_cv      = threading.Condition()
        self._jobs         = []                # pending jobs, priority-sorted
        self._lent         = False             # the GPU is lent to images
        self._busy         = False             # a job is rendering
        self._images_live  = False             # server up, workflows usable
        self._images_off   = False             # switched off for the session
        self._gpu_owner    = "text"
        self._scene_prompts = {}               # round -> (positive, negative, body)
        self._portrait_prompts = {}            # slot -> (positive, negative, body)
        self._takes        = {}                # round -> re-rolls so far
        # v12.1: the Picture-prompts wrappers (images12.PROMPT_FIELDS per kind)
        self.prompt_settings = (config.get("image_prompts")
                                or images.load_prompt_settings())
        for _kind in ("cinematic", "medium"):          # an older save's settings
            if _kind not in self.prompt_settings:
                self.prompt_settings = dict(self.prompt_settings,
                                            **{_kind: images.default_prompt_settings()[_kind]})
        self._names        = []                # the leads' names, for hygiene
        # v12.3: "classical" = v12.1's characterless scene (exactly v12.2);
        # "cinematic" = both leads drawn in the scene (Anima workflow)
        # v12.4: "medium" = both leads drawn by NovaFurry - Cinematic's story
        # reading (looks, clothes, doing, others), Classical's workflows
        self.scene_style   = (config.get("scene_style")
                              if config.get("scene_style") in ("cinematic", "medium")
                              else "classical")
        self._cine_looks   = {}                # slot -> cleaned looks (game start)
        self._cine_wearing = {}                # slot -> what they wear now
        self._portrait_wearing = {}            # slot -> wearing of the last portrait
        self._portraits_queued = False         # the game's first portraits
        self._scene_kinds  = {}                # round -> "classical" | "cinematic"
        self._cine_layers  = {}                # round -> painter layers (opener time)
        self._cine_backdrop = ("", "")         # (place, light) of the last cinematic scene
        self._player_text  = ""                # the player's own words for this round
        self._backlog_words = 0                # pushed but not yet played (words)
        self._portrait_kinds = {}              # slot -> "classical" | "cinematic"
        # --- v12.4 music ---
        self.music_wanted  = bool(config.get("music_enabled", False))
        self.music_style   = str(config.get("music_style") or "auto")
        self.music_seconds = float(config.get("music_seconds") or music.MUSIC_SECONDS)
        self.music_codes   = bool(config.get("music_codes", True))
        self._music_off    = False             # music switched off for the session
        self._soundtrack   = ""                # the game's palette key ("" = default)
        self._soundtrack_chosen = False        # chosen once per game (even if "")
        self._music_prompts = {}               # round -> music12 prompt dict
        self._music_log    = {}                # round -> {body, takes: [{file, seed, take}]}
        self._job_t0       = 0.0               # when the job in flight started
        # v12.4 portraits that follow the story (Classical) - all from data the
        # game already has, no extra model call:
        self._classic_wearing  = {}            # slot -> clothes the player's words gave
        self._classic_backdrop = ""            # the last scene's place + light
        self._classic_mood     = {}            # slot -> the last refresh's expression
        self._portrait_body_last = {}          # slot -> body of the last portrait queued
        self._warned_slow  = False             # "renders are slow" said once
        self._voice_made_s = 0.0               # speech synthesised (s) ...
        self._voice_took_s = 0.0               # ... and the time it took
        self._warned_voice = False

        # --- mutable session state ---
        self._injection_text  = ""
        self._injection_armed = False
        self._at_gate         = False         # story is waiting for the event
        self.voice_enabled    = bool(config.get("voice_enabled", True))
        self.mode             = "auto"
        self._seq             = 0
        self._cast            = {}
        self._skip_seq        = None
        self.run_dir          = None
        self._threads         = []

    # =========================================================================
    #  LIFECYCLE
    # =========================================================================

    def start(self) -> None:
        lanes = [("story", self._story_thread), ("voice", self._voice_worker),
                 ("presenter", self._presenter)]
        if self.images_wanted or self.music_wanted:     # v12.4: the ComfyUI lane
            lanes.append(("image", self._image_worker))
        for name, target in lanes:
            t = threading.Thread(target=target, name=f"director-{name}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        """End the session. Safe to call more than once."""
        self._stop.set()
        self._injection.set()
        self._skip.set()
        self._advance.set()
        self._pause.set()
        self._voice_q.put(_SENTINEL)
        with self._jobs_cv:
            self._jobs.clear()
            self._jobs_cv.notify_all()
        tts.stop_audio()

    # =========================================================================
    #  GUI-FACING CONTROLS  (called from the main thread)
    # =========================================================================

    def submit_injection(self, text: str) -> bool:
        text = text.strip()
        if not text or not self._injection_armed:
            return False
        self._injection_armed = False
        self._injection_text  = text
        self._injection.set()
        self._emit("injection_accepted", text)
        return True

    def continue_without_event(self) -> bool:
        if not self._injection_armed:
            return False
        self._injection_armed = False
        self._injection_text  = ""
        self._injection.set()
        self._emit("injection_accepted", "")
        return True

    def set_mode(self, mode: str) -> None:
        self.mode = "manual" if str(mode).lower().startswith("man") else "auto"
        self._advance.set()

    def set_voice(self, enabled: bool) -> None:
        self.voice_enabled = bool(enabled)
        self._emit("lane", "voice", "on" if enabled and self._cast else "off")

    def skip_current(self) -> None:
        self._skip.set()

    def advance(self) -> None:
        self._advance.set()

    def toggle_pause(self) -> bool:
        if self._pause.is_set():
            self._pause.clear()
            self._emit("status", "Paused - the current sentence finishes, then holds.")
            return True
        self._pause.set()
        self._emit("status", "Resumed.")
        return False

    def request_scene_reroll(self, round_num: int) -> bool:
        """
        Re-render a round's scene with the same prompt and a fresh seed. It is
        QUEUED: it renders at the next point the story lends the GPU - at once
        if the story is waiting for your event, otherwise within the round.
        """
        stored = self._scene_prompts.get(round_num)
        if not stored or not self._images_live:
            return False
        positive, negative, body = stored
        self._takes[round_num] = self._takes.get(round_num, 0) + 1
        take = self._takes[round_num]
        self._queue_image({"kind": "scene", "round": round_num, "prompt": positive,
                           "negative": negative, "body": body, "take": take,
                           "made_round": round_num,
                           "workflow": self._scene_kinds.get(round_num, "classical"),
                           "seed": self._image_seed("scene", round_num, take),
                           "priority": _PRIORITY["reroll"]})
        return True

    def request_portrait_reroll(self, slot: str) -> bool:
        """
        A new portrait of `slot`. v12.4: built from the story as it is NOW
        (Classical: the clothes the player's words gave, the last scene's
        place; Cinematic: the current clothes and backdrop) plus a different
        pose / expression / light per take - a new seed of the same prompt
        drew the same face, pose and hall (the user's game: 13 portraits, one
        look; "it does not update with reroll").
        """
        stored = self._portrait_prompts.get(slot)
        if not stored or not self._images_live:
            return False
        positive, negative, body = stored
        self._takes[slot] = self._takes.get(slot, 0) + 1
        interact = f"reroll{self._takes[slot]}"
        variation = images.reroll_variation(self._takes[slot])
        if self._chars:
            char = self._chars[0 if slot == "a" else 1]
            if self._portrait_kinds.get(slot) == "medium" and slot in self._cine_looks:
                body = images.portrait_body(char, "", self._cine_wearing.get(slot, ""),
                                            images.join_prompt(*self._cine_backdrop),
                                            variation)
                positive, negative = images.wrap_prompt("portrait", body,
                                                        self.prompt_settings)
            elif self._portrait_kinds.get(slot) == "cinematic" and slot in self._cine_looks:
                place, light = self._cine_backdrop
                built = images.build_cine_portrait_prompt(
                    char, self._cine_looks[slot], self._cine_wearing.get(slot, ""),
                    place, light, "", self.prompt_settings)
                positive = images.join_prompt(built["positive"], variation)
                negative, body = built["negative"], built["body"] + f" / {variation}"
            else:
                body = images.portrait_body(char, self._classic_mood.get(slot, ""),
                                            self._classic_wearing.get(slot, ""),
                                            self._classic_backdrop, variation)
                positive, negative = images.wrap_prompt("portrait", body,
                                                        self.prompt_settings)
        self._queue_image({"kind": "portrait", "slot": slot, "prompt": positive,
                           "negative": negative, "body": body, "interact": interact,
                           "workflow": self._portrait_kinds.get(slot, "classical"),
                           "made_round": self.round_done,
                           "seed": self._image_seed("portrait", slot, interact),
                           "priority": _PRIORITY["reroll"]})
        return True

    def request_music_reroll(self, round_num: int) -> bool:
        """v12.4: the round's music again - same caption, a new seed. Queued
        like a scene re-roll (renders at the next lend)."""
        prompt = self._music_prompts.get(round_num)
        if not prompt or not self._images_live or self._music_off:
            return False
        key = f"m{round_num}"
        self._takes[key] = self._takes.get(key, 0) + 1
        take = self._takes[key]
        self._queue_image({"kind": "music", "round": round_num, "prompt": prompt,
                           "take": take, "made_round": round_num,
                           "codes": self.music_codes,
                           "seed": self._image_seed("music", round_num, take),
                           "priority": _PRIORITY["reroll"]})
        self._emit("music_prompt", round_num, prompt["body"])
        return True

    # =========================================================================
    #  INTERNALS - emit / push / timing
    # =========================================================================

    def _emit(self, name: str, *args) -> None:
        fn = self.updaters.get(name)
        if fn is None:
            return
        self.app.after(0, lambda f=fn, a=args: f(*a))

    def _lane(self, lane: str, state: str) -> None:
        self._emit("lane", lane, state)

    def _push(self, kind: str, text: str, speaker: str = "",
              voice_key: str = "", phase: str = "", round_num: int = 0) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._seq += 1
        self._backlog_words += len(text.split())      # v12.3: unplayed words
        beats_key = ("narrator" if (self.cfg.get("beats_to_narrator")
                                    and voice_key in ("a", "b")) else None)
        chunks = tts.split_utterance(text, voice_key=voice_key,
                                     beats_voice_key=beats_key)
        self._voice_q.put(PresentationItem(
            seq=self._seq, kind=kind, round_num=round_num, speaker=speaker,
            text=text, phase=phase, voice_key=voice_key, chunks=chunks))

    def _put_present(self, record) -> bool:
        while not self._stop.is_set():
            try:
                self._present_q.put(record, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    def _record_timing(self, label: str, dt: float) -> None:
        self._emit("timing", label, dt)
        if self.run_dir:
            try:
                with open(os.path.join(self.run_dir, "timings.txt"),
                          "a", encoding="utf-8") as f:
                    f.write(f"{label}\t{dt:.1f}s\n")
            except Exception:
                pass

    def _timed(self, label: str, fn, *args, **kwargs):
        t0 = time.time()
        result = fn(*args, **kwargs)
        self._record_timing(label, time.time() - t0)
        return result

    def _sleep_interruptible(self, seconds: float) -> None:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            if self._skip.is_set() or self._stop.is_set():
                return
            time.sleep(0.02)

    # =========================================================================
    #  v12 - IMAGE JOBS AND THE GPU LEND
    # =========================================================================

    def _queue_image(self, job: dict) -> None:
        if self._images_off or self._stop.is_set():
            return
        if job.get("kind") == "music":                 # v12.4
            if not self.music_wanted or self._music_off:
                return
        elif not self.images_wanted:
            return
        with self._jobs_cv:
            self._jobs.append(job)
            self._jobs.sort(key=lambda j: j.get("priority", 9))   # stable
            self._jobs_cv.notify_all()

    def _jobs_pending(self) -> bool:
        with self._jobs_cv:
            return self._images_live and bool(self._jobs)

    def _gpu_to_images(self) -> None:
        if GPU_HANDOFF:
            self._record_timing("gpu text->images", ollama_unload())
        self._gpu_owner = "images"
        self._lane("gpu", "images")

    def _gpu_to_text(self) -> None:
        if GPU_HANDOFF:
            t0 = time.time()
            if self.server:
                images.free_vram(self.server)
            if not self._stop.is_set():                # v12.4: not after END SESSION
                ollama_prewarm()
            self._record_timing("gpu images->text", time.time() - t0)
        self._gpu_owner = "text"
        self._lane("gpu", "text")

    def _lend_gpu(self, where: str, until=None, max_s: float = None) -> None:
        """
        Lend the GPU to the image lane until its queue is empty, `until()`
        turns true, or IMAGE_LEND_MAX_S passes - then take it back. Called
        only from the story thread, only between engine calls. A job that is
        still rendering when the lend ends is allowed to finish (a ComfyUI
        job cannot be paused). v12.4: one that outlives its grace is asked
        about: if the server still answers and the job is still running it is
        SLOW, and the lend waits for it (_wait_slow_job); only a server that
        stops answering is interrupted and switched off for the session. The
        user's first music playtest (2026-10-17) had a power-capped GPU: one
        SDXL scene took 136 s, the old rule called that hung at 135 s, and
        pictures AND music went off for the whole game.
        """
        if not self._jobs_pending() or self._stop.is_set():
            return
        t0 = time.time()
        self._lane("story", f"GPU lent to images ({where})")
        self._gpu_to_images()
        with self._jobs_cv:
            self._lent = True
            self._jobs_cv.notify_all()
            deadline = time.time() + (IMAGE_LEND_MAX_S if max_s is None else max_s)
            while (not self._stop.is_set() and (self._jobs or self._busy)
                   and time.time() < deadline and not (until and until())):
                self._jobs_cv.wait(0.2)
            self._lent = False
            self._jobs_cv.notify_all()
            in_flight = (self._current_job or {}).get("kind")
            grace = time.time() + (MUSIC_JOB_GRACE_S if in_flight == "music"
                                   else IMAGE_JOB_GRACE_S)
            while self._busy and not self._stop.is_set() and time.time() < grace:
                self._jobs_cv.wait(0.2)
            wedged = self._busy
        if wedged and not self._stop.is_set():
            wedged = not self._wait_slow_job(in_flight)
        if wedged:
            try:
                requests.post(f"{self.server}/interrupt", timeout=5)
            except Exception:
                pass
            self._switch_images_off("ComfyUI stopped answering - images off "
                                    "for the rest of this session")
        self._gpu_to_text()
        self._record_timing(f"images lend {where}", time.time() - t0)

    def _comfy_alive(self) -> bool:
        """The server answers /queue and is running a job (v12.4)."""
        try:
            q = requests.get(f"{self.server}/queue", timeout=5).json()
            return bool(q.get("queue_running")) or self._busy
        except Exception:
            return False

    def _wait_slow_job(self, kind) -> bool:
        """
        v12.4: wait for a job that outlived its grace while the server says it
        is still working on it. True = it finished; False = the server stopped
        answering, or SLOW_JOB_MAX_S passed since the job started.
        """
        label = {"scene": "the scene", "portrait": "a portrait",
                 "music": "the music"}.get(kind, "a picture")
        if not self._comfy_alive():                    # dead now: no waiting
            return False
        self._emit("status", f"ComfyUI is slow on this machine - {label} has taken "
                             f"{time.time() - self._job_t0:.0f} s so far. Waiting for it.")
        self._warn_slow(kind, time.time() - self._job_t0)
        last_check = time.time()
        while not self._stop.is_set():
            with self._jobs_cv:
                if not self._busy:
                    return True
                self._jobs_cv.wait(0.5)
                if not self._busy:
                    return True
            if time.time() - self._job_t0 > SLOW_JOB_MAX_S:
                return False
            if time.time() - last_check >= SLOW_ALIVE_CHECK_S:
                last_check = time.time()
                if not self._comfy_alive():
                    return False
                self._lane("story", f"waiting for slow ComfyUI ({label}, "
                                    f"{time.time() - self._job_t0:.0f} s)")
        return True

    def _warn_slow(self, kind, seconds: float) -> None:
        """Say ONCE per session that renders are far slower than normal."""
        if self._warned_slow or seconds < SLOW_RENDER_S.get(kind, 60):
            return
        self._warned_slow = True
        msg = (f"Pictures/music are rendering very slowly ({kind} {seconds:.0f} s; "
               f"usually 10-30 s). The GPU looks power-limited - check the laptop's "
               f"performance mode (Gigabyte Control Center) and that the main charger "
               f"is plugged in.")
        print(f"  \u26a0 {msg}", flush=True)
        self._emit("status", msg)
        self._record_timing(f"SLOW {kind}", seconds)

    def _switch_images_off(self, reason: str) -> None:
        with self._jobs_cv:
            self._images_live = False
            self._images_off = True
            self._jobs.clear()
            self._jobs_cv.notify_all()
        self._lane("image", "off")
        self._emit("images_off", reason)
        if self.music_wanted and not self._music_off:   # v12.4: same server
            self._music_off = True
            self._emit("music_off", reason)
        print(f"  ⚠ {reason}", flush=True)

    def _switch_music_off(self, reason: str) -> None:
        """v12.4: music off for the session; the pictures go on."""
        with self._jobs_cv:
            self._music_off = True
            self._jobs = [j for j in self._jobs if j.get("kind") != "music"]
            self._jobs_cv.notify_all()
        self._emit("music_off", reason)
        print(f"  ⚠ {reason}", flush=True)

    def _image_worker(self) -> None:
        """
        LANE 4. Brings ComfyUI up, then renders queued jobs - only while the
        story thread has lent it the GPU. One job at a time, in priority order.
        """
        try:
            self._start_images()
        except Exception as e:
            traceback.print_exc()
            self._switch_images_off(f"image lane failed to start: {e}")
        while True:
            with self._jobs_cv:
                while not self._stop.is_set() and not (self._lent and self._jobs):
                    self._jobs_cv.wait(0.2)
                if self._stop.is_set():
                    break
                job = self._jobs.pop(0)
                self._busy = True
                self._current_job = job        # v12.2: a save mid-render keeps it
                self._job_t0 = time.time()
            try:
                self._render(job)
            except Exception as e:                    # one bad job never kills the lane
                print(f"  ✗ Image job failed: {e}", flush=True)
            finally:
                with self._jobs_cv:
                    self._busy = False
                    self._current_job = None
                    self._jobs_cv.notify_all()
                self._lane("image", "ready" if self._images_live else "off")
        self._lane("image", "ended")

    def _start_images(self) -> None:
        self._lane("image", "checking the workflows")
        summaries = []
        for path in ((images.WORKFLOW_PORTRAIT_FILE, images.WORKFLOW_SCENE_FILE)
                     if self.images_wanted else ()):
            try:
                images.load_workflow(path)
            except images.WorkflowError as e:
                if not self.music_wanted:
                    self._switch_images_off(f"workflow unusable - {e}")
                    return
                self.images_wanted = False             # v12.4: music goes on
                self._emit("images_off", f"workflow unusable - {e}")
                break
            summaries.append(images.workflow_summary(path))
        if self.images_wanted and self.scene_style == "cinematic":
            summaries.append(images.workflow_summary(images.WORKFLOW_CINEMATIC_FILE))
        if self.music_wanted:                          # v12.4
            try:
                music.load_music_workflow()
                summaries.append("music · " + os.path.basename(music.WORKFLOW_MUSIC_FILE))
            except music.MusicWorkflowError as e:
                self._switch_music_off(f"music off - {e}")
        if not self.images_wanted and (not self.music_wanted or self._music_off):
            self._switch_images_off("nothing for ComfyUI to do this session")
            return
        self._lane("image", "finding ComfyUI")
        log_path = os.path.join(engine.RUNS_DIR, "comfyui_server.log")
        # v12.3: up to 6 minutes - a ComfyUI's first start after an install or
        # an update can take 5+ (measured 5.5 min, then 30 s); this runs on the
        # image thread, so the story is not held up meanwhile.
        self.server = images.ensure_comfyui(
            auto_launch=self.cfg.get("auto_launch_comfyui", True),
            timeout=360, log_path=log_path,
            status=lambda t: self._lane("image", t))
        if self.server is None:
            self._switch_images_off("ComfyUI not found or did not start "
                                    f"(see {log_path})")
            return
        # v12.3: a Cinematic game needs a server that can load the Anima
        # workflow (ComfyUI 0.30+, the model files); otherwise its scenes
        # fall back to Classical for the session, and the reason is shown.
        if self.images_wanted and self.scene_style == "cinematic":
            missing = sorted(set(
                images.missing_models(self.server, images.WORKFLOW_CINEMATIC_FILE)
                + images.missing_models(self.server, images.WORKFLOW_CINE_PORTRAIT_FILE)))
            if missing:
                self.scene_style = "classical"
                msg = ("Cinematic scenes unavailable on this ComfyUI ("
                       + "; ".join(missing[:3]) + ") - using Classical scenes")
                print(f"  ⚠ {msg}", flush=True)
                self._emit("status", msg)
        # v12.4: an older ComfyUI has no ACE-Step 1.5 nodes; a fresh install
        # may not have the four model files
        if self.music_wanted and not self._music_off:
            missing = music.missing_models(self.server)
            if missing:
                self._switch_music_off("music unavailable on this ComfyUI ("
                                       + "; ".join(missing[:3]) + ")")
        # A server left holding a model (a previous session, the Desktop app)
        # would squeeze Rocinante off the card on its first load.
        images.free_vram(self.server)
        with self._jobs_cv:
            self._images_live = not self._stop.is_set()
            self._jobs_cv.notify_all()
        self._lane("image", "ready")
        self._emit("images_ready", f"{self.server}\n" + "\n".join(summaries))

    def _render(self, job: dict) -> None:
        if not self.run_dir:
            return
        if job["kind"] == "scene":
            r, take = job["round"], job.get("take", 0)
            label = f"scene r{r}" + (f" take {take + 1}" if take else "")
            t0 = time.time()
            path, seed = images.generate_scene_image(
                self.server, job["prompt"], r, self.run_dir, take=take,
                negative=job.get("negative"), seed=job.get("seed"),
                workflow_file=(images.WORKFLOW_CINEMATIC_FILE
                               if job.get("workflow") == "cinematic" else None),
                progress=lambda el: self._lane("image", f"{label}: {el:.0f}s"))
            self._record_timing(f"image {label}", time.time() - t0)
            self._warn_slow("scene", time.time() - t0)
            if path:
                with self._ckpt_lock:              # v12.2: into the save's record
                    s = self._scene_log.setdefault(r, {
                        "positive": job["prompt"], "negative": job.get("negative"),
                        "body": job.get("body", ""), "takes": []})
                    s["takes"].append({"file": os.path.basename(path), "seed": seed,
                                       "take": take})
                self._emit("scene_image", r, path, job.get("body", job["prompt"]), take)
        elif job["kind"] == "music":                   # v12.4
            r, take = job["round"], job.get("take", 0)
            label = f"music r{r}" + (f" take {take + 1}" if take else "")
            t0 = time.time()
            raw, seed = music.generate_music(
                self.server, job["prompt"], self.run_dir,
                music.raw_filename(r, take), seed=job.get("seed"),
                codes=job.get("codes", True),
                progress=lambda el: self._lane("image", f"{label}: {el:.0f}s"))
            self._record_timing(label, time.time() - t0)
            self._warn_slow("music", time.time() - t0)
            path = None
            if raw:                                    # always the user's EQ chain
                t1 = time.time()
                try:
                    path = music.equalise_file(
                        raw, os.path.join(self.run_dir, music.music_filename(r, take)))
                    self._record_timing(f"{label} equaliser", time.time() - t1)
                except Exception as e:
                    print(f"  \u2717 equaliser failed ({e}) - track skipped", flush=True)
            if path:
                with self._ckpt_lock:
                    m = self._music_log.setdefault(r, {"body": job["prompt"]["body"],
                                                       "takes": []})
                    m["takes"].append({"file": os.path.basename(path), "seed": seed,
                                       "take": take})
                self._emit("music", r, path, job["prompt"]["body"], take)
        else:
            slot = job["slot"]
            label = f"portrait {slot}"
            t0 = time.time()
            path, seed = images.generate_portrait_image(
                self.server, job["prompt"], slot, job.get("interact", 0),
                self.run_dir, negative=job.get("negative"), seed=job.get("seed"),
                workflow_file=(images.WORKFLOW_CINE_PORTRAIT_FILE
                               if job.get("workflow") == "cinematic" else None),
                progress=lambda el: self._lane("image", f"{label}: {el:.0f}s"))
            self._record_timing(f"image {label}", time.time() - t0)
            self._warn_slow("portrait", time.time() - t0)
            if path:
                with self._ckpt_lock:
                    self._portrait_log.append({
                        "slot": slot, "file": os.path.basename(path), "seed": seed,
                        "interact": job.get("interact", 0),
                        "round": job.get("made_round", 0), "body": job.get("body", "")})
                self._emit("portrait", slot, path, job["prompt"])
        # v12.2: a picture of a round that is already saved updates the save -
        # after the job stops counting as in flight, or the save would list a
        # finished picture as pending and a load would render it twice
        if path and job.get("made_round", 0) <= self.round_done:
            with self._jobs_cv:
                self._current_job = None
            self._write_checkpoint()

    def _queue_portraits(self, char_a, char_b, interact, mood: str = "",
                         slots=("a", "b"), made_round=None, skip_same=False) -> None:
        """v12.4: skip_same (living portraits) - a lead whose portrait text has
        not changed since the last one is not drawn again."""
        self._portraits_queued = True
        for slot, char in (("a", char_a), ("b", char_b)):
            if slot not in slots:
                continue
            workflow = "classical"
            if self.scene_style == "cinematic" and slot in self._cine_looks:
                # v12.3: drawn by Anima, as the story has them now, in front
                # of where they are now
                place, light = self._cine_backdrop
                built = images.build_cine_portrait_prompt(
                    char, self._cine_looks[slot], self._cine_wearing.get(slot, ""),
                    place, light, mood, self.prompt_settings)
                positive, negative, body = built["positive"], built["negative"], built["body"]
                self._portrait_wearing[slot] = self._cine_wearing.get(slot, "")
                workflow = "cinematic"
            elif self.scene_style == "medium" and slot in self._cine_looks:
                # v12.4: NovaFurry, as the story has them now, in front of where
                # they are now (the Classical portrait workflow)
                body = images.portrait_body(char, mood, self._cine_wearing.get(slot, ""),
                                            images.join_prompt(*self._cine_backdrop))
                positive, negative = images.wrap_prompt("portrait", body,
                                                        self.prompt_settings)
                self._portrait_wearing[slot] = self._cine_wearing.get(slot, "")
                workflow = "medium"
            else:
                if mood:
                    self._classic_mood[slot] = mood
                # the game's first portraits (interact 0) come before any scene;
                # a refresh (interact = the round) stands in front of its place
                first = (interact if made_round is None else made_round) in (0, None)
                body = images.portrait_body(char, mood, self._classic_wearing.get(slot, ""),
                                            "" if first else self._classic_backdrop)
                positive, negative = images.wrap_prompt("portrait", body,
                                                        self.prompt_settings)
            if skip_same and self._portrait_body_last.get(slot) == body:
                print(f"  \u21b7 portrait {slot}: nothing changed - not redrawn", flush=True)
                continue
            self._portrait_body_last[slot] = body
            self._portrait_prompts[slot] = (positive, negative, body)
            self._portrait_kinds[slot] = workflow
            self._queue_image({"kind": "portrait", "slot": slot, "prompt": positive,
                               "negative": negative, "body": body, "workflow": workflow,
                               "interact": interact,
                               "made_round": interact if made_round is None else made_round,
                               "seed": self._image_seed("portrait", slot, interact),
                               "priority": _PRIORITY["portrait"]})

    def _leads(self, char_a, char_b):
        return [("a", self._own_name(char_a), char_a.gender),
                ("b", self._own_name(char_b), char_b.gender)]

    def _note_player_clothes(self, char_a, char_b) -> None:
        """v12.4 Classical: the clothes the player's event put on each lead
        (images12.player_clothes), carried until the next change."""
        if not self._player_text:
            return
        for slot, garments in images.player_clothes(self._player_text,
                                                    self._leads(char_a, char_b)).items():
            if garments:
                self._classic_wearing[slot] = ", ".join(garments)

    @staticmethod
    def _own_name(char) -> str:
        """Every name a lead goes by (name, identity's name, address): the
        hygiene's own-name rules need all of them ("Kael Doran" / "Doran")."""
        return " ".join(n for n in (char.name, (char.identity or "").split(",")[0],
                                    char.address) if n)

    def _backlog_cover(self) -> bool:
        """v12.3: a Cinematic game whose presenter still has at least
        GATE_BACKLOG_S of words to play - time a gate render can hide in."""
        return (self.scene_style in ("cinematic", "medium")
                and self._backlog_words * READ_SECONDS_PER_WORD >= GATE_BACKLOG_S)

    def _cine_setup(self, char_a, char_b) -> None:
        """
        v12.3, game start of a Cinematic game: each lead's LOOKS (face, hair,
        eyes, build, marks - no clothes), one call each, cleaned by images12.
        If the call gives nothing usable, the extracted fp_image minus its
        clothing items stands in.
        """
        for slot, char in (("a", char_a), ("b", char_b)):
            raw = self._timed(f"cine looks {slot}", engine.generate_cine_field,
                              "looks", char.name, description=char.description)
            source = " ".join((char.description, char.fp_image))
            looks, dropped = images.cine_hygiene("looks", raw, (),
                                                 engine.CINE_EXAMPLE["looks"], source,
                                                 own_name=self._own_name(char))
            if not looks:
                looks, _ = images.cine_hygiene("looks", char.fp_image)
            self._cine_looks[slot] = looks
            write_run_file(self.run_dir, f"cine_looks_{slot}.txt",
                           f"RAW: {raw}\nLOOKS: {looks}\nDROPPED: {dropped}")

    def _cine_paint(self, round_num, setting, opener, scene_event) -> None:
        """
        v12.3, right after the opener (as Classical's painter): the scene
        painter's three layers for a Cinematic round, kept for the lend
        point. PLACE stops seeing the setting after round 1, so it follows
        the player's event (scene_painter_messages explains the measurement).
        """
        world = self.cfg.get("world_desc", "")
        self._cine_layers[round_num] = self._timed(
            f"scene prompt r{round_num}", generate_scene_layers, setting, opener,
            round_num, world, scene_event, place_sees_setting=False)

    def _build_cinematic(self, round_num, setting, opener, history, scene_event,
                         char_a, char_b):
        """
        v12.3: the round's Cinematic scene - the scene painter's PLACE /
        OBJECTS AND EFFECTS / LIGHT (painted after the opener, _cine_paint),
        plus per lead WEARING (carried over, the player's event nearest the
        cue) and RIGHT NOW, plus OTHERS in view; cleaned and laid out by
        images12. Called at the round's lend point, so the moment includes
        the first dialogue lines. Returns (positive, negative, body); writes
        round_NN_scene_prompt.txt.
        """
        world = self.cfg.get("world_desc", "")
        if round_num not in self._cine_layers:
            self._cine_paint(round_num, setting, opener, scene_event)
        layers = self._cine_layers.pop(round_num)
        source = " ".join((world if round_num <= 1 else "", setting, opener, scene_event))
        clean, dropped = {}, []
        for layer, text in layers.items():
            kept, drop = images.scene_hygiene(engine.scene_items(text), self._names,
                                              " ".join(SCENE_EXAMPLE.values()), source)
            budget, out = images.CINE_MAX_WORDS.get(layer, 20), []
            for t in kept:
                if len(t.split()) <= budget:
                    out.append(t)
                    budget -= len(t.split())
            clean[layer] = ", ".join(out)
            dropped += [(layer,) + d for d in drop]
        moment = "\n\n".join([opener] + list(history))
        lines, cast = [], []
        for slot, char, side in (("a", char_a, "left"), ("b", char_b, "right")):
            prev = self._cine_wearing.get(slot, "")
            raw_w = self._timed(f"cine wearing {slot} r{round_num}",
                                engine.generate_cine_field, "wearing", char.name,
                                description="" if prev else char.description,
                                scene=moment, event=scene_event, previous=prev,
                                player_text=self._player_text)
            wearing, d_w = images.cine_hygiene(
                "wearing", raw_w, self._names, engine.CINE_EXAMPLE["wearing"],
                " ".join((char.description, moment, scene_event, prev)),
                own_name=self._own_name(char))
            # no garment named at all = keep the last clothes (live game 2:
            # "Doran - Casual Encounter" as what Kael wears)
            if prev and not images.has_clothes(wearing):
                wearing = prev
            wearing = wearing or prev
            # v12.4: the player said what they put on, and the model answered
            # with other clothes (probe_wearing3: "They put on a spacesuit" ->
            # Harry in "Gryffindor robes" 5/5) - the player's words win
            said = (images.player_clothes(self._player_text, self._leads(char_a, char_b))
                    .get(slot, []) if self._player_text else [])
            if images.wearing_misses(wearing, said):
                d_w = list(d_w) + [(wearing, "player's clothes instead")]
                wearing = ", ".join(said)
            raw_d = self._timed(f"cine doing {slot} r{round_num}",
                                engine.generate_cine_field, "doing", char.name,
                                scene=moment, event=scene_event)
            doing, d_d = images.cine_hygiene(
                "doing", raw_d, self._names, engine.CINE_EXAMPLE["doing"],
                " ".join((moment, scene_event)), own_name=self._own_name(char),
                own_gender=char.gender)
            self._cine_wearing[slot] = wearing
            cast.append({"name": char.name, "gender": char.gender,
                         "age_group": char.age_group, "side": side,
                         "looks": self._cine_looks.get(slot, ""),
                         "wearing": wearing, "doing": doing})
            lines += [f"{char.name.upper()} WEARING raw: {raw_w}",
                      f"{char.name.upper()} WEARING: {wearing}  (dropped {d_w})",
                      f"{char.name.upper()} DOING raw: {raw_d}",
                      f"{char.name.upper()} DOING: {doing}  (dropped {d_d})"]
        raw_o = self._timed(f"cine others r{round_num}", engine.generate_cine_field,
                            "others", f"{char_a.name} and {char_b.name}",
                            scene=moment, event=scene_event,
                            world=world if round_num <= 1 else "")
        others, d_o = images.cine_hygiene(
            "others", raw_o, self._names, engine.CINE_EXAMPLE["others"],
            " ".join((world, setting, moment, scene_event)))
        build = (images.build_medium_prompt if self.scene_style == "medium"
                 else images.build_cinematic_prompt)
        built = build(cast, clean, others, self.prompt_settings)
        self._cine_backdrop = (clean.get("place", ""), clean.get("light", ""))
        write_run_file(self.run_dir, f"round_{round_num:02d}_scene_prompt.txt",
                       f"STYLE: {self.scene_style}\n"
                       + "\n".join(f"{k.upper()}: {v}" for k, v in layers.items())
                       + f"\nLAYERS DROPPED: {dropped}\n"
                       + "\n".join(lines)
                       + f"\nOTHERS raw: {raw_o}\nOTHERS: {others}  (dropped {d_o})"
                       + f"\n\nBODY:\n{built['body']}"
                       + f"\n\nPOSITIVE:\n{built['positive']}"
                       + f"\n\nNEGATIVE: {built['negative']}")
        return built["positive"], built["negative"], built["body"]

    def _cine_round(self, round_num, setting, opener, history, scene_event,
                    char_a, char_b) -> tuple:
        """
        v12.3, at the round's lend point (Y1). Cinematic: build and queue the
        scene (and in round 1 the game's first portraits). Returns the slots
        whose clothes CHANGED since their last portrait - the caller queues
        those after this lend, so they render while the story waits for the
        player (Y2) instead of holding up this round. (Live game 1: two
        portraits every round, the Y1 lend 91-108 s against Classical's 62 s,
        the presenter starved ~43 s a round.) A Classical game does nothing
        here (its scene was queued after the opener), unless the Cinematic
        check fell back AFTER that point: then the Classical scene and the
        first portraits are queued now.
        """
        if not self.images_wanted or self._images_off or self._stop.is_set():
            return ()
        if self.scene_style in ("cinematic", "medium"):
            style = self.scene_style
            positive, negative, body = self._build_cinematic(
                round_num, setting, opener, history, scene_event, char_a, char_b)
            if self.scene_style != style:              # fell back meanwhile
                return self._cine_round(round_num, setting, opener, history,
                                        scene_event, char_a, char_b)
            self._queue_scene(round_num, positive, negative, body, style)
            # The game's FIRST portraits wait for this lend's end too (live
            # game 2: scene + both portraits at round 1's lend = 91 s, the
            # reader waited 43 s; round 2, scene only, 41 s and no wait).
            # The scene already shows both leads; the cards follow at the gate.
            if not self._portraits_queued:
                return ("a", "b")
            return tuple(s for s in ("a", "b") if images.clothes_changed(
                self._portrait_wearing.get(s, ""), self._cine_wearing.get(s, "")))
        else:
            if round_num not in self._scene_prompts:
                positive, negative, body = self._build_scene(
                    round_num, setting, opener, scene_event)
                self._queue_scene(round_num, positive, negative, body, "classical")
            if not self._portraits_queued:
                self._queue_portraits(char_a, char_b, 0)
        return ()

    def _queue_scene(self, round_num, positive, negative, body, kind) -> None:
        self._scene_prompts[round_num] = (positive, negative, body)
        self._scene_kinds[round_num] = kind
        self._queue_image({"kind": "scene", "round": round_num,
                           "prompt": positive, "negative": negative,
                           "body": body, "take": 0, "made_round": round_num,
                           "workflow": kind,
                           "seed": self._image_seed("scene", round_num, 0),
                           "priority": _PRIORITY["scene"]})
        self._emit("scene_prompt", round_num, body)

    def _build_scene(self, round_num, setting, opener, scene_event):
        """
        v12.1: the round's scene image text - three painter layers (engine),
        hygiene + the Scene wrappers (images12). Returns (positive, negative,
        body) and writes all of it to round_NN_scene_prompt.txt.
        """
        world = self.cfg.get("world_desc", "")
        # v12.4 (the user's choice, 2026-10-18): Classical follows the events
        # too - PLACE sees the setting in round 1 only, as Cinematic since
        # v12.3 (probe_place: setting shown -> the platform 12/12, not shown
        # -> the event's place 12/12)
        layers = self._timed(f"scene prompt r{round_num}", generate_scene_layers,
                             setting, opener, round_num, world, scene_event,
                             place_sees_setting=False)
        source = " ".join((world if round_num <= 1 else "", setting, opener, scene_event))
        built = images.build_scene_prompt(layers, self._names,
                                          " ".join(SCENE_EXAMPLE.values()), source,
                                          self.prompt_settings)
        # v12.4: where the leads are now, behind their next (living) portrait
        self._classic_backdrop = images.backdrop_from_layers(
            layers, self._names, " ".join(SCENE_EXAMPLE.values()), source)
        write_run_file(self.run_dir, f"round_{round_num:02d}_scene_prompt.txt",
                       "\n".join(f"{k.upper()}: {v}" for k, v in layers.items())
                       + f"\n\nBODY: {built['body']}"
                       + f"\n\nDROPPED: {built['dropped']}"
                       + f"\n\nPOSITIVE: {built['positive']}"
                       + f"\n\nNEGATIVE: {built['negative']}")
        return built["positive"], built["negative"], built["body"]

    def _build_music(self, round_num, setting, opener, scene_event,
                     resolution: str = "") -> None:
        """
        v12.4: the round's music job, built at the END of the round. The
        soundtrack once per game (the player's style, else the composer's
        choice, else the world's keywords); the mood every round from the
        round's opener and resolution (its intro and how it ended) and the
        player's event; music12 writes the caption. All of it to
        round_NN_music_prompt.txt.
        """
        world = self.cfg.get("world_desc", "")
        if not self._soundtrack_chosen:
            if self.music_style in music.PALETTES:
                self._soundtrack, src = self.music_style, "player"
            else:
                s = self._timed("music soundtrack", generate_music_field, "soundtrack",
                                world=world, setting=setting)
                src = "composer"
                if not s:
                    s, src = music.guess_soundtrack(f"{world} {setting}"), "keywords"
                self._soundtrack = s
            self._soundtrack_chosen = True
            write_run_file(self.run_dir, "music_soundtrack.txt",
                           f"{self._soundtrack or 'cinematic (default palette)'} ({src})")
        story = "\n\n".join(t for t in (opener, resolution) if (t or "").strip())
        mood = self._timed(f"music mood r{round_num}", generate_music_field, "mood",
                           scene=story, event=scene_event)
        prompt = music.build_music_prompt(self._soundtrack, mood, story, scene_event,
                                          names=self._names, game_seed=self.game_seed,
                                          seconds=self.music_seconds)
        prompt["raw_mood"] = mood
        write_run_file(self.run_dir, f"round_{round_num:02d}_music_prompt.txt",
                       f"SOUNDTRACK: {self._soundtrack or '(default)'}\n"
                       f"MOOD (composer): {mood}\nCLASS: {prompt['mood_class']}\n"
                       f"BPM: {prompt['bpm']}  KEY: {prompt['keyscale']}  "
                       f"TIME: {prompt['timesignature']}/4  SECONDS: {prompt['seconds']}\n"
                       f"COLOURS: {', '.join(prompt['colours']) or '-'}\n\n"
                       f"CAPTION: {prompt['caption']}\n\nLYRICS: {prompt['lyrics']}")
        self._music_prompts[round_num] = prompt
        # An earlier round's first take that has not started yet is stale now:
        # the GUI plays the newest round's music, so on a slow machine it would
        # only delay this one (a regenerate the player asked for stays).
        with self._jobs_cv:
            stale = [j for j in self._jobs if j.get("kind") == "music"
                     and j.get("take", 0) == 0 and j.get("round", 0) < round_num]
            self._jobs = [j for j in self._jobs if j not in stale]
        for j in stale:
            print(f"  ↷ music r{j['round']} not rendered in time - skipped for "
                  f"round {round_num}'s", flush=True)
        self._queue_image({"kind": "music", "round": round_num, "prompt": prompt,
                           "take": 0, "made_round": round_num, "codes": self.music_codes,
                           "seed": self._image_seed("music", round_num, 0),
                           "priority": _PRIORITY["music"]})
        self._emit("music_prompt", round_num, prompt["body"])

    # =========================================================================
    #  LANE 1 - STORY THREAD
    # =========================================================================

    def _story_thread(self) -> None:
        try:
            self._run_story()
        except Exception as e:
            traceback.print_exc()
            self._emit("error", str(e))
        finally:
            self._voice_q.put(_SENTINEL)
            self._lane("story", "ended")

    def _run_story(self) -> None:
        cfg = self.cfg
        turns = int(cfg.get("turns_per_round", TURNS_PER_ROUND))
        max_rounds = int(cfg.get("rounds", 0))        # 0 = endless
        yield_at = min(IMAGE_YIELD_AFTER_TURN, turns)

        self._lane("story", "setup")
        self._emit("status", "Starting Ollama (GPU)...")
        start_ollama()
        # v12.2: one seed stream for every model call of this game; a resumed
        # game continues the stream where its checkpoint left it.
        engine.set_game_seed(self.game_seed, int(self.resume["snapshot"].get("llm_calls", 0))
                             if self.resume else 0)
        self._emit("game_seed", self.game_seed)
        # v12.2: the same seed replayed the same text only from the same kind
        # of model instance. Three seeded runs (loop_reports/v12_2_saves/
        # determinism2_*): two that inherited a model another program had
        # loaded matched each other, and the one that loaded its own did not;
        # five extractions across three self-loads (reload_probe.py) all
        # matched. So every game starts from a model loaded the same way -
        # unload, then the standard load request the GPU hand-over also uses.
        ollama_unload()
        self._record_timing("model reload (seeded start)", ollama_prewarm())

        st = self._restore() if self.resume else self._setup_new()
        if st is None or self._stop.is_set():
            return
        char_a, char_b, setting = st["char_a"], st["char_b"], st["setting"]
        mem_a, mem_b = st["mem_a"], st["mem_b"]
        event = seed = pressure = ""
        scene_event = ""                       # v12.1: the player's text + staging
        round_num = st["round_num"]
        if self.resume:                        # v12.2: straight to the saved gate
            g = self._gate(round_num - 1, setting, char_a, char_b,
                           st["resolution"], mem_a, mem_b)
            if g is None:
                return
            seed, event, pressure, scene_event = g

        # ---- rounds -----------------------------------------------------------
        while not self._stop.is_set():
            if max_rounds and round_num > max_rounds:
                self._emit("status", f"{max_rounds} rounds complete.")
                break
            self._lane("story", f"writing round {round_num}")

            self._injection_armed = True
            self._emit("await_injection", round_num)

            opener = self._timed(f"opener r{round_num}", generate_opener,
                                 setting, char_a, char_b, seed, round_num,
                                 cfg.get("prior_history", ""))
            if self._stop.is_set():
                break
            write_run_file(self.run_dir, f"round_{round_num:02d}_opener.txt", opener)
            append_log(self.run_dir, f"ROUND {round_num} OPENER:\n{opener}\n\n")
            self._push("narration", opener, "Narrator", "narrator", "opener", round_num)

            # v12.1: the round's scene - the engine's scene painter writes
            # three layers (world in round 1, the player's event from round
            # 2), images12 cleans them and wraps them in the Scene settings;
            # the image lane renders it at this round's lend (Y1).
            # Queued even while ComfyUI is still starting; skipped only once
            # the lane has been switched off. v12.3: a Cinematic round builds
            # its scene at the lend point instead (_cine_round).
            if (self.images_wanted and not self._images_off
                    and self.scene_style == "classical"):
                positive, negative, body = self._build_scene(
                    round_num, setting, opener, scene_event)
                self._scene_prompts[round_num] = (positive, negative, body)
                self._queue_image({"kind": "scene", "round": round_num,
                                   "prompt": positive, "negative": negative,
                                   "body": body, "take": 0, "made_round": round_num,
                                   "seed": self._image_seed("scene", round_num, 0),
                                   "priority": _PRIORITY["scene"]})
                self._emit("scene_prompt", round_num, body)
            elif self.images_wanted and not self._images_off:
                self._cine_paint(round_num, setting, opener, scene_event)

            history, lines_rec = [], []
            for t in range(turns):
                if self._stop.is_set():
                    break
                speaker, other = (char_a, char_b) if t % 2 == 0 else (char_b, char_a)
                mem = mem_a if speaker is char_a else mem_b
                line = self._timed(f"line r{round_num}.{t + 1}",
                                   generate_dialogue_turn, speaker, other,
                                   setting, opener, history,
                                   memory=mem, event=event, pressure=pressure,
                                   round_num=round_num, turn_index=t)
                history.append(f"{speaker.name}: {line}")
                key = "a" if speaker is char_a else "b"
                lines_rec.append({"key": key, "name": speaker.name, "text": line})
                self._push("line", line, speaker.name, key, "", round_num)
                if t + 1 == yield_at:                       # v12 Y1
                    first = not self._portraits_queued
                    later = self._cine_round(round_num, setting, opener, history,
                                             scene_event, char_a, char_b)
                    self._lend_gpu(f"r{round_num}")
                    if later:                               # v12.3: render at Y2
                        self._queue_portraits(char_a, char_b,
                                              0 if first else f"r{round_num}",
                                              slots=later, made_round=round_num)
                    self._lane("story", f"writing round {round_num}")
            if self._stop.is_set():
                break
            write_run_file(self.run_dir, f"round_{round_num:02d}_dialogue.txt",
                           "\n".join(history))
            append_log(self.run_dir,
                       f"ROUND {round_num} DIALOGUE:\n" + "\n".join(history) + "\n\n")

            resolution = self._timed(f"resolution r{round_num}", generate_resolution,
                                     setting, char_a, char_b, history, opener)
            write_run_file(self.run_dir, f"round_{round_num:02d}_resolution.txt",
                           resolution)
            append_log(self.run_dir, f"ROUND {round_num} RESOLUTION:\n{resolution}\n\n")
            self._push("narration", resolution, "Narrator", "narrator",
                       "resolution", round_num)

            mem_a = self._timed(f"memory A r{round_num}", generate_character_memory,
                                char_a, char_b, opener, history, resolution, mem_a,
                                event=event)
            mem_b = self._timed(f"memory B r{round_num}", generate_character_memory,
                                char_b, char_a, opener, history, resolution, mem_b,
                                peer_memory=mem_a,
                                event=event)
            write_run_file(self.run_dir, f"round_{round_num:02d}_memory_a.txt", mem_a)
            write_run_file(self.run_dir, f"round_{round_num:02d}_memory_b.txt", mem_b)
            append_log(self.run_dir,
                       f"ROUND {round_num} MEMORY A ({char_a.name}):\n{mem_a}\n\n"
                       f"ROUND {round_num} MEMORY B ({char_b.name}):\n{mem_b}\n\n")
            self._emit("memories", round_num, mem_a, mem_b)
            with self._ckpt_lock:                  # v12.2: the save game's record
                self._rounds.append({"round": round_num, "opener": opener,
                                     "lines": lines_rec, "resolution": resolution,
                                     "mem_a": mem_a, "mem_b": mem_b, "event": None})

            # v12: optional mood-keyed portrait refresh, rendered at the next
            # lend (Y2 if something else is queued, else next round's Y1).
            if self.images_wanted and cfg.get("portrait_refresh", False):
                if self.scene_style == "classical":     # v12.4: clothes, place, mood
                    self._note_player_clothes(char_a, char_b)
                self._queue_portraits(char_a, char_b, round_num,
                                      images.scan_mood(resolution), skip_same=True)

            # v12.4: the music comes LAST - all the round's text is written;
            # now its prompt, then one lend: the pictures still queued, then
            # the music (equalised in _render), not cut short by the event.
            if (self.music_wanted and not self._music_off and not self._images_off
                    and not self._stop.is_set()):
                self._build_music(round_num, setting, opener, scene_event, resolution)
                self._lend_gpu(f"r{round_num} end (music)", max_s=MUSIC_LEND_MAX_S)
                self._lane("story", f"round {round_num} written")

            g = self._gate(round_num, setting, char_a, char_b, resolution, mem_a, mem_b)
            if g is None:
                break
            seed, event, pressure, scene_event = g
            round_num += 1

    def _setup_new(self):
        """A new game: extract, build the world, voices, first portraits."""
        cfg = self.cfg
        char_a = self._timed("extract A", extract_character, cfg["char_a_inputs"])
        self._emit("character_ready", "a", char_a)
        char_b = self._timed("extract B", extract_character, cfg["char_b_inputs"])
        self._emit("character_ready", "b", char_b)
        if self._stop.is_set():
            return None
        self._names = [n for c in (char_a, char_b)
                       for n in (c.name, (c.identity or "").split(",")[0], c.address) if n]

        self._emit("status", "Building the world...")
        setting = self._timed("setting", generate_setting,
                              cfg["world_desc"], char_a, char_b)

        self.run_dir = make_run_dir(cfg["world_desc"])
        os.makedirs(os.path.join(self.run_dir, tts.AUDIO_SUBDIR), exist_ok=True)
        save_characters_json(self.run_dir, char_a, char_b)
        write_run_file(self.run_dir, "setting.txt", setting)
        self._chars, self._setting = (char_a, char_b), setting
        append_log(self.run_dir, f"GAME SEED: {self.game_seed}\n\n")

        # v12: portraits queued now, rendered at round 1's lend - after the
        # round-1 scene, which is queued ahead of them by priority.
        # v12.3: a Cinematic game reads each lead's looks now and queues the
        # portraits at round 1's lend point, once their clothes are known.
        if self.images_wanted:
            if self.scene_style in ("cinematic", "medium"):
                self._cine_setup(char_a, char_b)
            else:
                self._queue_portraits(char_a, char_b, 0)

        self._resolve_voices(char_a, char_b)
        self._emit("session_ready", char_a, char_b, setting)

        self._push("narration", setting, "Narrator", "narrator", "setting", 0)
        append_log(self.run_dir, f"SETTING:\n{setting}\n\n")
        return {"char_a": char_a, "char_b": char_b, "setting": setting,
                "mem_a": "", "mem_b": "", "round_num": 1}

    def _resolve_voices(self, char_a, char_b) -> None:
        cfg = self.cfg
        if self.voice_enabled and tts.tts_available():
            self._emit("status", "Building voices (first run downloads Kokoro)...")
            self._cast = tts.resolve_cast(char_a, char_b,
                                          cfg.get("narrator_gender", "woman"),
                                          cfg.get("narrator_accent", "rough"))
            tts.warmup(self._cast)
        summary = tts.cast_summary(self._cast)
        self._voice_summary = summary
        self._emit("voices", summary)
        write_run_file(self.run_dir, "voices.txt", summary)
        self._lane("voice", "ready" if self._cast else f"off ({tts.tts_status()})")

    def _restore(self):
        """
        v12.2: a saved game - everything the model knew, exactly as saved:
        the EXTRACTED characters (never re-extracted), the setting, both
        memories, the last resolution, the seed stream. Nothing is re-read
        aloud; the GUI lays the saved rounds out from the `resumed` updater.
        """
        snap, self.run_dir = self.resume["snapshot"], self.resume["run_dir"]
        n = int(snap["round_done"])
        names = {f.name for f in dataclasses.fields(StoryCharacter)}
        char_a, char_b = (StoryCharacter(**{k: v for k, v in snap["characters"][s].items()
                                            if k in names}) for s in ("a", "b"))
        setting = snap["setting"]
        self._chars, self._setting = (char_a, char_b), setting
        self._names = list(snap.get("names") or [char_a.name, char_b.name])
        with self._ckpt_lock:
            self._rounds = [dict(r) for r in snap.get("rounds", [])]
            self._scene_log = {int(r): s for r, s in snap.get("scenes", {}).items()}
            self._portrait_log = list(snap.get("portraits", []))
        self._scene_prompts = {int(r): tuple(v)
                               for r, v in snap.get("scene_prompts", {}).items()}
        self._portrait_prompts = {s: tuple(v)
                                  for s, v in snap.get("portrait_prompts", {}).items()}
        self._takes = {(int(k) if k.isdigit() else k): v
                       for k, v in snap.get("takes", {}).items()}
        cine = snap.get("cine") or {}                  # v12.3 (absent in v12.2 saves)
        self._cine_looks = dict(cine.get("looks") or {})
        self._cine_wearing = dict(cine.get("wearing") or {})
        self._portrait_wearing = dict(cine.get("portrait_wearing") or {})
        self._portraits_queued = bool(cine.get("portraits_queued", True))
        self._cine_backdrop = tuple(cine.get("backdrop") or ("", ""))
        self._portrait_kinds = dict(cine.get("portrait_kinds") or {})
        self._scene_kinds = {int(r): k for r, k in (cine.get("scene_kinds") or {}).items()}
        cls = snap.get("classic") or {}                # v12.4 (absent before)
        self._classic_wearing = dict(cls.get("wearing") or {})
        self._classic_backdrop = cls.get("backdrop", "") or ""
        self._classic_mood = dict(cls.get("mood") or {})
        mus = snap.get("music") or {}                  # v12.4 (absent before)
        self._soundtrack = mus.get("soundtrack", "") or ""
        self._soundtrack_chosen = bool(mus.get("chosen"))
        self._music_prompts = {int(r): p for r, p in (mus.get("prompts") or {}).items()}
        with self._ckpt_lock:
            self._music_log = {int(r): m for r, m in (mus.get("tracks") or {}).items()}
        if self.scene_style in ("cinematic", "medium") and not self._cine_looks:
            # a game saved in Classical, loaded with Cinematic on: read the
            # looks now (the run dir exists, the seed stream is restored)
            self._cine_setup(char_a, char_b)
        branch = saves.archive_later_rounds(self.run_dir, n)
        append_log(self.run_dir, f"=== RESUMED after round {n} (game seed "
                                 f"{self.game_seed})"
                                 + (f"; later rounds moved to {os.path.basename(branch)}"
                                    if branch else "") + " ===\n\n")
        self._emit("character_ready", "a", char_a)
        self._emit("character_ready", "b", char_b)
        self._resolve_voices(char_a, char_b)
        self._emit("session_ready", char_a, char_b, setting)
        self._emit("resumed", snap, self.run_dir, branch)
        for job in snap.get("pending_jobs", []):       # unfinished pictures: the
            self._queue_image(dict(job))               # same seeds, the same images
        st = snap.get("state", {})
        return {"char_a": char_a, "char_b": char_b, "setting": setting,
                "mem_a": st.get("mem_a", ""), "mem_b": st.get("mem_b", ""),
                "resolution": st.get("resolution", ""), "round_num": n + 1}

    def _gate(self, round_num, setting, char_a, char_b, resolution, mem_a, mem_b):
        """
        The event gate after round_num: write the checkpoint (v12.2 - the only
        consistent moment), wait for the player's event, consume it. Returns
        (seed, event, pressure, scene_event) for the next round, or None on stop.
        """
        cfg = self.cfg
        self.round_done = round_num
        with self._ckpt_lock:
            self._state = {"mem_a": mem_a, "mem_b": mem_b, "resolution": resolution}
            self._calls_at_gate = engine.game_seed_state()["calls"]
        self._write_checkpoint()
        self._emit("checkpoint", round_num)

        self._lane("story", "awaiting your event")
        if not self._injection_armed and not self._injection.is_set():
            self._injection_armed = True               # a resumed game arms here
            self._emit("await_injection", round_num)
        self._at_gate = not self._injection.is_set()
        # v12.3: in a Cinematic game the gate's lend (Y2) also renders the
        # portraits, and it keeps going after the event is in for as long as
        # the presenter still has GATE_BACKLOG_S of this round to play (live
        # game 3: an event typed during the round skipped Y2, and the first
        # portraits piled onto round 2's lend - 90 s instead of 46). A
        # Classical game: _backlog_cover() is always False - v12.2's loop.
        def until():
            return self._injection.is_set() and not self._backlog_cover()
        while not self._stop.is_set():
            if self._injection.wait(timeout=0.2) and not (
                    self._jobs_pending() and self._backlog_cover()):
                break
            if self._jobs_pending():                   # v12 Y2: re-rolls
                self._lend_gpu("while waiting", until=until)
                self._lane("story", "awaiting your event")
        self._at_gate = False
        if self._stop.is_set():
            return None
        injection = self._injection_text
        self._injection.clear()
        self._player_text = injection or ""            # v12.3: for the clothes role
        if not injection:                              # no event: carry on the world
            return resolution, "", "", ""
        write_run_file(self.run_dir,
                       f"round_{round_num:02d}_injection.txt", injection)
        append_log(self.run_dir,
                   f"ROUND {round_num} INJECTION: {injection}\n\n")
        self._push("event", injection, "You", "", "", round_num)
        staged, pressure = self._timed(
            f"event r{round_num}", condition_event,
            injection, setting, char_a, char_b, resolution, mem_a, mem_b)
        kept_raw = staged == " ".join(injection.split())
        sent = compose_event(injection, staged)
        self._emit("staged", round_num, injection, staged, kept_raw, sent)
        if cfg.get("show_staging", True):
            self._push("staged", staged, "", "",
                       "kept_raw" if kept_raw else "staged", round_num)
        write_run_file(self.run_dir,
                       f"round_{round_num:02d}_staged.txt",
                       staged + ("\n\nPRESSURE: " + pressure if pressure else ""))
        write_run_file(self.run_dir,
                       f"round_{round_num:02d}_event.txt", sent)
        append_log(self.run_dir,
                   f"ROUND {round_num} STAGED: {staged}\n"
                   f"ROUND {round_num} PRESSURE: {pressure}\n"
                   f"ROUND {round_num} SENT: {sent}\n\n")
        with self._ckpt_lock:
            for rec in self._rounds:
                if rec["round"] == round_num:
                    rec["event"] = {"injection": injection, "staged": staged,
                                    "kept_raw": kept_raw, "sent": sent,
                                    "pressure": pressure}
        # v12.1: the next scene sees the player's words once, then the
        # staging (the story's copies-twice rule is for the text model's
        # attention, not for a picture).
        scene_event = (injection if kept_raw else f"{injection.rstrip('. ')}. {staged}")
        return frame_injection(sent, resolution), sent, pressure, scene_event

    # =========================================================================
    #  v12.2 - CHECKPOINTS AND SAVE GAMES  (story_lab_saves12 holds the files)
    # =========================================================================

    def _image_seed(self, *parts) -> int:
        return engine.derive_seed(self.game_seed, "image", *parts)

    def _snapshot(self) -> dict:
        """
        The game after round_done, for a checkpoint. Must be called under
        _ckpt_lock. Only what belongs to rounds <= round_done goes in: the
        scene of the round being written, and an event typed for the NEXT
        round, are not part of this save.
        """
        n = self.round_done
        cfg = {k: v for k, v in self.cfg.items()}
        rounds = [dict(r) if r["round"] < n else dict(r, event=None)
                  for r in self._rounds if r["round"] <= n]
        with self._jobs_cv:
            jobs = [dict(j) for j in self._jobs] + (
                [dict(self._current_job)] if self._busy and self._current_job else [])
        pending = [j for j in jobs if j.get("made_round", 0) <= n]
        char_a, char_b = self._chars
        return {
            "format": saves.FORMAT,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "engine_version": engine.ENGINE_VERSION, "model": engine.MODEL,
            "image_checkpoint": self._ckpt_name,
            "game_seed": self.game_seed, "llm_calls": self._calls_at_gate,
            "story": {"title": cfg.get("story_title", "")},
            "config": cfg,
            "characters": {"a": dataclasses.asdict(char_a), "b": dataclasses.asdict(char_b)},
            "names": list(self._names), "setting": self._setting,
            "voices": self._voice_summary,
            "round_done": n, "state": dict(self._state), "rounds": rounds,
            "scenes": {str(r): s for r, s in self._scene_log.items() if r <= n},
            "portraits": [p for p in self._portrait_log if p.get("round", 0) <= n],
            "scene_prompts": {str(r): list(v) for r, v in self._scene_prompts.items()
                              if r <= n},
            "portrait_prompts": {s: list(v) for s, v in self._portrait_prompts.items()},
            "takes": {str(k): v for k, v in self._takes.items()},
            "pending_jobs": pending,
            # v12.3: what a Cinematic game's pictures were built from
            "cine": {"style": self.scene_style, "looks": dict(self._cine_looks),
                     "wearing": dict(self._cine_wearing),
                     "portrait_wearing": dict(self._portrait_wearing),
                     "portraits_queued": self._portraits_queued,
                     "backdrop": list(self._cine_backdrop),
                     "portrait_kinds": dict(self._portrait_kinds),
                     "scene_kinds": {str(r): k for r, k in self._scene_kinds.items()
                                     if r <= n}},
            # v12.4: what a Classical portrait follows
            "classic": {"wearing": dict(self._classic_wearing),
                        "backdrop": self._classic_backdrop,
                        "mood": dict(self._classic_mood)},
            # v12.4: the game's soundtrack and each round's music
            "music": {"soundtrack": self._soundtrack, "chosen": self._soundtrack_chosen,
                      "prompts": {str(r): p for r, p in self._music_prompts.items()
                                  if r <= n},
                      "tracks": {str(r): m for r, m in self._music_log.items() if r <= n}},
        }

    def _write_checkpoint(self) -> None:
        """The autosave: <run_dir>/checkpoints/round_NN.json. Never raises."""
        if not self.run_dir or self.round_done < 1 or self._chars is None:
            return
        try:
            with self._ckpt_lock:
                snap = self._snapshot()
                saves.write_checkpoint(self.run_dir, snap)
        except Exception as e:
            print(f"  ⚠ checkpoint not written: {e}", flush=True)

    def save_game(self, name: str):
        """
        A named save pointing at this game's latest checkpoint (GUI thread).
        Returns (path, round_done), or None before the first round is done.
        """
        if not self.run_dir or self.round_done < 1:
            return None
        self._write_checkpoint()
        return saves.save_game(name, self.run_dir, self.round_done), self.round_done

    # =========================================================================
    #  LANE 2 - VOICE WORKER  (unchanged from v11)
    # =========================================================================

    def _voice_worker(self) -> None:
        while True:
            item = self._voice_q.get()
            if item is _SENTINEL:
                self._put_present(_SENTINEL)
                break
            if not self._put_present(("item", item)):
                break
            for chunk in item.chunks:
                if self._stop.is_set():
                    break
                if (self.voice_enabled and self._cast
                        and chunk.voice_key in self._cast):
                    self._lane("voice",
                               f"voicing r{item.round_num} {item.kind} "
                               f"{chunk.idx + 1}/{len(item.chunks)}")
                    t_syn = time.time()
                    tts.synthesize_chunk(
                        chunk, self._cast[chunk.voice_key],
                        run_dir=self.run_dir,
                        prefix=f"r{item.round_num:02d}_{item.seq:03d}_{chunk.voice_key}")
                    self._note_voice_speed(chunk, time.time() - t_syn)
                    self._lane("voice", "ready")
                if not self._put_present(("chunk", item, chunk)):
                    break
            if not self._put_present(("item_end", item)):
                break
        self._lane("voice", "ended")

    def _note_voice_speed(self, chunk, took: float) -> None:
        """
        v12.4: Kokoro's real-time factor so far (speech made / time taken).
        Below VOICE_RTF_MIN the voice cannot keep up and the speech stutters;
        say so once. The user's music playtest stuttered: Kokoro measured
        0.5-0.6x on the power-capped CPU (about 4x in August, same laptop).
        """
        if chunk.audio is None:
            return
        self._voice_made_s += chunk.seconds
        self._voice_took_s += took
        if (self._warned_voice or self._voice_made_s < VOICE_RTF_AFTER_S
                or self._voice_took_s <= 0):
            return
        rtf = self._voice_made_s / self._voice_took_s
        if not getattr(self, "_rtf_noted", False):     # once, not every sentence
            self._rtf_noted = True
            self._record_timing("voice real-time factor (x)", rtf)
        if rtf < VOICE_RTF_MIN:
            self._warned_voice = True
            msg = (f"The voice is slower than real time on this machine ({rtf:.1f}x; "
                   f"it needs 1x to keep up, this laptop managed about 4x before), so "
                   f"speech will stutter. The CPU looks power-limited - check the "
                   f"laptop's performance mode, or switch VOICE off.")
            print(f"  \u26a0 {msg}", flush=True)
            self._emit("status", msg)

    # =========================================================================
    #  LANE 3 - PRESENTER  (unchanged from v11)
    # =========================================================================

    def _presenter(self) -> None:
        waited_since = None                     # v12 starvation instrument
        started = False                         # counts only once the feed has
                                                # begun (the first sentence split
                                                # warms up in ~4 s at setup)
        while True:
            try:
                record = self._present_q.get(timeout=0.2)
            except queue.Empty:
                if self._stop.is_set():
                    break
                # v12: the presenter ran dry while the story was still
                # writing - the one thing the GPU lend must never cause.
                # Waiting at the event gate is the player's pause, not a stall.
                if waited_since is None and started and not self._at_gate:
                    waited_since = time.time()
                elif waited_since is not None and self._at_gate:
                    waited_since = None
                continue
            if waited_since is not None:
                gap = time.time() - waited_since
                waited_since = None
                if gap >= STALL_REPORT_S:
                    self._record_timing("presenter starved", gap)
            started = True
            if record is _SENTINEL:
                break
            if self._stop.is_set():
                continue

            kind = record[0]

            if kind == "item":
                item = record[1]
                self._skip_seq = None
                self._emit("item", item)
                continue

            if kind == "item_end":
                item = record[1]
                self._backlog_words = max(0, self._backlog_words - len(item.text.split()))
                self._emit("item_done", item.seq)
                if (self.mode == "manual" and item.kind != "staged"
                        and not self._stop.is_set()):
                    self._advance.clear()
                    while not self._stop.is_set() and not self._advance.wait(timeout=0.2):
                        pass
                continue

            item, chunk = record[1], record[2]

            if self._skip_seq == item.seq:
                self._emit("speak_start", item.seq, chunk.idx, 0.0)
                self._emit("speak_end", item.seq, chunk.idx)
                continue

            self._pause.wait()
            if self._stop.is_set():
                continue

            self._skip.clear()
            self._emit("speak_start", item.seq, chunk.idx, chunk.seconds)

            if chunk.audio is not None:
                finished = tts.play_audio(chunk.audio, stop_event=self._skip)
            elif item.kind == "staged":
                finished = True
            else:
                self._sleep_interruptible(
                    max(READ_SECONDS_MIN, chunk.words * READ_SECONDS_PER_WORD))
                finished = not self._skip.is_set()

            self._emit("speak_end", item.seq, chunk.idx)

            if not finished and self._skip.is_set() and not self._stop.is_set():
                self._skip_seq = item.seq
                self._skip.clear()

        self._emit("done")

# =============================================================================
#  SECTION 5 - HEADLESS MODE
#
#  python story_lab_director12.py  runs the full pipeline in a console.
#    --mute       text-only (no Kokoro)
#    --no-images  no ComfyUI lane (v11's session exactly)
#    --rounds N   stop after N rounds
#    --auto       answer every armed input with "continue" (unattended runs)
#    --event TXT  with --auto: submit TXT as round 1's event instead
#    --story T    start from story T (built-in or saved; default Kerchoff Station)
#    --seed N     v12.2: the game seed (default: a random one, printed)
#    --load DIR   v12.2: resume the game in run folder DIR (its latest
#                 checkpoint, or --round N's)
# =============================================================================

class _ConsoleApp:
    """Minimal stand-in for the Tk app: after() just calls the function."""
    def after(self, _delay_ms, fn):
        fn()


def _headless_main() -> None:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    kinds = {"narration": "§", "line": ">", "event": "!", "staged": "↳",
             "system": "·"}
    state = {"item": None, "director": None}
    auto = "--auto" in sys.argv

    def show(item) -> None:
        state["item"] = item
        tag = kinds.get(item.kind, "?")
        who = f"{item.speaker}: " if item.speaker else ""
        print(f"\n {tag} [{item.round_num}] {who}", end="", flush=True)

    def speak_start(seq, idx, seconds) -> None:
        item = state["item"]
        if item and item.seq == seq and idx < len(item.chunks):
            print(item.chunks[idx].text + " ", end="", flush=True)

    scripted = (sys.argv[sys.argv.index("--event") + 1]
                if "--event" in sys.argv else "")
    # v12.3: --events "after round 1||after round 2||..." (empty = no event)
    script = (sys.argv[sys.argv.index("--events") + 1].split("||")
              if "--events" in sys.argv else [scripted] if scripted else [])

    def armed(r) -> None:
        print(f"\n  [input armed - type event for after round {r}, "
              f"Enter alone to continue]", flush=True)
        if auto:
            ev = script[r - 1].strip() if 0 < r <= len(script) else ""
            if ev:
                state["director"].submit_injection(ev)
            else:
                state["director"].continue_without_event()

    updaters = {
        "status":      lambda t: print(f"  [status] {t}", flush=True),
        "item":        show,
        "speak_start": speak_start,
        "item_done":   lambda _s: print("", flush=True),
        "memories":    lambda r, a, b: print(f"\n  [memories r{r}]\n  A: {a}\n  B: {b}",
                                             flush=True),
        "staged":      lambda r, raw, s, kept, sent: print(
            f"\n  [event r{r}] {'KEPT YOUR WORDS (conditioner gave up)' if kept else 'staged'}",
            flush=True),
        "await_injection": armed,
        "timing":      lambda l, s: print(f"  [time] {l}: {s:.1f}s", flush=True)
                                    if l.startswith(("gpu", "image", "music")) else None,
        "music_prompt": lambda r, b: print(f"  [music r{r} queued] {b}", flush=True),
        "music":       lambda r, p, b, take: print(f"  [music r{r} take {take}] {p}",
                                                   flush=True),
        "music_off":   lambda r: print(f"  [music] OFF - {r}", flush=True),
        "images_ready": lambda s: print(f"  [images] ready\n  {s}", flush=True),
        "images_off":  lambda r: print(f"  [images] OFF - {r}", flush=True),
        "portrait":    lambda slot, p, pr: print(f"  [portrait {slot}] {p}", flush=True),
        "scene_image": lambda r, p, pr, take: print(f"  [scene r{r} take {take}] {p}",
                                                    flush=True),
        "error":       lambda m: print(f"  [ERROR] {m}", flush=True),
        "done":        lambda: print("  [presentation drained]", flush=True),
    }

    rounds = 0
    if "--rounds" in sys.argv:
        rounds = int(sys.argv[sys.argv.index("--rounds") + 1])

    # v12.1: any story by title (built-in or saved); Kerchoff Station by default
    import story_lab_stories12 as stories
    title = (sys.argv[sys.argv.index("--story") + 1] if "--story" in sys.argv
             else stories.KERCHOFF["title"])
    story = stories.get_story(title)
    if story is None:
        print(f"  no story called {title!r}; known: "
              f"{[r['title'] for r in stories.list_stories()]}", flush=True)
        return
    config = stories.to_config(story)
    config.update({
        "voice_enabled":   "--mute" not in sys.argv,
        "beats_to_narrator": False,
        "rounds":          rounds or config["rounds"],
        "images_enabled":  "--no-images" not in sys.argv,
        "auto_launch_comfyui": True,
        "scene_style":     ("cinematic" if "--cinematic" in sys.argv
                            else "medium" if "--medium" in sys.argv else "classical"),
        # v12.4: --music [--music-style KEY] [--music-fast]
        "music_enabled":   "--music" in sys.argv,
        "music_style":     (sys.argv[sys.argv.index("--music-style") + 1]
                            if "--music-style" in sys.argv else "auto"),
        "music_codes":     "--music-fast" not in sys.argv,
        "portrait_refresh": "--living" in sys.argv,     # v12.4: living portraits
    })
    print(f"  story: {story['title']}  ({config['scene_style']} scenes"
          f"{', music' if config['music_enabled'] else ''})", flush=True)

    # v12.2: --seed N (the game seed), --load RUN_DIR [--round N] (resume)
    if "--seed" in sys.argv:
        config["game_seed"] = int(sys.argv[sys.argv.index("--seed") + 1])
    config["story_title"] = story["title"]
    resume = None
    if "--load" in sys.argv:
        import story_lab_saves12 as saves
        run = saves.resolve_run_dir(sys.argv[sys.argv.index("--load") + 1])
        rnd = int(sys.argv[sys.argv.index("--round") + 1]) if "--round" in sys.argv else None
        snap = saves.read_checkpoint(run, rnd)
        if snap is None:
            print(f"  no checkpoint in {run}", flush=True)
            return
        config = dict(snap["config"], voice_enabled="--mute" not in sys.argv,
                      images_enabled="--no-images" not in sys.argv,
                      music_enabled="--music" in sys.argv,
                      rounds=rounds or snap["config"].get("rounds", 0))
        resume = {"run_dir": run, "snapshot": snap}
        print(f"  resuming {run} after round {snap['round_done']} "
              f"(seed {snap['game_seed']})", flush=True)
    updaters["game_seed"] = lambda s: print(f"  [game seed] {s}", flush=True)
    updaters["checkpoint"] = lambda r: print(f"  [checkpoint] after round {r}", flush=True)
    updaters["resumed"] = lambda snap, run, branch: print(
        f"  [resumed] {len(snap['rounds'])} rounds restored"
        + (f"; later rounds moved to {branch}" if branch else ""), flush=True)

    app = _ConsoleApp()
    director = Director(app, updaters, config, resume=resume)
    state["director"] = director
    director.start()
    print(f"Story Lab v12 headless - engine {engine.ENGINE_VERSION}, "
          f"model {engine.MODEL}\nType an event and press Enter when armed "
          f"(empty Enter continues); 'quit' ends.\n", flush=True)
    try:
        if auto:
            while not director._stop.is_set() and director._threads[0].is_alive():
                time.sleep(0.5)
            time.sleep(2.0)
        else:
            while True:
                text = input()
                if text.strip().lower() in ("quit", "exit"):
                    break
                if text.strip():
                    if not director.submit_injection(text):
                        print("  [not armed yet - the round is still being written]",
                              flush=True)
                else:
                    director.continue_without_event()
    except (KeyboardInterrupt, EOFError):
        pass
    director.stop()
    time.sleep(0.5)
    images.shutdown_comfyui()            # only a server this process started
    print("Session ended.", flush=True)


if __name__ == "__main__":
    _headless_main()
