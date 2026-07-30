# Harvest failure recording — design

Date: 2026-07-31.
New entry; sits under Harvest (identified 2026-07-26 while debugging
resume) alongside "Shorten the google_books worklist".

## The problem

`google_books` gets 1,000 requests a day against a ~2,300-title
worklist, and Google answers a noticeable share of them with
`503 backendFailed`. Those titles cache nothing, so a later run asks
again. The worry this spec starts from: if the failing set is stable,
harvesting gets slower every day until it stops making progress at all.

### Two failure modes that look identical from the terminal

**A title Google does not have is not this problem.** An unknown title
returns HTTP 200 with `totalItems: 0`. `Source.get_json` caches any 200
that passes `validate`, and `GoogleBooks` overrides nothing, so an empty
result is stored permanently and `lookup` returns `[]` from the cached
payload. A book missing from the index costs exactly one request, once,
ever. Only a *non-response* — 5xx, connection error, timeout — leaves
nothing behind.

That leaves two candidate shapes for the 503s:

*Transient.* A 503 is Google's backend under load, uncorrelated with the
query. Model it as probability `p` per request: each day the budget buys
1,000 requests, `(1-p) x 1000` of them cache permanently, and the
uncached set shrinks by a constant every day. It never grows. Total
requests to finish is `N/(1-p)` — at `p = 0.5`, about 4,600 against
~2,300 titles, so five days rather than two. Slower, bounded, no action
required. This is what removing 5xx retries in `82d178b` bought: it took
the median cost from ~2.5 requests per title to `1/(1-p)`.

*Deterministic.* Some titles produce a 503 reliably, because of the
query rather than the load. Then the failing set F never caches, every
run re-spends |F| requests on it, and because `build_worklist` walks
A-to-Z from the top every run, F is met **before** the untried tail —
failures take first claim on the budget. As |F| approaches the daily
1,000, new titles stop being reached. That is the halt, and it is real.

### The evidence points at deterministic, and we cannot confirm it

A run on 2026-07-31 failed mostly on TTRPG supplements, comics, and
programming books. Those three share a query shape rather than a
subject: long titles, internal colons, `#` and `+`, volume-and-issue
notation, hyphenated ranges. `clean_title` strips only *trailing* noise
— a trailing parenthetical, a trailing edition, a trailing ": A Novel"
— so everything internal survives into `intitle:"<title>"`, a quoted
phrase inside a field operator. *Shadow Hound Vol. 1-6* and *Learn C#*
are the shapes at issue.

But this cannot be checked, because **nothing records a failure**.
`_run_pool` calls `prog.log`, which bottoms out at a terminal write.
Failures are not in the database, not counted, not queryable; once the
scrollback is gone the run's failure set is gone. "Did the same titles
fail again?" is unanswerable today and would still be unanswerable after
tomorrow's run.

So the first deliverable is measurement, not policy. Recording failures
is also the substrate any later rule — skip-after-N, deprioritise,
quarantine — would need, so it is not a detour.

### A credential leak in the same line

`harvest.py` prints the raw exception:

```python
prog.log(f"  {name} failed for '{title}': {exc}")
```

For an HTTP error from `raise_for_status`, `str(exc)` embeds the request
URL, and for `google_books` that URL carries `key=<the API key>`. The
key is printed to the terminal on every failed title. `check.py` already
redacts exactly this before display and `test_check.py` asserts the
secret never reaches the output; `harvest` never got the same treatment.
Since this design stores that same string in a new column, the fix
belongs here.

## The change

### `source_failure`

Added to `SCHEMA`, carried by migration 10 — the comment-only pattern
migrations 7 and 9 use, since `CREATE TABLE IF NOT EXISTS` in `SCHEMA`
has already run on the connection:

```sql
CREATE TABLE IF NOT EXISTS source_failure (
  source TEXT NOT NULL, title TEXT NOT NULL,
  failures INTEGER NOT NULL,
  first_failed_at TEXT NOT NULL, last_failed_at TEXT NOT NULL,
  last_error TEXT NOT NULL,
  PRIMARY KEY (source, title));
```

