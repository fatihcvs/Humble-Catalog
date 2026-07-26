import threading
from humble_catalog import db
from humble_catalog.enrich import SOURCE_ORDER, SOURCE_CLASSES
from humble_catalog.progress import HarvestProgress
from humble_catalog.sources.base import CacheMiss
from humble_catalog.titles import clean_title

SKIP_TYPES = ("music", "android")

def build_worklist(conn):
    """Map each source name to the de-duplicated cleaned titles it must fetch.

    Every non-music/android item contributes its cleaned title to each
    source in SOURCE_ORDER for its type. Titles are de-duped per source so
    two items with the same cleaned title cost one request, and order is
    preserved for stable, resumable progress.
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
    return {name: titles for name, titles in worklist.items() if titles}

def _is_429(exc):
    resp = getattr(exc, "response", None)
    return resp is not None and getattr(resp, "status_code", None) == 429

def _run_pool(name, src, titles, prog, incomplete, lock):
    """Walk one source's titles, ticking only the ones it actually got.

    A 429 ends the source's *network*, not its cache, so the quota dying
    switches the source offline and the walk continues: titles an earlier
    run already fetched still cost nothing and still count. Stopping
    outright instead would strand every cached title below the first
    uncached one, and a source whose first gap sits near the top of the
    list would show the same handful of steps on every rerun.
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
            prog.log(f"  {name}: rate limit hit - serving the rest from cache; "
                     f"rerun 'harvest' later to fetch the remainder")
            continue
        prog.tick(name)
    prog.settle(name, failed=failed)

def run(db_path="catalog.db", sources=None, _conn=None):
    """Fetch every relevant source for every eligible item into source_cache.

    One thread per source; each owns its Source (and, when live, its own
    db connection). Returns the set of sources left incomplete.
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
        t = threading.Thread(target=_run_pool,
                             args=(name, src, titles, prog, incomplete, lock),
                             name=f"harvest-{name}")
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    prog.finish(incomplete)
    if _conn is None:
        conn.close()
    return incomplete
