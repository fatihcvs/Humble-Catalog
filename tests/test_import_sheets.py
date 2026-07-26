import pytest
from openpyxl import Workbook
from humble_catalog import db, import_sheets

def make_wb(path, sheets):
    """sheets: {sheet_name: [row_tuple, ...]} — row 1 is the header."""
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    wb.save(path)
    return path

def test_read_workbook_headers_and_aliases(tmp_path):
    p = make_wb(tmp_path / "b.xlsx", {"Grimdark": [
        ("Name:", "Setting:", "Author:", "Narator:", "Humble:", "Rating:"),
        ("Axebearer", "The Elder Realm", "Alex Penner", "Sam Reader",
         "Epic Tales", 4.0),
    ]})
    rows, skipped, _ = import_sheets.read_workbook(p)
    assert skipped == []
    (row,) = rows
    assert row["sheet"] == "Grimdark"
    assert row["title"] == "Axebearer"
    assert row["genre"] == "The Elder Realm"        # Setting: -> genre
    assert row["authors"] == "Alex Penner"       # Author: -> authors
    assert row["narrator"] == "Sam Reader"   # Narator: typo handled
    assert row["rating"] == 4.0
    assert "bundle" not in row and "publisher" not in row

def test_read_workbook_skips_blank_rows_and_reports_bad_sheets(tmp_path):
    p = make_wb(tmp_path / "b.xlsx", {
        "Fiction": [
            ("Name:", "Genre:", "Series:", "Number in the series:", "Rating:"),
            ("All Systems Red", "Science Fiction", "Murderbot Diaries", 1.0, 0.0),
            (None, None, None, None, None),
            ("  ", None, None, None, None),
        ],
        "Ark3": [],
        "Notes": [("Random", "Junk"), ("no", "title header")],
    })
    rows, skipped, _ = import_sheets.read_workbook(p)
    assert [r["title"] for r in rows] == ["All Systems Red"]
    assert rows[0]["series_number"] == 1.0
    assert sorted(skipped) == ["Ark3", "Notes"]

def _catalog(tmp_path, items):
    """items: [(name, type)] -> connection with enrichment rows."""
    conn = db.connect(tmp_path / "cat.db")
    for n, (name, typ) in enumerate(items):
        conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?, ?, ?)",
            (f"{name.lower().replace(' ', '_')}_{typ}_{n}", name, typ))
        item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (item_id,))
    conn.commit()
    return conn

def test_norm_title():
    assert import_sheets.norm_title("The Endless Wars: Inferno!") == \
        import_sheets.norm_title("the endless wars inferno")
    assert import_sheets.norm_title(1632.0) == "1632"   # numeric cell

def test_type_scope():
    assert import_sheets.type_scope("Audiobooks (loose collection).xlsx") == ("audiobook",)
    assert import_sheets.type_scope("E-books (loose collection).xlsx") == ("ebook", "comic")

def test_match_scoped_unique_ambiguous_unmatched(tmp_path):
    conn = _catalog(tmp_path, [("All Systems Red", "audiobook"),
                               ("All Systems Red", "ebook"),
                               ("Dune", "audiobook"),
                               ("Dune", "audiobook")])
    index, display = import_sheets.build_index(conn, ("audiobook",))
    assert import_sheets.match(index, display, "All Systems Red") == \
        ("matched", index[import_sheets.norm_title("All Systems Red")][0], None)
    status, item_id, _ = import_sheets.match(index, display, "Dune")
    assert (status, item_id) == ("ambiguous", None)
    status, item_id, suggestion = import_sheets.match(index, display, "All System Red")
    assert (status, item_id) == ("unmatched", None)
    assert suggestion == "All Systems Red"   # original catalog name, not the norm key

def _get(conn, item_id):
    return conn.execute(
        "SELECT i.my_rating, e.* FROM items i "
        "JOIN enrichment e ON e.item_id = i.id WHERE i.id=?",
        (item_id,)).fetchone()

