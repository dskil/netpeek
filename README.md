# NetPeek / fsociety

**A legal, read-only look at your own network.**  
See who is connected to your Wi-Fi, what your own IP / MAC / DNS / listening
ports are, and get a security score for your machine — all from one friendly
command-line tool.

```text
$ netpeek me --ip
── IP ADDRESSES ────────────────────────────────────────
  Беспроводная сеть : 192.168.1.100  (IPv4)
  Radmin VPN        : 26.63.236.79   (IPv4)
  public            : 185.142.64.202  (AS50289 ..., RU)
  subnet            : 192.168.1.0/24
```

> **Same tool, two names.** `netpeek` and `fsociety` are the *same* package
> with the *same* commands — `fsociety` is the name for people who remember
> the show. Install once, use either.

---

## Why it is legal

NetPeek is a *diagnostic* tool, not an attack tool. By design:

| It **does** | It **never** does |
|---|---|
| Reads what the OS already knows about **this** machine | No exploits, no cracking, no brute force |
| Pings and reads the ARP table of **your own** subnet | No scanning outside your private networks |
| Connects to ports of hosts **on your network** | No data exfiltration, no modification of any system |
| Queries **public** data (DNS, whois, your own public IP) | No credentials, no passwords, no man-in-the-middle |

The guard is enforced in code, not just in the docs:
[`netpeek/guard.py`](netpeek/guard.py) refuses every active target that is not
loopback, not this machine, or not inside one of the private subnets this
machine is directly connected to.

Use it on networks you own, or where you have **written permission**. Check
your local laws — scanning even a home network you do not administer can be
illegal.

---

## Install

```bash
git clone https://github.com/dskil/netpeek.git
cd netpeek
pip install .            # gives you BOTH `netpeek` and `fsociety`
```

Optional extras:

```bash
pip install ".[dns]"     # full DNS records (MX/NS/TXT/DKIM) via dnspython
pip install ".[dev]"     # pytest, for development
```

Without the `dns` extra, `netpeek dns <domain>` still resolves A/AAAA records
using the standard library.

Requires **Python 3.9+**, no mandatory third-party dependencies, works on
Windows, Linux and macOS.

---

## Quick start

```bash
netpeek me                  # everything about this device
netpeek me --ports          # which ports THIS device is listening on
netpeek scan                # who is on my LAN right now
netpeek ports 192.168.1.1   # open ports of my router
netpeek report              # writes report.md + report.json
```

`fsociety` accepts exactly the same arguments:

```bash
fsociety scan
fsociety --help              # usage: fsociety ...
```

---

## Commands

### About my device

| Command | What it does |
|---|---|
| `me` | Full passport of this machine: interfaces, IPs, MACs, gateway, DNS, listening ports, active connections, Wi-Fi |
| `me --ip` / `--mac` / `--dns` / `--ports` / `--conns` / `--wifi` / `--gateway` | Only that section |
| `ip` | Local IPv4/IPv6, public IP and your subnets |
| `mac` | MAC of every interface + hardware vendor |
| `gateway` | Default gateway and DNS servers |
| `dns` | DNS servers in use (no argument), or records for a domain |
| `dns <domain>` | A/AAAA/MX/NS/TXT/CNAME + SPF, DMARC, DKIM check |
| `myports` | Ports **this** machine listens on, flagged if reachable from the LAN |
| `conns` | Active established TCP connections of this machine |
| `wifi` | SSID, signal, channel, cipher, security |
| `myip` | Public IP + country / city / provider |

### My network

| Command | What it does |
|---|---|
| `scan` | Devices in your LAN: ICMP sweep fills the ARP cache, then IP + MAC + vendor |
| `scan --no-sweep` | Passive: only what the ARP cache already knows (instant) |
| `scan --resolve` | Also try reverse-DNS names |
| `ports <ip> [--range 22,80,1000-1010]` | Open TCP ports of a host **on your subnet** |
| `ports <ip> --dry-run` | Validate the target without sending packets |
| `banner <ip> <port>` | Service banner (e.g. router login page headers) |
| `subnet [cidr]` | Mask, range, broadcast, usable hosts |

### Public data

| Command | What it does |
|---|---|
| `whois <domain\|ip>` | Registrar, registration/expiry dates, owner (via RDAP) |
| `tls <host>` | Certificate issuer, expiry and days left |

### Health & score

