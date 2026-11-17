"""Persistent report files: ``report.md`` and ``report.json``, plus compare."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _is_local(addr: str) -> bool:
    return addr in ("127.0.0.1", "::1", "localhost", "")


def _collapse(rows: List[dict]) -> List[dict]:
    """Merge ``::`` / ``0.0.0.0`` duplicates for the same port."""
    merged: Dict[int, dict] = {}
    for row in rows:
        key = int(row.get("port", 0))
        current = merged.get(key)
        if current is None:
            merged[key] = dict(row)
            continue
        current["exposed"] = current.get("exposed") or row.get("exposed")
        current["risk"] = current.get("risk") or row.get("risk")
        current["process"] = current.get("process") or row.get("process")
        if row.get("address") in ("0.0.0.0", "::"):
            current["address"] = "0.0.0.0"
    return sorted(merged.values(), key=lambda r: (not r.get("exposed"), key_of(r)))


def key_of(row: dict) -> int:
    try:
        return int(row.get("port", 0))
    except (TypeError, ValueError):
        return 0


def _md_table(rows: List[List[Any]], head: List[str]) -> str:
    if not rows:
        return "_nothing found_\n"
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    return "\n".join(out) + "\n"


def build(data: dict) -> str:
    lines: List[str] = []
    lines.append("# NetPeek network report\n")
    lines.append(f"Generated: **{_now()}**\n")
    lines.append(
        "> Only your own machine and your own local network were inspected. "
        "Nothing was modified.\n"
    )

    me = data.get("me") or {}
    lines.append("## This device\n")
    if me:
        # Link-local addresses (169.254.x.x) are noise; keep only real ones.
        local_ips = [
            ip for ip in me.get("ipv4", []) if not str(ip).startswith("169.254.")
        ]
        lines.append(_md_table(
            [
                ["IP (local)", ", ".join(local_ips) or "—"],
                ["IP (public)", me.get("public_ip", "") or "—"],
                ["MAC", ", ".join(me.get("macs", [])) or "—"],
                ["Gateway", me.get("gateway", "") or "—"],
                ["DNS", ", ".join(me.get("dns", [])) or "—"],
                ["Hostname", me.get("hostname", "") or "—"],
            ],
            ["Property", "Value"],
        ))

    devices = data.get("devices") or []
    lines.append("## Connected devices\n")
    lines.append(_md_table(
        [
            [d.get("ip", ""), d.get("mac", ""), d.get("vendor", ""),
             d.get("hostname", ""), "this device" if d.get("is_me") else ""]
            for d in devices
        ],
        ["IP", "MAC", "Vendor", "Hostname", ""],
    ))

    lines.append("## Listening ports (this device)\n")
    lines.append(_md_table(
        [
            [p.get("port"), p.get("address"), p.get("service", ""),
             p.get("process", ""), "exposed" if p.get("exposed") else "localhost",
             p.get("risk", "")]
            for p in _collapse(data.get("listening", []))
        ],
        ["Port", "Address", "Service", "Process", "Scope", "Note"],
    ))

    lines.append("## Findings\n")
    findings = data.get("findings") or []
    if findings:
        lines.append(_md_table(
            [[f.get("severity", ""), f.get("title", ""), f.get("advice", "")] for f in findings],
            ["Severity", "Finding", "Advice"],
        ))
    else:
        lines.append("_No obvious issues found._\n")

    lines.append("## Score\n")
    lines.append(f"**{data.get('score', '—')} / 100**\n")
    return "\n".join(lines)


def write(data: dict, directory: Path, name: str = "report") -> List[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    md = directory / f"{name}.md"
    js = directory / f"{name}.json"
    payload = dict(data)
    payload.setdefault("generated", _now())
    md.write_text(build(payload), encoding="utf-8")
    js.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return [md, js]


def diff(old_path: Path, new_path: Path) -> Dict[str, List[dict]]:
    def load(path: Path) -> Dict[str, dict]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return {d["ip"]: d for d in raw.get("devices", [])}

    old, new = load(old_path), load(new_path)
    added = [new[ip] for ip in sorted(set(new) - set(old))]
    removed = [old[ip] for ip in sorted(set(old) - set(new))]
    changed = [
        new[ip]
        for ip in sorted(set(new) & set(old))
        if new[ip].get("mac") != old[ip].get("mac")
    ]
    return {"added": added, "removed": removed, "changed": changed}
