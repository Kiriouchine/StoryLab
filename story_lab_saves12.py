"""
story_lab_saves12.py  —  Story Lab v12  //  save games

Designed with the user 2026-10-16 (loop_reports/v12_2_saves/design.md):
  1. a game is saved BETWEEN ROUNDS only - at the event gate, after both
     memories are written, the one moment the story is consistent;
  2. loading reads nothing aloud - the game just continues;
  3. a save POINTS AT the game's run folder, which already holds the text,
     the pictures and the audio; nothing is copied;
  4. the game seed is part of every checkpoint (visible, typeable).

WHY A SAVE CAN BE EXACT. Every engine call is stateless: what the model
"knows" next round is the extracted characters, the setting, both memories,
the last resolution and the round number - all of it in the checkpoint. The
seed stream's position (engine12.game_seed_state) is in it too, so a resumed
game continues the same random stream. Re-extracting would be wrong: the same
description extracts to a different character each game (Harry "with lion
emblem" one night, "messy brown hair" the next).

FILES
  <run_dir>/checkpoints/round_NN.json   the state after round NN (autosave,
                                        written by the director at every gate)
  saves/<name>.json                     a named save: a POINTER - run folder +
                                        round + what to show in the list
  <run_dir>/branch_<stamp>/             rounds that were played after a save
                                        and then abandoned by loading it -
                                        moved, never deleted

Pure functions; story_lab_director12 builds and restores the snapshot,
story_lab_gui12 offers the buttons.
"""

import os
import re
import json
import shutil
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAVES_DIR = os.path.join(_SCRIPT_DIR, "saves")
RUNS_DIR = os.path.join(_SCRIPT_DIR, "runSaves")
CHECKPOINT_SUBDIR = "checkpoints"
FORMAT = 1

_ROUND_FILE = re.compile(r"^round_(\d{2})_")
_SCENE_FILE = re.compile(r"^main_image_opening_(\d{2})")
_PORTRAIT_FILE = re.compile(r"^portrait_char[12]_interact(\d+)\.png$")
_AUDIO_FILE = re.compile(r"^r(\d{2})_")
_CKPT_FILE = re.compile(r"^round_(\d{2})\.json$")

# =============================================================================
#  CHECKPOINTS  (inside the run folder)
# =============================================================================

