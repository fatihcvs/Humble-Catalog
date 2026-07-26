# Catalog reset & rebuild — design

Date: 2026-07-24

## Problem

Populating the catalog couples two very different kinds of work:

- **Downloading** — expensive, network-bound, rate-limited: fetching each
  bundle's raw order JSON from Humble (`raw_orders`) and each item's
  external metadata from the book APIs (`source_cache`).
- **Deriving** — cheap, local, deterministic: parsing raw orders into
  `items`/`bundles`, classifying types, and matching enrichment
  candidates.

When a bug is found in a derived step, the only clean-slate remedy today
is deleting `catalog.db` — but that file holds the download caches *and*
the owner's hand-entered data, so a reset forces a full re-download and
loses manual work. `reparse` re-runs the parse over `raw_orders`, but it
is an upsert (`INSERT OR REPLACE`/`INSERT OR IGNORE`, [store.py]) that
never deletes, so stale or orphaned rows from a parser bug survive it.

## Goal

Let the owner **download once and rebuild the derived catalog as many
times as needed**, offline, from the download caches — with a true
clean slate (stale rows gone), while preserving the small set of
genuinely hand-authored, non-reconstructable fields.

## Core invariant

The derived catalog is a pure function of the preserved layer. Anything
`reset` wipes must be fully reconstructable — with **no network calls**
— from:

- `raw_orders` (Humble bundle JSON),
- `source_cache` (external-API metadata),
- the `covers/` image files,
- `user_item_data` (owner ratings/tags/comments — see below).

## Preserve / wipe split

`reset` preserves the four items above and wipes the derived layer.

| Preserved (never wiped) | Wiped by `reset` (FK-safe order) |
|---|---|
| `raw_orders` | `item_bundles` |
| `source_cache` | `downloads` |
| `covers/*.jpg` (files) | `external_keys` |
| `user_item_data` | `enrichment` |
| | `merges` |
| | `dismissed_pairs` |
| | `run_status` |
| | `items` |
| | `bundles` |

Deletion runs child-before-parent so `PRAGMA foreign_keys = ON` is
satisfied: the association/leaf tables first, then `items`, then
`bundles`.

### What is deliberately NOT preserved

Dropped on every reset, by explicit choice — these are derived cleanup
state the owner is content to redo:

- `items.type_overridden` (manual type corrections),
- `enrichment.hand_edited` / `enrichment.pre_edit` and the hand-edited
  enrichment column values (genre, series, authors, …),
- `merges` (dedupe decisions) and `dismissed_pairs`.

### What IS preserved

`my_rating`, `user_tags`, and `user_comment` — three fields on `items`
that are hand-authored and not reconstructable from any cache. They are
kept via a snapshot-and-restore mechanism (below) rather than by leaving
them in `items` (which `reset` must wipe to clear stale derived rows).

## Command surface

Keep `extract` as the normal one-shot; add `reset`; extend `reparse`.

- **`extract`** — unchanged externally. Incremental download (skips
  bundles already in `raw_orders`, fetches only new keys via
  `get_order`), re-parses the full cache via `_reparse_cached`, then
  tops up covers. Remains the everyday command.
- **`reset`** — new. Snapshots user data, wipes the derived layer,
  preserves the download caches. **Wipe only** — it does not rebuild;
  it prints the next steps. Guarded by a typed confirmation.
- **`reparse`** — gains offline cover **re-linking** (below) so that a
  post-reset `reparse` restores items, bundles, *and* cover links with
  zero network calls.

Full clean-slate loop:

```
reset        # wipe derived, keep caches + user data + covers
reparse      # rebuild items/bundles from raw_orders, re-link covers (offline)
harvest      # no-op if source_cache already populated
enrich        # rebuild enrichment from source_cache (offline)
```

### `reset` confirmation gate

`reset` drops hand edits, type overrides, and merges, so it follows the
existing destructive-action pattern used by `enrich.override_edited`:

- Interactive: require the user to type `RESET` verbatim; any other
  input aborts with nothing changed.
- Non-interactive (`not sys.stdin.isatty()`): refuse and exit without
  changes. There is deliberately no `--yes` flag — this must never fire
  from a script.

After a successful wipe it prints a summary and the next-step hint
(`reparse` → `harvest` → `enrich`).

## User-data preservation (snapshot & restore)

New table, a third preserved layer keyed by the rebuild-stable
`machine_name`:

```sql
CREATE TABLE IF NOT EXISTS user_item_data (
  machine_name TEXT PRIMARY KEY,
  my_rating INTEGER, user_tags TEXT, user_comment TEXT);
```

**Snapshot (in `reset`, before wiping `items`):**

```sql
DELETE FROM user_item_data;
INSERT INTO user_item_data (machine_name, my_rating, user_tags, user_comment)
SELECT machine_name, my_rating, user_tags, user_comment FROM items
WHERE my_rating IS NOT NULL OR user_tags IS NOT NULL
   OR user_comment IS NOT NULL;
```

The `DELETE` first is essential: it prevents a value the owner has since
*cleared* (set back to NULL) from resurrecting out of a prior snapshot.
`user_item_data` is never wiped by `reset`.

**Restore (in `store_order`, insert branch only):** when `store_order`
creates a *new* item (the `row is None` branch, [store.py:22]), it looks
up `machine_name` in `user_item_data` and, if present, writes the three
fields onto the freshly inserted row.

