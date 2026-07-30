import threading
from datetime import datetime, timezone
from humble_catalog import db, quota
from humble_catalog.enrich import SOURCE_ORDER, SOURCE_CLASSES
from humble_catalog.progress import HarvestProgress, duration
from humble_catalog.sources.base import CacheMiss
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
            with lock:
                incomplete.add(name)
            if not _is_429(exc):
                prog.log(f"  {name} failed for '{title}': {exc}")
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
    conn = _conn or db.connect(db_path)
    worklist = build_worklist(conn)
    if sources is None:
        sources = {name: SOURCE_CLASSES[name](db.connect(db_path))
                   for name in worklist}
    totals = {name: len(worklist[name]) for name in worklist}
    prog = HarvestProgress(conn, totals)
    incomplete, lock = set(), threading.Lock()
    threads = []
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
    for t in threads:
        t.join()
    # Read back rather than tracking in memory: this catches both a source
    # blocked before the threads started and one blocked by its own first
    # 429 during the run. They are the same condition.
    paused = {name: _when(resets_at) for name in worklist
              if (resets_at := quota.blocked(conn, name))}
    prog.finish(incomplete, paused=paused)
    if _conn is None:
        conn.close()
    return incomplete
