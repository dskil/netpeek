"""Configuration, history and local data files.

Everything lives under the per-user config directory, never in the repo:

* Windows: ``%APPDATA%\\netpeek\\``
* Linux/macOS: ``$XDG_CONFIG_HOME/netpeek`` or ``~/.config/netpeek``
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.9/3.10
    tomllib = None  # type: ignore

DEFAULTS: Dict[str, Any] = {
    "scan": {
        "sweep": True,
        "timeout_ms": 400,
        "workers": 64,
    },
    "ports": {
        "common_only": True,
        "timeout_s": 0.4,
    },
    "output": {
        "colour": True,
        "json": False,
    },
    "safety": {
        "require_local_targets": True,
    },
}


def config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "netpeek"


def data_dir() -> Path:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_NAME = "config.toml"


def config_path() -> Path:
    return config_dir() / CONFIG_NAME


def history_path() -> Path:
    return config_dir() / "history.jsonl"


def default_toml() -> str:
    return """# NetPeek / fsociety configuration
# Edited by hand or via `netpeek config set key value`.

[scan]
# Sweep the local subnet with ICMP before reading the ARP table.
sweep = true
# Per-host wait time in milliseconds.
timeout_ms = 400
workers = 64

[ports]
# Only scan a curated list of common ports unless a range is given.
common_only = true
timeout_s = 0.4

[output]
colour = true
json = false

[safety]
# Refuse any target outside your own private subnets.
require_local_targets = true
"""


def init(force: bool = False) -> Path:
    path = config_path()
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_toml(), encoding="utf-8")
    return path


def load() -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    path = config_path()
    if not path.exists():
        return cfg
    if tomllib is not None:
        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, ValueError):
            return cfg
        for section, values in data.items():
            if isinstance(values, dict) and isinstance(cfg.get(section), dict):
                cfg[section].update(values)
            else:
                cfg[section] = values
    return cfg


def get(key: str) -> Any:
    cfg = load()
    parts = key.split(".")
    for part in parts:
        if not isinstance(cfg, dict) or part not in cfg:
            return None
        cfg = cfg[part]
    return cfg


def set_value(key: str, raw_value: str) -> Path:
    """Write a single ``section.key = value`` into the TOML file."""
    cfg = load()
    parts = key.split(".")
    section = cfg
    for part in parts[:-1]:
        section = section.setdefault(part, {})
    old = section.get(parts[-1])
    section[parts[-1]] = _coerce(raw_value, old)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_toml(cfg), encoding="utf-8")
    return path


def _coerce(raw: str, old: Any) -> Any:
    text = raw.strip()
    if isinstance(old, bool) or text.lower() in ("true", "false"):
        return text.lower() in ("true", "yes", "1", "on")
    if isinstance(old, int):
        try:
            return int(text)
        except ValueError:
            return old
    if isinstance(old, float):
        try:
            return float(text)
        except ValueError:
            return old
    return text


def _to_toml(cfg: Dict[str, Any]) -> str:
    lines = ["# NetPeek / fsociety configuration"]
    for section, values in cfg.items():
        if isinstance(values, dict):
            lines.append("")
            lines.append(f"[{section}]")
            for key, value in values.items():
                lines.append(f"{key} = {_toml_value(value)}")
        else:
            lines.append(f"{section} = {_toml_value(values)}")
    return "\n".join(lines) + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def append_history(command: str, summary: str = "") -> None:
    try:
        path = history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "command": command,
            "summary": summary,
            "user": os.environ.get("USERNAME") or os.environ.get("USER", ""),
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read_history(limit: int = 20):
    path = history_path()
    if not path.exists():
        return []
    entries = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except (OSError, ValueError):
        return []
    return entries[-limit:]


def vendor_cache_path() -> Path:
    return config_dir() / "oui.json"


def load_vendor_cache() -> Dict[str, str]:
    path = vendor_cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
