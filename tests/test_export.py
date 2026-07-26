import csv
import io
from datetime import date, datetime
from openpyxl import load_workbook
from humble_catalog import db, export

def _seed(dbp):
    conn = db.connect(dbp)
    conn.execute("INSERT INTO bundles VALUES ('k1','Book Bundle','http://b1','2020-01-05T12:00:00')")
    conn.execute("INSERT INTO bundles VALUES ('k2','Comic Bundle','http://b2','2019-03-02T08:00:00')")
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, type, publisher, my_rating) "
        "VALUES ('asr','All Systems Red, Vol. 1','ebook','Tor',5)")
    item_id = cur.lastrowid
    conn.execute("INSERT INTO item_bundles VALUES (?, 'k1')", (item_id,))
    conn.execute("INSERT INTO item_bundles VALUES (?, 'k2')", (item_id,))
    conn.execute("INSERT INTO downloads (item_id, kind, url, formats) "
                 "VALUES (?, 'humble', 'http://d1', 'epub,pdf')", (item_id,))
    conn.execute("INSERT INTO downloads (item_id, kind, url, formats) "
                 "VALUES (?, 'humble', 'http://d2', 'mobi,epub')", (item_id,))
    conn.execute(
        "INSERT INTO enrichment (item_id, genre, series, series_number, authors, "
        "external_rating, rating_source, status) "
        "VALUES (?, '[\"SF\"]', 'Murderbot', 1, "
        "'[\"Martha Wells\", \"Ann Leckie\"]', 4.3, 'hardcover', 'auto')",
        (item_id,))
    conn.commit()
    return conn, item_id

def _export(conn):
    buf = io.StringIO(newline="")
    count = export.write_csv(conn, buf)
    return count, list(csv.reader(io.StringIO(buf.getvalue())))

def test_header_and_row(tmp_path):
    conn, _ = _seed(tmp_path / "t.db")
    count, rows = _export(conn)
    assert count == 1 and len(rows) == 2
    assert rows[0] == list(export.COLUMNS)
    row = dict(zip(rows[0], rows[1]))
    assert row["title"] == "All Systems Red, Vol. 1"  # comma survives quoting
    assert row["authors"] == "Martha Wells; Ann Leckie"
    assert row["genre"] == "SF"
    assert row["my_rating"] == "5"
    assert row["formats"] == "epub; mobi; pdf"
    assert row["bundles"] == "Comic Bundle; Book Bundle"  # purchased_at order
    assert row["first_purchased"] == "2019-03-02"  # date part of earliest
    assert row["narrator"] == ""  # NULL -> empty cell, not "None"
    assert row["edited"] == ""

def test_edited_flag(tmp_path):
    conn, item_id = _seed(tmp_path / "t.db")
    # hand_edited, not pre_edit: a re-enriched row keeps a snapshot but its
    # values came from a source, so it must not export as edited
    conn.execute("UPDATE enrichment SET pre_edit='{}', hand_edited=1 "
                 "WHERE item_id=?", (item_id,))
    conn.commit()
    _, rows = _export(conn)
    assert dict(zip(rows[0], rows[1]))["edited"] == "yes"

def test_read_status_exports_as_its_label(tmp_path):
    conn, _ = _seed(tmp_path / "t.db")
    conn.execute("UPDATE items SET read_status='want_to_read'")
    conn.commit()
    _, rows = _export(conn)
    row = dict(zip(rows[0], rows[1]))
    assert "read_status" in rows[0]
    assert row["read_status"] == "Want to read"

def test_read_status_column_can_be_selected_alone(tmp_path):
    conn, _ = _seed(tmp_path / "t.db")
    buf = io.StringIO(newline="")
    export.write_csv(conn, buf, columns=["title", "read_status"])
    header = next(csv.reader(io.StringIO(buf.getvalue())))
    assert header == ["title", "read_status"]

def test_empty_catalog_is_header_only(tmp_path):
    conn = db.connect(tmp_path / "e.db")
    count, rows = _export(conn)
    assert count == 0 and rows == [list(export.COLUMNS)]

