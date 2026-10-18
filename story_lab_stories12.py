"""
story_lab_stories12.py  —  Story Lab v12  //  stories: built-in and saved

A STORY is everything the setup screen asks for before BEGIN: the world, what
already happened, both characters, and the story's own feel (narrator voice,
theme, turns, rounds). Session switches (voice, captions, pictures) are not
part of a story - they belong to the machine and the player, not the tale.

Three stories are BUILT IN and live in this file, so they cannot be lost or
overwritten:
  1. "Hogwarts — Dracona & Harry"  the user's own playthrough setup
     (2026-10-16), kept as written; only spelling was corrected.
  2. "Fayrun — Kaya & Bobb"  the user's fox-girl wizard, paladin, puppy and
     dragon (their Fayrun scenario), filled out by request (v12.4).
  3. "Kerchoff Station — Vess & Kael"  the long-time demo cast, rebuilt with
     a world that is falling, a debt, a clock and a secret.

The player's stories are saved as one JSON file each in stories/ beside this
file. Pure functions, no GUI: story_lab_gui12 calls them, test_engine12 tests
them, and director12's headless mode can start from any story by title.
"""

import os
import re
import copy
import json

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STORIES_DIR = os.path.join(_SCRIPT_DIR, "stories")

GENDERS = ("female", "male", "nonbinary")
AGES = ("YoungAdult", "MiddleAged", "Elder")
NARRATOR_GENDERS = ("Woman", "Man", "Random")
NARRATOR_ACCENTS = ("Rough (American)", "Posh (British)")
THEMES = ("Cyberpunk", "Fantasy")
TURNS = ("4", "6", "8")
ROUNDS = ("endless", "3", "5", "7")
CHAR_FIELDS = ("name", "gender", "age", "identity", "address", "description")

# =============================================================================
#  THE TWO BUILT-IN STORIES
# =============================================================================

HOGWARTS = {
    "title": "Hogwarts — Dracona & Harry",
    "world_desc": (
        "The magical school grounds of Hogwarts feature the wizards' school in the "
        "background as the Hogwarts Express steam train stands still, steaming, beside "
        "our two students. Other students rush past Dracona and Harry to the castle "
        "school while Dracona and Harry argue on the platform. The world is of a "
        "magical variety, where students study at the castle of Hogwarts and discover "
        "the mysteries within the world."),
    "prior_history": "",
    "char_a": {
        "name": "Dracona Malfoid", "gender": "female", "age": "YoungAdult",
        "identity": "", "address": "",
        "description": (
            "A smug, tall blonde girl with blue eyes who wants to get sorted into "
            "Slytherin. She is confident and arrogant that she will become the best "
            "student at Hogwarts, but is interested in the famous boy Harry Potter and "
            "what secrets he may have about his family. Dracona currently wears first "
            "year student robes. She is uptight about not getting her way, but "
            "something deep might be making her insecure."),
    },
    "char_b": {
        "name": "Harry Potter", "gender": "male", "age": "YoungAdult",
        "identity": "", "address": "",
        "description": (
            "A timid and currently overwhelmed boy who lived. Harry is new to the "
            "wizarding world after spending so many years with his muggle family in "
            "unfortunate circumstances. While he is happy to be at Hogwarts now, he is "
            "also unsure of the wizarding powers his parents left him, but he is eager "
            "to make new friends at the school. Harry has frizzy brown hair and green "
            "eyes and has a small lightning-shaped scar on his forehead. Harry wears "
            "round glasses and currently wears a first year student robe."),
    },
    "narrator_gender": "Woman", "narrator_accent": "Posh (British)",
    "theme": "Fantasy", "turns": "4", "rounds": "endless",
}

