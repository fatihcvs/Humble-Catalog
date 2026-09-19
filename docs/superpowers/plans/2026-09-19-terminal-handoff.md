# Terminal handoff (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the viewer's Tasks tab run `login`, `reset` and `restore`, the
three commands that need a terminal. The viewer steps down, the command runs in
the console `serve` was started from, and then the viewer comes back by itself.

**Architecture:** A new `humble_catalog/handoff.py` holds the handoff
whitelist, the snapshot listing, a thread-safe `HandoffSlot` that a route
fills and the serve loop drains, and `run_in_terminal`, which runs the command
with inherited stdio. `webapp.serve()` changes from a single `app.run()` into a
loop over `make_server`: serve, drain a handoff, shut down, run the command,
rebind the *same* app objects, and repeat. The page arms a card with two clicks,
posts the handoff, shows a takeover screen, and reloads once `/api/jobs`
reports a higher handoff `generation`.

**Tech Stack:** Python 3.12, Flask/Werkzeug `make_server`, `subprocess`,
`threading`, pytest, plain ES2020 classic scripts, and the Node harness
(`tests/js/harness.mjs`) for JS behaviour tests.

**Spec:** `docs/superpowers/specs/2026-08-04-web-driven-jobs-design.md`
(sections "The handoff", "The Tasks tab", "Safety", "Error handling", and
"Delivery: two plans" → Plan 2). GitHub issue #8.

## Global Constraints

- **`reset` and `restore` keep their typed confirmation, at the terminal.**
  The page's two-click only arms the handoff; a human still types `RESET` /
  `RESTORE` at a console. Do not add a web modal, a `--yes` flag or any
  other bypass. `reset.run` and `backup.restore` are **not modified**.
- Argv comes from a whitelist table. **No request string is placed in a
  process argument unless it is first matched exactly against a server-side
  listing.** The snapshot name is the one such string, and it must equal a
  name that `handoff.list_backups()` returned. No `shell=True`.
- Every write endpoint takes **JSON only**.
- The handoff child **inherits stdin/stdout/stderr**: no `stdin=`,
  `stdout=`, `stderr=` or `creationflags=` arguments. Inheritance is what
  makes `input()` work and puts the login window in the foreground.
- The handoff is refused (409) while an in-page job is running, and an
  in-page job is refused (409) while a handoff is pending. A `restore`
  cannot swap a file a harvest holds open, and a `reset` must not wipe the
  catalog under one.
- The viewer **comes back whatever the command did**: a non-zero exit, a
  Ctrl-C, a failure to spawn, or an unexpected exception in the loop all
  end in a rebind. The one exit from the loop is Ctrl-C while *serving*.
- **The browser is not reopened after a handoff.** The spec says both "the
  browser is reopened" and "the page … reloads". Doing both leaves a second
  tab after every handoff. The page reconnects by itself and the console
  prints the URL, so a user who closed the tab still has it.
- `create_app()` alone (the demo server, `.claude/launch.json`) has no serve
  loop and so no handoff. Its `HANDOFF` config is `None`, the route answers
  409 saying so, and the page hides nothing. The error names the command to
  run instead.
- The LAN app is untouched. The handoff route is a write route, so it is
  absent there, and `LAN_RULES` in `tests/test_webapp.py` must not change.
- Test data: snapshot names are timestamps (`catalog-20260101-120000.db`).
  No book titles are needed. If one is, take it from `docs/TEST-DATA.md`.
- Any screenshot is taken against `scripts/demo_catalog.py` (port 8099).
  `leak_check.py` cannot read pixels.
- Run `.venv/Scripts/python -m pytest -q` after every task. Run
  `scripts/windows/verify.ps1` before the last commit of Task 7. Never pipe
  `leak_check.py`; read its output directly.
- Branch: `feat/terminal-handoff`, forked from `main` (already created; this
  plan is its first commit).

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `humble_catalog/jobs.py` | modify | Extract the bool-flag loop into `flags()` so both whitelists share one validator |
| `humble_catalog/handoff.py` | **create** | Handoff whitelist, `argv`, `list_backups`, `HandoffSlot`, `run_in_terminal` |
| `humble_catalog/humble_api.py` | modify | `login()`, which says "already logged in" instead of silently doing nothing |
| `humble_catalog/__main__.py` | modify | `login` dispatches to `humble_api.login()` |
| `humble_catalog/webapp/__init__.py` | modify | `_bind`, `_run_all(servers, slot)`, `_serve_loop`, both `serve()` paths through it; `GET /api/backups`, `POST /api/jobs/handoff`, `handoff` key in `GET /api/jobs`, start refused while a handoff is pending |
| `humble_catalog/webapp/static/tasks.js` | modify | Handoff cards, Danger group, restore picker, `startHandoff`, takeover, `reconnect`, Log in button on an expired session |
| `humble_catalog/webapp/static/index.html` | modify | `#handoff-screen` overlay |
| `humble_catalog/webapp/static/style.css` | modify | Takeover overlay, "uses the terminal" mark, Danger group |
| `tests/js/harness.mjs` | modify | Publish the new `const`s |
| `tests/test_handoff.py` | **create** | Unit tests for `handoff.py` |
| `tests/test_jobs.py`, `tests/test_humble_api.py`, `tests/test_main.py`, `tests/test_webapp.py`, `tests/test_webapp_js.py` | modify | As each task says |
| `README.md`, `docs/BACKLOG.md` | modify | Usage, exposure, backlog entry |

---

### Task 1: The handoff whitelist and the snapshot listing

**Files:**
- Modify: `humble_catalog/jobs.py` (`argv`, around lines 64-84)
- Create: `humble_catalog/handoff.py`
- Test: `tests/test_handoff.py` (create), `tests/test_jobs.py` (existing tests must still pass unchanged)

**Interfaces:**
- Produces: `jobs.flags(command: str, allowed: dict[str, str], options: dict | None) -> list[str]`
- Produces: `handoff.COMMANDS: dict[str, dict[str, str]]` = `{"login": {}, "reset": {}, "restore": {"covers": "--covers"}}`
- Produces: `handoff.list_backups(backups_dir) -> list[dict]`. Each dict is `{"name": str, "size": int, "modified": str, "covers": bool}`, newest first.
- Produces: `handoff.argv(command: str, options: dict | None = None, snapshot: str | None = None, backups_dir="backups") -> list[str]`, which raises `ValueError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handoff.py`:

```python
import sys
from pathlib import Path

import pytest

from humble_catalog import handoff


def _snap(d, stamp, covers=False):
    d.mkdir(exist_ok=True)
    p = d / f"catalog-{stamp}.db"
    p.write_bytes(b"x" * 10)
    if covers:
        (d / f"covers-{stamp}.zip").write_bytes(b"z")
    return p


def test_argv_for_login_and_reset_is_the_bare_command():
    assert handoff.argv("login") == [
        sys.executable, "-m", "humble_catalog", "login"]
    assert handoff.argv("reset", {}) == [
        sys.executable, "-m", "humble_catalog", "reset"]


def test_argv_refuses_an_in_page_command():
    # harvest is the job runner's; the handoff table knows only three.
    with pytest.raises(ValueError, match="unknown command"):
        handoff.argv("harvest")


def test_argv_refuses_a_non_boolean_option(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000")
    with pytest.raises(ValueError, match="must be true or false"):
        handoff.argv("restore", {"covers": "yes"},
                     snapshot="catalog-20260101-120000.db", backups_dir=d)


def test_restore_needs_a_snapshot(tmp_path):
    with pytest.raises(ValueError, match="snapshot"):
        handoff.argv("restore", {}, backups_dir=tmp_path)


def test_restore_takes_only_a_listed_snapshot(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000")
    for bad in ("../catalog.db", "catalog-20991231-000000.db",
                str(d / "catalog-20260101-120000.db"), 7):
        with pytest.raises(ValueError, match="snapshot"):
            handoff.argv("restore", {}, snapshot=bad, backups_dir=d)


def test_restore_argv_names_the_listed_file_and_the_covers_flag(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000", covers=True)
    line = handoff.argv("restore", {"covers": True},
                        snapshot="catalog-20260101-120000.db", backups_dir=d)
    assert line == [sys.executable, "-m", "humble_catalog", "restore",
                    str(d / "catalog-20260101-120000.db"), "--covers"]


def test_only_restore_takes_a_snapshot(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000")
    with pytest.raises(ValueError, match="snapshot"):
        handoff.argv("reset", {}, snapshot="catalog-20260101-120000.db",
                     backups_dir=d)


def test_list_backups_is_newest_first_and_pairs_covers(tmp_path):
    d = tmp_path / "backups"
    _snap(d, "20260101-120000", covers=True)
    _snap(d, "20260301-090000")
    rows = handoff.list_backups(d)
    assert [r["name"] for r in rows] == [
        "catalog-20260301-090000.db", "catalog-20260101-120000.db"]
    assert [r["covers"] for r in rows] == [False, True]
    assert rows[0]["size"] == 10
    assert len(rows[0]["modified"]) == len("2026-03-01 09:00")


def test_list_backups_leaves_out_raw_copies_of_a_damaged_catalog(tmp_path):
    # restore's own safety copy of an unreadable catalog. Nobody means to
    # put a damaged file back from a picker.
    d = tmp_path / "backups"
    _snap(d, "20260101-120000")
    (d / "catalog-20260102-120000.unreadable.db").write_bytes(b"?")
    assert [r["name"] for r in handoff.list_backups(d)] == [
        "catalog-20260101-120000.db"]


def test_list_backups_of_a_missing_directory_is_empty(tmp_path):
    assert handoff.list_backups(tmp_path / "nope") == []
```

Also add to `tests/test_jobs.py`:

```python
def test_flags_is_the_shared_option_validator():
    assert jobs.flags("harvest", {"ignore_quota": "--ignore-quota"},
                      {"ignore_quota": True}) == ["--ignore-quota"]
    with pytest.raises(ValueError, match="does not accept"):
        jobs.flags("reparse", {}, {"x": True})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_handoff.py tests/test_jobs.py -q`
Expected: FAIL. `ModuleNotFoundError: humble_catalog.handoff`, and `jobs` has no attribute `flags`.

- [ ] **Step 3: Extract `jobs.flags`**

In `humble_catalog/jobs.py`, replace the body of `argv` with a call to a new
`flags`. Keep the docstring reasoning next to the check it describes:

```python
def flags(command, allowed, options):
    """The CLI flags for `options`, validated against `allowed`.

    Shared with handoff.argv so the two whitelists cannot disagree about
    what a usable option is. A value that is not a bool is refused rather
    than coerced: coercion is how a request string would end up in a
    process argument.
    """
    out = []
    for name, value in (options or {}).items():
        if name not in allowed:
            raise ValueError(f"{command} does not accept the option {name!r}")
        if not isinstance(value, bool):
            raise ValueError(f"option {name!r} must be true or false")
        if value:
            out.append(allowed[name])
    return out


def argv(command, options=None):
    """The exact command line for a job, or ValueError.

    Every element is either a constant or a flag from COMMANDS.
    """
    if command not in COMMANDS:
        raise ValueError(f"unknown command: {command}")
    return [sys.executable, "-m", "humble_catalog",
            CLI_NAME.get(command, command), *ALWAYS.get(command, []),
            *flags(command, COMMANDS[command], options)]
```

Also update the comment above `COMMANDS` so it points at the new module:
"…is handled by the handoff in handoff.py, not by this runner."

- [ ] **Step 4: Create `humble_catalog/handoff.py` (whitelist and listing only)**

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_handoff.py tests/test_jobs.py -q`
Expected: PASS, including every existing `test_argv_*` in `test_jobs.py`.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/jobs.py humble_catalog/handoff.py tests/test_handoff.py tests/test_jobs.py
git commit -m "feat: handoff whitelist and snapshot listing for login, reset and restore"
```

---

### Task 2: `HandoffSlot` and `run_in_terminal`

**Files:**
- Modify: `humble_catalog/handoff.py`
- Test: `tests/test_handoff.py`

**Interfaces:**
- Consumes: `jobs.Busy`, `jobs._now()`
- Produces: `class HandoffSlot` with these methods:
  - `request(command: str, line: list[str]) -> int`. Returns the current generation, or raises `jobs.Busy`.
  - `busy() -> str | None`. The pending or active command.
  - `take() -> dict | None`. Returns `{"command", "argv"}` and marks it active.
  - `finish(exit_code: int | None) -> None`. Records `last`, clears active, and increments `generation`.
  - `state() -> dict`. Returns `{"generation": int, "pending": str | None, "last": dict | None}`.
- Produces: `run_in_terminal(command: str, line: list[str], _run=subprocess.run) -> int | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_handoff.py`:

```python
from humble_catalog import jobs


def test_a_slot_holds_one_handoff_until_it_is_finished():
    slot = handoff.HandoffSlot()
    assert slot.request("reset", ["x"]) == 0
    with pytest.raises(jobs.Busy, match="reset"):
        slot.request("login", ["y"])
    assert slot.take() == {"command": "reset", "argv": ["x"]}
    # Taken is not free: until the command has run and the viewer is back,
    # a second request would queue a handoff nobody asked for twice.
    assert slot.busy() == "reset"
    with pytest.raises(jobs.Busy):
        slot.request("login", ["y"])
    slot.finish(0)
    assert slot.busy() is None
    assert slot.state()["generation"] == 1
    assert slot.state()["last"]["command"] == "reset"
    assert slot.state()["last"]["exit_code"] == 0


def test_take_on_an_empty_slot_is_none():
    assert handoff.HandoffSlot().take() is None


def test_run_in_terminal_inherits_the_console(capsys):
    seen = {}

    class Done:
        returncode = 3

    def fake_run(line, **kw):
        seen["line"], seen["kw"] = line, kw
        return Done()

    assert handoff.run_in_terminal("reset", ["a", "b"], _run=fake_run) == 3
    assert seen["line"] == ["a", "b"]
    # No stdio redirection and no shell: inheriting the console is what
    # lets reset read RESET and puts the login window in front.
    for key in ("stdin", "stdout", "stderr", "shell", "creationflags"):
        assert key not in seen["kw"]
    out = capsys.readouterr().out
    assert "reset" in out and "viewer" in out.lower()


def test_run_in_terminal_survives_ctrl_c(capsys):
    def interrupted(line, **kw):
        raise KeyboardInterrupt

    assert handoff.run_in_terminal("login", ["a"], _run=interrupted) is None
    assert "interrupted" in capsys.readouterr().out.lower()


def test_run_in_terminal_survives_a_failed_spawn(capsys):
    def missing(line, **kw):
        raise FileNotFoundError("no python")

    assert handoff.run_in_terminal("login", ["a"], _run=missing) is None
    assert "could not start" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_handoff.py -q`
Expected: FAIL with `AttributeError: module 'humble_catalog.handoff' has no attribute 'HandoffSlot'`.

- [ ] **Step 3: Implement**

Add these imports at the top of `handoff.py`: `import os`, `import subprocess`, `import threading`. Then append:

