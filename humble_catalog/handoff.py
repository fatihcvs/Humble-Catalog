"""Commands the viewer hands to the terminal it was started from.

login, reset and restore cannot run as the job runner's background
children. login opens a foreground browser window the user clicks
through. restore swaps catalog.db, which fails while anything holds it
open. reset and restore also ask for a word typed at an interactive
console, and that guard is kept, not reimplemented. So `serve` steps
down, runs the command with the console's own stdin and stdout, and
comes back when it exits.
"""
import sys
from pathlib import Path

from humble_catalog import jobs
from humble_catalog.backup import _when

# The whole vocabulary of the handoff, in the same shape as
# jobs.COMMANDS: command -> {option accepted in a request: its flag}.
COMMANDS = {
    "login":   {},
    "reset":   {},
    "restore": {"covers": "--covers"},
}


def list_backups(backups_dir="backups"):
    """The snapshots `backup` wrote, newest first.

    The compact timestamp in the name sorts chronologically as text, so
    sorting by name is sorting by age. A raw copy of an unreadable
    catalog (restore's own safety net) is left out: it is kept for
    forensics, never to be put back from a picker.
    """
    d = Path(backups_dir)
    if not d.is_dir():
        return []
    rows = []
    for p in sorted(d.glob("catalog-*.db"), reverse=True):
        if not p.is_file() or p.name.endswith(".unreadable.db"):
            continue
        stem = p.stem[len("catalog-"):]
        rows.append({"name": p.name, "size": p.stat().st_size,
                     "modified": _when(p),
                     "covers": (d / f"covers-{stem}.zip").is_file()})
    return rows


def argv(command, options=None, snapshot=None, backups_dir="backups"):
    """The exact command line for a handoff, or ValueError.

    The snapshot is the one request string that reaches argv, and only
    after it has matched, exactly, a name list_backups returned. So it
    cannot name a path outside backups/, and cannot be anything but a
    file that is there now.
    """
    if command not in COMMANDS:
        raise ValueError(f"unknown command: {command}")
    line = [sys.executable, "-m", "humble_catalog", command]
    if command == "restore":
        names = {r["name"] for r in list_backups(backups_dir)}
        if not isinstance(snapshot, str) or snapshot not in names:
            raise ValueError("choose a snapshot from backups/")
        line.append(str(Path(backups_dir) / snapshot))
    elif snapshot is not None:
        raise ValueError(f"{command} does not take a snapshot")
    return line + jobs.flags(command, COMMANDS[command], options)
