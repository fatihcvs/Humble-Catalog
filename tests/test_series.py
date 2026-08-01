from humble_catalog import db, series


def _conn(tmp_path, *names):
    conn = db.connect(tmp_path / "catalog.db")
    for i, name in enumerate(names):
        conn.execute("INSERT INTO items (machine_name, name, type) "
                     "VALUES (?, ?, 'comic')", (f"mn{i}", name))
    conn.commit()
    return conn


def _index(tmp_path, *names):
    conn = _conn(tmp_path, *names)
    try:
        return series.owned_volumes(conn)
    finally:
        conn.close()


def test_collapse_renders_a_contiguous_run_as_a_range():
    assert series.collapse([1, 2, 3, 4, 5, 6]) == "1-6"


def test_collapse_renders_a_gap_honestly():
    assert series.collapse([1, 2, 3, 5, 6]) == "1-3, 5-6"


def test_collapse_renders_a_lone_volume_as_a_bare_number():
    assert series.collapse([3]) == "3"


def test_owned_volumes_indexes_a_series_by_key(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1", "Shadow Hound Vol. 2")
    assert index == {"shadow hound": {1, 2}}


def test_owned_volumes_merges_spellings_that_differ_only_in_punctuation(tmp_path):
    index = _index(tmp_path, "MOONFALL, Vol. 1", "Moonfall Vol. 2")
    assert index == {"moonfall": {1, 2}}


def test_owned_volumes_ignores_items_with_no_marker(tmp_path):
    assert _index(tmp_path, "Unrelated Book") == {}


def test_an_offered_volume_you_do_not_hold_reports_the_run(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1", "Shadow Hound Vol. 2")
    hit = series.describe("Shadow Hound Vol. 7", index)
    assert hit["kind"] == "volume"
    assert hit["already_owned"] is False
    assert hit["owned_display"] == "Vol. 1-2"
    assert hit["series_name"] == "Shadow Hound"


def test_an_offered_volume_you_already_hold_is_flagged_as_a_re_buy(tmp_path):
    # It matched no machine_name yet is a volume already held: a re-issue
    # or another edition of the same book. The mistake this report exists
    # to prevent, and today it prints as a bare 0.94.
    index = _index(tmp_path, "Shadow Hound Vol. 1", "Shadow Hound Vol. 2")
    assert series.describe("Shadow Hound Vol. 2", index)["already_owned"] is True


def test_an_offered_collection_reports_how_many_volumes_are_held(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1", "Shadow Hound Vol. 2")
    hit = series.describe("Shadow Hound Omnibus", index)
    assert hit["kind"] == "collection"
    assert hit["span"] is None            # no denominator to state
    assert hit["owned"] == [1, 2]


def test_an_offered_range_carries_the_denominator_it_states(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1")
    hit = series.describe("Shadow Hound Vol. 1-6", index)
    assert hit["kind"] == "collection"
    assert hit["span"] == [1, 6]
    assert hit["already_owned"] is False   # never read as its lower bound


def test_a_series_the_catalog_does_not_hold_is_not_described(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1")
    assert series.describe("Moonfall Vol. 3", index) is None


def test_a_title_with_no_marker_is_not_described(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1")
    assert series.describe("Unrelated Book", index) is None


def test_sort_puts_re_buys_first_then_collections_then_continuations():
    hits = [{"already_owned": False, "kind": "volume", "offered": "b"},
            {"already_owned": False, "kind": "collection", "offered": "c"},
            {"already_owned": True, "kind": "volume", "offered": "a"}]
    assert [h["offered"] for h in sorted(hits, key=series.sort_key)] == ["a", "c", "b"]
