# Budgeting a source's rate limit across harvest runs — design

Date: 2026-07-26

## Problem

`harvest`'s handling of a dead quota is entirely *within-run* state. When a
source 429s, `_run_pool` sets a local `quota_dead` flag and flips
`src.offline = True` ([harvest.py:45]); both die with the process. Nothing
crosses the run boundary.

The consequence is specific and is what prompted this entry. The free
Google Books quota is spent long before its worklist is, and google_books
is in `SOURCE_ORDER` for all three types, so its list is roughly twice any
other source's — it needs many days of runs to finish while every other
source completes from cache in seconds. On each of those days, `harvest`:

1. re-walks the whole google_books worklist from the top,
2. spends one live request on the first uncached title to rediscover a
   429 it already knew about yesterday,
3. reports it as a fresh failure, with the advice "rerun 'harvest' to
   resume" — which is the one thing that will not help.

Step 2 is the waste this design removes. `_with_retries` already treats
429 as terminal rather than retryable ([base.py:52]), so the cost is
precisely one request, not three — but it is one request out of a quota
whose scarcity is the whole problem, and it buys information the previous
run already had.

Step 3 is the misreporting. A source that is out of quota until tomorrow
morning is in a different state from a source that failed, and the run
says nothing about which.

## Goal

Record that a source's rate limit is spent, together with when it is
expected to lift, so that a later run can act on it: no live request, and
a message that says when to come back.

## What this is not

Two things the backlog entry raises that are deliberately out of scope.

- **Narrowing `SOURCE_ORDER`** so fewer types ask google_books. It is the
  other lever on the same symptom, and it works — but it changes which
  candidates every affected item can ever match against, which is a
  matching-quality decision rather than a quota one. Bundling the two
  would make their effects impossible to measure apart. It stays in
  `docs/BACKLOG.md` as its own entry.
- **`build_worklist` ordering.** A separate backlog entry, untouched here.
  This design does not depend on worklist order: it keys on the source
  name, not on a position in the list.

## Where the state lives

A new table, created in `SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS source_quota (
  source TEXT PRIMARY KEY, hit_at TEXT NOT NULL, resets_at TEXT NOT NULL);
```

At most one row per source, both timestamps ISO-8601 UTC, matching every
other timestamp in the schema.

`user_version` advances to 9 as a **carry-forward-only** migration — the
`executescript(SCHEMA)` in `connect()` has already created the table on
every connection by the time `_migrate` runs, so the migration exists only
to record the version. This is exactly the shape of migration 7, which
added the game tables ([db.py:404]).

`hit_at` is not read by any behaviour described below, and is kept anyway.
The single real risk in this design is a *wrong* reset guess, and a record
without the time it was written is undiagnosable: there is no way to tell a
row written five minutes ago from one written yesterday whose arithmetic
was wrong. One column is a cheap price for being able to answer that.

### Rejected: a sentinel row in `source_cache`

It needs no migration, and `reset` already preserves that table. Rejected
because a row whose `query` is `__quota__` and whose `json` is not a
response is a trap for every present and future reader of `source_cache` —
including `_migrate_secrets_out_of_cache_keys`, which rewrites keys
([db.py:528]), and the harvest cache lookup itself.

### Interaction with `reset`

`reset.DERIVED_TABLES` is an allowlist ([reset.py:8]), so `source_quota` is
preserved by omission and needs no change there. That is the correct
outcome, not an accident of the mechanism: the row describes the state of
Google's API, not the state of the owner's catalog, and wiping the derived
catalog does not give the quota back. `source_cache` and the game tables
are preserved the same way.

A test pins it, since "preserved by omission" is invisible in the code.

## Who knows that Google's quota is daily

Nothing in `harvest.py` may name a provider. The reset policy is a method
on `Source`:

```python
def quota_resets_at(self, now=None):
    """When a 429 from this source is expected to lift.

    Default: one hour. Deliberately short — a source whose real limit is
    per-minute must not sit out a whole day, and the cost of guessing
    short is one wasted request, while the cost of guessing long is lost
    harvesting.
    """
```

`GoogleBooks` overrides it with `quota.next_pacific_midnight(now)`. So the
one file that knows Google's Books quota is daily is `google_books.py`,
beside the comment that already explains its keyless quota is 0/day
([google_books.py:11]).

### The reset time is derived, not read

