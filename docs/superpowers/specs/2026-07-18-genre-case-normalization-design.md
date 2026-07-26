# Genre tag case normalization (v1.9)

Approved 2026-07-18.

## Problem

The same genre exists in several case variants (e.g. `fiction` vs
`Fiction`, `Science fiction` vs `science fiction`), splitting filter
results and the autocomplete vocabulary. Multi-tag filtering made the
duplicates visible.

## Goal

One spelling per genre tag, enforced at every write path and applied
once to existing data by migration.

## Rule: canonical merge

For each incoming genre tag:

1. If the current vocabulary (all tags across `enrichment.genre`)
   contains a case-insensitive match, snap to that existing spelling.
2. Otherwise the tag is new: apply `titleize` — uppercase the first
   letter of each space-separated word, leave the remaining letters
   untouched. `science fiction` → `Science Fiction`; `RPG` stays
   `RPG`. Hyphenated words raise only their first letter
   (`post-apocalyptic` → `Post-apocalyptic`) — accepted
   simplification.
3. Case-insensitively dedupe the resulting list, order preserved.

Consequence, accepted: two deliberate case variants of one tag cannot
coexist; saving `fantasy` silently becomes the existing `Fantasy`.

## Scope

**In:** genre only. A shared helper so the planned custom user-tags
column can adopt the same rule later.

**Out:** authors, narrator, illustrator (person names — title-casing
them is destructive), series, publisher, bundle names (facts from
Humble orders).

## Design

### Normalizer (`db.py`)

- `titleize(tag: str) -> str` — the rule above, pure function.
- `normalize_genre_tags(conn, tags: list[str]) -> list[str]` — builds
  the case-insensitive vocabulary map from `enrichment.genre`, snaps
  or titleizes each tag, dedupes case-insensitively preserving order.
  Called per write, so a tag written earlier in the same run is
  already in the vocabulary for later rows.

### Write paths

- `/api/items/<id>/edit` (webapp): normalize the `genre` array after
  the existing list validation/cleaning, before storing.
- `apply_candidate` (enrich): normalize the one-element genre wrap.
  URL import applies through `apply_candidate`, so it is covered.
- Spreadsheet import (`import_sheets`): normalize the genre values it
  writes.

### Migration (`db._migrate`)

`PRAGMA user_version` bump, same mechanism as the multi-value tags
migration:

- Collect every genre tag from `enrichment.genre` and from the
  `genre` field inside `pre_edit` snapshots; group case-insensitively.
- Canonical spelling per group: most frequent variant; ties prefer
  the variant equal to its own `titleize` form, then the
  alphabetically first. The winner is then itself `titleize`d, so a
  group whose only variant is all-lowercase comes out capitalized
  instead of pulling future correctly-cased input down to lowercase
  via the snap rule (harmless for acronyms — `titleize` leaves
  non-first letters alone).
- Rewrite both `enrichment.genre` and `pre_edit` genre arrays to
  canonical spellings, deduping within each array (order preserved).

No client-side changes: the viewer re-fetches after save, and the
autocomplete vocabulary is derived from the (now clean) item data.

## Testing

pytest, invented tags only (`docs/TEST-DATA.md`; leak check before
commits):

- `titleize`: multi-word, acronym, hyphenated.
- `normalize_genre_tags`: snap to existing spelling, titleize new,
  in-list case-insensitive dedupe.
- Migration: variants collapse to the most frequent spelling; tie
  prefers titleized; `pre_edit` innards rewritten; runs once.
- `/edit`: posted genre array comes back normalized.
- `apply_candidate`: source genre string snaps to existing vocabulary.
