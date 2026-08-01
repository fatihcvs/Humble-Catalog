# Undo for bulk tagging — design

Recover from a bulk tag operation that did the wrong thing, without
reaching for the catalog-wide delete that over-removes.

Covers the two bulk operations: add and remove. Not the catalog-wide
user-tag delete, and not rename — see **Out of scope**.

## Why this is prospective, not measured

The catalog currently holds **zero** user tags: no row carries one at
all. So the risk being retired has never been realised, and two
questions that would normally be settled by measurement — do
case-variant spellings coexist, and is array order meaningful? — have no
data behind them. Both are decided by reasoning below and pinned by
tests rather than by counts. Said plainly here so a later reader does
not mistake the reasoning for evidence.

What is not prospective is the gap itself, and it is wider than the
bulk tagging spec recorded. `user_tags` sits outside `pre_edit` by
design, so a bulk *remove* has no revert. That spec then offered the
catalog-wide `POST /api/user-tags/delete` as the escape hatch for a bad
bulk *add*, noting it over-removes when the tag was already in use
elsewhere — but **that route has no caller**: not in the viewer, not in
the CLI. The rename/delete UI in the statistics panel is genre-only.
So the escape hatch is reachable by hand with `curl` and by nothing
else, and a mis-aimed bulk add currently has no in-app remedy at all.

## The slot

One module-level variable in `catalog.js`:

```js
let lastTagOp = null;  // {ids, tag, action}
```

Three fields and no stored label: the button's text is derived from
`tag` and `ids.length` at render time, so it cannot disagree with the
operation it will perform.

Set by a bulk add or a bulk remove, but **only when the operation
changed at least one row**. Cleared when the undo fires. Replaced by the
next qualifying operation.

Browser memory, deliberately, and not a table in `catalog.db`. This
undo exists to correct a mistake while its result is still on screen.
A persisted one answers a different question — "undo something from last
Tuesday" — and answers it badly: the catalog moves underneath a stored
operation, and the stored row cannot tell a benign re-application from a
disagreement with edits made since. It would also drag in a `reset`
decision, undo state being derived but not rebuildable, which is the
awkward category `hidden_keys` had to argue its way out of. An undo
that visibly disappears on reload never promises durability it cannot
keep.

**Single level, and no redo.** Undoing an undo is just the original
operation, one click away in the same bar.

`action` holds the *inverse* verb, stored ready to fire, so the undo
path has no branching left to get wrong. The undo is the same call the
operation was:

```
POST /api/user-tags/bulk  {ids: <rows that actually changed>, tag, action: <inverse>}
```

### Staleness needs no mechanism

Unusually, the slot needs no expiry, no invalidation on other mutations,
and no version check. Both inverse operations are per-item idempotent —
`bulk_user_tag` skips rows already in the wanted state and does not count
them — and the bulk route already ignores unknown ids, since the catalog
can change under a page that has been open a while. So an undo fired
after unrelated edits, or after a merge removed some of its rows, does
the right thing quietly rather than clobbering.

## Server: return what changed, not how much

`bulk_user_tag` already computes the changed set and discards it,
returning only its size.

Undoing by re-sending the *original* ids with the inverse verb would be
wrong, which is the whole reason the server has to answer with ids: bulk
add to 47 rows where 12 already carried the tag, then "undo" by removing
from all 47, and the tag is stripped from 12 items that had it
beforehand. The recoverable set is the changed set.

So `bulk_user_tag` returns the list of changed ids instead of a count.
Callers wanting a count take `len()`.

`delete_tag`, `rename_tag` and `_rewrite_tags` are **not touched**. An
earlier draft of this spec changed `delete_tag` to return ids and the
stored spelling so a catalog-wide delete could be undone too; that was
dropped once the route turned out to have no caller. Changing a function
shared with `GENRE` — and its live genre route and tests — to serve a
path no user can take is speculative work, and the spelling subtlety it
was solving (`delete_tag` lowercases its argument, and after the delete
`normalize_tags` has nothing left to snap to) is recorded here rather
than built.

### Route

```
POST /api/user-tags/bulk  → {"ids": [1, 2, 3]}
```

