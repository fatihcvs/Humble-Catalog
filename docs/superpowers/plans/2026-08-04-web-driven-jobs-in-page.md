# In-page jobs (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the viewer start, watch and cancel the eight headless catalog
commands, so the everyday loop (extract → harvest → enrich → import) needs no
terminal.

**Architecture:** A new `humble_catalog/jobs.py` runs one command at a time as a
child process (`sys.executable -m humble_catalog <cmd>`), capturing its output
into a bounded in-memory log. Progress needs no new transport: the child writes
`run_status` exactly as it does from a terminal, and the page reads it. Three
new routes start, cancel and report the job; a new **Tasks** tab drives them.

**Tech Stack:** Python 3.12, Flask, sqlite3 (WAL), `subprocess`, pytest, plain
ES2020 classic scripts (no build step), Node-based JS harness for behaviour
tests.

**Spec:** `docs/superpowers/specs/2026-08-04-web-driven-jobs-design.md`

## Global Constraints

- Phase 1 does **not** touch `login`, `reset` or `restore`. They stay
  terminal-only and get no cards. Phase 2 adds them.
- Argv is built from the whitelist table in `jobs.py`. **No string from a
  request body is ever placed in a process argument**, and no shell is used
  (`shell=True` is forbidden).
- Every write endpoint takes **JSON only** — no multipart, no form encoding.
  This is a stated security property of the viewer; the spreadsheet upload is
  base64 inside JSON for exactly this reason.
- `GET /api/status` and `progress.py` are **not modified**. `run_status` is the
  CLI-neutral channel and must keep working for a command started in a terminal.
- The job log holds owned titles. It is in memory, bounded to the last 500
  lines, and must never be written to a file or included in an export.
- Any screenshot of this feature is taken against `scripts/demo_catalog.py` on
  port 8099, never the real catalog. `leak_check.py` cannot see inside images.
- Subprocesses are spawned with `encoding="utf-8"` explicitly. `text=True` alone
  decodes with the locale codepage (cp1252 on Windows) and mangles every
  non-ASCII title.
- Run `scripts/verify` before the final commit of each task that changes Python
  or docs. Never pipe `leak_check.py` — read its output directly.
- Branch: `feat/web-driven-jobs-in-page`, forked from `main` after the spec
  branch merges.

---

### Task 1: `extract --no-login`

`extract` calls `humble_api.ensure_login()`, which silently opens a browser
window and blocks on it when the session has expired. As a background child
process that is a job that hangs forever on a window nobody can see. This task
gives the caller a way to say "fail instead".

**Files:**
- Modify: `humble_catalog/humble_api.py:138-152` (`ensure_login`)
- Modify: `humble_catalog/extract.py:15` (`run` signature) and its
  `ensure_login()` call
- Modify: `humble_catalog/__main__.py:76-78` (the `extract` parser) and
  `:230-232` (its dispatch branch)
- Test: `tests/test_humble_api.py`, `tests/test_extract.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `humble_api.ensure_login(profile_dir=".playwright-profile",
  allow_login=True)` raising `humble_api.NotLoggedIn` when
  `allow_login=False` and the session is dead;
  `extract.run(db_path="catalog.db", covers_dir="covers", client=None,
  refetch=False, allow_login=True)`; the CLI flag `extract --no-login`.

- [ ] **Step 1: Write the failing test for `ensure_login`**

In `tests/test_humble_api.py`:

```python
def test_ensure_login_refuses_to_open_a_browser_when_not_allowed(monkeypatch):
    from humble_catalog import humble_api

    opened = []
    monkeypatch.setattr(humble_api, "get_cookies", lambda profile_dir=None: {})
    monkeypatch.setattr(humble_api.HumbleClient, "logged_in", lambda self: False)
    monkeypatch.setattr(humble_api, "manual_login",
                        lambda profile_dir=None: opened.append(profile_dir))

    with pytest.raises(humble_api.NotLoggedIn):
        humble_api.ensure_login(allow_login=False)
    assert opened == []   # the whole point: no window was opened
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/Scripts/python -m pytest tests/test_humble_api.py::test_ensure_login_refuses_to_open_a_browser_when_not_allowed -v`
Expected: FAIL — `TypeError: ensure_login() got an unexpected keyword argument 'allow_login'`

- [ ] **Step 3: Implement it**

In `humble_catalog/humble_api.py`, replace the head of `ensure_login`:

```python
def ensure_login(profile_dir=".playwright-profile", allow_login=True):
    client = HumbleClient(get_cookies(profile_dir))
    if client.logged_in():
        return client
    if not allow_login:
        # The viewer's job runner passes allow_login=False. manual_login
        # opens a browser window and then blocks on proc.wait(), which a
        # background child process can neither show nor explain -- it would
        # read as a slow fetch that never ends. Failing here lets the page
        # say "session expired" and offer the terminal handoff instead.
        # Same rule /api/choice-preview already follows.
        raise NotLoggedIn("HumbleBundle session missing or expired")
    print("HumbleBundle session missing or expired.")
    manual_login(profile_dir)
```

(the rest of the function is unchanged.)

- [ ] **Step 4: Run it and watch it pass**

Run: `.venv/Scripts/python -m pytest tests/test_humble_api.py -v`
Expected: PASS, and no existing test in the file regresses.

- [ ] **Step 5: Write the failing test for `extract.run`**

In `tests/test_extract.py`:

```python
def test_run_propagates_no_login(monkeypatch, tmp_path):
    from humble_catalog import extract, humble_api

    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake_ensure_login(profile_dir=".playwright-profile", allow_login=True):
        seen["allow_login"] = allow_login
        raise humble_api.NotLoggedIn("expired")

    monkeypatch.setattr(humble_api, "ensure_login", fake_ensure_login)
    with pytest.raises(humble_api.NotLoggedIn):
        extract.run(allow_login=False)
    assert seen["allow_login"] is False
```

- [ ] **Step 6: Run it and watch it fail**

Run: `.venv/Scripts/python -m pytest tests/test_extract.py::test_run_propagates_no_login -v`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'allow_login'`

- [ ] **Step 7: Implement it**

In `humble_catalog/extract.py`:

```python
def run(db_path="catalog.db", covers_dir="covers", client=None, refetch=False,
        allow_login=True):
```

and, inside, change the login line to:

```python
        if client is None:
            client = humble_api.ensure_login(allow_login=allow_login)
```

- [ ] **Step 8: Run it and watch it pass**

Run: `.venv/Scripts/python -m pytest tests/test_extract.py -v`
Expected: PASS.

- [ ] **Step 9: Write the failing test for the CLI flag**

In `tests/test_main.py`:

```python
def test_extract_no_login_reports_an_expired_session_without_a_traceback(
        monkeypatch, tmp_path, capsys):
    from humble_catalog import extract, humble_api

    monkeypatch.chdir(tmp_path)

    def fake_run(**kwargs):
        assert kwargs["allow_login"] is False
        raise humble_api.NotLoggedIn("expired")

    monkeypatch.setattr(extract, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "extract", "--no-login"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert "login" in str(exc.value)
```

- [ ] **Step 10: Run it and watch it fail**

