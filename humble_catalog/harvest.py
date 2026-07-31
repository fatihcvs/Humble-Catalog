import sys
import threading
from collections import Counter
from datetime import datetime, timezone
from humble_catalog import db, failures, quota, runs, stats
from humble_catalog.enrich import SOURCE_ORDER, SOURCE_CLASSES
from humble_catalog.progress import HarvestProgress, duration
from humble_catalog.sources.base import CacheMiss, redact
from humble_catalog.titles import clean_title

SKIP_TYPES = ("music", "android")

def build_worklist(conn):
    """Map each source name to the de-duplicated cleaned titles it must fetch.

    Every non-music/android item contributes its cleaned title to each
    source in SOURCE_ORDER for its type. Titles are de-duped per source so
    two items with the same cleaned title cost one request.

    Each list is sorted by casefolded title, which makes the order a pure
    function of the item set rather than of SQLite's row order - the query
    has no ORDER BY, so a reset, reparse or merge could reshuffle the scan.
    Resume does not depend on this (it is keyed on the cache, not on
    position); what the sort buys is that two runs over an unchanged
    catalog present the same work in the same sequence, and that a test
    can assert an order at all.

    The key is (casefold, raw) rather than casefold alone because Python's
    sort is stable: a case-only tie would otherwise fall back to that same
    unordered scan. Accents are not folded, so a title whose first letter
    is accented sorts past 'z' - determinism is the property needed here
    and codepoint order has it. See
    docs/superpowers/specs/2026-07-30-harvest-worklist-order-design.md.
    """
    worklist = {name: [] for name in SOURCE_CLASSES}
    seen = {name: set() for name in SOURCE_CLASSES}
    rows = conn.execute("SELECT name, type FROM items").fetchall()
    for row in rows:
        if row["type"] in SKIP_TYPES:
            continue
        cleaned, _ = clean_title(row["name"])
        for sname in SOURCE_ORDER.get(row["type"], SOURCE_ORDER["ebook"]):
            if cleaned not in seen[sname]:
                seen[sname].add(cleaned)
                worklist[sname].append(cleaned)
    return {name: sorted(titles, key=lambda t: (t.casefold(), t))
            for name, titles in worklist.items() if titles}

def _is_429(exc):
    resp = getattr(exc, "response", None)
    return resp is not None and getattr(resp, "status_code", None) == 429

def _run_pool(name, src, titles, prog, incomplete, lock, conn):
    """Walk one source's titles, ticking only the ones it actually got.

    A 429 ends the source's *network*, not its cache, so the quota dying
    switches the source offline and the walk continues: titles an earlier
    run already fetched still cost nothing and still count. Stopping
    outright instead would strand every cached title below the first
    uncached one, and a source whose first gap sits near the top of the
    list would show the same handful of steps on every rerun.

    `conn` is the caller's connection, used under `lock` to record the
    dead quota. The worker's own connection is deliberately not used:
    HarvestProgress promises that only one connection is ever written.
    """
    failed = quota_dead = False
    for title in titles:
        try:
            src.lookup(title)
        except CacheMiss:
            continue  # nothing cached and nothing left to fetch it with
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
            if quota_dead:
                break  # offline was ignored: stop before we hammer the API
            quota_dead = True
            src.offline = True
            resets_at = src.quota_resets_at()
            with lock:
                quota.record(conn, name, resets_at)
            prog.log(f"  {name}: rate limit hit - serving the rest from cache; "
                     f"rerun 'harvest' after {_when(resets_at)}")
            continue
        prog.tick(name)
    prog.settle(name, failed=failed)

def _when(resets_at):
    """A reset time as an absolute instant plus how long that is away."""
    ahead = (resets_at - datetime.now(timezone.utc)).total_seconds()
    return f"{resets_at.isoformat(timespec='minutes')} (in {duration(ahead)})"

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

def run(db_path="catalog.db", sources=None, _conn=None, ignore_quota=False):
    """Fetch every relevant source for every eligible item into source_cache.

    One thread per source; each owns its Source (and, when live, its own
    db connection). Returns the set of sources left incomplete.

    A source whose rate limit an earlier run recorded as spent starts
    offline, so it serves what is cached and spends no request proving
    the limit is still there. `ignore_quota` disregards those records for
    one run, for when the stored guess is wrong - a paid key rotated in,
    or a limit that turned out to be per-minute.
    """
    started = datetime.now(timezone.utc)
    conn = _conn or db.connect(db_path)
    worklist = build_worklist(conn)
    if sources is None:
        sources = {name: SOURCE_CLASSES[name](db.connect(db_path))
                   for name in worklist}
    totals = {name: len(worklist[name]) for name in worklist}
    prog = HarvestProgress(conn, totals)
    # prog.lock, not a second Lock of our own: it guards `conn`, and prog
    # writes run_status to that same connection from these same threads.
    # Two locks would each exclude only their own callers, which is not
    # mutual exclusion -- see HarvestProgress's docstring.
    incomplete, lock = set(), prog.lock
    threads, ran = [], []
    for name, titles in worklist.items():
        src = sources.get(name)
        if src is None:
            continue
        if not ignore_quota and (resets_at := quota.blocked(conn, name)):
            # Cache-only, not skipped: the walk is what keeps the progress
            # number true, so a 90%-cached source still reports 90% rather
            # than appearing to go backwards between runs. It costs one
            # indexed cache lookup per title and no requests at all.
            src.offline = True
            incomplete.add(name)
            prog.log(f"  {name}: quota still spent - serving from cache only "
                     f"until {_when(resets_at)}")
        t = threading.Thread(target=_run_pool,
                             args=(name, src, titles, prog, incomplete, lock,
                                   conn),
                             name=f"harvest-{name}")
        t.start()
        threads.append(t)
        # A source in the worklist with no entry in `sources` continued
        # above, so it gets no row: it did not run, and a zero row would
        # read as if it had.
        ran.append(name)
    for t in threads:
        t.join()
    # Read back rather than tracking in memory: this catches both a source
    # blocked before the threads started and one blocked by its own first
    # 429 during the run. They are the same condition.
    paused = {name: _when(resets_at) for name in worklist
              if (resets_at := quota.blocked(conn, name))}
    runs.record(conn, started.isoformat(),
                datetime.now(timezone.utc).isoformat(),
                _tally(conn, prog, started, ran))
    prog.finish(incomplete, paused=paused, repeats=_repeat_lines(conn))
    if _conn is None:
        conn.close()
    return incomplete

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
