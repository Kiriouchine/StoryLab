"""
setup_core.py - Story Lab setup assistant, the logic (no GUI).

What it does, in order (storylab_setup.py is the window around it):
  1. looks at the PC: NVIDIA GPU / VRAM / driver, free disk, an Ollama that
     answers, the ComfyUI installs it can find (and whether each can load
     Anima), model files already in their folders;
  2. builds a PLAN from the player's choices (text + voice always; Classical
     and/or Cinematic pictures), skipping everything already present;
  3. runs it: Ollama silent install + `/api/pull` for Rocinante, the Kokoro
     voices, the official ComfyUI portable (download + 7zr extract) or an
     existing ComfyUI, then every model into the folder ComfyUI reads it from;
  4. writes storylab_paths.json, which Story Lab reads to find all of it.

Downloads stream to <name>.part, RESUME with an HTTP Range request after an
interruption, are checked against the SHA-256 in manifest.json, and only
then renamed into place - a damaged file is deleted, never used. (The design
of CiviImport's downloader, github.com/Kiriouchine/CiviImport, MIT.)

HTTPS uses the Windows certificate store (truststore): on the PC this was
built on, the antivirus inspects TLS and Python's own certificate list
rejects civitai.com.
"""
from __future__ import annotations

import os
import re
import sys
import json
import time
import shutil
import hashlib
import threading
import subprocess
from dataclasses import dataclass, field

try:                                       # Windows certificate store for all HTTPS
    import truststore
    truststore.inject_into_ssl()
except Exception:                          # still works without it on a clean PC
    pass

import requests

SETUP_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_FILE = os.path.join(SETUP_DIR, "manifest.json")
PATHS_FILE_NAME = "storylab_paths.json"
OLLAMA_URL = "http://127.0.0.1:11434"
USER_AGENT = "StoryLab-Setup/1.0"
CHUNK = 1 << 20
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

COMPONENTS = ("core", "classical", "cinematic", "music")      # v12.4: + music


def default_app_dir() -> str:
    """The installed layout is <app>\\setup\\setup_core.py; in the source tree it
    is <project>\\installer\\setup_core.py. Either way: the parent."""
    return os.path.dirname(SETUP_DIR)


class SetupError(Exception):
    """A user-facing failure with a plain message."""


class NeedsKey(SetupError):
    """The source refused the download without (or with this) CivitAI key."""


class Cancelled(SetupError):
    pass


# =============================================================================
#  MANIFEST
# =============================================================================

def load_manifest(path: str = None) -> dict:
    with open(path or MANIFEST_FILE, encoding="utf-8") as f:
        man = json.load(f)
    man["by_id"] = {it["id"]: it for it in man["items"]}
    return man


def item_components(it) -> set:
    return set(it["component"].split("+"))


# =============================================================================
#  THE PC
# =============================================================================

@dataclass
class Gpu:
    name: str = ""
    vram_mb: int = 0
    driver: str = ""
    compute_cap: float = 0.0

    @property
    def nvidia(self) -> bool:
        return bool(self.name)

    @property
    def driver_major(self) -> int:
        try:
            return int(self.driver.split(".")[0])
        except ValueError:
            return 0


def gpu_info(run=subprocess.run) -> Gpu:
    """First NVIDIA GPU from nvidia-smi, or an empty Gpu."""
    try:
        out = run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version,compute_cap",
                   "--format=csv,noheader,nounits"], capture_output=True, text=True,
                  timeout=15, creationflags=NO_WINDOW).stdout
        name, mem, drv, cap = [x.strip() for x in out.strip().splitlines()[0].split(",")]
        return Gpu(name, int(float(mem)), drv, float(cap))
    except Exception:
        return Gpu()


def comfy_build_for(gpu: Gpu) -> str | None:
    """Which official portable build: 'comfyui' (CUDA 13, 20-series and newer),
    'comfyui_cu126' (10-series and older), or None (no NVIDIA GPU)."""
    if not gpu.nvidia:
        return None
    return "comfyui" if gpu.compute_cap >= 7.5 else "comfyui_cu126"


def free_gb(path: str) -> float:
    p = os.path.abspath(path)
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    try:
        return shutil.disk_usage(p).free / 1e9
    except OSError:
        return 0.0


# =============================================================================
#  OLLAMA
# =============================================================================

