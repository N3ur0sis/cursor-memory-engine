#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$SCRIPT_DIR/memory_tool.py" recall "$@"
fi

if command -v python >/dev/null 2>&1; then
  exec python "$SCRIPT_DIR/memory_tool.py" recall "$@"
fi

printf '%s\n' "Python 3 is required for tools/agent/recall.sh" >&2
exit 1
