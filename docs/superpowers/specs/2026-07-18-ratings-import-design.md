# Spreadsheet ratings & metadata import (v1.6)

Approved 2026-07-18. Closes the last "future extensions" item from
`2026-07-17-humblebundle-catalog-design.md`.

## Goal

Import the hand-entered data from the two reference spreadsheets
(`Reference spreadsheets/Audiobooks (loose collection).xlsx` and
`Reference spreadsheets/E-books (loose collection).xlsx`) into the
catalog: ratings into `items.my_rating`, and metadata (genre, authors,
narrator, series, series number) into empty enrichment fields, stored as
hand-edits. Never overwrite existing data; never guess a match.

## Facts about the source data (verified 2026-07-18)

- Audiobooks workbook: sheets `Fiction` (62 rows), `Grimdark` (38),
  `Non-Fiction` (2). E-books workbook: `Fiction` (47),
  `Programming books` (46), `Ark3` (empty).
- Header rows use trailing colons (`Name:`), with variations:
  `Narator:` (typo), `Humble:` (means bundle), `Setting:` (Grimdark
  sheet's genre-equivalent), `Number in the series:`.
- `Rating:` uses 0 for "unrated". Only 6 rows carry a real rating
  (four 4s, two 5s), all in Audiobooks `Fiction`.

## Scope

**In:** `import-sheets` CLI command; sheet parsing with header aliasing;
strict normalized-title matching scoped by item type; gap-fill import of
rating + five metadata fields via hand-edit semantics; stdout report with
fuzzy suggestions for unmatched rows; shared `db.apply_hand_edit` helper;
README documentation of `import-sheets`, `export`, and `check`; tests.

**Out:** modifying the spreadsheets; importing `Publisher:` or `Bundle:`
columns (both authoritative from Humble orders); fuzzy *auto*-matching;
any UI; XLSX export; overwriting non-empty catalog fields.

## 1. Command & shape

- New module `humble_catalog/import_sheets.py`;
  `python -m humble_catalog import-sheets [files...]` in `__main__`
  dispatch. No file arguments → the two default workbooks under
  `Reference spreadsheets/`.
- `openpyxl` added to `pyproject.toml` dependencies.
- Workbooks are opened read-only (`load_workbook(..., data_only=True,
  read_only=True)`) and never written.

## 2. Sheet parsing

- Row 1 of every sheet is the header row (true of all five real
  sheets). Empty sheets (e.g. `Ark3`) and sheets whose row 1 has no
  recognizable `title` header are skipped, and named in the report so
  a renamed column cannot silently drop a sheet.
- Header normalization: strip trailing `:`, trim, lowercase, then map
  through aliases: `narator` → `narrator`, `humble` → `bundle`,
  `setting` → `genre`, `author` → `authors`,
  `number in the series` → `series_number`, `name` → `title`.
  Unrecognized headers are ignored.
- Rows with an empty title cell are skipped. Cell values are trimmed;
  empty strings count as missing.
- Type scope comes from the workbook: a filename containing
  `audiobook` (case-insensitive) scopes rows to catalog type
  `audiobook`; otherwise to types `ebook` and `comic`.

## 3. Matching

- Title normalization for both spreadsheet titles and catalog names:
  lowercase, punctuation stripped, whitespace collapsed. Numeric titles
  (the sheet stores `1632` as a float) are formatted without a trailing
  `.0` before normalizing.
- A lookup index maps normalized catalog name → list of item ids,
  restricted to the row's type scope.
- Exactly one hit → the row imports. Zero hits → reported as unmatched,
  with the closest catalog title in scope (via
  `difflib.get_close_matches`, best single suggestion, display-only).
  Two or more hits → reported as ambiguous, nothing written.

## 4. Import semantics (gap-fill, idempotent)

- **Rating:** spreadsheet rating > 0 sets `items.my_rating = int(value)`
  only where `my_rating IS NULL`. 0, blank, or non-numeric → skipped.
  Ratings do not create a `pre_edit` snapshot (`my_rating` sits on
  `items`, outside the edit machinery, same as the star UI).
- **Metadata fields** `genre`, `authors`, `narrator` (tag fields) and
  `series`, `series_number` (scalars): a spreadsheet value is written
  only when the catalog field is empty (NULL, or empty tag array).
  Tag fields receive the spreadsheet cell as a single tag — no
  splitting, per the v1.5 rule. `series_number` stores as float.
- Metadata writes use hand-edit semantics: on the first write to an
  item, the enriched state snapshots into `pre_edit` (existing rule:
  later edits leave the snapshot alone), so the row shows the "edited"
  badge and revert works. The snapshot is taken only if at least one
  field is actually written.
- Consequence: a second run finds every gap filled and writes nothing —
  the command is idempotent. It also never disturbs rows the user
  already edited by hand.
- Refactor: the snapshot-then-update logic in the webapp `/edit`
  endpoint moves to `db.apply_hand_edit(conn, item_id, fields)`
  (fields already column-ready, i.e. tag JSON prepared by the caller);
  both the endpoint and the importer call it. Endpoint request
  validation stays in the webapp.

## 5. Report

Printed to stdout at the end of the run:

- Summary counts: rows read, rows matched, ratings set, fields filled,
  rows skipped because everything was already filled.
- `Unmatched:` list — workbook/sheet, row title, `closest: <name>`
  suggestion when one exists.
- `Ambiguous:` list — workbook/sheet, row title, the matching catalog
  names.
- Exit code 0 even with unmatched rows (they are expected work-to-do,
  not errors).

## 6. README

The Usage section gains entries for `import-sheets` plus the previously
undocumented `export` and `check` commands.

## 7. Testing

Pytest builds small synthetic `.xlsx` workbooks with openpyxl in
`tmp_path`. Covered:

- Header aliasing (`Narator:`, `Humble:`, `Setting:` → genre).
- Title normalization, numeric-title handling, and type scoping
  (an audiobook row never matches an ebook item of the same name).
- Gap-fill never overwrites a non-empty field; rating only when NULL.
- `pre_edit` snapshot created once, and only when a field is written.
- Second run is a no-op (no snapshot, no changes).
- Unmatched report includes the fuzzy suggestion; ambiguous rows
  (same normalized name twice in scope) are reported, not written.
- `db.apply_hand_edit` behaves identically for webapp edits
  (existing endpoint tests keep passing after the refactor).
