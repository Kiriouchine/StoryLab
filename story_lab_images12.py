"""
story_lab_images12.py  —  Story Lab v12  //  ComfyUI image layer, JSON-driven

PURPOSE
=======
Turn the two workflow JSON files that sit next to this script into images:

    Workflow_portrait_api3.json   one portrait per character  (800 x 1000)
    Workflow_wide_api_3.json      one wide scene per round    (1536 x 1024)

Pure blocking functions, no threads - story_lab_director12 runs them on its
image lane. The module never imports the engine (the voice layer has the same
rule): it reads a StoryCharacter by duck typing (name, gender, age_group,
fp_image) so it can be tested, and driven, on its own.

WHAT IS NEW AGAINST story_lab_images5
=====================================
1. THE JSON FILES ARE THE SOURCE OF TRUTH. v5 carried a hand-converted copy
   of the portrait workflow as a Python dict, so an edit made in ComfyUI never
   reached the game. v12 loads both files from disk on every job (cached by
   mtime) and accepts EITHER format ComfyUI saves:
     - API format  ("Export (API)": {"7": {"class_type": ..., "inputs": ...}})
     - UI format   (the editor's own save: {"nodes": [...], "links": [...]})
   UI format is converted here (convert_ui_to_api), including the frontend's
   PrimitiveInt / Primitive / Reroute helper nodes, which the server does not
   execute and which are folded into literal values.
2. NODES ARE FOUND BY ROLE, NOT BY ID. v5 wrote into node "5" and node "7".
   v12 follows the graph from the sampler: its `positive` input leads to the
   prompt node, `negative` to the negative prompt, `latent_image` to the size.
   A workflow re-saved with different ids, or with a LoRA loader inserted,
   still works. A workflow with no sampler or no prompt is refused with a
   message naming what is missing (WorkflowError), never sent half-filled.
3. COMFYUI DESKTOP IS FOUND AND LAUNCHED. The Desktop app serves on port 8001,
   which v5's probe list never tried. v12 probes 8188 and 8001 first, and can
   start the Desktop app's own backend headless (its venv Python + main.py,
   read from %APPDATA%\\ComfyUI\\config.json) on 8188.
4. SSLKEYLOGFILE IS STRIPPED from the launched server's environment. On this
   machine the antivirus sets it to a named pipe, and ComfyUI's Python then
   dies at startup with "OPENSSL_Uplink: no OPENSSL_Applink" (measured
   2026-10-16; the server starts in ~16 s once the variable is removed).
5. VRAM CAN BE HANDED BACK. free_vram() asks ComfyUI to unload its models
   AND free its memory, and waits until the card's own free memory shows it.
   The director calls it so the LLM and the image model can share one 12 GB
   card - see director12. (v12.0-12.3 sent unload_models only, to keep the
   checkpoint cached in RAM; that was right for the old ComfyUI 0.5. The new
   Comfy Desktop 0.30 - needed for Anima and ACE-Step 1.5 - keeps weights
   resident on the card after unload_models ("dynamic VRAM loading"), and
   its torch_vram_total reads ~0 while it does. Measured 2026-10-17,
   loop_reports/v12_4_music/probe_memory.json: after a picture + unload
   5.8 GB of 12 free, after a music job + unload 1.6 GB free - Rocinante
   (10.2 GB) was then loaded into the rest and paged; with free_memory too:
   11.0 GB free in 0.2 s.)
6. EVERY JOB IS LOGGED to <run_dir>/images.txt: kind, file, seed, seconds,
   and the exact prompt sent.

v12.3 CINEMATIC (Section 1d): the cinematographer's tag lines are cleaned
(cine_hygiene) and laid out for Anima, one sentence per character
(build_cinematic_prompt, build_cine_portrait_prompt); two more workflows
(WORKFLOW_CINEMATIC_FILE, WORKFLOW_CINE_PORTRAIT_FILE), two more prompt
kinds; missing_models() tells a session whether this server can draw them;
the new Comfy Desktop install (ComfyUI 0.30, the only one here that loads
Anima) is preferred when the game starts ComfyUI itself.

FAILURE MODEL
=============
Generation functions return a path or None. A dead ComfyUI, a missing
checkpoint or a malformed workflow degrades the session to text-and-voice;
images are decor, never a gate. Only load_workflow() raises (WorkflowError),
so a broken JSON file is reported once, clearly, instead of per job.
"""

import os
import re
import copy
import json
import time
import uuid
import random
import subprocess
import requests

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

WORKFLOW_SCENE_FILE    = os.path.join(_SCRIPT_DIR, "Workflow_wide_api_3.json")
WORKFLOW_PORTRAIT_FILE = os.path.join(_SCRIPT_DIR, "Workflow_portrait_api3.json")
# v12.3: the Cinematic scene (both leads in the picture) - the user's
# Animatwopersons_API.json at the wide 1216x832 (Anima's ~1 MP, 3:2) - and
# the Cinematic portrait, the same graph at 832x1040. Same model as the
# scene: the portrait face matches the scene's, and no SDXL swap (live game
# 1: SDXL portraits after an Anima scene took 18-40 s, against 10-12 s in a
# Classical game; Anima portraits 24 s with the model already loaded).
WORKFLOW_CINEMATIC_FILE = os.path.join(_SCRIPT_DIR, "Workflow_cinematic_api.json")
WORKFLOW_CINE_PORTRAIT_FILE = os.path.join(_SCRIPT_DIR, "Workflow_cinematic_portrait_api.json")

# 8188 = ComfyUI's own default and where launch_comfyui() starts it; 8001 =
# the ComfyUI Desktop app. The rest are v5's list, kept for other installs.
COMFYUI_PORTS = [8188, 8001, 8000, 8080, 8081, 3000]
LAUNCH_PORT   = 8188

MAX_IMAGE_WAIT = 300   # seconds before one job is abandoned (a wedged queue
                       # must never hang the lane)

# =============================================================================
#  SECTION 1 - CLIP PROMPT FRAMING   (verbatim from images5 unless noted)
#
#  CLIP reads 77 tokens. The scene prompter is asked for under fifty; these
#  wrappers add ~12 each.
# =============================================================================

IMAGE_PROMPT_PREPEND = ""

IMAGE_PROMPT_APPEND = (
    ", highly detailed, photorealistic, 8k resolution, "
    "masterpiece, cinematic composition, sharp focus"
)

PORTRAIT_PROMPT_APPEND = (
    ", portrait, solo, looking at viewer, detailed face, "
    "upper body, highly detailed, masterpiece, photorealistic"
)

_MOOD_TOKENS = {
    "tense":      "tense expression, furrowed brow",
    "afraid":     "wide eyes, fearful expression",
    "scared":     "wide eyes, fearful expression",
    "angry":      "stern expression, narrowed eyes",
    "grief":      "downcast eyes, sorrowful expression",
    "sad":        "downcast eyes, melancholic expression",
    "determined": "resolute expression, firm jaw",
    "relieved":   "relaxed expression, soft eyes",
    "happy":      "warm smile, bright eyes",
    "joyful":     "warm smile, bright eyes",
    "suspicious": "narrowed eyes, cautious expression",
    "surprised":  "wide eyes, raised eyebrows",
    "exhausted":  "weary expression, heavy eyes",
    "tender":     "soft gaze, gentle smile",
    "smug":       "confident smirk, raised eyebrow",
}
# v12.4: word STEMS per mood, counted over the whole text. The exact-word
# scan found nothing in the user's Classical game (2026-10-18): "tension
# crackles", "leans in", "flames crackle" - so all six "living portraits" of
# a lead had byte-identical prompts and looked the same.
_MOOD_STEMS = {
    "tense":      ("tens", "nervous", "anxious", "uneas", "wary", "strain", "edgy"),
    "afraid":     ("afraid", "fear", "terrif", "scared", "panic", "dread", "horror"),
    "angry":      ("angr", "anger", "furious", "fury", "rage", "glar", "snarl", "hostil"),
    "sad":        ("sad", "sorrow", "grief", "griev", "weep", "mourn", "melanchol", "heartbr"),
    "determined": ("determin", "resolv", "resolute", "steel", "defian"),
    "relieved":   ("reliev", "relief", "peace", "calm"),
    "happy":      ("happ", "joy", "laugh", "smil", "grin", "delight", "cheer", "celebrat"),
    "suspicious": ("suspic", "distrust", "guarded", "skeptic", "sceptic"),
    "surprised":  ("surpris", "shock", "astonish", "stunn", "gasp"),
    "exhausted":  ("exhaust", "tired", "weary", "drain"),
    "tender":     ("tender", "gentle", "affection", "love", "caress", "embrac"),
    "smug":       ("smirk", "smug", "superior", "arrogan", "haught", "condescend"),
}

_GENDER_TOKEN = {"female": "woman", "male": "man", "nonbinary": "person"}
_AGE_TOKEN    = {"YoungAdult": "young adult", "MiddleAged": "middle-aged",
                 "Elder": "elderly"}


def clean_tokens(text: str) -> str:
    """
    One line of CLIP tokens from extractor output. NEW in v12: the extractor
    sometimes wraps fp_image in brackets or quotes ("[Scarred jaw, Grey
    leather coat]" in a July run); CLIP reads those as weighting syntax.
    """
    text = " ".join((text or "").split())
    return text.strip(" []\"'").replace("[", "").replace("]", "")


def wrap_scene_prompt(raw_keywords: str) -> str:
    """The engine's RAW scene keywords inside the CLIP boosters."""
    return f"{IMAGE_PROMPT_PREPEND}{clean_tokens(raw_keywords)}{IMAGE_PROMPT_APPEND}"


def scan_mood(text: str) -> str:
    """The mood the text's words point to most -> portrait expression tokens
    ("" when no word does). v12.4: word stems, counted (see _MOOD_STEMS)."""
    words = re.findall(r"[a-z]+", (text or "").lower())
    best, score = "", 0
    for mood, stems in _MOOD_STEMS.items():
        n = sum(1 for w in words if w.startswith(stems))
        if n > score:
            best, score = mood, n
    return _MOOD_TOKENS[best] if best else ""


# v12.4: a re-roll is a different picture, not a new seed of the same one -
# NovaFurry drew the same face, pose and hall from the same prompt (the
# user's game: 13 portraits, one look). Take n uses variation n.
REROLL_VARIATIONS = (
    "three-quarter view, soft smile, warm light",
    "looking over shoulder, serious expression, dramatic side light",
    "close-up, determined look, rim light",
    "side profile, thoughtful expression, cool light",
    "slight head tilt, playful smirk, golden hour light",
    "looking down, pensive expression, soft window light",
)