It is **not** taken from the 429 response. Google's Cloud quotas reset at
midnight Pacific, which the response body does not state, so a
source-declared policy is the only thing that can produce a useful answer;
a generic "24 hours from the 429" would place the reset up to a whole day
after the real one and waste that entire day's quota.

If a `Retry-After` header turns out to be present on some source's 429,
honouring it in preference to the declared policy is a strict improvement
and can be added without changing anything else here. It is not assumed to
exist.

### Pacific as a fixed UTC-8

```python
PACIFIC = timezone(timedelta(hours=-8))
```

`next_pacific_midnight(now)` returns the next instant strictly after `now`
at which the Pacific wall clock reads 00:00 under that fixed offset — in
UTC terms, the next 08:00.

The offset is fixed rather than resolved through `zoneinfo` because
`ZoneInfo("America/Los_Angeles")` requires the `tzdata` package on Windows,
and the project has no timezone dependency (`pyproject.toml` lists five
runtime dependencies, none of them for dates). Adding one for a single
timestamp is out of proportion, on a project that hand-rolled PNG
generation to avoid an imaging dependency for one icon.

The cost is stated exactly: during Pacific Daylight Time the true reset is
07:00 UTC, so the computed time is **one hour late**. That is the safe
direction, and it is why the constant is UTC-8 rather than UTC-7 or an
average. Waiting an extra hour costs nothing — the source is walked from
cache either way, and the next run picks it up. Retrying an hour early
costs the proving request this design exists to save.

## `humble_catalog/quota.py`

A new module, following how `reset.py` and `backup.py` each own one small
concern rather than growing `db.py` (already 589 lines).

```python
def next_pacific_midnight(now=None) -> datetime
def record(conn, source, resets_at)          # INSERT OR REPLACE, commits
def clear(conn, source)                      # DELETE, does not commit
def blocked(conn, source, now=None)          # -> resets_at | None
```

`blocked` returns the stored `resets_at` when it is still in the future and
`None` otherwise, so an expired record needs no sweeping: it is simply
ignored, and overwritten by the next 429. Nothing ever has to run a
cleanup pass.

`clear` does not commit, because its one caller commits in the same
transaction as the cache insert (below). `record` does commit, because its
caller has nothing else to write.

The module imports only the standard library, so `sources/base.py` can
import it with no risk of a cycle.

### `progress._duration` becomes public

`quota` formats a reset time as "in 6h04m", which `progress._duration`
already does and does well, including the Windows-safe compact form. It
gains a second caller and therefore loses its underscore, exactly as
`stats._console_safe` did when `bundle_preview` started using it.

## Harvest flow

### Before the threads start

`run()` asks `quota.blocked(conn, name)` for each source in the worklist.
A blocked source is started with `offline = True` and its reset time is
passed to its pool. The pool then walks its list serving only what is
cached: every uncached title raises `CacheMiss` and is skipped, so the
source makes **zero** live requests, where today it makes one.

The cache-only walk is kept rather than skipping the source outright,
which is the more obvious reading of "skip the source and say so". The
reason is that the walk is what makes the progress number true. A source
that is 90% cached still reports `google_books 7200/8000` on a blocked
run; skipping it would report nothing, and the number would appear to go
backwards between runs. The walk costs one indexed cache lookup per
remaining title, which the backlog already judged "cheap per title and
correct".

A blocked source stays in `incomplete`. It has not finished its worklist,
and the existing contract is unchanged.

### When a 429 arrives

The existing 429 branch gains one call: `quota.record(conn, name,
src.quota_resets_at())`. Its message gains the reset time.

That write goes through **the caller's connection, under the existing
`lock`** — not the worker's own connection. `HarvestProgress`'s docstring
promises that "only one connection (the caller's) is ever written, off the
worker threads' own connections" ([progress.py:250]), and a second writer
would quietly falsify it. `_run_pool` therefore takes `conn` as an
argument; it already takes the lock.

`quota_resets_at` is called on the source directly, with no `getattr`
fallback, so a test double that 429s must define it. That is deliberate:
a silent default would let a real source lose its policy to a typo.

### Reporting a paused source

`HarvestProgress` carries three states — working, done, failed — for the
reason its own docstring gives: "the count alone is ambiguous". A source
out of quota until tomorrow is precisely a fourth case that the count
cannot express, and folding it into either neighbour loses the
distinction that motivates the mark at all. It would report as *done*
today, because `CacheMiss` is not a failure and `settle(failed=False)`
marks the source complete.

