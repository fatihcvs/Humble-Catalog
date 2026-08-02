"""Known-answer battery for the db-schema inventory row.

Covers humble_catalog/db.py: `connect`, the schema it applies, and every
step of `_migrate`.

A migration is the one place in this project where a defect destroys data
the owner cannot re-derive, and it is also the hardest thing to probe by
running the happy path: a fresh database takes every migration as a no-op,
so `connect()` on an empty file exercises almost none of this code. Each
case here therefore builds a LEGACY database by hand - the old schema, the
old data shapes - and drives it forward, which is the only way the rewrite
steps run at all.

Titles and names are invented, from docs/TEST-DATA.md.
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db                              # noqa: E402

PASS, FAIL = [], []
GROUPS = {}


def check(label, got, want, group=None):
    if group:
        GROUPS[label] = group
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def check_no_raise(label, fn, group=None):
    if group:
        GROUPS[label] = group
    try:
        fn()
    except Exception as exc:
        FAIL.append(f"{label}: raised {type(exc).__name__}: {exc}")
    else:
        PASS.append(label)


def fresh_path():
    return Path(tempfile.mkdtemp()) / "catalog.db"


# The subset of the pre-migration schema the migrations actually touch,
# written as an older build wrote it: no user_version, comma-joined tag
# columns, external_keys keyed on (gamekey, human_name), and none of the
# columns the ALTER steps add.
LEGACY = """
CREATE TABLE bundles (gamekey TEXT PRIMARY KEY, name TEXT, url TEXT,
                      purchased_at TEXT);
CREATE TABLE items (id INTEGER PRIMARY KEY, machine_name TEXT UNIQUE,
                    name TEXT, type TEXT, publisher TEXT, cover_url TEXT,
                    cover_path TEXT, my_rating INTEGER, type_overridden INTEGER
                    NOT NULL DEFAULT 0);
CREATE TABLE enrichment (item_id INTEGER PRIMARY KEY REFERENCES items(id),
                         genre TEXT, series TEXT, series_number REAL,
                         authors TEXT, narrator TEXT, illustrator TEXT,
                         external_rating REAL, rating_source TEXT,
                         match_confidence REAL,
                         status TEXT NOT NULL DEFAULT 'pending',
                         candidates TEXT);
CREATE TABLE external_keys (gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
                            human_name TEXT NOT NULL, key_type TEXT, raw TEXT,
                            PRIMARY KEY (gamekey, human_name));
