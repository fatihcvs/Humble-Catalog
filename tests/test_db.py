import json
import sqlite3

import pytest

from humble_catalog import db

EXPECTED = {"bundles", "items", "item_bundles", "downloads", "external_keys",
            "enrichment", "raw_orders", "source_cache", "run_status"}

def test_connect_creates_schema(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED <= names

def test_user_item_data_table_exists_with_columns(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "user_item_data" in names
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(user_item_data)")}
    assert cols == {"machine_name", "my_rating", "user_tags", "user_comment",
                    "read_status"}


def test_migration_adds_source_url_to_legacy_db(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE enrichment (item_id INTEGER PRIMARY KEY, "
                   "genre TEXT, status TEXT NOT NULL DEFAULT 'pending')")
    legacy.commit()
    legacy.close()
    conn = db.connect(path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(enrichment)")}
    assert "source_url" in cols

def test_migration_adds_pre_edit_to_legacy_db(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE enrichment (item_id INTEGER PRIMARY KEY, "
                   "genre TEXT, status TEXT NOT NULL DEFAULT 'pending')")
    legacy.commit()
    legacy.close()
    conn = db.connect(path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(enrichment)")}
    assert "pre_edit" in cols

def test_connect_is_idempotent(tmp_path):
    db.connect(tmp_path / "t.db").close()
    conn = db.connect(tmp_path / "t.db")  # second open must not fail
    conn.execute("INSERT INTO bundles VALUES ('k', 'n', 'u', NULL)")
    assert conn.execute("SELECT COUNT(*) c FROM bundles").fetchone()["c"] == 1

def test_fetch_items_flattens(tmp_path):
    conn = db.connect(tmp_path / "f.db")
    conn.execute("INSERT INTO bundles VALUES ('k1','Book Bundle','http://b1','2020-01-05T12:00:00')")
    conn.execute("INSERT INTO bundles VALUES ('k2','Comic Bundle','http://b2','2019-03-02T08:00:00')")
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, type, publisher, my_rating) "
        "VALUES ('asr','All Systems Red','ebook','Tor',5)")
    item_id = cur.lastrowid
    conn.execute("INSERT INTO item_bundles VALUES (?, 'k1')", (item_id,))
    conn.execute("INSERT INTO item_bundles VALUES (?, 'k2')", (item_id,))
    conn.execute("INSERT INTO downloads (item_id, kind, url, formats) "
                 "VALUES (?, 'humble', 'http://d1', 'epub,pdf')", (item_id,))
    conn.execute("INSERT INTO downloads (item_id, kind, url, formats) "
                 "VALUES (?, 'humble', 'http://d2', 'mobi,epub')", (item_id,))
    conn.execute(
        "INSERT INTO enrichment (item_id, genre, authors, status) "
        "VALUES (?, '[\"SF\"]', '[\"Martha Wells\"]', 'auto')", (item_id,))
    conn.commit()

    items = db.fetch_items(conn)
    assert len(items) == 1
    item = items[0]
    assert item["name"] == "All Systems Red"
    assert item["genre"] == ["SF"] and item["my_rating"] == 5
    assert item["edited"] is False and "pre_edit" not in item
    assert item["formats"] == ["epub", "mobi", "pdf"]
    # bundle order follows purchased_at, oldest first
    assert [b["name"] for b in item["bundles"]] == ["Comic Bundle", "Book Bundle"]

def test_migration_converts_tag_strings_to_arrays(tmp_path):
    import json
    path = tmp_path / "legacy.db"
    conn = db.connect(path)
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('m','N')")
    conn.execute(
        "INSERT INTO enrichment (item_id, genre, authors, narrator, pre_edit) "
        "VALUES (1, 'SF, Horror', 'Ann Leckie', NULL, "
        "'{\"genre\": \"Old, Genre\", \"series\": \"Keep, Me\"}')")
    conn.execute("PRAGMA user_version = 0")  # pretend this is a v1.4 file
    conn.commit()
    conn.close()

    conn = db.connect(path)  # reconnect triggers the migration
    row = conn.execute("SELECT * FROM enrichment").fetchone()
    assert json.loads(row["genre"]) == ["SF", "Horror"]
    assert json.loads(row["authors"]) == ["Ann Leckie"]
    assert row["narrator"] is None
    snap = json.loads(row["pre_edit"])
    assert json.loads(snap["genre"]) == ["Old", "Genre"]
    assert snap["series"] == "Keep, Me"  # single-value fields never split
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12

def test_migration_leaves_arrays_and_new_dbs_alone(tmp_path):
    import json
    path = tmp_path / "t.db"
    conn = db.connect(path)  # fresh DB: user_version already stamped current
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('m','N')")
    conn.execute("INSERT INTO enrichment (item_id, genre) VALUES (1, '[\"SF, Cozy\"]')")
    conn.commit()
    conn.close()
    conn = db.connect(path)  # reconnect must not re-split inside the array
    assert json.loads(conn.execute(
        "SELECT genre FROM enrichment").fetchone()["genre"]) == ["SF, Cozy"]

def test_tags_to_json_normalizes():
    assert db.tags_to_json(["Fantasy", " Horror ", "", "Fantasy"]) == '["Fantasy", "Horror"]'
    assert db.tags_to_json("Martha Wells") == '["Martha Wells"]'  # single string wraps
    assert db.tags_to_json([]) is None
    assert db.tags_to_json(["   "]) is None
    assert db.tags_to_json(None) is None
    assert db.tags_to_json("") is None

def test_tags_from_json():
    assert db.tags_from_json('["A", "B"]') == ["A", "B"]
    assert db.tags_from_json(None) == []
    assert db.tags_from_json("") == []

def test_titleize():
    assert db.titleize("science fiction") == "Science Fiction"
    assert db.titleize("RPG") == "RPG"                    # acronyms survive
    assert db.titleize("post-apocalyptic") == "Post-apocalyptic"
    assert db.titleize("fantasy") == "Fantasy"

def test_normalize_genre_tags_snaps_and_titleizes(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('m','N')")
    conn.execute("INSERT INTO enrichment (item_id, genre) VALUES (1, ?)",
                 (db.tags_to_json(["Science Fiction", "RPG"]),))
    conn.commit()
    # snap to existing spelling, titleize the new, dedupe case-insensitively
    assert db.normalize_tags(conn, db.GENRE, ["science fiction", "rpg",
                                          "cozy mystery", "Cozy Mystery"]) \
        == ["Science Fiction", "RPG", "Cozy Mystery"]
    assert db.normalize_tags(conn, db.GENRE, "science fiction") == ["Science Fiction"]
    assert db.normalize_tags(conn, db.GENRE, None) == []
    assert db.normalize_tags(conn, db.GENRE, ["  ", ""]) == []

def test_migration_collapses_genre_case_variants(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    for n, genre in enumerate((["fiction"], ["Fiction"], ["Fiction"],
                               ["science fiction", "fantasy"])):
        conn.execute("INSERT INTO items (machine_name, name) VALUES (?, ?)",
                     (f"m{n}", f"N{n}"))
        conn.execute("INSERT INTO enrichment (item_id, genre) VALUES (?, ?)",
                     (n + 1, db.tags_to_json(genre)))
    # a pre_edit snapshot holding a variant must be rewritten too
    conn.execute("UPDATE enrichment SET pre_edit=? WHERE item_id=1",
                 (json.dumps({"genre": db.tags_to_json(["FICTION"])}),))
    conn.execute("PRAGMA user_version = 1")   # pretend this is a v1.8 file
    conn.commit()
    conn.close()

    conn = db.connect(path)                   # reconnect triggers migration
    genres = [db.tags_from_json(r["genre"]) for r in conn.execute(
        "SELECT genre FROM enrichment ORDER BY item_id")]
    # most frequent spelling wins (Fiction x2 beats fiction x1);
    # unique tags get titleized
    assert genres == [["Fiction"], ["Fiction"], ["Fiction"],
                      ["Science Fiction", "Fantasy"]]
    snap = json.loads(conn.execute(
        "SELECT pre_edit FROM enrichment WHERE item_id=1").fetchone()["pre_edit"])
    assert db.tags_from_json(snap["genre"]) == ["Fiction"]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12

def test_migration_genre_case_tie_prefers_titleized(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    for n, genre in enumerate((["cozy mystery"], ["Cozy Mystery"])):
        conn.execute("INSERT INTO items (machine_name, name) VALUES (?, ?)",
                     (f"m{n}", f"N{n}"))
        conn.execute("INSERT INTO enrichment (item_id, genre) VALUES (?, ?)",
                     (n + 1, db.tags_to_json(genre)))
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    conn = db.connect(path)
    genres = {db.tags_from_json(r["genre"])[0] for r in conn.execute(
        "SELECT genre FROM enrichment")}
    assert genres == {"Cozy Mystery"}         # 1-1 tie -> titleized form

def _seed_item(conn, name="Book A", genre=None):
    conn.execute("INSERT INTO items (machine_name, name) VALUES (?, ?)",
                 (name.lower().replace(" ", "_"), name))
    item_id = conn.execute("SELECT id FROM items WHERE name=?", (name,)).fetchone()["id"]
    conn.execute("INSERT INTO enrichment (item_id, genre) VALUES (?, ?)",
                 (item_id, genre))
    conn.commit()
    return item_id

def test_apply_hand_edit_snapshots_once(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_item(conn, genre=db.tags_to_json(["Fantasy"]))
    assert db.apply_hand_edit(conn, item_id, {"series": "Circle of Storms"}) is True
    row = conn.execute("SELECT * FROM enrichment WHERE item_id=?", (item_id,)).fetchone()
    assert row["series"] == "Circle of Storms"
    snap = json.loads(row["pre_edit"])
    assert snap["series"] is None and snap["genre"] == db.tags_to_json(["Fantasy"])
    # second edit must not re-snapshot
    db.apply_hand_edit(conn, item_id, {"series": "Changed"})
    assert json.loads(conn.execute(
        "SELECT pre_edit FROM enrichment WHERE item_id=?",
        (item_id,)).fetchone()["pre_edit"])["series"] is None

def test_apply_hand_edit_missing_item_returns_false(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert db.apply_hand_edit(conn, 999, {"series": "X"}) is False

def _seed_full(conn, machine_name, name, *, bundle=None, genre=None,
               series=None, rating=None, publisher=None):
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, my_rating, publisher) "
        "VALUES (?,?,?,?)", (machine_name, name, rating, publisher))
    item_id = cur.lastrowid
    conn.execute("INSERT INTO enrichment (item_id, genre, series) VALUES (?,?,?)",
                 (item_id, genre, series))
    if bundle:
        conn.execute("INSERT OR IGNORE INTO bundles VALUES (?,?,?,NULL)",
                     (bundle, bundle, "http://" + bundle))
        conn.execute("INSERT INTO item_bundles VALUES (?,?)", (item_id, bundle))
        conn.execute("INSERT INTO downloads (item_id, kind, url, formats) "
                     "VALUES (?,?,?,?)", (item_id, "humble", "http://" + bundle, "epub"))
    conn.commit()
    return item_id

def test_merge_items_unions_and_gap_fills(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    keep = _seed_full(conn, "k", "Book, 2nd Edition", bundle="b1",
                      genre=db.tags_to_json(["Tech"]), rating=4)
    drop = _seed_full(conn, "d", "Book 2e", bundle="b2",
                      genre=db.tags_to_json(["Programming"]),
                      series="A Series", rating=5, publisher="OReilly")
    assert db.merge_items(conn, keep, drop) is True
    # bundles + downloads moved
    links = {r["gamekey"] for r in conn.execute(
        "SELECT gamekey FROM item_bundles WHERE item_id=?", (keep,))}
    assert links == {"b1", "b2"}
    dls = conn.execute("SELECT COUNT(*) c FROM downloads WHERE item_id=?",
                       (keep,)).fetchone()["c"]
    assert dls == 2
    # gap-fill: empty fields filled, non-empty kept
    row = conn.execute(
        "SELECT i.my_rating, i.publisher, e.genre, e.series FROM items i "
        "JOIN enrichment e ON e.item_id=i.id WHERE i.id=?", (keep,)).fetchone()
    assert row["my_rating"] == 4                       # survivor's kept
    assert row["publisher"] == "OReilly"               # gap filled
    assert db.tags_from_json(row["genre"]) == ["Tech"] # non-empty array kept
    assert row["series"] == "A Series"                 # gap filled
    # tombstone written; dropped row fully gone
    tomb = conn.execute("SELECT kept_item_id FROM merges "
                        "WHERE dropped_machine_name='d'").fetchone()
    assert tomb["kept_item_id"] == keep
    assert conn.execute("SELECT COUNT(*) c FROM items WHERE id=?",
                        (drop,)).fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM enrichment WHERE item_id=?",
                        (drop,)).fetchone()["c"] == 0

def test_merge_items_shared_bundle_no_conflict(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    keep = _seed_full(conn, "k", "Book", bundle="b1")
    drop = _seed_full(conn, "d", "Book", bundle="b1")   # SAME bundle
    assert db.merge_items(conn, keep, drop) is True
    assert conn.execute("SELECT COUNT(*) c FROM item_bundles WHERE item_id=?",
                        (keep,)).fetchone()["c"] == 1

def test_merge_items_bad_ids_change_nothing(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    keep = _seed_full(conn, "k", "Book")
    assert db.merge_items(conn, keep, 999) is False
    assert db.merge_items(conn, keep, keep) is False
    assert conn.execute("SELECT COUNT(*) c FROM merges").fetchone()["c"] == 0

def _seed_genres(tmp_path, rows):
    """rows: (machine_name, genre_json_or_None, pre_edit_json_or_None)."""
    conn = db.connect(tmp_path / "g.db")
    for idx, (mn, genre, pre) in enumerate(rows, 1):
        conn.execute("INSERT INTO items (machine_name, name) VALUES (?,?)",
                     (mn, mn))
        conn.execute("INSERT INTO enrichment (item_id, genre, pre_edit) "
                     "VALUES (?,?,?)", (idx, genre, pre))
    conn.commit()
    return conn

def test_rename_genre_tag_across_items(tmp_path):
    conn = _seed_genres(tmp_path, [
        ("a", '["Fantasy", "Adventure"]', None),
        ("b", '["Fantasy"]', None),
        ("c", '["Horror"]', None)])
    assert db.rename_tag(conn, db.GENRE, "Fantasy", "Epic Fantasy") == 2
    rows = conn.execute(
        "SELECT genre, pre_edit FROM enrichment ORDER BY item_id").fetchall()
    assert json.loads(rows[0]["genre"]) == ["Epic Fantasy", "Adventure"]
    assert json.loads(rows[1]["genre"]) == ["Epic Fantasy"]
    assert json.loads(rows[2]["genre"]) == ["Horror"]
    # a vocabulary rename is not a hand-edit: no snapshots appear
    assert all(r["pre_edit"] is None for r in rows)

def test_rename_genre_tag_merges_and_dedupes(tmp_path):
    conn = _seed_genres(tmp_path, [("a", '["Fantasy", "Epic Fantasy"]', None)])
    assert db.rename_tag(conn, db.GENRE, "Fantasy", "Epic Fantasy") == 1
    assert json.loads(conn.execute(
        "SELECT genre FROM enrichment").fetchone()["genre"]) == ["Epic Fantasy"]

def test_rename_genre_tag_matches_old_case_insensitively(tmp_path):
    conn = _seed_genres(tmp_path, [("a", '["fantasy"]', None)])
    assert db.rename_tag(conn, db.GENRE, "FANTASY", "epic fantasy") == 1
    # new spelling is titleized like any other new genre input
    assert json.loads(conn.execute(
        "SELECT genre FROM enrichment").fetchone()["genre"]) == ["Epic Fantasy"]

def test_rename_genre_tag_snaps_new_to_existing_spelling(tmp_path):
    conn = _seed_genres(tmp_path, [
        ("a", '["Sci-fi"]', None), ("b", '["Fantasy"]', None)])
    assert db.rename_tag(conn, db.GENRE, "Fantasy", "sci-fi") == 1
    assert json.loads(conn.execute(
        "SELECT genre FROM enrichment WHERE item_id=2").fetchone()["genre"]) \
        == ["Sci-fi"]

def test_rename_genre_tag_rewrites_pre_edit_snapshots(tmp_path):
    pre = json.dumps({"genre": '["Fantasy"]', "series": "Keep Me"})
    conn = _seed_genres(tmp_path, [("a", '["Fantasy"]', pre)])
    assert db.rename_tag(conn, db.GENRE, "Fantasy", "Epic Fantasy") == 1
    row = conn.execute("SELECT genre, pre_edit FROM enrichment").fetchone()
    assert json.loads(row["genre"]) == ["Epic Fantasy"]
    snap = json.loads(row["pre_edit"])  # still edited: snapshot kept, rewritten
    assert json.loads(snap["genre"]) == ["Epic Fantasy"]
    assert snap["series"] == "Keep Me"  # other snapshot fields untouched

def test_rename_genre_tag_unknown_or_blank_returns_none(tmp_path):
    conn = _seed_genres(tmp_path, [("a", '["Fantasy"]', None)])
    assert db.rename_tag(conn, db.GENRE, "Cooking", "Food") is None
    assert db.rename_tag(conn, db.GENRE, "", "Food") is None
    assert db.rename_tag(conn, db.GENRE, "Fantasy", "  ") is None
    assert json.loads(conn.execute(
        "SELECT genre FROM enrichment").fetchone()["genre"]) == ["Fantasy"]

def test_delete_genre_tag(tmp_path):
    pre = json.dumps({"genre": '["Fantasy", "Adventure"]'})
    conn = _seed_genres(tmp_path, [
        ("a", '["Fantasy"]', None),          # empties -> NULL
        ("b", '["Fantasy", "Horror"]', pre), # shrinks, snapshot rewritten
        ("c", '["Horror"]', None)])          # untouched
    assert db.delete_tag(conn, db.GENRE, "fantasy") == 2  # case-insensitive
    rows = conn.execute(
        "SELECT genre, pre_edit FROM enrichment ORDER BY item_id").fetchall()
    assert rows[0]["genre"] is None
    assert json.loads(rows[1]["genre"]) == ["Horror"]
    assert json.loads(json.loads(rows[1]["pre_edit"])["genre"]) == ["Adventure"]
    assert json.loads(rows[2]["genre"]) == ["Horror"]

def test_delete_genre_tag_unknown_returns_none(tmp_path):
    conn = _seed_genres(tmp_path, [("a", '["Fantasy"]', None)])
    assert db.delete_tag(conn, db.GENRE, "Cooking") is None

def test_user_columns_exist_and_default_null(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('m','N')")
    conn.commit()
    row = conn.execute(
        "SELECT user_tags, user_comment FROM items").fetchone()
    assert row["user_tags"] is None
    assert row["user_comment"] is None

def test_migration_adds_user_columns_to_old_db(tmp_path):
    # A pre-feature database: build items without the new columns, then
    # let connect() migrate it. Data must survive.
    path = tmp_path / "old.db"
    old = sqlite3.connect(str(path))
    old.executescript(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, "
        "machine_name TEXT UNIQUE NOT NULL, name TEXT NOT NULL, "
        "type TEXT NOT NULL DEFAULT 'ebook');"
        "INSERT INTO items (machine_name, name) VALUES ('m','Kept Row');")
    old.commit()
    old.close()
    conn = db.connect(path)
    row = conn.execute("SELECT name, user_tags, user_comment "
                       "FROM items").fetchone()
    assert row["name"] == "Kept Row"
    assert row["user_tags"] is None and row["user_comment"] is None

def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "t.db"
    db.connect(path).close()
    conn = db.connect(path)  # second connect must not raise
    assert conn.execute("SELECT user_tags FROM items").fetchall() == []

def test_user_tags_snap_but_do_not_titleize(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, user_tags) "
                 "VALUES ('m','N',?)", (db.tags_to_json(["to reread"]),))
    conn.commit()
    # snaps to the spelling already stored...
    assert db.normalize_tags(conn, db.USER_TAGS, ["To Reread"]) == ["to reread"]
    # ...but an unknown tag is kept exactly as typed, not titleized
    assert db.normalize_tags(conn, db.USER_TAGS, ["lent out"]) == ["lent out"]
    assert db.normalize_tags(conn, db.USER_TAGS, None) == []

def test_genre_still_titleizes(tmp_path):
    # the two descriptors must genuinely diverge
    conn = db.connect(tmp_path / "t.db")
    assert db.normalize_tags(conn, db.GENRE, ["cozy mystery"]) == ["Cozy Mystery"]

def test_fetch_items_decodes_user_tags(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, user_tags, "
                 "user_comment) VALUES ('m','The Quiet Harbor: A Novel',?,?)",
                 (db.tags_to_json(["to reread", "lent out"]), "Gift from Sam."))
    conn.execute("INSERT INTO enrichment (item_id) VALUES (1)")
    conn.commit()
    item = db.fetch_items(conn)[0]
    assert item["user_tags"] == ["to reread", "lent out"]
    assert item["user_comment"] == "Gift from Sam."

def test_fetch_items_user_tags_empty_is_list(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('m','N')")
    conn.execute("INSERT INTO enrichment (item_id) VALUES (1)")
    conn.commit()
    item = db.fetch_items(conn)[0]
    assert item["user_tags"] == []          # never None
    assert item["user_comment"] is None
    assert item["edited"] is False

def test_user_tag_rename_and_delete_skip_snapshots(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    pre = json.dumps({"genre": '["Fantasy"]'})
    conn.execute("INSERT INTO items (machine_name, name, user_tags) "
                 "VALUES ('m','N',?)", (db.tags_to_json(["to reread"]),))
    conn.execute("INSERT INTO enrichment (item_id, genre, pre_edit) "
                 "VALUES (1,?,?)", ('["Fantasy"]', pre))
    conn.commit()
    assert db.rename_tag(conn, db.USER_TAGS, "to reread", "reread") == 1
    assert json.loads(conn.execute(
        "SELECT user_tags FROM items").fetchone()["user_tags"]) == ["reread"]
    # the genre snapshot is untouched by a user-tag rename
    row = conn.execute("SELECT pre_edit FROM enrichment").fetchone()
    assert json.loads(row["pre_edit"]) == json.loads(pre)
    assert db.delete_tag(conn, db.USER_TAGS, "reread") == 1
    assert conn.execute(
        "SELECT user_tags FROM items").fetchone()["user_tags"] is None

def test_merge_unions_user_tags_and_fills_comment(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for idx, (mn, tags, comment) in enumerate((
            ("keep", ["to reread"], None),
            ("drop", ["lent out", "To Reread"], "Dropped note.")), 1):
        conn.execute("INSERT INTO items (machine_name, name, user_tags, "
                     "user_comment) VALUES (?,?,?,?)",
                     (mn, mn, db.tags_to_json(tags), comment))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (idx,))
    conn.commit()
    assert db.merge_items(conn, 1, 2) is True
    row = conn.execute("SELECT user_tags, user_comment FROM items "
                       "WHERE id=1").fetchone()
    # union, survivor first, case-insensitive dedupe drops "To Reread"
    assert json.loads(row["user_tags"]) == ["to reread", "lent out"]
    assert row["user_comment"] == "Dropped note."   # survivor was empty

def test_merge_keeps_survivor_comment(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for idx, (mn, comment) in enumerate((
            ("keep", "Survivor note."), ("drop", "Dropped note.")), 1):
        conn.execute("INSERT INTO items (machine_name, name, user_comment) "
                     "VALUES (?,?,?)", (mn, mn, comment))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (idx,))
    conn.commit()
    db.merge_items(conn, 1, 2)
    assert conn.execute("SELECT user_comment FROM items WHERE id=1"
                        ).fetchone()["user_comment"] == "Survivor note."

def _seed_user_tags(tmp_path, rows):
    """rows: (machine_name, [user tags])."""
    conn = db.connect(tmp_path / "b.db")
    for idx, (mn, tags) in enumerate(rows, 1):
        conn.execute("INSERT INTO items (machine_name, name, user_tags) "
                     "VALUES (?,?,?)", (mn, mn, db.tags_to_json(tags)))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (idx,))
    conn.commit()
    return conn

def test_bulk_add_appends_and_returns_only_changed_ids(tmp_path):
    conn = _seed_user_tags(tmp_path, [
        ("a", []), ("b", ["lent out"]), ("c", ["to reread"])])
    # c already has it, so only a and b change
    assert db.bulk_user_tag(conn, [1, 2, 3], "to reread", "add") == [1, 2]
    rows = conn.execute("SELECT user_tags FROM items ORDER BY id").fetchall()
    assert json.loads(rows[0]["user_tags"]) == ["to reread"]
    assert json.loads(rows[1]["user_tags"]) == ["lent out", "to reread"]
    assert json.loads(rows[2]["user_tags"]) == ["to reread"]

def test_bulk_add_snaps_to_an_existing_spelling(tmp_path):
    conn = _seed_user_tags(tmp_path, [("a", ["to reread"]), ("b", [])])
    assert db.bulk_user_tag(conn, [1, 2], "To Reread", "add") == [2]
    assert json.loads(conn.execute(
        "SELECT user_tags FROM items WHERE id=2").fetchone()["user_tags"]) \
        == ["to reread"]

def test_bulk_remove_is_case_insensitive_and_empties_to_null(tmp_path):
    conn = _seed_user_tags(tmp_path, [
        ("a", ["to reread"]), ("b", ["lent out", "to reread"]), ("c", [])])
    assert db.bulk_user_tag(conn, [1, 2, 3], "TO REREAD", "remove") == [1, 2]
    rows = conn.execute("SELECT user_tags FROM items ORDER BY id").fetchall()
    assert rows[0]["user_tags"] is None          # emptied -> NULL
    assert json.loads(rows[1]["user_tags"]) == ["lent out"]
    assert rows[2]["user_tags"] is None

def test_bulk_only_touches_the_given_ids(tmp_path):
    conn = _seed_user_tags(tmp_path, [("a", []), ("b", [])])
    assert db.bulk_user_tag(conn, [1], "to reread", "add") == [1]
    assert conn.execute(
        "SELECT user_tags FROM items WHERE id=2").fetchone()["user_tags"] is None

def test_bulk_ignores_unknown_ids(tmp_path):
    conn = _seed_user_tags(tmp_path, [("a", [])])
    assert db.bulk_user_tag(conn, [1, 999], "to reread", "add") == [1]

def test_bulk_never_marks_rows_edited(tmp_path):
    conn = _seed_user_tags(tmp_path, [("a", []), ("b", ["to reread"])])
    db.bulk_user_tag(conn, [1, 2], "to reread", "add")
    db.bulk_user_tag(conn, [1, 2], "to reread", "remove")
    assert all(r["pre_edit"] is None for r in
               conn.execute("SELECT pre_edit FROM enrichment"))

def test_bulk_rejects_an_unknown_action(tmp_path):
    conn = _seed_user_tags(tmp_path, [("a", [])])
    with pytest.raises(ValueError):
        db.bulk_user_tag(conn, [1], "to reread", "replace")

def test_bulk_returns_an_empty_list_when_nothing_changes(tmp_path):
    # An empty list and not None: the caller stores it and asks for
    # .length, and a None here would become an undo button offering to
    # restore nothing.
    conn = _seed_user_tags(tmp_path, [("a", ["to reread"])])
    assert db.bulk_user_tag(conn, [1], "to reread", "add") == []
    assert db.bulk_user_tag(conn, [], "to reread", "add") == []
    assert db.bulk_user_tag(conn, [1], "   ", "add") == []

def test_undoing_a_bulk_remove_restores_only_the_changed_rows(tmp_path):
    # The whole reason the id list is returned: b never carried the tag,
    # so undoing over the ids originally SENT would give it one it never
    # had. Undo goes over the ids that changed.
    conn = _seed_user_tags(tmp_path, [("a", ["lent out"]), ("b", [])])
    changed = db.bulk_user_tag(conn, [1, 2], "lent out", "remove")
    assert changed == [1]
    assert db.bulk_user_tag(conn, changed, "lent out", "add") == [1]
    rows = conn.execute("SELECT user_tags FROM items ORDER BY id").fetchall()
    assert json.loads(rows[0]["user_tags"]) == ["lent out"]
    assert rows[1]["user_tags"] is None

def test_new_db_has_override_columns(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(enrichment)")}
    assert {"hand_edited", "enrich_override"} <= cols

def test_migration_backfills_hand_edited_from_pre_edit(tmp_path):
    # every row that reads as edited today IS a hand edit today, so the
    # backfill must reproduce current behaviour exactly
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE enrichment (item_id INTEGER PRIMARY KEY, "
                   "genre TEXT, status TEXT NOT NULL DEFAULT 'pending', "
                   "pre_edit TEXT)")
    legacy.execute("INSERT INTO enrichment (item_id, pre_edit) VALUES (1, '{}')")
    legacy.execute("INSERT INTO enrichment (item_id, pre_edit) VALUES (2, NULL)")
    legacy.commit()
    legacy.close()
    conn = db.connect(path)
    rows = dict(conn.execute("SELECT item_id, hand_edited FROM enrichment"))
    assert rows == {1: 1, 2: 0}

def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "legacy.db"
    conn = db.connect(path)
    conn.execute("INSERT INTO items (machine_name, name) VALUES ('a', 'A Book')")
    conn.execute("INSERT INTO enrichment (item_id, hand_edited) VALUES (1, 0)")
    conn.commit()
    conn.close()
    # a second connect must not re-run the backfill and re-flag the row
    conn = db.connect(path)
    assert conn.execute(
        "SELECT hand_edited FROM enrichment WHERE item_id=1").fetchone()[0] == 0

def test_apply_hand_edit_marks_the_row_hand_edited(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_item(conn, genre='["Fantasy"]')
    db.apply_hand_edit(conn, item_id, {"series": "Harbor Tales"})
    row = conn.execute("SELECT hand_edited, pre_edit FROM enrichment "
                       "WHERE item_id=?", (item_id,)).fetchone()
    assert row["hand_edited"] == 1
    assert json.loads(row["pre_edit"])["genre"] == '["Fantasy"]'

def test_fetch_items_exposes_the_three_authorship_flags(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_item(conn, genre='["Fantasy"]')
    db.apply_hand_edit(conn, item_id, {"series": "Harbor Tales"})
    item = db.fetch_items(conn)[0]
    assert (item["edited"], item["re_enriched"], item["override"]) == (True, False, False)
    # raw columns must not leak into the payload
    assert "pre_edit" not in item and "hand_edited" not in item

def test_fetch_items_reports_a_re_enriched_row(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_item(conn, genre='["Fantasy"]')
    # the post-override shape: snapshot kept, authorship handed back to enrichment
    conn.execute("UPDATE enrichment SET pre_edit='{}', hand_edited=0 "
                 "WHERE item_id=?", (item_id,))
    conn.commit()
    item = db.fetch_items(conn)[0]
    assert (item["edited"], item["re_enriched"]) == (False, True)


def test_migration_renames_cover_files_to_machine_name_scheme(tmp_path,
                                                              monkeypatch):
    from humble_catalog.covers import cover_filename
    monkeypatch.chdir(tmp_path)
    covers_dir = tmp_path / "covers"
    covers_dir.mkdir()
    path = tmp_path / "legacy.db"
    conn = db.connect(path)
    conn.execute("INSERT INTO items (machine_name, name, cover_url, cover_path) "
                 "VALUES ('cooltower_android','Cool Tower Defense','http://x',"
                 "'covers/1.jpg')")
    conn.execute("PRAGMA user_version = 3")   # pretend this predates the rename
    conn.commit()
    conn.close()
    (covers_dir / "1.jpg").write_bytes(b"\xff\xd8jpg")

    conn = db.connect(path)                   # reconnect triggers the migration
    new_name = cover_filename("cooltower_android")
    assert (covers_dir / new_name).exists()
    assert not (covers_dir / "1.jpg").exists()
    assert conn.execute("SELECT cover_path FROM items").fetchone()["cover_path"] \
        == f"covers/{new_name}"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12


def test_migration_cover_rename_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "t.db"
    db.connect(path).close()   # fresh DB is stamped current version immediately
    conn = db.connect(path)    # second connect must not choke
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12


def test_migrates_v4_db_by_adding_read_status_default_unread(tmp_path):
    path = str(tmp_path / "catalog.db")
    raw = sqlite3.connect(path)        # a v4-shaped DB: no read_status columns
    raw.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, "
        "machine_name TEXT UNIQUE NOT NULL, name TEXT NOT NULL, "
        "type TEXT NOT NULL DEFAULT 'ebook', "
        "type_overridden INTEGER NOT NULL DEFAULT 0, publisher TEXT, "
        "cover_url TEXT, cover_path TEXT, my_rating INTEGER, "
        "user_tags TEXT, user_comment TEXT)")
    raw.execute(
        "CREATE TABLE user_item_data (machine_name TEXT PRIMARY KEY, "
        "my_rating INTEGER, user_tags TEXT, user_comment TEXT)")
    raw.execute("INSERT INTO items (machine_name, name) VALUES ('mn', 'All Systems Red')")
    raw.execute("PRAGMA user_version = 4")
    raw.commit()
    raw.close()

    conn = db.connect(path)            # the 4->5 step ADDs both columns
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    row = conn.execute("SELECT read_status FROM items WHERE machine_name='mn'").fetchone()
    assert row["read_status"] == "unread"
    icols = {r["name"] for r in conn.execute("PRAGMA table_info(user_item_data)")}
    assert "read_status" in icols
    conn.close()


def test_fresh_db_is_stamped_at_the_current_version(tmp_path):
    conn = db.connect(str(tmp_path / "catalog.db"))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    icols = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    assert "read_status" in icols
    conn.close()


def _has_download_index(conn):
    return any(r["name"] == "ix_downloads_item_id"
               for r in conn.execute("PRAGMA index_list(downloads)"))


def test_fresh_db_has_the_downloads_item_id_index(tmp_path):
    # fetch_items looks up formats per item; without this index that scan
    # is O(N) per item, making the whole fetch quadratic
    conn = db.connect(str(tmp_path / "t.db"))
    assert _has_download_index(conn)
    conn.close()


def test_migration_adds_the_downloads_index_to_an_older_db(tmp_path):
    dbp = tmp_path / "t.db"
    conn = db.connect(str(dbp))
    conn.execute("DROP INDEX ix_downloads_item_id")
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()

    conn = db.connect(str(dbp))          # reopening runs _migrate
    assert _has_download_index(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 6
    conn.close()


def test_the_downloads_index_migration_is_idempotent(tmp_path):
    dbp = tmp_path / "t.db"
    for _ in range(3):                   # re-running must not raise
        conn = db.connect(str(dbp))
        conn.close()
    conn = db.connect(str(dbp))
    assert _has_download_index(conn)
    conn.close()

def test_games_tables_exist_on_a_fresh_database(tmp_path):
    conn = db.connect(tmp_path / "catalog.db")
    try:
        names = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"games", "game_imports"} <= names
    finally:
        conn.close()


def test_games_is_keyed_by_store_and_store_id(tmp_path):
    # Re-importing must update a row, never duplicate it.
    conn = db.connect(tmp_path / "catalog.db")
    try:
        for title in ("Widget Quest", "Widget Quest: Definitive Edition"):
            conn.execute(
                "INSERT OR REPLACE INTO games (store, store_id, title, "
                "normalized_title, imported_at) VALUES ('steam','440',?,?,'t')",
                (title, "widget quest"))
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
    finally:
        conn.close()


def test_an_older_database_migrates_to_the_games_tables(tmp_path):
    # A pre-feature database has neither table and a lower user_version.
    path = tmp_path / "catalog.db"
    conn = db.connect(path)
    conn.execute("DROP TABLE games")
    conn.execute("DROP TABLE game_imports")
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    conn.close()

    conn = db.connect(path)
    try:
        names = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"games", "game_imports"} <= names
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 7
    finally:
        conn.close()

def _legacy_cache_row(conn, source, query, fetched_at, payload="{}"):
    conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                 "VALUES (?,?,?,?)", (source, query, fetched_at, payload))

_GB = "https://www.googleapis.com/books/v1/volumes"
_CV = "https://comicvine.gamespot.com/api/search/"

def test_migration_strips_api_keys_out_of_cache_keys(tmp_path):
    # Rows fetched before the key was excluded are still perfectly good
    # responses; rekeying them keeps them reachable instead of making the
    # next harvest refetch everything.
    path = tmp_path / "legacy.db"
    conn = db.connect(path)
    _legacy_cache_row(conn, "google_books",
                      f"{_GB}?key=SECRET&maxResults=5&q=intitle%3A%22Gray+Waters%22",
                      "2026-01-01", '{"items": []}')
    _legacy_cache_row(conn, "comicvine",
                      f"{_CV}?api_key=SECRET&format=json&limit=5&query=Shadow+Hound"
                      "&resources=volume", "2026-01-01")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()

    conn = db.connect(path)
    rows = {r["source"]: r["query"]
            for r in conn.execute("SELECT source, query FROM source_cache")}
    assert rows["google_books"] == f"{_GB}?maxResults=5&q=intitle%3A%22Gray+Waters%22"
    assert rows["comicvine"] == (f"{_CV}?format=json&limit=5&query=Shadow+Hound"
                                 "&resources=volume")
    assert "SECRET" not in "".join(rows.values())

def test_migration_keeps_the_newest_of_two_rows_for_one_rotated_key(tmp_path):
    # The same title fetched under two different keys collapses to one row
    # once the key is gone; the fresher response is the one worth keeping.
    path = tmp_path / "legacy.db"
    conn = db.connect(path)
    q = f"{_GB}?key=%s&maxResults=5&q=intitle%%3A%%22Gray+Waters%%22"
    _legacy_cache_row(conn, "google_books", q % "OLD", "2026-01-01", '{"items": ["old"]}')
    _legacy_cache_row(conn, "google_books", q % "NEW", "2026-06-01", '{"items": ["new"]}')
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()

    conn = db.connect(path)
    rows = conn.execute("SELECT query, json FROM source_cache").fetchall()
    assert len(rows) == 1
    assert "key=" not in rows[0]["query"]
    assert rows[0]["json"] == '{"items": ["new"]}'

def test_migration_leaves_keyless_sources_untouched(tmp_path):
    path = tmp_path / "legacy.db"
    conn = db.connect(path)
    keep = ("https://learning.oreilly.com/api/v2/search/"
            "?formats=book&limit=5&query=Gray+Waters")
    _legacy_cache_row(conn, "oreilly", keep, "2026-01-01")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()

    conn = db.connect(path)
    assert conn.execute("SELECT query FROM source_cache").fetchone()["query"] == keep


def test_migration_9_adds_source_quota_to_an_older_db(tmp_path):
    # Carry-forward only: executescript(SCHEMA) creates the table, so the
    # step exists to record the version. An older database starts with no
    # records, which is exactly "nothing is known to be rate-limited".
    path = str(tmp_path / "catalog.db")
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, "
                "machine_name TEXT, name TEXT)")
    old.execute("PRAGMA user_version = 8")
    old.commit()
    old.close()
    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    assert conn.execute("SELECT COUNT(*) FROM source_quota").fetchone()[0] == 0

def test_migration_10_adds_source_failure(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    conn.execute("PRAGMA user_version = 9")   # pretend this is a pre-10 file
    conn.execute("DROP TABLE source_failure")
    conn.commit()
    conn.close()

    conn = db.connect(path)                   # reconnect triggers the migration
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(source_failure)")}
    assert cols == {"source", "title", "failures",
                    "first_failed_at", "last_failed_at", "last_error"}

def test_migration_11_adds_harvest_run(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    conn.execute("PRAGMA user_version = 10")  # pretend this is a pre-11 file
    conn.execute("DROP TABLE harvest_run")
    conn.commit()
    conn.close()

    conn = db.connect(path)                   # reconnect triggers the migration
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harvest_run)")}
    assert cols == {"started_at", "source", "ended_at", "answered",
                    "succeeded", "failed", "quota_died"}

def test_cached_since_counts_only_rows_at_or_after_the_mark(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for when in ("2026-07-01T00:00:00+00:00", "2026-07-05T00:00:00+00:00"):
        conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                     "VALUES (?,?,?,?)", ("google_books", when, when, "{}"))
    conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                 "VALUES (?,?,?,?)",
                 ("hardcover", "x", "2026-07-05T00:00:00+00:00", "{}"))
    conn.commit()
    assert db.cached_since(conn, "google_books", "2026-07-03T00:00:00+00:00") == 1
    assert db.cached_since(conn, "google_books", "2026-07-01T00:00:00+00:00") == 2
    assert db.cached_since(conn, "google_books", "2026-08-01T00:00:00+00:00") == 0


def _v11_with_old_external_keys(path, rows):
    """A user_version 11 database whose external_keys still has the old
    (gamekey, human_name) primary key. `rows` is [(human_name, raw_json)].
    """
    raw = sqlite3.connect(path)
    raw.executescript(db.SCHEMA)
    raw.executescript("""
        DROP TABLE external_keys;
        CREATE TABLE external_keys (
          gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
          human_name TEXT, key_type TEXT, raw TEXT,
          PRIMARY KEY (gamekey, human_name));
    """)
    raw.execute("INSERT INTO bundles (gamekey, name, url) VALUES "
                "('kv789', 'Humble Game Bundle: Key Vault', "
                "'https://example.invalid/kv789')")
    for human_name, blob in rows:
        raw.execute("INSERT INTO external_keys "
                    "(gamekey, human_name, key_type, raw) "
                    "VALUES ('kv789', ?, 'steam', ?)", (human_name, blob))
    raw.execute("PRAGMA user_version = 11")
    raw.commit()
    raw.close()


def test_migration_rekeys_external_keys_on_machine_name(tmp_path):
    path = tmp_path / "t.db"
    _v11_with_old_external_keys(path, [
        ("Twin Lantern", json.dumps({"machine_name": "twinlantern_steam"}))])
    conn = db.connect(path)
    try:
        row = conn.execute("SELECT gamekey, machine_name, human_name "
                           "FROM external_keys").fetchone()
        assert (row["gamekey"], row["machine_name"]) == \
            ("kv789", "twinlantern_steam")
        assert row["human_name"] == "Twin Lantern"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    finally:
        conn.close()


def test_the_migrated_table_admits_two_stores_of_one_product(tmp_path):
    # The point of the re-key: the old table could not hold both, and the
    # one it kept was whichever Humble listed last.
    path = tmp_path / "t.db"
    _v11_with_old_external_keys(path, [
        ("Twin Lantern", json.dumps({"machine_name": "twinlantern_steam"}))])
    conn = db.connect(path)
    try:
        conn.execute("INSERT INTO external_keys "
                     "(gamekey, machine_name, human_name, key_type, raw) "
                     "VALUES ('kv789', 'twinlantern_gog', 'Twin Lantern', "
                     "'gog', '{}')")
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) c FROM external_keys").fetchone()["c"] == 2
    finally:
        conn.close()


def test_migration_skips_a_key_whose_blob_will_not_parse(tmp_path):
    # NOT NULL would abort the whole migration on one bad row, leaving the
    # database unopenable. Skipping loses one key; aborting loses the lot.
    path = tmp_path / "t.db"
    _v11_with_old_external_keys(path, [
        ("Twin Lantern", json.dumps({"machine_name": "twinlantern_steam"})),
        ("Hollowmere", "not json at all")])
    conn = db.connect(path)
    try:
        got = [r["machine_name"] for r in
               conn.execute("SELECT machine_name FROM external_keys")]
        assert got == ["twinlantern_steam"]
    finally:
        conn.close()


def test_a_fresh_database_is_not_rebuilt_by_migration_12(tmp_path):
    # SCHEMA already makes the new shape, so the column check must make
    # this a no-op rather than dropping and recreating a populated table.
    conn = db.connect(tmp_path / "t.db")
    try:
        cols = {r["name"] for r in
                conn.execute("PRAGMA table_info(external_keys)")}
        assert "machine_name" in cols
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 12
    finally:
        conn.close()
