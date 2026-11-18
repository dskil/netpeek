#!/usr/bin/env sh
# Prints the Python launcher to use. Works on Windows (Git Bash) too.

set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)

# 1) A project venv always wins.
if [ -x "$HERE/.venv/Scripts/python.exe" ]; then
    echo "$HERE/.venv/Scripts/python.exe"
    exit 0
fi
if [ -x "$HERE/.venv/bin/python" ]; then
    echo "$HERE/.venv/bin/python"
    exit 0
fi

# 2) Then whichever Python is on PATH.
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
            echo "$candidate"
            exit 0
        fi
    fi
done

echo ""
exit 1