Run: `.venv/Scripts/python -m pytest tests/test_main.py::test_extract_no_login_reports_an_expired_session_without_a_traceback -v`
Expected: FAIL — `error: unrecognized arguments: --no-login` (argparse exits 2).

- [ ] **Step 11: Implement it**

In `humble_catalog/__main__.py`, beside the existing `--refetch` argument:

```python
    p_extract.add_argument("--no-login", action="store_true",
                           help="Fail if the saved session has expired "
                                "instead of opening a login window (used by "
                                "the viewer, which cannot show one)")
```

and replace the dispatch branch:

```python
    if args.command == "extract":
        from humble_catalog import extract, humble_api
        try:
            extract.run(refetch=args.refetch, allow_login=not args.no_login)
        except humble_api.NotLoggedIn:
            # A message and a non-zero exit, not a traceback: the viewer
            # shows the last log lines verbatim, and this is the one
            # failure it must translate into an action the user can take.
            raise SystemExit("HumbleBundle session expired -- run "
                             "'python -m humble_catalog login', then "
                             "try again.")
```

- [ ] **Step 12: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_main.py tests/test_extract.py tests/test_humble_api.py -v`
Expected: PASS.

- [ ] **Step 13: Commit**

```bash
git add humble_catalog/humble_api.py humble_catalog/extract.py humble_catalog/__main__.py tests/test_humble_api.py tests/test_extract.py tests/test_main.py
git commit -m "feat: extract --no-login, for callers that cannot show a login window"
```

---

### Task 2: the job runner — start, log capture, completion

**Files:**
- Create: `humble_catalog/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: nothing from Task 1 (the whitelist merely names `extract`).
- Produces:
  - `jobs.COMMANDS` — `{command_name: {option_name: flag_string}}`
  - `jobs.Busy` — exception raised when the slot is taken
  - `jobs.argv(command, options)` → `list[str]`, raising `ValueError`
  - `jobs.JobRunner(db_path="catalog.db")` with
    `.start(command, options=None, args=(), cleanup=None)` → job dict,
    `.state()` → dict, `.wait(timeout=None)` → int|None (tests only)
  - job dict shape: `{"command": str, "options": dict, "started_at": iso str}`
  - state dict shape: `{"running": job|None, "log": list[str],
    "last": {"command", "state", "exit_code", "finished_at"}|None}`

- [ ] **Step 1: Write the failing tests for argv building**

Create `tests/test_jobs.py`:

```python
import sys
import time
import pytest
from humble_catalog import db, jobs


def test_argv_builds_from_the_whitelist():
    assert jobs.argv("harvest", {"ignore_quota": True}) == [
        sys.executable, "-m", "humble_catalog", "harvest", "--ignore-quota"]


def test_argv_always_passes_no_login_to_extract():
    # Non-negotiable: without it a background extract can block forever on
    # a browser window the page cannot show.
    assert "--no-login" in jobs.argv("extract", {})


def test_argv_renames_underscored_commands():
    assert jobs.argv("import_games", {})[3] == "import-games"


def test_argv_refuses_an_unknown_command():
    with pytest.raises(ValueError, match="unknown command"):
        jobs.argv("rm", {})


def test_argv_refuses_an_option_the_command_does_not_have():
    with pytest.raises(ValueError, match="does not accept"):
        jobs.argv("reparse", {"ignore_quota": True})


def test_argv_refuses_a_non_boolean_option():
    # The guard that keeps request strings out of argv entirely.
    with pytest.raises(ValueError, match="must be true or false"):
        jobs.argv("harvest", {"ignore_quota": "; rm -rf /"})


def test_argv_omits_options_set_to_false():
    assert jobs.argv("harvest", {"ignore_quota": False}) == [
        sys.executable, "-m", "humble_catalog", "harvest"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -v`
Expected: FAIL — `ImportError: cannot import name 'jobs'`

- [ ] **Step 3: Write the whitelist and `argv`**

Create `humble_catalog/jobs.py`:

```python
"""Runs catalog commands as child processes on the viewer's behalf.

One job at a time. Every command here is a whole-catalog operation, so
two at once is never what a user means; a second start answers Busy.

Subprocesses rather than threads, for one reason above the others:
`harvest` runs for hours and has to be cancellable, and a Python thread
cannot be killed while a process always can. Running the CLI itself also
keeps one definition of each command -- the rule the route comments in
webapp/__init__.py stateverbatim: the CLI and the web path must not be
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
# window) and is handled by the Phase 2 handoff, not by this runner.
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
```

- [ ] **Step 4: Run the argv tests**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Write the failing tests for running a job**

Append to `tests/test_jobs.py`:

```python
def _fake_runner(monkeypatch, tmp_path, script):
    """A JobRunner whose 'reparse' command is `script` instead of the CLI.

    Spawning the real CLI in a unit test would be slow and would touch a
    real catalog; only the plumbing is under test here.
    """
    monkeypatch.chdir(tmp_path)
    db.connect("catalog.db").close()
    runner = jobs.JobRunner(db_path="catalog.db")
    monkeypatch.setattr(jobs, "argv",
                        lambda command, options=None: [sys.executable, "-c",
                                                       script])
    return runner


def test_start_captures_the_child_s_output(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path,
                          "print('Bundle 1/2: The Hollow Crypt')")
    runner.start("reparse")
    assert runner.wait(timeout=30) == 0
    assert "Bundle 1/2: The Hollow Crypt" in runner.state()["log"]


def test_state_reports_the_running_job_then_the_finished_one(monkeypatch,
                                                             tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "import time; time.sleep(1)")
    runner.start("reparse")
    assert runner.state()["running"]["command"] == "reparse"
    runner.wait(timeout=30)
    assert runner.state()["running"] is None
    assert runner.state()["last"] == {
        "command": "reparse", "state": "done", "exit_code": 0,
        "finished_at": runner.state()["last"]["finished_at"]}


def test_a_failing_child_is_reported_as_failed(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "raise SystemExit(3)")
    runner.start("reparse")
    runner.wait(timeout=30)
    assert runner.state()["last"]["state"] == "failed"
    assert runner.state()["last"]["exit_code"] == 3


def test_a_second_start_while_one_runs_is_refused(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "import time; time.sleep(2)")
    runner.start("reparse")
    with pytest.raises(jobs.Busy):
        runner.start("reparse")
    runner.wait(timeout=30)


def test_the_log_is_bounded(monkeypatch, tmp_path):
    runner = _fake_runner(
        monkeypatch, tmp_path,
        f"[print(i) for i in range({jobs.LOG_LINES + 50})]")
    runner.start("reparse")
    runner.wait(timeout=60)
    assert len(runner.state()["log"]) == jobs.LOG_LINES


def test_cleanup_runs_after_the_child_exits(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "print('done')")
    called = []
    runner.start("reparse", cleanup=lambda: called.append(True))
    runner.wait(timeout=30)
    assert called == [True]
```

- [ ] **Step 6: Run them and watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -k "start or state or failing or second or bounded or cleanup" -v`
Expected: FAIL — `AttributeError: module 'humble_catalog.jobs' has no attribute 'JobRunner'`

- [ ] **Step 7: Implement `JobRunner`**

Append to `humble_catalog/jobs.py`:

```python
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
```

- [ ] **Step 8: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -v`
Expected: PASS (13 tests).

- [ ] **Step 9: Commit**

