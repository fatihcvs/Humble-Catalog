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

# Prefer ss (iproute2, present on modern distros); fall back to lsof.
find_listener_pids() {
  if command -v ss >/dev/null 2>&1; then
    ss -lptnH "sport = :$PORT" 2>/dev/null \
      | grep -oP "pid=\K[0-9]+" | sort -u || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:$PORT" -sTCP:LISTEN 2>/dev/null || true
  else
    echo "Need ss or lsof to find the server process." >&2
    return 1
  fi
}