def _seed_three(dbp):
    """Three minimal items. Returns (conn, {name: id})."""
    conn = db.connect(dbp)
    ids = {}
    for name in ("A Quiet Life in Harbors", "The Quiet Harbor: A Novel",
                 "Unrelated Book"):
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?,?,'ebook')",
            (name.lower().replace(" ", "-"), name))
        ids[name] = cur.lastrowid
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    conn.commit()
    return conn, ids

def _titles(rows):
    """Data-row titles, in file order."""
    return [r[rows[0].index("title")] for r in rows[1:]]

def test_ids_are_written_in_the_callers_order(tmp_path):
    # The viewer posts rows in the order it shows them, so write_csv must
    # not re-sort. Reverse of title order: sorting inside would show up here.
    conn, ids = _seed_three(tmp_path / "t.db")
    order = [ids["Unrelated Book"], ids["The Quiet Harbor: A Novel"],
             ids["A Quiet Life in Harbors"]]
    buf = io.StringIO(newline="")
    count = export.write_csv(conn, buf, ids=order)
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert count == 3
    assert _titles(rows) == ["Unrelated Book", "The Quiet Harbor: A Novel",
                             "A Quiet Life in Harbors"]

def test_ids_select_a_subset(tmp_path):
    conn, ids = _seed_three(tmp_path / "t.db")
    buf = io.StringIO(newline="")
    count = export.write_csv(conn, buf, ids=[ids["Unrelated Book"]])
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert count == 1
    assert _titles(rows) == ["Unrelated Book"]

def test_unknown_ids_are_skipped_not_fatal(tmp_path):
    # The client's snapshot can predate a merge or delete. The export is
    # read-only, so a vanished row must not cost the whole download.
    conn, ids = _seed_three(tmp_path / "t.db")
    buf = io.StringIO(newline="")
    count = export.write_csv(conn, buf, ids=[ids["Unrelated Book"], 99999])
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert count == 1  # the count reflects rows actually written
    assert _titles(rows) == ["Unrelated Book"]

def test_empty_id_list_is_header_only(tmp_path):
    conn, _ = _seed_three(tmp_path / "t.db")
    buf = io.StringIO(newline="")
    count = export.write_csv(conn, buf, ids=[])
    assert count == 0
    assert list(csv.reader(io.StringIO(buf.getvalue()))) == [list(export.COLUMNS)]

def test_ids_none_is_the_whole_catalog_in_title_order(tmp_path):
    # The backwards-compatibility guard: the full-catalog path is unchanged.
    conn, _ = _seed_three(tmp_path / "t.db")
    buf_default, buf_none = io.StringIO(newline=""), io.StringIO(newline="")
    export.write_csv(conn, buf_default)
    export.write_csv(conn, buf_none, ids=None)
    assert buf_default.getvalue() == buf_none.getvalue()
    rows = list(csv.reader(io.StringIO(buf_none.getvalue())))
    assert _titles(rows) == ["A Quiet Life in Harbors",
                             "The Quiet Harbor: A Novel", "Unrelated Book"]

def test_export_includes_user_columns(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, user_tags, "
                 "user_comment) VALUES ('m','The Quiet Harbor: A Novel',?,?)",
                 (db.tags_to_json(["to reread", "lent out"]), "Gift from Sam."))
    conn.execute("INSERT INTO enrichment (item_id) VALUES (1)")
    conn.commit()
    fh = io.StringIO()
    export.write_csv(conn, fh)
    rows = list(csv.reader(io.StringIO(fh.getvalue())))
    header, row = rows[0], rows[1]
    assert row[header.index("user_tags")] == "to reread; lent out"
    assert row[header.index("user_comment")] == "Gift from Sam."

