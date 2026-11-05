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

macOS signing (docs/SIGNING.md): with APPLE_SIGNING_IDENTITY set to a "Developer ID Application: …"
certificate in the keychain, every binary and the .app are signed with it (hardened runtime,
secure timestamp). With APPLE_ID, APPLE_PASSWORD (app-specific) and APPLE_TEAM_ID also set, the
.app is sent to Apple's notary service and the ticket is stapled to it. Without them the build is
signed ad hoc, as before. Windows is not signed (owner's decision).
"""

from __future__ import annotations

import json
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


def sign_identity() -> str:
    """The Developer ID to sign with on macOS, or "" for an ad hoc signature."""
    return os.environ.get("APPLE_SIGNING_IDENTITY", "").strip() if sys.platform == "darwin" else ""


def finish_mac_app(app: Path, version: str, identity: str) -> None:
    """Make the .app a background app (no Dock window) with the right version, then re-seal it.

    PyInstaller has already signed every bundled binary (with the Developer ID when one is given).
    Editing Info.plist breaks only the outer seal, so only the bundle itself is signed again; the
    inner signatures stay valid. Apple silicon refuses to run unsigned code, so even the ad hoc
    build is re-sealed. Only the Developer ID build opens on other Macs without a warning.
    """
    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    info.update({
        # Background app: the page in the browser is the window; closing its tab stops the app.
        "LSUIElement": True,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "NSHumanReadableCopyright": "MIT licence · yusungchang.com/sharepoint-navigator",  # Finder's Get Info
    })
    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle)
    if identity:
        # Notarization needs the hardened runtime and a secure timestamp on the outer seal too.
        subprocess.run(["codesign", "--force", "--options", "runtime", "--timestamp",
                        "--sign", identity, str(app)], check=True)
        # Fails the build if any part of the bundle is unsigned or signed by someone else.
        subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)], check=True)
    else:
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)


def notarize_mac_app(app: Path) -> bool:
    """Send the signed .app to Apple's notary service and staple the ticket; False on failure.

    Skipped (True) when the Apple ID credentials are not set. The ticket stapled to the .app lets
    Gatekeeper accept it even offline; the zip made afterwards carries it along.
    """
    creds = {k: os.environ.get(k, "").strip() for k in ("APPLE_ID", "APPLE_PASSWORD", "APPLE_TEAM_ID")}
    if not all(creds.values()):
        print("No APPLE_ID / APPLE_PASSWORD / APPLE_TEAM_ID: signed, not notarized.")
        return True
    work = Path(tempfile.mkdtemp(prefix="spnav-notarize-"))
    try:
        # The notary service takes a zip, dmg or pkg, not a bare .app; ditto keeps the bundle intact.
        upload = work / "upload.zip"
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(app), str(upload)], check=True)
        print("Notarizing with Apple (usually a few minutes)...")
        # The password goes in an environment variable, not the command line (process list).
        result = subprocess.run(
            ["xcrun", "notarytool", "submit", str(upload), "--wait",
             "--apple-id", creds["APPLE_ID"], "--team-id", creds["APPLE_TEAM_ID"],
             "--password", "@env:SPNAV_NOTARY_PASSWORD", "--output-format", "json"],
            env={**os.environ, "SPNAV_NOTARY_PASSWORD": creds["APPLE_PASSWORD"]},
            capture_output=True, text=True, check=False,
        )
        print(result.stdout.strip() or result.stderr.strip())
        try:
            status = json.loads(result.stdout).get("status")
        except ValueError:
            status = None
        if status != "Accepted":
            # Apple's log names each file it rejected and why.
            print("Notarization was not accepted. Details: xcrun notarytool log <id> ...")
            return False
        subprocess.run(["xcrun", "stapler", "staple", str(app)], check=True)
        subprocess.run(["xcrun", "stapler", "validate", str(app)], check=True)
        return True
    finally:
        shutil.rmtree(work, ignore_errors=True)


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
    identity = sign_identity()
    if identity:
        # PyInstaller then signs each bundled library and the bootloader with it, using the
        # hardened runtime and a secure timestamp, as notarization requires.
        options += ["--codesign-identity", identity]

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
            finish_mac_app(app, version, identity)
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
    # Notarize only after the self-check: running the app does not change the bundle.
    if mac and identity and not notarize_mac_app(built):
        return 1
    print(f"\nBuilt {built} (version {version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
