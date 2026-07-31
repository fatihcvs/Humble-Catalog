# Harvest Run Tally Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record what each harvest run cost per source — titles answered, live fetches, failures, and whether the budget died in that run — so the failure rate becomes a measurement rather than an inference.

**Architecture:** A new `harvest_run` table written once per run by a new `runs` module. Both counts already exist in the database when a run ends (successes are `source_cache` rows in the run's window, failures are `source_failure` rows in it), so `_run_pool`, `Source` and `progress` are untouched. Bounded by construction: `record` trims to the newest 500 runs.

**Tech Stack:** Python 3.12, SQLite (WAL), pytest. No new dependencies.

Spec: `docs/superpowers/specs/2026-07-31-harvest-run-tally-design.md`.

## Global Constraints

- **Privacy.** Committed text must use invented names from `docs/TEST-DATA.md` — never a real item. This plan's tests use *Gray Waters* and *Learn C#*, both already listed. Note that `harvest_run` itself stores no titles.
- `scripts/leak_check.py` matches **substrings**, so ordinary prose can trip it. Run it directly, never piped. If it flags a phrase in prose, reword the prose — do not add to `ALLOWED`.
- Run `.venv/Scripts/python -m pip`, never `.venv/Scripts/pip` (the shim exits 1 silently).
- Every commit message ends with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Never commit `catalog.db*`, `covers/`, `cache/`, or `Reference spreadsheets/`.
- Tests run with `.venv/Scripts/python -m pytest`.
- Terminal output containing catalog titles must pass through `stats.console_safe`. **Nothing in this plan prints a title**, so it does not arise here — `harvest_run` holds source names and counts only.

---

## File Structure

| File | Responsibility |
|---|---|
| `humble_catalog/runs.py` | **New.** The `harvest_run` table's reader/writer, including the retention trim. Imports nothing from the package. |
| `humble_catalog/db.py` | `SCHEMA` gains `harvest_run`; migration 11; `cached_since()` helper. |
| `humble_catalog/failures.py` | Gains `count_since()`. |
| `humble_catalog/quota.py` | Gains `hit_at()`. |
| `humble_catalog/harvest.py` | Captures the run's start, tallies after the joins, records; adds `report_runs()` and `forget_runs()`. |
| `humble_catalog/__main__.py` | `--runs` and `--forget-runs` flags and dispatch. |
| `tests/test_runs.py` | **New.** Unit tests for the module and the trim. |
| `tests/test_db.py`, `tests/test_failures.py`, `tests/test_quota.py`, `tests/test_harvest.py` | Migration, the three count helpers, the wiring and the read paths. |

---

### Task 1: The `harvest_run` table and migration 11

**Files:**
- Modify: `humble_catalog/db.py` (end of `SCHEMA`, and after the migration-10 block)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing.
- Produces: table `harvest_run(started_at TEXT, source TEXT, ended_at TEXT, answered INTEGER, succeeded INTEGER, failed INTEGER, quota_died INTEGER, PRIMARY KEY (started_at, source))`; `PRAGMA user_version` reaches `11`.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_db.py`:

```python
def test_migration_11_adds_harvest_run(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    conn.execute("PRAGMA user_version = 10")  # pretend this is a pre-11 file
    conn.execute("DROP TABLE harvest_run")
    conn.commit()
    conn.close()

    conn = db.connect(path)                   # reconnect triggers the migration
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harvest_run)")}
    assert cols == {"started_at", "source", "ended_at", "answered",
                    "succeeded", "failed", "quota_died"}
```

- [ ] **Step 2: Run it and watch it fail**

```bash
.venv/Scripts/python -m pytest tests/test_db.py::test_migration_11_adds_harvest_run -v
```

Expected: FAIL — `sqlite3.OperationalError: no such table: harvest_run` at the `DROP TABLE`.

- [ ] **Step 3: Add the table to `SCHEMA`**

In `humble_catalog/db.py`, `SCHEMA` currently ends with the `source_failure` table then `"""`. Insert the new table before the closing `"""`:

```python
CREATE TABLE IF NOT EXISTS source_failure (
  source TEXT NOT NULL, title TEXT NOT NULL,
  failures INTEGER NOT NULL,
  first_failed_at TEXT NOT NULL, last_failed_at TEXT NOT NULL,
  last_error TEXT NOT NULL,
  PRIMARY KEY (source, title));
CREATE TABLE IF NOT EXISTS harvest_run (
  started_at TEXT NOT NULL, source TEXT NOT NULL, ended_at TEXT NOT NULL,
  answered INTEGER NOT NULL, succeeded INTEGER NOT NULL,
  failed INTEGER NOT NULL, quota_died INTEGER NOT NULL,
  PRIMARY KEY (started_at, source));
"""
```

- [ ] **Step 4: Add migration 11**

Immediately after the migration-10 block that ends `conn.execute("PRAGMA user_version = 10")` / `conn.commit()`, add:

```python
    if conn.execute("PRAGMA user_version").fetchone()[0] < 11:
        # Adds harvest_run, one row per source per run: what it answered,
        # what it fetched live, what failed, and whether the budget died
        # in that run. As with migrations 7, 9 and 10, the
        # executescript(SCHEMA) above has already created the table on
        # this connection; this only carries the version forward. An
        # older database simply starts with no run history.
        conn.execute("PRAGMA user_version = 11")
        conn.commit()
```

- [ ] **Step 5: Bump the nine assertions that pin the old version**

`tests/test_db.py` asserts `user_version == 10` at lines **107, 113, 181, 631, 639, 661, 671, 832, 844**. Every one becomes `== 11`. Leave `conn.execute("PRAGMA user_version = 10")`, `= 9`, `= 8`, `= 1` and `= 0` lines alone — those deliberately simulate older files.

```bash
grep -c "user_version.*== 10" tests/test_db.py
```

Expected after the edit: `0`.

- [ ] **Step 6: Pin that a reset does not wipe the run history**

`reset` deletes `DERIVED_TABLES` only, and `harvest_run` is deliberately
absent from that tuple — it is an observation about a source, not
derived catalog, exactly like `source_cache` and `source_failure`.
Nothing enforces that today, so adding the table to `DERIVED_TABLES`
later would silently destroy the history. Add to `tests/test_reset.py`:

```python
def test_reset_keeps_the_observation_tables(tmp_path):
    # source_cache, source_failure and harvest_run record what the
    # outside world said, not what the catalog derived. A rebuild must
    # not spend the quota again to rediscover them.
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                 "VALUES ('google_books','q','2026-07-30T00:00:00+00:00','{}')")
    conn.execute("INSERT INTO source_failure (source, title, failures, "
                 "first_failed_at, last_failed_at, last_error) "
                 "VALUES ('google_books','Gray Waters',1,'a','a','e')")
    conn.execute("INSERT INTO harvest_run (started_at, source, ended_at, "
                 "answered, succeeded, failed, quota_died) "
                 "VALUES ('2026-07-30T21:00:00+00:00','google_books',"
                 "'2026-07-30T22:00:00+00:00',1,1,0,0)")
    conn.commit()
    reset.run(_conn=conn, _input=lambda _: "RESET")
    for table in ("source_cache", "source_failure", "harvest_run"):
        assert conn.execute(
            f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1, table
```

If `tests/test_reset.py` does not already import `reset`, add
`from humble_catalog import db, reset` at the top.

- [ ] **Step 7: Run the db and reset tests**

```bash
.venv/Scripts/python -m pytest tests/test_db.py tests/test_reset.py -q
```

Expected: PASS, all of them.

- [ ] **Step 8: Commit**

```bash
git add humble_catalog/db.py tests/test_db.py tests/test_reset.py
git commit -m "feat(db): add harvest_run and migration 11"
```

---

### Task 2: The three window counts, each from its table's owner

**Files:**
- Modify: `humble_catalog/db.py` (new `cached_since`), `humble_catalog/failures.py` (new `count_since`), `humble_catalog/quota.py` (new `hit_at`)
- Test: `tests/test_db.py`, `tests/test_failures.py`, `tests/test_quota.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `db.cached_since(conn, source: str, since: str) -> int`
  - `failures.count_since(conn, source: str, since: str) -> int`
  - `quota.hit_at(conn, source: str) -> datetime | None`

  `since` is an ISO-8601 string as written by `datetime.now(timezone.utc).isoformat()`. `hit_at` returns a timezone-aware `datetime`, or `None` when no record exists.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_db.py`:

```python
def test_cached_since_counts_only_rows_at_or_after_the_mark(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for when in ("2026-07-01T00:00:00+00:00", "2026-07-05T00:00:00+00:00"):
        conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                     "VALUES (?,?,?,?)", ("google_books", when, when, "{}"))
    conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                 "VALUES (?,?,?,?)",
                 ("hardcover", "x", "2026-07-05T00:00:00+00:00", "{}"))
    conn.commit()
    assert db.cached_since(conn, "google_books", "2026-07-03T00:00:00+00:00") == 1
    assert db.cached_since(conn, "google_books", "2026-07-01T00:00:00+00:00") == 2
    assert db.cached_since(conn, "google_books", "2026-08-01T00:00:00+00:00") == 0
```

Add to `tests/test_failures.py`:

```python
def test_count_since_counts_titles_that_failed_in_the_window(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    failures.record(conn, "google_books", "Gray Waters", "a")
    mark = conn.execute(
        "SELECT last_failed_at FROM source_failure").fetchone()[0]
    failures.record(conn, "google_books", "Learn C#", "b")
    assert failures.count_since(conn, "google_books", mark) == 2
    assert failures.count_since(conn, "google_books", "2099-01-01T00:00:00+00:00") == 0
    assert failures.count_since(conn, "comicvine", mark) == 0
```

Add to `tests/test_quota.py`:

```python
def test_hit_at_reports_when_the_limit_was_recorded(tmp_path):
    from datetime import datetime, timedelta, timezone
    conn = db.connect(tmp_path / "t.db")
    assert quota.hit_at(conn, "google_books") is None
    before = datetime.now(timezone.utc)
    quota.record(conn, "google_books",
                 datetime.now(timezone.utc) + timedelta(hours=1))
    hit = quota.hit_at(conn, "google_books")
    assert hit is not None and hit >= before
```

`tests/test_quota.py` already imports `db` and `quota`; if it does not, add
`from humble_catalog import db, quota` at the top.

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_db.py -k cached_since tests/test_failures.py -k count_since tests/test_quota.py -k hit_at -q
```

Expected: FAIL — `AttributeError` for each of `cached_since`, `count_since`, `hit_at`.

- [ ] **Step 3: Add `db.cached_since`**

In `humble_catalog/db.py`, add directly above `def connect(`:

```python
def cached_since(conn, source, since):
    """How many rows `source` cached at or after `since` (an ISO string).

    A live fetch is a cache write, so for a run that began at `since`
    this is that source's successful request count. Lives here because
    this module owns source_cache's schema, and one home for the query
    means one place to change if the cache ever changes shape.
    """
    return conn.execute(
        "SELECT COUNT(*) FROM source_cache WHERE source=? AND fetched_at >= ?",
        (source, since)).fetchone()[0]
```

- [ ] **Step 4: Add `failures.count_since`**

Add to the end of `humble_catalog/failures.py`:

```python
def count_since(conn, source, since):
    """How many of `source`'s titles failed at or after `since`.

    Exact for the run that just ended: a title fails at most once per run
    and that run stamps last_failed_at on every title that failed in it.
    Not exact for an older window, because last_failed_at moves - which
    is precisely why a run's count is written down rather than
    recomputed later.
    """
    return conn.execute(
        "SELECT COUNT(*) FROM source_failure "
        "WHERE source=? AND last_failed_at >= ?",
        (source, since)).fetchone()[0]
```

- [ ] **Step 5: Add `quota.hit_at`**

Add to the end of `humble_catalog/quota.py`:

```python
def hit_at(conn, source):
    """When `source`'s limit was last recorded as spent, or None.

    `blocked` answers "is it spent now"; this answers "when did that
    happen". The difference separates a run that exhausted the budget
    from one that started with it already gone - the same condition as
    far as advice goes, opposite meanings for a measured rate.
    """
    row = conn.execute("SELECT hit_at FROM source_quota WHERE source=?",
                       (source,)).fetchone()
    return datetime.fromisoformat(row["hit_at"]) if row else None
```

`quota.py` already imports `datetime` at the top, so no import change is needed.

- [ ] **Step 6: Run the tests**

```bash
.venv/Scripts/python -m pytest tests/test_db.py tests/test_failures.py tests/test_quota.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/db.py humble_catalog/failures.py humble_catalog/quota.py tests/test_db.py tests/test_failures.py tests/test_quota.py
git commit -m "feat: count a run's cache writes, failures and quota event"
```

---

### Task 3: The `runs` module and its retention trim

**Files:**
- Create: `humble_catalog/runs.py`
- Test: `tests/test_runs.py` (new)

**Interfaces:**
- Consumes: the `harvest_run` table from Task 1.
- Produces:
  - `runs.KEEP_RUNS = 500`
  - `runs.record(conn, started_at: str, ended_at: str, tallies: dict, keep: int = KEEP_RUNS) -> None` — `tallies` maps source name to `(answered, succeeded, failed, quota_died)`. Commits.
  - `runs.history(conn) -> list[sqlite3.Row]` — newest run first, then source.
  - `runs.forget(conn) -> int` — deletes every row, returns how many *runs* were dropped. Commits.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_runs.py`:

```python
from humble_catalog import db, runs

def _tally(**kw):
    return {name: vals for name, vals in kw.items()}

def test_record_writes_one_row_per_source(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    runs.record(conn, "2026-07-30T21:00:00+00:00", "2026-07-30T22:00:00+00:00",
                _tally(google_books=(1718, 573, 427, True),
                       hardcover=(1320, 7, 0, False)))
    rows = conn.execute(
        "SELECT * FROM harvest_run ORDER BY source").fetchall()
    assert [r["source"] for r in rows] == ["google_books", "hardcover"]
    assert rows[0]["answered"] == 1718
    assert rows[0]["succeeded"] == 573
    assert rows[0]["failed"] == 427
    assert rows[0]["quota_died"] == 1
    assert rows[1]["quota_died"] == 0
    assert rows[0]["ended_at"] == "2026-07-30T22:00:00+00:00"

def test_record_trims_to_the_newest_runs(tmp_path):
    # Without this the 500-run cap is a comment rather than a guarantee.
    conn = db.connect(tmp_path / "t.db")
    for day in ("01", "02", "03", "04"):
        runs.record(conn, f"2026-07-{day}T21:00:00+00:00",
                    f"2026-07-{day}T22:00:00+00:00",
                    _tally(google_books=(1, 1, 0, False),
                           hardcover=(1, 1, 0, False)),
                    keep=2)
    kept = sorted({r["started_at"][:10] for r in runs.history(conn)})
    assert kept == ["2026-07-03", "2026-07-04"]
    # both sources of a kept run survive - the cap counts runs, not rows
    assert len(runs.history(conn)) == 4

def test_history_is_newest_first(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for day in ("01", "02"):
        runs.record(conn, f"2026-07-{day}T21:00:00+00:00",
                    f"2026-07-{day}T22:00:00+00:00",
                    _tally(google_books=(1, 1, 0, False)))
    assert [r["started_at"][:10] for r in runs.history(conn)] == \
        ["2026-07-02", "2026-07-01"]

def test_forget_empties_the_table_and_counts_runs(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for day in ("01", "02"):
        runs.record(conn, f"2026-07-{day}T21:00:00+00:00",
                    f"2026-07-{day}T22:00:00+00:00",
                    _tally(google_books=(1, 1, 0, False),
                           hardcover=(1, 1, 0, False)))
    assert runs.forget(conn) == 2      # runs dropped, not the 4 rows
    assert runs.history(conn) == []

def test_forget_on_an_empty_table_drops_nothing(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert runs.forget(conn) == 0
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_runs.py -q
```

Expected: FAIL — `ImportError: cannot import name 'runs' from 'humble_catalog'`.

- [ ] **Step 3: Write the module**

Create `humble_catalog/runs.py`:

```python
"""What each harvest run cost, one row per source.

`source_failure` says which titles keep failing; this says how many
requests a run spent and how many succeeded, so the failure rate is a
measurement rather than an inference drawn from throttle arithmetic.

It exists because two facts decay. `source_failure.last_failed_at` is
overwritten, so failures-per-run can be counted right after a run and
never again. And `quota.blocked` cannot tell a run that exhausted the
budget from one that started with it already spent - the same condition
for the advice a run prints, opposite meanings for a measured rate.

Bounded by construction: `record` trims to the newest KEEP_RUNS runs, so
the table cannot grow without limit even if nobody ever prunes it.

Imports nothing from the package, as `quota` and `failures` do.
"""

KEEP_RUNS = 500

def record(conn, started_at, ended_at, tallies, keep=KEEP_RUNS):
    """Write one row per source for a finished run, then trim. Commits.

    `tallies` maps a source name to
    (answered, succeeded, failed, quota_died).

    `keep` is a parameter rather than a constant read in here purely so a
    test can prove the trim with three runs instead of five hundred.
    """
    conn.executemany(
        "INSERT OR REPLACE INTO harvest_run (started_at, source, ended_at, "
        "answered, succeeded, failed, quota_died) VALUES (?,?,?,?,?,?,?)",
        [(started_at, source, ended_at, answered, succeeded, failed, int(died))
         for source, (answered, succeeded, failed, died) in tallies.items()])
    # A run is a distinct started_at spread over up to six rows, so the
    # cap is counted in runs; trimming rows would behead a run mid-way.
    conn.execute(
        "DELETE FROM harvest_run WHERE started_at NOT IN ("
        "SELECT started_at FROM harvest_run "
        "GROUP BY started_at ORDER BY started_at DESC LIMIT ?)", (keep,))
    conn.commit()

def history(conn):
    """Every recorded row, newest run first then source by name.

    Named `history` rather than `all`, which would shadow the builtin.
    """
    return conn.execute(
        "SELECT started_at, source, ended_at, answered, succeeded, failed, "
        "quota_died FROM harvest_run ORDER BY started_at DESC, source").fetchall()

def forget(conn):
    """Delete every row. Returns how many runs were dropped. Commits."""
    n = conn.execute(
        "SELECT COUNT(DISTINCT started_at) FROM harvest_run").fetchone()[0]
    conn.execute("DELETE FROM harvest_run")
    conn.commit()
    return n
```

- [ ] **Step 4: Run them and watch them pass**

```bash
.venv/Scripts/python -m pytest tests/test_runs.py -q
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/runs.py tests/test_runs.py
git commit -m "feat(runs): record what a harvest run cost, capped at 500 runs"
```

---

### Task 4: Harvest records its tally

**Files:**
- Modify: `humble_catalog/harvest.py` (imports, and `run`)
- Test: `tests/test_harvest.py`

**Interfaces:**
- Consumes: `runs.record` (Task 3); `db.cached_since`, `failures.count_since`, `quota.hit_at` (Task 2).
- Produces: after `harvest.run`, one `harvest_run` row per source that started a thread.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_harvest.py`:

```python
def _caching(conn, source, ok_title):
    """A source that caches a row for one title and fails for any other.

    A real Source writes source_cache on a live fetch, which is what
    `succeeded` counts; a bare Mock would never write one, so the count
    would be untestable.
    """
    def lookup(title):
        if title != ok_title:
            raise RuntimeError("503 backendFailed")
        conn.execute(
            "INSERT OR REPLACE INTO source_cache "
            "(source, query, fetched_at, json) VALUES (?,?,?,?)",
            (source, title, datetime.now(timezone.utc).isoformat(), "{}"))
        conn.commit()
        return []
    src = Mock(); src.lookup.side_effect = lookup
    return src

def _run_rows(conn):
    return conn.execute(
        "SELECT * FROM harvest_run ORDER BY source").fetchall()

def test_a_run_records_its_successes_and_failures(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    _seed(conn, "Learn C#", "ebook")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": _caching(conn, "hardcover", "Gray Waters")},
                _conn=conn)
    rows = _run_rows(conn)
    assert len(rows) == 1
    assert rows[0]["source"] == "hardcover"
    assert rows[0]["answered"] == 1      # only the cached title ticked
    assert rows[0]["succeeded"] == 1
    assert rows[0]["failed"] == 1
    assert rows[0]["quota_died"] == 0
    assert rows[0]["ended_at"] >= rows[0]["started_at"]

def test_a_run_that_exhausts_the_budget_is_marked(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = _429()
    boom.quota_resets_at.return_value = RESET
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": boom}, _conn=conn)
    assert _run_rows(conn)[0]["quota_died"] == 1

def test_a_source_already_out_of_quota_is_not_marked_as_dying_here(tmp_path):
    # paused conflates these two; a measured rate must not.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    conn.execute("INSERT INTO source_quota (source, hit_at, resets_at) "
                 "VALUES (?,?,?)",
                 ("hardcover", "2020-01-01T00:00:00+00:00", RESET.isoformat()))
    conn.commit()
    miss = Mock(); miss.lookup.side_effect = CacheMiss("x")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": miss}, _conn=conn)
    assert _run_rows(conn)[0]["quota_died"] == 0
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -k "records_its_successes or exhausts_the_budget or already_out_of_quota" -q
```

Expected: FAIL — `sqlite3.OperationalError` is *not* what you should see (the table exists from Task 1); expect `IndexError: list index out of range` on `_run_rows(conn)[0]`, because nothing writes rows yet.

- [ ] **Step 3: Import `runs` in `harvest.py`**

`humble_catalog/harvest.py` currently imports:

```python
from humble_catalog import db, failures, quota, stats
```

Change it to:

```python
from humble_catalog import db, failures, quota, runs, stats
```

- [ ] **Step 4: Add the tally helper**

Add directly above `def run(` in `humble_catalog/harvest.py`:

```python
def _tally(conn, prog, started, names):
    """Each source's cost for the run that began at `started`.

    Every number but `answered` is counted out of a table that already
    holds it: a live fetch is a cache write, and a failure is a
    source_failure row stamped with this run's time. That is why nothing
    in the pool had to learn to count.
    """
    since = started.isoformat()
    tallies = {}
    for name in names:
        hit = quota.hit_at(conn, name)
        tallies[name] = (prog.done[name],
                         db.cached_since(conn, name, since),
                         failures.count_since(conn, name, since),
                         hit is not None and hit >= started)
    return tallies
```

- [ ] **Step 5: Capture the start, track which sources ran, and record**

In `run`, replace the line

```python
    conn = _conn or db.connect(db_path)
```

with

```python
    started = datetime.now(timezone.utc)
    conn = _conn or db.connect(db_path)
```

Then replace

```python
    incomplete, lock = set(), threading.Lock()
    threads = []
```

with

```python
    incomplete, lock = set(), threading.Lock()
    threads, ran = [], []
```

and, in the loop that starts the threads, add `ran.append(name)` immediately after `threads.append(t)`, so the block ends:

```python
        t.start()
        threads.append(t)
        ran.append(name)
```

A source in the worklist with no entry in `sources` `continue`s before
this, so it gets no row — it did not run, and a zero row would read as
if it had.

Finally, replace

```python
    prog.finish(incomplete, paused=paused, repeats=_repeat_lines(conn))
```

with

```python
    runs.record(conn, started.isoformat(),
                datetime.now(timezone.utc).isoformat(),
                _tally(conn, prog, started, ran))
    prog.finish(incomplete, paused=paused, repeats=_repeat_lines(conn))
```

- [ ] **Step 6: Run the harvest tests**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -q
```

Expected: PASS, including every pre-existing test.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/harvest.py tests/test_harvest.py
git commit -m "feat(harvest): record each run's cost per source"
```

---

### Task 5: `harvest --runs` and `harvest --forget-runs`

**Files:**
- Modify: `humble_catalog/harvest.py` (two new functions), `humble_catalog/__main__.py` (flags and dispatch), `README.md`
- Test: `tests/test_harvest.py`

**Interfaces:**
- Consumes: `runs.history`, `runs.forget` (Task 3).
- Produces: `harvest.report_runs(db_path="catalog.db", _conn=None) -> None` and `harvest.forget_runs(db_path="catalog.db", _conn=None) -> None`. Both print and return; neither makes a request.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_harvest.py`:

First extend the package import at the top of `tests/test_harvest.py`
from `from humble_catalog import db, failures, harvest` to
`from humble_catalog import db, failures, harvest, runs`. Then add:

```python
def test_report_runs_shows_the_failure_rate(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    runs.record(conn, "2026-07-30T21:25:00+00:00",
                    "2026-07-30T22:04:00+00:00",
                    {"google_books": (1718, 573, 427, True)})
    harvest.report_runs(_conn=conn)
    out = capsys.readouterr().out
    assert "google_books" in out
    assert "2026-07-30 21:25" in out
    assert "43%" in out            # 427 / (573 + 427)
    assert "spent" in out

def test_the_rate_column_is_blank_without_live_attempts(tmp_path, capsys):
    # A source served entirely from cache has no rate; 0% would read as
    # "never fails".
    conn = db.connect(tmp_path / "t.db")
    runs.record(conn, "2026-07-30T21:25:00+00:00",
                    "2026-07-30T21:26:00+00:00",
                    {"oreilly": (1214, 0, 0, False)})
    harvest.report_runs(_conn=conn)
    out = capsys.readouterr().out
    assert "0%" not in out
    assert "-" in out

def test_report_runs_on_an_empty_table_says_so(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    harvest.report_runs(_conn=conn)
    assert "No harvest runs recorded" in capsys.readouterr().out

def test_forget_runs_empties_the_history(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    runs.record(conn, "2026-07-30T21:25:00+00:00",
                    "2026-07-30T22:04:00+00:00",
                    {"google_books": (1, 1, 0, False)})
    harvest.forget_runs(_conn=conn)
    assert "Forgot 1 recorded run." in capsys.readouterr().out
    assert runs.history(conn) == []
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -k "report_runs or rate_column or forget_runs" -q
```

Expected: FAIL — `AttributeError: module 'humble_catalog.harvest' has no attribute 'report_runs'`.

- [ ] **Step 3: Write both functions**

Add to the end of `humble_catalog/harvest.py`:

```python
def report_runs(db_path="catalog.db", _conn=None):
    """Print what each recorded run cost, newest first. Reads only.

    Unlike `report_failures`, nothing here is private: the table holds
    source names, counts and timestamps, never a title. This output is
    safe to paste into an issue.
    """
    conn = _conn or db.connect(db_path)
    try:
        rows = runs.history(conn)
        if not rows:
            print("No harvest runs recorded.")
            return
        width = max(len(r["source"]) for r in rows)
        print("harvest runs, newest first\n")
        print(f"{'started':<16}  {'source':<{width}}  {'titles':>6}  "
              f"{'live':>5}  {'failed':>6}  {'rate':>5}  quota")
        for r in rows:
            live, failed = r["succeeded"], r["failed"]
            # A cache-only source has no rate at all; printing 0% would
            # claim it never fails.
            rate = f"{failed / (live + failed):.0%}" if live + failed else "-"
            print(f"{r['started_at'][:16].replace('T', ' '):<16}  "
                  f"{r['source']:<{width}}  {r['answered']:>6}  "
                  f"{live:>5}  {failed:>6}  {rate:>5}  "
                  f"{'spent' if r['quota_died'] else ''}".rstrip())
    finally:
        if _conn is None:
            conn.close()

def forget_runs(db_path="catalog.db", _conn=None):
    """Delete the recorded run history. Prints how many runs went."""
    conn = _conn or db.connect(db_path)
    try:
        n = runs.forget(conn)
        print(f"Forgot {n} recorded run{'' if n == 1 else 's'}.")
    finally:
        if _conn is None:
            conn.close()
```

- [ ] **Step 4: Add the flags**

In `humble_catalog/__main__.py`, after the existing `--failures` argument:

```python
    p_harvest.add_argument("--runs", action="store_true",
                           help="Show what each past run cost - titles, live "
                                "requests, failure rate - and exit")
    p_harvest.add_argument("--forget-runs", action="store_true",
                           help="Delete the recorded run history and exit")
```

And change the dispatch:

```python
    elif args.command == "harvest":
        from humble_catalog import harvest
        if args.failures:
            harvest.report_failures()
        else:
            harvest.run(ignore_quota=args.ignore_quota)
```

to:

```python
    elif args.command == "harvest":
        from humble_catalog import harvest
        if args.forget_runs:
            harvest.forget_runs()
        elif args.runs:
            harvest.report_runs()
        elif args.failures:
            harvest.report_failures()
        else:
            harvest.run(ignore_quota=args.ignore_quota)
```

(`argparse` exposes `--forget-runs` as `args.forget_runs`.)

- [ ] **Step 5: Run the tests, then both flags by hand**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -q
```

Expected: PASS.

```bash
.venv/Scripts/python -m humble_catalog harvest --runs
```

Expected: `No harvest runs recorded.` on a catalog that has not harvested since Task 4. No network activity.

- [ ] **Step 6: Document both flags**

In `README.md`, extend the paragraph added for `--failures` (it begins "A title the source could not fetch caches nothing") with:

> `harvest --runs` shows what each past run cost — titles resolved, live
> requests, failures, and the failure rate among live attempts — newest
> first, so a rate that is climbing is visible without arithmetic. It
> holds no titles, only counts, so unlike `--failures` its output is safe
> to share. `harvest --forget-runs` clears that history; it is capped at
> the newest 500 runs regardless.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/harvest.py humble_catalog/__main__.py README.md tests/test_harvest.py
git commit -m "feat(harvest): add --runs and --forget-runs"
```

---

### Task 6: Draw the privacy line, record the backlog entry, run the gate

**Files:**
- Modify: `CLAUDE.md` (the `harvest --failures` bullet), `docs/BACKLOG.md` (Harvest section)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code-facing.

- [ ] **Step 1: Say which harvest output is private and which is not**

`CLAUDE.md` has a bullet beginning **"`harvest --failures` prints real owned titles."** Append one sentence to it:

```markdown
  `harvest --runs` is the opposite case and safe to share: it holds
  source names, counts and timestamps, never a title.
```

Without this the existing warning generalises to all harvest reporting,
and the one report that is safe to paste when asking for help gets
treated as if it were not.

- [ ] **Step 2: Record what the tally is and is not for**

In the Harvest section of `docs/BACKLOG.md`, directly after the
"Failure recording shipped as measurement only (2026-07-31)" entry, add:

```markdown
- **Run tally shipped alongside it (2026-07-31)** — `harvest_run` records
  what each run cost per source: titles answered, live fetches, failures,
  and whether the budget died in that run. It measures the *rate* and
  whether the rate is moving; it does not decide the
  transient-versus-deterministic question, which `source_failure`
  answers. Built because two facts decay: `last_failed_at` is
  overwritten, so failures-per-run can be counted once and never again,
  and `quota.blocked` cannot separate a run that exhausted the budget
  from one that began with it already spent. Capped at the newest 500
  runs by `runs.record`; `harvest --forget-runs` clears it. See
  `specs/2026-07-31-harvest-run-tally-design.md`.
```

- [ ] **Step 3: Run the whole gate**

```bash
powershell -File scripts/windows/verify.ps1
```

Expected: the full suite passes, `check_no_data_tracked.py` prints `clean`, `leak_check.py` prints `clean`, and the run ends `Verified: tests pass, no private data in the repo.`

If `leak_check.py` flags a phrase, it is almost certainly a prose substring collision — reword the sentence rather than touching `ALLOWED`.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/BACKLOG.md
git commit -m "docs: record the run tally, and which harvest output is shareable"
```

---

## Notes for the implementer

- **Nothing in the pool changes.** If you find yourself adding a counter to `_run_pool` or to `Source`, stop: both numbers are counted out of tables that already hold them, and a request counter on `Source` would need every test double to grow a numeric attribute that a `Mock` supplies as a `Mock`, breaking arithmetic silently rather than loudly.
- **`failed` counts titles, not quota units.** `google_books` has `retry_server_errors = False` so the two coincide there; a source that retries spends up to three units per failed title. Do not add a derived "units" column — it would bake today's retry policy into old rows.
- **The trim counts runs, not rows.** Trimming rows would behead a run midway and leave a partial tally that reads as a real one.
