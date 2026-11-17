# Security policy — NetPeek / fsociety

NetPeek is a read-only diagnostic tool for **your own** network. Please keep
that promise when reporting issues.

## Intended use

* ✅ Inspecting your own machine and your own LAN.
* ✅ Network audits you have **written permission** to perform.
* ❌ Scanning, probing or enumerating networks you do not own.

If you use NetPeek outside its intended purpose, that is your responsibility,
not a vulnerability in the project.

## Scope-relevant design rules

These are security properties we want to keep. A change that breaks one of
them is a bug worth reporting:

1. `netpeek ports` and `netpeek banner` must never talk to a target outside
   the private subnets this machine is attached to, or to this machine itself.
2. No command may modify the local system (files, firewall, users, network).
3. No password, credential, cookie or payload may be captured or stored.
4. Reports must be written only to a path the user explicitly chose (or the
   current directory) and never uploaded anywhere.
5. Commands must not be run through a shell: all external calls use argument
   lists, so user-controlled values cannot inject shell syntax.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

1. Open a *private* GitHub security advisory on this repository
   ("Security" → "Report a vulnerability"), or
2. Contact the maintainer listed in `pyproject.toml`.

Include:

* affected version (`netpeek version`),
* the command you ran,
* what happened and what you expected,
* whether it breaks one of the rules above.

We aim to respond within 7 days.

## Supported versions

Only the latest release receives fixes.
