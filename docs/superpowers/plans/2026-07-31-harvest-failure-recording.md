# Harvest Failure Recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record which titles each source failed to fetch and how many runs each has failed, so a few harvests reveal whether Google's 503s are transient or reproducible.

**Architecture:** A new `source_failure` table, written by `harvest._run_pool` in the branch that already classifies non-429 errors, through a new `failures` module shaped like the existing `quota` module. Two read paths: an end-of-run summary block and a `harvest --failures` flag. No harvesting behaviour changes at all.

**Tech Stack:** Python 3.12, SQLite (WAL), pytest, `requests`. No new dependencies.

Spec: `docs/superpowers/specs/2026-07-31-harvest-failure-recording-design.md`.

## Global Constraints

- **Privacy is non-negotiable.** Committed text (tests, fixtures, docs, commit messages) must use invented names from `docs/TEST-DATA.md` — never a real item. This plan's tests use *Gray Waters*, *Shadow Hound Vol. 1-6*, *Learn C#*, *Moonfall Vol. 1-3*, *The Endless Wars: Inferno!*, all already listed there.
- `scripts/leak_check.py` matches **substrings**, so ordinary prose can trip it. Run it directly, never piped. If it flags a phrase in prose, reword the prose — do not add to `ALLOWED`.
- Run `.venv/Scripts/python -m pip`, never `.venv/Scripts/pip` (the shim exits 1 silently).
- Every commit message ends with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Never commit `catalog.db*`, `covers/`, `cache/`, or `Reference spreadsheets/`.
- Terminal output that includes catalog titles must pass through `stats.console_safe(text, encoding)` — the default Windows console is cp1252 and titles hold accents and curly apostrophes (*Café of Broken Clocks*, *Innkeeper's Ledger*). `keys.py:289` and `bundle_preview.py:425` are the existing precedents; import it from `stats`, do not move it.
- Tests run with `.venv/Scripts/python -m pytest`.

---

## File Structure

| File | Responsibility |
|---|---|
| `humble_catalog/failures.py` | **New.** The `source_failure` table's reader/writer. Imports nothing from the package, as `quota.py` does. |
| `humble_catalog/db.py` | `SCHEMA` gains `source_failure`; migration 10 carries the version. |
| `humble_catalog/sources/base.py` | Gains `redact()`, the shared credential scrubber for source error strings. |
| `humble_catalog/check.py` | Loses its private copy of the redaction regex; calls `redact()`. |
| `humble_catalog/harvest.py` | Records failures; builds the summary lines; adds `report_failures()`. |
| `humble_catalog/progress.py` | `finish()` writes a repeat-failures block it is handed. Formats nothing itself. |
| `humble_catalog/__main__.py` | `harvest --failures` flag and its dispatch. |
| `tests/test_failures.py` | **New.** Unit tests for the module. |
| `tests/test_harvest.py`, `tests/test_sources_base.py`, `tests/test_db.py` | Integration, redaction, migration. |

---

### Task 1: The `source_failure` table and migration 10

**Files:**
- Modify: `humble_catalog/db.py:60-62` (end of `SCHEMA`), `humble_catalog/db.py:417-426` (after migration 9)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces: table `source_failure(source TEXT, title TEXT, failures INTEGER, first_failed_at TEXT, last_failed_at TEXT, last_error TEXT, PRIMARY KEY (source, title))`; `PRAGMA user_version` reaches `10`.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_db.py`:

```python
def test_migration_10_adds_source_failure(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    conn.execute("PRAGMA user_version = 9")   # pretend this is a pre-10 file
    conn.execute("DROP TABLE source_failure")
    conn.commit()
    conn.close()

    conn = db.connect(path)                   # reconnect triggers the migration
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(source_failure)")}
    assert cols == {"source", "title", "failures",
                    "first_failed_at", "last_failed_at", "last_error"}
```

- [ ] **Step 2: Run it and watch it fail**

```bash
.venv/Scripts/python -m pytest tests/test_db.py::test_migration_10_adds_source_failure -v
```

Expected: FAIL — `sqlite3.OperationalError: no such table: source_failure` at the `DROP TABLE`.

- [ ] **Step 3: Add the table to `SCHEMA`**

In `humble_catalog/db.py`, the `SCHEMA` string currently ends:

```python
CREATE TABLE IF NOT EXISTS source_quota (
  source TEXT PRIMARY KEY, hit_at TEXT NOT NULL, resets_at TEXT NOT NULL);
"""
```

Insert the new table before the closing `"""`:

```python
CREATE TABLE IF NOT EXISTS source_quota (
  source TEXT PRIMARY KEY, hit_at TEXT NOT NULL, resets_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_failure (
  source TEXT NOT NULL, title TEXT NOT NULL,
  failures INTEGER NOT NULL,
  first_failed_at TEXT NOT NULL, last_failed_at TEXT NOT NULL,
  last_error TEXT NOT NULL,
  PRIMARY KEY (source, title));
"""
```

- [ ] **Step 4: Add migration 10**

In `humble_catalog/db.py`, immediately after the migration-9 block that ends `conn.execute("PRAGMA user_version = 9")` / `conn.commit()`, add:

```python
    if conn.execute("PRAGMA user_version").fetchone()[0] < 10:
        # Adds source_failure, which remembers which titles a source could
        # not fetch and in how many runs. As with migrations 7 and 9, the
        # executescript(SCHEMA) above has already created the table on this
        # connection; this only carries the version forward. Nothing is
        # read or rewritten - an older database starts with no rows, which
        # is exactly the state "no failure has been observed yet".
        conn.execute("PRAGMA user_version = 10")
        conn.commit()
```

- [ ] **Step 5: Update the eight assertions that hardcode the old version**

`tests/test_db.py` asserts `user_version == 9` at lines **107, 113, 181, 631, 639, 661, 671, 832**. Every one becomes `== 10`. Leave `conn.execute("PRAGMA user_version = 1")` and `= 0` lines alone — those deliberately simulate old files.

```bash
grep -n "user_version.*== 9" tests/test_db.py
```

Expected after the edit: no output.

- [ ] **Step 6: Run the db tests**

```bash
.venv/Scripts/python -m pytest tests/test_db.py -q
```

Expected: PASS, all of them.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/db.py tests/test_db.py
git commit -m "feat(db): add source_failure and migration 10"
```

---

### Task 2: A shared `redact()` for source error strings

**Files:**
- Modify: `humble_catalog/sources/base.py` (imports, plus a new function), `humble_catalog/check.py:12` and `:56-59`
- Test: `tests/test_sources_base.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `redact(text: str) -> str` in `humble_catalog.sources.base`. Replaces the value of any `key`, `apikey`, or `api_key` query parameter with `REDACTED`, case-insensitively.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sources_base.py`:

```python
def test_redact_hides_key_params():
    url = "https://api.example/v1?q=x&key=SECRETKEY&maxResults=5"
    out = base.redact(f"503 Server Error for url: {url}")
    assert "SECRETKEY" not in out
    assert "key=REDACTED" in out
    assert "q=x" in out            # ordinary params survive
    assert "maxResults=5" in out

def test_redact_covers_the_other_spellings_and_any_case():
    assert "S" not in base.redact("?api_key=S")
    assert "S" not in base.redact("?apikey=S")
    assert "S" not in base.redact("?API_KEY=S")

def test_redact_leaves_a_string_without_a_key_alone():
    assert base.redact("Connection aborted") == "Connection aborted"
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_sources_base.py -k redact -v
```

Expected: FAIL — `AttributeError: module 'humble_catalog.sources.base' has no attribute 'redact'`.

- [ ] **Step 3: Add `redact` to `sources/base.py`**

Add `re` to the imports at the top of `humble_catalog/sources/base.py` (it currently starts `import json`, `import time`):

```python
import json
import re
import time
```

Then add, directly below the `CacheMiss` class:

```python
_SECRET_PARAM = re.compile(r"((?:api_?)?key)=[^&\s]+", re.IGNORECASE)

def redact(text):
    """Hide credential query params in a source's error string.

    A `requests` HTTPError message embeds the whole request URL, and for
    a keyed source that URL carries the key. Anything derived from an
    exception - printed, logged, or stored - goes through here first.
    """
    return _SECRET_PARAM.sub(r"\1=REDACTED", text)
```

- [ ] **Step 4: Make `check.py` use it**

In `humble_catalog/check.py`, delete the now-unused `import re` (line 12) and add the import beside the existing `db` import:

```python
from humble_catalog import db
from humble_catalog.progress import LiveDisplay, grid
from humble_catalog.sources.base import redact
```

Replace the inline scrub in the `except` block:

```python
            except Exception as exc:
                # error strings can embed the request URL, key included
                detail = re.sub(r"((?:api_?)?key)=[^&\s]+", r"\1=REDACTED",
                                str(exc), flags=re.IGNORECASE)
                results[name] = ("FAIL", detail)
```

with:

```python
            except Exception as exc:
                # error strings can embed the request URL, key included
                results[name] = ("FAIL", redact(str(exc)))
```

- [ ] **Step 5: Run both test files**

```bash
.venv/Scripts/python -m pytest tests/test_sources_base.py tests/test_check.py -q
```

Expected: PASS. `test_check.py`'s existing `assert "SECRETKEY" not in ...` is the proof the move changed no behaviour — if it fails, the regex was transcribed wrongly.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/sources/base.py humble_catalog/check.py tests/test_sources_base.py
git commit -m "refactor(sources): share one redactor for source error strings"
```

---

### Task 3: The `failures` module

**Files:**
- Create: `humble_catalog/failures.py`
- Test: `tests/test_failures.py` (new)

**Interfaces:**
- Consumes: the `source_failure` table from Task 1.
- Produces:
  - `record(conn, source: str, title: str, error: str) -> None` — inserts with `failures = 1` or increments; commits.
  - `top(conn, min_failures: int = 1) -> list[sqlite3.Row]` — rows with `failures >= min_failures`, ordered `failures` desc, `last_failed_at` desc, then `source`, `title`.
  - `error_kind(error: str) -> str` — the error text with `" for url: ..."` and beyond removed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_failures.py`:

```python
from humble_catalog import db, failures

def test_a_first_failure_starts_the_count(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Learn C#", "503 backendFailed")
    row = conn.execute("SELECT * FROM source_failure").fetchone()
    assert row["source"] == "google_books"
    assert row["title"] == "Learn C#"
    assert row["failures"] == 1
    assert row["first_failed_at"] == row["last_failed_at"]
    assert row["last_error"] == "503 backendFailed"

def test_recording_the_same_title_again_increments_and_keeps_the_first_time(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Learn C#", "503 one")
    first = conn.execute("SELECT first_failed_at FROM source_failure").fetchone()[0]
    failures.record(conn, "google_books", "Learn C#", "503 two")
    row = conn.execute("SELECT * FROM source_failure").fetchone()
    assert row["failures"] == 2
    assert row["first_failed_at"] == first     # the first time never moves
    assert row["last_failed_at"] >= first      # the last time does
    assert row["last_error"] == "503 two"      # newest error wins

def test_the_same_title_under_two_sources_is_two_rows(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Moonfall Vol. 1-3", "a")
    failures.record(conn, "comicvine", "Moonfall Vol. 1-3", "b")
    assert conn.execute("SELECT COUNT(*) FROM source_failure").fetchone()[0] == 2

def test_top_orders_most_persistent_first(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Gray Waters", "a")
    for _ in range(3):
        failures.record(conn, "google_books", "Shadow Hound Vol. 1-6", "b")
    rows = failures.top(conn)
    assert [r["title"] for r in rows] == ["Shadow Hound Vol. 1-6", "Gray Waters"]

def test_top_can_exclude_one_off_failures(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Gray Waters", "a")
    failures.record(conn, "google_books", "Learn C#", "b")
    failures.record(conn, "google_books", "Learn C#", "b")
    rows = failures.top(conn, min_failures=2)
    assert [r["title"] for r in rows] == ["Learn C#"]

def test_error_kind_drops_the_url_so_titles_group_together(tmp_path):
    # The URL carries the title, so without this every stored error is
    # unique and a tally reports one of everything - no information.
    a = failures.error_kind(
        "503 Server Error: Service Unavailable for url: https://x/?q=Learn+C%23")
    b = failures.error_kind(
        "503 Server Error: Service Unavailable for url: https://x/?q=Gray+Waters")
    assert a == b == "503 Server Error: Service Unavailable"

def test_error_kind_passes_through_an_error_with_no_url():
    assert failures.error_kind("Connection aborted") == "Connection aborted"
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_failures.py -q
```

Expected: FAIL — `ImportError: cannot import name 'failures' from 'humble_catalog'`.

- [ ] **Step 3: Write the module**

Create `humble_catalog/failures.py`:

```python
"""Which titles a source could not fetch, and in how many runs.

`source_cache` records answers and `source_quota` records rate limits.
This is the third fact a harvest produces and the only one that used to
die with the process: a failure was printed and then forgotten, so
"did the same titles fail again?" had no way to be answered.

`failures` counts *runs*, not attempts. The pool visits each title once
per run, and google_books does not retry server errors, so one increment
per failure is one increment per run. A row at failures = 5 failed on
five separate days.

Imports nothing from the package, as `quota` does, so any layer may use
it without a cycle.
"""
from datetime import datetime, timezone

def _utcnow():
    return datetime.now(timezone.utc).isoformat()

def record(conn, source, title, error):
    """Count one more run in which `source` could not fetch `title`. Commits.

    `error` must already be scrubbed - see `sources.base.redact`. Doing it
    at the call site rather than here is what keeps this module free of
    package imports, and it means the printed and the stored text are the
    same string rather than two that could drift.
    """
    now = _utcnow()
    conn.execute(
        "INSERT INTO source_failure (source, title, failures, "
        "first_failed_at, last_failed_at, last_error) VALUES (?,?,1,?,?,?) "
        "ON CONFLICT(source, title) DO UPDATE SET "
        "failures = failures + 1, "
        "last_failed_at = excluded.last_failed_at, "
        "last_error = excluded.last_error",
        (source, title, now, now, error))
    conn.commit()

def top(conn, min_failures=1):
    """Failure rows, most persistent first.

    `min_failures=2` is the interesting view: one failure is noise, two
    in separate runs is the beginning of evidence.
    """
    return conn.execute(
        "SELECT source, title, failures, first_failed_at, last_failed_at, "
        "last_error FROM source_failure WHERE failures >= ? "
        "ORDER BY failures DESC, last_failed_at DESC, source, title",
        (min_failures,)).fetchall()

def error_kind(error):
    """The part of an error string that is the same for every title.

    A `requests` HTTP error ends in " for url: <the request URL>", and
    that URL contains the title being searched for. Grouping on the whole
    string would therefore tally one of everything; cutting at the marker
    leaves "503 Server Error: Service Unavailable", which is the thing
    worth counting.
    """
    return error.split(" for url:")[0].strip()
```

- [ ] **Step 4: Run them and watch them pass**

```bash
.venv/Scripts/python -m pytest tests/test_failures.py -q
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/failures.py tests/test_failures.py
git commit -m "feat(failures): record which titles a source could not fetch"
```

---

### Task 4: Harvest records its failures

**Files:**
- Modify: `humble_catalog/harvest.py:1-7` (imports), `humble_catalog/harvest.py:71-77` (the failure branch)
- Test: `tests/test_harvest.py`

**Interfaces:**
- Consumes: `failures.record` (Task 3), `sources.base.redact` (Task 2).
- Produces: after `harvest.run`, one `source_failure` row per (source, title) that raised a non-429 error.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_harvest.py`. `_seed`, `_fake` and `_429` already exist in that file:

```python
def _rows(conn):
    return conn.execute(
        "SELECT * FROM source_failure ORDER BY source, title").fetchall()

def test_a_failed_title_is_recorded(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError("503 backendFailed")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": boom}, _conn=conn)
    rows = _rows(conn)
    assert len(rows) == 1
    assert rows[0]["source"] == "hardcover"
    assert rows[0]["title"] == "Gray Waters"
    assert rows[0]["failures"] == 1
    assert "503 backendFailed" in rows[0]["last_error"]

def test_the_same_title_failing_again_counts_the_second_run(tmp_path):
    # The property the whole feature exists to produce: because the pool
    # visits a title once per run, the counter counts runs. If anyone
    # reintroduces per-run retries this turns into "attempts" and lies.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError("503 backendFailed")
    for _ in range(2):
        harvest.run(db_path=tmp_path / "t.db",
                    sources={"hardcover": boom}, _conn=conn)
    assert _rows(conn)[0]["failures"] == 2

def test_a_rate_limit_is_not_recorded_as_a_title_failure(tmp_path):
    # A 429 is a fact about the quota, not about the title, and
    # source_quota already holds it. Both errors arrive at the same
    # `except`, so this pins the branch that keeps them apart.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = _429()
    boom.quota_resets_at.return_value = RESET
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": boom}, _conn=conn)
    assert _rows(conn) == []
    assert conn.execute(
        "SELECT COUNT(*) FROM source_quota").fetchone()[0] == 1

def test_a_cache_miss_records_nothing(tmp_path):
    # An offline source declining to fetch is not a failure.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    miss = Mock(); miss.lookup.side_effect = CacheMiss("x")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": miss}, _conn=conn)
    assert _rows(conn) == []

def test_a_recorded_error_never_contains_the_api_key(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError(
        "503 Server Error for url: https://api.example/v1?q=x&key=SECRETKEY")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": boom}, _conn=conn)
    assert "SECRETKEY" not in _rows(conn)[0]["last_error"]
    assert "SECRETKEY" not in capsys.readouterr().out
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -k "recorded or counts_the_second or rate_limit_is_not or cache_miss_records" -q
```

Expected: FAIL — `test_a_failed_title_is_recorded` with `assert len([]) == 1`, and `test_a_recorded_error_never_contains_the_api_key` with `SECRETKEY` present in stdout (the leak this task also fixes).

- [ ] **Step 3: Update the imports in `harvest.py`**

`humble_catalog/harvest.py` currently starts:

```python
import threading
from datetime import datetime, timezone
from humble_catalog import db, quota
from humble_catalog.enrich import SOURCE_ORDER, SOURCE_CLASSES
from humble_catalog.progress import HarvestProgress, duration
from humble_catalog.sources.base import CacheMiss
from humble_catalog.titles import clean_title
```

Change the two lines that need it:

```python
from humble_catalog import db, failures, quota
...
from humble_catalog.sources.base import CacheMiss, redact
```

- [ ] **Step 4: Record in the failure branch**

In `_run_pool`, replace:

```python
        except Exception as exc:  # noqa: BLE001
            failed = True
            with lock:
                incomplete.add(name)
            if not _is_429(exc):
                prog.log(f"  {name} failed for '{title}': {exc}")
                continue  # skip this title, keep draining the queue
```

with:

```python
        except Exception as exc:  # noqa: BLE001
            failed = True
            # Scrubbed once and used for both the log line and the stored
            # row: a requests HTTPError embeds the request URL, and for a
            # keyed source that URL carries the key.
            detail = redact(str(exc))
            with lock:
                incomplete.add(name)
            if not _is_429(exc):
                prog.log(f"  {name} failed for '{title}': {detail}")
                # A 429 is deliberately not recorded here: it says nothing
                # about the title, and source_quota already holds it.
                with lock:
                    failures.record(conn, name, title, detail)
                continue  # skip this title, keep draining the queue
```

- [ ] **Step 5: Run the harvest tests**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -q
```

Expected: PASS, including the pre-existing tests — nothing about ordering, resume, or quota changes.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/harvest.py tests/test_harvest.py
git commit -m "feat(harvest): record failed titles, and stop printing the API key"
```

---

### Task 5: The end-of-run summary block

**Files:**
- Modify: `humble_catalog/harvest.py` (imports and `run`), `humble_catalog/progress.py:332-366` (`finish`)
- Test: `tests/test_harvest.py`

**Interfaces:**
- Consumes: `failures.top` (Task 3), `stats.console_safe`.
- Produces: `HarvestProgress.finish(incomplete, paused=None, repeats=())` — `repeats` is a list of **preformatted strings**, written verbatim under a heading. Progress formats nothing and queries nothing.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_harvest.py`:

```python
def test_the_summary_lists_repeat_offenders(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError("503 backendFailed")
    for _ in range(2):
        harvest.run(db_path=tmp_path / "t.db",
                    sources={"hardcover": boom}, _conn=conn)
    out = capsys.readouterr().out
    assert "Repeat failures" in out
    assert "2x" in out
    assert "Gray Waters" in out

def test_a_single_failure_is_not_called_a_repeat(tmp_path, capsys):
    # One failure is noise; the block would cry wolf on every flaky run.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError("503 backendFailed")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": boom}, _conn=conn)
    assert "Repeat failures" not in capsys.readouterr().out

def test_a_clean_run_says_nothing_about_failures(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": _fake()}, _conn=conn)
    assert "Repeat failures" not in capsys.readouterr().out
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -k "repeat or clean_run_says" -q
```

Expected: FAIL — `assert 'Repeat failures' in out` on the first test.

- [ ] **Step 3: Build the lines in `harvest.run`**

Add `import sys` to the top of `humble_catalog/harvest.py`, and `stats` to the package import:

```python
import sys
import threading
from datetime import datetime, timezone
from humble_catalog import db, failures, quota, stats
```

Add this helper directly above `def run(`:

```python
SUMMARY_ROWS = 5

def _repeat_lines(conn):
    """The repeat-failure block's lines, or [] when there is nothing to say.

    Formatted here rather than in HarvestProgress so that progress stays a
    display: it writes what it is handed and owns no query. `paused`
    already established that split.
    """
    rows = failures.top(conn, min_failures=2)
    if not rows:
        return []
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    lines = [f"  {r['failures']}x  {r['source']}  "
             f"{stats.console_safe(r['title'], encoding)}"
             for r in rows[:SUMMARY_ROWS]]
    if len(rows) > SUMMARY_ROWS:
        lines.append(f"  ...and {len(rows) - SUMMARY_ROWS} more - "
                     f"see 'harvest --failures'")
    return lines
```

Then in `run`, change the `prog.finish` call. It currently reads:

```python
    paused = {name: _when(resets_at) for name in worklist
              if (resets_at := quota.blocked(conn, name))}
    prog.finish(incomplete, paused=paused)
```

to:

```python
    paused = {name: _when(resets_at) for name in worklist
              if (resets_at := quota.blocked(conn, name))}
    prog.finish(incomplete, paused=paused, repeats=_repeat_lines(conn))
```

- [ ] **Step 4: Write the block in `progress.finish`**

In `humble_catalog/progress.py`, change the signature and docstring:

```python
    def finish(self, incomplete, paused=None, repeats=()):
        """Retire the run. `paused` maps a source name to when its rate
        limit lifts, already formatted for display. `repeats` is a list of
        already-formatted lines naming titles that have failed in more
        than one run - the caller queries and formats them, this only
        writes them.

        A paused source is reported apart from the merely incomplete ones,
        because "rerun 'harvest' to resume" is wrong advice for a source
        that will hit the same 429 immediately.
        """
```

Then, inside the `with self._lock:` block, after the `if not stalled and not paused:` branch and **before** the `self.conn.execute("UPDATE run_status ...")` call, add:

```python
            if repeats:
                self._display.write("\nRepeat failures (2+ runs):")
                for line in repeats:
                    self._display.write(line)
```

- [ ] **Step 5: Run the tests**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py tests/test_progress.py -q
```

Expected: PASS. `test_progress.py` calls `finish` without `repeats`, which the default `()` keeps working.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/harvest.py humble_catalog/progress.py tests/test_harvest.py
git commit -m "feat(harvest): name repeat failures in the run summary"
```

---

### Task 6: `harvest --failures`

**Files:**
- Modify: `humble_catalog/harvest.py` (new `report_failures`), `humble_catalog/__main__.py:84-87` and `:165-167`, `README.md`
- Test: `tests/test_harvest.py`

**Interfaces:**
- Consumes: `failures.top`, `failures.error_kind` (Task 3).
- Produces: `harvest.report_failures(db_path="catalog.db", _conn=None) -> None`. Prints and returns; makes no request and constructs no source.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_harvest.py`:

```python
def test_report_failures_prints_the_rows_without_harvesting(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")     # an item that would be harvested
    failures.record(conn, "google_books", "Shadow Hound Vol. 1-6",
                    "503 Server Error for url: https://x/?q=a")
    failures.record(conn, "google_books", "Shadow Hound Vol. 1-6",
                    "503 Server Error for url: https://x/?q=a")
    failures.record(conn, "comicvine", "Moonfall Vol. 1-3",
                    "503 Server Error for url: https://x/?q=b")
    harvest.report_failures(_conn=conn)
    out = capsys.readouterr().out
    assert "Shadow Hound Vol. 1-6" in out
    assert "Moonfall Vol. 1-3" in out
    assert "2  " in out                       # the run count
    # Two rows, two different URLs, one kind. The tally counts *titles*
    # hit by an error, not failure events - which is the number that says
    # how widespread a given error is.
    assert "2x  503 Server Error" in out

def test_report_failures_on_an_empty_table_says_so(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    harvest.report_failures(_conn=conn)
    assert "No source failures recorded" in capsys.readouterr().out
```

Add `failures` to that file's imports:

```python
from humble_catalog import db, failures, harvest
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -k report_failures -q
```

Expected: FAIL — `AttributeError: module 'humble_catalog.harvest' has no attribute 'report_failures'`.

- [ ] **Step 3: Write `report_failures`**

Add `Counter` to the imports at the top of `humble_catalog/harvest.py`:

```python
import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from humble_catalog import db, failures, quota, stats
```

Then add to the end of the file:

```python
def report_failures(db_path="catalog.db", _conn=None):
    """Print every recorded failure, most persistent first. Reads only.

    No source is constructed and no request is made - this exists so the
    table can be read between runs, when the interesting question is
    whether the same titles keep coming back.

    The error tally groups on `error_kind` rather than the stored text,
    because the stored text ends in the request URL and the URL contains
    the title: one row per title tallies one of everything. The count is
    a count of titles, not of failure events - "how widespread is this
    error", which is the question the hypothesis needs answered.
    """
    conn = _conn or db.connect(db_path)
    try:
        rows = failures.top(conn)
        if not rows:
            print("No source failures recorded.")
            return
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        width = max(len(r["source"]) for r in rows)
        print(f"{'runs':>4}  {'last failed':<11}  {'source':<{width}}  title")
        for r in rows:
            print(f"{r['failures']:>4}  {r['last_failed_at'][:10]:<11}  "
                  f"{r['source']:<{width}}  "
                  f"{stats.console_safe(r['title'], encoding)}")
        print("\nErrors seen:")
        for kind, n in Counter(
                failures.error_kind(r["last_error"]) for r in rows).most_common():
            print(f"  {n}x  {stats.console_safe(kind, encoding)}")
    finally:
        if _conn is None:
            conn.close()
```

- [ ] **Step 4: Add the flag**

In `humble_catalog/__main__.py`, after the existing `--ignore-quota` argument:

```python
    p_harvest.add_argument("--failures", action="store_true",
                           help="List titles that failed in past runs, most "
                                "persistent first, and exit without "
                                "harvesting")
```

And change the dispatch:

```python
    elif args.command == "harvest":
        from humble_catalog import harvest
        harvest.run(ignore_quota=args.ignore_quota)
```

to:

```python
    elif args.command == "harvest":
        from humble_catalog import harvest
        if args.failures:
            harvest.report_failures()
        else:
            harvest.run(ignore_quota=args.ignore_quota)
```

- [ ] **Step 5: Run the tests, then the flag by hand**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -q
```

Expected: PASS.

```bash
.venv/Scripts/python -m humble_catalog harvest --failures
```

Expected: either the table, or `No source failures recorded.` on a database that has not harvested since Task 4. No network activity either way.

- [ ] **Step 6: Document the flag**

In `README.md`, find where `harvest --ignore-quota` is documented and add a sibling entry for `--failures`, worded:

> `harvest --failures` lists the titles that failed in past runs, most
> persistent first, with a tally of the errors behind them. It reads the
> database and exits — no requests, no quota spent. A title with a high
> run count is failing reproducibly rather than unluckily.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/harvest.py humble_catalog/__main__.py README.md tests/test_harvest.py
git commit -m "feat(harvest): add --failures to read the failure table"
```

---

### Task 7: Backlog entries and the full gate

**Files:**
- Modify: `docs/BACKLOG.md` (Privacy section, and the Harvest section at `:152-171`)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code-facing.

- [ ] **Step 1: Add the privacy warning**

In the Privacy section of `docs/BACKLOG.md`, alongside the existing warning that images are invisible to `leak_check.py`, add:

```markdown
- **`harvest --failures` prints real owned titles.** It is a terminal
  report, so nothing tracks or scans it, and no automated check would
  notice if its output reached a commit message, a doc, an issue or a
  screenshot. Same blind spot as images: judge it by eye before pasting
  it anywhere.
```

- [ ] **Step 2: Record what shipped and why**

In the Harvest section of `docs/BACKLOG.md`, add:

```markdown
- **Failure recording shipped as measurement only (2026-07-31)** —
  `source_failure` counts the runs in which each title failed. It exists
  to answer one question before any policy is written: are google_books'
  503s transient, or do the same titles fail every run? A run on
  2026-07-31 failed mostly on TTRPG supplements, comics and programming
  books, which share a query shape rather than a subject — long titles
  with internal colons, `#`, `+` and volume ranges, none of which
  `clean_title` strips. If a few runs show the same titles at a rising
  count, the fix is query normalization for this one source, not retry
  scheduling. If the counts stay at 1 and the titles keep changing, the
  503s are load and nothing needs doing. See
  `specs/2026-07-31-harvest-failure-recording-design.md`.
```

- [ ] **Step 3: Run the whole gate**

```bash
powershell -File scripts/windows/verify.ps1
```

Expected: the full test suite passes, `check_no_data_tracked.py` prints `clean`, `leak_check.py` prints `clean`, and the run ends `Verified: tests pass, no private data in the repo.`

If `leak_check.py` flags a phrase, it is almost certainly a prose substring collision — reword the sentence rather than touching `ALLOWED`.

- [ ] **Step 4: Commit**

```bash
git add docs/BACKLOG.md
git commit -m "docs(backlog): record failure recording, and that --failures output is private"
```

---

## Notes for the implementer

- **Do not add a skip, cap, or reordering rule.** This plan is measurement only, on purpose. The table is what decides which policy is worth building, and building one now would destroy the evidence it was meant to gather.
- **`failures` counts runs only because retries are off** for `google_books` (`retry_server_errors = False`). If you find yourself changing that flag, `test_the_same_title_failing_again_counts_the_second_run` is the test that will tell you the counter has changed meaning.
- **The 429 branch stays untouched.** It records to `source_quota` and continues; it must not also write a `source_failure` row.
