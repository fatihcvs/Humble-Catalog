import json
import sqlite3
from collections import namedtuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS bundles (
  gamekey TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, purchased_at TEXT);
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY, machine_name TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'ebook', type_overridden INTEGER NOT NULL DEFAULT 0,
  publisher TEXT, cover_url TEXT, cover_path TEXT, my_rating INTEGER,
  user_tags TEXT, user_comment TEXT,
  read_status TEXT NOT NULL DEFAULT 'unread'
    CHECK (read_status IN ('want_to_read','unread','reading','read','dnf')));
CREATE TABLE IF NOT EXISTS item_bundles (
  item_id INTEGER NOT NULL REFERENCES items(id),
  gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
  PRIMARY KEY (item_id, gamekey));
CREATE TABLE IF NOT EXISTS downloads (
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id),
  kind TEXT NOT NULL, url TEXT NOT NULL, formats TEXT);
CREATE INDEX IF NOT EXISTS ix_downloads_item_id ON downloads(item_id);
CREATE TABLE IF NOT EXISTS external_keys (
  gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
  machine_name TEXT NOT NULL,
  human_name TEXT, key_type TEXT, raw TEXT,
  PRIMARY KEY (gamekey, machine_name));
/* The owner's "wherever this one ended up, I know it is resolved". Keyed
   on the pair rather than machine_name alone because 128 games are keyed
   in more than one bundle, and one bundle's key may have landed while the
   other's did not -- the hide is per key, not per game.
   No foreign key to external_keys, deliberately and against the
   convention around it: a hide has to OUTLIVE the row it names. It is
   absent from reset.DERIVED_TABLES on purpose, so a reset wipes the keys
   and keeps the hides, and an FK would either cascade them away or make
   the reset fail. keys.stale_hides reports the hides left dangling. */
CREATE TABLE IF NOT EXISTS hidden_keys (
  gamekey TEXT NOT NULL, machine_name TEXT NOT NULL,
  hidden_at TEXT NOT NULL,
  PRIMARY KEY (gamekey, machine_name));
