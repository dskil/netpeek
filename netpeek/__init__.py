"""NetPeek — a legal, read-only look at your own network.

The same code is published under two command names:

    netpeek   — the friendly, obvious name
    fsociety  — the same tool, for people who remember the show

Both entry points call :func:`netpeek.main:run` and expose exactly the same
commands.
"""

__version__ = "1.0.0"

#: Aliases that may be used on the command line.
ALIASES = ("netpeek", "fsociety")

__all__ = ["__version__", "ALIASES"]
