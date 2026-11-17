"""Listening ports and active connections on *this* machine only."""

from __future__ import annotations

import socket
import sys
from typing import List, Optional

from . import util

# Well-known ports with a human readable description.
WELL_KNOWN = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    135: "RPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    1433: "MSSQL",
    1521: "Oracle",
    2049: "NFS",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    5900: "VNC",
    6379: "Redis",
    8080: "HTTP-alt",
    8443: "HTTPS-alt",
    9200: "Elasticsearch",
    27017: "MongoDB",
}

# Ports that should normally not be reachable from the LAN.
RISKY_PORTS = {
    21: "FTP (unencrypted)",
    22: "SSH reachable from the network",
    23: "Telnet (unencrypted, obsolete)",
    135: "Windows RPC",
    139: "NetBIOS",
    445: "SMB file sharing",
    1433: "MSSQL",
    3389: "Remote Desktop exposed",
    5900: "VNC (often weakly protected)",
    6379: "Redis (usually unauthenticated by default)",
    27017: "MongoDB",
}

_PORT_RE = None


def service_name(port: int) -> str:
    if port in WELL_KNOWN:
        return WELL_KNOWN[port]
    try:
        return socket.getservbyport(port, "tcp")
    except OSError:
        return ""


def _parse_address(value: str) -> tuple:
    value = value.strip().strip("[]")
    if value.startswith("[") and value.endswith("]"):
        return value[1:-1], ""
    if ":" in value:
        # Split on the LAST colon so IPv6 works, but plain IPv4:port too.
        host, _, port = value.rpartition(":")
        return host.strip("[]"), port
    return value, ""


def _listen_windows() -> List[dict]:
    raw = util.power_shell(
        "$rows = foreach ($c in Get-NetTCPConnection -State Listen "
        "-ErrorAction SilentlyContinue) {"
        '  "$($c.LocalAddress):$($c.LocalPort)|$($c.OwningProcess)"'
        "};"
        "@($rows) | Out-String",
        timeout=25,
    )
    rows: List[dict] = []
    if raw:
        for line in raw.splitlines():
            line = line.strip()
            if "|" not in line:
                continue
            addr, _, rest = line.partition("|")
            pid = rest.strip()
            host, _, port = addr.rpartition(":")
            if not port.isdigit():
                continue
            rows.append(
                {
                    "address": host.strip("[]"),
                    "port": int(port),
                    "pid": int(pid) if pid.isdigit() else None,
                }
            )
    if rows:
        return rows
    return _via_netstat(listen_only=True)


def _via_netstat(listen_only: bool = True) -> List[dict]:
    raw = util.run_cmd(["netstat", "-ano" if util.is_windows() else "-an"], timeout=20) or ""
    rows = []
    for line in raw.splitlines():
        stripped = line.split()
        if len(stripped) < 4:
            continue
        proto = stripped[0].lower()
        if not proto.startswith("tcp"):
            continue
        local = stripped[1]
        state = stripped[3] if len(stripped) >= 4 else ""
        if listen_only and state.upper() != "LISTENING" and state.upper() != "LISTEN":
            continue
        addr, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        rows.append(
            {
                "address": addr.strip("[]"),
                "port": int(port),
                "pid": int(stripped[-1]) if stripped[-1].isdigit() else None,
            }
        )
    return rows


def _process_names() -> dict:
    """Map PID -> process name so listening ports can be attributed."""
    if util.is_windows():
        raw = util.power_shell(
            "$c = $null;"
            "try { $c = Get-Process -ErrorAction SilentlyContinue } catch {};"
            "$c | ForEach-Object { \"$($_.Id)|$($_.ProcessName)\" }",
            timeout=30,
        ) or ""
        names = {}
        for line in raw.splitlines():
            if "|" in line:
                pid, _, name = line.partition("|")
                if pid.strip().isdigit():
                    names[int(pid)] = name.strip()
        return names
    raw = util.run_cmd(["ps", "-eo", "pid=,comm="], timeout=15) or ""
    names = {}
    for line in raw.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            names[int(parts[0])] = parts[1].strip()
    return names


def listening_ports() -> List[dict]:
    rows = _listen_windows() if util.is_windows() else _via_netstat_everything()
    names = _process_names()
    result = []
    seen = set()
    for row in rows:
        key = (row["address"], row["port"])
        if key in seen:
            continue
        seen.add(key)
        address = row.get("address", "")
        port = row.get("port", 0)
        pid = row.get("pid")
        exposed = address not in ("127.0.0.1", "::1", "localhost")
        result.append(
            {
                "port": port,
                "address": address,
                "service": service_name(port),
                "process": names.get(pid, "") if pid else "",
                "pid": pid,
                "exposed": exposed,
                "risk": RISKY_PORTS.get(port, "") if exposed else "",
            }
        )
    result.sort(key=lambda r: (not r["exposed"], r["port"]))
    return result


def _via_netstat_everything() -> List[dict]:
    """Unix: ``ss -tlnp`` when present, otherwise ``netstat``."""
    raw = util.run_cmd(["ss", "-tlnp"], timeout=15) or ""
    rows = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0].lower() != "listen":
            continue
        local = parts[3]
        addr, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        pid = None
        proc = ""
        if "users:" in line:
            import re

            m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
            if m:
                proc, pid = m.group(1), int(m.group(2))
        rows.append({"address": addr.strip("[]"), "port": int(port), "pid": pid})
    if rows:
        return rows
    return _via_netstat(listen_only=True)


def active_connections(limit: Optional[int] = None) -> List[dict]:
    """ESTABLISHED outbound/inbound TCP connections of this machine."""
    raw = util.run_cmd(["netstat", "-ano"] if util.is_windows() else ["ss", "-tnp"], timeout=20) or ""
    if not raw:
        raw = util.run_cmd(["netstat", "-an"], timeout=20) or ""
    rows = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].lower().startswith("tcp"):
            continue
        payload = parts[0].lower()
        if payload == "tcp" and len(parts) >= 5:
            local, remote, state = parts[1], parts[2], parts[3]
        elif payload.startswith("tcp"):
            # ss format: tcp ESTAB ... local remote
            if "ESTAB" not in parts:
                continue
            local, remote = parts[3], parts[4]
            state = "ESTABLISHED"
        else:
            continue
        if state.upper() not in ("ESTABLISHED", "ESTAB"):
            continue
        if remote in ("*:*", "0.0.0.0:0"):
            continue
        r_addr, _, r_port = remote.rpartition(":")
        l_addr, _, l_port = local.rpartition(":")
        rows.append(
            {
                "local": f"{l_addr}:{l_port}",
                "remote_ip": r_addr.strip("[]"),
                "remote_port": int(r_port) if r_port.isdigit() else 0,
                "service": service_name(int(r_port)) if r_port.isdigit() else "",
            }
        )
    keep = []
    seen = set()
    for row in rows:
        key = (row["remote_ip"], row["remote_port"])
        if key in seen:
            continue
        seen.add(key)
        keep.append(row)
    keep.sort(key=lambda r: (r["remote_port"], r["remote_ip"]))
    return keep[:limit] if limit else keep


def listening_ipv4_ports(host: str) -> List[int]:
    """Which of the local listening ports answer on *host* — used by scan."""
    return [r["port"] for r in listening_ports() if r["address"] in ("0.0.0.0", host)]


def resolve_hostname(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, socket.herror):
        return ""
