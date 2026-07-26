#!/usr/bin/env bash
# Everything that must pass before a commit: tests, then the privacy gate.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_venv
cd "$ROOT"
"$PYTHON" -m pytest -q || { echo "Tests failed - stopping before the leak check." >&2; exit 1; }
"$PYTHON" scripts/check_no_data_tracked.py || { echo "A data file is tracked by git." >&2; exit 1; }
"$PYTHON" scripts/leak_check.py || { echo "Leak check failed." >&2; exit 1; }
echo
echo "Verified: tests pass, no private data in the repo."
