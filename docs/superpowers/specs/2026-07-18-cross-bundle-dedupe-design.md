# Cross-bundle duplicate merge (v1.7)

Approved 2026-07-18.

## Goal

The same book bought in two bundles sometimes lands as two catalog rows
("Building Widget Services 2e" vs "Building Widget Services, 2nd Edition").
A "Duplicates" panel in the viewer suggests such pairs; the user merges
them into one row (or dismisses false pairs). Merged rows stay merged
across future `extract`/`reparse` runs.

## Facts (measured against the real DB, 2026-07-18)

- ~15 duplicate pairs in the catalog: 3 exact name+type matches (same
  title twice as audiobook), 12 cosmetic variants (case, "ALL CAPS,
  Vol. 1" vs "All Caps Vol. 1", "2e" vs "2nd Edition", curly vs
  straight quotes).
- Known false-positive trap: naive punctuation stripping makes
  "Learn C#" == "Learn C". `#`/`+` must stay significant.
- Items are upserted from cached raw orders by `machine_name`; a deleted
  row resurrects on the next `extract`/`reparse` unless remembered.

## Decisions already settled

- Confirmed duplicates **merge into one row** (not link/group, not hide).
- Review happens in the **viewer UI**, styled after the review queue.
- Merge rule: **survivor wins + gap-fill** — the kept row keeps all its
  values; only its empty fields fill from the dropped row. Bundles and
  downloads always union.
- Candidate generation is **normalized-equality only** (approach A):
  same type + same `dedupe_key`. No fuzzy scoring, no cross-type pairs
  (an ebook and audiobook of the same title are legitimately separate).
- Merges are **irreversible** (hence UI confirm); no pre_edit interplay:
  the survivor's snapshot is untouched, the dropped row's is discarded.

## Scope

**In:** `dedupe_key` normalizer; `merges` tombstone + `dismissed_pairs`
tables (schema + idempotent migration); `db.merge_items`; store-layer
tombstone handling on upsert; `GET /api/duplicates`, `POST /api/merge`,
`POST /api/dismiss_pair`; Duplicates panel with count badge, keep-this
two-click confirm and not-duplicates dismissal; manual pair picker for
duplicates the detector cannot see (subtitle variants); tests; live
browser smoke test on the real pairs.

**Out:** fuzzy candidate scoring; cross-type merging; un-merge; merging
more than two rows in one action (a 3-row group resolves via two
pairwise merges); CLI interface; any change to CSV export shape.

## 1. Duplicate detection

- `dedupe_key(name)`: lowercase; punctuation replaced by space **except**
  `#` and `+`, which stay attached to their word; edition wording
  collapsed to the bare number — "2nd Edition", ", 2e", "2nd ed." all
  end as token "2"; whitespace collapsed.
- Candidates: items sharing `(dedupe_key(name), type)`, minus dismissed
  pairs. Computed live per request (2.5k items — instant); no stored
  candidate state, so fixes and new bundles reflect immediately.
- A group of 3+ rows appears as one group in the panel.

## 2. Data model

Two new tables (created via `SCHEMA`; both `CREATE TABLE IF NOT EXISTS`,
so existing DBs pick them up on `connect` — no version bump needed):

- `merges(dropped_machine_name TEXT PRIMARY KEY,
  kept_item_id INTEGER NOT NULL REFERENCES items(id))` — the tombstone.
  On upsert of a parsed item whose `machine_name` has a tombstone, the
  store layer does **not** insert an item; it links the current bundle
  to `kept_item_id` in `item_bundles` instead (INSERT OR IGNORE) and
  skips the item's downloads (the survivor already carries the merged
  downloads).
- `dismissed_pairs(a TEXT NOT NULL, b TEXT NOT NULL, PRIMARY KEY (a, b))`
  — machine_name pairs the user marked "not duplicates", stored with
  `a < b` (sorted) so each pair exists once. Keyed by machine_name, not
  row id, so dismissals survive re-extracts. `/api/duplicates` excludes
  a candidate pair when its sorted machine_names are in this table; a
  3+ group only drops members that are dismissed against *every* other
  member of the group.

## 3. Merge operation

