# Bundle preview: overlaps for items no tier sells — design

Date: 2026-07-31.
Backlog entry: "`_overlaps` hints about items no tier sells" (Bundle
preview, deferred from `specs/2026-07-25-bundle-preview-design.md`).

## The problem

`preview` carries two different notions of "the bundle's items", and
`_overlaps` reads the wrong one.

| Notion | Source | Read by |
|---|---|---|
| What the bundle **sells** | union of `tier_display_data[*]["tier_item_machine_names"]` | every count (`total`, `owned`, `possible`, `new`), the `adds` lists, `game_names`, `unmatched_stores` |
| What the bundle **describes** | `tier_item_data` | `_overlaps`, and nothing else |

Every other consumer of `tier_item_data` reaches it by *lookup* —
`items.get(name)` for a `name` that already came from a tier's list.
`_overlaps` is the only place that treats the metadata dict as the item
list, iterating `items.items()` directly.

The two are usually co-extensive, which is why this survived. On the
committed book fixture they are identical, 6 entries against 6 sold, so
no existing test could see it. The backlog entry records a live bundle
carrying 13 entries while its only tier listed 12.

### Reproduced

Adding one entry to `tier_item_data` in `bundle_data.json` and nothing
else — no tier sells it:

```
tier totals   : [6, 3, 1]        <- unchanged, correctly ignoring it
overlap: 'Shadow Hound Vol. 1-6'         ~ 'Shadow Hound Vol 1'  0.92
overlap: 'Shadow Hound Vol. 1-6 (Bonus)' ~ 'Shadow Hound Vol 1'  0.92   <- not for sale
overlap: 'Moonfall Vol. 1-3'             ~ 'MOONFALL, Vol. 1'    0.91
```

Every count correctly ignores the entry. The overlap list reports it
anyway, so the report hints that the owner may already own part of
something they cannot buy at any price.

### It is not only a spare row

The backlog entry describes this as an extra hint. It is worse than
that: a phantom entry also escapes the **book/game routing**.

`game_names` is accumulated by the tier walk. A phantom is never walked,
so it is never in `game_names`, so the exclusion at the call site —

```python
"overlaps": _overlaps(conn, items, owned | game_names),
```

— structurally cannot cover it. Both exclusion sets are keyed to the
sold set; neither can name an entry the sold set never mentions. A
phantom entry carrying `platforms_and_oses: {"game": {"steam": [...]}}`
is therefore scored against the **book** catalog:

```
overlap: 'Shadow Hound Vol. 1-6' ~ 'Shadow Hound Vol 1'  0.92    <- a game, matched to a book
```

That is exactly the cross-media invention the comment three lines above
that call says was fixed after being observed on a live bundle. The fix
is complete for sold items and empty for phantom ones.

`game_matching` also stays `False` in that case, because it too is
derived from the walk — so the report prints an approximate cross-media
hint with none of the "APPROXIMATE — verify anything you would buy on"
warning that exists to qualify it. The one hint least worth trusting
arrives with the least attached.

### What a phantom actually is

Not a Humble bug. `tier_item_data` is a metadata dictionary, and a
subproduct described there but sold by no tier is ordinary: a bonus
wallpaper, a soundtrack, an art pack, an item pulled from a tier after
the page data was assembled. `tests/fixtures/game_bundle_data.json`
already carries one — `bonuswallpaper_examplegames`, `"Bonus Wallpaper"`
with `platforms_and_oses: {}` — captured from a live bundle and
untouched since. It goes unnoticed today only because its title matches
nothing in the fixture catalog; at 32.3 it is nowhere near the 90 cutoff.

So the entry is real data being read for the wrong question, and the
right behaviour is to exclude it silently. There is no case for
reporting it: the whole report answers "should I buy this bundle", and
an item no tier sells cannot be bought by buying this bundle.

## The change

Collect the overlap candidates **during the tier walk**, and let
`_overlaps` take only that list.

`preview`'s loop already visits every sold item and already decides both
questions the exclusion sets encode — owned or not, book or game. The
book path is one branch:

```python
if not delivery_stores(item):
    new_names.append(name)
    continue
```

Owned items `continue` above it; games take the branch after it. So the
names reaching that branch are precisely *sold, unowned, book-path* —
precisely the overlap candidates. Collecting there makes all three
exclusions properties of how the list was built.

`_overlaps` loses both of its filter parameters:

```python
def _overlaps(conn, candidates):
    """Offered titles that look like partial matches for owned rows.

    `candidates` is {machine_name: offered_title} for the items a tier
    actually sells that matched no owned machine_name and took the book
    path -- built by preview's tier walk, which has already decided both
    questions. Nothing here re-derives them, so an owned item, a game,
    and an item no tier sells are all unrepresentable rather than
    filtered out.
    """
```

### Why collect rather than filter

The smaller change is to give `_overlaps` a `sold` set and skip
`machine_name not in sold`. It was considered and rejected. It is two
lines and provably preserves every current result, but it leaves the
module with **three** separate exclusion rules for one list — an
`owned` set, a `game_names` set, and now a `sold` set, all assembled by
the caller and all re-applied by the callee — when the caller already
computed the answer as a by-product of work it had to do anyway.

That is the arrangement that produced this bug. `owned | game_names` was
correct on the day it was written and became incomplete the moment a
third exclusion turned out to be needed, because nothing about its
shape said which items it was entitled to see. A fourth would fail the
same way. This is the same reasoning that moved the key report's chip
counts into a `displayState` helper so the four chips partition the
reported rows by construction, rather than by three filters agreeing —
and there the bug made unreachable was of exactly this kind.