```bash
git add humble_catalog/jobs.py tests/test_jobs.py
git commit -m "feat: job runner that runs one catalog command as a child process"
```

---

### Task 3: cancelling a job

`harvest` runs for hours. A user who starts one has to be able to stop it, and
the stop has to be the same interrupt the README already promises `harvest`
resumes from — not a kill mid-write.

**Files:**
- Modify: `humble_catalog/jobs.py` (add `cancel`, extend `_retire`)
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `JobRunner` from Task 2.
- Produces: `JobRunner.cancel()` → `bool` (False when nothing is running);
  `state()["last"]["state"]` gains the value `"cancelled"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jobs.py`:

```python
def test_cancel_stops_a_running_job(monkeypatch, tmp_path):
    # The child ignores nothing and simply sleeps; the interrupt ends it.
    runner = _fake_runner(monkeypatch, tmp_path,
                          "import time; time.sleep(60)")
    runner.start("reparse")
    time.sleep(0.5)          # let the interpreter reach the sleep
    assert runner.cancel() is True
    runner.wait(timeout=30)
    assert runner.state()["running"] is None
    assert runner.state()["last"]["state"] == "cancelled"


def test_cancel_with_nothing_running_is_false(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "print('x')")
    assert runner.cancel() is False
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -k cancel -v`
Expected: FAIL — `AttributeError: 'JobRunner' object has no attribute 'cancel'`

- [ ] **Step 3: Implement `cancel`**

In `humble_catalog/jobs.py`, add to `JobRunner` (public section) and adjust
`_retire`:

```python
    # How long a cancelled child gets to unwind before the escalation.
    GRACE_SECONDS = 10

    def cancel(self):
        """Interrupt the running job. False when there is nothing to stop.

        A real interrupt, not a kill: CTRL_BREAK_EVENT on Windows and
        SIGINT elsewhere both arrive as KeyboardInterrupt, which is the
        Ctrl-C the README already promises `harvest` survives and resumes
        from. terminate() only as an escalation, for a child wedged in a
        C call that never returns to the interpreter to see the signal.
        """
        with self._lock:
            proc = self._proc
            if proc is None or proc.poll() is not None:
                return False
            self._cancelled = True
        sig = (signal.CTRL_BREAK_EVENT if sys.platform == "win32"
               else signal.SIGINT)
        try:
            proc.send_signal(sig)
        except (ProcessLookupError, OSError):
            return False        # it exited between the poll and the signal
        try:
            proc.wait(timeout=self.GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            proc.terminate()
        return True

    def _retire(self, job, code):
        with self._lock:
            cancelled = self._cancelled
            self._cancelled = False
            self._last = {
                "command": job["command"],
                # Cancelled beats failed: an interrupted child exits
                # non-zero by definition, and reporting the user's own
                # deliberate stop as a failure would send them looking for
                # a fault that is not there.
                "state": "cancelled" if cancelled
                         else ("done" if code == 0 else "failed"),
                "exit_code": code, "finished_at": _now()}
```

and initialise the flag in `__init__`, beneath `self._last = None`:

```python
        self._cancelled = False
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -v`
Expected: PASS (15 tests).

Note: if `test_cancel_stops_a_running_job` is flaky on Windows, the cause is the
child not yet having installed its default SIGINT handler when the break
arrives — increase the `time.sleep(0.5)` before `cancel()`, do not weaken the
assertion.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/jobs.py tests/test_jobs.py
git commit -m "feat: cancel a running job with a real interrupt"
```

---

### Task 4: the two `run_status` hazards

Two things go wrong around `run_status`, and both are invisible until they
mislead someone: a job that dies without finalising its row makes the banner
claim work is still going, and a `harvest` started in a terminal is invisible to
the runner, so the page will happily start a second one.

**Files:**
- Modify: `humble_catalog/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `JobRunner` from Tasks 2–3.
- Produces: `JobRunner.start(..., force=False)`; `Busy` also raised when
  `run_status` shows a live row for that command; `_retire` finalises the row.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jobs.py`:

```python
def test_a_dead_job_does_not_leave_run_status_claiming_it_runs(monkeypatch,
                                                               tmp_path):
    # The child writes a run_status row and dies without finishing it --
    # what a crash, or a kill, leaves behind. The banner reads this table,
    # so a stale row is a viewer that lies about a run that ended.
    runner = _fake_runner(
        monkeypatch, tmp_path,
        "from humble_catalog import db;"
        "c = db.connect('catalog.db');"
        "c.execute(\"INSERT OR REPLACE INTO run_status "
        "(command, phase, done, total, current, started_at, updated_at) "
        "VALUES ('reparse','Bundle',1,9,'x','t','t')\");"
        "c.commit(); raise SystemExit(1)")
    runner.start("reparse")
    runner.wait(timeout=30)
    conn = db.connect("catalog.db")
    row = conn.execute("SELECT phase FROM run_status "
                       "WHERE command='reparse'").fetchone()
    conn.close()
    assert row["phase"] == "done"


def test_start_refuses_when_a_terminal_run_is_recorded(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "print('x')")
    conn = db.connect("catalog.db")
    conn.execute("INSERT OR REPLACE INTO run_status "
                 "(command, phase, done, total, current, started_at, updated_at)"
                 " VALUES ('reparse','Bundle',3,9,'x','t','t')")
    conn.commit()
    conn.close()
    with pytest.raises(jobs.Busy, match="already"):
        runner.start("reparse")


def test_force_starts_anyway(monkeypatch, tmp_path):
    runner = _fake_runner(monkeypatch, tmp_path, "print('x')")
    conn = db.connect("catalog.db")
    conn.execute("INSERT OR REPLACE INTO run_status "
                 "(command, phase, done, total, current, started_at, updated_at)"
                 " VALUES ('reparse','Bundle',3,9,'x','t','t')")
    conn.commit()
    conn.close()
    runner.start("reparse", force=True)
    assert runner.wait(timeout=30) == 0
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -k "run_status or terminal_run or force" -v`
Expected: FAIL — the first on `phase == 'Bundle'`, the other two on
`TypeError: start() got an unexpected keyword argument 'force'` / no `Busy`.

- [ ] **Step 3: Implement both**

In `humble_catalog/jobs.py`, change `start`'s signature and add the pre-flight:

```python
    def start(self, command, options=None, args=(), cleanup=None, force=False):
```

immediately after `line = argv(command, options) + list(args)`:

```python
        if not force:
            live = self._live_row(command)
            if live is not None:
                # A run started in a terminal is invisible to this runner:
                # different process, no shared state but the database. The
                # row may also simply be stale. Refusing with the timestamp
                # turns a silent double-run into a question the page can
                # put to the user, who can then answer it with force.
                raise Busy(f"a {command} run is already recorded as active "
                           f"(last updated {live['updated_at']})")
