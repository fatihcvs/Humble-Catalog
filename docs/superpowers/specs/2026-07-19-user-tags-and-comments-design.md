# User tags and comments — design

Add two user-owned fields to the catalog: a free-form tag column
(`user_tags`) that behaves like `genre`, and a free-text note field
(`user_comment`). Both are filled only by the user. Neither marks the
row as hand-edited, so neither blocks re-enrichment.

Landing this in two commits: a behavior-preserving extraction of the
genre tag machinery, then the feature built on the extracted code.

## Motivation

`genre` already has a full vocabulary implementation: case-snapping on
write, catalog-wide rename/merge, catalog-wide delete, and
autocomplete with counts. User tags want all of it. Rather than write
a parallel copy, generalize the existing code over a descriptor naming
which column it operates on.

## Why these columns live on `items`

The schema already separates two classes of field:

- **`enrichment`** — machine-derived, guarded by `pre_edit`. Editing
  any `EDITABLE_FIELDS` column snapshots the row and sets the `edited`
  flag, and enrichment then leaves the row alone.
- **`items`** — user-owned. `my_rating` and `type_overridden` live
  here, and `enrich --reset` deliberately preserves them.

"Never locks the row for enrichment" is not a new flag; it is what the
second class already provides. So `user_tags` and `user_comment` go on
`items`, next to `my_rating`, and stay out of `EDITABLE_FIELDS`,
`TAG_FIELDS`, and `pre_edit`.

Consequences, all intended:

- enrichment never reads or writes them,
- `enrich --reset` preserves them,
- the revert button ignores them,
- the `edited` flag stays false when only these change.

## Commit 1 — extract the tag-column machinery

Pure refactor. No schema change, no behavior change.

### The descriptor

```python
# A tag column with a managed vocabulary: case-snapping on write, plus
# catalog-wide rename and delete.
#
#   snapshot — column is copied into enrichment.pre_edit, so rewrites
#              must touch the snapshot too
#   titleize — unknown tags are title-cased rather than stored verbatim
#
# Person-name fields (authors, narrator, illustrator) are deliberately
# absent and must never be added: titleizing or snapping names would
# mangle spellings like "van der Berg" or "k.d. lang".
TagColumn = namedtuple("TagColumn", "table column snapshot titleize")

GENRE = TagColumn("enrichment", "genre", snapshot=True, titleize=True)
```

### Function changes

| Before | After |
|---|---|
| `_genre_vocab(conn)` | `tag_vocab(conn, col)` |
| `normalize_genre_tags(conn, tags)` | `normalize_tags(conn, col, tags)` |
| `_rewrite_genre_tags(conn, fn)` | `_rewrite_tags(conn, col, fn)` |
| `rename_genre_tag(conn, old, new)` | `rename_tag(conn, col, old, new)` |
| `delete_genre_tag(conn, tag)` | `delete_tag(conn, col, tag)` |

Two behaviors become conditional on the descriptor:

- `_rewrite_tags` runs its `pre_edit` rewriting block only when
  `col.snapshot`. For a non-snapshot column the block is not merely
  skipped — it does not apply, since the column never appears in a
  snapshot.
- `normalize_tags` falls back to `titleize(t)` for an unknown tag only
  when `col.titleize`; otherwise the tag is stored as typed. Snapping
  to an existing spelling happens either way.

### Call sites

Five, all updated directly; no wrapper aliases are kept.

- `enrich.py:33`
- `import_sheets.py:137`
- `webapp/__init__.py:166` (the `/edit` endpoint)
- `webapp/__init__.py:193` (`/api/genres/rename`)
- `webapp/__init__.py:204` (`/api/genres/delete`)

### Acceptance

The existing `test_db.py` tag tests pass with **call-site edits only**.
If any assertion has to change, the refactor has altered behavior and
is wrong.

## Commit 2 — user tags and comments

### Schema

```sql
ALTER TABLE items ADD COLUMN user_tags TEXT;     -- JSON array, or NULL
ALTER TABLE items ADD COLUMN user_comment TEXT;  -- free text, or NULL
```

