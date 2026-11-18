# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] — 2026-11-18

First stable release. NetPeek is now installable with a single command:

```bash
pipx install netpeek      # or: pip install netpeek
```

### Added

- **Two command names, one tool.** `netpeek` and `fsociety` are published from
  the same package and expose exactly the same commands.
- **`me`** — full passport of this device: interfaces, IPv4/IPv6, MAC +
  hardware vendor, gateway, DNS, listening ports with the owning process,
  active connections and Wi-Fi details. Narrow it with `--ip`, `--mac`,
  `--dns`, `--ports`, `--conns`, `--wifi`, `--gateway`.
- **`scan`** — devices on your LAN: reads the ARP cache and, unless
  `--no-sweep` is given, runs a bounded ICMP sweep over the private subnets
  this machine is attached to. `--resolve` adds reverse-DNS names.
- **`ports` / `banner`** — connect()-only TCP scan and service banner reader
  for hosts on your own network, with a `--range` parser (`22,80,1000-1010`)
  and `--dry-run`.
- **Public lookups** — `myip` (public IP, country, provider), `dns`
  (A/AAAA/MX/NS/TXT/CNAME plus SPF, DMARC and DKIM checks), `whois` (RDAP with
  a system-whois fallback) and `tls` (issuer and expiry from the certificate).
- **Health checks** — `audit`, `score`, `firewall` and `updates` for this host,
  with advisory findings and a 0–100 score.
- **Reports** — `report` writes `report.md` plus `report.json`, `export`
  produces md/json/csv/html, and `diff` compares two snapshots.
- **`watch`** — repeats the scan and prints devices joining or leaving.
- **Configuration** — `init` and `config` manage
  `~/.config/netpeek/config.toml`; `history` shows your recent runs.
- **`--json`** on every read-only command, plus `--no-color` and automatic
  colour detection when output is piped.

### Security

- A hard guard (`netpeek/guard.py`) refuses every active target that is not
  loopback, not this machine, or not inside one of the private subnets the
  machine is directly connected to. The rule is covered by tests.
- No command modifies the system, captures credentials or sends data anywhere
  except the public services it queries.
- External commands are always invoked as argument lists, never through a
  shell, so user input cannot inject shell syntax.

### Packaging

- Both command names are declared as console scripts in `pyproject.toml`.
- Zero mandatory runtime dependencies; `dnspython` is an optional extra that
  upgrades the `dns` command.
- `install.cmd` / `install.sh` set up an isolated `.venv` on the user PATH,
  and `netpeek.bat` / `bin/netpeek` run straight from a checkout with no
  install at all.

[Unreleased]: https://github.com/dskil/netpeek/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/dskil/netpeek/releases/tag/v1.0.0
