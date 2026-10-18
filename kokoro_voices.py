"""
kokoro_voices.py  —  Layer 1: Character trait → voice blend selector
Install: pip install kokoro soundfile sounddevice numpy

CONCEPT
=======
A character is described by four continuous traits (0.0 → 1.0) plus a
formality flag. The selector maps those traits to a primary voice, a
secondary voice, a blend weight, and a speed. No LLM calls — pure math.

TRAIT AXES
==========
  masculinity     0.0 = very feminine   1.0 = very masculine
  authority       0.0 = light/young     1.0 = heavy/commanding
  age             0.0 = young adult     1.0 = elderly
  emotional_base  -1.0 = anxious/fast   0.0 = neutral   +1.0 = melancholic/slow
  formality       False = casual        True  = pulls secondary toward British

PRIMARY VOICE SELECTION
=======================
Male characters   → primary always from am_ pool (authority decides which)
Female characters → primary always from af_ pool (authority decides which)
Formality=True    → primary shifts toward bm_ / bf_ regardless of gender

SECONDARY VOICE SELECTION
=========================
Male character:
  masculinity < 0.5  → secondary is female (af_ or bf_), weight = (0.5 - masculinity)
  masculinity >= 0.5 → secondary is male from a different authority tier
  formality=True     → secondary pulls toward British male

Female character:
  masculinity > 0.5  → secondary is male (am_ or bm_), weight = (masculinity - 0.5)
  masculinity <= 0.5 → secondary is female from adjacent authority tier
  formality=True     → secondary pulls toward British female

SECONDARY WEIGHT CAP
====================
Secondary weight is capped at 0.45 so the primary always dominates.
The primary weight is always (1.0 - secondary_weight).

SPEED DERIVATION
================
  age_speed       = 0.9 + 0.2 * (1.0 - age)     young=1.1  old=0.9
  emotion_speed   = emotional_base * -0.1         anxious=+0.1  melancholic=-0.1
  base_speed      = age_speed + emotion_speed

MOOD OFFSET  (applied at scene/event level on top of base_speed)
============
  tense      -0.10    serious, threatening
  angry      -0.10    controlled fury (slower, deliberate)
  grieving   -0.15    heaviest slowdown
  suspicious -0.05    slight caution
  neutral     0.00
  joyful     +0.10
  scared     +0.10    faster, breathless
  excited    +0.15    most energetic

VOICE QUALITY REFERENCE
========================
AMERICAN ENGLISH  (lang_code = "a")
  af_heart    female  A     best overall female
  af_bella    female  A-    warm, high quality
  af_nicole   female  B-    headphone-recorded feel
  af_sarah    female  C+    reliable general use
  af_aoede    female  C+
  af_kore     female  C+    suits older female
  am_fenrir   male    C+    best quality male
  am_michael  male    C+    solid, authoritative
  am_puck     male    C+    lighter, younger
  am_onyx     male    D     deepest tone
  am_echo     male    D     lighter
  am_eric     male    D     older feel

BRITISH ENGLISH  (lang_code = "b")
  bf_emma     female  B-    best British female
  bf_isabella female  C     lighter British female
  bm_george   male    C     best British male
  bm_fable    male    C     character feel
  bm_daniel   male    D

SPANISH  (lang_code = "e")  — exotic ring in English
  ef_dora     female
  em_alex     male

FRENCH  (lang_code = "f")   — fancy ring in English
  ff_siwis    female
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np

# =============================================================================
#  SECTION 1 — VOICE POOLS
#
#  Each entry is (authority_score, voice_id).
#  Authority score is a float 0.0→1.0 representing where that voice sits
#  on the light/commanding spectrum. The selector picks the closest match
#  to the character's authority trait.
# =============================================================================

# American male — primary pool for male characters
_AM_POOL = [
    (0.15, "am_puck"),       # lightest, youngest
    (0.35, "am_echo"),       # light
    (0.55, "am_fenrir"),     # best quality, mid authority
    (0.70, "am_michael"),    # solid, authoritative
    (0.85, "am_onyx"),       # deep, commanding
    (0.95, "am_eric"),       # older, heavy
]

# British male — secondary pool when formality=True for male
_BM_POOL = [
    (0.30, "bm_fable"),      # lighter British
    (0.55, "bm_daniel"),     # mid
    (0.80, "bm_george"),     # authoritative British
]

# American female — primary pool for female characters
_AF_POOL = [
    (0.20, "af_heart"),      # lightest, brightest
    (0.35, "af_bella"),      # warm, light-mid
    (0.50, "af_nicole"),     # mid
    (0.65, "af_sarah"),      # mid-heavy
    (0.80, "af_aoede"),      # heavier
    (0.95, "af_kore"),       # heaviest, suits older
]

# British female — secondary pool when formality=True for female
_BF_POOL = [
    (0.35, "bf_isabella"),   # lighter British female
    (0.75, "bf_emma"),       # authoritative British female
]


def _closest(pool: list[tuple[float, str]], target: float) -> str:
    """Return the voice ID whose authority score is closest to target."""
    return min(pool, key=lambda item: abs(item[0] - target))[1]


def _second_closest(pool: list[tuple[float, str]], target: float) -> str:
    """Return the voice ID with the second-closest authority score to target."""
    sorted_pool = sorted(pool, key=lambda item: abs(item[0] - target))
    return sorted_pool[1][1] if len(sorted_pool) > 1 else sorted_pool[0][1]


# =============================================================================
#  SECTION 2 — MOOD OFFSETS
# =============================================================================

MOOD_OFFSETS: dict[str, float] = {
    "grieving":   -0.15,
    "tense":      -0.10,
    "angry":      -0.10,
    "suspicious": -0.05,
    "neutral":     0.00,
    "joyful":     +0.10,
    "scared":     +0.10,
    "excited":    +0.15,
}


# =============================================================================
#  SECTION 3 — CHARACTER PROFILE
# =============================================================================

@dataclass
class CharacterProfile:
    """
    Describes a character's voice traits. All floats are 0.0 → 1.0
    unless noted otherwise.

    Parameters
    ----------
    name             : Display name used in logs.
    gender           : "male" | "female"
    masculinity      : 0.0 = very feminine, 1.0 = very masculine.
                       For a male character, values below 0.5 blend in female voice.
                       For a female character, values above 0.5 blend in male voice.
    authority        : 0.0 = light/young, 1.0 = heavy/commanding.
                       Selects position within the primary voice pool.
    age              : 0.0 = young adult, 1.0 = elderly.
                       Drives the speed baseline.
    emotional_base   : -1.0 = anxious (faster), 0.0 = neutral, +1.0 = melancholic (slower).
                       Persistent personality trait, not per-scene mood.
    formality        : If True, secondary voice pulls toward British accent.
    lang_code        : Kokoro language code. Defaults to "a" (American English).
                       Change to "b" for British, "e" Spanish, "f" French, etc.
    """
    name:           str
    gender:         str   = "male"
    masculinity:    float = 0.8     # default: fairly masculine male
    authority:      float = 0.5     # default: mid authority
    age:            float = 0.3     # default: young-ish adult
    emotional_base: float = 0.0     # default: neutral
    formality:      bool  = False
    lang_code:      str   = "a"

    def resolve(self, mood: str = "neutral") -> "ResolvedVoice":
        """
        Derive primary voice, secondary voice, blend weight, and final speed
        from this profile plus an optional per-scene mood string.

        Returns a ResolvedVoice ready to pass to the Kokoro pipeline.
        """
        return _resolve_profile(self, mood)


@dataclass
class ResolvedVoice:
    """
    Output of the selector. Contains everything needed to synthesise speech.

    Pass voice_tensor directly to pipeline() as the voice argument.
    Pass speed directly as the speed argument.
    """
    character_name:  str
    primary_voice:   str
    secondary_voice: Optional[str]
    primary_weight:  float
    secondary_weight: float
    base_speed:      float
    mood:            str
    mood_offset:     float
    final_speed:     float
    voice_tensor:    Optional[object]  # numpy array after build_tensor() is called
    lang_code:       str

    def describe(self) -> str:
        """Human-readable summary for logging."""
        if self.secondary_voice:
            blend_str = (
                f"{self.primary_voice}({self.primary_weight:.0%}) + "
                f"{self.secondary_voice}({self.secondary_weight:.0%})"
            )
        else:
            blend_str = self.primary_voice
        return (
            f"[{self.character_name}]  "
            f"voice={blend_str}  "
            f"speed={self.final_speed:.2f}  "
            f"mood={self.mood}({self.mood_offset:+.2f})  "
            f"lang={self.lang_code}"
        )


# =============================================================================
#  SECTION 4 — SELECTOR LOGIC
# =============================================================================

def _resolve_profile(p: CharacterProfile, mood: str) -> ResolvedVoice:
    """Core selector — maps traits to voice IDs and weights."""

    # ── Primary voice ─────────────────────────────────────────────────────────
    if p.gender == "male":
        primary = _closest(_BM_POOL if p.formality else _AM_POOL, p.authority)
    else:
        primary = _closest(_BF_POOL if p.formality else _AF_POOL, p.authority)

    # ── Secondary voice and weight ────────────────────────────────────────────
    secondary        = None
    secondary_weight = 0.0

    if p.gender == "male":
        cross_gender_pull = max(0.0, 0.5 - p.masculinity)          # >0 when masculinity < 0.5
        if cross_gender_pull > 0.0:
            # Masculine deficit → blend in female voice
            secondary_weight = min(cross_gender_pull, 0.45)         # cap at 0.45
            secondary = _closest(_BF_POOL if p.formality else _AF_POOL, p.authority)
        else:
            # Stay male — blend a different authority tier for texture
            authority_contrast = 1.0 - p.authority                  # pull toward the opposite end
            secondary_weight   = 0.15                               # subtle same-gender blend
            pool = _BM_POOL if p.formality else _AM_POOL
            secondary = _second_closest(pool, authority_contrast)
            if secondary == primary:
                secondary = None
                secondary_weight = 0.0

    else:  # female
        cross_gender_pull = max(0.0, p.masculinity - 0.5)           # >0 when masculinity > 0.5
        if cross_gender_pull > 0.0:
            # Femininity deficit → blend in male voice
            secondary_weight = min(cross_gender_pull, 0.45)
            secondary = _closest(_BM_POOL if p.formality else _AM_POOL, p.authority)
        else:
            # Stay female — blend adjacent authority tier
            authority_contrast = 1.0 - p.authority
            secondary_weight   = 0.15
            pool = _BF_POOL if p.formality else _AF_POOL
            secondary = _second_closest(pool, authority_contrast)
            if secondary == primary:
                secondary = None
                secondary_weight = 0.0

    primary_weight = 1.0 - secondary_weight

    # ── Speed ─────────────────────────────────────────────────────────────────
    age_speed      = 0.9 + 0.2 * (1.0 - p.age)              # young=1.1  old=0.9
    emotion_speed  = p.emotional_base * -0.1                 # anxious=faster, melancholic=slower
    base_speed     = round(age_speed + emotion_speed, 3)

    mood_offset    = MOOD_OFFSETS.get(mood.lower(), 0.0)
    final_speed    = round(max(0.5, min(1.5, base_speed + mood_offset)), 3)

    return ResolvedVoice(
        character_name   = p.name,
        primary_voice    = primary,
        secondary_voice  = secondary,
        primary_weight   = primary_weight,
        secondary_weight = secondary_weight,
        base_speed       = base_speed,
        mood             = mood,
        mood_offset      = mood_offset,
        final_speed      = final_speed,
        voice_tensor     = None,          # populated by build_tensor()
        lang_code        = p.lang_code,
    )


# =============================================================================
#  SECTION 5 — TENSOR BUILDER
#
#  Requires a KPipeline instance. Separated from the selector so the math
#  layer (this file) can be used and tested without Kokoro installed.
# =============================================================================

def build_tensor(resolved: ResolvedVoice, pipeline) -> ResolvedVoice:
    """
    Load voice tensors from the pipeline and compute the blend.
    Returns a new ResolvedVoice with voice_tensor populated.

    Parameters
    ----------
    resolved : ResolvedVoice from CharacterProfile.resolve()
    pipeline : KPipeline instance (already constructed)
    """
    t_primary = pipeline.load_voice(resolved.primary_voice)

    if resolved.secondary_voice:
        t_secondary   = pipeline.load_voice(resolved.secondary_voice)
        voice_tensor  = resolved.primary_weight * t_primary + resolved.secondary_weight * t_secondary
    else:
        voice_tensor  = t_primary

    return ResolvedVoice(
        character_name   = resolved.character_name,
        primary_voice    = resolved.primary_voice,
        secondary_voice  = resolved.secondary_voice,
        primary_weight   = resolved.primary_weight,
        secondary_weight = resolved.secondary_weight,
        base_speed       = resolved.base_speed,
        mood             = resolved.mood,
        mood_offset      = resolved.mood_offset,
        final_speed      = resolved.final_speed,
        voice_tensor     = voice_tensor,
        lang_code        = resolved.lang_code,
    )


# =============================================================================
#  SECTION 6 — PRESET ARCHETYPES
#
#  Ready-made profiles for common character types.
#  Override any field when instantiating your own characters.
# =============================================================================

NARRATOR = CharacterProfile(
    name="Narrator", gender="female",
    masculinity=0.4, authority=0.6, age=0.4,
    emotional_base=0.0, formality=False,
)

YOUNG_HERO = CharacterProfile(
    name="Young Hero", gender="male",
    masculinity=0.65, authority=0.3, age=0.05,
    emotional_base=-0.2,             # slightly anxious baseline
    formality=False,
)

ELDER = CharacterProfile(
    name="Elder", gender="male",
    masculinity=0.85, authority=0.9, age=0.9,
    emotional_base=0.3,              # slightly melancholic
    formality=True,                  # formal, measured
)

VILLAIN = CharacterProfile(
    name="Villain", gender="male",
    masculinity=0.9, authority=0.95, age=0.5,
    emotional_base=0.1,
    formality=True,
)

SCHOLAR = CharacterProfile(
    name="Scholar", gender="female",
    masculinity=0.35, authority=0.65, age=0.35,
    emotional_base=0.1,
    formality=True,
)

# Debate engine presets — drop-in for chatimage.py
SCIENTIST_PROFILE = CharacterProfile(
    name="Scientist", gender="male",
    masculinity=0.75, authority=0.7, age=0.35,
    emotional_base=0.0, formality=False,
)

PHILOSOPHER_PROFILE = CharacterProfile(
    name="Philosopher", gender="female",
    masculinity=0.3, authority=0.55, age=0.4,
    emotional_base=0.2,              # thoughtful, slightly slow
    formality=True,
)


# =============================================================================
#  SECTION 7 — DEMO  (run this file directly to hear all archetypes)
# =============================================================================

DEMO_TEXT = """
Introduction.
Welcome, adventurers, to the realm of Elyria — a land of magic and wonder.
You are brave souls chosen to uncover the secrets of a long-lost temple
hidden deep within the Whispering Woods.
Will you be the exception?
"""

DEMO_CHARACTERS = [
    (NARRATOR,          "neutral"),
    (YOUNG_HERO,        "scared"),
    (ELDER,             "tense"),
    (VILLAIN,           "angry"),
    (SCHOLAR,           "neutral"),
    (SCIENTIST_PROFILE, "neutral"),
    (PHILOSOPHER_PROFILE,"grieving"),
]


def run_demo():
    """Synthesise DEMO_TEXT for every preset archetype and save to demo_output/."""
    import os
    import soundfile as sf
    import sounddevice as sd

    try:
        from kokoro import KPipeline
    except ImportError:
        print("kokoro not installed — run: pip install kokoro")
        return

    os.makedirs("demo_output", exist_ok=True)

    # Cache pipelines by lang_code
    pipelines: dict[str, KPipeline] = {}

    for profile, mood in DEMO_CHARACTERS:
        resolved = profile.resolve(mood=mood)
        print(resolved.describe())

        lang = resolved.lang_code
        if lang not in pipelines:
            pipelines[lang] = KPipeline(lang_code=lang, repo_id='hexgrad/Kokoro-82M')

        resolved = build_tensor(resolved, pipelines[lang])

        samples = []
        for _, _, audio in pipelines[lang](DEMO_TEXT, voice=resolved.voice_tensor, speed=resolved.final_speed):
            samples.append(audio)

        import numpy as np
        audio_out  = np.concatenate(samples)
        safe_name  = profile.name.lower().replace(" ", "_")
        output_path = f"demo_output/{safe_name}_{mood}.wav"
        sf.write(output_path, audio_out, 24000)
        print(f"  ✓ Saved: {output_path}")

        sd.play(audio_out, samplerate=24000)
        sd.wait()

    print("\nDemo complete. Files written to demo_output/")


if __name__ == "__main__":
    # Print what each preset resolves to without needing Kokoro installed
    print("Character voice resolutions (no audio):\n")
    for profile, mood in DEMO_CHARACTERS:
        resolved = profile.resolve(mood=mood)
        print(resolved.describe())

    print()
    answer = input("Run full audio demo? [y/N]: ").strip().lower()
    if answer == "y":
        run_demo()
