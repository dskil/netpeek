"""Local interface discovery: addresses, MACs, gateways, DNS and Wi-Fi.

Only reads what the operating system already knows about *this* machine.
Nothing here sends packets to other hosts.
"""

from __future__ import annotations

import re
import socket
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import util


@dataclass
class Interface:
    name: str
    mac: str = ""
    ipv4: List[str] = field(default_factory=list)
    ipv6: List[str] = field(default_factory=list)
    is_up: bool = True
    is_wireless: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mac": self.mac,
            "vendor": mac_vendor(self.mac),
            "ipv4": self.ipv4,
            "ipv6": self.ipv6,
            "is_up": self.is_up,
            "is_wireless": self.is_wireless,
        }


# --------------------------------------------------------------------------- #
# MAC addresses
# --------------------------------------------------------------------------- #

# A tiny OUI table so the tool is useful offline. Extend it via
# ``netpeek update`` (json file in the user config directory).
_OUI: Dict[str, str] = {
    "000C29": "VMware",
    "005056": "VMware",
    "080027": "VirtualBox",
    "00155D": "Microsoft (Hyper-V)",
    "001C42": "Parallels",
    "A45E60": "Apple, Inc.",
    "3C0754": "Apple, Inc.",
    "F01898": "Apple, Inc.",
    "001124": "Apple, Inc.",
    "0021CC": "Intel Corporate",
    "3C970E": "Wistron / HP",
    "F4CE46": "Hewlett Packard",
    "001A2B": "Hewlett Packard",
    "001CC4": "Hewlett Packard",
    "000A27": "Cisco Systems",
    "00170F": "Cisco Systems",
    "0024C4": "Cisco Systems",
    "001DD8": "Microsoft",
    "00238B": "Intel Corporate",
    "001B21": "Intel Corporate",
    "68F728": "Atheros / Qualcomm",
    "F4F26D": "TP-Link",
    "EC086B": "TP-Link",
    "B827EB": "Raspberry Pi Foundation",
    "DCA632": "Raspberry Pi Trading",
    "E45F01": "Raspberry Pi Trading",
    "00E04C": "Realtek",
    "001C25": "Hon Hai (Foxconn)",
    "E0D55E": "GIGA-BYTE",
    "3462B4": "Xiaomi",
    "38E7D8": "Samsung Electronics",
    "F409D8": "Samsung Electronics",
    "001E58": "D-Link",
    "0013E0": "Murata / Nintendo",
}

# Locally administered / randomized MACs used by phones for privacy.
_LOCAL_ADMIN_BIT = 0x02


def normalise_mac(mac: str) -> str:
    """Return ``AA:BB:CC:DD:EE:FF`` or ``""``."""
    if not mac:
        return ""
    hexdigits = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
    if len(hexdigits) != 12:
        return ""
    return ":".join(hexdigits[i : i + 2] for i in range(0, 12, 2))


def mac_vendor(mac: str) -> str:
    mac = normalise_mac(mac)
    if not mac:
        return ""
    oui = mac.replace(":", "")[:6]
    vendor = _OUI.get(oui)
    if vendor:
        return vendor
    if int(mac[:2], 16) & _LOCAL_ADMIN_BIT:
        return "Private / randomized MAC"
    return "Unknown vendor"


# --------------------------------------------------------------------------- #
# Interface discovery
# --------------------------------------------------------------------------- #