def test_first_purchased_is_a_date_that_csv_stringifies(tmp_path):
    # _row yields a datetime.date so the XLSX writer gets a typed cell.
    # The CSV is unaffected because csv.writer calls str() on non-strings
    # and str(date(2019, 3, 2)) is exactly "2019-03-02". This test exists
    # so nobody "fixes" that implicit coercion by formatting in _row.
    conn, _ = _seed(tmp_path / "t.db")
    item = db.fetch_items(conn)[0]
    cells = dict(zip(export.COLUMNS, export._row(item, export.COLUMNS)))
    assert cells["first_purchased"] == date(2019, 3, 2)  # the EARLIER bundle
    _, rows = _export(conn)
    assert dict(zip(rows[0], rows[1]))["first_purchased"] == "2019-03-02"

def test_select_is_the_shared_row_source(tmp_path):
    # Both writers go through _select, so the order/unknown-id policy is
    # stated once. Pinned here rather than only through write_csv.
    conn, ids = _seed_three(tmp_path / "t.db")
    order = [ids["Unrelated Book"], 99999, ids["A Quiet Life in Harbors"]]
    assert [r["name"] for r in export._select(conn, order)] == [
        "Unrelated Book", "A Quiet Life in Harbors"]
    assert len(export._select(conn, None)) == 3
    assert export._select(conn, []) == []

def _export_xlsx(conn, ids=None):
    """Write a workbook to memory and read it back. Returns (count, ws)."""
    buf = io.BytesIO()
    count = export.write_xlsx(conn, buf, ids=ids)
    buf.seek(0)
    return count, load_workbook(buf).active

def _xlsx_cells(ws):
    """The first data row as {column: value}."""
    header = [c.value for c in ws[1]]
    return dict(zip(header, [c.value for c in ws[2]]))

def _xlsx_titles(ws):
    """Data-row titles, in file order."""
    col = [c.value for c in ws[1]].index("title")
    return [row[col].value for row in ws.iter_rows(min_row=2)]

def test_xlsx_header_and_row(tmp_path):
    conn, _ = _seed(tmp_path / "t.db")
    count, ws = _export_xlsx(conn)
    assert count == 1
    assert ws.title == "Catalog"
    assert [c.value for c in ws[1]] == list(export.COLUMNS)
    cells = _xlsx_cells(ws)
    assert cells["title"] == "All Systems Red, Vol. 1"
    assert cells["authors"] == "Martha Wells; Ann Leckie"
    assert cells["formats"] == "epub; mobi; pdf"
    # openpyxl reads an empty cell back as None, not ""
    assert (cells["narrator"] or "") == ""

def test_xlsx_ratings_are_numbers_not_text(tmp_path):
    # The point of the whole working-surface decision: a rating column
    # you can sort numerically. Fails the moment _row stringifies.
    conn, _ = _seed(tmp_path / "t.db")
    _, ws = _export_xlsx(conn)
    cells = _xlsx_cells(ws)
    assert cells["my_rating"] == 5
    assert isinstance(cells["my_rating"], int)
    assert cells["external_rating"] == 4.3
    assert isinstance(cells["external_rating"], float)

def test_xlsx_first_purchased_is_a_date_value(tmp_path):
    conn, _ = _seed(tmp_path / "t.db")
    _, ws = _export_xlsx(conn)
    value = _xlsx_cells(ws)["first_purchased"]
    # openpyxl reads dates back as datetime; the date part is what matters
    assert (value.year, value.month, value.day) == (2019, 3, 2)

def test_xlsx_ids_are_written_in_the_callers_order(tmp_path):
    # Same contract as the CSV: the viewer owns the order, so no re-sorting.
    conn, ids = _seed_three(tmp_path / "t.db")
    order = [ids["Unrelated Book"], ids["The Quiet Harbor: A Novel"],
             ids["A Quiet Life in Harbors"]]
    count, ws = _export_xlsx(conn, ids=order)
    assert count == 3
    assert _xlsx_titles(ws) == ["Unrelated Book", "The Quiet Harbor: A Novel",
                                "A Quiet Life in Harbors"]

def test_xlsx_unknown_ids_are_skipped_not_fatal(tmp_path):
    conn, ids = _seed_three(tmp_path / "t.db")
    count, ws = _export_xlsx(conn, ids=[ids["Unrelated Book"], 99999])
    assert count == 1
    assert _xlsx_titles(ws) == ["Unrelated Book"]

