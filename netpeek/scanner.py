"""Read-only TCP port scanner for hosts on *your* network.

A plain ``connect()`` scan: no raw packets, no SYN flooding, no exploitation.
The target must pass :func:`netpeek.guard.require_local` first.
"""

from __future__ import annotations

import concurrent.futures
import socket
from typing import Iterable, List, Optional

from . import guard, ports as ports_mod

COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445, 587, 993, 995,
    1433, 1521, 2049, 3000, 3306, 3389, 5000, 5432, 5900, 6379, 8000, 8080,
    8443, 8888, 9200, 27017,
]


def parse_ports(spec: str) -> List[int]:
    """Parse ``"22,80,1000-1010"`` into a sorted list of ports."""
    result = set()
    cleaned = spec.replace(" ", "")
    if not cleaned:
        raise ValueError("no ports given")
    for chunk in cleaned.split(","):
        if not chunk:
            raise ValueError(f"empty port in list: {spec!r}")
        if "-" in chunk:
            start, _, end = chunk.partition("-")
            if not (start.isdigit() and end.isdigit()):
                raise ValueError(f"bad port range: {chunk!r}")
            lo, hi = int(start), int(end)
            if lo > hi or lo < 1 or hi > 65535:
                raise ValueError(f"bad port range: {chunk!r}")
            result.update(range(lo, hi + 1))
        elif chunk.isdigit():
            port = int(chunk)
            if not 1 <= port <= 65535:
                raise ValueError(f"bad port: {chunk!r}")
            result.add(port)
        else:
            raise ValueError(f"bad port: {chunk!r}")
    if not result:
        raise ValueError("no ports given")
    return sorted(result)


def _probe(host: str, port: int, timeout: float) -> Optional[int]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return port
    except OSError:
        return None


def scan_ports(
    host: str,
    port_list: Iterable[int],
    timeout: float = 0.4,
    workers: int = 128,
    dry_run: bool = False,
) -> dict:
    """Return ``{"host":..., "open": [{port, service}, ...]}``."""
    target = guard.require_local(host, dry_run=dry_run)
    ports = sorted(set(port_list))
    if dry_run:
        return {
            "host": target,
            "dry_run": True,
            "would_scan": ports,
            "open": [],
        }
    open_ports: List[int] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe, target, p, timeout): p for p in ports}
        for fut in concurrent.futures.as_completed(futures):
            try:
                port = fut.result()
            except Exception:
                port = None
            if port:
                open_ports.append(port)
    open_ports.sort()
    return {
        "host": target,
        "scanned": len(ports),
        "open": [
            {
                "port": p,
                "service": ports_mod.service_name(p),
                "risk": ports_mod.RISKY_PORTS.get(p, ""),
            }
            for p in open_ports
        ],
    }


def grab_banner(host: str, port: int, timeout: float = 2.0) -> str:
    """Read a short service banner (HTTP head, TLS, SSH, etc.)."""
    target = guard.require_local(host)
    try:
        with socket.create_connection((target, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            if port in (443, 8443):
                return "TLS service (use `netpeek tls` for the certificate)"
            if port in (80, 8000, 8080, 8888, 5000):
                sock.sendall(f"HEAD / HTTP/1.1\r\nHost: {target}\r\nConnection: close\r\n\r\n".encode())
            data = sock.recv(1024)
            return data.decode("utf-8", "replace").strip()
    except OSError as exc:
        return f"(no banner: {exc})"
