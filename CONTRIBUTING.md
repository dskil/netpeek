# Contributing to NetPeek

Thanks for helping! NetPeek is deliberately small and dependency-free, and it
must stay legally safe. Please read this before opening a pull request.

## Ground rules

1. **Read-only.** No command may change the system (no file edits, no
   firewall changes, no services started).
2. **Local only.** Every active network operation must pass through
   `netpeek.guard.Guard`. A PR that scans arbitrary hosts will be rejected.
3. **No offensive tooling.** No exploits, brute force, credential capture,
   packet injection or evasion code.
4. **No mandatory dependencies.** Standard library only. Optional extras
   (like `dnspython`) must degrade gracefully.
5. **Both names.** `netpeek` and `fsociety` must always expose exactly the
   same commands — they are two entry points for one CLI.

## Development setup

```bash
git clone https://github.com/dskil/netpeek.git
cd netpeek
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[dev,dns]"
python -m pytest -q
```

Run the CLI without installing:

```bash
python -m netpeek --help
python -m netpeek me --ip
```

## Adding a command

1. Write a `cmd_<name>(args) -> int` function in `netpeek/main.py`.
   * Return `0` on success, `1` for a runtime error, `2` for a usage error.
   * Respect `args.json` — call `util.emit_json(...)` and return before any
     human-readable printing.
   * Use `util.header`, `util.bullet`, `util.warn` for output so colours and
     formatting stay consistent.
2. Register it in `build_parser()` with a `help=` string (it is the description
   in `netpeek --help`).
3. If it touches the network, put the data-gathering logic in the matching
   module (`netinfo.py`, `lanscan.py`, `ports.py`, `scanner.py`,
   `external.py`) and call it from `main.py`.
4. Add a test in `tests/` that does not require network access.
5. Update the command table in `README.md`.

## Code style

* Python 3.9 compatible, type hints where practical.
* `from __future__ import annotations` at the top of modules.
* Four-space indentation, ≤ 100 columns, no tabs.
* User-facing text in English, lower case, no emoji in output.

## Commit messages

Conventional-ish and imperative:

```
feat: add `netpeek via` to read the routing table
fix: guard refuses IPv6 link-local addresses
docs: explain exit code 2
test: cover parse_ports edge cases
```

## Pull requests

* One logical change per PR.
* `python -m pytest -q` must pass.
* Mention any platform you could not test on (Windows/Linux/macOS).
* Never commit generated reports (`report.md`, `report.json`, …).

## Reporting bugs

Open an issue with:

* OS and Python version,
* the exact command,
* what you expected vs. what happened.

Please redact your own IP addresses and MAC addresses in screenshots.