def test_xlsx_empty_id_list_is_header_only(tmp_path):
    conn, _ = _seed_three(tmp_path / "t.db")
    count, ws = _export_xlsx(conn, ids=[])
    assert count == 0
    assert ws.max_row == 1
    assert [c.value for c in ws[1]] == list(export.COLUMNS)

def test_xlsx_header_is_frozen_bold_and_filterable(tmp_path):
    # Many columns and hundreds of rows are unreadable without these; the
    # autofilter is what makes the sheet a place to ask questions.
    conn, _ = _seed(tmp_path / "t.db")
    _, ws = _export_xlsx(conn)
    assert ws.freeze_panes == "A2"
    assert all(c.font.bold for c in ws[1])
    assert ws.auto_filter.ref == "A1:T2"  # header + 1 data row, 20 columns

def test_xlsx_date_column_displays_iso(tmp_path):
    # The value is a date (see above); this is the separate question of
    # how Excel renders it. Two independent cell properties.
    conn, _ = _seed(tmp_path / "t.db")
    _, ws = _export_xlsx(conn)
    col = export.COLUMNS.index("first_purchased") + 1
    assert ws.cell(row=2, column=col).number_format == "YYYY-MM-DD"

def test_xlsx_column_widths_are_capped_and_never_below_the_header(tmp_path):
    # An uncapped width lets one long comment stretch a column off-screen.
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, user_comment) "
                 "VALUES ('m', 'A Quiet Life in Harbors', ?)",
                 ("x" * 300,))
    conn.execute("INSERT INTO enrichment (item_id) VALUES (1)")
    conn.commit()
    _, ws = _export_xlsx(conn)
    widths = {c.value: ws.column_dimensions[c.column_letter].width
              for c in ws[1]}
    assert widths["user_comment"] == export.WIDTH_CAP
    # "rating_source" is 13 chars and the row leaves it empty, so the
    # header alone has to hold the column open
    assert widths["rating_source"] >= len("rating_source")

def test_xlsx_survives_control_characters_in_text(tmp_path):
    # openpyxl refuses control characters that SQLite and csv accept, so
    # a scraped comment could 500 the xlsx route while the csv route
    # succeeded. Strip them silently: the alternative is a download that
    # fails over data the catalog legitimately holds.
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, user_comment) "
                 "VALUES ('m', 'A Quiet Life in Harbors', ?)",
                 ("bell\x07 and null\x00 gone",))
    conn.execute("INSERT INTO enrichment (item_id) VALUES (1)")
    conn.commit()
    count, ws = _export_xlsx(conn)
    assert count == 1
    assert _xlsx_cells(ws)["user_comment"] == "bell and null gone"

def test_xlsx_keeps_legal_whitespace(tmp_path):
    # Tab, newline and carriage return are legal in a cell -- stripping
    # them would quietly reformat a multi-line note.
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, user_comment) "
                 "VALUES ('m', 'A Quiet Life in Harbors', ?)",
                 ("line one\nline two",))
    conn.execute("INSERT INTO enrichment (item_id) VALUES (1)")
    conn.commit()
    _, ws = _export_xlsx(conn)
    assert _xlsx_cells(ws)["user_comment"] == "line one\nline two"

def test_columns_normalizes_to_canonical_order(tmp_path):
    # The caller never controls column order: one comprehension is the
    # validator, the de-duplicator and the ordering policy at once.
    assert export._columns(["authors", "title"]) == ("title", "authors")
    assert export._columns(["title", "title"]) == ("title",)

def test_columns_drops_unknown_names(tmp_path):
    assert export._columns(["title", "not_a_column"]) == ("title",)

def test_columns_falls_back_to_everything(tmp_path):
    # None, empty and all-unknown all mean "everything": a zero-column
    # file is never a useful answer.
    assert export._columns(None) == export.COLUMNS
    assert export._columns([]) == export.COLUMNS
    assert export._columns(["nope"]) == export.COLUMNS

