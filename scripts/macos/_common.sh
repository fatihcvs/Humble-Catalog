#!/usr/bin/env bash
# Shared setup for the POSIX scripts. Source this, don't run it.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
PORT="${HUMBLE_PORT:-8087}"

require_venv() {
  if [ ! -x "$PYTHON" ]; then
    echo "No virtualenv at .venv - run $(dirname "${BASH_SOURCE[1]}")/setup.sh first." >&2
    exit 1
  fi
}

# macOS ships lsof; it reports the listening PIDs directly.
find_listener_pids() {
  lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null || true
}
