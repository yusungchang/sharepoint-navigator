#!/usr/bin/env python3
"""Build SharePoint Navigator for the current OS: a windowless app with its icon.

Run on each OS you want a build for (PyInstaller does not cross-compile):

    python -m pip install -r requirements-build.txt
    python build_app.py

Output:
  macOS:   dist/SharePoint Navigator.app  (a background app: no Dock window, the browser is its window)
  Windows: dist/SharePoint Navigator.exe  (one file, no console window)
Without a terminal, the app shows setup and sign-in in the browser and writes messages to
~/.sharepoint-navigator/app.log. A <tenant>_clientid.txt next to the .app or .exe is still honoured.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "SharePoint Navigator"
BUNDLE_ID = "com.yusungchang.sharepoint-navigator"


def read_version() -> str:
    """The app's __version__, read from the source without importing it."""
    for line in (ROOT / "sharepoint-navigator.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split('"')[1]
    return "0.0.0"


def finish_mac_app(app: Path, version: str) -> None:
    """Make the .app a background app (no Dock window) with the right version, then re-seal it.

    PyInstaller signs the bundle ad hoc; editing Info.plist breaks that seal, so it is signed
    ad hoc again (Apple silicon refuses to run unsigned code). This is not a Developer ID
    signature: Gatekeeper still asks once on other Macs.
    """
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    info.update({
        # Background app: the page in the browser is the window; closing its tab stops the app.
        "LSUIElement": True,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "NSHumanReadableCopyright": "MIT licence · github.com/yusungchang/sharepoint-navigator",
    })
    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)


def main() -> int:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("PyInstaller is not installed. Run: python -m pip install -r requirements-build.txt")
        return 1

    mac = sys.platform == "darwin"
    dist = ROOT / "dist"
    version = read_version()
    options = [
        str(ROOT / "sharepoint-navigator.py"),
        "--name", NAME,
        "--windowed",      # no console window; setup and sign-in happen in the browser
        "--icon", str(ROOT / "assets" / ("icon.icns" if mac else "icon.ico")),
        "--add-data", f"{ROOT / 'sharepoint-navigator.html'}{os.pathsep}.",
        "--distpath", str(dist),
        "--noconfirm", "--clean", "--log-level", "WARN",
    ]
    # macOS: a normal .app folder (one-file .app bundles are discouraged by PyInstaller).
    # Windows: one .exe, simplest to hand around.
    options += ["--osx-bundle-identifier", BUNDLE_ID] if mac else ["--onefile"]

    # Keep PyInstaller's scratch files out of the project folder (it may be cloud-synced).
    work = Path(tempfile.mkdtemp(prefix="spnav-build-"))
    try:
        pyinstaller.run(options + ["--workpath", str(work / "build"), "--specpath", str(work)])
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if mac:
        app = dist / f"{NAME}.app"
        exe = app / "Contents" / "MacOS" / NAME
        # PyInstaller also leaves a plain folder build next to the .app; only the .app is shipped.
        shutil.rmtree(dist / NAME, ignore_errors=True)
        if exe.is_file():
            finish_mac_app(app, version)
        built = app
    else:
        exe = built = dist / f"{NAME}.exe"
    if not exe.is_file():
        print("Build failed: the app was not created.")
        return 1
    # A windowless app prints nothing; the exit code tells whether it can start.
    check = subprocess.run([str(exe), "--self-check"], check=False)
    if check.returncode != 0:
        print("Build finished, but the app's self-check failed (see ~/.sharepoint-navigator/app.log).")
        return 1
    print(f"\nBuilt {built} (version {version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
