"""
story_lab_metrics.py — the measuring instrument, with its own test suite.

WHY THIS EXISTS
===============
The engine has 200+ unit checks. Until now the MEASUREMENT code had none, and
every metric written ad hoc during an analysis went straight into a conclusion
unvalidated. Four errors followed in a single session:

  * D-02 read 144 on bag-of-words overlap; true near-verbatim count was 0.
  * D-01 read 8 by matching "You are " — which caught the dialogue line
    "You are strong,"; then MISSED 5 more by not matching the "What matters
    about" variant. Wrong in both directions on the same question.
  * cap-cut read 5% by one detector and 36% by another; never reconciled.
  * v9.1 read "+18.3pt speech" — an artifact. The intervention moved narration
    out of asterisks into bare prose, and a stage-direction VERB LIST counted
    the result as speech because "lean" was not in the list.

The last one is the important one: a metric that infers a semantic category
from surface patterns is only valid while the output keeps the shape the
patterns were written for. An intervention that changes the shape invalidates
the metric silently, and it does so exactly when the metric is being used to
judge that intervention.

THE ARCHITECTURE THAT FOLLOWS FROM THAT
=======================================
TIER 1 — assumption-free. Counts what the MARKUP says, never what a heuristic
    infers: words inside *asterisks*, words inside "quotes", words in neither.
    The harness controls those delimiters. Nothing here can be fooled by a
    change in writing style, and these are the PRIMARY numbers.

TIER 2 — the bare bucket only. Bare runs are genuinely ambiguous (speech
    without quote marks, or narration without asterisks), so they get a
    classifier — and the classifier's accuracy is MEASURED against a
    hand-labelled gold set spanning five engine eras, including the v9.1 shape
    that broke the previous one. See test_metrics.py.

RULE OF THUMB: report Tier 1 always. Report Tier 2 only with its accuracy
attached. If the two disagree about a conclusion, Tier 1 wins.

Field practice this follows (see loop_reports + the good-roleplay skill):
gold sets of ~200 items, agreement reported rather than assumed, and judges
from a different model family than the generator.
"""
from __future__ import annotations

import re
from collections import Counter

# ---------------------------------------------------------------- TIER 1 ----

_BEAT_RE  = re.compile(r"\*+[^*]+\*+")
_QUOTE_RE = re.compile(r"[\"“][^\"”]+[\"”]")
_WORD_RE  = re.compile(r"[A-Za-z']+")

MARKED, QUOTED, BARE = "marked", "quoted", "bare"


def wc(text: str) -> int:
    """Word count. One definition, used everywhere, so totals reconcile."""
    return len(_WORD_RE.findall(text))


def strip_speaker(block: str) -> str:
    """'Rosa: *beat* "line"' -> '*beat* "line"'."""
    return re.sub(r"^[A-Z][a-zA-Z]{1,12}:\s*", "", block).strip()


def is_orphan_quote(text: str) -> str | None:
    """
    Does this unpaired run carry an orphan quote mark — i.e. did the model MARK
    it as speech and only break the pair?

    Found by hand-auditing the gold set: 32 of 200 bare runs opened or closed
    with a lone quote, and all 32 were speech. 100%, no exceptions. The signal
    was sitting inside the item and the segmenter was discarding it, which put
    the LEAST ambiguous runs in the corpus into the ambiguous bucket — and
    undercounted the primary metric by 18-25% per arm.

    Still Tier 1: this reads a delimiter, not meaning. Returns which end the
    orphan sits on, for diagnostics.
    """
    s = text.strip()
    if s.startswith(('"', "“")):
        return "open"
    if s.endswith(('"', "”")):
        return "close"
    return None


def segments(line: str) -> list[tuple[str, str]]:
    """
    Split ONE dialogue line into (kind, text) segments, in document order.

    Beats are extracted FIRST because asterisks are the reliable delimiter:
    measured across five arms, 0% of lines carry an odd asterisk count, while
    15-29% carry an odd quote count. Parsing quotes first lets an orphan quote
    swallow a whole beat and mis-file it as speech.
    """
    out: list[tuple[str, str]] = []
    for chunk in re.split(r"(\*+[^*]+\*+)", line):
        if not chunk or not chunk.strip():
            continue
        if chunk.startswith("*"):
            out.append((MARKED, chunk))
            continue
        for piece in re.split(r"([\"“][^\"”]+[\"”])", chunk):
            if not piece or not piece.strip():
                continue
            if piece[0] in '"“':
                out.append((QUOTED, piece))          # properly paired
            elif is_orphan_quote(piece):
                out.append((QUOTED, piece))          # marked speech, broken pair
            else:
                out.append((BARE, piece))
    return out


