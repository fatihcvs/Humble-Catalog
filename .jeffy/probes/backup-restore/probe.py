"""Known-answer battery for the backup-restore inventory row.

Covers `humble_catalog/backup.py`: snapshot naming, the cover zip,
`_items`, `_when`, `_safety_copy` and `restore`'s confirmation.

This row has the worst failure mode in the project. Every other defect
found this run produced a wrong answer; a defect here destroys the only
copy of data the owner cannot re-derive. So the cases are weighted
towards what must NOT happen: every refusal path asserts the live catalog
is byte-for-byte unchanged afterwards, and the confirmation is driven
with the wrong answers as hard as with the right one.

The traversal cases matter for the same reason as the covers route's:
a zip entry naming `../../x` must land in covers/ as a bare filename.

Every title is invented, from docs/TEST-DATA.md. Fresh tmpdir per case.
"""
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import backup, db  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def workspace():
    return pathlib.Path(tempfile.mkdtemp())


def make_catalog(path, titles):
    conn = db.connect(path)
    for i, title in enumerate(titles):
        cur = conn.execute(
            "INSERT INTO items (machine_name, name) VALUES (?,?)",
            (f"mn_{i}", title))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    conn.commit()
    conn.close()
    return path


def titles_in(path):
    conn = sqlite3.connect(path)
    try:
        return sorted(r[0] for r in conn.execute("SELECT name FROM items"))
    finally:
        conn.close()


TWO = ["Salt and Sextant", "Nightjar Post"]
THREE = ["Gray Waters", "Unrelated Book", "The Copper Almanac"]


# --------------------------------------------------------- snapshot naming

def case_a_snapshot_is_named_for_its_instant():
    ws = workspace()
    now = datetime(2026, 8, 2, 15, 4, 5)
    check("the stamp is compact and colon-free, so Windows accepts it",
          backup._snapshot_path(ws, now).name, "catalog-20260802-150405.db")


def case_snapshot_names_sort_chronologically_as_text():
    ws = workspace()
    early = backup._snapshot_path(ws, datetime(2026, 8, 2, 9, 0, 0)).name
    late = backup._snapshot_path(ws, datetime(2026, 8, 2, 15, 0, 0)).name
    check("an earlier stamp sorts before a later one as plain text",
          early < late, True)


def case_a_collision_takes_the_next_free_suffix():
    ws = workspace()
    now = datetime(2026, 8, 2, 15, 4, 5)
    first = backup._snapshot_path(ws, now)
    first.write_bytes(b"x")
    second = backup._snapshot_path(ws, now)
    second.write_bytes(b"x")
    check("the second snapshot in one second gets -2",
          second.name, "catalog-20260802-150405-2.db")
    check("and the third gets -3",
          backup._snapshot_path(ws, now).name,
          "catalog-20260802-150405-3.db")


def case_the_cover_archive_is_derived_from_the_snapshot_stem():
    # Documented: a collision suffix carries across, so the two files can
    # never drift apart.
    ws = workspace()
    plain = ws / "catalog-20260802-150405.db"
    bumped = ws / "catalog-20260802-150405-2.db"
    check("the archive pairs with the plain snapshot",
          backup._covers_path(plain).name, "covers-20260802-150405.zip")
    check("and a bumped snapshot keeps its suffix in the archive name",
          backup._covers_path(bumped).name, "covers-20260802-150405-2.zip")


# ------------------------------------------------------------------- run

def case_a_snapshot_holds_the_same_rows():
    ws = workspace()
    make_catalog(ws / "catalog.db", TWO)
    snap = backup.run(db_path=ws / "catalog.db", dest=ws / "backups")
    check("the snapshot holds exactly the catalog's rows",
          titles_in(snap), sorted(TWO))


def case_a_snapshot_captures_writes_still_in_the_wal():
    # The documented reason the online backup API is used rather than a
    # file copy: db.connect runs in WAL mode, so committed rows can be
    # sitting in catalog.db-wal and a plain copy would silently miss them.
    ws = workspace()
    path = ws / "catalog.db"
    make_catalog(path, TWO)
    conn = db.connect(path)                       # holds the WAL open
    cur = conn.execute(
        "INSERT INTO items (machine_name, name) VALUES ('late','Late Arrival')")
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                 (cur.lastrowid,))
    conn.commit()
    snap = backup.run(db_path=path, dest=ws / "backups")
    conn.close()
    check("a row committed into the WAL is in the snapshot",
          "Late Arrival" in titles_in(snap), True)