```python
class HandoffSlot:
    """The one handoff a route has asked for, and how the last one ended.

    A route calls request(); the serve loop calls take() between polls,
    runs the command, then finish(). `generation` counts finished
    handoffs, and the page reloads once it has moved past the value its
    request was answered with. That is how the page tells "the server is
    back" from "the server has not gone down yet".
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = None
        self._active = None
        self.generation = 0
        self.last = None

    def request(self, command, line):
        with self._lock:
            held = self._pending or self._active
            if held is not None:
                raise jobs.Busy(f"{held['command']} is already being handed "
                                "to the terminal")
            self._pending = {"command": command, "argv": list(line)}
            return self.generation

    def busy(self):
        with self._lock:
            held = self._pending or self._active
            return held["command"] if held else None

    def take(self):
        with self._lock:
            req, self._pending = self._pending, None
            if req is not None:
                self._active = req
            return req

    def finish(self, exit_code):
        with self._lock:
            command = self._active["command"] if self._active else None
            self.last = {"command": command, "exit_code": exit_code,
                         "finished_at": jobs._now()}
            self._active = None
            self.generation += 1

    def state(self):
        with self._lock:
            held = self._pending or self._active
            return {"generation": self.generation,
                    "pending": held["command"] if held else None,
                    "last": dict(self.last) if self.last else None}


def run_in_terminal(command, line, _run=subprocess.run):
    """Run a handoff command in this console. Returns its exit code, or
    None when it never finished (Ctrl-C, or it could not start).

    Deliberately no stdin/stdout/stderr arguments: the child inherits the
    console, which is the entire point. No creationflags either. The job
    runner's CREATE_NEW_PROCESS_GROUP would detach it from Ctrl-C, and
    here the user's Ctrl-C is meant for exactly this child.

    Ctrl-C reaches the child and this process alike. It is caught here so
    that it aborts the command and not the viewer. A second Ctrl-C, once
    the viewer is back, quits `serve` as it always has.
    """
    print(f"\n--- The viewer handed `{command}` to this terminal. It comes "
          "back when the command finishes. ---\n", flush=True)
    try:
        return _run(line, cwd=os.getcwd()).returncode
    except KeyboardInterrupt:
        print(f"\n`{command}` interrupted. Bringing the viewer back.")
        return None
    except OSError as exc:
        print(f"Could not start `{command}`: {exc}")
        return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_handoff.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/handoff.py tests/test_handoff.py
git commit -m "feat: a handoff slot, and running a command in the viewer's console"
```

---

### Task 3: `login` says when there is nothing to do

With a live session, `login` today exits without printing anything. From a
terminal that is only puzzling. After a handoff, the viewer goes away, the
promised browser window never opens, and the viewer comes back, all without
a word.

**Files:**
- Modify: `humble_catalog/humble_api.py` (add `login` beside `ensure_login`, around line 139)
- Modify: `humble_catalog/__main__.py` (the `login` dispatch branch)
- Test: `tests/test_humble_api.py`, `tests/test_main.py`

**Interfaces:**
- Produces: `humble_api.login(profile_dir=".playwright-profile") -> None`

- [ ] **Step 1: Write the failing tests**

In `tests/test_humble_api.py`, stubbing the same way
`test_ensure_login_refuses_to_open_a_browser_when_not_allowed` does:

```python
def test_login_with_a_live_session_says_so(monkeypatch, capsys):
    monkeypatch.setattr(humble_api, "get_cookies", lambda profile_dir=None: {})
    monkeypatch.setattr(humble_api.HumbleClient, "logged_in", lambda self: True)
    called = []
    monkeypatch.setattr(humble_api, "manual_login", lambda d: called.append(d))
    humble_api.login()
    assert called == []
    assert "already logged in" in capsys.readouterr().out.lower()


def test_login_with_an_expired_session_opens_the_window(monkeypatch):
    monkeypatch.setattr(humble_api, "get_cookies", lambda profile_dir=None: {})
    states = iter([False, True])
    monkeypatch.setattr(humble_api.HumbleClient, "logged_in",
                        lambda self: next(states))
    called = []
    monkeypatch.setattr(humble_api, "manual_login", lambda d: called.append(d))
    humble_api.login()
    assert called == [".playwright-profile"]
```

In `tests/test_main.py`:

```python
def test_login_dispatches_to_humble_api_login(monkeypatch):
    from humble_catalog import humble_api
    called = []
    monkeypatch.setattr(humble_api, "login", lambda: called.append(True))
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "login"])
    main()
    assert called == [True]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_humble_api.py tests/test_main.py -q -k login`
Expected: FAIL. `humble_api` has no attribute `login`.

- [ ] **Step 3: Implement**

In `humble_api.py`, after `ensure_login`:

```python
def login(profile_dir=".playwright-profile"):
    """The `login` command: ensure_login, but never silent.

    With a live session ensure_login returns without a word, which after
    a viewer handoff reads as "the promised window never opened".
    """
    if HumbleClient(get_cookies(profile_dir)).logged_in():
        print("Already logged in to HumbleBundle; nothing to do.")
        return
    ensure_login(profile_dir)
```

In `__main__.py`, change the `login` branch body to `humble_api.login()`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_humble_api.py tests/test_main.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/humble_api.py humble_catalog/__main__.py tests/test_humble_api.py tests/test_main.py
git commit -m "feat(login): say so when the session is already live"
```

---

### Task 4: The serve loop

`serve()` stops being one blocking call. Both paths, plain and `--lan`, build
their `(host, port, app, kwargs)` list once, then loop: bind, serve until
Ctrl-C or a handoff, and on a handoff run the command and bind again. The
**same app objects** are rebound, so the job runner's last result and the
handoff slot's `generation` survive the restart.

**Files:**
- Modify: `humble_catalog/webapp/__init__.py`: `_run_all`, `serve`, plus new `_bind` and `_serve_loop`. Add imports `traceback` and `from humble_catalog import handoff`.
- Test: `tests/test_webapp.py`

**Interfaces:**
- Consumes: `handoff.HandoffSlot`, `handoff.run_in_terminal`
- Produces: `app.config["HANDOFF"]`. It is a `HandoffSlot` on the loopback app built by `serve()`, and `None` from a bare `create_app()`.
- Produces: `_run_all(servers, slot=None) -> dict | None`. Returns the taken handoff request, or None on Ctrl-C.
- Produces: `_bind(wanted, error_cls, hint) -> list[server]`
- Produces: `_serve_loop(wanted, slot, viewer_url, error_cls, hint, servers) -> None`

- [ ] **Step 1: Update the shared stub, then write the failing tests**

In `tests/test_webapp.py`, in `_stub_servers`, change the `_run_all` stub to
the new signature:

```python
    monkeypatch.setattr(webmod, "_run_all", lambda servers, slot=None: None)
```

Then add:

```python
from humble_catalog import handoff as handoffmod


def test_create_app_alone_has_no_handoff(tmp_path):
    # The demo server and launch.json call create_app().run(): no serve
    # loop, so nothing could ever drain a handoff.
    assert create_app(db_path=str(tmp_path / "c.db")).config["HANDOFF"] is None


def test_serve_without_lan_goes_through_the_loop(tmp_path, monkeypatch, capsys):
    built = _stub_servers(monkeypatch)
    dbp = tmp_path / "catalog.db"
    _seed(dbp)
    webmod.serve(db_path=str(dbp), port=8087)
    [loop] = built
    assert (loop.host, loop.port) == ("127.0.0.1", 8087)
    assert isinstance(loop.app.config["HANDOFF"], handoffmod.HandoffSlot)
    assert "http://127.0.0.1:8087/" in capsys.readouterr().out


def _handoff_once(monkeypatch, run_result):
    """_run_all hands off once, then the user presses Ctrl-C."""
    calls = []

    def fake_run_all(servers, slot=None):
        calls.append(servers)
        if len(calls) == 1:
            slot.request("reset", ["python", "-m", "humble_catalog", "reset"])
            return slot.take()
        return None

    ran = []

    def fake_terminal(command, line):
        ran.append((command, line))
        if isinstance(run_result, Exception):
            raise run_result
        return run_result

    monkeypatch.setattr(webmod, "_run_all", fake_run_all)
    monkeypatch.setattr(handoffmod, "run_in_terminal", fake_terminal)
    return calls, ran


@pytest.mark.parametrize("lan", [None, "lan"])
def test_a_handoff_runs_the_command_then_rebinds_the_same_apps(
        tmp_path, monkeypatch, lan):
    built = _stub_servers(monkeypatch)
    calls, ran = _handoff_once(monkeypatch, 0)
    dbp = tmp_path / "catalog.db"
    _seed(dbp)
    webmod.serve(db_path=str(dbp), port=8087,
                 lan=lanmod.LanOptions() if lan else None)
    assert [c for c, _ in ran] == ["reset"]
    assert len(calls) == 2                       # served, handed off, served
    per_round = len(built) // 2
    first, second = built[:per_round], built[per_round:]
    # The same app objects, so the job runner's history and the slot's
    # generation survive the restart.
    assert [s.app for s in first] == [s.app for s in second]
    slot = first[0].app.config["HANDOFF"]
    assert slot.state()["generation"] == 1
    assert slot.state()["last"]["exit_code"] == 0
    assert slot.busy() is None


