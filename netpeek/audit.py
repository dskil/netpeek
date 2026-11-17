"""Health checks and the security score for *this* host and its LAN.

Everything here is advisory: findings are suggestions, not exploits. The tool
never changes system state.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List

from . import netinfo, ports, util


def hostname_checks() -> List[str]:
    return []


def listening_checks() -> Dict[str, List[dict]]:
    risky = []
    for row in ports.listening_ports():
        if row["exposed"] and row["risk"]:
            risky.append(row)
    return {"risky": risky}


def firewall_status() -> dict:
    if util.is_windows():
        raw = util.power_shell(
            "Get-NetFirewallProfile | ForEach-Object { "
            '"$($_.Name)|$($_.Enabled)"; } | Out-String',
            timeout=25,
        ) or ""
        profiles = {}
        for line in raw.splitlines():
            if "|" in line:
                name, _, enabled = line.partition("|")
                profiles[name.strip()] = enabled.strip().lower() == "true"
        return {
            "backend": "Windows Defender Firewall",
            "profiles": profiles,
            "enabled": bool(profiles) and all(profiles.values()),
        }
    raw = util.run_cmd(["ufw", "status"], timeout=10)
    if raw:
        return {"backend": "ufw", "status": raw.strip(), "enabled": "active" in raw.lower()}
    raw = util.run_cmd(["systemctl", "is-active", "firewalld"], timeout=10) or ""
    if raw.strip() == "active":
        return {"backend": "firewalld", "enabled": True}
    raw = util.run_cmd(["pfctl", "-s", "info"], timeout=10) or ""
    return {"backend": "pf" if raw else "unknown", "enabled": "enabled" in raw.lower()}


def updates_status() -> dict:
    if util.is_windows():
        raw = util.power_shell(
            "$u = Get-HotFix | Sort-Object InstalledOn -Descending | "
            "Select-Object -First 1; "
            '"$($u.HotFixID)|$($u.InstalledOn)"',
            timeout=40,
        ) or ""
        if "|" in raw:
            hotfix, _, date = raw.strip().partition("|")
            return {"last_update": hotfix.strip(), "installed_on": date.strip()}
        return {"last_update": "unknown"}
    raw = util.run_cmd(["apt", "list", "--upgradable"], timeout=40) or ""
    count = max(0, len(raw.strip().splitlines()) - 1) if raw else 0
    return {"upgradable_packages": count}


def weak_local_settings() -> List[str]:
    """Look for obvious local misconfigurations, never modifying anything."""
    findings: List[str] = []
    home = Path.home()
    ssh = home / ".ssh"
    if ssh.is_dir():
        for key in ssh.glob("id_*"):
            if key.suffix == ".pub":
                continue
            try:
                mode = key.stat().st_mode & 0o777
            except OSError:
                continue
            if os.name != "nt" and mode & 0o077:
                findings.append(
                    f"{key} is readable by other users (chmod 600 recommended)"
                )
    return findings


def score(findings: List[dict], total: int = 100) -> int:
    weight = {
        "critical": 20,
        "high": 10,
        "medium": 4,
        "low": 1,
        "info": 0,
    }
    penalty = sum(weight.get(f.get("severity", "info"), 0) for f in findings)
    return max(0, total - penalty)


def collect_findings() -> List[dict]:
    findings: List[dict] = []

    # 1. Listening ports reachable from the LAN.
    seen_ports = set()
    for row in ports.listening_ports():
        if row["exposed"] and row["risk"] and row["port"] not in seen_ports:
            seen_ports.add(row["port"])
            findings.append(
                {
                    "severity": "high" if row["port"] in (23, 445, 3389, 6379) else "medium",
                    "title": f"Port {row['port']} ({row['service'] or 'unknown'}) is listening on {row['address']}",
                    "advice": f"{row['risk']}. Allow it only from localhost or trusted hosts.",
                }
            )

    # 2. Firewall.
    fw = firewall_status()
    if not fw.get("enabled", False):
        findings.append(
            {
                "severity": "high",
                "title": "Host firewall is disabled or could not be verified",
                "advice": f"Enable {fw.get('backend', 'the firewall')}.",
            }
        )

    # 3. Local file permissions.
    for item in weak_local_settings():
        findings.append({"severity": "medium", "title": item, "advice": "Restrict permissions."})

    # 4. DNS servers that are not on the local network and not well-known.
    dns = netinfo.get_dns_servers()
    if dns:
        findings.append(
            {
                "severity": "info",
                "title": f"DNS servers in use: {', '.join(dns)}",
                "advice": "If these are unexpected, a router or VPN may be overriding DNS.",
            }
        )
    return findings
