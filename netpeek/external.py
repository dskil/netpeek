"""Public-data lookups: my public IP, DNS records, whois and TLS certificates.

These commands never touch the local network; they query public services
(the DNS, a whois server, the website you ask about).
"""

from __future__ import annotations

import json
import re
import socket
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import util

IP_ENDPOINTS = [
    ("https://api.ipify.org?format=json", "json", "ip"),
    ("https://ifconfig.me/all.json", "json", "ip_addr"),
    ("https://ident.me", "text", ""),
]


def _http_get(url: str, timeout: float = 6.0) -> Optional[bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "netpeek/0.1 (+https://github.com/)",
            "Accept": "application/rdap+json, application/json, */*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(200_000)
    except Exception:
        return None


def public_ip() -> str:
    """Ask a few public services for this machine's egress IP."""
    for url, kind, key in IP_ENDPOINTS:
        raw = _http_get(url)
        if not raw:
            continue
        text = raw.decode("utf-8", "replace").strip()
        if kind == "json":
            try:
                data = json.loads(text)
            except ValueError:
                continue
            value = data.get(key) if key else None
            if value:
                return str(value)
        elif text and re.fullmatch(r"[0-9a-fA-F:.]+", text):
            return text
    return ""


def ip_details(ip: str) -> dict:
    """Country / provider / ASN for an IP (public, rate-limited service)."""
    raw = _http_get(f"https://ipinfo.io/{ip}/json")
    if not raw:
        return {"ip": ip}
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return {"ip": ip}
    return {
        "ip": data.get("ip", ip),
        "country": data.get("country", ""),
        "city": data.get("city", ""),
        "org": data.get("org", ""),
        "hostname": data.get("hostname", ""),
    }


# --------------------------------------------------------------------------- #
# DNS
# --------------------------------------------------------------------------- #

# Only these record types are accepted, which keeps the argument space closed.
DNS_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA", "SRV")


def dns_query(domain: str, rtype: str = "A") -> List[str]:
    rtype = rtype.upper()
    if rtype not in DNS_TYPES:
        raise ValueError(f"unsupported record type: {rtype}")
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        if rtype in ("A", "AAAA"):
            family = socket.AF_INET if rtype == "A" else socket.AF_INET6
            try:
                infos = socket.getaddrinfo(domain, None, family)
            except OSError:
                return []
            return sorted({info[4][0] for info in infos})
        return []
    try:
        answers = dns.resolver.resolve(domain, rtype, lifetime=5)
    except Exception:
        return []
    out = []
    for answer in answers:
        try:
            if rtype == "MX":
                out.append(f"{answer.preference} {answer.exchange}")
            else:
                out.append(answer.to_text())
        except AttributeError:
            out.append(str(answer))
    return sorted(out)


def dns_report(domain: str) -> dict:
    report: Dict[str, object] = {"domain": domain, "records": {}}
    for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME"):
        values = dns_query(domain, rtype)
        if values:
            report["records"][rtype] = values  # type: ignore[index]

    txt = report["records"].get("TXT", [])  # type: ignore[index]
    txt_text = " ".join(txt) if isinstance(txt, list) else ""
    report["spf"] = next(
        (v.strip('"') for v in re.findall(r'"v=spf1[^"]*"', txt_text)), ""
    )
    dmarc = dns_query(f"_dmarc.{domain}", "TXT")
    report["dmarc"] = " ".join(dmarc).strip('"') if dmarc else ""
    dkim_common = []
    for selector in ("default", "google", "selector1", "k1"):
        found = dns_query(f"{selector}._domainkey.{domain}", "TXT")
        if found:
            dkim_common.append(selector)
    report["dkim_selectors"] = dkim_common

    checks = []
    if not report["spf"]:
        checks.append("SPF is missing (mail spoofing is easier)")
    if not report["dmarc"]:
        checks.append("DMARC is missing (no policy for forged mail)")
    if not dkim_common:
        checks.append("No DKIM selector found among common names")
    if not checks:
        checks.append("SPF, DMARC and DKIM look present")
    report["checks"] = checks
    return report


# --------------------------------------------------------------------------- #
# whois
# --------------------------------------------------------------------------- #

_WHOIS_FIELDS = {
    "domain": ["Domain Name", "Registrar", "Creation Date", "Registry Expiry Date", "Updated Date"],
    "net": ["NetName", "OrgName", "Organization", "Country", "CIDR"],
}


def whois(target: str) -> dict:
    target = target.strip()
    is_ip = _parse_ip(target) is not None
    url = (
        f"https://rdap.org/ip/{urllib.parse.quote(target, safe='')}"
        if is_ip
        else f"https://rdap.org/domain/{urllib.parse.quote(target, safe='')}"
    )
    raw = _http_get(url, timeout=25.0)
    if raw:
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            data = None
        if isinstance(data, dict) and not data.get("errorCode"):
            result: Dict[str, str] = {
                "query": target,
                "source": "rdap",
                "type": str(data.get("objectClassName", "")),
            }
            for entity in data.get("entities") or []:
                roles = entity.get("roles") or []
                name = ""
                vcard = entity.get("vcardArray") or [None, []]
                for item in vcard[1] if len(vcard) > 1 else []:
                    if isinstance(item, list) and item and item[0] == "fn":
                        name = str(item[3])
                        break
                if name and "registrar" in roles:
                    result["registrar"] = name
                elif name and "registrant" in roles and "registrant" not in result:
                    result["registrant"] = name
            for event in data.get("events") or []:
                action = str(event.get("eventAction", "")).replace(" ", "_")
                if action in ("registration", "expiration", "last_changed"):
                    result[action] = str(event.get("eventDate", ""))
            for key in ("handle", "ldhName", "country", "startAddress", "name"):
                if data.get(key):
                    result[key] = str(data[key])
            status = data.get("status")
            if status:
                result["status"] = ", ".join(str(s) for s in status[:4])
            if data.get("ipVersion"):
                result["ip_version"] = str(data["ipVersion"])
            if len(result) > 3:
                return result

    # Fallback: the system whois client, when present.
    output = util.run_cmd(["whois", target], timeout=20)
    if output:
        result = {"query": target, "source": "whois"}
        for line in output.splitlines():
            field, sep, value = line.partition(":")
            key = field.strip().lower().replace(" ", "_")
            if key in (
                "registrar",
                "creation_date",
                "registry_expiry_date",
                "registrant_organization",
                "country",
                "netname",
                "orgname",
            ) and key not in result:
                result[key] = value.strip()
        if len(result) > 2:
            return result
    return {"query": target, "source": "unavailable"}


def _parse_ip(value: str):
    import ipaddress

    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# TLS certificate
# --------------------------------------------------------------------------- #


def tls_info(host: str, port: int = 443) -> dict:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=6) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert() or {}
    except (OSError, ssl.SSLError) as exc:
        return {"host": host, "error": str(exc)}
    not_after = cert.get("notAfter", "")
    days_left = None
    if not_after:
        try:
            expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
                tzinfo=timezone.utc
            )
            days_left = (expires - datetime.now(timezone.utc)).days
        except ValueError:
            expires = None
    issuer = {k: v for part in cert.get("issuer", []) for k, v in part}
    subject = {k: v for part in cert.get("subject", []) for k, v in part}
    alt = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]
    return {
        "host": host,
        "subject": subject.get("commonName", ""),
        "issuer": issuer.get("organizationName", issuer.get("commonName", "")),
        "not_after": not_after,
        "days_left": days_left,
        "san": alt,
        "warning": (
            "certificate expires soon"
            if days_left is not None and days_left < 14
            else ""
        ),
    }
