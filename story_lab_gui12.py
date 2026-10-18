"""
story_lab_gui12.py  —  Story Lab v12  //  GUI (widgets only)

RUN THIS FILE:   .venv/Scripts/python story_lab_gui12.py

WHAT CHANGED FROM THE v11 GUI
=============================
v12 brings the pictures back: two PORTRAITS and one large SCENE per round,
rendered by ComfyUI from the two workflow JSON files beside this script
(story_lab_images12, driven by story_lab_director12). Everything v11 built -
the karaoke feed, the caption bar, the always-enabled event box, the staging
line, the UI log - is carried over unchanged. Engine 12.0 is engine 11.6
promoted verbatim.

The layout returns to the three-column shape of the v3/v5 builds (feed |
portraits | scene), with v11's cast cards folded INTO the portraits:

  +--------------------------------------------------------------------------+
  | ◈ STORY LAB v12  ROUND 03  status              KARAOKE|TYPE|CALM VOICE END |
  +--------------------------+--------------+--------------------------------+
  | ▸ TRANSMISSION LOG  LIVE | CHARACTER A ↻| ▸ SCENE · ROUND 03           ↻ |
  |                          | [ portrait ] | +----------------------------+ |
  |  FEED (tk.Text)          |  VESS     ●  | |                            | |
  |  dim -> lit, sentence by |  role · voice| |   wide scene, 3:2, scales  | |
  |  sentence as it is spoken+--------------+ |   with the window          | |
  |                          | CHARACTER B ↻| +----------------------------+ |
  |                          | [ portrait ] |  the prompt it was drawn from  |
  |                          |  KAEL        |  [r1] [r2] [r3]   past scenes  |
  |                          +--------------+  STORY · VOICE · IMAGE · GPU   |
  |                          | NARRATOR  ●  |                       OBSERVE  |
  +--------------------------+--------------+--------------------------------+
  |  ▶  VESS   "the sentence currently being spoken"          (caption bar) |
  +--------------------------------------------------------------------------+
  |  ▸ INPUT [..........] SEND  CONTINUE  ◉ armed  PAUSE SKIP AUTO|MANUAL NEXT |
  +--------------------------------------------------------------------------+

HOW THE PICTURES BEHAVE
=======================
  - THE SPEAKER LIGHTS UP. The portrait card of whoever is being spoken
    gets its accent border and a dot (v11's cast-card cue, now on a face).
  - A SCENE NEVER RUNS AHEAD OF THE STORY. Generation runs ahead of
    presentation, so round 3's picture can be finished while round 2 is still
    being read. It is HELD until the presenter reaches round 3's opener; the
    header says "rendering round 3" or "round 3 ready" in the meantime.
  - CROSS-FADE. A new portrait or scene fades in over the old one (~0.4 s,
    eight PIL blends) instead of snapping.
  - SCENE HISTORY. Every round's scene stays as a thumbnail. Clicking one
    PINS the panel to that round; clicking the newest one (or the header's
    "live" tag) follows the story again.
  - RE-ROLL (↻). Same prompt, fresh seed, for the scene on screen or either
    portrait. It is queued and renders the next time the story lends the GPU
    - at once if the story is waiting for your event. Takes are kept side by
    side in the run folder; the newest take is shown.
  - WHAT IT WAS ASKED. The scene's CLIP prompt sits under the image, small
    and muted - the scene prompter is an engine role like any other, and its
    drift is worth seeing.
  - NO COMFYUI, NO CRASH. Images off (switched off on the setup screen,
    ComfyUI missing, a workflow file unusable) leaves the placeholders up
    with the reason, and the session is v11's text-and-voice game.

The setup screen gains a PICTURES row: images on/off, start ComfyUI if it is
not running (the Desktop app's backend, headless), a fresh portrait per round
(mood-keyed, off by default), plus a live probe of the server and a summary
of both workflow files (checkpoint, size, steps) read from the JSON itself.

Everything else in this header is v11's, kept as it was:

THE EVENT BOX IS NEVER DISABLED
===============================
It stays state="normal" for the whole session and its placeholder is set
exactly once. A disabled tk Entry SILENTLY IGNORES programmatic insert/delete,
so re-configuring placeholder_text while disabled left CTkEntry's placeholder
FLAG set with no placeholder in the widget - and CTkEntry.get() returns ""
whenever that flag is set. Arming state lives on the buttons and the ◉ lamp,
and _read_injection() reconciles get() against the raw widget as a backstop.

EVERY CONTROL IS LOGGED to runSaves/ui_<stamp>.log, stdout and the OBSERVE
drawer, with the arming state at the moment of the click.

THE TEXT/VOICE SYNCHRONISATION: the director hands the GUI an item's FULL
SENTENCE SPLIT before any audio exists, then reports speak_start/speak_end as
each sentence sounds - karaoke (default), typewriter, or calm, switchable
mid-session; caption bar; optional word walker; auto-scroll with a LIVE
button. The feed is a raw tk.Text for per-range colour tags, APPEND-ONLY, so a
character index captured at insert time stays valid for the session.

THREADING: this file never generates anything. Every director callback
arrives via app.after(0, ...) on the Tk main thread. Image decoding and the
fade frames are small enough to run there (a 1536x1024 PNG decodes in ~30 ms).
"""

import os
import re
import time
import threading
import tkinter as tk
import tkinter.messagebox                 # tk.messagebox only exists once imported
import customtkinter as ctk
from datetime import datetime

try:
    from PIL import Image
except ImportError:                       # Pillow ships with customtkinter
    Image = None

import story_lab_engine12 as engine
import story_lab_tts10 as tts            # v10's voice layer, unchanged in v12
import story_lab_images12 as images
import story_lab_music12 as music
import story_lab_stories12 as stories    # v12.1: built-in + saved stories
import story_lab_saves12 as saves        # v12.2: save games
from story_lab_director12 import Director, PresentationItem, TURNS_PER_ROUND

_RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runSaves")

FADE_STEPS = 8          # cross-fade frames; 0 = snap
FADE_MS    = 45         # per frame
THUMB_W, THUMB_H = 78, 52

# =============================================================================
#  SECTION 1 - PALETTES
# =============================================================================

_L = {   # setup screen - always neutral light
    "bg": "#f0f2f5", "card": "#ffffff", "border": "#d0d4dc",
    "accent": "#4a6fa5", "accent_dim": "#6b8cbf",
    "text": "#1a1f2e", "muted": "#6b7280",
}

THEMES = {
    "scifi": {
        "bg_deep": "#090912", "bg_panel": "#0d0d1a",
        "bg_widget": "#10101f", "bg_card": "#0a0a18", "bg_ribbon": "#080810",
        "primary": "#00f5ff", "primary_dim": "#00a8b5", "status_ok": "#00ff88",
        "char_a_accent": "#ffb347", "char_b_accent": "#c084fc",
        "text_log": "#dce0ff", "text_narr": "#88ccff", "text_res": "#88ff88",
        "text_inject": "#ff88dd", "text_muted": "#5a5a8a", "text_input": "#dce0ff",
        "dim": "#3a3a5c",
        "band_narr": "#122036", "band_a": "#2a2010", "band_b": "#221033",
        "band_event": "#2a0f22",
        "lit_narr": "#bfe4ff", "lit_a": "#ffd9a0", "lit_b": "#e2c6ff",
        "font_family": "Courier New", "corner": 10, "border_w": 1,
        "appearance": "dark",
        "title_text": "◈  STORY LAB v12  //  CYBERPUNK",
        "log_header": "▸ TRANSMISSION LOG",
        "scene_header": "▸ SCENE", "placeholder": "[ NO SIGNAL ]",
        "char_a_label": "CHARACTER A", "char_b_label": "CHARACTER B",
        "input_label": "▸ INPUT", "send_label": "SEND ▶",
    },
    "fantasy": {
        "bg_deep": "#EDE0C4", "bg_panel": "#E4D4A8",
        "bg_widget": "#FDF6E4", "bg_card": "#FBF3E0", "bg_ribbon": "#DFC88A",
        "primary": "#B8860B", "primary_dim": "#8B6508", "status_ok": "#2D6A2D",
        "char_a_accent": "#8B2020", "char_b_accent": "#5B3A8C",
        "text_log": "#2C1810", "text_narr": "#2C3A6A", "text_res": "#2D6A2D",
        "text_inject": "#7A2060", "text_muted": "#6B4E2A", "text_input": "#3D2B1A",
        "dim": "#BCA982",
        "band_narr": "#E7E2CE", "band_a": "#F3DED8", "band_b": "#E7DEF2",
        "band_event": "#F1DCEA",
        "lit_narr": "#1B2A5A", "lit_a": "#6E1414", "lit_b": "#3F2470",
        "font_family": "Georgia", "corner": 18, "border_w": 2,
        "appearance": "light",
        "title_text": "⚜   THE GREAT STORY   ⚜",
        "log_header": "❧  CHRONICLE",
        "scene_header": "✦  VISION", "placeholder": "[ NO VISION ]",
        "char_a_label": "⚗  CHARACTER A", "char_b_label": "✦  CHARACTER B",
        "input_label": "✦  SPEAK", "send_label": "PROCLAIM  ⚜",
    },
}

ACTIVE_THEME = "scifi"
def T(k): return THEMES[ACTIVE_THEME][k]

_DEMO_WORLD = ("A rusting orbital station above a dying gas giant, "
               "where salvage crews trade in secrets.")
_DEMO_A = ("A wary smuggler with a scarred jaw and a grey coat, quick to "
           "read a room, speaks in short clipped sentences, owes a dangerous debt.")
_DEMO_B = ("An overconfident debt collector in a red jacket, silver tongue, "
           "hides fear behind jokes, wants the bounty on Vess.")

_AUDITION = {
    "a": "This is my voice. You will be hearing rather a lot of it.",
    "b": "And this is mine. Try to keep up.",
    "narrator": "The story begins here, in a place you have not yet imagined.",
}

# =============================================================================
#  SECTION 2 - THE APP
# =============================================================================