`db.merge_items(conn, keep_id, drop_id)` in one transaction (single
commit at the end; returns False when either id is missing, True on
success):

1. `item_bundles`: INSERT OR IGNORE the dropped row's links onto
   `keep_id`, then delete the dropped row's links.
2. `downloads`: UPDATE `item_id` to `keep_id`.
3. Gap-fill `items` columns on the survivor where NULL: `my_rating`,
   `publisher`, `cover_url`, `cover_path`. `type`/`type_overridden`
   stay the survivor's.
4. Gap-fill enrichment: scalar fields (`series`, `series_number`,
   `external_rating`, `rating_source`, `source_url`) fill where the
   survivor's is NULL; tag fields (`genre`, `authors`, `narrator`,
   `illustrator`) fill only where the survivor's array is empty.
   Survivor's `status`, `candidates`, and `pre_edit` are untouched.
5. Tombstone: INSERT the dropped row's `machine_name` -> `keep_id` into
   `merges`.
6. Delete the dropped row's `enrichment` and `items` rows.

## 4. Web API

- `GET /api/duplicates` -> `{"groups": [[item, item, ...], ...]}` where
  each item carries `id`, `machine_name`, `name`, `type`, `cover_path`,
  `publisher`, `my_rating`, `edited` flag, enrichment summary (genre
  tags, series), and its bundle names. Groups sorted by name.
- `POST /api/merge` `{keep_id, drop_id}` -> 400 unless both exist,
  differ, and share the same `type` (an ebook and its audiobook stay
  separate; the rule holds for manual pairs too); runs `merge_items`;
  `{"ok": true}`.
- `POST /api/dismiss_pair` `{id_a, id_b}` -> 400 unless both exist and
  differ; stores the sorted machine_name pair; `{"ok": true}`.

## 5. Viewer UI

- A "Duplicates" panel beside the review queue, with a count badge
  (number of candidate groups); hidden when zero.
- Each group renders its items side by side: cover, name, type badge,
  publisher, bundle names, genre badges, series, rating stars, edited
  badge — enough to distinguish an edition variant from a false pair.
- Per card: **"Keep this one"** behind the standard two-click confirm;
  merging keeps that card's item and merges the *other* item into it.
  In a 3+ group the action merges the top-most other item; the group
  re-renders after refresh and the user repeats.
- **"Not duplicates"** appears on 2-item groups only and dismisses that
  pair permanently. A 3+ group (none exist today) offers merges only;
  once merges/re-scans reduce it to a pair, dismissal becomes available.
  (The API supports dismissing any pair; only the UI is restricted.)
- **Manual pair picker** at the top of the panel, for duplicates the
  detector cannot see (e.g. subtitle variants like "Watchers of the
  Throne: The Regent's Legion" vs "The Regent's Legion"): two
  autocomplete inputs reusing the v1.5 `Autocomplete` component,
  searching catalog items by name. With both chosen, the pair renders
  as a normal side-by-side group with the same "Keep this one" confirm
  — one rendering path, no separate merge flow. No dismissal on manual
  pairs (nothing to suppress); cross-type picks are rejected by the
  `/api/merge` type guard and surfaced as an error message.
- After any action the panel re-fetches `/api/duplicates`.

## 6. Testing

- `dedupe_key`: case/punctuation/whitespace variants match; edition
  variants ("2e", "2nd Edition", ", 2nd ed.") match; "Learn C#"
  != "Learn C"; "C++" != "C".
- `merge_items`: bundle union incl. both-in-same-bundle conflict;
  download re-pointing; gap-fill never overwrites non-empty survivor
  fields (incl. tag arrays); tombstone written; dropped enrichment and
  item rows gone; missing ids -> False, nothing changed.
- Store: upserting a parsed item whose machine_name is tombstoned links
  the bundle to the kept item and does not recreate the row.
- Webapp: `/api/duplicates` groups exact and cosmetic variants, honors
  dismissals; `/api/merge` and `/api/dismiss_pair` contracts incl. 400s
  (missing ids, same id twice, cross-type merge rejected).
- Manual: browser smoke test working through the real ~15 pairs.
