"""
story_lab_engine12.py  —  Story Lab v12.4  //  Ollama text generation layer

WHAT CHANGED IN v12.4  (user-designed 2026-10-17: background music)
====================================================================
Instrumental music for every scene, by ACE-Step 1.5 in ComfyUI. The
engine's part is a new helper role, the COMPOSER: generate_music_field()
asks one question per call - which SOUNDTRACK the world suits (once per
game, one word from the closed list MUSIC_SOUNDTRACKS) and the scene's
MOOD (every round, from the opener and the player's event). Everything
musical - palettes, tempo, key, the prose caption ACE-Step reads - is
authored in story_lab_music12: two probes asked this model to write the
music itself and it wrote track titles and "Hedwig's Theme" (the block's
note has the numbers). New: MAX_TOKENS/GENERATION_PARAMS["music_field"].
Only the director calls it, only when music is on.

WHAT CHANGED IN v12.3  (user-designed 2026-10-17: Cinematic scenes)
====================================================================
An optional second scene style. "Classical" is v12.1's characterless scene
and makes exactly v12.2's calls. "Cinematic" draws both leads IN the scene,
as the story has them right now, with an Anima checkpoint (two people kept
apart by one sentence each - measured in loop_reports/v12_3_cinematic/). The
engine's part is a new helper role, the CINEMATOGRAPHER: generate_cine_field()
asks one question per call - a lead's LOOKS (once, no clothes), what each
lead is WEARING (carried over from the last round, the player's event
nearest the cue), what each is doing RIGHT NOW, and who ELSE is in view.
New: MAX_TOKENS/GENERATION_PARAMS["cine_field"]. Only the director calls it,
only in Cinematic mode.

WHAT CHANGED IN v12.2  (user-directed 2026-10-16: save games and a game seed)
=============================================================================
A GAME SEED: set_game_seed(master) makes every Ollama call of a game draw its
seed from one stream (derive_seed(master, "llm", call_index)), so the same
story, seed and player events replay the same text; game_seed_state() is what
a save game stores to resume the stream. Unset (the default, and the research
harness) the calls are exactly v12.1's - no seed key is sent. Nothing else in
the engine changed; saving and loading live in story_lab_saves12 and the
director.

WHAT CHANGED IN v12.1  (user-designed 2026-10-16: characterless scenes)
=======================================================================
The scene image's prompt is written by a new role, generate_scene_layers()
(the SCENE PAINTER), instead of v3's generate_scene_prompt(), which stays in
the file unused. The user's playtests (Vess/Kael, then Harry Potter and
"Dracona Malfoid") showed the old prompts were tiny, about people, and named
them - "Heels-click, stone-thump" for a castle hall full of sparks; "Dracona"
drawn as a dragon. The user's design: a longer prompt that takes in more of
the story (the world description for the first images, the setting, the
opener, the player's event), structured so what matters comes first, and a
characterless scene (people in the negative). Three layers, one call each:
PLACE, OBJECTS AND EFFECTS (what the moment leaves behind), LIGHT. The only
other change here: MAX_TOKENS["scene_layer"]. Hygiene and the prompt
wrappers (the new Picture prompts screen) live in story_lab_images12. The
measurement is loop_reports/v12_1_scene_prompts/.

WHAT v12.0 IS  (user-directed 2026-10-16: "preserve 11.6, make version 12")
===========================================================================
Engine v11.6 PROMOTED VERBATIM. Only the module title above, this note and
ENGINE_VERSION differ from story_lab_engine11.py; test_engine12.py proves it
for as long as the version reads 12.0 and retires the check at the first
behavioural change (the v11.0 pattern). v11.6 itself is frozen in
story_lab_engine11.py and in backups/v11.6_frozen_20261016/ with sha256 sums.

v12 is the IMAGE generation. story_lab_director12 adds a ComfyUI lane driven by
the two workflow JSON files (story_lab_images12) and story_lab_gui12 shows the
two portraits and the wide scene. Nothing in THIS file had to change for that:
every StoryCharacter already carries fp_image (extracted since v3) and
generate_scene_prompt() (the v3/v5 scene prompter, untouched since) already
turns an opener into CLIP keywords. The research harness story_lab_loop12
stays text-only.

NUM_GPU stays 99, measured 2026-10-16 on the RTX 5070 Ti laptop (12 227 MB):
Rocinante resident at num_ctx 16384 holds 10.18 GB, so it and the 6.5 GB SDXL
checkpoint cannot both live on the card. Run side by side, Windows pages VRAM
and both slow down (portrait 9.4 -> 13.6 s; the next LLM call 1.4 -> 6.2 s).
director12 instead HANDS the card over at two fixed points per round (unload
Ollama 1.2 s, free ComfyUI 1.7 s, reload Ollama 7.7 s) - see its header. The
CPU pin (NUM_GPU 0, the v5 design) was not needed.

The history below is v11.x's, kept as it was.

(v11.6 module title: story_lab_engine11.py  —  Story Lab v11.6  //  Ollama text generation layer)

WHAT CHANGED IN v11.6  (user-designed 2026-09-29: side-character takeovers)
===========================================================================
v11.3-v11.5 read 30 turns spent voicing someone else. 25 were a SIDE character
(Captain Oresh, the aliens, the shepherd boy "Astley", once the dragon) taking
the WHOLE turn while its owner said nothing - '"I promise you're safe here,"
*Oresh says softly*' as Kaya's line. 2 were shared turns, 2 the other main
character, 1 narration. None was on turn 1 (turn 2: 6, turn 3: 1, turns 4-6:
23). They cluster (iter 332 round 5: all three of Bobb's turns went to Astley)
and persist: Astley, coined in a Bobb turn, entered the resolution, the next
opener and both memories ("rely on Astley's magic support") and took 7 more
turns through round 5. v11.5: 16 D-09 on 168 event lines, the largest defect.
User's design: turns 1-3 run free - a one-turn takeover is creativity, a
round-long one is not - and from turn 4:
  REMINDER  only when one of the last two lines WAS a takeover, one line,
            "(Kaya speaks as herself.)", immediately before the cue (the slot
            where the name line once cut surname defects 12 -> 0). Otherwise
            the prompt is byte-identical to v11.5: it cannot go stale, cannot
            become a line-start attractor, cannot crowd out the event (whose
            window is turns 1-2). A name only - no story, nothing to parrot.
  GUARD     a turn-4+ draw that is itself a takeover is re-rolled once by the
            same arbiter, the retry carrying the reminder; if the retry is no
            better the first draw is kept (never worse). Every rejected draw
            is printed in full to the log so each firing can be read.
Detector (_is_takeover) built offline on all 576 v11.3-v11.5 lines: 22/26 of
the hand-read takeovers, 0/548 false positives, 0/2 shared turns - IN-SAMPLE,
so the live firings are the real test. Names count only if the NARRATOR side
holds them (setting, opener, event, memory); dialogue is where the garbles
live ('Asterns', 'Astutely', '*Voice chokes*').
Where a side character speaks instead: the event staging and the openers
already quote them; a character may still relay them or share a turn with
them - only a turn with NO own speech is a takeover.

REGISTERED BEFORE THE RUNS (4 runs, dragon storyline, 8 rounds x 6 turns, vs
v11.5's iters 332-335; the 168 event-following lines read blind with 42
re-test lines from the v11.5 batch; D-09 typed as in the v11.5 analysis):
  TARGET      rounds with two or more takeover turns 5 -> <= 1; takeover lines
              that ship on turns 4-6 10 -> <= 3
  GUARD RAILS reaction not worse than v11.5 (14.9/18) by more than 2/18; turns
              4-6 reacting not down by more than 8/84 (70); ignores <= 10; of
              the guard's rejected draws read, >= 2/3 genuine takeovers; the
              reminder spoken aloud in <= 2 lines; words/line within 10% of
              55.4; raw fallbacks 0
  ADOPT       target met and every rail holds
  REVERT      reaction worse by more than 2/18, or fewer than half of the
              guard's firings genuine, or the reminder spoken in > 2 lines
  OTHERWISE   keep, report the missed rail, replicate
  Reported, not ruled on: takeovers on turns 1-3 (free by design), whether
  side characters' information still reaches the story, reminder firings.

v11.5 RESULT (iters 332-335, sha b0af1ade; code in loop_saves/Loop332-335):
ADOPTED. Lost-quote lines 15 -> 0, odd-quote 14 -> 2, 0 junk shapes, words/
line 55.4. Read blind: 83% react (14.9/18), ignores 7, runs 35/36/34/34 - the
v11.4 replication passed (iter 328 was an outlier). D-12 49 -> 42; D-09 5 ->
16 (14 in 2 runs); a Bobb "*Ast..." opener attractor 8 -> 14 -> 23 lines over
v11.3/4/5. Report: loop_reports/v115_quotefix_report.md.

WHAT CHANGED IN v11.5  (user-directed 2026-09-29: the leading-quote strip)
=========================================================================
The dialogue cleanup ran raw.strip().lstrip('"') - a leftover from the open-
quote cue retired in v5.4, when the model could echo the cue's quote. Since
v5.4 the cue is a bare "Kaya:", so a leading quote is always the model's own
opening quote. Stripping it broke the line two ways:
  "Oh no!" *runs*         -> Oh no!" *runs*       (speech outside quotes)
  "We need to go NOW!"    -> We need to go NOW!   (the lone-quote unwrap then
                                                   took the closing one too)
v11.4's short lines open in speech more often: 15/192 lines lost their quotes
(v11.3: 4/192), 10 of v11.4's 49 D-12 register breaks on the event lines.
Fix: both .lstrip('"') calls deleted (after the name strip and after a leading
[bracket]). Two guards for the only risks the code allows:
  - the echoed-label strip accepts an optional leading quote and keeps it
    ('"Kaya: Hi."' -> '"Hi."'; before, the lstrip ran first and hid this)
  - a closing '"' right after , ; or : (_QUOTE_CONTINUES) is a cut before a
    dialogue tag, not the model's ending: '"Stay close,"' is trimmed back. More
    lines now have an even quote count, so this check matters more than before.
  The suite then caught a REAL regression the probe could not see (it compared
  cleaned text, not the re-roll checks): the event-parrot and duplicate checks
  compared exact text, and '"<the event>"' matched the beat only because the
  strip + unwrap removed both quotes. They now compare quote-blind
  (_quote_blind). And a cut line with no sentence end at all now gets its open
  quote closed ('"We have to go before the' -> '...the"').
Measured before shipping (scratchpad quote_probe*.py): 257 real turn prompts,
the SAME raw text through both cleanups. Turns 1/4: 0/129 raw outputs open with
a quote (no change). Kaya turns 3/5: 32/129 open with one, all 32 real speech
(0 wraps, 0 label echoes); odd-quote lines 27 -> 3, quote-less speech 3 -> 1,
0 lines differ in any WORD. The dialogue model itself already read re-paired
quotes (v9.2 view), so its input barely changes; keeper and resolver read the
raw lines and now get correct quotes. Tier-1 quoted words barely move (the
metrics already counted an orphan-quoted run as speech).

REGISTERED BEFORE THE RUNS (4 runs, dragon storyline, 8 rounds x 6 turns, vs
v11.4's iters 328-331):
  TARGET      lines that lost quotes (bare opening + closing quote, or speech
              with no quotes) 15/192 -> <= 3/192; odd-quote lines 14 -> <= 7;
              0 stored lines opening with an echoed label; lines ending ',"'
              <= 2
  GUARD RAILS words/line within 10% of 53.4; real truncations <= 5% (a closed
              *beat* without a period is not a cut - the v11.4 counter fault);
              quoted words/line >= 13.4; "no speech" redraws <= 10%; raw
              fallbacks 0; the length note spoken aloud in <= 2 lines
  ADOPT       target met and every rail holds
  REVERT      a junk-quote shape (a quote wrapping a *beat*, or an echoed
              label) in >= 3 lines, or words/line moves by more than 10%
  OTHERWISE   keep, report the missed rail, replicate
v11.4 REPLICATION, registered here because v11.5 should behave like v11.4 (the
fix changes quote marks only): the 168 event-following lines read blind with 42
re-test lines from the v11.4 batch. Ignores <= 11 (v11.3's same-hand 8 + 3) and
reaction within 2/18 of v11.3 -> iter 328 was an outlier and the short lines
stand. Ignores > 11 again -> the short-line cost is real; the next fix is the
event order in the opener seed, not more length work.

v11.4 RESULT (iters 328-331, sha 782f261c; code in loop_saves/Loop328-331):
words/line 70.9 -> 53.4, all of it action (quoted 14.98 -> 14.85, *action*
49.1 -> 31.6); reaction 84% -> 76% (run level -1.4 +/- 1.2 /18, rail held);
ignores 8 -> 17 (bar 11, MISSED; 9 in iter 328, every cluster began with an
opener or staging that dropped the event); cut counter 11% but 0 real
truncations (21/22 were model-closed beats without a period - counter fault);
defects/100 44 -> 51, 39 -> 40 excluding D-06. Neither adopted nor reverted.
Report: loop_reports/v114_shortlines_report.md.

WHAT CHANGED IN v11.4  (ONE package, user-directed 2026-09-29: shorter lines)
===========================================================================
Character lines ran ~71-77 words. The user asked for slightly shorter replies.
Two levers, measured on a paired probe of 64 real v11.3 turn prompts before
anything shipped (scratchpad brief_probe.py / cap_probe.py / cap_rubric.py):
  prompt wording alone        stage direction -1%, "(Keep X's reply short.)" -7%
                              -> fails a registered 10% bar (Law 4: wording
                              barely moves length on this model)
  dialogue token cap 110 -> 95            -18% words/line, reactions 80% = 80%
  cap 95 + "(Keep X's next reply short.)"  -20% words/line, reactions 88% (vs 80%,
                              +7 +/- 6, n.s.), defects 45 vs 55 per 100 lines,
                              quoted speech 13.5 -> 15.2 words/line, 0 leaks
v11.4 ships the third: MAX_TOKENS["dialogue"] 110 -> 95 and DIALOGUE_BRIEF_CUE on
with that line, placed after the dialogue so far and before the voice sample -
the Author's-Note-at-depth-0 slot. The cap does the shortening safely only
because v11.3 now trims every cut line back to its last full sentence.
A lexical proxy (event words kept per line) said the note cost reactions; the
blind reading said it did not - short speech reacts without naming nouns.

REGISTERED BEFORE THE RUNS (4 runs, dragon storyline, 8 rounds x 6 turns, vs
v11.3's iters 324-327; v11.3's and v11.4's 168 event-following lines each are
read blind in ONE shuffled batch, R/M/I plus rubric defect codes, so both get
the same hand; v11.3's earlier labels re-test that hand):
  TARGET      words/line at least 10% below v11.3 (71 -> <= 64)
  GUARD RAILS reaction not worse than v11.3 by more than 2 lines/18; ignored
              lines not more than v11.3 + 3; turns 4-6 reacting not worse than
              v11.3 by more than 8 of 84; cut lines <= 5%; the note spoken aloud
              in <= 2 lines; parroting <= 2; raw fallbacks 0; "no speech"
              redraws <= 10%
  ADOPT       target met and every guard rail holds
  REVERT      reaction worse by more than 2 lines/18, or the note leaks in more
              than 2 lines, or redraws above 10%
  OTHERWISE   keep v11.4 live, report which rail missed, and replicate before
              building on it (the middle case v11.3's rule forgot)

v11.3 RESULT (iters 324-327, sha 7ff6bae1; code in loop_saves/Loop324-327):
cut lines 45% -> 1%, odd-quote lines 47 -> 10, words/line 77 -> 71; reaction
15.4 -> 14.4/18 (allowed), ignores 3 -> 7 (bar <= 6, missed by one; all at
turns 4-5, D-06 = 0), turns 4-6 reacting 67 -> 56 of 84. Neither adopted nor
reverted by its rule; kept live. Report: loop_reports/v113_cutfix_report.md.

WHAT CHANGED IN v11.3  (ONE change: cut-off dialogue lines, D-07 — 2026-09-28)
===========================================================================
46% OF DIALOGUE LINES WERE SHIPPING CUT MID-SENTENCE, in every version since
v10.8 (v10.8 46%, v11.1 49%, v11.2 41% on armA, 46% on the dragon field test).
The 110-token cap cuts a ~80-word line; the trimmer that should hide the cut
existed but was being skipped. The mechanism, in order:
  1. the cap cuts inside an *action beat*: "...and grabbed Bobb's hand while"
  2. _balance_asterisks closes the open beat; when the beat's tail holds no
     complete sentence it keeps the fragment: "*...while still clutching her*"
  3. the line now ENDS WITH "*", and the dialogue path treated any line ending
     in "*" as a legal closing beat — so _trim_to_sentence never ran.
The v5.5 OBS-031 repair fixed this only when the cut beat still contained a
full sentence; the long single-sentence beats this model writes slipped past.

FIX - judge the ending BEFORE the repair touches it. A closing mark the MODEL
wrote (a closing "*" or a closing '"', count even) is a real ending and is
kept, exactly as before. A closing mark the REPAIR added is not: the line is
cut back to its last complete sentence by _trim_line_to_sentence(), which also
(a) keeps closing marks that sit right after that sentence, so '"Bobb!" *She
grabbed his hand while' becomes '"Bobb!"' and not '"Bobb!', and (b) closes a
quote the cut left open. Lines that already ended cleanly are unchanged, and
a line ending in a closed quote with no full stop ('"Then we go together"')
is now kept whole instead of being trimmed back to its opening beat.
Simulated on the 192 dragon-test lines before shipping: 89 cut -> 3 (no
terminator anywhere), none emptied, cut lines lose ~18% of their words, and
of 66 cut lines that reacted to their event only 1 loses every event word.
5 (~3%) lose their only speech, which the existing "action-only reply" check
then redraws inside the existing retry budget - no new re-roll loop.
Found while fixing, deliberately NOT changed (one variable per version): the
dialogue path strips a line's LEADING quote (raw.strip().lstrip('"'), left
over from the open-quote cue retired in v5.4), so a line that opens in speech
ships with an orphan closing quote ('Transported WHERE?!?" *My eyes...').
_trim_line_to_sentence is written to cope with that (it keeps a '"' only if
it closes an open quote, and closes speech by looking at the last quote
itself rather than at parity).

REGISTERED BEFORE THE RUNS (4 runs of scenario_kaya_bobb_dragon_to_stars,
8 rounds x 6 turns, compared with v11.2's iters 320-323; 168 new event-
following lines read blind with 24 re-test lines from the v11.2 batch):
  TARGET      cut-mid-sentence lines <= 5% (v11.2: 46%)
  GUARD RAILS reaction not worse than v11.2's 15.4/18 by more than 2 lines
              (>= 13.4/18); ignores <= 6 (v11.2: 3); parroting <= 2 lines;
              raw fallbacks 0; "action-only" redraws <= 10% of lines
  ADOPT       target met and every guard rail holds
  REVERT      reaction worse by more than 2 lines/18, or redraws above 10%
  Predictions, reported not ruled on: words/line down ~15-20%; turns 4-6
  react at least as well as v11.2; lines do not lengthen within a round.
  If fewer than 20 of the 24 re-test lines get their earlier label, the
  reading comparison is reported as unreliable.

v11.2 RESULT (armN iters 316-319, sha 562eb565): ADOPTED. armA reaction
11.75 -> 14.00 /18 (15, 14, 12, 15), ignores 6 -> 2, staging-dropped player
words in dialogue 25% -> 15%, no parroting. FIELD TEST (iters 320-323, Kaya &
Bobb, dragon -> ship -> glass moon, 8 rounds): 86% of 168 event-following
lines react (15.4/18), every event 13.5-18/18, 0 fallbacks, no parroting; the
story went where it was sent in 3 of 4 runs (iter 321 lagged a round - the
opener seed puts the event BEFORE the resolution). Report:
loop_reports/v112_dragon_to_stars_report.md. It is also where D-07 was found.

WHAT CHANGED IN v11.2  (ONE change, user-directed 2026-09-25)
===========================================================================
THE PLAYER'S TEXT TWICE, THEN THE STAGING. EVENT_INPUT_COPIES 1 -> 2, the arm
v11.1 was built to make a one-constant change. Every channel now receives

    "<the player's text>. <the player's text>. <the staging>"

Why: prompt repetition (Leviathan, Kalman & Matias 2025, arXiv 2512.14982) -
a model that reads left to right cannot let early words see later ones;
a second copy is read with the whole of the first already in view. The paper
repeated the WHOLE prompt on question-answering tasks (47 wins, 0 losses on
non-reasoning models); this repeats only the player's text, in place. Part of
the mechanism carries over (copy two is read knowing copy one), part does not
(nothing else in the prompt is re-read). The known counter-risk is this
engine's own: a repeated string is copy material ("parrot bait", the v10.1
pressure-line note), so parroting is the registered revert bar again.
On a conditioner give-up the player's text is sent twice with no staging.

REGISTERED BEFORE THE RUNS (4 runs, armA, 4 rounds x 6 turns, as v11.1's
iters 312-315). v11.2's 72 lines are read blind, shuffled together with 24
already-labelled lines (12 v10.8, 12 v11.1) that re-test the hand.
  Baseline = v11.1: 11.75 reacting lines /18, 6 ignores, 25% of the player's
  staging-dropped words reaching dialogue, no parroting.
  ADOPT 11.2  if its reacting mean is >= 11.75 with no more ignores, OR it is
              within 2 lines and carries MORE of the player's staging-dropped
              words (> 25%).
  REVERT      if it is worse by more than 2 lines/18, or more than 2 of its 72
              lines parrot the player's text (a shared run of 8+ words).
  Otherwise   keep v11.1 (one copy is simpler, and already measured).
  If fewer than 20 of the 24 re-test lines get their earlier label, the hand
  has drifted and the comparison is reported as unreliable.

WHAT CHANGED IN v11.1  (ONE change, user-directed 2026-09-25)
===========================================================================
THE PLAYER'S OWN WORDS TRAVEL WITH THE STAGING. Since v10.1 every channel
received ONLY the conditioner's staging. The staging makes an event land in
the room, but it keeps what can be staged and drops what the event MEANT. The
first v11 session (runSaves/a_rusting_orbital_station_abov_20260925_000243)
showed it plainly: event 2 was "They offer Vess and Kael office jobs. If they
disarm they can begin training.", and its staging was two maintenance
androids gliding in. The offer, the profit, the disarming and the training
were all gone, and the content guard still passed, on the one word
"android". Nobody in the story could react to a job offer no one was told of.

FIX - compose_event(). The narrator (the next opener's seed), the characters
(the bracketed stage beat) and the memory keeper now all receive ONE event:

    "<the player's text>. <the staging>"

A full stop is added after the player's text only when it does not already
end a sentence (. ! ? or an ellipsis, optionally followed by a closing quote
or bracket); a trailing , ; : or dash is replaced by it. When the conditioner
gave up - its fallback IS the player's text - the text is sent once, not
twice. The conditioner, its prompt and its guards are untouched, and so is
every prompt the event lands in: only the event string changed.

Why it may work where raw text alone failed in v10.0 (3-6% uptake): the model
ignores what it is TOLD and reacts to what is in the ROOM. The staging still
puts the event in the room; the player's text now rides along as its meaning.
New risk, measured rather than guarded: a raw epistemic sentence in every
prompt is fresh copy material, so watch for lines that parrot it.

REGISTERED BEFORE THE RUNS (4 runs, armA, 4 rounds x 6 turns = v10.8's iters
306-309). All 144 lines - 72 from v11.1 and v10.8's 72 re-read by the same
hand - are labelled R/M/I in one shuffled blind batch.
  ADOPT 11.1  if its reacting-line mean /18 is >= v10.8's (as re-labelled)
              and it has no more ignores, OR it is within 2 lines of v10.8
              and carries more of the player's own content words into the
              following round's dialogue (the thing this change targets).
  REVERT      if it is worse by more than 2 lines/18, or if more than 2 of its
              72 lines parrot the player's text (a shared run of 8+ words).
Next arm, pre-built: EVENT_INPUT_COPIES = 2 sends the player's text twice
before the staging - prompt repetition (Leviathan, Kalman & Matias 2025,
arXiv 2512.14982: repeating the input helps non-reasoning models).

v11.1 RESULT (iters 312-315, sha 1426bc11; code in loop_saves/Loop312-315):
ADOPTED. Read blind with v10.8's 306-309 re-read in the same batch:
  reacting lines /18   v10.8 10, 11, 14, 9 (11.00)   v11.1 7, 8, 17, 15 (11.75)
  ignores              8 -> 6
  staging-dropped player words reaching dialogue   6/84 (7%) -> 26/105 (25%)
  parroting            none (longest shared run 2 words)
The reaction gain is inside the noise; the meaning result is not - every
v11.1 run carried more of the player's words than every v10.8 run.
(The raw-fallback count also fell 2 -> 0, by chance: the conditioner is
unchanged, and event 1, where both v10.8 fallbacks fell, is staged before
compose_event can touch anything.)

WHAT CHANGED IN v11.0  (NO MECHANICAL CHANGE — v10.8 promoted, 2026-09-24)
===========================================================================
v11.0 is story_lab_engine10.py v10.8 copied verbatim (sha256 60964f21...).
Not one line of logic, prompt text, threshold or guard differs — only the
module name, this note and ENGINE_VERSION. story_lab_engine10.py stays
FROZEN at v10.8 as the preserved reference, as v7.3 was when v8.0 began.

What v10.8 is: v10.1's event-conditioner prompt VERBATIM (byte-checked
against loop_saves/Loop279) and v10.1's dialogue behaviour (reaction gate
off, no second-person check, first soft staging banked), on v10.7's
repaired content guard (setting words and names excluded at stem level,
5-letter partial floor, 5 base-temperature draws on "player content lost",
hard defects checked before soft ones).

The evidence it carries (iters 306-309, read blind, R/M/I labels):
  reacting lines /18   10, 14, 11, 8   mean 10.75, sd 2.5
  collapsed runs       0 of 4          (v10.6 baseline: 2 of 8)
  player events lost   0 of 12
  raw-text fallbacks   2 of 12 — and those two were the ONLY dead events
The noise floor is ~8 lines/18 for a two-run comparison (six identical
v10.6 runs scored 14, 11, 14, 2, 3, 13), so v10.8 was chosen on steadiness
and fidelity, not on a proven reaction gain. The first behavioural change
made here should bump to 11.1 and be measured against the numbers above
with ~4-6 runs, not two. The top candidate: replace the raw-text fallback
with a final retry that names the player's key words it must keep.

Paired files: story_lab_director11.py, story_lab_gui11.py (the playable
build), story_lab_loop11.py (the headless harness), test_engine11.py. The
voice layer is story_lab_tts10.py, unchanged — it never imports the engine.

---------------------------------------------------------------------------
The history below is v10.x's, kept as it was.
---------------------------------------------------------------------------

WHAT CHANGED IN v8.1  (one change: OBS-065/066, the keeper demonstration)
===========================================================================
The v8.0 replication was the first study to capture the engine's own guard
telemetry (stdout) for every run, and it named the most expensive defect in
the engine. Across ten 7-round runs the memory keeper filled 140 memory
slots using 211 generations — a 50% overhead — and 43 of those extra draws
were one defect: the model copying the keeper's own demonstration line.
32 hits landed on the FIRST attempt (22.9% of all slots), 3 slots exhausted
the whole budget and banked a defective memory. The distribution is the
finding: only 5 of the 32 were in round 1; 27 were in rounds 2-7, and the
rate rose with round number (7 of 20 at round 7).

Rounds 2+ never needed the example. They already carry a stronger, in-register
anchor written by the character itself — the previous memory, in the block
immediately below the system prompt. So the example there is pure attractor
(C-09; model-empathy P3/P8: a CONSTANT demonstration is worse than a one-shot
one), and enumerating more tripwire phrases cannot help, because the model
copies the FRAME, not the words: "Next time ..." appears in 17-24% of all 280
banked memories in the v7.3 and v8.0 arms, and iter 059's "You still can't
tell if he's genuinely trying to help" is the demo's second sentence with the
object swapped. Both pass every guard we own.

FIX — ANCHOR-THEN-WITHDRAW AT THE KEEPER. The quoted demonstration is emitted
in ROUND 1 ONLY (previous_memory empty); from round 2 the register is carried
by the plain description plus the character's own accumulated memory. This is
the v5.8/OBS-034 voice re-architecture — the program's strongest single result
— transplanted from the dialogue role to the memory role. Keyed on the ROUND,
not the attempt, so it is stable across the budget's re-rolls (the same
discipline as include_sample). It REMOVES generations rather than adding any,
so the "one arbiter, one budget" constraint is untouched, and no guard is
retired: the demo tripwire still guards round 1 and still catches a phrase
carried in by recursion. Round-1 prompt wording is byte-identical to v8.0.

  NOT taken, deliberately (one variable per iteration): OBS-067, the header
  strip covering generate_opener() only, which let "Ilsmere Cathedral" ship as
  the SETTING's first line and be inherited by every downstream prompt in
  iter 075 — two lines, a recorded specimen, and the top conservative
  candidate for next time. Also open: OBS-068 (the v7.3 "Forms of address:"
  block paraphrased back as a whole dialogue turn, 1 in 10 runs) and OBS-069
  (the resolver's echo re-roll returned EMPTY twice in iter 072, and its print
  does not say WHICH of the three echo tests fired).

WHAT CHANGED IN v8.0  (NO MECHANICAL CHANGE — a preserved-baseline copy)
===========================================================================
v8.0 is story_lab_engine7.py v7.3 copied verbatim. Not one line of logic,
prompt text, threshold or guard differs — only the module name and the
version constant. story_lab_engine7.py stays FROZEN at v7.3 as the preserved
reference (as v5 was frozen at 5.13 before it); v8 is the file to develop in.

Because behaviour is identical, the v7.3 evidence carries over unchanged and
v8.0 needs no re-validation to be trusted as a starting point:
  header leaks        0 across 20 runs (v7.1 arm: 11 in 10)
  name defects        0 across 10 runs, split metric (v7.1 arm: 32)
  severe memory       0/10 runs, max overlap 6 words (v7.2 arm peaked at 61)
The first behavioural change made here should bump to 8.1 and be measured
against those numbers, not against a fresh baseline.

WHAT CHANGED IN v7.3  (corrections forced by the 20-run replication study)
===========================================================================
Running the five scenarios TWICE on each engine (n=10 per arm) separated fix
effect from roll variance for the first time, and overturned two v7.2 claims.

FIX 3 CORRECTED — SALVAGE, NOT MORE ATTEMPTS. v7.2 reported memory survivors
eliminated (2/5 -> 0/5). At n=10 that was luck: iter 055 produced a 61-WORD
survivor, larger than the 18-word case v7.2 was built to remove. The detector
was not at fault — tested on those specimens it returns `frozen opening`. The
fallback was: `soft_keep` won UNCONDITIONALLY, so a soft-defective draw banked
at attempt 1 beat everything once attempts 2 and 3 hit hard defects. More
attempts provably cannot fix that. Nor can preferring previous_memory: the
61-word span sat in a 94-word memory (~65% repeat) where previous_memory is a
100% repeat. _strip_repeated_span() therefore drops the copied SENTENCES and
keeps the novel ones, mirroring _strip_demo_phrases (v5.11). Threshold measured
across 240 real memory pairs: 235 sat at 0-4 words, outliers were 11/18/19/61,
so _MEMORY_SEVERE_REPEAT = 10 separates them with wide margin. The soft
candidate is also now the LEAST repetitive of the attempts rather than the
first banked.

FIX 2 CORRECTED — POSITION, NOT INFORMATION. v7.2's authored identity halved
titled-name errors pooled (19 -> 10) but per roll the effect was 12->4 then
7->6: comparable to the noise floor (per-run sd ~1.5-2.0), so the headline was
a favourable draw. Diagnosis: the information was already present and simply
outvoted. A single round's transcript primes the BARE FIRST NAME 6-7 times
(speaker labels + the cue) and contains the surname ZERO times — measured on
iter 053: "Edmund:" x3, "Harriet:" x3, "Fowler" x0, "Quill" x0 — against one
surname mention in the system prompt at maximum distance from the cue. v7.3
adds an authored `address` field emitted as a "Forms of address:" line placed
IMMEDIATELY BEFORE THE CUE (recency, P4), where the competition actually is.
Emitted only when a scenario supplies it, so modern casts gain no noise.
DELIBERATELY NOT BUILT: a name-check guard. The replication metric conflates
two different things — "Miss Ashford" applied to Harriet is a defect, but
"Mr. Blackwood's estate" names a character the scenario never named, which is
legitimate world-building. A guard cannot tell them apart without knowing the
referent, so it would fire on correct behaviour.

WHAT CHANGED IN v7.2  (three fixes from the 5-trial genre sweep, iters 037-041)

WHAT CHANGED IN v7.2  (three fixes from the 5-trial genre sweep, iters 037-041)
===========================================================================
A five-scenario sweep (period / noir / horror / mundane / mythic, all built to
the Tier-4 scenario laws) showed the remaining defects collapse into three
root causes rather than fifteen separate bugs.

FIX 1 — THE OPENER WAS THE LAST UNGUARDED ROLE. Every other prose role has a
typed defect detector (_setting_defect 3 types, _reply_defect 5, the resolver's
3 echo checks, _memory_defect 6); the opener had only _echoes_setting, which
fires from round 2. Yet the opener is injected into EVERY dialogue turn as
"The scene:\n{opener}", so a bad one contaminates six turns. All defects
clustered there: 6 header leaks across 5 runs, every one on LINE 1 —
"Present tense - third person narration", "A Storm-Blocked Tower", "Ilsmere
Floods", "No dialogue - just description & action:", "Scene Opening",
"Setting", a bare "*", and "---". _header_lead() catches all eight with one
rule (a first line carrying no sentence-terminal punctuation is a header, not
narration) and the fix is a STRIP, not a re-roll: the body underneath is
usually good prose, so deleting the line costs nothing and cannot return
something worse. Re-roll only if stripping leaves nothing.
  NOT built, deliberately: (a) a first/second-person narration guard — the
  sweep measured 0/7 in all five trials, because v7.0's setting fix removed
  the upstream cause; guarding a defect that no longer occurs is speculative
  armor. (b) dialogue-in-openers as a re-roll — it fires on 34% of openers
  (12/35) for a mild D-12, and the principled fix is demonstration over
  prohibition (P1/P3), which is a prompt change deserving its own A/B.

FIX 2 — THE PROMPT RECEIVED FRAGMENTS OF THE CHARACTER, NOT THE CHARACTER.
Four logged observations shared one root: OBS-041 (surname invented — "Mr.
Vesper" for Grant, "Mr. Salerno" for Ferrant, "Miss Harriet" for Quill; 3 of
5 trials), OBS-044 (gender drift), OBS-053 (the word "human" never reached
any prompt, so a human character called herself a synthetic), OBS-048 (cast
classification derived from the extractor's paraphrase, which loses the word).
Fixed by an AUTHORED identity, never a derived one — OBS-048's lesson is that
a stable fact must not come from a small model's summary. Scenarios may now
set char_x_inputs["identity"] ("Harriet Quill, she/her, human"); it is stored
verbatim on StoryCharacter along with the authored description, and injected
at the TOP of the dialogue, keeper and opener prompts (identity is stable
state -> primacy, P4). Absent an authored value, _identity_line() synthesises
"Name (she/her)" from the existing gender field, so every existing scenario
improves without being edited.
  ECHO SURFACE: the identity is injected INLINE in each role's system prompt
  ("You are Harriet Quill, she/her, human.") rather than as a new labelled
  user block, so it adds no new block label for the stops or _strip_block_labels
  to cover — deliberately, because C-16 records that a grounding block added
  for one model became echo bait for the next. The residual risk is different
  in kind: pronoun NOTATION ("she/her") leaking into prose, where a character
  sheet would never say it aloud. Verification greps for exactly that.

FIX 3 — ONE RE-ROLL IS NOT ENOUGH FOR THE KEEPER. The sweep left survivors in
2 of 5 trials (18-word and 11-word verbatim runs, both logging "exhausted"),
after a 102-word survivor in iter_031. The repetition is regenerated from the
round context, so dropping previous_memory does not remove its cause. This
needs MORE attempts, which is the one thing the project agreed not to add
piecemeal — four independent retry loops risk a cascade (a hot memory re-roll
producing a demo-echo, which strips to empty, which re-injects the voice
sample). So the budget is made EXPLICIT rather than implicit: MEMORY_ATTEMPTS
caps the keeper's total generations, and the loop spends them in priority
order instead of each guard retrying on its own. That is the "one arbiter,
one budget" discipline applied to the role that needed it first.

WHAT CHANGED IN v7.1  (Tier 3 — two fixes riding on the v7.0 baseline)

WHAT CHANGED IN v7.1  (Tier 3 — two fixes riding on the v7.0 baseline)
===========================================================================
OBS-051 — THE RESOLVER COULD STILL ECHO THE SETTING. v5.13 wired
_echoes_setting() into generate_opener() ONLY, and the resolver's existing
guard, _is_context_echo(), is a VERBATIM first-40-character prefix test. So
iter 027's round-4 resolution slipped both: it was a PARAPHRASE of the
setting converted to third person ("I stand watch outside the docking bay as
the cargo shuttle departs..." -> "The cargo shuttle departs with its usual
groan of engines, leaving Sable alone..."). The first attempt at this fix —
simply reusing _echoes_setting() on the resolver — FAILED its own unit test:
that function is tuned for openers, where the copy begins verbatim at the
top, and the real specimen shares only a 5-word contiguous run (threshold 8)
with no first-word overlap at all. Measurement then found the discriminator:
the echo is a FIRST-SENTENCE PARAPHRASE. Across 21 real resolutions from
three runs the known echo scored 0.389 content-word overlap on the opening
sentence while every honest resolution scored 0.000-0.130 — a clean gap.
_paraphrases_setting() (threshold 0.30, measured not guessed) now joins
_is_context_echo (verbatim prefix) and _echoes_setting (fuzzy opening +
verbatim run) in generate_resolution()'s existing re-roll path: three tests,
three different echo shapes, both narration surfaces covered. Armor every
role, not just the one that failed first (model-empathy P7).

OBS-050 — AN ESTABLISHED RELATIONSHIP WAS SILENTLY RESET TO A FIRST MEETING.
iter 027 declared a two-year affair in the scenario; the model honoured it in
rounds 1-2 and then restarted the pair as strangers in rounds 3-4, inventing
an employer to justify it ("Then who sent you here?"). Not a refusal — a
PREMISE RESET: the RP corpus overwhelmingly opens scene 1 on strangers
meeting, and the round-1 instruction ("bring both characters into the scene")
primes precisely that introduction, so the premise lost to the corpus prior.
generate_opener() takes an optional `prior_history`; when present it (a)
swaps in a system prompt that FORBIDS an introduction and (b) appends the
history as the LAST block before the completion cue (attention geography,
P4). It is injected EVERY round, not just round 1 — the reset happened in
round 3, so pinning only the opener of round 1 would not have prevented it.
This fix is only safe because v7.0 Tier 2 decoupled the setting-echo guard
from context_seed; under 5.x, seeding a round-1 premise would have switched
that guard on for the one round where reprinting the setting is correct.

WHAT CHANGED IN v7.0  (two tiers, bundled at a declared baseline)

WHY THIS FILE EXISTS (and why there is no v6)
=============================================
story_lab_engine5.py is FROZEN at v5.13 and still drives the GUI
(story_lab_director5.py) and the original harness (story_lab_loop.py). It is
the known-good, shipped engine; nothing here modifies it.

v6 is DELIBERATELY SKIPPED. The version jumps 5.13 -> 7.0 to mark that this
is an ARCHITECTURAL change, not another incremental guard: it removes a
structural assumption the whole 5.x line was built on (Tier 2 below).
Skipping a number makes that discontinuity visible at a glance in
provenance.json, loop_state.json and every report — a reader who sees "7.0"
knows the engine's CONTRACT changed, not just its behaviour.

Runs from 5.x and 7.x stay comparable by sha256 and defect rate, but 7.0 is
a DECLARED NEW BASELINE (good-roleplay Part 4).

WHAT CHANGED IN v7.0  (two tiers, bundled at a declared baseline)
===========================================================================
TIER 1 — THE WORLD BUILDER WAS THE MOST CONTAMINATING ROLE (iter 026/027).
generate_setting() was the ONLY output surface in the engine with zero
post-processing (`return result` — no trim, no strip, no guard), and its
output is injected into EVERY opener and resolver prompt. Four defects, all
with whole-run reach:
  1. NO PERSON PIN. The prompt said "places us in this world" and never
     fixed the person, so 4 of the last 5 settings came back in FIRST
     PERSON ("I stand watch outside the docking bay..."). Openers and
     resolutions inherited that register — Run 19 returned three
     first-person openers though the opener prompt says third person
     (D-12 x7).
  2. NO CAST. It received world_desc only and never learned who the
     characters were, so it populated the scene with invented people
     ("Dr. Elena Vasquez", iter 026), contaminating 8 downstream items and
     mutating the lead's name (OBS-046).
  3. NO TRIM. Settings were cap-cut mid-sentence ("...when their
     internal") — diagnosed generations ago in the model-empathy catalog
     (C-19: a cap-cut setting is a GM-layer trigger) and never fixed.
  4. NO STRIPS. Markdown could pass through untouched.
Fixed: third-person/no-dialogue pin in the prompt, the cast passed in and
pinned ("name no other person"), _setting_defect() + ONE re-roll as the
mechanical guarantee behind the prompt (P6 — never trust, verify), then
_trim_to_sentence(_strip_markdown(...)) like every other prose role.

TIER 2 — THE ENGINE HAD NO ROUND AWARENESS (the structural change).
`round_num` appeared ZERO times in 5.x. Every role inferred the round from
an EMPTY STRING, and those inferences had quietly become load-bearing for
guards:
    context_seed == ""  ->  "round 1"  ->  drove BOTH the opener's
                            establish/continue branch AND the v5.13
                            setting-echo guard
    memory       == ""  ->  "round 1"  ->  drove voice_sample injection
                            (the v5.8 voice re-architecture)
Two planned fixes were on a collision course with that. Pinning an
established-relationship premise (OBS-050) means seeding context_seed in
round 1 — which would have silently switched the setting-echo guard ON for
the one round where reproducing the setting is CORRECT. And a refusal
fallback returning "" for a memory would have re-triggered include_sample
mid-arc, reviving the catchphrase parrot v5.8 eliminated (OBS-029).
Fixed by separating the two meanings riding on one variable:
    BRANCH stays CONTENT-driven:  if context_seed:    (establish vs continue)
    GUARD  becomes ROUND-driven:  if round_num > 1:   (setting-echo check)
    VOICE  becomes ROUND-driven:  include_sample = (round_num == 1)
generate_opener() and generate_dialogue_turn() take an explicit `round_num`
(default 1, so this is behaviour-neutral today: round 1 was exactly
context_seed=="" before). generate_resolution() will take it when OBS-051
lands; it is not added speculatively.

PURPOSE
=======
Pure functions only. No classes, no threading, no ComfyUI calls, no audio.
Called by the STORY THREAD in story_lab_director5.py, which owns the loop.
The frozen v5.0 baseline lives beside this file as story_lab_engine5_0.py.

EIGHT AI roles, all dolphin-llama3.1, differentiated by prompt + context:
  1. Character Parser   — extract_character()          (once per character)
  2. World Builder      — generate_setting()           (once per session)
  3. Storyteller open   — generate_opener()            (once per round)
  4. Character A        — generate_dialogue_turn()     (alternating turns)
  5. Character B        — generate_dialogue_turn()     (alternating turns)
  6. Storyteller close  — generate_resolution()        (once per round)
  7. Memory Keeper      — generate_character_memory()  (once per character
                                                        per round)
  8. Scene Prompter     — generate_scene_prompt()      (once per round)

WHAT CHANGED IN v5.13  (opener-echoes-setting guard — OBS-042, iter 023)
===========================================================================
The wedding comedy (Run 16) exposed a new long-arc echo: the round-7 opener
reproduced the SETTING paragraph's first two sentences VERBATIM (Jaccard-vs-
setting 0.65 where every other opener was <=0.10). The frozen-opening guard
only compares an opener to the PREVIOUS opener, so a copy of the setting
slipped it. Same family as the OBS-038 memory freeze: under dense late-arc
context the model reaches for the most "opener-shaped" prose in scope — the
setting itself. Fix: _echoes_setting() (the fuzzy _opening_frozen overlap OR
a >=8-word verbatim run) now checks round-2+ openers against the setting, and
on a hit generate_opener() re-rolls ONCE with the setting block DROPPED from
the prompt (nothing to copy) — mirroring the keeper recursion-break re-roll.
Round 1 is exempt: establishing the world there is the job. A re-roll that
still echoes is discarded (the first is no worse — thin beats poisoned).

WHAT CHANGED IN v5.12  (two harness-polish fixes — OBS-037, iter 020)
===========================================================================
The domestic-drama runs (11/12/13) confirmed the last two HARNESS-fixable
defects (everything else remaining is model prose/invention, not the harness):
  OBS-037  RESOLVER MENU + META. The resolver prompt ENUMERATED the story-
           move options ("a threat emerged or drew closer, something was
           revealed...") and the model copied one verbatim as its opening;
           worse (iter 020) it wrote literary commentary — "This scene is
           exploring a marriage breakdown...". The menu is removed from the
           prompt, the meta-relapse is forbidden explicitly, and
           _strip_meta_lead() drops any "This scene is exploring..." opener
           mechanically (empty-after-strip -> re-roll -> thin seed).
  REPEATED BODY. The frozen-opening guard only checked a memory's first
           words; iter 020 had James's r1 and r2 memories share near-
           identical BODIES under different openings. _body_repeat() (trigram
           overlap >= 0.35 vs the previous memory) catches whole-body
           recurrence; it is a SOFT defect, so the v5.10 recursion-break
           re-roll regenerates a fresh memory.

WHAT CHANGED IN v5.11  (demo-echo fallback duplicate — OBS-040, iter 017)
===========================================================================
The v5.10 freeze fix exposed a residual: when BOTH keeper attempts leaked a
demonstration phrase (a HARD "demonstration echo" exhaustion), the fallback
returned the PREVIOUS memory verbatim — a duplicate (iter 017: round 4 ==
round 3). _strip_demo_phrases() now drops the tainted SENTENCE(S) from the
fresh attempt and keeps the rest; the exhaustion fallback prefers that
fresh-minus-phrase memory over a duplicate previous one. Order:
soft-repetitive > demo-stripped-fresh > previous (stale) > any > "".

WHAT CHANGED IN v5.10  (memory-freeze fix — OBS-038, iter 015 Fayrun)
===========================================================================
The first 7-round run exposed the recursion ratchet at scale: Kaya's
memory stopped evolving mid-arc (rounds 5 and 6 came out BYTE-IDENTICAL,
rounds 4-7 all opening "You're (absolutely) right Bobb—something IS very
wrong"). Two coupled failures, two fixes:
  1. The frozen-opening guard's EXACT first-4-word match was defeated by
     lexical mutation ("you're RIGHT bobb" -> "you're ABSOLUTELY right
     bobb"). _opening_frozen() now ALSO does a fuzzy first-8-word overlap
     (Jaccard >= 0.6), catching the mutated variant.
  2. Where the guard DID fire, the single re-roll reproduced the memory
     because it still read (and was told to "fold in") the frozen
     previous_memory at temperature 0.5. The keeper re-roll now BREAKS the
     recursion: it rebuilds the context WITHOUT previous_memory and runs
     at temperature 0.85, so it writes a fresh memory from this round's
     events instead of copying the stuck one. (ollama_chat() gained an
     optional per-call `temperature` override for this.)
User-directed: the "too-readily-agree" friction note (OBS-039) is LEFT
ALONE by request — no change to the friction clause or cast dynamics.

WHAT CHANGED IN v5.9  (NO MECHANICAL CHANGE — scenario/version stamp)
===========================================================================
v5.9 is byte-for-byte the v5.8 engine logic; only ENGINE_VERSION and this
note change. Bumped at the user's request to stamp a new PLAYABLE SCENARIO
(the fantasy world "Fayrun": Kaya the fox-wizard and Bobb the paladin, a
wild dragon over the city of Marara) as its own provenance-tracked baseline.
Because the scenario CHANGES, this run is NOT a controlled comparison with
the v5.2..v5.8 orbital-station iterations (good-roleplay rubric Part 4: a
new scenario declares a new baseline) — it is scored on absolute quality.

WHAT CHANGED IN v5.8  (voice re-architecture — USER-DIRECTED CREATIVE, iter 012)
===========================================================================
The conservative track plateaued (~32 defects/100 for two iterations), so
per the good-roleplay rubric the next move is creative. The user chose the
VOICE RE-ARCHITECTURE. Root cause of the surviving catchphrase parrot
(OBS-029) AND the keeper person-drift (OBS-034): the full quoted
voice_sample was re-injected into the dialogue system prompt EVERY turn,
constantly re-priming the sample's opening clause. Now the quoted sample
anchors ROUND 1 ONLY (the strongest few-shot establishment); from round 2
the caller passes include_sample=False and the voice is carried by the
non-quotable style DESCRIPTION plus the character's own memory. The system
prompt is deliberately no longer byte-identical across rounds — that
property was the very thing causing the parrot. HYPOTHESIS: parrot and
drift die at the source without a voice collapse; if the voice DOES
collapse in round 2+, that is the finding and Loop-prior is the rollback.
Folded in (cheap mechanical leftovers): OBS-035 (strip a leading
"**Name:**" speaker-label echo at position 0) and OBS-036 (run
_strip_markdown on the opener — a "**A moment ago:**" header leaked).
Expected fingerprints: round-1 dialogue system contains the quoted sample,
round-2+ does not; no dialogue line opens with the sample clause after
round 1; no leading "**Name:**" in dialogue; no "**…:**" opener header.

WHAT CHANGED IN v5.7  (catchphrase guard — OBS-029, iter 009)
===========================================================================
Conservative round with v5.6: the voice_sample is injected every turn to
hold the voice, but its opening clause is also the strongest line-start
attractor — iter 009 had Kael open ~3 rounds with his sample's "Well now,
ain't you just...". The per-round duplicate guard can't see it (history
resets each round). _reply_defect() now takes the speaker's voice_sample
opening n-gram and re-rolls a reply whose SPOKEN opening matches it — the
sample still primes the voice, only its first five words must differ.
Expected fingerprint: no dialogue line repeats the speaker's voice_sample
opening across rounds; console may show "voice-sample parrot" re-rolls.

WHAT CHANGED IN v5.6  (one-line follow-up — OBS-033, iter 009)
===========================================================================
The v5.5 OBS-031 fix left a sibling bug the v5.5 run then exposed: when a
CLOSED beat ends "sentence.*" with trailing text, _trim_to_sentence cuts
at the period (before the closing "*"), orphaning the beat's opening
asterisk — 5 of 18 dialogue lines shipped an unclosed beat (cosmetic:
complete sentences missing a closing italic marker, NOT fragments). The
dialogue else-branch now re-runs _balance_asterisks after the trim.
Expected fingerprint: every stored dialogue line has an EVEN asterisk count.

WHAT CHANGED IN v5.5  (conservative cleanup bundle — OBS-030/031/032, iter 007)
===========================================================================
Three mechanical fixes after the iter 007 score, all localised:
  OBS-030  KEEPER DEMONSTRATION LEAK + RECURSION FREEZE. The v5.3 example
           line transplanted into real memories ("door codes" became the
           plot) and froze across rounds (both characters opened "You held
           your ground" x3). Fix: content-free example that does not open
           with an action; demonstration-echo tripwire (HARD re-roll);
           frozen-opening (vs last round) and shared-opening (vs the peer
           memory, now threaded in) checks (SOFT); priority fallback. See
           generate_character_memory + _memory_defect.
  OBS-031  ASTERISK REPAIR FROZE CAP-CUTS. _balance_asterisks() closed an
           unclosed beat verbatim, turning a mid-sentence cap cut into a
           legal-looking beat the trim then skipped. Now the open tail is
           sentence-trimmed BEFORE closing.
  OBS-032  RESOLVER MARKDOWN RELAPSE. The resolver now runs _strip_markdown
           (kills ** bold / * whole-line italic headers) and
           _strip_block_labels (an echoed context label); the keeper gets
           the block-label strip too.
Expected fingerprints: no "manifest"/"door codes"/"ally or a mark" in
memories; memories across rounds/characters do not share a 4-word opening;
no line ending in a fragment-then-asterisk; no "**"/"*header*" in
resolutions; console may show "Memory defect [frozen opening]" /
"[shared opening (matches peer)]" / "[demonstration echo]".

WHAT CHANGED IN v5.4  (the dialect embrace — OBS-028, USER-DIRECTED creative)
===========================================================================
Iter 004 showed 7/18 dialogue lines drifting into Rocinante's native
*asterisk-action* register while the dolphin-era armor amputated them
(the cut-at-first-quote strip kept the action and DELETED the speech).
Per the user's decision on StoryLabLoopReport4, the dialect is EMBRACED:
transcript lines feed back as emitted (no quote-wrap), the completion cue
is the bare name, the '"\n' stop is retired, [directions] are normalised
to *beats* (brackets stay reserved for the player's event), odd asterisk
counts are repaired, a closing *beat* is a legal line ending, and the cue
sentence names the dialect ("Speak, and add brief *actions* in asterisks
when they matter."). A new action-only defect (reply with no speech left
after removing *spans*) joins the re-roll guard. Ships with v5.3 as a
DECLARED BUNDLE — iter 006 is the new baseline; per-role fingerprints
keep attribution separable (memories = v5.3, dialogue = v5.4).
Expected fingerprints: dialogue lines may legally contain *beats*; no
bracketed [directions] in character lines; no unclosed asterisk spans;
"action-only reply" may appear in console re-roll notices.

WHAT CHANGED IN v5.3  (the Memory Keeper rescue — OBS-027, loop iter 004)
===========================================================================
The first SCORED loop run (iter 004) showed the keeper collapsing into
Rocinante's note-taking dialect — "**NOTES:**" markdown scaffolds with
bullet lists instead of second-person prose — and, three rounds straight,
Kael's memory written from VESS'S perspective ("How you now see Kael"
inside Kael's own memory). Memory feeds the next round's dialogue context,
so both defects compound. generate_character_memory() was rebuilt:
identity-first prompt with ONE demonstration line instead of the
instruction list the model was echoing as headers; a completion cue block
("Your notes to yourself, X:") at the very end; stops on its own context
labels; _strip_markdown() + _strip_label_lines() + _trim_to_sentence();
and a _memory_defect() detector (empty / own-name wrong-perspective) with
ONE re-roll, falling back to the PREVIOUS memory — stale beats poisoned
(OBS-022 rule, character channel). Also NUM_GPU 0 -> 99 (text-only loop
era: no ComfyUI contention; revert to 0 for GUI-with-images sessions).
Expected fingerprints: memories in log.txt are plain second-person prose
(no "**", no "- " bullets, no "NOTES:"), Kael's memory never contains
"Kael", and "Memory defect [" appears in the console log on bad rolls.

WHAT CHANGED IN v5.2  (the Rocinante dialect port — OBS-026, first loop run)
===========================================================================
The MODEL swapped from dolphin-llama3.1 (completion tune) to Rocinante-X-
12B (TheDrummer RP finetune, Mistral-Nemo base). The first loop-harness
run caught extraction scoring 0/6: Rocinante answers the KV request in
its corpus dialect — "**Voice Sample:**" bold Title-Case headers, bullet
lists BELOW bare headers, "Archetype" for "role" — and the retry
temperature bump pushed it deeper into markdown, not out of it.
parse_kv_output() now strips bullets/markdown emphasis before key
matching, maps observed key synonyms, and joins bullet-list values under
the pending field. Harness-side port per model-empathy §4; the extractor
prompt is UNCHANGED this iteration so the parser fix is measured alone.
Expected fingerprints: extraction logs "6/6 fields" on attempt 1; the
"Proceeding with N/6" warning disappears from loop logs.

WHAT CHANGED IN v5.1  (the reactivity patch — OBS-016..025, first live run)
===========================================================================
The first full GUI session verified the v5 lanes and localised five failure
mechanisms. Each fix below is mapped to its observation entry:

  OBS-017  EVENT INTO THE TRANSCRIPT. The mid-context "Just now:" block is
           gone. The player's injection now enters the dialogue call as a
           bare present-tense BRACKETED STAGE BEAT inside the transcript
           itself — subtitle register: [A robotic monster bursts in.] —
           chronologically FIRST among the lines. On the first turn of a
           round (empty history) that makes it the LAST thing before the
           completion cue: maximum salience exactly when reaction matters
           most; it then recedes naturally as spoken lines accumulate. The
           beat is assembled per call and never stored in history, so the
           resolver and keeper read a pure spoken transcript.
           Why brackets: the base-model diet (subtitle files, chat logs,
           scripts) is full of [event] lines BETWEEN dialogue lines —
           attended as part of the pattern, but marked non-speech, so they
           cannot be quoted back as a line (the R5 verbatim-echo failure).
  OBS-018  STUCK-RECORD REWORK. The friction clause now demands reaction
           before pursuit ("React to what was just said and what just
           happened, then push toward what you want."); the voice_sample
           is extracted as ONE OR TWO short sentences (a two-sentence
           sample is a weaker verbatim attractor and primes the requested
           2-3 sentence line length); the cue softens to "One reply.".
  OBS-019  REPEAT_LAST_N = 256. Ollama's repeat_penalty only scans the
           last repeat_last_n tokens (default 64) — the R2 cross-character
           verbatim echo sat outside that window. 256 covers the whole
           transcript window; it also penalises regurgitating the context
           blocks, which helps OBS-020 for free.
  OBS-020  RESOLVER ARMOR. The resolution call finally gets the same
  OBS-024  harness treatment that saved dialogue: stop sequences on the
           context-block labels, a label-line post-strip (kills the
           "The story move:" scaffold relapse), a context-echo detector
           with ONE retry, and _trim_to_sentence(). If both attempts echo,
           the resolver returns "" — frame_injection() degrades to an
           event-only seed. A THIN SEED BEATS A POISONED ONE (OBS-022:
           resolver hallucinations were being canonised into the world).
           Dialogue gets the same label guard (one setting-echo turn in 48).
  OBS-021  RESOLVER GROUNDING. generate_resolution() now receives the
           OPENER — "what just happened in the world" finally has a world
           to read, instead of inventing groups and alliances.
  OBS-016  TRIMS EVERYWHERE. _trim_to_sentence() now also covers opener
  OBS-023  and resolution (six of eight live openers died mid-sentence at
           the cap), and drops dangling commas on fragments. Dialogue cap
           80 -> 110 for the 2-3 sentence target.
  Plus: ENGINE_VERSION stamped into every run's characters.json, and a
  degenerate-reply guard (empty / verbatim-duplicate / beat-echo lines get
  ONE re-roll — see DIALOGUE_RETRY).

WHAT CHANGED IN v5.0  (deployment)
==================================
Dolphin moved to CPU (NUM_GPU = 0) so ComfyUI owns the GPU alone and the
VRAM handoff is deleted; the Scene Prompter moved in from images3 so the
engine owns every Ollama call; the loop moved out to story_lab_director5.

WHAT CHANGED FROM v3  (why dialogue went flat — still the core teaching)
========================================================================
v3 fixed HOW dolphin is prompted (OBS-010/011/012: no scaffolding, voice
anchoring, Proppian resolution). v4 fixed WHAT dolphin knows:

  1. CHARACTERS WERE STATELESS ACROSS ROUNDS -> the CHARACTER memory
     channel: the Memory Keeper rewrites a short second-person memory per
     character per round, injected at the top of the dialogue context.
  2. MOTIVATION WAS FROZEN AT EXTRACTION -> every memory ENDS with "the
     one thing you want next" — an evolving scene objective.
  3. EVENTS REACHED CHARACTERS SECOND-HAND -> the raw injection goes into
     the dialogue call directly (v5.1 sharpens WHERE — see OBS-017 above).
  4. THE AGREEMENT DEFAULT -> one friction clause as character truth
     (v5.1 rewords it — see OBS-018 above).
Plus the sixth extraction field, voice_sample — the strongest voice AND
length anchor a completion model has.

THE TWO MEMORY CHANNELS
=======================
  WORLD channel:     resolution -> frame_injection() -> context_seed ->
                     next round's OPENER. The storyteller remembers the world.
  CHARACTER channel: round events -> generate_character_memory() -> memory
                     string -> next round's DIALOGUE turns. Each character
                     remembers themself.
The transcript resets EVERY round: each dialogue call sees only identity,
memory, world, scene, and the in-round lines. Round 1 carries nothing;
round 2+ carries exactly two things — the memory and the event beat. The
injection therefore reaches the character twice, in two temporal registers:
as BREAKING NEWS (this round's bracket at the cue) and, one round later, as
PROCESSED EXPERIENCE (folded into "What you remember" by the keeper).

The character memory is RECURSIVE SUMMARIZATION: rewritten each round from
(previous memory + round events) under a hard cap — bounded forever.
Literature: arXiv:2308.15022 (recursive summary memory), 2304.03442
(Generative Agents: reflections > raw logs), 2310.08560 (MemGPT: bounded
rewritten memory), 2303.11366 (Reflexion), 2307.03172 (Lost in the Middle:
why memory sits at the TOP and the cue at the very END).

PROMPT PHILOSOPHY  (laconic prompts, smart harness)
===================================================
Prompt length scales with model CAPABILITY, not task complexity. dolphin
treats elaborate instructions as material to imitate, not direction to
follow. Every role prompt keeps a soft ~60-word budget in the register of
its output; the elaborateness lives in the HARNESS — assembly order, stop
sequences, per-role sampling, post-processing, and (new in v5.1) echo
guards and re-roll insurance.

LENGTH CONTROL  (target: 2-3 short sentences per line — OBS-023)
================================================================
Ranked by how strongly dolphin actually obeys:
  1. voice_sample        — few-shot length prime, now ONE OR TWO sentences
  2. transcript register — short lines beget short lines; HISTORY_WINDOW
                           stays small so one bloated line washes out fast
  3. speaking_style      — terse voice description
  4. mechanical backstop — 110-token cap + stop sequences + sentence trim
Counting instructions are the anti-pattern (OBS-009/011): nothing in this
file asks dolphin to count. At CPU speeds (~8-15 tok/s) a 110-token worst
case is a playable 8-14 s beat; typical lines run far shorter.

STORY THREAD CONTRACT  (what story_lab_director5.py does with this module)
==========================================================================
  setup:    extract_character() x2 -> generate_setting() -> make_run_dir()
            mem_a = mem_b = event = context_seed = ""
  round N:  opener       = generate_opener(setting, A, B, context_seed)
            scene_kw     = generate_scene_prompt(opener, A, B)  # image lane
            turns (A first, alternating):
              generate_dialogue_turn(speaker, other, setting, opener,
                                     history, memory=mem_x, event=event)
              (round 1: mem_x and event are "" — nothing carried, as spec'd)
            resolution   = generate_resolution(setting, A, B, history,
                                               opener)          # v5.1: grounded
            mem_a / mem_b = generate_character_memory(...)      # recursion
            consume the player injection (armed since round start)
            context_seed = frame_injection(injection, resolution)
            event        = injection        # becomes next round's bracket beat
  If the resolver returns "" (double context-echo), frame_injection yields
  an event-only seed — the world channel runs thin for one round instead of
  canonising garbage (OBS-022).

NON-NEGOTIABLE PRINCIPLES (scar tissue — do not remove):
  - build_messages() returns a FRESH 2-message list every call. History is
    plain text in content blocks, never prior assistant turns.
  - ollama_chat() passes an integer cap as options={"num_predict": cap}.
    Without it dolphin can suppress EOS and generate forever at 100% load.
  - unload_ollama() reads the actual loaded name from `ollama ps`, then
    polls /api/ps until the models list is empty. keep_alive=0 with the
    namespaced model string is silently a no-op.
  - KV line extraction only. Never ask dolphin for JSON.
  - UTF-8 on all file writes — dolphin emits em-dashes and smart quotes
    that crash Windows' default cp1252 encoding.
"""

