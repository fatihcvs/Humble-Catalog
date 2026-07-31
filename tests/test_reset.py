from humble_catalog import db, reset
from humble_catalog.store import store_order


def _seed(conn):
    conn.execute("INSERT INTO bundles VALUES ('k','B','http://b',NULL)")
    conn.execute("INSERT INTO raw_orders (gamekey, fetched_at, json) "
                 "VALUES ('k','2021-01-01T00:00:00','{}')")
    conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                 "VALUES ('hardcover','q','2021-01-01T00:00:00','{}')")
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, my_rating, user_tags, "
        "user_comment) VALUES ('cooltower_android','Cool Tower Defense',5,?,?)",
        (db.tags_to_json(["to reread"]), "Gift."))
    item_id = cur.lastrowid
    conn.execute("INSERT INTO enrichment (item_id, status) VALUES (?, 'matched')",
                 (item_id,))
    conn.execute("INSERT INTO item_bundles VALUES (?, 'k')", (item_id,))
    conn.execute("INSERT INTO downloads (item_id, kind, url, formats) "
                 "VALUES (?, 'humble', 'http://d', 'epub')", (item_id,))
    conn.commit()
    return item_id


class _NoTTY:
    def isatty(self):
        return False


def test_reset_wipes_derived_but_preserves_caches(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)
    reset.run(_conn=conn, _input=lambda prompt: "RESET")
    for table in ("items", "bundles", "item_bundles", "downloads", "enrichment"):
        assert conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM raw_orders").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM source_cache").fetchone()["c"] == 1


def test_reset_snapshots_user_data(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)
    reset.run(_conn=conn, _input=lambda prompt: "RESET")
    row = conn.execute("SELECT * FROM user_item_data "
                       "WHERE machine_name='cooltower_android'").fetchone()
    assert row["my_rating"] == 5
    assert row["user_tags"] == db.tags_to_json(["to reread"])
    assert row["user_comment"] == "Gift."


def test_reset_roundtrip_restores_user_data(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)
    reset.run(_conn=conn, _input=lambda prompt: "RESET")
    raw = {"gamekey": "k", "product": {"human_name": "B"},
           "subproducts": [{"machine_name": "cooltower_android",
                            "human_name": "Cool Tower Defense",
                            "downloads": [{"platform": "android",
                                           "download_struct": [{"name": "APK"}]}]}]}
    store_order(conn, raw)
    item = conn.execute("SELECT my_rating, user_comment FROM items").fetchone()
    assert item["my_rating"] == 5 and item["user_comment"] == "Gift."


_REBUILD_ORDER = {
    "gamekey": "k", "product": {"human_name": "B"},
    "subproducts": [{"machine_name": "cooltower_android",
                     "human_name": "Cool Tower Defense",
                     "downloads": [{"platform": "android",
                                    "download_struct": [{"name": "APK"}]}]}]}


def test_read_status_survives_reset_and_rebuild(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    conn.execute("UPDATE items SET read_status='reading' WHERE id=?", (item_id,))
    conn.commit()
    reset.run(_conn=conn, _input=lambda prompt: "RESET")
    assert conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 0
    store_order(conn, _REBUILD_ORDER)
    restored = conn.execute("SELECT read_status FROM items "
                            "WHERE machine_name='cooltower_android'").fetchone()
    assert restored["read_status"] == "reading"


def test_default_unread_round_trips_through_reset(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)   # read_status left at its 'unread' default
    reset.run(_conn=conn, _input=lambda prompt: "RESET")
    store_order(conn, _REBUILD_ORDER)
    statuses = {r["read_status"] for r in conn.execute("SELECT read_status FROM items")}
    assert statuses == {"unread"}


def test_reset_cleared_value_does_not_resurrect(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn)
    conn.execute("INSERT INTO user_item_data (machine_name, my_rating) "
                 "VALUES ('cooltower_android', 3)")   # stale snapshot
    conn.execute("UPDATE items SET my_rating=NULL WHERE id=?", (item_id,))
    conn.commit()
    reset.run(_conn=conn, _input=lambda prompt: "RESET")
    row = conn.execute("SELECT my_rating FROM user_item_data "
                       "WHERE machine_name='cooltower_android'").fetchone()
    # the row survives (tags/comment are non-null) but the cleared rating is gone
    assert row is not None and row["my_rating"] is None


def test_reset_aborts_on_wrong_word(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)
    reset.run(_conn=conn, _input=lambda prompt: "nope")
    assert conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 1


def test_reset_aborts_cleanly_on_eof(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)

    def _eof(prompt):
        raise EOFError   # e.g. Ctrl-D at the prompt

    assert reset.run(_conn=conn, _input=_eof) == 0
    assert conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 1
    assert "Aborted" in capsys.readouterr().out


def test_reset_refuses_without_a_tty(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn)
    monkeypatch.setattr("sys.stdin", _NoTTY())
    reset.run(_conn=conn)   # no _input -> hits the isatty guard
    assert conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 1

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