```

and add the two helpers to the internals section:

```python
    def _conn(self):
        """A short-lived connection of this thread's own.

        Never the viewer's request connection: this runs on the reader
        thread, and Flask's `g` belongs to a request that has long
        returned.
        """
        return db.connect(self.db_path)

    def _live_row(self, command):
        conn = self._conn()
        try:
            return conn.execute(
                "SELECT updated_at FROM run_status "
                "WHERE command=? AND phase != 'done'", (command,)).fetchone()
        finally:
            conn.close()

    def _finalize_row(self, command):
        """Mark this command's run_status row finished, however it ended.

        A child that crashes, or is cancelled, never reaches
        Progress.finish(), so its row would sit at phase='Bundle' forever
        and the viewer's banner would report a run that is over. The CLI
        has the same gap on Ctrl-C; this at least stops the runner adding
        to it.
        """
        conn = self._conn()
        try:
            conn.execute("UPDATE run_status SET phase='done', updated_at=? "
                         "WHERE command=? AND phase != 'done'",
                         (_now(), CLI_NAME.get(command, command)))
            conn.commit()
        finally:
            conn.close()
```

Finally, call it from `_retire`, as its first statement (outside the lock is
fine; it touches no shared state):

```python
    def _retire(self, job, code):
        self._finalize_row(job["command"])
        with self._lock:
            ...
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_jobs.py -v`
Expected: PASS (18 tests).

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/jobs.py tests/test_jobs.py
git commit -m "fix: finalize run_status on a dead job, and refuse a double run"
```

---

### Task 5: the routes

**Files:**
- Modify: `humble_catalog/webapp/__init__.py` (import `jobs`; create the runner
  in `create_app`; three routes near `/api/status` at `:719-722`)
- Test: `tests/test_webapp.py`

**Interfaces:**
- Consumes: `jobs.JobRunner`, `jobs.Busy`, `jobs.COMMANDS` from Tasks 2–4.
- Produces: `app.config["JOB_RUNNER"]` (the seam tests replace);
  `POST /api/jobs/start` (202/400/409), `POST /api/jobs/cancel` (202/409),
  `GET /api/jobs` → `{"running", "log", "last", "progress"}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webapp.py`:

```python
class _StubRunner:
    """Stands in for JobRunner so no test spawns a real command."""

    def __init__(self):
        self.started = []
        self.busy = False
        self.cancelled = False

    def start(self, command, options=None, args=(), cleanup=None, force=False):
        from humble_catalog import jobs
        jobs.argv(command, options)          # keep the whitelist in the path
        if self.busy:
            raise jobs.Busy("harvest is already running")
        self.started.append((command, options, force))
        return {"command": command, "options": options or {},
                "started_at": "2026-08-04T00:00:00+00:00"}

    def cancel(self):
        self.cancelled = True
        return True

    def state(self):
        return {"running": None, "log": ["Bundle 1/2: The Hollow Crypt"],
                "last": {"command": "reparse", "state": "done",
                         "exit_code": 0, "finished_at": "2026-08-04T00:00:01"}}


def _job_client(tmp_path):
    app = create_app(db_path=str(tmp_path / "catalog.db"))
    runner = _StubRunner()
    app.config["JOB_RUNNER"] = runner
    return app.test_client(), runner


def test_start_a_job(tmp_path):
    client, runner = _job_client(tmp_path)
    resp = client.post("/api/jobs/start",
                       json={"command": "harvest",
                             "options": {"ignore_quota": True}})
    assert resp.status_code == 202
    assert runner.started == [("harvest", {"ignore_quota": True}, False)]


def test_start_refuses_a_command_outside_the_whitelist(tmp_path):
    client, _ = _job_client(tmp_path)
    # reset is a handoff command in Phase 2, never a background job.
    for command in ("reset", "restore", "login", "rm -rf /"):
        resp = client.post("/api/jobs/start", json={"command": command})
        assert resp.status_code == 400, command


def test_start_refuses_a_non_boolean_option(tmp_path):
    client, _ = _job_client(tmp_path)
    resp = client.post("/api/jobs/start",
                       json={"command": "harvest",
                             "options": {"ignore_quota": "yes"}})
    assert resp.status_code == 400


def test_start_answers_409_when_busy(tmp_path):
    client, runner = _job_client(tmp_path)
    runner.busy = True
    resp = client.post("/api/jobs/start", json={"command": "harvest"})
    assert resp.status_code == 409
    assert "already running" in resp.get_json()["error"]


def test_start_needs_a_command(tmp_path):
    client, _ = _job_client(tmp_path)
    assert client.post("/api/jobs/start", json={}).status_code == 400
    assert client.post("/api/jobs/start", json=[]).status_code == 400


def test_start_passes_force_through(tmp_path):
    client, runner = _job_client(tmp_path)
    client.post("/api/jobs/start", json={"command": "reparse", "force": True})
    assert runner.started == [("reparse", {}, True)]


def test_cancel(tmp_path):
    client, runner = _job_client(tmp_path)
    assert client.post("/api/jobs/cancel").status_code == 202
    assert runner.cancelled is True


def test_get_jobs_reports_state_and_progress(tmp_path):
    client, _ = _job_client(tmp_path)
    conn = db.connect(str(tmp_path / "catalog.db"))
    conn.execute("INSERT OR REPLACE INTO run_status "
                 "(command, phase, done, total, current, started_at, updated_at)"
                 " VALUES ('harvest','Source',5,9,'hardcover','t','t')")
    conn.commit()
    conn.close()
    body = client.get("/api/jobs").get_json()
    assert body["log"] == ["Bundle 1/2: The Hollow Crypt"]
    assert body["last"]["state"] == "done"
    # Every unfinished run_status row, whoever started it -- the same
    # table /api/status reads, so the page cannot hold two disagreeing
    # accounts of how far a run has got.
    assert [r["command"] for r in body["progress"]] == ["harvest"]
    assert body["progress"][0]["done"] == 5
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k job -v`
Expected: FAIL — 404 on every route.

- [ ] **Step 3: Implement the routes**

In `humble_catalog/webapp/__init__.py`, extend the package import at the top:

```python
from humble_catalog import (bundle_preview, choice_preview, db, dedupe,
                            editions, export, humble_api, jobs, keys, stats,
                            url_import)
```

In `create_app`, beside the other config lines:

```python
    # One runner per app. Held in config rather than a module global so a
    # test can swap in a stub, and so two apps in one process (the suite
    # makes several) never share a job slot.
    app.config["JOB_RUNNER"] = jobs.JobRunner(db_path=db_path)
```

And, just above `@app.get("/api/status")`:

```python
    def _runner():
        return app.config["JOB_RUNNER"]

    @app.post("/api/jobs/start")
    def start_job():
        data = _json_object()
        command = _text_field(data, "command")
        options = data.get("options") or {}
        if not command:
            return jsonify({"error": "command required"}), 400
        if not isinstance(options, dict):
            return jsonify({"error": "options must be an object"}), 400
        try:
            # jobs.argv does the whitelisting, inside start(): an unknown
            # command and a bad option value are the same class of refusal
            # and must not be re-implemented here, or the two could drift.
            job = _runner().start(command, options,
                                  force=bool(data.get("force")))
        except jobs.Busy as exc:
            return jsonify({"error": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(job), 202

    @app.post("/api/jobs/cancel")
    def cancel_job():
        if not _runner().cancel():
            return jsonify({"error": "nothing is running"}), 409
        return jsonify({"ok": True}), 202

    @app.get("/api/jobs")
    def job_state():
        state = _runner().state()
        # The progress rows come from run_status, the same table
        # /api/status reads, so the page never has two disagreeing
        # accounts of how far a run has got.
        state["progress"] = [dict(r) for r in conn().execute(
            "SELECT * FROM run_status WHERE phase != 'done'")]
        return jsonify(state)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`
