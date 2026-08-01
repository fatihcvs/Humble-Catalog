"""Known-answer probes for the managed tag vocabulary in db.py.

Every answer here is the one the function's own docstring promises. The
`col` parameter is exercised at both its values (GENRE titleizes, USER_TAGS
does not) and `action` at both of its, because a documented parameter whose
value changes nothing is a finding. Tags and titles come from the canonical
invented universe in docs/TEST-DATA.md.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import db   # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


# --- tags_to_json / tags_from_json: pure, no connection needed. ---
check("tags_to_json: trims entries", db.tags_to_json(["  Fantasy  "]),
      '["Fantasy"]')
check("tags_to_json: drops empties", db.tags_to_json(["Fantasy", "", "   "]),
      '["Fantasy"]')
check("tags_to_json: drops exact duplicates, order kept",
      db.tags_to_json(["Manga", "Fantasy", "Manga"]), '["Manga", "Fantasy"]')
check("tags_to_json: a bare string wraps as one tag",
      db.tags_to_json("Fantasy"), '["Fantasy"]')
check("tags_to_json: None -> NULL", db.tags_to_json(None), None)
check("tags_to_json: empty string -> NULL", db.tags_to_json(""), None)
check("tags_to_json: everything dropped -> NULL", db.tags_to_json(["", " "]),
      None)
check("tags_to_json: non-ascii is kept literal, not escaped",
      db.tags_to_json(["Café"]), '["Café"]')
check("tags_from_json: NULL -> []", db.tags_from_json(None), [])
check("tags_from_json: empty -> []", db.tags_from_json(""), [])
check("tags_from_json: round-trips tags_to_json",
      db.tags_from_json(db.tags_to_json(["Manga", "Fantasy"])),
      ["Manga", "Fantasy"])

# --- titleize: first letter of each space-separated word only. ---
check("titleize: lowercases nothing else (acronym survives)",
      db.titleize("RPG supplements"), "RPG Supplements")
check("titleize: plain words", db.titleize("science fiction"),
      "Science Fiction")
check("titleize: already capitalized is unchanged",
      db.titleize("Science Fiction"), "Science Fiction")
check("titleize: inner capitals survive", db.titleize("k.d. lang"),
      "K.d. Lang")

with tempfile.TemporaryDirectory() as td:
    dbp = str(Path(td) / "probe.db")
    conn = db.connect(dbp)
    for n, (mn, name) in enumerate([("sas", "Salt and Sextant"),
                                    ("ub", "Unrelated Book"),
                                    ("gw", "Gray Waters")], start=1):
        conn.execute("INSERT INTO items (machine_name, name, type) "
                     "VALUES (?,?,'ebook')", (mn, name))
        conn.execute("INSERT INTO enrichment (item_id, status) VALUES (?,?)",
                     (n, "matched"))
    conn.commit()

    # Seed a genre vocabulary with a deliberate spelling: "Science Fiction".
    conn.execute("UPDATE enrichment SET genre=? WHERE item_id=1",
                 (db.tags_to_json(["Science Fiction"]),))
    conn.commit()

    # --- normalize_tags: snap to the existing spelling, case-insensitively. ---
    check("normalize_tags: snaps to the vocabulary spelling",
          db.normalize_tags(conn, db.GENRE, ["science fiction"]),
          ["Science Fiction"])
    check("normalize_tags: an unknown tag is titleized for GENRE",
          db.normalize_tags(conn, db.GENRE, ["space opera"]), ["Space Opera"])
    # The col parameter must change the outcome, not merely be accepted.
    check("normalize_tags: USER_TAGS does NOT titleize (col matters)",
          db.normalize_tags(conn, db.USER_TAGS, ["lent out"]), ["lent out"])
    check("normalize_tags: dedupes case-insensitively, order kept",
          db.normalize_tags(conn, db.GENRE, ["Manga", "manga", "Fantasy"]),
          ["Manga", "Fantasy"])
    check("normalize_tags: bare string accepted",
          db.normalize_tags(conn, db.GENRE, "manga"), ["Manga"])
    check("normalize_tags: None -> []", db.normalize_tags(conn, db.GENRE, None),
          [])
    check("normalize_tags: blank entries dropped",
          db.normalize_tags(conn, db.GENRE, ["", "  "]), [])

    # --- rename_tag: returns rows changed, or None for an unknown tag. ---
    conn.execute("UPDATE enrichment SET genre=? WHERE item_id=2",
                 (db.tags_to_json(["Manga"]),))
    conn.commit()
    check("rename_tag: unknown tag -> None",
          db.rename_tag(conn, db.GENRE, "Nonexistent Genre", "Whatever"), None)
    check("rename_tag: blank new -> None",
          db.rename_tag(conn, db.GENRE, "Manga", "   "), None)
    # The rename target is a deliberately invented genre, not a real one:
    # leak_check matches substrings, and a plausible genre name can collide
    # with the owner's private library. See the Lessons in PLAN.md.
    check("rename_tag: renames and reports the row count",
          db.rename_tag(conn, db.GENRE, "manga", "invented genre"), 1)
    check("rename_tag: the new spelling is titleized for GENRE",
          db.tags_from_json(conn.execute(
              "SELECT genre FROM enrichment WHERE item_id=2").fetchone()[0]),
          ["Invented Genre"])
    # A rename is explicitly NOT a hand edit.
    check("rename_tag: hand_edited is untouched",
          conn.execute("SELECT hand_edited FROM enrichment WHERE item_id=2")
          .fetchone()[0], 0)

    # Renaming onto an existing tag must merge, and the array must dedupe.
    conn.execute("UPDATE enrichment SET genre=? WHERE item_id=3",
                 (db.tags_to_json(["Science Fiction", "Space Opera"]),))
    conn.commit()
    db.rename_tag(conn, db.GENRE, "Space Opera", "Science Fiction")
    check("rename_tag: renaming onto an existing tag merges and dedupes",
          db.tags_from_json(conn.execute(
              "SELECT genre FROM enrichment WHERE item_id=3").fetchone()[0]),
          ["Science Fiction"])

    # --- rename/delete must rewrite pre_edit snapshots too (GENRE.snapshot),
    # or a revert would resurrect the old spelling. ---
    import json as _json
    conn.execute("UPDATE enrichment SET genre=?, pre_edit=? WHERE item_id=1",
                 (db.tags_to_json(["Science Fiction"]),
                  _json.dumps({"genre": db.tags_to_json(["Science Fiction"])})))
    conn.commit()
    db.rename_tag(conn, db.GENRE, "Science Fiction", "SF")
    _pre = _json.loads(conn.execute(
        "SELECT pre_edit FROM enrichment WHERE item_id=1").fetchone()[0])
    check("rename_tag: the pre_edit snapshot is rewritten too",
          db.tags_from_json(_pre["genre"]), ["SF"])

    # --- delete_tag ---
    check("delete_tag: unknown tag -> None",
          db.delete_tag(conn, db.GENRE, "Nonexistent Genre"), None)
    db.delete_tag(conn, db.GENRE, "sf")
    check("delete_tag: an emptied array stores as NULL, not '[]'",
          conn.execute("SELECT genre FROM enrichment WHERE item_id=1")
          .fetchone()[0], None)
    check("delete_tag: the snapshot copy is dropped too",
          db.tags_from_json(_json.loads(conn.execute(
              "SELECT pre_edit FROM enrichment WHERE item_id=1").fetchone()[0]
          )["genre"]), [])

    # --- bulk_user_tag: returns the ids ACTUALLY changed. ---
    check("bulk_user_tag: add reports every id it changed",
          db.bulk_user_tag(conn, [1, 2, 3], "lent out", "add"), [1, 2, 3])
    check("bulk_user_tag: re-adding changes nothing and reports nothing",
          db.bulk_user_tag(conn, [1, 2, 3], "lent out", "add"), [])
    check("bulk_user_tag: a second casing snaps to the first spelling",
          db.tags_from_json(conn.execute(
              "SELECT user_tags FROM items WHERE id=1").fetchone()[0]),
          ["lent out"])
    db.bulk_user_tag(conn, [1], "Lent Out", "add")
    check("bulk_user_tag: the snap really prevented a second casing",
          db.tags_from_json(conn.execute(
              "SELECT user_tags FROM items WHERE id=1").fetchone()[0]),
          ["lent out"])
    # The action parameter must change the outcome.
    check("bulk_user_tag: remove reports the ids it changed",
          db.bulk_user_tag(conn, [1, 2], "lent out", "remove"), [1, 2])
    check("bulk_user_tag: removing an absent tag reports nothing",
          db.bulk_user_tag(conn, [1, 2], "lent out", "remove"), [])
    check("bulk_user_tag: an emptied array stores as NULL",
          conn.execute("SELECT user_tags FROM items WHERE id=1").fetchone()[0],
          None)
    check("bulk_user_tag: empty id list -> []",
          db.bulk_user_tag(conn, [], "lent out", "add"), [])
    check("bulk_user_tag: blank tag -> []",
          db.bulk_user_tag(conn, [1], "   ", "add"), [])
    try:
        db.bulk_user_tag(conn, [1], "lent out", "toggle")
        check("bulk_user_tag: an unknown action raises ValueError",
              "no exception", "ValueError")
    except ValueError:
        check("bulk_user_tag: an unknown action raises ValueError",
              "ValueError", "ValueError")

    conn.close()

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
