"""
fetch_tools.py - download the three tools the installer build needs.

  python installer/fetch_tools.py

The repository does not carry these programs (about 60 MB); this fetches the
exact versions the 12.4 installer was built with, from their official
release pages, and refuses any file whose SHA-256 differs:

  uv 0.13.1        -> installer/vendor/uv/uv.exe   (bundled into the setup:
                      builds the player's Python)
  7zr.exe 26.04    -> installer/vendor/7zr.exe     (bundled: unpacks the
                      ComfyUI portable)
  Inno Setup 7.1.0 -> installer/tools/InnoSetup/   (the compiler, installed
                      for the current user only; not bundled)

Inno Setup's licence: free for non-commercial use (jrsoftware.org/isinfo.php).
Already-present files with the right SHA-256 are kept. Standard library only.
"""
import os
import sys
import hashlib
import zipfile
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "vendor")
TOOLS = os.path.join(HERE, "tools")

UV_ZIP = ("https://github.com/astral-sh/uv/releases/download/0.13.1/uv-x86_64-pc-windows-msvc.zip",
          "3b2661a463a5baea7f5076ea2b25ab71d77f36a6c0d809e5350651792f80a672")
SEVEN_ZR = ("https://www.7-zip.org/a/7zr.exe",
            "256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282")
INNO = ("https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe",
        "0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(url, want, dst):
    """dst with SHA-256 `want` - kept if already right, else downloaded."""
    if os.path.isfile(dst) and sha(dst) == want:
        print(f"  ok (already here)  {os.path.relpath(dst, HERE)}")
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    print(f"  downloading {url}")
    part = dst + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "StoryLab-build"})
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
        for b in iter(lambda: r.read(1 << 20), b""):
            f.write(b)
    got = sha(part)
    if got != want:
        os.remove(part)
        sys.exit(f"SHA-256 mismatch for {url}\n  expected {want}\n  got      {got}\n"
                 "(7-zip.org serves the newest 7zr.exe: if 7-Zip released a new "
                 "version, check it and update SEVEN_ZR and build_installer.TOOL_SHA)")
    os.replace(part, dst)
    print(f"  ok  {os.path.relpath(dst, HERE)}")


def main():
    if os.name != "nt":
        sys.exit("the installer is built on Windows")
    zpath = os.path.join(VENDOR, "uv.zip")
    fetch(*UV_ZIP, zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(os.path.join(VENDOR, "uv"))
    print(f"  ok  vendor/uv/uv.exe  (sha256 {sha(os.path.join(VENDOR, 'uv', 'uv.exe'))[:16]}...)")
    fetch(*SEVEN_ZR, os.path.join(VENDOR, "7zr.exe"))
    iscc = os.path.join(TOOLS, "InnoSetup", "ISCC.exe")
    if os.path.isfile(iscc):
        print("  ok (already here)  tools/InnoSetup/ISCC.exe")
    else:
        exe = os.path.join(TOOLS, "innosetup-7.1.0-x64.exe")
        fetch(*INNO, exe)
        print("  installing Inno Setup 7.1.0 into installer/tools/InnoSetup (current user) ...")
        # per-user, no Start-menu folder, no desktop icon, no optional tasks:
        # only the compiler's files in installer/tools/InnoSetup (it can be
        # removed again with its unins000.exe there)
        r = subprocess.run([exe, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                            "/CURRENTUSER", "/NOICONS", "/TASKS=",
                            f"/DIR={os.path.join(TOOLS, 'InnoSetup')}",
                            f"/LOG={os.path.join(TOOLS, 'inno_install.log')}"])
        if r.returncode or not os.path.isfile(iscc):
            sys.exit(f"Inno Setup did not install (exit {r.returncode}); "
                     "see installer/tools/inno_install.log")
        print("  ok  tools/InnoSetup/ISCC.exe")
    print("done - now: python installer/build_installer.py")


if __name__ == "__main__":
    main()
