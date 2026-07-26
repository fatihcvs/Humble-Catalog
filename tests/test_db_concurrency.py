import threading
from humble_catalog import db

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