import os
import re
import json
import time
import shutil
import hashlib
import subprocess
import dataclasses
import requests
import httpx
from datetime import datetime
from ollama import chat

# =============================================================================
#  SECTION 1 — CONFIG
# =============================================================================

ENGINE_VERSION = "12.4"

# v7.2 FIX 3: the keeper's TOTAL generation budget per memory. Made explicit so
# guards spend a shared allowance in priority order instead of each retrying
# independently (the "one arbiter, one budget" rule). 3 = first attempt + two
# recursion-breaking re-rolls; the sweep showed one re-roll leaves survivors.
MEMORY_ATTEMPTS = 3
# v10.1 EVENT CONDITIONER. The player's raw text was the ONLY unguarded
# input in the pipeline: frame_injection() was four lines of string glue.
# Measured uptake of an unconditioned epistemic event: 3-6% of its novel
# vocabulary reaching the next round's dialogue, against 28-35% for a
# hand-written physical one. Same budget shape as the keeper.
EVENT_ATTEMPTS  = 3
# v10.7 FIDELITY BUDGET. Losing the player's content gets MORE draws, and they
# are drawn at the BASE temperature, not up the heat ladder.
#   More draws: v10.7 makes the content guard stricter (setting words no longer
# count), so it will reject more, and exhaustion on a content loss falls back
# to the player's raw text — v10.0's behaviour, ~3% uptake. v10.6 already
# rejected five stagings for content loss across two runs.
#   No extra heat: the escalating ladder (0.6 -> 0.8 -> 1.0) was inherited from
# the memory keeper, where the defect is a FROZEN output and the cure is more
# randomness. Content loss is the opposite defect — the rewrite has already
# drifted AWAY from what the player asked for — and heating it makes it drift
# further. A fresh draw at the base temperature is still a different sample.
EVENT_ATTEMPTS_FIDELITY = 5
_EVENT_FIDELITY_DEFECTS = frozenset({"player content lost"})
# How many turns of the round carry the PRESSURE line near the cue. The
# bracket beat itself is prepended to the transcript every turn, but it
# recedes from the cue as lines accumulate; the pressure line was meant as a
# second, fresher presence that fades by design.
#
# DEFAULT 0 — OFF, on evidence. Measured beat-uptake into dialogue:
#     iter 279  conditioner, pressure never emitted     21%
#     iter 280  conditioner, pressure never emitted     21%
#     iter 282  conditioner + pressure pinned (3 turns) 13%
# Two replications agreeing at 21% against one run at 13% is not proof of a
# regression, but there is no evidence of benefit, and the generated clauses
# were thin where they were not degenerate ("They must evacuate immediately",
# and one that was the single word "Sealed"). A second block near the cue also
# competes with the voice-sample exemplar, whose effect IS established (+44%
# quoted/line, reproduced across two arms).
#   The conditioner's STAGING is the part that carries the 3% -> 21% result,
# and it is independent of this. Set to 3 to re-test the pin once the pressure
# clause itself is worth pinning.
EVENT_PIN_TURNS = 0
# v10.2 REACTION GATE. How many turns after an event must ACKNOWLEDGE it, and
# how many draws they get to. Two turns is not arbitrary: it is the rubric's
# own D-06 window ("an injected event gets zero acknowledgment in the following
# two dialogue lines"), so the guard and the defect it prevents are defined
# over exactly the same span.
#   Every other role in this engine re-rolls when it fails its contract;
# reactivity — the thing the whole event channel exists to produce — was the
# one contract with no guard behind it. This is that guard.
EVENT_REACT_TURNS    = 0   # v10.8: OFF, as in v10.1 (the gate is v10.2's). The
                           # designed value is 2 — the D-06 window — and the
                           # tests exercise it at 2. v10.8 is v10.1's behaviour
                           # on v10.7's repaired guard; the gate fired ~once a
                           # run and never measurably changed anything.
