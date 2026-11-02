#!/usr/bin/env python3
"""Take the product page's screenshots from the demo (tools/demo.py) with headless Chrome.

    python tools/shots.py

Writes site/shots/{tree,search}{,-ko}{,-dark}.png at 2x. Needs Google Chrome; set CHROME to
use another Chromium-based browser. Only made-up data appears (see tools/demo.py).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "shots"
CHROME = os.environ.get("CHROME") or next(
    (p for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 shutil.which("google-chrome") or "", shutil.which("chromium") or "") if p and Path(p).exists()), "")
# (file name, page fragment, window width, height)
SHOTS = [
    ("tree", "shot=tree&lang=en&theme=light", 1280, 900),
    ("tree-ko", "shot=tree&lang=ko&theme=light", 1280, 900),
    ("tree-dark", "shot=tree&lang=en&theme=dark", 1280, 900),
    ("tree-ko-dark", "shot=tree&lang=ko&theme=dark", 1280, 900),
    ("search", "shot=search&lang=en&theme=light", 1280, 820),
    ("search-ko", "shot=search&lang=ko&theme=light", 1280, 820),
    ("search-dark", "shot=search&lang=en&theme=dark", 1280, 820),
    ("search-ko-dark", "shot=search&lang=ko&theme=dark", 1280, 820),
]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main() -> int:
    if not CHROME:
        print("Google Chrome was not found; set CHROME to a Chromium-based browser.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    demo = subprocess.Popen([sys.executable, str(ROOT / "tools" / "demo.py"), str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        for name, fragment, width, height in SHOTS:
            # A fresh profile each time, so no language or theme is remembered between shots.
            with tempfile.TemporaryDirectory() as profile:
                target = OUT / f"{name}.png"
                subprocess.run([
                    CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                    f"--user-data-dir={profile}", f"--window-size={width},{height}", "--force-device-scale-factor=2",
                    "--virtual-time-budget=30000", f"--screenshot={target}",
                    f"http://127.0.0.1:{port}/#{fragment}",
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
                print(f"{target.relative_to(ROOT)}  {target.stat().st_size // 1024} KB")
    finally:
        # Ask the demo to stop, then make sure it has.
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/stop", data=b"{}", method="POST"), timeout=2)
        except OSError:
            pass
        demo.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
