"""
storylab_setup.py - Story Lab Setup, the window.

Started by the installer after it has copied Story Lab and made its Python
environment, and from the Start menu ("Story Lab Setup") whenever pictures
should be added, a download resumed, or something repaired. All the work is
in setup_core.py; this file only asks and shows.

Pages: Welcome -> Pictures -> ComfyUI -> CivitAI key (only if needed) ->
Licences -> Install -> Done.

  pythonw storylab_setup.py [--app-dir DIR] [--dry-run]
  --dry-run   walks every page and fakes the install (for trying the UI)
"""
from __future__ import annotations

import os
import sys
import time
import queue
import threading
import subprocess
import webbrowser

import customtkinter as ctk
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup_core as sc

# ---- look --------------------------------------------------------------------
BG, PANEL, CARD = "#14152b", "#1d1f3d", "#262950"
TEXT, MUTED, FAINT = "#eef0ff", "#a3a8d2", "#6f75a8"
AMBER, AMBER_DIM, VIOLET = "#f0a948", "#b97c2c", "#6b5bd6"
GREEN, RED = "#6fd39a", "#ff8a8a"
FONT = "Segoe UI"


def gb(n: float) -> str:
    if n >= 1e8:
        return f"{n / 1e9:.1f} GB"
    return f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


def find_asset(name: str) -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, "assets"), os.path.join(os.path.dirname(here), "assets")):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