def _atomic_write_json(path: str, data) -> None:
    """Write via a temp file and os.replace: a crash never leaves half a save."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def checkpoint_path(run_dir: str, round_done: int) -> str:
    return os.path.join(run_dir, CHECKPOINT_SUBDIR, f"round_{int(round_done):02d}.json")


def write_checkpoint(run_dir: str, snapshot: dict) -> str:
    path = checkpoint_path(run_dir, snapshot["round_done"])
    _atomic_write_json(path, snapshot)
    return path


def checkpoints_in(run_dir: str) -> list:
    """Round numbers that have a checkpoint, ascending."""
    try:
        names = os.listdir(os.path.join(run_dir, CHECKPOINT_SUBDIR))
    except OSError:
        return []
    return sorted(int(m.group(1)) for n in names if (m := _CKPT_FILE.match(n)))


def read_checkpoint(run_dir: str, round_done: int = None):
    """The snapshot after `round_done` (the latest when None), or None."""
    rounds = checkpoints_in(run_dir)
    if not rounds:
        return None
    r = rounds[-1] if round_done is None else int(round_done)
    try:
        with open(checkpoint_path(run_dir, r), encoding="utf-8") as f:
            snap = json.load(f)
    except (OSError, ValueError):
        return None
    return snap if isinstance(snap, dict) and snap.get("format") == FORMAT else None


def recent_games(runs_dir: str = None, limit: int = 6) -> list:
    """The newest run folders that have a checkpoint (autosaves), newest first."""
    d = runs_dir or RUNS_DIR
    rows = []
    try:
        entries = [os.path.join(d, n) for n in os.listdir(d)]
    except OSError:
        return rows
    for run in entries:
        rounds = checkpoints_in(run)
        if not rounds:
            continue
        path = checkpoint_path(run, rounds[-1])
        rows.append({"run_dir": run, "round": rounds[-1], "mtime": os.path.getmtime(path)})
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    for r in rows[:limit]:
        snap = read_checkpoint(r["run_dir"], r["round"]) or {}
        r.update(story_title=snap.get("story", {}).get("title", ""),
                 seed=snap.get("game_seed"), saved_at=snap.get("saved_at", ""),
                 thumbnail=thumbnail_for(snap, r["run_dir"]))
    return rows[:limit]


def thumbnail_for(snapshot: dict, run_dir: str):
    """The last scene picture of a snapshot (its shown take), else a portrait."""
    for rnd in reversed(snapshot.get("rounds", [])):
        takes = (rnd.get("scene") or {}).get("takes") or []
        if takes:
            path = os.path.join(run_dir, takes[-1]["file"])
            if os.path.isfile(path):
                return path
    for p in reversed(snapshot.get("portraits", [])):
        path = os.path.join(run_dir, p["file"])
        if os.path.isfile(path):
            return path
    return None

# =============================================================================
#  NAMED SAVES  (pointers in saves/)
# =============================================================================

def _rel(path: str) -> str:
    """Relative to the project when inside it, so a moved project still loads."""
    try:
        rel = os.path.relpath(path, _SCRIPT_DIR)
    except ValueError:                        # another drive
        return path
    return path if rel.startswith("..") else rel


def resolve_run_dir(stored: str) -> str:
    return stored if os.path.isabs(stored) else os.path.join(_SCRIPT_DIR, stored)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:60] or "save"


def save_game(name: str, run_dir: str, round_done: int, saves_dir: str = None) -> str:
    """
    Write (or replace, same name in any case) a named save pointing at
    run_dir's checkpoint for round_done. Returns its path. Raises
    FileNotFoundError when that checkpoint does not exist.
    """
    snap = read_checkpoint(run_dir, round_done)
    if snap is None:
        raise FileNotFoundError(f"no checkpoint for round {round_done} in {run_dir}")
    d = saves_dir or SAVES_DIR
    name = (name or "").strip()[:80] or "Saved game"
    data = {"format": FORMAT, "name": name, "run_dir": _rel(run_dir),
            "round": int(round_done), "saved_at": datetime.now().isoformat(timespec="seconds"),
            "story_title": snap.get("story", {}).get("title", ""),
            "game_seed": snap.get("game_seed")}
    existing = next((r["path"] for r in list_saves(d) if r["name"].lower() == name.lower()), None)
    path = existing or os.path.join(d, _slug(name) + ".json")
    n = 2
    while existing is None and os.path.exists(path):
        path = os.path.join(d, f"{_slug(name)}_{n}.json")
        n += 1
    _atomic_write_json(path, data)
    return path


def list_saves(saves_dir: str = None) -> list:
    """Named saves, newest first; `ok` says whether the game can still be loaded."""
    d = saves_dir or SAVES_DIR
    rows = []
    try:
        names = os.listdir(d)
    except OSError:
        return rows
    for fn in names:
        if not fn.lower().endswith(".json"):
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not (isinstance(data, dict) and data.get("format") == FORMAT
                and "run_dir" in data and "round" in data):
            continue
        run = resolve_run_dir(data["run_dir"])
        snap = read_checkpoint(run, data["round"])
        rows.append({"name": data.get("name", fn), "path": path, "run_dir": run,
                     "round": data["round"], "saved_at": data.get("saved_at", ""),
                     "story_title": data.get("story_title", ""),
                     "game_seed": data.get("game_seed"), "ok": snap is not None,
                     "thumbnail": thumbnail_for(snap, run) if snap else None})
    rows.sort(key=lambda r: r["saved_at"], reverse=True)
    return rows


def delete_save(name: str, saves_dir: str = None) -> bool:
    """Delete a named save (the POINTER only - the run folder is untouched)."""
    for r in list_saves(saves_dir):
        if r["name"].lower() == (name or "").lower():
            os.remove(r["path"])
            return True
    return False

# =============================================================================
#  CONTINUING FROM AN EARLIER ROUND
# =============================================================================

def later_rounds_exist(run_dir: str, round_done: int) -> bool:
    return any(r > round_done for r in checkpoints_in(run_dir)) or any(
        (m := _ROUND_FILE.match(n)) and int(m.group(1)) > round_done
        for n in _listdir(run_dir))


def _listdir(d):
    try:
        return os.listdir(d)
    except OSError:
        return []


def archive_later_rounds(run_dir: str, round_done: int, stamp: str = None):
    """
    Before a game continues from round_done, move everything of the rounds
    AFTER it - text files, pictures, audio, checkpoints - into
    branch_<stamp>/, so the new rounds cannot overwrite the old ones and
    nothing is lost. Returns the branch folder, or None if nothing was later.
    Logs (images.txt, timings.txt, log.txt) keep growing in place.
    """
    stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    branch = os.path.join(run_dir, f"branch_{stamp}")
    moved = 0

    def move(src, rel):
        nonlocal moved
        dst = os.path.join(branch, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        moved += 1

    for n in _listdir(run_dir):
        m = (_ROUND_FILE.match(n) or _SCENE_FILE.match(n) or _PORTRAIT_FILE.match(n))
        if m and int(m.group(1)) > round_done:
            move(os.path.join(run_dir, n), n)
    for sub, pat in ((CHECKPOINT_SUBDIR, _CKPT_FILE), ("audio", _AUDIO_FILE)):
        for n in _listdir(os.path.join(run_dir, sub)):
            m = pat.match(n)
            if m and int(m.group(1)) > round_done:
                move(os.path.join(run_dir, sub, n), os.path.join(sub, n))
    return branch if moved else None


def compatibility(snapshot: dict, engine_version: str, model: str, checkpoint: str) -> list:
    """Warnings (never refusals) when a save was made with other software."""
    warn = []
    if snapshot.get("engine_version") != engine_version:
        warn.append(f"saved with engine v{snapshot.get('engine_version')}, "
                    f"now v{engine_version} - the story may continue a little differently")
    if snapshot.get("model") != model:
        warn.append(f"saved with text model {snapshot.get('model')}")
    if checkpoint and snapshot.get("image_checkpoint") not in (None, checkpoint):
        warn.append(f"saved with image checkpoint {snapshot.get('image_checkpoint')}")
    return warn