"""


def legacy_db(rows=True, external=()):
    """A database as an older build left it, ready for connect() to migrate."""
    path = fresh_path()
    raw = sqlite3.connect(str(path))
    raw.executescript(LEGACY)
    raw.execute("INSERT INTO bundles (gamekey, name) VALUES ('abc123', "
                "'Humble Book Bundle: Test by Example Press')")
    if rows:
        raw.execute("INSERT INTO items (machine_name, name, type, cover_path) "
                    "VALUES ('graywaters_ebook', 'Gray Waters', 'ebook', "
                    "'covers/legacy-name.jpg')")
        raw.execute(
            "INSERT INTO enrichment (item_id, genre, authors, status) "
            "VALUES (1, 'fantasy, epic fantasy', 'Alex Penner, Sam Coder', "
            "'matched')")
    for human, payload in external:
        raw.execute("INSERT INTO external_keys (gamekey, human_name, key_type, "
                    "raw) VALUES ('abc123', ?, 'steam', ?)", (human, payload))
    raw.commit()
    raw.close()
    return path


# --------------------------------------------------------------------
# A fresh database
# --------------------------------------------------------------------
path = fresh_path()
conn = db.connect(path)
version = conn.execute("PRAGMA user_version").fetchone()[0]
check("fresh: the schema lands at the current version", version, 12)
check("fresh: foreign keys are enforced",
      conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
check("fresh: the journal is WAL, which is what lets readers run during a "
      "harvest write", conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
tables = {r["name"] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
for table in ("bundles", "items", "item_bundles", "downloads", "external_keys",
              "hidden_keys", "enrichment", "raw_orders", "source_cache",
              "user_item_data", "run_status", "merges", "dismissed_pairs",
              "games", "game_imports", "source_quota", "source_failure",
              "harvest_run"):
    check(f"fresh: table {table} exists", table in tables, True)
check("fresh: external_keys is keyed on machine_name, not human_name",
      "machine_name" in {r["name"] for r in
                         conn.execute("PRAGMA table_info(external_keys)")}, True)
check("fresh: the downloads index from migration 6 exists",
      conn.execute("SELECT COUNT(*) c FROM sqlite_master WHERE type='index' "
                   "AND name='ix_downloads_item_id'").fetchone()["c"], 1)
conn.close()

# Re-opening must be a no-op, not a second migration.
conn = db.connect(path)
check("fresh: re-opening keeps the version",
      conn.execute("PRAGMA user_version").fetchone()[0], 12)
conn.close()
check_no_raise("fresh: a third open still succeeds",
               lambda: db.connect(path).close())

# --------------------------------------------------------------------
# A legacy database, migrated forward
# --------------------------------------------------------------------
path = legacy_db(external=[
    ("Twin Lantern", json.dumps({"machine_name": "twinlantern_steam"}))])
conn = db.connect(path)
check("legacy: the version is carried to the current one",
      conn.execute("PRAGMA user_version").fetchone()[0], 12)

ecols = {r["name"] for r in conn.execute("PRAGMA table_info(enrichment)")}
for col in ("source_url", "pre_edit", "hand_edited", "enrich_override"):
    check(f"legacy: enrichment.{col} was added", col in ecols, True)
icols = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
for col in ("user_tags", "user_comment", "read_status"):
    check(f"legacy: items.{col} was added", col in icols, True)
check("legacy: read_status defaults to unread rather than NULL",
      conn.execute("SELECT read_status FROM items").fetchone()["read_status"],
      "unread")

# The data rewrites, which are what a migration can actually destroy.
row = conn.execute("SELECT genre, authors FROM enrichment").fetchone()
check("legacy: a comma-joined genre became a JSON array",
      db.tags_from_json(row["genre"]), ["Fantasy", "Epic Fantasy"])
check("legacy: a comma-joined author list became a JSON array",
      db.tags_from_json(row["authors"]), ["Alex Penner", "Sam Coder"])
check("legacy: the genre was titleized, the authors were not - person "
      "names are not a managed vocabulary",
      (db.tags_from_json(row["genre"])[0], db.tags_from_json(row["authors"])[0]),
      ("Fantasy", "Alex Penner"))
check("legacy: the item survived the migration",
      conn.execute("SELECT name FROM items").fetchone()["name"], "Gray Waters")
check("legacy: the bundle survived",
      conn.execute("SELECT COUNT(*) c FROM bundles").fetchone()["c"], 1)

check("legacy: external_keys was re-keyed and the row kept its data",
      dict(conn.execute("SELECT gamekey, machine_name, human_name, key_type "
                        "FROM external_keys").fetchone()),
      {"gamekey": "abc123", "machine_name": "twinlantern_steam",
       "human_name": "Twin Lantern", "key_type": "steam"})
check("legacy: nothing still references the rebuilt table's old name",
      conn.execute("SELECT COUNT(*) c FROM sqlite_master "
                   "WHERE name='external_keys_new'").fetchone()["c"], 0)
conn.close()
check_no_raise("legacy: re-opening a migrated database succeeds",
               lambda: db.connect(path).close())

# hand_edited is derived from pre_edit exactly once, reproducing the old
# meaning of "edited" for databases that predate the column.
path = legacy_db()
raw = sqlite3.connect(str(path))
raw.execute("ALTER TABLE enrichment ADD COLUMN pre_edit TEXT")
raw.execute("UPDATE enrichment SET pre_edit='{}'")
raw.commit()
raw.close()
conn = db.connect(path)
check("legacy: a row carrying a snapshot is marked hand-edited",
      conn.execute("SELECT hand_edited FROM enrichment").fetchone()["hand_edited"],
      1)
conn.close()

# --------------------------------------------------------------------
# The documented guard: a row whose `raw` will not parse is SKIPPED, and
# the migration still completes. json_extract RAISES on malformed JSON,
# so without the json_valid CASE one bad row leaves the database
# unopenable - the worst failure available here.
# --------------------------------------------------------------------
path = legacy_db(external=[
    ("Twin Lantern", json.dumps({"machine_name": "twinlantern_steam"})),
    ("Cinder Vale", "{not json at all"),
    ("Verdant Reach", json.dumps({"key_type": "uplay"}))])  # no machine_name
check_no_raise("guard: a malformed raw payload does not abort the migration",
               lambda: db.connect(path).close())
conn = db.connect(path)
check("guard: the parseable row was carried across",
      [r["machine_name"] for r in conn.execute(
          "SELECT machine_name FROM external_keys ORDER BY machine_name")],
      ["twinlantern_steam"])
check("guard: the database is fully migrated despite the skipped rows",
      conn.execute("PRAGMA user_version").fetchone()[0], 12)
conn.close()

# Every row unparseable: the migration must still complete, leaving an
# empty table rather than an unopenable database.
path = legacy_db(external=[("Cinder Vale", "{not json"),
                           ("Hollowmere", None)])
check_no_raise("guard: every row unparseable still migrates",
               lambda: db.connect(path).close())
conn = db.connect(path)
check("guard: and leaves the table empty rather than broken",
      conn.execute("SELECT COUNT(*) c FROM external_keys").fetchone()["c"], 0)
conn.close()

# --------------------------------------------------------------------
# A database with no external_keys rows at all, and one already migrated
# --------------------------------------------------------------------
path = legacy_db(rows=False)
check_no_raise("empty: a legacy database with no items migrates",
               lambda: db.connect(path).close())
conn = db.connect(path)
check("empty: it still reaches the current version",
      conn.execute("PRAGMA user_version").fetchone()[0], 12)
conn.close()


def group_of(line):
    for label, group in GROUPS.items():
        if line.startswith(label + ":"):
            return group
    return "BROKEN"


def main():
    for line in FAIL:
        print(f"{group_of(line):<6} {line}")
    total = len(PASS) + len(FAIL)
    print(f"\ndb-schema: {len(PASS)}/{total} held")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