| Command | What it does |
|---|---|
| `audit` | Findings: exposed risky ports, firewall, last OS update, file permissions |
| `score` | 0–100 score with a short explanation |
| `firewall` | Firewall status (Windows Defender / ufw / firewalld / pf) |
| `updates` | Last installed OS update / pending upgrades |

### Reports & automation

| Command | What it does |
|---|---|
| `report` | Full snapshot → `report.md` + `report.json` |
| `export --format md\|json\|csv\|html` | Export the current snapshot |
| `diff old.json new.json` | Devices that appeared / disappeared / changed MAC |
| `watch [--interval 60]` | Repeat scan, print devices joining and leaving |
| `history` | Your recent NetPeek commands (local log) |

### Settings

| Command | What it does |
|---|---|
| `init` | Create `config.toml` |
| `config` / `config get <key>` / `config set <key> <value>` | Show or change settings |
| `--json` | Any read-only command can output machine-readable JSON |
| `--no-color` | Disable ANSI colours (auto-disabled when piped) |
| `version` / `--version` | Version information |

Every command supports `--help`:

```bash
netpeek --help          # list of commands
netpeek me --help       # options of `me`
netpeek ports --help    # options of `ports`
```

---

## JSON output

Every read-only command accepts `--json`, which makes scripting easy:

```bash
netpeek me --ip --json          # {"ipv4": [...], "public_ip": ...}
netpeek scan --json             # [{"ip": "...", "mac": "...", "vendor": "..."}]
netpeek ports 192.168.1.1 --json
netpeek audit --json
```

`--json` also disables colour and never splits a table across lines.

---

## Configuration

Stored outside the repository:

* Windows — `%APPDATA%\netpeek\config.toml`
* Linux/macOS — `~/.config/netpeek/config.toml`

```toml
[scan]
sweep = true          # sweep before reading the ARP cache
timeout_ms = 400      # ping timeout
workers = 64

[ports]
common_only = true
timeout_s = 0.4

[output]
colour = true

[safety]
require_local_targets = true   # keep this on
```

`netpeek config set scan.timeout_ms 800` edits it safely.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Runtime problem (offline, service unavailable) |
| `2` | Usage error — including a target **outside your network** |
| `130` | Interrupted with Ctrl+C |

---

## How it works (and why it is safe)

* **Discovery** — reads the ARP/neighbour table and, unless `--no-sweep` is
  used, sends a bounded ICMP sweep (max /22) over the private subnets the
  machine is attached to. No raw sockets, no root required.
* **Port scan** — plain TCP `connect()` on a curated port list or a range you
  choose, after the target passes the guard.
* **Passwords** — never asked, never guessed, never stored.
* **Reports** — written locally, and `report.*` is in `.gitignore` so your own
  network details don't end up on GitHub by accident.
* **Windows encoding** — helper processes are decoded explicitly so Cyrillic or
  other non-ASCII interface names come out correctly.

---

## Development

```bash
pip install ".[dev]"
python -m pytest -q
python -m netpeek --help      # runs without installing
python -m netpeek me
```

```
netpeek/
├── pyproject.toml        # two console scripts: netpeek + fsociety
├── netpeek/
│   ├── main.py           # argparse CLI, one handler per command
│   ├── netinfo.py        # interfaces, MAC, gateway, DNS, hostname, Wi-Fi
│   ├── ports.py          # listening ports & active connections
│   ├── lanscan.py        # ARP cache + ping sweep
│   ├── scanner.py        # TCP port scan + banner grab
│   ├── guard.py          # legality boundary: only local targets
│   ├── external.py       # public IP, DNS, whois, TLS
│   ├── audit.py          # findings + score
│   ├── report.py         # md/json/csv/html output and diff
│   ├── config.py         # settings + local history
│   └── util.py           # colour, subprocess, IP helpers
└── tests/
```

---

## Roadmap

- [ ] mDNS / Bonjour discovery (optional `zeroconf` package)
- [ ] HTML report with charts
- [ ] Local OUI database refresh in `update`
- [ ] `systemd`/Task Scheduler integration for `watch`

---

## Legal

NetPeek is provided for **defensive, educational and administrative use on
networks you own or are authorised to inspect**. Scanning, probing or
enumerating systems without permission may be illegal in your country.

The authors accept no liability for misuse. See [LICENSE](LICENSE) (MIT).