def test_a_crashing_handoff_still_brings_the_viewer_back(
        tmp_path, monkeypatch, capsys):
    built = _stub_servers(monkeypatch)
    calls, _ran = _handoff_once(monkeypatch, RuntimeError("boom"))
    dbp = tmp_path / "catalog.db"
    _seed(dbp)
    webmod.serve(db_path=str(dbp), port=8087)
    assert len(calls) == 2 and len(built) == 2
    slot = built[0].app.config["HANDOFF"]
    assert slot.state()["last"]["exit_code"] is None
    assert "boom" in capsys.readouterr().err


def test_the_browser_opens_once_not_after_every_handoff(tmp_path, monkeypatch):
    _stub_servers(monkeypatch)
    opened = []
    monkeypatch.setattr(webmod.webbrowser, "open", lambda url: opened.append(url))
    _handoff_once(monkeypatch, 0)
    dbp = tmp_path / "catalog.db"
    _seed(dbp)
    webmod.serve(db_path=str(dbp), port=8087)
    # The page reconnects by itself; a second open would be a second tab.
    assert opened == ["http://127.0.0.1:8087/"]


def test_run_all_stops_for_a_handoff_and_shuts_every_server():
    import threading

    class Server:
        def __init__(self):
            self.stop = threading.Event()
            self.closed = False
        def serve_forever(self):
            self.stop.wait(5)
        def shutdown(self):
            self.stop.set()
        def server_close(self):
            self.closed = True

    slot = handoffmod.HandoffSlot()
    slot.request("login", ["x"])
    servers = [Server(), Server()]
    req = webmod._run_all(servers, slot)
    assert req == {"command": "login", "argv": ["x"]}
    assert all(s.stop.is_set() and s.closed for s in servers)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -q -k "serve or handoff or run_all"`
Expected: FAIL, because `config["HANDOFF"]` is missing and `serve()` without `--lan` still calls `app.run`.

- [ ] **Step 3: Implement**

In `create_app`, beside `JOB_RUNNER`:

```python
    # Set by serve(), which is the only thing that can drain a handoff.
    # A bare create_app() (the demo server, launch.json) leaves it None
    # and the handoff route says so rather than queueing into nothing.
    app.config["HANDOFF"] = None
```

Replace `_run_all`:

```python
def _run_all(servers, slot=None):
    """Serve every server on its own thread until Ctrl-C or a handoff,
    then stop all. Returns the handoff request taken from `slot`, or None
    when it was Ctrl-C.

    Polled with sleep() rather than join(): on Windows a bare join() is not
    interrupted by Ctrl-C, so the process would ignore it. The same poll
    checks the slot, so no extra thread or event is needed.
    """
    threads = [threading.Thread(target=s.serve_forever, daemon=True)
               for s in servers]
    for t in threads:
        t.start()
    request = None
    try:
        while any(t.is_alive() for t in threads):
            request = slot.take() if slot is not None else None
            if request is not None:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()
    return request
```

Add `_bind`, which is the existing bind loop moved out of `serve()`, with
the error class and hint as parameters:

```python
def _bind(wanted, error_cls, hint):
    """Build (and so bind) every server before any starts, so a busy port
    stops the whole command rather than leaving half of it running."""
    servers = []
    for h, p, app, kw in wanted:
        try:
            servers.append(make_server(h, p, app, threaded=True, **kw))
        except (OSError, SystemExit) as exc:
            # Werkzeug 3.1 catches the bind OSError itself, prints a line
            # and calls sys.exit(1); a raw OSError is caught too, in case
            # it ever stops doing that.
            for s in servers:
                s.server_close()
            detail = f" ({exc})" if isinstance(exc, OSError) else ""
            raise error_cls(
                f"cannot listen on {h}:{p}{detail} -- {hint}") from exc
    return servers
```

The first round is bound by `serve()` itself, *before* `webbrowser.open`, so
a busy port is reported instead of opening a tab onto whatever already
holds it. So `_serve_loop` takes those already-bound servers and binds
again only after a handoff:

```python
def _serve_loop(wanted, slot, viewer_url, error_cls, hint, servers):
    """Serve; on a handoff, step down, run it, and serve again.

    `servers` is the first round, already bound by serve() so that a busy
    port is reported before the browser opens. Every way the command can
    end -- an exit code, Ctrl-C, a failed spawn, or a bug in this loop's
    own handling -- still rebinds, because a reset that crashed and left
    no viewer and no explanation is the failure this loop exists to
    prevent. Only Ctrl-C while SERVING ends it. The browser is not
    reopened: the page reconnects by itself, and a second webbrowser.open
    would be a second tab after every handoff.
    """
    while True:
        request = _run_all(servers, slot)
        if request is None:
            return
        code = None
        try:
            code = handoff.run_in_terminal(request["command"],
                                           request["argv"])
        except Exception:                     # noqa: BLE001 - see docstring
            traceback.print_exc()
        finally:
            slot.finish(code)
        servers = _bind(wanted, error_cls, hint)
        print(f"Viewer back at {viewer_url}", flush=True)
```

`serve()` in full. The `--lan` half is the existing code with the bind loop
swapped for `_bind`, the loopback app pulled into a variable so it can
carry the slot, and `_run_all(servers)` swapped for `_serve_loop`:

```python
LAN_HINT = "choose another port with --lan-port (or --port for the viewer itself)"


def serve(db_path="catalog.db", port=8087, lan=None):
    slot = handoff.HandoffSlot()
    viewer_url = f"http://127.0.0.1:{port}/"
    if lan is None:
        app = create_app(db_path=db_path)
        app.config["HANDOFF"] = slot
        wanted = [("127.0.0.1", port, app, {})]
        hint = "choose another port with --port"
        servers = _bind(wanted, SystemExit, hint)
        print(f"Viewer: {viewer_url}  (Ctrl-C to stop)")
        webbrowser.open(viewer_url)
        _serve_loop(wanted, slot, viewer_url, SystemExit, hint, servers)
        return

    from humble_catalog import lan as lanmod
    # ... unchanged: check_port calls, host, lan_dir, token, ensure_ca,
    #     issue_server_cert ...
    loopback = create_app(db_path=db_path)
    loopback.config["HANDOFF"] = slot
    wanted = [
        ("127.0.0.1", port, loopback, {}),
        (host, lan_port,
         create_lan_app(db_path=db_path, host=host, port=lan_port, token=token),
         {"ssl_context": lanmod.ssl_context(crt, key),
          "request_handler": LanRequestHandler}),
    ]
    if lan.setup:
        wanted.append((host, lan_port + 1, lanmod.ca_download_app(lan_dir), {}))
    servers = _bind(wanted, lanmod.LanStateError, LAN_HINT)
    # ... unchanged: print_instructions(...) ...
    webbrowser.open(viewer_url)
    _serve_loop(wanted, slot, viewer_url, lanmod.LanStateError, LAN_HINT,
                servers)
```

The two `# ... unchanged` comments mark code that stays exactly as it is
today. Do not retype it. `SystemExit(message)` is the plain path's error
class because `__main__` does not catch `LanStateError` there, and a
`SystemExit` carrying a string prints it and exits 1. The first-round bind
failure used to be Werkzeug's own line from `app.run`; now it is ours and
names `--port`.
The busy-port tests (`test_a_busy_port_closes_what_was_opened_and_says_which`)
must pass unchanged, because the message text is identical.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -q`
Expected: PASS, including every existing `test_serve_lan_*` and busy-port test.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "feat(serve): a loop that steps down for a terminal handoff and comes back"
```

---

### Task 5: `GET /api/backups`, `POST /api/jobs/handoff`, and handoff state in `/api/jobs`

