#!/usr/bin/env python3
"""Take the product page's screenshots from the demo (tools/demo.py) with headless Chrome.

    python tools/shots.py

Writes site/shots/{tree,search,menu}{,-ko}{,-dark}.png at 2x. Needs Google Chrome; set CHROME to
use another Chromium-based browser. Only made-up data appears (see tools/demo.py).

The tree and search shots use Chrome's one-shot --screenshot. The menu shots can't: in that mode
Chrome leaves the open row menu out of the picture. They drive Chrome over its DevTools pipe
instead (standard library only), which also crops them around the row and its menu.
"""
from __future__ import annotations

import base64
import fcntl
import json
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
# The open "⋯" menu on a file row, for the page's "where the tools are" section (cropped; see menu_shot).
MENU_SHOTS = [
    ("menu", "shot=menu&lang=en&theme=light"),
    ("menu-ko", "shot=menu&lang=ko&theme=light"),
    ("menu-dark", "shot=menu&lang=en&theme=dark"),
    ("menu-ko-dark", "shot=menu&lang=ko&theme=dark"),
]
MENU_WINDOW = (1000, 1040)


class DevTools:
    """Chrome started with --remote-debugging-pipe: JSON commands in on fd 3, answers out on fd 4,
    each message ending in a NUL byte. Enough of the protocol for one page and a screenshot."""

    def __init__(self, profile: str):
        to_chrome_r, self.to_chrome = os.pipe()
        self.from_chrome, from_chrome_w = os.pipe()

        def fds():
            # Chrome expects the pipe on exactly fds 3 and 4. Copy both ends above 10 first, so
            # putting one on 3 can't overwrite the other if it happens to be there already.
            read_end = fcntl.fcntl(to_chrome_r, fcntl.F_DUPFD, 10)
            write_end = fcntl.fcntl(from_chrome_w, fcntl.F_DUPFD, 10)
            os.dup2(read_end, 3)
            os.dup2(write_end, 4)

        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
             f"--user-data-dir={profile}", "--remote-debugging-pipe", "about:blank"],
            # Python closes other fds after fds() runs, so 3 and 4 must be on the keep list.
            pass_fds=(3, 4, to_chrome_r, from_chrome_w), preexec_fn=fds,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(to_chrome_r)
        os.close(from_chrome_w)
        self.buffer = b""
        self.next_id = 0
        self.session = None

    def send(self, method: str, params: dict | None = None):
        """Send one command (to the attached page once there is one) and return its result."""
        self.next_id += 1
        message = {"id": self.next_id, "method": method, "params": params or {}}
        if self.session:
            message["sessionId"] = self.session
        os.write(self.to_chrome, json.dumps(message).encode() + b"\0")
        while True:
            # Events arrive in between; skip everything but the answer to this command.
            while b"\0" not in self.buffer:
                chunk = os.read(self.from_chrome, 1 << 20)
                if not chunk:
                    raise RuntimeError("Chrome closed the DevTools pipe.")
                self.buffer += chunk
            raw, self.buffer = self.buffer.split(b"\0", 1)
            answer = json.loads(raw)
            if answer.get("id") == self.next_id:
                if "error" in answer:
                    raise RuntimeError(f"{method}: {answer['error']}")
                return answer.get("result", {})

    def evaluate(self, expression: str):
        return self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})["result"].get("value")

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)
        os.close(self.to_chrome)
        os.close(self.from_chrome)


def menu_shot(url: str, target: Path):
    """Open the demo with a row menu showing and save a 2x picture cropped around the row and menu."""
    with tempfile.TemporaryDirectory() as profile:
        chrome = DevTools(profile)
        try:
            page = chrome.send("Target.createTarget", {"url": "about:blank"})["targetId"]
            chrome.session = chrome.send("Target.attachToTarget", {"targetId": page, "flatten": True})["sessionId"]
            width, height = MENU_WINDOW
            # Size first, so the page never sees a resize (resizing closes the menu).
            chrome.send("Emulation.setDeviceMetricsOverride",
                        {"width": width, "height": height, "deviceScaleFactor": 2, "mobile": False})
            chrome.send("Page.navigate", {"url": url})
            for _ in range(300):
                if chrome.evaluate("document.body && document.body.dataset.demoReady"):
                    break
                time.sleep(0.1)
            box = chrome.evaluate("""(() => {
              const menu = document.querySelector('.row-menu:not([hidden])');
              const row = document.querySelector('.row-menu-button[aria-expanded="true"]');
              if (!menu || !row) return null;
              const a = menu.getBoundingClientRect(), b = row.closest('summary').getBoundingClientRect();
              return { top: Math.min(a.top, b.top), bottom: Math.max(a.bottom, b.bottom) };
            })()""")
            if not box:
                raise RuntimeError(f"The row menu didn't open for {url}")
            # Some rows above for context, a margin below; the full width, so names and sizes show.
            top = max(0, box["top"] - 230)
            bottom = min(height, box["bottom"] + 30)
            shot = chrome.send("Page.captureScreenshot", {"format": "png", "clip": {
                "x": 0, "y": top, "width": width, "height": bottom - top, "scale": 1}})
            target.write_bytes(base64.b64decode(shot["data"]))
        finally:
            chrome.close()


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
        for name, fragment in MENU_SHOTS:
            target = OUT / f"{name}.png"
            menu_shot(f"http://127.0.0.1:{port}/#{fragment}", target)
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
