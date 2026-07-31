# Harvest run tally — design

Date: 2026-07-31.
Follows `specs/2026-07-31-harvest-failure-recording-design.md`, which
shipped `source_failure` the same day. That spec answers "do the same
titles keep failing?"; this one answers "at what rate, and is the rate
moving?".

## The problem

`source_failure` counts how many runs each title failed in. It does not
say how many requests a run spent, how many succeeded, or what fraction
of live attempts failed. Those are the numbers that turn "harvesting
feels slow" into an estimate.

Most of them can be reconstructed today, which is worth stating so the
new table is not oversold:

- **Successes per run are permanent and exact.** Every `source_cache`
  row carries `fetched_at`, so bucketing by day gives new fetches per
  run for all time.
- **The quota event is recorded.** `source_quota.hit_at` says when a
  source's budget died.
- **The last run's duration is recorded**, in `run_status`.

Worked from those three, the 2026-07-30 harvest reads as: ran 21:25:11
to 22:04:03 UTC; `google_books` hit its limit at 22:04:02, one second
before the run ended; 573 new `google_books` rows cached that day. The
run therefore spent its whole allowance to buy 573 titles, putting the
failure rate somewhere around 45-50% of requests. At that rate the 1,163
remaining titles need two to three more full runs.

### What is missing

**Failures per run decay.** `source_failure.last_failed_at` is
overwritten, so a title that failed in runs 1, 2 and 3 leaves only run
3's timestamp. Counting failures in a window is exact for the run that
just happened and progressively wrong for older ones. Successes never
decay; failures do.

That asymmetry means the rate above can be derived once, immediately
after a run, and never again. A per-run row makes it permanent.

**"The budget died in this run" is not distinguishable from "the source
started out dead."** `harvest.run` computes `paused` from
`quota.blocked`, which is true in both cases. That is correct for the
advice `finish` prints - both mean "do not expect progress" - but it is
exactly the wrong conflation for "did this run get its full budget?",
which decides whether a rate computed from it means anything.

## The change

### `harvest_run`

Added to `SCHEMA`, carried by migration 11 - the comment-only pattern
migrations 7, 9 and 10 use.

```sql
CREATE TABLE IF NOT EXISTS harvest_run (
  started_at TEXT NOT NULL, source TEXT NOT NULL, ended_at TEXT NOT NULL,
  answered INTEGER NOT NULL,    -- titles resolved, from cache or live
  succeeded INTEGER NOT NULL,   -- live fetches that cached a row
  failed INTEGER NOT NULL,      -- titles that errored (non-429)
  quota_died INTEGER NOT NULL,  -- 1 if the budget was exhausted in THIS run
  PRIMARY KEY (started_at, source));
```

Like `source_cache`, `source_quota` and `source_failure`, it stays out of
`reset`'s `DERIVED_TABLES`: it is an observation about a source, not
derived catalog.

**`failed` counts titles, not quota units.** `google_books` has
`retry_server_errors = False` so the two coincide there, but a source
that retries spends up to three units per failed title. The table stores
what it observed; any analysis applies the multiplier itself. Storing a
derived "units" column would bake today's retry policy into old rows.

### No new plumbing

Both counts already exist in the database when a run ends:

- `succeeded` is `source_cache` rows for that source with
  `fetched_at >= started_at`. A live fetch **is** a cache write, so
  there is nothing else to count.
- `failed` is `source_failure` rows with `last_failed_at >= started_at`.
  A title fails at most once per run and this run stamps every title
  that failed in it, so the window count is exact - and the row, once
  written, keeps that exactness after `last_failed_at` later moves.

So `_run_pool` is untouched, `Source` is untouched, `progress` is
untouched. The `failed` boolean stays a boolean. The feature is:
capture `started_at` at the top of `run`, then count after the joins.

The rejected alternative was a request counter on `Source`, incremented
in `get_json`. It would touch the class every source inherits from, and
every test double would need a numeric attribute - a `Mock`
auto-creates `requests` as a `Mock`, so the arithmetic would break
silently rather than loudly.

`answered` is the one number not in a table: it is `prog.done[name]`,
tracked under lock and final once the threads join.

### `humble_catalog/runs.py`

Matching `quota.py` and `failures.py` - one table, one module, testable
alone. `harvest.py` already holds seven functions and should not absorb
an eighth concern.

```python
KEEP_RUNS = 500

def record(conn, started_at, ended_at, tallies, keep=KEEP_RUNS)
def history(conn)      # newest first
def forget(conn)       # delete every row; returns how many runs were dropped
```