**Files:**
- Modify: `humble_catalog/webapp/__init__.py`. Add `create_app(..., backups_dir="backups")`, which sets `app.config["BACKUPS_DIR"]`. Add the two routes inside `_register_write_routes`, beside the job routes, and extend `job_state` and `start_job`.
- Test: `tests/test_webapp.py`

**Interfaces:**
- Consumes: `handoff.argv`, `handoff.list_backups`, `HandoffSlot.request/busy/state`, and `JobRunner.state()["running"]`
- Produces (HTTP):
  - `GET /api/backups` → `200 {"backups": [{name, size, modified, covers}]}`
  - `POST /api/jobs/handoff` takes `{command, options?, snapshot?}` and answers `200 {"command", "generation"}`. It answers `400` on a whitelist or snapshot refusal, and `409` when there is no serve loop, a job is running, or a handoff is already pending.
  - `GET /api/jobs` gains `"handoff": {"available": bool, "generation": int, "pending": str|None, "last": {...}|None}`
  - `POST /api/jobs/start` and `POST /api/jobs/import-sheets` answer `409` while a handoff is pending.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_webapp.py`, after the job-route tests:

```python
def _handoff_client(tmp_path, slot=True):
    backups = tmp_path / "backups"
    app = create_app(db_path=str(tmp_path / "catalog.db"),
                     backups_dir=str(backups))
    runner = _StubRunner()
    app.config["JOB_RUNNER"] = runner
    s = handoffmod.HandoffSlot() if slot else None
    app.config["HANDOFF"] = s
    return app.test_client(), runner, s, backups


def _write_snapshot(backups, stamp="20260101-120000"):
    backups.mkdir(exist_ok=True)
    (backups / f"catalog-{stamp}.db").write_bytes(b"x")
    return f"catalog-{stamp}.db"


def test_backups_lists_the_snapshots(tmp_path):
    client, _r, _s, backups = _handoff_client(tmp_path)
    name = _write_snapshot(backups)
    body = client.get("/api/backups").get_json()
    assert [b["name"] for b in body["backups"]] == [name]


def test_handoff_queues_the_whitelisted_command(tmp_path):
    client, _r, slot, _b = _handoff_client(tmp_path)
    resp = client.post("/api/jobs/handoff", json={"command": "reset"})
    assert resp.status_code == 200
    assert resp.get_json() == {"command": "reset", "generation": 0}
    assert slot.take()["argv"][-1] == "reset"


def test_handoff_restore_takes_a_listed_snapshot(tmp_path):
    client, _r, slot, backups = _handoff_client(tmp_path)
    name = _write_snapshot(backups)
    resp = client.post("/api/jobs/handoff", json={
        "command": "restore", "options": {"covers": True}, "snapshot": name})
    assert resp.status_code == 200
    line = slot.take()["argv"]
    assert line[-2:] == [str(backups / name), "--covers"]


@pytest.mark.parametrize("body", [
    {"command": "harvest"},                      # an in-page command
    {"command": "restore"},                      # no snapshot
    {"command": "restore", "snapshot": "../catalog.db"},
    {"command": "reset", "options": {"covers": True}},
    {"command": "reset", "options": ["--yes"]},
    {},
])
def test_handoff_refuses_what_the_whitelist_does_not_allow(tmp_path, body):
    client, _r, slot, _b = _handoff_client(tmp_path)
    assert client.post("/api/jobs/handoff", json=body).status_code == 400
    assert slot.busy() is None


def test_handoff_refuses_a_malformed_body(tmp_path):
    client, _r, _s, _b = _handoff_client(tmp_path)
    for body in ([], "reset", None):
        resp = client.post("/api/jobs/handoff", json=body)
        assert resp.status_code == 400
        assert resp.is_json


def test_handoff_without_a_serve_loop_says_how_to_get_one(tmp_path):
    client, _r, _s, _b = _handoff_client(tmp_path, slot=False)
    resp = client.post("/api/jobs/handoff", json={"command": "login"})
    assert resp.status_code == 409
    assert "humble_catalog serve" in resp.get_json()["error"]


def test_handoff_waits_for_a_running_job(tmp_path):
    client, runner, slot, _b = _handoff_client(tmp_path)
    runner.state = lambda: {"running": {"command": "harvest"}, "log": [],
                            "last": None}
    resp = client.post("/api/jobs/handoff", json={"command": "reset"})
    assert resp.status_code == 409
    assert "harvest" in resp.get_json()["error"]
    assert slot.busy() is None


def test_a_second_handoff_is_refused(tmp_path):
    client, _r, _s, _b = _handoff_client(tmp_path)
    client.post("/api/jobs/handoff", json={"command": "login"})
    assert client.post("/api/jobs/handoff",
                       json={"command": "reset"}).status_code == 409


def test_no_job_starts_while_a_handoff_is_pending(tmp_path):
    client, runner, _s, _b = _handoff_client(tmp_path)
    client.post("/api/jobs/handoff", json={"command": "reset"})
    resp = client.post("/api/jobs/start", json={"command": "harvest"})
    assert resp.status_code == 409
    assert runner.started == []


def test_jobs_reports_the_handoff_state(tmp_path):
    client, _r, slot, _b = _handoff_client(tmp_path)
    slot.request("login", ["x"]); slot.take(); slot.finish(0)
    body = client.get("/api/jobs").get_json()
    assert body["handoff"]["available"] is True
    assert body["handoff"]["generation"] == 1
    assert body["handoff"]["last"]["command"] == "login"


def test_jobs_reports_no_handoff_without_a_serve_loop(tmp_path):
    client, _r, _s, _b = _handoff_client(tmp_path, slot=False)
    h = client.get("/api/jobs").get_json()["handoff"]
    assert h == {"available": False, "generation": 0, "pending": None,
                 "last": None}
```

Also add `"/api/backups"` and `"/api/jobs/handoff"` to whatever the suite
uses to pin loopback-only routes, if such a list exists. Search for
`/api/jobs/start` in `tests/test_webapp.py` to find out. `LAN_RULES` does
**not** change.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -q -k "handoff or backups"`
Expected: FAIL. `create_app` gets an unexpected keyword `backups_dir`, and the routes are 404.

- [ ] **Step 3: Implement**

Change `create_app` to `def create_app(db_path="catalog.db", covers_dir="covers", backups_dir="backups"):`
and add `app.config["BACKUPS_DIR"] = backups_dir`. The default matches
`backup`'s CLI default and is relative to the working directory, like
`catalog.db`.

In `_register_write_routes`, after `_runner()`:

```python
    def _slot():
        return app.config.get("HANDOFF")

    @app.get("/api/backups")
    def backups():
        # So restore is chosen from a list, never typed as a path.
        return jsonify({"backups": handoff.list_backups(
            app.config["BACKUPS_DIR"])})

    @app.post("/api/jobs/handoff")
    def handoff_job():
        """Queue login, reset or restore for the terminal serve runs in.

        The answer goes out before the server steps down; the page then
        shows the takeover screen and waits for `generation` to move.
        The page's two clicks only ARM this. reset and restore still ask
        for a typed word at the console, and that is the real guard.
        """
        data = _json_object_or_none()
        if data is None:
            return jsonify({"error": "a JSON object is required"}), 400
        slot = _slot()
        if slot is None:
            return jsonify({"error": "this viewer was not started with "
                            "`python -m humble_catalog serve`, so it has no "
                            "terminal to hand over to"}), 409
        command = _text_field(data, "command")
        options = data.get("options") or {}
        if not command:
            return jsonify({"error": "command required"}), 400
        if not isinstance(options, dict):
            return jsonify({"error": "options must be an object"}), 400
        running = _runner().state()["running"]
        if running:
            # restore cannot swap a file a job holds open, and reset must
            # not wipe the catalog under one.
            return jsonify({"error": f"{running['command']} is running; "
                            "cancel it or let it finish first"}), 409
        try:
            line = handoff.argv(command, options, data.get("snapshot"),
                                app.config["BACKUPS_DIR"])
            generation = slot.request(command, line)
        except jobs.Busy as exc:
            return jsonify({"error": str(exc)}), 409
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"command": command, "generation": generation})
```

