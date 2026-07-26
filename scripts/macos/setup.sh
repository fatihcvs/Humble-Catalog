#!/usr/bin/env bash
# Create the virtualenv and install the project with dev extras.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd "$ROOT"

PY=python3.12
command -v "$PY" >/dev/null || {
  echo "$PY not found on PATH. Install Python 3.12 first." >&2
  exit 1
}

# Debian and Ubuntu split ensurepip into a separate package, so venv
# imports fine but creation dies partway and leaves a .venv with no pip.
"$PY" -c 'import ensurepip' 2>/dev/null || {
  echo "$PY cannot create virtualenvs: the ensurepip module is missing." >&2
  echo "With Homebrew: brew install python@3.12" >&2
  exit 1
}

# Test for the interpreter, not the directory. A failed run leaves a
# .venv behind, and re-running must not mistake that for a working one.
[ -x "$PYTHON" ] || "$PY" -m venv .venv
"$ROOT/.venv/bin/pip" install -e ".[dev]"
"$ROOT/.venv/bin/playwright" install chromium
echo "Setup complete."
