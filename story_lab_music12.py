"""
story_lab_music12.py  —  Story Lab v12.4  //  Background music

PURPOSE
=======
Instrumental background music for each round, made by ACE-Step 1.5 in
ComfyUI from the round's scene (the user's design, 2026-10-17). Four parts,
none of which imports the engine:

  1. THE MUSIC ITSELF. engine12's composer names two things - the kind of
     SOUNDTRACK the world suits (once per game, one word from a closed list)
     and the scene's MOOD (every round, a few words). This module turns them
     into what ACE-Step reads: a prose caption, a bpm and a key.
       - PALETTES: one hand-written palette per soundtrack - genre phrase,
         instruments, and the instrument that takes each role (melody, bed,
         pulse, colour). Orchestral where the world is, synth where it is.
       - MOOD_CLASSES: the mood words vote (MOOD_LEXICON) for one of twelve
         classes, each with a tempo, major or minor (research: tempo drives
         arousal, mode drives valence) and how each role plays in it.
       - SCENE_COLOURS: a few story words that give the music a colour
         (a wedding -> soft bell-like chimes, a storm, the sea, space).
       Why the model does not write the music: two probes (loop_reports/
       v12_4_music/) asked it to; it wrote track titles, the assistant
       register and "Hedwig's Theme". It names feelings well.
     Caption register: ACE-Step 1.5's training captions are prose written by
     its own captioner ("A melancholic indie folk track featuring
     fingerpicked acoustic guitar as the primary instrument. The track opens
     with ..."); its tutorial keeps tempo and key OUT of the caption (they
     have their own fields) and calls 30-60 s a stable length.
  2. THE WORKFLOW. The user's Musicgenerator_ace_1v5_good.json (ACE-Step
     1.5 turbo: 8 steps, cfg 1) with caption, lyrics ("[Instrumental]"),
     seed, bpm, key, duration and the output node set per job - the output
     becomes lossless FLAC so the EQ works on the real signal.
  3. THE USER'S EQUALISER. musicpy.py's post-processing chain, settings
     kept exactly: low shelf 350 Hz -2.5 dB, high shelf 3 kHz +3 dB, high
     shelf 10 kHz +2 dB, RMS normalise to -22 dBFS, true-peak limit at -1
     dBFS. Re-implemented in numpy (the game's environment has no scipy):
     the shelves are applied zero-phase with |H|^2, which is what scipy's
     filtfilt does. It ALWAYS runs, right after generation (equalise_file:
     the raw render is kept beside it) - the user's rule, 2026-10-17: the
     equaliser is not a toggle. (The EQ/flat comparison lives on only in
     the Grid 1 listening study.)
  4. THE PLAYER. One sounddevice OutputStream of its own (the voice uses
     sd.play, whose sd.stop() never touches this stream; Windows mixes
     the two): it plays the equalised file - seamless loop (fades trimmed,
     the tail cross-faded into the head), a cross-fade between tracks,
     volume, pause, and ducking under the voice (games dip music a few dB
     under dialogue; DUCK_DB).
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import threading
import time
import uuid

try:
    import numpy as np
except Exception:                                   # pragma: no cover
    np = None
try:
    import soundfile as sf
except Exception:                                   # pragma: no cover
    sf = None
try:
    import sounddevice as sd
except Exception:                                   # pragma: no cover
    sd = None

import requests

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_MUSIC_FILE = os.path.join(_SCRIPT_DIR, "Musicgenerator_ace_1v5_good.json")

MUSIC_SECONDS = 70          # one track (the user's choice, 2026-10-17: ~70 s, looping
                            # until the next is ready; their own 70 s render was good)
MAX_MUSIC_WAIT = 600        # seconds before one job is abandoned
LYRICS = "[Instrumental]"   # the official way to ask ACE-Step 1.5 for no vocals

# =============================================================================
#  SECTION 1 - PALETTES  (one per engine12.MUSIC_SOUNDTRACKS entry)
# =============================================================================
#  genre        the caption's genre phrase
#  instruments  the caption's "featuring ..." list
#  lead         the melody's instrument: {"default": ..., <mood class>: ...}
#  bed / pulse / colour   the other three roles, one instrument phrase each
#  default_mood the mood class when the composer's mood fails every draw
#               (probe v3: calm jazz for a noir interrogation was the miss)

PALETTES = {
    "fantasy": {
        "default_mood": "wonder",
        "label": "Orchestral fantasy",
        "genre": "orchestral fantasy score",
        "instruments": "warm strings, harp, celesta, French horns, flute and soft timpani",
        "lead": {"default": "a solo flute", "tense": "low strings",
                 "urgent": "the full string section", "epic": "French horns",
                 "sad": "a solo cello", "eerie": "a celesta", "mysterious": "a clarinet",
                 "playful": "pizzicato strings"},
        "bed": "warm strings", "pulse": "soft timpani", "colour": "a harp"},
    "science fiction": {
        "default_mood": "mysterious",
        "label": "Ambient synth (sci-fi)",
        "genre": "ambient electronic science-fiction score",
        "instruments": ("analog synth pads, deep sub-bass drones, glassy arpeggiated "
                        "synths, a soft electronic pulse and distant metallic textures"),
        "lead": {"default": "a glassy lead synth", "sad": "a soft, filtered synth",
                 "epic": "a bright, brassy synth", "tender": "a soft, filtered synth"},
        "bed": "analog synth pads", "pulse": "a soft electronic pulse",
        "colour": "glassy arpeggiated synths"},
    "horror": {
        "default_mood": "eerie",
        "label": "Dark ambient horror",
        "genre": "dark ambient horror score",
        "instruments": ("low bowed cellos, dissonant string clusters, a sparse detuned "
                        "piano, deep drones and metallic scrapes"),
        "lead": {"default": "a sparse, detuned piano", "tense": "low bowed cellos",
                 "urgent": "dissonant string clusters", "sad": "low bowed cellos"},
        "bed": "deep drones", "pulse": "a slow, muffled drum",
        "colour": "dissonant string clusters"},
    "crime noir": {
        "default_mood": "tense",
        "label": "Noir jazz",
        "genre": "smoky noir jazz piece",
        "instruments": "tenor saxophone, muted trumpet, upright bass, brushed drums and sparse piano",
        "lead": {"default": "a smoky tenor saxophone", "sad": "a muted trumpet",
                 "tense": "a muted trumpet", "eerie": "a muted trumpet"},
        "bed": "a sparse piano", "pulse": "brushed drums",
        "colour": "a walking upright bass"},
    "historical": {
        "default_mood": "calm",
        "label": "Classical chamber",
        "genre": "classical chamber piece",
        "instruments": "string quartet, harpsichord, solo violin and cello",
        "lead": {"default": "a solo violin", "sad": "a solo cello", "tense": "a solo cello",
                 "eerie": "a solo cello"},
        "bed": "a string quartet", "pulse": "a harpsichord", "colour": "a cello"},
    "modern": {
        "default_mood": "calm",
        "label": "Acoustic indie (modern)",
        "genre": "soft acoustic indie track",
        "instruments": "acoustic guitar, felt piano, warm bass, light percussion and soft synth pads",
        "lead": {"default": "a felt piano", "joyful": "a strummed acoustic guitar",
                 "playful": "a strummed acoustic guitar"},
        "bed": "soft synth pads", "pulse": "light percussion",
        "colour": "a fingerpicked acoustic guitar"},
    "romance": {
        "default_mood": "tender",
        "label": "Romantic piano & strings",
        "genre": "romantic piano and strings piece",
        "instruments": "grand piano, lush strings, solo cello and harp",
        "lead": {"default": "a grand piano", "sad": "a solo cello", "tender": "a solo cello"},
        "bed": "lush strings", "pulse": "low strings", "colour": "a harp"},
    "adventure": {
        "default_mood": "epic",
        "label": "Adventure orchestral",
        "genre": "adventurous orchestral score",
        "instruments": "bold brass, driving strings, snare drum, timpani and bright woodwinds",
        "lead": {"default": "bold French horns", "tender": "a solo oboe", "sad": "a solo oboe",
                 "mysterious": "low woodwinds", "playful": "bright woodwinds"},
        "bed": "driving strings", "pulse": "a snare drum and timpani",
        "colour": "bright woodwinds"},
    "western": {
        "default_mood": "calm",
        "label": "Cinematic western",
        "genre": "cinematic western score",
        "instruments": "twangy electric guitar, strummed acoustic guitar, harmonica, a lone trumpet and slow tom drums",
        "lead": {"default": "a twangy electric guitar", "sad": "a harmonica",
                 "tender": "a harmonica", "epic": "a lone trumpet"},
        "bed": "a strummed acoustic guitar", "pulse": "slow tom drums",
        "colour": "a harmonica"},
    "cyberpunk": {
        "default_mood": "tense",
        "label": "Dark synthwave (cyberpunk)",
        "genre": "dark synthwave track",
        "instruments": ("analog synth pads, a pulsing arpeggiated bass, gated electronic "
                        "drums and a glassy lead synth"),
        "lead": {"default": "a glassy lead synth", "sad": "a soft, detuned synth"},
        "bed": "analog synth pads", "pulse": "gated electronic drums",
        "colour": "a pulsing arpeggiated bass"},
    "post-apocalyptic": {
        "default_mood": "sad",
        "label": "Desolate ambient",
        "genre": "desolate post-apocalyptic ambient score",
        "instruments": "reverb-drenched electric guitar, low drones, a distant piano and dusty percussion",
        "lead": {"default": "a reverb-drenched electric guitar", "sad": "a distant piano",
                 "tender": "a distant piano"},
        "bed": "low drones", "pulse": "dusty, distant percussion", "colour": "a distant piano"},
    "comedy": {
        "default_mood": "playful",
        "label": "Playful orchestral (comedy)",
        "genre": "playful orchestral score",
        "instruments": "pizzicato strings, bassoon, clarinet, glockenspiel and light percussion",
        "lead": {"default": "a bassoon", "tender": "a clarinet", "sad": "a clarinet",
                 "joyful": "a clarinet"},
        "bed": "pizzicato strings", "pulse": "light percussion", "colour": "a glockenspiel"},
    "mythic": {
        "default_mood": "epic",
        "label": "Epic mythic orchestral",
        "genre": "epic mythic orchestral score",
        "instruments": "soaring strings, deep brass, booming taiko drums and an ancient wooden flute",
        "lead": {"default": "deep brass", "tender": "an ancient wooden flute",
                 "sad": "an ancient wooden flute", "mysterious": "an ancient wooden flute",
                 "eerie": "an ancient wooden flute"},
        "bed": "soaring strings", "pulse": "booming taiko drums",
        "colour": "an ancient wooden flute"},
}
DEFAULT_PALETTE = {
    "default_mood": "calm",
    "label": "Cinematic",
    "genre": "cinematic orchestral score",
    "instruments": "strings, piano, soft brass, harp and light percussion",
    "lead": {"default": "a piano", "epic": "soft brass"},
    "bed": "strings", "pulse": "light percussion", "colour": "a harp"}

# =============================================================================
#  SECTION 2 - MOOD CLASSES AND THE LEXICON
# =============================================================================
#  bpm/mode: tempo drives arousal, mode drives valence (Gabrielsson; the
#  affective-music literature). Kept between 64 and 128: this is music to
#  talk over.  melody = (noun phrase, verb that agrees with it).

MOOD_CLASSES = {
    "calm":       {"bpm": 70,  "mode": "major", "feel": "calm and spacious",
                   "melody": ("A slow, unhurried melody", "drifts"),
                   "bed": "holding long, quiet chords", "pulse": "barely moving",
                   "colour": "adding gentle, drifting notes"},
    "tender":     {"bpm": 74,  "mode": "major", "feel": "tender and intimate",
                   "melody": ("A slow, gentle melody", "floats"),
                   "bed": "holding soft, sustained chords", "pulse": "stirring quietly",
                   "colour": "rippling in quiet arpeggios"},
    "romantic":   {"bpm": 78,  "mode": "major", "feel": "warm and romantic",
                   "melody": ("A warm, flowing melody", "rises and falls"),
                   "bed": "swelling softly", "pulse": "swaying in a slow, lilting rhythm",
                   "colour": "adding glowing arpeggios"},
    "wonder":     {"bpm": 84,  "mode": "major", "feel": "magical and wide-eyed",
                   "melody": ("A soaring, wondering melody", "unfolds"),
                   "bed": "shimmering in wide, open chords", "pulse": "rolling softly",
                   "colour": "twinkling in rising arpeggios"},
    "joyful":     {"bpm": 112, "mode": "major", "feel": "bright and joyful",
                   "melody": ("A bright, lilting melody", "dances"),
                   "bed": "bouncing in light, happy chords",
                   "pulse": "keeping a lively, dancing rhythm",
                   "colour": "sparkling in quick runs"},
    "playful":    {"bpm": 104, "mode": "major", "feel": "playful and light-footed",
                   "melody": ("A cheeky, bouncing tune", "skips along"),
                   "bed": "plucking short, springy chords",
                   "pulse": "tapping a light, bouncy rhythm",
                   "colour": "adding playful flourishes"},
    "mysterious": {"bpm": 84,  "mode": "minor", "feel": "mysterious and hushed",
                   "melody": ("A hushed, wandering melody", "drifts"),
                   "bed": "holding low, shifting chords", "pulse": "ticking quietly",
                   "colour": "adding strange, shimmering notes"},
    "eerie":      {"bpm": 64,  "mode": "minor", "feel": "eerie and haunting",
                   "melody": ("A thin, unsettling line", "creeps"),
                   "bed": "holding low, dissonant drones", "pulse": "almost silent",
                   "colour": "adding cold, distant notes"},
    "tense":      {"bpm": 100, "mode": "minor", "feel": "tense and suspenseful",
                   "melody": ("Short, uneasy figures", "flicker"),
                   "bed": "holding low, dissonant chords",
                   "pulse": "keeping a restless, ticking pulse",
                   "colour": "adding sharp, nervous accents"},
    "urgent":     {"bpm": 128, "mode": "minor", "feel": "urgent and driving",
                   "melody": ("A fast, insistent ostinato", "drives forward"),
                   "bed": "surging in pounding chords",
                   "pulse": "hammering a relentless rhythm",
                   "colour": "flaring in rising stabs"},
    "sad":        {"bpm": 66,  "mode": "minor", "feel": "melancholic and sorrowful",
                   "melody": ("A slow, aching melody", "falls"),
                   "bed": "holding soft, sorrowful chords", "pulse": "sparse and heavy",
                   "colour": "adding falling notes"},
    "epic":       {"bpm": 100, "mode": "major", "feel": "epic and heroic",
                   "melody": ("A bold, heroic theme", "rings out"),
                   "bed": "swelling in broad, powerful chords",
                   "pulse": "beating a strong, marching rhythm",
                   "colour": "adding bright fanfares"},
}
DEFAULT_MOOD = "calm"

_LEX = {
    "calm": """calm peaceful serene still quiet relaxed restful soothing tranquil
        contemplative reflective meditative pensive thoughtful easy lazy drowsy
        sleepy unhurried settled content contented patient composed steady
        introspective measured""",
    "tender": """tender intimate warm soft affectionate caring comforting sweet
        bittersweet fond vulnerable delicate hopeful longing wistful nostalgic
        sentimental touching moving heartfelt grateful relieved safe gentle
        hope""",
    "romantic": """romantic loving love passionate flirtatious flirty sensual
        smitten adoring desire attraction yearning""",
    "wonder": """wonder wondrous magical awe awed enchanted dreamy curious amazed
        marvel marvelling transformative ethereal otherworldly""",
    "joyful": """joyful happy cheerful bright festive celebratory jubilant elated
        excited lively upbeat delighted glad carefree exuberant euphoric giddy
        joy celebration""",
    "playful": """playful sly mischievous cheeky teasing witty amused amusement
        lighthearted light-hearted silly quirky whimsical flippant reckless smug
        confident cocky banter""",
    "mysterious": """mysterious mystery enigmatic secretive hushed uncertain
        intrigued intriguing cryptic mystical strange unknown guarded cautious
        wary watchful searching alert calculating calculated controlled detached
        ambiguous suspicious isolated curiosity vigilant aware""",
    "eerie": """eerie haunting haunted ghostly creepy unsettling unnerving uncanny
        ominous sinister dread dreadful foreboding chilling spooky macabre
        menacing desolate bleak cold hollow forsaken disquiet disquieting
        uneasiness""",
    "tense": """tense tension suspense suspenseful uneasy anxious nervous edgy
        threatened threatening dangerous danger predatory trapped cornered caged
        pressured apprehensive anticipatory anticipation restless agitated
        defiant hostile territorial confrontational simmering brooding volatile
        combative competitive determined resolute gritty grim off-kilter
        vibrating charged fearful wired poised predator""",
    "urgent": """urgent frantic desperate panicked panic chaotic frenzied
        breathless racing driving explosive violent furious fierce ferocious
        relentless alarmed terrified adrenaline rushing wild hectic action
        battle combat""",
    "sad": """sad sorrowful sorrow melancholy melancholic mournful grief grieving
        tragic somber sombre heartbroken lonely loss regretful regret resigned
        defeated weary tired hopeless despair forlorn aching heavy gloomy
        dejected broken weighty""",
    "epic": """epic heroic triumphant majestic grand noble glorious victorious
        powerful sweeping soaring bold proud mighty stirring rousing inspiring
        awe-inspiring""",
}
MOOD_LEXICON = {w: cls for cls, words in _LEX.items() for w in words.split()}

_WORD = re.compile(r"[a-z]+(?:-[a-z]+)*")


def mood_class(mood: str) -> str:
    """
    The MOOD_CLASSES key the mood words vote for. Items are weighted by
    position (first 3, second 2, the rest 1) - the composer puts the
    strongest feeling first; ties go to the earliest vote. Adverbs that are
    not in the lexicon ("subtly", "quietly") are not votes.
    """
    votes, first = {}, {}
    for i, item in enumerate(t for t in re.split(r"[,;/]", (mood or "").lower()) if t.strip()):
        weight = 3 if i == 0 else 2 if i == 1 else 1
        for w in _WORD.findall(item):
            cls = MOOD_LEXICON.get(w)
            if cls is None and w.endswith("s"):
                cls = MOOD_LEXICON.get(w[:-1])
            if cls:
                votes[cls] = votes.get(cls, 0) + weight
                first.setdefault(cls, len(first))
    if not votes:
        return DEFAULT_MOOD
    return max(votes, key=lambda c: (votes[c], -first[c]))

# =============================================================================
#  SECTION 3 - SCENE COLOURS
# =============================================================================
#  Story words that colour the music. Words in the player's event count
#  double (it is what just happened); a colour needs a score of 2 - so one
#  passing mention in the opener ("competitive fire") does not set it.

SCENE_COLOURS = (
    ("wedding", "wedding bride groom married marry marries vows veil altar",
     "a ceremonial warmth, with soft bell-like chimes"),
    ("storm", "storm stormy thunder lightning gale tempest hurricane",
     "the rumble of a gathering storm"),
    ("rain", "rain raining rainy drizzle downpour", "a misty, rain-washed haze"),
    ("sea", "sea ocean waves wave tide shore beach surf harbour harbor",
     "the slow swell of the sea"),
    ("tropical", "tropical island palm palms lagoon cocktails honeymoon",
     "a warm, sunlit breeze"),
    ("night", "night midnight moonlight moonlit moon", "a nocturnal, moonlit hush"),
    ("winter", "snow snowy blizzard ice icy frost frozen winter",
     "a crystalline, wintry chill"),
    ("fire", "flames blaze inferno embers burning bonfire",
     "a smouldering, flickering heat"),
    ("battle", "battle fight fighting duel combat attack attacks war sword swords",
     "the clash of battle"),
    ("chase", "chase chasing flee fleeing pursuit escape escaping",
     "the rush of a chase"),
    ("festive", "party festival feast celebration celebrate dance dancing ball ballroom waltz",
     "a festive, dancing lift"),
    ("sacred", "church cathedral temple chapel shrine", "a sacred, echoing resonance"),
    ("space", "space orbit orbital vacuum gravity zero-g starship spacecraft",
     "the vast, weightless emptiness of space"),
    ("forest", "forest woods trees glade grove", "an earthy, woodland air"),
    ("funeral", "funeral grave graveyard mourning coffin buried",
     "a solemn, funereal weight"),
    ("machine", "machinery engines reactor factory industrial hydraulic",
     "a low, mechanical hum beneath it"),
)
_COLOUR_WORDS = [(key, frozenset(words.split()), phrase) for key, words, phrase in SCENE_COLOURS]


def scene_colours(scene: str = "", event: str = "", limit: int = 2) -> list:
    """[(key, phrase)] - at most `limit`, strongest first."""
    sw = _WORD.findall((scene or "").lower())
    ew = _WORD.findall((event or "").lower())
    scored = []
    for order, (key, words, phrase) in enumerate(_COLOUR_WORDS):
        score = sum(1 for w in sw if w in words) + 2 * sum(1 for w in ew if w in words)
        if score >= 2:
            scored.append((-score, order, key, phrase))
    return [(k, p) for _s, _o, k, p in sorted(scored)[:limit]]

# =============================================================================
#  SECTION 4 - THE CAPTION
# =============================================================================

# Not "hum": a machine's hum is one of the scene colours.
_VOCAL_WORDS = frozenset("""vocal vocals voice voices vocalist singing singer
    singers sung sings sing choir choirs choral chant chanting chants lyric lyrics
    rap rapping humming""".split())
_KEY_WORDS = re.compile(r"\b\d{2,3}\s*bpm\b|\bin\s+[a-g](?:#|b|\s+sharp|\s+flat)?\s+"
                        r"(?:major|minor)\b|\bkey\s+of\s+\w+", re.IGNORECASE)
MOOD_ITEMS_MAX = 3

# The game's home key: a minor key from the game seed, and its relative
# major for bright moods - the two share their notes, so the cross-fade
# from one round's music to the next stays in one tonal world.
_HOME_MINORS = ("A", "D", "E", "B", "G", "C", "F#")
_RELATIVE_MAJOR = {"A": "C", "D": "F", "E": "G", "B": "D", "G": "Bb", "C": "Eb", "F#": "A"}


def keyscale_for(mode: str, game_seed: int = 0) -> str:
    root = _HOME_MINORS[int(game_seed or 0) % len(_HOME_MINORS)]
    return f"{_RELATIVE_MAJOR[root]} major" if mode == "major" else f"{root} minor"


# When the composer names no soundtrack (probe v3: 4 of 12 world draws were
# a title or a place), the world's own words choose: the entry with the
# most hint words in the world description and the setting, if any.
SOUNDTRACK_HINTS = {
    "fantasy": """magic magical wizard wizards witch witches sorcery spell spells
        dragon dragons elf elves castle kingdom hogwarts wand wands enchanted fairy
        quest sorcerer knight knights""",
    "science fiction": """space station orbit orbital starship spaceship planet
        planets android androids robot robots alien aliens galaxy colony hangar
        airlock salvage sci-fi futuristic shuttle asteroid""",
    "horror": """horror haunted ghost ghosts demon demons corpse undead zombie
        zombies nightmare lighthouse cursed occult""",
    "crime noir": """detective precinct interrogation noir crime murder police cop
        cops suspect gangster mob charges""",
    "historical": """victorian edwardian medieval regency solicitor solicitors duke
        duchess carriage gaslight gas""",
    "cyberpunk": "neon cyberpunk megacity hacker implants chrome dystopia",
    "post-apocalyptic": "wasteland apocalypse apocalyptic ruins fallout survivors",
    "western": "frontier saloon cowboy cowboys sheriff outlaw outlaws ranch",
    "romance": "romance lovers",
    "adventure": "adventure expedition treasure jungle pirates pirate",
    "mythic": "gods goddess myth mythic olympus valhalla titans",
    "comedy": "comedy farce sitcom",
    "modern": "apartment office cafe suburb college bakery hospital",
}
_HINT_WORDS = {k: frozenset(v.split()) for k, v in SOUNDTRACK_HINTS.items()}


def guess_soundtrack(text: str) -> str:
    """The PALETTES key whose hint words the text has most of ("" if none)."""
    words = _WORD.findall((text or "").lower())
    best, score = "", 0
    for key, hints in _HINT_WORDS.items():
        n = sum(1 for w in words if w in hints)
        if n > score:
            best, score = key, n
    return best


def palette_for(soundtrack: str) -> dict:
    return PALETTES.get((soundtrack or "").strip().lower(), DEFAULT_PALETTE)


def clean_mood(mood: str, names=()) -> str:
    """The composer's mood words for the caption: lower case, no names, no
    vocal words, no digits, at most MOOD_ITEMS_MAX items."""
    name_words = {w.lower() for n in names for w in re.findall(r"[A-Za-z']+", n or "")
                  if len(w) > 2}
    items = []
    for item in re.split(r"[,;/]", mood or ""):
        # a hyphenated word goes if any part is a name ("Rosa-focused")
        words = [w for w in re.findall(r"[A-Za-z'-]+", item)
                 if not any(part in name_words for part in w.lower().split("-"))
                 and w.lower() not in _VOCAL_WORDS]
        text = " ".join(words).lower().strip(" -'")
        if text and text not in items:
            items.append(text)
    return ", ".join(items[:MOOD_ITEMS_MAX])


def _article(word: str) -> str:
    return "An" if (word or "x")[0].lower() in "aeiou" else "A"


def _join_list(items):
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _scrub(text: str) -> str:
    """No tempo or key words in the caption (ACE-Step's tutorial), no vocal words."""
    text = _KEY_WORDS.sub("", text)
    words = text.split(" ")
    kept = [w for w in words if re.sub(r"[^a-z]", "", w.lower()) not in _VOCAL_WORDS]
    return re.sub(r"\s{2,}", " ", " ".join(kept)).replace(" ,", ",").strip()


def build_music_prompt(soundtrack: str, mood: str, scene: str = "", event: str = "",
                       names=(), game_seed: int = 0, seconds: float = MUSIC_SECONDS) -> dict:
    """
    Everything one ACE-Step job needs, from the composer's two notes:
    {caption, lyrics, bpm, keyscale, timesignature, seconds, mood_class,
    mood, soundtrack, colours, body}. `body` is the short line the GUI shows.
    """
    pal = palette_for(soundtrack)
    words = clean_mood(mood, names)
    cls = mood_class(words) if words else pal["default_mood"]
    if words and cls == DEFAULT_MOOD and not any(
            w in MOOD_LEXICON for w in _WORD.findall(words)):
        cls = pal["default_mood"]                 # no word voted: the palette's own
    mc = MOOD_CLASSES[cls]
    words = words or mc["feel"].replace(" and ", ", ")
    lead = pal["lead"].get(cls, pal["lead"]["default"])
    np_, verb = mc["melody"]
    sentence = (f"{np_} on {lead} {verb} over {pal['bed']} {mc['bed']}, with "
                f"{pal['pulse']} {mc['pulse']} and {pal['colour']} {mc['colour']}.")
    colours = scene_colours(scene, event)
    colour_sentence = (f" The music carries {_join_list([p for _k, p in colours])}."
                       if colours else "")
    # The probe's first captions led with the composer's words ("A predatory
    # focus, defiant confidence, underlying tension instrumental smoky noir
    # jazz"); the class's feel leads now and the words get their own clause.
    caption = (f"{_article(mc['feel'])} {mc['feel']} instrumental {pal['genre']} for a "
               f"video game soundtrack, featuring {pal['instruments']}. Mood: {words}. "
               f"{sentence}{colour_sentence} It plays as background music, consistent, "
               f"smooth and flowing from start to finish, with a clean, spacious mix.")
    text = " ".join((scene or "") .lower().split() + (event or "").lower().split())
    return {
        "caption": _scrub(caption),
        "lyrics": LYRICS,
        "bpm": int(mc["bpm"]),
        "keyscale": keyscale_for(mc["mode"], game_seed),
        "timesignature": "3" if "waltz" in text else "4",
        "seconds": float(seconds),
        "mood_class": cls,
        "mood": words,
        "soundtrack": soundtrack if soundtrack in PALETTES else "",
        "colours": [k for k, _p in colours],
        "body": f"{pal['label']} · {words} ({cls}, {int(mc['bpm'])} bpm, "
                f"{keyscale_for(mc['mode'], game_seed)})",
    }

# =============================================================================
#  SECTION 5 - THE WORKFLOW
# =============================================================================

class MusicWorkflowError(Exception):
    """The music workflow file cannot be used; the message says why."""


_TE_CLASS = "TextEncodeAceStepAudio1.5"
_LATENT_CLASS = "EmptyAceStep1.5LatentAudio"
_SAVE_CLASSES = {"SaveAudio", "SaveAudioMP3", "SaveAudioOpus", "PreviewAudio"}
_LOADER_FILES = {"UNETLoader": ("unet_name",), "VAELoader": ("vae_name",),
                 "CheckpointLoaderSimple": ("ckpt_name",),
                 "DualCLIPLoader": ("clip_name1", "clip_name2"),
                 "CLIPLoader": ("clip_name",)}
_wf_cache = {}


def load_music_workflow(path: str = None) -> dict:
    """The API-format workflow (cached by mtime). Raises MusicWorkflowError."""
    path = path or WORKFLOW_MUSIC_FILE
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        raise MusicWorkflowError(f"music workflow not found: {path}")
    hit = _wf_cache.get(path)
    if hit and hit[0] == mtime:
        return copy.deepcopy(hit[1])
    try:
        with open(path, encoding="utf-8") as f:
            api = json.load(f)
    except ValueError as e:
        raise MusicWorkflowError(f"{os.path.basename(path)} is not valid JSON ({e})")
    if not (isinstance(api, dict) and api and all(
            isinstance(v, dict) and "class_type" in v for v in api.values())):
        raise MusicWorkflowError(f"{os.path.basename(path)} is not an API-format "
                                 f"workflow (File > Export (API) in ComfyUI)")
    classes = [n["class_type"] for n in api.values()]
    if _TE_CLASS not in classes:
        raise MusicWorkflowError(f"no {_TE_CLASS} node - not an ACE-Step 1.5 workflow")
    if not _SAVE_CLASSES & set(classes):
        raise MusicWorkflowError("no audio output node (SaveAudio...) in the workflow")
    _wf_cache[path] = (mtime, api)
    return copy.deepcopy(api)


def parameterize_music(api: dict, prompt: dict, seed: int, codes: bool = True,
                       prefix: str = "storylab_music") -> dict:
    """Set caption, lyrics, seed, bpm, key, time signature and duration on
    every node that has them; the output becomes one lossless FLAC."""
    for nid, node in list(api.items()):
        cls, inp = node["class_type"], node["inputs"]
        if cls == _TE_CLASS:
            inp.update(tags=prompt["caption"], lyrics=prompt["lyrics"], seed=int(seed),
                       bpm=int(prompt["bpm"]), duration=float(prompt["seconds"]),
                       timesignature=str(prompt["timesignature"]),
                       keyscale=prompt["keyscale"], language="en",
                       generate_audio_codes=bool(codes))
        elif cls == _LATENT_CLASS:
            inp["seconds"] = float(prompt["seconds"])
        elif cls in ("KSampler", "KSamplerAdvanced") and "seed" in inp:
            inp["seed"] = int(seed)
        elif cls in ("KSamplerAdvanced",) and "noise_seed" in inp:
            inp["noise_seed"] = int(seed)
        elif cls in _SAVE_CLASSES:
            api[nid] = {"class_type": "SaveAudio",
                        "inputs": {"audio": inp["audio"], "filename_prefix": f"audio/{prefix}"}}
    return api


def missing_models(server: str, workflow_file: str = None) -> list:
    """What the music workflow needs that this server cannot load ([] = ready):
    an older ComfyUI has no ACE-Step 1.5 nodes; a fresh one may lack the files."""
    try:
        api = load_music_workflow(workflow_file)
    except MusicWorkflowError as e:
        return [str(e)]
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
        for key in _LOADER_FILES.get(cls, ()):
            if not isinstance(node["inputs"].get(key), str):
                continue
            spec = info[cls].get("input", {}).get("required", {}).get(key, [[]])
            options = spec[0] if spec and isinstance(spec[0], list) else []
            if node["inputs"][key] not in options:
                missing.append(f"{cls}: {node['inputs'][key]}")
    return sorted(set(missing))


def _submit_audio(server: str, workflow: dict, label: str, dest: str, progress=None):
    """Queue, poll /history, download the first audio file to `dest`."""
    try:
        r = requests.post(f"{server}/prompt",
                          json={"prompt": workflow, "client_id": str(uuid.uuid4())},
                          timeout=15)
    except Exception as e:
        print(f"  ✗ Queue failed [{label}]: {e}", flush=True)
        return None
    if r.status_code != 200:
        print(f"  ✗ ComfyUI refused [{label}]: {r.text[:400]}", flush=True)
        return None
    prompt_id = r.json().get("prompt_id")
    start, last = time.time(), 0.0
    while True:
        elapsed = time.time() - start
        if elapsed > MAX_MUSIC_WAIT:
            print(f"  ✗ Timed out after {MAX_MUSIC_WAIT}s [{label}]", flush=True)
            return None
        if progress and elapsed - last >= 1.0:
            progress(elapsed)
            last = elapsed
        try:
            entry = requests.get(f"{server}/history/{prompt_id}", timeout=5).json().get(prompt_id)
        except Exception:
            entry = None
        if not entry:
            time.sleep(0.5)
            continue
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            msgs = [m for m in status.get("messages", []) if m and m[0] == "execution_error"]
            detail = msgs[0][1].get("exception_message", "") if msgs else ""
            print(f"  ✗ ComfyUI error [{label}]: {detail[:300]}", flush=True)
            return None
        for node_out in entry.get("outputs", {}).values():
            for meta in node_out.get("audio", []):
                try:
                    data = requests.get(f"{server}/view", params=meta, timeout=60).content
                    with open(dest, "wb") as f:
                        f.write(data)
                except Exception as e:
                    print(f"  ✗ Download failed [{label}]: {e}", flush=True)
                    return None
                return dest
        if status.get("completed"):
            print(f"  ⚠ No audio in output [{label}]", flush=True)
            return None
        time.sleep(0.5)


def music_filename(round_num: int, take: int = 0) -> str:
    """The equalised track - the one that plays."""
    return (f"music_round_{round_num:02d}.flac" if not take
            else f"music_round_{round_num:02d}_take{take + 1}.flac")


def raw_filename(round_num: int, take: int = 0) -> str:
    """ACE-Step's render as it came, before the equaliser (kept for reference)."""
    return music_filename(round_num, take).replace(".flac", "_raw.flac")


def generate_music(server: str, prompt: dict, run_dir: str, filename: str,
                   seed: int = None, codes: bool = True, progress=None,
                   workflow_file: str = None):
    """One track. Returns (path or None, seed). Logs to run_dir/music.txt."""
    if seed is None:
        seed = int.from_bytes(os.urandom(4), "little")
    try:
        wf = parameterize_music(load_music_workflow(workflow_file), prompt, seed, codes)
    except MusicWorkflowError as e:
        print(f"  ✗ Music workflow unusable: {e}", flush=True)
        return None, seed
    dest = os.path.join(run_dir, filename)
    t0 = time.time()
    path = _submit_audio(server, wf, f"music {filename}", dest, progress)
    try:
        with open(os.path.join(run_dir, "music.txt"), "a", encoding="utf-8") as f:
            f.write(f"{filename if path else 'FAILED ' + filename}\tseed={seed}\t"
                    f"{time.time() - t0:.1f}s\tbpm={prompt['bpm']}\t{prompt['keyscale']}\t"
                    f"codes={codes}\n  {prompt['caption']}\n")
    except Exception:
        pass
    if path:
        print(f"  ✓ music -> {filename} in {time.time() - t0:.1f}s", flush=True)
    return path, seed

# =============================================================================
#  SECTION 6 - THE USER'S EQUALISER (musicpy.py's chain, in numpy)
# =============================================================================

EQ_BANDS = (("low_shelf", 350, -2.5), ("high_shelf", 3000, +3.0), ("high_shelf", 10000, +2.0))
TARGET_RMS_DB = -22.0
CEILING_DB = -1.0
LIMIT_ATTACK_MS = 0.5
LIMIT_RELEASE_MS = 50.0
TRUE_PEAK_OVERSAMPLE = 4


def shelf_coeffs(freq, gain_db, sr, shelf_type):
    """RBJ cookbook shelf (S = 1) - musicpy.py's _shelf_coeffs, unchanged."""
    A = 10 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * freq / sr
    cos_w0, sin_w0 = math.cos(w0), math.sin(w0)
    alpha = sin_w0 / 2.0 * math.sqrt(2.0 * (A + 1.0 / A))
    sa = 2 * math.sqrt(A) * alpha
    if shelf_type == "low":
        b = (A * ((A + 1) - (A - 1) * cos_w0 + sa), 2 * A * ((A - 1) - (A + 1) * cos_w0),
             A * ((A + 1) - (A - 1) * cos_w0 - sa))
        a = ((A + 1) + (A - 1) * cos_w0 + sa, -2 * ((A - 1) + (A + 1) * cos_w0),
             (A + 1) + (A - 1) * cos_w0 - sa)
    else:
        b = (A * ((A + 1) + (A - 1) * cos_w0 + sa), -2 * A * ((A - 1) + (A + 1) * cos_w0),
             A * ((A + 1) + (A - 1) * cos_w0 - sa))
        a = ((A + 1) - (A - 1) * cos_w0 + sa, 2 * ((A - 1) - (A + 1) * cos_w0),
             (A + 1) - (A - 1) * cos_w0 - sa)
    return np.array(b) / a[0], np.array(a) / a[0]


def eq_power_response(n_fft: int, sr: int, bands=EQ_BANDS):
    """|H(f)|^2 of all shelves in series at the rfft bins - the zero-phase
    response filtfilt gives (each band applied forward and backward)."""
    w = 2 * np.pi * np.fft.rfftfreq(n_fft, 1.0 / sr) / sr
    z = np.exp(-1j * w)
    resp = np.ones_like(w)
    for kind, freq, gain in bands:
        b, a = shelf_coeffs(freq, gain, sr, "low" if kind == "low_shelf" else "high")
        h = (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)
        resp = resp * np.abs(h) ** 2
    return resp


EQ_FIR_TAPS = 16384         # the zero-phase impulse of |H|^2, centred (~0.34 s)
EQ_BLOCK = 1 << 16


def eq_fir(sr: int, bands=EQ_BANDS, taps: int = EQ_FIR_TAPS):
    """The shelves' zero-phase response as a centred FIR (Hann-windowed).
    The shelves' impulse dies out in a few ms, so truncation is far below
    audibility (test: within -120 dBFS of filtfilt)."""
    n_fft = taps * 4
    h = np.fft.irfft(eq_power_response(n_fft, sr, bands), n=n_fft)
    h = np.roll(h, taps // 2)[:taps]
    return h * np.hanning(taps)


def apply_eq(audio, sr: int, bands=EQ_BANDS):
    """Zero-phase shelving EQ = filtfilt of the three shelves, done as an
    overlap-add convolution with eq_fir() (one 4M-point FFT took 1-2.5 s on
    this laptop; blocks take a fraction)."""
    h = eq_fir(sr, bands)
    taps, n = len(h), audio.shape[0]
    n_fft = 1 << int(math.ceil(math.log2(EQ_BLOCK + taps)))
    H = np.fft.rfft(h, n=n_fft)[:, None]
    out = np.zeros((n + taps, audio.shape[1]), dtype=np.float64)
    for s in range(0, n, EQ_BLOCK):
        seg = audio[s:s + EQ_BLOCK]
        y = np.fft.irfft(np.fft.rfft(seg, n=n_fft, axis=0) * H, n=n_fft, axis=0)
        k = seg.shape[0] + taps - 1
        out[s:s + k] += y[:k]
    half = taps // 2
    return out[half:half + n].astype(audio.dtype, copy=False)


def rms_normalize(audio, target_db: float = TARGET_RMS_DB):
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    if rms < 1e-10:
        return audio
    return audio * (10 ** ((target_db - 20 * math.log10(rms)) / 20.0))


TRUE_PEAK_MARGIN_DB = 6.0   # inter-sample peaks overshoot the samples by a
                            # few dB at most; only blocks this close are checked


def _oversampled_peak(audio, factor: int = TRUE_PEAK_OVERSAMPLE, near: float = None):
    """Per-sample true peak: the largest |x| among each sample's `factor`
    band-limited (FFT) interpolation points, across channels. Only blocks
    holding a sample above `near` are oversampled (each with a guard band
    against the FFT's wrap-around); elsewhere the sample peak stands."""
    n = audio.shape[0]
    sample_peak = np.abs(audio).max(axis=1)
    peak = sample_peak.astype(np.float32)
    block, guard = 4096, 512
    if near is None:
        idx = range(0, n, block)
    else:
        hot = np.flatnonzero(sample_peak > near)
        idx = sorted({int(i) // block * block for i in hot})
    for s in idx:
        a, b = max(0, s - guard), min(n, s + block + guard)
        seg = audio[a:b].astype(np.float64)
        m = seg.shape[0]
        spec = np.fft.rfft(seg, axis=0)
        up = np.zeros((m * factor // 2 + 1, seg.shape[1]), dtype=complex)
        up[:spec.shape[0]] = spec
        over = np.fft.irfft(up, n=m * factor, axis=0) * factor
        o = np.abs(over).max(axis=1).reshape(m, factor).max(axis=1)
        e = min(n, s + block)
        peak[s:e] = np.maximum(peak[s:e], o[s - a:s - a + (e - s)])
    return peak


def true_peak_limit(audio, sr: int, ceiling_db: float = CEILING_DB,
                    attack_ms: float = LIMIT_ATTACK_MS, release_ms: float = LIMIT_RELEASE_MS):
    """
    musicpy.py's true-peak limiter: the gain each sample needs to stay under
    the ceiling (measured on the 4x-oversampled signal), smoothed with a fast
    attack and a slower release, then a hard clip at the ceiling. The
    original ran its envelope sample by sample in Python over the whole 4x
    signal; here it runs at the base rate and only where the gain is below
    1 (plus its release tail) - after the -22 dBFS normalise that is a few
    peaks, so a minute of music limits in well under a second.
    """
    ceiling = 10 ** (ceiling_db / 20.0)
    near = 10 ** ((ceiling_db - TRUE_PEAK_MARGIN_DB) / 20.0)
    req = np.minimum(1.0, ceiling / np.maximum(_oversampled_peak(audio, near=near), 1e-10))
    gain = np.ones(audio.shape[0], dtype=np.float64)
    hot = np.flatnonzero(req < 1.0)
    if hot.size:
        att = math.exp(-1.0 / max(1, int(attack_ms * sr / 1000)))
        rel = math.exp(-1.0 / max(1, int(release_ms * sr / 1000)))
        tail = int(release_ms * sr / 1000) * 12        # back to 1.0 within 1e-5
        lead = max(1, int(attack_ms * sr / 1000)) * 12
        spans, s0, e0 = [], max(0, hot[0] - lead), hot[0] + tail
        for i in hot[1:]:
            if i - lead <= e0:
                e0 = i + tail
            else:
                spans.append((s0, e0))
                s0, e0 = max(0, i - lead), i + tail
        spans.append((s0, e0))
        for s, e in spans:
            e = min(e, audio.shape[0])
            g = 1.0
            for i in range(s, e):
                t = req[i]
                g = att * g + (1 - att) * t if t < g else rel * g + (1 - rel) * t
                gain[i] = min(g, t)
    out = audio * gain[:, None].astype(audio.dtype)
    return np.clip(out, -ceiling, ceiling)


def trim_silence(audio, threshold_db: float = -50.0, keep_s: float = 0.05, sr: int = 48000):
    """Drop leading and trailing near-silence (keeping keep_s of it)."""
    level = np.abs(audio).max(axis=1)
    loud = np.flatnonzero(level > 10 ** (threshold_db / 20.0))
    if not loud.size:
        return audio
    keep = int(keep_s * sr)
    return audio[max(0, loud[0] - keep):min(audio.shape[0], loud[-1] + keep + 1)]


FADE_DROP_DB = 12.0         # an end more than this below the track's body is a fade


def trim_fades(audio, sr: int, drop_db: float = FADE_DROP_DB, frame_s: float = 0.25):
    """
    Cut a fade-in and a fade-out (an intro swelling up, an outro dying away)
    so the loop seam joins two parts at full level. The body's level is the
    median of the middle 60% (in frame_s frames); the track keeps everything
    from the first to the last frame within drop_db of it. Grid 1's raw
    tracks: 4 of 10 ended 36-49 dB below their middle, which a 4 s
    cross-fade alone would play as a dip every loop.
    """
    win = max(1, int(frame_s * sr))
    n = audio.shape[0] // win
    if n < 8:
        return audio
    frames = audio[:n * win].reshape(n, win, -1)
    level = 10 * np.log10(np.mean(np.square(frames, dtype=np.float64), axis=(1, 2)) + 1e-20)
    body = float(np.median(level[int(n * 0.2):int(n * 0.8)]))
    keep = np.flatnonzero(level >= body - drop_db)
    if not keep.size:
        return audio
    return audio[keep[0] * win:min(audio.shape[0], (keep[-1] + 1) * win)]


def process(audio, sr: int, eq: bool = True):
    """The user's chain: (EQ) -> RMS normalise -> true-peak limit."""
    x = audio.astype(np.float32)
    if eq:
        x = apply_eq(x, sr)
    x = rms_normalize(x).astype(np.float32)
    return true_peak_limit(x, sr).astype(np.float32)


def equalise_file(raw_path: str, out_path: str) -> str:
    """The user's chain on a rendered track, written as 24-bit FLAC: EQ ->
    RMS normalise -> true-peak limit. Returns out_path."""
    audio, sr = read_audio(raw_path)
    sf.write(out_path, process(audio, sr, eq=True), sr, subtype="PCM_24")
    return out_path


def read_audio(path: str):
    """(float32 frames x 2, sample rate) - mono is doubled to stereo."""
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    return audio[:, :2], sr

# =============================================================================
#  SECTION 7 - THE PLAYER
# =============================================================================

PLAYER_SR = 48000
LOOP_XFADE_S = 4.0          # the loop seam: tail cross-faded into the head
TRACK_XFADE_S = 4.0         # one round's music into the next
PAUSE_FADE_S = 0.3
DUCK_DB = -8.0              # under the voice ("a few dB"; 6-12 is the usual range)
DUCK_ATTACK_S = 0.15
DUCK_RELEASE_S = 0.8
DUCK_HOLD_S = 0.6           # a sentence's duck outlasts it, so gaps do not pump
DEFAULT_VOLUME = 0.5


def _resample(audio, sr_in: int, sr_out: int):
    if sr_in == sr_out:
        return audio
    n_out = int(round(audio.shape[0] * sr_out / sr_in))
    t_in = np.arange(audio.shape[0]) / sr_in
    t_out = np.arange(n_out) / sr_out
    return np.stack([np.interp(t_out, t_in, audio[:, c]) for c in range(audio.shape[1])],
                    axis=1).astype(np.float32)


def make_loop(audio, sr: int, xfade_s: float = LOOP_XFADE_S):
    """
    (intro, loop) for seamless repetition: the track plays from its start,
    then `loop` repeats forever. The loop's last xfade_s are the track's
    tail fading out over its head fading in (equal power), so the jump back
    lands exactly where the head left off.
    """
    n = audio.shape[0]
    x = int(min(xfade_s * sr, n // 4))
    if x < 1:
        return audio[:0], audio
    t = np.linspace(0, math.pi / 2, x, dtype=np.float32)[:, None]
    seam = audio[n - x:] * np.cos(t) + audio[:x] * np.sin(t)
    loop = np.concatenate([audio[x:n - x], seam], axis=0)
    return audio[:x], loop


class Track:
    """One track ready to loop: the EQUALISED file (equalise_file), its
    fades trimmed, as (intro, loop)."""

    def __init__(self, path: str, label: str = "", round_num: int = 0, take: int = 0):
        audio, sr = read_audio(path)
        audio = trim_fades(trim_silence(audio, sr=sr), sr)
        self.path, self.label, self.round, self.take = path, label, round_num, take
        self.intro, self.loop = make_loop(_resample(audio, sr, PLAYER_SR), PLAYER_SR)
        self.seconds = audio.shape[0] / float(sr)

    def frames(self, pos: int, n: int):
        """n frames from `pos` of the endless (intro + loop*) signal."""
        intro, loop = self.intro, self.loop
        out = np.empty((n, 2), dtype=np.float32)
        done = 0
        while done < n:
            p = pos + done
            if p < len(intro):
                k = min(n - done, len(intro) - p)
                out[done:done + k] = intro[p:p + k]
            else:
                q = (p - len(intro)) % len(loop)
                k = min(n - done, len(loop) - q)
                out[done:done + k] = loop[q:q + k]
            done += k
        return out


class _Voice:
    def __init__(self, track, gain=0.0, target=1.0):
        self.track, self.pos, self.gain, self.target = track, 0, gain, target


def _ramp(current: float, target: float, seconds: float, n: int, sr: int):
    """A linear per-sample ramp from current toward target at a rate that
    covers the full 0..1 range in `seconds`. Returns (ramp, new value)."""
    if current == target:
        return np.full(n, current, dtype=np.float32), current
    step = 1.0 / max(1.0, seconds * sr)
    total = abs(target - current)
    k = min(n, int(math.ceil(total / step)))
    direction = 1.0 if target > current else -1.0
    ramp = current + direction * step * np.arange(1, n + 1, dtype=np.float32)
    ramp[k:] = target
    if direction > 0:
        np.minimum(ramp, target, out=ramp)
    else:
        np.maximum(ramp, target, out=ramp)
    return ramp, float(ramp[-1])


class MusicPlayer:
    """
    The game's music: play / pause, volume, ducking, loop and track
    cross-fades. It plays equalised files; it does no processing of its own. Thread model: the GUI calls the setters (plain
    attribute writes); the PortAudio callback reads them; the list of voices
    is swapped under a lock.
    """

    def __init__(self, volume: float = DEFAULT_VOLUME):
        self.volume = float(volume)
        self.paused = False
        self._vol_gain = self._vol_to_gain(volume)
        self._pause_gain = 1.0
        self._duck_gain = 1.0
        self._duck_until = 0.0
        self._voices = []
        self._lock = threading.Lock()
        self._stream = None
        self.current = None
        self.error = ""
        self._gen = 0                # stop() bumps it: a load still running is dropped

    @staticmethod
    def _vol_to_gain(v: float) -> float:
        v = min(1.0, max(0.0, float(v)))
        return v * v                                  # a slider feels even this way

    @staticmethod
    def available() -> bool:
        return np is not None and sf is not None and sd is not None

    # ---- controls (any thread) ------------------------------------------------
    def set_volume(self, v: float) -> None:
        self.volume = min(1.0, max(0.0, float(v)))

    def set_paused(self, paused: bool) -> None:
        self.paused = bool(paused)

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        return self.paused

    def duck_for(self, seconds: float) -> None:
        """Keep the music ducked for `seconds` (+ DUCK_HOLD_S) from now."""
        self._duck_until = max(self._duck_until, time.time() + seconds + DUCK_HOLD_S)

    def play_track(self, track: "Track") -> None:
        """Cross-fade to `track` (the first one fades in)."""
        if not self._ensure_stream():
            return
        with self._lock:
            for v in self._voices:
                v.target = 0.0
            self._voices.append(_Voice(track))
            self.current = track

    def load_file(self, path: str, label: str = "", round_num: int = 0, take: int = 0,
                  on_ready=None, on_error=None) -> None:
        """Prepare a file on a worker thread (trim + loop), then play it -
        unless stop() was called meanwhile (a new story must not inherit it)."""
        gen = self._gen

        def work():
            try:
                tr = Track(path, label, round_num, take)
                if gen != self._gen:
                    return
                self.play_track(tr)
                if on_ready:
                    on_ready(tr)
            except Exception as e:
                self.error = str(e)
                print(f"  ✗ Music load failed ({os.path.basename(path)}): {e}", flush=True)
                if on_error:
                    on_error(str(e))
        threading.Thread(target=work, name="music-load", daemon=True).start()

    def stop(self) -> None:
        self._gen += 1
        with self._lock:
            self._voices = []
            self.current = None
        s, self._stream = self._stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass

    # ---- the stream ---------------------------------------------------------
    def _ensure_stream(self) -> bool:
        if self._stream is not None:
            return True
        if not self.available():
            self.error = "numpy / soundfile / sounddevice unavailable"
            return False
        try:
            self._stream = sd.OutputStream(samplerate=PLAYER_SR, channels=2,
                                           dtype="float32", latency="high",
                                           callback=self._callback)
            self._stream.start()
            return True
        except Exception as e:
            self.error = f"audio output failed: {e}"
            print(f"  ✗ Music {self.error}", flush=True)
            self._stream = None
            return False

    def _callback(self, outdata, frames, _time, _status):
        try:
            outdata[:] = self.render(frames)
        except Exception:
            outdata.fill(0)

    def render(self, n: int):
        """The next n frames of the mix (the callback's body; testable)."""
        sr = PLAYER_SR
        vol, self._vol_gain = _ramp(self._vol_gain, self._vol_to_gain(self.volume), 0.15, n, sr)
        pause, self._pause_gain = _ramp(self._pause_gain, 0.0 if self.paused else 1.0,
                                        PAUSE_FADE_S, n, sr)
        ducked = time.time() < self._duck_until
        duck_target = 10 ** (DUCK_DB / 20.0) if ducked else 1.0
        duck, self._duck_gain = _ramp(self._duck_gain, duck_target,
                                      DUCK_ATTACK_S if ducked else DUCK_RELEASE_S, n, sr)
        out = np.zeros((n, 2), dtype=np.float32)
        if self._pause_gain == 0.0 and pause[0] == 0.0:
            return out                                  # paused: hold position
        with self._lock:
            voices = list(self._voices)
        for v in voices:
            g, v.gain = _ramp(v.gain, v.target, TRACK_XFADE_S, n, sr)
            out += v.track.frames(v.pos, n) * g[:, None]
            v.pos += n
        with self._lock:
            self._voices = [v for v in self._voices if not (v.target == 0.0 and v.gain == 0.0)]
        out *= (vol * pause * duck)[:, None]
        return out