At the top of `start_job` and `import_sheets_job`, before any work (in
`import_sheets_job` that means before the temp dir is created):

```python
        pending = _slot() and _slot().busy()
        if pending:
            return jsonify({"error": f"the viewer is handing {pending} to "
                            "the terminal"}), 409
```

In `job_state`, before `return`:

```python
        slot = _slot()
        state["handoff"] = ({"available": True, **slot.state()} if slot
                            else {"available": False, "generation": 0,
                                  "pending": None, "last": None})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -q`
Expected: PASS, and `test_lan_app_serves_only_the_pinned_read_routes` still passes.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "feat: POST /api/jobs/handoff, GET /api/backups and handoff state in /api/jobs"
```

---

### Task 6: The page: handoff cards, restore picker, takeover and reconnect

**Files:**
- Modify: `humble_catalog/webapp/static/tasks.js`
- Modify: `humble_catalog/webapp/static/index.html`. Add the overlay just inside `<body>` or after `section-tasks`.
- Modify: `humble_catalog/webapp/static/style.css` (Tasks block, lines ~452-480)
- Modify: `tests/js/harness.mjs`. Add `TAKEOVER_TEXT` to the published bindings next to `TASK_CARDS, TASK_GROUPS, …`.
- Test: `tests/test_webapp_js.py`, `tests/test_webapp.py`

**Interfaces:**
- Consumes: `POST /api/jobs/handoff`, `GET /api/backups`, and `state.handoff` from `GET /api/jobs` (Task 5); `armOrFire`, `post`, `esc`, `$` (app.js)
- Produces (JS, global function declarations unless noted):
  - `TASK_CARDS` entries may carry `handoff: true` and `picker: "snapshot"`
  - `TASK_GROUPS` gains `"Danger"` (last)
  - `const TAKEOVER_TEXT = {login, reset, restore}` (published in the harness)
  - `handoffBody(command, options) -> object`
  - `async startHandoff(command, options) -> "handed" | "error"`
  - `renderTakeover(command) -> string` (writes `#handoff-screen`)
  - `async reconnect(generation, sleep = (ms) => new Promise((r) => setTimeout(r, ms)))`
  - `renderBackups(list) -> string` (writes `#restore-snapshot`)
  - `async loadBackups()`

- [ ] **Step 1: Write the failing tests**

In `tests/test_webapp_js.py`, replace `test_task_cards_cover_every_headless_command` with:

```python
def test_task_cards_cover_every_command_in_both_whitelists():
    from humble_catalog import handoff, jobs
    cards = eval_js("app.TASK_CARDS")
    in_page = {c["command"] for c in cards if not c.get("handoff")}
    handed = {c["command"] for c in cards if c.get("handoff")}
    # Each card posts to the endpoint whose whitelist owns its command. A
    # card on the wrong side would answer 400, which is a dead button.
    assert in_page == set(jobs.COMMANDS)
    assert handed == set(handoff.COMMANDS)


def test_handoff_cards_say_they_use_the_terminal():
    html = eval_js("(app.renderTasks(), dom.writes['#task-cards'])")
    assert html.count("uses the terminal") == 3
    assert 'data-handoff="1"' in html
    assert "<h3>Danger</h3>" in html


def test_reset_sits_alone_in_the_danger_group():
    cards = eval_js("app.TASK_CARDS.filter((c) => c.group === 'Danger')")
    assert [c["command"] for c in cards] == ["reset"]


def test_restore_body_carries_the_chosen_snapshot_and_covers():
    body = eval_js("""(() => {
        document.querySelector("#restore-snapshot").value =
          "catalog-20260101-120000.db";
        document.querySelector("#restore-covers").checked = true;
        return handoffBody("restore", {});
      })()""")
    assert body == {"command": "restore", "options": {"covers": True},
                    "snapshot": "catalog-20260101-120000.db"}


def test_a_plain_handoff_body_has_no_snapshot():
    assert eval_js('handoffBody("reset", {})') == {
        "command": "reset", "options": {}}


def test_start_handoff_shows_the_takeover_and_reconnects():
    result = eval_js("""(async () => {
        const posted = [];
        let reloaded = false;
        location.reload = () => { reloaded = true; };
        let polls = 0;
        app.setFetch((url, init) => {
          if (init && init.method === "POST") {
            posted.push([url, JSON.parse(init.body)]);
            return Promise.resolve({ok: true, status: 200,
              json: () => Promise.resolve({command: "reset", generation: 4})});
          }
          polls += 1;
          // down, still the old server, then back with a new generation
          if (polls === 1) return Promise.reject(new TypeError("refused"));
          const generation = polls === 2 ? 4 : 5;
          return Promise.resolve({ok: true,
            json: () => Promise.resolve({handoff: {generation}})});
        });
        globalThis.__sleep = () => Promise.resolve();
        const how = await startHandoff("reset", {}, globalThis.__sleep);
        return {how, posted, polls, reloaded,
                screen: dom.writes["#handoff-screen"],
                hidden: document.querySelector("#handoff-screen").hidden};
      })()""")
    assert result["how"] == "handed"
    assert result["posted"] == [["/api/jobs/handoff",
                                 {"command": "reset", "options": {}}]]
    assert result["polls"] == 3 and result["reloaded"] is True
    assert "RESET" in result["screen"] and result["hidden"] is False


def test_a_refused_handoff_stays_on_the_page():
    result = eval_js("""(async () => {
        app.setFetch(() => Promise.resolve({ok: false, status: 409,
          json: () => Promise.resolve({error: "harvest is running"})}));
        const how = await startHandoff("reset", {}, () => Promise.resolve());
        return {how, msg: dom.writes["#task-message:text"],
                screen: dom.writes["#handoff-screen"] || ""};
      })()""")
    assert result["how"] == "error"
    assert "harvest is running" in result["msg"]
    # A refusal must not tell the user to go and type RESET somewhere.
    assert "RESET" not in result["screen"]


def test_every_handoff_command_has_takeover_text():
    from humble_catalog import handoff
    text = eval_js("app.TAKEOVER_TEXT")
    assert set(text) == set(handoff.COMMANDS)
    assert "RESET" in text["reset"] and "RESTORE" in text["restore"]


def test_takeover_says_the_page_comes_back_by_itself():
    html = eval_js('renderTakeover("login")')
    assert "reconnect" in html.lower()


def test_render_backups_escapes_and_marks_covers():
    html = eval_js("""renderBackups([
        {name: "catalog-20260301-090000.db", size: 2000000,
         modified: "2026-03-01 09:00", covers: true},
        {name: "catalog-<x>.db", size: 1, modified: "m", covers: false}])""")
    assert "catalog-20260301-090000.db" in html and "covers" in html
    assert "<x>" not in html


def test_render_backups_with_none_disables_restore():
    html = eval_js("renderBackups([])")
    assert "No snapshots" in html
    assert eval_js("""(renderBackups([]),
        document.querySelector("#restore-go").disabled)""") is True


def test_an_expired_session_offers_a_log_in_handoff():
    html = eval_js("""renderJobPanel({
      running: null, progress: [],
      log: ["HumbleBundle session expired -- run "
            + "'python -m humble_catalog login', then try again."],
      last: {command: "extract", state: "failed", exit_code: 1,
             finished_at: "2026-08-04T00:01:00+00:00"}})""")
    assert 'data-command="login"' in html and 'data-handoff="1"' in html


def test_job_panel_reports_the_last_handoff():
    html = eval_js("""renderJobPanel({running: null, progress: [], log: [],
      last: null, handoff: {available: true, generation: 1, pending: null,
        last: {command: "reset", exit_code: 0,
               finished_at: "2026-09-19T00:00:00+00:00"}}})""")
    assert "reset" in html and "terminal" in html.lower()
```

The existing `test_job_panel_translates_an_expired_session` asserts that
`"humble_catalog login"` appears in the HTML. Keep that line in the hint
text, as the fallback for a viewer with no serve loop.

