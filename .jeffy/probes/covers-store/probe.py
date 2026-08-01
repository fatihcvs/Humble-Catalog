"""Known-answer probes for covers.cover_filename, covers.relink, store.store_order.

cover_filename turns a third-party string into a path on disk, so the cases
below state the exact name for a fixed input and check that no separator,
drive letter or parent-directory token survives the mapping. relink and
store_order are the write paths that decide whether a rebuild recovers the
owner's data or overwrites it. Every case states the answer the docstring
promises, not the answer the code happens to give. Titles come from
docs/TEST-DATA.md.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import db  # noqa: E402
from humble_catalog.covers import cover_filename, relink  # noqa: E402
from humble_catalog.store import store_order  # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


_seq = [0]


def fresh(td):
    """An empty catalog on a FRESH file every call.

    Reusing one file would carry the previous case's rows into the next and
    trip the machine_name UNIQUE constraint.
    """
    _seq[0] += 1
    conn = db.connect(str(Path(td) / f"probe{_seq[0]}.db"))
    return conn


def order(gamekey, bundle_name, subs, tpks=None):
    """A raw HumbleBundle order in the shape parse_order reads."""
    return {
        "gamekey": gamekey,
        "created": "2020-01-01T00:00:00",
        "product": {"human_name": bundle_name},
        "subproducts": subs,
        "tpkd_dict": {"all_tpks": tpks or []},
    }


def sub(machine_name, human_name, platform="ebook", fmt="epub", icon=None,
        payee="Example Press"):
    return {
        "machine_name": machine_name,
        "human_name": human_name,
        "payee": {"human_name": payee},
        "icon": icon,
        "downloads": [{"platform": platform,
                       "download_struct": [{"name": fmt}]}],
    }


# ---------------------------------------------------------------- filenames
# Literal expected names: these pin stability, which is the whole point of a
# rebuild-stable basename. If the mapping ever changes, every cover on disk
# is orphaned, and that must not happen silently.
check("cover_filename: exact name for a plain key",
      cover_filename("salt_and_sextant"), "salt_and_sextant-510c6a6b257a.jpg")
check("cover_filename: stable across calls",
      cover_filename("salt_and_sextant"), cover_filename("salt_and_sextant"))

# The slug is lossy, so three spellings collapse to one slug. The digest is
# taken from the RAW key, so the three names stay distinct: without it, the
# second cover fetched would overwrite the first.
names = [cover_filename(s) for s in
         ("salt_and_sextant", "Salt and Sextant", "salt and sextant")]
check("cover_filename: casing variants keep one slug",
      [n.split("-")[0] for n in names],
      ["salt_and_sextant"] * 3)
check("cover_filename: casing variants get distinct names",
      len(set(names)), 3)

# Traversal and absolute-path shapes. The assertion is on the RESULT rather
# than on the input class, so a future mapping change is judged by whether
# the output is still a bare basename.
for hostile, label in [("../../../etc/passwd", "posix parent traversal"),
                       ("..\\..\\windows\\system32", "windows parent traversal"),
                       ("/etc/passwd", "posix absolute"),
                       ("C:\\Windows\\notes", "windows drive-absolute"),
                       ("a/b/c", "bare separators"),
                       ("...", "dot run"),
                       ("cover\x00.png", "embedded NUL"),
                       ("cover\nname", "embedded newline")]:
    got = cover_filename(hostile)
    check(f"cover_filename: {label} yields a bare basename",
          Path(got).name, got)
    check(f"cover_filename: {label} keeps only allowed characters",
          set(got[:-4]) - set("abcdefghijklmnopqrstuvwxyz0123456789_-"), set())

check("cover_filename: traversal maps to underscores, exact name",
      cover_filename("../../../etc/passwd"), "_________etc_passwd-43a77a15d11f.jpg")
check("cover_filename: a Windows reserved name is never bare",
      cover_filename("con"), "con-64f7f592f584.jpg")
check("cover_filename: non-ASCII is folded, not passed through",
      cover_filename("Caf\u00e9 of Broken Clocks"),
      "caf__of_broken_clocks-a28ac456e9fa.jpg")
check("cover_filename: an empty key still yields a usable name",
      cover_filename(""), "-ddd9c40767f9.jpg")

with tempfile.TemporaryDirectory() as td:
    # ------------------------------------------------------------- relink
    # covers_dir is relink's one parameter besides the connection: exercised
    # at two values that must change the answer.
    conn = fresh(td)
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('sas','Salt and Sextant','ebook')")
    conn.execute("INSERT INTO items (machine_name, name, type, cover_path) "
                 "VALUES ('ub','Unrelated Book','ebook','covers/already.jpg')")
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('gw','Gray Waters','ebook')")
    conn.commit()

    empty_dir = Path(td) / "empty"
    empty_dir.mkdir()
    check("relink: no files on disk re-links nothing", relink(conn, empty_dir), 0)

    full_dir = Path(td) / "full"
    full_dir.mkdir()
    (full_dir / cover_filename("sas")).write_bytes(b"x")
    # A file for an item that already HAS a path: relink must not count it.
    (full_dir / cover_filename("ub")).write_bytes(b"x")
    check("relink: same catalog, a directory holding one match re-links it",
          relink(conn, full_dir), 1)
    check("relink: the re-linked row gets the covers/ prefixed name",
          conn.execute("SELECT cover_path FROM items WHERE machine_name='sas'"
                       ).fetchone()["cover_path"],
          f"covers/{cover_filename('sas')}")
    check("relink: an item that already had a path keeps it",
          conn.execute("SELECT cover_path FROM items WHERE machine_name='ub'"
                       ).fetchone()["cover_path"], "covers/already.jpg")
    check("relink: an item with no file on disk stays unlinked",
          conn.execute("SELECT cover_path FROM items WHERE machine_name='gw'"
                       ).fetchone()["cover_path"], None)
    check("relink: re-running finds nothing left to do", relink(conn, full_dir), 0)
    check("relink: accepts a string path as well as a Path",
          relink(conn, str(full_dir)), 0)
    conn.close()

    # ---------------------------------------------------------- store_order
    conn = fresh(td)
    store_order(conn, order("abc123", "Humble Book Bundle: Test by Example Press",
                            [sub("sas", "Salt and Sextant", icon="http://x/1.jpg"),
                             sub("gw", "Gray Waters")]))
    check("store_order: the bundle row is written",
          conn.execute("SELECT name FROM bundles WHERE gamekey='abc123'"
                       ).fetchone()["name"],
          "Humble Book Bundle: Test by Example Press")
    check("store_order: one item row per qualifying subproduct",
          conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"], 2)
    check("store_order: every new item gets an enrichment row",
          conn.execute("SELECT COUNT(*) c FROM enrichment").fetchone()["c"], 2)
    check("store_order: the publisher comes from the payee",
          conn.execute("SELECT publisher FROM items WHERE machine_name='sas'"
                       ).fetchone()["publisher"], "Example Press")
    check("store_order: one download row per item for this bundle",
          conn.execute("SELECT COUNT(*) c FROM downloads").fetchone()["c"], 2)

    # Idempotence is the contract reparse rests on: the same order stored
    # twice must leave the catalog identical, not doubled.
    store_order(conn, order("abc123", "Humble Book Bundle: Test by Example Press",
                            [sub("sas", "Salt and Sextant", icon="http://x/1.jpg"),
                             sub("gw", "Gray Waters")]))
    check("store_order: re-storing the same order adds no item",
          conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"], 2)
    check("store_order: re-storing the same order adds no download row",
          conn.execute("SELECT COUNT(*) c FROM downloads").fetchone()["c"], 2)
    check("store_order: re-storing the same order adds no bundle link",
          conn.execute("SELECT COUNT(*) c FROM item_bundles").fetchone()["c"], 2)

    # A second bundle carrying the same item links, it does not duplicate.
    store_order(conn, order("def456", "Bundle One",
                            [sub("sas", "Salt and Sextant")]))
    check("store_order: an item in two bundles stays one item",
          conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"], 2)
    check("store_order: an item in two bundles gets two bundle links",
          conn.execute("SELECT COUNT(*) c FROM item_bundles WHERE item_id="
                       "(SELECT id FROM items WHERE machine_name='sas')"
                       ).fetchone()["c"], 2)
    conn.close()

    # Platform filtering: a subproduct with no ebook/audio/android platform is
    # not an item at all. The negative side of the same parameter.
    conn = fresh(td)
    store_order(conn, order("g1", "Humble Game Bundle: Samples",
                            [sub("winonly", "Widget Quest", platform="windows")]))
    check("store_order: a non-book platform yields no item",
          conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"], 0)
    check("store_order: the bundle row is written even with no items",
          conn.execute("SELECT COUNT(*) c FROM bundles").fetchone()["c"], 1)
    conn.close()

    # Type resolution across bundles. 'ebook' is the no-evidence default, so
    # it must never demote a comic, in either arrival order.
    conn = fresh(td)
    store_order(conn, order("c1", "Humble Comics Bundle: Shadow Hound",
                            [sub("nj", "Nightjar Post", fmt="cbz")]))
    first = conn.execute("SELECT type FROM items WHERE machine_name='nj'"
                         ).fetchone()["type"]
    store_order(conn, order("b1", "Humble Book Bundle: Test by Example Press",
                            [sub("nj", "Nightjar Post", fmt="epub")]))
    check("store_order: a comic classification is reached first", first, "comic")
    check("store_order: a later ebook bundle does not demote a comic",
          conn.execute("SELECT type FROM items WHERE machine_name='nj'"
                       ).fetchone()["type"], "comic")

    # type_overridden is the owner's decision and outranks any bundle.
    conn.execute("UPDATE items SET type='ebook', type_overridden=1 "
                 "WHERE machine_name='nj'")
    conn.commit()
    store_order(conn, order("c2", "Humble Comics Bundle: Shadow Hound",
                            [sub("nj", "Nightjar Post", fmt="cbz")]))
    check("store_order: an owner override survives a re-store",
          conn.execute("SELECT type FROM items WHERE machine_name='nj'"
                       ).fetchone()["type"], "ebook")
    conn.close()

    # ------------------------------------------------- merge tombstone
    conn = fresh(td)
    store_order(conn, order("abc123", "Humble Book Bundle: Test by Example Press",
                            [sub("sas", "Salt and Sextant")]))
    kept = conn.execute("SELECT id FROM items WHERE machine_name='sas'"
                        ).fetchone()["id"]
    conn.execute("INSERT INTO merges (dropped_machine_name, kept_item_id) "
                 "VALUES ('sas_dup', ?)", (kept,))
    conn.commit()
    store_order(conn, order("xyz789", "Bundle One",
                            [sub("sas_dup", "Salt and Sextant 2e")]))
    check("store_order: a merged-away key does not resurrect as an item",
          conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"], 1)
    check("store_order: the new bundle links to the surviving item",
          conn.execute("SELECT COUNT(*) c FROM item_bundles WHERE item_id=? "
                       "AND gamekey='xyz789'", (kept,)).fetchone()["c"], 1)
    check("store_order: a merged-away key adds no download row",
          conn.execute("SELECT COUNT(*) c FROM downloads").fetchone()["c"], 1)
    conn.close()

    # --------------------------------------------- user data across a reset
    # The snapshot restores only when the item is being RE-CREATED. A normal
    # re-store must not overwrite a live edit with a stale snapshot.
    conn = fresh(td)
    conn.execute("INSERT INTO user_item_data (machine_name, my_rating, user_tags, "
                 "user_comment, read_status) VALUES ('sas', 5, ?, 'kept', 'read')",
                 (db.tags_to_json(["lent out"]),))
    conn.commit()
    store_order(conn, order("abc123", "Humble Book Bundle: Test by Example Press",
                            [sub("sas", "Salt and Sextant")]))
    row = conn.execute("SELECT my_rating, user_tags, user_comment, read_status "
                       "FROM items WHERE machine_name='sas'").fetchone()
    check("store_order: a snapshot restores the rating on re-create",
          row["my_rating"], 5)
    check("store_order: a snapshot restores the tags on re-create",
          db.tags_from_json(row["user_tags"]), ["lent out"])
    check("store_order: a snapshot restores the comment on re-create",
          row["user_comment"], "kept")
    check("store_order: a snapshot restores the read status on re-create",
          row["read_status"], "read")

    conn.execute("UPDATE items SET my_rating=2 WHERE machine_name='sas'")
    conn.commit()
    store_order(conn, order("abc123", "Humble Book Bundle: Test by Example Press",
                            [sub("sas", "Salt and Sextant")]))
    check("store_order: a live edit is not overwritten by the stale snapshot",
          conn.execute("SELECT my_rating FROM items WHERE machine_name='sas'"
                       ).fetchone()["my_rating"], 2)
    conn.close()

    # A pre-read_status snapshot carries NULL, and the column is NOT NULL:
    # COALESCE must land it on 'unread' rather than raising.
    conn = fresh(td)
    conn.execute("INSERT INTO user_item_data (machine_name, my_rating, read_status) "
                 "VALUES ('sas', 3, NULL)")
    conn.commit()
    store_order(conn, order("abc123", "Humble Book Bundle: Test by Example Press",
                            [sub("sas", "Salt and Sextant")]))
    check("store_order: a NULL snapshot status restores as unread",
          conn.execute("SELECT read_status FROM items WHERE machine_name='sas'"
                       ).fetchone()["read_status"], "unread")
    conn.close()

    # ------------------------------------------------------ external keys
    conn = fresh(td)
    tpk = {"machine_name": "widget_quest_steam", "human_name": "Widget Quest",
           "key_type": "steam"}
    store_order(conn, order("k1", "Humble Game Bundle: Key Vault", [], [tpk]))
    check("store_order: an external key row is written",
          conn.execute("SELECT key_type FROM external_keys WHERE "
                       "machine_name='widget_quest_steam'").fetchone()["key_type"],
          "steam")
    store_order(conn, order("k1", "Humble Game Bundle: Key Vault", [], [tpk]))
    check("store_order: re-storing does not duplicate an external key",
          conn.execute("SELECT COUNT(*) c FROM external_keys").fetchone()["c"], 1)
    conn.close()

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