def case_backing_up_a_missing_catalog_answers_none():
    ws = workspace()
    check("there is nothing to back up",
          backup.run(db_path=ws / "nope.db", dest=ws / "backups"), None)
    check("and no destination is conjured",
          (ws / "backups").exists(), False)


def case_run_does_not_create_a_catalog_from_a_bad_path():
    # Documented: plain sqlite3.connect, deliberately NOT db.connect, which
    # would run the schema and conjure an empty database from a bad path.
    ws = workspace()
    backup.run(db_path=ws / "typo.db", dest=ws / "backups")
    check("a mistyped catalog path leaves no file behind",
          (ws / "typo.db").exists(), False)


def case_covers_are_archived_only_when_asked():
    ws = workspace()
    make_catalog(ws / "catalog.db", TWO)
    covers = ws / "covers"
    covers.mkdir()
    (covers / "a.jpg").write_bytes(b"aaa")
    (covers / "b.jpg").write_bytes(b"bbb")

    plain = backup.run(db_path=ws / "catalog.db", dest=ws / "backups",
                       covers_dir=covers)
    check("no archive without with_covers",
          backup._covers_path(plain).exists(), False)

    withc = backup.run(db_path=ws / "catalog.db", dest=ws / "backups",
                       covers_dir=covers, with_covers=True)
    archive = backup._covers_path(withc)
    check("with_covers writes the paired archive", archive.exists(), True)
    with zipfile.ZipFile(archive) as z:
        check("holding both covers", sorted(z.namelist()), ["a.jpg", "b.jpg"])


def case_a_missing_covers_directory_yields_an_empty_archive():
    ws = workspace()
    make_catalog(ws / "catalog.db", TWO)
    snap = backup.run(db_path=ws / "catalog.db", dest=ws / "backups",
                      covers_dir=ws / "nope", with_covers=True)
    with zipfile.ZipFile(backup._covers_path(snap)) as z:
        check("no covers is an empty archive, not a crash", z.namelist(), [])


def case_archive_entries_are_bare_filenames():
    # Documented: an entry can then never place a file outside covers/.
    ws = workspace()
    make_catalog(ws / "catalog.db", TWO)
    covers = ws / "covers"
    (covers / "nested").mkdir(parents=True)
    (covers / "a.jpg").write_bytes(b"aaa")
    (covers / "nested" / "deep.jpg").write_bytes(b"ddd")
    snap = backup.run(db_path=ws / "catalog.db", dest=ws / "backups",
                      covers_dir=covers, with_covers=True)
    with zipfile.ZipFile(backup._covers_path(snap)) as z:
        check("only top-level files are archived, by bare name",
              z.namelist(), ["a.jpg"])


def case_unzip_reduces_a_traversing_entry_to_its_basename():
    ws = workspace()
    archive = ws / "covers-x.zip"
    covers = ws / "covers"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../../escaped.jpg", b"nope")
        z.writestr("nested/deep.jpg", b"deep")
        z.writestr("plain.jpg", b"ok")
    backup._unzip_covers(archive, covers)
    check("every entry lands in covers/ under its bare name",
          sorted(p.name for p in covers.iterdir()),
          ["deep.jpg", "escaped.jpg", "plain.jpg"])
    check("and nothing escaped the directory",
          (ws / "escaped.jpg").exists(), False)


# ----------------------------------------------------------------- _items

def case_items_counts_a_real_catalog():
    ws = workspace()
    make_catalog(ws / "catalog.db", THREE)
    check("the count is the row count", backup._items(ws / "catalog.db"), 3)


def case_items_refuses_a_file_that_is_not_a_database():
    ws = workspace()
    junk = ws / "junk.db"
    junk.write_bytes(b"this is not a database" * 100)
    check("a non-database answers None", backup._items(junk), None)


def case_items_refuses_a_database_with_no_items_table():
    ws = workspace()
    other = ws / "other.db"
    conn = sqlite3.connect(other)
    conn.execute("CREATE TABLE something (x INTEGER)")
    conn.commit()
    conn.close()
    check("a database without the items table answers None",
          backup._items(other), None)


def case_when_reports_missing_for_an_absent_file():
    ws = workspace()
    check("an absent file has no timestamp",
          backup._when(ws / "nope.db"), "missing")


def case_when_reports_a_minute_stamp():
    ws = workspace()
    make_catalog(ws / "catalog.db", TWO)
    stamp = backup._when(ws / "catalog.db")
    check("the stamp is to the minute", len(stamp), len("2026-08-02 15:04"))
    check("and is not the missing marker", stamp == "missing", False)