In `tests/test_webapp.py`, **replace** `test_tasks_tab_offers_no_terminal_only_command` with:

```python
def test_index_has_the_takeover_screen():
    html = (Path(__file__).parent.parent / "humble_catalog" / "webapp"
            / "static" / "index.html").read_text(encoding="utf-8")
    assert '<div id="handoff-screen"' in html and "hidden" in html
```

`startHandoff(command, options, sleep)` forwards `sleep` to `reconnect`. The
click handler omits it, so `reconnect`'s default applies. The tests pass an
instant one.

Also add a pollJobs test for the snapshot refresh:

```python
def test_the_first_poll_loads_the_snapshot_list_even_with_no_job_history():
    seen = eval_js("""(async () => {
        const seen = [];
        app.setFetch((url) => { seen.push(url); return Promise.resolve({
          json: () => Promise.resolve(url === "/api/backups"
            ? {backups: []}
            : {running: null, progress: [], log: [], last: null})}); });
        await pollJobs();
        await pollJobs();
        return seen;
      })()""")
    # Once on the first poll, not again until a job finishes.
    assert seen.count("/api/backups") == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py tests/test_webapp.py -q -k "task or handoff or takeover or backups or job_panel"`
Expected: FAIL, because `handoffBody`, `startHandoff`, `TAKEOVER_TEXT` and the rest are not defined. (If Node is not installed the JS tests skip, and the runner must install Node before continuing, because these are the tests for this task.)

- [ ] **Step 3: Implement `tasks.js`**

Update the header comment. `login`, `reset` and `restore` are now cards
that post to `/api/jobs/handoff`, and `handoff.COMMANDS` is their
whitelist, pinned by a test just like the in-page one.

Add to `TASK_CARDS`:

```js
  {group: "Update", command: "login", label: "Log in to HumbleBundle",
   handoff: true,
   note: "Opens a browser window to sign in. Needed when a fetch says the session expired."},
  {group: "Backup", command: "restore", label: "Restore a snapshot",
   handoff: true, picker: "snapshot",
   note: "Puts a backup back over the catalog, after snapshotting the current one."},
  {group: "Danger", command: "reset", label: "Reset the catalog",
   handoff: true,
   note: "Wipes the derived catalog for a clean rebuild. Keeps downloads, covers and your ratings, tags and notes."},
```

and `const TASK_GROUPS = ["Update", "Enrich", "Import", "Backup", "Diagnose", "Danger"];`

In `renderTasks`, render handoff cards with the mark, the flag and, for the
picker card, the snapshot controls. Give the Danger group a class so the CSS
can set it apart:

```js
function taskCard(c) {
  const picker = c.picker === "snapshot" ? `
    <div class="task-picker">
      <select id="restore-snapshot" aria-label="Snapshot to restore"></select>
      <label><input type="checkbox" id="restore-covers"> with covers</label>
    </div>` : "";
  return `
    <div class="task-card">
      <div class="task-label">${esc(c.label)}${c.handoff
        ? ` <span class="task-terminal">uses the terminal</span>` : ""}</div>
      <div class="task-note">${esc(c.note)}</div>
      ${picker}
      <button class="task-go"${c.picker === "snapshot" ? ' id="restore-go"' : ""}
              data-command="${esc(c.command)}"${c.handoff ? ' data-handoff="1"' : ""}
              data-options='${esc(JSON.stringify(c.options || {}))}'
              >Run</button>
    </div>`;
}

function renderTasks() {
  const el = $("#task-cards");
  if (!el) return;
  el.innerHTML = TASK_GROUPS.map((group) => `
    <div class="task-group${group === "Danger" ? " task-danger" : ""}">
      <h3>${esc(group)}</h3>
      ${TASK_CARDS.filter((c) => c.group === group).map(taskCard).join("")}
    </div>`).join("");
  return el.innerHTML;
}
```

The backup list, the takeover and the reconnect:

```js
function renderBackups(list) {
  const sel = $("#restore-snapshot");
  const go = $("#restore-go");
  if (!sel) return "";
  sel.innerHTML = list.length
    ? list.map((b) => `<option value="${esc(b.name)}">${esc(b.modified)}
        (${esc((b.size / 1e6).toFixed(1))} MB${b.covers ? ", covers" : ""})
        </option>`).join("")
    : `<option value="">No snapshots in backups/ yet</option>`;
  sel.disabled = list.length === 0;
  if (go) go.disabled = list.length === 0;
  return sel.innerHTML;
}

async function loadBackups() {
  const {backups} = await (await fetch("/api/backups")).json();
  renderBackups(backups || []);
}

// What to look at while the viewer is away. Shown only AFTER the second
// click -- the arm text on the button is the warning; this is the
// instruction.
const TAKEOVER_TEXT = {
  login: "A browser window is opening. Sign in to HumbleBundle, wait "
       + "for your library page, then close that window.",
  reset: "Switch to the terminal window you started the viewer from. "
       + "It asks you to type RESET; anything else cancels and changes "
       + "nothing.",
  restore: "Switch to the terminal window you started the viewer from. "
         + "It shows both catalogs and asks you to type RESTORE; anything "
         + "else cancels. The current catalog is snapshotted first.",
};

function renderTakeover(command) {
  const el = $("#handoff-screen");
  el.innerHTML = `<div class="handoff-box">
      <h2>${esc(command)} is running in the terminal</h2>
      <p>${esc(TAKEOVER_TEXT[command] || "")}</p>
      <p>The viewer is closed until it finishes. This page will reconnect
         by itself.</p>
    </div>`;
  el.hidden = false;
  return el.innerHTML;
}

function handoffBody(command, options) {
  if (command !== "restore") return {command, options};
  return {command,
          options: {covers: Boolean($("#restore-covers").checked)},
          snapshot: $("#restore-snapshot").value};
}

// Reload once the server answers with a generation past the one the
// request was answered with. Polling "/" alone cannot tell "back" from
// "not gone down yet": the first poll can land before the server steps
// down, and a reload then meets a refused connection mid-handoff. There is
// no timeout: a user reading the reset prompt may take minutes.
async function reconnect(generation,
                         sleep = (ms) => new Promise((r) => setTimeout(r, ms))) {
  for (;;) {
    await sleep(1000);
    try {
      const state = await (await fetch("/api/jobs")).json();
      if (state.handoff && state.handoff.generation > generation) {
        location.reload();
        return;
      }
    } catch (err) {
      // Refused while the command runs. That is the expected state.
    }
  }
}

async function startHandoff(command, options, sleep) {
  taskMessage("");
  const resp = await post("/api/jobs/handoff", handoffBody(command, options));
  if (!resp.ok) {
    taskMessage((await resp.json()).error || "Could not hand that over.");
    return "error";
  }
  const {generation} = await resp.json();
  renderTakeover(command);
  await reconnect(generation, sleep);
  return "handed";
}
```

In the click handler, before the `import_sheets` branch:

```js
    if (btn.dataset.handoff) {
      // Two clicks only ARM the handoff. reset and restore still ask for
      // a word typed at the console; that, not this, is the real guard.
      armOrFire(btn, () => startHandoff(command, options));
      return;
    }
```

In `renderJobPanel`, change the expired-session hint to include a button the
same click handler already serves, and keep the command text as the fallback:

```js
    parts.push(`<div class="job-hint">Your HumbleBundle session has expired.
      <button class="task-go" data-command="login" data-handoff="1"
              data-options='{}'>Log in</button>
      (or run <code>python -m humble_catalog login</code> in the terminal
      running this viewer), then try again.</div>`);
```

and, after the `state.last` block, add the last handoff line:

```js
  const handed = state.handoff && state.handoff.last;
  if (handed)
    parts.push(`<div class="job-handoff"><strong>${esc(handed.command)}</strong>
      ran in the terminal${handed.exit_code === null ? " and was interrupted"
        : ` (exit ${esc(handed.exit_code)})`}; the terminal shows what it did.</div>`);
```