Expected: PASS, with no existing webapp test regressing.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "feat: POST /api/jobs/start, /api/jobs/cancel and GET /api/jobs"
```

---

### Task 6: the spreadsheet upload

`import-sheets` needs a workbook. A multipart form post would break the
viewer's stated invariant that every write endpoint takes JSON only — that is
what stops a cross-origin HTML form driving the API — so the file travels
base64-encoded inside the JSON body.

**Files:**
- Modify: `humble_catalog/webapp/__init__.py`
- Test: `tests/test_webapp.py`

**Interfaces:**
- Consumes: `app.config["JOB_RUNNER"]` from Task 5.
- Produces: `POST /api/jobs/import-sheets` taking
  `{"filename": str, "content_b64": str}`, answering 202/400/409;
  `webapp.MAX_UPLOAD_BYTES = 25 * 1024 * 1024`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webapp.py`:

```python
def _xlsx_bytes():
    from openpyxl import Workbook
    wb = Workbook()
    wb.active.append(["Name"])
    wb.active.append(["The Hollow Crypt"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_sheets_upload_starts_a_job_with_the_written_path(tmp_path):
    import base64
    client, runner = _job_client(tmp_path)
    resp = client.post("/api/jobs/import-sheets", json={
        "filename": "ratings-audiobooks.xlsx",
        "content_b64": base64.b64encode(_xlsx_bytes()).decode()})
    assert resp.status_code == 202
    command, _options, _force = runner.started[0]
    assert command == "import_sheets"
    path = Path(resp.get_json()["path"])
    assert path.exists() and path.read_bytes() == _xlsx_bytes()
    # The name is preserved: import-sheets matches audiobooks by FILE NAME,
    # so a renamed temp file would silently import against the wrong pool.
    assert path.name == "ratings-audiobooks.xlsx"


def test_import_sheets_upload_refuses_a_non_xlsx_name(tmp_path):
    import base64
    client, _ = _job_client(tmp_path)
    for name in ("ratings.csv", "../evil.xlsx", "sub/dir.xlsx"):
        resp = client.post("/api/jobs/import-sheets", json={
            "filename": name,
            "content_b64": base64.b64encode(b"x").decode()})
        assert resp.status_code == 400, name


def test_import_sheets_upload_refuses_bad_base64(tmp_path):
    client, _ = _job_client(tmp_path)
    resp = client.post("/api/jobs/import-sheets",
                       json={"filename": "a.xlsx", "content_b64": "not!base64"})
    assert resp.status_code == 400


def test_import_sheets_upload_enforces_the_size_cap(tmp_path):
    import base64
    from humble_catalog import webapp
    client, _ = _job_client(tmp_path)
    big = b"x" * (webapp.MAX_UPLOAD_BYTES + 1)
    resp = client.post("/api/jobs/import-sheets", json={
        "filename": "a.xlsx", "content_b64": base64.b64encode(big).decode()})
    assert resp.status_code == 400
    assert "too large" in resp.get_json()["error"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k import_sheets_upload -v`
Expected: FAIL — 404.

- [ ] **Step 3: Implement the route**

At the top of `humble_catalog/webapp/__init__.py`, add to the stdlib imports:

```python
import base64
import binascii
import shutil
import tempfile
```

and beside `LOOPBACK_AUTHORITIES`:

```python
# Large enough for any ratings workbook, small enough that a request
# cannot spend the machine's memory. The body is base64, so the encoded
# form is ~4/3 of this; the cap is checked on the DECODED bytes.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
```

Then, after the `/api/jobs/cancel` route:

```python
    @app.post("/api/jobs/import-sheets")
    def import_sheets_job():
        """Upload one workbook and run import-sheets over it.

        Base64 inside JSON rather than a multipart form, and that is a
        security decision rather than a taste one: form-encoded and
        multipart are exactly the body types a cross-origin HTML form can
        send, and refusing them is what stops a page you visit driving
        this API. Keeping "every write endpoint takes JSON only" true
        without exceptions is worth an unglamorous encoding.
        """
        data = _json_object()
        name = _text_field(data, "filename")
        content = data.get("content_b64")
        if not name or not isinstance(content, str):
            return jsonify({"error": "filename and content_b64 required"}), 400
        # The name is kept as given, so it must be a bare .xlsx file name:
        # import-sheets decides ebooks-vs-audiobooks from the FILE NAME, so
        # it cannot be sanitised away, which makes rejecting any path
        # separator or traversal the only safe rule.
        if not name.lower().endswith(".xlsx") or Path(name).name != name \
                or name in (".", ".."):
            return jsonify({"error": "filename must be a plain .xlsx name"}), 400
        try:
            blob = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError):
            return jsonify({"error": "content_b64 is not valid base64"}), 400
        if len(blob) > MAX_UPLOAD_BYTES:
            return jsonify({"error": "file too large"}), 400
        tmpdir = tempfile.mkdtemp(prefix="humble-import-")
        path = Path(tmpdir) / name
        path.write_bytes(blob)
        try:
            # cleanup runs after the CHILD exits, not here: the file has to
            # outlive this request, and the runner is the only thing that
            # knows when the import is done with it.
            job = app.config["JOB_RUNNER"].start(
                "import_sheets", {}, args=[str(path)],
                cleanup=lambda: shutil.rmtree(tmpdir, ignore_errors=True),
                force=bool(data.get("force")))
        except jobs.Busy as exc:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return jsonify({"error": str(exc)}), 409
        except ValueError as exc:
            shutil.rmtree(tmpdir, ignore_errors=True)
            return jsonify({"error": str(exc)}), 400
        return jsonify({**job, "path": str(path)}), 202
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -v`
Expected: PASS.

- [ ] **Step 5: Verify the whole suite and the privacy checks**

Run: `.venv/Scripts/python -m pytest -q` then
`.venv/Scripts/python scripts/leak_check.py`
Expected: all pass; leak check `clean`.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "feat: upload a workbook as base64 JSON and run import-sheets"
```

---

### Task 7: the Tasks tab

**Files:**
- Create: `humble_catalog/webapp/static/tasks.js`
- Modify: `humble_catalog/webapp/static/index.html` (tab link at `:32`, section
  after `:147`, script tag before `shell.js`)
- Modify: `humble_catalog/webapp/static/shell.js` (`SECTIONS` at `:21-26`,
  `pending` at `:56`, `badgeCount` at `:67`)
- Modify: `humble_catalog/webapp/static/style.css` (card styles)
- Modify: `tests/js_harness.py:24-26` (`VIEWER_JS`)
- Test: `tests/test_webapp.py`, `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: `POST /api/jobs/start` from Task 5; `armOrFire`, `$`, `esc`, `post`
  from `app.js`.
- Produces: globals `TASK_CARDS` (array of
  `{command, label, note, options?, danger?}`), `renderTasks()`,
  `startTask(command, options, el)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_webapp.py`:

```python
def test_index_has_a_tasks_tab_and_section():
    html = (Path(__file__).parent.parent / "humble_catalog" / "webapp"
            / "static" / "index.html").read_text(encoding="utf-8")
    assert '<a id="tab-tasks" href="#/tasks">' in html
    assert '<section id="section-tasks"' in html
    assert '<script src="/static/tasks.js"></script>' in html


def test_tasks_tab_offers_no_terminal_only_command():
    # reset, restore and login are Phase 2 handoffs. A card that posted
    # them to /api/jobs/start would 400, which is a dead button.
    js = _viewer_js()
    for command in ("reset", "restore", "login"):
        assert f'command: "{command}"' not in js
```

In `tests/test_webapp_js.py`:

```python
def test_task_cards_cover_every_headless_command():
    from humble_catalog import jobs
    from tests.js_harness import eval_js
    listed = set(eval_js("TASK_CARDS.map((c) => c.command)"))
    assert listed == set(jobs.COMMANDS)


def test_tasks_gets_no_badge_even_with_a_job_running():
    # A badge means a queue you can empty, never an optional backlog, and
    # "you could run a harvest" is the definition of an optional backlog.
    from tests.js_harness import eval_js
    assert eval_js("(pending.tasks = 5, badgeCount('tasks'))") == 0
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k tasks tests/test_webapp_js.py -k task -v`
Expected: FAIL — the HTML assertions, and `TASK_CARDS is not defined`.

- [ ] **Step 3: Write `tasks.js`**

Create `humble_catalog/webapp/static/tasks.js`:

```javascript
// The Tasks section: start a catalog command and watch it run.
//
// Every card posts to /api/jobs/start, whose whitelist is the authority
// on what may run. The cards here are a menu of that whitelist, never a
// second definition of it -- a test pins the two sets equal.
//
// login, reset and restore are absent because they need a terminal, and
// the handoff that gives them one is separate work.
const TASK_CARDS = [
  {group: "Update", command: "extract", label: "Fetch new bundles",
   note: "Asks HumbleBundle for purchases you have not catalogued yet. Minutes."},
  {group: "Update", command: "reparse", label: "Rebuild from the cache",
   note: "Re-reads bundles already downloaded. No network. Seconds."},
  {group: "Enrich", command: "harvest", label: "Harvest metadata",
   note: "Fetches every source for every title. Hours, and resumable."},
  {group: "Enrich", command: "harvest", label: "Harvest, ignoring quota",
   options: {ignore_quota: true},
   note: "Retries sources recorded as out of quota. Use after adding a key."},
  {group: "Enrich", command: "enrich", label: "Match and fill",
   note: "Matches the harvested cache to your items. Seconds."},
  {group: "Enrich", command: "enrich", label: "Match, retrying misses",
   options: {retry: true},
   note: "Also re-scores items that previously found no match."},
  {group: "Enrich", command: "enrich", label: "Fill comic credits",
   options: {credits: true},
   note: "Writer and illustrator for matched comics. Slower; resumable."},
  {group: "Enrich", command: "enrich", label: "Fill series from titles",
   options: {series: true},
   note: "Reads \"Vol. 2\" out of a title where no source supplied it."},
  {group: "Import", command: "import_sheets", label: "Import a spreadsheet",
   note: "Ratings and metadata from an .xlsx. Choose the file below."},
  {group: "Import", command: "import_games", label: "Import game libraries",
   note: "Reads Heroic's caches and Steam's Web API. No login."},
  {group: "Backup", command: "backup", label: "Back up the catalog",
   note: "A timestamped snapshot in backups/. Nothing is ever deleted."},
  {group: "Backup", command: "backup", label: "Back up with covers",
   options: {covers: true},
   note: "The snapshot plus a zip of covers/. Larger and slower."},
  {group: "Diagnose", command: "check", label: "Test every source",
   note: "One live search per metadata API, to see which keys work."},
];

const TASK_GROUPS = ["Update", "Enrich", "Import", "Backup", "Diagnose"];

function renderTasks() {
  const el = $("#task-cards");
  if (!el) return;
  el.innerHTML = TASK_GROUPS.map((group) => `
    <div class="task-group">
      <h3>${esc(group)}</h3>
      ${TASK_CARDS.filter((c) => c.group === group).map((c, i) => `
        <div class="task-card">
          <div class="task-label">${esc(c.label)}</div>
          <div class="task-note">${esc(c.note)}</div>
          <button class="task-go" data-command="${esc(c.command)}"
                  data-options='${esc(JSON.stringify(c.options || {}))}'
                  >Run</button>
        </div>`).join("")}
    </div>`).join("");
}

// Reported through the panel rather than alert(): a refusal here is
// usually "something is already running", which is information about the
// page's own state and belongs on the page.
function taskMessage(text) {
  const el = $("#task-message");
  if (el) el.textContent = text || "";
}

async function startTask(command, options) {
  taskMessage("");
  const resp = await post("/api/jobs/start", {command, options});
  if (resp.status === 409) {
    // The one refusal with a second answer available: a run recorded as
    // active may simply be stale, so offer force rather than dead-ending.
    const {error} = await resp.json();
    taskMessage(`${error} Click Run again within 3 seconds to start anyway.`);
    return "busy";
  }
  if (!resp.ok) {
    taskMessage((await resp.json()).error || "Could not start that.");
    return "error";
  }
  await pollJobs();
  return "started";
}

if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest && ev.target.closest(".task-go");
    if (!btn) return;
    const command = btn.dataset.command;
    const options = JSON.parse(btn.dataset.options || "{}");
    // Two clicks for every card, not just the risky ones: these all cost
    // real time or real network, and the arm text is the only place the
    // page can say so before it happens.
    armOrFire(btn, async () => {
      if (await startTask(command, options) === "busy")
        armOrFire(btn, () => post("/api/jobs/start",
                                  {command, options, force: true}));
    });
  });
}
```

- [ ] **Step 4: Add the HTML**

In `index.html`, after the Bundles tab link (`:32`):

```html
    <a id="tab-tasks" href="#/tasks">Tasks<span class="badge-count"></span></a>
```

after the Bundles `</section>` (`:147`):

```html
  <section id="section-tasks" hidden>
    <div id="job-panel" hidden></div>
    <div id="task-message" role="status"></div>
    <div id="task-upload">
      <label for="sheet-file">Spreadsheet to import</label>
      <input id="sheet-file" type="file" accept=".xlsx">
    </div>
    <div id="task-cards"></div>
  </section>
```

and a script tag before `shell.js`:

```html
<script src="/static/tasks.js"></script>
```

- [ ] **Step 5: Register the section**

In `shell.js`, add to `SECTIONS` after `bundles`:

```javascript
  {id: "tasks",       label: "Tasks"},
```

extend the `pending` initialiser:

```javascript
let pending = {library: 0, maintenance: 0, keys: 0, bundles: 0, tasks: 0};
```

and extend `badgeCount`, keeping the existing comment above it intact:

```javascript
// ... existing comment about Library ...
//
// Tasks is silent for the same reason: its only candidate count is "jobs
// you could run", which is an optional backlog by definition and would
// light the badge forever.
function badgeCount(section) {
  return (section === "library" || section === "tasks")
    ? 0 : (pending[section] || 0);
}
```

In `app.js`'s `load()`, add `tasks: 0` to the `pending` assignment and
`renderTasks` to the renderer loop:

```javascript
  for (const step of [render, loadReview, loadDupes, refreshStats, loadKeys,
                      renderTasks]) {
```

