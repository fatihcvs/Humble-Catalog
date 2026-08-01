"""Known-answer probes for apply_hand_edit and merge_items.

These two write paths are irreversible in different ways: apply_hand_edit's
pre_edit snapshot is the ONLY revert target, and merge_items deletes a row
outright. Each case states the answer the docstring promises. Titles and
tags come from docs/TEST-DATA.md.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import db   # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


_seq = [0]


def fresh(td, n):
    """A catalog with n items, each with an enrichment row.

    A fresh FILE every call - reusing one would carry the previous case's
    rows into the next and trip the machine_name UNIQUE constraint.
    """
    _seq[0] += 1
    dbp = str(Path(td) / f"probe{_seq[0]}.db")
    conn = db.connect(dbp)
    names = [("sas", "Salt and Sextant"), ("ub", "Unrelated Book"),
             ("gw", "Gray Waters")]
    for i, (mn, name) in enumerate(names[:n], start=1):
        conn.execute("INSERT INTO items (machine_name, name, type) "
                     "VALUES (?,?,'ebook')", (mn, name))
        conn.execute("INSERT INTO enrichment (item_id, status) VALUES (?,?)",
                     (i, "matched"))
    conn.commit()
    return conn


with tempfile.TemporaryDirectory() as td:
    # --- apply_hand_edit ---
    conn = fresh(td, 1)
    conn.execute("UPDATE enrichment SET series=?, series_number=? "
                 "WHERE item_id=1", ("The Elder Realm", 1.0))
    conn.commit()

    check("apply_hand_edit: missing item -> False",
          db.apply_hand_edit(conn, 9999, {"series": "X"}), False)

    check("apply_hand_edit: first edit -> True",
          db.apply_hand_edit(conn, 1, {"series": "Shadow Hound Legends"}), True)
    row = conn.execute("SELECT series, hand_edited, pre_edit FROM enrichment "
                       "WHERE item_id=1").fetchone()
    check("apply_hand_edit: the new value is stored", row["series"],
          "Shadow Hound Legends")
    check("apply_hand_edit: the row is marked hand_edited", row["hand_edited"], 1)
    snap = json.loads(row["pre_edit"])
    check("apply_hand_edit: the snapshot holds the PRE-edit value",
          snap["series"], "The Elder Realm")
    check("apply_hand_edit: the snapshot covers every editable field",
          sorted(snap) == sorted(db.EDITABLE_FIELDS), True)
    check("apply_hand_edit: untouched fields are snapshotted at their value",
          snap["series_number"], 1.0)

    # The snapshot is taken ONCE. A second edit must not overwrite it, or
    # revert would return to the first edit instead of to the enriched
    # state -- the original would be unrecoverable.
    db.apply_hand_edit(conn, 1, {"series": "A Second Typo"})
    snap2 = json.loads(conn.execute(
        "SELECT pre_edit FROM enrichment WHERE item_id=1").fetchone()[0])
    check("apply_hand_edit: a second edit does NOT re-snapshot",
          snap2["series"], "The Elder Realm")
    conn.close()

    # --- merge_items: refusals ---
    conn = fresh(td, 2)
    check("merge_items: equal ids -> False", db.merge_items(conn, 1, 1), False)
    check("merge_items: missing keep -> False",
          db.merge_items(conn, 9999, 1), False)
    check("merge_items: missing drop -> False",
          db.merge_items(conn, 1, 9999), False)
    check("merge_items: a refused merge deleted nothing",
          conn.execute("SELECT COUNT(*) FROM items").fetchone()[0], 2)
    conn.close()

    # --- merge_items: the fill-if-empty and union rules ---
    conn = fresh(td, 2)
    conn.execute("INSERT INTO bundles VALUES ('k1','Bundle One','http://b1','2020-01-01')")
    conn.execute("INSERT INTO item_bundles VALUES (2, 'k1')")
    # survivor has a rating, no publisher; dropped has a publisher and a
    # rating that must NOT overwrite the survivor's
    conn.execute("UPDATE items SET my_rating=5, user_tags=? WHERE id=1",
                 (db.tags_to_json(["lent out"]),))
    conn.execute("UPDATE items SET my_rating=2, publisher=?, user_tags=? "
                 "WHERE id=2", ("Example Press", db.tags_to_json(["to reread"])))
    conn.execute("UPDATE enrichment SET series=? WHERE item_id=2",
                 ("The Elder Realm",))
    conn.commit()

    check("merge_items: a valid merge -> True", db.merge_items(conn, 1, 2), True)
    keep = conn.execute("SELECT * FROM items WHERE id=1").fetchone()
    check("merge_items: the survivor's set field is NOT overwritten",
          keep["my_rating"], 5)
    check("merge_items: the survivor's EMPTY field fills from the dropped row",
          keep["publisher"], "Example Press")
    # user_tags unions rather than fill-if-empty, because a merge is
    # irreversible and hand-typed tags would be unrecoverable.
    check("merge_items: user_tags UNION, not fill-if-empty",
          db.tags_from_json(keep["user_tags"]), ["lent out", "to reread"])
    check("merge_items: enrichment fills from the dropped row too",
          conn.execute("SELECT series FROM enrichment WHERE item_id=1")
          .fetchone()[0], "The Elder Realm")
    check("merge_items: the dropped item row is gone",
          conn.execute("SELECT COUNT(*) FROM items WHERE id=2").fetchone()[0], 0)
    check("merge_items: the dropped enrichment row is gone",
          conn.execute("SELECT COUNT(*) FROM enrichment WHERE item_id=2")
          .fetchone()[0], 0)
    check("merge_items: the dropped row's bundle moved to the survivor",
          conn.execute("SELECT gamekey FROM item_bundles WHERE item_id=1")
          .fetchone()[0], "k1")
    check("merge_items: a tombstone stops the next extract resurrecting it",
          conn.execute("SELECT kept_item_id FROM merges "
                       "WHERE dropped_machine_name='ub'").fetchone()[0], 1)
    conn.close()

    # --- fetch_items: the shared read path for the viewer and both exports ---
    conn = fresh(td, 1)
    conn.execute("UPDATE items SET my_rating=4 WHERE id=1")
    conn.execute("UPDATE enrichment SET genre=? WHERE item_id=1",
                 (db.tags_to_json(["Science Fiction"]),))
    conn.commit()
    rows = db.fetch_items(conn)
    check("fetch_items: returns one row per item", len(rows), 1)
    check("fetch_items: carries the item's own columns", rows[0]["name"],
          "Salt and Sextant")
    check("fetch_items: carries enrichment columns", rows[0]["my_rating"], 4)
    check("fetch_items: tag columns arrive decoded, not as JSON text",
          rows[0]["genre"], ["Science Fiction"])
    conn.close()

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