Added through the additive `PRAGMA table_info` path already used for
`source_url` and `pre_edit`. No `user_version` bump: there is no
existing data to convert, so the migration is idempotent by
construction.

```python
USER_TAGS = TagColumn("items", "user_tags", snapshot=False, titleize=False)
```

### Normalization

User tags snap to an existing spelling when one matches
case-insensitively, and are otherwise stored exactly as typed. Typing
`to reread` stores `to reread`; typing `To Reread` afterwards snaps
back to `to reread`. This keeps near-duplicate tags from accumulating
without imposing title case on a personal vocabulary.

`user_comment` is stored verbatim apart from stripping surrounding
whitespace. Empty stores as NULL.

### Reads

`fetch_items` selects `i.*`, so both columns arrive automatically.
`user_tags` needs decoding: the loop that walks `TAG_FIELDS` currently
covers enrichment columns only, so it gains `user_tags` explicitly.
This is the one place the two tables' tag columns meet.

Export gains `user_tags` (joined with `; `, matching the other tag
columns) and `user_comment`.

### API

Two new write endpoints, following the `/rating` and `/type` pattern
rather than the `/edit` pattern — this is what keeps them clear of
`apply_hand_edit` and therefore clear of the lock:

- `POST /api/items/<id>/user-tags` — body `{"tags": [...]}`
- `POST /api/items/<id>/comment` — body `{"comment": "..."}`

Two vocabulary-management endpoints mirroring the genre ones:

- `POST /api/user-tags/rename` — body `{"old": ..., "new": ...}`
- `POST /api/user-tags/delete` — body `{"tag": ...}`

Both return `{"changed": n}`, or 404 when the tag is unknown.

### Viewer

`user_tags` gets a tag editor and autocomplete matching `genre`.
Autocomplete needs no server work: suggestions and counts are computed
client-side in `autocomplete.js` from the `/api/items` payload, so the
field appearing in that payload is sufficient.

`user_comment` gets a multi-line text field. It is not searchable or
filterable in this version (see Out of scope).

### Merge behavior

`merge_items` currently fills a survivor's column from the dropped row
only when the survivor's value is empty. That rule is wrong for
`user_tags`: hand-typed tags on the dropped row would be discarded
silently and unrecoverably, since a merge is irreversible.

- `user_tags` — **union** the two arrays, survivor's order first,
  de-duplicated case-insensitively.
- `user_comment` — fill-if-empty, matching `my_rating` and `publisher`.

## Testing

New tests in `test_db.py` and `test_webapp.py` covering:

- both columns survive `enrich --reset` and re-enrichment,
- writing either leaves `edited` false and `pre_edit` NULL,
- revert does not restore either column,
- user tags snap to existing spelling but are not titleized,
- genre tags are still titleized (the descriptor flags do diverge),
- rename and delete work on user tags and skip `pre_edit` rewriting,
- rename and delete on genre still rewrite `pre_edit`,
- merge unions `user_tags` and fills `user_comment` only when empty.

Per `CLAUDE.md`, tests use invented data from `docs/TEST-DATA.md`
(e.g. tagging *Axebearer (Grim & Fell)* or *The Quiet Harbor: A
Novel*). Any new invented tag names are added to that file, and
`scripts/leak_check.py` runs before either commit.

## Out of scope

This version makes user tags and comments writable and visible, not
yet useful for finding things. Filtering and search are a deliberate
follow-up, tracked in `BACKLOG.md` under "User tags and comments":

- **Filter by user tags** — genre and user tags will filter as two
  independent pools, never one combined pool. The `chipFilters`
  registry in `app.js` already works this way (fields AND together,
  each with its own chips and all/any mode), so the work is one
  registry entry plus one input in `index.html`. Deferred because it
  is a separable slice of work, not because anything is unresolved.
- **Search comment text** — `#search` will not cover `user_comment`,
  and is better changed alongside fuzzy matching.
- **Bulk tagging** across a selection of items.

Also out of scope, and not planned:

- Markdown or any rich formatting in `user_comment`.
- Vocabularies for the person-name fields, which must not have them.
