#!/usr/bin/env python3
"""Build a one-file SharePoint Navigator executable for the current OS.

Run on each OS you want a build for (PyInstaller does not cross-compile):

    python -m pip install -r requirements-build.txt
    python build_app.py

Output: dist/sharepoint-navigator (macOS) or dist\\sharepoint-navigator.exe (Windows).
Put <tenant>_clientid.txt in the same folder as the executable before running it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "sharepoint-navigator"


def main() -> int:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("PyInstaller is not installed. Run: python -m pip install -r requirements-build.txt")
        return 1

    dist = ROOT / "dist"
    # Keep PyInstaller's scratch files out of the project folder (it may be cloud-synced).
    work = Path(tempfile.mkdtemp(prefix="spnav-build-"))
    try:
        pyinstaller.run([
            str(ROOT / "sharepoint-navigator.py"),
            "--onefile",
            "--console",
            "--name", NAME,
            "--add-data", f"{ROOT / 'sharepoint-navigator.html'}{os.pathsep}.",
            "--distpath", str(dist),
            "--workpath", str(work / "build"),
            "--specpath", str(work),
            "--noconfirm",
            "--clean",
            "--log-level", "WARN",
        ])
    finally:
        shutil.rmtree(work, ignore_errors=True)

    exe = dist / (NAME + (".exe" if os.name == "nt" else ""))
    if not exe.is_file():
        print("Build failed: the executable was not created.")
        return 1
    check = subprocess.run([str(exe), "--self-check"], check=False)
    if check.returncode != 0:
        print("Build finished, but the executable's self-check failed.")
        return 1
    print(f"\nBuilt {exe}")
    print("Next: put <tenant>_clientid.txt beside it, then run it from a terminal or by double-clicking.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
