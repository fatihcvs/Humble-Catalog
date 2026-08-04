"""Runs catalog commands as child processes on the viewer's behalf.

One job at a time. Every command here is a whole-catalog operation, so
two at once is never what a user means; a second start answers Busy.

Subprocesses rather than threads, for one reason above the others:
`harvest` runs for hours and has to be cancellable, and a Python thread
cannot be killed while a process always can. Running the CLI itself also
keeps one definition of each command -- the rule the route comments in
webapp/__init__.py state verbatim: the CLI and the web path must not be
able to disagree.

Progress needs no transport here. The child writes run_status exactly as
it does from a terminal, and the page reads it through /api/status.
"""
import os
import signal
import subprocess
import sys
import threading
from collections import deque
from datetime import datetime, timezone

from humble_catalog import db

# The last N lines of the child's output, kept for the page. IN MEMORY
# ONLY: these lines name owned titles ("enrich 12/300: <title>"), so they
# must never reach a file, a log or an export.
LOG_LINES = 500

# The whitelist: command -> {option name accepted in a request: the flag
# it becomes}. This table is the entire vocabulary of the job runner.
# Nothing from a request body is ever placed in argv -- only flags looked
# up here -- which is what makes a POSTed string harmless.
#
# reset, restore and login are absent on purpose: each needs a terminal
# (a typed confirmation, a file nobody holds open, a foreground browser
# window) and is handled by the handoff, not by this runner.
COMMANDS = {
    "extract":       {"refetch": "--refetch"},
    "reparse":       {},
    "harvest":       {"ignore_quota": "--ignore-quota"},
    "enrich":        {"retry": "--retry", "credits": "--credits",
                      "series": "--series"},
    "import_games":  {},
    "import_sheets": {},
    "backup":        {"covers": "--covers"},
    "check":         {},
}

# Option names are Python-ish so they can be JSON keys; two commands
# spell differently on the command line.
CLI_NAME = {"import_games": "import-games", "import_sheets": "import-sheets"}

# Flags the runner adds itself, whatever the request asked for.
ALWAYS = {"extract": ["--no-login"]}


class Busy(Exception):
    """A job is already running (or one is recorded as running elsewhere)."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def argv(command, options=None):
    """The exact command line for a job, or ValueError.

    Every element is either a constant or a flag from COMMANDS. A value
    that is not a bool is refused rather than coerced: coercion is how a
    request string would end up in a process argument.
    """
    if command not in COMMANDS:
        raise ValueError(f"unknown command: {command}")
    allowed = COMMANDS[command]
    flags = []
    for name, value in (options or {}).items():
        if name not in allowed:
            raise ValueError(f"{command} does not accept the option {name!r}")
        if not isinstance(value, bool):
            raise ValueError(f"option {name!r} must be true or false")
        if value:
            flags.append(allowed[name])
    return [sys.executable, "-m", "humble_catalog",
            CLI_NAME.get(command, command), *ALWAYS.get(command, []), *flags]


class JobRunner:
    """The viewer's single job slot.

    Thread-safety: `_lock` guards every mutation of the slot. The reader
    thread is the only writer of the log and the only place a job is
    retired, so a caller never has to poll the process itself.
    """

    def __init__(self, db_path="catalog.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._proc = None
        self._job = None
        self._reader = None
        self._log = deque(maxlen=LOG_LINES)
        self._last = None

    # ---- public -------------------------------------------------------

    def start(self, command, options=None, args=(), cleanup=None):
        """Spawn a job. Busy if one is running; ValueError if malformed.

        `args` are positional arguments appended after the flags. They
        never come from a request body -- the only caller that passes any
        is the spreadsheet upload, which passes a path IT created.
        """
        line = argv(command, options) + list(args)
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                raise Busy(f"{self._job['command']} is already running")
            self._log.clear()
            self._job = {"command": command, "options": dict(options or {}),
                         "started_at": _now()}
            self._proc = self._spawn(line)
            self._reader = threading.Thread(
                target=self._pump, args=(self._proc, self._job, cleanup),
                daemon=True)
            self._reader.start()
            return dict(self._job)

    def state(self):
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            return {"running": dict(self._job) if running else None,
                    "log": list(self._log),
                    "last": dict(self._last) if self._last else None}

    def wait(self, timeout=None):
        """Block until the job finishes. For tests and shutdown only."""
        reader = self._reader
        if reader is not None:
            reader.join(timeout)
        return self._proc.poll() if self._proc else None

    # ---- internals ----------------------------------------------------

    def _spawn(self, line):
        # CREATE_NEW_PROCESS_GROUP so cancel() can send CTRL_BREAK_EVENT
        # to the child alone rather than to this console's whole group,
        # which would interrupt the viewer itself.
        #
        # encoding is explicit: text=True alone decodes with the locale
        # codepage (cp1252 on Windows) while the child writes UTF-8, which
        # silently mangles every accented title in the log.
        creationflags = (subprocess.CREATE_NEW_PROCESS_GROUP
                         if sys.platform == "win32" else 0)
        return subprocess.Popen(
            line, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            cwd=os.getcwd(), creationflags=creationflags)

    def _pump(self, proc, job, cleanup):
        """Drain the child's output, then retire the job.

        Reading to EOF before wait() is deliberate: a child that fills the
        pipe buffer blocks forever if nobody drains it, and `harvest`
        prints thousands of lines.
        """
        try:
            for line in proc.stdout:
                with self._lock:
                    self._log.append(line.rstrip("\n"))
        finally:
            proc.stdout.close()
            code = proc.wait()
            self._retire(job, code)
            if cleanup is not None:
                try:
                    cleanup()
                except Exception as exc:      # noqa: BLE001 - never fatal
                    print(f"job cleanup failed: {exc}", file=sys.stderr)

    def _retire(self, job, code):
        with self._lock:
            self._last = {"command": job["command"],
                          "state": "done" if code == 0 else "failed",
                          "exit_code": code, "finished_at": _now()}
