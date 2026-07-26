from humble_catalog.parse_order import parse_order

def store_order(conn, raw):
    bundle, items, externals = parse_order(raw)
    conn.execute(
        "INSERT OR REPLACE INTO bundles (gamekey, name, url, purchased_at) VALUES (?,?,?,?)",
        (bundle["gamekey"], bundle["name"], bundle["url"], bundle["purchased_at"]))
    for it in items:
        # A merged-away machine_name must not resurrect: link this
        # bundle to the surviving item and move on (the survivor already
        # carries the merged downloads).
        tomb = conn.execute(
            "SELECT kept_item_id FROM merges WHERE dropped_machine_name=?",
            (it["machine_name"],)).fetchone()
        if tomb is not None:
            conn.execute(
                "INSERT OR IGNORE INTO item_bundles (item_id, gamekey) VALUES (?,?)",
                (tomb["kept_item_id"], bundle["gamekey"]))
            continue
        row = conn.execute("SELECT id FROM items WHERE machine_name=?",
                           (it["machine_name"],)).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO items (machine_name, name, type, publisher, cover_url) "
                "VALUES (?,?,?,?,?)",
                (it["machine_name"], it["name"], it["type"], it["publisher"],
                 it["cover_url"]))
            item_id = cur.lastrowid
            conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (item_id,))
            # Restore owner-authored fields preserved across a reset. Only
            # fires when re-creating an item (post-reset rebuild); a normal
            # re-store finds the item already present and takes the else
            # branch, so live edits are never overwritten by a stale snapshot.
            saved = conn.execute(
                "SELECT my_rating, user_tags, user_comment, read_status "
                "FROM user_item_data WHERE machine_name=?",
                (it["machine_name"],)).fetchone()
            if saved is not None:
                # COALESCE guards a pre-read_status snapshot (NULL) against
                # the NOT NULL column: an absent status restores as 'unread'.
                conn.execute(
                    "UPDATE items SET my_rating=?, user_tags=?, user_comment=?, "
                    "read_status=COALESCE(?, 'unread') WHERE id=?",
                    (saved["my_rating"], saved["user_tags"],
                     saved["user_comment"], saved["read_status"], item_id))
        else:
            item_id = row["id"]
            # 'ebook' is the no-evidence default, so it never demotes a comic;
            # any bundle providing comic evidence wins regardless of order.
            conn.execute(
                "UPDATE items SET type=? WHERE id=? AND type_overridden=0 "
                "AND NOT (type='comic' AND ?='ebook')",
                (it["type"], item_id, it["type"]))
        conn.execute("INSERT OR IGNORE INTO item_bundles (item_id, gamekey) VALUES (?,?)",
                     (item_id, bundle["gamekey"]))
        conn.execute("DELETE FROM downloads WHERE item_id=? AND kind='humble' AND url=?",
                     (item_id, bundle["url"]))
        conn.execute("INSERT INTO downloads (item_id, kind, url, formats) VALUES (?,?,?,?)",
                     (item_id, "humble", bundle["url"], ",".join(it["formats"])))
    for ext in externals:
        conn.execute(
            "INSERT OR REPLACE INTO external_keys (gamekey, human_name, key_type, raw) "
            "VALUES (?,?,?,?)",
            (bundle["gamekey"], ext["human_name"], ext["key_type"], ext["raw"]))
    conn.commit()
