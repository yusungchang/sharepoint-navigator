#!/usr/bin/env python3
"""Build SharePoint Navigator for the current OS: a windowless app with its icon.

Run on each OS you want a build for (PyInstaller does not cross-compile):

    python -m pip install -r requirements-build.txt
    python build_app.py

Output (what gets released is in dist/release/, under the fixed names the product page links to):
  macOS:   dist/SharePoint Navigator.app  (a background app: no Dock window, the browser is its window)
           dist/release/SharePoint-Navigator-macOS-AppleSilicon.dmg  (or -Intel on an Intel Mac): the
           app with a link to Applications, to drag across
  Windows: dist/SharePoint Navigator.exe  (one file, no console window)
           dist/release/SharePoint-Navigator-Windows-Setup.exe  (per-user installer, Inno Setup 6;
           skipped with a message when ISCC.exe is not installed)
           dist/release/SharePoint-Navigator-Windows.zip  (the bare .exe, for running without installing)
Without a terminal, the app shows setup and sign-in in the browser and writes messages to
~/.sharepoint-navigator/app.log. A <tenant>_clientid.txt next to the .app or .exe is still honoured.

macOS signing (docs/SIGNING.md): with APPLE_SIGNING_IDENTITY set to a "Developer ID Application: …"
certificate in the keychain, every binary and the .app are signed with it (hardened runtime,
secure timestamp). With APPLE_ID, APPLE_PASSWORD (app-specific) and APPLE_TEAM_ID also set, the
.app and then the .dmg are sent to Apple's notary service and the tickets are stapled to them.
Without them the build is signed ad hoc, as before. Windows is not signed (owner's decision).
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "SharePoint Navigator"
BUNDLE_ID = "com.yusungchang.sharepoint-navigator"
# Fixed names of the released files: the product page links to releases/latest/download/<name>.
FILE_STEM = "SharePoint-Navigator"


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


def notarize(upload: Path, staple: Path) -> bool:
    """Send a zip or dmg to Apple's notary service, then staple the ticket to `staple`.

    False when Apple does not accept it. Skipped (True) when the Apple ID credentials are not set.
    A stapled ticket lets Gatekeeper accept the file even offline.
    """
    creds = {k: os.environ.get(k, "").strip() for k in ("APPLE_ID", "APPLE_PASSWORD", "APPLE_TEAM_ID")}
    if not all(creds.values()):
        print("No APPLE_ID / APPLE_PASSWORD / APPLE_TEAM_ID: signed, not notarized.")
        return True
    print(f"Notarizing {staple.name} with Apple (usually a few minutes)...")
    # notarytool takes the password only as an argument (altool's "@env:" form is not
    # supported). It is an app-specific password, and CI masks it in the log.
    result = subprocess.run(
        ["xcrun", "notarytool", "submit", str(upload), "--wait",
         "--apple-id", creds["APPLE_ID"], "--team-id", creds["APPLE_TEAM_ID"],
         "--password", creds["APPLE_PASSWORD"], "--output-format", "json"],
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
    subprocess.run(["xcrun", "stapler", "staple", str(staple)], check=True)
    subprocess.run(["xcrun", "stapler", "validate", str(staple)], check=True)
    return True


def notarize_mac_app(app: Path) -> bool:
    """Notarize the signed .app and staple its ticket, before it goes into the dmg.

    The notary service takes a zip, dmg or pkg, not a bare .app; ditto keeps the bundle intact.
    """
    work = Path(tempfile.mkdtemp(prefix="spnav-notarize-"))
    try:
        upload = work / "upload.zip"
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(app), str(upload)], check=True)
        return notarize(upload, app)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# Finder layout of the dmg window, as PDF Epsilon's (Tauri's defaults): 660 x 400 points, the app
# on the left and the Applications link on the right, 128-point icons.
DMG_LAYOUT = """
tell application "Finder"
  tell disk "{volume}"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {{200, 120, 860, 520}}
    set opts to the icon view options of container window
    set arrangement of opts to not arranged
    set icon size of opts to 128
    set text size of opts to 13
    set position of item "{app}" of container window to {{180, 170}}
    set position of item "Applications" of container window to {{480, 170}}
    update without registering applications
    delay 1
    close
  end tell