So a fourth state, `paused`, is added: `⏸`, with `-` in the ASCII set.

**A source is paused if it has a live quota record when the run ends** —
which covers both a source blocked before the threads started and one
that hit its first 429 mid-run. The two are the same condition and must
not report differently. `_run_pool` therefore keeps calling `settle`
exactly as it does now, marking a fresh 429 as failed; `finish` then
overrides the mark for every named source. One rule, applied in one
place, rather than two paths that could drift.

`_glyphs()` tests the whole glyph set for encodability at once
([progress.py:236]), so a console that cannot encode the new mark
downgrades all four to ASCII rather than just one. Accepted: it is the
existing behaviour of that function and the ASCII set is legible. In
practice the Windows console codepages that matter (cp437, cp850, cp1252)
encode none of `▸✓✗`, so they are already on the ASCII path.

`finish()` gains an optional `paused` mapping of source name to reset time
and prints those sources on their own line, with their reset time, instead
of letting them inherit "rerun 'harvest' to resume". For a source that
will 429 again immediately, that advice is actively wrong, which is the
misreporting named in the problem statement.

## Recovering from a wrong record

A stored reset time is a derived guess, so it can be wrong: a paid key
rotated in, or a limit that was per-minute rather than daily. Left
unaddressed, a wrong guess means up to a day of refused harvesting with no
way out short of editing the database. Two mechanisms, and the second is
why the first is rarely needed.

- **`harvest --ignore-quota`** ignores every stored record for that run.
  It does not delete them: a genuine 429 will re-record, so the flag
  asserts nothing about the future.
- **A successful live request clears its source's row.** `get_json`
  deletes it in the same transaction as the cache insert it already
  performs, so a source that has come back to life cannot leave a stale
  record behind to mislead the next run. One statement against a table
  with at most six rows, keyed on its primary key.

### Why `check` cannot clear a record

`check` runs against `:memory:` so that `source_cache` can never fake a
success ([check.py:3]). That connection has its own empty `source_quota`,
so a successful `check` clears nothing in the real catalog, and a
`check` cannot be used to unblock a harvest.

This is correct rather than a gap — `check`'s question is "is this API
answering right now, with this key", and it must not consult or mutate
persistent state to answer it — but it is written down here because it
otherwise reads as a bug. `check` is unchanged by this design: a
dead-quota source reports `FAIL` with the 429, which is a truthful answer
to the question it asks.

## Module layout

- `humble_catalog/quota.py` — new; the table and the arithmetic.
- `humble_catalog/db.py` — `source_quota` in `SCHEMA`; `user_version` 9.
- `humble_catalog/sources/base.py` — `Source.quota_resets_at`; the
  clear-on-success delete in `get_json`.
- `humble_catalog/sources/google_books.py` — the Pacific-midnight
  override.
- `humble_catalog/harvest.py` — the pre-thread `blocked` check, the
  `quota.record` call, `conn` into `_run_pool`, `paused` into `finish`.
- `humble_catalog/progress.py` — the `paused` state and glyph;
  `_duration` → `duration`; `finish(incomplete, paused=None)`.
- `humble_catalog/__main__.py` — `harvest --ignore-quota`.
- `README.md` — a sentence on the harvest bullet.

## Privacy

`source_quota` holds source names and timestamps. Nothing in it is derived
from the catalog: no titles, no authors, no counts, nothing that reveals
what the owner owns. It is not exported by `export.py` and not read by the
viewer, and it adds no term for `leak_check.py` to consider.

New tests seed items by title, so `.venv/Scripts/python
scripts/leak_check.py` runs after they are added, and titles come from
`docs/TEST-DATA.md` — `test_harvest.py` currently uses *Gray Waters*,
*Shadow Hound*, *Night Signal* and `Book {i}`, which this extends rather
than replaces.

## Testing

`tests/test_quota.py` for the module, extending `tests/test_harvest.py`
for the flow. Time is injected through the `now=` parameters throughout —
no test sleeps, and none depends on the real clock.

**Arithmetic** (`test_quota.py`)

- 09:00 UTC yields tomorrow's 08:00 UTC; 03:00 UTC yields today's.
- Exactly 08:00 UTC yields the *next* day's, pinning "strictly after now"
  — the boundary a run started at the reset instant would hit.
