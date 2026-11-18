"""The command-line interface.

Two console scripts call :func:`run`:

    netpeek  <command>
    fsociety <command>

The program name is taken from ``os.path.basename(sys.argv[0])`` so the help
text always shows the name you actually typed.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import shutil
import socket
import sys
import time
from pathlib import Path
from typing import List, Optional

from . import __version__, audit, config, external, guard, lanscan, netinfo, ports, report, scanner, util

EPILOG = """\
NetPeek is read-only and legal by design:
  * it only inspects THIS machine and the private network it is connected to;
  * active scans refuse any target outside your own subnet (`safety`);
  * it never exploits, brute-forces, modifies or exfiltrates anything.

Use it on your own network, or where you have written permission.

Examples (replace <cmd> with whichever name you installed):
  <cmd> me                          # full report about this device
  <cmd> me --ports --json           # which ports this device listens on
  <cmd> scan                        # who is in my LAN right now
  <cmd> ports 192.168.1.10 --range 1-1024
  <cmd> report                      # write report.md + report.json
  <cmd> version                     # show the version

The two names are one tool: same commands, same output.
"""

# --------------------------------------------------------------------------- #
# Presentation helpers
# --------------------------------------------------------------------------- #


def program_name() -> str:
    """Name used in usage/help — whichever alias the user invoked."""
    name = os.path.basename(sys.argv[0]).lower()
    if name.endswith(".exe"):
        name = name[:-4]
    if name in ("netpeek", "fsociety"):
        return name
    return "netpeek"


def _send(stream, text: str) -> None:
    newline = "\r\n" if os.name == "nt" and getattr(stream, "isatty", lambda: False)() else "\n"
    stream.write(text + newline)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def collect_me(with_connections: bool = False, with_public: bool = True) -> dict:
    interfaces = [i.to_dict() for i in netinfo.get_interfaces()]
    macs = [i["mac"] for i in interfaces if i["mac"]]
    ipv4 = [ip for i in interfaces for ip in i["ipv4"]]
    ipv6 = [ip for i in interfaces for ip in i["ipv6"]]
    data = {
        "hostname": netinfo.get_hostname(),
        "interfaces": interfaces,
        "macs": macs,
        "ipv4": ipv4,
        "ipv6": ipv6,
        "gateway": netinfo.get_gateway() or "",
        "dns": netinfo.get_dns_servers(),
        "networks": [str(n) for n in netinfo.local_networks()],
        "wifi": netinfo.get_wifi(),
        "public_ip": "",
        "public_details": {},
    }
    if with_public:
        data["public_ip"] = external.public_ip()
        if data["public_ip"]:
            data["public_details"] = external.ip_details(data["public_ip"])
    if with_connections:
        data["connections"] = ports.active_connections(limit=40)
    return data


def supports_ansi() -> bool:
    """ANSI colour works in modern Windows terminals only."""
    if os.name != "nt":
        return sys.stdout.isatty()
    if not sys.stdout.isatty():
        return False
    return bool(os.environ.get("WT_SESSION") or os.environ.get("TERM"))


def collapse_dual_stack(rows: list) -> list:
    """Merge ``::`` and ``0.0.0.0`` entries for the same port into one row.

    On Windows every dual-stack listener appears twice; showing it once with
    the process name is much easier to read.
    """
    merged: dict = {}
    for row in rows:
        key = row["port"]
        current = merged.get(key)
        if current is None:
            merged[key] = dict(row)
            continue
        current["exposed"] = current["exposed"] or row["exposed"]
        current["risk"] = current["risk"] or row["risk"]
        current["process"] = current["process"] or row["process"]
        if row["address"] in ("0.0.0.0", "::"):
            current["address"] = "0.0.0.0"
    ordered = sorted(merged.values(), key=lambda r: (not r["exposed"], r["port"]))
    return ordered


def cmd_me(args) -> int:
    show_all = not (args.ip or args.mac or args.dns or args.ports_ or args.conns or args.wifi or args.gateway)
    with_public = not (args.mac or args.ports_)
    # Listening ports are only expensive on Windows (PowerShell); fetch them
    # on demand so the plain `me` command stays fast.
    data = collect_me(with_connections=show_all or args.conns, with_public=with_public)
    if args.json:
        out = dict(data)
        if show_all or args.ports_:
            out["listening"] = ports.listening_ports()
        util.emit_json(out)
        return 0

    host = data["hostname"]
    util.header("this device")
    util.bullet("hostname", host.get("hostname", ""))
    if host.get("fqdn") and host.get("fqdn") != host.get("hostname"):
        util.bullet("fqdn", host["fqdn"])
    if host.get("domain"):
        util.bullet(host.get("domain_type", "domain"), host["domain"])

    if show_all or args.ip:
        util.header("ip addresses")
        if not data["ipv4"]:
            util.warn("no IPv4 address found — are you offline?")
        width = max([len(i["name"]) for i in data["interfaces"]] + [8])
        for iface in data["interfaces"]:
            for ip in iface["ipv4"]:
                util.bullet(iface["name"], f"{ip}  (IPv4)", width=width)
            for ip in iface["ipv6"]:
                util.bullet(iface["name"], f"{ip}  (IPv6)", width=width)
        if data["public_ip"]:
            det = data.get("public_details", {})
            extra = ", ".join(x for x in (det.get("org", ""), det.get("country", "")) if x)
            util.bullet("public", f"{data['public_ip']}  {('(' + extra + ')') if extra else ''}")
        if data["networks"]:
            util.bullet("subnet", ", ".join(data["networks"]))

    if show_all or args.mac:
        util.header("mac addresses")
        width = max([len(i["name"]) for i in data["interfaces"]] + [8])
        for iface in data["interfaces"]:
            if iface.get("mac"):
                util.bullet(
                    iface["name"],
                    f"{iface['mac']}  ({iface.get('vendor') or 'unknown vendor'})",
                    width=width,
                )

    if show_all or args.gateway:
        util.header("gateway & dns")
        util.bullet("gateway", data["gateway"] or "not found")
        util.bullet("dns", ", ".join(data["dns"]) or "not configured")

    if show_all or args.ports_:
        util.header("listening ports (this device)")
        rows = ports.listening_ports()
        rows = collapse_dual_stack(rows)
        if not rows:
            print("  nothing is listening")
        for row in rows:
            line = f"{row['port']:<6} {row['service'] or '':<14} {row['process'] or '':<22} {row['address']}"
            if row["risk"]:
                print(f"  {line}  {util.style('⚠ ' + row['risk'], 'yellow')}")
            elif row["exposed"]:
                print(f"  {line}  {util.style('(reachable from the LAN)', 'dim')}")
            else:
                print(f"  {line}  {util.style('(localhost only)', 'dim')}")

    if show_all or args.conns:
        util.header("active connections")
        rows = data.get("connections", [])
        if not rows:
            print("  no established connections")
        for row in rows:
            print(f"  {row['remote_ip']:<40} :{row['remote_port']:<6} {row['service']}")

    if (show_all or args.wifi) and data["wifi"]:
        util.header("wi-fi")
        for key, value in data["wifi"].items():
            util.bullet(key, value)
    return 0


def cmd_ip(args) -> int:
    data = collect_me(with_public=True)
    out = {
        "local": data["ipv4"],
        "ipv6": data["ipv6"],
        "public": data["public_ip"],
        "networks": data["networks"],
    }
    if args.json:
        util.emit_json(out)
        return 0
    util.header("ip addresses")
    for ip in out["local"]:
        util.bullet("local", ip)
    for ip in out["ipv6"]:
        util.bullet("ipv6", ip)
    util.bullet("public", out["public"] or "unavailable (offline?)")
    for net in out["networks"]:
        util.bullet("subnet", net)
    return 0


def cmd_mac(args) -> int:
    data = collect_me(with_public=False)
    rows = [
        {"iface": i["name"], "mac": i["mac"], "vendor": i.get("vendor", "")}
        for i in data["interfaces"]
        if i.get("mac")
    ]
    if args.json:
        util.emit_json(rows)
        return 0
    util.header("mac addresses")
    if not rows:
        util.warn("no MAC address found")
    for row in rows:
        util.bullet(row["iface"][:10], f"{row['mac']}  ({row['vendor'] or 'unknown vendor'})")
    return 0


def cmd_gateway(args) -> int:
    gw = netinfo.get_gateway()
    data = {"gateway": gw or "", "dns": netinfo.get_dns_servers()}
    if args.json:
        util.emit_json(data)
        return 0
    util.header("gateway")
    util.bullet("gateway", gw or "not found")
    util.bullet("dns", ", ".join(data["dns"]) or "not configured")
    return 0


def cmd_dns(args) -> int:
    if not args.domain:
        data = {
            "dns": netinfo.get_dns_servers(),
            "hostname": netinfo.get_hostname(),
        }
        if args.json:
            util.emit_json(data)
        else:
            util.header("dns servers")
            util.bullet("servers", ", ".join(data["dns"]) or "not configured")
            util.bullet("hostname", data["hostname"].get("hostname", ""))
        return 0

    result = external.dns_report(args.domain)
    if args.json:
        util.emit_json(result)
        return 0
    util.header(f"dns records — {args.domain}")
    if not result["records"]:
        util.warn("no records found")
    for rtype, values in result["records"].items():
        for value in values:
            util.bullet(rtype, value)
    util.header("mail authentication")
    util.bullet("spf", result["spf"] or "missing")
    util.bullet("dmarc", result["dmarc"] or "missing")
    util.bullet("dkim", ", ".join(result["dkim_selectors"]) or "not found")
    print()
    for check in result["checks"]:
        print(f"  • {check}")
    return 0


def cmd_myip(args) -> int:
    ip = external.public_ip()
    details = external.ip_details(ip) if ip else {}
    if args.json:
        util.emit_json(details or {"ip": ""})
        return 0
    util.header("public ip")
    if not ip:
        util.warn("could not reach the internet")
        return 1
    util.bullet("ip", ip)
    for key in ("country", "city", "org", "hostname"):
        if details.get(key):
            util.bullet(key, details[key])
    return 0


def cmd_whois(args) -> int:
    result = external.whois(args.target)
    if args.json:
        util.emit_json(result)
        return 0
    util.header(f"whois — {args.target}")
    if result.get("source") == "unavailable":
        util.warn("whois service unavailable (offline?)")
        return 1
    for key, value in result.items():
        if key in ("query", "source"):
            continue
        util.bullet(key[:12], value)
    return 0


def cmd_tls(args) -> int:
    result = external.tls_info(args.host)
    if args.json:
        util.emit_json(result)
        return 0
    util.header(f"tls — {args.host}")
    if result.get("error"):
        util.warn(result["error"])
        return 1
    util.bullet("subject", result["subject"])
    util.bullet("issuer", result["issuer"])
    util.bullet("expires", f"{result['not_after']}  ({result['days_left']} days left)")
    if result.get("warning"):
        util.warn(result["warning"])
    for name in result.get("san", [])[:10]:
        util.bullet("san", name)
    return 0


def cmd_scan(args) -> int:
    cfg = config.load()
    networks = None
    if args.network:
        net = util.parse_network(args.network)
        if net is None or not isinstance(net, ipaddress.IPv4Network):
            util.warn(f"invalid IPv4 network: {args.network}")
            return 2
        networks = [net]
    devices = lanscan.scan(
        networks,
        sweep=not args.no_sweep,
        timeout_ms=args.timeout,
    )
    if args.resolve:
        lanscan.resolve_names(devices)
    if args.json:
        util.emit_json(devices)
        return 0
    util.header("devices in your network")
    if not devices:
        util.warn("nothing found — try `scan` without --no-sweep")
        return 0
    print()
    print(util.flatten_rows(
        [
            {
                "IP": d["ip"],
                "MAC": d["mac"],
                "VENDOR": d["vendor"][:26],
                "HOSTNAME": d.get("hostname", ""),
                "": "← this device" if d.get("is_me") else "",
            }
            for d in devices
        ]
    ))
    print()
    print(f"  {len(devices)} device(s) found")
    config.append_history("scan", f"{len(devices)} devices")
    return 0


def cmd_ports(args) -> int:
    if args.range:
        try:
            port_list = scanner.parse_ports(args.range)
        except ValueError as exc:
            util.warn(str(exc))
            return 2
    else:
        port_list = scanner.COMMON_PORTS
    try:
        result = scanner.scan_ports(
            args.host, port_list, timeout=args.timeout, dry_run=args.dry_run
        )
    except guard.NotAllowed as exc:
        util.warn(str(exc))
        return 2
    if args.json:
        util.emit_json(result)
        return 0
    util.header(f"open ports — {result['host']}")
    if result.get("dry_run"):
        util.warn(f"dry run: would scan {len(result.get('would_scan', []))} ports")
        return 0
    if not result["open"]:
        print("  no open ports in the scanned range")
    for row in result["open"]:
        line = f"{row['port']:<6} {row['service']}"
        if row.get("risk"):
            print(f"  {line}  {util.style('⚠ ' + row['risk'], 'yellow')}")
        else:
            print(f"  {line}")
    print()
    print(f"  {result['scanned']} ports scanned on your own network only")
    return 0


def cmd_banner(args) -> int:
    try:
        banner = scanner.grab_banner(args.host, args.port)
    except guard.NotAllowed as exc:
        util.warn(str(exc))
        return 2
    if args.json:
        util.emit_json({"host": args.host, "port": args.port, "banner": banner})
        return 0
    util.header(f"banner — {args.host}:{args.port}")
    for line in banner.splitlines()[:20]:
        print(f"  {line}")
    return 0


def cmd_subnet(args) -> int:
    target = args.network
    if not target:
        nets = netinfo.local_networks()
        if not nets:
            util.warn("no local network detected")
            return 1
        target = str(nets[0])
    net = util.parse_network(target)
    if net is None:
        util.warn(f"invalid network: {target}")
        return 2
    hosts = net.num_addresses - 2 if net.num_addresses > 2 else net.num_addresses
    data = {
        "network": str(net),
        "prefix": net.prefixlen,
        "netmask": str(net.netmask),
        "broadcast": str(net.broadcast_address),
        "first_host": str(next(net.hosts())) if hosts else "",
        "hosts": hosts,
        "private": net.is_private,
    }
    if args.json:
        util.emit_json(data)
        return 0
    util.header("subnet")
    for key, value in data.items():
        util.bullet(key, value)
    return 0


def cmd_wifi(args) -> int:
    wifi = netinfo.get_wifi()
    if args.json:
        util.emit_json(wifi)
        return 0
    util.header("wi-fi")
    if not wifi:
        util.warn("no Wi-Fi information available")
        return 0
    for key, value in wifi.items():
        util.bullet(key, value)
    return 0


def cmd_myports(args) -> int:
    rows = collapse_dual_stack(ports.listening_ports())
    if args.json:
        util.emit_json(rows)
        return 0
    util.header("listening ports (this device)")
    for row in rows:
        mark = util.style("exposed", "yellow") if row["exposed"] else util.style("localhost", "dim")
        print(f"  {row['port']:<6} {row['service']:<14} {mark:<12} {row['address']:<18} {row['process']}")
    risky = [r for r in rows if r["risk"]]
    if risky:
        print()
        for row in risky:
            util.warn(f"port {row['port']}: {row['risk']}")
    return 0


def cmd_conns(args) -> int:
    rows = ports.active_connections(limit=args.limit)
    if args.json:
        util.emit_json(rows)
        return 0
    util.header("active connections")
    for row in rows:
        print(f"  {row['remote_ip']:<40} :{row['remote_port']:<6} {row['service']}")
    return 0


def run_audit() -> dict:
    findings = audit.collect_findings()
    return {
        "findings": findings,
        "firewall": audit.firewall_status(),
        "updates": audit.updates_status(),
        "score": audit.score(findings),
    }


def cmd_audit(args) -> int:
    result = run_audit()
    if args.json:
        util.emit_json(result)
        return 0
    util.header("host audit")
    util.bullet("firewall", result["firewall"].get("backend", "unknown"))
    for key, value in result["updates"].items():
        util.bullet(key[:12], value)
    util.header("findings")
    if not result["findings"]:
        print("  nothing obvious found")
    for item in result["findings"]:
        colour = {"high": "red", "medium": "yellow", "critical": "red"}.get(
            item.get("severity", ""), "dim"
        )
        print(f"  {util.style(item.get('severity', '').upper(), colour):<18} {item['title']}")
        if item.get("advice"):
            print(f"  {'':<18} {util.style(item['advice'], 'dim')}")
    print()
    print(f"  score: {util.style(str(result['score']) + '/100', 'bold')}")
    config.append_history("audit", f"score {result['score']}")
    return 0


def cmd_score(args) -> int:
    result = run_audit()
    if args.json:
        util.emit_json({"score": result["score"], "findings": len(result["findings"])})
        return 0
    util.header("security score")
    score = result["score"]
    colour = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    print(f"  {util.style(str(score), 'bold', colour)} / 100")
    print(f"  findings: {len(result['findings'])}")
    return 0


def cmd_firewall(args) -> int:
    result = audit.firewall_status()
    if args.json:
        util.emit_json(result)
        return 0
    util.header("firewall")
    for key, value in result.items():
        util.bullet(key, value)
    return 0


def cmd_updates(args) -> int:
    result = audit.updates_status()
    if args.json:
        util.emit_json(result)
        return 0
    util.header("updates")
    for key, value in result.items():
        util.bullet(key, value)
    return 0


def cmd_report(args) -> int:
    out_dir = Path(args.output) if args.output else Path.cwd()
    me = collect_me(with_public=True)
    data = {
        "me": {
            "hostname": me["hostname"].get("hostname", ""),
            "ipv4": me["ipv4"],
            "macs": me["macs"],
            "gateway": me["gateway"],
            "dns": me["dns"],
            "public_ip": me["public_ip"],
        },
        "devices": lanscan.scan(sweep=not args.no_sweep, timeout_ms=args.timeout),
        "listening": ports.listening_ports(),
        "findings": audit.collect_findings(),
    }
    data["score"] = audit.score(data["findings"])
    if args.json:
        util.emit_json(data)
        return 0
    paths = report.write(data, out_dir)
    util.header("report written")
    for path in paths:
        util.bullet("file", str(path))
    util.bullet("score", f"{data['score']}/100")
    config.append_history("report", f"{len(data['devices'])} devices")
    return 0


def cmd_export(args) -> int:
    out = Path(args.output or "report.json")
    data = {
        "me": collect_me(with_public=False),
        "devices": lanscan.scan(sweep=not args.no_sweep),
        "listening": ports.listening_ports(),
    }
    if args.format == "md":
        out = out.with_suffix(".md")
        out.write_text(report.build(data), encoding="utf-8")
    elif args.format == "csv":
        import csv

        out = out.with_suffix(".csv")
        with out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["ip", "mac", "vendor", "hostname", "is_me"])
            for d in data["devices"]:
                writer.writerow([d["ip"], d["mac"], d["vendor"], d.get("hostname", ""), d.get("is_me")])
    elif args.format == "html":
        out = out.with_suffix(".html")
        import html as html_mod

        body = report.build(data)
        out.write_text(
            "<!doctype html><meta charset='utf-8'><title>NetPeek report</title>"
            "<style>body{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}"
            "table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}</style>"
            "<pre>" + html_mod.escape(body) + "</pre>",
            encoding="utf-8",
        )
    else:
        import json

        out = out.with_suffix(".json")
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"written: {out}")
    return 0


def cmd_diff(args) -> int:
    try:
        result = report.diff(Path(args.old), Path(args.new))
    except (OSError, ValueError) as exc:
        util.warn(f"cannot compare reports: {exc}")
        return 2
    if args.json:
        util.emit_json(result)
        return 0
    util.header("new devices")
    for d in result["added"]:
        print(f"  + {d['ip']:<16} {d['mac']}  {d.get('vendor', '')}")
    util.header("gone")
    for d in result["removed"]:
        print(f"  - {d['ip']:<16} {d['mac']}  {d.get('vendor', '')}")
    util.header("changed")
    for d in result["changed"]:
        print(f"  ~ {d['ip']:<16} {d['mac']}")
    return 0


def cmd_history(args) -> int:
    entries = config.read_history(limit=args.limit)
    if args.json:
        util.emit_json(entries)
        return 0
    util.header("history")
    if not entries:
        print("  no history yet")
    for entry in entries:
        print(f"  {entry.get('time', ''):<28} {entry.get('command', ''):<10} {entry.get('summary', '')}")
    return 0


def cmd_watch(args) -> int:
    if args.json:
        util.warn("--json is not supported with watch")
        return 2
    util.header(f"watching your network every {args.interval}s — Ctrl+C to stop")
    previous = {}
    try:
        while True:
            devices = lanscan.scan(sweep=True, timeout_ms=args.timeout)
            current = {d["ip"]: d for d in devices}
            for ip, dev in current.items():
                if ip not in previous:
                    print(f"  {util.style('+ joined', 'green'):<20} {ip:<16} {dev['mac']}  {dev.get('vendor', '')}")
            for ip, dev in previous.items():
                if ip not in current:
                    print(f"  {util.style('- left', 'yellow'):<20} {ip:<16} {dev['mac']}")
            previous = current
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()
        print("  stopped")
        return 0


def cmd_init(args) -> int:
    path = config.init(force=args.force)
    util.header("config")
    util.bullet("file", str(path))
    return 0


def cmd_config(args) -> int:
    if args.action == "set":
        if not args.key or args.value is None:
            util.warn("usage: config set <section.key> <value>")
            return 2
        path = config.set_value(args.key, args.value)
        util.header("config updated")
        util.bullet("file", str(path))
        util.bullet("key", args.key)
        util.bullet("value", args.value)
        return 0
    if args.action == "get":
        value = config.get(args.key or "")
        if value is None:
            util.warn(f"unknown key: {args.key}")
            return 2
        print(value)
        return 0
    path = config.init()
    cfg = config.load()
    if args.json:
        util.emit_json(cfg)
        return 0
    util.header("config")
    util.bullet("file", str(path))
    for section, values in cfg.items():
        util.header(section)
        if isinstance(values, dict):
            for key, value in values.items():
                util.bullet(key, value)
        else:
            util.bullet(section, values)
    return 0


def cmd_update(args) -> int:
    """Refresh local data (vendor table). Code is updated with pip."""
    util.header("update data")
    util.bullet("vendors", f"{len(netinfo._OUI)} built-in entries")
    util.bullet("python", sys.version.split()[0])
    util.bullet("netpeek", __version__)
    util.bullet("config", str(config.config_dir()))
    print()
    print("  To update the code itself: pip install --upgrade netpeek")
    return 0


def cmd_version(args) -> int:
    print(f"{program_name()} {__version__}  (python {sys.version.split()[0]})")
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #


def build_parser(name: Optional[str] = None) -> argparse.ArgumentParser:
    name = name or program_name()
    parser = argparse.ArgumentParser(
        prog=name,
        description=(
            f"{name} — a legal, read-only look at your own network: "
            "who is connected, your IP/MAC/DNS, listening ports and a security score."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--no-color", action="store_true", help="disable ANSI colour output"
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def add(name, func, help_text, aliases=()):
        p = sub.add_parser(name, help=help_text, description=help_text, aliases=list(aliases))
        p.set_defaults(func=func)
        p.add_argument("--json", action="store_true", help="machine-readable JSON output")
        p.add_argument("--no-color", action="store_true", help="disable ANSI colour output")
        return p

    # --- about my device ---------------------------------------------------
    p = add("me", cmd_me, "Full report about THIS device (IP, MAC, DNS, gateway, ports, connections).", aliases=["info"])
    p.add_argument("--ip", action="store_true", help="only IP addresses")
    p.add_argument("--mac", action="store_true", help="only MAC addresses")
    p.add_argument("--dns", action="store_true", help="only DNS servers")
    p.add_argument("--ports", dest="ports_", action="store_true", help="only listening ports")
    p.add_argument("--conns", action="store_true", help="only active connections")
    p.add_argument("--wifi", action="store_true", help="only Wi-Fi information")
    p.add_argument("--gateway", action="store_true", help="only the gateway")

    add("myip", cmd_myip, "Public IP address and its country/provider.")

    add("ip", cmd_ip, "Local (IPv4/IPv6), public IP and your subnets.")
    add("mac", cmd_mac, "MAC address of every interface with the hardware vendor.")
    add("gateway", cmd_gateway, "Default gateway and configured DNS servers.")
    p = add("dns", cmd_dns, "DNS servers, or records + SPF/DMARC/DKIM check for a domain.")
    p.add_argument("domain", nargs="?", help="domain to look up (optional)")
    add("myports", cmd_myports, "Which ports THIS device is listening on.")
    p = add("conns", cmd_conns, "Active established connections of this device.")
    p.add_argument("--limit", type=int, default=50, help="max rows (default 50)")
    add("wifi", cmd_wifi, "Wi-Fi SSID, signal, channel and security of this machine.")

    # --- my network --------------------------------------------------------
    p = add("scan", cmd_scan, "Who is connected to your LAN right now (ARP + ping sweep).", aliases=["devices"])
    p.add_argument("--network", help="only this subnet, e.g. 192.168.1.0/24")
    p.add_argument("--no-sweep", action="store_true", help="read the ARP cache only (fast, passive)")
    p.add_argument("--timeout", type=int, default=400, help="ping timeout in ms (default 400)")
    p.add_argument("--resolve", action="store_true", help="also resolve hostnames (slow)")

    p = add("ports", cmd_ports, "Open TCP ports of a host ON YOUR OWN network.")
    p.add_argument("host", help="IP address inside your local subnet (or this machine)")
    p.add_argument("--range", help="port list/range, e.g. 22,80,1000-1010 (default: common ports)")
    p.add_argument("--timeout", type=float, default=0.4, help="per-port timeout in seconds")
    p.add_argument("--dry-run", action="store_true", help="validate the target, scan nothing")

    p = add("banner", cmd_banner, "Read the service banner of a host on your network.")
    p.add_argument("host")
    p.add_argument("port", type=int)

    p = add("subnet", cmd_subnet, "Break down a subnet: mask, range, host count.")
    p.add_argument("network", nargs="?", help="e.g. 192.168.1.0/24 (default: detected LAN)")

    # --- public data -------------------------------------------------------
    p = add("whois", cmd_whois, "Registrar / network owner for a domain or IP (public data).")
    p.add_argument("target")

    p = add("tls", cmd_tls, "TLS certificate of a site: issuer and expiry.")
    p.add_argument("host")
    p.add_argument("--port", type=int, default=443)

    # --- health ------------------------------------------------------------
    add("audit", cmd_audit, "Checks for this host: exposed ports, firewall, updates.")
    add("score", cmd_score, "Security score (0-100) with the top findings.")
    add("firewall", cmd_firewall, "Firewall status for this machine.")
    add("updates", cmd_updates, "Latest OS update information.")

    # --- reports -----------------------------------------------------------
    p = add("report", cmd_report, "Collect everything and write report.md + report.json.")
    p.add_argument("--output", help="directory for the report (default: current)")
    p.add_argument("--no-sweep", action="store_true", help="passive ARP only")
    p.add_argument("--timeout", type=int, default=400)

    p = add("export", cmd_export, "Export the current snapshot as md/json/csv/html.")
    p.add_argument("--format", choices=["md", "json", "csv", "html"], default="json")
    p.add_argument("--output", help="output file (extension is fixed per format)")
    p.add_argument("--no-sweep", action="store_true")

    p = add("diff", cmd_diff, "Compare two report.json files.")
    p.add_argument("old")
    p.add_argument("new")

    # --- watch / history ---------------------------------------------------
    p = add("watch", cmd_watch, "Repeat scan and report devices joining/leaving.")
    p.add_argument("--interval", type=int, default=60, help="seconds between scans")
    p.add_argument("--timeout", type=int, default=400)

    p = add("history", cmd_history, "Your recent NetPeek commands (local log).")
    p.add_argument("--limit", type=int, default=20)

    # --- config ------------------------------------------------------------
    p = add("init", cmd_init, "Create the local config file (see the `config` command).")
    p.add_argument("--force", action="store_true", help="overwrite an existing config")

    p = add("config", cmd_config, "Show or change settings.")
    p.add_argument("action", nargs="?", choices=["show", "get", "set"], default="show")
    p.add_argument("key", nargs="?", help="section.key for get/set")
    p.add_argument("value", nargs="?", help="new value for set")

    add("update", cmd_update, "Refresh local data tables.")
    add("version", cmd_version, "Print the version.")

    return parser


def run(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(program_name())
    args = parser.parse_args(argv)

    util.configure(no_color=getattr(args, "no_color", False) or not supports_ansi())
    if getattr(args, "json", False):
        util.configure(no_color=True)

    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    if os.name == "nt":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - old Python
            import io

            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )

    try:
        return int(args.func(args) or 0)
    except guard.NotAllowed as exc:
        util.warn(str(exc))
        return 2
    except KeyboardInterrupt:
        print()
        return 130
    except BrokenPipeError:  # e.g. `netpeek scan | head`
        return 0