end tell
"""


def make_dmg(app: Path, target: Path, identity: str) -> bool:
    """Put the .app and a link to Applications into a compressed dmg; sign and notarize it.

    The window layout is set through Finder. When Finder can't be scripted (no permission, no
    session), the dmg still works, just with Finder's default layout, so that only warns.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    work = Path(tempfile.mkdtemp(prefix="spnav-dmg-"))
    try:
        stage = work / "stage"
        stage.mkdir()
        # ditto keeps the bundle's links, signature and stapled ticket.
        subprocess.run(["ditto", str(app), str(stage / app.name)], check=True)
        (stage / "Applications").symlink_to("/Applications")
        # A writable image first, so Finder can store the layout in it; compressed afterwards.
        rw = work / "rw.dmg"
        subprocess.run(["hdiutil", "create", "-quiet", "-srcfolder", str(stage), "-volname", NAME,
                        "-fs", "HFS+", "-format", "UDRW", "-ov", str(rw)], check=True)
        # Mounted under /Volumes as usual, since Finder only scripts disks it lists. The name may
        # get a number ("… 1") if a volume of that name is already open, so read it back.
        attached = subprocess.run(["hdiutil", "attach", "-readwrite", "-noverify", "-noautoopen",
                                   "-plist", str(rw)], capture_output=True, check=True)
        mount = next(Path(e["mount-point"]) for e in plistlib.loads(attached.stdout)["system-entities"]
                     if e.get("mount-point"))
        try:
            script = DMG_LAYOUT.format(volume=mount.name, app=app.name)
            try:
                laid_out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                                          timeout=120, check=False)
                if laid_out.returncode != 0:
                    print(f"Warning: dmg window layout not set ({laid_out.stderr.strip()}).")
            except subprocess.TimeoutExpired:
                print("Warning: dmg window layout timed out (Finder did not answer).")
            # macOS's file-event log on the volume is of no use to anyone opening the dmg.
            shutil.rmtree(mount / ".fseventsd", ignore_errors=True)
            subprocess.run(["sync"], check=False)
        finally:
            subprocess.run(["hdiutil", "detach", "-quiet", str(mount)], check=False)
        subprocess.run(["hdiutil", "convert", "-quiet", str(rw), "-format", "UDZO",
                        "-imagekey", "zlib-level=9", "-o", str(target)], check=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not identity:
        return True
    # A signed and notarized dmg passes Gatekeeper's check when it is opened, before the app is.
    subprocess.run(["codesign", "--force", "--timestamp", "--sign", identity, str(target)], check=True)
    return notarize(target, target)


def find_iscc() -> str:
    """Path of Inno Setup 6's compiler (ISCC.exe), or "" when it isn't installed."""
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA") and os.path.join(os.environ["LOCALAPPDATA"], "Programs")):
        candidate = Path(base or "") / "Inno Setup 6" / "ISCC.exe"
        if base and candidate.is_file():
            return str(candidate)
    return ""


def make_windows_release(exe: Path, release: Path, version: str) -> bool:
    """The installer (installer/windows.iss) and a zip of the bare .exe, in `release`."""
    release.mkdir(parents=True, exist_ok=True)
    # The portable zip: the .exe alone, for people who'd rather not install (or who put a
    # <tenant>_clientid.txt next to it).
    portable = release / f"{FILE_STEM}-Windows.zip"
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(exe, exe.name)
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup 6 (ISCC.exe) not found: no installer made. Install it from jrsoftware.org.")
        # Only a release build must have the installer; CI installs Inno Setup first.
        return not os.environ.get("CI")
    result = subprocess.run([
        iscc, "/Q",
        f"/DAppVersion={version}",
        f"/DSourceExe={exe}",
        f"/DIconFile={ROOT / 'assets' / 'icon.ico'}",
        f"/DOutputDir={release}",
        f"/DOutputName={FILE_STEM}-Windows-Setup",
        str(ROOT / "installer" / "windows.iss"),
    ], check=False)
    return result.returncode == 0


def main() -> int:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        print("PyInstaller is not installed. Run: python -m pip install -r requirements-build.txt")
        return 1

    mac = sys.platform == "darwin"
    dist = ROOT / "dist"
    release = dist / "release"
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
    # Windows: one .exe, which the installer copies into place.
    options += ["--osx-bundle-identifier", BUNDLE_ID] if mac else ["--onefile"]
    identity = sign_identity()
    if identity:
        # PyInstaller then signs each bundled library and the bootloader with it, using the
        # hardened runtime and a secure timestamp, as notarization requires.
        options += ["--codesign-identity", identity]

    # Start from an empty release folder, so only this build's files are shipped.
    shutil.rmtree(release, ignore_errors=True)
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
    else:
        exe = dist / f"{NAME}.exe"
    if not exe.is_file():
        print("Build failed: the app was not created.")
        return 1
    # A windowless app prints nothing; the exit code tells whether it can start.
    check = subprocess.run([str(exe), "--self-check"], check=False)
    if check.returncode != 0:
        print("Build finished, but the app's self-check failed (see ~/.sharepoint-navigator/app.log).")
        return 1

    if mac:
        # Notarize only after the self-check: running the app does not change the bundle.
        if identity and not notarize_mac_app(app):
            return 1
        chip = "AppleSilicon" if platform.machine() == "arm64" else "Intel"
        if not make_dmg(app, release / f"{FILE_STEM}-macOS-{chip}.dmg", identity):
            return 1
    elif not make_windows_release(exe, release, version):
        print("The Windows installer could not be made.")
        return 1
    print(f"\nBuilt version {version}:")
    for item in sorted(release.glob("*")):
        print(f"  {item.relative_to(ROOT)}  ({item.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
