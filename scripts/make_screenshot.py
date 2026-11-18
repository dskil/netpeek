"""Render NetPeek's coloured terminal output into a PNG screenshot.

Usage:
    python scripts/make_screenshot.py "netpeek me --ip" docs/screenshots/me.png

Needs Pillow (a dev-only dependency, never required at runtime).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Dark terminal palette that matches the screenshots in the README.
BG = (24, 24, 27)
FG = (205, 214, 244)
PALETTE = {
    "31": (243, 139, 168),   # red
    "32": (166, 227, 161),   # green
    "33": (249, 226, 175),   # yellow
    "34": (137, 180, 250),   # blue
    "35": (203, 166, 247),   # magenta
    "36": (137, 220, 235),   # cyan
    "90": (108, 112, 134),   # grey
}
BOLD = "1"
DIM = "2"
RESET = "0"

FONT_SIZE = 15
PAD = 22
LINE_HEIGHT = 21


def load_font(size: int):
    from PIL import ImageFont

    candidates = [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\CascadiaMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def ansi_to_runs(line: str):
    """Split an ANSI-coloured line into [(text, colour, bold, dim), ...]."""
    runs = []
    colour = FG
    bold = False
    dim = False
    for part in re.split(r"(\x1b\[[0-9;]*m)", line):
        if not part:
            continue
        if part.startswith("\x1b["):
            codes = part[2:-1].split(";")
            for code in codes:
                if code == RESET or code == "":
                    colour, bold, dim = FG, False, False
                elif code == BOLD:
                    bold = True
                elif code == DIM:
                    dim = True
                elif code in PALETTE:
                    colour = PALETTE[code]
            continue
        runs.append((part, colour, bold, dim))
    return runs


def render(command: str, output: Path, title: str = "") -> None:
    from PIL import Image, ImageDraw

    env = dict(os.environ, FORCE_COLOR="1", PYTHONUTF8="1")
    proc = subprocess.run(
        command,
        shell=True,
        cwd=str(ROOT),
        capture_output=True,
        env=env,
        timeout=240,
    )
    raw = (proc.stdout or b"").decode("utf-8", "replace")
    text = raw.rstrip("\n")
    if not text.strip():
        raise SystemExit(f"command produced no output: {command}")

    font = load_font(FONT_SIZE)
    lines = text.split("\n")
    # First line is the shell prompt, shown brighter than the output.
    prompt = title or command
    lines = [f"$ {prompt}"] + lines

    char_w = font.getbbox("M")[2] - font.getbbox("M")[0]
    visible = [re.sub(r"\x1b\[[0-9;]*m", "", ln) for ln in lines]
    width = max(len(ln) for ln in visible) * char_w
    height = len(lines) * LINE_HEIGHT

    bg_inner = BG
    img = Image.new("RGB", (int(width) + PAD * 2, height + PAD * 2), bg_inner)
    draw = ImageDraw.Draw(img)

    y = PAD
    for index, line in enumerate(lines):
        x = PAD
        if index == 0:
            # Prompt line: green "$" + light text.
            draw.text((x, y), "$", font=font, fill=PALETTE["32"])
            draw.text((x + char_w * 2, y), prompt, font=font, fill=FG)
            y += LINE_HEIGHT + 4
            continue
        for chunk, colour, bold, dim in ansi_to_runs(line):
            shown = colour
            if dim:
                shown = tuple(int(c * 0.55) for c in colour)
            draw.text((x, y), chunk, font=font, fill=shown)
            x += len(chunk) * char_w
        y += LINE_HEIGHT

    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output)
    print(f"wrote {output} ({img.width}x{img.height})")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    render(sys.argv[1], Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "")