def word_flow(lines) -> dict:
    """
    TIER 1 PRIMARY METRIC. Words by markup class over a corpus of lines.

    `quoted_per_line` is the headline: it is the only speech measure that
    CANNOT be inflated by unmarking narration, which is the failure mode that
    produced v9.1's phantom +18.3pt.
    """
    tot = Counter()
    n = 0
    orphan_w = 0
    for line in lines:
        body = strip_speaker(line)
        if not body:
            continue
        n += 1
        for kind, text in segments(body):
            tot[kind] += wc(text)
            if kind == QUOTED:
                s = text.strip()
                paired = len(s) >= 2 and s[0] in '"“' and s[-1] in '"”'
                if not paired:            # counted as speech via a BROKEN pair
                    orphan_w += wc(text)
    total = tot[MARKED] + tot[QUOTED] + tot[BARE]
    return {
        "lines": n,
        "marked_action_w": tot[MARKED],
        "quoted_speech_w": tot[QUOTED],
        "bare_w": tot[BARE],
        "total_w": total,
        "orphan_quoted_w": orphan_w,     # subset of quoted_speech_w, for transparency
        "quoted_per_line": round(tot[QUOTED] / n, 2) if n else 0.0,
        "words_per_line": round(total / n, 1) if n else 0.0,
        "marked_pct": round(100 * tot[MARKED] / total, 1) if total else 0.0,
        "quoted_pct": round(100 * tot[QUOTED] / total, 1) if total else 0.0,
        "bare_pct": round(100 * tot[BARE] / total, 1) if total else 0.0,
    }


def conservation_ok(flow: dict) -> bool:
    """marked + quoted + bare must equal total. Catches parser drift."""
    return (flow["marked_action_w"] + flow["quoted_speech_w"]
            + flow["bare_w"]) == flow["total_w"]


def markup_health(lines) -> dict:
    """
    Markup defects that need no semantic judgement at all. Every one of these
    is a literal count of delimiters, so all are Tier 1.
    """
    n = odd_ast = odd_q = dbl_q = beat_in_q = 0
    for line in lines:
        b = strip_speaker(line)
        if not b:
            continue
        n += 1
        if b.count("*") % 2:
            odd_ast += 1
        if (b.count('"') + b.count("“") + b.count("”")) % 2:
            odd_q += 1
        if '""' in b.replace('" "', "§"):
            dbl_q += 1
        if any("*" in s for s in b.split('"')[1::2]):
            beat_in_q += 1
    pct = lambda x: round(100 * x / n, 1) if n else 0.0
    return {"lines": n, "odd_asterisk_pct": pct(odd_ast), "odd_quote_pct": pct(odd_q),
            "doubled_quote_pct": pct(dbl_q), "beat_inside_quote_pct": pct(beat_in_q)}


# ---------------------------------------------------------------- TIER 2 ----
# Bare runs only. Everything below is a HYPOTHESIS about language and must be
# reported with the accuracy that test_metrics.py measures against the gold set.

_BODY = frozenset("""voice eyes eye face hand hands finger fingers jaw head shoulder
shoulders chest throat mouth lips gaze expression breath arm arms feet foot knuckles
brow chin neck spine posture stance grip""".split())

_SPEECH_ACT = frozenset("""say says said reply replies replied respond responds responded
murmur murmurs murmured mutter mutters muttered add adds added continue continues
continued ask asks asked whisper whispers whispered state states stated admit admits
admitted agree agrees agreed remark remarks remarked answer answers answered echo
echoes echoed repeat repeats repeated offer offers offered""".split())

