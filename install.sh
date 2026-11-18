#!/usr/bin/env sh
# NetPeek / fsociety - make `netpeek` and `fsociety` available in every
# terminal, using an isolated virtual environment (nothing global changes).
#
# Usage:  ./install.sh
#         ./install.sh --dry-run     (show what would happen)
#
# What it does:
#   1. creates .venv in this folder (needs Python 3.9+)
#   2. pip installs this package into it
#   3. adds .venv/bin to your PATH in your shell rc file (no sudo needed)
#   4. prints how to remove everything again (./uninstall.sh)

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
VENV="$HERE/.venv"
BIN="$VENV/bin"

DRY=0
case "${1:-}" in
    --dry-run|-n) DRY=1 ;;
esac

echo
echo " NetPeek / fsociety installer"
echo " ============================"
echo "  project : $HERE"
echo "  venv    : $VENV"
echo "  PATH    : $BIN"
echo

# ----------------------------------------------------------------------- #
# 1. Find Python
# ----------------------------------------------------------------------- #

PY=$(sh "$HERE/.find-python.sh" 2>/dev/null || true)

if [ -z "$PY" ]; then
    echo "  [X] Python 3.9+ was not found."
    echo "      Install it, e.g.  sudo apt install python3 python3-venv"
    exit 9009
fi

echo "  [ok] Python: $("$PY" --version 2>&1)"

if [ "$DRY" -eq 1 ]; then
    echo
    echo "  DRY RUN - nothing was changed."
    echo "    would create : $VENV"
    echo "    would install: pip install \"$HERE\""
    echo "    would add    : $BIN to PATH in the shell rc file"
    exit 0
fi

# ----------------------------------------------------------------------- #
# 2. Virtual environment
# ----------------------------------------------------------------------- #

if [ -x "$BIN/python" ]; then
    echo "  [ok] virtual environment already exists"
else
    echo "  [..] creating virtual environment"
    if ! "$PY" -m venv "$VENV"; then
        echo "  [X] could not create the virtual environment."
        echo "      Debian/Ubuntu:  sudo apt install python3-venv"
        exit 1
    fi
    echo "  [ok] virtual environment created"
fi

# ----------------------------------------------------------------------- #
# 3. Install
# ----------------------------------------------------------------------- #

echo "  [..] installing netpeek into the venv"
"$BIN/python" -m pip install --quiet --disable-pip-version-check --upgrade pip
if ! "$BIN/python" -m pip install --quiet --disable-pip-version-check "$HERE"; then
    echo "  [X] installation failed."
    exit 1
fi
echo "  [ok] netpeek installed"

# ----------------------------------------------------------------------- #
# 4. PATH
# ----------------------------------------------------------------------- #

SHELL_NAME=$(basename "${SHELL:-sh}")
case "$SHELL_NAME" in
    zsh)  RC="$HOME/.zshrc" ;;
    bash) RC="$HOME/.bashrc" ;;
    *)    RC="$HOME/.profile" ;;
esac

MARKER="# >>> netpeek >>>"
if [ -f "$RC" ] && grep -qF "$MARKER" "$RC"; then
    echo "  [ok] PATH entry already present in $RC"
else
    echo "  [..] adding $BIN to PATH in $RC"
    {
        echo ""
        echo "$MARKER"
        echo "export PATH=\"$BIN:\$PATH\""
        echo "# <<< netpeek <<<"
    } >> "$RC"
    echo "  [ok] PATH updated"
fi

# ----------------------------------------------------------------------- #
# 5. Verify
# ----------------------------------------------------------------------- #

echo
echo "  Checking the installation:"
"$BIN/netpeek" version || { echo "  [X] netpeek did not run."; exit 1; }
"$BIN/fsociety" version || { echo "  [X] fsociety did not run."; exit 1; }

echo
echo "  Done."
echo
echo "    open a NEW terminal (or run: source \"$RC\") and try:"
echo "        netpeek --help"
echo "        netpeek me"
echo "        fsociety --help"
echo
echo "    to remove everything:  ./uninstall.sh"
echo
