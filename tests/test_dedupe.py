from humble_catalog import db, dedupe

def test_new_tables_exist_after_connect(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    names = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"merges", "dismissed_pairs"} <= names

def test_dedupe_key_cosmetic_variants_match():
    assert dedupe.dedupe_key("MOONFALL, Vol. 1") == dedupe.dedupe_key("Moonfall Vol. 1")
    assert dedupe.dedupe_key("Innkeeper’s Ledger") == dedupe.dedupe_key("Innkeeper's Ledger")

def test_dedupe_key_edition_variants_match():
    key = dedupe.dedupe_key("Building Widget Services, 2nd Edition")
    assert key == dedupe.dedupe_key("Building Widget Services 2e")
    assert key == dedupe.dedupe_key("Building Widget Services, 2nd ed.")

def test_dedupe_key_keeps_hash_and_plus_significant():
    assert dedupe.dedupe_key("Learn C#") != dedupe.dedupe_key("Learn C")
    assert dedupe.dedupe_key("Programming C++") != dedupe.dedupe_key("Programming C")

def _seed(conn, rows):
    """rows: [(machine_name, name, type)] -> {machine_name: id}"""
    ids = {}
    for mn, name, typ in rows:
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
            (mn, name, typ))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (cur.lastrowid,))
        ids[mn] = cur.lastrowid
    conn.commit()
    return ids

def test_find_groups_same_key_and_type_only(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    ids = _seed(conn, [
        ("a1", "The Starless War", "audiobook"),
        ("a2", "The Starless War", "audiobook"),
        ("e1", "The Starless War", "ebook"),          # different type: no pair
        ("b1", "Building Widget Services 2e", "ebook"),
        ("b2", "Building Widget Services, 2nd Edition", "ebook"),
        ("u1", "Unrelated Book", "ebook"),
    ])
    groups = dedupe.find_groups(conn)
    # sorted by lowest member name: "building widget services..." < "the starless war"
    assert groups == [sorted([ids["b1"], ids["b2"]]),
                      sorted([ids["a1"], ids["a2"]])]

def test_find_groups_honors_dismissals(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("h1", "Learn Java", "ebook"),
                 ("h2", "Learn Java", "ebook")])
    a, b = sorted(["h1", "h2"])
    conn.execute("INSERT INTO dismissed_pairs (a, b) VALUES (?,?)", (a, b))
    conn.commit()
    assert dedupe.find_groups(conn) == []