Restoring only on the insert branch is what keeps this inert during
normal operation: a routine `extract`/`reparse` finds items already
present and takes the update branch, so live user edits are never
overwritten by a stale snapshot. The restore fires only when an item is
being re-created — i.e. during a post-reset rebuild.

Rejected alternative: permanently moving these three columns out of
`items` into `user_item_data`, joined at read time. Architecturally
cleaner, but it would ripple through the webapp edit/read endpoints,
`fetch_items`, `bulk_user_tag`, `merge_items`, and export. The
snapshot-and-restore path achieves the same preservation for a fraction
of the change.

## Covers: re-key by machine_name

Cover files today are named `covers/{item_id}.jpg` ([extract.py:65]),
keyed by the DB id — which is regenerated on rebuild, so a reset would
orphan every file and force a full re-download. Re-key them by the
rebuild-stable `machine_name` instead.

### Filename scheme

`covers/{safe_slug}-{hash12}.jpg`, where:

- `safe_slug` = `machine_name` lowercased, with every character outside
  `[a-z0-9_-]` replaced by `_`.
- `hash12` = `blake2b(machine_name.encode(), digest_size=6).hexdigest()`
  — a 12-hex-char digest over the *raw* machine_name, not the slug.

The hash suffix makes the filename collision-proof, case-safe, and
reserved-name-safe on Windows (the owner's platform), where `safe_slug`
alone could collide (`Foo` vs `foo`) or be illegal (`con`, `nul`). The
DB `items.cover_path` remains the authoritative item→file mapping; the
filename only has to be a stable, safe 1:1 function of `machine_name`.

blake2b is used rather than SHA-1: the digest is non-adversarial (inputs
are Humble's own identifiers), so collision resistance is not the
concern — but blake2b is stdlib, lets `digest_size` set the truncation
directly, and carries none of SHA-1's FIPS-mode breakage
(`hashlib.sha1()` raises under FIPS without `usedforsecurity=False`) or
"why is a broken hash here" review friction. 48 bits (12 hex) puts
birthday collisions near 50% only around ~16M items — effectively zero
for a personal library.

A single helper derives the name, e.g. `cover_filename(machine_name)`,
used by both the re-link and download paths.

### Download logic splits in two

- **Offline re-link** (runs in `reparse`, filesystem-only): for each
  item whose `covers/{...}.jpg` exists on disk, set `cover_path` without
  any network call. This is how a post-reset `reparse` gets covers back.
- **Online download** (stays in `extract`): only items whose cover file
  is absent are fetched from Humble (still throttled, login required).

### One-time migration

A migration in `db._migrate`, gated by a `PRAGMA user_version` bump so
it runs exactly once, renames existing `covers/{item_id}.jpg` files to
`covers/{safe_slug}-{hash12}.jpg` using the current `items` table
(`id → machine_name`) and updates each row's `cover_path`. No
re-download. Files with no matching item row are left untouched.

## Module layout

- `humble_catalog/reset.py` — new module: `run(db_path, _conn=None,
  _input=None)` doing snapshot → confirm → wipe → summary. Kept separate
  from `extract.py` because it spans enrichment and dedupe tables, not
  just the extract-owned ones, and to keep each file focused.
- `humble_catalog/covers.py` — new module: `cover_filename(machine_name)`
  and the offline re-link/existence helpers, shared by `extract` and
  `reparse`. (Alternatively these live in `extract.py`; a small module
  keeps the naming logic testable in isolation.)
- `store.py` — restore hook on the insert branch.
- `extract.py` — cover download uses `cover_filename`; `reparse` calls
  the offline re-link step.
- `db.py` — `user_item_data` in `SCHEMA`; cover-rename migration in
  `_migrate`.
- `__main__.py` — `reset` subcommand wired to `reset.run`.

## Testing

All fixtures/examples use invented names from `docs/TEST-DATA.md` (e.g.
machine_name `cooltower_android`); run `.venv/Scripts/python
scripts/leak_check.py` after adding tests or fixtures.

- **reset wipe/preserve**: after `reset`, derived tables are empty while
  `raw_orders`, `source_cache`, and `user_item_data` retain their rows;
  cover files remain on disk.
- **round-trip**: seed a catalog with ratings/tags/comments, `reset`,
  then `reparse` + `enrich` against the caches; assert items/bundles are
  rebuilt and the three user fields are reattached by machine_name,
  while hand edits / type overrides / merges are gone.
- **cleared-value safety**: a rating set then cleared to NULL does not
  reappear after reset+rebuild.
- **confirmation gate**: typing the wrong word aborts with no changes;
  non-interactive invocation refuses.
- **cover filename**: slug/hash generation including Windows edge cases
  — case-only difference, reserved name (`con`), and a non-slug
  character all yield distinct, safe filenames.
- **offline re-link**: with a cover file present, `reparse` sets
  `cover_path` and makes no HTTP call.
- **migration**: existing `covers/{id}.jpg` files are renamed once to
  the new scheme and `cover_path` updated; a second run is a no-op.

## Out of scope

- No `--yes`/scriptable `reset`.
- No partial/selective reset (single bundle, single table); this is
  all-or-nothing by design.
- No change to how `extract` decides which bundles are new, or to the
  enrichment matching logic.