# ---------------------------------------------------------------- restore

def restore_ws(live=TWO, snap=THREE):
    ws = workspace()
    make_catalog(ws / "catalog.db", live)
    snapshot = make_catalog(ws / "snap.db", snap)
    return ws, snapshot


def case_a_typed_confirmation_swaps_the_database():
    ws, snapshot = restore_ws()
    ok = backup.restore(snapshot, db_path=ws / "catalog.db",
                        dest=ws / "backups", _input=lambda _p: "RESTORE")
    check("the restore reports success", ok, True)
    check("and the live catalog now holds the snapshot's rows",
          titles_in(ws / "catalog.db"), sorted(THREE))


def case_a_restore_snapshots_the_catalog_it_replaces():
    ws, snapshot = restore_ws()
    backup.restore(snapshot, db_path=ws / "catalog.db", dest=ws / "backups",
                   _input=lambda _p: "RESTORE")
    saved = list((ws / "backups").glob("catalog-*.db"))
    check("exactly one safety copy was taken", len(saved), 1)
    check("and it holds the REPLACED rows, not the restored ones",
          titles_in(saved[0]), sorted(TWO))


def case_every_wrong_answer_changes_nothing():
    # The confirmation is the only thing between a stray command and the
    # live catalog, so it is driven with everything that is not the word.
    for answer in ["", "restore", "Restore", "y", "yes", "RESTORE now",
                   " RESTOR ", "RESTOREX"]:
        ws, snapshot = restore_ws()
        before = (ws / "catalog.db").read_bytes()
        ok = backup.restore(snapshot, db_path=ws / "catalog.db",
                            dest=ws / "backups", _input=lambda _p, a=answer: a)
        check(f"refused: {answer!r}", ok, False)
        check(f"catalog untouched after {answer!r}",
              (ws / "catalog.db").read_bytes(), before)
        check(f"and no safety copy was taken for {answer!r}",
              list((ws / "backups").glob("*.db")) if (ws / "backups").exists()
              else [], [])


def case_a_lowercase_confirmation_is_not_accepted():
    # Called out separately because it is the likeliest near-miss.
    ws, snapshot = restore_ws()
    ok = backup.restore(snapshot, db_path=ws / "catalog.db",
                        dest=ws / "backups", _input=lambda _p: "restore")
    check("the word is case-sensitive", ok, False)
    check("and the catalog still holds its own rows",
          titles_in(ws / "catalog.db"), sorted(TWO))


def case_the_surrounding_whitespace_is_stripped():
    ws, snapshot = restore_ws()
    ok = backup.restore(snapshot, db_path=ws / "catalog.db",
                        dest=ws / "backups", _input=lambda _p: "  RESTORE  ")
    check("a padded confirmation is still the word", ok, True)


def case_ctrl_d_at_the_prompt_aborts_cleanly():
    def eof(_prompt):
        raise EOFError

    ws, snapshot = restore_ws()
    before = (ws / "catalog.db").read_bytes()
    ok = backup.restore(snapshot, db_path=ws / "catalog.db",
                        dest=ws / "backups", _input=eof)
    check("an EOF aborts rather than raising", ok, False)
    check("and changes nothing",
          (ws / "catalog.db").read_bytes(), before)


def case_a_missing_snapshot_is_refused_before_anything_is_touched():
    ws, _snapshot = restore_ws()
    before = (ws / "catalog.db").read_bytes()

    def never(_prompt):
        raise AssertionError("the confirmation was reached for a bad path")

    ok = backup.restore(ws / "nope.db", db_path=ws / "catalog.db",
                        dest=ws / "backups", _input=never)
    check("a mistyped snapshot path is refused", ok, False)
    check("without even asking", (ws / "catalog.db").read_bytes(), before)


def case_an_unreadable_snapshot_is_refused_before_the_prompt():
    # Documented: validate BEFORE touching the live catalog, so a mistyped
    # filename costs nothing.
    ws, _snapshot = restore_ws()
    junk = ws / "junk.db"
    junk.write_bytes(b"not a database" * 100)
    before = (ws / "catalog.db").read_bytes()

    def never(_prompt):
        raise AssertionError("the confirmation was reached for a bad snapshot")

    ok = backup.restore(junk, db_path=ws / "catalog.db",
                        dest=ws / "backups", _input=never)
    check("an unreadable snapshot is refused", ok, False)
    check("and the live catalog is untouched",
          (ws / "catalog.db").read_bytes(), before)