class SetupApp(ctk.CTk):
    PAGES = ("welcome", "pictures", "comfy", "key", "licences", "install", "done")

    def __init__(self, app_dir: str, dry_run: bool = False):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.app_dir, self.dry = app_dir, dry_run
        self.title("Story Lab Setup")
        self.geometry("1120x720")
        self.minsize(980, 640)
        self.configure(fg_color=BG)
        ico = find_asset("storylab.ico")
        if ico:
            try:
                self.iconbitmap(ico)
            except Exception:
                pass
        self.man = sc.load_manifest()
        self.ch = sc.Choices(classical=True, cinematic=True, music=True, lazyneg=False)
        self.gpu = sc.gpu_info()
        self.comfys = sc.find_comfy_installs(app_dir)
        self.ollama_exe = sc.find_ollama_exe()
        self.ollama_up = sc.ollama_running()
        self.key_ok = False
        self.agreed = {}                      # item id -> BooleanVar
        self.events = queue.Queue()
        self.runner = None
        self.rows = {}
        self.page = None
        self._build_frame()
        self.show("welcome")
        self.after(100, self._poll)

    # ---- frame ---------------------------------------------------------------
    def _build_frame(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, fg_color=BG, corner_radius=0, width=352)
        side.grid(row=0, column=0, sticky="ns")
        art = find_asset("side_panel.png")
        if art:
            img = Image.open(art)
            self._side_img = ctk.CTkImage(img, size=(330, 630))
            ctk.CTkLabel(side, text="", image=self._side_img).pack(padx=(12, 6), pady=12)
        right = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 24), pady=18)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        logo = find_asset("storylab_1024.png")
        if logo:
            self._logo = ctk.CTkImage(Image.open(logo), size=(46, 46))
            ctk.CTkLabel(head, text="", image=self._logo).pack(side="left", padx=(0, 12))
        tbox = ctk.CTkFrame(head, fg_color="transparent")
        tbox.pack(side="left", fill="x", expand=True)
        self.h_title = ctk.CTkLabel(tbox, text="", text_color=TEXT, anchor="w",
                                    font=(FONT, 24, "bold"))
        self.h_title.pack(fill="x")
        self.h_sub = ctk.CTkLabel(tbox, text="", text_color=MUTED, anchor="w",
                                  font=(FONT, 13), justify="left", wraplength=640)
        self.h_sub.pack(fill="x")
        self.body = ctk.CTkFrame(right, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", pady=(14, 10))
        foot = ctk.CTkFrame(right, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew")
        self.dots = ctk.CTkLabel(foot, text="", text_color=FAINT, font=(FONT, 12))
        self.dots.pack(side="left")
        self.b_next = ctk.CTkButton(foot, text="Next", width=130, height=38, fg_color=AMBER,
                                    hover_color=AMBER_DIM, text_color="#1b1406",
                                    font=(FONT, 14, "bold"), command=self.next)
        self.b_next.pack(side="right")
        self.b_back = ctk.CTkButton(foot, text="Back", width=100, height=38, fg_color=CARD,
                                    hover_color=VIOLET, font=(FONT, 13), command=self.back)
        self.b_back.pack(side="right", padx=8)
        self.b_cancel = ctk.CTkButton(foot, text="Close", width=100, height=38,
                                      fg_color="transparent", border_width=1,
                                      border_color=CARD, hover_color=CARD,
                                      font=(FONT, 13), command=self.close)
        self.b_cancel.pack(side="right", padx=8)

    def _clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def _card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, **kw)

    def _flow(self):
        pics = sc.wants_comfy(self.ch)
        pages = ["welcome", "pictures"]
        if pics:
            pages.append("comfy")
        if self._key_items():
            pages.append("key")
        return pages + ["licences", "install", "done"]

    def show(self, name):
        self.page = name
        self._clear()
        getattr(self, f"_page_{name}")()
        flow = self._flow()
        i = flow.index(name) if name in flow else 0
        self.dots.configure(text="   ".join("●" if j == i else "○"
                                           for j in range(len(flow))))
        self.b_back.configure(state="normal" if 0 < i and name not in ("install", "done")
                              else "disabled")
        self._refresh_next()

    def next(self):
        flow = self._flow()
        if self.page == "install" and self.runner is None:
            return self._start_install()
        if self.page == "done":
            return self.close()
        i = flow.index(self.page)
        if i + 1 < len(flow):
            self.show(flow[i + 1])

    def back(self):
        flow = self._flow()
        i = flow.index(self.page)
        if i > 0:
            self.show(flow[i - 1])

    def close(self):
        if self.runner is not None and self.page == "install" and not getattr(self, "_finished", False):
            self.runner.cancel.set()
            self.after(600, self.destroy)
        else:
            self.destroy()

    def _refresh_next(self):
        ok, label = True, "Next"
        if self.page == "licences":
            ok = all(v.get() for v in self.agreed.values())
        elif self.page == "key":
            ok = self.key_ok or not self._key_items()
        elif self.page == "install":
            label = "Install" if self.runner is None else "Next"
            ok = self.runner is None or getattr(self, "_finished", False)
            if self.runner is None and getattr(self, "_space_problem", ""):
                ok = False
        elif self.page == "done":
            label = "Finish"
        self.b_next.configure(state="normal" if ok else "disabled", text=label)

    # ---- helpers ---------------------------------------------------------------
    def _default_comfy(self):
        """An existing ComfyUI that can draw what was chosen, else None (= ours)."""
        for c in self.comfys:
            if c.kind != "portable" or os.path.normcase(c.base) != os.path.normcase(
                    os.path.join(self.app_dir, "ComfyUI_windows_portable")):
                if sc.comfy_can(c, self.ch):
                    return c
        return None

    def _plan(self):
        return sc.build_plan(self.man, self.ch, self.app_dir, self.gpu)

    def _pending_ids(self):
        return {s.item["id"] for s in self._plan() if s.item and s.status != "skipped"}

    def _key_items(self):
        pend = self._pending_ids()
        return [it for it in sc.picture_items(self.man, self.ch)
                if sc.needs_key(it) and it["id"] in pend]

    # ---- pages -------------------------------------------------------------------
    def _page_welcome(self):
        self.h_title.configure(text="Welcome to Story Lab")
        self.h_sub.configure(text="Two characters, a world you describe, and a story that "
                                  "answers you - told aloud and, if you like, painted and scored. This "
                                  "assistant gets everything Story Lab needs onto this PC.")
        card = self._card(self.body)
        card.pack(fill="x", pady=(4, 10))
        ctk.CTkLabel(card, text="WHAT THIS PC HAS", text_color=AMBER, anchor="w",
                     font=(FONT, 13, "bold")).pack(fill="x", padx=18, pady=(14, 6))
        g = self.gpu
        rows = []
        if g.nvidia:
            rows.append((True, f"{g.name} - {g.vram_mb / 1024:.0f} GB, driver {g.driver}"))
            if g.vram_mb < 11500:
                rows.append((None, "Less than 12 GB of video memory: the story will run; "
                                   "pictures may be slow or not fit."))
            if g.driver_major and g.driver_major < 580:
                rows.append((None, "Graphics driver older than 580: update it before pictures "
                                   "(nvidia.com/drivers)."))
        else:
            rows.append((False, "No NVIDIA graphics card found - the story needs one to run "
                                "at a playable speed; pictures need one."))
        rows.append((bool(self.ollama_exe or self.ollama_up),
                     "Ollama is installed" if (self.ollama_exe or self.ollama_up)
                     else "Ollama is not installed yet - Setup installs it"))
        if self.comfys:
            for c in self.comfys:
                cannot = [w for w, has in (("draw Cinematic", c.supports_anima),
                                           ("make music", c.supports_music)) if not has]
                rows.append((True, f"{c.label}" + (f"  (cannot {' or '.join(cannot)})"
                                                   if cannot else "")))
        else:
            rows.append((None, "No ComfyUI found - Setup can install the official one"))
        rows.append((True, f"Free space: {sc.free_gb(self.app_dir):.0f} GB where Story Lab "
                           f"lives, {sc.free_gb(os.path.expanduser('~')):.0f} GB in your user "
                           f"folder (where Ollama keeps its models)"))
        for ok, text in rows:
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(fill="x", padx=18, pady=2)
            sym, col = ("✓", GREEN) if ok else ("✗", RED) if ok is False else ("!", AMBER)
            ctk.CTkLabel(r, text=sym, text_color=col, width=22, font=(FONT, 14, "bold")).pack(side="left")
            ctk.CTkLabel(r, text=text, text_color=TEXT, anchor="w", justify="left",
                         wraplength=600, font=(FONT, 13)).pack(side="left", fill="x")
        ctk.CTkLabel(card, text="", height=6).pack()
        ctk.CTkLabel(self.body, text="Nothing is downloaded until the Install page, and every "
                                     "model asks for your OK to its licence first.",
                     text_color=MUTED, anchor="w", font=(FONT, 12)).pack(fill="x", pady=(6, 0))

    def _page_pictures(self):
        self.h_title.configure(text="What should Story Lab do?")
        self.h_sub.configure(text="The story and the voices are always installed. Pictures and "
                                  "music are your choice. You can add them later by running "
                                  "Story Lab Setup again.")
        by = self.man["by_id"]

        def size_of(ids):
            return sum(by[i].get("size_bytes", 0) for i in ids)

        core = self._card(self.body)
        core.pack(fill="x", pady=(2, 8))
        ctk.CTkLabel(core, text="✓  Text and voice", text_color=TEXT, anchor="w",
                     font=(FONT, 16, "bold")).pack(fill="x", padx=18, pady=(12, 0))
        ctk.CTkLabel(core, text=f"Ollama + Rocinante-X-12B (the storyteller) + Kokoro voices "
                                f"- about {gb(size_of(['ollama', 'rocinante', 'kokoro']))}, "
                                f"less if already here", text_color=MUTED, anchor="w",
                     font=(FONT, 12)).pack(fill="x", padx=18, pady=(0, 12))

        self.v_classical = ctk.BooleanVar(value=self.ch.classical)
        self.v_cinematic = ctk.BooleanVar(value=self.ch.cinematic)
        self.v_music = ctk.BooleanVar(value=self.ch.music)
        self.v_lazyneg = ctk.BooleanVar(value=self.ch.lazyneg)

        def changed():
            self.ch.classical = self.v_classical.get()
            self.ch.cinematic = self.v_cinematic.get()
            self.ch.music = self.v_music.get()
            self.ch.lazyneg = self.v_lazyneg.get() and self.ch.classical
            self.lazy_box.configure(state="normal" if self.ch.classical else "disabled")
            self.ch.comfy = self._default_comfy() if sc.wants_comfy(self.ch) else None
            self._refresh_next()

        for var, title, text, ids in (
                (self.v_classical, "Classical + Medium scenes",
                 "Classical paints the place of each round - no people in it - beside a "
                 "portrait of each character; Medium puts both characters in the scene (a "
                 "little unruly). Nova Furry XL, an Illustrious model.", ["novafurry"]),
                (self.v_cinematic, "Cinematic scenes  (advanced)",
                 "Draws both characters IN the scene, in what the story has them wearing now, "
                 "with the people around them; portraits follow their clothes. Anima.",
                 ["marshmallow_anima", "qwen_text_encoder", "qwen_image_vae"]),
                (self.v_music, "Background music",
                 "A new instrumental track for every round, made from its mood and the "
                 "story's genre, looping under the voices. ACE-Step 1.5.",
                 list(sc.MUSIC_ITEMS))):
            c = self._card(self.body)
            c.pack(fill="x", pady=6)
            top = ctk.CTkFrame(c, fg_color="transparent")
            top.pack(fill="x", padx=18, pady=(12, 0))
            ctk.CTkCheckBox(top, text=title, variable=var, command=changed,
                            text_color=TEXT, font=(FONT, 16, "bold"), fg_color=AMBER,
                            hover_color=AMBER_DIM, checkmark_color="#1b1406").pack(side="left")
            ctk.CTkLabel(top, text=f"{gb(size_of(ids))} of models", text_color=AMBER,
                         font=(FONT, 12)).pack(side="right")
            ctk.CTkLabel(c, text=text, text_color=MUTED, anchor="w", justify="left",
                         wraplength=640, font=(FONT, 12)).pack(fill="x", padx=50, pady=(2, 4))
            if var is self.v_classical:
                self.lazy_box = ctk.CTkCheckBox(
                    c, text="Also lazyneg - optional, tidies Classical pictures (needs a free "
                            "CivitAI key)", variable=self.v_lazyneg, command=changed,
                    text_color=MUTED, font=(FONT, 12), fg_color=VIOLET, checkbox_width=18,
                    checkbox_height=18)
                self.lazy_box.pack(anchor="w", padx=50, pady=(0, 12))
            elif var is self.v_cinematic:
                ctk.CTkLabel(c, text="The Anima model Story Lab was tuned with needs a free "
                                     "CivitAI key; without one, the official Anima can be used.",
                             text_color=FAINT, anchor="w", font=(FONT, 11)).pack(
                    fill="x", padx=50, pady=(0, 12))
            else:
                ctk.CTkLabel(c, text="No key needed. Made on the graphics card at the end of "
                                     "each round, about 25 s on a 12 GB card.",
                             text_color=FAINT, anchor="w", font=(FONT, 11)).pack(
                    fill="x", padx=50, pady=(0, 12))
        pics = sc.wants_comfy(self.ch)
        self.ch.comfy = self._default_comfy() if pics else None
        changed()

    def _page_comfy(self):
        self.h_title.configure(text="ComfyUI - the picture and music engine")
        self.h_sub.configure(text="ComfyUI draws the pictures and makes the music; Story Lab starts and stops it by "
                                  "itself, you never have to open it.")
        self.v_comfy = ctk.StringVar(value="own" if self.ch.comfy is None
                                     else os.path.normcase(self.ch.comfy.main))
        build = sc.comfy_build_for(self.gpu)
        it = self.man["by_id"][build or "comfyui"]
        own_dir = os.path.join(self.app_dir, "ComfyUI_windows_portable")

        def pick():
            v = self.v_comfy.get()
            self.ch.comfy = None if v == "own" else next(
                c for c in self.comfys if os.path.normcase(c.main) == v)
            self._refresh_next()

        c = self._card(self.body)
        c.pack(fill="x", pady=6)
        ctk.CTkRadioButton(c, text="Install the official ComfyUI for Story Lab", value="own",
                           variable=self.v_comfy, command=pick, text_color=TEXT,
                           font=(FONT, 15, "bold"), fg_color=AMBER, hover_color=AMBER_DIM
                           ).pack(anchor="w", padx=18, pady=(12, 2))
        detail = (f"ComfyUI {it['version']} Windows portable from Comfy-Org on GitHub - "
                  f"{'CUDA 13 build for RTX cards' if build == 'comfyui' else 'CUDA 12.6 build for older cards'}"
                  f". {gb(it['size_bytes'])} download, about 6 GB unpacked, into\n{own_dir}\n"
                  f"Models go into its own models folders. Nothing else on the PC changes.")
        if not self.gpu.nvidia:
            detail += "\n⚠ No NVIDIA card was found: ComfyUI would run on the processor - very slow."
        ctk.CTkLabel(c, text=detail, text_color=MUTED, anchor="w", justify="left",
                     wraplength=640, font=(FONT, 12)).pack(fill="x", padx=50, pady=(0, 12))
        for inst in self.comfys:
            ok = sc.comfy_can(inst, self.ch)
            cc = self._card(self.body)
            cc.pack(fill="x", pady=6)
            ctk.CTkRadioButton(cc, text=f"Use the ComfyUI already here: {inst.label}",
                               value=os.path.normcase(inst.main), variable=self.v_comfy,
                               command=pick, text_color=TEXT if ok else FAINT,
                               state="normal" if ok else "disabled",
                               font=(FONT, 14, "bold"), fg_color=AMBER, hover_color=AMBER_DIM
                               ).pack(anchor="w", padx=18, pady=(12, 2))
            lacks = [w for w, need, has in (("Anima (Cinematic)", self.ch.cinematic,
                                              inst.supports_anima),
                                             ("ACE-Step 1.5 (music)", self.ch.music,
                                              inst.supports_music)) if need and not has]
            why = (f"Models go where it reads them: {inst.model_roots[0]}" if ok else
                   f"This version cannot load {' or '.join(lacks)} - update it, or let Setup "
                   "install the official ComfyUI.")
            ctk.CTkLabel(cc, text=why, text_color=MUTED, anchor="w", justify="left",
                         wraplength=640, font=(FONT, 12)).pack(fill="x", padx=50, pady=(0, 12))
        pick()

    def _page_key(self):
        self.h_title.configure(text="A free CivitAI key")
        self.h_sub.configure(text="Some models live on CivitAI, which only hands them to "
                                  "signed-in people. A key lets Setup download them for you - "
                                  "it is free and takes a minute.")
        need = self._key_items()
        c = self._card(self.body)
        c.pack(fill="x", pady=6)
        names = ", ".join(it["what"].split(" (")[0].split(" - ")[0] for it in need)
        steps = ("1.  Open your CivitAI account page (make a free account if you have none)\n"
                 "2.  Scroll to  API Keys  and press  Add API key  - name it “Story Lab”\n"
                 "3.  Copy the key and paste it below, then press  Check")
        ctk.CTkLabel(c, text=f"Needed for: {names}", text_color=AMBER, anchor="w",
                     font=(FONT, 13, "bold")).pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkLabel(c, text=steps, text_color=TEXT, anchor="w", justify="left",
                     font=(FONT, 13)).pack(fill="x", padx=18)
        ctk.CTkButton(c, text="Open the CivitAI account page ↗", fg_color=VIOLET,
                      hover_color="#5848c0", height=34, font=(FONT, 13),
                      command=lambda: webbrowser.open(self.man["civitai_key_page"])
                      ).pack(anchor="w", padx=18, pady=10)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 6))
        self.e_key = ctk.CTkEntry(row, placeholder_text="paste your CivitAI API key", show="•",
                                  width=430, height=36, font=(FONT, 13))
        self.e_key.pack(side="left")
        if self.ch.civitai_key:
            self.e_key.insert(0, self.ch.civitai_key)
        self.l_key = ctk.CTkLabel(c, text="", text_color=MUTED, anchor="w", font=(FONT, 12))

        def check():
            key = self.e_key.get().strip()
            self.l_key.configure(text="checking with CivitAI...", text_color=MUTED)
            self.update_idletasks()
            ok = self.dry or bool(key) and sc.check_civitai_key(key, need[0]["url"])
            self.key_ok = ok
            if ok:
                self.ch.civitai_key = key
                self.l_key.configure(text="✓ The key works - CivitAI will hand over the files.",
                                     text_color=GREEN)
            else:
                self.l_key.configure(text="✗ CivitAI did not accept that key. Check it was "
                                          "copied whole, or make a new one.", text_color=RED)
            self._refresh_next()

        ctk.CTkButton(row, text="Check", width=90, height=36, fg_color=AMBER, hover_color=AMBER_DIM,
                      text_color="#1b1406", font=(FONT, 13, "bold"), command=check).pack(side="left", padx=8)
        self.l_key.pack(fill="x", padx=18, pady=(0, 14))
        alt = self._card(self.body)
        alt.pack(fill="x", pady=6)
        ctk.CTkLabel(alt, text="No key?", text_color=AMBER, anchor="w",
                     font=(FONT, 13, "bold")).pack(fill="x", padx=18, pady=(12, 2))
        self.v_official = ctk.BooleanVar(value=self.ch.anima_official)

        def no_key():
            if self.ch.cinematic:
                self.ch.anima_official = self.v_official.get()
            if self.v_official.get():
                self.ch.lazyneg = False
            self.key_ok = not self._key_items() or self.key_ok
            self._refresh_next()

        text = []
        if self.ch.cinematic:
            text.append("Cinematic uses the official Anima Aesthetic from CircleStone Labs "
                        "instead (no key; a slightly different look)")
        if self.ch.lazyneg:
            text.append("lazyneg is left out (it is optional)")
        ctk.CTkCheckBox(alt, text="Continue without a key", variable=self.v_official,
                        command=no_key, text_color=TEXT, font=(FONT, 13, "bold"),
                        fg_color=VIOLET).pack(anchor="w", padx=18, pady=(2, 2))
        bullets = "\n".join("• " + t for t in text)
        ctk.CTkLabel(alt, text=bullets, text_color=MUTED,
                     anchor="w", justify="left", wraplength=620, font=(FONT, 12)
                     ).pack(fill="x", padx=50, pady=(0, 14))

    def _page_licences(self):
        self.h_title.configure(text="Licences")
        self.h_sub.configure(text="Each program and model comes from its own makers under its own "
                                  "licence. Read what you like, and tick each one to agree. Setup "
                                  "downloads nothing you have not agreed to.")
        plan = self._plan()
        status = {s.item["id"]: s for s in plan if s.item}
        items = sc.licence_items(self.man, self.ch)
        if self.ch.comfy is None and sc.wants_comfy(self.ch):
            build = sc.comfy_build_for(self.gpu) or "comfyui"
            items = [self.man["by_id"][build] if i["id"] == "comfyui" else i for i in items]
        box = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        box.pack(fill="both", expand=True)
        keep = {}
        for it in items:
            st = status.get(it["id"])
            already = st is not None and st.status == "skipped"
            lic = it["licence"]
            c = self._card(box)
            c.pack(fill="x", pady=5, padx=(0, 6))
            top = ctk.CTkFrame(c, fg_color="transparent")
            top.pack(fill="x", padx=16, pady=(10, 0))
            ctk.CTkLabel(top, text=it["what"], text_color=TEXT, anchor="w", justify="left",
                         wraplength=560, font=(FONT, 14, "bold")).pack(side="left")
            if it.get("size_bytes"):
                ctk.CTkLabel(top, text=gb(it["size_bytes"]), text_color=MUTED,
                             font=(FONT, 12)).pack(side="right")
            ctk.CTkLabel(c, text=f"{lic['name']}\n{lic['summary']}", text_color=MUTED, anchor="w",
                         justify="left", wraplength=640, font=(FONT, 12)).pack(fill="x", padx=16)
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(6, 10))
            ctk.CTkButton(row, text="Read the licence ↗", width=150, height=28, fg_color=VIOLET,
                          hover_color="#5848c0", font=(FONT, 12),
                          command=lambda u=lic["url"]: webbrowser.open(u)).pack(side="left")
            if lic.get("url2"):
                ctk.CTkButton(row, text="Model page ↗", width=120, height=28, fg_color=CARD,
                              border_width=1, border_color=VIOLET, hover_color="#33366a",
                              font=(FONT, 12), command=lambda u=lic["url2"]: webbrowser.open(u)
                              ).pack(side="left", padx=8)
            if already:
                ctk.CTkLabel(row, text="✓ already on this PC", text_color=GREEN,
                             font=(FONT, 12)).pack(side="right")
                continue
            var = self.agreed.get(it["id"]) or ctk.BooleanVar(value=False)
            keep[it["id"]] = var
            ctk.CTkCheckBox(row, text="I agree to this licence", variable=var,
                            command=self._refresh_next, text_color=TEXT, font=(FONT, 12, "bold"),
                            fg_color=AMBER, hover_color=AMBER_DIM, checkmark_color="#1b1406"
                            ).pack(side="right")
        self.agreed = keep

    def _page_install(self):
        self.h_title.configure(text="Install")
        plan = self._plan()
        self.plan = plan
        total = sc.plan_bytes(plan)
        # disk: the Ollama model goes to the user folder; everything else to its target
        need = {}
        for s in plan:
            if s.status == "skipped" or not s.size:
                continue
            where = os.path.expanduser("~") if s.kind in ("ollama_install", "ollama_pull", "hf_snapshot") \
                else (s.target or self.app_dir)
            drive = os.path.splitdrive(os.path.abspath(where))[0].upper() or where
            extra = 4e9 if s.kind == "comfy_portable" else 0          # unpacked size
            need[drive] = need.get(drive, 0) + s.size + extra
        problems = [f"{d} needs {gb(n)} but has {sc.free_gb(d + os.sep):.0f} GB free"
                    for d, n in need.items() if sc.free_gb(d + os.sep) * 1e9 < n * 1.05]
        self._space_problem = "; ".join(problems)
        self.h_sub.configure(text=(f"{gb(total)} to download. Downloads resume if the connection "
                                   f"drops - just run Setup again." if total else
                                   "Everything is already on this PC - Setup will just connect it.")
                             + (f"\n⚠ Not enough space: {self._space_problem}" if problems else ""))
        box = ctk.CTkScrollableFrame(self.body, fg_color="transparent")
        box.pack(fill="both", expand=True)
        self.rows = {}
        for s in plan:
            c = self._card(box)
            c.pack(fill="x", pady=4, padx=(0, 6))
            top = ctk.CTkFrame(c, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(8, 2))
            icon = ctk.CTkLabel(top, text="○", width=22, text_color=FAINT, font=(FONT, 15, "bold"))
            icon.pack(side="left")
            ctk.CTkLabel(top, text=s.label, text_color=TEXT, anchor="w", font=(FONT, 13, "bold")
                         ).pack(side="left")
            note = ctk.CTkLabel(top, text=(s.note if s.status == "skipped"
                                           else gb(s.size) if s.size else ""),
                                text_color=MUTED, font=(FONT, 12))
            note.pack(side="right")
            bar = ctk.CTkProgressBar(c, height=8, progress_color=AMBER, fg_color="#30335f")
            bar.set(1 if s.status == "skipped" else 0)
            bar.pack(fill="x", padx=(48, 14), pady=(2, 10))
            if s.status == "skipped":
                icon.configure(text="✓", text_color=GREEN)
                bar.configure(progress_color=GREEN)
            self.rows[s.id] = (icon, note, bar)
        self.log = ctk.CTkTextbox(self.body, height=70, fg_color=PANEL, text_color=MUTED,
                                  font=("Consolas", 11))
        self.log.pack(fill="x", pady=(8, 0))
        self.log.insert("end", f"Story Lab folder: {self.app_dir}\n")
        if self.ch.comfy:
            self.log.insert("end", f"ComfyUI: {self.ch.comfy.label}\n")

    def _page_done(self):
        ok = getattr(self, "_ok", False)
        self.h_title.configure(text="Story Lab is ready" if ok else "Setup stopped")
        self.h_sub.configure(text=("Everything is installed and connected. Start a story from "
                                   "the desktop icon, or right here." if ok else
                                   "Something did not finish (see the Install page). Run Story "
                                   "Lab Setup again from the Start menu - finished downloads are "
                                   "kept, interrupted ones continue."))
        c = self._card(self.body)
        c.pack(fill="x", pady=6)
        styles = [n for n, on in (("Classical + Medium", self.ch.classical),
                                  ("Cinematic", self.ch.cinematic)) if on]
        extra = ((" + " + " and ".join(styles) + " pictures") if styles else "") + \
            (" + music" if self.ch.music else "")
        ctk.CTkLabel(c, text=f"Text and voice{extra}",
                     text_color=TEXT, anchor="w", font=(FONT, 15, "bold")).pack(fill="x", padx=18, pady=(14, 4))
        self.l_test = ctk.CTkLabel(c, text="", text_color=MUTED, anchor="w", justify="left",
                                   font=(FONT, 12), wraplength=640)
        self.l_test.pack(fill="x", padx=18)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=14)
        if ok:
            ctk.CTkButton(row, text="▶  Play Story Lab", width=190, height=40, fg_color=AMBER,
                          hover_color=AMBER_DIM, text_color="#1b1406", font=(FONT, 15, "bold"),
                          command=self._play).pack(side="left")
            ctk.CTkButton(row, text="Test everything", width=150, height=40, fg_color=VIOLET,
                          hover_color="#5848c0", font=(FONT, 13), command=self._test
                          ).pack(side="left", padx=10)

    # ---- install ----------------------------------------------------------------
    def _start_install(self):
        self.b_back.configure(state="disabled")
        self.b_cancel.configure(text="Cancel")
        emit = lambda *a: self.events.put(a)
        if self.dry:
            self.runner = _FakeRunner(self.plan, emit)
        else:
            self.runner = sc.Runner(self.man, self.ch, self.plan, self.app_dir, emit, self.gpu)
        self.runner.start()
        self._refresh_next()

    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                self._on_event(*ev)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _on_event(self, kind, st, *data):
        if kind == "log":
            if hasattr(self, "log") and self.log.winfo_exists():
                self.log.insert("end", data[0] + "\n")
                self.log.see("end")
            return
        if kind == "finished":
            self._finished, self._ok = True, bool(data[0])
            self.b_cancel.configure(text="Close")
            self._refresh_next()
            if self._ok:
                self.after(600, lambda: self.show("done"))
            return
        row = self.rows.get(st.id) if st else None
        if not row:
            return
        icon, note, bar = row
        if kind == "start":
            icon.configure(text="◔", text_color=AMBER)
        elif kind == "progress":
            done, total, phase = (data + ("",))[:3]
            if total:
                bar.set(min(1.0, done / total))
                note.configure(text=f"{phase}  {gb(done)} / {gb(total)}" if total > 1 else phase)
            else:
                note.configure(text=phase)
        elif kind in ("done", "skipped"):
            icon.configure(text="✓", text_color=GREEN)
            bar.configure(progress_color=GREEN)
            bar.set(1)
            note.configure(text="done" if kind == "done" else st.note)
        elif kind == "failed":
            icon.configure(text="✗", text_color=RED)
            bar.configure(progress_color=RED)
            note.configure(text="stopped")
            self._on_event("log", None, f"{st.label}: {data[0]}")

    def _play(self):
        py = sys.executable
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        game = os.path.join(self.app_dir, "story_lab_gui12.py")
        subprocess.Popen([pyw if os.path.isfile(pyw) else py, game], cwd=self.app_dir)
        self.after(500, self.destroy)

    def _test(self):
        self.l_test.configure(text="Testing - Ollama, then ComfyUI with each picture style "
                                   "(up to a minute)...")
        lines = []

        def work():
            if self.dry:
                time.sleep(1)
                lines.append("dry run - nothing tested")
            else:
                sc.self_test(self.app_dir, events=lines.append)
            self.after(0, lambda: self.l_test.configure(text="\n".join(lines)))

        threading.Thread(target=work, daemon=True).start()


class _FakeRunner:
    """--dry-run: walks the plan with made-up progress."""

    def __init__(self, steps, events):
        self.steps, self.events = steps, events
        self.cancel = threading.Event()

    def start(self):
        def run():
            for st in self.steps:
                if st.status == "skipped":
                    self.events("skipped", st)
                    continue
                self.events("start", st)
                for k in range(11):
                    if self.cancel.is_set():
                        self.events("finished", None, False)
                        return
                    self.events("progress", st, k * max(st.size, 1) / 10, max(st.size, 1), "downloading")
                    time.sleep(0.08)
                self.events("done", st)
            self.events("finished", None, True)
        threading.Thread(target=run, daemon=True).start()


def main():
    args = sys.argv[1:]
    app_dir = args[args.index("--app-dir") + 1] if "--app-dir" in args else sc.default_app_dir()
    SetupApp(os.path.abspath(app_dir), dry_run="--dry-run" in args).mainloop()


if __name__ == "__main__":
    main()