In `tests/js_harness.py`, add the script to `VIEWER_JS` (before `shell.js`, the
same order as `index.html`):

```python
VIEWER_JS = [_STATIC / "app.js", _STATIC / "catalog.js",
             _STATIC / "maintenance.js", _STATIC / "keys.js",
             _STATIC / "bundles.js", _STATIC / "tasks.js",
             _STATIC / "shell.js"]
```

- [ ] **Step 6: Add the styles**

In `style.css`, beside the other section styles:

```css
.task-group { margin-bottom: 1.5rem; }
.task-group h3 { margin: 0 0 .5rem; font-size: 1rem; color: var(--muted); }
.task-card {
  display: grid; grid-template-columns: 1fr auto; align-items: center;
  gap: .25rem 1rem; padding: .6rem .8rem; margin-bottom: .4rem;
  background: var(--surface);
  border: 1px solid var(--border); border-radius: 6px;
}
.task-label { font-weight: 600; }
.task-note { grid-column: 1; color: var(--muted); font-size: .9rem; }
.task-go { grid-column: 2; grid-row: 1 / span 2; }
#task-message:not(:empty) {
  margin: .5rem 0; padding: .5rem .8rem; border-radius: 6px;
  background: var(--panel-warn-bg); border: 1px solid var(--panel-warn-border);
  color: var(--fg);
}
```

Those variable names are the ones `:root` already defines (`--surface`,
`--border`, `--muted`, `--panel-warn-bg`, `--panel-warn-border`), and each is
redefined in the dark and `[data-theme]` blocks, so the section themes itself.
Do not introduce new custom properties.

- [ ] **Step 7: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py tests/test_webapp_js.py -v`
Expected: PASS. (The JS behaviour tests skip if Node is absent — install Node or
note the skip; they must not be deleted.)

- [ ] **Step 8: Commit**

```bash
git add humble_catalog/webapp/static/tasks.js humble_catalog/webapp/static/index.html humble_catalog/webapp/static/shell.js humble_catalog/webapp/static/app.js humble_catalog/webapp/static/style.css tests/js_harness.py tests/test_webapp.py tests/test_webapp_js.py
git commit -m "feat: a Tasks tab that starts catalog commands"
```

---

### Task 8: the running-job panel

**Files:**
- Modify: `humble_catalog/webapp/static/tasks.js` (add `pollJobs`,
  `renderJobPanel`, the upload handler, the cancel handler)
- Modify: `humble_catalog/webapp/static/shell.js` (call `pollJobs` from the
  existing 5-second interval at `:107-108`)
- Modify: `humble_catalog/webapp/static/style.css`
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: `GET /api/jobs` (Task 5), `POST /api/jobs/cancel` (Task 5),
  `POST /api/jobs/import-sheets` (Task 6), `TASK_CARDS` (Task 7).
- Produces: globals `pollJobs()`, `renderJobPanel(state)`, `uploadSheet(file)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webapp_js.py`:

```python
def test_job_panel_shows_progress_and_the_log():
    from tests.js_harness import eval_js
    html = eval_js("""(renderJobPanel({
      running: {command: "harvest", started_at: "2026-08-04T00:00:00+00:00"},
      progress: [{command: "harvest", phase: "Source", done: 5, total: 9,
                  current: "hardcover"}],
      log: ["harvest  hardcover 5/9"], last: null}),
      dom["#job-panel"])""")
    assert "harvest" in html and "5" in html and "9" in html
    assert "hardcover 5/9" in html


def test_job_panel_reports_a_cancelled_job_as_cancelled_not_failed():
    from tests.js_harness import eval_js
    html = eval_js("""(renderJobPanel({
      running: null, progress: [], log: [],
      last: {command: "harvest", state: "cancelled", exit_code: 2,
             finished_at: "2026-08-04T00:01:00+00:00"}}),
      dom["#job-panel"])""")
    assert "cancelled" in html.lower()
    assert "fail" not in html.lower()


def test_job_panel_translates_an_expired_session():
    # The one failure the page must turn into an action rather than show
    # raw: the fix is a terminal command, and Phase 1 can only say so.
    from tests.js_harness import eval_js
    html = eval_js("""(renderJobPanel({
      running: null, progress: [],
      log: ["HumbleBundle session expired -- run "
            + "'python -m humble_catalog login', then try again."],
      last: {command: "extract", state: "failed", exit_code: 1,
             finished_at: "2026-08-04T00:01:00+00:00"}}),
      dom["#job-panel"])""")
    assert "session" in html.lower()
    assert "humble_catalog login" in html
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k job_panel -v`
Expected: FAIL — `renderJobPanel is not defined`.

- [ ] **Step 3: Implement the panel**

Append to `tasks.js`:

```javascript
// The one child failure the page translates rather than shows raw. The
// fix is a command in a terminal, and a user who is here precisely to
// avoid terminals needs to be told plainly which one.
const EXPIRED = /session (expired|missing)/i;

function renderJobPanel(state) {
  const el = $("#job-panel");
  if (!el) return;
  const running = state.running;
  const row = (state.progress || []).find(
    (p) => running && p.command === running.command) || null;
  const parts = [];
  if (running) {
    const bar = row
      ? `<progress value="${row.done}" max="${row.total || 1}"></progress>
         <span class="job-count">${row.phase} ${row.done}/${row.total}</span>
         <span class="job-current">${esc(row.current || "starting")}</span>`
      : `<span class="job-count">starting</span>`;
    parts.push(`<div class="job-head"><strong>${esc(running.command)}</strong>
                  ${bar}
                  <button id="job-cancel">Cancel</button></div>`);
  } else if (state.last) {
    const {command, state: how, exit_code: code} = state.last;
    // "cancelled" is its own word, never folded into failure: an
    // interrupted child exits non-zero by definition, and calling the
    // user's own deliberate stop a failure sends them hunting a fault
    // that is not there.
    const verdict = how === "done" ? "finished"
                  : how === "cancelled" ? "cancelled"
                  : `failed (exit ${code})`;
    parts.push(`<div class="job-head"><strong>${esc(command)}</strong>
                  <span class="job-verdict job-${how}">${verdict}</span></div>`);
  }
  const log = state.log || [];
  if (log.some((line) => EXPIRED.test(line)))
    parts.push(`<div class="job-hint">Your HumbleBundle session has expired.
      Run <code>python -m humble_catalog login</code> in the terminal running
      this viewer, then try again.</div>`);
  if (log.length)
    parts.push(`<pre class="job-log">${esc(log.slice(-200).join("\n"))}</pre>`);
  el.innerHTML = parts.join("");
  el.hidden = parts.length === 0;
  return el.innerHTML;
}

async function pollJobs() {
  const state = await (await fetch("/api/jobs")).json();
  renderJobPanel(state);
}

async function uploadSheet(file) {
  // FileReader gives base64 via a data: URL, whose payload sits after the
  // comma. The endpoint takes JSON only -- see its docstring for why a
  // multipart form is not an option here.
  const b64 = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  const resp = await post("/api/jobs/import-sheets",
                          {filename: file.name, content_b64: b64});
  if (!resp.ok) {
    taskMessage((await resp.json()).error || "Could not import that file.");
    return;
  }
  taskMessage(`Importing ${file.name}.`);
  await pollJobs();
}