def reroll_variation(take: int) -> str:
    return REROLL_VARIATIONS[(max(1, int(take)) - 1) % len(REROLL_VARIATIONS)]


def portrait_body(char, mood_hint: str = "", wearing: str = "",
                  backdrop: str = "", variation: str = "") -> str:
    """
    The character part of a portrait prompt - no LLM call. Order as images5:
    the character's own visual tokens first (CLIP weights the front highest),
    then age and gender, then the optional mood. v12.1: the framing moved to
    the portrait's positive POSTPEND (prompt settings), so it can be edited.
    v12.4 (Classical living portraits and re-rolls): `wearing` replaces the
    clothing items of the character's look (the clothes the player's words
    gave them); `backdrop` = the round's place and light behind them;
    `variation` = a re-roll's pose / expression / light. All empty = v12.3.
    """
    parts = []
    fp = clean_tokens(getattr(char, "fp_image", "") or "")
    if fp and fp.lower() != "unspecified":
        if wearing:
            # the look's clothing items go - and a lowercase continuation of
            # one ("Worn school robes, slightly too long for him", live)
            keep, after_cut = [], False
            for t in (x for x in re.split(r"\s*[,;]\s*", fp) if x):
                if any(w.lower() in _CLOTHING_WORDS for w in _WORD.findall(t)):
                    after_cut = True
                elif after_cut and t[0].islower():
                    continue
                else:
                    after_cut = False
                    keep.append(t)
            fp = ", ".join(keep)
        if fp:
            parts.append(fp)
    if wearing:
        parts.append(f"wearing {wearing}")
    parts.append(f"{_AGE_TOKEN.get(getattr(char, 'age_group', ''), 'adult')} "
                 f"{_GENDER_TOKEN.get(getattr(char, 'gender', ''), 'person')}")
    if mood_hint:
        parts.append(mood_hint)
    if variation:
        parts.append(variation)
    if backdrop:
        parts.append(f"background: {backdrop}")
    return join_prompt(*parts)


def build_portrait_prompt(char, mood_hint: str = "") -> str:
    """v12.0's portrait prompt, byte for byte = body + the default framing."""
    return join_prompt(portrait_body(char, mood_hint), PORTRAIT_PROMPT_APPEND)


def join_prompt(*parts) -> str:
    """Comma-join prompt parts, skipping empties, never doubling a comma."""
    return ", ".join(p.strip(" ,\n") for p in parts if p and p.strip(" ,\n"))

# =============================================================================
#  SECTION 1b - v12.1 PROMPT SETTINGS  (the "Picture prompts" screen)
#
#  Every image's text = POSITIVE PREPEND + body + POSITIVE POSTPEND, and its
#  negative = NEGATIVE PREPEND + NEGATIVE POSTPEND, per kind ("scene",
#  "portrait"). Saved to image_prompt_settings.json beside this file.
#
#  Scene defaults, from how characterless backgrounds are prompted on
#  Danbooru-tag models like this Illustrious checkpoint (2026-10-16 survey:
#  CivitAI background-tag guide #7972, the NovelAI image tutorial, Illustrious
#  background LoRAs): "no humans" and "scenery" lead, because what comes
#  first steers most - and in ComfyUI literally so: CLIPTextEncode encodes a
#  long prompt in 77-token sections and concatenates them, but SDXL's pooled
#  vector comes from the FIRST section only (comfy/sd1_clip.py,
#  "first_pooled"). "still life" (nature morte) is the Danbooru tag for an
#  arrangement of objects - right for a table of things, too close-up for a
#  room or a landscape, so it is not a default. People go in the negative.
#  Portrait defaults reproduce v12.0's portraits exactly.
# =============================================================================

PROMPT_SETTINGS_FILE = os.path.join(_SCRIPT_DIR, "image_prompt_settings.json")
SCENE_BODY_MAX_WORDS = 180
PROMPT_FIELDS = ("pos_prepend", "pos_postpend", "neg_prepend", "neg_postpend")
PROMPT_KINDS = ("scene", "portrait", "cinematic", "cine_portrait",   # v12.3: + 2
                "medium")                                               # v12.4: + 1
# v12.4 MEDIUM's style words - the v12.3 study's own (cine_lab USER_STYLE)
MEDIUM_POS_POSTPEND = ("highly detailed, photorealistic, 8k resolution, masterpiece, "
                       "cinematic composition, sharp focus")

SCENE_POS_PREPEND = "no humans, scenery, wide shot, detailed background"
# v12.3 Cinematic defaults. Anima's own recommended prefix ("masterpiece, best
# quality, score_7, safe" - the model card; "safe" because the card warns
# that short or vague prompts can drift into unwanted content) followed by
# the user's style words. The negative: the card's low-quality and low-score
# tags, "solo" (two people are wanted), and the user's usual defects.
CINE_POS_PREPEND = ("masterpiece, best quality, score_7, safe, highly detailed, "
                    "photorealistic, 8k resolution, cinematic composition, sharp focus")
CINE_NEG_PREPEND = ("worst quality, low quality, score_1, score_2, score_3, solo, "
                    "blurry, jpeg artifacts, bad anatomy, bad hands, extra fingers, "
                    "text, watermark, signature, furry, monochrome, simple background, "
                    "deformed, disfigured, poorly drawn face, crosseyed, lowres, nsfw")
# the portrait wants ONE person: "solo" leaves the negative, the multiples go in
CINE_PORTRAIT_NEG = (CINE_NEG_PREPEND.replace(" solo,", "")
                     + ", multiple girls, multiple boys, 2girls, 2boys")
SCENE_NEG_POSTPEND = (
    "1girl, 1boy, multiple girls, multiple boys, solo, person, people, human, "
    "humanoid, crowd, character, face, portrait, figure, silhouette, hands, "
    "legs, feet, footwear, boots, high heels"
)


def workflow_negative(path: str) -> str:
    """The negative prompt text stored in a workflow file ("" if none)."""
    try:
        api = load_workflow(path)
        neg = find_roles(api)["negative"]
        return api[neg]["inputs"].get("text", "") if neg else ""
    except WorkflowError:
        return ""


def default_prompt_settings() -> dict:
    return {
        "scene": {"pos_prepend": SCENE_POS_PREPEND,
                  "pos_postpend": IMAGE_PROMPT_APPEND.lstrip(", "),
                  "neg_prepend": workflow_negative(WORKFLOW_SCENE_FILE),
                  "neg_postpend": SCENE_NEG_POSTPEND},
        "portrait": {"pos_prepend": "",
                     "pos_postpend": PORTRAIT_PROMPT_APPEND.lstrip(", "),
                     "neg_prepend": workflow_negative(WORKFLOW_PORTRAIT_FILE),
                     "neg_postpend": ""},
        "cinematic": {"pos_prepend": CINE_POS_PREPEND,
                      "pos_postpend": "",
                      "neg_prepend": CINE_NEG_PREPEND,
                      "neg_postpend": ""},
        "cine_portrait": {"pos_prepend": CINE_POS_PREPEND,
                          "pos_postpend": "",
                          "neg_prepend": CINE_PORTRAIT_NEG,
                          "neg_postpend": ""},
        # v12.4: Medium = NovaFurry with both leads - the scene workflow's own
        # negative, no people tags in it (they are the point)
        "medium": {"pos_prepend": "",
                   "pos_postpend": MEDIUM_POS_POSTPEND,
                   "neg_prepend": workflow_negative(WORKFLOW_SCENE_FILE),
                   "neg_postpend": ""},
    }