CREATE TABLE IF NOT EXISTS enrichment (
  item_id INTEGER PRIMARY KEY REFERENCES items(id),
  genre TEXT, series TEXT, series_number REAL, authors TEXT, narrator TEXT,
  illustrator TEXT, external_rating REAL, rating_source TEXT,
  match_confidence REAL, status TEXT NOT NULL DEFAULT 'pending', candidates TEXT,
  source_url TEXT, pre_edit TEXT,
  hand_edited INTEGER NOT NULL DEFAULT 0,
  enrich_override INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS raw_orders (
  gamekey TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_cache (
  source TEXT NOT NULL, query TEXT NOT NULL, fetched_at TEXT NOT NULL, json TEXT,
  PRIMARY KEY (source, query));
CREATE TABLE IF NOT EXISTS user_item_data (
  machine_name TEXT PRIMARY KEY, my_rating INTEGER,
  user_tags TEXT, user_comment TEXT, read_status TEXT);
CREATE TABLE IF NOT EXISTS run_status (
  command TEXT PRIMARY KEY, phase TEXT, done INTEGER, total INTEGER,
  current TEXT, started_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS merges (
  dropped_machine_name TEXT PRIMARY KEY,
  kept_item_id INTEGER NOT NULL REFERENCES items(id));
CREATE TABLE IF NOT EXISTS dismissed_pairs (
  a TEXT NOT NULL, b TEXT NOT NULL, PRIMARY KEY (a, b));
CREATE TABLE IF NOT EXISTS games (
  store TEXT NOT NULL, store_id TEXT NOT NULL, title TEXT NOT NULL,
  normalized_title TEXT NOT NULL, imported_at TEXT NOT NULL,
  source_timestamp TEXT,
  PRIMARY KEY (store, store_id));
CREATE INDEX IF NOT EXISTS ix_games_normalized ON games(normalized_title);
CREATE TABLE IF NOT EXISTS game_imports (
  store TEXT PRIMARY KEY, imported_at TEXT NOT NULL,
  count INTEGER NOT NULL, source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_quota (
  source TEXT PRIMARY KEY, hit_at TEXT NOT NULL, resets_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_failure (
  source TEXT NOT NULL, title TEXT NOT NULL,
  failures INTEGER NOT NULL,
  first_failed_at TEXT NOT NULL, last_failed_at TEXT NOT NULL,
  last_error TEXT NOT NULL,
  PRIMARY KEY (source, title));
CREATE TABLE IF NOT EXISTS harvest_run (
  started_at TEXT NOT NULL, source TEXT NOT NULL, ended_at TEXT NOT NULL,
  answered INTEGER NOT NULL, succeeded INTEGER NOT NULL,
  failed INTEGER NOT NULL, quota_died INTEGER NOT NULL,
  PRIMARY KEY (started_at, source));
"""

# The four multi-value enrichment fields. Stored as JSON arrays in TEXT
# columns (or NULL); everything else in enrichment stays scalar.
TAG_FIELDS = ("genre", "authors", "narrator", "illustrator")

def tags_to_json(values):
    """Normalize tags to a column value: trim entries, drop empties and
    exact duplicates (order kept); a bare string wraps as one tag.
    Returns None when nothing is left, so empty always stores as NULL."""
    if values is None or values == "":
        return None
    if isinstance(values, str):
        values = [values]
    out = []
    for v in values:
        v = str(v).strip()
        if v and v not in out:
            out.append(v)
    return json.dumps(out, ensure_ascii=False) if out else None

def tags_from_json(value):
    """Column value -> list of tags; NULL/empty -> []."""
    return json.loads(value) if value else []

def titleize(tag):
    """Uppercase the first letter of each space-separated word, leaving
    the other letters alone (so acronyms like RPG survive)."""
    return " ".join(w[:1].upper() + w[1:] for w in tag.split(" "))

# A tag column with a managed vocabulary: case-snapping on write, plus
# catalog-wide rename and delete.
#
#   key      — primary-key column of `table`, for targeted UPDATEs
#   snapshot — column is copied into enrichment.pre_edit, so rewrites
#              must touch the snapshot too or a revert would resurrect
#              a renamed/deleted spelling
#   titleize — unknown tags are title-cased rather than stored verbatim
#
# Person-name fields (authors, narrator, illustrator) are deliberately
# absent and must never be added: titleizing or snapping names would
# mangle spellings like "van der Berg" or "k.d. lang".
TagColumn = namedtuple("TagColumn", "table column key snapshot titleize")

GENRE = TagColumn("enrichment", "genre", "item_id", snapshot=True, titleize=True)

# User-owned, on items rather than enrichment: never in EDITABLE_FIELDS,
# never in pre_edit, so filling it is not a hand edit and never locks the
# row for enrichment. Not titleized — a personal vocabulary keeps the
# casing the user typed.
USER_TAGS = TagColumn("items", "user_tags", "id", snapshot=False, titleize=False)

def tag_vocab(conn, col):
    """lowercase tag -> stored spelling, over live arrays in col."""
    vocab = {}
    for r in conn.execute(f"SELECT {col.column} FROM {col.table} "
                          f"WHERE {col.column} IS NOT NULL"):
        for t in tags_from_json(r[col.column]):
            vocab.setdefault(t.lower(), t)
    return vocab

def normalize_tags(conn, col, tags):
    """Canonical-merge tags for col: snap each tag to the spelling
    already in col's vocabulary when one matches case-insensitively,
    otherwise titleize it (col.titleize) or keep it as typed. Dedupes
    case-insensitively, order kept. Accepts list, bare string, or None.
    Managed columns only — person-name fields must never come here."""
    if tags is None or tags == "":
        return []
    if isinstance(tags, str):
        tags = [tags]
    vocab = tag_vocab(conn, col)
    out, seen = [], set()
    for t in tags:
        t = str(t).strip()
        if not t:
            continue
        t = vocab.get(t.lower(), titleize(t) if col.titleize else t)
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out

def _rewrite_tags(conn, col, fn):
    """Apply fn(tag) -> replacement | None (None drops the tag) to every
    tag in col, and — when col.snapshot — to pre_edit snapshot copies
    too, so a revert cannot resurrect a renamed/deleted spelling.
    Returns the number of rows changed. Does not commit."""
    changed = 0
    remap = lambda val: tags_to_json(
        [x for t in tags_from_json(val) if (x := fn(t)) is not None])
    extra = ", pre_edit" if col.snapshot else ""
    rows = conn.execute(
        f"SELECT {col.key}, {col.column}{extra} FROM {col.table}").fetchall()
    for r in rows:
        value = remap(r[col.column])
        if not col.snapshot:
            if value != r[col.column]:
                changed += 1
                conn.execute(
                    f"UPDATE {col.table} SET {col.column}=? WHERE {col.key}=?",
                    (value, r[col.key]))
            continue
        pre = r["pre_edit"]
        if pre is not None:
            snap = json.loads(pre)
            if col.column in snap:
                snap[col.column] = remap(snap[col.column])
            pre = json.dumps(snap, ensure_ascii=False)
        if value != r[col.column] or pre != r["pre_edit"]:
            changed += 1
            conn.execute(
                f"UPDATE {col.table} SET {col.column}=?, pre_edit=? "
                f"WHERE {col.key}=?", (value, pre, r[col.key]))
    return changed

def rename_tag(conn, col, old, new):
    """Catalog-wide rename within col's vocabulary (NOT a hand-edit:
    edited status never changes). `old` matches case-insensitively;
    `new` snaps to an existing spelling (ignoring `old` itself), or is
    titleized when col.titleize, so renaming onto an existing tag
    merges and arrays dedupe. Returns the number of rows changed, or
    None when `old` is unknown or either argument is blank."""
    old = (old or "").strip().lower()
    new = (new or "").strip()
    vocab = tag_vocab(conn, col)
    if not old or not new or old not in vocab:
        return None
    del vocab[old]
    new = vocab.get(new.lower(), titleize(new) if col.titleize else new)
    changed = _rewrite_tags(conn, col, lambda t: new if t.lower() == old else t)
    conn.commit()
    return changed

def delete_tag(conn, col, tag):
    """Remove a tag from every row in col (and pre_edit snapshots when
    col.snapshot); arrays that empty store as NULL. Returns the number
    of rows changed, or None when the tag is not in the vocabulary."""
    tag = (tag or "").strip().lower()
    if not tag or tag not in tag_vocab(conn, col):
        return None
    changed = _rewrite_tags(conn, col, lambda t: None if t.lower() == tag else t)
    conn.commit()
    return changed

# The hand-editable enrichment columns. The webapp edit endpoint and the
# spreadsheet importer both write through apply_hand_edit, so the
# snapshot-then-update rule cannot drift between them.
EDITABLE_FIELDS = ("genre", "series", "series_number", "authors",
                   "narrator", "illustrator", "source_url")

def apply_hand_edit(conn, item_id, fields):
    """Write hand-edited enrichment columns for one item.

    `fields` maps EDITABLE_FIELDS names to column-ready values (tag
    fields already JSON-encoded). The first edit snapshots the enriched
    state into pre_edit as the revert target; later edits leave the
    snapshot alone. Returns False if the item has no enrichment row."""
    row = conn.execute(
        "SELECT " + ", ".join(EDITABLE_FIELDS) + ", pre_edit "
        "FROM enrichment WHERE item_id=?", (item_id,)).fetchone()
    if row is None:
        return False
    if row["pre_edit"] is None:
        snapshot = json.dumps({f: row[f] for f in EDITABLE_FIELDS})
        conn.execute("UPDATE enrichment SET pre_edit=? WHERE item_id=?",
                     (snapshot, item_id))
    conn.execute(
        "UPDATE enrichment SET hand_edited=1, "
        + ", ".join(f"{k}=?" for k in fields)
        + " WHERE item_id=?", (*fields.values(), item_id))
    conn.commit()
    return True

def bulk_user_tag(conn, ids, tag, action):
    """Add or remove one user tag across many items. Returns the number
    of rows actually changed; items already in the wanted state are left
    alone and not counted.

    Deliberately USER_TAGS-only, with no TagColumn parameter. Bulk-editing
    genre would have to snapshot pre_edit and mark rows edited, because
    genre is enrichment data and editing it by hand is a hand edit. A
    generic signature would invite exactly that wrong use."""
    if action not in ("add", "remove"):
        raise ValueError(f"action must be 'add' or 'remove', got {action!r}")
    tag = (tag or "").strip()
    if not tag or not ids:
        return 0
    # Snap to the spelling already in the vocabulary, so a bulk add cannot
    # fork "to reread" into a second casing.
    if action == "add":
        tag = normalize_tags(conn, USER_TAGS, [tag])[0]
    wanted = tag.lower()
    changed = 0
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, user_tags FROM items WHERE id IN ({placeholders})",
        tuple(ids)).fetchall()
    for r in rows:
        current = tags_from_json(r["user_tags"])
        has = any(t.lower() == wanted for t in current)
        if action == "add":
            if has:
                continue
            updated = current + [tag]
        else:
            if not has:
                continue
            updated = [t for t in current if t.lower() != wanted]
        conn.execute("UPDATE items SET user_tags=? WHERE id=?",
                     (tags_to_json(updated), r["id"]))
        changed += 1
    conn.commit()
    return changed

def merge_items(conn, keep_id, drop_id):
    """Merge duplicate catalog rows: keep_id survives, drop_id's bundles
    and downloads move over, the survivor's EMPTY fields fill from the
    dropped row, a tombstone in `merges` stops the next extract/reparse
    from resurrecting the dropped machine_name, and the dropped row is
    deleted. Irreversible. Returns False when ids are missing/equal."""
    keep = conn.execute("SELECT * FROM items WHERE id=?", (keep_id,)).fetchone()
    drop = conn.execute("SELECT * FROM items WHERE id=?", (drop_id,)).fetchone()
    if keep is None or drop is None or keep_id == drop_id:
        return False
    conn.execute("INSERT OR IGNORE INTO item_bundles (item_id, gamekey) "
                 "SELECT ?, gamekey FROM item_bundles WHERE item_id=?",
                 (keep_id, drop_id))
    conn.execute("DELETE FROM item_bundles WHERE item_id=?", (drop_id,))
    conn.execute("UPDATE downloads SET item_id=? WHERE item_id=?",
                 (keep_id, drop_id))
    for col in ("my_rating", "publisher", "cover_url", "cover_path",
                "user_comment"):
        if keep[col] is None and drop[col] is not None:
            conn.execute(f"UPDATE items SET {col}=? WHERE id=?",
                         (drop[col], keep_id))
    # user_tags unions rather than fill-if-empty: a merge is irreversible,
    # so discarding the dropped row's hand-typed tags is unrecoverable.
    merged = tags_from_json(keep["user_tags"])
    seen = {t.lower() for t in merged}
    for t in tags_from_json(drop["user_tags"]):
        if t.lower() not in seen:
            seen.add(t.lower())
            merged.append(t)
    conn.execute("UPDATE items SET user_tags=? WHERE id=?",
                 (tags_to_json(merged), keep_id))
    ekeep = conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                         (keep_id,)).fetchone()
    edrop = conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                         (drop_id,)).fetchone()
    if ekeep is not None and edrop is not None:
        for col in ("series", "series_number", "external_rating",
                    "rating_source", "source_url"):
            if ekeep[col] is None and edrop[col] is not None:
                conn.execute(f"UPDATE enrichment SET {col}=? WHERE item_id=?",
                             (edrop[col], keep_id))
        for col in TAG_FIELDS:
            if not tags_from_json(ekeep[col]) and tags_from_json(edrop[col]):
                conn.execute(f"UPDATE enrichment SET {col}=? WHERE item_id=?",
                             (edrop[col], keep_id))
    conn.execute("INSERT OR REPLACE INTO merges "
                 "(dropped_machine_name, kept_item_id) VALUES (?,?)",
                 (drop["machine_name"], keep_id))
    conn.execute("DELETE FROM enrichment WHERE item_id=?", (drop_id,))
    conn.execute("DELETE FROM items WHERE id=?", (drop_id,))
    conn.commit()
    return True

def cached_since(conn, source, since):
    """How many rows `source` cached at or after `since` (an ISO string).

    A live fetch is a cache write, so for a run that began at `since`
    this is that source's successful request count. Lives here because
    this module owns source_cache's schema, and one home for the query
    means one place to change if the cache ever changes shape.
    """
    return conn.execute(
        "SELECT COUNT(*) FROM source_cache WHERE source=? AND fetched_at >= ?",
        (source, since)).fetchone()[0]

def connect(path="catalog.db"):
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets the six harvest threads' readers run while one writer commits;
    # busy_timeout makes a blocked writer await the write lock rather than raise.
    # (":memory:" ignores WAL and reports "memory" -- harmless.)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn

def _migrate(conn):
    """Idempotent upgrades for databases created by older versions."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(enrichment)")}
    for col in ("source_url", "pre_edit"):
        if col not in cols:
            conn.execute(f"ALTER TABLE enrichment ADD COLUMN {col} TEXT")
            conn.commit()
    # INTEGER, not TEXT, so they get their own loop. hand_edited splits the
    # authorship question out of pre_edit, which now means only "what Revert
    # returns you to".
    for col in ("hand_edited", "enrich_override"):
        if col not in cols:
            conn.execute(f"ALTER TABLE enrichment ADD COLUMN {col} "
                         "INTEGER NOT NULL DEFAULT 0")
            conn.commit()
    icols = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    for col in ("user_tags", "user_comment"):
        if col not in icols:
            conn.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT")
            conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 1:
        _migrate_tags_to_arrays(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 2:
        _migrate_genre_case(conn)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 3:
        # Before this version "edited" was derived from pre_edit, so every
        # row with a snapshot is a hand edit. Reproduces old behaviour exactly.
        conn.execute("UPDATE enrichment SET hand_edited=1 "
                     "WHERE pre_edit IS NOT NULL")
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 4:
        _migrate_cover_filenames(conn)
        conn.execute("PRAGMA user_version = 4")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 5:
        # read_status is owner data on items; a nullable copy on
        # user_item_data lets a reset snapshot carry it. SQLite ADD COLUMN
        # cannot attach the CHECK, so migrated DBs rely on route validation
        # while fresh DBs (built from SCHEMA above) get the constraint.
        icols = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        if "read_status" not in icols:
            conn.execute("ALTER TABLE items ADD COLUMN read_status TEXT "
                         "NOT NULL DEFAULT 'unread'")
        uicols = {r["name"] for r in conn.execute(
            "PRAGMA table_info(user_item_data)")}
        if "read_status" not in uicols:
            conn.execute("ALTER TABLE user_item_data ADD COLUMN read_status TEXT")
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 6:
        # Purely a speed fix, unlike every migration above it: fetch_items
        # reads formats per item, and without this index each read scans
        # the whole downloads table, so the fetch was quadratic in the
        # catalog size. No columns change and no data is rewritten.
        conn.execute("CREATE INDEX IF NOT EXISTS ix_downloads_item_id "
                     "ON downloads(item_id)")
        conn.execute("PRAGMA user_version = 6")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 7:
        # Adds the game-ownership tables. CREATE TABLE IF NOT EXISTS in
        # SCHEMA already made them on this connection, so this only has to
        # carry the version forward -- the executescript above is the
        # migration for anything that ran an older build.
        conn.execute("PRAGMA user_version = 7")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 8:
        _migrate_secrets_out_of_cache_keys(conn)
        conn.execute("PRAGMA user_version = 8")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 9:
        # Adds source_quota, which remembers that a source's rate limit is
        # spent so a rerun need not spend a request rediscovering it. As
        # with migration 7, the executescript(SCHEMA) above has already
        # created the table on this connection; this only carries the
        # version forward. No existing data is read or rewritten - an
        # older database simply starts with no records, which is exactly
        # the state "nothing is known to be rate-limited".
        conn.execute("PRAGMA user_version = 9")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 10:
        # Adds source_failure, which remembers which titles a source could
        # not fetch and in how many runs. As with migrations 7 and 9, the
        # executescript(SCHEMA) above has already created the table on this
        # connection; this only carries the version forward. Nothing is
        # read or rewritten - an older database starts with no rows, which
        # is exactly the state "no failure has been observed yet".
        conn.execute("PRAGMA user_version = 10")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 11:
        # Adds harvest_run, one row per source per run: what it answered,
        # what it fetched live, what failed, and whether the budget died
        # in that run. As with migrations 7, 9 and 10, the
        # executescript(SCHEMA) above has already created the table on
        # this connection; this only carries the version forward. An
        # older database simply starts with no run history.
        conn.execute("PRAGMA user_version = 11")
        conn.commit()
    if conn.execute("PRAGMA user_version").fetchone()[0] < 12:
        # Re-keys external_keys on (gamekey, machine_name) and adds
        # hidden_keys. As with migrations 7 and 9-11, executescript(SCHEMA)
        # above has already created hidden_keys on this connection, so only
        # external_keys needs rebuilding here.
        _migrate_external_keys_to_machine_name(conn)
        conn.execute("PRAGMA user_version = 12")
        conn.commit()

def _legacy_tags(value):
    """v1.4-era comma-joined string -> JSON-array string; None passes
    through; values already shaped like a JSON array are left alone.
    Known, accepted limitation: names containing ', ' split wrongly once
    (fixable afterwards in the tag editor)."""
    if value is None:
        return None
    try:
        if isinstance(json.loads(value), list):
            return value
    except (ValueError, TypeError):
        pass
    return tags_to_json(value.split(","))

def _migrate_tags_to_arrays(conn):
    # pre_edit snapshots hold *copies* of the tag columns, so they must be
    # converted too, or a later revert would resurrect the string format.
    # Tolerate tables missing tag columns (hand-built or partial DBs).
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(enrichment)")}
    fields = [f for f in TAG_FIELDS if f in cols]
    rows = conn.execute(
        "SELECT item_id, pre_edit" + "".join(f", {f}" for f in fields)
        + " FROM enrichment").fetchall()
    for r in rows:
        pre = r["pre_edit"]
        if pre is not None:
            snap = json.loads(pre)
            for f in TAG_FIELDS:
                if f in snap:
                    snap[f] = _legacy_tags(snap[f])
            pre = json.dumps(snap, ensure_ascii=False)
        conn.execute(
            "UPDATE enrichment SET pre_edit=?"
            + "".join(f", {f}=?" for f in fields) + " WHERE item_id=?",
            (pre, *(_legacy_tags(r[f]) for f in fields), r["item_id"]))

def _migrate_genre_case(conn):
    # One-time collapse of case variants (e.g. 'fiction' vs 'Fiction'):
    # canonical spelling = most frequent variant; ties prefer the
    # titleized form, then alphabetical. pre_edit snapshots hold copies
    # of genre, so they are rewritten too or a revert would resurrect
    # the merged variant.
    counts = {}
    rows = conn.execute("SELECT item_id, genre, pre_edit FROM enrichment").fetchall()
    for r in rows:
        snap = json.loads(r["pre_edit"]) if r["pre_edit"] else {}
        for t in tags_from_json(r["genre"]) + tags_from_json(snap.get("genre")):
            counts[t] = counts.get(t, 0) + 1
    groups = {}
    for t in counts:
        groups.setdefault(t.lower(), []).append(t)
    # titleize the winner too: a surviving all-lowercase tag would pull
    # future correctly-cased input down to lowercase via the snap rule.
    canon = {low: titleize(sorted(vs, key=lambda v: (-counts[v], v != titleize(v), v))[0])
             for low, vs in groups.items()}
    remap = lambda val: tags_to_json(
        [canon[t.lower()] for t in tags_from_json(val)])
    for r in rows:
        pre = r["pre_edit"]
        if pre is not None:
            snap = json.loads(pre)
            if "genre" in snap:
                snap["genre"] = remap(snap["genre"])
            pre = json.dumps(snap, ensure_ascii=False)
        conn.execute("UPDATE enrichment SET genre=?, pre_edit=? WHERE item_id=?",
                     (remap(r["genre"]), pre, r["item_id"]))

def _migrate_cover_filenames(conn):
    # One-time rename of legacy covers/{id}.jpg files to the
    # machine_name-derived scheme, so a later reset can re-link them
    # instead of re-downloading. The stored cover_path is the source path;
    # a missing file is skipped but its cover_path is still rewritten, so
    # the next extract re-fetches it under the new name. Imported locally
    # to avoid a module-load cycle (covers imports nothing from db).
    from pathlib import Path
    from humble_catalog.covers import cover_filename
    # Tolerate partial/hand-built items tables (as the tag migrations do):
    # a table without cover_path has nothing to rename.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    if "cover_path" not in cols or "machine_name" not in cols:
        return
    rows = conn.execute(
        "SELECT id, machine_name, cover_path FROM items "
        "WHERE cover_path IS NOT NULL").fetchall()
    for r in rows:
        new_name = cover_filename(r["machine_name"])
        old_path = Path(r["cover_path"])
        if old_path.name == new_name:
            continue  # already on the new scheme
        new_cover_path = f"{old_path.parent.as_posix()}/{new_name}"
        if old_path.exists():
            old_path.rename(old_path.parent / new_name)
        conn.execute("UPDATE items SET cover_path=? WHERE id=?",
                     (new_cover_path, r["id"]))
    conn.commit()

def _migrate_external_keys_to_machine_name(conn):
    """Re-key external_keys from (gamekey, human_name) to (gamekey, machine_name).

    The old key is not unique. Humble ships each storefront of a
    multi-store product as its own tpk and every one carries the same
    human_name, so store_order's INSERT OR REPLACE turned the violated
    constraint into a silent last-write-wins. Measured on a 2,275-row
    catalog: raw_orders holds 2,278 tpks, and in both collisions the
    survivor was the less useful key -- one kept a gog key over the steam
    one, the other an expired gift key over the steam one -- so the report
    was checking two games against the wrong store's library.

    A fresh database already has the new shape from SCHEMA, so the column
    check makes this a no-op there; only a database written by an older
    build is rebuilt. SQLite cannot alter a primary key, hence the copy.

    Rows whose `raw` will not parse are skipped rather than aborting on
    the NOT NULL column. No such row exists in the author's catalog --
    all 2,278 tpks across 13 key types carry a machine_name -- but a
    migration that leaves the database unopenable is the worst failure
    available here, so the guard is cheap insurance against future data.

    That guard has to be json_valid inside a CASE, not `json_extract(...)
    IS NOT NULL`: json_extract RAISES on malformed JSON rather than
    returning NULL, so the null test never gets the chance to filter and
    one bad row takes down the whole migration. CASE is documented to
    evaluate lazily, which a WHERE-clause AND is not, and the subquery
    keeps the projection from re-evaluating it unguarded.

    The three keys the old key already dropped are NOT recovered here:
    they are not in the table being copied, only in raw_orders. keys.py
    names them and points at `reparse`, which is the command that can.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(external_keys)")}
    if "machine_name" in cols:
        return
    conn.executescript("""
        CREATE TABLE external_keys_new (
          gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
          machine_name TEXT NOT NULL,
          human_name TEXT, key_type TEXT, raw TEXT,
          PRIMARY KEY (gamekey, machine_name));
        INSERT OR IGNORE INTO external_keys_new
          (gamekey, machine_name, human_name, key_type, raw)
          SELECT gamekey, mn, human_name, key_type, raw FROM (
            SELECT gamekey, human_name, key_type, raw,
                   CASE WHEN json_valid(raw)
                        THEN json_extract(raw, '$.machine_name') END AS mn
              FROM external_keys)
           WHERE mn IS NOT NULL;
        DROP TABLE external_keys;
        ALTER TABLE external_keys_new RENAME TO external_keys;
    """)

def _rekey_without_secrets(query, secrets):
    """A cache key with its credential params removed, or itself unchanged.

    Rebuilt through the same helper get_json uses, so a rekeyed row lands
    on exactly the key a lookup now builds. The optional '|<json body>'
    tail (hardcover's GraphQL) is carried across untouched.
    """
    from humble_catalog.sources.base import cache_key_params
    from urllib.parse import parse_qsl, urlencode
    base, sep, body = query.partition("|")
    url, mark, qs = base.partition("?")
    if not mark:
        return query
    kept = cache_key_params(parse_qsl(qs, keep_blank_values=True), secrets)
    return url + "?" + urlencode(sorted(kept)) + sep + body

def _migrate_secrets_out_of_cache_keys(conn):
    # Rows written before API keys were excluded from the cache key are
    # good responses stranded under an unreachable key: rekey them rather
    # than let the next harvest refetch the lot. Rows fetched under a
    # since-rotated key come back to life the same way. Where two keys
    # cached the same request, the collision resolves to the fresher
    # response - hence oldest-first, so the newer row overwrites.
    # Imported locally, as the covers migration does: enrich imports db.
    from humble_catalog.enrich import SOURCE_CLASSES
    for name, cls in SOURCE_CLASSES.items():
        secrets = getattr(cls, "secret_params", ())
        if not secrets:
            continue
        rows = conn.execute(
            "SELECT query FROM source_cache WHERE source=? ORDER BY fetched_at",
            (name,)).fetchall()
        for r in rows:
            new = _rekey_without_secrets(r["query"], secrets)
            if new == r["query"]:
                continue
            conn.execute("DELETE FROM source_cache WHERE source=? AND query=?",
                         (name, new))
            conn.execute("UPDATE source_cache SET query=? WHERE source=? AND query=?",
                         (new, name, r["query"]))
    conn.commit()

def fetch_items(conn):
    # Flattened per-item catalog view shared by /api/items and CSV export,
    # so the two serializations cannot drift.
    rows = conn.execute(
        "SELECT i.*, e.genre, e.series, e.series_number, e.authors, e.narrator, "
        "e.illustrator, e.external_rating, e.rating_source, e.status, "
        "e.source_url, e.pre_edit, e.hand_edited, e.enrich_override "
        "FROM items i JOIN enrichment e ON e.item_id = i.id ORDER BY i.name").fetchall()
    out = []
    for r in rows:
        bundles = conn.execute(
            "SELECT b.name, b.url, b.purchased_at FROM bundles b "
            "JOIN item_bundles ib ON ib.gamekey = b.gamekey "
            "WHERE ib.item_id = ? ORDER BY b.purchased_at", (r["id"],)).fetchall()
        fmts = conn.execute(
            "SELECT formats FROM downloads WHERE item_id=? AND kind='humble'",
            (r["id"],)).fetchall()
        item = dict(r)
        # TAG_FIELDS is enrichment-only; user_tags lives on items. This is
        # the one place the two tables' tag columns meet.
        for f in (*TAG_FIELDS, "user_tags"):
            item[f] = tags_from_json(item[f])
        # pre_edit no longer answers "was this hand-edited?" - it only says a
        # Revert target exists. A re-enriched row keeps its snapshot but its
        # visible values came from a source, so it is not "edited".
        pre = item.pop("pre_edit")
        hand = item.pop("hand_edited")
        item["edited"] = bool(hand)
        item["re_enriched"] = pre is not None and not hand
        item["override"] = bool(item.pop("enrich_override"))
        item["bundles"] = [dict(b) for b in bundles]
        item["formats"] = sorted({f for row2 in fmts
                                  for f in (row2["formats"] or "").split(",") if f})
        out.append(item)
    return out