# Built to the harness's input-craft rules (model_empathy_small_models4 §7):
# ONE PUSHER (Kael, who must collect by the end of the shift) and ONE RESISTER
# (Vess, who will not give up the box) - two avoiders stall; STAKES that are
# physical and unambiguous (a falling station, a clamped ship, three days,
# seats that are bought or collected) - vagueness is resolved in the least
# committal direction; the cast is the two of them - a third speaking agent
# has no turn slot; and concrete visual tokens up front for the portraits.
KERCHOFF = {
    "title": "Kerchoff Station — Vess & Kael",
    "world_desc": (
        "Kerchoff Station: a rusting salvage platform in low orbit over Morrow, a "
        "dying gas giant whose storms drag the station a little lower every day. "
        "Salvage crews strip wrecks from the debris ring and trade in secrets as "
        "readily as scrap. The only law is the Ledger, the Halvane Company's debt "
        "registry, and its collectors can seize a debtor's ship, air allowance or "
        "seat off-station. The last evacuation shuttle leaves in three days. Seats "
        "are not given; they are bought, or collected."),
    "prior_history": (
        "A year ago Kael clamped and repossessed Vess's ship; she broke his nose for "
        "it, and they have not spoken since."),
    "char_a": {
        "name": "Vess", "gender": "female", "age": "MiddleAged",
        "identity": "Vess Arden, she/her, human", "address": "Arden",
        "description": (
            "Vess Arden, a salvage pilot with a scarred jaw, close-cropped grey-streaked "
            "hair and a patched grey flight coat with a cracked visor clipped to the "
            "collar. Twelve years ago she flew the wreck-run that killed her crew, and "
            "she still owes Halvane for the ship she lost. Wary and quick to read a "
            "room, she speaks in short clipped sentences, never says thank you, and "
            "answers questions with questions. Yesterday she pulled a sealed black-box "
            "recorder out of the debris ring - from a ship the Ledger says never "
            "existed - and she carries it inside her coat. She wants one seat on the "
            "last shuttle, and she will not give up the box to get it."),
    },
    "char_b": {
        "name": "Kael", "gender": "male", "age": "YoungAdult",
        "identity": "Kael Doran, he/him, human", "address": "Doran",
        "description": (
            "Kael Doran, a Halvane debt collector in a sharp red company jacket, with "
            "slicked-back dark hair, a crooked healed nose and a silver earpiece that "
            "reads him the Ledger. Silver-tongued and overconfident, he hides fear "
            "behind jokes and never stops talking. His orders are to settle Vess's "
            "debt by the end of the shift - her clamped ship, the black box, or her "
            "shuttle seat - and if he fails, his own seat is forfeit. He pushes: he "
            "bargains, flatters, threatens politely and follows her everywhere."),
    },
    "narrator_gender": "Woman", "narrator_accent": "Rough (American)",
    "theme": "Cyberpunk", "turns": "6", "rounds": "endless",
}

