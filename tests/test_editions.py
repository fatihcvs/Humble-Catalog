"""Cross-format edition detection.

Titles are invented -- see docs/TEST-DATA.md."""
from humble_catalog import db, editions


def test_a_trailing_format_marker_is_stripped():
    key = editions.edition_key("Salt and Sextant")
    assert key == editions.edition_key("Salt and Sextant Audiobook")
    assert key == editions.edition_key("Salt and Sextant (Unabridged)")


def test_a_run_of_trailing_markers_strips_as_a_unit():
    # "(audiobook novella)" is two markers in a row, which is why the
    # strip repeats rather than applying once.
    assert editions.edition_key("The Copper Almanac") == \
        editions.edition_key("The Copper Almanac (audiobook novella)")


def test_a_marker_inside_the_title_is_kept():
    # Trailing-only, deliberately: an anywhere-strip would reduce this
    # to "engineering handbook" and invite a collision with a
    # genuinely different book.
    assert editions.edition_key("Audio Engineering Handbook") == \
        "audio engineering handbook"


def test_a_title_that_is_only_markers_keeps_its_key():
    # Stripping to empty would group every such title together, so the
    # last non-empty key wins.
    assert editions.edition_key("Audiobook") == "audiobook"


def test_work_types_excludes_android_and_music():
    # The exclusion IS the precision story -- every measured false
    # positive came from one of these two.
    assert "android" not in editions.WORK_TYPES
    assert "music" not in editions.WORK_TYPES
    assert editions.WORK_TYPES == {"ebook", "audiobook", "comic"}


def _seed(conn, rows):
    """rows: [(machine_name, name, type)] -> {machine_name: id}"""
    ids = {}
    for mn, name, typ in rows:
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
            (mn, name, typ))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
        ids[mn] = cur.lastrowid
    conn.commit()
    return ids


def test_an_ebook_and_its_audiobook_group(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    ids = _seed(conn, [
        ("e1", "Salt and Sextant", "ebook"),
        ("a1", "Salt and Sextant Audiobook", "audiobook"),
        ("u1", "Unrelated Book", "ebook"),
    ])
    assert editions.find_groups(conn) == [sorted([ids["e1"], ids["a1"]])]


def test_two_items_of_the_same_type_never_group(tmp_path):
    # That is dedupe's question, not this one. A group must SPAN types.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("a1", "The Starless War", "audiobook"),
                 ("a2", "The Starless War", "audiobook")])
    assert editions.find_groups(conn) == []


def test_a_game_and_its_soundtrack_are_never_an_edition_group(tmp_path):
    # The measured false-positive shape, five times over in the real
    # catalog: an APK and its own soundtrack share a name because they
    # shipped together, not because they are the same work.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("g1", "Cool Tower Defense", "android"),
                 ("m1", "Cool Tower Defense", "music")])
    assert editions.find_groups(conn) == []


def test_a_subset_title_is_not_an_edition_group(tmp_path):
    # "compass" is a token subset of the longer title, so token_set_ratio
    # scores this pair 100 -- the exact trap that made fuzzy matching
    # produce 8 false positives. Exact keys differ, so: no group.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("e1", "Compass", "ebook"),
                 ("a1", "The Compass of Broken Years Audiobook", "audiobook")])
    assert editions.find_groups(conn) == []


def test_a_comic_and_an_ebook_group(tmp_path):
    # No such pair exists in the catalog yet. This test is what says the
    # comic type is admitted on purpose rather than by accident.
    conn = db.connect(tmp_path / "t.db")
    ids = _seed(conn, [("c1", "Nightjar Post", "comic"),
                       ("e1", "Nightjar Post", "ebook")])
    assert editions.find_groups(conn) == [sorted([ids["c1"], ids["e1"]])]


def test_a_dismissed_cross_type_pair_disappears(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("e1", "Salt and Sextant", "ebook"),
                 ("a1", "Salt and Sextant Audiobook", "audiobook")])
    a, b = sorted(["e1", "a1"])
    conn.execute("INSERT INTO dismissed_pairs (a, b) VALUES (?,?)", (a, b))
    conn.commit()
    assert editions.find_groups(conn) == []


def test_a_dismissed_same_type_pair_leaves_editions_alone(tmp_path):
    # dismissed_pairs is shared with dedupe, and the two meanings cannot
    # collide: dedupe's pairs are always same-type, edition pairs always
    # cross-type. This asserts that disjointness rather than assuming it.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("e1", "Salt and Sextant", "ebook"),
                 ("e2", "Salt and Sextant", "ebook"),
                 ("a1", "Salt and Sextant Audiobook", "audiobook")])
    a, b = sorted(["e1", "e2"])
    conn.execute("INSERT INTO dismissed_pairs (a, b) VALUES (?,?)", (a, b))
    conn.commit()
    # e1 and e2 are dismissed against each other but NOT against a1, so
    # both survive and the group still spans two types.
    assert len(editions.find_groups(conn)) == 1
    assert len(editions.find_groups(conn)[0]) == 3


def test_groups_are_sorted_by_lowest_member_name(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    ids = _seed(conn, [
        ("e1", "Salt and Sextant", "ebook"),
        ("a1", "Salt and Sextant Audiobook", "audiobook"),
        ("c1", "Nightjar Post", "comic"),
        ("e2", "Nightjar Post", "ebook"),
    ])
    assert editions.find_groups(conn) == [
        sorted([ids["c1"], ids["e2"]]),      # "nightjar post"
        sorted([ids["e1"], ids["a1"]]),      # "salt and sextant"
    ]
