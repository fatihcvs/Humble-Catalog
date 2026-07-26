#!/usr/bin/env bash
# Run the test suite. Extra args pass through to pytest.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_venv
cd "$ROOT"
exec "$PYTHON" -m pytest "$@"
