"""Small helpers shared by every NetPeek command."""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Iterable, List, Optional, Sequence

# --------------------------------------------------------------------------- #
# Colour / terminal output
# --------------------------------------------------------------------------- #

_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
    "white": "\033[97m",
}

_COLOR_ENABLED = True


def configure(no_color: bool = False) -> None:
    """Turn colour off when asked, or when stdout is not a terminal."""
    global _COLOR_ENABLED
    _COLOR_ENABLED = not no_color and sys.stdout.isatty()


def supports_color() -> bool:
    return _COLOR_ENABLED


def style(text: str, *names: str) -> str:
    """Wrap *text* in ANSI styles (silently skipped when colour is off)."""
    if not _COLOR_ENABLED or not names:
        return text
    prefix = "".join(_COLORS.get(n, "") for n in names)
    return f"{prefix}{text}{_COLORS['reset']}"


# Terminal styling for values, keyed by meaning rather than by colour name.
_STYLE_VALUE = {
    "plain": (),
    "strong": ("bold",),
    "ok": ("bold", "green"),
    "warn": ("bold", "yellow"),
    "bad": ("bold", "red"),
    "info": ("bold", "cyan"),
    "muted": ("dim",),
}

#: Human-readable names for API-style keys (whois, TLS, JSON fields).
_LABEL_NAMES = {
    "ldhname": "domain",
    "handle": "handle",
    "registrar": "registrar",
    "registrant": "registrant",
    "registration": "registered",
    "expiration": "expires",
    "last_changed": "last changed",
    "startaddress": "ip range",
    "ip_version": "ip version",
    "status": "status",
    "country": "country",
    "name": "name",
    "objectclassname": "type",
    "not_after": "expires",
    "days_left": "days left",
    "san": "SAN",
    "subject": "subject",
    "issuer": "issuer",
}


def prettify_label(key: str) -> str:
    """Turn ``last_changed`` into ``last changed``, ``ldhName`` into ``domain``."""
    plain = key.replace("_", " ").replace("-", " ")
    if key.lower().replace("_", "").replace("-", "") in _LABEL_NAMES:
        return _LABEL_NAMES[key.lower().replace("_", "").replace("-", "")]
    return plain


def style_value(text: Any, kind: str = "plain") -> str:
    return style(str(text), *_STYLE_VALUE.get(kind, ()))


def header(title: str) -> None:
    line = style(f"── {title.upper()} " + "─" * max(0, 52 - len(title)), "bold", "cyan")
    print()
    print(line)


def warn(text: str) -> None:
    print(f"  {style('⚠', 'yellow')} {style(text, 'yellow')}")


def bullet(
    label: str,
    value: Any,
    danger: bool = False,
    width: int = 10,
    kind: str = "plain",
) -> None:
    """Print ``label : value`` with a readable, colour-coded label.

    *label* stays grey so the eye lands on the value, but the value itself
    is plain (not dim), which was almost unreadable on dark terminals.
    """
    name = style(f"{label:<{width}}", "bold")
    text = str(value)
    if danger and kind == "plain":
        kind = "bad"
    print(f"  {name}: {style_value(text, kind)}")


# --------------------------------------------------------------------------- #
# Subprocess / shell
# --------------------------------------------------------------------------- #


def _subprocess_env() -> "os._Environ | dict":
    """Environment for helper processes; never sets text-mode vars.

    ``PYTHONIOENCODING`` must stay unset: PowerShell 5.1 reads it and then
    re-encodes its stdout (double encoding). We decode the bytes ourselves.
    """
    return dict(os.environ)


def _ps_script(script: str) -> "list[str]":
    """Build the argv for a PowerShell snippet."""
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]


def power_shell(script: str, timeout: float = 20.0) -> Optional[str]:
    """Run a PowerShell snippet and return its decoded stdout."""
    return run_cmd(_ps_script(script), timeout=timeout)


