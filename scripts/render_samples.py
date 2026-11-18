"""Render sample terminal output for the README screenshots.

Unlike scripts/make_screenshot.py (which runs the real command and would leak
the author's own IP addresses), this renders *fixed* sample text using
documentation-range addresses. Safe to commit.

Usage:
    python scripts/render_samples.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"

BG = (24, 24, 27)
FG = (205, 214, 244)
PALETTE = {
    "31": (243, 139, 168),
    "32": (166, 227, 161),
    "33": (249, 226, 175),
    "34": (137, 180, 250),
    "35": (203, 166, 247),
    "36": (137, 220, 235),
    "90": (108, 112, 134),
}
FONT_SIZE = 15
PAD = 22
LINE_HEIGHT = 21


def load_font(size: int):
    from PIL import ImageFont

    for path in (
        r"C:\Windows\Fonts\consola.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def ansi_runs(line: str):
    runs, colour, bold, dim = [], FG, False, False
    for part in re.split(r"(\x1b\[[0-9;]*m)", line):
        if not part:
            continue
        if part.startswith("\x1b["):
            for code in part[2:-1].split(";"):
                if code == "0" or code == "":
                    colour, bold, dim = FG, False, False
                elif code == "1":
                    bold = True
                elif code == "2":
                    dim = True
                elif code in PALETTE:
                    colour = PALETTE[code]
            continue
        runs.append((part, colour, bold, dim))
    return runs


def render(lines: list, prompt: str, output: Path) -> None:
    from PIL import Image, ImageDraw

    font = load_font(FONT_SIZE)
    visible = [re.sub(r"\x1b\[[0-9;]*m", "", ln) for ln in lines]
    char_w = font.getbbox("M")[2] - font.getbbox("M")[0]
    width = max(max(len(v) for v in visible), len(prompt) + 2) * char_w
    height = (len(lines) + 1) * LINE_HEIGHT + 6

    img = Image.new("RGB", (int(width) + PAD * 2, height + PAD * 2), BG)
    draw = ImageDraw.Draw(img)

    draw.text((PAD, PAD), "$", font=font, fill=PALETTE["32"])
    draw.text((PAD + char_w * 2, PAD), prompt, font=font, fill=FG)

    y = PAD + LINE_HEIGHT + 6
    for line in lines:
        x = PAD
        for chunk, colour, bold, dim in ansi_runs(line):
            shown = tuple(int(c * 0.55) for c in colour) if dim else colour
            draw.text((x, y), chunk, font=font, fill=shown)
            x += len(chunk) * char_w
        y += LINE_HEIGHT

    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output)
    print(f"wrote {output.relative_to(ROOT)} ({img.width}x{img.height})")


# --------------------------------------------------------------------------- #
# Sample content (documentation ranges only)
# --------------------------------------------------------------------------- #

C = {
    "hdr": "\x1b[1m\x1b[36m",
    "lbl": "\x1b[90m",
    "info": "\x1b[1m\x1b[36m",
    "strong": "\x1b[1m",
    "ok": "\x1b[1m\x1b[32m",
    "warn": "\x1b[1m\x1b[33m",
    "dim": "\x1b[2m",
    "off": "\x1b[0m",
}


def hdr(title: str) -> str:
    return f"\n{C['hdr']}── {title} {'─' * (52 - len(title))}{C['off']}"


def row(label: str, value: str, width: int, style: str = "") -> str:
    pad = f"{label:<{width}}"
    tint = C.get(style, "")
    return f"  {C['lbl']}{pad}{C['off']}: {tint}{value}{C['off']}"


def sample_me() -> list:
    return [
        hdr("THIS DEVICE"),
        row("hostname", "my-laptop", 12, "info"),
        row("workgroup", "WORKGROUP", 12),
        hdr("IP ADDRESSES"),
        row("Wi-Fi", "192.168.0.42  (IPv4)", 26, "info"),
        row("Ethernet", "10.0.0.15  (IPv4)", 26, "info"),
        row("public", "203.0.113.7  (AS64500 Example ISP, XX)", 26, "strong"),
        row("subnet", "192.168.0.0/24, 10.0.0.0/24", 26),
        hdr("MAC ADDRESSES"),
        row("Wi-Fi", "A4:5E:60:12:34:56  (Apple, Inc.)", 26, "info"),
        hdr("GATEWAY & DNS"),
        row("gateway", "192.168.0.1", 12, "info"),
        row("dns", "192.168.0.1, 8.8.8.8", 12),
        hdr("LISTENING PORTS (THIS DEVICE)"),
        (
            "  \x1b[1m445  \x1b[0m SMB            System                0.0.0.0"
            f"            {C['warn']}⚠ SMB file sharing{C['off']}"
        ),
        (
            "  \x1b[1m5000 \x1b[0m                python                127.0.0.1"
            f"          {C['dim']}(localhost only){C['off']}"
        ),
        hdr("WI-FI"),
        row("ssid", "HomeNet", 10),
        row("channel", "36", 10),
        row("security", "WPA2-Personal", 10),
        row("signal", "84%", 10, "ok"),
    ]


def sample_scan() -> list:
    head = f"  {'IP':<15} {'MAC':<19}  {'VENDOR':<26} {'HOSTNAME'}"
    rule = f"  {'─' * 15} {'─' * 19}  {'─' * 26} {'─' * 12}"
    return [
        hdr("DEVICES IN YOUR NETWORK"),
        "",
        f"\x1b[1m{head}\x1b[0m",
        rule,
        f"  {C['info']}192.168.0.1    {C['off']} 50:FF:20:76:59:50  Router vendor",
        f"  {C['info']}192.168.0.45   {C['off']} A4:5E:60:12:34:56  Apple, Inc.          my-iphone",
        f"  {C['info']}192.168.0.103  {C['off']} AA:42:7A:83:0D:F6  Private / randomized MAC",
        "",
        "  3 device(s) found",
    ]


def sample_whois() -> list:
    return [
        hdr("WHOIS — EXAMPLE.COM"),
        row("type", "domain", 13),
        row("registrar", "RESERVED-Internet Assigned Numbers Authority", 13),
        row("registered", "1995-08-14T04:00:00Z", 13),
        row("expires", "2027-08-13T04:00:00Z   (265 days left)", 13, "ok"),
        row("last changed", "2026-08-14T07:01:34Z", 13),
        row("handle", "2336799_DOMAIN_COM-VRSN", 13),
        row("domain", "EXAMPLE.COM", 13, "info"),
        hdr("STATUS"),
        f"  {C['warn']}•{C['off']} client delete prohibited",
        f"  {C['warn']}•{C['off']} client transfer prohibited",
        f"  {C['warn']}•{C['off']} client update prohibited",
    ]


def sample_audit() -> list:
    return [
        hdr("HOST AUDIT"),
        row("firewall", "Windows Defender Firewall", 12),
        row("last_update", "KB5039212", 12),
        hdr("FINDINGS"),
        f"  {C['warn']}MEDIUM{C['off']}            Port 139 (NetBIOS) is listening on 192.168.0.42",
        f"  {C['dim']}                   NetBIOS. Allow it only from localhost.{C['off']}",
        f"  {C['warn']}HIGH{C['off']}              Port 445 (SMB) is listening on 0.0.0.0",
        f"  {C['dim']}                   SMB file sharing. Restrict it to trusted hosts.{C['off']}",
        "",
        f"  score: {C['ok']}72/100{C['off']}",
    ]


SAMPLES = {
    "netpeek-me.png": ("netpeek me", sample_me),
    "netpeek-scan.png": ("netpeek scan", sample_scan),
    "netpeek-whois.png": ("netpeek whois example.com", sample_whois),
    "netpeek-audit.png": ("netpeek audit", sample_audit),
}


if __name__ == "__main__":
    for name, (prompt, maker) in SAMPLES.items():
        render(maker(), prompt, OUT / name)
