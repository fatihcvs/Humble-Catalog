# Multi-value tags for the catalog viewer (v1.5)

Approved 2026-07-18.

## Goal

Genre, authors, and narrator/artist hold multiple values per item, shown as
badges and edited as chips with autocomplete. The genre and bundle filters
become autocomplete inputs that match items *containing* a tag, not items
whose whole string equals the dropdown entry.

## Scope

**In:** JSON-array storage for the four multi-value enrichment fields;
one-time migration; badge display; chip editor with add/remove and
autocomplete; free-form tag creation; autocomplete filter inputs for genre
and bundle; contains-tag filter semantics; CSV join with `"; "`; tests.

**Out (later rounds):** multi-tag filtering (several tags at once),
tag management (rename/merge across items), tag counts in dropdowns,
autocomplete filters for authors/series, an enrichment-override toggle
for edited rows.

## Decisions already settled

- Bundles stay display-only links (badge-styled); they are facts from
  Humble orders, never edited.
- Series and publisher stay single-valued.
- Autocomplete vocabulary is derived from the tags currently on items,
  client-side. A tag removed from its last item vanishes from the
  vocabulary; no registry, no provenance tracking, no purge job. This
  applies equally to enrichment-created tags (re-enrichment can
  reintroduce them).
- Enrichment already never touches hand-edited rows (it only processes
  status `pending`/`unmatched`); no change needed or wanted there.
- A source genre like "Science Fiction / Fantasy" stays one tag; we do
  not guess at splitting source data.

## 1. Data model & migration

`genre`, `authors`, `narrator`, `illustrator` in `enrichment` keep their
TEXT columns but hold either NULL or a JSON array of non-empty strings,
e.g. `["Fantasy","Horror"]`. No schema change.

One-time migration in `db._migrate`, gated by `PRAGMA user_version`:

- Each non-NULL value of the four columns that is not already a JSON
  array is split on `", "`, entries trimmed, empties dropped, stored as
  a JSON array.
- The same conversion is applied to the four fields inside every
  `pre_edit` snapshot, so a later revert restores array-format values.
- `candidates` JSON is untouched (candidate `authors` are already lists).
- Known limitation, accepted: the one-time split mangles names that
  legitimately contain `", "` (e.g. "Martin Luther King, Jr."); such rows
  are rare and fixable in the chip editor. New data is never ambiguous
  because storage is structurally a list.

## 2. Pipeline writes

`apply_candidate` stores `authors` as `json.dumps(cand["authors"])`
(sources already return lists); `genre`, `narrator`, `illustrator` are
single strings from sources and are wrapped as one-element arrays.

## 3. API

- `db.fetch_items` json-loads the four fields; `/api/items` serves arrays.
- `/api/items/<id>/edit` accepts JSON arrays for the four fields:
  entries coerced to str, trimmed, empties dropped, exact duplicates
  removed (order preserved); empty array stores NULL. Non-list values for
  these fields are rejected with 400. `series`/`series_number` unchanged.
- No new endpoints; vocabulary is computed client-side from loaded items.

## 4. Read-mode display

- Genre, authors, narrator/artist cells render one badge per value.
- Bundle links keep current behavior, restyled as badges.
- Column sort compares the `", "`-joined array text (sorts by first
  entry, as today).
- The free-text search haystack flattens all tag arrays in.

## 5. Edit mode: chip editor

- Each multi-value cell becomes a chip input: existing tags as chips
  with an × to remove, plus a text box to add.
- Typing filters a dropdown of that column's vocabulary
  (case-insensitive substring). Enter/click adds the highlighted
  suggestion; Enter with nothing highlighted adds the typed text as a
  new free-form tag. Esc closes the dropdown.
- Changing a tag = remove + re-add.
- Narrator/illustrator keeps the existing `personField` logic: chips
  edit whichever of the two fields is active for the item.
- Save posts arrays; Cancel discards.

## 6. Filter bar

- Genre and Bundle selects become autocomplete inputs sharing the chip
  editor's dropdown component (vanilla JS, no library).
- Picking a suggestion filters by exact tag membership; free-typed text
  filters by case-insensitive substring across that column's tags.
  Clearing the input clears the filter.
- Type and flag filters stay plain selects.

## 7. CSV export

Arrays join with `"; "` — the convention `formats` and `bundles` already
use. Authors in the CSV change from `"A, B"` to `"A; B"`.

## 8. Testing

Extend existing suites: migration round-trip including `pre_edit`
innards (`test_db`), `apply_candidate` storing JSON (`test_enrich`),
`/edit` array validation and rejection of non-list garbage
(`test_webapp`), `"; "` join (`test_export`). The chip/autocomplete UI
is vanilla JS with no browser test harness; verify by hand in the
browser, as with the existing UI.
