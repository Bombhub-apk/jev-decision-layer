#!/usr/bin/env bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if command -v python3 &>/dev/null; then
    python3 "$SCRIPT_DIR/bin/jev_cli.py" "$@"
else
    python "$SCRIPT_DIR/bin/jev_cli.py" "$@"
fi
