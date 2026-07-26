#!/usr/bin/env bash
# Stop the catalog viewer by killing whatever listens on its port.
#
# Targets the port rather than a stored PID so it also catches a server
# started some other way - a detached run, an editor's task runner, or
# one left over from an earlier session.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

PIDS="$(find_listener_pids)"
if [ -z "$PIDS" ]; then
  echo "Nothing listening on port $PORT."
  exit 0
fi
for pid in $PIDS; do
  name="$(ps -p "$pid" -o comm= 2>/dev/null || echo unknown)"
  kill "$pid" 2>/dev/null || true
  sleep 1
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  echo "Stopped $name (PID $pid) on port $PORT."
done
