import os
import sqlite3
import zipfile
from datetime import datetime

import pytest

from humble_catalog import backup, db

# A fixed instant so snapshot names are predictable in assertions.
STAMP = datetime(2026, 7, 25, 14, 30, 12)


def _seed(path):
    """A catalog with one item. Returns the OPEN connection: callers that
    want the commit left sitting in the WAL simply do not close it."""
    conn = db.connect(path)
    conn.execute("INSERT INTO items (machine_name, name) "
                 "VALUES ('cooltower_android', 'Cool Tower Defense')")
    conn.commit()
    return conn


def test_backup_writes_a_snapshot_named_for_the_time(tmp_path):
    live = tmp_path / "catalog.db"
    _seed(live).close()
    out = backup.run(db_path=live, dest=tmp_path / "backups", _now=STAMP)
    assert out.name == "catalog-20260725-143012.db"
    assert out.exists()


def test_backup_captures_a_commit_still_in_the_wal(tmp_path):
    # The whole reason for sqlite3's online backup API. The connection is
    # left OPEN, so the committed row is still resident in catalog.db-wal
    # and a plain file copy of catalog.db would miss it entirely.
    live = tmp_path / "catalog.db"
    conn = _seed(live)
    out = backup.run(db_path=live, dest=tmp_path / "backups", _now=STAMP)
    conn.close()
    snap = sqlite3.connect(out)
    try:
        assert snap.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    finally:
        snap.close()


def test_backup_does_not_mutate_its_source(tmp_path):
    # Pins the plain-sqlite3.connect choice: db.connect would run the
    # schema script and migrations against the database being snapshotted.
    live = tmp_path / "catalog.db"
    _seed(live).close()
    before = live.read_bytes()
    backup.run(db_path=live, dest=tmp_path / "backups", _now=STAMP)
    assert live.read_bytes() == before


def test_backup_refuses_a_missing_catalog(tmp_path, capsys):
    # sqlite3.connect would happily create an empty database here, turning
    # "back up my catalog" into "invent one and back that up".
    missing = tmp_path / "catalog.db"
    dest = tmp_path / "backups"
    assert backup.run(db_path=missing, dest=dest) is None
    assert not missing.exists()
    assert not dest.exists()
    assert "nothing to back up" in capsys.readouterr().out


def test_backup_suffixes_a_colliding_name(tmp_path):
    live = tmp_path / "catalog.db"
    _seed(live).close()
    dest = tmp_path / "backups"
    first = backup.run(db_path=live, dest=dest, _now=STAMP)
    second = backup.run(db_path=live, dest=dest, _now=STAMP)
    assert first.name == "catalog-20260725-143012.db"
    assert second.name == "catalog-20260725-143012-2.db"


def _covers(tmp_path):
    """A covers directory with one file, named the way covers.py names
    them (machine_name slug + digest)."""
    d = tmp_path / "covers"
    d.mkdir()
    (d / "cooltower_android-2f1a4b6c8d0e.jpg").write_bytes(b"jpegbytes")
    return d


def test_backup_covers_writes_a_stored_zip_beside_the_snapshot(tmp_path):
    live = tmp_path / "catalog.db"
    _seed(live).close()
    out = backup.run(db_path=live, dest=tmp_path / "backups",
                     covers_dir=_covers(tmp_path), with_covers=True,
                     _now=STAMP)
    archive = out.with_name("covers-20260725-143012.zip")
    assert archive.exists()
    with zipfile.ZipFile(archive) as z:
        assert z.namelist() == ["cooltower_android-2f1a4b6c8d0e.jpg"]
        info = z.getinfo("cooltower_android-2f1a4b6c8d0e.jpg")
        # Stored, not deflated: compression costs time to save ~4% on
        # already-compressed JPEG data.
        assert info.compress_type == zipfile.ZIP_STORED
        assert z.read(info) == b"jpegbytes"


def test_backup_without_the_flag_writes_no_archive(tmp_path):
    live = tmp_path / "catalog.db"
    _seed(live).close()
    out = backup.run(db_path=live, dest=tmp_path / "backups",
                     covers_dir=_covers(tmp_path), _now=STAMP)
    assert list(out.parent.glob("covers-*.zip")) == []