_STAGE_VERB = frozenset("""lean leans leaning lower lowers shift shifts turn turns
pause pauses step steps place places raise raises nod nods glance glances look looks
move moves clutch clutches grip grips kneel kneels stand stands watch watches feel feels
draw draws reach reaches press presses tighten tightens breathe breathes smile smiles
frown frowns sigh sighs gesture gestures point points hold holds cross crosses drop drops
lift lifts tilt tilts narrow narrows spin spins whip whips blink blinks swallow swallows
clench clenches catch catches grab grabs slide slides settle settles rise rises fall falls
flicker flickers drum drums trail trails hang hangs carry carries""".split())

_FIRST_SUBJ = frozenset("i my his her their its our".split())

_NLP = None
_STRUCT_CACHE: dict[str, int] = {}


def _structural_narration(sent: str) -> int:
    """
    Structural narration signal from the dependency parse, worth +2.

    Fires on "<pronoun subject> <verb> <object|prepositional phrase>" — the
    shape of a stage direction: "I take a tiny step toward the edge",
    "I regard him with cold deliberation". It exists because the word-list
    features miss any verb nobody thought to list, which is the brittleness
    that produced the v9.1 error in the first place; a parse generalises where
    a list cannot.

    NOTE — the obvious companion feature, "subject is a common noun rather
    than a person" ("The rain intensifies"), was TESTED AND REJECTED: on the
    development half it lifted recall 0.65 -> 0.74 but dropped precision
    0.88 -> 0.61, because spoken lines have noun subjects too ("The civilians
    need us ready"). Measured, not assumed.

    Degrades to 0 if spaCy is unavailable, so the module still runs; the suite
    reports the accuracy that actually applies.
    """
    global _NLP
    if sent in _STRUCT_CACHE:
        return _STRUCT_CACHE[sent]
    if _NLP is None:
        try:
            import spacy
            _NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
        except Exception as e:
            # Degrading is allowed; degrading SILENTLY is not. A cold-start
            # load failure (2026-09-28: one suite run in seven after three
            # idle days) flipped a classification and would change the
            # engine's history view for a whole run with no trace in its log.
            print(f"  ! story_lab_metrics: spaCy unavailable, structural "
                  f"feature off for this process ({type(e).__name__}: {e})",
                  flush=True)
            _NLP = False
    if _NLP is False:
        return 0
    val = 0
    for t in _NLP(sent):
        if t.dep_ == "nsubj" and t.text.casefold() in ("i", "he", "she", "they"):
            if t.head.pos_ == "VERB" and any(c.dep_ in ("dobj", "prep") for c in t.head.children):
                val = 2
                break
    _STRUCT_CACHE[sent] = val
    return val


def classify_bare(run: str) -> str:
    """
    TIER 2. One BARE run -> "SPEECH" or "NARRATION".

    Rule, not a trained model, so it stays inspectable. The features are the
    linguistic difference between describing and addressing:
      NARRATION describes a body, an action, or the manner of speaking.
      SPEECH addresses someone — questions, exclamations, second person.

    Deliberately NOT tuned to the gold set beyond choosing the threshold on a
    development half; test_metrics.py reports held-out accuracy per era.
    """
    s = run.strip()
    low = s.casefold()
    toks = _WORD_RE.findall(low)
    if not toks:
        return "SPEECH"
    score = 0

    # subject + stage verb in the opening (the classic stage-direction shape)
    if toks[0] in _FIRST_SUBJ or toks[0] in {"he", "she", "they", "the", "a"}:
        if any(t in _STAGE_VERB for t in toks[1:4]):
            score += 2
    # possessive + body part ("my voice", "his fingers")
    for i, t in enumerate(toks[:-1]):
        if t in _FIRST_SUBJ and toks[i + 1] in _BODY:
            score += 2
            break
    # a speech-act framing verb = describing the act of speaking, not speaking
    if any(t in _SPEECH_ACT for t in toks):
        score += 2
    # dependency-parse shape, for the verbs no list contains
    score += _structural_narration(s)
    # addressed-speech signals push the other way
    if "?" in s:
        score -= 3
    if "!" in s:
        score -= 2
    if any(t in {"you", "your", "you're", "yours"} for t in toks):
        score -= 2
    if re.search(r"\b[A-Z]{3,}\b", s):          # shouted caps
        score -= 2
    return "NARRATION" if score >= 2 else "SPEECH"


_STRONG = 2          # score at/above which NARRATION is asserted outright
_STRONG_SPEECH = -2  # score at/below which SPEECH is asserted outright