class StoryLabApp(ctk.CTk):
    """One window, two screens, one Director per session."""

    def __init__(self):
        super().__init__()
        self.title("Story Lab v12")
        # Fit the WORK AREA (screen minus taskbar) in LOGICAL pixels - the
        # unit CTk's geometry() takes. Measured on this laptop (150%): Tk's
        # winfo_screenwidth() already reports logical 1707, while the window's
        # own winfo_width() is physical, so dividing the former by the scale
        # (the first v12 draft) opened the window at its minimum size and cut
        # the portrait column off. The Win32 work area is physical, so it is
        # divided here; anything else falls back to Tk's logical numbers.
        aw, ah = self._work_area_logical()
        w, h = min(1640, aw - 40), min(960, ah - 50)
        self.geometry(f"{w}x{h}+{max(0, (aw - w) // 2)}+8")
        self.minsize(1240, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.director = None
        self.drawer = None
        self.drawer_box = None

        self._armed_round = None
        self._ui_t0 = time.time()
        self._ui_log_path = os.path.join(
            _RUNS_DIR, f"ui_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        try:
            os.makedirs(_RUNS_DIR, exist_ok=True)
            with open(self._ui_log_path, "w", encoding="utf-8") as f:
                f.write(f"Story Lab v12 UI log — {datetime.now():%Y-%m-%d %H:%M:%S}\n"
                        f"engine v{engine.ENGINE_VERSION} · {engine.MODEL}\n"
                        f"voice stack: {tts.tts_status()}\n\n")
        except Exception as e:
            print(f"  ! UI log unavailable ({e})", flush=True)
            self._ui_log_path = None

        # --- feed synchronisation state ---
        self._items = {}
        self._ranges = {}
        self._pending_nl = set()
        self._word_jobs = []
        self._follow = True

        # --- options mirrored from the setup screen ---
        self.reveal_style = "karaoke"
        self.word_sync = False
        self.caption_on = True

        self._preview_lock = threading.Lock()
        self.music_player = None    # v12.4: one MusicPlayer for the app's life
        self._reset_image_state()
        self._build_setup_screen()

    def _work_area_logical(self):
        try:
            import ctypes
            import ctypes.wintypes as wt
            rect = wt.RECT()
            ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)
            scale = self._get_window_scaling()
            return (int((rect.right - rect.left) / scale),
                    int((rect.bottom - rect.top) / scale))
        except Exception:
            return self.winfo_screenwidth(), self.winfo_screenheight()

    def _reset_image_state(self):
        self._img = {}              # key ("scene", "a", "b") -> display state
        self._scenes = {}           # round -> [(path, prompt), ...] one per take
        self._scene_prompts = {}    # round -> prompt (queued, maybe not rendered)
        self._presented_round = 0   # the round whose opener is on screen
        self._pinned_round = None   # None = follow the story
        self._shown_scene = None    # (round, take) on screen
        self._thumbs = {}           # round -> (button, CTkImage)
        self._images_on = False
        # v12.4 music: like the scenes, a round's track waits for its round
        self._music = {}            # round -> [(path, body), ...] one per take
        self._music_prompts = {}    # round -> body (queued, maybe not rendered)
        self._music_playing = None  # (round, take) loaded into the player
        self._music_on = False
        self._music_status = ""

    # =========================================================================
    #  SCREEN 1 - SETUP
    # =========================================================================

    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=_L["card"], corner_radius=10,
                            border_color=_L["border"], border_width=1)

    def _build_setup_screen(self):
        ctk.set_appearance_mode("light")
        self.setup_root = ctk.CTkFrame(self, fg_color=_L["bg"], corner_radius=0)
        self.setup_root.pack(fill="both", expand=True)
        self.setup_frame = ctk.CTkScrollableFrame(self.setup_root, fg_color=_L["bg"],
                                                  corner_radius=0)
        self.setup_frame.pack(fill="both", expand=True)
        f = self.setup_frame

        ctk.CTkLabel(f, text="STORY LAB  v12", text_color=_L["accent"],
                     font=("Segoe UI", 30, "bold")).pack(pady=(18, 2))
        ctk.CTkLabel(f, text="two characters · one world · your events "
                             "· spoken aloud · pictured",
                     text_color=_L["muted"], font=("Segoe UI", 13)).pack(pady=(0, 12))

        # ---- v12.1: stories - the built-in ones (three since v12.4) and the player's saved ones
        scard = self._card(f)
        scard.pack(fill="x", padx=40, pady=6)
        srow = ctk.CTkFrame(scard, fg_color="transparent")
        srow.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(srow, text="STORY", text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        self.story_menu = ctk.CTkOptionMenu(srow, values=["—"], width=380,
                                            fg_color=_L["accent_dim"],
                                            dynamic_resizing=False)
        self.story_menu.pack(side="left", padx=(10, 6))
        for text, cmd, w in (("LOAD", self._story_load, 80),
                             ("SAVE AS…", self._story_save, 100),
                             ("DELETE", self._story_delete, 80)):
            ctk.CTkButton(srow, text=text, width=w, height=28,
                          fg_color=_L["accent_dim"], hover_color=_L["accent"],
                          font=("Segoe UI", 12, "bold"),
                          command=cmd).pack(side="left", padx=4)
        self.story_status = ctk.CTkLabel(scard, text="", text_color=_L["muted"],
                                         font=("Segoe UI", 11), anchor="w")
        self.story_status.pack(fill="x", padx=14, pady=(0, 10))
        self._story_titles = {}           # menu label -> story title

        # ---- v12.2: the game - seed, continue, load ---------------------------
        gcard = self._card(f)
        gcard.pack(fill="x", padx=40, pady=6)
        grow = ctk.CTkFrame(gcard, fg_color="transparent")
        grow.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(grow, text="GAME", text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        ctk.CTkLabel(grow, text="   SEED", text_color=_L["muted"],
                     font=("Segoe UI", 11, "bold")).pack(side="left")
        self.seed_entry = ctk.CTkEntry(grow, width=130, fg_color="#ffffff",
                                       text_color=_L["text"], border_color=_L["border"],
                                       placeholder_text="random")
        self.seed_entry.pack(side="left", padx=(6, 4))
        ctk.CTkButton(grow, text="🎲", width=34, height=28, fg_color=_L["accent_dim"],
                      hover_color=_L["accent"], font=("Segoe UI", 13),
                      command=self._roll_seed).pack(side="left")
        ctk.CTkButton(grow, text="LOAD GAME…", width=120, height=28,
                      fg_color=_L["accent_dim"], hover_color=_L["accent"],
                      font=("Segoe UI", 12, "bold"),
                      command=self._open_load_dialog).pack(side="right", padx=4)
        self.continue_btn = ctk.CTkButton(grow, text="CONTINUE LAST GAME", width=180,
                                          height=28, fg_color=_L["accent"],
                                          hover_color=_L["accent_dim"],
                                          font=("Segoe UI", 12, "bold"),
                                          command=self._continue_last_game)
        self.continue_btn.pack(side="right", padx=4)
        self.game_status = ctk.CTkLabel(gcard, text="", text_color=_L["muted"],
                                        font=("Segoe UI", 11), anchor="w")
        self.game_status.pack(fill="x", padx=14, pady=(0, 10))
        self._refresh_game_status()

        # ---- world ----------------------------------------------------------
        world_card = self._card(f)
        world_card.pack(fill="x", padx=40, pady=6)
        ctk.CTkLabel(world_card, text="THE WORLD", text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        self.world_box = ctk.CTkTextbox(world_card, height=62, fg_color="#ffffff",
                                        text_color=_L["text"], border_color=_L["border"],
                                        border_width=1, font=("Segoe UI", 13), wrap="word")
        self.world_box.pack(fill="x", padx=14, pady=(0, 6))
        self.world_box.insert("1.0", _DEMO_WORLD)
        ctk.CTkLabel(world_card, text="ALREADY HAPPENED  (optional — one sentence "
                                      "of history the opener may lean on)",
                     text_color=_L["muted"], font=("Segoe UI", 11)).pack(anchor="w", padx=14)
        self.prior_entry = ctk.CTkEntry(world_card, fg_color="#ffffff",
                                        text_color=_L["text"], border_color=_L["border"],
                                        placeholder_text="e.g. They have met once before, "
                                                         "and it ended badly.")
        self.prior_entry.pack(fill="x", padx=14, pady=(2, 12))

        # ---- characters -------------------------------------------------------
        chars_row = ctk.CTkFrame(f, fg_color="transparent")
        chars_row.pack(fill="x", padx=40, pady=6)
        chars_row.grid_columnconfigure((0, 1), weight=1, uniform="chars")
        self.char_widgets = {}
        for i, (slot, dname, ddesc) in enumerate(
                (("a", "Vess", _DEMO_A), ("b", "Kael", _DEMO_B))):
            card = self._card(chars_row)
            card.grid(row=0, column=i, sticky="nsew",
                      padx=(0 if i == 0 else 8, 8 if i == 0 else 0))

            head = ctk.CTkFrame(card, fg_color="transparent")
            head.pack(fill="x", padx=14, pady=(10, 4))
            ctk.CTkLabel(head, text=f"CHARACTER {slot.upper()}",
                         text_color=_L["accent"],
                         font=("Segoe UI", 13, "bold")).pack(side="left")
            ctk.CTkButton(head, text="▶ hear voice", width=110, height=26,
                          fg_color=_L["accent_dim"], hover_color=_L["accent"],
                          font=("Segoe UI", 11),
                          command=lambda s=slot: self._audition(s)).pack(side="right")

            row = ctk.CTkFrame(card, fg_color="transparent"); row.pack(fill="x", padx=14)
            name = ctk.CTkEntry(row, placeholder_text="Name", width=140,
                                fg_color="#ffffff", text_color=_L["text"],
                                border_color=_L["border"])
            name.pack(side="left"); name.insert(0, dname)
            gender = ctk.CTkOptionMenu(row, values=list(stories.GENDERS),
                                       width=115, fg_color=_L["accent_dim"])
            gender.pack(side="left", padx=6)
            gender.set("female" if slot == "a" else "male")
            age = ctk.CTkOptionMenu(row, values=list(stories.AGES),
                                    width=125, fg_color=_L["accent_dim"])
            age.pack(side="left"); age.set("MiddleAged" if slot == "a" else "YoungAdult")

            row2 = ctk.CTkFrame(card, fg_color="transparent")
            row2.pack(fill="x", padx=14, pady=(6, 0))
            ident = ctk.CTkEntry(row2, placeholder_text="identity (optional): full name, "
                                                        "pronouns, what they are",
                                 fg_color="#ffffff", text_color=_L["text"],
                                 border_color=_L["border"], font=("Segoe UI", 11))
            ident.pack(side="left", fill="x", expand=True)
            addr = ctk.CTkEntry(row2, placeholder_text="called (optional)", width=140,
                                fg_color="#ffffff", text_color=_L["text"],
                                border_color=_L["border"], font=("Segoe UI", 11))
            addr.pack(side="left", padx=(6, 0))

            desc = ctk.CTkTextbox(card, height=84, fg_color="#ffffff",
                                  text_color=_L["text"], border_color=_L["border"],
                                  border_width=1, font=("Segoe UI", 12), wrap="word")
            desc.pack(fill="x", padx=14, pady=(6, 12)); desc.insert("1.0", ddesc)
            self.char_widgets[slot] = {"name": name, "gender": gender, "age": age,
                                       "identity": ident, "address": addr, "desc": desc}

        # ---- narrator + pacing --------------------------------------------------
        opts = self._card(f)
        opts.pack(fill="x", padx=40, pady=6)
        orow = ctk.CTkFrame(opts, fg_color="transparent")
        orow.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(orow, text="NARRATOR VOICE", text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        self.narr_gender = ctk.CTkOptionMenu(orow, values=list(stories.NARRATOR_GENDERS),
                                             width=105, fg_color=_L["accent_dim"])
        self.narr_gender.pack(side="left", padx=(10, 4)); self.narr_gender.set("Woman")
        self.narr_accent = ctk.CTkOptionMenu(
            orow, values=list(stories.NARRATOR_ACCENTS),
            width=155, fg_color=_L["accent_dim"])
        self.narr_accent.pack(side="left", padx=4)
        self.narr_accent.set("Rough (American)")
        ctk.CTkButton(orow, text="▶ hear voice", width=110, height=26,
                      fg_color=_L["accent_dim"], hover_color=_L["accent"],
                      font=("Segoe UI", 11),
                      command=lambda: self._audition("narrator")).pack(side="left", padx=8)

        ctk.CTkLabel(orow, text="   TURNS / ROUND", text_color=_L["accent"],
                     font=("Segoe UI", 12, "bold")).pack(side="left", padx=(18, 4))
        self.turns_menu = ctk.CTkOptionMenu(orow, values=list(stories.TURNS), width=65,
                                            fg_color=_L["accent_dim"])
        self.turns_menu.pack(side="left"); self.turns_menu.set(str(TURNS_PER_ROUND))
        ctk.CTkLabel(orow, text="   ROUNDS", text_color=_L["accent"],
                     font=("Segoe UI", 12, "bold")).pack(side="left", padx=(14, 4))
        self.rounds_menu = ctk.CTkOptionMenu(orow, values=list(stories.ROUNDS),
                                             width=90, fg_color=_L["accent_dim"])
        self.rounds_menu.pack(side="left"); self.rounds_menu.set("endless")

        prow = ctk.CTkFrame(opts, fg_color="transparent")
        prow.pack(fill="x", padx=14, pady=(6, 4))
        ctk.CTkLabel(prow, text="HOW THE TEXT MEETS THE VOICE",
                     text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        self.reveal_menu = ctk.CTkOptionMenu(
            prow, values=["Karaoke  (dim → lit)",
                          "Typewriter  (appears as spoken)",
                          "Calm  (quiet band only)"],
            width=250, fg_color=_L["accent_dim"])
        self.reveal_menu.pack(side="left", padx=(10, 8))
        self.reveal_menu.set("Karaoke  (dim → lit)")
        self.theme_menu = ctk.CTkOptionMenu(prow, values=list(stories.THEMES),
                                            width=120, fg_color=_L["accent_dim"])
        self.theme_menu.pack(side="left", padx=4); self.theme_menu.set("Cyberpunk")

        trow = ctk.CTkFrame(opts, fg_color="transparent")
        trow.pack(fill="x", padx=14, pady=(0, 4))
        self.sw_voice = ctk.CTkSwitch(trow, text="Voice (Kokoro, CPU)",
                                      progress_color=_L["accent"])
        self.sw_voice.pack(side="left", padx=(0, 16)); self.sw_voice.select()
        self.sw_caption = ctk.CTkSwitch(trow, text="Caption bar",
                                        progress_color=_L["accent"])
        self.sw_caption.pack(side="left", padx=16); self.sw_caption.select()
        self.sw_words = ctk.CTkSwitch(trow, text="Word-level sync (approximate)",
                                      progress_color=_L["accent"])
        self.sw_words.pack(side="left", padx=16)
        self.sw_beats = ctk.CTkSwitch(trow, text="Narrator reads *action beats*",
                                      progress_color=_L["accent"])
        self.sw_beats.pack(side="left", padx=16)

        erow = ctk.CTkFrame(opts, fg_color="transparent")
        erow.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(erow, text="YOUR EVENTS", text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        self.sw_staging = ctk.CTkSwitch(erow, text="Show how your event was staged",
                                        progress_color=_L["accent"])
        self.sw_staging.pack(side="left", padx=(10, 12)); self.sw_staging.select()
        ctk.CTkLabel(erow, text="the characters are handed a rewrite of what you "
                                "type - this shows it under your line",
                     text_color=_L["muted"], font=("Segoe UI", 11)).pack(side="left")

        # ---- v12: pictures ----------------------------------------------------
        pics = self._card(f)
        pics.pack(fill="x", padx=40, pady=6)
        irow = ctk.CTkFrame(pics, fg_color="transparent")
        irow.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(irow, text="PICTURES", text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        self.sw_images = ctk.CTkSwitch(irow, text="Portraits + scene (ComfyUI)",
                                       progress_color=_L["accent"])
        self.sw_images.pack(side="left", padx=(10, 16)); self.sw_images.select()
        self.sw_launch = ctk.CTkSwitch(irow, text="Start ComfyUI if it is not running",
                                       progress_color=_L["accent"])
        self.sw_launch.pack(side="left", padx=16); self.sw_launch.select()
        self.sw_refresh = ctk.CTkSwitch(irow, text="✨ Living portraits — faces follow the story",
                                        progress_color=_L["accent"])     # default OFF
        self.sw_refresh.pack(side="left", padx=16)
        # v12.3: Classical = the empty-place scene (v12.1); Cinematic = both
        # leads drawn in the scene in their current clothes (Anima workflow).
        # v12.4: MEDIUM between them (both leads, drawn by NovaFurry); the
        # choice is three large buttons with a line explaining the one picked
        # (the user: "make the choice more pronounced").
        srow = ctk.CTkFrame(pics, fg_color="transparent")
        srow.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(srow, text="SCENE STYLE", text_color=_L["accent"],
                     font=("Segoe UI", 15, "bold")).pack(side="left", padx=(0, 14))
        # v12.3 Setup: only the styles that were installed are offered
        # (Medium needs only the Classical model)
        styles = images.available_styles()
        offered = [label for label, key in self._SCENE_STYLES.items()
                   if styles.get("classical" if key == "medium" else key)]
        self.scene_style_menu = ctk.CTkSegmentedButton(
            srow, values=offered or ["not installed"], height=42,
            font=("Segoe UI", 14, "bold"), dynamic_resizing=False,
            selected_color="#23406e", selected_hover_color="#23406e",
            unselected_color=_L["accent_dim"], unselected_hover_color=_L["accent"],
            text_color="#ffffff", command=self._scene_style_changed)
        self.scene_style_menu.set((offered or ["not installed"])[0])
        self.scene_style_menu.pack(side="left", fill="x", expand=True)
        self.scene_style_hint = ctk.CTkLabel(pics, text="", text_color=_L["text"],
                                             font=("Segoe UI", 12), anchor="w",
                                             justify="left", wraplength=1100)
        self.scene_style_hint.pack(fill="x", padx=14, pady=(4, 2))
        if not offered:                          # text + voice only
            self.scene_style_menu.configure(state="disabled")
            self.sw_images.deselect()
            self.sw_images.configure(state="disabled")
            self.sw_refresh.configure(state="disabled")
        self._scene_style_changed(self.scene_style_menu.get(), log=False)
        self.comfy_label = ctk.CTkLabel(pics, text="ComfyUI: checking...",
                                        text_color=_L["muted"], font=("Segoe UI", 11),
                                        anchor="w", justify="left")
        self.comfy_label.pack(fill="x", padx=14, pady=(2, 0))
        wf_text = (f"portrait  ·  {images.workflow_summary(images.WORKFLOW_PORTRAIT_FILE)}\n"
                   f"scene     ·  {images.workflow_summary(images.WORKFLOW_SCENE_FILE)}\n"
                   f"cinematic ·  {images.workflow_summary(images.WORKFLOW_CINEMATIC_FILE)}")
        ctk.CTkLabel(pics, text=wf_text, text_color=_L["muted"],
                     font=("Consolas", 11), anchor="w",
                     justify="left").pack(fill="x", padx=14, pady=(0, 6))
        prow2 = ctk.CTkFrame(pics, fg_color="transparent")
        prow2.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(prow2, text="✎  Picture prompts…", width=170, height=28,
                      fg_color=_L["accent_dim"], hover_color=_L["accent"],
                      font=("Segoe UI", 12),
                      command=self._open_prompts_screen).pack(side="left")
        self.prompts_hint = ctk.CTkLabel(prow2, text="", text_color=_L["muted"],
                                         font=("Segoe UI", 11), anchor="w")
        self.prompts_hint.pack(side="left", padx=10)
        self._refresh_prompts_hint()
        threading.Thread(target=self._probe_comfy, daemon=True).start()

        # ---- v12.4: music ------------------------------------------------------
        mus = self._card(f)
        mus.pack(fill="x", padx=40, pady=6)
        mrow = ctk.CTkFrame(mus, fg_color="transparent")
        mrow.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(mrow, text="MUSIC", text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        self.sw_music = ctk.CTkSwitch(mrow, text="Background music (ComfyUI · ACE-Step 1.5)",
                                      progress_color=_L["accent"])
        self.sw_music.pack(side="left", padx=(10, 16))
        # v12.4 Setup: offered when it was installed (a source checkout: always)
        if (music.MusicPlayer.available() and os.path.isfile(music.WORKFLOW_MUSIC_FILE)
                and images.available_styles().get("music")):
            self.sw_music.select()
        else:
            self.sw_music.configure(state="disabled",
                                    text="Background music - not installed (run Story Lab Setup)")
        self.music_style_menu = ctk.CTkOptionMenu(
            mrow, values=list(self._MUSIC_STYLES), width=230,
            fg_color=_L["accent_dim"], button_color=_L["accent_dim"],
            button_hover_color=_L["accent"])
        self.music_style_menu.set(next(iter(self._MUSIC_STYLES)))
        self.music_style_menu.pack(side="left", padx=(0, 16))
        self.sw_music_fast = ctk.CTkSwitch(mrow, text="Fast (no audio codes)",
                                           progress_color=_L["accent"])  # default OFF
        self.sw_music_fast.pack(side="left", padx=4)
        ctk.CTkLabel(mus, text="A new instrumental track for every round, made last - after "
                               "the round's text and pictures - from its mood and the story's "
                               "genre, put through the equaliser, then looped under the voices "
                               "(it dips while they speak) until the next one. Play / pause, "
                               "volume and regenerate are on the MUSIC card beside the "
                               "portraits. Fast skips ACE-Step's audio-code step (several "
                               "times quicker; judge the sound).",
                     text_color=_L["muted"], font=("Segoe UI", 11), anchor="w",
                     justify="left", wraplength=1100).pack(fill="x", padx=14, pady=(2, 12))

        # ---- begin ----------------------------------------------------------------
        self.begin_btn = ctk.CTkButton(f, text="BEGIN THE STORY", height=44, width=280,
                                       fg_color=_L["accent"], hover_color=_L["accent_dim"],
                                       font=("Segoe UI", 15, "bold"),
                                       command=self._begin_session)
        self.begin_btn.pack(pady=14)
        model_short = engine.MODEL.split("/")[-1]
        self.setup_status = ctk.CTkLabel(
            f, text=f"engine v{engine.ENGINE_VERSION} · {model_short} on the GPU, "
                    f"lent to ComfyUI for pictures · Kokoro on the CPU "
                    f"· voice: {tts.tts_status()}",
            text_color=_L["muted"], font=("Segoe UI", 12))
        self.setup_status.pack(pady=(0, 18))

        for label, widget in (("char A gender",   self.char_widgets["a"]["gender"]),
                              ("char A age",      self.char_widgets["a"]["age"]),
                              ("char B gender",   self.char_widgets["b"]["gender"]),
                              ("char B age",      self.char_widgets["b"]["age"]),
                              ("narrator gender", self.narr_gender),
                              ("narrator accent", self.narr_accent),
                              ("turns/round",     self.turns_menu),
                              ("rounds",          self.rounds_menu),
                              ("music style",     self.music_style_menu),
                              ("reveal style",    self.reveal_menu),
                              ("theme",           self.theme_menu)):
            widget.configure(command=lambda v, n=label: self._ui_log(f"MENU {n} = {v}"))
        for label, widget in (("voice",           self.sw_voice),
                              ("caption bar",     self.sw_caption),
                              ("word sync",       self.sw_words),
                              ("beats→narrator",  self.sw_beats),
                              ("show staging",    self.sw_staging),
                              ("images",          self.sw_images),
                              ("launch comfyui",  self.sw_launch),
                              ("portrait refresh", self.sw_refresh),
                              ("music",           self.sw_music),
                              ("music fast",      self.sw_music_fast)):
            widget.configure(command=lambda n=label, w=widget:
                             self._ui_log(f"SWITCH {n} = "
                                          f"{'on' if w.get() else 'off'}"))
        # v12.1: the setup opens on the first built-in story (Hogwarts)
        first = stories.BUILTIN_STORIES[0]["title"]
        self._refresh_story_menu(select=first)
        self._apply_story(stories.get_story(first))
        self.story_status.configure(text=f"★ {first}  ·  built in")
        self._ui_log("setup screen ready")

    # =========================================================================
    #  SCREEN 1b - PICTURE PROMPTS  (v12.1)
    #
    #  Every picture's text is  POSITIVE PREPEND + story part + POSITIVE
    #  POSTPEND, and its negative is  NEGATIVE PREPEND + NEGATIVE POSTPEND,
    #  separately for the scene and the portraits. Saved to
    #  image_prompt_settings.json; read at BEGIN. The story part is the
    #  scene painter's three layers (scene) or the character's look (portrait).
    # =========================================================================

    _PROMPT_FIELD_LABELS = (
        ("pos_prepend",  "POSITIVE · before the story part"),
        ("pos_postpend", "POSITIVE · after the story part"),
        ("neg_prepend",  "NEGATIVE · first"),
        ("neg_postpend", "NEGATIVE · then"),
    )
    _PROMPT_SAMPLE_BODY = {
        "scene": "‹place›, ‹objects and effects of this moment›, ‹light›",
        "portrait": "‹the character's look›, ‹age› ‹gender›",
        "cine_portrait": "1girl, solo, portrait, upper body, looking at viewer / ‹A›, a "
                         "young woman with ‹looks›, wearing ‹clothes now›. / Behind: "
                         "‹place›, ‹light›.",
        "medium": "2people, 1girl, 1boy, duo, 1girl, ‹looks›, ‹clothes now›, ‹what she is "
                  "doing›, 1boy, ‹looks›, ‹clothes now›, ‹what he is doing›, ‹place›, "
                  "‹light›, ‹others›",
        "cinematic": "1girl, 1boy, two people / ‹place›, ‹light›. / On the left is "
                     "‹A›, a young woman with ‹looks›, wearing ‹clothes now›; ‹what she "
                     "is doing›. / On the right is ‹B›, ... / Around them: ‹objects›. / "
                     "In the background: ‹others›.",
    }

    def _refresh_prompts_hint(self):
        try:
            s = images.load_prompt_settings()
            saved = os.path.isfile(images.PROMPT_SETTINGS_FILE)
            self.prompts_hint.configure(
                text=f"scene starts with “{s['scene']['pos_prepend'][:48]}”"
                     f"{'' if saved else '  (defaults)'}")
        except Exception:
            pass

    def _open_prompts_screen(self):
        self._ui_log("CLICK picture prompts")
        self.setup_root.pack_forget()
        self._prompt_boxes = {}
        settings = images.load_prompt_settings()
        defaults = images.default_prompt_settings()
        root = ctk.CTkFrame(self, fg_color=_L["bg"], corner_radius=0)
        root.pack(fill="both", expand=True)
        self.prompts_root = root
        page = ctk.CTkScrollableFrame(root, fg_color=_L["bg"], corner_radius=0)
        page.pack(fill="both", expand=True)

        ctk.CTkLabel(page, text="PICTURE PROMPTS", text_color=_L["accent"],
                     font=("Segoe UI", 26, "bold")).pack(pady=(16, 2))
        ctk.CTkLabel(page, text="what is written around the story's part of every "
                                "picture prompt — for the scene and for the portraits",
                     text_color=_L["muted"], font=("Segoe UI", 13)).pack(pady=(0, 6))
        ctk.CTkLabel(
            page, justify="left", anchor="w", text_color=_L["text"],
            font=("Segoe UI", 12), wraplength=1100,
            text=("The picture model reads the FRONT of a prompt hardest (ComfyUI encodes "
                  "long prompts in 77-token pieces, but the overall look comes from the "
                  "first piece), so what the picture IS goes first. For a scene without "
                  "people the tag-trained checkpoints use “no humans, scenery”; people "
                  "belong in the negative. “still life” (nature morte) is the tag for an "
                  "arrangement of objects — good for a table of things, too close-up for "
                  "a whole room or landscape.")).pack(fill="x", padx=44, pady=(0, 8))

        for kind, title in (("scene", "THE SCENE  (the large image) · Classical"),
                            ("portrait", "THE PORTRAITS"),
                            ("medium", "THE SCENE · Medium  (NovaFurry: both characters "
                                       "in the picture, as tags)"),
                            ("cinematic", "THE SCENE · Cinematic  (Anima: both characters "
                                          "in the picture; one line per part, not commas)"),
                            ("cine_portrait", "THE PORTRAITS · Cinematic  (Anima: the "
                                              "character as they are now, where they are)")):
            card = self._card(page)
            card.pack(fill="x", padx=40, pady=6)
            ctk.CTkLabel(card, text=title, text_color=_L["accent"],
                         font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14,
                                                             pady=(10, 4))
            grid = ctk.CTkFrame(card, fg_color="transparent")
            grid.pack(fill="x", padx=14)
            grid.grid_columnconfigure((0, 1), weight=1, uniform=f"g{kind}")
            for i, (field, label) in enumerate(self._PROMPT_FIELD_LABELS):
                cell = ctk.CTkFrame(grid, fg_color="transparent")
                cell.grid(row=i // 2, column=i % 2, sticky="nsew",
                          padx=(0 if i % 2 == 0 else 8, 8 if i % 2 == 0 else 0), pady=4)
                head = ctk.CTkFrame(cell, fg_color="transparent")
                head.pack(fill="x")
                ctk.CTkLabel(head, text=label, text_color=_L["muted"],
                             font=("Segoe UI", 11, "bold")).pack(side="left")
                default_text = defaults[kind][field]
                ctk.CTkButton(head, text="↺ default" if (field != "neg_prepend"
                                                         or kind.startswith("cine"))
                              else "↺ from the JSON", width=96, height=22,
                              fg_color=_L["accent_dim"], hover_color=_L["accent"],
                              font=("Segoe UI", 10),
                              command=lambda k=kind, f=field, d=default_text:
                              self._set_prompt_box(k, f, d)).pack(side="right")
                box = ctk.CTkTextbox(cell, height=70, fg_color="#ffffff",
                                     text_color=_L["text"], border_color=_L["border"],
                                     border_width=1, font=("Consolas", 11), wrap="word")
                box.pack(fill="x", pady=(2, 0))
                box.insert("1.0", settings[kind][field])
                box.bind("<KeyRelease>", lambda _e, k=kind: self._update_prompt_preview(k))
                self._prompt_boxes[(kind, field)] = box
            prev = ctk.CTkLabel(card, text="", text_color=_L["muted"], anchor="w",
                                justify="left", font=("Consolas", 10), wraplength=1080)
            prev.pack(fill="x", padx=14, pady=(6, 12))
            self._prompt_boxes[(kind, "preview")] = prev
        # Only once BOTH cards exist: the scene card's preview reads the box
        # values, and built alone it found no portrait boxes and stayed blank.
        for kind in images.PROMPT_KINDS:
            self._update_prompt_preview(kind)

        brow = ctk.CTkFrame(page, fg_color="transparent")
        brow.pack(pady=14)
        ctk.CTkButton(brow, text="SAVE AND GO BACK", width=200, height=40,
                      fg_color=_L["accent"], hover_color=_L["accent_dim"],
                      font=("Segoe UI", 14, "bold"),
                      command=lambda: self._close_prompts_screen(save=True)).pack(side="left", padx=6)
        ctk.CTkButton(brow, text="CANCEL", width=120, height=40,
                      fg_color=_L["accent_dim"], hover_color=_L["accent"],
                      font=("Segoe UI", 13),
                      command=lambda: self._close_prompts_screen(save=False)).pack(side="left", padx=6)
        ctk.CTkButton(brow, text="ALL TO DEFAULTS", width=160, height=40,
                      fg_color=_L["accent_dim"], hover_color=_L["accent"],
                      font=("Segoe UI", 13),
                      command=self._reset_prompt_boxes).pack(side="left", padx=6)

    def _prompt_box_values(self) -> dict:
        return {kind: {f: self._prompt_boxes[(kind, f)].get("1.0", "end").strip()
                       for f, _l in self._PROMPT_FIELD_LABELS}
                for kind in images.PROMPT_KINDS}

    def _set_prompt_box(self, kind, field, text):
        box = self._prompt_boxes[(kind, field)]
        box.delete("1.0", "end")
        box.insert("1.0", text)
        self._update_prompt_preview(kind)

    def _reset_prompt_boxes(self):
        self._ui_log("CLICK picture prompts: all to defaults")
        for kind, fields in images.default_prompt_settings().items():
            for field, text in fields.items():
                self._set_prompt_box(kind, field, text)

    def _update_prompt_preview(self, kind):
        try:
            values = self._prompt_box_values()
            pos, neg = images.wrap_prompt(kind, self._PROMPT_SAMPLE_BODY[kind], values)
            self._prompt_boxes[(kind, "preview")].configure(
                text=f"SENT AS ▸ positive: {pos}\n          negative: {neg}")
        except Exception:
            pass

    def _close_prompts_screen(self, save: bool):
        if save:
            values = self._prompt_box_values()
            try:
                images.save_prompt_settings(values)
                self._ui_log("SAVED picture prompts: " + " | ".join(
                    f"{k}.{f}={v[:40]!r}" for k, fs in values.items() for f, v in fs.items()))
            except Exception as e:
                self._ui_log(f"picture prompts NOT saved: {e}")
        else:
            self._ui_log("CLICK picture prompts: cancel")
        self.prompts_root.destroy()
        self.setup_root.pack(fill="both", expand=True)
        self._refresh_prompts_hint()

    # =========================================================================
    #  v12.1 - STORIES  (save / load what the setup screen describes)
    # =========================================================================

    def _refresh_story_menu(self, select: str = None):
        self._story_titles = {}
        labels = []
        for row in stories.list_stories():
            label = ("★ " if row["builtin"] else "") + row["title"]
            self._story_titles[label] = row["title"]
            labels.append(label)
        self.story_menu.configure(values=labels)
        if select is not None:
            label = next((l for l, t in self._story_titles.items() if t == select), None)
            if label:
                self.story_menu.set(label)

    @staticmethod
    def _set_entry(entry, text):
        entry.delete(0, "end")             # an unfocused, emptied CTkEntry shows
        if text:                           # its placeholder again; insert() then
            entry.insert(0, text)          # clears it - no stale placeholder flag

    @staticmethod
    def _set_textbox(box, text):
        box.delete("1.0", "end")
        box.insert("1.0", text or "")

    def _collect_story(self) -> dict:
        """Everything the setup screen describes, as a story dict."""
        def char(slot):
            w = self.char_widgets[slot]
            return {"name": w["name"].get().strip(), "gender": w["gender"].get(),
                    "age": w["age"].get(), "identity": w["identity"].get().strip(),
                    "address": w["address"].get().strip(),
                    "description": w["desc"].get("1.0", "end").strip()}
        return {"world_desc": self.world_box.get("1.0", "end").strip(),
                "prior_history": self.prior_entry.get().strip(),
                "char_a": char("a"), "char_b": char("b"),
                "narrator_gender": self.narr_gender.get(),
                "narrator_accent": self.narr_accent.get(),
                "theme": self.theme_menu.get(),
                "turns": self.turns_menu.get(), "rounds": self.rounds_menu.get()}

    def _apply_story(self, story: dict):
        s = stories.normalize(story)
        self._set_textbox(self.world_box, s["world_desc"])
        self._set_entry(self.prior_entry, s["prior_history"])
        for slot in ("a", "b"):
            c, w = s[f"char_{slot}"], self.char_widgets[slot]
            self._set_entry(w["name"], c["name"])
            w["gender"].set(c["gender"])
            w["age"].set(c["age"])
            self._set_entry(w["identity"], c["identity"])
            self._set_entry(w["address"], c["address"])
            self._set_textbox(w["desc"], c["description"])
        self.narr_gender.set(s["narrator_gender"])
        self.narr_accent.set(s["narrator_accent"])
        self.theme_menu.set(s["theme"])
        self.turns_menu.set(s["turns"])
        self.rounds_menu.set(s["rounds"])

    def _story_load(self):
        title = self._story_titles.get(self.story_menu.get())
        story = stories.get_story(title) if title else None
        self._ui_log(f"CLICK story load {title!r} -> {'ok' if story else 'not found'}")
        if story is None:
            self.story_status.configure(text="pick a story in the list first")
            return
        self._apply_story(story)
        self.story_status.configure(
            text=f"loaded {'★ ' if stories.is_builtin(title) else ''}{title}")

    def _story_save(self):
        current = self._story_titles.get(self.story_menu.get(), "")
        a = self.char_widgets["a"]["name"].get().strip() or "A"
        b = self.char_widgets["b"]["name"].get().strip() or "B"
        suggestion = (current if current and not stories.is_builtin(current)
                      else f"{a} & {b}")
        dialog = ctk.CTkInputDialog(text="Name this story:", title="Save story")
        # CTkInputDialog has no default-text option; its entry exists ~10 ms
        # after construction, so pre-fill it once it does.
        dialog.after(150, lambda: (dialog._entry.insert(0, suggestion),
                                   dialog._entry.select_range(0, "end"))
                     if hasattr(dialog, "_entry") else None)
        name = dialog.get_input()
        if not name or not name.strip():
            self._ui_log("CLICK story save -> cancelled")
            return
        name = name.strip()
        exists = any(r["title"].lower() == name.lower() and not r["builtin"]
                     for r in stories.list_stories())
        if exists and not tk.messagebox.askyesno(
                "Save story", f"“{name}” already exists. Replace it?", parent=self):
            self._ui_log(f"CLICK story save {name!r} -> not replaced")
            return
        used, path = stories.save_story(self._collect_story(), name)
        self._refresh_story_menu(select=used)
        note = "  (built-in names are kept; saved as your version)" if used != name else ""
        self.story_status.configure(text=f"saved “{used}” → stories/{os.path.basename(path)}{note}")
        self._ui_log(f"CLICK story save {name!r} -> {used!r} {path}")

    def _story_delete(self):
        title = self._story_titles.get(self.story_menu.get())
        if not title:
            return
        if stories.is_builtin(title):
            self.story_status.configure(text="the built-in stories cannot be deleted")
            self._ui_log(f"CLICK story delete {title!r} -> refused (built in)")
            return
        if not tk.messagebox.askyesno("Delete story", f"Delete “{title}”?", parent=self):
            return
        ok = stories.delete_story(title)
        self._ui_log(f"CLICK story delete {title!r} -> {'deleted' if ok else 'not found'}")
        self._refresh_story_menu(select=stories.BUILTIN_STORIES[0]["title"])
        self.story_status.configure(text=f"deleted “{title}”" if ok else "not found")

    # =========================================================================
    #  v12.2 - GAMES  (seed, save, load - story_lab_saves12 holds the files)
    #
    #  Saved BETWEEN ROUNDS only; a save points at the game's run folder;
    #  loading lays the saved rounds out as text (nothing is read aloud) and
    #  puts the pictures back from the folder, then waits for the next event.
    # =========================================================================

    def _seed_from_entry(self):
        text = (self.seed_entry.get() or "").strip() if hasattr(self, "seed_entry") else ""
        return int(text) if text.isdigit() else None

    def _roll_seed(self):
        import random
        self._set_entry(self.seed_entry, str(random.randint(1, 999_999_999)))
        self._ui_log(f"CLICK roll seed -> {self.seed_entry.get()}")

    def _current_story_title(self) -> str:
        title = self._story_titles.get(self.story_menu.get(), "") if hasattr(
            self, "story_menu") else ""
        loaded = (self.story_status.cget("text") if hasattr(self, "story_status") else "")
        if title and title in loaded:
            return title
        a = self.char_widgets["a"]["name"].get().strip() or "A"
        b = self.char_widgets["b"]["name"].get().strip() or "B"
        return f"{a} & {b}"

    # v12.3: menu label -> config value; v12.4: + Medium, as large buttons
    _SCENE_STYLES = {"Classical  ·  safe": "classical",
                     "Medium  ·  manageable": "medium",
                     "Cinematic  ·  advanced": "cinematic"}
    _SCENE_STYLE_HINTS = {
        "classical": "CLASSICAL — the place itself, painted from the story with nobody in it "
                     "(NovaFurry). The portraits beside it show the characters. Fastest.",
        "medium":    "MEDIUM — both characters in the scene, drawn by NovaFurry (the Classical "
                     "model) in what the story has them wearing now. Quick, and a little "
                     "unruly: now and then a detail lands on the wrong person, or a third "
                     "one wanders in.",
        "cinematic": "CINEMATIC — both characters in the scene, drawn by Anima: the two kept "
                     "apart and detailed, in their current clothes. Slower (~30-40 s a scene).",
    }

    def _scene_style_changed(self, value, log=True):
        key = self._SCENE_STYLES.get(value)
        try:
            self.scene_style_hint.configure(
                text=self._SCENE_STYLE_HINTS.get(key, "pictures are not installed"))
        except Exception:
            pass
        if log:
            self._ui_log(f"MENU scene style = {value}")

    # v12.4: menu label -> music_style ("auto" or a music12.PALETTES key)
    _MUSIC_STYLES = {"Auto — from the story": "auto",
                     **{pal["label"]: key for key, pal in music.PALETTES.items()}}

    def _music_switches(self) -> dict:
        try:
            return {"music_enabled": bool(self.sw_music.get()),
                    "music_style": self._MUSIC_STYLES.get(self.music_style_menu.get(), "auto"),
                    "music_codes": not bool(self.sw_music_fast.get())}
        except Exception:
            return {"music_enabled": False}

    def _scene_style(self) -> str:
        try:
            return self._SCENE_STYLES.get(self.scene_style_menu.get(), "classical")
        except Exception:
            return "classical"

    def _switches_from_setup(self) -> dict:
        return {"voice_enabled": bool(self.sw_voice.get()),
                "beats_to_narrator": bool(self.sw_beats.get()),
                "show_staging": bool(self.sw_staging.get()),
                "images_enabled": bool(self.sw_images.get()),
                "auto_launch_comfyui": bool(self.sw_launch.get()),
                "portrait_refresh": bool(self.sw_refresh.get()),
                "scene_style": self._scene_style(),
                **self._music_switches()}

    def _setup_alive(self) -> bool:
        try:
            return bool(self.setup_root.winfo_exists())
        except Exception:
            return False

    @staticmethod
    def _describe_game(story, rnd, saved_at, seed) -> str:
        when = saved_at.replace("T", " ")[:16] if saved_at else ""
        return f"{story or 'game'}  ·  after round {rnd}  ·  {when}  ·  seed {seed}"

    def _refresh_game_status(self):
        last = saves.recent_games(limit=1)
        if last:
            g = last[0]
            self.game_status.configure(text="last game: " + self._describe_game(
                g["story_title"], g["round"], g["saved_at"], g["seed"]))
            self.continue_btn.configure(state="normal")
        else:
            self.game_status.configure(text="no saved games yet - every game saves "
                                            "itself after each round")
            self.continue_btn.configure(state="disabled")

    def _continue_last_game(self):
        last = saves.recent_games(limit=1)
        self._ui_log(f"CLICK continue last game -> {last[0]['run_dir'] if last else None}")
        if last:
            snap = saves.read_checkpoint(last[0]["run_dir"], last[0]["round"])
            if snap:
                self._start_resume(last[0]["run_dir"], snap)

    def _open_load_dialog(self):
        """Named saves first, then the recent games' autosaves."""
        self._ui_log("CLICK load game")
        dlg = ctk.CTkToplevel(self)
        dlg.title("Load a game")
        dlg.geometry("780x560")
        dlg.transient(self)
        dlg.after(50, dlg.lift)
        page = ctk.CTkScrollableFrame(dlg, fg_color=_L["bg"])
        page.pack(fill="both", expand=True)
        self._load_thumbs = []

        def row(r, named):
            card = ctk.CTkFrame(page, fg_color=_L["card"], corner_radius=8,
                                border_color=_L["border"], border_width=1)
            card.pack(fill="x", padx=10, pady=4)
            if r.get("thumbnail") and Image is not None:
                try:
                    pil = Image.open(r["thumbnail"]).convert("RGB")
                    pil.thumbnail((240, 160))
                    cimg = ctk.CTkImage(light_image=pil, dark_image=pil, size=(120, 80))
                    self._load_thumbs.append(cimg)
                    ctk.CTkLabel(card, image=cimg, text="").pack(side="left", padx=8, pady=6)
                except Exception:
                    pass
            text = ctk.CTkFrame(card, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, padx=6)
            title = r["name"] if named else os.path.basename(r["run_dir"])
            ctk.CTkLabel(text, text=title, text_color=_L["text"], anchor="w",
                         font=("Segoe UI", 13, "bold")).pack(fill="x")
            ctk.CTkLabel(text, text=self._describe_game(
                r.get("story_title"), r["round"], r.get("saved_at"),
                r.get("game_seed", r.get("seed"))), text_color=_L["muted"], anchor="w",
                font=("Segoe UI", 11)).pack(fill="x")
            ok = r.get("ok", True)
            if named:
                ctk.CTkButton(card, text="DELETE", width=70, fg_color=_L["accent_dim"],
                              hover_color=_L["accent"],
                              command=lambda: self._delete_save(r["name"], dlg)).pack(
                                  side="right", padx=6)
            ctk.CTkButton(card, text="LOAD" if ok else "missing", width=70,
                          state="normal" if ok else "disabled",
                          fg_color=_L["accent"], hover_color=_L["accent_dim"],
                          command=lambda: self._load_from_dialog(r, dlg)).pack(
                              side="right", padx=6)

        named = saves.list_saves()
        ctk.CTkLabel(page, text="SAVED GAMES", text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        if not named:
            ctk.CTkLabel(page, text="none yet - SAVE GAME in a game makes one",
                         text_color=_L["muted"]).pack(anchor="w", padx=12)
        for r in named:
            row(r, True)
        ctk.CTkLabel(page, text="RECENT GAMES  (saved by themselves after every round)",
                     text_color=_L["accent"],
                     font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(14, 2))
        for r in saves.recent_games(limit=8):
            row(r, False)

    def _load_from_dialog(self, r, dlg):
        snap = saves.read_checkpoint(r["run_dir"], r["round"])
        self._ui_log(f"LOAD {r.get('name', r['run_dir'])} round {r['round']} -> "
                     f"{'ok' if snap else 'unreadable'}")
        try:
            dlg.destroy()
        except Exception:
            pass
        if snap:
            self._start_resume(r["run_dir"], snap)

    def _delete_save(self, name, dlg):
        if tk.messagebox.askyesno("Delete save", f"Delete the save “{name}”?\n"
                                                 "(the game's own folder is kept)", parent=dlg):
            saves.delete_save(name)
            self._ui_log(f"DELETED save {name!r}")
            dlg.destroy()
            self._open_load_dialog()

    def _start_resume(self, run_dir, snap):
        """End whatever is on screen, then continue `snap` from its gate."""
        global ACTIVE_THEME
        switches = (self._switches_from_setup() if self._setup_alive()
                    else getattr(self, "_last_switches", None)) or {}
        if self._setup_alive():
            style = self.reveal_menu.get()
            self.reveal_style = ("typewriter" if style.startswith("Type")
                                 else "calm" if style.startswith("Calm") else "karaoke")
            self.word_sync = bool(self.sw_words.get())
            self.caption_on = bool(self.sw_caption.get())
        if self.director:
            self.director.stop()
            self.director = None
        cfg = dict(snap.get("config", {}))
        cfg.update(switches)
        cfg["image_prompts"] = images.load_prompt_settings()
        self._last_switches = switches
        ACTIVE_THEME = cfg.get("theme") if cfg.get("theme") in THEMES else ACTIVE_THEME
        try:
            _api = images.load_workflow(images.WORKFLOW_SCENE_FILE)
            ckpt = next((n["inputs"]["ckpt_name"] for n in _api.values()
                         if "ckpt_name" in n["inputs"]), None)
        except Exception:
            ckpt = None
        warnings = saves.compatibility(snap, engine.ENGINE_VERSION, engine.MODEL, ckpt)
        if self._setup_alive():
            self.setup_root.destroy()
        try:
            self.story_frame.destroy()
        except Exception:
            pass
        self._items, self._ranges, self._pending_nl = {}, {}, set()
        self._follow = True
        self._armed_round = None           # the previous game's arm must not carry over
        self._reset_image_state()
        self._images_on = bool(cfg.get("images_enabled"))
        self._music_on = bool(cfg.get("music_enabled"))
        self._stop_music()
        self._build_story_screen()
        for slot in ("a", "b"):
            self.cast_names[slot].configure(text=snap["characters"][slot]["name"])
        self._ui_log(f"RESUME {run_dir} after round {snap['round_done']} "
                     f"seed {snap.get('game_seed')}")
        for w in warnings:
            self._drawer_append("LOAD NOTE: " + w)
        self.director = Director(self, self._updaters(), cfg,
                                 resume={"run_dir": run_dir, "snapshot": snap})
        self.director.start()

    def _save_game_clicked(self):
        d = self.director
        if d is None or d.round_done < 1:
            self._u_status("nothing to save yet — games are saved between rounds")
            return
        story = d.cfg.get("story_title") or "Game"
        dialog = ctk.CTkInputDialog(text="Name this save:", title="Save game")
        suggestion = f"{story} · round {d.round_done}"
        dialog.after(150, lambda: (dialog._entry.insert(0, suggestion),
                                   dialog._entry.select_range(0, "end"))
                     if hasattr(dialog, "_entry") else None)
        name = dialog.get_input()
        if not name or not name.strip():
            self._ui_log("CLICK save game -> cancelled")
            return
        name = name.strip()
        if any(r["name"].lower() == name.lower() for r in saves.list_saves()) and \
                not tk.messagebox.askyesno("Save game", f"“{name}” exists. Replace it?",
                                           parent=self):
            return
        res = d.save_game(name)
        if res:
            path, rnd = res
            self._u_status(f"saved “{name}” — the end of round {rnd}")
            self._ui_log(f"SAVED game {name!r} round {rnd} -> {path}")

    def _load_game_clicked(self):
        self._ui_log("CLICK load game (in game)")
        self._open_load_dialog()

    def _u_game_seed(self, seed):
        self.seed_label.configure(text=f"SEED {seed}")
        self._drawer_append(f"GAME SEED {seed}")

    def _u_checkpoint(self, round_num):
        self._ui_log(f"autosaved after round {round_num}")

    def _u_resumed(self, snap, run_dir, branch):
        """Lay a saved game out: every finished round as text, the pictures
        back from the folder. Nothing is voiced and nothing waits."""
        f = self.feed
        f.configure(state="normal")

        def put(text, tag, voice_key="", italic_beats=True):
            for ch in tts.split_utterance(text or "", voice_key=voice_key,
                                          beats_voice_key=None):
                if ch.para_break:
                    f.insert("end", "\n")
                tags = (tag, "beat") if italic_beats and ch.mode == "narration" else (tag,)
                f.insert("end", ch.text + " ", tags)
            f.insert("end", "\n\n")

        put(snap.get("setting", ""), "narr", "narrator")
        show_staging = self.director.cfg.get("show_staging", True) if self.director else True
        for rec in snap.get("rounds", []):
            f.insert("end", f"──  round {rec['round']:02d}  ────────\n", "sys")
            put(rec.get("opener", ""), "narr", "narrator")
            for ln in rec.get("lines", []):
                f.insert("end", f"{ln['name']}:  ", "a_name" if ln["key"] == "a" else "b_name")
                put(ln["text"], "a_body" if ln["key"] == "a" else "b_body", ln["key"])
            put(rec.get("resolution", ""), "res", "narrator")
            ev = rec.get("event")
            if ev:
                f.insert("end", "⚡ YOU:  ", "event")
                put(ev["injection"], "event", italic_beats=False)
                if show_staging:
                    if f.get("end-3c", "end-1c") == "\n\n":
                        f.delete("end-2c")
                    f.insert("end", "   ↳ kept your words — no rewrite passed the guards:  "
                             if ev.get("kept_raw") else "   ↳ staged as:  ", "staged_head")
                    put(ev["staged"], "staged", italic_beats=False)
        n = int(snap["round_done"])
        f.insert("end", f"──  saved game  ·  continues after round {n:02d}  ·  "
                        f"seed {snap.get('game_seed')}  ──\n\n", "sys")
        f.configure(state="disabled")
        f.see("end")
        self.round_label.configure(text=f"ROUND {n:02d}")

        for r_str, s in sorted(snap.get("scenes", {}).items(), key=lambda kv: int(kv[0])):
            r = int(r_str)
            for t in sorted(s.get("takes", []), key=lambda t: t.get("take", 0)):
                path = os.path.join(run_dir, t["file"])
                if os.path.isfile(path):
                    self._scenes.setdefault(r, []).append((path, s.get("body", "")))
                    self._add_thumb(r, path)
            self._scene_prompts[r] = s.get("body", "")
        self._presented_round = n
        self._refresh_scene(fade=False)
        for r_str, m in (snap.get("music") or {}).get("tracks", {}).items():   # v12.4
            for t in sorted(m.get("takes", []), key=lambda t: t.get("take", 0)):
                path = os.path.join(run_dir, t["file"])
                if os.path.isfile(path):
                    self._music.setdefault(int(r_str), []).append((path, m.get("body", "")))
        self._refresh_music()
        latest = {}
        for p in snap.get("portraits", []):
            latest[p["slot"]] = p
        for slot, p in latest.items():
            path = os.path.join(run_dir, p["file"])
            if os.path.isfile(path):
                self._show_image(slot, path, fade=False)
        self._u_status(f"loaded — type the event for round {n + 1}, or CONTINUE")
        if branch:
            self._drawer_append(f"LOAD NOTE: the rounds played after round {n} were "
                                f"moved to {branch}")

    def _probe_comfy(self):
        """Setup-screen probe: is a server up, and can one be started?"""
        styles = images.available_styles()
        if not any(styles.values()):
            text = ("Pictures are not installed - run “Story Lab Setup” from the "
                    "Start menu to add Classical and/or Cinematic pictures")
            try:
                self.after(0, lambda: self.comfy_label.winfo_exists()
                           and self.comfy_label.configure(text=text))
            except Exception:
                pass
            return
        port = images.find_comfyui_port()
        if port:
            text = f"ComfyUI: running on 127.0.0.1:{port} - pictures will use it"
            # v12.3: can this server draw Cinematic scenes?
            missing = images.missing_models(f"http://127.0.0.1:{port}",
                                            images.WORKFLOW_CINEMATIC_FILE)
            text += (" · Cinematic scenes: ready" if not missing else
                     " · Cinematic scenes NOT available here (" + "; ".join(missing[:2])
                     + ") - they would fall back to Classical")
        elif (images._configured_install() or images._desktop_install()
              or images._portable_install()):
            text = ("ComfyUI: not running - BEGIN starts it headless "
                    "(first picture ~30 s in)")
        else:
            text = "ComfyUI: not found - the story will run without pictures"
        try:
            self.after(0, lambda: self.comfy_label.winfo_exists()
                       and self.comfy_label.configure(text=text))
        except Exception:
            pass

    # ---- voice audition (setup screen) --------------------------------------

    def _audition(self, slot: str):
        if not tts.tts_available():
            self.setup_status.configure(text=f"voice unavailable: {tts.tts_status()}")
            return
        if slot == "narrator":
            label = "narrator"
            args = ("narrator", self.narr_gender.get().lower(),
                    "posh" if "Posh" in self.narr_accent.get() else "rough")
        else:
            w = self.char_widgets[slot]
            label = w["name"].get().strip() or slot.upper()
            args = ("char", label, w["gender"].get(), w["age"].get())

        def work():
            if not self._preview_lock.acquire(blocking=False):
                return
            try:
                if args[0] == "narrator":
                    resolved = tts.resolve_narrator_preview(args[1], args[2])
                else:
                    resolved = tts.resolve_preview(args[1], args[2], args[3])
                if resolved is None:
                    self.after(0, lambda: self.setup_status.configure(
                        text=f"voice unavailable: {tts.tts_status()}"))
                    return
                desc = resolved.describe()
                self.after(0, lambda: self.setup_status.configure(text=desc))
                tts.speak_now(_AUDITION.get(slot, _AUDITION["a"]), resolved)
            except Exception as e:
                msg = f"audition failed: {e}"
                self.after(0, lambda: self.setup_status.configure(text=msg))
            finally:
                self._preview_lock.release()

        self._ui_log(f"CLICK hear-voice [{slot}] {label}")
        self.setup_status.configure(text=f"building {label}'s voice "
                                         f"(first time takes a moment)...")
        threading.Thread(target=work, daemon=True).start()

    # =========================================================================
    #  SESSION START
    # =========================================================================

    def _begin_session(self):
        global ACTIVE_THEME
        ACTIVE_THEME = "fantasy" if self.theme_menu.get() == "Fantasy" else "scifi"

        style = self.reveal_menu.get()
        self.reveal_style = ("typewriter" if style.startswith("Type")
                             else "calm" if style.startswith("Calm") else "karaoke")
        self.word_sync = bool(self.sw_words.get())
        self.caption_on = bool(self.sw_caption.get())

        def grab(slot):
            w = self.char_widgets[slot]
            return {"name":        w["name"].get().strip() or ("Ava" if slot == "a" else "Ben"),
                    "gender":      w["gender"].get(),
                    "age":         w["age"].get(),
                    "identity":    w["identity"].get().strip(),
                    "address":     w["address"].get().strip(),
                    "description": w["desc"].get("1.0", "end").strip()}

        rounds_choice = self.rounds_menu.get()
        config = {
            "world_desc":       self.world_box.get("1.0", "end").strip() or _DEMO_WORLD,
            "prior_history":    self.prior_entry.get().strip(),
            "char_a_inputs":    grab("a"),
            "char_b_inputs":    grab("b"),
            "narrator_gender":  self.narr_gender.get().lower(),
            "narrator_accent":  "posh" if "Posh" in self.narr_accent.get() else "rough",
            "voice_enabled":    bool(self.sw_voice.get()),
            "beats_to_narrator": bool(self.sw_beats.get()),
            "turns_per_round":  int(self.turns_menu.get()),
            "rounds":           0 if rounds_choice == "endless" else int(rounds_choice),
            "show_staging":     bool(self.sw_staging.get()),
            "images_enabled":   bool(self.sw_images.get()),
            "auto_launch_comfyui": bool(self.sw_launch.get()),
            "portrait_refresh": bool(self.sw_refresh.get()),
            "scene_style":      self._scene_style(),                # v12.3
            **self._music_switches(),                               # v12.4
            "image_prompts":    images.load_prompt_settings(),     # v12.1
            # v12.2: the game seed (typed, or None = the director draws one),
            # and what a save game shows and restores
            "game_seed":        self._seed_from_entry(),
            "story_title":      self._current_story_title(),
            "theme":            ACTIVE_THEME,
        }
        self._last_switches = self._switches_from_setup()

        self._ui_log("CLICK begin | " + " ".join(
            f"{k}={config[k]!r}" for k in ("narrator_gender", "narrator_accent",
                                           "voice_enabled", "beats_to_narrator",
                                           "turns_per_round", "rounds",
                                           "show_staging", "images_enabled",
                                           "auto_launch_comfyui", "portrait_refresh",
                                           "scene_style", "music_enabled", "music_style",
                                           "music_codes")))
        self._ui_log(f"  reveal={self.reveal_style} theme={ACTIVE_THEME} "
                     f"word_sync={self.word_sync} caption={self.caption_on}")
        self._ui_log(f"  world={config['world_desc']!r}")
        for slot in ("a", "b"):
            c = config[f"char_{slot}_inputs"]
            self._ui_log(f"  char {slot}: {c['name']} / {c['gender']} / {c['age']}")

        self._images_on = config["images_enabled"]
        self._music_on = config["music_enabled"]
        self._armed_round = None
        self.setup_root.destroy()
        self._build_story_screen()
        for slot in ("a", "b"):
            self.cast_names[slot].configure(text=config[f"char_{slot}_inputs"]["name"])

        self.director = Director(self, self._updaters(), config)
        self.director.start()

    def _updaters(self) -> dict:
        return {
            "status":            self._u_status,
            "lane":              self._u_lane,
            "character_ready":   self._u_character_ready,
            "session_ready":     self._u_session_ready,
            "voices":            self._u_voices,
            "item":              self._u_item,
            "speak_start":       self._u_speak_start,
            "speak_end":         self._u_speak_end,
            "item_done":         self._u_item_done,
            "memories":          self._u_memories,
            "staged":            self._u_staged,
            "timing":            self._u_timing,
            "await_injection":   self._u_await_injection,
            "injection_accepted": self._u_injection_accepted,
            "images_ready":      self._u_images_ready,
            "images_off":        self._u_images_off,
            "portrait":          self._u_portrait,
            "scene_image":       self._u_scene_image,
            "scene_prompt":      self._u_scene_prompt,
            "music_prompt":      self._u_music_prompt,      # v12.4
            "music":             self._u_music,             # v12.4
            "music_off":         self._u_music_off,         # v12.4
            "game_seed":         self._u_game_seed,         # v12.2
            "checkpoint":        self._u_checkpoint,        # v12.2
            "resumed":           self._u_resumed,           # v12.2
            "error":             self._u_error,
            "done":              self._u_done,
        }

    # =========================================================================
    #  SCREEN 2 - STORY
    # =========================================================================

    def _build_story_screen(self):
        ctk.set_appearance_mode(T("appearance"))
        self.story_frame = ctk.CTkFrame(self, fg_color=T("bg_deep"), corner_radius=0)
        self.story_frame.pack(fill="both", expand=True)
        sf = self.story_frame
        sf.grid_rowconfigure(1, weight=1)
        sf.grid_columnconfigure(0, weight=4)     # feed
        sf.grid_columnconfigure(1, weight=0)     # portraits
        sf.grid_columnconfigure(2, weight=5)     # scene - the large image
        fam = T("font_family")

        # ---- title bar ---------------------------------------------------------
        bar = ctk.CTkFrame(sf, fg_color=T("bg_ribbon"), corner_radius=0, height=46)
        bar.grid(row=0, column=0, columnspan=3, sticky="ew")
        ctk.CTkLabel(bar, text=T("title_text"), text_color=T("primary"),
                     font=(fam, 16, "bold")).pack(side="left", padx=14, pady=8)
        self.round_label = ctk.CTkLabel(bar, text="ROUND —",
                                        text_color=T("status_ok"), font=(fam, 14, "bold"))
        self.round_label.pack(side="left", padx=18)
        self.status_label = ctk.CTkLabel(bar, text="starting...",
                                         text_color=T("text_muted"), font=(fam, 12))
        self.status_label.pack(side="left", padx=18)
        self.end_btn = ctk.CTkButton(bar, text="END SESSION", width=120,
                                     fg_color=T("bg_widget"), hover_color=T("primary_dim"),
                                     text_color=T("primary"), border_color=T("primary_dim"),
                                     border_width=1, font=(fam, 12, "bold"),
                                     command=self._end_or_new)
        self.end_btn.pack(side="right", padx=12, pady=6)
        # v12.2: save between rounds / load another game; the seed is shown
        for text, cmd in (("LOAD GAME", self._load_game_clicked),
                          ("SAVE GAME", self._save_game_clicked)):
            ctk.CTkButton(bar, text=text, width=100, fg_color=T("bg_widget"),
                          hover_color=T("primary_dim"), text_color=T("primary"),
                          border_color=T("primary_dim"), border_width=1,
                          font=(fam, 11, "bold"), command=cmd).pack(side="right", padx=4, pady=6)
        self.seed_label = ctk.CTkLabel(bar, text="SEED —", text_color=T("text_muted"),
                                       font=(fam, 11))
        self.seed_label.pack(side="right", padx=10)
        self.voice_sw = ctk.CTkSwitch(bar, text="VOICE", font=(fam, 11, "bold"),
                                      progress_color=T("primary_dim"),
                                      command=self._voice_toggled)
        self.voice_sw.pack(side="right", padx=14); self.voice_sw.select()
        self.reveal_seg = ctk.CTkSegmentedButton(
            bar, values=["KARAOKE", "TYPE", "CALM"], width=210, height=26,
            font=(fam, 10, "bold"), command=self._reveal_changed)
        self.reveal_seg.set({"karaoke": "KARAOKE", "typewriter": "TYPE",
                             "calm": "CALM"}[self.reveal_style])
        self.reveal_seg.pack(side="right", padx=8)

        # ---- feed ---------------------------------------------------------------
        feed_card = ctk.CTkFrame(sf, fg_color=T("bg_card"), corner_radius=T("corner"),
                                 border_color=T("primary_dim"), border_width=T("border_w"))
        feed_card.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=8)
        head = ctk.CTkFrame(feed_card, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(head, text=T("log_header"), text_color=T("primary"),
                     font=(fam, 13, "bold")).pack(side="left")
        self.live_btn = ctk.CTkButton(head, text="▾ LIVE", width=70, height=24,
                                      fg_color=T("bg_widget"), hover_color=T("primary_dim"),
                                      text_color=T("primary"), font=(fam, 11),
                                      command=self._resume_follow)
        self.live_btn.pack(side="right")
        self.live_btn.configure(state="disabled")

        feed_wrap = ctk.CTkFrame(feed_card, fg_color="transparent")
        feed_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.feed = tk.Text(feed_wrap, bg=T("bg_widget"), fg=T("text_log"),
                            insertbackground=T("text_log"), wrap="word",
                            relief="flat", font=(fam, 14), state="disabled",
                            padx=14, pady=10, spacing1=2, spacing3=8)
        scroll = ctk.CTkScrollbar(feed_wrap, command=self._on_scrollbar)
        self.feed.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.feed.pack(side="left", fill="both", expand=True)
        self.feed.bind("<MouseWheel>", self._on_user_scroll)
        self.feed.bind("<Button-4>", self._on_user_scroll)
        self.feed.bind("<Button-5>", self._on_user_scroll)
        self._config_feed_tags()

        # ---- portraits + narrator (v11's cast cards, now with faces) -------------
        col = ctk.CTkFrame(sf, fg_color="transparent")
        col.grid(row=1, column=1, sticky="ns", padx=5, pady=8)
        self.cast_cards, self.cast_names, self.cast_subs, self.cast_dots = {}, {}, {}, {}
        self.portrait_labels = {}
        self._portrait_box = (196, 245)                     # logical px, 4:5
        for key, title_key, accent in (("a", "char_a_label", "char_a_accent"),
                                       ("b", "char_b_label", "char_b_accent")):
            card = ctk.CTkFrame(col, fg_color=T("bg_card"), corner_radius=T("corner"),
                                border_color=T("bg_card"), border_width=2)
            card.pack(fill="x", pady=(0, 8))
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(6, 2))
            ctk.CTkLabel(top, text=T(title_key), text_color=T("text_muted"),
                         font=(fam, 10, "bold")).pack(side="left")
            ctk.CTkButton(top, text="↻", width=24, height=20, font=(fam, 12),
                          fg_color=T("bg_widget"), hover_color=T("primary_dim"),
                          text_color=T("primary"),
                          command=lambda s=key: self._reroll_portrait(s)).pack(side="right")
            dot = ctk.CTkLabel(top, text=" ", text_color=T(accent), font=(fam, 14, "bold"))
            dot.pack(side="right", padx=4)
            img = ctk.CTkLabel(card, text=T("placeholder"), width=self._portrait_box[0],
                               height=self._portrait_box[1], fg_color=T("bg_widget"),
                               text_color=T("text_muted"), font=(fam, 11),
                               corner_radius=6)
            img.pack(padx=10, pady=(0, 4))
            name = ctk.CTkLabel(card, text="—", text_color=T(accent),
                                font=(fam, 14, "bold"), anchor="w")
            name.pack(fill="x", padx=10)
            sub = ctk.CTkLabel(card, text="", text_color=T("text_muted"),
                               font=(fam, 10), anchor="w", justify="left",
                               wraplength=self._portrait_box[0])
            sub.pack(fill="x", padx=10, pady=(0, 8))
            self.cast_cards[key], self.cast_names[key] = card, name
            self.cast_subs[key], self.cast_dots[key] = sub, dot
            self.portrait_labels[key] = img
            self._img[key] = {"label": img, "pil": None, "ctk": None, "jobs": [],
                              "box": lambda: self._portrait_box}
        ncard = ctk.CTkFrame(col, fg_color=T("bg_card"), corner_radius=T("corner"),
                             border_color=T("bg_card"), border_width=2)
        ncard.pack(fill="x")
        ntop = ctk.CTkFrame(ncard, fg_color="transparent")
        ntop.pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkLabel(ntop, text="NARRATOR", text_color=T("text_muted"),
                     font=(fam, 10, "bold")).pack(side="left")
        ndot = ctk.CTkLabel(ntop, text=" ", text_color=T("text_narr"),
                            font=(fam, 14, "bold"))
        ndot.pack(side="right")
        nsub = ctk.CTkLabel(ncard, text="", text_color=T("text_muted"), font=(fam, 10),
                            anchor="w", justify="left", wraplength=self._portrait_box[0])
        nsub.pack(fill="x", padx=10, pady=(0, 8))
        self.cast_cards["narrator"], self.cast_dots["narrator"] = ncard, ndot
        self.cast_subs["narrator"] = nsub
        self.cast_names["narrator"] = ctk.CTkLabel(ncard, text="Narrator")   # unpacked:
        # kept so v11's voice-summary matcher finds the narrator by name
        if self._music_on:
            self._build_music_card(col, fam)
        self.portrait_col = col
        self._pcol_job = None
        col.bind("<Configure>", self._on_portrait_col_resize)

        # ---- scene ---------------------------------------------------------------
        scene = ctk.CTkFrame(sf, fg_color=T("bg_card"), corner_radius=T("corner"),
                             border_color=T("primary_dim"), border_width=T("border_w"))
        scene.grid(row=1, column=2, sticky="nsew", padx=(5, 10), pady=8)
        scene.grid_columnconfigure(0, weight=1)
        scene.grid_rowconfigure(1, weight=1)
        shead = ctk.CTkFrame(scene, fg_color="transparent")
        shead.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        self.scene_title = ctk.CTkLabel(shead, text=T("scene_header"),
                                        text_color=T("primary"), font=(fam, 13, "bold"))
        self.scene_title.pack(side="left")
        self.scene_state = ctk.CTkLabel(shead, text="", text_color=T("text_muted"),
                                        font=(fam, 11))
        self.scene_state.pack(side="left", padx=12)
        ctk.CTkButton(shead, text="↻ re-roll", width=80, height=24,
                      fg_color=T("bg_widget"), hover_color=T("primary_dim"),
                      text_color=T("primary"), font=(fam, 11),
                      command=self._reroll_scene).pack(side="right")
        self.live_scene_btn = ctk.CTkButton(shead, text="◉ live", width=60, height=24,
                                            fg_color=T("bg_widget"),
                                            hover_color=T("primary_dim"),
                                            text_color=T("primary"), font=(fam, 11),
                                            command=self._scene_follow)
        self.live_scene_btn.pack(side="right", padx=6)
        self.live_scene_btn.configure(state="disabled")

        self.scene_holder = ctk.CTkFrame(scene, fg_color=T("bg_widget"), corner_radius=8)
        self.scene_holder.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self.scene_holder.grid_propagate(False)
        self.scene_label = ctk.CTkLabel(
            self.scene_holder,
            text=T("placeholder") + ("\n\nthe first scene renders while the "
                                     "world is read to you" if self._images_on
                                     else "\n\npictures are off for this session"),
            text_color=T("text_muted"), font=(fam, 12))
        self.scene_label.place(relx=0.5, rely=0.5, anchor="center")
        self.scene_holder.bind("<Configure>", self._on_scene_resize)
        self._img["scene"] = {"label": self.scene_label, "pil": None, "ctk": None,
                              "jobs": [], "box": self._scene_box}
        self._resize_job = None

        self.scene_prompt_lbl = ctk.CTkLabel(scene, text="", text_color=T("text_muted"),
                                             font=(fam, 10), anchor="w", justify="left",
                                             wraplength=640)
        self.scene_prompt_lbl.grid(row=2, column=0, sticky="ew", padx=14)

        self.thumb_row = ctk.CTkScrollableFrame(scene, orientation="horizontal",
                                                height=THUMB_H + 26,
                                                fg_color="transparent")
        self.thumb_row.grid(row=3, column=0, sticky="ew", padx=8, pady=(2, 0))

        # One lane per row: side by side, the longer states ran into each other.
        lanes = ctk.CTkFrame(scene, fg_color="transparent")
        lanes.grid(row=4, column=0, sticky="ew", padx=12, pady=(2, 8))
        lanes.grid_columnconfigure(0, weight=1)
        self.lane_labels = {}
        for i, lane in enumerate(("story", "voice", "image", "gpu")):
            lbl = ctk.CTkLabel(lanes, text=f"{lane.upper()} · —", height=16,
                               text_color=T("text_muted"), font=(fam, 10),
                               anchor="w", justify="left")
            lbl.grid(row=i, column=0, sticky="ew")
            self.lane_labels[lane] = lbl
        obs = ctk.CTkButton(lanes, text="OBSERVE", height=24, width=90,
                            fg_color=T("bg_widget"), hover_color=T("primary_dim"),
                            text_color=T("primary"), border_color=T("primary_dim"),
                            border_width=1, font=(fam, 10, "bold"),
                            command=self._open_drawer)
        obs.grid(row=0, column=1, rowspan=4, sticky="e", padx=(8, 0))
        if not self._images_on:
            self._u_lane("image", "off (switched off on the setup screen)")

        # ---- caption bar -----------------------------------------------------------
        self.caption = ctk.CTkLabel(
            sf, text="", text_color=T("text_narr"), fg_color=T("bg_panel"),
            font=(fam, 16), anchor="w", justify="left", wraplength=1200, height=58)
        if self.caption_on:
            self.caption.grid(row=2, column=0, columnspan=3, sticky="ew",
                              padx=10, pady=(0, 4))
            self.bind("<Configure>", self._resize_caption)

        # ---- bottom bar ---------------------------------------------------------------
        bot = ctk.CTkFrame(sf, fg_color=T("bg_ribbon"), corner_radius=0)
        bot.grid(row=3, column=0, columnspan=3, sticky="ew")
        ctk.CTkLabel(bot, text=T("input_label"), text_color=T("primary"),
                     font=(fam, 12, "bold")).pack(side="left", padx=(12, 6), pady=10)
        # The event box is ALWAYS state="normal" and its placeholder is set
        # ONCE, here (see the header - a disabled CTkEntry swallowed an event).
        self.inject_entry = ctk.CTkEntry(bot, width=400, fg_color=T("bg_widget"),
                                         text_color=T("text_input"),
                                         border_color=T("primary_dim"),
                                         placeholder_text="type an event any time...",
                                         font=(fam, 12))
        self.inject_entry.pack(side="left", pady=8)
        self.inject_entry.bind("<Return>", lambda _e: self._send())
        self.send_btn = ctk.CTkButton(bot, text=T("send_label"), width=95,
                                      fg_color=T("primary_dim"), hover_color=T("primary"),
                                      font=(fam, 12, "bold"), state="disabled",
                                      command=self._send)
        self.send_btn.pack(side="left", padx=8)

        def small(text, cmd, w=78):
            return ctk.CTkButton(bot, text=text, width=w, fg_color=T("bg_widget"),
                                 hover_color=T("primary_dim"), text_color=T("primary"),
                                 border_color=T("primary_dim"), border_width=1,
                                 font=(fam, 11, "bold"), command=cmd)

        self.cont_btn = small("CONTINUE ▸", self._continue, w=110)
        self.cont_btn.pack(side="left", padx=4); self.cont_btn.configure(state="disabled")
        self.arm_label = ctk.CTkLabel(bot, text="○ not armed", text_color=T("text_muted"),
                                      font=(fam, 11), width=112, anchor="w")
        self.arm_label.pack(side="left", padx=(8, 0))
        self.pause_btn = small("PAUSE", self._toggle_pause)
        self.pause_btn.pack(side="left", padx=(10, 4))
        small("SKIP", self._skip).pack(side="left", padx=4)
        self.mode_seg = ctk.CTkSegmentedButton(bot, values=["AUTO", "MANUAL"], width=140,
                                               font=(fam, 11, "bold"),
                                               command=self._mode_changed)
        self.mode_seg.set("AUTO"); self.mode_seg.pack(side="left", padx=8)
        self.next_btn = small("NEXT ▸", self._advance)
        self.next_btn.pack(side="left", padx=4); self.next_btn.configure(state="disabled")

    def _resize_caption(self, _event=None):
        # winfo_* is PHYSICAL, wraplength is LOGICAL (CTk scales it)
        try:
            self.caption.configure(
                wraplength=max(400, int(self.winfo_width() / self._scale()) - 60))
            self.scene_prompt_lbl.configure(
                wraplength=max(200, self._scene_box()[0] - 24))
        except Exception:
            pass

    # Per-card space that is not the portrait itself (title row, name, role
    # line, padding) and the narrator card, in logical px.
    _CARD_CHROME, _NARR_CARD = 112, 62
    _MUSIC_CARD = 104                     # v12.4: the music card under the narrator

    def _on_portrait_col_resize(self, _event=None):
        if self._pcol_job:
            try:
                self.after_cancel(self._pcol_job)
            except Exception:
                pass
        self._pcol_job = self.after(120, self._fit_portrait_column)

    def _fit_portrait_column(self):
        """Size both portraits (4:5) so the whole column fits the window."""
        self._pcol_job = None
        try:
            avail = self.portrait_col.winfo_height() / self._scale()
        except Exception:
            return
        h = int((avail - 2 * self._CARD_CHROME - self._NARR_CARD - 16
                 - (self._MUSIC_CARD if self._music_on else 0)) / 2)
        h = max(110, min(260, h))
        w = int(h * 0.8)
        if (w, h) == self._portrait_box:
            return
        self._portrait_box = (w, h)
        for slot in ("a", "b"):
            self.portrait_labels[slot].configure(width=w, height=h)
            self.cast_subs[slot].configure(wraplength=w)
            st = self._img[slot]
            if st["pil"] is not None:
                self._set_label_image(st, st["pil"], self._fit(st["pil"], (w, h)))
        self.cast_subs["narrator"].configure(wraplength=w)

    # =========================================================================
    #  FEED TAGS  (v11, unchanged)
    # =========================================================================

    def _config_feed_tags(self):
        fam = T("font_family")
        f = self.feed
        f.tag_config("narr",   foreground=T("text_narr"))
        f.tag_config("res",    foreground=T("text_res"))
        f.tag_config("a_body", foreground=T("text_log"))
        f.tag_config("b_body", foreground=T("text_log"))
        f.tag_config("event",  foreground=T("text_inject"))
        f.tag_config("staged", foreground=T("text_inject"), font=(fam, 12, "italic"))
        f.tag_config("staged_head", foreground=T("text_muted"), font=(fam, 11, "bold"),
                     lmargin2=44)
        f.tag_config("sys",    foreground=T("text_muted"), font=(fam, 11))
        f.tag_config("a_name", foreground=T("char_a_accent"), font=(fam, 14, "bold"))
        f.tag_config("b_name", foreground=T("char_b_accent"), font=(fam, 14, "bold"))
        f.tag_config("n_name", foreground=T("text_narr"), font=(fam, 12, "bold"))
        f.tag_config("beat",   font=(fam, 14, "italic"))
        f.tag_config("dim",    foreground=T("dim"))
        for key, band, lit in (("narr", "band_narr", "lit_narr"),
                               ("res",  "band_narr", "text_res"),
                               ("a",    "band_a",    "lit_a"),
                               ("b",    "band_b",    "lit_b"),
                               ("event", "band_event", "text_inject"),
                               ("staged", "band_event", "text_inject")):
            f.tag_config(f"say_{key}", background=T(band), foreground=T(lit))
        f.tag_config("word", underline=True)

    # ---- scrolling -----------------------------------------------------------

    def _on_scrollbar(self, *args):
        self.feed.yview(*args)
        self._detach_follow()

    def _on_user_scroll(self, _event=None):
        self._detach_follow()

    def _detach_follow(self):
        if self._follow:
            self._follow = False
            self.live_btn.configure(state="normal")

    def _resume_follow(self):
        self._ui_log("CLICK live (re-attach auto-scroll)")
        self._follow = True
        self.live_btn.configure(state="disabled")
        self.feed.see("end")

    # =========================================================================
    #  v12 - PICTURES
    # =========================================================================

    def _scale(self) -> float:
        # NB the CTk ROOT has no _get_widget_scaling() (only its child widgets
        # do); calling it raised, and a fallback of 1.0 sized the scene in
        # physical pixels - 1.5x too big, centre-cropped by its frame.
        try:
            return ctk.ScalingTracker.get_widget_scaling(self)
        except Exception:
            return 1.0

    def _scene_box(self):
        """The scene holder's inner size in LOGICAL px (CTkImage's unit)."""
        s = self._scale()
        w = max(120, int(self.scene_holder.winfo_width() / s) - 8)
        h = max(80, int(self.scene_holder.winfo_height() / s) - 8)
        return w, h

    @staticmethod
    def _fit(pil, box):
        iw, ih = pil.size
        k = min(box[0] / iw, box[1] / ih)
        return max(1, int(iw * k)), max(1, int(ih * k))

    def _show_image(self, key: str, path: str, fade: bool = True) -> None:
        """Load a PNG into one of the three picture slots, cross-fading."""
        st = self._img.get(key)
        if st is None or Image is None or not path or not os.path.isfile(path):
            return
        try:
            new = Image.open(path).convert("RGB")
            new.load()
        except Exception as e:
            self._ui_log(f"image load failed ({key}): {e}")
            return
        for job in st["jobs"]:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        st["jobs"] = []
        old, st["pil"] = st["pil"], new
        size = self._fit(new, st["box"]())
        if old is None or not fade or FADE_STEPS <= 0:
            self._set_label_image(st, new, size)
            return
        s = self._scale()
        phys = (max(1, int(size[0] * s)), max(1, int(size[1] * s)))
        a, b = old.resize(phys), new.resize(phys)
        for i in range(1, FADE_STEPS + 1):
            frame = b if i == FADE_STEPS else Image.blend(a, b, i / FADE_STEPS)
            st["jobs"].append(self.after(i * FADE_MS,
                                         lambda fr=frame, k=st:
                                         self._set_label_image(k, fr, size)))

    def _set_label_image(self, st, pil, size):
        try:
            cimg = ctk.CTkImage(light_image=pil, dark_image=pil, size=size)
            st["ctk"] = cimg                                  # keep a reference
            st["label"].configure(image=cimg, text="")
        except Exception:
            pass

    def _on_scene_resize(self, _event=None):
        if self._resize_job:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.after(140, self._refit_scene)

    def _refit_scene(self):
        self._resize_job = None
        st = self._img.get("scene")
        if st and st["pil"] is not None:
            self._set_label_image(st, st["pil"], self._fit(st["pil"], self._scene_box()))
        self._resize_caption()

    # ---- scenes: held per round, shown when the story gets there ----------------

    def _scene_target(self):
        """(round, take) the panel should show now, or None."""
        r = self._pinned_round
        if r is None:
            ready = [k for k in self._scenes if k <= self._presented_round]
            if not ready:
                return None
            r = max(ready)
        if r not in self._scenes:
            return None
        return r, len(self._scenes[r]) - 1

    def _refresh_scene(self, fade=True):
        target = self._scene_target()
        if target and target != self._shown_scene:
            r, take = target
            path, prompt = self._scenes[r][take]
            self._shown_scene = target
            self._show_image("scene", path, fade=fade)
            # what the scene painter asked for - the story part only (v12.1:
            # the director sends the body; the wrappers are the same on every
            # image and live on the Picture prompts screen)
            asked = prompt.replace(images.IMAGE_PROMPT_APPEND, "").strip(" ,")
            self.scene_prompt_lbl.configure(
                text="asked for: " + (asked[:220] + "…" if len(asked) > 220 else asked))
            self._mark_thumbs()
        self._update_scene_header()

    def _update_scene_header(self):
        shown = self._shown_scene[0] if self._shown_scene else None
        title = T("scene_header") + (f"  ·  ROUND {shown:02d}" if shown else "")
        self.scene_title.configure(text=title)
        cur = self._presented_round
        if self._pinned_round is not None:
            state = "pinned - press live to follow the story"
        elif not self._images_on:
            state = ""
        elif cur and cur not in self._scenes:
            state = (f"rendering round {cur}..." if cur in self._scene_prompts
                     else "")
        elif any(r > cur for r in self._scenes):
            state = f"round {max(self._scenes)} ready - shows when the story gets there"
        else:
            state = ""
        self.scene_state.configure(text=state)
        self.live_scene_btn.configure(
            state="normal" if self._pinned_round is not None else "disabled")

    def _add_thumb(self, round_num, path):
        if Image is None:
            return
        try:
            pil = Image.open(path).convert("RGB")
            pil.thumbnail((THUMB_W * 2, THUMB_H * 2))
            cimg = ctk.CTkImage(light_image=pil, dark_image=pil, size=(THUMB_W, THUMB_H))
        except Exception:
            return
        fam = T("font_family")
        if round_num in self._thumbs:
            btn = self._thumbs[round_num][0]
            btn.configure(image=cimg)
        else:
            btn = ctk.CTkButton(self.thumb_row, image=cimg, text=f"r{round_num}",
                                compound="top", width=THUMB_W + 8, height=THUMB_H + 22,
                                fg_color=T("bg_widget"), hover_color=T("primary_dim"),
                                text_color=T("text_muted"), font=(fam, 10),
                                border_width=2, border_color=T("bg_widget"),
                                command=lambda r=round_num: self._pick_scene(r))
            btn.grid(row=0, column=round_num, padx=3, pady=2)
        self._thumbs[round_num] = (btn, cimg)
        self._mark_thumbs()

    def _mark_thumbs(self):
        shown = self._shown_scene[0] if self._shown_scene else None
        for r, (btn, _c) in self._thumbs.items():
            future = r > self._presented_round and self._pinned_round != r
            btn.configure(border_color=T("primary") if r == shown else T("bg_widget"),
                          state="disabled" if future else "normal")

    def _pick_scene(self, round_num):
        self._ui_log(f"CLICK scene thumb r{round_num}")
        newest = max([r for r in self._scenes if r <= self._presented_round] or [0])
        self._pinned_round = None if round_num >= newest else round_num
        self._refresh_scene()

    def _scene_follow(self):
        self._ui_log("CLICK scene live")
        self._pinned_round = None
        self._refresh_scene()

    def _reroll_scene(self):
        r = self._shown_scene[0] if self._shown_scene else None
        self._ui_log(f"CLICK re-roll scene r{r}")
        if not self.director or r is None:
            self._u_status("no scene on screen to re-roll yet")
            return
        if self.director.request_scene_reroll(r):
            self.scene_state.configure(text=f"re-roll of round {r} queued - renders "
                                            f"at the next pause in the story")
        else:
            self._u_status("pictures are not running - nothing to re-roll")

    def _reroll_portrait(self, slot):
        self._ui_log(f"CLICK re-roll portrait {slot}")
        if self.director and self.director.request_portrait_reroll(slot):
            self._u_status(f"new portrait for {self.cast_names[slot].cget('text')} "
                           f"queued")
        else:
            self._u_status("no portrait to re-roll yet")

    # ---- the image updaters -------------------------------------------------

    # =========================================================================
    #  v12.4 - MUSIC  (the card, the player, the updaters)
    # =========================================================================

    def _build_music_card(self, col, fam):
        card = ctk.CTkFrame(col, fg_color=T("bg_card"), corner_radius=T("corner"),
                            border_color=T("bg_card"), border_width=2)
        card.pack(fill="x", pady=(8, 0))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(top, text="MUSIC", text_color=T("text_muted"),
                     font=(fam, 10, "bold")).pack(side="left")

        def btn(text, cmd, w=28):
            return ctk.CTkButton(top, text=text, width=w, height=20, font=(fam, 12),
                                 fg_color=T("bg_widget"), hover_color=T("primary_dim"),
                                 text_color=T("primary"), command=cmd)
        self.music_regen_btn = btn("↻", self._regen_music, 24)
        self.music_regen_btn.pack(side="right")
        self.music_play_btn = btn("❚❚", self._toggle_music)
        self.music_play_btn.pack(side="right", padx=4)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(2, 0))
        vol = self.music_player.volume if self.music_player else music.DEFAULT_VOLUME
        self.music_vol = ctk.CTkSlider(row, from_=0, to=1, number_of_steps=40, width=120,
                                       height=14, button_color=T("primary"),
                                       progress_color=T("primary_dim"),
                                       command=self._music_volume)
        self.music_vol.set(vol)
        self.music_vol.pack(side="left", fill="x", expand=True)
        self.music_state = ctk.CTkLabel(card, text="music is made at the end of each "
                                                   "round, after the text and pictures",
                                        text_color=T("text_muted"),
                                        font=(fam, 10), anchor="w", justify="left",
                                        wraplength=self._portrait_box[0])
        self.music_state.pack(fill="x", padx=10, pady=(2, 8))

    def _ensure_player(self):
        if self.music_player is None and music.MusicPlayer.available():
            self.music_player = music.MusicPlayer()
        return self.music_player

    def _stop_music(self):
        if self.music_player is not None:
            self.music_player.stop()
        self._music_playing = None

    def _set_music_state(self, text):
        self._music_status = text
        try:
            self.music_state.configure(text=text)
        except Exception:
            pass

    def _music_target(self):
        """(round, take) that should be playing: the newest take of the newest
        round the presenter has reached - never a round still ahead."""
        ready = [r for r in self._music if r <= self._presented_round]
        if not ready:
            return None
        r = max(ready)
        return r, len(self._music[r]) - 1

    def _refresh_music(self):
        target = self._music_target()
        if target is None or target == self._music_playing:
            return
        player = self._ensure_player()
        if player is None:
            self._set_music_state("music: no audio output available")
            return
        r, take = target
        path, body = self._music[r][take]
        self._music_playing = target
        self._set_music_state(f"round {r}" + (f" · take {take + 1}" if take else "")
                              + f"\n{body}")
        self._ui_log(f"MUSIC play r{r} take {take}: {os.path.basename(path)}")
        player.load_file(path, body, r, take,
                         on_error=lambda e: self.after(0, lambda: self._set_music_state(
                             f"music: could not play ({e})")))

    def _toggle_music(self):
        if self.music_player is None:
            return
        paused = self.music_player.toggle_pause()
        self.music_play_btn.configure(text="▶" if paused else "❚❚")
        self._ui_log(f"CLICK music {'pause' if paused else 'play'}")

    def _music_volume(self, value):
        player = self._ensure_player()
        if player is not None:
            player.set_volume(float(value))

    def _regen_music(self):
        r = (self._music_playing or (None,))[0] or max(self._music_prompts or {0: None})
        ok = bool(self.director and r and self.director.request_music_reroll(r))
        self._ui_log(f"CLICK music regenerate r{r} -> {'queued' if ok else 'refused'}")
        if ok:
            self._set_music_state(f"round {r} · a new take is queued (renders "
                                  f"with the next pictures, or at once while the game "
                                  f"waits for your event)")

    def _u_music_prompt(self, round_num, body):
        self._music_prompts[round_num] = body
        if self._music_playing is None:
            self._set_music_state(f"composing round {round_num}\n{body}")

    def _u_music(self, round_num, path, body, take):
        self._music.setdefault(round_num, []).append((path, body))
        self._ui_log(f"MUSIC ready r{round_num} take {take}: {os.path.basename(path)}")
        self._refresh_music()

    def _u_music_off(self, reason):
        self._ui_log(f"MUSIC OFF {reason}")
        self._set_music_state(f"music off — {reason}")
        self._drawer_append(f"MUSIC OFF: {reason}")

    def _u_images_ready(self, summary):
        self._drawer_append("IMAGES READY\n" + summary + "\n")
        self._ui_log("images ready")

    def _u_images_off(self, reason):
        self._images_on = False
        self._drawer_append(f"IMAGES OFF: {reason}\n")
        self._ui_log(f"IMAGES OFF {reason}")
        if self._img["scene"]["pil"] is None:
            self.scene_label.configure(text=f"{T('placeholder')}\n\n{reason}",
                                       wraplength=420)
        self._update_scene_header()

    def _u_portrait(self, slot, path, prompt):
        self._ui_log(f"PORTRAIT {slot} {os.path.basename(path)}")
        self._drawer_append(f"PORTRAIT {slot}: {prompt}\n")
        self._show_image(slot, path)

    def _u_scene_prompt(self, round_num, prompt):
        self._scene_prompts[round_num] = prompt
        self._drawer_append(f"ROUND {round_num:02d} SCENE PROMPT\n  {prompt}\n")
        self._update_scene_header()

    def _u_scene_image(self, round_num, path, prompt, take):
        self._ui_log(f"SCENE r{round_num} take {take} {os.path.basename(path)}")
        self._scenes.setdefault(round_num, []).append((path, prompt))
        self._add_thumb(round_num, path)
        if take and self._shown_scene and self._shown_scene[0] == round_num:
            self._shown_scene = None                     # force the new take in
        self._refresh_scene()

    # =========================================================================
    #  DIRECTOR UPDATERS  (v11, with the cast now living on the portrait cards)
    # =========================================================================

    def _u_status(self, text):
        self.status_label.configure(text=text)
        self._ui_log(f"status: {text}")

    def _u_lane(self, lane, state):
        lbl = getattr(self, "lane_labels", {}).get(lane)
        if lbl:
            lbl.configure(text=f"{lane.upper()} · {state}")

    def _u_character_ready(self, slot, char):
        self.cast_names[slot].configure(text=char.name)
        self.cast_subs[slot].configure(text=char.role)
        self._u_status(f"{char.name} extracted — {char.role}")

    def _u_session_ready(self, char_a, char_b, setting):
        self._u_status("the story begins")
        run_dir = getattr(self.director, "run_dir", None)
        if run_dir:
            self._ui_log(f"run dir: {run_dir}")

    def _u_voices(self, summary):
        self._drawer_append("VOICES\n" + summary + "\n")
        for line in summary.splitlines():
            m = re.match(r"\[(.+?)\]\s+voice=(\S+)", line.strip())
            if not m:
                continue
            who, voice = m.group(1), m.group(2)
            for key in ("narrator", "a", "b"):
                if self.cast_names[key].cget("text") == who or (
                        key == "narrator" and who.lower() == "narrator"):
                    cur = self.cast_subs[key].cget("text")
                    self.cast_subs[key].configure(
                        text=(cur + "  ·  " if cur else "") + voice)

    # ---- the feed: lay out, then light up -----------------------------------

    def _u_item(self, item: PresentationItem):
        self._items[item.seq] = item
        self._ui_log(f"ITEM {item.seq:3} {item.kind:9} r{item.round_num} "
                     f"{item.speaker or '-':10} {len(item.chunks)} chunks")
        f = self.feed
        f.configure(state="normal")

        if item.kind == "narration" and item.phase == "opener" and item.round_num > 0:
            self.round_label.configure(text=f"ROUND {item.round_num:02d}")
            f.insert("end", f"──  round {item.round_num:02d}  "
                            f"────────\n", "sys")
            self._presented_round = item.round_num      # v12: release its scene
            self._refresh_scene()
            self._refresh_music()                        # v12.4: and its music

        if item.kind == "line":
            name_tag = "a_name" if item.voice_key == "a" else "b_name"
            f.insert("end", f"{item.speaker}:  ", name_tag)
            body_tag = "a_body" if item.voice_key == "a" else "b_body"
        elif item.kind == "event":
            f.insert("end", "⚡ YOU:  ", "event")
            body_tag = "event"
        elif item.kind == "staged":
            if f.get("end-3c", "end-1c") == "\n\n":
                f.delete("end-2c")
            f.insert("end", "   ↳ kept your words — no rewrite passed the guards:  "
                     if item.phase == "kept_raw" else "   ↳ staged as:  ",
                     "staged_head")
            body_tag = "staged"
        elif item.kind == "narration":
            body_tag = "res" if item.phase == "resolution" else "narr"
        else:
            body_tag = "sys"

        if self.reveal_style != "typewriter":
            for chunk in item.chunks:
                if chunk.para_break:
                    f.insert("end", "\n")
                start = f.index("end-1c")
                tags = ((body_tag, "beat") if chunk.mode == "narration"
                        and item.kind != "staged" else (body_tag,))
                f.insert("end", chunk.text + " ", tags)
                end = f.index("end-1c")
                self._ranges[(item.seq, chunk.idx)] = (start, end)
                if self.reveal_style == "karaoke":
                    f.tag_add("dim", start, end)
            f.insert("end", "\n\n")
        else:
            self._pending_nl.add(item.seq)

        f.configure(state="disabled")
        if self._follow:
            f.see("end")

    def _u_speak_start(self, seq, chunk_idx, seconds):
        item = self._items.get(seq)
        if item is None or chunk_idx >= len(item.chunks):
            return
        chunk = item.chunks[chunk_idx]
        # v12.4: dip the music under a sentence that is actually voiced (an
        # unvoiced chunk is paced silently - nothing to make room for)
        if self.music_player is not None and getattr(chunk, "audio", None) is not None:
            self.music_player.duck_for(seconds)
        f = self.feed

        if self.reveal_style == "typewriter":
            body_tag = ("a_body" if item.voice_key == "a"
                        else "b_body" if item.voice_key == "b"
                        else "event" if item.kind == "event"
                        else "staged" if item.kind == "staged"
                        else "res" if item.phase == "resolution" else "narr")
            f.configure(state="normal")
            if chunk.para_break:
                f.insert("end", "\n")
            start = f.index("end-1c")
            tags = ((body_tag, "beat") if chunk.mode == "narration"
                    and item.kind != "staged" else (body_tag,))
            f.insert("end", chunk.text + " ", tags)
            end = f.index("end-1c")
            f.configure(state="disabled")
            self._ranges[(seq, chunk_idx)] = (start, end)

        rng = self._ranges.get((seq, chunk_idx))
        if rng:
            start, end = rng
            f.tag_remove("dim", start, end)
            f.tag_add(self._say_tag(item), start, end)
            if self._follow:
                f.see(end)
            if self.word_sync and seconds > 0.2:
                self._start_word_walk(chunk.text, start, seconds)

        self._set_speaking(chunk.voice_key, True)
        if self.caption_on and item.kind != "staged":
            who = item.speaker or "Narrator"
            self.caption.configure(text=f"▶  {who.upper()}   {chunk.text}",
                                   text_color=T(self._accent_for(chunk.voice_key)))

    def _u_speak_end(self, seq, chunk_idx):
        self._cancel_word_walk()
        item = self._items.get(seq)
        rng = self._ranges.get((seq, chunk_idx))
        if item is not None and rng:
            self.feed.tag_remove(self._say_tag(item), rng[0], rng[1])
        if item is not None and chunk_idx < len(item.chunks):
            self._set_speaking(item.chunks[chunk_idx].voice_key, False)

    def _u_item_done(self, seq):
        item = self._items.get(seq)
        if item is None:
            return
        if seq in self._pending_nl:
            self._pending_nl.discard(seq)
            self.feed.configure(state="normal")
            self.feed.insert("end", "\n\n")
            self.feed.configure(state="disabled")
        for idx in range(len(item.chunks)):
            rng = self._ranges.get((seq, idx))
            if rng:
                self.feed.tag_remove("dim", rng[0], rng[1])
        for key in ("narrator", "a", "b"):
            self._set_speaking(key, False)
        if self._follow:
            self.feed.see("end")

    def _say_tag(self, item) -> str:
        if item.kind == "line":
            return "say_a" if item.voice_key == "a" else "say_b"
        if item.kind == "event":
            return "say_event"
        if item.kind == "staged":
            return "say_staged"
        return "say_res" if item.phase == "resolution" else "say_narr"

    def _accent_for(self, voice_key) -> str:
        return {"a": "char_a_accent", "b": "char_b_accent"}.get(voice_key, "text_narr")

    def _set_speaking(self, voice_key, on: bool):
        card = self.cast_cards.get(voice_key)
        if card is None:
            return
        accent = T(self._accent_for(voice_key))
        card.configure(border_color=accent if on else T("bg_card"))
        self.cast_dots[voice_key].configure(text="●" if on else " ")

    # ---- optional word-level walker (v11) -----------------------------------

    def _start_word_walk(self, text, start, seconds):
        self._cancel_word_walk()
        words = list(re.finditer(r"\S+", text))
        if not words:
            return
        total = sum(len(w.group()) + 1 for w in words)
        elapsed = 0.0
        for w in words:
            share = (len(w.group()) + 1) / total
            delay = int(elapsed * 1000)
            s_off, e_off = w.start(), w.end()
            job = self.after(delay, lambda so=s_off, eo=e_off:
                             self._mark_word(start, so, eo))
            self._word_jobs.append(job)
            elapsed += share * seconds

    def _mark_word(self, start, s_off, e_off):
        try:
            self.feed.tag_remove("word", "1.0", "end")
            self.feed.tag_add("word", f"{start}+{s_off}c", f"{start}+{e_off}c")
        except Exception:
            pass

    def _cancel_word_walk(self):
        for job in self._word_jobs:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._word_jobs = []
        try:
            self.feed.tag_remove("word", "1.0", "end")
        except Exception:
            pass

    # ---- remaining updaters ---------------------------------------------------

    def _u_memories(self, round_num, mem_a, mem_b):
        self._drawer_append(f"ROUND {round_num:02d} MEMORIES\nA: {mem_a}\nB: {mem_b}\n")

    def _u_staged(self, round_num, raw, staged, kept_raw, sent=""):
        verdict = ("KEPT YOUR WORDS - no rewrite passed the guards"
                   if kept_raw else "staged")
        self._drawer_append(f"ROUND {round_num:02d} EVENT ({verdict})\n"
                            f"  you typed: {raw}\n  staged as: {staged}\n"
                            f"  sent to the story: {sent or staged}\n")
        self._ui_log(f"STAGED r{round_num} kept_raw={kept_raw} len={len(staged.split())}w")

    def _u_timing(self, label, seconds):
        self._drawer_append(f"  {label}: {seconds:.1f}s")

    def _u_await_injection(self, round_num):
        self._armed_round = round_num
        self.send_btn.configure(state="normal")
        self.cont_btn.configure(state="normal")
        self.arm_label.configure(text=f"◉ armed → r{round_num + 1}",
                                 text_color=T("status_ok"))
        self._ui_log(f"ARMED for round {round_num} "
                     f"(event will shape round {round_num + 1})")

    def _u_injection_accepted(self, text):
        self._armed_round = None
        self.inject_entry.delete(0, "end")
        self.send_btn.configure(state="disabled")
        self.cont_btn.configure(state="disabled")
        self.arm_label.configure(text="○ locked in", text_color=T("text_muted"))
        self._u_status("event locked in" if text else "continuing without an event")
        self._ui_log(f"ACCEPTED {text!r}" if text else "ACCEPTED (no event)")

    def _u_error(self, message):
        self._ui_log(f"ERROR {message}")
        self.feed.configure(state="normal")
        self.feed.insert("end", f"✗ {message}\n", "sys")
        self.feed.configure(state="disabled")
        self._u_status(f"error: {message}")

    def _u_done(self):
        self._u_status("presentation finished")

    # =========================================================================
    #  CONTROLS  (v11)
    # =========================================================================

    def _read_injection(self) -> str:
        api = (self.inject_entry.get() or "").strip()
        try:
            raw = (self.inject_entry._entry.get() or "").strip()
            ph = (self.inject_entry.cget("placeholder_text") or "").strip()
        except Exception:
            return api
        if api:
            return api
        if raw and raw != ph:
            recovered = raw[len(ph):].strip() if ph and raw.startswith(ph) else raw
            if recovered:
                self._ui_log(f"ENTRY MISMATCH get()='' raw={raw!r} "
                             f"-> recovered {recovered!r}")
                return recovered
        return ""

    def _send(self):
        text = self._read_injection()
        armed = bool(self.director and self.director._injection_armed)
        self._ui_log(f"CLICK send | text={text!r} armed={armed} "
                     f"session={'yes' if self.director else 'no'}")
        if not self.director:
            self._u_status("no session running")
            return
        if not text:
            self._u_status("nothing typed — type an event, or press CONTINUE")
            self.inject_entry.focus_set()
            return
        if not self.director.submit_injection(text):
            self._u_status("not armed yet — the round is still being written")
            self._ui_log("  -> REJECTED by director (not armed)")

    def _continue(self):
        armed = bool(self.director and self.director._injection_armed)
        self._ui_log(f"CLICK continue | armed={armed}")
        if not self.director:
            return
        if not self.director.continue_without_event():
            self._u_status("not armed yet — the round is still being written")
            self._ui_log("  -> REJECTED by director (not armed)")

    def _skip(self):
        self._ui_log("CLICK skip")
        if self.director:
            self.director.skip_current()

    def _advance(self):
        self._ui_log("CLICK next")
        if self.director:
            self.director.advance()

    def _toggle_pause(self):
        self._ui_log("CLICK pause")
        if self.director:
            paused = self.director.toggle_pause()
            self.pause_btn.configure(text="RESUME" if paused else "PAUSE")

    def _mode_changed(self, value):
        self._ui_log(f"MENU mode = {value}")
        if self.director:
            self.director.set_mode(value)
        self.next_btn.configure(state="normal" if value == "MANUAL" else "disabled")

    def _voice_toggled(self):
        on = bool(self.voice_sw.get())
        self._ui_log(f"SWITCH voice = {'on' if on else 'off'}")
        if self.director:
            self.director.set_voice(on)

    def _reveal_changed(self, value):
        self.reveal_style = {"KARAOKE": "karaoke", "TYPE": "typewriter",
                             "CALM": "calm"}[value]
        self._ui_log(f"MENU reveal = {self.reveal_style}")

    def _end_or_new(self):
        self._ui_log("CLICK end-session" if self.director else "CLICK new-story")
        if self.director:
            self.director.stop()
            self.director = None
            self.end_btn.configure(text="NEW STORY")
            self._u_status("session ended")
            return
        self._stop_music()
        self.story_frame.destroy()
        self._items, self._ranges, self._pending_nl = {}, {}, set()
        self._follow = True
        self._reset_image_state()
        self._build_setup_screen()

    # =========================================================================
    #  OBSERVATION DRAWER  (v11)
    # =========================================================================

    def _ui_log(self, message: str) -> None:
        line = f"[{time.time() - self._ui_t0:7.1f}s] {message}"
        try:
            print("  » " + line, flush=True)
        except Exception:
            pass
        if self._ui_log_path:
            try:
                with open(self._ui_log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
        try:
            self._drawer_append("» " + line)
        except Exception:
            pass

    def _drawer_append(self, text):
        if self.drawer_box is None:
            self._drawer_buffer = getattr(self, "_drawer_buffer", [])
            self._drawer_buffer.append(text)
            return
        self.drawer_box.configure(state="normal")
        self.drawer_box.insert("end", text + "\n")
        self.drawer_box.see("end")
        self.drawer_box.configure(state="disabled")

    def _open_drawer(self):
        self._ui_log("CLICK observe")
        if self.drawer is not None and self.drawer.winfo_exists():
            self.drawer.lift()
            return
        self.drawer = ctk.CTkToplevel(self)
        self.drawer.title("Story Lab — observation")
        self.drawer.geometry("640x560")
        box = tk.Text(self.drawer, bg=T("bg_widget"), fg=T("text_log"), wrap="word",
                      relief="flat", font=(T("font_family"), 11), state="disabled",
                      padx=10, pady=8)
        box.pack(fill="both", expand=True)
        self.drawer_box = box
        for text in getattr(self, "_drawer_buffer", []):
            self._drawer_append(text)
        self._drawer_buffer = []

    # =========================================================================
    #  SHUTDOWN
    # =========================================================================

    def _on_close(self):
        self._ui_log("WINDOW closed")
        if self.director:
            self.director.stop()
        tts.stop_audio()
        self._stop_music()
        images.shutdown_comfyui()        # only a server THIS app started
        self.destroy()


# =============================================================================
#  SECTION 3 - ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ctk.set_default_color_theme("blue")
    StoryLabApp().mainloop()