# v12.4: the user's Kaya & Bobb (their Fayrun scenario: the fox-girl wizard,
# the paladin, the puppy Billy and the dragon over Marara), kept in every
# point and filled out to the same rules as Kerchoff: ONE PUSHER (Bobb, sworn
# to settle the dragon by sunset tomorrow) and ONE RESISTER (Kaya, who will
# not fry it) wanting the same thing by different means; a clock; a shared
# yesterday; both on the wall in the first scene; visual tokens first for the
# portraits. Billy is spelled out as a small white DOG - in the 2026-09-28
# field test a staging's "your son" turned him into Bobb's son for 4 lines.
KAYA_BOBB = {
    "title": "Fayrun — Kaya & Bobb",
    "world_desc": (
        "Fayrun is a mystical land of misty green hills, crystal rivers and glowing "
        "lantern-moths, home to many creatures, from pixies in the wheat fields to "
        "the fox-folk of the deep woods. Its jewel is Marara, a walled city of white "
        "stone towers and blue-tiled roofs around a cathedral with a great bronze "
        "bell. For seven nights a wild gold dragon has circled the hills above "
        "Marara, burning barns and carrying off sheep, and every night it flies a "
        "little closer to the walls. It must be tamed or driven away before it "
        "wrecks the whole city, and the city council has given its dragon-hunters "
        "until sunset tomorrow. Tonight the market square is empty, shutters are "
        "nailed shut and children hide in the cellars, while Kaya and Bobb stand "
        "together on top of the city wall above the north gate, torches spitting in "
        "the wind, with Kaya's puppy Billy, a small fluffy white dog, shivering at "
        "her feet. They watch the dark hills for the dragon's fire and argue about "
        "it: Bobb wants Kaya's lightning ready to strike the beast down, and Kaya "
        "wants to tame it."),
    "prior_history": (
        "Bobb rode into Marara three days ago and asked the wizards' guild for a "
        "lightning mage; with every senior wizard hiding, the guild sent Kaya. "
        "Yesterday Kaya's puppy Billy ran off after the dragon's shadow, and Bobb "
        "carried the little dog home on his shoulders - the only reason Kaya agreed "
        "to stand on the wall with him tonight."),
    "char_a": {
        "name": "Kaya", "gender": "female", "age": "YoungAdult",
        "identity": "Kaya, she/her, fox girl wizard", "address": "Kaya",
        "description": (
            "Kaya is a cute fox girl and a young wizard with fluffy orange fox ears, a "
            "big bushy white-tipped tail and bright green eyes. She wears a floppy "
            "purple wizard hat with silver stars and a blue robe, carries a satchel of "
            "honey cakes, and blue sparks crackle around her fingers and the tip of her "
            "oak staff. She has real magic and can call down lightning to destroy her "
            "enemies, though her spells sometimes go wrong in silly ways. She likes "
            "cute toys and puppies, keeps a stuffed dragon plush in her satchel and "
            "sleeps every night curled up with her puppy Billy, a small fluffy white "
            "dog who follows her everywhere. Kaya is bubbly, curious and brave in "
            "bursts, but scared of the dark; she talks fast, squeals, gives everything "
            "cute nicknames and blurts out whatever she sees the moment she sees it. "
            "She refuses to fry the dragon: she found one of its golden scales with a "
            "broken arrow stuck through it, is sure the beast is hurt and frightened "
            "rather than evil, and wants to tame it with kindness."),
    },
    "char_b": {
        "name": "Bobb", "gender": "male", "age": "MiddleAged",
        "identity": "Sir Bobb, he/him, human paladin", "address": "Sir Bobb",
        "description": (
            "Bobb is a brave paladin, a holy knight of the Order of the Dawn: "
            "broad-shouldered, with a short brown beard going grey, kind brown eyes, "
            "dented silver plate armour under a white tabard with a golden sun, a big "
            "round shield and a longsword that glows when he prays. He has sworn on "
            "the cathedral altar to tame or destroy the dragon threatening the city of "
            "Marara before sunset tomorrow; if he fails, his Order will break his sword "
            "and the city will burn. He would rather tame the beast than kill it, but "
            "he needs Kaya's lightning either way, so he pushes: he wants to march "
            "into the hills tonight and keeps asking her to be ready to strike. "
            "Steady, honest and a little old-fashioned, he speaks slowly and formally, "
            "swears by the Dawn, calls Kaya \"little mage\" and always steps in front "
            "of her and Billy when danger comes. He likes Billy far more than a stern "
            "knight should, sneaks him bits of sausage and lets him chew his gauntlet."),
    },
    "narrator_gender": "Man", "narrator_accent": "Posh (British)",
    "theme": "Fantasy", "turns": "6", "rounds": "endless",
}

# Shown in this order: the user's Hogwarts first, then Kaya & Bobb, then Kerchoff.
BUILTIN_STORIES = (HOGWARTS, KAYA_BOBB, KERCHOFF)

# =============================================================================
#  NORMALISING  (every story that leaves this module has every field)
# =============================================================================

def _pick(value, allowed, default):
    value = str(value) if value is not None else ""
    return value if value in allowed else default


def normalize(story: dict) -> dict:
    """A complete, valid story from any dict - missing or odd values get defaults."""
    s = story if isinstance(story, dict) else {}
    out = {"title": str(s.get("title") or "Untitled story").strip()[:80],
           "world_desc": str(s.get("world_desc") or ""),
           "prior_history": str(s.get("prior_history") or "")}
    for slot, gender, age in (("char_a", "female", "MiddleAged"),
                              ("char_b", "male", "YoungAdult")):
        c = s.get(slot) if isinstance(s.get(slot), dict) else {}
        out[slot] = {"name": str(c.get("name") or "").strip(),
                     "gender": _pick(c.get("gender"), GENDERS, gender),
                     "age": _pick(c.get("age"), AGES, age),
                     "identity": str(c.get("identity") or ""),
                     "address": str(c.get("address") or ""),
                     "description": str(c.get("description") or "")}
    out["narrator_gender"] = _pick(s.get("narrator_gender"), NARRATOR_GENDERS, "Woman")
    out["narrator_accent"] = _pick(s.get("narrator_accent"), NARRATOR_ACCENTS,
                                   "Rough (American)")
    out["theme"] = _pick(s.get("theme"), THEMES, "Cyberpunk")
    out["turns"] = _pick(s.get("turns"), TURNS, "6")
    out["rounds"] = _pick(s.get("rounds"), ROUNDS, "endless")
    return out