- The returned value is timezone-aware UTC, so `isoformat()` round-trips
  through the column and compares correctly against a later `now`.
- `blocked` returns the time while it is future, `None` once it is past,
  and `None` for a source with no row.
- `record` twice for one source leaves one row (the `INSERT OR REPLACE`).

**Flow** (`test_harvest.py`)

- A 429 writes a `source_quota` row whose `resets_at` is the source's own
  `quota_resets_at`, not a shared constant.
- **A blocked rerun makes zero live attempts and still ticks the cached
  titles.** The core test: `_SpentQuota` extends with an assertion that
  `src.live == 0` — today it is 1 — while `run_status.done` still counts
  the cached ones. This is the test that fails if the pre-thread check is
  ever removed.
- A blocked source reports `paused`, not `done`. Guards the specific way
  this could regress silently: `CacheMiss` is not a failure, so without
  the fourth state a blocked source reports as complete.
- A source that hits its *first* 429 mid-run also reports `paused`, not
  `failed` — the two paths into the same condition must agree.
- An expired record is ignored: the source goes live and attempts a
  request.
- `--ignore-quota` attempts a live request despite an unexpired record,
  and leaves the record in place.
- A successful live request clears its row (through a real `Source` with a
  mocked `http`, as `test_fully_cached_harvest_sends_nothing` does).
- The default `quota_resets_at` is about an hour out, and `GoogleBooks`
  overrides it to a Pacific midnight. Pins that the provider knowledge
  lives in the subclass.
- `reset` preserves `source_quota` — the omission from `DERIVED_TABLES` is
  invisible in the code, so only a test states it.

**Existing tests that must keep passing unchanged**

`test_429_stops_only_its_pool` and
`test_429_keeps_draining_the_titles_already_cached` describe the
*first* run's behaviour, which this design does not alter: with no
record present, a 429 still costs one live request and still switches
the source to cache-only. If either needs editing, the change has gone
further than intended.

## Appendix: what each source's limit actually is

Surveyed 2026-07-26, after the mechanism shipped, to decide which sources
should declare a window rather than inherit the one-hour fallback.
"Our rate" is the throttle in `Source.delay` for a single harvest run.

| Source | Documented limit | Window | Our rate | Declares? |
|---|---|---|---|---|
| `google_books` | 10,000/day (keyless: 0) | daily, midnight Pacific | 0.5/s | yes — Pacific midnight |
| `comicvine` | 200 per *resource*, per hour | rolling hour | 180/hr | yes — 1 hour |
| `hardcover` | 60/minute | per minute | 30/min | yes — 2 minutes |
| `open_library` | 1/s (3/s if identified) | per second | 0.5/s | no |
| `oreilly` | none published | — | 0.5/s | no |
| `audible` | none published | — | 0.5/s | no |

Three findings changed the code:

- **Hardcover's window is per-minute**, so the one-hour fallback would
  idle it about sixty times longer than the limit lasts. This is the
  failure the fallback's docstring warns about, and it turned out to be
  real rather than hypothetical. It declares two minutes.
- **Comic Vine's hour matches the fallback by coincidence**, and it is the
  source most likely to 429 in normal use (180/hr against a 200/hr cap).
  It declares the hour, so a later change to the fallback cannot move it.
  Its limit being per *resource* also means `search/` and the `credits()`
  top-up draw on separate budgets.
- **Open Library rate-limits with 403, not 429**, so `_is_429` never sees
  it and it falls through to the ordinary failure path. Left as-is and
  documented in `open_library.py`: a 403 is ambiguous, and recording one
  as a spent quota would idle the source over what may be a permanent
  block.

`oreilly` and `audible` are undocumented internal endpoints. They keep the
fallback, which is the honest position — there is no window to declare.

## Out of scope

- No change to `check`, `enrich`, or `SOURCE_ORDER`.
- No viewer or `/api/stats` surface for quota state. `harvest` is the only
  command that can act on it, and the panel counts catalog contents rather
  than run state.
- No `Retry-After` parsing (see above — not assumed to exist).
- No request *budgeting* in the accounting sense: nothing counts requests
  or predicts exhaustion in advance. The record is written after a 429 and
  says only "spent, until roughly then".
- No per-source configuration surface. The reset policy is code, on the
  source class, not a setting.
