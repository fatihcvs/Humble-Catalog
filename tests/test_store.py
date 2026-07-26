import json
from pathlib import Path
from humble_catalog import db
from humble_catalog.store import store_order

FIXTURE = Path(__file__).parent / "fixtures" / "order_book.json"

def _raw():
    return json.loads(FIXTURE.read_text())

def test_store_creates_rows(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    store_order(conn, _raw())
    item = conn.execute("SELECT * FROM items").fetchone()
    assert item["name"] == "All Systems Red"
    assert conn.execute("SELECT status FROM enrichment WHERE item_id=?",
                        (item["id"],)).fetchone()["status"] == "pending"
    dl = conn.execute("SELECT * FROM downloads WHERE item_id=?", (item["id"],)).fetchone()
    assert dl["kind"] == "humble" and dl["formats"] == "epub,pdf"
    assert dl["url"] == "https://www.humblebundle.com/downloads?key=abc123"
    assert conn.execute("SELECT COUNT(*) c FROM external_keys").fetchone()["c"] == 1

def test_rerun_preserves_user_data(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    store_order(conn, _raw())
    conn.execute("UPDATE items SET my_rating=4, type='comic', type_overridden=1")
    conn.execute("UPDATE enrichment SET status='manually_fixed', genre='SF'")
    store_order(conn, _raw())  # re-run
    item = conn.execute("SELECT * FROM items").fetchone()
    assert (item["my_rating"], item["type"], item["type_overridden"]) == (4, "comic", 1)
    enr = conn.execute("SELECT * FROM enrichment").fetchone()
    assert (enr["status"], enr["genre"]) == ("manually_fixed", "SF")
    assert conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM item_bundles").fetchone()["c"] == 1

def test_rerun_updates_type_when_not_overridden(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    store_order(conn, _raw())
    # simulate an item stored under an old, wrong classification
    conn.execute("UPDATE items SET type='audiobook' WHERE type_overridden=0")
    conn.commit()
    store_order(conn, _raw())  # re-store from cache must re-classify
    assert conn.execute("SELECT type FROM items").fetchone()["type"] == "ebook"

def test_comic_evidence_is_sticky_across_bundles(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    comic_bundle = _raw()
    comic_bundle["product"]["human_name"] = "Humble Comics Bundle: Shadow Hound"
    store_order(conn, comic_bundle)
    assert conn.execute("SELECT type FROM items").fetchone()["type"] == "comic"
    generic_bundle = _raw()  # same item, bundle name reveals nothing
    generic_bundle["gamekey"] = "def456"
    store_order(conn, generic_bundle)
    # the generically-named bundle must not demote the comic to ebook
    assert conn.execute("SELECT type FROM items").fetchone()["type"] == "comic"

def test_same_item_in_two_bundles(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    store_order(conn, _raw())
    second = _raw()
    second["gamekey"] = "def456"
    second["product"]["human_name"] = "Humble Book Bundle: Second"
    store_order(conn, second)
    assert conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM item_bundles").fetchone()["c"] == 2

def test_store_restores_preserved_user_data_on_insert(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute(
        "INSERT INTO user_item_data "
        "(machine_name, my_rating, user_tags, user_comment) "
        "VALUES ('allsystemsred_ebook', 5, '[\"to reread\"]', 'Gift.')")
    conn.commit()
    store_order(conn, _raw())
    item = conn.execute(
        "SELECT my_rating, user_tags, user_comment FROM items").fetchone()
    assert item["my_rating"] == 5
    assert item["user_tags"] == '["to reread"]'
    assert item["user_comment"] == "Gift."


def test_store_does_not_restore_over_an_existing_item(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    store_order(conn, _raw())
    conn.execute("UPDATE items SET my_rating=2")
    conn.execute("INSERT INTO user_item_data (machine_name, my_rating) "
                 "VALUES ('allsystemsred_ebook', 5)")  # stale snapshot
    conn.commit()
    store_order(conn, _raw())  # item exists -> update branch, no restore
    assert conn.execute("SELECT my_rating FROM items").fetchone()["my_rating"] == 2


def test_store_without_snapshot_leaves_user_fields_null(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    store_order(conn, _raw())  # empty user_item_data -> nothing restored
    item = conn.execute(
        "SELECT my_rating, user_tags, user_comment FROM items").fetchone()
    assert (item["my_rating"], item["user_tags"], item["user_comment"]) \
        == (None, None, None)


def test_tombstoned_item_relinks_instead_of_resurrecting(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    # survivor exists; the fixture's machine_name was merged into it earlier
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, type) VALUES ('kept','Book','ebook')")
    kept_id = cur.lastrowid
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (kept_id,))
    conn.execute("INSERT INTO merges VALUES ('allsystemsred_ebook', ?)", (kept_id,))
    conn.commit()
    store_order(conn, _raw())
    # no new item row; bundle linked to the survivor; no orphan downloads
    assert conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 1
    links = conn.execute("SELECT COUNT(*) c FROM item_bundles WHERE item_id=?",
                         (kept_id,)).fetchone()["c"]
    assert links == 1
    assert conn.execute("SELECT COUNT(*) c FROM downloads").fetchone()["c"] == 0