`record` takes every source's tally at once -
`{source: (answered, succeeded, failed, quota_died)}` - so a harvest
writes its rows and trims once rather than trimming per source. `keep`
is a parameter rather than a constant read inside the function purely so
a test can prove the trim with three runs instead of five hundred.

`history` rather than `all`, which would shadow the builtin.

### Retention

The table is bounded by construction: `record` trims to the newest
`KEEP_RUNS` runs after inserting. At roughly one run a day and six rows
each, 500 runs is about 500 days and 3,000 rows - small, and incapable
of growing past that even if nobody ever thinks about it again. For a
trend table the oldest rows are the least valuable, so automatic
trimming discards the right end.

`harvest --forget-runs` empties it deliberately, for a clean slate.

A run is a distinct `started_at` across up to six rows, so the trim
works on runs rather than rows:

```sql
DELETE FROM harvest_run WHERE started_at NOT IN (
  SELECT started_at FROM harvest_run
  GROUP BY started_at ORDER BY started_at DESC LIMIT ?)
```

### Where each count comes from

Each is asked of the module that owns its table, rather than `harvest`
reaching across:

| Count | Owner |
|---|---|
| `failures.count_since(conn, source, since)` | `failures.py`, which owns `source_failure` |
| `db.cached_since(conn, source, since)` | `db.py`, which owns the schema and already hosts `fetch_items` |
| `quota.hit_at(conn, source)` | `quota.py`, for the `quota_died` comparison |
| `answered` | `prog.done[name]`, in memory |

This costs three small functions and means the `source_cache` window
query has one home if the cache ever changes shape.

### `harvest --runs`

```
harvest runs, newest first

started           source          titles   live  failed   rate  quota
2026-07-30 21:25  google_books      1718    573     427    43%  spent
2026-07-30 21:25  hardcover         1320      7       0       -
2026-07-30 21:25  comicvine          988      0       0       -
```

The `titles` column is `answered` and the `live` column is `succeeded`;
the headings are what a reader wants to see, the column names are what
the row means. `titles - live` is therefore what came from cache.

`rate` is `failed / (succeeded + failed)` - the failure rate among live
attempts, which is the number this whole exercise is about. It prints
`-` rather than `0%` when nothing live was attempted: a source served
entirely from cache has no rate, and `0%` would read as "never fails".

`quota` reads `spent` when `quota_died`, blank otherwise.

Empty table: `No harvest runs recorded.`

### CLI

`--runs` and `--forget-runs` join `--ignore-quota` and `--failures` on
the existing `harvest` parser. Dispatch checks `--forget-runs`, then
`--runs`, then `--failures`, then runs the harvest.

## Testing

| Test | Pins |
|---|---|
| `test_record_writes_one_row_per_source` | six sources in, six rows out |
| `test_record_trims_to_the_newest_runs` | four runs with `keep=2` leaves the two newest, all their sources intact |
| `test_history_is_newest_first` | ordering |
| `test_forget_empties_the_table_and_counts_runs` | the return value counts runs, not rows |
| `test_a_run_records_its_successes_and_failures` | one source, one title cached and one failing, gives `succeeded=1, failed=1` |
| `test_a_source_already_out_of_quota_is_not_marked_as_dying_here` | blocked before the run gives `quota_died=0` - the distinction `paused` loses |
| `test_the_rate_column_is_blank_without_live_attempts` | a cache-only source shows `-` |
| `test_report_runs_on_an_empty_table_says_so` | empty case |

The trim test is the one that matters for the objection this table was
revised to answer: without it, `KEEP_RUNS` is a comment rather than a
guarantee.

## Privacy

**This table holds no titles** - source names, counts, timestamps, a
flag. Nothing in it reveals what is owned, so the output of
`harvest --runs` is safe to paste into an issue or a commit message.

That is worth writing down, because the standing order in `CLAUDE.md`
currently warns that `harvest --failures` prints real owned titles, and
someone could reasonably over-generalise that to all harvest reporting.
The bullet gains a sentence drawing the line.

Tests use the invented source-agnostic data already in this repo; no new
`docs/TEST-DATA.md` entries are needed, since the table names sources
rather than books.

## Verification

`scripts/windows/verify.ps1` - pytest, `check_no_data_tracked.py`, then
`leak_check.py`. Run `leak_check.py` directly after the test edits, on
its own rather than piped.

## Docs

`README.md` gains `--runs` and `--forget-runs` beside `--failures`.
`docs/BACKLOG.md` records what the tally is for and what it is not: it
measures the rate, it does not decide the transient-versus-deterministic
question, which `source_failure` answers.