EVENT_REACT_ATTEMPTS = 3   # only on those turns, and only when a beat is live
# v11.1 EVENT COMPOSITION (see the header). What the narrator, the characters
# and the memory keeper receive for a player event: the player's own text
# first, then the staging. False restores v10.1-v11.0 (the staging alone).
EVENT_PREPEND_INPUT = True
# How many copies of the player's text lead the event. 1 = v11.1 (measured,
# adopted). 2 = v11.2, prompt repetition (see the header) - LIVE while it is
# measured; set back to 1 to restore v11.1 exactly.
EVENT_INPUT_COPIES  = 2
# Stamped into every run's characters.json tunables (save_characters_json),
# so each run folder permanently records which engine produced it —
# provenance lives in the data, not just the filename.

MODEL = 'hf.co/bartowski/TheDrummer_Rocinante-X-12B-v1-GGUF:Q4_K_M'
# Ollama stores this internally as 'dolphin-llama3.1:latest' (no namespace).
# unload_ollama() accounts for this — see its docstring.

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR    = os.path.join(_SCRIPT_DIR, "runSaves")

# Paths to ComfyUI workflow files — consumed by story_lab_images5.py.
WORKFLOW_SCENE_FILE    = os.path.join(_SCRIPT_DIR, "Workflow_wide_api_3.json")
WORKFLOW_PORTRAIT_FILE = os.path.join(_SCRIPT_DIR, "Workflow_portrait_api3.json")

# =============================================================================
#  SECTION 2 — GENERATION SETTINGS
#
#  MAX_TOKENS — passed as the `cap` integer to ollama_chat(). Hard-stops
#  generation after that many tokens regardless of what the model wants.
#
#  GENERATION_PARAMS — temperature / top_p per role.
#    temperature — LOW (~0.2) = sharp, precise. HIGH (~0.85) = varied voice.
#    top_p       — nucleus cutoff after temperature; trims the unlikely tail.
#
#  All values are hand-tunable defaults. Edit here, run, read the log.
# =============================================================================

MAX_TOKENS = {
    "char_extract": 190,   # six KV lines; +10 in v5.1 for the two-sentence
                           # voice_sample (OBS-018/023)
    "setting":      120,   # 2-3 sentence world paragraph
    "opener":       240,   # two tight paragraphs; _trim_to_sentence() now
                           # hides the cap cut (OBS-016: 6/8 live openers
                           # died mid-sentence)
    "dialogue":      95,   # v11.4: was 110 (v5.1: 80). Safe since v11.3 trims
                           # every cut line to its last full sentence; probed
                           # -18% words/line alone, -20% with DIALOGUE_BRIEF_CUE.
                           # v5.1 note: Target is 2-3 SHORT sentences
                           # (OBS-023: 80 + one-line samples skewed output
                           # to degenerate "Kid," fragments). Stop sequences
                           # still end most lines early; the cap is backstop.
                           # CPU worst case ~8-14 s — still a playable beat.
    "resolution":   120,   # 2-3 sentence Proppian story beat (world memory)
    "char_memory":  130,   # the rewritten per-character memory — ALSO a
                           # length prime at the top of the dialogue context
    "scene_prompt": 120,   # comma-separated CLIP keywords for the scene image
    "scene_layer":   80,   # v12.1: one scene-painter layer (place/things/light)
    "cine_field":    60,   # v12.3: one cinematographer field (looks/wearing/
                           # doing/others) - a tag line of ~10-25 words
    "music_field":   40,   # v12.4: one composer note - a soundtrack word or a
                           # few mood words
    "event":        120,   # v10.5: restored from 70. The 70-token cap was the
                           # REAL length limit in v10.3-10.4 (~50 words) and it
                           # also cut beats mid-quote ('"Vess?' with no closing
                           # mark). v10.5 tests whether that shortening cost
                           # engagement: 6.0 -> 4.3 reused words per event.
}

GENERATION_PARAMS = {
    # KV extraction: precision and stable line format, not creativity.
    "char_extract": {"temperature": 0.2,  "top_p": 0.8},
    # World-building: moderate creativity; the world must feel stable.
    "setting":      {"temperature": 0.7,  "top_p": 0.9},
    # Scene opener: atmospheric descriptive prose — room to be vivid.
    "opener":       {"temperature": 0.8,  "top_p": 0.9},
    # Dialogue: highest of the prose roles — voice variety across turns.
    "dialogue":     {"temperature": 0.85, "top_p": 0.9},
    # Resolution: LOWER than dialogue. Samey bonding beats (OBS-012) are a
    # high-temperature symptom.
    "resolution":   {"temperature": 0.65, "top_p": 0.85},
    # Memory keeper: lowest prose role — must commit to the round's facts.
    "char_memory":  {"temperature": 0.5,  "top_p": 0.85},
    # Scene prompter: precise comma-separated tokens, not prose (OBS-014a).
    "scene_prompt": {"temperature": 0.4,  "top_p": 0.8},
    # v12.1 scene painter layers: the scene prompter's profile, own key.
    "scene_layer":  {"temperature": 0.4,  "top_p": 0.8},
    # v12.3 cinematographer fields: the same precise-tag profile.
    "cine_field":   {"temperature": 0.4,  "top_p": 0.8},
    # v12.4 composer notes: a closed-list choice and a few mood words - the
    # tag roles' profile.
    "music_field":  {"temperature": 0.4,  "top_p": 0.8},
    # Event conditioner: a bounded REWRITE, not invention. Low enough to
    # keep the player's content, high enough to find a physical form.
    "event":        {"temperature": 0.6,  "top_p": 0.9},
}

NUM_CTX = 16384
# Context window — how many tokens the model can SEE. If input exceeds
# num_ctx, Ollama silently truncates from the BEGINNING — the system prompt
# dies first. 16K is truncation INSURANCE, not an invitation to stuff:
# assembled dialogue contexts still target ~900 tokens, for attention (more
# context = more places for an 8B to wander) and CPU prompt-eval speed.
# On CPU the KV cache lives in system RAM (~2 GB at 16K), not VRAM.

NUM_GPU = 99
# DEPLOYMENT PIN. 99 = every layer on GPU. Switched from 0 (CPU) for the
# text-only loop era: no images are being generated, so the GPU is free
# and Rocinante-12B Q4 (7.5 GB) + 16K KV cache fits the 12 GB card.
# ~10x faster rounds = ~10x more loop iterations per session.
# RETURN TO 0 before running GUI sessions WITH images — at 99 the old
# unload_ollama()/unload_comfyui() VRAM handoff becomes necessary again.
# (v5 CPU-pin rationale preserved in story_lab_engine5_0.py.)

REPEAT_PENALTY = 1.2
# Resists echoing context back verbatim (Ollama default: 1.1). Side effect:
# it also penalises repeated punctuation, which can nudge the model to
# avoid ending a sentence — the dialogue stop sequences neutralise this.

REPEAT_LAST_N = 256
# v5.1 (OBS-019). How far back the repeat penalty LOOKS. Ollama's default
# is 64 tokens — the first live run's cross-character verbatim echo ("You're
# nothing but lies.") sat five lines back, safely outside that window, so
# the 1.2 penalty literally could not see it. 256 covers the whole
# HISTORY_WINDOW transcript plus the scene tail; it also mildly penalises
# regurgitating the context blocks (helps the OBS-020 resolver echo).
# Applied in ollama_chat() — NOT in the extractor's direct call, where
# penalising repeated field-name tokens would destabilise the KV format.

HISTORY_WINDOW = 6
# Most-recent dialogue lines passed per turn (= 3 exchanges). Deliberately
# small even at 16K: the transcript is a length/register prime, so one
# verbose line washes out within an exchange instead of compounding.

# Candidate length cue (OFF until measured). One stage-direction line placed
# right after the dialogue so far and before the voice sample and the cue - the
# "Author's Note at depth 0" slot that RP front-ends use for reply length, in
# the USER message (the live channel; system-prompt wording has been inert on
# this model). Phrased as a stage direction, not a rule and not a word count -
# counts are ignored here, and rules get spoken aloud. The token cap has been
# the only lever that ever moved line length on this model (the allocation
# invariant), so this is tested with a paired probe before it goes live.
#   PROBED 2026-09-28 (64 real v11.3 turn prompts, each generated per arm, same
#   prompt, bar registered first: >= 10% shorter, <= 1 leak, speech share kept):
#     stage direction (the line below)        -1% words/line, 0 leaks  -> FAILS
#     "(Keep {speaker}'s next reply short.)"  -7% words/line, 0 leaks  -> FAILS
#   Both RAISED quoted speech (13.1 -> 15.8 / 16.7 words per line) while action
#   stayed at 66% - unmarked prose moved into quotes, the labelling effect, not
#   an allocation change. An early peek at 25 contexts read -10% for the second
#   wording; it regressed to -7% at 64. Kept OFF; the cap is the length lever.
#   v11.4: ON, with the second wording, TOGETHER WITH the cap 95. Probed as a
#   package on the same 64 prompts: -20% words/line, reactions 88% vs 80% (read
#   blind, n.s.), defects 45 vs 55 per 100 lines, 0 leaks. The cap shortens; the
#   note shifts what survives the cut toward speech.
DIALOGUE_BRIEF_CUE  = True
DIALOGUE_BRIEF_LINE = "(Keep {speaker}'s next reply short.)"

# v11.6 SIDE-CHARACTER TAKEOVER (D-09) - see the header. Turns 1-3 run free;
# from turn 4 the REMINDER (only after a takeover in the last two lines) and
# the GUARD (a turn-4+ takeover draw is re-rolled once, never worse).
DIALOGUE_SELF_CUE       = True
TAKEOVER_GUARD          = True
DIALOGUE_SELF_FROM_TURN = 3        # 0-based: turns 4-6 only; turns 1-3 run free
DIALOGUE_SELF_LINE      = "({speaker} speaks as {self}.)"
_REFLEXIVE = {"female": "herself", "male": "himself"}   # anything else: themself

DIALOGUE_RETRY = True
# v5.1 degenerate-reply insurance. If a cleaned line comes back EMPTY,
# duplicates a transcript line verbatim, or parrots the event beat (all
# observed in the first live run), the turn is re-rolled ONCE — same
# sampling params; temperature 0.85 randomness alone diverges. Cost: one
# extra 4-14 s CPU call on the rare bad roll. Set False to measure the raw
# defect rate for the observation log.

# =============================================================================
#  SECTION 3 — StoryCharacter DATACLASS
#
#  name / gender / age_group are GUI passthrough — never model-extracted.
#  gender + age_group also drive the Kokoro voice selection in
#  story_lab_tts5.py. The six _EXTRACT_FIELDS come from the Parser as KV lines.
# =============================================================================

@dataclasses.dataclass
class StoryCharacter:
    name:                str
    gender:              str = "unspecified"  # from GUI: female | male | nonbinary
    age_group:           str = "unspecified"  # from GUI: YoungAdult | MiddleAged | Elder
    role:                str = "unspecified"  # extracted — one archetype phrase
    personality_summary: str = "unspecified"  # extracted — 1-2 sentences max
    speaking_style:      str = "unspecified"  # extracted — tone, pace, vocabulary
    motivation:          str = "unspecified"  # extracted — the static CORE drive;
                                              # the evolving scene objective lives
                                              # in the character MEMORY instead
    voice_sample:        str = "unspecified"  # extracted — one or TWO short
                                              # sentences (v5.1): the strongest
                                              # voice AND length anchor. Stored
                                              # unquoted; re-quoted at injection.
    fp_image:            str = "unspecified"  # extracted — 3-5 CLIP tokens for
                                              # portraits and scene prompts
    # v7.2 FIX 2 — AUTHORED, never extracted. The extractor is a small-model
    # call and paraphrases away exactly the facts that must stay stable: it
    # rendered "companion-class synthetic" as "The Analytical Companion"
    # (OBS-048) and dropped "human" entirely (OBS-053). So these two come
    # straight from the scenario and are never overwritten by LLM output.
    identity:            str = ""             # authored: "Harriet Quill, she/her, human"
    address:             str = ""             # authored (v7.3): the form others use
                                              # aloud, e.g. "Miss Quill" / "Detective
                                              # Kestrel". Placed adjacent to the
                                              # completion cue, where the transcript
                                              # otherwise primes only the first name.
    description:         str = ""             # authored: the raw input description

_EXTRACT_FIELDS = ["role", "personality_summary", "speaking_style",
                   "motivation", "voice_sample", "fp_image"]

# =============================================================================
#  SECTION 4 — OLLAMA INFRASTRUCTURE + POST-PROCESSING HELPERS
# =============================================================================

def _ollama_exe() -> str:
    """v12.3: the Ollama program - from storylab_paths.json (written by Story
    Lab Setup), else PATH, else Ollama's own per-user install folder. Right
    after Setup installs Ollama, PATH in an already-open process does not
    have it yet."""
    try:
        with open(os.path.join(_SCRIPT_DIR, "storylab_paths.json"), encoding="utf-8") as f:
            exe = (json.load(f).get("ollama") or {}).get("exe") or ""
        if exe and os.path.isfile(exe):
            return exe
    except (OSError, ValueError):
        pass
    found = shutil.which("ollama")
    if found:
        return found
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    return local if os.path.isfile(local) else "ollama"


