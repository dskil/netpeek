"""Self-check for NetPeek before publishing.

Runs the same checks a reviewer would run, and prints a clear PASS/FAIL report.

    python scripts/check_before_publish.py

Nothing here changes your system: it inspects files, runs the CLI in a
temporary directory and (optionally) checks the installed console scripts.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

# Make `import netpeek` work even when the package is not installed.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

results: List[Tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not ok else ""))


def run(args: List[str], cwd: Path = ROOT, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        timeout=timeout,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )


def cli(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return run([PY, "-m", "netpeek", *args], cwd=cwd)


# --------------------------------------------------------------------------- #
# 1. Repository hygiene
# --------------------------------------------------------------------------- #


def check_files() -> None:
    required = [
        "README.md",
        "LICENSE",
        "pyproject.toml",
        ".gitignore",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "netpeek/__init__.py",
        "netpeek/main.py",
        "tests/test_core.py",
        ".github/workflows/tests.yml",
    ]
    missing = [f for f in required if not (ROOT / f).is_file()]
    check("required files present", not missing, ", ".join(missing))

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    check("both console scripts declared",
          "netpeek = " in text and "fsociety = " in text)
    check("no REPLACE_ME placeholders left", "REPLACE_ME" not in text)

    # Looking for a *real* machine's address accidentally committed. Examples
    # in docs, well-known public resolvers used as test targets, RFC5737
    # documentation ranges and reserved blocks are all fine.
    import ipaddress

    ALLOWED = {"8.8.8.8", "1.1.1.1", "255.255.255.0", "999.1.1.1"}
    leaks = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix not in {".py", ".md", ".toml", ".yml", ".yaml", ".txt"}:
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", body):
            ip = match.group(1)
            if ip in ALLOWED:
                continue
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            # Private, loopback, link-local, multicast, reserved and the
            # documentation ranges are all harmless.
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_multicast
                or addr in ipaddress.ip_network("192.0.2.0/24")
                or addr in ipaddress.ip_network("198.51.100.0/24")
                or addr in ipaddress.ip_network("203.0.113.0/24")
            ):
                continue
            leaks.append(f"{path.relative_to(ROOT)}: {ip}")
    check("no real (public) IPs committed in docs/code", not leaks, ", ".join(leaks))

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    check("reports are git-ignored", "report.md" in gitignore and "report.json" in gitignore)


# --------------------------------------------------------------------------- #
# 2. Tests
# --------------------------------------------------------------------------- #


def check_tests() -> None:
    proc = run([PY, "-m", "pytest", "-q"], timeout=600)
    out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
    check("pytest suite passes", proc.returncode == 0, out.strip().splitlines()[-1] if out else "")


# --------------------------------------------------------------------------- #
# 3. CLI surface
# --------------------------------------------------------------------------- #

COMMANDS = [
    "me", "ip", "mac", "gateway", "dns", "myports", "conns", "wifi", "myip",
    "scan", "ports", "banner", "subnet", "whois", "tls",
    "audit", "score", "firewall", "updates",
    "report", "export", "diff", "watch", "history",
    "init", "config", "update", "version",
]


def check_help() -> None:
    proc = cli("--help", "--no-color")
    top = proc.stdout.decode("utf-8", "replace")
    check("`netpeek --help` works", proc.returncode == 0 and "usage:" in top)
    missing = [c for c in COMMANDS if c not in top]
    check("every command listed in --help", not missing, ", ".join(missing))

    broken = []
    for cmd in COMMANDS:
        if cmd == "version":
            continue
        p = cli(cmd, "--help")
        if p.returncode != 0:
            broken.append(cmd)
    check("`netpeek <cmd> --help` works for all commands", not broken, ", ".join(broken))

    me_help = cli("me", "--help").stdout.decode("utf-8", "replace")
    wanted = ["--ip", "--mac", "--dns", "--ports", "--conns", "--wifi", "--gateway", "--json"]
    check("`me --help` documents its flags",
          all(w in me_help for w in wanted),
          ", ".join(w for w in wanted if w not in me_help))

    check("`--version` works", "netpeek" in cli("--version").stdout.decode("utf-8", "replace"))


def check_aliases() -> None:
    """Both names must expose the same commands."""
    from netpeek.main import build_parser  # noqa: WPS433

    def commands(name: str) -> set:
        parser = build_parser(name)
        sub = parser._subparsers._group_actions[0]  # type: ignore[union-attr]
        return set(sub.choices)

    net = commands("netpeek")
    fs = commands("fsociety")
    check("netpeek and fsociety expose identical commands", net == fs,
          f"diff: {net ^ fs}")

    a = build_parser("netpeek").format_help().replace("netpeek", "X")
    b = build_parser("fsociety").format_help().replace("fsociety", "X")
    check("help text is identical apart from the name", a == b)


# --------------------------------------------------------------------------- #
# 4. Safety: the guard must refuse foreign targets
# --------------------------------------------------------------------------- #


def check_guard() -> None:
    proc = cli("ports", "8.8.8.8", "--no-color")
    out = proc.stdout.decode("utf-8", "replace")
    check("`ports 8.8.8.8` is refused", proc.returncode == 2 and "outside your local network" in out)

    proc = cli("ports", "1.1.1.1", "--json")
    check("refusal also applies with --json", proc.returncode == 2)

    proc = cli("ports", "not-an-ip")
    check("invalid target is rejected", proc.returncode == 2)


# --------------------------------------------------------------------------- #
# 5. Real commands on this machine
# --------------------------------------------------------------------------- #


def check_commands() -> None:
    cases = [
        (("me", "--ip", "--no-color"), ["IP"]),
        (("me", "--mac", "--no-color"), ["MAC"]),
        (("me", "--ports", "--no-color"), ["LISTENING PORTS"]),
        (("myip", "--no-color"), ["PUBLIC IP"]),
        (("subnet", "--no-color"), ["SUBNET"]),
        (("scan", "--no-sweep", "--no-color"), ["DEVICES"]),
        (("score", "--no-color"), ["SECURITY SCORE"]),
    ]
    for args, needles in cases:
        proc = cli(*args)
        out = proc.stdout.decode("utf-8", "replace")
        ok = proc.returncode == 0 and all(n in out for n in needles)
        check(f"`netpeek {' '.join(args)}`", ok,
              (proc.stderr.decode("utf-8", "replace") or out)[-160:])

    proc = cli("me", "--ip", "--json")
    ok = proc.returncode == 0 and proc.stdout.lstrip().startswith(b"{")
    check("`--json` returns valid JSON", ok)


def check_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        proc = cli("report", "--output", tmp, "--no-sweep")
        md = Path(tmp) / "report.md"
        js = Path(tmp) / "report.json"
        ok = proc.returncode == 0 and md.is_file() and js.is_file()
        check("`report` writes report.md + report.json", ok)
        if ok:
            body = md.read_text(encoding="utf-8")
            check("report has the expected sections",
                  all(s in body for s in ("This device", "Connected devices",
                                          "Listening ports", "Findings", "Score")))


# --------------------------------------------------------------------------- #
# 6. Packaging
# --------------------------------------------------------------------------- #


def check_packaging() -> None:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.9/3.10
        tomllib = None  # type: ignore

    if tomllib is not None:
        with (ROOT / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        scripts = data.get("project", {}).get("scripts", {})
        check("entry points resolve to netpeek.main:run",
              scripts.get("netpeek") == "netpeek.main:run"
              and scripts.get("fsociety") == "netpeek.main:run")
        check("requires-python is declared",
              bool(data.get("project", {}).get("requires-python")))

    proc = run([PY, "-m", "build", "--version"])
    if proc.returncode != 0:
        check("sdist/wheel build (skipped: `pip install build` to enable)", True)
        return
    with tempfile.TemporaryDirectory() as tmp:
        proc = run([PY, "-m", "build", "--outdir", tmp], timeout=600)
        built = sorted(p.name for p in Path(tmp).iterdir()) if Path(tmp).exists() else []
        check("package builds (sdist + wheel)",
              proc.returncode == 0 and any(b.endswith(".whl") for b in built),
              ", ".join(built))


# --------------------------------------------------------------------------- #


def main() -> int:
    print(f"Checking {ROOT}\n")
    for fn in (check_files, check_tests, check_help, check_aliases,
               check_guard, check_commands, check_report, check_packaging):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(f"{fn.__name__} crashed", False, f"{type(exc).__name__}: {exc}")

    failed = [name for name, ok, _ in results if not ok]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILED:")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("Everything looks ready to publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