def run_cmd(
    args: Sequence[str],
    timeout: float = 15.0,
) -> Optional[str]:
    """Run *args* and return stdout, or ``None`` if unavailable/failed.

    Commands are always invoked as argument lists (never through a shell), so
    user-supplied values can never be interpreted as shell syntax.
    """
    if not args or shutil.which(args[0]) is None:
        return None
    try:
        proc = subprocess.run(
            list(args),
            capture_output=True,  # always bytes; no locale guessing
            timeout=timeout,
            check=False,
            env=_subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = _decode(proc.stdout or b"")
    if proc.returncode != 0 and not text:
        return None
    return text


def _decode(raw: bytes) -> str:
    """Decode subprocess output that may be UTF-8 or a legacy Windows code page.

    PowerShell 5.1 usually writes UTF-8, but for some console hosts it
    re-encodes Cyrillic through the OEM code page. Both layouts are detected
    and repaired here.
    """
    if not raw:
        return ""
    # Layout A: UTF-8 text that PowerShell re-encoded as cp866/cp1251.
    for codec in ("utf-8", "cp1251"):
        try:
            repaired = raw.decode(codec).encode("cp866").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            repaired = None
        if repaired and "\ufffd" not in repaired:
            return repaired
    # Layout B: legacy code page bytes, e.g. "Р‘РµСЃРїСЂ" (cp866 read as cp1251).
    try:
        legacy = raw.decode("cp1251")
    except UnicodeDecodeError:
        legacy = ""
    if legacy and "\u0400" <= legacy[0] <= "\u04ff" and "Р" in legacy[:40]:
        try:
            return legacy.encode("cp1251").decode("cp866")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    try:
        text = raw.decode("utf-8")
        if "\ufffd" not in text:
            return text
    except UnicodeDecodeError:
        pass
    for codec in ("cp866", "cp1251", "mbcs"):
        try:
            return raw.decode(codec)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def is_windows() -> bool:
    return os.name == "nt"


# --------------------------------------------------------------------------- #
# IP address helpers
# --------------------------------------------------------------------------- #

#: Addresses/blocks that never belong to a real LAN.
_BLOCKED = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
]


def parse_ip(value: str) -> Optional[ipaddress._BaseAddress]:
    """Parse *value* into an IPv4/IPv6 address or (for CIDR tasks) network."""
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def parse_network(value: str) -> Optional[ipaddress._BaseNetwork]:
    try:
        return ipaddress.ip_network(value.strip(), strict=False)
    except ValueError:
        return None


def is_private_lan(ip: str) -> bool:
    """True when *ip* is a private (RFC1918 / ULA) host address."""
    addr = parse_ip(ip)
    if addr is None:
        return False
    if any(addr in net for net in _BLOCKED):
        return False
    return addr.is_private


def same_network(ip: str, networks: Iterable[ipaddress._BaseNetwork]) -> bool:
    """True when *ip* is inside one of *networks* (the local networks)."""
    addr = parse_ip(ip)
    if addr is None:
        return False
    return any(
        addr.version == net.version and addr in net for net in networks
    )


def ip_sort_key(ip: str) -> tuple:
    addr = parse_ip(ip)
    if addr is None:
        return (99, 0, ip)
    return (addr.version, int(addr), "")


# --------------------------------------------------------------------------- #
# JSON output
# --------------------------------------------------------------------------- #


def emit_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def flatten_rows(rows: Iterable[dict], columns: Optional[List[str]] = None) -> str:
    """Render a list of dicts as a simple fixed-width table."""
    rows = list(rows)
    if not rows:
        return ""
    if columns is None:
        columns = list(rows[0].keys())
    widths = {c: len(str(c)) for c in columns}
    for row in rows:
        for c in columns:
            widths[c] = max(widths[c], len(str(row.get(c, ""))))
    out = []
    out.append("  " + "  ".join(style(str(c).ljust(widths[c]), "bold") for c in columns))
    out.append("  " + "  ".join("─" * widths[c] for c in columns))
    for row in rows:
        out.append("  " + "  ".join(str(row.get(c, "")).ljust(widths[c]) for c in columns))
    return "\n".join(out)
