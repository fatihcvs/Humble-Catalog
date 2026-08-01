import json
import time
from datetime import datetime, timezone
from pathlib import Path
from humble_catalog import covers, db, humble_api, outbound
from humble_catalog.progress import Progress
from humble_catalog.store import store_order

def run(db_path="catalog.db", covers_dir="covers", client=None, refetch=False):
    conn = db.connect(db_path)
    # Backfill first: parser improvements auto-apply to already-fetched
    # bundles (local JSON re-parse, no network, idempotent).
    _reparse_cached(conn)
    if client is None:
        client = humble_api.ensure_login()
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
        prog.step(raw.get("product", {}).get("human_name", key))
    prog.detach()  # the cover phase paints its own block below this one
    covers = _download_covers(conn, client, covers_dir)
    prog.finish(f"Fetched {len(new)} new bundles ({len(keys) - len(new)} already "
                f"cached). Covers downloaded: {covers}.")
    conn.close()

def reparse(db_path="catalog.db", covers_dir="covers"):
    """Re-run parsing/classification over the local raw-order cache.

    Purely local (no HumbleBundle requests); user data is preserved by
    store_order's usual rules. Also re-links any cover files already on
    disk, so a post-reset reparse recovers covers without downloading."""
    conn = db.connect(db_path)
    _reparse_cached(conn)
    covers.relink(conn, covers_dir)
    conn.close()

def _reparse_cached(conn):
    rows = conn.execute("SELECT gamekey, json FROM raw_orders").fetchall()
    if not rows:
        return  # fresh database: nothing cached, keep first-run output clean
    prog = Progress(conn, "reparse", total=len(rows), phase="Bundle")
    for row in rows:
        raw = json.loads(row["json"])
        prog.step(raw.get("product", {}).get("human_name", row["gamekey"]))
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
            resp = outbound.get(client.http, row["cover_url"], timeout=30)
            if resp.status_code != 200:
                prog.count("missing")
                continue
            (covers_dir / fname).write_bytes(resp.content)
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
