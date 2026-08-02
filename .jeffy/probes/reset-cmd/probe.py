"""Known-answer battery for the reset-cmd inventory row.

Covers `humble_catalog/reset.py`: what it wipes, what it preserves, and
the confirmation in front of both.

This is a destructive command, so the cases follow the same rule as the
backup row: assert what SURVIVES, not just that the call returned. The
distinction the module exists for is that some tables are derived and
rebuildable while three are the preserved layer a rebuild reads FROM -
and a reset that took one of those with it would destroy the download
cache and the owner's own ratings, which nothing can re-derive.

Every title is invented, from docs/TEST-DATA.md. Fresh database per case.
"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, reset  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def seeded():
    """A catalog with a row in every table reset touches or preserves."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = db.connect(pathlib.Path(tmp.name))
    conn.execute("INSERT INTO bundles (gamekey, name, url, purchased_at) "
                 "VALUES ('k1','Bundle One','https://e.invalid/k1','2026-01-01')")
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, my_rating, user_tags, "
        "user_comment, read_status) VALUES (?,?,?,?,?,?)",
        ("salt_sextant", "Salt and Sextant", 5,
         db.tags_to_json(["lent out"]), "A note.", "read"))
    item_id = cur.lastrowid
    conn.execute("INSERT INTO enrichment (item_id, genre) VALUES (?,?)",
                 (item_id, db.tags_to_json(["Mystery"])))
    conn.execute("INSERT INTO item_bundles VALUES (?, 'k1')", (item_id,))
    # url is NOT NULL: read the CREATE TABLE before inserting, which is
    # what the Lessons say and what this line cost when it was skipped.
    conn.execute("INSERT INTO downloads (item_id, kind, url, formats) "
                 "VALUES (?, 'humble', 'https://e.invalid/d', 'epub')",
                 (item_id,))
    conn.execute("INSERT INTO external_keys (gamekey, machine_name, "
                 "human_name, key_type) VALUES ('k1','wq','Widget Quest','steam')")
    conn.execute("INSERT INTO merges (dropped_machine_name, kept_item_id) "
                 "VALUES ('dropped_mn', ?)", (item_id,))
    conn.execute("INSERT INTO dismissed_pairs (a, b) VALUES ('a','b')")
    conn.execute("INSERT INTO run_status (command, phase) VALUES ('harvest','x')")
    # The preserved layer.
    conn.execute("INSERT INTO raw_orders (gamekey, fetched_at, json) "
                 "VALUES ('k1','2026-01-01', ?)", (json.dumps({"x": 1}),))
    conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                 "VALUES ('hardcover','salt and sextant','2026-01-01','{}')")
    conn.commit()
    return conn


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def snapshot(conn):
    return {t: count(conn, t) for t in
            (*reset.DERIVED_TABLES, "raw_orders", "source_cache",
             "user_item_data")}


# ------------------------------------------------------------- the wipe

def case_every_derived_table_is_emptied():
    conn = seeded()
    n = reset.run(_conn=conn, _input=lambda _p: "RESET")
    check("the pre-wipe item count is returned", n, 1)
    check("every derived table is empty",
          {t: count(conn, t) for t in reset.DERIVED_TABLES},
          {t: 0 for t in reset.DERIVED_TABLES})
    conn.close()


def case_the_preserved_layer_survives():
    """The distinction the module exists for.

    raw_orders and source_cache are what a rebuild reads FROM, so a reset
    that took them would turn a rebuild into a re-download - or, for a
    bundle since retired, into permanent loss.
    """
    conn = seeded()
    reset.run(_conn=conn, _input=lambda _p: "RESET")
    check("the order cache survives", count(conn, "raw_orders"), 1)
    check("the metadata cache survives", count(conn, "source_cache"), 1)
    conn.close()


def case_the_owners_own_fields_are_snapshotted():
    conn = seeded()
    reset.run(_conn=conn, _input=lambda _p: "RESET")
    row = conn.execute("SELECT * FROM user_item_data").fetchone()
    check("one snapshot row was written", count(conn, "user_item_data"), 1)
    check("keyed by the rebuild-stable machine_name",
          row["machine_name"], "salt_sextant")
    check("carrying the rating", row["my_rating"], 5)
    check("the tags", db.tags_from_json(row["user_tags"]), ["lent out"])
    check("the comment", row["user_comment"], "A note.")
    check("and the read status", row["read_status"], "read")
    conn.close()


