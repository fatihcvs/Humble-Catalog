#!/usr/bin/env bash
# Privacy gate: fails if anything from the real library appears in the repo.
# Required by CLAUDE.md before committing tests, fixtures, or docs.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_venv
cd "$ROOT"
exec "$PYTHON" scripts/leak_check.py