def test_import_row_fills_gaps_only(tmp_path):
    conn = _catalog(tmp_path, [("All Systems Red", "audiobook")])
    item_id = conn.execute("SELECT id FROM items").fetchone()["id"]
    conn.execute("UPDATE enrichment SET genre=? WHERE item_id=?",
                 (db.tags_to_json(["SF"]), item_id))
    conn.commit()
    row = {"sheet": "Fiction", "title": "All Systems Red", "rating": 4.0,
           "genre": "Science Fiction", "series": "Murderbot Diaries",
           "series_number": 1.0, "narrator": "Kevin R. Free"}
    ratings, filled = import_sheets.import_row(conn, item_id, row)
    got = _get(conn, item_id)
    assert (ratings, filled) == (1, 3)                 # series, number, narrator
    assert got["my_rating"] == 4
    assert db.tags_from_json(got["genre"]) == ["SF"]   # not overwritten
    assert got["series"] == "Murderbot Diaries"
    assert got["series_number"] == 1.0
    assert db.tags_from_json(got["narrator"]) == ["Kevin R. Free"]
    assert got["pre_edit"] is not None                 # stored as hand-edit

def test_import_row_zero_rating_and_full_row_touch_nothing(tmp_path):
    conn = _catalog(tmp_path, [("Dune", "audiobook")])
    item_id = conn.execute("SELECT id FROM items").fetchone()["id"]
    ratings, filled = import_sheets.import_row(
        conn, item_id, {"sheet": "Fiction", "title": "Dune", "rating": 0.0})
    assert (ratings, filled) == (0, 0)
    assert _get(conn, item_id)["pre_edit"] is None     # no snapshot: nothing written

def test_run_is_idempotent_and_reports(tmp_path, capsys):
    conn = _catalog(tmp_path, [("All Systems Red", "audiobook")])
    conn.close()
    make_wb(tmp_path / "Audiobooks test.xlsx", {"Fiction": [
        ("Name:", "Genre:", "Rating:"),
        ("All Systems Red", "Science Fiction", 5.0),
        ("All System Red", "Mystery", 0.0),   # near-miss: unmatched + suggestion
    ]})
    db_path = tmp_path / "cat.db"
    import_sheets.run([str(tmp_path / "Audiobooks test.xlsx")], db_path=db_path)
    out1 = capsys.readouterr().out
    assert "1 ratings set" in out1 and "1 fields filled" in out1
    assert "All System Red" in out1 and "closest: All Systems Red" in out1
    import_sheets.run([str(tmp_path / "Audiobooks test.xlsx")], db_path=db_path)
    out2 = capsys.readouterr().out
    assert "0 ratings set" in out2 and "0 fields filled" in out2
    assert "1 already complete" in out2   # matched but nothing left to write

def test_na_cells_and_bad_series_numbers_are_ignored(tmp_path):
    p = make_wb(tmp_path / "b.xlsx", {"Non-Fiction": [
        ("Name:", "Genre:", "Number in the series:", "Rating:"),
        ("How Sound Behaves", "N/A", "n/a", 0.0),
    ]})
    rows, _, _ = import_sheets.read_workbook(p)
    (row,) = rows
    assert "genre" not in row and "series_number" not in row
    # a stray non-numeric series_number that slips through must not crash
    conn = _catalog(tmp_path, [("How Sound Behaves", "audiobook")])
    item_id = conn.execute("SELECT id FROM items").fetchone()["id"]
    ratings, filled = import_sheets.import_row(
        conn, item_id, {"sheet": "x", "title": "How Sound Behaves",
                        "rating": None, "series_number": "one"})
    assert (ratings, filled) == (0, 0)

def test_import_row_normalizes_genre_case(tmp_path):
    conn = _catalog(tmp_path, [("All Systems Red", "audiobook"),
                               ("Dune", "audiobook")])
    a, b = [r["id"] for r in conn.execute("SELECT id FROM items ORDER BY id")]
    conn.execute("UPDATE enrichment SET genre=? WHERE item_id=?",
                 (db.tags_to_json(["Science Fiction"]), a))
    conn.commit()
    import_sheets.import_row(conn, b, {"sheet": "Fiction", "title": "Dune",
                                       "genre": "science fiction",
                                       "narrator": "sam reader"})
    got = _get(conn, b)
    assert db.tags_from_json(got["genre"]) == ["Science Fiction"]  # snapped
    assert db.tags_from_json(got["narrator"]) == ["sam reader"]    # untouched