def case_a_row_with_nothing_owner_authored_is_not_snapshotted():
    # The WHERE clause: only rows carrying something worth keeping.
    conn = seeded()
    conn.execute("INSERT INTO items (machine_name, name) VALUES (?,?)",
                 ("plain_row", "Unrelated Book"))
    conn.commit()
    reset.run(_conn=conn, _input=lambda _p: "RESET")
    check("only the annotated row is snapshotted",
          [r["machine_name"] for r in
           conn.execute("SELECT machine_name FROM user_item_data")],
          ["salt_sextant"])
    conn.close()


def case_a_cleared_value_cannot_resurrect_from_an_older_snapshot():
    """The documented reason the snapshot DELETEs first.

    Reset once with a rating set, clear the rating, reset again: without
    the DELETE the first snapshot would still be there and the rating
    would come back on the next rebuild.
    """
    conn = seeded()
    reset.run(_conn=conn, _input=lambda _p: "RESET")
    check("the first reset stored the rating",
          conn.execute("SELECT my_rating FROM user_item_data").fetchone()[0], 5)

    # rebuild the row, this time with the rating cleared
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, my_rating, read_status) "
        "VALUES ('salt_sextant','Salt and Sextant', NULL, 'unread')")
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                 (cur.lastrowid,))
    conn.commit()
    reset.run(_conn=conn, _input=lambda _p: "RESET")
    check("the second reset leaves no stale snapshot behind",
          count(conn, "user_item_data"), 0)
    conn.close()


def case_the_wipe_order_satisfies_foreign_keys():
    # The comment says the order is chosen so PRAGMA foreign_keys = ON is
    # always satisfied. Asserted by turning it on and resetting.
    conn = seeded()
    conn.execute("PRAGMA foreign_keys = ON")
    n = reset.run(_conn=conn, _input=lambda _p: "RESET")
    check("the reset completes with foreign keys enforced", n, 1)
    check("and everything derived is gone",
          sum(count(conn, t) for t in reset.DERIVED_TABLES), 0)
    conn.close()


def case_items_and_bundles_come_last_in_the_order():
    # The property that makes the above true, stated directly: every
    # child table is listed before the two it references.
    order = list(reset.DERIVED_TABLES)
    for child in ("item_bundles", "downloads", "external_keys", "enrichment",
                  "merges"):
        check(f"{child} is deleted before items",
              order.index(child) < order.index("items"), True)
    check("and bundles is last", order[-1], "bundles")


def case_the_preserved_tables_are_absent_from_the_wipe_list():
    for table in ("user_item_data", "raw_orders", "source_cache"):
        check(f"{table} is not in DERIVED_TABLES",
              table in reset.DERIVED_TABLES, False)


# ---------------------------------------------------------- the refusals

def case_every_wrong_answer_changes_nothing():
    for answer in ["", "reset", "Reset", "y", "yes", "RESET now", "RESETX"]:
        conn = seeded()
        before = snapshot(conn)
        n = reset.run(_conn=conn, _input=lambda _p, a=answer: a)
        check(f"refused: {answer!r}", n, 0)
        check(f"nothing changed after {answer!r}", snapshot(conn), before)
        conn.close()


def case_the_confirmation_is_stripped_before_comparing():
    conn = seeded()
    n = reset.run(_conn=conn, _input=lambda _p: "  RESET  ")
    check("a padded confirmation is accepted", n, 1)
    conn.close()


def case_ctrl_d_aborts_cleanly():
    def eof(_prompt):
        raise EOFError

    conn = seeded()
    before = snapshot(conn)
    n = reset.run(_conn=conn, _input=eof)
    check("an EOF aborts rather than raising", n, 0)
    check("and wipes nothing", snapshot(conn), before)
    conn.close()


def case_an_empty_catalog_resets_to_zero():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = db.connect(pathlib.Path(tmp.name))
    check("resetting an empty catalog reports zero items",
          reset.run(_conn=conn, _input=lambda _p: "RESET"), 0)
    conn.close()


CASES = [v for k, v in sorted(globals().items()) if k.startswith("case_")]

if __name__ == "__main__":
    for fn in CASES:
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            FAIL.append(fn.__name__)
            print(f"  FAIL {fn.__name__} raised: "
                  f"{type(exc).__name__}: {exc}")
    total = len(PASS) + len(FAIL)
    print(f"reset-cmd: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
