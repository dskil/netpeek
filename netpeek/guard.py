"""Guard-rails that keep NetPeek on the legal side of the line.

Every *active* network operation goes through :func:`guard_target`, which
refuses anything that is not one of:

* the machine itself (loopback / its own addresses);
* a host on a private subnet that this machine is directly connected to.
"""

from __future__ import annotations

import ipaddress
from typing import Iterable, List, Optional

from . import netinfo, util


class NotAllowed(Exception):
    """Raised when a target falls outside this machine's own network."""


class Guard:
    def __init__(self, networks: Optional[Iterable] = None) -> None:
        self.networks: List[ipaddress._BaseNetwork] = list(
            networks if networks is not None else netinfo.local_networks()
        )
        self.my_ips = set()
        for iface in netinfo.get_interfaces():
            self.my_ips.update(iface.ipv4)
            self.my_ips.update(iface.ipv6)

    def describe(self) -> str:
        if not self.networks:
            return "no private network detected"
        return ", ".join(str(n) for n in self.networks)

    def is_self(self, addr) -> bool:
        return addr.is_loopback or str(addr) in self.my_ips

    def check(self, target: str, dry_run: bool = False) -> str:
        """Return the validated IP, or raise :class:`NotAllowed`."""
        addr = util.parse_ip(target)
        if addr is None:
            raise NotAllowed(f"'{target}' is not a valid IP address")
        if self.is_self(addr):
            return str(addr)
        if not any(
            addr.version == net.version and addr in net for net in self.networks
        ):
            raise NotAllowed(
                f"{target} is outside your local network "
                f"({self.describe() or 'none detected'}). "
                "NetPeek only talks to your own subnet."
            )
        if dry_run:
            return str(addr)
        return str(addr)


def require_local(target: str, dry_run: bool = False) -> str:
    return Guard().check(target, dry_run=dry_run)
