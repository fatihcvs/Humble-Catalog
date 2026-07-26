# Enrichment: split harvest from match

Date: 2026-07-19

## Problem

A full `enrich` run over the ~2,250 pending items takes an estimated 8-9
hours, and any improvement to matching that needs data an earlier run
declined to fetch forces the whole run again.

Two independent causes:

1. **Idle waiting.** Each `Source` throttles itself with its own `delay`
   (`base.py`), but `enrich.run()` walks items and sources strictly
   sequentially. While one source sleeps its delay, the other five are
   idle. The pipeline runs at one request per delay overall instead of
   one request per delay *per source*.

2. **The early break.** `enrich.run()` stops consulting sources once a
   candidate clears `AUTO`. That saves quota today, but it means the
   skipped sources were never fetched, so a later matching improvement
   that wants their data has no cache to replay and must re-run the
   whole network pass.

Measured shape of the remaining work (2,246 pending; ~1.5 lookups per
item in the enriched sample so far):

| source        | lookups | delay | serial time |
|---------------|---------|-------|-------------|
| comicvine     |   988   | 20.0s | **5.5 h**   |
| google_books  | 2,303   |  2.0s | 77 min      |
| hardcover     | 1,315   |  2.0s | 44 min      |
| open_library  | 1,207   |  2.0s | 40 min      |
| oreilly       | 1,207   |  2.0s | 40 min      |
| audible       |   108   |  2.0s |  4 min      |

The two bottlenecks are different in kind. The 2s sources are
**idle-bound**: slow only because they wait their turn, and concurrency
recovers all of it. Comic Vine is **quota-bound** at 200 requests/hour,
so its 5.5 hours are immovable by any scheduling. Concurrency cannot
create quota.

## Decision

Split enrichment into three phases with `source_cache` as the contract
between them:

```
harvest        ->  source_cache  ->  enrich        ->  enrich --credits
network, ~5.5h     (exists)          local, secs       network, ~3h
6 threads                            no network        comics only
resumable                            re-runnable       resumable
```

Harvest fetches every relevant source for every item unconditionally.
Matching then becomes a purely local operation that can be re-run in
seconds, as often as ideas arrive, without touching the network.

This deliberately spends more quota once (~7,100 lookups instead of
~3,400) to buy unlimited cheap iteration afterwards.

### Alternatives rejected

- **Parallelise the existing loop in place** (N workers over items, with
  a shared locked per-source limiter). Roughly the same speedup, smaller
  change, but keeps the early break and therefore keeps the "an
  improvement invalidates the run" problem, which is the actual
  complaint.
- **Per-source queues with an item state machine** routing items from
  source to source as each fails to match. Preserves the early break
  *and* parallelises, but the scheduling machinery is far more complex
  than either of the other two for no additional benefit once the early
  break is abandoned anyway.
- **Drop Comic Vine as the first source for comics.** Could remove most
  of the 5.5h wall, but risks materially worse comic metadata;
  google_books is weak on volumes and single issues. Not taken.

## Components

### `humble_catalog/harvest.py` (new)

Builds a worklist of `(source, cleaned_title)` pairs: for every item
whose type is not `music` or `android`, every source in
`SOURCE_ORDER[type]`, with no early break. `SOURCE_ORDER` continues to
define which sources are relevant per type; only the break is dropped.

Groups the worklist by source and runs one thread per source, each
draining its own queue and calling `src.lookup(cleaned)`.

**One thread per source is load-bearing.** `Source._last`, the throttle
state in `base.get_json`, is per-instance mutable state. With exactly
one thread per instance it is never contended, so the existing
rate-limiting code is correct under concurrency with no locks and no
edits. A generic N-workers-over-items pool would instead require a
shared, locked limiter.

**Resumability needs no bookkeeping.** Harvest does not compute which
pairs are already fetched. It calls `lookup` for every pair and lets the
existing cache check in `get_json` turn already-fetched pairs into a
local SELECT. Because `_last` is only updated inside `_send`, cache hits
do not pay the throttle: a resumed harvest fast-forwards through
completed work at disk speed and resumes throttling where it stopped.
Reconstructing cache keys outside the sources would require duplicating
each source's URL and param construction, creating a second notion of
"done" that could drift from the real one.

### `humble_catalog/enrich.py` (modified)

`run()` keeps its scoring loop but runs offline. It drops:

- the `disabled` set and 429 handling (no network to rate-limit)
- the early `break` at the `AUTO` threshold; scoring every cached
  candidate costs microseconds and yields strictly better matches

### `humble_catalog/sources/base.py` (small change)

`Source.__init__` gains `offline=False`. When set, `get_json` raises
`CacheMiss` instead of calling `_send`. This *guarantees* the match
phase is local rather than assuming it, and makes the guarantee
testable.

### `humble_catalog/db.py` (small change)

`connect()` gains WAL mode and `check_same_thread=False`. Each harvest
thread gets its own connection.

### `humble_catalog/progress.py` (modified)

`Progress` assumes one linear counter and a single `current` item, which
is meaningless with six concurrent pools. Harvest reports per-source
counts instead:

```
harvest  comicvine 412/988 - google_books 2303/2303 done - hardcover 1315/1315 done
```

### Credits top-up

`ComicVine.credits()` is a second request per matched comic, and it is
dependent: the issue URL is only known once matching has picked a
winner. Harvesting credits for all five candidates per comic would add
4,940 requests, about 27 hours, so it is not part of harvest.

Instead `enrich --credits` runs after matching: for each comic with
status `matched`, it reads the winning candidate's
`extra.first_issue_api_url` from the stored `candidates` JSON, calls
`credits()`, and patches `authors` and `illustrator`. Single-threaded,
cached, resumable, roughly 3 hours for the comics that match.

## Data flow

Harvest writes **only** `source_cache`. It never touches `enrichment` or
`items`, so an interrupted harvest cannot leave enrichment half-updated.

Match reads `source_cache` and writes `enrichment` exactly as today.

Credits reads `candidates` and patches `enrichment`.

## Error handling

Each pool is isolated; a failing thread must not end the run. Per-item
`try/except` inside each pool mirrors today's handling in `enrich.run()`.

A 429 stops that pool only and marks the source incomplete; the other
five continue. The final summary names incomplete sources. Because
harvest is idempotent, the remedy is always to run it again later.

## Testing

`tests/test_enrich.py` already injects fake sources, so match-phase
tests survive largely intact, moving to pre-populated cache rows.

New coverage:

- harvest calls every source for every eligible item (no early break),
  and only type-relevant sources
- a fully pre-populated cache makes harvest perform zero network calls
- one source raising does not stop the others, and is reported as
  incomplete
- match in offline mode never sends, and degrades gracefully on
  `CacheMiss`
- a fake source recording thread identities confirms one thread per
  source, the assumption the lock-free throttle rests on

## Expected outcome

| | today | after |
|---|---|---|
| first full run | 8-9 h | ~5.5 h harvest + ~3 h credits |
| re-run after a matching change | 8-9 h | seconds |
| interrupted run | restarts network work | resumes from cache |

The first run is not dramatically faster, because Comic Vine's quota
dominates and cannot be scheduled away. The win is that it is the
**last** full run: every later matching idea replays from cache.

## Known costs

- ~7,100 lookups instead of ~3,400. Some of that quota buys data no
  matcher ever uses.
- End-to-end first run is ~8.5 h, not 5.5 h, since credits cannot begin
  until matching completes. It is fully incremental and interruptible.
