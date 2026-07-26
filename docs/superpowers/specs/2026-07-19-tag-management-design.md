# Genre tag management — design

Date: 2026-07-19
Backlog item: **Tag management** — rename or merge a tag across all
items (deferred from multi-value tags,
`specs/2026-07-18-multi-value-tags-design.md`).

## Goal

Rename, merge, or delete a genre tag across the whole catalog from the
viewer, instead of editing every item that carries the tag.

Scope decisions (owner-approved):

- **Genre only.** The person-name tag fields (authors, narrator,
  illustrator) are out of scope; they rarely need merging and are
  riskier to mass-edit.
- **Operations: rename and delete.** Renaming a tag to an existing
  tag's name is the merge case — no separate merge operation.
- **UI: a dedicated collapsible "Genres" panel** in the viewer, like
  the Duplicates and Review sections.

## Semantics

A vocabulary operation is catalog-wide housekeeping, not a per-item
hand-edit:

- It does **not** go through `apply_hand_edit`, does not create or
  update `pre_edit` snapshots as an edit would, and does not change any
  item's edited status.
- It **rewrites the tag inside existing `pre_edit` snapshots** as well
  as the live `genre` arrays — the rule the genre-case migration
  established — so a later revert cannot resurrect the old spelling.
- Matching against the vocabulary is **case-insensitive** (the
  vocabulary is already case-collapsed, but defensive matching keeps a
  stray variant from escaping a rename).
- The new name is normalized like any other genre input: snapped to an
  existing vocabulary spelling if one matches case-insensitively
  (ignoring the tag being renamed), otherwise titleized.
- If the new name already exists in an item's array, the array is
  deduped (`tags_to_json` already does this) — that is the merge.
- Deleting the last tag from an item leaves `genre` as NULL, the
  existing empty-array representation.
- Operations are irreversible (like item merges); the UI confirms
  before delete and before a rename that merges into an existing tag.

## Components

### DB layer (`humble_catalog/db.py`)

- `rename_genre_tag(conn, old, new)` → number of items changed, or
  `None` when `old` is not in the vocabulary or `new` is blank.
  Scans every `enrichment` row; rewrites `old` → normalized `new` in
  the `genre` array and in the `genre` copy inside `pre_edit`
  snapshots; dedupes; commits once.
- `delete_genre_tag(conn, tag)` → number of items changed, or `None`
  when the tag is not in the vocabulary. Same scan; removes the tag
  from `genre` arrays and `pre_edit` snapshots; commits once.

### Endpoints (`humble_catalog/webapp/__init__.py`)

- `POST /api/genres/rename` with `{"old": ..., "new": ...}` →
  `{"changed": n}`; 400 on missing/blank fields, 404 when `old` is
  unknown.
- `POST /api/genres/delete` with `{"tag": ...}` → `{"changed": n}`;
  400 on missing/blank tag, 404 when unknown.

### Viewer panel (`humble_catalog/webapp/static`)

A collapsible **Genres** section listing every genre tag with its item
count, computed client-side from the already-loaded items (no new
read endpoint). Per tag: an inline rename control and a delete button.
`confirm()` guards delete and merge-causing renames. After a
successful operation the viewer refetches items so the table, filter
dropdowns, and counts all update.

## Error handling

- Unknown tag → 404 from the endpoint; the panel shows the error and
  refetches (the vocabulary may have changed in another tab).
- Blank or missing input → 400; rename to the identical spelling is a
  no-op the UI can skip.
- DB functions commit only after the full scan succeeds, so a failure
  mid-scan leaves the catalog unchanged.

## Testing

- **DB unit tests:** plain rename; rename-as-merge with dedupe;
  case-insensitive match of `old`; new name titleized / snapped to
  existing casing; `pre_edit` snapshots rewritten (revert cannot
  resurrect the old tag); edited flags untouched; delete removes tag
  and empties to NULL; unknown tag returns `None`.
- **Endpoint tests:** success, 400, and 404 paths for both endpoints.
- All test data drawn from `docs/TEST-DATA.md` (invented titles;
  generic genre names like Fantasy / Science Fiction are allowed);
  run `scripts/leak_check.py` after adding tests.

## Out of scope

- Rename/merge for authors, narrator, illustrator tags.
- Undo for vocabulary operations.
- Tag counts in the autocomplete dropdowns (separate backlog item,
  though the panel's counts may share code later).
