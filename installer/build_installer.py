"""
build_installer.py - assemble Story Lab's installer payload and compile it.

  python installer/build_installer.py          -> installer/dist/StoryLabSetup-12.4.exe

Payload = only what the game uses (the v12 build, its workflows, the setup
assistant, docs, uv.exe and 7zr.exe). No research files, no older engine
versions, no runs or saves. Every file that goes in is listed below, and the
build fails if one is missing - a moved file must be noticed, not shipped
silently without.
"""
import os
import sys
import json
import shutil
import hashlib
import subprocess
import ast

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build", "payload")
# Inno Setup 7: the copy fetch_tools.py installs into the project, else a
# normal installation (per-user or for all users)
ISCC = next((p for p in (
    os.path.join(HERE, "tools", "InnoSetup", "ISCC.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 7", "ISCC.exe"),
    os.path.join(os.environ.get("ProgramFiles", ""), "Inno Setup 7", "ISCC.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Inno Setup 7", "ISCC.exe"))
    if os.path.isfile(p)), os.path.join(HERE, "tools", "InnoSetup", "ISCC.exe"))

GAME = ["story_lab_gui12.py", "story_lab_director12.py", "story_lab_engine12.py",
        "story_lab_images12.py", "story_lab_saves12.py", "story_lab_stories12.py",
        "story_lab_tts10.py", "story_lab_tts5.py", "kokoro_voices.py", "story_lab_metrics.py",
        "Workflow_portrait_api3.json", "Workflow_wide_api_3.json",
        "Workflow_cinematic_api.json", "Workflow_cinematic_portrait_api.json",
        # v12.4 music: the module and the user's ACE-Step 1.5 workflow (Setup
        # fetches its four model files when music is chosen)
        "story_lab_music12.py", "Musicgenerator_ace_1v5_good.json"]
SETUP = ["setup_core.py", "storylab_setup.py", "manifest.json", "make_env.cmd"]
ASSETS = ["storylab.ico", "storylab_1024.png", "side_panel.png"]
DOCS = ["LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "README.txt"]
TOOLS = {"uv.exe": os.path.join(HERE, "vendor", "uv", "uv.exe"),
         "7zr.exe": os.path.join(HERE, "vendor", "7zr.exe")}
# sha256 of the bundled tools (uv 0.13.1: uv.exe inside the GitHub release
# zip; 7zr: 7-zip.org, 26.04) - python installer/fetch_tools.py gets both
TOOL_SHA = {"uv.exe": "4075a09490327d2bedfacc807fa48252fb93647c5bd7ef28f00e579160ea3fb5",
            "7zr.exe": "256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282"}


def local_imports(files):
    """Top-level 'import x' of the game's own modules, so a module the game
    needs cannot be left out of GAME."""
    mods = {f[:-3] for f in os.listdir(ROOT) if f.endswith(".py")}
    need = set()
    for f in files:
        if not f.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(ROOT, f), encoding="utf-8").read())
        for n in tree.body:                       # module level only: lazy imports
            names = []                            # inside research helpers are not
            if isinstance(n, ast.Import):         # part of the game
                names = [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                names = [n.module.split(".")[0]]
            need |= {m + ".py" for m in names if m in mods}
    return need


def copy(src, rel):
    dst = os.path.join(BUILD, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.isfile(src):
        sys.exit(f"missing: {src}")
    shutil.copy2(src, dst)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    missing = local_imports(GAME) - set(GAME)
    if missing:
        sys.exit(f"the game imports {sorted(missing)} - add them to GAME")
    shutil.rmtree(os.path.join(HERE, "build"), ignore_errors=True)
    for f in GAME:
        copy(os.path.join(ROOT, f), f)
    for f in SETUP:
        copy(os.path.join(HERE, f), os.path.join("setup", f))
    cmd = os.path.join(BUILD, "setup", "make_env.cmd")      # cmd.exe wants CRLF
    lines = open(cmd, encoding="utf-8").read().splitlines()
    open(cmd, "w", encoding="ascii", newline=chr(13) + chr(10)).write(chr(10).join(lines) + chr(10))
    for f in ASSETS:
        copy(os.path.join(HERE, "assets", f), os.path.join("assets", f))
    for f in DOCS:
        copy(os.path.join(HERE, "payload_docs", f), f)
    copy(os.path.join(HERE, "requirements.txt"), "requirements.txt")
    for name, src in TOOLS.items():
        if not os.path.isfile(src):
            sys.exit(f"missing: {src} - run python installer/fetch_tools.py first")
        if TOOL_SHA[name] and sha(src) != TOOL_SHA[name]:
            sys.exit(f"{name}: unexpected SHA-256 - re-download it")
        copy(src, os.path.join("tools", name))
    # the Cinematic workflows ship pointing at the model Story Lab was tuned with
    for wf in ("Workflow_cinematic_api.json", "Workflow_cinematic_portrait_api.json"):
        d = json.load(open(os.path.join(BUILD, wf), encoding="utf-8"))
        unets = [n["inputs"]["unet_name"] for n in d.values() if n.get("class_type") == "UNETLoader"]
        if unets != ["marshmallowMilkAnima_v10.safetensors"]:
            sys.exit(f"{wf}: UNETLoader is {unets}")
    files = sum(len(fs) for _, _, fs in os.walk(BUILD))
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(BUILD) for f in fs)
    print(f"payload: {files} files, {size / 1e6:.1f} MB")
    if not os.path.isfile(ISCC):
        sys.exit(f"Inno Setup compiler not found: {ISCC} - run python installer/fetch_tools.py first")
    r = subprocess.run([ISCC, "/Qp", os.path.join(HERE, "StoryLab.iss")], cwd=HERE)
    if r.returncode:
        sys.exit(f"ISCC failed ({r.returncode})")
    out = os.path.join(HERE, "dist", "StoryLabSetup-12.4.exe")
    print(f"built: {out}  ({os.path.getsize(out) / 1e6:.1f} MB)  sha256 {sha(out)}")


if __name__ == "__main__":
    main()
