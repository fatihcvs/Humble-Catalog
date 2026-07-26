# Bulk tagging — design

Apply or remove a user tag across many items at once, instead of one row
at a time.

## The selection model

The set acted on is **whatever the filters are currently showing**.
There is no checkbox column.

The filter bar already composes type, genre, authors, narrator,
publisher, bundle, user tags and note text, and `visible()` already
computes the result. So the app can express "everything currently shown"
for free, and the natural workflow — narrow to *audiobooks by one
author*, tag the lot — needs no new selection concept.

The safety argument is that **the visible table is a preview of the
blast radius**: the rows on screen are exactly the rows that will
change, and the confirmation names the count. Checkboxes would let you
deselect a few within that set, but they would not tell you anything the
table does not already show.

### Why not checkboxes

Considered and rejected. Per-row selection needs a checkbox column, a
"select all", a checked-id `Set` held outside the DOM (the table rebuilds
via `innerHTML` on every render), and reconciliation when the filter
changes and checked rows leave the visible set — a footgun of its own.

A hybrid (filter-scoped adding, checkbox removal) was considered too. It
does not save anything: once removal needs per-row selection the whole
checkbox apparatus exists anyway, and restricting adding to filter-scope
then looks arbitrary.

## Asymmetry between adding and removing

Adding is recoverable, removing is not.

`user_tags` sits outside `pre_edit` by design, so there is no snapshot
and no revert. A mistaken bulk *add* of a newly coined tag can be undone
with the existing catalog-wide `POST /api/user-tags/delete`, which
removes it everywhere. That escape hatch over-removes only if the tag was
already in use elsewhere. A mistaken bulk *remove* is unrecoverable.

So removal is gated: the button is disabled unless the view is actually
narrowed (`visible().length < items.length`). "Remove from all 2503" is
never one click away. Adding is ungated.

This residual risk is accepted knowingly. The proper fix is a
single-level undo, deferred to `BACKLOG.md`.

## UI

A bulk bar under the filter bar:

```
Bulk: [tag input]  [Add to N shown]  [Remove from N shown]
```

- The input autocompletes over the user-tag vocabulary, using the same
  client-side pool the filter uses — no server work.
- Both buttons go through `armOrFire`, the existing arm-then-confirm
  idiom, with the confirmation naming operation, tag and count.
- `N` tracks the live filtered count.
- Both buttons are disabled when the tag input is empty or `N` is 0;
  Remove is additionally disabled when nothing is filtered.

## API

```
POST /api/user-tags/bulk
  {"ids": [1, 2, 3], "tag": "to reread", "action": "add" | "remove"}
→ {"changed": n}
```

Ids are sent explicitly rather than having the server re-derive the
filter. The client knows exactly which rows it displayed; re-computing
server-side could act on a different set than the one that was confirmed.

Validation: `ids` must be a non-empty list of integers, `tag` non-blank,
`action` one of the two verbs. Unknown ids are ignored rather than
erroring, since the catalog can change under a stale page.

## Semantics

**Add** appends the tag where absent, snapping to an existing spelling
via `normalize_tags(conn, USER_TAGS, ...)` so bulk-adding "To Reread"
does not fork a vocabulary that already has "to reread". Items already
carrying the tag are left alone and are not counted as changed.

**Remove** matches case-insensitively and drops the tag. An array that
empties stores as `NULL`, matching `delete_tag`.

Neither touches `pre_edit`. Bulk tagging never marks a row edited and
never locks it for enrichment — the same guarantee the single-item
endpoint provides.

`changed` counts rows actually modified, so the result can distinguish
"added to 12 items" from "35 already had it".

## One deliberate non-generalization

`bulk_user_tag` takes no `TagColumn`, unlike its neighbours in `db.py`.

Bulk-tagging `genre` would have to snapshot `pre_edit` and mark rows
edited, because genre is an enrichment field and editing it by hand is a
hand edit. That is materially different behaviour, and a generic
signature would invite exactly that wrong use. The narrow signature makes
it impossible; a comment records why.

## Testing

Database level:
- add appends and snaps to an existing spelling,
- add skips items that already carry the tag, and does not count them,
- remove matches case-insensitively,
- removing the last tag stores `NULL`,
- `pre_edit` stays `NULL` and `edited` stays false throughout,
- unknown ids are ignored,
- `changed` is the number of rows actually modified.

API level: both verbs end to end, plus validation of `ids`, `tag` and
`action`.

JavaScript level, via the node harness: the gating rule — Remove is
unavailable when nothing is filtered, available when the view is
narrowed.

Invented data from `docs/TEST-DATA.md`; `scripts/leak_check.py` before
committing.

## Out of scope

- **Undo.** The right fix for the residual removal risk. Recorded in
  `BACKLOG.md`.
- **Bulk editing any other field.** Genre and the person fields are
  enrichment data with snapshot semantics; comments are per-item prose
  that nothing would sensibly bulk-set.
- **Selecting across pages or saved selections.** The filter is the
  selection.
