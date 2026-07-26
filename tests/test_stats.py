from humble_catalog import stats


def _item(**kw):
    """A settled item with every field populated; override to change one."""
    base = {"type": "ebook", "my_rating": 5, "read_status": "read",
            "status": "matched", "genre": ["Fantasy"],
            "cover_path": "covers/x.jpg", "source_url": "http://example.test/x"}
    base.update(kw)
    return base


def _rows(items, key):
    """The rows of one section, as a {label: count} dict."""
    sections, _total = stats.report(items)
    return dict(next(rows for k, _label, rows in sections if k == key))


def test_report_returns_every_section_in_order():
    sections, total = stats.report([_item()])
    assert [k for k, _l, _r in sections] == [
        "type", "rating", "status", "enrichment", "gaps", "genre"]
    assert total == 1


def test_type_section_counts_each_type():
    items = [_item(type="ebook"), _item(type="ebook"), _item(type="comic")]
    rows = _rows(items, "type")
    assert rows["E-books"] == 2
    assert rows["Comics"] == 1
    assert rows["Audiobooks"] == 0     # a zero row is present, not omitted


def test_type_section_ignores_an_unknown_type():
    # counted nowhere rather than inventing a row, so sections need not
    # sum to the total
    rows = _rows([_item(type="hologram")], "type")
    assert sum(rows.values()) == 0


def test_rating_section_covers_one_to_five_and_omits_unrated():
    # unrated is a gap, and listing it here too would duplicate it
    items = [_item(my_rating=5), _item(my_rating=5), _item(my_rating=None)]
    rows = _rows(items, "rating")
    assert rows["★5"] == 2
    assert rows["★1"] == 0
    assert not any("nrated" in label for label in rows)


def test_status_section_uses_lifecycle_order():
    sections, _ = stats.report([_item()])
    rows = next(r for k, _l, r in sections if k == "status")
    assert [label for label, _n in rows] == [
        "Want to read", "Unread", "Reading", "Read", "DNF"]


def test_status_section_treats_a_missing_status_as_unread():
    # the column defaults to 'unread'; an older payload omits it entirely
    rows = _rows([{"type": "ebook"}], "status")
    assert rows["Unread"] == 1


def test_enrichment_section_counts_each_state():
    items = [_item(status="matched"), _item(status="unmatched"),
             _item(status="pending")]
    rows = _rows(items, "enrichment")
    assert rows["Matched"] == 1
    assert rows["Unmatched"] == 1
    assert rows["Pending"] == 1
    assert rows["Low confidence"] == 0


def test_gaps_section_keeps_the_three_shipped_gaps():
    items = [_item(my_rating=None), _item(cover_path=""), _item(source_url=None)]
    rows = _rows(items, "gaps")
    assert rows == {"Unrated": 1, "No cover": 1, "No source URL": 1}


def test_genre_section_orders_by_count_then_alphabetically():
    items = [_item(genre=["Fantasy", "Horror"]), _item(genre=["Fantasy"]),
             _item(genre=["Adventure"])]
    sections, _ = stats.report(items)
    rows = next(r for k, _l, r in sections if k == "genre")
    # Fantasy leads on count; Adventure precedes Horror on the 1-1 tie
    assert rows == [("Fantasy", 2), ("Adventure", 1), ("Horror", 1)]


def test_genre_section_returns_every_tag():
    # truncation to a top N is the viewer's business, not the report's
    items = [_item(genre=[f"Genre {i}"]) for i in range(20)]
    sections, _ = stats.report(items)
    rows = next(r for k, _l, r in sections if k == "genre")
    assert len(rows) == 20


def test_report_of_an_empty_catalog_is_zeroes_in_order():
    sections, total = stats.report([])
    assert total == 0
    assert [k for k, _l, _r in sections] == [
        "type", "rating", "status", "enrichment", "gaps", "genre"]
    assert dict(next(r for k, _l, r in sections if k == "gaps")) == {
        "Unrated": 0, "No cover": 0, "No source URL": 0}
    assert next(r for k, _l, r in sections if k == "genre") == []


def test_every_section_tolerates_a_wholly_empty_item():
    # a partial payload from an older server must not raise anywhere
    sections, _ = stats.report([{}])
    assert len(sections) == 6


def test_run_prints_a_heading_per_section_and_a_total(capsys, monkeypatch):
    monkeypatch.setattr(stats.db, "fetch_items",
                        lambda _conn: [_item(type="ebook", my_rating=4)])
    stats.run(object())          # run() only passes the conn to fetch_items

    out = capsys.readouterr().out
    for heading in ("By type", "Ratings", "Reading status",
                    "Enrichment", "Gaps", "Genres"):
        assert heading in out
    assert "1  E-books" in out
    assert "1  items total" in out


def test_star_labels_degrade_on_a_console_that_cannot_encode_them():
    # the default Windows console is cp1252, which has no star; printing
    # the shared label raw crashed the command
    assert stats.console_safe("★5", "cp1252") == "*5"
    assert stats.console_safe("★5", "utf-8") == "★5"


def test_console_safe_replaces_any_other_unencodable_character():
    # genre tags are arbitrary user data, not just the labels we choose
    assert stats.console_safe("Sci-Fi ☃", "cp1252") == "Sci-Fi ?"