_seen = {}                                 # short memo: the window re-plans on every page


def _memo(key, fn, ttl=8.0):
    hit = _seen.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _seen[key] = (time.time(), val)
    return val


def ollama_running(url: str = OLLAMA_URL) -> bool:
    def ask():
        try:
            return requests.get(f"{url}/api/version", timeout=3).status_code == 200
        except Exception:
            return False
    return _memo(("up", url), ask)


def find_ollama_exe() -> str | None:
    for cand in (shutil.which("ollama"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
                 os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe")):
        if cand and os.path.isfile(cand):
            return cand
    return None


def start_ollama(exe: str, url: str = OLLAMA_URL, wait: float = 60.0) -> bool:
    """Start `ollama serve` with no window and wait until it answers."""
    _seen.clear()
    if ollama_running(url):
        return True
    subprocess.Popen([exe, "serve"], creationflags=NO_WINDOW,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < wait:
        _seen.clear()
        if ollama_running(url):
            return True
        time.sleep(1)
    return False


def ollama_models(url: str = OLLAMA_URL, fresh: bool = False) -> list:
    def ask():
        try:
            return [m["name"] for m in requests.get(f"{url}/api/tags", timeout=10).json()
                    .get("models", [])]
        except Exception:
            return []
    if fresh:
        _seen.pop(("tags", url), None)
    return _memo(("tags", url), ask)


def ollama_has(model: str, url: str = OLLAMA_URL) -> bool:
    want = model.lower()
    return any(m.lower() == want or m.lower() == want + ":latest" for m in ollama_models(url))


def ollama_pull(model: str, progress=None, cancel=None, url: str = OLLAMA_URL) -> None:
    """Ollama's own download (it keeps the model where Ollama keeps models)."""
    with requests.post(f"{url}/api/pull", json={"model": model, "stream": True},
                       stream=True, timeout=(10, 600)) as r:
        if r.status_code != 200:
            raise SetupError(f"Ollama refused the pull ({r.status_code}): {r.text[:200]}")
        for line in r.iter_lines():
            if cancel is not None and cancel.is_set():
                raise Cancelled("cancelled - the pull continues next time")
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("error"):
                raise SetupError(f"Ollama: {msg['error']}")
            if progress and msg.get("total"):
                progress(msg.get("completed", 0), msg["total"], msg.get("status", ""))
            if msg.get("status") == "success":
                return
    _seen.clear()
    if not ollama_has(model, url):
        raise SetupError("Ollama ended the pull without the model")


def install_ollama(setup_exe: str, wait: float = 900.0) -> None:
    """Official installer, silent, per user (installs to %LOCALAPPDATA%\\Programs\\Ollama)."""
    p = subprocess.run([setup_exe, "/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                       timeout=wait, creationflags=NO_WINDOW)
    if p.returncode != 0:
        raise SetupError(f"the Ollama installer stopped with code {p.returncode}")


# =============================================================================
#  COMFYUI - what is installed, and where its models go
# =============================================================================

@dataclass
class ComfyInstall:
    kind: str                       # "portable" | "desktop" | "desktop2"
    label: str
    python: str
    main: str
    base: str                       # --base-directory (desktop) / portable root
    model_roots: list = field(default_factory=list)   # first = where new files go
    extra_yaml: str = ""
    version: str = ""
    supports_anima: bool = False
    supports_music: bool = False    # v12.4: has the ACE-Step 1.5 nodes

    def launch(self) -> dict:
        """What Story Lab needs to start this ComfyUI (storylab_paths.json)."""
        return {"kind": self.kind, "python": self.python, "main": self.main,
                "base": self.base, "extra_model_paths": self.extra_yaml,
                "version": self.version}


def _comfy_meta(code_dir: str):
    """(version, supports_anima) from a ComfyUI source folder."""
    version = ""
    try:
        txt = open(os.path.join(code_dir, "comfyui_version.py"), encoding="utf-8").read()
        m = re.search(r'__version__\s*=\s*"([^"]+)"', txt)
        version = m.group(1) if m else ""
    except OSError:
        pass
    try:
        sm = open(os.path.join(code_dir, "comfy", "supported_models.py"), encoding="utf-8").read()
        anima = "class Anima(" in sm
    except OSError:
        anima = False
    return version, anima


def _comfy_music(code_dir: str) -> bool:
    """v12.4: can this ComfyUI make Story Lab's music? (its ACE-Step 1.5
    nodes - the old Desktop 0.5 has only ACE-Step 1.0's)."""
    try:
        src = open(os.path.join(code_dir, "comfy_extras", "nodes_ace.py"), encoding="utf-8").read()
        return "TextEncodeAceStepAudio1.5" in src
    except OSError:
        return False


def _with_music(inst):
    inst.supports_music = _comfy_music(os.path.dirname(inst.main))
    return inst


def _yaml_base_paths(path: str) -> list:
    """base_path values from an extra_model_paths YAML, in file order."""
    out = []
    try:
        for line in open(path, encoding="utf-8"):
            m = re.match(r"\s*base_path:\s*['\"]?([^'\"#\n]+?)['\"]?\s*$", line)
            if m and not line.lstrip().startswith("#"):
                out.append(m.group(1).strip())
    except OSError:
        pass
    return out


def portable_at(root: str) -> ComfyInstall | None:
    py = os.path.join(root, "python_embeded", "python.exe")
    main = os.path.join(root, "ComfyUI", "main.py")
    if not (os.path.isfile(py) and os.path.isfile(main)):
        return None
    version, anima = _comfy_meta(os.path.join(root, "ComfyUI"))
    return _with_music(ComfyInstall("portable", f"ComfyUI portable {version} - {root}", py,
                                    main, root, [os.path.join(root, "ComfyUI", "models")], "",
                                    version, anima))


def find_comfy_installs(app_dir: str = None, env=os.environ) -> list:
    """Every ComfyUI this PC has that Story Lab knows how to start."""
    found = []
    appdata, local = env.get("APPDATA", ""), env.get("LOCALAPPDATA", "")
    home = os.path.expanduser("~")
    # 1. a portable copy: ours first, then the usual places
    roots = []
    if app_dir:
        roots.append(os.path.join(app_dir, "ComfyUI_windows_portable"))
    for r in (home, os.path.join(home, "Desktop"), os.path.join(home, "Downloads"), "C:\\", "D:\\"):
        roots.append(os.path.join(r, "ComfyUI_windows_portable"))
    seen = set()
    for r in roots:
        inst = portable_at(r)
        if inst and os.path.normcase(r) not in seen:
            seen.add(os.path.normcase(r))
            found.append(inst)
    # 2. the new Comfy Desktop app (several installs, shared model folders)
    try:
        insts = json.load(open(os.path.join(appdata, "Comfy Desktop", "installations.json"),
                               encoding="utf-8"))
    except Exception:
        insts = []
    for inst in insts if isinstance(insts, list) else []:
        path = inst.get("installPath")
        if not path or inst.get("status") != "installed":
            continue
        code = os.path.join(path, "ComfyUI")
        py = inst.get("adoptedPythonPath") or os.path.join(path, ".venv", "Scripts", "python.exe")
        main = os.path.join(code, "main.py")
        if not (os.path.isfile(py) and os.path.isfile(main)):
            continue
        yaml = os.path.join(appdata, "Comfy Desktop", "instance-model-paths", f"{inst.get('id')}.yaml")
        roots = _yaml_base_paths(yaml) or [os.path.join(code, "models")]
        version, anima = _comfy_meta(code)
        found.append(_with_music(ComfyInstall(
            "desktop2", f"Comfy Desktop {version} - {inst.get('name', '')}",
            py, main, inst.get("adoptedBaseDir") or path, roots,
            yaml if os.path.isfile(yaml) else "", version, anima)))
    # 3. the older ComfyUI Desktop app
    try:
        base = json.load(open(os.path.join(appdata, "ComfyUI", "config.json"),
                              encoding="utf-8")).get("basePath")
    except Exception:
        base = None
    if base:
        py = os.path.join(base, ".venv", "Scripts", "python.exe")
        code = os.path.join(local, "Programs", "ComfyUI", "resources", "ComfyUI")
        main = os.path.join(code, "main.py")
        if os.path.isfile(py) and os.path.isfile(main):
            yaml = os.path.join(appdata, "ComfyUI", "extra_models_config.yaml")
            version, anima = _comfy_meta(code)
            found.append(_with_music(ComfyInstall(
                "desktop", f"ComfyUI Desktop {version}", py, main, base,
                [os.path.join(base, "models")],
                yaml if os.path.isfile(yaml) else "", version, anima)))
    return found


# ComfyUI reads each kind from either folder name (both are registered)
FOLDER_ALIASES = {"diffusion_models": ("diffusion_models", "unet"),
                  "text_encoders": ("text_encoders", "clip"),
                  "checkpoints": ("checkpoints",), "embeddings": ("embeddings",),
                  "vae": ("vae",)}


def find_model_file(roots, folder: str, filename: str, size: int = None) -> str | None:
    """An existing copy of a model under any root/alias folder (name + size)."""
    for root in roots:
        for sub in FOLDER_ALIASES.get(folder, (folder,)):
            p = os.path.join(root, sub, filename)
            if os.path.isfile(p) and (not size or os.path.getsize(p) == size):
                return p
    return None


def model_target(roots, folder: str) -> str:
    """Where a new file of this kind goes: the first root, the folder name
    ComfyUI's own docs use (diffusion_models, text_encoders...)."""
    if not roots:
        raise SetupError("no model folder known for this ComfyUI")
    return os.path.join(roots[0], FOLDER_ALIASES.get(folder, (folder,))[0])


# =============================================================================
#  DOWNLOADS
# =============================================================================

def sha256_file(path: str, progress=None, cancel=None) -> str:
    h, done, total = hashlib.sha256(), 0, os.path.getsize(path)
    with open(path, "rb") as f:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled("cancelled")
            b = f.read(CHUNK * 8)
            if not b:
                break
            h.update(b)
            done += len(b)
            if progress:
                progress(done, total, "checking")
    return h.hexdigest()


def download(url: str, dest: str, sha256: str = None, size: int = None,
             headers: dict = None, progress=None, cancel=None, session=None) -> str:
    """
    Stream url to dest. Resumes a <dest>.part left by an interrupted run
    (Range request); verifies sha256; renames into place. Returns dest.
    Raises NeedsKey on 401/403, SetupError on anything else, Cancelled.
    """
    s = session or requests.Session()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    h = hashlib.sha256()
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if have and size and have > size:              # junk from elsewhere
        os.remove(part)
        have = 0
    if have:                                       # rebuild the hash of what we have
        with open(part, "rb") as f:
            for b in iter(lambda: f.read(CHUNK * 8), b""):
                h.update(b)
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    if have:
        hdrs["Range"] = f"bytes={have}-"
    try:
        r = s.get(url, headers=hdrs, stream=True, timeout=(15, 120), allow_redirects=True)
    except requests.RequestException as e:
        raise SetupError(f"could not reach {url.split('/')[2]}: {e}")
    with r:
        if r.status_code in (401, 403):
            raise NeedsKey(f"{url.split('/')[2]} wants a key for this file ({r.status_code})")
        if r.status_code == 416 and have:          # we already have all of it
            pass
        elif r.status_code == 200 and have:        # server ignored Range: start over
            have, h = 0, hashlib.sha256()
            open(part, "wb").close()
        elif r.status_code not in (200, 206):
            raise SetupError(f"download failed: HTTP {r.status_code} from {url.split('/')[2]}")
        total = size or (have + int(r.headers.get("Content-Length", 0) or 0))
        if r.status_code in (200, 206):
            with open(part, "ab" if have else "wb") as f:
                last = 0.0
                try:
                    for b in r.iter_content(CHUNK):
                        if cancel is not None and cancel.is_set():
                            raise Cancelled("cancelled - the download resumes next time")
                        if not b:
                            continue
                        f.write(b)
                        h.update(b)
                        have += len(b)
                        if progress and time.time() - last > 0.2:
                            progress(have, total, "downloading")
                            last = time.time()
                except requests.RequestException as e:   # keep the .part: resume later
                    raise SetupError(f"the connection dropped after {have / 1e9:.2f} GB - "
                                     f"run Setup again to continue where it stopped ({e.__class__.__name__})")
        if total and have < total:
            raise SetupError(f"{os.path.basename(dest)} is incomplete ({have} of {total} bytes) - "
                             f"run Setup again to continue")
    if progress:
        progress(have, total, "checking")
    got = h.hexdigest()
    if sha256 and got != sha256.lower():
        os.remove(part)
        raise SetupError(f"{os.path.basename(dest)} arrived damaged (SHA-256 does not match) "
                         f"- deleted, it will be downloaded again next time")
    os.replace(part, dest)
    return dest


def civitai_headers(key: str | None) -> dict:
    return {"Authorization": f"Bearer {key}"} if key else {}


def check_civitai_key(key: str, url: str, session=None) -> bool:
    """True if CivitAI serves this file with this key (asks for 1 byte)."""
    s = session or requests.Session()
    try:
        r = s.get(url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0",
                                **civitai_headers(key)},
                  stream=True, timeout=(15, 30), allow_redirects=True)
        r.close()
        return r.status_code in (200, 206)
    except requests.RequestException:
        return False


def hf_cached(repo: str, filename: str, env=os.environ) -> bool:
    """Is this file already in the Hugging Face cache (where kokoro looks)?"""
    home = env.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    hub = env.get("HF_HUB_CACHE") or os.path.join(home, "hub")
    snaps = os.path.join(hub, "models--" + repo.replace("/", "--"), "snapshots")
    try:
        return any(os.path.exists(os.path.join(snaps, s, filename)) for s in os.listdir(snaps))
    except OSError:
        return False


def hf_url(repo: str, path: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{path}"


def item_url(it: dict) -> str:
    return it.get("url") or hf_url(it["hf_repo"], it["hf_file"])


# =============================================================================
#  THE PLAN
# =============================================================================

@dataclass
class Choices:
    classical: bool = True                # Classical AND Medium (one model: Nova Furry)
    cinematic: bool = True
    music: bool = True                    # v12.4: background music (ACE-Step 1.5)
    lazyneg: bool = False                 # optional, needs a CivitAI key
    civitai_key: str = ""
    anima_official: bool = False          # no key: the official Anima instead
    comfy: ComfyInstall | None = None     # None = install the official portable


@dataclass
class Step:
    id: str
    label: str
    kind: str                             # see Runner.run_step
    item: dict = None
    size: int = 0
    status: str = "waiting"               # waiting|running|done|skipped|failed
    note: str = ""
    target: str = ""


MUSIC_ITEMS = ("ace15_turbo", "ace15_qwen_06b", "ace15_qwen_17b", "ace15_vae")


def wants_comfy(ch) -> bool:
    """Does anything chosen need ComfyUI? (pictures or music)"""
    return bool(ch.classical or ch.cinematic or getattr(ch, "music", False))


def comfy_can(inst, ch) -> bool:
    """Can this ComfyUI do everything chosen?"""
    return ((not ch.cinematic or inst.supports_anima)
            and (not getattr(ch, "music", False) or inst.supports_music))


def anima_item(man: dict, ch: Choices) -> dict:
    return man["by_id"]["anima_aesthetic" if ch.anima_official else "marshmallow_anima"]


def picture_items(man: dict, ch: Choices) -> list:
    """The ComfyUI model files these choices need, in install order."""
    its = []
    if ch.classical:
        its.append(man["by_id"]["novafurry"])
        if ch.lazyneg:
            its.append(man["by_id"]["lazyneg"])
    if ch.cinematic:
        its += [anima_item(man, ch), man["by_id"]["qwen_text_encoder"],
                man["by_id"]["qwen_image_vae"]]
    if getattr(ch, "music", False):                 # v12.4
        its += [man["by_id"][i] for i in MUSIC_ITEMS]
    return its


def licence_items(man: dict, ch: Choices) -> list:
    """Everything the player is asked to accept for these choices."""
    ids = ["ollama", "rocinante", "kokoro"]
    if wants_comfy(ch):
        if ch.comfy is None:
            ids.append("comfyui")
    out = [man["by_id"][i] for i in ids] + picture_items(man, ch)
    return out


def needs_key(it: dict) -> bool:
    return it.get("auth", "").startswith("civitai-key")


def build_plan(man: dict, ch: Choices, app_dir: str, gpu: Gpu = None) -> list:
    """The steps, with what is already on the PC marked skipped."""
    steps = []
    exe = find_ollama_exe()
    if ollama_running() or exe:
        steps.append(Step("ollama", "Ollama", "ollama_install", man["by_id"]["ollama"],
                          status="skipped", note="already installed"))
    else:
        steps.append(Step("ollama", "Ollama", "ollama_install", man["by_id"]["ollama"],
                          man["by_id"]["ollama"]["size_bytes"]))
    roc = man["by_id"]["rocinante"]
    st = Step("rocinante", "Rocinante (the story model)", "ollama_pull", roc, roc["size_bytes"])
    if ollama_running() and ollama_has(roc["pull"]):
        st.status, st.note, st.size = "skipped", "already in Ollama", 0
    steps.append(st)
    kok = man["by_id"]["kokoro"]
    st = Step("kokoro", "Kokoro voices", "hf_snapshot", kok, kok["size_bytes"])
    if hf_cached(kok["hf_repo"], "kokoro-v1_0.pth"):
        st.status, st.note, st.size = "skipped", "already downloaded", 0
    steps.append(st)
    if wants_comfy(ch):
        if ch.comfy is None:
            build = comfy_build_for(gpu or gpu_info()) or "comfyui"
            it = man["by_id"][build]
            st = Step("comfyui", "ComfyUI (official portable)", "comfy_portable", it,
                      it["size_bytes"], target=os.path.join(app_dir, "ComfyUI_windows_portable"))
            if portable_at(st.target):
                st.status, st.note, st.size = "skipped", "already installed", 0
            steps.append(st)
            roots = [os.path.join(app_dir, "ComfyUI_windows_portable", "ComfyUI", "models")]
        else:
            roots = ch.comfy.model_roots
            steps.append(Step("comfyui", "ComfyUI", "none", status="skipped",
                              note=f"using {ch.comfy.label}"))
        for it in picture_items(man, ch):
            found = find_model_file(roots, it["folder"], it["filename"], it.get("size_bytes"))
            st = Step(it["id"], it["what"].split(" (")[0], "model", it, it.get("size_bytes", 0),
                      target=os.path.join(model_target(roots, it["folder"]), it["filename"]))
            if found:
                st.status, st.note, st.size, st.target = "skipped", "already there", 0, found
            steps.append(st)
    steps.append(Step("paths", "Tell Story Lab where everything is", "write_paths"))
    return steps


def plan_bytes(steps) -> int:
    return sum(s.size for s in steps if s.status != "skipped")


# =============================================================================
#  STORY LAB'S PATHS FILE
# =============================================================================

def paths_file(app_dir: str) -> str:
    return os.path.join(app_dir, PATHS_FILE_NAME)


def read_paths(app_dir: str) -> dict:
    try:
        with open(paths_file(app_dir), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_paths(app_dir: str, ch: Choices, comfy: ComfyInstall | None, anima_file: str,
                ollama_exe: str | None) -> dict:
    data = {
        "version": 1,
        "written": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ollama": {"url": OLLAMA_URL, "exe": ollama_exe or ""},
        "comfyui": comfy.launch() if comfy else None,
        "styles": {"classical": bool(ch.classical and comfy),
                   "cinematic": bool(ch.cinematic and comfy),
                   "music": bool(getattr(ch, "music", False) and comfy)},
        "anima_model": anima_file if ch.cinematic else "",
    }
    tmp = paths_file(app_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, paths_file(app_dir))
    return data


CINEMATIC_WORKFLOWS = ("Workflow_cinematic_api.json", "Workflow_cinematic_portrait_api.json")


def set_anima_model(app_dir: str, filename: str) -> int:
    """Point both Cinematic workflows at the Anima file that was installed.
    Returns how many files changed."""
    changed = 0
    for name in CINEMATIC_WORKFLOWS:
        p = os.path.join(app_dir, name)
        try:
            wf = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        hit = False
        for node in wf.values():
            if isinstance(node, dict) and node.get("class_type") == "UNETLoader":
                if node["inputs"].get("unet_name") != filename:
                    node["inputs"]["unet_name"] = filename
                    hit = True
        if hit:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(wf, f, indent=2, ensure_ascii=False)
            changed += 1
    return changed


# =============================================================================
#  RUNNER
# =============================================================================

class Runner:
    """Runs a plan on a thread. events: callback(kind, step, *data) where kind is
    'start' | 'progress'(done, total, phase) | 'done' | 'skipped' | 'failed'(msg)
    | 'log'(text) | 'finished'(ok)."""

    def __init__(self, man, ch: Choices, steps, app_dir: str, events, gpu: Gpu = None):
        self.man, self.ch, self.steps, self.app_dir = man, ch, steps, app_dir
        self.events, self.gpu = events, gpu
        self.cancel = threading.Event()
        self.session = requests.Session()
        self.downloads = os.path.join(app_dir, "downloads")
        self.comfy = ch.comfy

    def log(self, text):
        self.events("log", None, text)

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        return t

    def _run(self):
        ok = True
        for st in self.steps:
            if self.cancel.is_set():
                ok = False
                break
            if st.status == "skipped":
                self.events("skipped", st)
                continue
            st.status = "running"
            self.events("start", st)
            try:
                self.run_step(st)
                st.status = "done"
                self.events("done", st)
            except Cancelled as e:
                st.status, st.note = "failed", str(e)
                self.events("failed", st, str(e))
                ok = False
                break
            except Exception as e:                       # one step failing stops the rest
                st.status, st.note = "failed", str(e)
                self.events("failed", st, str(e))
                ok = False
                if st.kind in ("ollama_install", "comfy_portable", "write_paths"):
                    break
        self.events("finished", None, ok)

    def _progress(self, st):
        return lambda done, total, phase="": self.events("progress", st, done, total, phase)

    def run_step(self, st: Step):
        if st.kind == "ollama_install":
            dest = os.path.join(self.downloads, "OllamaSetup.exe")
            download(st.item["url"], dest, st.item.get("sha256"), st.item.get("size_bytes"),
                     progress=self._progress(st), cancel=self.cancel, session=self.session)
            self.log("installing Ollama (silent)...")
            self.events("progress", st, 1, 1, "installing")
            install_ollama(dest)
            exe = find_ollama_exe()
            if not exe or not start_ollama(exe):
                raise SetupError("Ollama was installed but does not answer - restart the PC "
                                 "and run Story Lab Setup again")
            os.remove(dest)
        elif st.kind == "ollama_pull":
            exe = find_ollama_exe()
            if not ollama_running() and not (exe and start_ollama(exe)):
                raise SetupError("Ollama is not running")
            ollama_pull(st.item["pull"], self._progress(st), self.cancel)
        elif st.kind == "hf_snapshot":
            self._kokoro(st)
        elif st.kind == "comfy_portable":
            self._comfy_portable(st)
        elif st.kind == "model":
            it = st.item
            headers = civitai_headers(self.ch.civitai_key) if needs_key(it) else {}
            download(item_url(it), st.target, it.get("sha256"), it.get("size_bytes"),
                     headers=headers, progress=self._progress(st), cancel=self.cancel,
                     session=self.session)
        elif st.kind == "write_paths":
            if self.ch.cinematic:
                set_anima_model(self.app_dir, anima_item(self.man, self.ch)["filename"])
            comfy = None
            if wants_comfy(self.ch):                     # ours may predate this run
                comfy = self.comfy or portable_at(
                    os.path.join(self.app_dir, "ComfyUI_windows_portable"))
            write_paths(self.app_dir, self.ch, comfy,
                        anima_item(self.man, self.ch)["filename"], find_ollama_exe())
        elif st.kind == "none":
            pass
        else:
            raise SetupError(f"unknown step kind {st.kind}")

    def _kokoro(self, st):
        """The voices into the Hugging Face cache, where the kokoro package
        looks for them (it would otherwise fetch them during the first game)."""
        from huggingface_hub import snapshot_download
        self.events("progress", st, 0, st.size, "downloading")
        snapshot_download(st.item["hf_repo"],
                          allow_patterns=["config.json", "*.pth", "voices/*.pt"])
        self.events("progress", st, st.size, st.size, "done")

    def _comfy_portable(self, st):
        it = st.item
        archive = os.path.join(self.downloads, os.path.basename(it["url"]))
        download(it["url"], archive, it.get("sha256"), it.get("size_bytes"),
                 progress=self._progress(st), cancel=self.cancel, session=self.session)
        seven = os.path.join(self.app_dir, "tools", "7zr.exe")
        if not os.path.isfile(seven):
            seven = os.path.join(SETUP_DIR, "vendor", "7zr.exe")     # source tree
        self.events("progress", st, 0, 1, "unpacking (a few minutes)")
        p = subprocess.run([seven, "x", archive, f"-o{self.app_dir}", "-y", "-bso0", "-bsp0"],
                           creationflags=NO_WINDOW, capture_output=True, text=True)
        if p.returncode != 0:
            raise SetupError(f"unpacking ComfyUI failed: {p.stderr[-300:]}")
        inst = portable_at(st.target)
        if inst is None:
            raise SetupError("ComfyUI was unpacked but its python/main.py are not where expected")
        for sub in ("checkpoints", "embeddings", "diffusion_models", "text_encoders", "vae"):
            os.makedirs(os.path.join(inst.model_roots[0], sub), exist_ok=True)
        self.comfy = inst
        os.remove(archive)
        # The FIRST start of a freshly unpacked ComfyUI is slow (5.5 minutes on
        # the dev PC, the antivirus scanning thousands of new files; the second
        # start took 30 s). Do it here, so the first game does not wait.
        self.events("progress", st, 0, 1, "first start of ComfyUI (several minutes, once)")
        secs = first_start(inst, cancel=self.cancel)
        self.log(f"ComfyUI {inst.version} first start: {secs:.0f} s")
        self.events("progress", st, 1, 1, f"ComfyUI {inst.version}")


def first_start(inst: ComfyInstall, port: int = 8189, wait: float = 900.0, cancel=None) -> float:
    """Start a portable ComfyUI once, wait until it answers, stop it. Returns
    the seconds it took. Port 8189, so another ComfyUI on 8188 is not in the way."""
    env = {k: v for k, v in os.environ.items() if k.upper() != "SSLKEYLOGFILE"}
    log = open(os.path.join(inst.base, "first_start.log"), "w", encoding="utf-8")
    p = subprocess.Popen([inst.python, "-s", inst.main, "--windows-standalone-build",
                          "--listen", "127.0.0.1", "--port", str(port), "--disable-auto-launch"],
                         cwd=inst.base, env=env, stdout=log, stderr=subprocess.STDOUT,
                         creationflags=NO_WINDOW)
    t0 = time.time()
    try:
        while time.time() - t0 < wait:
            if cancel is not None and cancel.is_set():
                raise Cancelled("cancelled")
            if p.poll() is not None:
                raise SetupError(f"ComfyUI stopped during its first start (see "
                                 f"{os.path.join(inst.base, 'first_start.log')})")
            try:
                if requests.get(f"http://127.0.0.1:{port}/system_stats", timeout=2).status_code == 200:
                    return time.time() - t0
            except requests.RequestException:
                pass
            time.sleep(2)
        raise SetupError("ComfyUI did not answer within 15 minutes on its first start")
    finally:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(20)
            except Exception:
                p.kill()
        log.close()


# =============================================================================
#  SELF-TEST (after install)
# =============================================================================

def self_test(app_dir: str, events=print) -> dict:
    """Ollama answers and has the model; Story Lab's paths file is complete;
    ComfyUI starts with the saved parameters and can load each installed
    picture style's workflows (images12.missing_models)."""
    res = {}
    paths = read_paths(app_dir)
    res["paths"] = bool(paths)
    res["ollama"] = ollama_running() and ollama_has("hf.co/bartowski/TheDrummer_Rocinante-X-12B-v1-GGUF:Q4_K_M")
    events(f"Ollama + Rocinante: {'ok' if res['ollama'] else 'MISSING'}")
    comfy = paths.get("comfyui")
    styles = [s for s, on in (paths.get("styles") or {}).items() if on]
    if comfy and styles:
        sys.path.insert(0, app_dir)
        import story_lab_images12 as images
        server = images.ensure_comfyui(auto_launch=True, timeout=180)
        if not server:
            res["comfyui"] = False
            events("ComfyUI: did not start")
            return res
        wf = {"classical": (images.WORKFLOW_SCENE_FILE, images.WORKFLOW_PORTRAIT_FILE),
              "cinematic": (images.WORKFLOW_CINEMATIC_FILE, images.WORKFLOW_CINE_PORTRAIT_FILE)}
        for s in styles:
            if s == "music":                           # v12.4
                import story_lab_music12 as music
                missing = music.missing_models(server)
                res[s] = not missing
                events(f"Music: {'ok' if not missing else 'missing ' + ', '.join(missing)}")
                continue
            missing = sorted({m for f in wf[s] for m in images.missing_models(server, f)})
            res[s] = not missing
            events(f"{s.capitalize()} pictures: {'ok' if not missing else 'missing ' + ', '.join(missing)}")
        images.shutdown_comfyui()
    return res
