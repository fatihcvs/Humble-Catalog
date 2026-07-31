import io
import threading
from humble_catalog import db, failures
from humble_catalog.progress import HarvestProgress

def test_connect_enables_wal_for_file_db(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"

def test_two_threads_can_write_source_cache(tmp_path):
    path = tmp_path / "t.db"
    db.connect(path).close()  # create schema
    errors = []

    def writer(source):
        try:
            c = db.connect(path)
            for i in range(20):
                c.execute(
                    "INSERT OR REPLACE INTO source_cache (source, query, fetched_at, json) "
                    "VALUES (?,?,?,?)", (source, f"q{i}", "2026-01-01", "{}"))
                c.commit()
            c.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(s,))
               for s in ("hardcover", "google_books", "comicvine")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    conn = db.connect(path)
    assert conn.execute("SELECT count(*) FROM source_cache").fetchone()[0] == 60

# The test above is the pattern for source data: a connection per thread,
# and WAL lets them write at once. The harvest's *progress* writes take the
# opposite arrangement on purpose -- one shared connection, serialized by a
# lock -- so they need their own contract, which is what follows.

WRITES = 400  # enough to lose the race reliably when the lock is not shared

def test_harvest_progress_writes_under_the_caller_s_lock(tmp_path):
    """One connection, ONE lock -- the harvest's actual arrangement.

    _run_pool writes source_failure and source_quota to the caller's
    connection under `lock`, while HarvestProgress writes run_status to
    that same connection from those same worker threads. Both groups have
    to hold the same lock, or there is no mutual exclusion at all.

    HarvestProgress used to guard its own writes with a private lock, so
    the two groups excluded their own kind and not each other. A shared
    connection is not thread-safe just because check_same_thread=False
    lets you use it from two threads -- that flag removes Python's guard,
    it does not add synchronization. Concurrent execute/commit corrupts
    the sqlite3 module's own state, and it surfaced as any of
    "cannot commit - no transaction is active" (commit() checks
    sqlite3_get_autocommit and then issues COMMIT, and the other thread
    commits in between), "bad parameter or other API misuse", or a bare
    SystemError with no exception set.

    Driven through the real methods rather than raw SQL, because the bug
    was in which lock they took, not in what they wrote.
    """
    conn = db.connect(tmp_path / "t.db")
    prog = HarvestProgress(conn, {"google_books": WRITES},
                           stream=io.StringIO())
    errors = []

    def ticker():
        try:
            for _ in range(WRITES):
                prog.tick("google_books")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"tick: {type(exc).__name__}: {exc}")

    def recorder():
        # Exactly what _run_pool does with the caller's connection: take
        # the shared lock, write, commit.
        try:
            for i in range(WRITES):
                with prog.lock:
                    failures.record(conn, "google_books", f"title {i}", "503")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"record: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=ticker), threading.Thread(target=recorder)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # And both writers' work actually landed.
    assert conn.execute(
        "SELECT done FROM run_status WHERE command='harvest'"
    ).fetchone()[0] == WRITES
    assert conn.execute(
        "SELECT count(*) FROM source_failure").fetchone()[0] == WRITES