**`failures` counts runs, not attempts.** `_run_pool` visits each title
once per run, and `retry_server_errors = False` makes that visit one
request, so the two collapse into the same number. A title at
`failures = 5` failed on five separate days. No run identifier is needed
for that to be true — which is what makes an aggregate table sufficient
and an append-only event log unnecessary.

Bounded by the worklist size, and it never needs sweeping: a title that
starts succeeding simply stops incrementing.

### `humble_catalog/failures.py`

Shaped like `quota.py`, and for the same reason — a fact about a source
that must outlive the process. Imports nothing from the package.

- `record(conn, source, title, error)` — `INSERT ... ON CONFLICT(source,
  title) DO UPDATE SET failures = failures + 1, ...`, so the counter
  needs no read-modify-write. Commits, as `quota.record` does.
- `top(conn, limit=None)` — rows by `failures` desc, then
  `last_failed_at` desc.

### Redaction

The regex moves out of `check.py` into `redact()` in `sources/base.py` —
it is a fact about source error strings, which is that module's subject.
`check.py` calls it; `harvest` calls it once and uses the result for
both the log line and the stored `last_error`, so the printed and the
persisted text cannot drift apart.

Redaction happens at the call site rather than inside `failures.record`,
which keeps `failures.py` free of package imports.

### Recording, in `_run_pool`

```python
except Exception as exc:  # noqa: BLE001
    failed = True
    detail = redact(str(exc))
    with lock:
        incomplete.add(name)
    if not _is_429(exc):
        prog.log(f"  {name} failed for '{title}': {detail}")
        with lock:
            failures.record(conn, name, title, detail)
        continue
    ...
```

Two lock acquisitions rather than one merged block: each guards one
coherent fact, the lock is uncontended, and `quota.record` already holds
it across a commit further down the same branch. Merging them would mean
hoisting the `_is_429` test above the `incomplete.add`, which buys
nothing and makes the branch read less like the classification it is.

`conn` is the caller's connection — the same one `quota.record` writes
through. WAL and `busy_timeout = 30000` are what make a second writer
safe here.

**Not recorded:** a 429, which is a fact about the quota rather than the
title and already lives in `source_quota`; and `CacheMiss`, which is an
offline source declining to fetch. Both already sit in their own
branches, so this falls out of the existing structure.

### Read path A — end-of-run summary

`harvest.run` reads the table after the threads join, alongside the
existing `paused` computation, and passes it to `prog.finish`. Progress
stays a display: it formats what it is given and queries nothing, which
is the pattern `paused` established.

Shown only when non-empty, so a clean run gains no noise:

```
Repeat failures (2+ runs):
  5x  google_books  Shadow Hound Vol. 1-6
  4x  google_books  Learn C#
  3x  google_books  The Endless Wars: Inferno!
  ...and 12 more - see 'harvest --failures'
```

A cutoff of 2 is the point of the exercise: one failure is noise, two in
separate runs is the beginning of evidence. Top 5 keeps a summary a
summary.

### Read path B — `harvest --failures`

A flag on the existing `harvest` parser, next to `--ignore-quota`, so it
is visible to someone staring at a slow harvest. Dispatch branches to
`harvest.report_failures()` and returns without running: no network, no
quota, no `HarvestProgress`.

```
runs  last failed  source        title
   5  2026-07-31   google_books  Shadow Hound Vol. 1-6
   4  2026-07-31   google_books  Learn C#
   1  2026-07-28   comicvine     Moonfall Vol. 1-3

Errors seen:
  47x  503 Server Error: Service Unavailable for url: ...key=REDACTED...
   2x  ConnectionError: ...
```

The trailing tally is what decides the question. If the query-shape
theory holds, nearly every row carries the same `backendFailed` text
over titles that visibly share a shape. If instead the errors scatter
across titles that never repeat, the theory is dead — for the cost of
reading one screen.

