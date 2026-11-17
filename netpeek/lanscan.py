"""LAN discovery: who is connected to *this* network right now.

Two passive/active techniques are used and merged:

* the OS neighbour (ARP) cache — already collected by the system;
* a short ICMP/TCP sweep over the local subnet(s), which fills the ARP cache.

The sweep is throttled and bounded, and only ever targets the private
subnets of the machine running the tool.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import re
import socket
import subprocess
import sys
from typing import Dict, List, Optional

from . import netinfo, util

_ARP_RE_WINDOWS = re.compile(
    r"^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})\s+(\S+)"
)
_ARP_RE_UNIX = re.compile(
    r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]{17})"
)


def read_arp_table() -> Dict[str, dict]:
    """Return ``{ip: {"mac":..., "iface":...}}`` from the OS neighbour cache."""
    table: Dict[str, dict] = {}
    if util.is_windows():
        raw = util.run_cmd(["arp", "-a"], timeout=20) or ""
        for line in raw.splitlines():
            m = _ARP_RE_WINDOWS.match(line)
            if not m:
                continue
            ip, mac, iface = m.groups()
            table[ip] = {"mac": netinfo.normalise_mac(mac), "iface": iface.strip()}
    else:
        raw = util.run_cmd(["arp", "-an"], timeout=20) or ""
        for line in raw.splitlines():
            m = _ARP_RE_UNIX.search(line)
            if m:
                table[m.group(1)] = {"mac": netinfo.normalise_mac(m.group(2)), "iface": ""}
        if not table:
            raw = util.run_cmd(["ip", "neigh"], timeout=20) or ""
            for line in raw.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[-2] == "lladdr":
                    table[parts[0]] = {"mac": netinfo.normalise_mac(parts[-1]), "iface": parts[2]}
    # Drop incomplete / broadcast entries.
    return {
        ip: info
        for ip, info in table.items()
        if info["mac"] and not info["mac"].startswith("FF:FF")
    }


def _ping(ip: str, timeout_ms: int = 400) -> bool:
    """Single ICMP echo. Uses the OS ``ping`` binary (no root required)."""
    if util.is_windows():
        args = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        oneshot = 0.4 if sys.platform == "darwin" else 1
        args = ["ping", "-c", "1", "-W", str(oneshot), ip]
    proc = subprocess.run(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=max(2.0, timeout_ms / 1000 + 2),
        check=False,
    )
    return proc.returncode == 0


def _tcp_probe(ip: str, port: int = 443, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _alive(ip: str) -> bool:
    try:
        return _ping(ip)
    except (OSError, subprocess.SubprocessError):
        return False


def scan_subnet(
    network: ipaddress.IPv4Network,
    workers: int = 64,
    timeout_ms: int = 400,
) -> List[str]:
    """Ping-sweep *network* and return the addresses that answered."""
    hosts = [str(h) for h in network.hosts()]
    if not hosts:
        return []
    alive: List[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_ping, ip, timeout_ms): ip for ip in hosts}
        for fut in concurrent.futures.as_completed(futures):
            try:
                if fut.result():
                    alive.append(futures[fut])
            except Exception:
                continue
    alive.sort(key=util.ip_sort_key)
    return alive


def scan(
    networks: Optional[List[ipaddress.IPv4Network]] = None,
    sweep: bool = True,
    timeout_ms: int = 400,
) -> List[dict]:
    """Return every device visible on the local network(s).

    Each entry contains ip, mac, vendor, hostname and whether it is this host.
    """
    if networks is None:
        networks = netinfo.local_networks()
    if not networks:
        return []

    if sweep:
        for network in networks:
            # Bound the sweep so /8 misconfigurations cannot hang the tool.
            if network.num_addresses > 4096:
                network = ipaddress.ip_network(
                    f"{next(network.hosts())}/22", strict=False
                )
            try:
                scan_subnet(network, timeout_ms=timeout_ms)
            except OSError:
                continue

    arp = read_arp_table()
    my_ips = set()
    for iface in netinfo.get_interfaces():
        my_ips.update(iface.ipv4)

    devices: List[dict] = []
    for ip, info in arp.items():
        if not util.same_network(ip, networks):
            continue
        mac = info["mac"]
        devices.append(
            {
                "ip": ip,
                "mac": mac,
                "vendor": netinfo.mac_vendor(mac),
                "hostname": "" if ip in my_ips else "",
                "is_me": ip in my_ips,
                "iface": info.get("iface", ""),
            }
        )
    devices.sort(key=lambda d: util.ip_sort_key(d["ip"]))
    return devices


def resolve_names(devices: List[dict], workers: int = 32) -> None:
    """Best-effort reverse DNS for each device (in place)."""
    from . import ports as _ports  # local import avoids a cycle

    def work(dev):
        if not dev.get("hostname"):
            dev["hostname"] = _ports.resolve_hostname(dev["ip"])

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, devices))