def _bare_score(run: str) -> int:
    """The raw feature score behind classify_bare, exposed for the sequential
    classifier so it can tell a CONFIDENT call from a coin-flip."""
    s = run.strip()
    toks = _WORD_RE.findall(s.casefold())
    if not toks:
        return 0
    score = 0
    if toks[0] in _FIRST_SUBJ or toks[0] in {"he", "she", "they", "the", "a"}:
        if any(t in _STAGE_VERB for t in toks[1:4]):
            score += 2
    for i, t in enumerate(toks[:-1]):
        if t in _FIRST_SUBJ and toks[i + 1] in _BODY:
            score += 2
            break
    if any(t in _SPEECH_ACT for t in toks):
        score += 2
    score += _structural_narration(s)
    if "?" in s:
        score -= 3
    if "!" in s:
        score -= 2
    if any(t in {"you", "your", "you're", "yours"} for t in toks):
        score -= 2
    if re.search(r"\b[A-Z]{3,}\b", s):
        score -= 2
    return score


def classify_bare_run(run: str) -> list[tuple[str, str]]:
    """
    Label EVERY sentence of one bare run, in order, with INHERITANCE.

    Why sequential. Two facts from the gold set pull in opposite directions and
    only a sequential rule satisfies both:

      * a bare run can contain BOTH modes, so labelling whole runs is wrong.
        (id 16 "Oh shoot sorry Bobb I'm making everything worse aren't I?" =
        speech, immediately followed inside the SAME run by id 22 "The sparks
        fade down to just little tingles around my fingertips" = narration.)

      * a sentence torn out of its run is often undecidable, so labelling
        sentences independently is also wrong. (id 39 "My lightning could
        probably blast away some rubble but what if it hurts them instead?"
        reads as thought alone, but directly follows "Bobb please tell me you
        know how to get them out safely?!" with no break — she is still
        talking. The second annotator got this right and the isolated
        classifier could not.)

    So: a sentence with STRONG evidence decides for itself; a sentence with
    weak evidence inherits the mode of the sentence before it. Inheritance does
    NOT cross a beat or a quoted span — those end the run — because a bare run
    following a quote is usually a speech tag ("he says quietly"), which is
    narration, not a continuation.

    *** MEASURED AND NOT ADOPTED (2026-08-03). ***
    On 151 gold items with recoverable parent runs this scored 84.8% against
    the isolated classifier's 86.1% — inheritance propagates a wrong call to
    the sentences after it, and that costs more than the context gains.

    The motivating case turned out not to need it either: id 39 scores SPEECH
    in isolation anyway, because its question mark alone is decisive. The
    disagreement there was annotator-vs-annotator, never a classifier failure
    — and adjudication moved the GOLD LABEL, not the code.

    Kept, unused, because the reasoning is sound enough that someone will
    propose it again; this is the record that it was tried and measured.
    `speech_action_split` deliberately calls `classify_bare`, not this.
    """
    out: list[tuple[str, str]] = []
    prev: str | None = None
    for sent in re.split(r"(?<=[.!?])\s+", run):
        s = sent.strip()
        if not s:
            continue
        if wc(s) < 4:                      # too short to carry evidence
            mode = prev or "SPEECH"
        else:
            sc = _bare_score(s)
            if sc >= _STRONG:
                mode = "NARRATION"
            elif sc <= _STRONG_SPEECH:
                mode = "SPEECH"
            else:
                mode = prev or "SPEECH"    # weak evidence -> inherit
        out.append((mode, s))
        prev = mode
    return out


def speech_action_split(lines) -> dict:
    """
    TIER 1 + TIER 2 combined: the full speech/action picture.
    ALWAYS returns the Tier 1 flow alongside, so the assumption-free numbers
    travel with the inferred ones and a reader can see which is which.
    """
    flow = word_flow(lines)
    sp = nar = 0
    for line in lines:
        for kind, text in segments(strip_speaker(line)):
            if kind != BARE:
                continue
            for sent in re.split(r"(?<=[.!?])\s+", text):
                if wc(sent) < 4:
                    sp += wc(sent)                    # too short to judge
                    continue
                if classify_bare(sent) == "NARRATION":
                    nar += wc(sent)
                else:
                    sp += wc(sent)
    speech = flow["quoted_speech_w"] + sp
    action = flow["marked_action_w"] + nar
    return {**flow,
            "bare_speech_w": sp, "bare_narration_w": nar,
            "speech_w": speech, "action_w": action,
            "speech_pct_tier2": round(100 * speech / (speech + action), 1)
            if speech + action else 0.0}


