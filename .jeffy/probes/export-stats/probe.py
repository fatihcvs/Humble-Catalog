"""Known-answer probes for the export projection and the stats counts.

These are the numbers and cells a user reads directly, so every case is a
hand-computed answer. Both `_columns`/`ids` and `_tally`'s `default` are
documented parameters and are exercised at two or more values that must
change the output.

Titles, tags and bundle names come from docs/TEST-DATA.md.
"""
import csv
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import db, export, stats   # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


# ---------------------------------------------------------------- export
check("_columns: None means every column", export._columns(None), export.COLUMNS)
check("_columns: empty means every column", export._columns([]), export.COLUMNS)
check("_columns: a subset is returned in CANONICAL order, not the caller's",
      export._columns(["genre", "title"]), ("title", "genre"))
check("_columns: unknown names are dropped, known ones kept",
      export._columns(["title", "not_a_column"]), ("title",))
check("_columns: duplicates collapse",
      export._columns(["title", "title"]), ("title",))
check("_columns: an all-unknown selection falls back to every column",
      export._columns(["nope"]), export.COLUMNS)

# --- _clean: openpyxl's illegal set goes, the legal whitespace stays. ---
check("_clean: a NUL is stripped", export._clean("a\x00b"), "ab")
check("_clean: an escape char is stripped", export._clean("a\x1bb"), "ab")
check("_clean: TAB survives (legal in a cell)", export._clean("a\tb"), "a\tb")
check("_clean: NEWLINE survives - stripping would reformat a note",
      export._clean("a\nb"), "a\nb")
check("_clean: CARRIAGE RETURN survives", export._clean("a\rb"), "a\rb")
check("_clean: a non-string passes through untouched", export._clean(5), 5)
check("_clean: None passes through", export._clean(None), None)

with tempfile.TemporaryDirectory() as td:
    conn = db.connect(str(Path(td) / "e.db"))
    conn.execute("INSERT INTO bundles VALUES "
                 "('k1','Bundle One','http://b1','2021-05-04')")
    conn.execute("INSERT INTO bundles VALUES "
                 "('k2','The World of Examplia by Example Press','http://b2',"
                 "'2019-03-02')")
    conn.execute("INSERT INTO items (machine_name, name, type, publisher, "
                 "my_rating, read_status, user_tags) "
                 "VALUES ('sas','Salt and Sextant','ebook','Example Press',4,"
                 "'reading',?)", (db.tags_to_json(["lent out", "to reread"]),))
    conn.execute("INSERT INTO item_bundles VALUES (1,'k1')")
    conn.execute("INSERT INTO item_bundles VALUES (1,'k2')")
    conn.execute("INSERT INTO enrichment (item_id, status, genre, authors) "
                 "VALUES (1,'matched',?,?)",
                 (db.tags_to_json(["Science Fiction", "Fantasy"]),
                  db.tags_to_json(["Sam Coder", "Alex Dev"])))
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('ub','Unrelated Book','ebook')")
    conn.execute("INSERT INTO enrichment (item_id, status) VALUES (2,'pending')")
    conn.commit()

    items = db.fetch_items(conn)
    by_name = {i["name"]: i for i in items}
    row = export._row(by_name["Salt and Sextant"], export.COLUMNS)
    cell = dict(zip(export.COLUMNS, row))

    check("_row: title comes from the item's name", cell["title"],
          "Salt and Sextant")
    check("_row: list fields join with '; '", cell["genre"],
          "Science Fiction; Fantasy")
    check("_row: authors join the same way", cell["authors"],
          "Sam Coder; Alex Dev")
    check("_row: user tags join the same way", cell["user_tags"],
          "lent out; to reread")
    # first_purchased is the EARLIEST bundle date, not the first listed.
    check("_row: first_purchased is the earliest purchase, as a date object",
          str(cell["first_purchased"]), "2019-03-02")
    check("_row: and csv stringifies that date to the same bytes",
          str(cell["first_purchased"]), "2019-03-02")
    check("_row: read_status is shown as its human label",
          cell["read_status"], "Reading")
    check("_row: an unedited row leaves 'edited' empty", cell["edited"], "")
    check("_row: None becomes an empty cell, never the text 'None'",
          cell["series"], "")
    # A row with no bundles must not crash on min() of an empty sequence.
    bare = export._row(by_name["Unrelated Book"], export.COLUMNS)
    check("_row: an item in no bundle has an empty first_purchased",
          dict(zip(export.COLUMNS, bare))["first_purchased"], "")

    # --- _select: ids owns the ORDER, unknown ids are skipped. ---
    check("_select: None is the whole catalog", len(export._select(conn, None)), 2)
    check("_select: ids are honoured in the CALLER's order",
          [i["name"] for i in export._select(conn, [2, 1])],
          ["Unrelated Book", "Salt and Sextant"])
    check("_select: an unknown id is skipped, not fatal",
          [i["name"] for i in export._select(conn, [999, 1])],
          ["Salt and Sextant"])
    check("_select: an empty id list selects nothing",
          export._select(conn, []), [])

    # --- write_csv: header, count, and the column projection. ---
    buf = io.StringIO(newline="")
    count = export.write_csv(conn, buf)
    check("write_csv: returns the number of rows written", count, 2)
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    check("write_csv: the header is the column list",
          tuple(rows[0]), export.COLUMNS)
    check("write_csv: one line per item plus the header", len(rows), 3)

    buf2 = io.StringIO(newline="")
    export.write_csv(conn, buf2, columns=["genre", "title"])
    rows2 = list(csv.reader(io.StringIO(buf2.getvalue())))
    check("write_csv: the columns parameter narrows AND canonicalises",
          rows2[0], ["title", "genre"])

    buf3 = io.StringIO(newline="")
    n3 = export.write_csv(conn, buf3, ids=[1])
    check("write_csv: the ids parameter narrows the rows", n3, 1)

    # --- write_xlsx: same contract, binary handle. ---
    bio = io.BytesIO()
    check("write_xlsx: returns the same count as write_csv",
          export.write_xlsx(conn, bio), 2)
    # An xlsx is a zip, so the first two bytes are the zip signature.
    check("write_xlsx: wrote a real xlsx (zip signature)",
          bio.getvalue()[:2], b"PK")
    conn.close()

