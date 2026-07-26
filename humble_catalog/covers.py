import hashlib
import re
from pathlib import Path


def cover_filename(machine_name):
    """Filesystem-safe, rebuild-stable cover basename for an item.

    machine_name is Humble's unique per-item key. The name is a
    lowercased slug (every character outside [a-z0-9_-] -> '_') plus a
    12-hex blake2b digest of the RAW machine_name. The suffix keeps
    distinct items distinct even when their slugs collide (e.g. 'Foo'
    vs 'foo') and keeps Windows reserved names (con, nul) from ever
    appearing bare. blake2b, not SHA-1: the digest is non-adversarial,
    so collision resistance is moot, but blake2b sets its length via
    digest_size and carries no FIPS-mode breakage.
    """
    slug = re.sub(r"[^a-z0-9_-]", "_", machine_name.lower())
    digest = hashlib.blake2b(machine_name.encode(), digest_size=6).hexdigest()
    return f"{slug}-{digest}.jpg"


def relink(conn, covers_dir):
    """Point cover_path at cover files already present on disk (offline).

    For every item lacking a cover_path whose machine_name maps to an
    existing file under covers_dir, set cover_path. No network. Returns
    the number of rows re-linked. This is what lets a post-reset reparse
    recover covers without re-downloading them.
    """
    covers_dir = Path(covers_dir)
    rows = conn.execute(
        "SELECT id, machine_name FROM items WHERE cover_path IS NULL").fetchall()
    count = 0
    for row in rows:
        fname = cover_filename(row["machine_name"])
        if (covers_dir / fname).exists():
            conn.execute("UPDATE items SET cover_path=? WHERE id=?",
                         (f"covers/{fname}", row["id"]))
            count += 1
    conn.commit()
    return count
