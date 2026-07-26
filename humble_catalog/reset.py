import sys
from humble_catalog import db

# Deleted in this order so PRAGMA foreign_keys = ON is always satisfied:
# every child/association table before the items and bundles it references.
# user_item_data, raw_orders, and source_cache are deliberately absent -
# they are the preserved layer a rebuild reads from.
DERIVED_TABLES = ("item_bundles", "downloads", "external_keys", "enrichment",
                  "merges", "dismissed_pairs", "run_status", "items", "bundles")


def run(db_path="catalog.db", _conn=None, _input=None):
    """Wipe the derived catalog, preserving the download caches and the
    owner's ratings/tags/comments. Wipe only - prints the rebuild steps
    rather than running them. Returns the pre-wipe item count (0 if the
    reset was refused or aborted).
    """
    conn = _conn or db.connect(db_path)
    try:
        ask = _input
        if ask is None:
            if not sys.stdin.isatty():
                # No --yes by design: a reset must never fire from a script.
                print("Refusing to reset without an interactive confirmation.")
                return 0
            ask = input
        n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        print(f"This wipes the derived catalog ({n_items} items): items, "
              "bundles, enrichment, merges, and dedupe state.\n"
              "Downloads (raw_orders, source_cache), cover files, and your "
              "ratings/tags/comments are kept.\n"
              "Hand edits, type overrides, and merges are NOT kept.")
        try:
            answer = ask("Type RESET to continue: ").strip()
        except EOFError:
            answer = ""  # Ctrl-D at the prompt: abort cleanly, wipe nothing
        if answer != "RESET":
            print("Aborted; nothing was changed.")
            return 0
        # Snapshot owner-authored fields, keyed by the rebuild-stable
        # machine_name. DELETE first so a value the owner has since cleared
        # cannot resurrect out of an older snapshot.
        conn.execute("DELETE FROM user_item_data")
        conn.execute(
            "INSERT INTO user_item_data "
            "(machine_name, my_rating, user_tags, user_comment, read_status) "
            "SELECT machine_name, my_rating, user_tags, user_comment, read_status "
            "FROM items WHERE my_rating IS NOT NULL OR user_tags IS NOT NULL "
            "OR user_comment IS NOT NULL OR read_status != 'unread'")
        for table in DERIVED_TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        print(f"Reset {n_items} items. Rebuild with: reparse, then harvest "
              "(a no-op if cached), then enrich.")
        return n_items
    finally:
        if _conn is None:
            conn.close()
