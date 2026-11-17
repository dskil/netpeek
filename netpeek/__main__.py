"""Allow ``python -m netpeek`` to behave exactly like the ``netpeek`` command."""

import sys

from .main import run

if __name__ == "__main__":  # pragma: no cover - trivial wrapper
    # ``python -m`` writes through a stream created in the ANSI code page;
    # re-wrap stdout in UTF-8 so non-ASCII output survives on Windows.
    if sys.platform == "win32":
        try:
            import io

            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
            )
        except (AttributeError, ValueError):
            pass
    raise SystemExit(run())