def test_csv_writes_only_the_requested_columns(tmp_path):
    conn, _ = _seed(tmp_path / "t.db")
    buf = io.StringIO(newline="")
    count = export.write_csv(conn, buf, columns=["my_rating", "title"])
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert count == 1
    assert rows[0] == ["title", "my_rating"]  # canonical, not requested, order
    assert rows[1] == ["All Systems Red, Vol. 1", "5"]

def test_rows_and_columns_compose(tmp_path):
    # The two axes must not consult each other: rows keep the caller's
    # order, columns get forced into canonical order, in one call.
    conn, item_id = _seed(tmp_path / "t.db")
    other = conn.execute(
        "INSERT INTO items (machine_name, name, type) "
        "VALUES ('qlh', 'A Quiet Life in Harbors', 'ebook')").lastrowid
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (other,))
    conn.commit()
    buf = io.StringIO(newline="")
    count = export.write_csv(conn, buf, ids=[other, item_id],
                             columns=["type", "title"])
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert count == 2
    assert rows[0] == ["title", "type"]
    assert [r[0] for r in rows[1:]] == ["A Quiet Life in Harbors",
                                        "All Systems Red, Vol. 1"]

def test_xlsx_writes_only_the_requested_columns(tmp_path):
    conn, _ = _seed(tmp_path / "t.db")
    buf = io.BytesIO()
    count = export.write_xlsx(conn, buf, columns=["my_rating", "title"])
    ws = load_workbook(io.BytesIO(buf.getvalue())).active
    assert count == 1
    assert [c.value for c in ws[1]] == ["title", "my_rating"]
    # The autofilter has to span the NARROWED last column, not column 19.
    assert ws.auto_filter.ref == "A1:B2"
    # Widths are still computed, and still floored at the header's own
    # width -- the loop walks the sheet's real columns, so narrowing must
    # not have quietly disabled it.
    assert ws.column_dimensions["B"].width >= len("my_rating")

def test_xlsx_without_first_purchased_formats_nothing(tmp_path):
    # The COLUMNS.index landmine: styling must look up the date column in
    # the columns actually being written, and skip it when it is absent.
    conn, _ = _seed(tmp_path / "t.db")
    buf = io.BytesIO()
    export.write_xlsx(conn, buf, columns=["title", "my_rating"])
    ws = load_workbook(io.BytesIO(buf.getvalue())).active
    for row in ws.iter_rows():
        for cell in row:
            assert cell.number_format != "YYYY-MM-DD"

def test_xlsx_date_format_follows_the_column_it_lands_in(tmp_path):
    # first_purchased is COLUMNS index 14; here it is the second column,
    # so a positional assumption would format the wrong cell.
    conn, _ = _seed(tmp_path / "t.db")
    buf = io.BytesIO()
    export.write_xlsx(conn, buf, columns=["title", "first_purchased"])
    ws = load_workbook(io.BytesIO(buf.getvalue())).active
    assert [c.value for c in ws[1]] == ["title", "first_purchased"]
    assert ws.cell(row=2, column=2).value == datetime(2019, 3, 2, 0, 0)
    assert ws.cell(row=2, column=2).number_format == "YYYY-MM-DD"
    assert ws.cell(row=2, column=1).number_format != "YYYY-MM-DD"

def test_xlsx_rows_and_columns_compose(tmp_path):
    conn, item_id = _seed(tmp_path / "t.db")
    other = conn.execute(
        "INSERT INTO items (machine_name, name, type) "
        "VALUES ('qlh', 'A Quiet Life in Harbors', 'ebook')").lastrowid
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (other,))
    conn.commit()
    buf = io.BytesIO()
    count = export.write_xlsx(conn, buf, ids=[other, item_id],
                              columns=["type", "title"])
    ws = load_workbook(io.BytesIO(buf.getvalue())).active
    assert count == 2
    assert [c.value for c in ws[1]] == ["title", "type"]
    assert _xlsx_titles(ws) == ["A Quiet Life in Harbors",
                                "All Systems Red, Vol. 1"]
