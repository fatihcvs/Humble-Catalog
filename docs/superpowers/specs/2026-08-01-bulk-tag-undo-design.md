# Undo for bulk tagging — design

Recover from a bulk tag operation that did the wrong thing, without
reaching for the catalog-wide delete that over-removes.

Covers three operations: bulk add, bulk remove, and the catalog-wide
user-tag delete. Not rename — see **Out of scope**.

## Why this is prospective, not measured

The catalog currently holds **zero** user tags: no row carries one at
all. So the risk being retired has never been realised, and two
questions that would normally be settled by measurement — do
case-variant spellings coexist, and is array order meaningful? — have no
data behind them. Both are decided by reasoning below and pinned by
tests rather than by counts. Said plainly here so a later reader does
not mistake the reasoning for evidence.

What is not prospective is the gap itself. `user_tags` sits outside
`pre_edit` by design, so a bulk *remove* has no revert, and the bulk
tagging spec's own escape hatch for a bad bulk *add* — the catalog-wide
`POST /api/user-tags/delete` — removes the tag everywhere, including
from rows the bulk add never touched.

## The slot

One module-level variable in `catalog.js`:

```js
let lastTagOp = null;  // {ids, tag, action}
```

Three fields and no stored label: the button's text is derived from
`tag` and `ids.length` at render time, so it cannot disagree with the
operation it will perform.

Set by a bulk add, a bulk remove, or a catalog-wide delete, but **only
when the operation changed at least one row**. Cleared when the undo
fires. Replaced by the next qualifying operation.

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
path has no branching left to get wrong. All three operations reduce to
one call:

```
POST /api/user-tags/bulk  {ids: <rows that actually changed>, tag, action: <inverse>}
```

A catalog-wide delete's inverse is a bulk add over the ids it touched.
That is why delete was cheap to include and rename was not.

### Staleness needs no mechanism

Unusually, the slot needs no expiry, no invalidation on other mutations,
and no version check. Both inverse operations are per-item idempotent —
`bulk_user_tag` skips rows already in the wanted state and does not count
them — and the bulk route already ignores unknown ids, since the catalog
can change under a page that has been open a while. So an undo fired
after unrelated edits, or after a merge removed some of its rows, does
the right thing quietly rather than clobbering.

## Server: return what changed, not how much

Both operations already compute the changed set and discard it.

Undoing by re-sending the *original* ids with the inverse verb would be
wrong, which is the whole reason the server has to answer with ids: bulk
add to 47 rows where 12 already carried the tag, then "undo" by removing
from all 47, and the tag is stripped from 12 items that had it
beforehand. The recoverable set is the changed set.

- `bulk_user_tag` returns the list of changed ids instead of a count.
  Callers wanting a count take `len()`.
- `_rewrite_tags` returns the list of changed keys instead of a count.
  `rename_tag` returns `len()` of it and is otherwise untouched.
- `delete_tag` returns `(ids, spelling)`: the ids it changed, and **the
  stored spelling it removed**, read from `tag_vocab` before the delete.
  The spelling is load-bearing. `delete_tag` lowercases its argument for
  matching, and once the tag is gone from the vocabulary
  `normalize_tags` has nothing to snap to — so an undo built from the
  user's typed string could restore `lent out` where `Lent Out` stood.
  It returns `(None, None)` where it used to return `None`, keeping the
  route's 404-on-unknown-tag behaviour.

`_rewrite_tags` keeps its existing rule about what counts as a changed
row, including the `GENRE`-only case where `pre_edit` moved but the live
column did not. That case cannot arise for `USER_TAGS`, which is
`snapshot=False`, so the undo never receives a row whose visible tags
stayed put. The rule is left alone rather than narrowed: `rename_tag`
and the genre routes depend on it.

### Routes

```
POST /api/user-tags/bulk    → {"ids": [1, 2, 3]}
POST /api/user-tags/delete  → {"ids": [1, 2, 3], "tag": "Lent Out"}
```

`changed` is dropped rather than left beside `ids` as a second
derivation of one fact; the client says `ids.length`. Same reasoning as
the unsold-overlaps fix — a count re-derived beside the set it came from
is where the two quietly stop agreeing.

Validation on the bulk route is unchanged.

## Client

`renderBulkBar` gains a third control, after the note:

```
Bulk: [tag input] [Add to N shown] [Remove from N shown]  [Undo: restore "lent out" to 47 items]
```

Hidden when the slot is empty.

**The label names the operation, not just "Undo".** Required, because
the affordance lives in a bar labelled *Bulk* while one of the three
operations it covers was performed in a different panel entirely.

**The bulk bar, and not in place beside each control.** Rendering the
undo next to whichever control fired is better to read and has a
specific failure here: tag management sits behind an *Edit tags* toggle
inside the collapsible statistics panel, which is rebuilt via
`innerHTML` on every render, so an undo offered there can vanish the
moment the panel closes. An undo you cannot find is worse than none,
because you stop looking for another remedy. The bulk bar is outside the
table's `innerHTML` rebuild and is never collapsed.

**Two slots, one per panel, were rejected.** Single-level undo makes at
most one operation recoverable anyway, and two slots would let you undo
the older of two operations while the newer stands — not what
single-level means, and confusing to offer.

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
- **Collapses case variants.** Both operations match case-insensitively
  and drop every spelling; the undo restores one. Reasoned, not
  measured — there is no data to measure.
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
- `delete_tag` returns the ids it changed and the stored spelling, with
  the spelling taken from the catalog rather than from the argument
  (delete `lent out` where `Lent Out` is stored, and get `Lent Out`
  back).
- `delete_tag` still reports an unknown tag distinguishably.
- `rename_tag` still returns a count, unchanged by `_rewrite_tags`'
  new return type.
- `pre_edit` stays `NULL` and `hand_edited` stays false across a bulk
  add, a bulk remove, a delete and an undo of each.

API level:

- both routes' new response shape;
- a round trip — bulk remove, then the inverse bulk add over the
  returned ids, restores exactly the rows that changed and leaves rows
  that never carried the tag alone;
- the same round trip for a catalog-wide delete, restoring the stored
  spelling;
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

- **Rename.** Its inverse needs a per-item record of which rows held the
  old spelling and which already held the new one — the merge is
  genuinely lossy, and a changed-id list cannot reconstruct it. A
  different feature wearing the same word.
- **A redo.** See above: the original operation is one click away.
- **Persisting the slot**, in any form. The argument is in **The slot**.
- **Undo for anything outside the user-tag vocabulary.** Genre is
  enrichment data with `pre_edit` behind it and already has Revert.