`changed` is dropped rather than left beside `ids` as a second
derivation of one fact; the client says `ids.length`. Same reasoning as
the unsold-overlaps fix — a count re-derived beside the set it came from
is where the two quietly stop agreeing.

Validation is unchanged.

## Client

`renderBulkBar` gains a third control, after the note:

```
Bulk: [tag input] [Add to N shown] [Remove from N shown]  [Undo: restore "lent out" to 47 items]
```

Hidden when the slot is empty.

**The label names the tag and the count, not just "Undo".** The two
operations are opposites, so a bare "Undo" beside them says nothing
about which direction the click goes — and the count is the same
blast-radius readout the Add and Remove labels already carry.

**The bulk bar.** Both operations are fired from it and it is outside
the table's `innerHTML` rebuild — there is already a comment saying so
at the listener that refreshes it — so the affordance cannot be
destroyed by a re-render or hidden by a collapse.

**No `armOrFire`.** The other two buttons arm-then-confirm because they
are the destructive direction; undo is by construction the recovering
one, and demanding two clicks to recover from a mistake is friction
pointing the wrong way. It is likewise not subject to the `filtered`
gate on Remove: that gate exists so "remove from all 2503" is never one
click, whereas undo acts on a recorded id list rather than on the
current view. So undo is available precisely when Remove is not.

After firing: `await load()`, clear the slot, and report into
`#bulk-note` — `Restored "lent out" to 47 items.`

## Boundaries

- **Restores membership, not position.** A restored tag appends to the
  end of its array, and `tagBadges` renders array order, so a tag that
  sat first may come back last. An order-preserving record is not worth
  it for a personal vocabulary with no ordering semantics.
- **Collapses case variants.** Bulk remove matches case-insensitively
  and drops every spelling of the tag; undoing it restores one, the
  spelling the operation was issued with. Reasoned, not measured —
  there is no data to measure.
- **`pre_edit` and `hand_edited` stay untouched throughout**, undo
  included. Pinned by a test, because the point of `user_tags` living
  outside them is that tagging never marks a row edited or locks it for
  enrichment, and a new write path is exactly where that could leak in.

## Testing

Database level:

- `bulk_user_tag` returns the ids it changed, not the ids it was given —
  rows already in the wanted state are absent from the list.
- `bulk_user_tag` returns an empty list, not `None`, when nothing
  changes.
- `pre_edit` stays `NULL` and `hand_edited` stays false across a bulk
  add, a bulk remove, and an undo of each.

API level:

- the route's new response shape;
- a round trip — bulk remove, then the inverse bulk add over the
  returned ids, restores exactly the rows that changed and leaves rows
  that never carried the tag alone;
- the add-side asymmetry: bulk add where some rows already carried the
  tag, then undo, leaves those rows still carrying it.

JavaScript level, via the node harness:

- the slot is set only when the operation changed at least one row;
- it is cleared after the undo fires;
- a later operation replaces it;
- the label names the tag and the count;
- undo is available while the Remove button is gated off by `filtered`.

Invented tags (`lent out`, `to reread`) added to `docs/TEST-DATA.md`.
`scripts/leak_check.py` before committing — it matches substrings, so a
new invented tag is vetted against `build_terms()` like any other.

## Out of scope

- **The catalog-wide user-tag delete.** `POST /api/user-tags/delete` has
  no caller in the viewer or the CLI, so an undo for it would be
  unreachable: nothing in the browser could set the slot. Undoing it
  properly means first giving user tags the rename/delete UI that genre
  has — a separate feature, and one that would put a destructive
  catalog-wide button in front of the owner where none exists today.
  Worth its own backlog entry rather than being smuggled in here.
- **Rename.** Its inverse needs a per-item record of which rows held the
  old spelling and which already held the new one — the merge is
  genuinely lossy, and a changed-id list cannot reconstruct it. A
  different feature wearing the same word.
- **A redo.** See above: the original operation is one click away.
- **Persisting the slot**, in any form. The argument is in **The slot**.
- **Undo for anything outside the user-tag vocabulary.** Genre is
  enrichment data with `pre_edit` behind it and already has Revert.