def test_run_shows_a_live_scoreboard_on_a_terminal(tmp_path, monkeypatch):
    import io, re
    from humble_catalog import progress as mod

    class Tty(io.StringIO):
        def isatty(self):
            return True

    out = Tty()
    monkeypatch.setattr(mod, "_enable_ansi", lambda stream: True)
    monkeypatch.setattr(mod.sys, "stdout", out)
    conn = _catalog(tmp_path, [("All Systems Red", "audiobook")])
    conn.close()
    make_wb(tmp_path / "Audiobooks test.xlsx", {"Fiction": [
        ("Name:", "Genre:", "Rating:"),
        ("All Systems Red", "Science Fiction", 5.0),
        ("All System Red", "Mystery", 0.0),   # near-miss: unmatched
    ]})
    import_sheets.run([str(tmp_path / "Audiobooks test.xlsx")],
                      db_path=tmp_path / "cat.db")
    text = out.getvalue()
    assert "Workbook 1/1" in text                 # the read phase is visible too
    final = re.split(r"\x1b\[\d+A", text)[-1]
    assert "Row 2/2 100%" in final
    assert "matched 1" in final and "unmatched 1" in final
    assert "ratings 1" in final and "filled 1" in final
    summary = ("2 rows read, 1 matched, 1 ratings set, "
               "1 fields filled, 0 already complete")
    assert summary in final                       # summary lands below the grid
    assert final.index(summary) < final.index("Unmatched:")   # then the detail lists

def test_run_without_a_terminal_does_not_name_every_row(tmp_path, capsys):
    # thousands of rows must not flood a piped log - or list private titles in it
    conn = _catalog(tmp_path, [("All Systems Red", "audiobook")])
    conn.close()
    make_wb(tmp_path / "Audiobooks test.xlsx", {"Fiction": [
        ("Name:", "Genre:", "Rating:"),
        ("All Systems Red", "Science Fiction", 5.0),
    ]})
    import_sheets.run([str(tmp_path / "Audiobooks test.xlsx")],
                      db_path=tmp_path / "cat.db")
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert "Row 1/1" not in out
    assert out.startswith("1 rows read, 1 matched")


# --- unrecognized columns --------------------------------------------------

def test_unrecognized_columns_are_collected_not_silently_dropped(tmp_path):
    # The trap this closes: "Ratings" instead of "Rating" imports nothing
    # and the run still reports success.
    p = make_wb(tmp_path / "b.xlsx", {"Fiction": [
        ("Name:", "Ratings:", "Authors", "Bundle:", None, "  "),
        ("Axebearer", 4.0, "Alex Penner", "Epic Tales", None, None),
    ]})
    rows, skipped, unknown = import_sheets.read_workbook(p)
    assert skipped == []
    assert unknown == [("Fiction", ["Ratings", "Authors"])]
    # Bundle is recognized-and-dropped, so it is not a mistake; blank
    # header cells are ordinary trailing columns, not mistakes either.
    (row,) = rows
    assert "rating" not in row or row["rating"] is None
    assert "authors" not in row


def test_a_misspelled_name_column_is_reported_twice(tmp_path):
    # Both facts are needed to diagnose it: the sheet was skipped, and
    # "Title" is why -- neither alone points at the fix.
    p = make_wb(tmp_path / "b.xlsx", {"Fiction": [
        ("Title:", "Rating:"),
        ("Axebearer", 4.0),
    ]})
    rows, skipped, unknown = import_sheets.read_workbook(p)
    assert rows == []
    assert skipped == ["Fiction"]
    assert unknown == [("Fiction", ["Title"])]


def test_run_reports_unrecognized_columns_and_the_vocabulary(tmp_path, capsys):
    make_wb(tmp_path / "Audiobooks test.xlsx", {"Fiction": [
        ("Name:", "Ratings:"),
        ("All Systems Red", 5.0),
    ]})
    _catalog(tmp_path, [("All Systems Red", "audiobook")])
    import_sheets.run([str(tmp_path / "Audiobooks test.xlsx")],
                      db_path=tmp_path / "cat.db")
    out = capsys.readouterr().out
    assert "Unrecognized columns" in out
    assert "Ratings" in out
    # Naming the accepted spellings is the point: the fix has to be
    # visible without going to the docs.
    assert "Name" in out and "Rating" in out
    assert "0 ratings set" in out