if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("click", async (ev) => {
    if (ev.target && ev.target.id === "job-cancel") {
      await post("/api/jobs/cancel");
      await pollJobs();
    }
  });
  document.addEventListener("change", (ev) => {
    if (ev.target && ev.target.id === "sheet-file" && ev.target.files[0])
      uploadSheet(ev.target.files[0]);
  });
}
```

Replace the `import_sheets` card's button behaviour by making its `Run` button
open the file picker instead of posting — in the click handler added in Task 7,
before `armOrFire`:

```javascript
    if (command === "import_sheets") {
      // Nothing to start without a file; the picker IS this card's action.
      $("#sheet-file").click();
      return;
    }
```

- [ ] **Step 4: Poll from the shell**

In `shell.js`, replace the two boot lines:

```javascript
pollStatus();
setInterval(pollStatus, 5000);
```

with:

```javascript
// One interval for both. pollStatus draws the header banner (which must
// keep working for a run started in a terminal); pollJobs draws the Tasks
// panel, which knows only about jobs this viewer started.
async function pollAll() {
  await pollStatus();
  try {
    await pollJobs();
  } catch (err) {
    console.error("pollJobs() failed:", err);
  }
}
pollAll();
setInterval(pollAll, 5000);
```

- [ ] **Step 5: Add the styles**

In `style.css`:

```css
#job-panel { margin-bottom: 1rem; padding: .8rem; border: 1px solid var(--border);
             border-radius: 6px; }
.job-head { display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; }
.job-current { color: var(--muted); }
.job-log {
  max-height: 14rem; overflow: auto; margin: .6rem 0 0;
  font-family: ui-monospace, monospace; font-size: .85rem;
  white-space: pre-wrap; word-break: break-word;
}
.job-hint { margin-top: .6rem; }
.job-failed { color: var(--danger); }
.job-cancelled { color: var(--muted); }
```

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/webapp/static/tasks.js humble_catalog/webapp/static/shell.js humble_catalog/webapp/static/style.css tests/test_webapp_js.py
git commit -m "feat: show a running job's progress, log and cancel button"
```

---

### Task 9: documentation, and a look at the real thing

**Files:**
- Modify: `README.md` (the Browsing section around `:278-284`, and "The
  viewer's exposure" at `:469-491`)
- Modify: `docs/BACKLOG.md` (a Done entry)
- Test: `tests/test_webapp.py` (a doc assertion), then a manual pass

**Interfaces:**
- Consumes: everything above.
- Produces: no code interface.

- [ ] **Step 1: Write the failing test**

In `tests/test_webapp.py`:

```python
def test_readme_documents_the_viewer_s_new_reach():
    readme = (Path(__file__).parent.parent / "README.md").read_text(
        encoding="utf-8")
    exposure = readme.split("### The viewer's exposure")[1]
    # The security note must not quietly go stale: the viewer can now
    # start processes, and the section that describes its exposure is the
    # one place a reader will look for that.
    assert "start" in exposure and "job" in exposure.lower()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k readme -v`
Expected: FAIL — `AssertionError`.

- [ ] **Step 3: Update the README's Browsing section**

After the `serve` bullet, add:

```markdown
The viewer's **Tasks** tab runs the catalog commands for you: fetching new
bundles, harvesting, enriching, importing a spreadsheet or your game
libraries, and taking a backup. Each runs as a separate process with its
progress, its output and a Cancel button on the page, so the terminal is
needed only for `login`, `reset` and `restore` — the three that need a
browser window, a database file nobody holds open, or a word typed at a
console. A command started in a terminal still shows in the banner, as
it always did.
```

- [ ] **Step 4: Update "The viewer's exposure"**

Add a paragraph at the end of that section, before the "Note that any process"
line:

```markdown
Since the Tasks tab, the viewer can also **start catalog commands** as child
processes. That widens what a program on your own machine could do through
the port — it could begin a harvest, or an import — so it is worth knowing.
Three things bound it. The two defences above are unchanged, so a page you
visit still cannot drive any of it. The command line is built from a fixed
table of commands and flags, never from anything in the request, so no
string from a caller reaches a process argument. And the destructive
commands are not reachable this way at all: `reset` and `restore` still
require a word typed at an interactive terminal.
```

- [ ] **Step 5: Run the test**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k readme -v`
Expected: PASS.

- [ ] **Step 6: Add the backlog entry**

Add this to the Done section of `docs/BACKLOG.md`, matching the surrounding
entries' bold-lead-then-prose shape:

```markdown
- **Catalog commands from the viewer (Phase 1)** —
  `superpowers/specs/2026-08-04-web-driven-jobs-design.md`.
  The Tasks tab starts `extract`, `reparse`, `harvest`, `enrich`,
  `import-sheets`, `import-games`, `backup` and `check` as child
  processes, with progress read from `run_status` — the same table the
  banner reads, so a run started in a terminal still shows. `jobs.py`
  holds one slot; argv comes from a whitelist table, so nothing in a
  request body reaches a process argument.

  `extract` grew `--no-login`, which the runner always passes. Without it
  `ensure_login` silently opens a browser window and blocks on it, which
  as a background child is a job that hangs forever with nothing on
  screen to say why. The page reports the expiry and names the `login`
  command instead.

  The spreadsheet upload is base64 inside JSON rather than a multipart
  form, which is a security decision and not a taste one: multipart and
  form-encoded are exactly what a cross-origin HTML form can send, and
  refusing them is what keeps a page you visit from driving the API.

  Cancel sends a real interrupt (`CTRL_BREAK_EVENT` / `SIGINT`), the
  Ctrl-C `harvest` already resumes from, and a cancelled job is reported
  as cancelled rather than failed. A job that dies without finishing now
  has its `run_status` row closed by the runner, so the banner cannot
  claim a run that ended is still going.

  Still outstanding: Phase 2, the terminal handoff for `login`, `reset`
  and `restore`.
```

- [ ] **Step 7: Run everything**

Run: `.venv/Scripts/python -m pytest -q`
Then: `scripts/windows/verify` (or `scripts/verify` on macOS/Linux)
Expected: suite green; both privacy checks pass.

- [ ] **Step 8: Look at it running, against the demo catalog**

Start the demo viewer — **not the real catalog**, because anything you
screenshot or paste from the real one leaks the owner's library and no
automated check can see it:

```bash
.venv/Scripts/python scripts/demo_catalog.py
```

Open `http://127.0.0.1:8099/#/tasks` and confirm by eye: the cards render in
their groups; **Run** arms and then fires; `check` completes and its output
appears in the log pane; a long job shows a progress bar that advances and a
Cancel button that stops it and reads "cancelled"; the Tasks tab shows no badge
at any point.

- [ ] **Step 9: Commit**

```bash
git add README.md docs/BACKLOG.md tests/test_webapp.py
git commit -m "docs: the Tasks tab, and what it adds to the viewer's exposure"
```

---

## What Phase 1 deliberately leaves undone

- `login`, `reset` and `restore` have no cards. An expired session is reported
  with the terminal command to run, not a button.
- `GET /api/backups` and `POST /api/jobs/handoff` do not exist yet.
- The viewer does not shut down or restart itself.

All four are Phase 2.
