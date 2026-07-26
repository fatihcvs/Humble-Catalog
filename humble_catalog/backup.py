"""Timestamped snapshots of the catalog, and putting one back.

The database is copied with sqlite3's online backup API rather than by
copying the file. db.connect runs in WAL mode, so committed transactions
can still be sitting in catalog.db-wal: a plain copy of catalog.db alone
would silently produce a database missing them.
"""
import os
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path


def _snapshot_path(dest, now=None):
    """A free timestamped path under dest. The compact stamp sorts
    chronologically as text and avoids the colons Windows forbids."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    path = dest / f"catalog-{stamp}.db"
    n = 2
    while path.exists():
        path = dest / f"catalog-{stamp}-{n}.db"
        n += 1
    return path


def _covers_path(db_snapshot):
    """The cover archive paired with a database snapshot. Derived from the
    snapshot's own stem, so a collision suffix carries across and the two
    files can never drift apart."""
    stem = db_snapshot.stem[len("catalog-"):]
    return db_snapshot.with_name(f"covers-{stem}.zip")


def _zip_covers(covers_dir, archive):
    """Archive the cover files, stored rather than deflated. Covers are
    thousands of ~4 KB JPEGs, so the cost is per-file overhead, not bytes:
    one stored zip is ~3x faster than copying the tree, and matters far
    more on an external or network destination. Deflate would spend
    noticeable time to save ~4% on already-compressed data."""
    covers_dir = Path(covers_dir)
    files = sorted(p for p in covers_dir.iterdir()
                   if p.is_file()) if covers_dir.is_dir() else []
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as z:
        for p in files:
            # Bare filename, never a path: an entry can then never place a
            # file outside covers/ when the archive is extracted.
            z.write(p, p.name)
    return len(files)


def _unzip_covers(archive, covers_dir):
    """Extract a cover archive over covers_dir. Entry names are reduced to
    their bare filename, so a crafted archive cannot write outside it."""
    covers_dir = Path(covers_dir)
    covers_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            target = covers_dir / Path(name.replace("\\", "/")).name
            with z.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def run(db_path="catalog.db", dest="backups", covers_dir="covers",
        with_covers=False, _now=None):
    """Write a consistent snapshot of the catalog. Returns its Path, or
    None if there was no catalog to copy."""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"No catalog at {db_path}; nothing to back up.")
        return None
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    target = _snapshot_path(dest, _now)
    # Plain sqlite3.connect, deliberately NOT db.connect: that one runs the
    # schema script and _migrate, which would write to the very database
    # being snapshotted (and would conjure an empty one from a bad path).
    src = sqlite3.connect(db_path)
    try:
        out = sqlite3.connect(target)
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    print(f"Wrote {target} ({target.stat().st_size / 1e6:.1f} MB)")
    if with_covers:
        archive = _covers_path(target)
        n = _zip_covers(covers_dir, archive)
        print(f"Wrote {archive} ({n} covers)")
    return target


def _when(path):
    """A file's modification time, to the minute. Shown beside the item
    counts so the two sides of a restore are told apart by age as well as
    size -- two catalogs can easily hold the same number of items."""
    if not Path(path).exists():
        return "missing"
    return datetime.fromtimestamp(
        Path(path).stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def _items(path):
    """Item count of a database, or None if it is not one we can read.
    Opened read-write rather than read-only: a WAL-mode database with no
    sidecars beside it cannot always be opened read-only, and closing
    cleanly removes anything this creates."""
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error:
        return None
    try:
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            return None
        return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _safety_copy(db_path, dest, now):
    """Snapshot the catalog about to be replaced, falling back to a raw
    byte copy when it is too damaged for the online backup API.

    A catalog SQLite will not open is the likeliest reason to be restoring
    at all, so this step must never be what blocks the restore. The raw
    copy keeps the damaged bytes rather than discarding them -- a corrupt
    file is still the only copy of whatever it holds.

    The error is caught rather than predicted: readability does not
    settle it either way. A truncated file fails both _items and backup,
    while a scribbled page fails _items yet backs up perfectly well.
    """
    try:
        return run(db_path=db_path, dest=dest, _now=now)
    except sqlite3.Error as exc:
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        target = _snapshot_path(dest, now).with_suffix(".unreadable.db")
        shutil.copyfile(db_path, target)
        for suffix in ("-wal", "-shm"):
            side = db_path.with_name(db_path.name + suffix)
            if side.exists():
                shutil.copyfile(side, target.with_name(target.name + suffix))
        print(f"Could not read {db_path} ({exc}); "
              f"kept a raw copy at {target}")
        return target


def restore(snapshot, db_path="catalog.db", dest="backups",
            covers_dir="covers", with_covers=False, _input=None, _now=None):
    """Put a snapshot back over the live catalog, behind a typed
    confirmation. Returns True only if the database was swapped."""
    snapshot, db_path = Path(snapshot), Path(db_path)
    if not snapshot.exists():
        print(f"No such snapshot: {snapshot}")
        return False
    # Validate BEFORE touching the live catalog, so a mistyped filename
    # costs nothing.
    snap_items = _items(snapshot)
    if snap_items is None:
        print(f"{snapshot} is not a readable SQLite database; "
              "nothing was changed.")
        return False
    if not db_path.exists():
        live_label = "no catalog yet"
    else:
        n = _items(db_path)
        # None means SQLite would not read it -- worth saying plainly,
        # since that is usually why a restore is happening.
        live_label = "unreadable" if n is None else f"{n} items"
    ask = _input
    if ask is None:
        if not sys.stdin.isatty():
            # No --yes by design: a restore must never fire from a script.
            print("Refusing to restore without an interactive confirmation.")
            return False
        ask = input
    print(f"This replaces {db_path} "
          f"({live_label}, {_when(db_path)}) with\n"
          f"                 {snapshot} "
          f"({snap_items} items, {_when(snapshot)}).\n"
          "A snapshot of the current catalog is taken first.")
    try:
        answer = ask("Type RESTORE to continue: ").strip()
    except EOFError:
        answer = ""   # Ctrl-D at the prompt: abort cleanly, change nothing
    if answer != "RESTORE":
        print("Aborted; nothing was changed.")
        return False
    if db_path.exists():
        _safety_copy(db_path, dest, _now)
    # Copy then os.replace: the swap is atomic, and os.replace is what
    # makes "refuse while the viewer is running" true -- it fails on an
    # open file, where an in-place write would succeed and corrupt it.
    tmp = db_path.with_name(db_path.name + ".restoring")
    shutil.copyfile(snapshot, tmp)
    try:
        os.replace(tmp, db_path)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        print(f"{db_path} is open in another process; stop `serve` and "
              "retry. Nothing was changed.")
        return False
    # The old database's sidecars. Left beside the restored file, SQLite
    # may replay them over it.
    for suffix in ("-wal", "-shm"):
        db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
    if with_covers:
        archive = _covers_path(snapshot)
        if not archive.exists():
            print(f"No paired cover archive at {archive}; covers unchanged.")
        else:
            _unzip_covers(archive, covers_dir)
            print(f"Restored covers from {archive}")
    print(f"Restored {db_path} from {snapshot} ({snap_items} items).")
    return True
