#!/usr/bin/env sh
# NetPeek / fsociety - undo what install.sh did.
# Removes the PATH entry and deletes .venv. Your repository is untouched.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
VENV="$HERE/.venv"
BIN="$VENV/bin"

echo
echo " NetPeek / fsociety uninstaller"
echo " =============================="
echo

SHELL_NAME=$(basename "${SHELL:-sh}")
case "$SHELL_NAME" in
    zsh)  RC="$HOME/.zshrc" ;;
    bash) RC="$HOME/.bashrc" ;;
    *)    RC="$HOME/.profile" ;;
esac

if [ -f "$RC" ] && grep -qF "# >>> netpeek >>>" "$RC"; then
    echo "  [..] removing the PATH block from $RC"
    TMP=$(mktemp)
    awk '
        /# >>> netpeek >>>/ { skip = 1; next }
        /# <<< netpeek <<</ { skip = 0; next }
        !skip { print }
    ' "$RC" > "$TMP"
    mv "$TMP" "$RC"
    echo "  [ok] PATH entry removed"else
    echo "  [ok] no PATH entry found"
fi

if [ -d "$VENV" ]; then
    echo "  [..] deleting $VENV"
    rm -rf "$VENV"
    echo "  [ok] virtual environment deleted"
else
    echo "  [ok] no virtual environment to delete"
fi

echo
echo "  Done. Open a new terminal for the PATH change to take effect."
echo "  If you also installed with \"pip install .\", remove that copy with:"
echo "      pip uninstall netpeek"
echo