# =============================================================================
#  LISTING, LOADING, SAVING, DELETING
# =============================================================================

def _builtin_titles() -> set:
    return {b["title"].lower() for b in BUILTIN_STORIES}


def _saved(stories_dir: str = None):
    """[(title, path)] of the player's saved stories, readable ones only."""
    d = stories_dir or STORIES_DIR
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for fn in names:
        if not fn.lower().endswith(".json"):
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue                      # a broken file is skipped, never fatal
        # Only something that looks like a story counts - any other JSON
        # dropped in the folder is not listed as an "Untitled story".
        if not (isinstance(data, dict) and "world_desc" in data
                and isinstance(data.get("char_a"), dict)):
            continue
        title = normalize(data)["title"]
        out.append((title, path))
    return out


def list_stories(stories_dir: str = None) -> list:
    """[{title, builtin, path}] - the built-ins first, then saved ones A-Z."""
    rows = [{"title": b["title"], "builtin": True, "path": None} for b in BUILTIN_STORIES]
    saved = sorted(_saved(stories_dir), key=lambda tp: tp[0].lower())
    rows += [{"title": t, "builtin": False, "path": p} for t, p in saved]
    return rows


def get_story(title: str, stories_dir: str = None):
    """The story with this title (a copy), or None."""
    for b in BUILTIN_STORIES:
        if b["title"].lower() == (title or "").lower():
            return normalize(copy.deepcopy(b))
    for t, path in _saved(stories_dir):
        if t.lower() == (title or "").lower():
            with open(path, encoding="utf-8") as f:
                return normalize(json.load(f))
    return None


def is_builtin(title: str) -> bool:
    return (title or "").strip().lower() in _builtin_titles()


def _slug(title: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:60]
    return s or "story"


def save_story(story: dict, title: str, stories_dir: str = None) -> tuple:
    """
    Save under `title`; returns (title_used, path). A built-in title is never
    overwritten - the story is saved as "<title> (my version)" instead. A
    saved story with the same title is overwritten in place.
    """
    d = stories_dir or STORIES_DIR
    title = (title or "").strip()[:80] or "Untitled story"
    if is_builtin(title):
        title = f"{title} (my version)"
    s = normalize(dict(story, title=title))
    os.makedirs(d, exist_ok=True)
    path = next((p for t, p in _saved(d) if t.lower() == title.lower()), None)
    if path is None:
        base = os.path.join(d, _slug(title))
        path, n = base + ".json", 2
        while os.path.exists(path):
            path, n = f"{base}_{n}.json", n + 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)
    return title, path


def delete_story(title: str, stories_dir: str = None) -> bool:
    """Delete a SAVED story. Built-ins cannot be deleted. True if removed."""
    if is_builtin(title):
        return False
    for t, path in _saved(stories_dir):
        if t.lower() == (title or "").lower():
            os.remove(path)
            return True
    return False


def to_config(story: dict) -> dict:
    """The director's config keys for a story (the GUI adds the session switches)."""
    s = normalize(story)

    def char(c):
        return {"name": c["name"], "gender": c["gender"], "age": c["age"],
                "identity": c["identity"], "address": c["address"],
                "description": c["description"]}

    return {"world_desc": s["world_desc"], "prior_history": s["prior_history"],
            "char_a_inputs": char(s["char_a"]), "char_b_inputs": char(s["char_b"]),
            "narrator_gender": s["narrator_gender"].lower(),
            "narrator_accent": "posh" if s["narrator_accent"].startswith("Posh") else "rough",
            "turns_per_round": int(s["turns"]),
            "rounds": 0 if s["rounds"] == "endless" else int(s["rounds"])}