def test_cover_archive_keeps_the_snapshots_collision_suffix(tmp_path):
    # The pair must stay matched, or restore --covers would reach for the
    # wrong archive.
    live = tmp_path / "catalog.db"
    _seed(live).close()
    dest = tmp_path / "backups"
    covers = _covers(tmp_path)
    backup.run(db_path=live, dest=dest, covers_dir=covers,
               with_covers=True, _now=STAMP)
    second = backup.run(db_path=live, dest=dest, covers_dir=covers,
                        with_covers=True, _now=STAMP)
    assert second.name == "catalog-20260725-143012-2.db"
    assert second.with_name("covers-20260725-143012-2.zip").exists()


def test_backup_covers_tolerates_a_missing_covers_directory(tmp_path):
    live = tmp_path / "catalog.db"
    _seed(live).close()
    out = backup.run(db_path=live, dest=tmp_path / "backups",
                     covers_dir=tmp_path / "nope", with_covers=True,
                     _now=STAMP)
    with zipfile.ZipFile(out.with_name("covers-20260725-143012.zip")) as z:
        assert z.namelist() == []


LATER = datetime(2026, 7, 25, 15, 0, 0)


class _NoTTY:
    def isatty(self):
        return False


def _name(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT name FROM items").fetchone()[0]
    finally:
        conn.close()


def _snapshot_then_edit(tmp_path):
    """Snapshot a seeded catalog, then change the live one. Returns
    (live path, snapshot path, backups dir)."""
    live = tmp_path / "catalog.db"
    _seed(live).close()
    dest = tmp_path / "backups"
    snap = backup.run(db_path=live, dest=dest, _now=STAMP)
    conn = db.connect(live)
    conn.execute("UPDATE items SET name='Unrelated Book'")
    conn.commit()
    conn.close()
    return live, snap, dest


def test_restore_puts_the_snapshot_back(tmp_path):
    live, snap, dest = _snapshot_then_edit(tmp_path)
    assert backup.restore(snap, db_path=live, dest=dest,
                          _input=lambda p: "RESTORE", _now=LATER) is True
    assert _name(live) == "Cool Tower Defense"


def test_restore_takes_a_safety_snapshot_of_the_pre_restore_state(tmp_path):
    live, snap, dest = _snapshot_then_edit(tmp_path)
    backup.restore(snap, db_path=live, dest=dest,
                   _input=lambda p: "RESTORE", _now=LATER)
    safety = dest / "catalog-20260725-150000.db"
    assert safety.exists()
    assert _name(safety) == "Unrelated Book"


def test_restore_clears_the_stale_wal_and_shm(tmp_path):
    # These belong to the OLD database. Left beside a swapped-in file,
    # SQLite may replay them over the restored data. This is the step a
    # hand-restore forgets, and it fails silently.
    live, snap, dest = _snapshot_then_edit(tmp_path)
    live.with_name("catalog.db-wal").write_bytes(b"stale")
    live.with_name("catalog.db-shm").write_bytes(b"stale")
    backup.restore(snap, db_path=live, dest=dest,
                   _input=lambda p: "RESTORE", _now=LATER)
    assert not live.with_name("catalog.db-wal").exists()
    assert not live.with_name("catalog.db-shm").exists()


def test_restore_rejects_a_file_that_is_not_a_database(tmp_path, capsys):
    live, _snap, dest = _snapshot_then_edit(tmp_path)
    junk = tmp_path / "notes.txt"
    junk.write_text("this is not a database")
    assert backup.restore(junk, db_path=live, dest=dest,
                          _input=lambda p: "RESTORE") is False
    assert _name(live) == "Unrelated Book"      # untouched
    assert "not a readable SQLite database" in capsys.readouterr().out


def test_restore_rejects_a_missing_snapshot(tmp_path, capsys):
    live, _snap, dest = _snapshot_then_edit(tmp_path)
    assert backup.restore(tmp_path / "nope.db", db_path=live, dest=dest,
                          _input=lambda p: "RESTORE") is False
    assert "No such snapshot" in capsys.readouterr().out


def test_restore_aborts_on_the_wrong_word(tmp_path):
    live, snap, dest = _snapshot_then_edit(tmp_path)
    assert backup.restore(snap, db_path=live, dest=dest,
                          _input=lambda p: "yes") is False
    assert _name(live) == "Unrelated Book"


def test_restore_aborts_cleanly_on_eof(tmp_path, capsys):
    live, snap, dest = _snapshot_then_edit(tmp_path)

    def _eof(prompt):
        raise EOFError      # e.g. Ctrl-D at the prompt

    assert backup.restore(snap, db_path=live, dest=dest, _input=_eof) is False
    assert _name(live) == "Unrelated Book"
    assert "Aborted" in capsys.readouterr().out


def test_restore_refuses_without_a_tty(tmp_path, monkeypatch):
    # No --yes by design: a restore must never fire from a script.
    live, snap, dest = _snapshot_then_edit(tmp_path)
    monkeypatch.setattr("sys.stdin", _NoTTY())
    assert backup.restore(snap, db_path=live, dest=dest) is False
    assert _name(live) == "Unrelated Book"


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows-only: POSIX replaces an open file happily, so there "
           "is no refusal to assert")