# ------------------------------------------------------- MEMORY CHANNEL ----

def memory_health(run_dirs) -> dict:
    """
    Is the memory channel still alive, or has it gone useless / recycled?

    Memory FEEDS the next round's dialogue, so a defect here compounds in a way
    a bad spoken line does not — which is why the rubric weights it heavier.
    Three failure modes, all with history in this project:

      RECYCLED  consecutive memories for one character repeat each other. The
                engine guards this at _MEMORY_SEVERE_REPEAT = 10 words, using
                _longest_shared_run; we reuse BOTH so the number means the same
                thing here as it does inside the guard.
      USELESS   the memory never surfaces in later dialogue. Measured as
                content-word carry-over into the next round — and reported
                WITH a shuffled control, because the naive figure has an ~81%
                floor (two texts about the same scene share vocabulary
                whatever happens). Only the lift over control is evidence.
      DRIFTED   written in the wrong person. The keeper asks for second person;
                v8.1's anchor-then-withdraw collapsed it and the drift was
                never reverted.

    Checked on EVERY arm from now on, because the speech work changes what the
    keeper reads, and 'we did not break memory' should be measured, not hoped.
    """
    import glob as _glob, os as _os, random as _random, statistics as _stat
    import story_lab_engine8 as _E

    stop = set("the a an and or but of to in on at by for with from into is are "
               "was were be been it its this that they them he she his her you your "
               "i my we our not no as if when then there here what how who".split())
    def _cw(s):
        return {w for w in re.findall(r"[a-z']{4,}", s.lower()) if w not in stop}

    runs, sev, pairs, second, n, lens = [], 0, 0, 0, 0, []
    hits = trials = 0
    pool = []
    for d in run_dirs:
        for slot in ("a", "b"):
            prev = None
            for rd in range(1, 8):
                f = _os.path.join(d, f"round_{rd:02d}_memory_{slot}.txt")
                if not _os.path.exists(f):
                    continue
                t = open(f, encoding="utf-8", errors="replace").read().strip()
                if not t:
                    continue
                n += 1
                lens.append(wc(t))
                low = [w.casefold() for w in _WORD_RE.findall(t)]
                you_n = sum(1 for w in low if w in ("you", "your", "yours"))
                me_n = sum(1 for w in low if w in ("i", "me", "my", "mine"))
                if you_n > me_n:
                    second += 1
                if prev:
                    r = _E._longest_shared_run(t, prev)
                    runs.append(r)
                    pairs += 1
                    if r >= _E._MEMORY_SEVERE_REPEAT:
                        sev += 1
                nd = _os.path.join(d, f"round_{rd+1:02d}_dialogue.txt")
                if _os.path.exists(nd):
                    pool.append((t, open(nd, encoding="utf-8", errors="replace").read()))
                prev = t
    for t, dial in pool:
        c = _cw(t)
        if not c:
            continue
        trials += 1
        if len(c & _cw(dial)) / len(c) >= 0.15:
            hits += 1
    _random.seed(0)
    ctrl = 0
    for t, _ in pool:
        c = _cw(t)
        if not c:
            continue
        other = _random.choice(pool)[1]
        if len(c & _cw(other)) / len(c) >= 0.15:
            ctrl += 1
    return {
        "memories": n,
        "mean_len_w": round(_stat.mean(lens), 0) if lens else 0,
        "recycle_mean_w": round(_stat.mean(runs), 1) if runs else 0,
        "recycle_max_w": max(runs) if runs else 0,
        "severe_repeats": sev, "pairs": pairs,
        "second_person_pct": round(100 * second / n, 0) if n else 0,
        "uptake_pct": round(100 * hits / trials, 0) if trials else 0,
        "uptake_control_pct": round(100 * ctrl / trials, 0) if trials else 0,
        "uptake_lift_pt": round(100 * (hits - ctrl) / trials, 0) if trials else 0,
    }