def _interfaces_windows() -> List[Interface]:
    import json
    import subprocess

    raw = util.power_shell(
        "$items = foreach ($c in Get-NetIPConfiguration) {"
        "  $a = $c.NetAdapter;"
        "  [pscustomobject]@{"
        "    InterfaceAlias = $c.InterfaceAlias;"
        "    InterfaceIndex = $c.InterfaceIndex;"
        "    mac = $a.MacAddress;"
        "    ipv4 = @($c.IPv4Address.IPAddress);"
        "    ipv6 = @($c.IPv6Address.IPAddress);"
        "    up = ($a.Status -eq 'Up');"
        "    wifi = ($a.InterfaceType -eq 71)"
        "  }"
        "};"
        "@($items) | ConvertTo-Json -Depth 4",
        timeout=25,
    )
    if not raw or not raw.strip():
        return []
    data = json.loads(raw.strip() or "[]")
    if isinstance(data, dict):
        data = [data]
    result = []
    for item in data:
        name = item.get("InterfaceAlias") or f"interface {item.get('InterfaceIndex')}"
        result.append(
            Interface(
                name=str(name),
                mac=normalise_mac(str(item.get("mac") or "")),
                ipv4=_as_list(item.get("ipv4")),
                ipv6=_as_list(item.get("ipv6")),
                is_up=bool(item.get("up")),
                is_wireless=bool(item.get("wifi")),
            )
        )
    return result


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)]


def _interfaces_unix() -> List[Interface]:
    """Use the ``ip`` command when available, else fall back to sockets."""
    interfaces: Dict[str, Interface] = {}

    if sys.platform.startswith("linux"):
        raw = util.run_cmd(["ip", "-o", "addr"], timeout=10)
        if raw:
            for line in raw.splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue
                name, family, addr = parts[1], parts[2], parts[3]
                iface = interfaces.setdefault(name, Interface(name=name))
                if family == "inet":
                    iface.ipv4.append(addr.split("/")[0])
                elif family == "inet6":
                    iface.ipv6.append(addr.split("/")[0])
        link = util.run_cmd(["ip", "-o", "link"], timeout=10)
        if link:
            for line in link.splitlines():
                m = re.search(r"^\d+:\s+(\S+):.*?link/ether\s+([0-9a-fA-F:]{17})", line)
                if m:
                    interfaces.setdefault(m.group(1), Interface(name=m.group(1))).mac = (
                        normalise_mac(m.group(2))
                    )
        wifi = util.run_cmd(["iw", "dev"], timeout=10) or ""
        for name in interfaces:
            if re.search(rf"Interface {re.escape(name)}\b", wifi):
                interfaces[name].is_wireless = True

    if not interfaces and sys.platform == "darwin":
        ifconfig = util.run_cmd(["ifconfig"], timeout=10) or ""
        current: Optional[Interface] = None
        for line in ifconfig.splitlines():
            if line and not line[0].isspace():
                name = line.split(":")[0]
                current = interfaces.setdefault(name, Interface(name=name))
            elif current is not None:
                if "ether" in line:
                    current.mac = normalise_mac(line.split("ether")[1].split()[0])
                elif "inet " in line:
                    current.ipv4.append(line.split("inet ")[1].split()[0])
                elif "inet6 " in line:
                    addr = line.split("inet6 ")[1].split()[0]
                    if not addr.startswith("fe80"):
                        current.ipv6.append(addr.split("%")[0])
        networksetup = util.run_cmd(["networksetup", "-listallhardwareports"], timeout=10) or ""
        wifi_name = ""
        m = re.search(r"Wi-Fi.*?Device:\s*(\S+)", networksetup, re.S)
        if m:
            wifi_name = m.group(1)
        if wifi_name in interfaces:
            interfaces[wifi_name].is_wireless = True

    return [i for i in interfaces.values() if i.ipv4 or i.mac]


def get_interfaces() -> List[Interface]:
    if util.is_windows():
        ifaces = _interfaces_windows()
    else:
        ifaces = _interfaces_unix()
    # Newest-first ordering that puts the default route interface on top.
    ifaces.sort(key=lambda i: (not i.ipv4, i.is_wireless is False, i.name))
    return ifaces


# --------------------------------------------------------------------------- #
# Routes / DNS / hostname
# --------------------------------------------------------------------------- #


