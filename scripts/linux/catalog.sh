#!/usr/bin/env bash
# Passthrough to the catalog CLI, e.g.
#   ./scripts/<os>/catalog.sh enrich --limit 20
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_venv
cd "$ROOT"
exec "$PYTHON" -m humble_catalog "$@"
