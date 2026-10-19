# Story Lab installer

`python installer\build_installer.py` builds `installer\dist\StoryLabSetup-12.4.exe`:
one file, about 16 MB, installed per user (no admin rights).

## What it does

1. **Setup wizard (Inno Setup 7)**: welcome, Apache 2.0 licence, choose the
   folder, desktop icon. It copies only what the game uses: the game files,
   their workflows, the setup assistant, uv.exe, 7zr.exe and the docs.
2. **Builds Story Lab's own Python** in that folder (`setup\make_env.cmd`):
   uv downloads Python 3.11, Python's own `venv` makes `.venv`, then PyTorch
   (CPU build) and the pinned packages go in. About 4 minutes, about 1 GB.
   It uses the Windows certificate store, so antivirus programs that inspect
   HTTPS do not break the downloads.
3. **Opens Story Lab Setup** (`setup\storylab_setup.py`), the assistant:
   - **Welcome**: what this PC has (graphics card, video memory, driver,
     Ollama, ComfyUI installs, free space)
   - **Pictures and music**: text and voice always; Classical + Medium (Nova
     Furry XL) and/or Cinematic (Anima); lazyneg optional; background music
     (ACE-Step 1.5, on by default)
   - **ComfyUI**: installs the official portable build (CUDA 13, or the CUDA
     12.6 build for 10-series cards) into the Story Lab folder, or uses one
     already on the PC if it can do everything chosen
   - **CivitAI key**: only if a chosen model needs one (Marshmallow Milk
     Anima, lazyneg). A button opens the account page, then you paste the
     key and Setup checks it. You can also continue without a key: Setup
     uses the official Anima instead and leaves lazyneg out.
   - **Licences**: one card per program or model, with its licence, a link
     and an "I agree" box. Nothing downloads without it.
   - **Install**: only what is missing. Downloads resume, are SHA-256
     checked, and go where Ollama and that ComfyUI read them.
   - **Done**: Play, or "Test everything" (starts Ollama and ComfyUI and
     checks every chosen style's workflow)
4. Writes `storylab_paths.json`. The game reads it to know which ComfyUI to
   start and how, which Ollama to use, which picture styles to offer, and
   which Anima file to load.

Start menu: Story Lab, Story Lab Setup (pictures, models, repair), Read me,
Uninstall. The uninstaller asks before deleting the downloaded ComfyUI and
models, and before deleting saved games (both default to keep). Ollama
stays, because it is its own program.

## Build

```
python installer\fetch_tools.py
python installer\build_installer.py
```

`fetch_tools.py` downloads the exact tool versions the build uses and checks
each file's SHA-256:

- **Inno Setup 7.1.0**, the compiler. It comes from the GitHub release and is
  installed for the current user into `installer\tools\InnoSetup`, with no
  shortcuts. An Inno Setup 7 that is already installed is also found.
- **uv 0.13.1** (signed, from the GitHub release) into `installer\vendor\`.
- **7zr.exe 26.04** (from 7-zip.org) into `installer\vendor\`.

The repository does not carry these programs.

To publish a version, attach `installer\dist\StoryLabSetup-<version>.exe` to
a GitHub release tagged `v<version>` (for example `v12.4`). The setup file is
never committed to git.

## Files

| file | what |
|---|---|
| `StoryLab.iss` | the Inno Setup script |
| `build_installer.py` | gathers the payload (only the files the game uses; fails if one is missing) and compiles the setup |
| `fetch_tools.py` | downloads Inno Setup, uv and 7zr for the build |
| `make_env.cmd` | builds the player's Python environment (venv, torch, packages) |
| `requirements.txt` | the game's packages, pinned |
| `setup_core.py` | the assistant's logic: detection, plan, downloads, Ollama, ComfyUI, paths |
| `storylab_setup.py` | the assistant's window (`--dry-run` walks it without installing) |
| `manifest.json` | every download: URL, size, SHA-256, folder, whether a key is needed, licence |
| `assets/` | icon and wizard images |
| `payload_docs/` | LICENSE (Apache 2.0), NOTICE, THIRD_PARTY_NOTICES.md, and README.txt for players |

## Known limits

- The setup file is not code-signed. Windows SmartScreen shows "Windows
  protected your PC" (More info → Run anyway). On PCs with Smart App
  Control switched on, Windows may refuse to run it at all. Code signing
  removes both. The options, cheapest first:
  - SignPath Foundation: free for open-source projects, signs in a GitHub
    Action.
  - Azure Trusted Signing: about 10 USD a month.
  - A classic OV code-signing certificate.
- Pictures and music need an NVIDIA graphics card. AMD and Intel ComfyUI
  builds are not offered.
- Story Lab Setup is in English only.