def get_gateway() -> Optional[str]:
    if util.is_windows():
        raw = util.power_shell(
            "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue "
            "| Sort-Object RouteMetric | Select-Object -First 1).NextHop",
            timeout=20,
        )
        gw = (raw or "").strip()
        return gw or None
    if sys.platform == "darwin":
        raw = util.run_cmd(["route", "-n", "get", "default"], timeout=10) or ""
        m = re.search(r"gateway:\s*(\S+)", raw)
        return m.group(1) if m else None
    raw = util.run_cmd(["ip", "route", "show", "default"], timeout=10) or ""
    m = re.search(r"default via (\S+)", raw)
    return m.group(1) if m else None


def get_dns_servers() -> List[str]:
    servers: List[str] = []
    if util.is_windows():
        raw = util.power_shell(
            "(Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue)"
            ".ServerAddresses | Select-Object -Unique",
            timeout=20,
        )
        servers = [s.strip() for s in (raw or "").splitlines() if s.strip()]
    else:
        try:
            with open("/etc/resolv.conf", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip().startswith("nameserver"):
                        servers.append(line.split()[1])
        except OSError:
            pass
    if not servers:
        try:
            import subprocess

            raw = util.run_cmd(["nslookup", "example.com"], timeout=10) or ""
            for line in raw.splitlines():
                if "Address:" in line and ":" in line:
                    addr = line.rsplit(":", 1)[-1].strip()
                    if addr and addr not in servers:
                        servers.append(addr)
        except Exception:  # pragma: no cover - best effort only
            pass
    # De-duplicate, keep order.
    seen = set()
    unique = []
    for s in servers:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def get_hostname() -> dict:
    info = {"hostname": socket.gethostname()}
    try:
        info["fqdn"] = socket.getfqdn()
    except OSError:
        info["fqdn"] = ""
    if util.is_windows():
        raw = util.power_shell(
            "$c = Get-CimInstance Win32_ComputerSystem; "
            "\"$($c.Domain)|$($c.PartOfDomain)\"",
            timeout=20,
        )
        if raw and "|" in raw:
            domain, part = raw.strip().split("|", 1)
            info["domain"] = domain
            info["domain_type"] = "domain" if part.lower() == "true" else "workgroup"
    return info


def get_wifi() -> dict:
    """Return SSID/signal/security of the connected Wi-Fi (read-only)."""
    if util.is_windows():
        raw = util.run_cmd(["netsh", "wlan", "show", "interfaces"], timeout=15) or ""
        result: Dict[str, str] = {}
        for line in raw.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip()
            low = key.lower()
            if "ssid" == low:
                result["ssid"] = val
            elif "signal" in low:
                result["signal"] = val
            elif "authentication" in low:
                result["security"] = val
            elif "cipher" in low:
                result["cipher"] = val
            elif "channel" in low:
                result["channel"] = val
        return result
    if sys.platform == "darwin":
        raw = util.run_cmd(
            ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
            timeout=10,
        ) or ""
        result = {}
        for line in raw.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                result[key.strip().lower()] = val.strip()
        return {"ssid": result.get("ssid", ""), "channel": result.get("channel", "")}
    raw = util.run_cmd(["iwgetid", "-r"], timeout=10) or ""
    return {"ssid": raw.strip()} if raw.strip() else {}


def local_networks() -> List:
    """Return IPv4 networks for the real LAN interfaces of this machine.

    Link-local (169.254.x.x) addresses are skipped: they are not a network
    the user wants to scan. VPN adapters such as Radmin VPN / ZeroTier are
    included because they *are* private networks this machine belongs to.
    """
    import ipaddress

    nets = []
    seen = set()
    for iface in get_interfaces():
        for addr in iface.ipv4:
            parsed = util.parse_ip(addr)
            if parsed is None or not parsed.is_private:
                continue
            if parsed.is_link_local:
                continue
            net = ipaddress.ip_network(f"{addr}/24", strict=False)
            if str(net) in seen:
                continue
            seen.add(str(net))
            nets.append(net)
    return nets
