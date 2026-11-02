#!/usr/bin/env python3
"""Make the app icons from assets/icon.svg: assets/icon.icns (macOS) and assets/icon.ico (Windows).

    python tools/make_icons.py          # needs Google Chrome (to draw the SVG) and Pillow

macOS icons sit inside a 1024 px canvas with a margin (824 px shape), like Apple's own; Windows
icons fill the square. The results are committed, so builds don't need Chrome or Pillow.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "icon.svg"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def render(size: int, shape: int, out: Path) -> Image.Image:
    """Draw the SVG at `shape` px, centred on a transparent `size` px square."""
    html = out.with_suffix(".html")
    margin = (size - shape) // 2
    html.write_text(f'<html><body style="margin:0;background:transparent">'
                    f'<img src="{SVG.as_uri()}" width="{shape}" height="{shape}" '
                    f'style="display:block;margin:{margin}px"></body></html>', encoding="utf-8")
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                        f"--user-data-dir={profile}", f"--window-size={size},{size}", "--default-background-color=00000000",
                        f"--screenshot={out}", html.as_uri()], check=True, capture_output=True, timeout=60)
    return Image.open(out).convert("RGBA")


def main() -> int:
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        # macOS: an .iconset folder of 10 PNGs, packed by Apple's iconutil.
        mac = render(1024, 824, work / "mac.png")
        iconset = work / "icon.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{base}x{base}{'@2x' if scale == 2 else ''}.png"
                mac.resize((base * scale,) * 2, Image.LANCZOS).save(iconset / name)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ROOT / "assets" / "icon.icns")], check=True)
        # Windows: one .ico holding every size Explorer and the taskbar ask for.
        win = render(1024, 1024, work / "win.png")
        win.save(ROOT / "assets" / "icon.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
        # A 512 px PNG for the product page and anything else that wants a bitmap.
        win.resize((512, 512), Image.LANCZOS).save(ROOT / "site" / "icon.png")
    for name in ("icon.icns", "icon.ico"):
        print(f"assets/{name}  {(ROOT / 'assets' / name).stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
