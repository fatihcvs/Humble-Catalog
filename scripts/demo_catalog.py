"""Serve the catalog viewer against a throwaway catalog of INVENTED
titles.

Point any visual check at this rather than the real catalog. A viewer
screenshot shows titles, counts, bundle names, ratings, tags and notes,
and no automated check reads pixels -- `leak_check.py` sees compressed
bytes and `check_no_data_tracked.py` filters paths -- so a screenshot of
the real library passes `verify` without complaint. See the Privacy
section of CLAUDE.md.

Every title here comes from docs/TEST-DATA.md. This file is tracked, so
`leak_check.py` scans it like any other committed text; that is the
point of keeping the demo data in the repo rather than in a scratch file.

    python scripts/demo_catalog.py

Serves on port 8099 -- deliberately not 8087, which `serve` uses and
`stop` targets.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from humble_catalog import db                          # noqa: E402
from humble_catalog.webapp import create_app           # noqa: E402

PORT = 8099

DEMO_BUNDLES = [
    ("bk1", "Humble Book Bundle: Test by Example Press", "2020-03-02"),
    ("au1", "Humble Audiobook Bundle: Epic Tales 2020 by Example Audio",
     "2021-06-14"),
    ("cm1", "Humble Comics Bundle: Shadow Hound", "2022-01-09"),
    ("gm1", "Humble Game Bundle: Samples", "2023-08-21"),
]

# A spread chosen to light up the viewer's surfaces, not just one
# feature: every type, a same-type duplicate pair for the Duplicates
# panel, a low-confidence row for the Review panel, a pair of
# near-titles and an accented one for search, and enough
# ratings/tags/series that the columns are not all empty.
#
# Every title is from docs/TEST-DATA.md.
DEMO_ROWS = [
    # -- a same-type duplicate pair (Duplicates panel) ----------------
    {"mn": "widget_2e", "name": "Building Widget Services 2e",
     "type": "ebook", "bundle": "bk1", "publisher": "Example Press",
     "rating": 4, "genre": ["Programming"], "status": "matched"},
    {"mn": "widget_2nd", "name": "Building Widget Services, 2nd Edition",
     "type": "ebook", "bundle": "bk1", "publisher": "Example Press",
     "status": "matched"},
    # -- a low-confidence row (Review panel) --------------------------
    {"mn": "quiet_harbor", "name": "The Quiet Harbor: A Novel",
     "type": "ebook", "bundle": "bk1", "status": "low_confidence",
     "candidates": [
         {"source": "hardcover", "title": "The Quiet Harbor",
          "authors": ["Alex Penner"], "genre": "Fiction", "series": None,
          "series_number": None, "rating": 4.1, "narrator": None,
          "illustrator": None, "extra": {}, "confidence": 0.72}]},
    # -- search foils: a near-title, and an accent ---------------------
    {"mn": "quiet_life", "name": "A Quiet Life in Harbors", "type": "ebook",
     "bundle": "bk1", "status": "matched"},
    {"mn": "cafe_clocks", "name": "Café of Broken Clocks", "type": "ebook",
     "bundle": "bk1", "rating": 3, "status": "matched"},
    # -- a fully annotated row: rating, tag, note, read status ---------
    {"mn": "unrelated", "name": "Unrelated Book", "type": "ebook",
     "bundle": "bk1", "rating": 2, "tags": ["lent out"],
     "comment": "Borrowed by a friend.", "read_status": "read",
     "status": "matched"},
    # -- audiobooks, one with the full series/narrator set -------------
    {"mn": "axebearer", "name": "Axebearer (Grim & Fell)",
     "type": "audiobook", "bundle": "au1", "rating": 5,
     "genre": ["Fantasy"], "series": "The Elder Realm", "series_number": 1,
     "authors": ["Alex Penner"], "narrator": "Sam Reader",
     "read_status": "read", "status": "matched"},
    {"mn": "starless_war", "name": "The Starless War", "type": "audiobook",
     "bundle": "au1", "genre": ["Science Fiction"],
     "read_status": "reading", "status": "matched"},
    # -- comics, one with an illustrator ------------------------------
    {"mn": "shadowhound_v1", "name": "Shadow Hound Vol 1", "type": "comic",
     "bundle": "cm1", "publisher": "Example Comics", "genre": ["Manga"],
     "authors": ["Bo Writer"], "illustrator": "Alex Artist",
     "read_status": "want_to_read", "status": "matched"},
    {"mn": "moonfall_v1", "name": "MOONFALL, Vol. 1", "type": "comic",
     "bundle": "cm1", "status": "matched"},
    # -- android and music --------------------------------------------
    {"mn": "cooltower_android", "name": "Cool Tower Defense",
     "type": "android", "bundle": "gm1", "publisher": "Indie Dev Co",
     "status": "matched"},
    {"mn": "cooltower_ost", "name": "Sample Game OST", "type": "music",
     "bundle": "gm1", "status": "matched"},
    {"mn": "some_album", "name": "Some Album", "type": "music",
     "bundle": "gm1", "status": "matched"},
]


def seed(db_path):
    """Build a demo catalog at `db_path`, replacing any existing rows.

    Rerunnable: main() reuses one temp path, so a second run must not
    trip the machine_name UNIQUE constraint.
    """
    conn = db.connect(db_path)
    # Child-first, so foreign keys stay satisfied while emptying.
    for table in ("item_bundles", "enrichment", "items", "bundles"):
        conn.execute(f"DELETE FROM {table}")
    for gamekey, name, purchased in DEMO_BUNDLES:
        conn.execute(
            "INSERT INTO bundles (gamekey, name, url, purchased_at) "
            "VALUES (?,?,?,?)",
            (gamekey, name, f"https://example.invalid/{gamekey}", purchased))
    for row in DEMO_ROWS:
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type, publisher, "
            "my_rating, user_tags, user_comment, read_status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (row["mn"], row["name"], row["type"], row.get("publisher"),
             row.get("rating"), db.tags_to_json(row.get("tags")),
             row.get("comment"), row.get("read_status", "unread")))
        item_id = cur.lastrowid
        conn.execute("INSERT INTO item_bundles (item_id, gamekey) VALUES (?,?)",
                     (item_id, row["bundle"]))
        conn.execute(
            "INSERT INTO enrichment (item_id, genre, series, series_number, "
            "authors, narrator, illustrator, status, candidates) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            # narrator and illustrator are in db.TAG_FIELDS, so they are
            # JSON arrays like genre and authors -- not the plain TEXT
            # their singular names suggest. tags_to_json wraps a bare
            # string as a one-entry list.
            (item_id, db.tags_to_json(row.get("genre")), row.get("series"),
             row.get("series_number"), db.tags_to_json(row.get("authors")),
             db.tags_to_json(row.get("narrator")),
             db.tags_to_json(row.get("illustrator")),
             row.get("status", "matched"),
             json.dumps(row["candidates"]) if row.get("candidates") else None))
    conn.commit()
    conn.close()


def main():
    # A fixed name inside the system temp directory: stable enough to
    # reopen between runs, and never beside catalog.db, where a stray
    # demo.db would sit outside .gitignore's `catalog.db*` rule.
    db_path = Path(tempfile.gettempdir()) / "humble-catalog-demo.db"
    seed(db_path)
    print(f"Demo catalog: {db_path}")
    print(f"Serving {len(DEMO_ROWS)} invented items on "
          f"http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    # covers_dir points at a directory with no files, so every row draws
    # its blank-cover state rather than reaching the real covers/.
    create_app(db_path=str(db_path),
               covers_dir=str(Path(tempfile.gettempdir()) /
                              "humble-catalog-demo-covers")
               ).run(host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
