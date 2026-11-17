"""Unit tests for NetPeek. No network access is required."""

from __future__ import annotations

import ipaddress

import pytest

from netpeek import guard, util
from netpeek.scanner import parse_ports


# --------------------------------------------------------------------------- #
# MAC helpers
# --------------------------------------------------------------------------- #


def test_normalise_mac_accepts_common_formats():
    from netpeek.netinfo import normalise_mac

    assert normalise_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"
    assert normalise_mac("AA-BB-CC-DD-EE-FF") == "AA:BB:CC:DD:EE:FF"
    assert normalise_mac("aabb.ccdd.eeff") == "AA:BB:CC:DD:EE:FF"
    assert normalise_mac("") == ""
    assert normalise_mac("not-a-mac") == ""


def test_mac_vendor_known_and_private():
    from netpeek.netinfo import mac_vendor

    assert mac_vendor("00:0C:29:11:22:33") == "VMware"
    assert mac_vendor("02:50:DE:AC:78:56").startswith("Private")
    assert mac_vendor("00:11:22:33:44:55") == "Unknown vendor"
    assert mac_vendor("") == ""


# --------------------------------------------------------------------------- #
# IP helpers
# --------------------------------------------------------------------------- #


def test_parse_ip():
    assert str(util.parse_ip("192.168.1.1")) == "192.168.1.1"
    assert util.parse_ip("999.1.1.1") is None


def test_is_private_lan():
    assert util.is_private_lan("192.168.1.10")
    assert util.is_private_lan("10.0.0.1")
    assert not util.is_private_lan("8.8.8.8")
    assert not util.is_private_lan("127.0.0.1")
    assert not util.is_private_lan("169.254.1.1")


def test_ip_sort_key_orders_numerically():
    ips = ["192.168.1.100", "192.168.1.2", "192.168.1.20"]
    assert sorted(ips, key=util.ip_sort_key) == [
        "192.168.1.2",
        "192.168.1.20",
        "192.168.1.100",
    ]


# --------------------------------------------------------------------------- #
# Guard — the legality boundary
# --------------------------------------------------------------------------- #


def test_guard_allows_local_target():
    g = guard.Guard([ipaddress.ip_network("192.168.1.0/24")])
    assert g.check("192.168.1.10") == "192.168.1.10"


def test_guard_allows_loopback():
    g = guard.Guard([])
    assert g.check("127.0.0.1") == "127.0.0.1"


def test_guard_refuses_public_ip():
    g = guard.Guard([ipaddress.ip_network("192.168.1.0/24")])
    with pytest.raises(guard.NotAllowed):
        g.check("8.8.8.8")


def test_guard_refuses_invalid():
    g = guard.Guard([ipaddress.ip_network("192.168.1.0/24")])
    with pytest.raises(guard.NotAllowed):
        g.check("example.com")


def test_guard_accepts_own_addresses():
    g = guard.Guard([ipaddress.ip_network("10.1.0.0/16")])
    g.my_ips = {"10.1.2.3"}
    assert g.check("10.1.2.3") == "10.1.2.3"


# --------------------------------------------------------------------------- #
# Port parsing
# --------------------------------------------------------------------------- #


def test_parse_ports_list():
    assert parse_ports("22,80,443") == [22, 80, 443]


def test_parse_ports_range():
    assert parse_ports("1000-1003") == [1000, 1001, 1002, 1003]


def test_parse_ports_mixed_and_sorted():
    assert parse_ports("443,22,100-101") == [22, 100, 101, 443]


@pytest.mark.parametrize("spec", ["", "abc", "10-5", "22,", "-20"])
def test_parse_ports_rejects_bad_input(spec):
    with pytest.raises(ValueError):
        parse_ports(spec)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def test_score_caps_at_zero():
    from netpeek.audit import score

    findings = [{"severity": "critical"} for _ in range(10)]
    assert score(findings) == 0


def test_score_without_findings_is_perfect():
    from netpeek.audit import score

    assert score([]) == 100


# --------------------------------------------------------------------------- #
# Programme name / aliases
# --------------------------------------------------------------------------- #


def test_parser_uses_given_programme_name():
    from netpeek.main import build_parser

    assert "netpeek" in build_parser("netpeek").prog
    assert "fsociety" in build_parser("fsociety").prog


@pytest.mark.parametrize("alias", ["netpeek", "fsociety"])
def test_both_aliases_expose_the_same_commands(alias, monkeypatch):
    from netpeek import main

    monkeypatch.setattr(main.sys, "argv", [alias])
    parser = main.build_parser(alias)
    commands = parser._subparsers._group_actions[0].choices  # type: ignore[union-attr]
    assert {"me", "scan", "ports", "report", "dns"} <= set(commands)


def test_every_command_has_help():
    import argparse

    from netpeek.main import build_parser

    parser = build_parser("netpeek")
    sub = parser._subparsers._group_actions[0]  # type: ignore[union-attr]
    assert isinstance(sub, argparse._SubParsersAction)
    for name, action in sub.choices.items():
        assert action.description, f"command {name} lacks a description"
        assert action.format_help(), f"command {name} lacks help output"


def test_me_has_help_with_its_options(capsys):
    from netpeek.main import run

    with pytest.raises(SystemExit) as exc:
        run(["me", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for option in ("--ip", "--mac", "--dns", "--ports", "--conns", "--wifi", "--json"):
        assert option in out
