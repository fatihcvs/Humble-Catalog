# Android APK Items — Design (v1.4)

Date: 2026-07-18
Status: Approved

## Purpose

Humble bundles also deliver Android games/apps as APK downloads. Today
`parse_order` drops any subproduct whose downloads lack the `ebook` or
`audio` platform, so APKs never reach the catalog. This feature makes
them first-class, searchable catalog items of a new type `android`.

Out of scope (explicitly decided):
- Desktop game downloads (windows/mac/linux) and Steam/GOG keys stay out
  of the items table (keys remain in `external_keys` as today).
- No game-metadata enrichment source (Google Play/IGDB). Humble's own
  data — name, publisher, cover, bundle, formats — is all we store.
- A standalone Android *viewer app* for the catalog is a separately
  recorded gap (see `docs/BACKLOG.md`), not part of this work.

## Section 1 — Parsing & classification

- `parse_order` platform gate widens from `{ebook, audio}` to
  `{ebook, audio, android}`.
- `classify` gains an Android rule checked **first**: if the item has
  any `android`-platform download, return `"android"`.
  - Before the audio branch: a game shipping an APK plus soundtrack is
    a game, not music.
  - Before comic/ebook checks: a game bundled with a PDF manual is a
    game, not an ebook.
- No signature changes; `classify` already receives `platforms`.
- APK format names from `download_struct` are stored as-is.

## Section 2 — Storage, enrichment skip, backfill

- No schema change. `items.type` is free text; downstream queries are
  type-agnostic.
- `enrich` extends its music guard to `("music", "android")`, marking
  APK items `skipped` so book/comic sources never query for them.
- Backfill: `extract` first re-runs `store_order` over every order in
  `raw_orders` (local JSON re-parse, no network, idempotent) before
  fetching new bundles. Existing bundles gain their APK items on the
  next `extract`, and future parser improvements auto-apply to old data.
- Known quirk, accepted: the type-precedence rule in `store.py` only
  protects `comic` from demotion, so an item parsed as `android` from
  one bundle and `ebook` from another takes the last-stored type. Real
  overlaps are rare; `type_overridden` hand-fixes always win.

## Section 3 — Viewer, export, testing

- Viewer type dropdown gets `<option value="android">Android apps</option>`.
- Search, bundle filter, covers, CSV export need no changes — all flow
  through the shared `db.fetch_items`.
- Detail rows show empty enrichment fields, exactly as music does; no
  special casing.
- Tests (pytest, existing conventions):
  - classify: APK+soundtrack → android; APK+manual → android; plain
    audiobook still audiobook; music/comic rules unchanged.
  - parse_order: android-only subproduct is kept with its formats.
  - enrich: android items get status `skipped` without source queries.
  - extract backfill: re-parsing stored raw_orders is idempotent and
    adds previously-dropped APK items.
