import json
import time
from datetime import datetime, timezone
from pathlib import Path
from humble_catalog import covers, db, humble_api, outbound
from humble_catalog.progress import Progress
from humble_catalog.shapes import as_mapping
from humble_catalog.store import store_order

# Generous for cover art - the icons Humble serves run well under a
# megabyte - and small enough that a hostile endpoint cannot spend the
# machine's memory on one item.
MAX_COVER_BYTES = 8 * 1024 * 1024

def run(db_path="catalog.db", covers_dir="covers", client=None, refetch=False,
        allow_login=True):
    # try/finally, not a bare close at the end: an exception raised while a
    # write is still uncommitted - a malformed order reaching store_order is
    # the real case - otherwise leaves the connection open with that
    # transaction pending, and on Windows the next open of the same file
    # fails with "database is locked". A CLI run never sees it because the
    # process exits; the suite and any in-process caller do. Closing rolls
    # the pending transaction back, which is what should happen to a write
    # whose order could not be parsed.
    conn = db.connect(db_path)
    try:
        # Backfill first: parser improvements auto-apply to already-fetched
        # bundles (local JSON re-parse, no network, idempotent).
        _reparse_cached(conn)
        if client is None:
            client = humble_api.ensure_login(allow_login=allow_login)
        keys = client.list_order_keys()
        known = {r["gamekey"] for r in conn.execute("SELECT gamekey FROM raw_orders")}
        new = list(keys) if refetch else [k for k in keys if k not in known]
        prog = Progress(conn, "extract", total=len(new), phase="Bundle")
        for key in new:
            raw = client.get_order(key)
            conn.execute("INSERT OR REPLACE INTO raw_orders (gamekey, fetched_at, json) "
                         "VALUES (?,?,?)",
                         (key, datetime.now(timezone.utc).isoformat(), json.dumps(raw)))
            store_order(conn, raw)
            prog.step(as_mapping(raw.get("product")).get("human_name") or key)
        prog.detach()  # the cover phase paints its own block below this one
        # Not `covers`: that is the module imported above, and binding it here
        # would make the name local to this whole function, so any later use of
        # covers.relink above this line would fail at runtime.
        downloaded = _download_covers(conn, client, covers_dir)
        prog.finish(f"Fetched {len(new)} new bundles ({len(keys) - len(new)} already "
                    f"cached). Covers downloaded: {downloaded}.")
    finally:
        conn.close()

def reparse(db_path="catalog.db", covers_dir="covers"):
    """Re-run parsing/classification over the local raw-order cache.

    Purely local (no HumbleBundle requests); user data is preserved by
    store_order's usual rules. Also re-links any cover files already on
    disk, so a post-reset reparse recovers covers without downloading."""
    conn = db.connect(db_path)
    try:
        _reparse_cached(conn)
        covers.relink(conn, covers_dir)
    finally:
        conn.close()

def _reparse_cached(conn):
    rows = conn.execute("SELECT gamekey, json FROM raw_orders").fetchall()
    if not rows:
        return  # fresh database: nothing cached, keep first-run output clean
    prog = Progress(conn, "reparse", total=len(rows), phase="Bundle")
    for row in rows:
        raw = json.loads(row["json"])
        prog.step(as_mapping(raw.get("product")).get("human_name")
                  or row["gamekey"])
        store_order(conn, raw)
    prog.finish(f"Re-parsed {len(rows)} cached bundles.")

def _download_covers(conn, client, covers_dir):
    covers_dir = Path(covers_dir)
    covers_dir.mkdir(parents=True, exist_ok=True)
    # Re-link anything already on disk first, so a rebuild never re-fetches
    # covers it still has.
    covers.relink(conn, covers_dir)
    rows = conn.execute(
        "SELECT id, machine_name, name, cover_url FROM items "
        "WHERE cover_url IS NOT NULL AND cover_path IS NULL").fetchall()
    prog = Progress(conn, "extract", total=len(rows), phase="Cover",
                    tallies=("saved", "missing", "failed"))
    count = 0
    for row in rows:
        prog.step(row["name"])
        fname = covers.cover_filename(row["machine_name"])
        try:
            # cover_url comes out of the order JSON, which the envelope
            # classifies adversarial: it names a URL this project then
            # requests, so it goes through the outbound guard rather than
            # straight into the session. A refusal raises ValueError and is
            # counted as a failed cover below, never fatal to the harvest.
            #
            # stream=True with a capped read, not resp.content: the body is
            # third-party, and buffering it whole would let one hostile or
            # broken response balloon memory. Over the cap the cover is
            # refused outright rather than truncated - half a JPEG on disk
            # looks like a real cover and would never be re-fetched.
            with outbound.get(client.http, row["cover_url"], timeout=30,
                              stream=True) as resp:
                if resp.status_code != 200:
                    prog.count("missing")
                    continue
                body = outbound.read_capped(resp, MAX_COVER_BYTES)
            (covers_dir / fname).write_bytes(body)
            conn.execute("UPDATE items SET cover_path=? WHERE id=?",
                         (f"covers/{fname}", row["id"]))
            conn.commit()
            count += 1
            prog.count("saved")
        except Exception as exc:
            prog.count("failed")
            prog.log(f"  cover failed for item {row['id']}: {exc}")
        time.sleep(1.0)
    return count