It also removes the asymmetry that hid the bug: after this change
`tier_item_data` is read only by lookup, everywhere, with no consumer
iterating it.

### Order stays deterministic

`_overlaps` sorts by score descending, and Python's sort is stable, so
equal scores keep input order. Today that input order is
`tier_item_data`'s JSON order. It becomes the tier-walk order —
`tier_display_data` dict order, then each tier's list order, deduped on
first appearance.

Both are deterministic and both come from the parsed page, so nothing
here rests on set iteration order. Worth stating explicitly because it
is the trap the harvest worklist entry documents: a `set` of
machine_names would have made tie order vary between processes under
hash randomization, and the sort would have hidden it everywhere except
on exact ties. The candidate collection is therefore a `dict`, which
dedupes and preserves order at once.

The observable consequence is that two overlaps with identical scores
may swap places. No test asserts a position, and the list is read as a
set of hints.

### A sold name that `tier_item_data` does not describe

Skipped, preserving today's behaviour exactly: such a name is not a key
of `items`, so `_overlaps` never sees it now either. The collection is
guarded on `name in items` rather than on the `items.get(name) or {}`
the surrounding loop uses.

Falling back to the bare `machine_name` was considered — the tier loop
already does that for its own counts, where it is right, because a name
with no metadata is still an item being sold and must be counted. It is
wrong here. A machine_name is not a title:
`shadowhound_vol1_examplecomics` scored against real titles is a coin
toss whose result is presented to a human as a suspicion, and the
overlap list's entire value is that it is short and its members are
worth reading. Counting must be exhaustive; hinting must not be.

This case appears in neither fixture and has not been observed live, so
the guard is written to keep the current behaviour rather than to
handle a case the change would otherwise introduce.

## What does not change

- Every tier count. `total`, `owned`, `possible`, `new`, `adds`,
  `keyed_items` and `possible_items` are all derived from the sold set
  already and are untouched. A test asserts this.
- `game_matching`, `libraries`, `unimported_stores`.
- The 90.0 cutoff, `clean_title` normalization, the scorer, the output
  format, the viewer, the API shape.
- The book fixture's current three overlaps, unchanged in content and
  order.

## Tests

In `tests/test_bundle_preview.py`:

- **`test_an_item_no_tier_sells_is_never_an_overlap`** — add a phantom
  book entry to a copy of the book fixture's `tier_item_data` and assert
  it is absent from `overlaps`, and that the overlap list is byte-equal
  to the unmodified fixture's. Fails before the change with the phantom
  present.
- **`test_an_item_no_tier_sells_does_not_change_any_count`** — the same
  bundle, asserting the tier counts match the unmodified fixture's.
  Passes before and after; it pins that the fix stayed on the overlap
  list and did not reach the counting, which is the way this change
  could do damage.
- **`test_an_unsold_game_entry_is_not_matched_against_books`** — a
  phantom carrying `platforms_and_oses: {"game": {...}}`, asserting no
  overlap. This is the cross-media half, and it fails before the change
  for a different reason than the first test: not a spare row, but the
  wrong catalog.

The phantom's `human_name` is **`Shadow Hound Vol 1 Bonus Art Pack`**,
measured at **100.0** against the owned `Shadow Hound Vol 1` — the owned
title's tokens are fully contained in it, which is where
`token_set_ratio` returns a perfect score. Chosen deliberately: it is a
plausible Humble subproduct, and because it outscores both genuine
overlaps it sorts to the *head* of the list, so a regression is the
first line of the block rather than a row buried in the middle.

The phantom is added by the tests to a mutated copy of the fixture, not
committed into `bundle_data.json`. The fixture is an anonymized capture
of a real page and the existing tests read its counts directly; editing
it would mean re-deriving those expectations to test something the tests
can express on their own.

Existing tests stay green unchanged. `test_game_titles_never_produce_book_overlap_hints`
keeps asserting `overlaps == []` on the game fixture, and now does so for
a stronger reason: `bonuswallpaper_examplegames` is excluded structurally
rather than by scoring 32.3.

Verification is `scripts/windows/verify.ps1` — the full suite plus both
privacy checks, the latter because this change adds a name to
`docs/TEST-DATA.md` and to a test. `preview` is pure, so no network and
no live bundle is needed to prove the change.

## Also in this change

- **`docs/TEST-DATA.md`** — add `Shadow Hound Vol 1 Bonus Art Pack`
  under *Comics / manga*, noted as the described-but-unsold subproduct
  for the bundle-preview phantom tests. `Bonus Wallpaper` is already
  listed and needs no change.
- **`docs/BACKLOG.md`** — move this entry to **Done**, recording the
  cross-media half, which the open entry did not know about, and the
  collect-versus-filter decision.
- **`_overlaps`'s docstring** — its current first paragraph explains why
  an exactly-owned item cannot appear, a fact that moves from the
  function to its caller. Restated to describe what `candidates` is and
  who guarantees it.

## Explicitly not in scope

**Volume-range resolution.** The open backlog entry directly above this
one — parsing `Vol. 1-6` into a set and reporting "you own 1 of 6"
instead of listing a possible overlap. It changes what an overlap
*means*; this changes which items are eligible to be one. Both fixture
overlaps are volume-range pairs, so the two entries touch the same
rows and are still independent.

**A sweep for other consumers reading the wrong collection.** This entry
is about `_overlaps`. `tier_item_data` has no other iterating reader
after this change, which is the claim worth making here; whether a
similar split exists elsewhere in the project is its own question.