Refresh the snapshot list when the page boots and whenever a job has
finished, because a `backup` job adds one. In `pollJobs`:

```js
// undefined, not null: a catalog with no job history reports last: null,
// and the first poll must still differ so it loads the list.
let lastFinished;
async function pollJobs() {
  const state = await (await fetch("/api/jobs")).json();
  renderJobPanel(state);
  const finished = state.last ? state.last.finished_at : null;
  if (finished !== lastFinished) {
    lastFinished = finished;
    // Awaited so a test can count the request; still never fatal.
    await loadBackups().catch((err) =>
      console.error("loadBackups() failed:", err));
  }
}
```

The first poll therefore also serves as the initial load. The picker exists
by then: `renderTasks` is one of the renderers `load()` runs
(`app.js:45`), `boot()` awaits `load()`, and polling starts only after
`boot()` (`shell.js`, `start`).

`index.html`, after `</section>` of `section-tasks`:

```html
  <div id="handoff-screen" hidden role="alertdialog" aria-live="assertive"></div>
```

`style.css`, appended to the Tasks block. Use only existing custom
properties, as the block's own comment requires:

```css
.task-terminal {
  margin-left: .4rem; padding: 0 .4rem; border-radius: 4px;
  font-size: .75rem; font-weight: 400; color: var(--muted);
  border: 1px solid var(--border);
}
.task-picker { grid-column: 1; display: flex; gap: .6rem; flex-wrap: wrap;
               align-items: center; }
.task-danger { padding-top: 1rem; border-top: 1px solid var(--panel-warn-border); }
.task-danger .task-card { border-color: var(--panel-warn-border); }
.job-handoff { margin-top: .4rem; color: var(--muted); }
#handoff-screen {
  position: fixed; inset: 0; z-index: 100;
  display: grid; place-items: center; padding: 16px;
  background: color-mix(in srgb, var(--bg) 85%, transparent);
}
#handoff-screen[hidden] { display: none; }
.handoff-box {
  max-width: 32rem; padding: 1.2rem 1.4rem; border-radius: 8px;
  background: var(--surface); border: 1px solid var(--border);
}
```

`--bg` and `--surface` are defined on `:root` and in both dark blocks.

Harness: add `TAKEOVER_TEXT` to the `publish` block in `tests/js/harness.mjs`
next to `TASK_CARDS, TASK_GROUPS`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py tests/test_webapp.py -q`
Expected: PASS, including the existing `test_render_tasks_groups_every_card_and_escapes_its_text`
(its `<h3>{group}</h3>` check now covers Danger) and
`test_job_panel_translates_an_expired_session`.

- [ ] **Step 5: Look at it (demo catalog only)**

Start the `catalog-viewer-demo` preview (port 8099, invented titles). Open
`#/tasks` and check the three handoff cards, the Danger group, and that the
restore picker reads "No snapshots" and is disabled. A handoff click
answers the "not started with serve" 409 in the task message, because the
demo server is a bare `create_app()`. That is correct, and it is the only
handoff path an automated check can reach. Resize to mobile and check the
cards and picker wrap without horizontal scroll. Do **not** screenshot the
real catalog.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/webapp/static/tasks.js humble_catalog/webapp/static/index.html humble_catalog/webapp/static/style.css tests/js/harness.mjs tests/test_webapp_js.py tests/test_webapp.py
git commit -m "feat(viewer): login, reset and restore cards that hand over to the terminal"
```

---

### Task 7: Docs, and the privacy gate

**Files:**
- Modify: `README.md`. Update the Tasks paragraph (~line 284) and "The viewer's exposure" (~line 527).
- Modify: `docs/BACKLOG.md`. Update the "Still outstanding: Phase 2 … (#8)" line (~line 136).
- Test: `tests/test_webapp.py`

- [ ] **Step 1: Write the failing test**

```python
def test_readme_explains_the_handoff_and_its_guard():
    readme = _readme()
    exposure = readme.split("### The viewer's exposure")[1]
    # The destructive path's real guard is the typed word at the console.
    # The exposure section must say a local process can now QUEUE a
    # reset, and why that still cannot wipe anything unattended.
    assert "handoff" in exposure.lower() or "hand" in exposure.lower()
    assert "RESET" in exposure
    assert "needed only for `login`, `reset` and `restore`" not in readme
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -q -k readme`
Expected: FAIL on the `RESET` assertion.

- [ ] **Step 3: Edit the docs**

README Tasks paragraph. Replace the sentence that begins "so the terminal
is needed only for `login`, `reset` and `restore`" with prose saying that
those three are cards too, marked "uses the terminal". Clicking one twice
steps the viewer down and runs the command in the console `serve` was
started from, where `reset` and `restore` still ask for their typed word.
The page then reconnects by itself. Add one sentence saying that Ctrl-C
during a handed-over command cancels that command and brings the viewer
back, and a second Ctrl-C quits `serve`. Say that a viewer started any
other way than `python -m humble_catalog serve` cannot hand over.

README exposure section. Replace "And the destructive commands are not
reachable this way at all: `reset` and `restore` still require a word typed
at an interactive terminal." with a statement that a process on this
machine can now *queue* `login`, `reset` or `restore` for the console. The
wipe and the restore still happen only after a human types `RESET` or
`RESTORE` there. `login` only opens a browser window. The restore snapshot
must be one of the files already in `backups/`.

BACKLOG. Change "Still outstanding: Phase 2 …" to a one-line note that
Phase 2 shipped, pointing to this plan. Match the tone of neighbouring
entries and add no private data.

Update the `jobs.py` comment above `COMMANDS` if Task 1 did not already, and
check that `tasks.js`'s header comment no longer says the handoff is
"separate work".

- [ ] **Step 4: Run the full gate**

Run: `pwsh scripts/windows/verify.ps1`
Expected: tests pass, `check_no_data_tracked.py` and `leak_check.py` are
clean, and it ends with "Verified: tests pass, no private data in the
repo." Read `leak_check.py`'s output directly; never pipe it.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/BACKLOG.md humble_catalog/jobs.py humble_catalog/webapp/static/tasks.js tests/test_webapp.py
git commit -m "docs: the terminal handoff, and what it adds to the viewer's exposure"
```

---

### Task 8: Human smoke test (not automatable)

The two things only a real console can show are that `input()` reads the
typed word through the handoff and that `restore`'s `os.replace` succeeds
once the viewer has let go of `catalog.db`. The spec forbids tests that
invoke real `reset`/`restore`/`login`, and an agent cannot type at the
console, so **the owner runs this**. Use a throwaway catalog so nothing real
is at stake.

- [ ] **Step 1: Prepare a scratch catalog.** In a new directory outside the
  repo, copy a demo database in as `catalog.db`. `scripts/demo_catalog.py`
  prints or builds one, so read it for the path. Then run `backup` once so
  `backups/` has a snapshot:
  `<repo>\.venv\Scripts\python -m humble_catalog backup`
- [ ] **Step 2:** In the same directory, run
  `<repo>\.venv\Scripts\python -m humble_catalog serve --port 8099`.
- [ ] **Step 3: reset.** Tasks → Danger → Reset → click twice. Check that
  the takeover screen appears, the console shows the banner and the RESET
  prompt, and typing `no` prints "Aborted". Check that the page reloads by
  itself and the job panel says reset ran in the terminal.
- [ ] **Step 4: restore.** Pick the snapshot, click twice, and type
  `RESTORE`. Check that the console says "Restored …" (not "open in another
  process") and the page comes back.
- [ ] **Step 5: Ctrl-C.** Start `reset` again and press Ctrl-C at the
  prompt. Check that the viewer comes back, then press Ctrl-C again and
  check that `serve` exits.
- [ ] **Step 6: login.** With a live session, check that the console says
  "Already logged in". (Optional: with an expired session, check that the
  browser window opens in front.)
- [ ] **Step 7: busy guards.** Start "Harvest metadata", then try Reset.
  Check that the task message says harvest is running. Cancel the harvest.

Any failure goes back to the relevant task. Then open the PR with
"Closes #8" in the description.