def start_ollama() -> None:
    """Ping Ollama; start it via subprocess if not already running.
    v12.3: 127.0.0.1 (localhost costs ~2 s per request on Windows), the
    program found by _ollama_exe(), no console window, and a wait until the
    server answers instead of a fixed 2 s."""
    try:
        httpx.get('http://127.0.0.1:11434', timeout=3)
        print("  Ollama already running.", flush=True)
    except Exception:
        print("  Starting Ollama...", flush=True)
        subprocess.Popen([_ollama_exe(), 'serve'], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(60):                       # up to ~30 s on a cold start
            time.sleep(0.5)
            try:
                httpx.get('http://127.0.0.1:11434', timeout=2)
                break
            except Exception:
                continue


def unload_ollama(timeout: int = 30) -> None:
    """
    Evict the Ollama model from VRAM so ComfyUI can use the full GPU budget.

    v5 NOTE: with NUM_GPU = 0 dolphin never touches VRAM, so the director
    NEVER calls this. Kept for manual use and for anyone who flips NUM_GPU
    back to GPU mode — in that world this function is load-bearing again.

    CRITICAL: do NOT use keep_alive=0 with MODEL directly. Ollama stores the
    model under its short name, stripping the namespace prefix; the full
    namespaced string is silently a no-op and ComfyUI OOMs. Fix: read the
    actual name from `ollama ps`, then poll /api/ps until empty.
    """
    actual_name = None
    try:
        result = subprocess.run(['ollama', 'ps'], capture_output=True, text=True, timeout=10)
        lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
        if len(lines) >= 2:
            actual_name = lines[1].split()[0]   # first token of second line = model name
            print(f"  Ollama loaded: '{actual_name}'", flush=True)
        else:
            print("  No model loaded in Ollama.", flush=True)
            return
    except Exception as e:
        print(f"  ollama ps failed ({e}), using short name.", flush=True)
        actual_name = MODEL.split('/')[-1]      # best-effort fallback

    for endpoint in ['/api/generate', '/api/chat']:
        try:
            requests.post(f'http://localhost:11434{endpoint}',
                          json={'model': actual_name, 'keep_alive': 0}, timeout=15)
        except Exception:
            pass                                # endpoint may not be loaded — fine

    print("  Waiting for VRAM release", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ps = requests.get('http://localhost:11434/api/ps', timeout=3).json()
            if not ps.get('models'):
                print("  \u2713 Ollama VRAM freed.", flush=True)
                time.sleep(1)                   # one extra second for OS page release
                return
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(f"\n  \u26a0 Ollama did not unload within {timeout}s — continuing.", flush=True)


# =============================================================================
#  v12.2 — THE GAME SEED
#
#  Measured 2026-10-16 (loop_reports/v12_2_saves/seed_probe.py): one prompt
#  sent 3x without a seed (every call before v12.2) gave 3 different lines;
#  with Ollama's `seed` option, the same line 3x. So a game can be replayed -
#  same story, same seed, same player events -> same text - if every call
#  draws its seed from ONE stream: call i of a game gets derive_seed(master,
#  "llm", i). A counter rather than a per-role seed: the re-roll guards need
#  each draw to differ, and a role's label repeats every turn. The counter is
#  the state a save game stores (game_seed_state) and a load restores
#  (set_game_seed), so a resumed game continues the same stream.
#  master None (the default; the research harness) = no seed key at all - the
#  options Ollama receives are byte-identical to v12.1's.
# =============================================================================

_GAME_SEED = {"master": None, "calls": 0}


def derive_seed(master: int, *parts) -> int:
    """A stable 31-bit seed from the game seed and any labels (Ollama-safe)."""
    key = "|".join(str(p) for p in (master,) + parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(key).digest()[:4], "big") & 0x7FFFFFFF


def set_game_seed(master, calls: int = 0) -> None:
    """Start (or resume, with `calls`) a game's seed stream. None = unseeded."""
    _GAME_SEED["master"] = None if master is None else int(master)
    _GAME_SEED["calls"] = int(calls)


def game_seed_state() -> dict:
    return dict(_GAME_SEED)


def _next_call_seed():
    if _GAME_SEED["master"] is None:
        return None
    seed = derive_seed(_GAME_SEED["master"], "llm", _GAME_SEED["calls"])
    _GAME_SEED["calls"] += 1
    return seed


def _flush_prompt_cache() -> None:
    """
    A seed alone did not replay a game: two runs with the same game seed
    differed from the FIRST call on (loop_reports/v12_2_saves/determinism_*).
    Measured (cache_probe.py), one prompt, one seed: cold == reloaded ==
    "a different prompt in between", but the same prompt sent straight after
    itself - its context served from Ollama's prompt cache - came back
    different. Reusing cached context changes the arithmetic of the next
    tokens, and whether it is reused depends on what ran before: another
    game, a GPU hand-over, a re-roll the player clicked. So in a seeded game
    every call is preceded by this one-token request, which replaces the
    cached context; the real prompt is then evaluated fresh, the same way
    every time. Same num_ctx / num_gpu as every call (or Ollama reloads the
    runner); a fixed seed so it never touches the game's stream.
    """
    try:
        chat(model=MODEL, messages=[{"role": "user", "content": "."}],
             options={"num_ctx": NUM_CTX, "num_gpu": NUM_GPU, "num_predict": 1,
                      "temperature": 0, "seed": 0})
    except Exception as e:
        print(f"  ⚠ prompt-cache flush failed: {e}", flush=True)


def build_messages(system: str, *content_blocks: str) -> list:
    """
    Return a FRESH stateless [system, user] pair for one Ollama call.
    History is plain text inside the user message, never prior assistant
    turns. Blocks are joined with a blank line — a natural paragraph break
    ("---" separators got echoed as scene breaks; OBS-011).
    """
    combined = "\n\n".join(content_blocks)
    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": combined},
    ]


def ollama_chat(messages: list, label: str, cap: int,
                params_key: str = "dialogue", stop: list = None,
                temperature=None) -> str:
    """
    Single stateless Ollama call, pinned to CPU (see NUM_GPU).
      `cap`         — integer token limit (num_predict). Non-negotiable
                      infinite-generation safeguard; raise it, never remove it.
      `params_key`  — key into GENERATION_PARAMS for this role's sampling.
      `stop`        — optional stop sequences; generation halts the instant
                      output ends with any of these, and the stop string is
                      stripped from the returned text.
      `temperature` — v5.10: optional per-call override of the role's
                      temperature (the memory-keeper re-roll uses a hotter
                      value to force divergence — OBS-038).
    """
    p = GENERATION_PARAMS.get(params_key, GENERATION_PARAMS["dialogue"])   # role sampling profile
    temp = p["temperature"] if temperature is None else temperature        # v5.10 per-call override
    print(f"  \u21bb [{label}] generating (cap: {cap}, temp: {temp}, "
          f"top_p: {p['top_p']}{', stop=' + str(stop) if stop else ''})...", flush=True)
    opts = {
        "num_ctx":        NUM_CTX,            # prevents silent front-truncation
        "num_predict":    cap,                # non-negotiable infinite-gen safeguard
        "num_gpu":        NUM_GPU,            # 0 = CPU-only, VRAM stays ComfyUI's
        "temperature":    temp,               # v5.10: per-call override or role default
        "top_p":          p["top_p"],         # nucleus cutoff: trim the unlikely tail
        "repeat_penalty": REPEAT_PENALTY,     # resist echoing context back verbatim
        "repeat_last_n":  REPEAT_LAST_N,      # v5.1: how far back the penalty SEES
    }
    if stop:                                  # mechanical stop at structural boundaries
        opts["stop"] = stop
    call_seed = _next_call_seed()             # v12.2: None unless a game seed is set
    if call_seed is not None:
        opts["seed"] = call_seed
        _flush_prompt_cache()                 # a fresh evaluation, every time
    try:
        response = chat(
            model=MODEL,
            messages=messages,
            options=opts,
        )
        return response.message.content.strip()
    except Exception as e:
        print(f"  \u2717 Ollama error [{label}]: {e}", flush=True)
        raise


_SENTENCE_ENDS = ".!?\u2026"   # terminators _trim_to_sentence() recognises ( . ! ? … )

def _trim_to_sentence(text: str) -> str:
    """
    Post-processing backstop for the token cap. v5.1 applies this to
    dialogue, memory, OPENER and RESOLUTION (OBS-016).

    If generation was cut mid-sentence, trim back to the LAST complete
    sentence so the cut is invisible — in the UI, the log, the Kokoro
    read-out, and the transcript, where a ragged line would become a
    ragged-line PRIME for later turns.

    A trailing em-dash counts as a clean ending (an interrupted line is
    valid dialogue). If no terminator exists at all, the fragment is kept —
    a fragment beats an empty reply — but dangling separators are dropped
    (OBS-023: lines like  I'm done playing your games,  read and voice badly).
    """
    text = text.strip()
    if not text or text[-1] in _SENTENCE_ENDS + "\u2014":   # already ends cleanly
        return text
    cut = max(text.rfind(c) for c in _SENTENCE_ENDS)        # last terminator anywhere
    if cut != -1:
        return text[:cut + 1].strip()
    return text.rstrip(",;: ")            # fragment: at least drop dangling punctuation


# v11.3 (D-07): closing marks that may follow a sentence's terminator and
# belong to it: the end of a quote or of an *action beat*.
_LINE_CLOSERS = "\"*\u201d\u2019)"
# v11.5: a closing quote right after one of these is a cut before a dialogue
# tag ('"Stay close," he') - not the model ending its line. Anything else
# before the closing quote is the model's own ending, period or not: v11.3
# keeps '"Then we go together"' whole, as it keeps an unpunctuated *beat*.
_QUOTE_CONTINUES = ",;:"


def _trim_line_to_sentence(text: str) -> str:
    """
    v11.3: _trim_to_sentence for a DIALOGUE line, which mixes speech and beats.

    Cuts back to the last complete sentence like _trim_to_sentence, but keeps
    the closing marks that sit directly after its terminator - '"Bobb!" *She
    grabbed his hand while' -> '"Bobb!"', where the plain trim gave '"Bobb!'
    - and closes a quote the cut left open ('"We sell one memory. Just one,
    and then we' -> '"We sell one memory."'). A line that already ends on a
    terminator or an em-dash is returned as it is, apart from closing an
    open quote; a line with no terminator at all keeps its fragment, as
    _trim_to_sentence does (a fragment beats an empty reply).
    """
    text = text.strip()
    if not text:
        return text
    if text[-1] in _SENTENCE_ENDS + "\u2014":
        out = text
    else:
        cut = max(text.rfind(c) for c in _SENTENCE_ENDS)
        if cut == -1:
            # No full sentence: keep the fragment, as before - but fall
            # through so an open quote is still closed (v11.5; with the
            # leading quote kept, '"We have to go before the' needs it).
            out = text.rstrip(",;: ")
        else:
            end = cut + 1
            while end < len(text) and text[end] in _LINE_CLOSERS:
                mark = text[end]
                # A '"' or '*' is kept only if it CLOSES one that is open. An
                # orphan or the opener of the next beat is left behind, as
                # the plain trim always did.
                if mark in '"*' and text[:end].count(mark) % 2 == 0:
                    break
                end += 1
            out = text[:end].rstrip()
    # Close speech the cut left open - judged by whether the LAST quote opens
    # speech (a letter follows it), not by parity. Written when the dialogue
    # path stripped a line's leading quote (retired in v11.5); still the more
    # robust test, since the model's own broken pairs defeat parity too.
    last = out.rfind('"')
    if last != -1 and last + 1 < len(out) and (out[last + 1].isalnum()
                                               or out[last + 1] in "…'"):
        out += '"'
    return out


# --- v5.1 echo guards (OBS-020 / OBS-024) ------------------------------------
# The first live run showed dolphin occasionally completing the CONTEXT
# instead of the task: a dialogue turn emitted the world paragraph verbatim,
# and three resolutions regurgitated their own input blocks. These helpers
# are the harness answer — mechanical, not prompted.

_CONTEXT_LABELS = (
    "The world:", "The scene:", "What you remember:",
    "The dialogue so far:", "What each character wants:",
    "The full exchange:", "The other character is",
)


def _cut_at_context_label(text: str) -> str:
    """Cut a reply short at the first echoed context lead-in (OBS-024)."""
    earliest = -1
    for label in _CONTEXT_LABELS:
        idx = text.find(label)
        if idx != -1 and (earliest == -1 or idx < earliest):
            earliest = idx
    return text[:earliest].strip() if earliest != -1 else text


_LABEL_LINE = re.compile(r"^([A-Z][A-Za-z '\u2019-]{0,40}):\s*(.*)$")

def _strip_label_lines(text: str) -> str:
    """
    Remove scaffold-header lines the model invents ("The story move:",
    "Unresolved tension:", "Closing:") — the OBS-010 relapse seen in the
    first live run's resolutions and one opener. A line whose label part is
    five words or fewer is treated as a header: a BARE header line is
    dropped; a header WITH content on the same line keeps the content.
    Longer colon lines (real prose) pass through untouched.
    """
    kept = []
    for line in text.splitlines():
        m = _LABEL_LINE.match(line.strip())
        if m and len(m.group(1).split()) <= 5:
            if m.group(2).strip():
                kept.append(m.group(2).strip())    # keep content, drop the header
            continue                               # bare header: dropped entirely
        kept.append(line)
    return "\n".join(kept).strip()


# --- v5.3 memory armor (OBS-027) ---------------------------------------------
# The first scored loop run showed the Memory Keeper collapsing into
# Rocinante's note-taking dialect: "**NOTES:**" markdown scaffolds with
# bullet lists instead of second-person prose, and — worse — Kael's memory
# written from Vess's perspective three rounds straight. Memory FEEDS the
# next round's dialogue context, so a poisoned memory compounds (P9:
# armor the summarizer hardest).

def _strip_markdown(text: str) -> str:
    """
    Flatten RP-finetune markdown out of a prose role's output: remove **
    bold and * italic markers and leading list bullets, then drop any bare
    scaffold header lines that remain (via _strip_label_lines).

    v5.5 (OBS-032): also flattens single-* emphasis, not just ** bold — the
    resolver relapse in iter 007 used both ("*The tension hangs unresolved:*
    Both parties know..."). PROSE-ROLE ONLY (resolver, keeper): those roles
    have no legitimate *action beats*, so every paired *span* is markdown to
    remove. The dialogue lane never calls this — it keeps its beats via
    _normalize_beats / _balance_asterisks instead.
    """
    text = text.replace("**", "")
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s[:2] in ("- ", "* "):
            s = s[2:].strip()
        elif s[:1] == "•":                    # • bullets
            s = s[1:].strip()
        s = re.sub(r"\*([^*\n]+?)\*", r"\1", s)   # *emphasis*/*headers* -> plain
        lines.append(s)
    return _strip_label_lines("\n".join(lines))


# v8.6 (D-01, 9 leaks across iters 172-191): the model turns the resolver's and
# keeper's own INSTRUCTION phrases into output headers —
#   resolver  L~2107  "...state the unresolved tension that now hangs over what
#                      comes next..."   ->  "The unresolved tension that hangs
#                                            over what comes next: With the..."
#   keeper    L~2267  "...what still matters about you and {other}..."
#                                       ->  "What still matters about you and
#                                            Sal right now: Our partnership..."
#
# _strip_label_lines and the _BLOCK_LABELS loop below BOTH structurally miss
# these, on three independent counts: the header sits MID-PARAGRAPH (both are
# anchored to line starts / the first colon), its label runs 7-9 words (the
# line-stripper caps at 5), and 53 chars (that regex caps the label at 40).
#
# So match the authored phrasings literally and position-independently, the way
# _cut_at_context_label already does for user-message block headers — but DROP
# the header and KEEP what follows, because the substance is after the colon.
# The engine authored these strings, so matching them cannot eat honest prose.
#
# The trailing colon is REQUIRED. Without it these read as legitimate sentences
# and must survive: iter 178 has "What still matters about me and Ines right now
# is this terrible truth..." — prose, not a header, and correctly untouched.
_AUTHORED_HEADER_RE = re.compile(
    r"(?:The\s+)?[Uu]nresolved tension[^:\n]{0,50}:\s*"
    r"|What\s+hangs over[^:\n]{0,50}:\s*"
    r"|What\s+(?:still\s+)?matters about[^:\n]{0,50}:\s*"
)

_BLOCK_LABELS = frozenset({
    "what you carried into this scene", "the scene", "the dialogue",
    "how the scene closed", "the world", "what each character wants",
    "the full exchange",
})

def _strip_block_labels(text: str) -> str:
    """
    Remove a harness context-block label the model echoed as a line
    (iter 007: a memory that OPENED with "What you carried into this
    scene:"). The label part before the first colon must EXACTLY match a
    known block label — honest prose never does — so any content after the
    colon on that line is kept. Also matches the keeper's own cue, which
    carries the owner's name ("Your notes to yourself, Kael:").

    v8.6 adds a second pass for INSTRUCTION phrases the model converts into
    output headers — a different failure from an echoed block label, and one
    the line loop below structurally cannot see (see _AUTHORED_HEADER_RE).
    """
    text = _AUTHORED_HEADER_RE.sub("", text)          # v8.6, mid-paragraph safe
    kept = []
    for line in text.splitlines():
        label, _, rest = line.partition(":")
        head = label.strip().casefold()
        if head in _BLOCK_LABELS or head.startswith("your notes to yourself"):
            if rest.strip():
                kept.append(rest.strip())          # keep content, drop the label
            continue                               # bare label line: dropped
        kept.append(line)
    return "\n".join(kept).strip()


# v5.5 (OBS-030): the distinctive phrases of the keeper's demonstration
# line. iter 007 showed the OLD example ("...the manifest... door codes...")
# transplanted near-verbatim into real memories and then canonised into the
# plot via recursion. The example is now content-free (see the keeper
# prompt), and these phrases are TRIPWIRES: if the model echoes the sample
# instead of summarising the scene, the memory is re-rolled. Keep this list
# in sync with the demonstration whenever that wording changes.
_MEMORY_DEMO_PHRASES = ("worse than planned", "ally or a mark", "move first")


def _opening_ngram(text: str, n: int = 4) -> str:
    """First n words of a memory, normalised — used to detect a FROZEN
    opening (same start as last round: the recursion ratchet) or a SHARED
    opening (both characters starting identically off one demonstration)."""
    words = re.findall(r"[a-z0-9']+", text.casefold())
    return " ".join(words[:n])


def _opening_frozen(a: str, b: str, exact_n: int = 4,
                    window: int = 8, jaccard: float = 0.6) -> bool:
    """
    True when memory `a`'s opening repeats memory `b`'s — either an EXACT
    first-`exact_n`-word match OR high word overlap in the first `window`
    words. v5.10 (OBS-038): the exact match alone was defeated by lexical
    mutation ("you're RIGHT bobb something" -> "you're ABSOLUTELY right
    bobb"); the fuzzy overlap catches the mutated variant that slipped the
    n-gram across a 7-round arc.
    """
    if not a or not b:
        return False
    if _opening_ngram(a, exact_n) and _opening_ngram(a, exact_n) == _opening_ngram(b, exact_n):
        return True
    wa = set(re.findall(r"[a-z0-9']+", a.casefold())[:window])
    wb = set(re.findall(r"[a-z0-9']+", b.casefold())[:window])
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= jaccard


def _longest_shared_run(a: str, b: str) -> int:
    """Length (in words) of the longest CONTIGUOUS run shared by a and b —
    a word-level longest-common-substring. A long verbatim run is a strong,
    paraphrase-proof 'reused formulation' signal (n-gram OVERLAP misses
    paraphrase; a shared run does not)."""
    wa = re.findall(r"[a-z0-9']+", a.casefold())
    wb = re.findall(r"[a-z0-9']+", b.casefold())
    best = 0
    prev = [0] * (len(wb) + 1)
    for i in range(1, len(wa) + 1):
        cur = [0] * (len(wb) + 1)
        ai = wa[i - 1]
        for j in range(1, len(wb) + 1):
            if ai == wb[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


_PRONOUNS = {"female": "she/her", "male": "he/him",
             "nonbinary": "they/them", "unspecified": "they/them"}


def _identity_line(char: StoryCharacter) -> str:
    """
    One compact identity string for `char` — v7.2 Fix 2.

    Prefers the AUTHORED `identity` field. Falls back to synthesising
    "Name (pronouns)" from the gender field, so scenarios written before v7.2
    still gain pronoun anchoring without being edited.

    This is the fix for four observations with one root cause: the prompt
    previously received only the GUI first name, so the model invented
    surnames (OBS-041: "Mr. Vesper" for Grant, "Mr. Salerno" for Ferrant,
    "Miss Harriet" for Quill), drifted pronouns (OBS-044), and lost species
    entirely (OBS-053: a human character called herself a synthetic, because
    "synthetic" was in the other sheet every turn and "human" was nowhere).
    """
    if char.identity.strip():
        return char.identity.strip()
    pron = _PRONOUNS.get((char.gender or "unspecified").casefold(), "they/them")
    return f"{char.name} ({pron})"


def _header_lead(text: str) -> bool:
    """
    True when a prose role's FIRST line is a scaffold header rather than
    narration — v7.2 Fix 1. One rule covers every specimen the project has
    collected, because they differ in punctuation but share a shape:

        "Present tense - third person narration"   (instruction paraphrase)
        "No dialogue - just description & action:" (instruction, with colon)
        "A Storm-Blocked Tower" / "Ilsmere Floods" (invented titles)
        "Scene Opening" / "Setting"                (block labels)
        "*" / "---"                                (stray markers)

    The discriminator is punctuation, not vocabulary: narration's opening
    line always carries a sentence terminator (or an em-dash), a header never
    does. The <=9-word cap keeps a long cap-cut opening sentence — which is a
    truncation artifact, not a header — out of scope.

    Earlier guards missed these for three different reasons: _LABEL_LINE
    requires a colon (misses titles), its character class excludes "&", and
    its label cap is 5 words. Shape beats enumeration.
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    first = lines[0].strip()
    if re.search(r"[.!?—]", first):
        return False
    return len(first.split()) <= 9


def _strip_header_lead(text: str) -> str:
    """Drop a header first line and keep the body. A STRIP, not a re-roll:
    the prose under the header is usually sound (iter 036's opener body was
    fine), so deleting one line costs no generation and cannot return
    something worse."""
    if not _header_lead(text):
        return text
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if l.strip():
            return "\n".join(lines[i + 1:]).strip()
    return text


_FIRST_PERSON = re.compile(r"\b(i|i'm|i've|i'll|i'd|me|my|mine|myself|we|we're|"
                           r"our|ours|us)\b", re.I)
# Personal TITLES are the reliable tell for an invented inhabitant: a world
# paragraph may legitimately name a place ("Tessell Minor"), but "Dr. Elena
# Vasquez" is a person the cast does not contain.
_PERSON_TITLE = re.compile(r"\b(dr|mr|mrs|ms|miss|prof(?:essor)?|capt(?:ain)?|"
                           r"sgt|sergeant|lt|lieutenant|adm(?:iral)?|"
                           r"comm(?:ander)?|sir|lady|lord)\.?\s+[A-Z][a-z]+",
                           re.I)


def _setting_defect(setting: str, cast_names: tuple = ()) -> str:
    """
    Typed defect for the World Builder — v7.0 Tier 1. The setting is injected
    into EVERY opener and resolver prompt, so a defect here contaminates the
    whole run; it gets the same never-trust-verify treatment as the keeper.

      "first person"    the paragraph narrates as "I"/"we". 4 of the last 5
                        5.x settings did this and the openers inherited it.
      "invented person" a titled person who is not in the cast (iter 026's
                        "Dr. Elena Vasquez", which then renamed the lead).
      "empty"           nothing usable.
    Returns "" when the setting is clean.
    """
    if not setting or not setting.strip():
        return "empty"
    if _FIRST_PERSON.search(setting):
        return "first person"
    for m in _PERSON_TITLE.finditer(setting):
        named = m.group(0).split()[-1].casefold()
        if not any(named in n.casefold() or n.casefold() in named
                   for n in cast_names if n):
            return "invented person"
    return ""


_ECHO_STOPWORDS = frozenset(
    "the a an and or but of to in on at as with for from by is are was were it "
    "its his her their they she he them this that into over under be been had "
    "has have".split())


def _content_words(text: str) -> list:
    return [w for w in re.findall(r"[a-z']+", text.casefold())
            if w not in _ECHO_STOPWORDS and len(w) > 2]


def _paraphrases_setting(text: str, setting: str, thresh: float = 0.30,
                         min_words: int = 6) -> bool:
    """
    True when `text` OPENS by restating the setting IN OTHER WORDS — the
    paraphrase echo that verbatim tests cannot see (OBS-051, iter 027 r4:
    a first-person setting reappeared as third-person narration, sharing
    almost no contiguous wording).

    Compares CONTENT-WORD overlap of the two FIRST SENTENCES, because the
    echo is front-loaded: the opening sentence restates the world, then the
    passage moves on, which dilutes any whole-text measure below usefulness.

    Thresholds are measured, not guessed. Across 21 real resolutions from
    three runs the single known echo scored 0.389 while every honest
    resolution scored 0.000-0.130, so 0.30 sits in the gap with >2x margin.
    `min_words` skips very short openers ("She left."), where a coincidental
    one-word overlap would otherwise dominate the ratio.
    """
    if not text or not setting:
        return False
    first = _content_words(re.split(r"(?<=[.!?])\s+", text.strip())[0])
    if len(first) < min_words:
        return False
    base = _content_words(re.split(r"(?<=[.!?])\s+", setting.strip())[0])
    if not base:
        return False
    a, b = set(first), set(base)
    return len(a & b) / max(len(a | b), 1) >= thresh


# v7.3 FIX 3: the overlap at which a SOFT-defective memory is too repetitive to
# ship wholesale. Measured, not guessed: across 240 consecutive memory pairs in
# the 20-run replication study, 235 sat at 0-4 words and the only outliers were
# 11, 18, 19 and 61. A bound of 10 catches every real case with wide margin.
_MEMORY_SEVERE_REPEAT = 10


def _strip_repeated_span(memory: str, previous_memory: str,
                         min_run: int = 8) -> str:
    """
    Drop the SENTENCES of `memory` that duplicate `previous_memory`, keep the
    novel ones — v7.3 Fix 3.

    The replication study showed extra attempts cannot fix a banked repeat: in
    iter 055 the keeper detected the defect (`frozen opening`), re-rolled twice,
    hit hard defects on both, and the fallback then shipped the 61-word repeat
    because `soft_keep` was preferred unconditionally.

    Choosing `previous_memory` instead would be WORSE, not better: that 61-word
    span sat in a 94-word memory (a ~65% repeat), while previous_memory is a
    100% repeat — the exact duplicate defect OBS-040 exists to prevent. So the
    answer is salvage rather than selection: strip the copied sentences and keep
    what is new, leaving a memory that actually evolved.

    Mirrors _strip_demo_phrases (v5.11), which does the same operation for a
    different defect and works.
    """
    if not memory or not previous_memory:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", memory.strip())
    kept = [s for s in parts
            if _longest_shared_run(s, previous_memory) < min_run]
    return _trim_to_sentence(" ".join(kept).strip())


def _echoes_setting(opener: str, setting: str, min_run: int = 8) -> bool:
    """
    True when a ROUND-2+ opener has regurgitated the SETTING instead of
    opening the new beat — OBS-042 (iter 023 Run 16: the round-7 opener
    reproduced the setting's first two sentences word-for-word). Two signals:
      * fuzzy opening overlap (_opening_frozen: exact first-4-word n-gram OR
        Jaccard >= 0.6 over the first 8 words) — catches a copy that starts
        at the top, as the r7 specimen did; AND
      * a >= `min_run`-word CONTIGUOUS verbatim run anywhere — paraphrase-
        proof, and catches a copy that follows a short lead-in sentence.
    Eight words in a row is far past any incidental proper-noun reuse a
    legitimate continuation would share with the world paragraph.
    """
    if not opener or not setting:
        return False
    if _opening_frozen(opener, setting):
        return True
    return _longest_shared_run(opener, setting) >= min_run


def _body_repeat(a: str, b: str, min_run: int = 5) -> bool:
    """
    True when memory `a`'s BODY reuses a formulation from `b` — a shared
    verbatim run of >= min_run words. v5.12 (OBS-037 sibling): the frozen-
    opening guard only checks the first words, so iter 020 had James's r1
    and r2 memories share the near-verbatim body "the house isn't really
    about ... heirlooms; she found ... to avoid" under DIFFERENT openings
    and slip through. Five consecutive identical words rarely occur in
    genuinely different prose, so false positives are rare — and it is a
    SOFT defect anyway (a spurious hit just re-rolls once).
    """
    if not a or not b:
        return False
    return _longest_shared_run(a, b) >= min_run


def _memory_defect(memory: str, own_name: str,
                   previous_memory: str = "", peer_memory: str = "") -> str:
    """
    Defect check for a keeper output, or "" when the memory is usable.

    OBS-027: a second-person memory has no business naming its OWN owner
    ("how you now see Kael" inside KAEL'S memory) — the wrong-perspective
    fingerprint. HARD defect (fall back to previous memory).

    OBS-030 (three new checks, all from iter 007):
      - demonstration echo: the keeper copied the example instead of the
        scene ("the manifest"/"door codes" leaked, then became canon). HARD.
      - frozen opening: opening repeats LAST round's memory — the recursion
        ratchet freezing the intro across rounds. v5.10 (OBS-038): now a
        FUZZY match (_opening_frozen), catching lexical mutation. SOFT
        (fresh content still beats stale; the re-roll breaks the recursion).
      - shared opening: opening repeats the OTHER character's memory this
        round — both parroting one demonstration (iter 007: both memories
        opened "You held your ground"). SOFT.
      - repeated body: v5.12 (OBS-037 sibling) — the whole body largely
        repeats last round's under a DIFFERENT opening (iter 020: James r1
        ~ r2), which the opening checks miss. SOFT (recursion-break re-roll).
    """
    if not memory.strip():
        return "empty"                                    # HARD
    if re.search(rf"\b{re.escape(own_name)}\b", memory):
        return "own-name (wrong perspective)"             # HARD
    low = memory.casefold()
    if any(p in low for p in _MEMORY_DEMO_PHRASES):
        return "demonstration echo"                       # HARD
    if previous_memory and _opening_frozen(memory, previous_memory):
        return "frozen opening"                           # SOFT
    if peer_memory and _opening_frozen(memory, peer_memory):
        return "shared opening (matches peer)"            # SOFT
    if previous_memory and _body_repeat(memory, previous_memory):
        return "repeated body"                            # v5.12 SOFT (OBS-037 sibling)
    return ""


_MEMORY_SOFT_DEFECTS = {"frozen opening", "shared opening (matches peer)",
                        "repeated body"}
# Soft = a repetitive INTRO, not poisoned CONTENT. On exhausted re-rolls the
# fresh memory is kept (its body is still this round's); only hard defects
# fall back to the previous memory (stale beats poisoned — the OBS-022 rule).


def _strip_demo_phrases(text: str) -> str:
    """
    v5.11 (OBS-040): drop any SENTENCE that contains a keeper demonstration
    phrase, keeping the rest. When BOTH keeper attempts leak a demo phrase
    (a HARD "demonstration echo" exhaustion), the old fallback returned the
    PREVIOUS memory verbatim — a duplicate (iter 017: round 4 == round 3).
    Removing just the tainted sentence(s) salvages the fresh, this-round
    content so a duplicate is no longer needed. Sentence-level (not phrase-
    level) removal avoids leaving a mangled half-sentence behind.
    """
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in parts
            if not any(p in s.casefold() for p in _MEMORY_DEMO_PHRASES)]
    return _trim_to_sentence(" ".join(kept).strip())


# --- v5.4 dialect embrace (OBS-028, user-directed CREATIVE path) -------------
# Rocinante natively interleaves *asterisk action beats* with speech —
# SillyTavern corpus register. v5.2/v5.3 suppressed and amputated it (the
# cut-at-first-quote strip kept the action and DELETED the speech). Per the
# user's call on StoryLabLoopReport4, the dialect is now embraced: actions
# are legal dialogue-line content; the harness normalises and repairs the
# formatting instead of fighting it. Brackets stay RESERVED for the
# player's event beat — character-emitted [directions] are converted to
# asterisk beats so the two channels stay distinguishable.

def _normalize_beats(text: str) -> str:
    """Convert character-emitted [bracketed] stage directions (with or
    without inner asterisks) into *asterisk* beats."""
    return re.sub(r"\[\s*\*?\s*([^\[\]*]+?)\s*\*?\s*\]", r"*\1*", text)


try:                                    # the view normaliser needs the Tier 2
    import story_lab_metrics as _METRICS  # classifier; engine still runs without
except Exception:                         # it, just without normalisation
    _METRICS = None


_VIEW_CACHE: dict[str, str] = {}
_VIEW_CACHE_MAX = 4096


def _normalize_history_view(line: str) -> str:
    """
    v9.2 — the DIALOGUE VIEW of one history line, with every segment MARKED.
    Storage is untouched; only what the model reads back changes.

    WHY, and why this is not what v9.1 did.
    v9.1 compressed the words inside each beat and left everything else alone.
    It KEPT the asterisks — so "unmarking" was never shown to the model. What
    the view actually taught was two things at once: beats are ~4-word
    flickers, AND bare prose passes through untouched. Writing long narration
    as bare prose is a rational read of that, and it is exactly what the model
    did: marked action fell 53%, bare prose rose 154%, quoted speech FELL 17%.

    So the lever was right and the direction was wrong. The transcript is what
    the model imitates — measured, it moves behaviour ~43pt where prompt
    wording moves ≤7 — but it must be shown the target shape, not a shape with
    a hole in it. Here nothing bare survives into the view:

        beat            -> kept verbatim
        paired quote    -> kept verbatim
        orphan quote    -> re-wrapped properly (a broken pair in the view
                           teaches broken pairs; 16% of runs carry one)
        bare narration  -> wrapped in *asterisks*
        bare speech     -> wrapped in "quotes"

    Measured on the v8.6 corpus, this moves the imitation target from 20% to
    31% quoted with nothing unmarked left to copy, and beats keep their full
    length — v9.1 already showed that shrinking them backfires.

    COST, stated honestly: the bare split comes from the Tier 2 classifier at
    ~86% held-out accuracy, so roughly 14% of bare runs get the wrong wrapper.
    Bare is ~17% of the view, so ~2.4% of what the model reads is mismarked.
    That is the price of removing 100% of the unmarked prose.

    Keeper and resolver are UNAFFECTED — both read `dialogue_history` directly.
    """
    if _METRICS is None:
        return line
    # v10.0 CACHE. A history line is re-normalised once per call it survives in
    # the window, so with HISTORY_WINDOW=6 the same line is recomputed up to six
    # times identically. Normalisation is deterministic and spaCy-backed, and
    # measured on the v9.2 arm it cost 4.1 -> 11.5 min/run (2.8x). Memoising by
    # raw line removes ~5/6 of that work and CANNOT change output.
    hit = _VIEW_CACHE.get(line)
    if hit is not None:
        return hit
    m = re.match(r"^([A-Z][a-zA-Z]{1,12}:\s*)(.*)$", line, re.S)
    if not m:
        return line                              # unlabelled: nothing to normalise
    head, body = m.group(1), m.group(2)

    out: list[str] = []
    pending: list[str] = []          # consecutive same-mode sentences, merged
    pending_mode: str | None = None

    def flush():
        nonlocal pending, pending_mode
        if pending:
            txt = " ".join(pending).strip()
            if txt:
                out.append(f"*{txt}*" if pending_mode == "NARRATION" else f'"{txt}"')
        pending, pending_mode = [], None

    for kind, text in _METRICS.segments(body):
        if kind == _METRICS.MARKED:
            flush()
            out.append(text.strip())
        elif kind == _METRICS.QUOTED:
            flush()
            s = text.strip()
            paired = len(s) >= 2 and s[0] in '"“' and s[-1] in '"”'
            out.append(s if paired else '"' + s.strip('"“”').strip() + '"')
        else:
            for sent in re.split(r"(?<=[.!?])\s+", text):
                sent = sent.strip()
                if not sent:
                    continue
                mode = ("SPEECH" if _METRICS.wc(sent) < 4
                        else _METRICS.classify_bare(sent))
                if mode != pending_mode:
                    flush()
                    pending_mode = mode
                pending.append(sent)
    flush()
    result = head + " ".join(out)
    if len(_VIEW_CACHE) < _VIEW_CACHE_MAX:      # bounded: a long session must not leak
        _VIEW_CACHE[line] = result
    return result


def _balance_asterisks(text: str) -> str:
    """
    Repair an odd asterisk count — the unclosed-beat artifact (iter 004,
    Kael r2.2). A dangling trailing '*' is dropped.

    v5.5 (OBS-031): an unclosed OPENER is almost always a cap-cut mid-beat
    (iter 007: "...instead his*"). Closing it verbatim froze a mid-sentence
    fragment into a legal-looking beat that the ends-with-* rule then
    exempted from the sentence trim. So the open tail is now sentence-
    trimmed FIRST, then closed: "...at an aggressive pace. Kael doesn't
    look back; instead his" -> "*...at an aggressive pace.*". If nothing
    survives the trim, the dangling opener is dropped entirely.
    """
    if text.count("*") % 2 == 0:
        return text
    if text.rstrip().endswith("*"):                   # dangling closer: drop it
        return text.rstrip()[:-1].rstrip()
    open_idx = text.rfind("*")                         # unclosed opener: trim its tail
    head, tail = text[:open_idx], text[open_idx + 1:]
    tail = _trim_to_sentence(tail)                     # keep whole sentences only
    if tail:
        return f"{head}*{tail}*".strip()              # close after the last full sentence
    return head.strip()                               # nothing salvageable — drop the opener


def _strip_action_beats(text: str) -> str:
    """The speech left when *action* spans are removed — '' means the
    reply is action-only (a defect: every line must still SPEAK)."""
    return re.sub(r"\*[^*]*\*", " ", text).strip()


def _is_context_echo(text: str, setting: str) -> bool:
    """
    True when output regurgitates the setting paragraph — the signature of
    the catastrophic resolver failure (three of eight rounds in the first
    live run). Forty verbatim characters of the setting cannot appear in
    honest prose with repeat_penalty active; if they do, it is an echo.
    """
    return bool(setting) and setting[:40] in text

# =============================================================================
#  SECTION 5 — CHARACTER EXTRACTION  (Character Parser AI)
# =============================================================================

_KEY_SYNONYMS = {"archetype": "role"}
# v5.2 (OBS-026): Rocinante renames the requested field — every markdown-
# dialect extraction attempt answered "**Archetype:**" where the prompt
# asked for "role:". Constrained normalisation, per character_builder.py:
# map OBSERVED synonyms only, never guess.


def parse_kv_output(raw: str, char_inputs: dict) -> StoryCharacter:
    """
    Parse KV-line output from the extractor. Robust to model deviations:
    extra lines dropped, missing fields default to "unspecified", synonym
    variants normalised. GUI inputs (name, gender, age) are taken directly
    from char_inputs — never from LLM output.

    v5.2 (OBS-026) — RP-FINETUNE DIALECT PORT. Rocinante answers the KV
    request in its corpus dialect: "**Voice Sample:**" bold Title-Case
    headers, bullet-list values on the lines BELOW a bare header, and
    "Archetype" for "role". The v5.1 parser scored 0/6 on that dialect
    (empty character sheets — every downstream role starves), and the
    extractor's retry temperature bump only pushed the model deeper into
    markdown. The dialect is absorbed HERE, mechanically, instead of
    fought in the prompt (model-empathy §4: port the harness first).

    Note: .strip("'\\\"") also strips the quotes the extractor is asked to
    put around voice_sample — the sample is stored UNQUOTED and re-quoted at
    injection time in _build_dialogue_system().
    """
    _UNSPECIFIED = {"unspecified", "n/a", "none", "unknown", "not specified",
                    "not stated", "not provided", "unclear", ""}
    data = {}
    last_key = None                     # pending field for bullet-list values
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Bullets and markdown emphasis come OFF before key matching:
        # "**Voice Sample:** ..." and "- fp_image: ..." both become KV lines.
        stripped = line.lstrip("-*•# ").strip()
        key, sep, value = stripped.partition(":")
        norm = (key.strip().strip("*_#").strip().lower()
                .replace(" ", "_").replace("-", "_"))
        norm = _KEY_SYNONYMS.get(norm, norm)
        if sep and norm in _EXTRACT_FIELDS:                 # a recognised KV line
            value = value.strip().strip("*").strip().strip("'\"")
            data[norm] = "unspecified" if value.lower() in _UNSPECIFIED else value
            last_key = norm
            continue
        if sep and norm and norm.replace("_", "").isalnum():
            continue                                        # unknown KV key — drop (v5.1 rule)
        if last_key is None or line[0] not in "-*•":
            continue                                        # non-bullet chatter — drop
        # Bullet line under the most recent field header: "fp_image:" (bare)
        # followed by "- grey coat" lines. First bullet fills the empty
        # field; later bullets join comma-separated (CLIP tokens downstream).
        frag = stripped.strip("'\"")
        if not frag:
            continue
        if data.get(last_key, "") in ("", "unspecified"):
            data[last_key] = frag
        else:
            data[last_key] += ", " + frag

    extracted = [k for k, v in data.items() if v != "unspecified"]
    print(f"  \u2713 Extracted {len(extracted)}/{len(_EXTRACT_FIELDS)} fields: "
          f"{', '.join(extracted) or 'none'}", flush=True)

    return StoryCharacter(
        name                = char_inputs.get("name", "Unknown"),
        gender              = char_inputs.get("gender", "unspecified"),
        age_group           = char_inputs.get("age", "unspecified"),
        role                = data.get("role",                "unspecified"),
        personality_summary = data.get("personality_summary", "unspecified"),
        speaking_style      = data.get("speaking_style",      "unspecified"),
        motivation          = data.get("motivation",          "unspecified"),
        voice_sample        = data.get("voice_sample",        "unspecified"),
        fp_image            = data.get("fp_image",            "unspecified"),
        # v7.2: authored fields, taken from char_inputs like name/gender/age —
        # never from LLM output.
        identity            = char_inputs.get("identity",    ""),
        address             = char_inputs.get("address",     ""),
        description         = char_inputs.get("description", ""),
    )


def extract_character(char_inputs: dict, max_retries: int = 2) -> StoryCharacter:
    """
    Character Parser AI: Ollama call -> StoryCharacter (six fields).

    The ONE role that legitimately wants structured output — the KV lines
    ARE the desired format — so the prompt is a plain field list (no
    RULES:/STOP. scaffold, per OBS-011) held stable by 0.2 temperature.

    Retries up to max_retries times if fewer than all six fields extract,
    bumping temperature (+0.15) each retry so the model does not repeat the
    same miss. Returns the richest result seen.
    """
    system = (
        "You are a character analyst. Given a character description, output "
        "exactly six lines in KEY: value format.\n\n"
        "role: one short archetype phrase\n"
        "personality_summary: one or two sentences only\n"
        "speaking_style: tone, pace, vocabulary — what their voice actually sounds like\n"
        "motivation: what they want right now, in one sentence\n"
        "voice_sample: one or two short sentences of dialogue they would actually say, in quotes\n"
        "fp_image: three to five visual tokens — most distinctive feature and outfit\n\n"
        "Write only these six lines. Use 'unspecified' for anything unknown. Do not invent."
    )
    # v5.1 (OBS-018/023): voice_sample is now ONE OR TWO sentences. The
    # sample is the few-shot LENGTH prime — a single ultra-short line begat
    # degenerate "Kid," turns AND became a verbatim catchphrase attractor
    # (five rounds of "I'm just here for my money"). Two sentences prime
    # the requested 2-3 sentence lines and are much harder to parrot whole.

    name = char_inputs.get("name", "Unknown")
    print(f"\n  -- Character Parser: '{name}' --", flush=True)
    user = (f"name: {name}\n"
            f"gender: {char_inputs.get('gender', 'unspecified')}\n"
            f"age: {char_inputs.get('age', 'unspecified')}\n"
            f"description: {char_inputs.get('description', '')}")

    best_char  = None      # richest StoryCharacter seen so far
    best_count = -1        # non-"unspecified" fields in best_char

    for attempt in range(1, max_retries + 2):       # attempts 1..max_retries+1
        # Bump temperature on retries so the model doesn't repeat the same miss.
        retry_temp = GENERATION_PARAMS["char_extract"]["temperature"] + (attempt - 1) * 0.15
        p = {"temperature": min(retry_temp, 0.7),
             "top_p":       GENERATION_PARAMS["char_extract"]["top_p"]}

        print(f"  \u21bb [CharParser[{name}]] attempt {attempt} "
              f"(temp: {p['temperature']})...", flush=True)
        messages = build_messages(system, user)
        try:
            # Direct chat() call (not ollama_chat): the retry loop overrides
            # temperature per attempt, and repeat_last_n is deliberately left
            # at Ollama's default here — a 256-token penalty window would
            # penalise the repeated field-name tokens the KV format needs.
            x_opts = {
                "num_ctx":        NUM_CTX,
                "num_predict":    MAX_TOKENS["char_extract"],
                "num_gpu":        NUM_GPU,      # CPU-pinned like every call
                "temperature":    p["temperature"],
                "top_p":          p["top_p"],
                "repeat_penalty": REPEAT_PENALTY,
            }
            x_seed = _next_call_seed()          # v12.2: the game's seed stream
            if x_seed is not None:
                x_opts["seed"] = x_seed
                _flush_prompt_cache()
            response = chat(
                model=MODEL,
                messages=messages,
                options=x_opts,
            )
            raw = response.message.content.strip()
        except Exception as e:
            print(f"  \u2717 Ollama error [CharParser[{name}]]: {e}", flush=True)
            raise

        print(f"  Raw:\n{raw}\n", flush=True)
        char = parse_kv_output(raw, char_inputs)

        # Count how many of the six fields were actually extracted
        extracted = sum(1 for f in _EXTRACT_FIELDS
                        if getattr(char, f, "unspecified") != "unspecified")

        if extracted > best_count:                    # keep the richest result
            best_char, best_count = char, extracted

        if best_count >= len(_EXTRACT_FIELDS):        # all six — stop retrying
            if attempt > 1:
                print(f"  \u2713 All {len(_EXTRACT_FIELDS)} fields on attempt {attempt}.", flush=True)
            return best_char

        if attempt <= max_retries:
            print(f"  \u26a0 {extracted}/{len(_EXTRACT_FIELDS)} fields — "
                  f"retrying ({attempt}/{max_retries})...", flush=True)

    print(f"  \u26a0 Proceeding with {best_count}/{len(_EXTRACT_FIELDS)} fields "
          f"after {max_retries + 1} attempts.", flush=True)
    return best_char

# =============================================================================
#  SECTION 6 — GENERATION FUNCTIONS
#  One function per AI role. Pure I/O — no side effects, no shared state.
#  System prompts are INLINED in their functions (base-file convention).
# =============================================================================

def generate_setting(desc: str, char_a: StoryCharacter = None,
                     char_b: StoryCharacter = None) -> str:
    """
    World Builder AI: setting description -> 2-3 sentence world context.

    v7.0 TIER 1 \u2014 this role's output is injected into EVERY opener and
    resolver prompt, which made it the engine's most contaminating surface
    and (until now) its only unprocessed one. Four changes:

      PERSON PIN   "third person, no dialogue, no 'I' and no 'you'". The old
                   prompt said "places us in this world" and never fixed the
                   person; 4 of the last 5 settings came back first-person
                   and the openers inherited the register (OBS: D-12 x7).
      CAST PIN     the characters are named and the model is told to name no
                   other person \u2014 the fix for OBS-046 ("Dr. Elena Vasquez"
                   was invented here, then renamed the lead downstream).
      GUARD        _setting_defect() + ONE re-roll. The prompt is the ask;
                   the check is the guarantee (P6). A defective second
                   attempt is still returned \u2014 a flawed world paragraph
                   beats no world at all, and every downstream role strips.
      TRIM/STRIP   _trim_to_sentence(_strip_markdown(...)) like every other
                   prose role, closing the C-19 cap-cut noted generations
                   ago (a mid-sentence setting invites the GM layer).
    """
    names = tuple(c.name for c in (char_a, char_b) if c and c.name)
    system = (
        "You are a world-builder. Read the setting description and write a "
        "dense, present-tense paragraph in THIRD PERSON that places the "
        "reader in this world. Cover where this is, what kind of world it "
        "is, and the atmosphere or tension hanging over it. No dialogue, no "
        "'I', no 'you'. Two to three sentences. Vivid, no padding."
    )
    blocks = [f"Setting description:\n{desc}"]
    if names:
        blocks.append(f"The only people in this world are "
                      f"{' and '.join(names)}. Name no other person.")
    print("\n  -- World Builder --", flush=True)
    msgs = build_messages(system, *blocks)
    raw = ollama_chat(msgs, "WorldBuilder", MAX_TOKENS["setting"], "setting")
    setting = _trim_to_sentence(_strip_markdown(raw))

    defect = _setting_defect(setting, names)
    if defect:
        print(f"  \u26a0 Setting defect [{defect}] - re-rolling once.", flush=True)
        raw2 = ollama_chat(msgs, "WorldBuilder", MAX_TOKENS["setting"],
                           "setting", temperature=0.85)
        setting2 = _trim_to_sentence(_strip_markdown(raw2))
        if setting2 and not _setting_defect(setting2, names):
            setting = setting2

    print(f"  \u2192 {setting[:100]}...\n", flush=True)
    return setting


def generate_opener(setting: str, char_a: StoryCharacter,
                    char_b: StoryCharacter, context_seed: str,
                    round_num: int = 1, prior_history: str = "") -> str:
    """
    Storyteller AI (opening): the scene prose the player reads first.

    TWO VARIANTS — a settled-branch conditional, not a flag:
      Round 1  (context_seed == ""): ESTABLISH the world and both characters,
               close on unresolved tension.
      Round 2+ (context_seed set):   CONTINUE mid-motion on the injected
               event and its consequences (the OBS-013 fix).

    v5.1: output passes through _strip_label_lines() (one live opener
    emitted a bare "Closing:" header) and _trim_to_sentence() (six of eight
    live openers died mid-sentence at the cap — OBS-016). The trim costs at
    most one dangling part-sentence; the narrator no longer reads ragged cuts.
    """
    print("\n  -- Storyteller: opener --", flush=True)
    if context_seed:
        system = (
            "You are a skilled author continuing a story. Present tense, "
            "third person, no dialogue — narration only. The world is "
            "already known; do not re-describe it. Open mid-motion on what "
            "the story context says just happened, show its immediate "
            "consequences in the scene, and close on both characters facing "
            "it. One or two tight paragraphs."
        )
    elif prior_history:
        # v7.1 (OBS-050): an ESTABLISHED relationship must not be re-introduced.
        # iter 027 declared a two-year affair and the model still played a
        # first meeting in r3-r4 ("you're not supposed to be here", "Then who
        # sent you here?") because the RP corpus overwhelmingly opens scene 1
        # on strangers meeting, and the standard round-1 instruction ("bring
        # both characters into the scene") primes exactly that introduction.
        # The premise loses to the corpus prior unless the instruction itself
        # forbids the introduction.
        system = (
            "You are a skilled author opening a scene between two people who "
            "already know each other well. Present tense, third person, no "
            "dialogue — narration only. Place us in the location: its "
            "atmosphere, light, sound, physical texture. Do NOT introduce "
            "them and do NOT let them meet or notice each other for the first "
            "time — their history is established. Open on that history as it "
            "already stands, and close on a moment of unresolved tension "
            "between them. Two tight paragraphs."
        )
    else:
        system = (
            "You are a skilled author opening a scene. Present tense, third "
            "person, no dialogue — narration only. Place us in the location: "
            "its atmosphere, light, sound, the physical texture of the "
            "place. Then bring both characters into the scene and close on "
            "a moment of unresolved dramatic tension. Two tight paragraphs."
        )
    # v7.2 FIX 2: full identity, not the bare first name — the narrator was
    # inventing surnames and forms of address ("Miss Harriet" for Miss Quill).
    chars = (f"The characters:\n"
             f"{_identity_line(char_a)} — {char_a.role}: {char_a.personality_summary}\n"
             f"{_identity_line(char_b)} — {char_b.role}: {char_b.personality_summary}")
    blocks = [f"The world:\n{setting}", chars]
    if context_seed:
        blocks.append(f"The story so far:\n{context_seed}")
    # v7.1 (OBS-050): the history goes LAST, adjacent to the completion cue —
    # attention geography (P4). It is injected EVERY round, not only round 1:
    # iter 027 honoured the premise in rounds 1-2 and reset it in round 3, so
    # pinning only the first round would not have prevented the failure.
    if prior_history:
        blocks.append(f"What is already true between them:\n{prior_history}")
    blocks.append("Write the opening of the scene now.")
    msgs = build_messages(system, *blocks)
    raw = ollama_chat(msgs, "Storyteller[opener]", MAX_TOKENS["opener"], "opener")
    # v5.8 (OBS-036): the opener relapsed into a markdown scaffold header
    # ("**A moment ago:** ...", iter 012 r2) that _strip_label_lines missed.
    # _strip_markdown (which subsumes _strip_label_lines) de-emphasises it —
    # openers are author-voice prose, so markdown there is always a leak.
    # v7.2 Fix 1: drop a scaffold header first line before anything else reads
    # this opener — it otherwise reaches the transcript AND all six of this
    # round's dialogue prompts via "The scene:\n{opener}".
    opener = _trim_to_sentence(_strip_header_lead(_strip_markdown(raw)))
    if not opener:
        # The header was the WHOLE output — nothing survived the strip. This is
        # the only case where Fix 1 costs a generation.
        print("  ⚠ Opener was a bare header - re-rolling once.", flush=True)
        opener = _trim_to_sentence(_strip_header_lead(_strip_markdown(
            ollama_chat(msgs, "Storyteller[opener]",
                        MAX_TOKENS["opener"], "opener", temperature=0.85))))

    # v5.13 (OBS-042): a round-2+ opener must OPEN THE NEW BEAT, not reprint
    # the world (iter 023 r7 reproduced the setting's first two sentences
    # verbatim). Round 1 is exempt — establishing the world there IS the job.
    # On a copy, re-roll ONCE with the setting block DROPPED (nothing to
    # copy); keep the re-roll only if it actually broke the echo (else the
    # first is no worse — thin beats poisoned, the resolver's rule).
    #
    # v7.0 TIER 2: this gate reads `round_num`, NOT `context_seed`. The two
    # meant the same thing in 5.x, which is precisely the trap: pinning an
    # established-relationship premise (OBS-050) seeds context_seed in round
    # 1, and under the old gate that would have switched this guard ON for
    # the one round where reprinting the setting is CORRECT.
    if round_num > 1 and _echoes_setting(opener, setting):
        print("  ⚠ Opener echoed the setting - re-rolling once without it.",
              flush=True)
        reroll_blocks = [chars, f"The story so far:\n{context_seed}",
                         "Write the opening of the scene now."]
        raw2 = ollama_chat(build_messages(system, *reroll_blocks),
                           "Storyteller[opener]", MAX_TOKENS["opener"], "opener")
        opener2 = _trim_to_sentence(_strip_markdown(raw2))
        if opener2 and not _echoes_setting(opener2, setting):
            opener = opener2
    return opener


def generate_dialogue_turn(speaker: StoryCharacter, other: StoryCharacter,
                           setting: str, scene_opener: str,
                           dialogue_history: list[str],
                           memory: str = "", event: str = "",
                           pressure: str = "", round_num: int = 1,
                           turn_index: int = 0) -> str:
    """
    Character AI: one spoken reply from `speaker`.

    Round 1:  memory="" and event="" — nothing carried; the round runs
              WITHOUT the summarizer, as specified.
    Round 2+: memory = this character's rewritten memory (its closing want
              is the scene objective), event = the player's raw injection.

    v5.1 EVENT PLACEMENT (OBS-017). The event enters the TRANSCRIPT as a
    bracketed stage beat in subtitle register —  [The lights cut out.]  —
    chronologically FIRST among the lines:

        turn 1 of the round (no lines yet):     later in the round:
          The scene:                              The dialogue so far:
          <opener>                                [The lights cut out.]
                                                  Vess: "Move — now!"
          [The lights cut out.]                   Kael: "Right behind you."

          Vess: "                                 Vess: "

    At turn 1 the beat is the LAST thing before the completion cue — the
    position this project's own findings say dolphin actually obeys — and
    it recedes naturally as reactions accumulate, exactly like a real
    event. The bracket cadence is corpus-native (subtitle files, chat logs,
    scripts): attended as part of the pattern, but marked NON-SPEECH, so it
    cannot be quoted back as a line (the R5 verbatim-echo failure). The
    beat is assembled per call and never stored in dialogue_history, so the
    resolver and keeper read a pure spoken transcript. One round later the
    keeper folds the aftermath into "What you remember" — breaking news and
    processed experience, two registers, no duplication.

    OPTION E — the proven layers, re-dialected in v5.4 (OBS-028):
      LAYER 1: TRANSCRIPT FORMAT. v5.4: history lines feed back AS EMITTED
               (*action* beats interleaved with speech — Rocinante's
               native register) and the cue is the BARE NAME "Vess:".
               The dolphin-era quote-wrap + open-quote cue forced a
               speech-only dialect the RP finetune kept fighting.
      LAYER 2: STOP SEQUENCES. Halt on the other name or own name. The
               '"\\n' closing-quote stop is retired with the quote cue.
      LAYER 3: POST-STRIP. v5.4: character-emitted [directions] become
               *beats* (brackets stay reserved for the player's event);
               odd asterisk counts are repaired; a lone wrapping quote is
               unwrapped; echoed context labels are cut (OBS-024); the
               sentence trim hides cap cuts (OBS-023) but a closing beat
               "*grins*" is a legal line ending. The v5.2-era
               cut-at-first-quote is GONE — it amputated the speech out
               of mixed action+speech lines (iter 004).
      LAYER 4 (v5.1): DEGENERATE-REPLY RE-ROLL. Empty, verbatim-duplicate,
               beat-parroting — and NEW in v5.4: action-only (a reply must
               still SPEAK) — get ONE retry (DIALOGUE_RETRY). A surviving
               duplicate is returned anyway — a repeated line beats a hole
               in the scene; a surviving empty becomes "…".
    """
    # v5.8 (OBS-029/034): the quoted voice_sample anchors ROUND 1 only; from
    # round 2 the style description carries the voice instead.
    #
    # v7.0 TIER 2: keyed to `round_num`, NOT to memory=="". The empty-memory
    # proxy was load-bearing and fragile — any guard whose fallback returned
    # "" for a memory (the planned refusal fallback did) would have silently
    # re-injected the sample mid-arc and revived the catchphrase parrot that
    # v5.8 eliminated (OBS-029). Round number is the honest signal.
    system = _build_dialogue_system(speaker, include_sample=(round_num == 1))
    # v5.7 (OBS-029): the speaker's voice_sample opening n-gram — the cross-
    # round catchphrase-parrot tripwire for _reply_defect(). Kept ACTIVE every
    # turn (even in round 2+ where the sample is no longer injected) as a
    # backstop against habitual parroting. "" disables it (unspecified sample).
    sample_opening = (_opening_ngram(speaker.voice_sample, 5)
                      if speaker.voice_sample != "unspecified" else "")
    blocks = []

    if memory:                                        # round 2+: what YOU carry
        blocks.append(f"What you remember:\n{memory}")

    # Other character: name + role only — full personality here made
    # speakers ventriloquise each other (settled EXP_2 finding).
    blocks.append(f"The other character is {other.name} ({other.role}).")

    blocks.append(f"The world:\n{setting}")

    if scene_opener:
        blocks.append(f"The scene:\n{scene_opener}")

    # --- LAYER 1: transcript (beat first) + open-quote completion cue ---
    window = dialogue_history[-HISTORY_WINDOW:] if HISTORY_WINDOW > 0 else []
    beat = " ".join(event.split()) if event else ""   # one-line, whatever the player typed
    transcript = []
    if beat:
        transcript.append(f"[{beat}]")                # the stage beat opens the round's record
    for line in window:
        # v5.4 fed lines back AS EMITTED so the transcript would teach the
        # dialect. v9.2 keeps that principle and fixes the exemplar: the view
        # is the same lines with every segment MARKED, so the dialect being
        # taught no longer includes "unmarked prose is fine".
        transcript.append(_normalize_history_view(line))
    if window:                                        # spoken lines exist -> labelled block
        blocks.append("The dialogue so far:\n" + "\n".join(transcript))
    elif beat:                                        # first turn: the beat stands ALONE,
        blocks.append(transcript[0])                  # immediately before the cue
    # v10.1 PRESSURE LINE. The beat is prepended to the transcript on every
    # turn, but it RECEDES from the cue as lines accumulate — by turn 6 with
    # HISTORY_WINDOW=6 it sits six lines up, the weakest position in the
    # block. The measured signature of that decay: in the two runs where the
    # event failed, opener uptake EXCEEDED dialogue uptake (18% vs 14%), the
    # inverse of the corpus runs where it worked (12% vs 30%) — the narrator
    # was carrying the event and the characters were not.
    #   So the conditioner's second field gets a fresher slot. It is NOT the
    # beat repeated (a repeated string is parrot bait, and LAYER 4 would spend
    # its retry on it); it is one clause naming the thing they can no longer
    # avoid. It fades after EVENT_PIN_TURNS because an event stops being news.
    #   Placed BEFORE the voice-sample and address blocks, which keep the two
    # slots immediately before the cue: displacing a proven 12->0 name result
    # (v7.3 Fix 2) for an unproven gain is a bad trade.
    if pressure and turn_index < EVENT_PIN_TURNS:
        blocks.append(f"What neither of them can avoid now:\n{pressure}")
    # v7.3 FIX 2 (positional): the surname loses to the transcript, not to a
    # lack of information. v7.2 put the full identity at the TOP of the system
    # prompt, but a single round's transcript primes the BARE FIRST NAME ~6-7
    # times (speaker labels plus the cue below) and contains the surname zero
    # times — measured on iter 053: "Edmund:" x3, "Harriet:" x3, "Fowler" x0,
    # "Quill" x0. Primacy cannot outvote that much recency, which is why the
    # period register (constant titled address) still drifted after v7.2.
    # So the address forms go HERE, immediately before the cue. Emitted only
    # when a scenario authors them, so modern casts gain no noise.
    # v8.5: the voice sample as a SPOKEN EXEMPLAR near the cue, EVERY round.
    #
    # Two positional experiments settled which channel is live. v7.3 Fix 2 moved
    # the address line into the USER message just before the cue: name defects
    # 12 -> 0, zero variance. v8.2 reordered a clause inside the SYSTEM prompt:
    # +0.4pt, inert. Same principle, opposite outcomes — the user message near
    # the cue is heard, the system prompt is not. Every wording attempt so far
    # has been in the dead channel; this one is not.
    #
    # The CONTENT teaches the shape the census says pays: lines that begin with
    # speech ran 58.3% speech with ZERO markup defects (v8.3 arm, n=91), against
    # 32.6% for beat-led lines. A quoted sample with no action beat models
    # exactly that opening — as an EXEMPLAR, which this model copies far more
    # readily than it follows instructions (v8.1: withdrawing one demonstration
    # moved keeper behaviour 43 echoes -> ~0).
    #
    # Nothing is written into the model's OUTPUT, unlike the v8.3 open-quote cue
    # and its v8.4 repair — both of which manufactured malformed markup (29.5%
    # odd quotes, then 14.4% doubled). This block is input only, so that entire
    # defect class is structurally unavailable.
    #
    # Placed BEFORE the address line, not after: v7.3's fix depends on the
    # address forms sitting IMMEDIATELY before the cue, and displacing a proven
    # 12->0 result for an unproven gain is a bad trade. For the seven corpus
    # scenarios with no authored address this block IS last before the cue (the
    # pure recency test); for the three with one it sits second-to-last.
    #
    # RISK: this partially revives what v5.8 removed — re-injecting the sample
    # every turn caused the catchphrase parrot (iter 012, Kael's "Well now,
    # ain't you just..." three rounds running). Position and framing differ, but
    # that is a hypothesis, not a defence. The `sample_opening` tripwire in
    # _reply_defect stays active every turn and makes the parrot COUNTABLE.
    # KILL CRITERIA: parrot fires materially above the v8.2 arm, or P1 voice
    # distinctness dropping. In round 1 the sample also still appears in the
    # system prompt, so round-1 fires are the duplication signal specifically.
    # Candidate length cue (DIALOGUE_BRIEF_CUE, off by default): after the
    # dialogue so far, BEFORE the voice sample and the address line, so the two
    # proven cue-adjacent blocks keep their slots.
    if DIALOGUE_BRIEF_CUE and DIALOGUE_BRIEF_LINE:
        blocks.append(DIALOGUE_BRIEF_LINE.format(speaker=speaker.name, other=other.name))
    if speaker.voice_sample != "unspecified":
        blocks.append(f'{speaker.name} sounds like: "{speaker.voice_sample}"')

    addr = [c for c in (speaker, other) if c.address.strip()]
    if addr:
        blocks.append("Forms of address: "
                      + "; ".join(f"{c.name} is called {c.address.strip()}"
                                  for c in addr) + ".")
    # v11.6: the self-reminder - turns 4-6, only after a takeover in the last
    # two lines; otherwise nothing is added and the prompt is v11.5's exactly.
    known = _known_names(setting, scene_opener, beat, memory)
    self_cue = _self_cue(speaker, other, window, turn_index, known)
    if self_cue:
        blocks.append(self_cue)                       # immediately before the cue
    blocks.append(f"{speaker.name}:")                 # v5.4 bare-name cue: the model opens
                                                      # with speech OR an *action* beat

    msgs = build_messages(system, *blocks)

    # --- LAYER 2: mechanical stop sequences ---
    stop = [
        f"\n{other.name}:",     # model starts speaking as the other character
        f"\n{speaker.name}:",   # model starts a second turn for itself
    ]                           # v5.4: '"\n' retired with the open-quote cue

    reply = ""
    attempts = 2 if DIALOGUE_RETRY else 1
    # v10.2: the two turns covered by the reaction gate get a larger budget,
    # spent by the SAME arbiter below rather than by a second nested retry —
    # the "one arbiter, one budget" rule that kept the keeper's guards from
    # cascading. Only when a beat is actually live; an eventless round is
    # byte-identical to v10.1.
    _novel_beat = (_event_words(beat)
                   - _event_words(setting) - _event_words(scene_opener)
                   ) if (beat and turn_index < EVENT_REACT_TURNS) else set()
    if _novel_beat:
        attempts = max(attempts, EVENT_REACT_ATTEMPTS)
    banked = ""              # first healthy line a gate flagged (event ignored /
                             # v11.6 takeover): returned if nothing better comes
    for attempt in range(attempts):
        raw = ollama_chat(msgs, f"Char[{speaker.name}]", MAX_TOKENS["dialogue"],
                          "dialogue", stop=stop)

        # --- LAYER 3: post-strip cleanup (v5.4 dialect-aware) ---
        # v11.5: the leading quote is KEPT. The .lstrip('"') here dated from
        # the open-quote cue retired in v5.4; since then a leading quote is
        # the model's own, and stripping it put speech outside quotes (or, with
        # the lone-quote unwrap below, left a speech-only line with none).
        raw = raw.strip()
        # v5.8 (OBS-035): the bare-name cue can echo the speaker's own label
        # at position 0, markdown-wrapped ("**Kael:** ..."). The mid-line
        # name-leak cut below needs a leading newline, so it misses this;
        # strip a leading own/other label here. v11.5: a quote in front of
        # the label ('"Kaya: Hi."') is kept - the lstrip used to hide it.
        raw = re.sub(rf'^("?)\*{{0,2}}\s*(?:{re.escape(speaker.name)}|'
                     rf"{re.escape(other.name)})\s*:\**\s*", r"\1", raw)
        raw = re.sub(r"^\(\s*[A-Z][\w'-]* speaks as \w+\.?\s*\)\s*", "", raw)   # v11.6: echoed reminder
        if raw.startswith("["):                       # leading bracket = the EVENT register —
            close = raw.find("]")                     # keep whatever follows the beat
            raw = (raw[close + 1:] if close != -1 else "").lstrip()
        raw = _normalize_beats(raw)                   # [directions] -> *beats*: brackets stay
                                                      # reserved for the player's event
        if raw.count('"') == 1 and raw.endswith('"'):
            raw = raw[:-1]                            # unwrap a lone dangling wrap-quote
        for name in (speaker.name, other.name):       # belt-and-suspenders name-leak cut
            marker = f"\n{name}:"
            if marker in raw:
                raw = raw[:raw.index(marker)]
        raw = _cut_at_context_label(raw)              # OBS-024: echoed world/scene blocks
        raw = raw.strip()
        # v11.3 (D-07): judge the ending BEFORE the repair can fake one. A
        # closing "*" or '"' the MODEL wrote (even count) is a legal line
        # ending and is never trimmed. The "*" that _balance_asterisks adds to
        # a cap-cut beat used to pass the same test, which exempted 46% of all
        # lines - every line cut inside a beat - from the sentence trim.
        # v11.5: a closing quote after a continuation mark (_QUOTE_CONTINUES)
        # is a cut, not an ending; with opening quotes kept, more cut lines
        # have an even quote count, so this now matters.
        model_closed = ((raw.endswith("*") and raw.count("*") % 2 == 0)
                        or (raw.endswith('"') and raw.count('"') % 2 == 0
                            and raw[:-1].rstrip()[-1:] not in _QUOTE_CONTINUES))
        raw = _balance_asterisks(raw)                 # repair unclosed *beats* (iter 004)
        if model_closed:                              # the model's own closing beat or
            reply = raw                               # quote — never trim it away
        else:
            # v5.6 (OBS-033): when a CLOSED beat ends "sentence.*" with
            # trailing text, _trim_to_sentence cuts at the period — BEFORE
            # the closing "*" — orphaning the beat's opener (iter 009: 5/18
            # lines shipped an unclosed beat). Re-balance after the trim so
            # any beat the cut re-opened is closed again.
            # v11.3: _trim_line_to_sentence keeps the quote/beat closer after
            # the last full sentence and closes a quote the cut left open.
            reply = _balance_asterisks(_trim_line_to_sentence(raw))

        # --- LAYER 4: degenerate-reply re-roll (v5.1; v5.7 adds sample parrot) ---
        defect = _reply_defect(reply, window, beat, sample_opening)
        # v10.2 REACTION GATE. Within the D-06 window, a reply that names
        # nothing the event brought into the scene is a failure of the same
        # kind as an empty or duplicate line, so it joins the same ladder.
        #   The test is deliberately narrow: the reply must reuse a content
        # word the BEAT introduced and that is not already in the setting or
        # the opener. Matching on the beat's whole vocabulary would be
        # satisfied by any shared scene furniture; matching on novel content
        # means the character mentioned the NEW thing.
        #   Honest caveat, recorded here because it will matter when reading
        # the numbers: this gate optimises the uptake metric DIRECTLY. It
        # raises measured uptake by construction, so the number it produces is
        # no longer independent evidence that reactivity improved \u2014 the
        # specimens are. Read the lines, not the percentage.
        if not defect and _novel_beat and not _event_content_kept(
                " ".join(_novel_beat), reply):
            defect = "ignored the event"
            # Bank it. A line that is healthy in every other respect but does
            # not happen to reuse the event's vocabulary is still a good line \u2014
            # "Sixty seconds. Move." reacts perfectly and references nothing.
            # Without this bank the ladder could END on a duplicate or an
            # ellipsis and call that an improvement, so the gate could make
            # the scene WORSE while making the metric better. With it the gate
            # is strictly non-harmful: it upgrades when it finds a referencing
            # line and otherwise returns the first healthy one.
            if not banked:
                banked = reply
        # v11.6 TAKEOVER GUARD (turns 4-6). Same ladder, same bank: a draw in
        # which only someone else speaks is re-rolled once, the retry carrying
        # the reminder; if the retry is no better, the first draw is kept.
        if (not defect and TAKEOVER_GUARD and turn_index >= DIALOGUE_SELF_FROM_TURN
                and _is_takeover(reply, speaker.name, other.name, known)):
            defect = "voices someone else"
            if not banked:
                banked = reply
            print(f"  ⚠ takeover draw ({speaker.name}): {' '.join(reply.split())}", flush=True)
            if not self_cue:
                self_cue = _self_line(speaker)
                blocks.insert(len(blocks) - 1, self_cue)   # right before the cue
                msgs = build_messages(system, *blocks)
        if not defect:
            return reply
        if attempt + 1 < attempts:
            print(f"  \u26a0 Re-rolling {speaker.name}'s line ({defect}).", flush=True)

    if banked:                                        # gate exhausted, not the line
        if defect == "voices someone else" or _is_takeover(banked, speaker.name, other.name, known):
            print(f"  ↯ takeover kept for {speaker.name} (retry no better)", flush=True)
        return banked
    if not reply:                                     # both attempts empty:
        reply = "\u2026"                              # a beat of silence beats a hole
    return reply                                      # a surviving duplicate returns as-is


# ---------------------------------------------------------------------------
# v11.6 takeover detector. A TAKEOVER is a turn in which every quote belongs to
# someone other than its owner. Attribution per quote, in order:
#   1. a tag right after it   '"...," *Oresh says softly*' / 'whispers Bobb'
#   2. a tag right before it  "Captain Oresh's voice crackles ...: "..."";
#      'it <verb>' is never a cast member; he/she/I/they/you is the owner
#      unless the beat before the quote is led by a side character
#   3. the subject of the *beat* right before it: a side-character role, or a
#      name the NARRATOR side already holds (setting, opener, event, memory)
#   4. otherwise the previous quote's speaker; the owner for the first quote.
# A shared turn (the owner speaks too) is NOT a takeover. Built offline on all
# 576 v11.3-v11.5 lines: 22/26 caught, 0/548 false positives (in-sample).
_TK_VERB = (r"(?:says?|said|asks?|asked|repl(?:y|ies|ied)|whispers?|intones?|interjects?|"
            r"calls?|announces?|stammers?|rasps?|murmurs?|continues?|speaks?|crackles?|"
            r"rumbles?|declares?|explains?|chitters?|booms?|growls?|mutters?|adds?|"
            r"responds?|answers?|shouts?|yells?|cries|chokes?)")
_TK_ROLE = (r"(?i:the captain|the boy|the shepherd(?: boy)?|the (?:grey|gray)[-\w]* (?:being|beings|"
            r"alien|aliens|woman|figure|figures)|the (?:being|beings|alien|aliens|creature|dragon|"
            r"beast|golden beast|controller|voice)|a voice|one of them|another one)")
_TK_PRON = r"(?:[Hh]e|[Ss]he|[Tt]hey|I|[Yy]ou|[Ii]t)"
_TK_NAME = r"[A-Z][a-z]+(?: [A-Z][a-z]+)?"
_TK_NOT_A_NAME = {"The", "His", "Her", "Their", "My", "Your", "It", "He", "She", "I", "A",
                  "An", "Then", "But", "And", "With", "Without", "As", "Still", "Now", "Just",
                  "Even", "Oh", "Wait", "Okay", "Yes", "No", "Please", "Something",
                  "Everything", "Nothing"}
_TK_AFTER = re.compile(rf"^\s*[,.!?]?\s*\*?\s*(?:(?P<who>{_TK_ROLE}|{_TK_NAME}|{_TK_PRON})"
                       rf"(?:'s voice)?(?:\s+\w+){{0,2}}?\s+{_TK_VERB}\b|{_TK_VERB}\s+(?P<who2>{_TK_NAME}))")
_TK_BEFORE = re.compile(rf"(?P<who>{_TK_ROLE}|{_TK_NAME}|{_TK_PRON})(?:'s voice)?[^\"*]{{0,60}}?"
                        rf"\b{_TK_VERB}\b[^\"*]{{0,40}}[:,]\s*\*?\s*$")
_TK_BEAT = re.compile(r"\*([^*]+)\*\s*$")
_TK_SUBJ = re.compile(rf"^\s*(?:(?P<role>{_TK_ROLE})\s+(?:[a-z]+ly\s+)?[a-z]+\b|"
                      rf"(?P<who>{_TK_NAME})(?!'s)\s+(?:[a-z]+ly\s+)?[a-z]+s\b)")


def _tk_classify(who: str, owner: str, other: str, known) -> str:
    """'owner' | 'other' | 'npc' | 'pron' | '' (no claim) for one tagged name."""
    w = " ".join((who or "").split())
    if not w:
        return ""
    lw = w.lower()
    if lw in ("he", "she", "they", "i", "you"):
        return "pron"
    if lw == "it":
        return "npc"
    if re.fullmatch(_TK_ROLE, w):
        return "npc"
    if w.split()[0] in _TK_NOT_A_NAME:
        return ""
    last = w.split()[-1]
    if owner in (w, last):
        return "owner"
    if other in (w, last):
        return "other"
    return "npc" if last in known else ""


def _tk_beat_subject(before: str, owner: str, other: str, known) -> str:
    m = _TK_BEAT.search(before)
    s = _TK_SUBJ.match(m.group(1)) if m else None
    if not s:
        return ""
    if s.group("role"):
        return "npc"
    return "npc" if _tk_classify(s.group("who"), owner, other, known) == "npc" else ""


def _tk_quote_speakers(text: str, owner: str, other: str, known) -> list:
    out = []
    quotes = list(re.finditer(r'"[^"]+"', text))
    for i, q in enumerate(quotes):
        nxt = quotes[i + 1].start() if i + 1 < len(quotes) else len(text)
        prv = quotes[i - 1].end() if i else 0
        after = text[q.end():min(nxt, q.end() + 90)]
        before_full = text[prv:q.start()]
        who = ""
        m = _TK_AFTER.match(after)
        if m:
            who = _tk_classify(m.group("who") or m.group("who2"), owner, other, known)
        if not who:
            m = _TK_BEFORE.search(before_full[-140:])
            if m:
                who = _tk_classify(m.group("who"), owner, other, known)
        if who == "pron":
            who = _tk_beat_subject(before_full, owner, other, known) or "owner"
        if not who:
            who = _tk_beat_subject(before_full, owner, other, known)
        if not who:
            who = out[-1] if out else "owner"
        out.append(who)
    return out


def _known_names(*texts: str) -> frozenset:
    """Capitalised words the NARRATOR side holds (setting, opener, event, the
    speaker's memory) - the only names that can take a turn over."""
    words = set()
    for t in texts:
        words.update(re.findall(r"\b[A-Z][a-z]{2,}\b", t or ""))
    return frozenset(words - _TK_NOT_A_NAME)


def _is_takeover(text: str, owner: str, other: str, known=frozenset()) -> bool:
    """True when the line has speech and none of it is its owner's (v11.6)."""
    sp = _tk_quote_speakers(" ".join((text or "").split()), owner, other, known)
    return bool(sp) and all(s in ("npc", "other") for s in sp)


def _self_line(speaker: StoryCharacter) -> str:
    return DIALOGUE_SELF_LINE.format(
        speaker=speaker.name,
        self=_REFLEXIVE.get((speaker.gender or "").lower(), "themself"))


def _self_cue(speaker: StoryCharacter, other: StoryCharacter,
              window: list, turn_index: int, known) -> str:
    """The v11.6 reminder - only on turns 4-6, and only when one of the last
    two lines was a takeover. Otherwise "" and the prompt is unchanged."""
    if not DIALOGUE_SELF_CUE or turn_index < DIALOGUE_SELF_FROM_TURN:
        return ""
    for line in window[-2:]:
        owner, _, text = line.partition(": ")
        owner_other = other.name if owner == speaker.name else speaker.name
        if _is_takeover(text, owner, owner_other, known):
            print(f"  ↺ self-cue for {speaker.name} (takeover in {owner}'s line)", flush=True)
            return _self_line(speaker)
    return ""


def _quote_blind(text: str) -> str:
    """Case-, whitespace- and quote-mark-insensitive form for the parrot and
    duplicate checks (v11.5): a line that differs only in quotes is the same."""
    return " ".join(re.sub(r'["\u201c\u201d]', "", text).casefold().split())


def _reply_defect(reply: str, window: list[str], beat: str,
                  sample_opening: str = "") -> str:
    """
    Name the defect in a cleaned dialogue reply, or return "" if healthy.
    The first four defects were observed verbatim in the first live run.

    v5.7 (OBS-029): `sample_opening` is the speaker's voice_sample opening
    n-gram (see generate_dialogue_turn). The voice_sample is injected into
    the system prompt EVERY turn to hold the voice, but its opening clause
    is also the strongest line-start attractor — iter 009 had Kael open
    ~3 rounds with his sample's "Well now, ain't you just...". The per-
    round duplicate check below cannot see it (history resets each round),
    so a dedicated cross-round check compares the reply's SPOKEN opening to
    the sample's. It re-rolls a verbatim sample-parrot while still letting
    the sample PRIME the voice (only the first few words must differ).
    """
    if not reply:
        return "empty after cleanup"                  # e.g. pure context echo (OBS-024)
    speech = _strip_action_beats(reply)
    if not speech:
        return "action-only reply (no speech)"        # v5.4: beats are welcome, but a
                                                      # dialogue turn must still SPEAK
    # v11.5: compared QUOTE-BLIND. Until v11.5 the cleanup stripped a line's
    # quotes before this check, so '"<the event>"' matched the beat; with the
    # model's quotes kept, an exact compare let a parroted beat through.
    norm = _quote_blind(reply)
    if beat and norm == _quote_blind(beat):
        return "parrots the event beat"               # the R5 injection-echo failure
    for line in window:
        prior = line.split(": ", 1)[1] if ": " in line else line
        if norm == _quote_blind(prior):
            return "verbatim duplicate of a transcript line"    # the R2 mirror (OBS-019)
    if sample_opening and _opening_ngram(speech, 5) == sample_opening:
        return "voice-sample parrot"                  # OBS-029 catchphrase attractor
    return ""


# v5.12 (OBS-037): the resolver relapsed into literary COMMENTARY about the
# scene instead of narrating it — iter 020: "This scene is exploring a
# marriage breakdown through an intimate confrontation...". These lead-ins
# mark a sentence that talks ABOUT the story, not AS it. Kept tight so honest
# narration ("The scene closes as the door slams") is NOT caught.
_META_MARKERS = ("this scene is", "this scene explores", "this scene depicts",
                 "this scene shows", "this scene captures", "this represents",
                 "this moment represents", "this exchange represents",
                 "the story move", "this passage", "in this scene",
                 "this section explores", "this story explores", "this chapter")


def _strip_meta_lead(text: str) -> str:
    """Drop leading sentences that comment ABOUT the scene rather than
    narrate it (OBS-037), keeping from the first real narrative sentence.
    Returns "" if the whole thing was commentary — the resolver then
    re-rolls, and a thin seed beats a meta one (the OBS-022 rule)."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    while parts and any(m in parts[0].casefold() for m in _META_MARKERS):
        parts.pop(0)
    return " ".join(parts).strip()


def generate_resolution(setting: str, char_a: StoryCharacter,
                        char_b: StoryCharacter, dialogue_history: list[str],
                        opener: str = "") -> str:
    """
    Storyteller AI (closing): the Proppian story beat after the round.
    Output becomes the WORLD channel's memory: frame_injection() prepends
    the player event and the result seeds the next opener.

    The prompt is kept VERBATIM from v3 — the prompt was never the failure.
    v5.1 gives the call what dialogue always had, because the first live
    run showed the unarmoured resolver failing five rounds of eight:

      GROUNDING (OBS-021): the OPENER joins the context. "What just
        happened in the world" finally has a world-event source — the live
        resolver invented groups and alliances because it had none.
      STOPS (OBS-020): generation halts if the model starts regurgitating a
        context-block label on a new line (exact labels, colon included, so
        legitimate prose like "The world had shifted" never trips them).
      LABEL STRIP: invented scaffold headers ("The story move:") are removed
        post-hoc, keeping any content beneath them.
      ECHO GUARD + RETRY: if the output contains the setting paragraph
        verbatim, it is a context echo — re-roll once; if the retry echoes
        too, return "" and let frame_injection() build an event-only seed.
        A THIN SEED BEATS A POISONED ONE: the live run showed a garbage
        resolution erasing the desert escape and canonising a hallucinated
        "Kael's team" into the next two openers (OBS-022).
      TRIM: _trim_to_sentence() hides cap cuts, as everywhere else.
    """
    system = (
        "You are a story editor writing the closing beat of this scene in two or "
        "three sentences of flowing prose. "
        "Open with the concrete thing that just changed in the world this round — "
        "name it by what actually happened, grounded in the environment and the "
        "situation, not by category and not with how the characters feel about each "
        "other. Then state the unresolved tension that now hangs over what comes "
        "next. If the characters' bond shifted, mention it only as a consequence of "
        "what happened around them. "
        "Write it AS the story, never ABOUT the story: no summary of 'the scene', "
        "no 'this represents' or 'this scene explores', no labels or numbers — "
        "prose only, past tense, third person."
    )
    # v5.12 (OBS-037): the old prompt ENUMERATED the story-move options ("a
    # threat emerged or drew closer, something was revealed...") and the model
    # copied one verbatim as its opening; and it relapsed into literary
    # commentary ("This scene is exploring..."). The menu is gone and the
    # meta-relapse is forbidden explicitly here AND stripped mechanically below.
    print("\n  -- Storyteller: resolution --", flush=True)
    chars = (f"What each character wants:\n"
             f"{char_a.name}: {char_a.motivation}\n"
             f"{char_b.name}: {char_b.motivation}")
    blocks = [f"The world:\n{setting}", chars]
    if opener:                                        # v5.1 grounding (OBS-021)
        blocks.append(f"The scene:\n{opener}")
    blocks.append("The full exchange:\n" + "\n".join(dialogue_history))
    msgs = build_messages(system, *blocks)

    # Stops fire only when the model EMITS a context label on a new line —
    # full labels with colons, so honest prose never trips them (OBS-020).
    stop = ["\nThe world:", "\nWhat each character wants:",
            "\nThe scene:", "\nThe full exchange:"]

    for attempt in range(2):
        raw = ollama_chat(msgs, "Storyteller[resolution]",
                          MAX_TOKENS["resolution"], "resolution", stop=stop)
        # v5.5 (OBS-032): iter 007 relapsed into markdown scaffold headers
        # ("**The scene ends...:**", "*The tension hangs unresolved:*").
        # _strip_markdown de-emphasises and (via _strip_label_lines) drops
        # bare headers; _strip_block_labels catches an echoed context label.
        # v5.12 (OBS-037): _strip_meta_lead drops a "This scene is exploring..."
        # commentary opener; if that leaves nothing, the resolution WAS meta.
        # v7.1 (OBS-051): _is_context_echo is a VERBATIM first-40-character
        # prefix test, so it missed iter 027's r4 resolution - a PARAPHRASE of
        # the setting converted to third person ("I stand watch outside the
        # docking bay as the cargo shuttle departs..." became "The cargo
        # shuttle departs with its usual groan of engines, leaving Sable
        # alone..."). _echoes_setting adds the fuzzy-opening + >=8-word
        # verbatim-run test already used on openers, so the same defect is now
        # caught on BOTH narration surfaces. Armor every role, not just the one
        # that failed first (model-empathy P7).
        cleaned = _strip_meta_lead(_strip_block_labels(_strip_markdown(raw)))
        if (cleaned and not _is_context_echo(cleaned, setting)
                and not _echoes_setting(cleaned, setting)
                and not _paraphrases_setting(cleaned, setting)):
            return _trim_to_sentence(cleaned)
        if attempt == 0:
            print("  \u26a0 Resolution echoed or went meta — re-rolling once.", flush=True)

    print("  \u26a0 Resolution unusable twice — returning empty (event-only seed "
          "this round; thin beats poisoned).", flush=True)
    return ""


def generate_character_memory(character: StoryCharacter, other: StoryCharacter,
                              opener: str, dialogue_history: list[str],
                              resolution: str, previous_memory: str = "",
                              peer_memory: str = "", event: str = "") -> str:
    """
    Memory Keeper AI: rewrite `character`'s private memory.

    The round summarizer, per character — it answers "what do you now
    carry?" (subjective state), not "what happened?" (the camera view the
    resolution provides). Its payload is what a camera cannot record:
    private knowledge, stance toward the other AS A CONSEQUENCE of events,
    and the closing want — the next round's scene objective.

    RECURSION: reads previous_memory + this round's events, writes a fresh
    memory under the cap. Rewrite-not-append keeps it bounded forever
    (arXiv:2308.15022); "fold in / keeping only what still matters" is the
    compression rule that makes recursion work.

    REGISTER: second person, short plain sentences — it slots under the
    dialogue system's "You are {name}" register AND acts as a length prime
    from the top of the context.

    SCOPE: opener + transcript + resolution. Not the setting (token
    economy), never the upcoming injection (it does not exist yet, and
    characters discover events in-scene — v5.1: as the bracket beat).

    v5.3 (OBS-027): the v5.1 keeper prompt was an instruction LIST ("what
    you did and said, what you learned, gained or lost, and how you now
    see X") — and the first scored loop run showed Rocinante completing
    the list as a NOTES scaffold: markdown headers, bullet points, and,
    three rounds straight, Kael's memory written from Vess's perspective.
    The rewrite is register-first (P2/P3): identity leads ("You are X" —
    the same anchor the dialogue system uses), ONE demonstration line
    shows the wanted second-person prose, no enumerable list to echo.
    v5.5 (OBS-030): iter 007 exposed the demonstration's OWN failure mode.
    The old example ("You held the airlock shut alone. The stranger lied
    about the manifest... You want the door codes next.") transplanted
    near-verbatim into real memories — "the manifest"/"door codes" had no
    source in the scene — and RECURSION froze it: every round read the
    prior memory and kept its opening, so both characters opened "You held
    your ground" for three rounds and "door codes" became the plot's
    MacGuffin (C-09 demonstration attractor + C-18 memory freeze). Three
    coupled fixes: (1) the example is now CONTENT-FREE and does not open
    with an action verb — it teaches register without a plot to copy or a
    "You held" intro to freeze; (2) _memory_defect() gains a demonstration
    -echo tripwire (HARD), plus frozen-opening (vs last round) and shared-
    opening (vs the peer's memory this round) checks (SOFT — re-roll to
    break the repeat, but keep fresh content if it persists); (3)
    peer_memory (the other character's memory, written first this round)
    is passed in so the shared-opening check can fire.

    Armor (P9, summarizers get the strongest): stops on this call's own
    context labels, markdown flatten + block-label + scaffold strip (v5.5,
    OBS-032: a memory opened with "What you carried into this scene:"),
    sentence trim, and the defect detector above. Exhaustion fallback, in
    priority order: a fresh memory with only a SOFT (intro) defect > the
    PREVIOUS memory (stale beats a hard-poisoned one, the OBS-022 rule) >
    any non-empty cleaned attempt (round 1 has no previous) > "".
    """
    # v7.2 FIX 2: identity leads here too. The keeper FEEDS later dialogue, so
    # a memory written without species or pronouns propagates the error — this
    # is where OBS-053 took hold (Nadia's r4 memory declared synthetics "tools",
    # and by r5 she was speaking as one).
    # v8.1 FIX (OBS-065/066) — ANCHOR-THEN-WITHDRAW AT THE KEEPER.
    # The v5.8 voice re-architecture (OBS-034), transplanted from the dialogue
    # role to the memory role because the measurement finally showed the same
    # shape of failure here. The v8.0 study captured keeper stdout for all ten
    # runs: 140 memory slots consumed 211 generations (a 50% overhead), and the
    # single largest cause was the model copying THIS demonstration — 43 fires,
    # 32 of them on the first attempt (22.9%), 3 slots exhausted into a banked
    # defective memory. Crucially, only 5 of the 32 were in ROUND 1; 27 were in
    # rounds 2-7, and the rate ROSE with round number (7/20 at round 7).
    #   Rounds 2+ do not need the example. They already carry a better register
    # anchor: the character's OWN previous memory, sitting in the very next
    # block ("What you carried into this scene:"). The example is then pure
    # attractor — C-09, and model-empathy P3/P8's rule that a CONSTANT
    # demonstration is worse than a one-shot one. Three conservative fixes were
    # already spent on this class (v5.5 content-free example, v5.11 demo-phrase
    # salvage, v7.3 explicit budget) and it survived all three, because the
    # attractor is re-injected on every one of the 140 calls.
    #   So: quote the example in ROUND 1 ONLY (previous_memory empty = round 1,
    # the one call with nothing else to imitate); from round 2 the register is
    # carried by the description plus the character's own accumulated memory,
    # exactly as the voice is carried in the dialogue lane from round 2.
    # Keyed on the ROUND (previous_memory), not on the attempt, so it is stable
    # across the budget's re-rolls — the same discipline as include_sample.
    # This REMOVES generations rather than adding any, so it stays inside the
    # "one arbiter, one budget" constraint. The demo tripwire STAYS: it still
    # guards round 1, and it still catches a phrase carried in by recursion.
    # Round-1 wording is byte-identical to v8.0, so round 1 is unchanged.
    _keeper_lead = (
        f"You are {_identity_line(character)}. The scene just ended. Write the short "
        f"private notes you keep for yourself — two or three plain "
        f'sentences, spoken to yourself as "you"'
    )
    _keeper_demo = (
        ', like: "That went worse than planned. You still can\'t tell if '
        "they're an ally or a mark. Next time you move first.\""
    )
    _keeper_tail = (
        f" Write about THIS scene in your own "
        f"words. Fold in what you carried before, keep only what still "
        f"matters about you and {other.name}, and end with the one thing "
        f"you want next."
    )
    system = _keeper_lead + (_keeper_demo if not previous_memory else ".") + _keeper_tail
    print(f"\n  -- Memory Keeper: {character.name} --", flush=True)
    # Stops on this call's own block labels: if the model starts re-typing
    # the context, generation halts at the boundary instead of canonising it.
    keeper_stops = ["\nThe scene:", "\nThe dialogue:",
                    "\nHow the scene closed:", "\nWhat you carried",
                    "\nWhat broke into"]          # v10.1 event block label

    def _assemble(include_prev: bool):
        # v5.10 (OBS-038): the re-roll rebuilds WITHOUT the previous memory,
        # so it cannot copy a frozen one — it writes fresh from this round.
        blocks = []
        if include_prev and previous_memory:          # round 2+ recursion input
            blocks.append(f"What you carried into this scene:\n{previous_memory}")
        blocks.append(f"The scene:\n{opener}")
        blocks.append("The dialogue:\n" + "\n".join(dialogue_history))
        # v10.1: the EVENT reaches the keeper. Until now the player's event
        # touched only the opener seed and the round's dialogue beat, so an
        # event the dialogue happened to ignore was erased at the round
        # boundary and could never become a fact the world held — measured as
        # 0% of injected novel vocabulary surviving into ANY memory across
        # three arms. The keeper is the only channel that persists, so an
        # event that never reaches it has a half-life of exactly one round.
        if event:
            blocks.append(f"What broke into the scene:\n{event}")
        blocks.append(f"How the scene closed:\n{resolution}")
        blocks.append(f"Your notes to yourself, {character.name}:")  # cue at the very end
        return build_messages(system, *blocks)

    result = ""
    soft_keep = ""      # a fresh memory whose only flaw is a repetitive intro
    soft_overlap = 10 ** 6   # v7.3: overlap of the banked soft candidate
    demo_stripped = ""  # v5.11: a fresh memory with its demo-echo sentence removed
    any_keep  = ""      # any non-empty cleaned attempt — last-resort fallback
    # v7.2 FIX 3: ONE EXPLICIT BUDGET (MEMORY_ATTEMPTS), spent in priority
    # order, replacing the implicit two-attempt loop. The sweep showed one
    # re-roll is not enough: survivors of 18 and 11 words in 2 of 5 trials,
    # after 102 words in iter 031. The repetition is regenerated from the ROUND
    # CONTEXT, so dropping previous_memory does not remove its cause — it needs
    # another draw. Escalation ladder, hotter each time:
    #     attempt 1: full context, role temperature
    #     attempt 2: recursion broken (no previous_memory), 0.85
    #     attempt 3: recursion broken, 1.0 — a genuinely different draw
    # This is the "one arbiter, one budget" rule applied to the role that
    # needed it first: the guards share this allowance instead of each adding
    # its own retry, which is what would have risked a cascade.
    for attempt in range(1, MEMORY_ATTEMPTS + 1):
        reroll = attempt > 1
        msgs = _assemble(include_prev=not reroll)
        raw = ollama_chat(msgs, f"MemKeeper[{character.name}]",
                          MAX_TOKENS["char_memory"], "char_memory",
                          stop=keeper_stops,
                          temperature=(None if attempt == 1
                                       else 0.85 if attempt == 2 else 1.0))
        # flatten scaffold, drop echoed block labels (OBS-032), trim clean
        cleaned = _trim_to_sentence(_strip_block_labels(_strip_markdown(raw)))
        defect = _memory_defect(cleaned, character.name,
                                previous_memory, peer_memory)
        if not defect:
            result = cleaned
            break
        if cleaned:
            any_keep = cleaned
            if defect in _MEMORY_SOFT_DEFECTS:
                # v7.3: keep the LEAST repetitive soft candidate, not the first
                # one banked. Costs nothing and helps whenever more than one
                # soft draw exists (it would not have saved iter 055, whose
                # other two attempts hit hard defects).
                _ov = (_longest_shared_run(cleaned, previous_memory)
                       if previous_memory else 0)
                if not soft_keep or _ov < soft_overlap:
                    soft_keep, soft_overlap = cleaned, _ov
            elif defect == "demonstration echo":      # v5.11 (OBS-040)
                stripped = _strip_demo_phrases(cleaned)
                if len(stripped.split()) >= 8:        # enough left to be a real memory
                    demo_stripped = stripped
        print(f"  ⚠ Memory defect [{defect}] "
              f"{'- exhausted.' if attempt == MEMORY_ATTEMPTS else f'- re-roll {attempt + 1}/{MEMORY_ATTEMPTS}.'}",
              flush=True)
    else:
        # v5.11 priority: fresh-but-repetitive intro > fresh demo-echo with the
        # tainted sentence removed (OBS-040, beats a duplicate) > previous
        # (stale beats poisoned) > any non-empty cleaned attempt > "".
        # v7.3 FIX 3: a banked soft candidate that is SEVERELY repetitive is
        # salvaged rather than shipped whole — strip the copied sentences and
        # keep the novel ones. Falling back to previous_memory instead would be
        # a 100% repeat, i.e. worse than the partial it replaces.
        if (soft_keep and previous_memory
                and _longest_shared_run(soft_keep, previous_memory)
                >= _MEMORY_SEVERE_REPEAT):
            salvaged = _strip_repeated_span(soft_keep, previous_memory)
            if len(salvaged.split()) >= 8:       # enough left to be a real memory
                print(f"  ⚠ Memory severely repetitive - salvaged "
                      f"{len(salvaged.split())}w of {len(soft_keep.split())}w.",
                      flush=True)
                soft_keep = salvaged
        result = soft_keep or demo_stripped or previous_memory or any_keep
    print(f"  \u2192 {result[:100]}...\n", flush=True)  # truncated dialogue — trim it clean
    return result


def generate_scene_prompt(scene_text: str, char_a: StoryCharacter,
                          char_b: StoryCharacter) -> str:
    """
    Scene Prompter AI: one line of RAW comma-separated CLIP keywords for
    the round's wide scene image. Prompt kept VERBATIM from v3 (the
    validated OBS-014a fix). Returns RAW keywords only — the CLIP boosters
    live in story_lab_images5.wrap_scene_prompt(): engine owns Ollama,
    images owns CLIP framing.
    """
    system = (
        "You are an image-prompt engineer for a text-to-image model. Read the scene "
        "and write a single line of comma-separated visual keywords capturing the "
        "most visually dramatic moment — under fifty tokens. "
        "Order the keywords like this: the action and key object first, then the "
        "environment and lighting, then the mood and colour, then the character "
        "tokens exactly as given. "
        "Describe what is SEEN, not who is present — translate the moment into visual "
        "detail, and copy the character tokens verbatim rather than naming people. "
        "One line of keywords only, no sentences."
    )
    print("\n  -- Scene Prompter --", flush=True)
    fp_parts = [f"{c.name}: {c.fp_image}"
                for c in (char_a, char_b) if c.fp_image != "unspecified"]
    fp_block = "\n".join(fp_parts) or "(no character tokens)"

    msgs = build_messages(
        system,
        "The scene:\n" + scene_text[:600],            # first 600 chars carry the moment
        "Character tokens (copy these verbatim):\n" + fp_block,
    )
    raw = ollama_chat(msgs, "ScenePrompter", MAX_TOKENS["scene_prompt"], "scene_prompt")
    keywords = " ".join(raw.split())                  # collapse stray newlines to one line
    print(f"  \u2192 {keywords[:100]}...", flush=True)
    return keywords

# =============================================================================
#  v12.1 \u2014 THE SCENE PAINTER  (three layers, one cue per call)
#
#  generate_scene_prompt() above is v3's and is no longer called by
#  director12. Read across every v12.0 image run it returned 5-9 words that
#  kept one trivial detail and dropped the place: "Scratching boots on metal
#  gridding" (a hangar), "Heels-click, stone-thump" (a castle entrance hall
#  full of purple sparks - which lived only in the staged event it never saw),
#  "Dracona stepping onto platform" (drawn as a dragon). Four mechanisms:
#    1. It saw the first 600 characters of the opener and nothing else - not
#       the world, not the player's event, not its staging.
#    2. It was handed "Name: tokens" lines and asked for people, so names and
#       people's actions filled the prompt.
#    3. One cue asked for action, place, light, mood AND people in one line;
#       this model completes the cue it is given and spends its budget on the
#       first thing (the one-cue-per-field rule, v10.1).
#    4. "Under fifty tokens" - written against a 77-token CLIP limit that
#       ComfyUI does not have: CLIPTextEncode encodes every 77-token section
#       and concatenates them (comfy/sd1_clip.py, torch.cat on dim -2).
#  The painter asks for THREE layers, each in its own call with its own cue,
#  of an EMPTY scene - images12 puts "no humans, scenery" in front of them and
#  people in the negative. Inputs per round: the player's world description
#  (round 1 only), the setting, the opener in full, and - from round 2 - the
#  player's event and its staging, placed nearest the cue.
#  One demonstration line per layer from a story NO scenario uses (a desert
#  caravanserai; a lighthouse was the first draft and is the horror world),
#  so its echo can be told from the story's own words: images12 drops any tag
#  that only the demonstration could have supplied.
# =============================================================================

SCENE_LAYERS = ("place", "things", "light")

SCENE_EXAMPLE = {
    "place":  "caravanserai courtyard, sandstone arches, carved wooden balconies, "
              "tiled fountain, palm trees, striped market awning",
    "things": "sparks leaping from a fallen brazier, spilled spice sacks, overturned "
              "brass lantern, scattered coins, torn silk banner caught in the wind",
    "light":  "dusk, low orange sun, long shadows, dust haze, warm lamplight, "
              "deep blue sky",
}
# "Things in view:" (first draft) came back as the room again; the cue now
# names the MOMENT's objects and effects, and the demonstration leads with one.
_SCENE_CUE = {"place": "Place:", "things": "Objects and effects:", "light": "Light:"}
_SCENE_FRAME = (
    "A background painter is preparing the backdrop for this moment of the "
    "story: the place itself, painted empty - nobody standing in it, no faces, "
    "no animals - only the room or the landscape, the things in it and the "
    "light. The painter's notes are short image tags separated by commas."
)
# THINGS gets its own frame. Under the shared one it described the room
# again (A/B on the 9 event rounds, things_variant.log: castle round "Marble
# floor polished to mirror shine"); asked for what the moment LEAVES BEHIND
# it brought the event in - "sparks swirling mid-air, scorch marks on stone
# floor", "shattered scale fragments glinting", "maintenance drone hovering".
_SCENE_FRAME_MOMENT = (
    "A background painter is preparing the backdrop for this moment of the "
    "story. The scene is painted empty - nobody in it, no faces, no animals - "
    "so what is happening right now has to show in the things it leaves "
    "behind: objects, effects and traces. The painter's notes are short image "
    "tags separated by commas."
)
# Which context each layer sees. The SETTING is written once, at session
# start, about the opening place: in the first draft it dragged later rounds'
# light back to round 1 (Hogwarts r6, set in the castle, lit as "Hogwarts
# station ... scattered students"). So it anchors PLACE every round, LIGHT in
# round 1 only, and never THINGS - which is about this moment alone.
_SCENE_SEES_SETTING = {"place": True, "things": False, "light": False}


def scene_painter_messages(layer: str, setting: str, opener: str,
                           round_num: int = 1, world_desc: str = "",
                           event: str = "", place_sees_setting: bool = True) -> list:
    """
    The [system, user] pair for one layer. Pure - unit-testable.
    v12.3: place_sees_setting=False (Cinematic) shows the setting to PLACE in
    round 1 only. Live game 1 (2026-10-17): the player married the leads in
    the Great Hall, then sent them to a tropical beach, and PLACE - anchored
    on the setting every round - still painted "Platform 9 3/4, King's Cross"
    under a Great Hall / tropical-sunset LIGHT layer (which never saw it).
    """
    blocks = []
    if round_num <= 1 and (world_desc or "").strip() and layer != "things":
        blocks.append("The world:\n" + world_desc.strip())
    sees = _SCENE_SEES_SETTING[layer] and (place_sees_setting or round_num <= 1)
    if (setting or "").strip() and (sees or (round_num <= 1 and layer == "light")):
        blocks.append("The place:\n" + setting.strip())
    blocks.append("The scene:\n" + (opener or "").strip())
    if (event or "").strip():                       # nearest the cue: Law 2
        blocks.append("What just happened:\n" + " ".join(event.split()))
    cue = _SCENE_CUE[layer]
    frame = _SCENE_FRAME_MOMENT if layer == "things" else _SCENE_FRAME
    blocks.append(f"{frame}\n\nFor a different story, the painter wrote:\n"
                  f"{cue} {SCENE_EXAMPLE[layer]}\n\nFor this story:\n{cue}")
    return build_messages("You write image tags for background paintings.", *blocks)


_SCENE_ITEM_SPLIT = re.compile(r"\s*[,;|]\s*")
# Meta-label prefixes the RP dialect puts inside a tag line ("Time: dusk",
# "Lighting:** amber glow") - the label goes, the value stays. A closed list:
# an open "Word:" pattern would also eat place names ("Hogsmeade Station:
# cobblestones slick with evening mist", first draft, hp_r4).
_SCENE_INNER_LABEL = re.compile(
    r"^(?:(?:background\s+)?(?:painting\s+)?(?:image\s+)?tags|background\s+painting|"
    r"background(?:\s+elements)?|scene|light\s+source|notes|location|place|"
    r"setting|time(?:\s+of\s+day)?|light(?:ing)?|mood|atmosphere|weather|"
    r"colou?rs?|palette|interior|exterior|objects?(?:\s+and\s+effects)?|effects?)"
    r"\s*:\s*", re.IGNORECASE)


def scene_items(text: str) -> list:
    """Split a tag line on , ; | into non-empty items."""
    return [t for t in _SCENE_ITEM_SPLIT.split(text or "") if t.strip()]


def _scene_layer_text(raw: str, layer: str) -> str:
    """
    One line of tags from a raw completion, in the RP dialect it actually
    arrives in (first draft, 20 cases): "**Image Tags:**" header lines with
    the tags on the NEXT line - a "\\n\\n" stop cut 9 of 20 light layers down
    to the header alone -, a repeated cue, "Label: value" items, bullets.
    Stops at any other layer's label. Markdown is removed, never the content.
    """
    out = []
    own = _SCENE_CUE[layer].lower()
    others = tuple(c.lower() for k, c in _SCENE_CUE.items() if k != layer)
    for line in (raw or "").splitlines():
        s = line.replace("**", "").replace("__", "").strip().lstrip("-*\u2022#> ").strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith(others) or low.startswith(("for this story", "for a different")):
            break
        if low.startswith(own):
            s = s[len(own):].strip()
        if not s or (s.endswith(":") and len(s.split()) <= 5):   # a header line
            continue
        out.append(s.rstrip(",. "))
    items = [_SCENE_INNER_LABEL.sub("", t).strip() for t in scene_items(", ".join(out))]
    return ", ".join(t for t in items if t)


def generate_scene_layers(setting: str, opener: str, round_num: int = 1,
                          world_desc: str = "", event: str = "",
                          place_sees_setting: bool = True) -> dict:
    """
    v12.1: {"place": ..., "things": ..., "light": ...} - raw tag lines, one
    Ollama call each. A layer that comes back with fewer than two tags gets
    one hotter redraw (its own budget of two; nothing else retries).
    Hygiene (names, people, sounds, demo echo) is images12's, not this role's.
    v12.3: place_sees_setting - see scene_painter_messages (Cinematic: False).
    """
    print("\n  -- Scene Painter --", flush=True)
    layers = {}
    p = GENERATION_PARAMS["scene_layer"]
    for layer in SCENE_LAYERS:
        msgs = scene_painter_messages(layer, setting, opener, round_num,
                                      world_desc, event, place_sees_setting)
        # No "\n\n" stop: the dialect puts a header and a blank line BEFORE
        # the tags. The cap bounds length; the labels below bound the layer.
        stops = (["\n" + c for k, c in _SCENE_CUE.items() if k != layer]
                 + ["\n**" + c for k, c in _SCENE_CUE.items() if k != layer]
                 + ["\nFor a different story", "\nFor this story"])
        text = ""
        for attempt in range(2):
            raw = ollama_chat(msgs, f"ScenePainter[{layer}]", MAX_TOKENS["scene_layer"],
                              "scene_layer", stop=stops,
                              temperature=p["temperature"] + 0.2 * attempt)
            text = _scene_layer_text(raw, layer)
            if len(scene_items(text)) >= 2:
                break
            print(f"  \u26a0 Scene layer [{layer}] thin ({text!r}) - redraw", flush=True)
        layers[layer] = text
        print(f"  \u2192 {layer}: {text[:100]}", flush=True)
    return layers

# =============================================================================
#  v12.3 \u2014 THE CINEMATOGRAPHER  (cinematic scenes: the characters drawn IN
#  the scene, as the story has them right now)
#
#  The user's design (2026-10-17): beside the v12.1 characterless scene
#  ("Classical"), an optional "Cinematic" scene that puts both leads in the
#  picture with their CURRENT clothes and what they are doing - the wedding
#  dress in the wedding round, the swimsuit on the beach - plus whoever else
#  is around. Drawn by an Anima checkpoint, whose Qwen3 text encoder reads
#  sentences per character (loop_reports/v12_3_cinematic/: the SDXL
#  checkpoint fused or tripled the pair on the same text).
#  Four fields, ONE CUE PER CALL (the v10.1 rule - a second labelled field
#  from one completion came back 0 times in 6):
#    LOOKS     once per character at game start: face, hair, eyes, build,
#              marks - never clothes (images12 drops clothing items), so the
#              clothes can change while the face stays.
#    WEARING   every round, per character: carried forward from the last
#              round ("Last seen wearing:") unless the story changed it. The
#              player's event is placed nearest the cue (Law 2): it is the
#              newest information and the one most likely to change clothes.
#    RIGHT NOW every round, per character: pose, gesture, expression, from
#              the opener and the first dialogue lines (the latest lines last).
#    OTHERS    every round: who else is in view, or nobody.
#  Each with one demonstration from a story no scenario uses (a rainy fishing
#  harbour) so a demo echo can be told from the story's own words. Hygiene
#  (names, clothes in LOOKS, demo echo, "nobody") is images12's. Only the
#  director calls these, and only in Cinematic mode: a Classical game makes
#  exactly v12.2's calls.
# =============================================================================

CINE_FIELDS = ("looks", "wearing", "doing", "others")

CINE_EXAMPLE_NAME = "Milo"
CINE_EXAMPLE = {
    "looks":   "short curly red hair, freckles, amber eyes, broad shoulders, "
               "a chipped front tooth",
    "wearing": "a rain-soaked yellow oilskin coat, rubber boots and a grey "
               "knitted scarf",
    "doing":   "crouching on the pier, hauling a dripping net, squinting into "
               "the rain",
    "others":  "two fishermen mending nets on an upturned boat, gulls on the "
               "bollards",
}


def _cine_cue(field: str, name: str = "") -> str:
    return {"looks": f"{name}'s appearance:",
            "wearing": f"{name} is wearing:",
            "doing": f"{name}, right now:",
            "others": "Others in view:"}[field]


_CINE_FRAME = {
    "looks":   ("A character illustrator is noting how {name} looks - face, hair, "
                "eyes, build and any marks - but not the clothes, which change from "
                "scene to scene. The notes are short image tags separated by commas."),
    "wearing": ("A costume designer is noting exactly what {name} is wearing at this "
                "moment of the story. Clothes stay the same from scene to scene "
                "unless the story changes them. The notes are short image tags "
                "separated by commas."),
    "doing":   ("A storyboard artist is sketching this exact moment. The notes say "
                "what {name} is doing right now - pose, gesture, expression - as "
                "short image tags separated by commas."),
    "others":  ("A storyboard artist is noting who else can be seen in this moment "
                "besides {name} - background figures, crowds, creatures - as short "
                "image tags separated by commas, or nobody if the two are alone."),
}


def cine_messages(field: str, name: str, description: str = "", scene: str = "",
                  event: str = "", previous: str = "", world: str = "",
                  player_text: str = "") -> list:
    """
    The [system, user] pair for one cinematographer call. Pure.
    v12.3 player_text (WEARING): the player's own words, once more, as the
    last story line - "The player said: ...". Probe on 7 real cases x 3
    seeds (loop_reports/v12_3_cinematic/probe_wearing.log): a clothes change
    in the event reached WEARING 2/12 without it, 11/12 with it (the staged
    rewrite, and the opener, often keep the old clothes); moving "Last seen
    wearing" further from the cue added nothing.
    """
    blocks = []
    if field == "looks":
        blocks.append(f"{name}:\n{(description or '').strip()}")
    elif field == "wearing":
        if (description or "").strip():
            blocks.append(f"{name}:\n{description.strip()}")
        if (previous or "").strip():
            blocks.append(f"Last seen wearing: {previous.strip()}")
        if (scene or "").strip():
            blocks.append("The scene:\n" + scene.strip())
        if (event or "").strip():                    # nearest the cue: Law 2
            blocks.append("What just happened:\n" + " ".join(event.split()))
        if (player_text or "").strip():
            blocks.append("The player said: " + " ".join(player_text.split()))
    else:                                            # doing / others
        if (world or "").strip():
            blocks.append("The world:\n" + world.strip())
        if (event or "").strip():
            blocks.append("What just happened:\n" + " ".join(event.split()))
        if (scene or "").strip():                    # the latest lines last
            blocks.append("The scene:\n" + scene.strip())
    frame = _CINE_FRAME[field].format(name=name)
    demo_cue = _cine_cue(field, CINE_EXAMPLE_NAME)
    blocks.append(f"{frame}\n\nFor a different story, the notes read:\n"
                  f"{demo_cue} {CINE_EXAMPLE[field]}\n\nFor this story:\n"
                  f"{_cine_cue(field, name)}")
    return build_messages("You write image tags for illustrations of a story.", *blocks)


# The RP dialect answers a tag cue with a labelled bullet list (first live
# probe, 2026-10-17, the user's Hogwarts rounds): "**Pose:** Standing tall
# beside mountain of luggage", "**Expression:** Supercilious smirk", and for
# Harry's RIGHT NOW: "**Setting:** Platform Nine and Three-Quarters",
# "**Characters Present:** Dracona Malfoid (standing near luggage)". A line
# whose label names another field or the scene is dropped whole; any other
# short label ("Pose:", "Gesture:", "Hair:") is cut and its value kept.
_CINE_WRONG_FIELD = frozenset([
    "setting", "location", "place", "time", "weather", "time/weather", "scene",
    "background", "characters", "characters present", "others", "others in view",
    "lighting", "light", "mood", "atmosphere"])
_CINE_LABEL = re.compile(r"^([A-Za-z][A-Za-z /'-]{0,24}?)\s*:\s*")


def _cine_text(raw: str, field: str, name: str = "") -> str:
    """One tag line from a raw completion: markdown, bullets, a repeated cue
    and inner labels off; wrong-field lines dropped; stops at a blank line
    after content or at another field's cue. Content is never re-worded."""
    own = _cine_cue(field, name).lower()
    others = tuple(_cine_cue(f, name).lower() for f in CINE_FIELDS if f != field)
    out = []
    for line in (raw or "").splitlines():
        # "+" bullets too (live game 1: "+ Expression shifts rapidly...")
        s = line.replace("**", "").replace("__", "").strip().lstrip("-*+\u2022#> ").strip()
        if not s:
            if out:
                break
            continue
        low = s.lower()
        if low.startswith(others) or low.startswith(("for this story", "for a different")):
            break
        if low.startswith(own):
            s = s[len(own):].strip()
        if not s or (s.endswith(":") and len(s.split()) <= 5):
            continue
        s = s.strip("`").strip()                  # live game 2: a "```" fence
        if not re.search(r"[A-Za-z]", s):         # alone counted as an answer,
            continue                              # so the redraw never fired
        m = _CINE_LABEL.match(s)
        if m:
            if m.group(1).strip().lower() in _CINE_WRONG_FIELD:
                continue
            s = s[m.end():].strip()
            if not s:
                continue
        out.append(s.rstrip(",. "))
    return ", ".join(t.strip() for t in scene_items(", ".join(out)) if t.strip())


def generate_cine_field(field: str, name: str, description: str = "",
                        scene: str = "", event: str = "", previous: str = "",
                        world: str = "", player_text: str = "") -> str:
    """
    v12.3: one cinematographer field as a raw tag line. A field that comes
    back empty gets one hotter redraw (its own budget of two, as the scene
    painter's layers). WEARING falls back to `previous` - clothes carry over.
    """
    msgs = cine_messages(field, name, description, scene, event, previous, world,
                         player_text)
    p = GENERATION_PARAMS["cine_field"]
    stops = ["\nFor a different story", "\nFor this story", "\n\n\n"]
    text = ""
    for attempt in range(2):
        raw = ollama_chat(msgs, f"Cinematographer[{field}:{name}]",
                          MAX_TOKENS["cine_field"], "cine_field", stop=stops,
                          temperature=p["temperature"] + 0.2 * attempt)
        text = _cine_text(raw, field, name)
        if text:
            break
        print(f"  \u26a0 Cine field [{field}:{name}] empty - redraw", flush=True)
    if not text and field == "wearing":
        text = (previous or "").strip()
    print(f"  \u2192 {field} [{name}]: {text[:100]}", flush=True)
    return text

# =============================================================================
#  v12.4 — THE COMPOSER  (background music for each scene)
#
#  The user's design (2026-10-17): instrumental background music made from
#  the scene's intro and story by ACE-Step 1.5 in ComfyUI, its genre and its
#  mood taken from the story - orchestral or synth as the world suggests.
#  This role asks the model only what it answers well; story_lab_music12
#  writes the music itself (palettes, tempo, key, the prose caption):
#    SOUNDTRACK   once per game: which kind of soundtrack suits the world,
#                 ONE WORD FROM A CLOSED LIST (MUSIC_SOUNDTRACKS). music12
#                 holds a hand-written palette for each.
#    MOOD         every round: what the music should make the listener feel
#                 now, from the opener and the player's event (nearest the
#                 cue: Law 2), as a few words.
#
#  NEGATIVE RESULTS - two probes before this design (loop_reports/
#  v12_4_music/probe_composer_v1.log and probe_composer.log, 8 real scenes
#  in 4 genres x 2 draws). The model was asked to write the music itself:
#    - genre + instruments ("Score:", then "Genre:" / "Instruments:" as two
#      cues): a track title ("Hogwarts School Year Opening", "Hogwarts
#      School Theme" - 4 of 4 Hogwarts draws), sound-effect prose ("The hum
#      of life support systems vibrates through"), the assistant register
#      ("Based on your description, here are some instrument choices",
#      "The choice is yours! What genre captures Vess's situation?") - 9 of
#      12 world draws unusable;
#    - an arrangement sentence: the scene narrated again ("The industrial
#      ambiance breathes around Vess"), a copyrighted theme ("The 'Hedwig's
#      Theme' melody slowly unfolds on solo flute"), onomatopoeia ("HUMMMM...
#      TICK-TOCK") - about 11 of 32 usable;
#    - the MOOD tags: 27 of 32 usable as they came ("bittersweet, tender,
#      transformative"; "Tense, calculating, trapped"); the misses were a
#      scene header on the first line ("Interview Room 2 - Scene Setup") -
#      skipped by _music_text and refused by music_note_ok.
#  So the model names feelings; the music is authored.
# =============================================================================

MUSIC_FIELDS = ("soundtrack", "mood")

# The closed list. story_lab_music12.PALETTES has one palette per entry
# (test_engine12 checks the two stay in step).
MUSIC_SOUNDTRACKS = ("fantasy", "science fiction", "horror", "crime noir",
                     "historical", "modern", "romance", "adventure", "western",
                     "cyberpunk", "post-apocalyptic", "comedy", "mythic")

MUSIC_EXAMPLES = (
    {"world": "a paddle-steamer casino on the Mississippi in 1925: card tables, "
              "brass lamps, a band playing on the deck",
     "soundtrack": "historical",
     "mood": "playful, sly, a little reckless"},
    {"world": "a neon megacity in endless rain: towering advertising screens, "
              "hover traffic, noodle bars under the flyovers",
     "soundtrack": "cyberpunk",
     "mood": "lonely, watchful, quietly tense"},
)
_MUSIC_CUE = {"soundtrack": "Soundtrack:", "mood": "Mood:"}
_MUSIC_FRAME = {
    "soundtrack": ("A composer sorts stories by the soundtrack that suits their "
                   "world: " + ", ".join(MUSIC_SOUNDTRACKS) + "."),
    "mood": ("A composer is spotting a scene for its background music. The mood "
             "note says what the music should make the listener feel at this "
             "moment, in a few words separated by commas."),
}
_MUSIC_WORDS_MAX = {"soundtrack": 3, "mood": 8}
# The mood gets a third draw: probe v3 had one scene (the noir interview
# room, a header-first opener) fail two draws running ("Interview Room 2").
_MUSIC_DRAWS = {"soundtrack": 2, "mood": 3}


def music_messages(field: str, world: str = "", setting: str = "", scene: str = "",
                   event: str = "") -> list:
    """The [system, user] pair for one composer call. Pure - unit-testable."""
    blocks = []
    if field == "soundtrack":
        if (world or "").strip():
            blocks.append("The world:\n" + world.strip())
        if (setting or "").strip():
            blocks.append("The place:\n" + setting.strip())
    else:
        if (scene or "").strip():
            blocks.append("The scene:\n" + scene.strip())
        if (event or "").strip():                    # nearest the cue: Law 2
            blocks.append("What just happened:\n" + " ".join(event.split()))
    cue = _MUSIC_CUE[field]
    if field == "soundtrack":
        demos = [f"For a story set in {ex['world']}:\n{cue} {ex['soundtrack']}"
                 for ex in MUSIC_EXAMPLES]
    else:
        demos = [f"{cue} {ex['mood']}" for ex in MUSIC_EXAMPLES]
    blocks.append(f"{_MUSIC_FRAME[field]}\n\nFor other stories, the composer wrote:\n\n"
                  + "\n\n".join(demos) + f"\n\nFor this story:\n{cue}")
    return build_messages("You write a composer's notes for background music.", *blocks)


_MUSIC_STOP_HEADS = ("for this story", "for other stories", "for a story",
                     "the world:", "the place:", "the scene:")
_MUSIC_SUB_LABEL = re.compile(r"^(?:mood|feelings?|emotions?|soundtrack|genre)"
                              r"\s*:\s*", re.IGNORECASE)


def _music_header(line: str) -> bool:
    """A title line the RP dialect puts first ("Kerchoff Station - Central
    Corridor", "Interview Room 2 - Scene Setup"): a spaced dash, no comma."""
    return " - " in line and "," not in line


def _music_title(line: str) -> bool:
    """A comma-less line shaped like a place or scene title rather than
    feelings: it has a digit ("Interview Room 2"), or is two or more words
    all capitalised ("Platform Nine And Three-Quarters")."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", line)
    return bool(re.search(r"\d", line)) or (
        len(words) >= 2 and all(w[0].isupper() for w in words))


def _music_text(raw: str, field: str) -> str:
    """
    One note from a raw completion, in the RP dialect: markdown, asterisks
    and bullets off, a repeated cue off, a title line skipped, stops at
    another field's cue or a demonstration header. One comma line,
    parentheses dropped; cut to _MUSIC_WORDS_MAX words (Law 1: a word count
    in the prompt is not obeyed).
    """
    own = _MUSIC_CUE[field].lower()
    others = tuple(c.lower() for k, c in _MUSIC_CUE.items() if k != field)
    out, looked = [], 0
    for line in (raw or "").splitlines():
        s = line.replace("**", "").replace("__", "").replace("*", "").strip()
        s = s.lstrip("-+•#> ").strip()
        if not s:
            if out:
                break
            continue
        low = s.lower()
        if low.startswith(others) or low.startswith(_MUSIC_STOP_HEADS):
            break
        if low.startswith(own):
            s = s[len(own):].strip()
        s = s.strip("`\"[]").strip()
        if not s or not re.search(r"[A-Za-z]", s) or _music_header(s):
            continue
        if s.endswith(":") and len(s.split()) <= 5:          # a header line
            continue
        if field == "soundtrack":
            # The entry itself, from the first of three lines that names one:
            # a title line first is common ("The salvage platform", then the
            # answer), and a long answer must not be cut before its entry
            # ("Genre/Subgenre: Hard sci-fi").
            choice = soundtrack_choice(s)
            if choice:
                return choice
            looked += 1
            if looked >= 3:
                break
            continue
        if not out and "," not in s and _music_title(s):
            continue                     # "Interview Room 2", then the tags
        out.append(s)
    joined = re.sub(r"\([^)]*\)", "", ", ".join(out))
    items = [_MUSIC_SUB_LABEL.sub("", t).strip().rstrip(".!") for t in scene_items(joined)]
    text = ", ".join(t for t in items if t)
    words = text.split()
    cap = _MUSIC_WORDS_MAX[field]
    if len(words) > cap:
        text = " ".join(words[:cap])
        if "," in text:
            text = text.rsplit(",", 1)[0]
    return text.strip().rstrip(",;")


# Spellings the model uses for a list entry (probe v3: "Genre/Subgenre:
# Hard sci-fi", "Sci-Fi / Survival", "Magical atmosphere").
_SOUNDTRACK_ALIASES = {
    "sci-fi": "science fiction", "scifi": "science fiction", "sf": "science fiction",
    "space": "science fiction", "magical": "fantasy", "magic": "fantasy",
    "wizarding": "fantasy", "fairy": "fantasy", "detective": "crime noir",
    "noir": "crime noir", "thriller": "crime noir", "victorian": "historical",
    "period": "historical", "gothic": "horror", "haunted": "horror",
    "apocalyptic": "post-apocalyptic", "dystopian": "cyberpunk", "epic": "mythic",
    "myth": "mythic", "romantic": "romance", "contemporary": "modern",
    "comedic": "comedy", "comic": "comedy",
}


def soundtrack_choice(text: str) -> str:
    """The MUSIC_SOUNDTRACKS entry an answer names ("" if none): the entry,
    its first or last word ("science" / "noir"), or an alias ("sci-fi");
    the earliest mention wins."""
    low = (text or "").lower()
    keys = {}
    for name in MUSIC_SOUNDTRACKS:
        for key in {name, name.split()[0], name.split()[-1]}:
            keys.setdefault(key, name)
    for alias, name in _SOUNDTRACK_ALIASES.items():
        keys.setdefault(alias, name)
    best, at = "", len(low) + 1
    for key, name in keys.items():
        m = re.search(r"(?<![a-z])" + re.escape(key) + r"(?![a-z])", low)
        if m and m.start() < at:
            best, at = name, m.start()
    return best


def music_note_ok(field: str, text: str) -> bool:
    """
    The shape a note must have to be used (a failed one gets the redraw):
    a soundtrack must name a list entry; a mood is a few short items, no
    digits, no all-caps words (probe: "CORRECTION NEEDED - PROMPT DOESN'T
    MATCH SPECIFICATIONS"), no title dash.
    """
    text = (text or "").strip()
    if field == "soundtrack":
        return bool(soundtrack_choice(text))
    if not text or re.search(r"\d", text) or " - " in text:
        return False
    if any(len(w) >= 4 and w.isupper() for w in re.findall(r"[A-Za-z]+", text)):
        return False
    return all(len(t.split()) <= 4 for t in scene_items(text))


def generate_music_field(field: str, world: str = "", setting: str = "",
                         scene: str = "", event: str = "") -> str:
    """
    v12.4: one composer note - a MUSIC_SOUNDTRACKS entry, or the mood tags.
    "" when every draw fails the shape check (the director has a fallback
    for each: the world's keywords, the palette's own mood). Budget
    _MUSIC_DRAWS[field], each draw 0.2 hotter.
    """
    msgs = music_messages(field, world, setting, scene, event)
    p = GENERATION_PARAMS["music_field"]
    stops = ["\nFor this story", "\nFor other stories", "\nFor a story", "\n\n\n"]
    text = ""
    for attempt in range(_MUSIC_DRAWS[field]):
        raw = ollama_chat(msgs, f"Composer[{field}]", MAX_TOKENS["music_field"],
                          "music_field", stop=stops,
                          temperature=p["temperature"] + 0.2 * attempt)
        text = _music_text(raw, field)
        if music_note_ok(field, text):
            if field == "soundtrack":
                text = soundtrack_choice(text)
            break
        print(f"  ⚠ Composer [{field}] unusable ({text[:60]!r}) - redraw", flush=True)
        text = ""
    print(f"  → music {field}: {text[:110]}", flush=True)
    return text

# =============================================================================
#  SECTION 7 — CONTEXT ASSEMBLY HELPERS
# =============================================================================

# =============================================================================
#  v10.1 — THE EVENT CONDITIONER
#
#  The player types into a box mid-round. Until v10.1 that raw string went
#  STRAIGHT into both channels: frame_injection() glued it to the resolution
#  for the opener, and generate_dialogue_turn() bracketed it as a stage beat.
#  Every other role in this engine has a validator and a re-roll budget; the
#  one input written by a human had neither.
#
#  WHY IT MATTERS (measured: iter 275/276 and the 2026-08-24 GUI playthrough).
#  Novel-vocabulary uptake — content words the event introduces that are not
#  already in the scene, counted in the NEXT round's dialogue:
#
#      epistemic event, raw ("they offer them office jobs")       3-6%
#      physical event, hand-written ("a desk lands between them")  14%
#      physical + pair-directed (Fayrun / Maren corpus)          28-35%
#
#  Two separate deficits sit in that gap. The first is SHAPE: events phrased
#  as something the characters LEARN or ARE OFFERED produce deliberation, not
#  action (the harness's own Scenario-Craft Law 2, earned in runs 15-20). The
#  second is ADDRESS: a partition wall dropping nearby can be watched, whereas
#  "commands you both to stand aside" cannot. The corpus events do both; a
#  player typing mid-scene reasonably does neither.
#
#  So the conditioner is a REWRITER, not an author. It is handed the world,
#  the last resolution, both characters' current wants and the raw text, and
#  returns the same event re-staged as something physical, close enough to
#  touch, aimed at the pair. Its risk is obvious — a rewriter can rewrite the
#  player out of their own idea — so the validator's central check is CONTENT
#  PRESERVATION: at least one of the player's own content-word stems must
#  survive. That is the mechanical guarantee standing in for "please keep what
#  they asked for", an instruction this model size does not reliably obey.
#  Arm B's invented "Helix-VII lightning storm", one line after a badge landed,
#  is exactly the failure this check exists to catch.
#
#  THIRD PARTIES. Scenario-Craft Law 4 forbids an injection whose payload IS a
#  new character, because the turn loop is strictly two-role and such a figure
#  "has nowhere to be voiced". The conditioner resolves that: a third party may
#  act AND speak, but only INSIDE the bracket beat, which is input-only and
#  never enters dialogue_history. It has somewhere to be voiced now, so the two
#  characters can answer it without the loop ever needing a third slot.
# =============================================================================

_EVENT_MIN_WORDS = 6      # shorter than this is not a staged beat
_EVENT_MAX_WORDS = 60     # longer and it starts writing the scene for them
_EVENT_ECHO_RUN  = 12     # shared run with a context block == copied, not staged

_EVENT_PAIR_TOKENS = ("both", "them", "their", "they", "between", "each")

# Which defects a beat may still SHIP with when the budget is exhausted.
# "not pair-directed" and "too long" are shape flaws: the event is still the
# player's event, just staged less sharply than we wanted, and a staged beat
# beats raw epistemic text. The rest are disqualifying, and one especially:
# "player content lost" is the check that protects the player from the
# rewriter, so banking a beat that failed it would defeat the entire point of
# having the check. Those fall back to the raw text instead (OBS-022: thin and
# honest beats poisoned).
_EVENT_SOFT_DEFECTS = frozenset({"not pair-directed", "too long",
                                 "too descriptive", "second person"})

# v10.7 SECOND PERSON. The narration of a staged beat must be third person.
# v10.6 stagings addressed the reader — "reverberates through your bones",
# "the corridor you're standing in", "rifles all trained directly at you and
# Kael" — and a "you" in the beat is a register break the dialogue then has to
# absorb. SOFT: a second-person beat still carries the player's event. Quoted
# speech is exempt, because a third party speaking TO the pair ("You two —
# identify yourselves") is exactly what v10.4's address instruction asks for.
_EVENT_QUOTED = re.compile(r'"[^"]*"|“[^”]*”|"[^"]*$|“[^”]*$')
_EVENT_SECOND_PERSON = re.compile(r"\b(?:you|your|yours|yourself|yourselves)\b", re.I)
# v10.8: OFF, as in v10.1 — a v10.7 design addition, not a bug fix. Kept for
# re-testing; v10.7 had 0 second-person stagings in 6, v10.6 had 3 in 18.
EVENT_SECOND_PERSON_CHECK = False
# v10.8: bank the FIRST soft-defect staging, as v10.1 did. v10.4's "shortest"
# bank was part of the shorten-the-denominator strategy that did not pay.
EVENT_BANK_SHORTEST = False

# v10.4 DESCRIPTOR BUDGET. Measured on iter 286, word by word: the beat words
# characters went on to REUSE were nouns (feet, footfalls, servos, corporate,
# data, barrier); the words NOBODY reused were descriptors (rhythmic, regular,
# soft, whirring, crisp, blue, white, somehow, adjacent, intervals). Uptake is
# reused novel words over novel words, so every descriptor is pure denominator
# — scenery the characters can see past. A prompt asking for "25 words or
# fewer" produced 35-49, so the budget is enforced here, mechanically, not
# requested. Colour, sound, light and -ly manner words: a small closed class,
# cheap to count without a tagger, and exactly the class the specimens showed.
_EVENT_DESCRIPTORS = frozenset("""
    red blue green white black grey gray amber crimson golden silver scarlet
    bright dim dark pale glowing glow glows flicker flickers flickering flash
    flashes flashing gleam gleaming shimmer shimmering light lights lit shadow
    shadows hum hums humming whir whirs whirring whine whining buzz buzzing
    clank clanks clanking clatter crackle crackles crackling hiss hissing
    echo echoes echoing rhythmic soft loud faint sharp crisp sleek heavy
    metallic mechanical ominous eerie strange sudden suddenly slowly quietly
    """.split())
_EVENT_MAX_DESCRIPTORS = 3
# v10.6: OFF. The budget existed to raise uptake by shrinking its denominator,
# and uptake's fraction never moves (20-23% across v10.1-v10.5). It burned
# about two re-rolls per run, and on exhaustion the shortest-soft bank shipped
# the SHORTEST candidate — working against the length v10.5 restored, and
# length is what carried engagement (4.3 -> 6.3 reused words per event). Kept,
# not deleted, so it can be re-tested; set True to re-enable.
EVENT_DESCRIPTOR_BUDGET = False

# NEGATIVE RESULT (v10.4, measured 2026-09-24) — recorded here so the idea is
# not re-proposed. Shortening the staged beat (v10.3: prompt asks "25 words or
# fewer" and the "event" token cap drops 120 -> 70; v10.4: "under twenty
# words" plus the descriptor budget) was meant to raise uptake by shrinking its
# denominator. It did not.
#   CORRECTION: _EVENT_MAX_WORDS was reported as lowered 60 -> 30 in v10.3. It
# never was — the edit script died on a later anchor before writing, and the
# loss went unnoticed. It stayed 60 throughout. The effective length limit in
# v10.3/10.4 was the 70-TOKEN CAP (~50 words): staged beats ran 18-43 words and
# "too long" fired zero times, which a 30-word cap could not have produced.
# Pooled across two runs per arm, reused-words / novel-words held at 20-22% in
# EVERY arm from v10.1 to v10.4 while the beat's novel-word count swung from
# 33.3 to 16.7. The fraction is invariant; the ABSOLUTE reuse is what moved —
# and it moved the wrong way, 6.7 words per beat (v10.2, long) to 4.3 (v10.4,
# compact). A shorter beat simply carries less for the characters to pick up.
# Same signature as the allocation invariant: the model references its input
# at a stable rate, and prompting changes how much there is, not the rate.
#   What v10.4 DID buy is qualitative and does not show in the fraction: the
# third party now addresses a lead in every staging, and the leads answer it
# directly (iter 290: Kael steps between Vess and the drones, "Whoa whoa, easy
# there little guys... I'm gonna need y'all to stand down"). Keep the address;
# treat the shortening as unproven. v10.5 tests exactly that: every v10.4
# content change kept, only the LENGTH levers restored to v10.1-10.2 (token cap
# 120, "one or two sentences") — address plus the longer beats that carried more.

# v10.4 SCAFFOLD LEAK. The v10.3 prompt's placeholder "<ONE sentence, 25 words
# or fewer, of what physically happens>" was completed LITERALLY — iter 286's
# round-2 staging opened "One sentence describing what physically happens:".
# A D-01 defect introduced by a prompt edit, and it also put four dead words
# (describing, happens, physically, sentence) into the uptake denominator.
_EVENT_LEAK_PREFIX = re.compile(
    r"^\s*(?:here(?:'s| is)[^:]{0,40}:|(?:one|a)\s+(?:short\s+)?sentence[^:]{0,60}:)\s*",
    re.I)
_EVENT_LEAK = re.compile(
    r"\b(?:one|short)\s+sentence\b|\bdescribing what\b|\bwords or fewer\b"
    r"|\bphysically happens\b", re.I)


def _event_descriptors(text: str) -> int:
    """Count colour / sound / light / manner words — the class nobody reuses."""
    words = re.findall(r"[a-z']+", text.lower())
    return sum(1 for w in words
               if w in _EVENT_DESCRIPTORS or (w.endswith("ly") and len(w) > 4))


def _event_words(text: str) -> set:
    """Content words — lowercase, 4+ letters, stopwords removed."""
    return {w for w in re.findall(r"[A-Za-z']+", text.lower())
            if len(w) > 3 and w not in _ECHO_STOPWORDS}


def _event_stems(text: str) -> set:
    """Prefix-5 stems of the content words (offices ~ office)."""
    return {w[:5] for w in _event_words(text)}


_EVENT_PARTIAL_MIN = 5    # v10.6: shortest word allowed a PARTIAL (substring) match


def _event_content_kept(raw: str, happens: str, exclude: tuple = ()) -> bool:
    """
    Did any of the player's own content survive the re-staging?

    v10.6 — STRICT AGAIN, with one narrow allowance. The history, because the
    check has now been wrong in both directions:
      v10.1  prefix-5 stems must match exactly. Strict — and the v10.1 runs
             lost 0 of 6 player events — but it rejected the conditioner's
             single most natural re-wording, "droids" -> "android".
      v10.2  relaxed to substring containment from 4 letters, so droid/android
             would pass. Too broad, and measurably so: iter 292 turned the
             economist-droid takeover into "something heavy impacts against a
             support beam... magnetic locks securing" and PASSED because the
             player's "ring" (from "ring world") sits inside "secu-RING"; iter
             293 passed on "need" inside "needed". Worse, more output words mean
             more accidental matches, so the guard weakened exactly as events
             got longer. Player intent survived in 2 of 6 v10.5 stagings.
      v10.6  exact prefix-5 stem match (v10.1's rule), OR a partial match where
             BOTH words are at least _EVENT_PARTIAL_MIN letters. "droid" in
             "android" passes; "ring" and "need" are four letters and cannot.
    And the character names are excluded: a player event that mentions "Vess
    and Kael" would otherwise be "preserved" by ANY staging that names either
    of them — the names are always in the scene and prove nothing.
    What this still cannot catch is a hollow match on a real word (iter 293:
    "VERSUS VOICE RECOGNITION CONFIRMED" keeps "confirm" and loses the
    employment ultimatum). A word-level guard cannot judge meaning; it can only
    stop wholesale replacement, which is the failure it exists for.
    """
    def _singular(w: str) -> str:
        if w.endswith("ies") and len(w) > 4:
            return w[:-3] + "y"
        if w.endswith("es") and len(w) > 4:
            return w[:-2]
        if w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
        return w

    # v10.7: exclusion works at the same STEM granularity as the check itself.
    # Whole-word exclusion would let "station's" or "stations" (and "Kael's")
    # slip past it and then match "station" in the staging — the exact hollow
    # pass the exclusion exists to stop. Possessives are normalised first.
    def _norm(w: str) -> str:
        return re.sub(r"'s$|'$", "", w)
    excl = {_norm(x.lower())[:5] for x in exclude if x}
    raw_w = {w for w in map(_norm, _event_words(raw)) if w[:5] not in excl}
    out_w = {w for w in map(_norm, _event_words(happens)) if w[:5] not in excl}
    if not raw_w:
        return True                       # nothing to preserve
    # 1. v10.1's strict rule: an exact prefix-5 stem survived (office/offices,
    #    confirm/confirmed, station/stations).
    if {w[:5] for w in raw_w} & {w[:5] for w in out_w}:
        return True
    # 2. The one allowance: a PARTIAL match, singularised (the plural is what
    #    defeats containment — "droids" is not inside "android", "droid" is),
    #    and only when both words are long enough that a match means something.
    raw_s = {_singular(w) for w in raw_w}
    out_s = {_singular(w) for w in out_w}
    return any(min(len(r), len(o)) >= _EVENT_PARTIAL_MIN and (r in o or o in r)
               for r in raw_s for o in out_s)


def _event_defect(happens: str, raw: str, char_a, char_b,
                  echo_sources: list, scene_words: tuple = ()) -> str:
    """
    Validator for one conditioned event. Returns a defect name or "".

    INVARIANT (v10.4): every HARD check runs before any SOFT one, so a soft
    verdict GUARANTEES the staging carries no hard defect. The exhaustion
    fallback relies on exactly that — it may ship a soft-defect staging — and
    until v10.4 the order was cheapest-first, which broke it twice: "too long"
    returned before content preservation, and "too descriptive" before
    speaks-for-a-character, so a long staging that had DROPPED the player's
    idea was classified soft, banked, and could ship. The same class of bug the
    v10.1 offline gate caught, surviving in the branch order.

    Every check is mechanical: none asks whether the beat is GOOD, only whether
    it is structurally usable — a quality judgement from this model size is
    not worth the generation it would cost.
    """
    # ---------------- HARD: disqualifying, fall back to the raw text -------
    if not happens:
        return "empty"
    n = len(happens.split())
    if n < _EVENT_MIN_WORDS:
        return "too short"
    # SCAFFOLD LEAK — the prompt's own wording in the fiction is D-01, and it
    # inflates the uptake denominator with words no one will ever say.
    if _EVENT_LEAK.search(happens):
        return "scaffold leak"
    # CONTENT PRESERVATION — the player must still be inside their own event.
    # v10.7: words already in the SCENE are excluded along with the names. Both
    # events v10.6 lost passed on "station" alone — the setting's first word —
    # and a word the story is already full of proves nothing about whether the
    # player's idea survived. Tested on all six v10.6 stagings: rejects exactly
    # the two lost events and the one partial, keeps all three full-intent ones.
    if not _event_content_kept(raw, happens,
                               (char_a.name, char_b.name) + tuple(scene_words)):
        return "player content lost"
    # CONTEXT ECHO — a block was copied instead of transformed.
    for src in echo_sources:
        if src and _longest_shared_run(happens, src) >= _EVENT_ECHO_RUN:
            return "context echo"
    # SPOKEN-FOR — the beat must not put words in the pair's mouths; they
    # answer it themselves. A third party speaking here is allowed and is the
    # whole point, so the test is name-anchored, not quote-anchored.
    for c in (char_a, char_b):
        if re.search(rf"\b{re.escape(c.name)}\b\s*[:,]?\s*[\"“]", happens):
            return "speaks for a character"
    # ---------------- SOFT: shape flaws, may ship when budget is spent -----
    if n > _EVENT_MAX_WORDS:
        return "too long"
    # PAIR ADDRESS — the axis that separates 14% uptake from 30%.
    # Tokenised with a regex, NOT str.split(): a beat very often ENDS on the
    # pronoun ("...sets it down in front of them."), and split() leaves the
    # period attached, so "them." failed to match "them" — caught by the unit
    # tests; the live runs only showed it as a pile of unexplained fires.
    low = happens.lower()
    tokens = set(re.findall(r"[a-z']+", low))
    if not (char_a.name.lower() in low or char_b.name.lower() in low
            or tokens & set(_EVENT_PAIR_TOKENS)):
        return "not pair-directed"
    # DESCRIPTOR BUDGET — colour, sound, light, manner: the class no character
    # ever reuses, i.e. pure uptake denominator.
    if EVENT_DESCRIPTOR_BUDGET and _event_descriptors(happens) > _EVENT_MAX_DESCRIPTORS:
        return "too descriptive"
    # SECOND PERSON (v10.7) — the narration addresses the reader. Quoted speech
    # is removed first: a third party saying "you" to the pair is intended.
    if EVENT_SECOND_PERSON_CHECK and _EVENT_SECOND_PERSON.search(
            _EVENT_QUOTED.sub(" ", happens)):
        return "second person"
    return ""


def condition_event(injection: str, setting: str, char_a, char_b,
                    resolution: str = "", mem_a: str = "",
                    mem_b: str = "") -> tuple:
    """
    Event Conditioner AI: re-stage the player's raw text as a physical beat.

    Returns (happens, pressure). `happens` is the bracket beat for the
    dialogue channel and the seed for the world channel; `pressure` is one
    clause naming what the pair can no longer avoid, carried near the
    completion cue for the first EVENT_PIN_TURNS turns of the round.

    FALLBACK IS THE RAW TEXT. A guard that can swallow the player's event is
    worse than no guard: on exhaustion this returns what they typed, which is
    exactly v10.0 behaviour. The conditioner can improve or no-op, never eat.

    Attention geography: the player's line is the LAST block before the cue,
    and the cue is the literal label "HAPPENS:" so the call is a COMPLETION
    rather than an instruction to obey. The world, the last beat and the two
    wants sit above it as context the rewrite may draw on.
    """
    if not injection.strip():
        return "", ""
    # v10.4 PROMPT. Three changes, each from a measured specimen:
    #   (1) The two-line "HAPPENS: <...> / PRESSURE: <...>" format spec is GONE.
    #       PRESSURE has its own call since v10.1a, so the spec only taught a
    #       shape the model never produced — and its angle-bracket placeholder
    #       was completed literally (iter 286: "One sentence describing what
    #       physically happens:"). The completion cue "HAPPENS:" at the end of
    #       the user message carries the format on its own.
    #   (2) PLAIN NOUNS AND VERBS, phrased positively. The reused words were
    #       nouns; the ignored ones were colour, sound and light. Naming the
    #       banned classes ("no colours, no sounds") risks priming them at this
    #       model size, so the prompt asks for the class it wants and the
    #       descriptor budget in _event_defect() polices the rest.
    #   (3) A THIRD PARTY ADDRESSES A LEAD BY NAME. The corpus's strongest
    #       events all speak to the pair and wait ("commands you both to stand
    #       aside"). An RP model answers in the terms of what it was asked, so
    #       a direct order or question hands the characters the words to reply
    #       with — the model's echo habit, pointed somewhere useful.
    # v10.6 GROUNDING RESTORED. v10.1's prompt said "in the room they are
    # standing in", "Use the objects and places already in the scene" and
    # "Present tense". The v10.4 rewrite dropped all three without any test of
    # the loss, and the runs show the cost: v10.4/v10.5 stagings invented a
    # hangar, "Vess's workspace", tunnels, "Level 7" and a customs officer, and
    # that officer grew into a "Federation security" subplot that displaced the
    # player's droids from the characters' memories (4-5 of 12 memories kept
    # the event, against 12 of 12 in v10.1). Read over all six turns, v10.1's
    # reactions BUILT (4/6 -> 6/6, zero ignores) while v10.4's FADED (to 2/6,
    # six ignores). An event that stays in the room keeps forcing a reaction;
    # one that pulls the scene somewhere new competes with the player's.
    # v10.8: v10.1's PROMPT, VERBATIM — copied from v10.1's run snapshot
    # (loop_saves/Loop279), not retyped. v10.1 scored 13 and 15 reacting lines
    # /18 against 9.5 for v10.6/v10.7, and its wording asks for the thing being
    # measured: "one of them has to do something about it" — a demand for a
    # REACTION, where v10.4 onward asked for physical contact ("lands ON one of
    # them") and prescribed the third party's line. v10.8 tests whether that
    # wording was doing real work, on v10.7's repaired guard. The v10.4-v10.7
    # rationale comments above describe the prompt this one replaces.
    # The trailing format spec is v10.1's too; its placeholder is now covered
    # by the scaffold-leak guard ("physically happens" is a hard defect).
    system = (
        f"You are the stage manager for a scene between {char_a.name} and "
        f"{char_b.name}. The player has typed a rough event. Re-stage it as "
        f"something that PHYSICALLY HAPPENS in the room they are standing in, "
        f"right now.\n"
        f"Keep what the player asked for, however strange - make it real, never "
        f"swap it for something else. Use the objects and places already in the "
        f"scene. Present tense. It happens close enough to {char_a.name} and "
        f"{char_b.name} to touch, and one of them has to do something about it. "
        f"Anyone ELSE may act and speak inside the event; {char_a.name} and "
        f"{char_b.name} never speak here - they answer it themselves afterwards.\n"
        f"Reply in exactly two labelled lines:\n"
        f"HAPPENS: <one or two sentences of what physically happens>\n"
        f"PRESSURE: <one clause naming what they can no longer avoid>"
    )
    print("\n  -- Event Conditioner --", flush=True)
    stops = ["\nThe world:", "\nWhat just happened:", "\nThe player types:",
             "\nWhat they each want:"]
    wants = "\n".join(f"{c.name}: {m}" for c, m in
                      ((char_a, mem_a), (char_b, mem_b)) if m)

    def _assemble():
        blocks = [f"The world:\n{setting}"]
        if resolution:
            blocks.append(f"What just happened:\n{resolution}")
        if wants:
            blocks.append(f"What they each want:\n{wants}")
        blocks.append(f"The player types:\n{injection}")
        blocks.append("HAPPENS:")                  # completion cue, last
        return build_messages(system, *blocks)

    echo_sources = [setting, resolution, mem_a, mem_b]
    scene_words = tuple(_event_words(setting))       # v10.7: prove nothing
    happens = pressure = ""
    any_keep = ("", "")
    # v10.7: the budget and the temperature both depend on WHY the last draw
    # failed. A shape defect climbs the heat ladder as before; a fidelity
    # defect extends the budget to EVENT_ATTEMPTS_FIDELITY and redraws at the
    # base temperature (see the constant for why heat is the wrong cure).
    budget = EVENT_ATTEMPTS
    attempt = 0
    heat = 0                                          # shape re-rolls so far
    last_defect = ""
    while attempt < budget:
        attempt += 1
        if attempt == 1 or last_defect in _EVENT_FIDELITY_DEFECTS:
            temp = None                               # the role's base temperature
        else:
            heat += 1
            temp = 0.8 if heat == 1 else 1.0
        raw = ollama_chat(_assemble(), "EventCond", MAX_TOKENS["event"],
                          "event", stop=stops, temperature=temp)
        cleaned = _strip_block_labels(_strip_markdown(raw)).strip()
        # The cue already wrote "HAPPENS:", so the model completes it; one that
        # re-types the label anyway is tolerated rather than punished.
        cleaned = re.sub(r"^\s*HAPPENS\s*:\s*", "", cleaned, flags=re.I)
        cleaned = _EVENT_LEAK_PREFIX.sub("", cleaned)  # v10.4: strip a leaked
                                                       # "One sentence ...:" lead
        parts = re.split(r"\n?\s*PRESSURE\s*:\s*", cleaned, maxsplit=1,
                         flags=re.I)
        h = " ".join(parts[0].split())
        p = " ".join(parts[1].split()) if len(parts) > 1 else ""
        h = _trim_to_sentence(h) or h
        defect = _event_defect(h, injection, char_a, char_b, echo_sources,
                               scene_words)
        if not defect:
            happens, pressure = h, p
            break
        last_defect = defect
        if defect in _EVENT_FIDELITY_DEFECTS:
            budget = max(budget, EVENT_ATTEMPTS_FIDELITY)
        # v10.4: bank the SHORTEST soft-defect staging, not the first. Length
        # is the uptake denominator, so among flawed-but-usable stagings the
        # tightest one is the better one to ship.
        if h and defect in _EVENT_SOFT_DEFECTS and (
                not any_keep[0] or (EVENT_BANK_SHORTEST and
                                    len(h.split()) < len(any_keep[0].split()))):
            any_keep = (h, p)
        print("  ⚠ Event defect [%s] %s" %
              (defect, "- exhausted." if attempt >= budget
               else "- re-roll %d/%d." % (attempt + 1, budget)),
              flush=True)
    else:
        # Exhausted: a flawed staged beat still beats raw epistemic text, but
        # an EMPTY one does not — fall back to what the player typed (OBS-022:
        # thin and honest beats poisoned).
        if any_keep[0]:
            happens, pressure = any_keep
            print("  → exhausted: shipping the best soft-defect staging.",
                  flush=True)
        else:
            happens, pressure = " ".join(injection.split()), ""
            print("  → exhausted: falling back to the player's own words.",
                  flush=True)
    print(f"  → HAPPENS: {happens[:110]}", flush=True)
    # v10.1a: PRESSURE needs its own call. Measured on iter 279/280: across six
    # conditioner calls the label was emitted ZERO times — the model completes
    # the "HAPPENS:" cue and spends the whole 120-token budget on prose before
    # it ever reaches the second field (5 of those 6 calls also tripped "too
    # long"). A two-field completion from one cue is not a shape this model
    # size delivers; it obeys ONE cue at a time. So the field that did not
    # arrive is asked for separately, with the staged beat as its context and
    # its own label as the cue. Cheap (30 tokens) and it cannot fail closed:
    # an empty pressure simply means no line is pinned, which is v10.0.
    # v10.4: only when something will READ it. With EVENT_PIN_TURNS = 0 the
    # clause was generated, written to disk and never shown to any character —
    # one dead generation per event.
    if happens and not pressure and EVENT_PIN_TURNS > 0:
        p_raw = ollama_chat(
            build_messages(
                f"You are the stage manager. In ONE short clause, name the thing "
                f"{char_a.name} and {char_b.name} can no longer avoid now that "
                f"this has happened. No full sentence, no advice, no dialogue.",
                f"What just happened:\n{happens}",
                "PRESSURE:"),
            "EventPressure", 30, "event", stop=["\nWhat just happened:"])
        cand = " ".join(_strip_block_labels(_strip_markdown(p_raw)).split())
        cand = re.sub(r"^\s*PRESSURE\s*:\s*", "", cand, flags=re.I)
        # Same disqualifiers as the beat: it must not speak for either of them,
        # and it must not simply restate the beat back at the model.
        if (cand and len(cand.split()) <= 25
                and _longest_shared_run(cand, happens) < _EVENT_ECHO_RUN
                and not any(re.search(rf"\b{re.escape(c.name)}\b\s*[:,]?\s*[\"“]",
                                      cand) for c in (char_a, char_b))):
            pressure = cand
    if pressure:
        print(f"  → PRESSURE: {pressure[:110]}", flush=True)
    return happens, pressure


def frame_injection(injection: str, resolution: str) -> str:
    """
    Wrap the player's story injection and prepend it to the resolution.
    The result is the WORLD channel's context_seed for the next opener.
    If the resolver returned "" (double context-echo, v5.1), the seed is
    the framed event alone — thin, but honest (OBS-022).
    """
    framed = f"[STORY EVENT: {injection}]"
    return f"{framed}\n\n{resolution}" if resolution else framed


# A sentence already ends when the text closes on . ! ? or an ellipsis,
# optionally followed by closing quotes or brackets:  'Run!'  '"Stop."'  '(sic.)'
_EVENT_TERMINAL = re.compile(r"[.!?\u2026][\"'\u201d\u2019)\]]*$")
_EVENT_DANGLING = re.compile(r"[\s,;:\u2013\u2014-]+$")


def _end_sentence(text: str) -> str:
    """Close `text` with a full stop unless it already ends a sentence."""
    if _EVENT_TERMINAL.search(text):
        return text
    return _EVENT_DANGLING.sub("", text) + "."


def compose_event(injection: str, staged: str) -> str:
    """
    v11.1: the ONE event string every channel receives for a player event -
    the next opener's seed (via frame_injection), the characters' stage beat
    and the memory keeper's "What broke into the scene:" block.

        compose_event("They offer Vess and Kael office jobs",
                      "An android slides a contract across the crate.")
        -> "They offer Vess and Kael office jobs. An android slides ..."

    The player's text comes first, EVENT_INPUT_COPIES times, each copy closed
    as a sentence; the staging follows once. When the conditioner gave up its
    fallback IS the player's text (whitespace-collapsed), and that text is
    sent on its own rather than twice. Whitespace is collapsed throughout -
    the dialogue channel carries the event as a single bracketed line.
    """
    raw = " ".join((injection or "").split())
    beat = " ".join((staged or "").split())
    if not EVENT_PREPEND_INPUT or not raw:
        return beat
    parts = [raw] * max(1, EVENT_INPUT_COPIES)
    if beat and beat != raw:                  # a real staging, not the fallback
        parts.append(beat)
    return " ".join([_end_sentence(p) for p in parts[:-1]] + [parts[-1]])


def _build_dialogue_system(speaker: StoryCharacter,
                           include_sample: bool = True) -> str:
    """
    Identity system prompt for a speaker.

    Anchor order = the length-control ranking: the voice SAMPLE leads
    (few-shot prime, strongest), style second, then personality and the
    static core drive. Short and declarative to match the transcript
    register (Option E) — a prose-heavy system fighting a transcript
    context is a register conflict the model resolves by drifting.

    v5.8 (OBS-029/034, USER-DIRECTED CREATIVE — voice re-architecture).
    The prompt is NO LONGER byte-identical every round. Through v5.7 the
    full quoted voice_sample was re-injected EVERY turn to hold the voice;
    that constant re-priming was the root cause of two defects: the
    catchphrase parrot (iter 012: Kael shipped his sample's "Well now,
    ain't you just..." even after a re-roll) and the keeper person-drift.
    Now the QUOTED sample anchors ROUND 1 ONLY (include_sample=True — first
    establishment, the strongest few-shot prime). From round 2 the caller
    passes include_sample=False: the voice is carried by the style
    DESCRIPTION (kept below, non-quotable so nothing to parrot) plus the
    character's own accumulating memory. Hypothesis: kills the parrot and
    the drift at the source without collapsing the voice. If voice DOES
    collapse in round 2+, that is the finding — roll back to Loop-prior.
    """
    # v7.2 FIX 2: the identity leads — full name, pronouns and nature, authored
    # not extracted. Previously this line was "You are Harriet." and nothing
    # else in scope carried a surname, pronouns or species, so the model
    # supplied its own (OBS-041/044/053). Identity is stable state, so it takes
    # the primacy position (P4).
    parts = [f"You are {_identity_line(speaker)}."]
    if include_sample and speaker.voice_sample != "unspecified":
        parts.append(f'You sound like this: "{speaker.voice_sample}"')   # round-1 few-shot prime
    if speaker.speaking_style != "unspecified":
        parts.append(f"You speak like this: {speaker.speaking_style}.")  # style: the round-2+ voice cue
    if speaker.personality_summary != "unspecified":
        parts.append(speaker.personality_summary)                        # who you are
    if speaker.motivation != "unspecified":
        parts.append(f"You want: {speaker.motivation}.")                 # static core drive
    parts.append("React to what was just said and what just happened, "
                 "then push toward what you want.")
    # ^ the friction clause, reworked in v5.1 (OBS-018). The v5.0 wording
    #   ("Every line you speak pushes toward what you want.") made restating
    #   the want the maximally compliant completion — five rounds of "I'm
    #   just here for my money." Reaction now comes FIRST, and "what just
    #   happened" has a concrete referent: the bracket beat sitting next to
    #   the cue. Still character truth, not a rule.
    parts.append("One reply. Add brief *actions* in asterisks when they "
                 "matter, and speak.")
    # ^ v5.4 (OBS-028): the cue now NAMES the dialect instead of fighting
    #   it — "Write only dialogue" produced action-narration anyway, just
    #   unmarked. Speech stays primary; the action-only defect guard in
    #   _reply_defect() enforces that mechanically, not this sentence.
    # ^ v8.2: SAME WORDS, ORDER SWAPPED — the only change in this version.
    #   v8.1 measured 30.9% speech / 2.2:1 action over 20 runs (iters
    #   085-104), with 79-98% of lines OPENING on an action beat costing
    #   25-30 words before anyone speaks. The cue previously ENDED on
    #   "add brief *actions*", putting the action instruction at recency,
    #   nearest the generation point. This is v7.2's Fix-2 move applied to
    #   the dialogue cue: same information, different position ("the
    #   information was never missing, it was outvoted by position").
    #   The dialect is still NAMED, so v5.4's finding is preserved, and the
    #   format cue still sits last, so markup discipline should hold.
    #   ROLL-BACK TRIGGER: asterisk balance degrading, or narration turning
    #   UNMARKED (the v5.4 failure mode, strictly worse than marked action).
    return " ".join(parts)

# =============================================================================
#  SECTION 8 — FILE I/O
#  The run directory IS the research product: per-round openers, dialogue,
#  resolutions, both character memories, every spoken WAV, lane timings,
#  and a tunables snapshot with the engine version for provenance.
# =============================================================================

def make_run_dir(setting_desc: str) -> str:
    """Create runSaves/<slug>_<timestamp>/ and return its path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", setting_desc[:30].lower()).strip("_") or "story"
    run_dir = os.path.join(RUNS_DIR, f"{slug}_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    print(f"  \u2713 Run dir: {run_dir}", flush=True)
    return run_dir


def write_run_file(run_dir: str, filename: str, content: str) -> None:
    """Write UTF-8 file to run_dir. UTF-8 is mandatory — dolphin emits em-dashes."""
    with open(os.path.join(run_dir, filename), "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  \u2713 {filename}", flush=True)


def append_log(run_dir: str, text: str) -> None:
    """Append to log.txt. The log IS the research artifact — read it after a run."""
    with open(os.path.join(run_dir, "log.txt"), "a", encoding="utf-8") as f:
        f.write(text)


def save_characters_json(run_dir: str, char_a: StoryCharacter,
                         char_b: StoryCharacter) -> None:
    """
    Save both characters + the active tunables to characters.json.
    Every run records the exact settings AND ENGINE VERSION that produced
    it — provenance for the research log.
    """
    data = {
        "char_a":   dataclasses.asdict(char_a),
        "char_b":   dataclasses.asdict(char_b),
        "tunables": {
            "engine_version":    ENGINE_VERSION,
            "event_prepend_input": EVENT_PREPEND_INPUT,   # v11.1
            "event_input_copies":  EVENT_INPUT_COPIES,    # v11.1
            "dialogue_self_cue":   DIALOGUE_SELF_CUE,     # v11.6
            "takeover_guard":      TAKEOVER_GUARD,        # v11.6
            "dialogue_self_from_turn": DIALOGUE_SELF_FROM_TURN,  # v11.6
            "max_tokens":        MAX_TOKENS,
            "generation_params": GENERATION_PARAMS,
            "num_ctx":           NUM_CTX,
            "num_gpu":           NUM_GPU,
            "repeat_penalty":    REPEAT_PENALTY,
            "repeat_last_n":     REPEAT_LAST_N,
            "history_window":    HISTORY_WINDOW,
            "dialogue_retry":    DIALOGUE_RETRY,
            "model":             MODEL,
        },
    }
    with open(os.path.join(run_dir, "characters.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("  \u2713 characters.json", flush=True)