def test_restore_refuses_while_the_catalog_is_open(tmp_path, capsys):
    # The guarantee is a property of os.replace specifically: an in-place
    # write would succeed here and corrupt the open database.
    live = tmp_path / "catalog.db"
    conn = _seed(live)
    dest = tmp_path / "backups"
    snap = backup.run(db_path=live, dest=dest, _now=STAMP)
    conn.execute("UPDATE items SET name='Unrelated Book'")
    conn.commit()
    ok = backup.restore(snap, db_path=live, dest=dest,
                        _input=lambda p: "RESTORE", _now=LATER)
    conn.close()
    assert ok is False
    assert "open in another process" in capsys.readouterr().out
    assert _name(live) == "Unrelated Book"


def test_restore_survives_an_unreadable_live_catalog(tmp_path, capsys):
    # A corrupt catalog is the likeliest reason to be restoring at all, so
    # the safety snapshot must never be the step that prevents recovery.
    # Truncation is the realistic damage -- a partial write or a full disk
    # leaves exactly this, and SQLite then refuses the file outright.
    live, snap, dest = _snapshot_then_edit(tmp_path)
    live.write_bytes(live.read_bytes()[:len(live.read_bytes()) // 2])
    assert backup.restore(snap, db_path=live, dest=dest,
                          _input=lambda p: "RESTORE", _now=LATER) is True
    assert _name(live) == "Cool Tower Defense"
    out = capsys.readouterr().out
    # The damaged bytes are preserved rather than discarded...
    assert "kept a raw copy" in out
    assert len(list(dest.glob("*.unreadable.db"))) == 1
    # ...and the prompt says so instead of printing "None items".
    assert "unreadable" in out


def test_restore_covers_puts_the_archived_files_back(tmp_path):
    live = tmp_path / "catalog.db"
    _seed(live).close()
    covers = _covers(tmp_path)
    dest = tmp_path / "backups"
    snap = backup.run(db_path=live, dest=dest, covers_dir=covers,
                      with_covers=True, _now=STAMP)
    (covers / "cooltower_android-2f1a4b6c8d0e.jpg").write_bytes(b"clobbered")
    assert backup.restore(snap, db_path=live, dest=dest, covers_dir=covers,
                          with_covers=True, _input=lambda p: "RESTORE",
                          _now=LATER) is True
    restored = covers / "cooltower_android-2f1a4b6c8d0e.jpg"
    assert restored.read_bytes() == b"jpegbytes"


def test_restore_covers_reports_a_missing_archive(tmp_path, capsys):
    live, snap, dest = _snapshot_then_edit(tmp_path)   # no --covers backup
    covers = _covers(tmp_path)
    assert backup.restore(snap, db_path=live, dest=dest, covers_dir=covers,
                          with_covers=True, _input=lambda p: "RESTORE",
                          _now=LATER) is True
    assert "No paired cover archive" in capsys.readouterr().out
    # The database still restored; only the covers were left alone.
    assert _name(live) == "Cool Tower Defense"


def test_restore_covers_cannot_escape_the_covers_directory(tmp_path):
    # A hand-made archive with a traversing entry name. The command only
    # ever reads back its own archives, but it should not depend on that.
    live, snap, dest = _snapshot_then_edit(tmp_path)
    covers = _covers(tmp_path)
    with zipfile.ZipFile(backup._covers_path(snap), "w") as z:
        z.writestr("../escaped.jpg", b"nope")
    backup.restore(snap, db_path=live, dest=dest, covers_dir=covers,
                   with_covers=True, _input=lambda p: "RESTORE", _now=LATER)
    assert not (tmp_path / "escaped.jpg").exists()
    assert (covers / "escaped.jpg").exists()