**The tally groups on the error *kind*, not the stored string.** A
`requests` HTTP error message ends in `" for url: <the full request
URL>"`, and that URL contains the title, so every stored `last_error` is
unique and a naive `GROUP BY` would report a tally of 1 for every row —
exactly no information. The grouping key is therefore the message
truncated at `" for url:"`, falling back to the whole string when that
marker is absent (connection errors, timeouts, `ValueError` from a bad
payload). `last_error` itself keeps the full redacted string, because
the URL is the useful part when diagnosing a single title.

### What this deliberately does not do

No behaviour changes. The same titles are requested in the same order;
nothing is skipped, deprioritised, or capped. A harvest costs what it
costs today plus one small write per failed title. In a few runs the
table says which policy, if any, is worth building.

## Testing

In `tests/test_harvest.py`, in the existing `_seed` + `Mock` style:

| Test | Pins |
|---|---|
| `test_a_failed_title_is_recorded` | one row, `failures = 1`, `first_failed_at == last_failed_at` |
| `test_the_same_title_failing_again_counts_the_second_run` | two `harvest.run` calls on one connection give `failures = 2` |
| `test_a_rate_limit_is_not_recorded_as_a_title_failure` | a 429 leaves a `source_quota` row and an empty `source_failure` |
| `test_a_cache_miss_records_nothing` | an offline source raising `CacheMiss` writes no rows |
| `test_a_recorded_error_never_contains_the_api_key` | `key=SECRETKEY` absent from both the stored `last_error` and stdout |
| `test_the_summary_lists_repeat_offenders` | the block appears after two failing runs, and is absent from a clean run |
| `test_report_failures_prints_without_harvesting` | seeded rows print with no sources constructed and no lookups made |

The second is the one that matters most: it is the single property the
feature exists to produce, and it should fail loudly if anyone later
reintroduces per-run retries and quietly turns `failures` into
"attempts".

The third is a separation test — it asserts two nearby facts stay in
different tables. Worth writing because both errors arrive at the same
`except`, so the branch keeping them apart is easy to collapse in a
later refactor.

`tests/test_sources_base.py` gains `test_redact_hides_key_params`:
`key=`, `api_key=`, `apikey=`, case-insensitive, other params untouched.
`tests/test_check.py`'s existing assertion stays exactly as it is and
becomes the proof that relocating the regex changed no behaviour.

`tests/test_db.py` gains a migration case: a database at
`user_version = 9` gains `source_failure` and arrives at 10.

## Privacy

1. Test titles come from `docs/TEST-DATA.md` only — *Shadow Hound
   Vol. 1-6*, *Learn C#*, *The Endless Wars: Inferno!*, *Gray Waters*,
   *Moonfall Vol. 1-3*. All already exist there, and they are the
   punctuation-heavy shapes this work investigates, so no new entries
   are needed.
2. The table lives only in `catalog.db`, which is gitignored. Nothing in
   `export.py` or the webapp reads it; `report_failures` writes to the
   terminal and nowhere else.
3. **A new leakable artifact exists even though no code leaks.**
   `harvest --failures` prints a list of real owned titles. That output
   must never reach a commit message, a doc, an issue, or a screenshot,
   and no automated check would catch it if it did — the same blind spot
   the Privacy section of `docs/BACKLOG.md` already records for images.
   One line is added there saying so.

The redaction fix is a privacy fix of a different kind: a credential
rather than catalog data.

## Verification

`scripts/windows/verify.ps1` — pytest, then `check_no_data_tracked.py`,
then `leak_check.py`. Plus `leak_check.py` run directly after the test
edits, per `CLAUDE.md`, on its own rather than piped.

## Docs

`README.md` gains `--failures` where `--ignore-quota` is documented.
`docs/BACKLOG.md` gains the privacy line above and a Harvest entry
recording that failure recording shipped as **measurement only**, naming
the question it exists to answer — so whoever reads the table in a week
knows which decision it was gathered for.