def case_restoring_over_no_catalog_at_all_works():
    ws = workspace()
    snapshot = make_catalog(ws / "snap.db", THREE)
    ok = backup.restore(snapshot, db_path=ws / "catalog.db",
                        dest=ws / "backups", _input=lambda _p: "RESTORE")
    check("a first restore with no live catalog succeeds", ok, True)
    check("and the catalog appears with the snapshot's rows",
          titles_in(ws / "catalog.db"), sorted(THREE))
    check("with no safety copy, there being nothing to save",
          list((ws / "backups").glob("catalog-*.db")) if
          (ws / "backups").exists() else [], [])


def case_the_old_sidecars_are_removed():
    # Documented: left beside the restored file, SQLite may replay them
    # over it - which would silently undo the restore.
    ws, snapshot = restore_ws()
    for suffix in ("-wal", "-shm"):
        (ws / f"catalog.db{suffix}").write_bytes(b"stale")
    backup.restore(snapshot, db_path=ws / "catalog.db", dest=ws / "backups",
                   _input=lambda _p: "RESTORE")
    check("the stale sidecars are gone",
          [s for s in ("-wal", "-shm")
           if (ws / f"catalog.db{s}").exists()], [])


def case_no_restoring_temp_file_is_left_behind():
    ws, snapshot = restore_ws()
    backup.restore(snapshot, db_path=ws / "catalog.db", dest=ws / "backups",
                   _input=lambda _p: "RESTORE")
    check("the .restoring temp file is gone",
          (ws / "catalog.db.restoring").exists(), False)


def case_covers_are_restored_only_when_asked_and_paired():
    ws, snapshot = restore_ws()
    covers = ws / "covers"
    covers.mkdir()
    (covers / "old.jpg").write_bytes(b"old")
    archive = backup._covers_path(ws / "catalog-20260101-000000.db")
    shutil.copyfile(snapshot, ws / "unused.db")
    with zipfile.ZipFile(ws / "covers-snap.zip", "w") as z:
        z.writestr("new.jpg", b"new")

    backup.restore(snapshot, db_path=ws / "catalog.db", dest=ws / "backups",
                   covers_dir=covers, with_covers=True,
                   _input=lambda _p: "RESTORE")
    check("an unpaired archive leaves the covers alone",
          sorted(p.name for p in covers.iterdir()), ["old.jpg"])
    check("and the derived archive path is where it looked",
          archive.name, "covers-20260101-000000.zip")


def case_a_paired_cover_archive_is_extracted():
    ws, snapshot = restore_ws()
    covers = ws / "covers"
    covers.mkdir()
    (covers / "old.jpg").write_bytes(b"old")
    # snapshot is snap.db, whose stem does not start with "catalog-", so
    # pair the archive the way _covers_path derives it.
    paired = backup._covers_path(snapshot)
    with zipfile.ZipFile(paired, "w") as z:
        z.writestr("new.jpg", b"new")
    backup.restore(snapshot, db_path=ws / "catalog.db", dest=ws / "backups",
                   covers_dir=covers, with_covers=True,
                   _input=lambda _p: "RESTORE")
    check("the paired archive is extracted over covers/",
          "new.jpg" in [p.name for p in covers.iterdir()], True)


# ----------------------------------------------------------- _safety_copy

def case_a_damaged_catalog_still_gets_a_raw_copy():
    # The documented promise: a catalog SQLite will not open is the
    # likeliest reason to be restoring at all, so this step must never be
    # what blocks the restore, and the damaged bytes are KEPT.
    ws = workspace()
    damaged = ws / "catalog.db"
    damaged.write_bytes(b"SQLite format 3\x00" + b"\xff" * 2000)
    saved = backup._safety_copy(damaged, ws / "backups",
                                datetime(2026, 8, 2, 15, 4, 5))
    check("something was kept", saved is not None, True)
    check("and it holds the damaged bytes verbatim",
          pathlib.Path(saved).read_bytes(), damaged.read_bytes())


def case_a_restore_over_a_damaged_catalog_still_happens():
    ws = workspace()
    damaged = ws / "catalog.db"
    damaged.write_bytes(b"SQLite format 3\x00" + b"\xff" * 2000)
    snapshot = make_catalog(ws / "snap.db", THREE)
    ok = backup.restore(snapshot, db_path=damaged, dest=ws / "backups",
                        _input=lambda _p: "RESTORE")
    check("the restore is not blocked by the damaged catalog", ok, True)
    check("and the catalog now holds the snapshot's rows",
          titles_in(damaged), sorted(THREE))


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
    print(f"backup-restore: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