def load_prompt_settings(path: str = None) -> dict:
    """Defaults overlaid with whatever was saved (unknown keys ignored)."""
    settings = default_prompt_settings()
    try:
        with open(path or PROMPT_SETTINGS_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return settings
    for kind in PROMPT_KINDS:
        for field in PROMPT_FIELDS:
            value = (saved.get(kind) or {}).get(field)
            if isinstance(value, str):
                settings[kind][field] = value
    return settings


def save_prompt_settings(settings: dict, path: str = None) -> None:
    clean = {k: {f: str(settings.get(k, {}).get(f, "")) for f in PROMPT_FIELDS}
             for k in PROMPT_KINDS}
    with open(path or PROMPT_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=1, ensure_ascii=False)


def wrap_prompt(kind: str, body: str, settings: dict = None) -> tuple:
    """(positive, negative) for one image of `kind` around its body."""
    s = (settings or default_prompt_settings())[kind]
    return (join_prompt(s["pos_prepend"], body, s["pos_postpend"]),
            join_prompt(s["neg_prepend"], s["neg_postpend"]))

# =============================================================================
#  SECTION 1c - v12.1 SCENE HYGIENE  (what may reach a characterless scene)
#
#  The scene painter (engine12) is asked for an empty place; these checks
#  make that true whatever it writes. Built on the first draft's 20 cases:
#  "students and their families", "Kaya & Bobb", "distant-sea-moans",
#  "chatter", "rusty_orbital_hangar", pipes for commas.
# =============================================================================

_PERSON_WORDS = frozenset("""
man men woman women girl girls boy boys child children kid kids person persons
people figure figures crowd crowds student students teacher teachers professor
professors headmaster headmasters headmistress family families stranger
strangers someone somebody everyone everybody anyone nobody passenger
passengers guard guards soldier soldiers worker workers crew keeper keepers
detective officer captain collector smuggler wizard wizards witch witches
knight knights traveler travelers traveller travellers couple pair duo lady
ladies gentleman gentlemen parent parents mother father son daughter friend
friends townsfolk townspeople villagers onlookers bystanders residents citizens
personnel staff audience spectators pupils pupil adults adult elders
head heads
he she him his her hers they them their theirs i me my myself we us our you
your yourself
face faces eyes eye hand hands finger fingers arm arms leg legs foot feet heel
heels boot boots shoe shoes hair lips smile smirk expression gaze stare glance
shoulder shoulders characters
kneeling kneels crouching crouched stumbling stumble stumbles staring
""".split())
# NOT person words, though the first draft had them: running/sitting/standing
# describe objects as often as people ("hydraulic line running along ceiling").
_PRONOUNS = frozenset("he she him his her hers they them their theirs i me my "
                      "myself we us our you your yourself".split())
# A trace of a person is what a characterless scene SHOWS ("a single boot print
# visible in dust") - a body word next to one of these is not a person.
_TRACE_WORDS = frozenset("print prints footprint footprints bootprint bootprints "
                         "track tracks mark marks".split())
_CUT_AT = frozenset("as while where with behind near beside between around before "
                    "toward towards past by for of from under over among except "
                    "and".split())
_SOUND_WORDS = frozenset("""
sound sounds noise noises voice voices silence silent quiet whisper whispers
whispering shout shouts scream screams echo echoes echoing chatter murmur
murmurs moan moans moaning click clicks clicking clink clank thud thump bang
hum humming whistle whistling creak creaking rattle rattling smell smells
scent scents odor odour taste aroma
""".split())
_TRAILING_LINKS = frozenset("""
behind near beside with at by of for to from around before between over under
and & toward towards past on in into onto the a an its atop upon inside against
""".split())
_STOP = frozenset("the a an of and with in on at to from into onto over under".split())
# The painter talking about its task rather than the scene ("Awaiting
# additional scene details", "No other personnel present").
_META_PHRASES = ("scene details", "awaiting", "not yet", "n/a", "no other")
_WORD = re.compile(r"[A-Za-z][A-Za-z']*")


def _norm_tag(tag: str) -> str:
    t = tag.replace("_", " ").replace("**", "")
    if t.count("-") >= 2:                       # "lighthouse-lamp-room"
        t = t.replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip(" \"'`*[]{}.,:;!?")
    t = t.lstrip(")").rstrip("(").strip()
    words = t.split()                           # a cap cut mid-item: "Platform at"
    while words and words[-1].lower().strip(".,") in _TRAILING_LINKS:
        words.pop()
    t = " ".join(words)
    if t.count("(") > t.count(")"):             # a comma split a parenthesis:
        t = t + ")" * (t.count("(") - t.count(")"))   # close it (it is a cut point)
    elif t.count(")") > t.count("("):
        t = " ".join(t.replace(")", " ").split())
    return t


def _person_hits(low_words) -> list:
    """Indexes of words that put a person (or a sound) into the tag."""
    if any(w in _TRACE_WORDS for w in low_words):
        return [i for i, w in enumerate(low_words) if w in _PRONOUNS]
    return [i for i, w in enumerate(low_words) if w in _PERSON_WORDS or w in _PRONOUNS]


def _cut_before(words, hit: int):
    """
    Keep the head of a tag up to the clause that brings in a person: "Steam
    rising from train engine | behind them", "Magical mist swirling near
    floor | as students pass through", "Empty platform | (nobody visible".
    Needs a cut point (a linking word, or an opening parenthesis) and at least
    two words left; otherwise None.
    """
    for i in range(hit, 0, -1):
        w = words[i]
        if w.lower().strip(".,") in _CUT_AT or w.startswith("("):
            head = words[:i]
            while head and head[-1].lower().strip(".,") in _TRAILING_LINKS:
                head.pop()
            return head if len(head) >= 2 else None
    return None


def _name_tokens(names) -> list:
    titles = {"miss", "mr", "mrs", "ms", "dr", "detective", "professor", "captain",
              "lord", "lady", "sir", "madam", "master"}
    out = set()
    for n in names or []:
        for w in _WORD.findall(n or ""):
            # removesuffix, NOT rstrip("'s"): rstrip strips every trailing
            # "s" and "'" - "Vess" became "Ve", and "behind Vess" shipped
            # in 2 of 20 prompts before reading caught it.
            w = w.lower().removesuffix("'s")
            if len(w) >= 3 and w not in titles:
                out.add(w)
    return sorted(out)


def _is_name(word: str, tokens) -> bool:
    # "Kael—a vast cathedral": a dash glued to the name hides it
    w = re.split(r"[—–-]", word.strip(".,'\"&()"))[0].lower()
    if w.endswith("'s"):
        w = w[:-2]
    if w in tokens:
        return True
    # A misspelt lead ("Draconi" for Dracona): capitalised, same first five
    # letters, length within one. Known cost: "Pottery" would match "Potter".
    return word[:1].isupper() and any(len(t) >= 5 and w[:5] == t[:5]
                                      and abs(len(w) - len(t)) <= 1 for t in tokens)


def scene_hygiene(tags, names=(), example: str = "", source: str = ""):
    """
    (kept, dropped) - kept tags in order, dropped as (tag, reason). Names are
    CUT out of a tag (the rest is kept: "Gothic cathedral looming behind Kaya &
    Bobb" -> "Gothic cathedral looming"); a person, a body part, a pronoun or a
    sound DROPS the tag; so does a tag only the demonstration line could have
    supplied; repeats are dropped.
    """
    tokens = _name_tokens(names)
    src = {w.lower() for w in _WORD.findall(source or "")}
    demo = {w.lower() for w in _WORD.findall(example or "")} - src
    kept, dropped, seen = [], [], set()
    for raw in tags:
        tag = _norm_tag(raw)
        if not tag:
            continue
        if any(m in tag.lower() for m in _META_PHRASES):
            dropped.append((tag, "meta"))
            continue
        words = _WORD.findall(tag)
        split = tag.split()
        name_at = [i for i, w in enumerate(split) if tokens and _is_name(w, tokens)]
        head = _cut_before(split, name_at[0]) if name_at else None
        if head is not None:                     # "...still visible on cobblestone
            dropped.append((tag, "name cut"))    #  | where Kaya had been skipping"
            tag, words = " ".join(head), _WORD.findall(" ".join(head))
        elif name_at:
            pieces = [w for w in split if not _is_name(w, tokens)]
            while pieces and pieces[-1].lower().strip(".,") in _TRAILING_LINKS:
                pieces.pop()
            while pieces and pieces[0].lower().strip(".,") in ("&", "and"):
                pieces.pop(0)
            new = " ".join(pieces).strip(" ,&")
            # What a name leaves behind can be only the name's action
            # ("Draconi standing alone" -> "standing alone"): not a scene.
            lead = new.split()[0].lower() if new else ""
            if new and len(new.split()) <= 3 and lead.endswith(("ing", "ed")):
                new = ""
            dropped.append((tag, "name cut" if new else "name"))
            if not new:
                continue
            tag, words = new, _WORD.findall(new)
        for kind, hits_of in (("person", _person_hits),
                              ("sound", lambda lw: [i for i, w in enumerate(lw)
                                                    if w in _SOUND_WORDS])):
            split = tag.split()
            low_split = [w.lower().strip(".,()'\"").removesuffix("'s") for w in split]
            hits = hits_of(low_split)
            if not hits:
                continue
            head = _cut_before(split, hits[0])
            if head is None:
                dropped.append((tag, kind))
                tag = ""
                break
            dropped.append((tag, f"{kind} cut"))
            tag = " ".join(head)
        if not tag:
            continue
        words = _WORD.findall(tag)
        low = [w.lower().removesuffix("'s") for w in words]
        # A demonstration echo: at least half the tag's content words come
        # from the demo line and none from the story ("brass fixtures" alone
        # is not enough - one shared word is ordinary vocabulary).
        content = [w for w in low if len(w) >= 4 and w not in _STOP]
        n_demo = sum(1 for w in content if w in demo)
        if content and n_demo * 2 >= len(content) and n_demo >= 1 \
                and not any(w in src for w in content):
            dropped.append((tag, "demo echo"))
            continue
        key = " ".join(low)
        if key in seen:
            dropped.append((tag, "repeat"))
            continue
        seen.add(key)
        kept.append(tag)
    return kept, dropped


def backdrop_from_layers(layers: dict, names=(), example: str = "", source: str = "",
                         n_place: int = 4, n_light: int = 2) -> str:
    """v12.4: a portrait's backdrop from the scene painter's layers - the
    first few clean PLACE tags and LIGHT tags ("tropical beach, palm trees,
    turquoise sea, white sand, sunset, warm light")."""
    out, seen = [], []
    for layer, n in (("place", n_place), ("light", n_light)):
        tags = [t for t in re.split(r"\s*[,;|]\s*", layers.get(layer, "") or "") if t.strip()]
        kept, _d = scene_hygiene(tags, names, example, source)
        added = 0
        for t in kept:
            # "Sunlight: bright midday sun" -> the value; a repeat of an
            # earlier tag ("Platform 9 3/4" in place AND light) -> skipped
            t = re.sub(r"^[A-Za-z ]{1,20}:\s*", "", t).strip()
            low = t.lower()
            if not t or len(t.split()) > 6 or any(low in x or x in low for x in seen):
                continue
            out.append(t)
            seen.append(low)
            added += 1
            if added >= n:
                break
    return ", ".join(out)


def build_scene_prompt(layers: dict, names=(), example: str = "", source: str = "",
                       settings: dict = None, order=("place", "things", "light")) -> dict:
    """
    v12.1: the scene image's full text. Body = PLACE, then OBJECTS AND
    EFFECTS, then LIGHT (layer order = importance: the first CLIP section
    steers the pooled vector), each through scene_hygiene, wrapped in the
    scene's prompt settings. Returns {positive, negative, body, dropped}.
    """
    tags = []
    for layer in order:
        tags += [t for t in re.split(r"\s*[,;|]\s*", layers.get(layer, "") or "") if t.strip()]
    kept, dropped = scene_hygiene(tags, names, example, source)
    # Long is good on this checkpoint (the user's observation, and ComfyUI
    # concatenates 77-token sections), but not unbounded: past ~180 words the
    # tail is the light layer repeating itself.
    budget, body_tags = SCENE_BODY_MAX_WORDS, []
    for t in kept:
        n = len(t.split())
        if n > budget:
            dropped.append((t, "over length"))
            continue
        body_tags.append(t)
        budget -= n
    body = join_prompt(*body_tags)
    positive, negative = wrap_prompt("scene", body, settings)
    return {"positive": positive, "negative": negative, "body": body,
            "dropped": dropped}

# =============================================================================
#  SECTION 1d - v12.3 CINEMATIC SCENES  (both leads drawn in the scene)
#
#  The engine's cinematographer writes four tag lines per character (looks,
#  wearing, doing) and one for the scene (others); this section cleans them
#  and writes the Anima prompt. Measured layout (loop_reports/v12_3_cinematic/
#  grid1): one prompt, a count line, the place, then ONE SENTENCE PER
#  CHARACTER that starts with where they stand and their name, then the extras.
#  The user's BREAK-paragraph layout put Harry's scar on Dracona in 4 of 4
#  pictures; NovaFurry (SDXL) tripled or fused the pair on the same text; the
#  core ComfyUI "latent couple" (masked conditioning) dropped one character.
# =============================================================================

_CLOTHING_WORDS = frozenset("""
robe robes coat coats jacket jackets dress dresses gown gowns shirt shirts
blouse tie ties uniform uniforms hat hats cap cloak cloaks cape capes boot boots
shoe shoes sandals trousers pants jeans skirt skirts apron suit suits tuxedo
armor armour scarf scarves glove gloves vest waistcoat sweater cardigan hoodie
jumpsuit overalls bikini swimsuit trunks veil corset stockings socks belt
clothes clothing outfit attire garb collar sleeves sleeve
badge brooch crest emblem pin
ribbon headband hairband hairpin tiara crown necklace earrings helmet goggles
mask sunglasses
slacks shorts leggings tunic kimono sari hood hoodie overcoat parka blazer
pyjamas pajamas nightgown nightdress lingerie bra underwear toga sash shawl
poncho raincoat trenchcoat coverall coveralls spacesuit wetsuit harness holster
sneakers trainers loafers slippers heels mittens beanie bonnet turban frock
pinafore leotard bodysuit jumper pullover top tank tee chemise petticoat bodice
breeches doublet jerkin swimwear beachwear sleepwear chainmail fatigues
""".split())


# =============================================================================
#  v12.4 - CLOTHES FROM THE PLAYER'S WORDS
#
#  The cinematographer's WEARING answer missed the clothes the player had
#  just asked for in half the user's Cinematic game (2026-10-18; replayed in
#  loop_reports/v12_4_portraits/probe_wearing3: "They put on a spacesuit" ->
#  Dracona kept her swimsuit 5/5, Harry went back to "Gryffindor robes" 5/5,
#  and again after "The two get more luxurious space suits" - the model knows
#  Harry Potter, and its prior beats the event). The player's sentence says
#  what changed and on whom, so it is read here, in code, and used when the
#  model's answer names none of those garments.
# =============================================================================

# Garments only: the WEARING list also has accessories and words that are
# something else in a story sentence ("tie up", "on top", "asteroid belt").
_GARMENTS = _CLOTHING_WORDS - frozenset("""tie ties badge brooch crest emblem pin
    ribbon headband hairband hairpin tiara crown necklace earrings collar sleeves
    sleeve belt harness holster top tank tee mask cap hood clothes clothing outfit
    attire garb""".split())
# Plural-only garments keep their -s; other plural heads become singular.
_PLURAL_ONLY = frozenset("""sunglasses glasses trousers pants jeans shorts overalls
    trunks leggings tights pyjamas pajamas coveralls slacks breeches fatigues goggles
    sneakers trainers""".split())
# Heads too generic to tell two garments apart alone: "space suit" vs "swimsuit".
_GENERIC_HEADS = frozenset("suit dress coat gown robe uniform jacket shirt".split())
_NP_BREAK = frozenset("""a an the their his her its my your our this that these
    those in into on onto with and or but now both all each they them he she him
    put puts putting wear wears wearing wore don dons change changes changed get
    gets got are is was were be been being of to for from at by more new also then
    still just as some two pair couple""".split())
_GIVE_VERBS = frozenset("""throw throws threw toss tosses tossed give gives gave hand
    hands handed offer offers offered lend lends lent pass passes passed bring brings
    brought""".split())
_REMOVE = re.compile(r"\b(?:off\s+(?:him|her|them|his|their)|(?:takes?|took|tears?|"
                     r"tore|rips?|ripped|burns?|burned|burnt)\s+(?:\w+\s+){0,4}off\b|"
                     r"removes?|removed|strips?|stripped|sheds?|shed)\b", re.IGNORECASE)
_BOTH_WORDS = frozenset("they them both everyone".split())
_BOTH_PHRASES = ("the two", "the pair", "the couple", "each of them", "both of them")


def _garment_word(w: str) -> bool:
    w = w.lower()
    return (w in _GARMENTS or (w.endswith("s") and w[:-1] in _GARMENTS)
            or w.endswith(("suit", "suits")) and len(w) > 5)


def _singular(w: str) -> str:
    """'suits' -> 'suit', 'dresses' -> 'dress'; 'dress', 'trunks' stay."""
    lw = w.lower()
    if lw in _PLURAL_ONLY or not lw.endswith("s"):
        return w
    if lw[:-1] in _GARMENTS or lw.endswith("suits"):
        return w[:-1]
    if lw.endswith("es") and lw[:-2] in _GARMENTS:
        return w[:-2]
    return w


def _garment_phrases(words) -> list:
    """The garments in one clause, each with the words describing it:
    'put on bulky orange pressure suits with helmets' -> ['bulky orange
    pressure suit', 'helmet']."""
    out = []
    for i, w in enumerate(words):
        if not _garment_word(w):
            continue
        j = i
        while j > 0 and i - j < 4 and words[j - 1].lower() not in _NP_BREAK \
                and not _garment_word(words[j - 1]):
            j -= 1
        phrase = words[j:i] + [_singular(w)]
        out.append(" ".join(x.lower() for x in phrase))
    return out


def garment_key(phrase: str) -> str:
    """What a WEARING line must contain to count as having this garment: the
    head, or modifier + head for a generic head ("spacesuit" vs "swimsuit")."""
    words = phrase.lower().split()
    if len(words) >= 2 and words[-1] in _GENERIC_HEADS:
        return words[-2] + words[-1]
    return words[-1]


def player_clothes(text: str, leads) -> dict:
    """
    {slot: [garment phrases]} that the player's text puts ON each lead.
    `leads` = [(slot, name, gender)]. Per clause (sentences, then commas):
    a giving verb with a pronoun or name gives to that person ("Vess throws
    him her spare grey mechanic overalls" -> him); otherwise the leads it
    names; "they / the two / both" -> both; he / she -> by gender; else the
    clause before it in the same sentence. A clause that takes clothes OFF
    ("burns the red company jacket off him") gives nothing.
    """
    out = {slot: [] for slot, _n, _g in leads}
    name_tokens = {slot: _name_tokens([name]) for slot, name, _g in leads}
    by_gender = {}
    for slot, _n, g in leads:
        by_gender.setdefault(g, []).append(slot)
    pron = {"him": "male", "he": "male", "his": "male", "her": "female", "she": "female"}
    for sentence in re.split(r"[.;!?:]+", text or ""):
        who_before = []
        for clause in sentence.split(","):
            words = re.findall(r"[A-Za-z][A-Za-z'-]*", clause)
            low = [w.lower() for w in words]
            if not words:
                continue
            who, give_at = [], None
            for k, w in enumerate(low):                      # giving: to whom
                if w in _GIVE_VERBS and k + 1 < len(low):
                    give_at = k
                    nxt = low[k + 1]
                    if nxt == "them":
                        who = [s for s, _n, _g in leads]
                    elif nxt in ("him", "her") and len(by_gender.get(pron[nxt], [])) == 1:
                        who = list(by_gender[pron[nxt]])
                    else:
                        who = [s for s in name_tokens if _is_name(words[k + 1], name_tokens[s])]
                    break
            if not who:
                who = [s for s in name_tokens
                       if any(_is_name(w, name_tokens[s]) for w in words)]
            if not who and (any(w in _BOTH_WORDS for w in low)
                            or any(p in " ".join(low) for p in _BOTH_PHRASES)):
                who = [s for s, _n, _g in leads]
            if not who:
                for w in low:
                    if w in ("he", "she") and len(by_gender.get(pron[w], [])) == 1:
                        who = list(by_gender[pron[w]])
                        break
            if not who:
                who = who_before
            who_before = who
            if _REMOVE.search(clause):
                continue
            if give_at is not None:
                # what is given goes to the receiver; what the giver wears
                # before the verb is theirs ("Hagrid arrives wearing a huge fur
                # coat and hands them thick fur cloaks" - the coat is Hagrid's)
                givers = [s for s in name_tokens
                          if any(_is_name(w, name_tokens[s]) for w in words[:give_at])]
                for slot in givers:
                    for g in _garment_phrases(words[:give_at]):
                        if g not in out[slot]:
                            out[slot].append(g)
                words = words[give_at + 1:]
            garments = _garment_phrases(words)
            for slot in who:
                for g in garments:
                    if g not in out[slot]:
                        out[slot].append(g)
    return out


def wearing_misses(wearing: str, garments) -> bool:
    """True when the WEARING line names none of the player's garments."""
    flat = re.sub(r"[\s-]+", "", (wearing or "").lower())
    return bool(garments) and not any(garment_key(g) in flat for g in garments)


def has_clothes(text: str) -> bool:
    """v12.3: does a WEARING line name any garment at all? (live game 2:
    "Kael Doran - Casual Encounter" came back as what Kael wears)"""
    return any(w.lower().removesuffix("'s") in _CLOTHING_WORDS
               or w.lower().rstrip("s") in _CLOTHING_WORDS
               for w in _WORD.findall(text or ""))
# NOT clothing words: "wearing round glasses" is how a face is described
# (the first live probe dropped Harry's glasses from his looks on "wearing").
# Inner labels ("Pose:", "Setting:") are the engine's to strip (_cine_text).
_NOBODY = ("nobody", "no one", "none", "noone", "no-one", "alone", "empty",
           "no others", "no other", "nothing", "n/a")
CINE_MAX_WORDS = {"looks": 25, "wearing": 25, "doing": 20, "others": 20,
                  "place": 30, "things": 20, "light": 15}
_NOUN_BY = {"female": ("woman", "girl"), "male": ("man", "boy"),
            "nonbinary": ("person", "other")}
_AGE_ADJ = {"YoungAdult": "young", "MiddleAged": "middle-aged", "Elder": "old"}
_COUNT_WORDS = {1: "one person", 2: "two people", 3: "three people", 4: "four people"}


_BODY_WORDS = frozenset("""
chest hair face hand hands arm arms shoulder shoulders lips mouth eyes head neck
cheek cheeks waist back hip hips knee knees fingers wrist chin forehead
""".split())
_OTHER_POSSESSIVE = {"male": "her", "female": "his"}
# words that make a WEARING item part of the face, not the clothes
_LOOKS_ONLY = frozenset("hair eyes eye face skin complexion scar scars freckles "
                        "beard stubble".split())


def cine_hygiene(field: str, text: str, lead_names=(), example: str = "",
                 source: str = "", own_name: str = "", own_gender: str = "") -> tuple:
    """
    (clean tag line, dropped [(tag, reason)]) for one cinematographer field.
      looks    clothing items dropped (clothes live in `wearing`)
      others   any item naming a lead dropped (they are not "others"); a
               "nobody" answer becomes ""
      doing    an item that STARTS with another lead's name is about them,
               not about `own_name` ("Dracona stands frozen mid-breath" came
               back as Harry's pose in the first live probe) - dropped; so is
               one with the other gender's possessive on a body part ("Hand
               flies up to touch her chest" as Harry's, live game 1), and a
               spoken line (a quote, or a "?"/"!" ending) - speech is not a pose
      all      an item that is only a name (a "**Dracona Malfoid**" header
               line) dropped; the demonstration's own words dropped (an item
               whose content words come more than half from the demo and
               none from the story); repeats dropped; capped at
               CINE_MAX_WORDS[field]
    Names are NOT cut from inside looks/wearing/doing: the prompt names every
    character, so "glaring at Harry" is a coherent instruction to Anima -
    and measured harmless (h2/: no more leaks, and the pair face each other).
    """
    dropped, kept, seen = [], [], set()
    tokens = _name_tokens(lead_names)
    own_tokens = _name_tokens([own_name]) if own_name else []
    any_tokens = sorted(set(tokens) | set(own_tokens))
    src = {w.lower() for w in _WORD.findall(source or "")}
    demo = {w.lower() for w in _WORD.findall(example or "")} - src
    # v12.4: the RP dialect sometimes quotes its WHOLE answer ('"Swimsuit -
    # black with silver accents..., sunglasses perched atop nose bridge"',
    # the user's Cinematic game, 2026-10-18 r2): the opening quote stuck to
    # the first item and the closing one to the last, both were dropped as
    # speech, and Dracona's portrait kept her school robes. One pair of
    # quotes around everything is a wrapper, not a spoken line.
    stripped = (text or "").strip()
    if (len(stripped) > 1 and stripped[0] in "\"\u201c" and stripped[-1] in "\"\u201d"
            and not re.search(r"[\"\u201c\u201d]", stripped[1:-1])):
        text = stripped[1:-1]
    low_all = " ".join((text or "").lower().split()).strip(" .,")
    if field == "others" and (low_all in _NOBODY
                              or any(low_all.startswith(n + w) for n in _NOBODY
                                     for w in (" ", ",", ".", " -"))):
        return "", [(text, "nobody")] if text else []
    for raw in re.split(r"\s*[,;|]\s*", text or ""):
        tag = _norm_tag(raw)
        if not tag or any(m in tag.lower() for m in _META_PHRASES):
            if tag:
                dropped.append((tag, "meta"))
            continue
        # speech is never a tag - in any field (probe_wearing: the model now
        # and then continues the transcript: '"Doesn't it?" *Kael's voice...')
        if re.search(r"[\"“”]", raw) or raw.strip().endswith(("?", "!")):
            dropped.append((tag, "speech"))
            continue
        words = [w.lower().removesuffix("'s") for w in _WORD.findall(tag)]
        poss = _OTHER_POSSESSIVE.get(own_gender)
        if field == "doing" and poss and any(
                a == poss and b in _BODY_WORDS for a, b in zip(words, words[1:])):
            dropped.append((tag, "other lead"))
            continue
        if any_tokens and tag.split() and all(_is_name(w, any_tokens) for w in tag.split()):
            dropped.append((tag, "name only"))
            continue
        # "Dracona Malfoid Standing Tall Posture Rigid" (live game 1, r4):
        # the lead's own name as a prefix on every item - cut, keep the rest
        split = tag.split()
        n_own = 0
        while own_tokens and n_own < len(split) - 1 and _is_name(split[n_own], own_tokens):
            n_own += 1
        if n_own:
            tag = " ".join(split[n_own:])
            words = [w.lower().removesuffix("'s") for w in _WORD.findall(tag)]
        first = tag.split()[0] if tag.split() else ""
        if (field == "doing" and own_tokens and first and _is_name(first, tokens)
                and not _is_name(first, own_tokens)):
            dropped.append((tag, "other lead"))
            continue
        # "grey-streaked hair" as an item of what Vess is WEARING (live game 2)
        if field == "wearing" and any(w in _LOOKS_ONLY for w in words) \
                and not any(w in _CLOTHING_WORDS for w in words):
            dropped.append((tag, "not clothes"))
            continue
        if field == "looks" and any(w in _CLOTHING_WORDS for w in words):
            dropped.append((tag, "clothes"))
            continue
        if field == "others" and tokens and any(_is_name(w, tokens) for w in tag.split()):
            dropped.append((tag, "lead"))
            continue
        content = [w for w in words if len(w) >= 4 and w not in _STOP]
        n_demo = sum(1 for w in content if w in demo)
        # MORE than half (the scene tags' rule is "at least half"): clothes
        # share common words with the demo ("patched grey flight coat" has
        # two of four), and dropping real clothes is worse than keeping a
        # half-echo; "rubber boots" (2 of 2) still goes.
        if content and n_demo * 2 > len(content) \
                and not any(w in src for w in content):
            dropped.append((tag, "demo echo"))
            continue
        key = " ".join(words)
        if key in seen:
            dropped.append((tag, "repeat"))
            continue
        seen.add(key)
        kept.append(tag)
    budget, out = CINE_MAX_WORDS.get(field, 25), []
    for t in kept:
        n = len(t.split())
        if n > budget:
            dropped.append((t, "over length"))
            continue
        out.append(t)
        budget -= n
    return ", ".join(out), dropped


_CLOTHES_SIMILAR = 0.5


def clothes_changed(old: str, new: str) -> bool:
    """
    v12.3: did a lead change clothes? The WEARING field is re-written every
    round, and the model re-words what it carries over (live game 1: Harry
    "robes (burgundy and gold), round glasses, worn sneakers" -> "robes
    (burgundy and gold), round glasses"), so exact text re-rendered both
    portraits every round. Changed = the content words overlap less than
    half (Jaccard < 0.5); robes -> wedding dress is a change, a dropped
    pair of sneakers is not. No new clothes = no change.
    """
    def words(t):
        return {w.lower().removesuffix("s") for w in _WORD.findall(t or "")
                if len(w) >= 3 and w.lower() not in _STOP}
    a, b = words(old), words(new)
    if not b:
        return False
    if not a:
        return True
    return len(a & b) / len(a | b) < _CLOTHES_SIMILAR


def count_tags(genders) -> str:
    """'1girl, 1boy' / '2girls' / '1boy, 1other' - Danbooru subject counts."""
    n = {"girl": 0, "boy": 0, "other": 0}
    for g in genders:
        n[_NOUN_BY.get(g, ("person", "other"))[1]] += 1
    out = []
    for key, plural in (("girl", "girls"), ("boy", "boys"), ("other", "others")):
        if n[key]:
            out.append(f"1{key}" if n[key] == 1 else f"{n[key]}{plural}")
    return ", ".join(out)


def person_noun(gender: str, age_group: str) -> str:
    """'young woman', 'middle-aged man', 'old person'... with its article."""
    noun = _NOUN_BY.get(gender, ("person", "other"))[0]
    adj = _AGE_ADJ.get(age_group, "")
    phrase = f"{adj} {noun}".strip()
    return ("an " if phrase[:1] in "aeiou" else "a ") + phrase


def cine_character_sentence(c: dict) -> str:
    """'On the left is Dracona, a young woman with LOOKS, wearing WEARING; DOING.'"""
    s = f"On the {c.get('side', 'left')} is {c['name']}, " \
        f"{person_noun(c.get('gender', ''), c.get('age_group', ''))}"
    if c.get("looks"):
        s += f" with {c['looks']}"
    if c.get("wearing"):
        s += f", wearing {c['wearing']}"
    if c.get("doing"):
        s += f"; {c['doing']}"
    return s + "."


def build_cinematic_prompt(cast, layers: dict, others: str = "",
                           settings: dict = None) -> dict:
    """
    v12.3: the Cinematic scene's text. `cast` = [{name, gender, age_group,
    looks, wearing, doing, side}] (already cleaned), `layers` = the scene
    painter's {place, things, light} (cleaned). Returns {positive, negative,
    body}. Body layout, one line each:
        1girl, 1boy, two people
        <place>, <light>.
        On the left is A, a young woman with ..., wearing ...; <doing>.
        On the right is B, ...
        Around them: <things>.
        In the background: <others>.
    """
    lines = [join_prompt(count_tags([c.get("gender", "") for c in cast]),
                         _COUNT_WORDS.get(len(cast), ""))]
    where = join_prompt(layers.get("place", ""), layers.get("light", ""))
    if where:
        lines.append(where + ".")
    lines += [cine_character_sentence(c) for c in cast]
    if layers.get("things"):
        lines.append(f"Around them: {layers['things']}.")
    if others:
        lines.append(f"In the background: {others}.")
    body = "\n".join(lines)
    s = (settings or default_prompt_settings())["cinematic"]
    positive = "\n".join(p for p in (s["pos_prepend"].strip(" ,\n"), body,
                                     s["pos_postpend"].strip(" ,\n")) if p)
    negative = join_prompt(s["neg_prepend"], s["neg_postpend"])
    return {"positive": positive, "negative": negative, "body": body}


# v12.4 MEDIUM: the v12.3 study's NovaFurry method (S_plain) as it was -
# "2people, 1girl, 1boy, duo", then per character its Danbooru tag, looks,
# clothes now and what it is doing, then place, light and the background
# people. Measured (loop_reports/v12_4_medium, blind, 5 shots x 2 seeds):
# exactly two people 6/10 - a third person wanders in now and then. Tried
# and NOT kept: a "no third person" negative (6/10) and each character
# encoded on its own + ConditioningConcat (5/10); the user: "three people are
# even funnier" - it stays as it is.
_MEDIUM_TAG = {("female", "YoungAdult"): "1girl", ("female", "MiddleAged"): "1girl, mature female",
               ("female", "Elder"): "1girl, old woman", ("male", "YoungAdult"): "1boy",
               ("male", "MiddleAged"): "1boy, mature male", ("male", "Elder"): "1boy, old man"}
_PEOPLE_WORDS = {1: "solo", 2: "duo"}


def build_medium_prompt(cast, layers: dict, others: str = "", settings: dict = None) -> dict:
    """v12.4: the Medium scene's tags. `cast` / `layers` / `others` as for
    build_cinematic_prompt (the same cleaned cinematographer notes)."""
    genders = [c.get("gender", "") for c in cast]
    head = join_prompt(f"{len(cast)}people", count_tags(genders),
                       _PEOPLE_WORDS.get(len(cast), ""))
    chars = [join_prompt(_MEDIUM_TAG.get((c.get("gender", ""), c.get("age_group", "")),
                                         count_tags([c.get("gender", "")])),
                         c.get("looks", ""), c.get("wearing", ""), c.get("doing", ""))
             for c in cast]
    body = join_prompt(head, *chars, layers.get("place", ""), layers.get("light", ""), others)
    positive, negative = wrap_prompt("medium", body, settings)
    return {"positive": positive, "negative": negative, "body": body}


def build_cine_portrait_prompt(char, looks: str, wearing: str, place: str = "",
                               light: str = "", mood_hint: str = "",
                               settings: dict = None) -> dict:
    """
    v12.3: a Cinematic portrait (Anima): the lead as the story has them now,
    in front of where they are now. Body, one line each:
        1girl, solo, portrait, upper body, looking at viewer
        Dracona, a young woman with LOOKS, wearing WEARING; MOOD.
        Behind: PLACE, LIGHT.
    Returns {positive, negative, body} (kind "cine_portrait" settings).
    """
    gender, age = getattr(char, "gender", ""), getattr(char, "age_group", "")
    line = f"{char.name}, {person_noun(gender, age)}"
    if looks:
        line += f" with {looks}"
    if wearing:
        line += f", wearing {wearing}"
    if mood_hint:
        line += f"; {mood_hint}"
    lines = [join_prompt(count_tags([gender]), "solo, portrait, upper body, "
                                               "looking at viewer"), line + "."]
    behind = join_prompt(place, light)
    if behind:
        lines.append(f"Behind: {behind}.")
    body = "\n".join(lines)
    s = (settings or default_prompt_settings())["cine_portrait"]
    positive = "\n".join(p for p in (s["pos_prepend"].strip(" ,\n"), body,
                                     s["pos_postpend"].strip(" ,\n")) if p)
    return {"positive": positive, "body": body,
            "negative": join_prompt(s["neg_prepend"], s["neg_postpend"])}

# =============================================================================
#  SECTION 2 - WORKFLOW LOADING  (both ComfyUI save formats)
# =============================================================================

class WorkflowError(Exception):
    """The workflow file cannot be used as-is; the message says why."""


# Nodes that exist only in the ComfyUI editor. The server rejects a prompt
# that contains them, so they are folded away during conversion.
_FRONTEND_ONLY = {"Note", "MarkdownNote", "Reroute", "PrimitiveNode"}
# Value-holder nodes. PrimitiveInt & co. are real server nodes in current
# ComfyUI, but folding them into literals removes a dependency on the
# server's version AND lets parameterize() overwrite a seed or a size that
# the editor had routed through one (the portrait workflow does exactly that).
_PRIMITIVES = {"PrimitiveNode", "PrimitiveInt", "PrimitiveFloat",
               "PrimitiveString", "PrimitiveStringMultiline", "PrimitiveBoolean"}
# The editor saves a "control after generate" setting straight after every
# seed-like INT widget (widgets_values [seed, "randomize", steps, ...]). It is
# not an input of the node and must be skipped.
_CONTROL_VALUES = {"fixed", "increment", "decrement", "randomize"}
# Widget order for common nodes, for UI files written by older editors that
# do not list widget inputs in node["inputs"].
_KNOWN_WIDGETS = {
    "CheckpointLoaderSimple": ["ckpt_name"],
    "EmptyLatentImage":       ["width", "height", "batch_size"],
    "CLIPTextEncode":         ["text"],
    "CLIPSetLastLayer":       ["stop_at_clip_layer"],
    "LoraLoader":             ["lora_name", "strength_model", "strength_clip"],
    "KSampler":               ["seed", "steps", "cfg", "sampler_name",
                               "scheduler", "denoise"],
    "KSamplerAdvanced":       ["add_noise", "noise_seed", "steps", "cfg",
                               "sampler_name", "scheduler", "start_at_step",
                               "end_at_step", "return_with_leftover_noise"],
    "VAEDecode":              [],
    "VAEDecodeTiled":         ["tile_size", "overlap", "temporal_size",
                               "temporal_overlap"],
    "SaveImage":              ["filename_prefix"],
    "PrimitiveInt":           ["value"],
    "PrimitiveFloat":         ["value"],
    "PrimitiveString":        ["value"],
    "PrimitiveStringMultiline": ["value"],
    "PrimitiveBoolean":       ["value"],
    "PrimitiveNode":          ["value"],
}
_OUTPUT_TYPES = {"SaveImage", "PreviewImage"}

_workflow_cache = {}   # path -> (mtime, api dict)


def is_ui_format(data) -> bool:
    return isinstance(data, dict) and isinstance(data.get("nodes"), list)


def _widget_values(node: dict) -> dict:
    """{widget name: saved value} for one UI-format node."""
    saved = node.get("widgets_values")
    if isinstance(saved, dict):                     # some custom nodes save a dict
        return dict(saved)
    values = list(saved or [])
    names = [i["widget"]["name"] for i in node.get("inputs", [])
             if isinstance(i, dict) and i.get("widget")]
    known = _KNOWN_WIDGETS.get(node.get("type"), [])
    if len(known) > len(names):                     # older editor: only converted
        names = known                               # widgets were listed
    out, pos = {}, 0
    for name in names:
        if pos >= len(values):
            break
        value = values[pos]
        pos += 1
        out[name] = value
        if (isinstance(value, int) and not isinstance(value, bool)
                and pos < len(values) and values[pos] in _CONTROL_VALUES):
            pos += 1                                # skip "control after generate"
    return out


def convert_ui_to_api(ui: dict) -> dict:
    """
    Convert an editor-format workflow to the API format /prompt accepts.
    Muted nodes (mode 2) are dropped; bypassed nodes (mode 4) pass their
    first input of the matching type through; Reroutes are followed;
    primitives become literal values. Only nodes an output node depends on
    are kept, so stray editor nodes cannot fail validation.
    """
    nodes = {n["id"]: n for n in ui.get("nodes", [])}
    links = {}
    for link in ui.get("links", []):
        if isinstance(link, dict):
            links[link["id"]] = (link["origin_id"], link["origin_slot"])
        else:                                       # [id, src, slot, dst, slot, type]
            links[link[0]] = (link[1], link[2])

    def resolve(src_id, slot, depth=0):
        """('link', [id, slot]) or ('value', literal) for one upstream end."""
        if depth > 32:
            raise WorkflowError("link cycle while resolving the workflow")
        node = nodes.get(src_id)
        if node is None:
            raise WorkflowError(f"link points at missing node {src_id}")
        kind = node.get("type", "")
        if kind in _PRIMITIVES:
            vals = _widget_values(node)
            if "value" in vals:
                return "value", vals["value"]
            saved = node.get("widgets_values") or [None]
            return "value", saved[0] if isinstance(saved, list) else None
        if kind == "Reroute" or node.get("mode") == 4:
            want = None
            outs = node.get("outputs") or []
            if slot < len(outs):
                want = outs[slot].get("type")
            for inp in node.get("inputs", []):
                if inp.get("link") is None:
                    continue
                if kind == "Reroute" or want in (None, "*", inp.get("type")):
                    s, sl = links[inp["link"]]
                    return resolve(s, sl, depth + 1)
            raise WorkflowError(f"{kind or 'bypassed node'} {src_id} has no "
                                f"input to pass through")
        return "link", [str(src_id), slot]

    api = {}
    for nid, node in nodes.items():
        kind = node.get("type", "")
        if (kind in _FRONTEND_ONLY or kind in _PRIMITIVES
                or node.get("mode") in (2, 4)):
            continue
        inputs = _widget_values(node)
        for inp in node.get("inputs", []):
            name = inp.get("name")
            if inp.get("link") is None or name is None:
                continue
            src, slot = links[inp["link"]]
            how, value = resolve(src, slot)
            inputs[name] = value                    # literal or [id, slot]
        api[str(nid)] = {"class_type": kind, "inputs": inputs,
                         "_meta": {"title": node.get("title") or kind}}
    return _prune_to_outputs(api)


def _prune_to_outputs(api: dict) -> dict:
    outputs = [nid for nid, n in api.items() if n["class_type"] in _OUTPUT_TYPES]
    if not outputs:
        raise WorkflowError("no SaveImage/PreviewImage node - nothing would be saved")
    keep, stack = set(), list(outputs)
    while stack:
        nid = stack.pop()
        if nid in keep or nid not in api:
            continue
        keep.add(nid)
        for value in api[nid]["inputs"].values():
            if _is_link(value):
                stack.append(value[0])
    return {nid: api[nid] for nid in api if nid in keep}


def _is_link(value) -> bool:
    return (isinstance(value, list) and len(value) == 2
            and isinstance(value[0], str) and isinstance(value[1], int))


def load_workflow(path: str) -> dict:
    """
    Read a workflow file (either format) -> API dict. Cached by mtime, so an
    edit saved from ComfyUI is picked up on the next job without a restart.
    Raises WorkflowError with a readable reason.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        raise WorkflowError(f"workflow file not found: {path}")
    cached = _workflow_cache.get(path)
    if cached and cached[0] == mtime:
        return copy.deepcopy(cached[1])
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise WorkflowError(f"{os.path.basename(path)} is not valid JSON ({e})")
    if is_ui_format(data):
        api = convert_ui_to_api(data)
    elif isinstance(data, dict) and data and all(
            isinstance(v, dict) and "class_type" in v for v in data.values()):
        api = _prune_to_outputs(data)
    else:
        raise WorkflowError(f"{os.path.basename(path)} is neither an API-format "
                            f"nor an editor-format ComfyUI workflow")
    find_roles(api)                                 # refuse it now, not per job
    _workflow_cache[path] = (mtime, api)
    return copy.deepcopy(api)

# =============================================================================
#  SECTION 3 - ROLES  (which node is the prompt, the seed, the size)
# =============================================================================

def _walk_to_text(api: dict, start, depth=0):
    """Follow a conditioning link upstream to the node holding the text."""
    if not _is_link(start) or depth > 12:
        return None
    nid = start[0]
    node = api.get(nid)
    if node is None:
        return None
    if isinstance(node["inputs"].get("text"), str):
        return nid
    for value in node["inputs"].values():
        if _is_link(value):
            found = _walk_to_text(api, value, depth + 1)
            if found:
                return found
    return None


def find_roles(api: dict) -> dict:
    """
    {sampler, seed_key, positive, negative, latent, save} node ids. positive
    is required (it is where the story's prompt goes); the rest are optional
    and simply not set when absent. Raises WorkflowError.
    """
    sampler = seed_key = None
    for nid, node in api.items():
        ins = node["inputs"]
        if _is_link(ins.get("positive")) and _is_link(ins.get("negative")):
            sampler = nid
            seed_key = next((k for k in ("seed", "noise_seed") if k in ins), None)
            break
    if sampler is None:
        raise WorkflowError("no sampler with positive/negative inputs found")
    ins = api[sampler]["inputs"]
    positive = _walk_to_text(api, ins.get("positive"))
    if positive is None:
        raise WorkflowError("the sampler's positive input does not lead to a "
                            "text prompt node")
    negative = _walk_to_text(api, ins.get("negative"))
    latent = None
    if _is_link(ins.get("latent_image")):
        cand = ins["latent_image"][0]
        if {"width", "height"} <= set(api.get(cand, {}).get("inputs", {})):
            latent = cand
    save = [nid for nid, n in api.items() if n["class_type"] == "SaveImage"]
    return {"sampler": sampler, "seed_key": seed_key, "positive": positive,
            "negative": negative, "latent": latent, "save": save}


def parameterize(api: dict, positive: str, seed: int = None,
                 prefix: str = "storylab", negative: str = None) -> tuple:
    """
    A filled-in COPY of the workflow and the seed it will use. negative=None
    keeps the workflow's own negative text (v12.0 behaviour); a string
    replaces it (v12.1 prompt settings - whose default negative prepend IS
    the workflow's own text).
    """
    wf = copy.deepcopy(api)
    roles = find_roles(wf)
    wf[roles["positive"]]["inputs"]["text"] = positive
    if negative is not None and roles["negative"]:
        wf[roles["negative"]]["inputs"]["text"] = negative
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
    if roles["seed_key"]:
        wf[roles["sampler"]]["inputs"][roles["seed_key"]] = seed
    for nid in roles["save"]:
        wf[nid]["inputs"]["filename_prefix"] = prefix
    return wf, seed


def workflow_summary(path: str) -> str:
    """One line for the setup screen / drawer: checkpoint, size, steps."""
    try:
        api = load_workflow(path)
        roles = find_roles(api)
    except WorkflowError as e:
        return f"unusable: {e}"
    ckpt = next((n["inputs"].get(k) for n in api.values()
                 for k in ("ckpt_name", "unet_name") if k in n["inputs"]), "?")
    size = ""
    if roles["latent"]:
        li = api[roles["latent"]]["inputs"]
        size = f"{li.get('width')}x{li.get('height')}"
    steps = api[roles["sampler"]]["inputs"].get("steps", "?")
    return f"{os.path.basename(path)}: {ckpt}, {size}, {steps} steps"

# =============================================================================
#  SECTION 4 - THE SERVER  (find, launch, free VRAM)
# =============================================================================

_launched = {"proc": None, "log": None}   # a server THIS module started


def find_comfyui_port(ports=None):
    for port in ports or COMFYUI_PORTS:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/system_stats", timeout=1)
            if r.status_code == 200 and "system" in r.json():
                return port
        except Exception:
            pass
    return None


PATHS_FILE = os.path.join(_SCRIPT_DIR, "storylab_paths.json")


def read_install_paths() -> dict:
    """v12.3: what Story Lab Setup installed and where (storylab_paths.json,
    written by installer/setup_core.py). {} in a source checkout."""
    try:
        with open(PATHS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def available_styles() -> dict:
    """{"classical": bool, "cinematic": bool, "music": bool} - the picture
    styles (and, v12.4, the music) Setup installed. Without a paths file (a
    developer's source checkout, which finds its ComfyUI the v12.2 way)
    everything is offered. A paths file from Setup 12.3 has no "music" key:
    music is off there until Setup 12.4 installs it."""
    data = read_install_paths()
    if not data:
        # an installed copy (setup\ beside the game) whose Setup has not
        # finished: nothing is installed yet. A source checkout: both.
        installed = os.path.isfile(os.path.join(_SCRIPT_DIR, "setup", "setup_core.py"))
        return {"classical": not installed, "cinematic": not installed,
                "music": not installed}
    styles = data.get("styles") or {}
    return {k: bool(styles.get(k)) for k in ("classical", "cinematic", "music")}


def _configured_install():
    """The ComfyUI Setup chose (storylab_paths.json) if its files still exist:
    {kind, python, main, base, extra_model_paths}, else None."""
    c = read_install_paths().get("comfyui") or {}
    if c.get("python") and os.path.isfile(c["python"]) and os.path.isfile(c.get("main", "")):
        return c
    return None


def _desktop2_install():
    """
    v12.3: (python, main.py, base_dir, extra_paths_yaml) for the NEW "Comfy
    Desktop" app (%APPDATA%\\Comfy Desktop\\installations.json), or None. On
    this machine it adopted the old Desktop install in place: same venv and
    base directory, but newer server code (ComfyUI 0.30 vs 0.5) under
    %LOCALAPPDATA%\\Comfy-Desktop\\ComfyUI-Installs, and a per-instance model
    paths file that adds ComfyUI-Shared\\models (where the Anima files are).
    The old 0.5 server cannot load Anima at all (no "anima" model type).
    """
    appdata = os.environ.get("APPDATA", "")
    root = os.path.join(appdata, "Comfy Desktop")
    try:
        with open(os.path.join(root, "installations.json"), encoding="utf-8") as f:
            insts = json.load(f)
    except Exception:
        return None
    for inst in insts if isinstance(insts, list) else []:
        path = inst.get("installPath")
        if not path or inst.get("status") != "installed":
            continue
        main = os.path.join(path, "ComfyUI", "main.py")
        base = inst.get("adoptedBaseDir") or path
        py = inst.get("adoptedPythonPath") or os.path.join(path, ".venv", "Scripts",
                                                            "python.exe")
        extra = os.path.join(root, "instance-model-paths", f"{inst.get('id')}.yaml")
        if os.path.isfile(py) and os.path.isfile(main):
            return py, main, base, extra if os.path.isfile(extra) else None
    return None


def _desktop_install():
    """
    (python, main.py, base_dir, extra_paths_yaml) for ComfyUI Desktop, read
    from the app's own config, or None. The Desktop app keeps its venv in the
    base directory and the server code inside the program folder.
    v12.3: the new Comfy Desktop app is preferred when it is installed.
    """
    new = _desktop2_install()
    if new:
        return new
    appdata = os.environ.get("APPDATA", "")
    local = os.environ.get("LOCALAPPDATA", "")
    try:
        with open(os.path.join(appdata, "ComfyUI", "config.json"), encoding="utf-8") as f:
            base = json.load(f).get("basePath")
    except Exception:
        base = None
    if not base:
        return None
    py = os.path.join(base, ".venv", "Scripts", "python.exe")
    main = os.path.join(local, "Programs", "ComfyUI", "resources", "ComfyUI", "main.py")
    extra = os.path.join(appdata, "ComfyUI", "extra_models_config.yaml")
    if os.path.isfile(py) and os.path.isfile(main):
        return py, main, base, extra if os.path.isfile(extra) else None
    return None


def _portable_install():
    """(python_embeded, main.py) for a portable install in a usual place."""
    home = os.path.expanduser("~")
    own = os.path.join(_SCRIPT_DIR, "ComfyUI_windows_portable")      # v12.3: Setup's copy
    py, main = (os.path.join(own, "python_embeded", "python.exe"),
                os.path.join(own, "ComfyUI", "main.py"))
    if os.path.isfile(py) and os.path.isfile(main):
        return py, main
    for root in (home, os.path.join(home, "Desktop"), os.path.join(home, "Downloads"),
                 "C:\\", "D:\\"):
        for name in ("ComfyUI_windows_portable", "ComfyUI_portable", "ComfyUI"):
            d = os.path.join(root, name)
            py = os.path.join(d, "python_embeded", "python.exe")
            main = os.path.join(d, "ComfyUI", "main.py")
            if os.path.isfile(py) and os.path.isfile(main):
                return py, main
    return None


def launch_comfyui(log_path: str = None, port: int = LAUNCH_PORT):
    """
    Start a ComfyUI backend headless (no window, no browser tab). Prefers the
    ComfyUI Story Lab Setup chose (storylab_paths.json, v12.3), then the
    Desktop install, then a portable one. Returns the Popen or None.
    """
    env = {k: v for k, v in os.environ.items() if k.upper() != "SSLKEYLOGFILE"}
    conf = _configured_install()                 # v12.3: what Setup installed
    desk = None if conf else _desktop_install()
    if conf and conf.get("kind") == "portable":
        py, main = conf["python"], conf["main"]
        args = [py, "-s", main, "--windows-standalone-build"]
        cwd = conf.get("base") or os.path.dirname(os.path.dirname(main))
    elif conf:                                   # an existing Desktop install
        py, main, base = conf["python"], conf["main"], conf["base"]
        args = [py, "-s", main, "--base-directory", base,
                "--user-directory", os.path.join(base, "user"),
                "--input-directory", os.path.join(base, "input"),
                "--output-directory", os.path.join(base, "output")]
        if conf.get("extra_model_paths") and os.path.isfile(conf["extra_model_paths"]):
            args += ["--extra-model-paths-config", conf["extra_model_paths"]]
        cwd = base
    elif desk:
        py, main, base, extra = desk
        args = [py, "-s", main, "--base-directory", base,
                "--user-directory", os.path.join(base, "user"),
                "--input-directory", os.path.join(base, "input"),
                "--output-directory", os.path.join(base, "output")]
        if extra:
            args += ["--extra-model-paths-config", extra]
        cwd = base
    else:
        port_inst = _portable_install()
        if not port_inst:
            print("  ComfyUI not found (no Desktop config, no portable install).",
                  flush=True)
            return None
        py, main = port_inst
        args = [py, "-s", main, "--windows-standalone-build"]
        cwd = os.path.dirname(os.path.dirname(main))
    args += ["--listen", "127.0.0.1", "--port", str(port), "--disable-auto-launch"]
    log_path = log_path or os.path.join(_SCRIPT_DIR, "runSaves", "comfyui_server.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "w", encoding="utf-8")
    kwargs = {"cwd": cwd, "stdout": log, "stderr": subprocess.STDOUT,
              "stdin": subprocess.DEVNULL, "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(args, **kwargs)
    except Exception as e:
        print(f"  \u2717 ComfyUI launch failed: {e}", flush=True)
        log.close()
        return None
    _launched["proc"], _launched["log"] = proc, log
    print(f"  ComfyUI launching on {port} (log: {log_path})", flush=True)
    return proc


def ensure_comfyui(auto_launch: bool = True, timeout: int = 120,
                   log_path: str = None, status=None):
    """
    Server URL ("http://127.0.0.1:8188"), or None when images are off for the
    session. `status` is an optional callback(text) for the GUI.
    """
    port = find_comfyui_port()
    if port is None and auto_launch:
        if status:
            status("starting ComfyUI (first start ~15-30 s)...")
        proc = launch_comfyui(log_path)
        deadline = time.time() + timeout
        while proc is not None and time.time() < deadline:
            if proc.poll() is not None:
                print(f"  \u2717 ComfyUI exited at startup (code {proc.returncode})"
                      f" - see its log", flush=True)
                break
            port = find_comfyui_port([LAUNCH_PORT])
            if port:
                break
            time.sleep(1)
    if port is None:
        print("  ComfyUI unavailable - running without images.", flush=True)
        return None
    print(f"  \u2713 ComfyUI on port {port}", flush=True)
    return f"http://127.0.0.1:{port}"


def shutdown_comfyui() -> None:
    """Stop the server only if this module started it."""
    proc = _launched.get("proc")
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    if _launched.get("log"):
        try:
            _launched["log"].close()
        except Exception:
            pass
    _launched["proc"] = _launched["log"] = None


# Loader inputs that name a file the server must have (class -> input name).
_LOADER_FILES = {"CheckpointLoaderSimple": "ckpt_name", "UNETLoader": "unet_name",
                 "CLIPLoader": "clip_name", "VAELoader": "vae_name",
                 "UpscaleModelLoader": "model_name", "LoraLoader": "lora_name",
                 "LoraLoaderModelOnly": "lora_name"}


def missing_models(server: str, workflow_file: str) -> list:
    """
    v12.3: what a workflow needs that this server cannot load - unknown node
    classes and model files not in the loader's list - as readable strings.
    [] = ready. Checked before a session picks the Cinematic workflow: the
    old ComfyUI 0.5 server answers an Anima job only with a failed render.
    """
    try:
        api = load_workflow(workflow_file)
    except WorkflowError as e:
        return [str(e)]
    _apply_anima_choice(api, workflow_file)      # the Anima file Setup installed
    missing, info = [], {}
    for node in api.values():
        cls = node["class_type"]
        if cls not in info:
            try:
                r = requests.get(f"{server}/object_info/{cls}", timeout=10)
                info[cls] = r.json().get(cls) if r.status_code == 200 else None
            except Exception:
                info[cls] = None
        if info[cls] is None:
            missing.append(f"node {cls}")
            continue
        key = _LOADER_FILES.get(cls)
        if key and isinstance(node["inputs"].get(key), str):
            spec = info[cls].get("input", {}).get("required", {}).get(key, [[]])
            options = spec[0] if spec and isinstance(spec[0], list) else []
            if node["inputs"][key] not in options:
                missing.append(f"{cls}: {node['inputs'][key]}")
    return sorted(set(missing))


def vram_used_mb(server: str):
    """What ComfyUI's torch holds on the GPU right now (MB), or None. NOTE:
    the new ComfyUI's dynamic VRAM is not counted here - use vram_free_mb."""
    try:
        dev = requests.get(f"{server}/system_stats", timeout=3).json()["devices"][0]
        return dev.get("torch_vram_total", 0) / 2**20
    except Exception:
        return None


def vram_free_mb(server: str):
    """(free, total) MB of the whole card as ComfyUI's device sees it, or None."""
    try:
        dev = requests.get(f"{server}/system_stats", timeout=3).json()["devices"][0]
        return dev["vram_free"] / 2**20, dev["vram_total"] / 2**20
    except Exception:
        return None


FREE_MARGIN_MB = 2000       # the desktop, browser and driver hold ~1-1.5 GB


def free_vram(server: str, wait: float = 15.0, margin_mb: float = FREE_MARGIN_MB) -> float:
    """
    Ask ComfyUI to unload its models and free its memory, and WAIT until the
    card really has the room back (free >= total - margin), or until the free
    memory stops rising (other programs may hold some). The server acts on
    the request between jobs (~1 s). Returns the seconds it took.
    """
    t0 = time.time()
    try:
        requests.post(f"{server}/free", json={"unload_models": True, "free_memory": True},
                      timeout=5)
    except Exception:
        return time.time() - t0
    last, steady_since = None, None
    while time.time() - t0 < wait:
        fm = vram_free_mb(server)
        if fm is None:
            break
        free, total = fm
        if free >= total - margin_mb:
            break
        if last is not None and abs(free - last) < 16:
            steady_since = steady_since or time.time()
            if time.time() - steady_since >= 1.5 and time.time() - t0 >= 2.0:
                break                                  # nothing more is coming
        else:
            steady_since = None
        last = free
        time.sleep(0.25)
    return time.time() - t0

# =============================================================================
#  SECTION 5 - SUBMISSION
# =============================================================================

def _submit(server: str, workflow: dict, label: str, dest: str, progress=None):
    """Queue, poll /history, download the first image to `dest`. Path or None."""
    try:
        r = requests.post(f"{server}/prompt",
                          json={"prompt": workflow, "client_id": str(uuid.uuid4())},
                          timeout=15)
    except Exception as e:
        print(f"  \u2717 Queue failed [{label}]: {e}", flush=True)
        return None
    if r.status_code != 200:
        # 400 carries node_errors - the one place a bad workflow explains itself
        print(f"  \u2717 ComfyUI refused [{label}]: {r.text[:400]}", flush=True)
        return None
    prompt_id = r.json().get("prompt_id")
    start = time.time()
    last = 0.0
    while True:
        elapsed = time.time() - start
        if elapsed > MAX_IMAGE_WAIT:
            print(f"  \u2717 Timed out after {MAX_IMAGE_WAIT}s [{label}]", flush=True)
            return None
        if progress and elapsed - last >= 1.0:
            progress(elapsed)
            last = elapsed
        try:
            hist = requests.get(f"{server}/history/{prompt_id}", timeout=5).json()
        except Exception:
            time.sleep(0.5)
            continue
        entry = hist.get(prompt_id)
        if not entry:
            time.sleep(0.5)
            continue
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
            detail = msgs[0][1].get("exception_message", "") if msgs else ""
            print(f"  \u2717 ComfyUI error [{label}]: {detail[:300]}", flush=True)
            return None
        for node_out in entry.get("outputs", {}).values():
            for meta in node_out.get("images", []):
                try:
                    data = requests.get(f"{server}/view", params=meta, timeout=30).content
                    with open(dest, "wb") as f:
                        f.write(data)
                except Exception as e:
                    print(f"  \u2717 Download failed [{label}]: {e}", flush=True)
                    return None
                return dest
        if status.get("completed"):
            print(f"  \u26a0 No image in output [{label}]", flush=True)
            return None
        time.sleep(0.5)


def _log_job(run_dir: str, kind: str, dest, seed: int, seconds: float,
             prompt: str) -> None:
    try:
        with open(os.path.join(run_dir, "images.txt"), "a", encoding="utf-8") as f:
            f.write(f"{kind}\t{os.path.basename(dest) if dest else 'FAILED'}\t"
                    f"seed={seed}\t{seconds:.1f}s\n  {prompt}\n")
    except Exception:
        pass


def _apply_anima_choice(wf: dict, workflow_file: str) -> None:
    """v12.3 Setup: a player without a CivitAI key gets the official Anima
    file instead of Marshmallow Milk Anima - storylab_paths.json names the
    one installed, and the Cinematic workflows load that (even if a later
    reinstall put the shipped JSON back)."""
    name = read_install_paths().get("anima_model") or ""
    if not name or os.path.basename(workflow_file) not in (
            os.path.basename(WORKFLOW_CINEMATIC_FILE), os.path.basename(WORKFLOW_CINE_PORTRAIT_FILE)):
        return
    for node in wf.values():
        if node.get("class_type") == "UNETLoader":
            node["inputs"]["unet_name"] = name


def generate_image(server: str, workflow_file: str, prompt: str, run_dir: str,
                   filename: str, kind: str, seed: int = None, progress=None,
                   negative: str = None):
    """
    One image from one workflow file. Returns (path or None, seed). A bad
    workflow file is reported and returns None - the session goes on.
    """
    try:
        wf, seed = parameterize(load_workflow(workflow_file), prompt, seed,
                                prefix=f"storylab_{kind.split()[0]}", negative=negative)
        _apply_anima_choice(wf, workflow_file)
    except WorkflowError as e:
        print(f"  \u2717 Workflow unusable [{kind}]: {e}", flush=True)
        return None, seed
    dest = os.path.join(run_dir, filename)
    t0 = time.time()
    path = _submit(server, wf, kind, dest, progress)
    _log_job(run_dir, kind, path, seed, time.time() - t0, prompt
             + (f"\n  NEGATIVE: {negative}" if negative is not None else ""))
    if path:
        print(f"  \u2713 {kind} -> {filename} in {time.time() - t0:.1f}s", flush=True)
    return path, seed


def generate_scene_image(server, prompt, round_num, run_dir, take=0,
                         progress=None, workflow_file=None, negative=None,
                         seed=None):
    """The round's wide image. take > 0 = a re-roll, kept beside the first."""
    name = (f"main_image_opening_{round_num:02d}.png" if not take
            else f"main_image_opening_{round_num:02d}_take{take + 1}.png")
    return generate_image(server, workflow_file or WORKFLOW_SCENE_FILE, prompt,
                          run_dir, name, f"scene r{round_num}", seed=seed,
                          progress=progress, negative=negative)


def generate_portrait_image(server, prompt, slot, interact_num, run_dir,
                            progress=None, workflow_file=None, negative=None,
                            seed=None):
    """slot 'a'/'b'. File names keep v5's char1/char2 for old-run continuity.
    seed: v12.2 game seed (None = a random one, as before)."""
    name = f"portrait_char{1 if slot == 'a' else 2}_interact{interact_num}.png"
    return generate_image(server, workflow_file or WORKFLOW_PORTRAIT_FILE, prompt,
                          run_dir, name, f"portrait {slot}", seed=seed,
                          progress=progress, negative=negative)