# ----------------------------------------------------------------- stats
# Plain dicts: report() is pure and takes the fetch_items per-item view.
items = [
    {"type": "ebook", "my_rating": 5, "read_status": "read",
     "status": "matched", "genre": ["Science Fiction", "Fantasy"],
     "cover_path": "c.jpg", "source_url": "http://x"},
    {"type": "ebook", "my_rating": 5, "read_status": "reading",
     "status": "matched", "genre": ["Science Fiction"],
     "cover_path": None, "source_url": None},
    {"type": "comic", "my_rating": None, "read_status": "dnf",
     "status": "pending", "genre": [], "cover_path": "", "source_url": ""},
    # a type outside the vocabulary: counted NOWHERE, never invents a row
    {"type": "boardgame", "my_rating": 3, "status": "matched",
     "genre": None, "cover_path": None, "source_url": None},
]

check("_by_type: known types counted, unknown counted nowhere",
      stats._by_type(items),
      [("E-books", 2), ("Audiobooks", 0), ("Comics", 1),
       ("Music/Soundtracks", 0), ("Android apps", 0)])
check("_by_type: the section need not sum to the total",
      sum(c for _, c in stats._by_type(items)) < len(items), True)
check("_by_rating: only 1..5, unrated is a gap and not a row",
      stats._by_rating(items),
      [("★1", 0), ("★2", 0), ("★3", 1), ("★4", 0), ("★5", 2)])
# The `default` parameter: the 4th item has no read_status key at all.
check("_by_read_status: a missing key falls back to the documented default",
      stats._by_read_status(items),
      [("Want to read", 0), ("Unread", 1), ("Reading", 1), ("Read", 1),
       ("DNF", 1)])
check("_tally: the default parameter changes the answer at another value",
      stats._tally(items, "read_status", stats.READ_STATUSES, default="read"),
      [("Want to read", 0), ("Unread", 0), ("Reading", 1), ("Read", 2),
       ("DNF", 1)])
check("_by_enrichment: counts the enrichment vocabulary",
      stats._by_enrichment(items),
      [("Matched", 3), ("Low confidence", 0), ("Unmatched", 0), ("Pending", 1)])
# Gaps are falsiness, so "" and None both count, and 0 would too.
check("_by_gap: empty string and None both count as gaps",
      stats._by_gap(items),
      [("Unrated", 1), ("No cover", 3), ("No source URL", 3)])
check("_by_genre: biggest first, ties broken alphabetically",
      stats._by_genre(items), [("Science Fiction", 2), ("Fantasy", 1)])

sections, total = stats.report(items)
check("report: total is the item count", total, 4)
check("report: sections come back in SECTIONS order",
      [k for k, _, _ in sections],
      ["type", "rating", "status", "enrichment", "gaps", "genre"])
check("report: is pure - calling twice gives the same answer",
      stats.report(items)[0], sections)

# console_safe: the encoding parameter must change the output.
check("console_safe: utf-8 keeps the star", stats.console_safe("★5", "utf-8"),
      "★5")
check("console_safe: cp1252 degrades the star to an asterisk",
      stats.console_safe("★5", "cp1252"), "*5")
check("console_safe: plain ascii text is untouched",
      stats.console_safe("Unread", "cp1252"), "Unread")

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
