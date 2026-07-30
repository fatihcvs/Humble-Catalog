# Harvest worklist order — design

Date: 2026-07-30.
Backlog entry: "`build_worklist` order is incidental, not guaranteed"
(Harvest, identified 2026-07-26 while debugging resume).

## The problem

`build_worklist`'s docstring promises:

> Titles are de-duped per source so two items with the same cleaned title
> cost one request, and order is preserved for stable, resumable progress.

Half of that is enforced by the code — the `seen` sets do the de-duping.
The other half is not. The query is `SELECT name, type FROM items` with no
`ORDER BY`, so the row order is whatever SQLite chooses to return. Today
that is a rowid scan, which is insertion order, and the promise holds by
accident. Nothing in SQL guarantees it, and `reset`, a `reparse`, a merge
or a schema change could each reorder the scan without warning.

No test pins the order, so a reshuffle would be silent. The three
existing worklist tests assert with `in` and `.count()`, never an index.

### What actually depends on it

**Determinism, and nothing else.** That is the whole case for this
change, and it is worth being precise about why the more appealing
justification does not survive measurement.

Not resume. `_run_pool` decides each title on its own — a cache hit costs
nothing, a `CacheMiss` is skipped — so the set of uncached titles shrinks
monotonically whatever order the list is walked in. Resume is keyed on
the cache, not on position, and the backlog entry says so.

Not the quota either, except briefly. It is tempting to argue that order
chooses which titles a rate-limited source enriches today, since the list
is walked front to back until the quota dies. But the cache-skip is free,
so the walk is really "visit the *uncached* set in list order" — and if
that set is smaller than the day's budget, every member of it is fetched
today whatever position it holds. Order decides something only while the
uncached remainder exceeds the daily quota.

Measured 2026-07-30: ~2,300 eligible items, ~570 google_books titles
cached, so ~1,750 uncached against roughly 1,000 requests a day after
`82d178b`. That condition holds for about two more days. Reopening it
would need a single day's purchases to leave more than ~1,000 titles
uncached, and the largest bundle in the catalog is ~150 items.

So this is a tidiness fix, deliberately and by measurement — not a
performance one. What it buys is that two runs over an unchanged catalog
present the same work in the same sequence, so a log from one run reads
against another, and a test can assert an order at all. The defect being
fixed is a docstring stating a guarantee the code does not make, which is
worth fixing on its own terms and would be worth fixing if the quota were
infinite.

## The change

Sort each source's list after de-duplication, in `build_worklist`'s
return statement:

```python
return {name: sorted(titles, key=lambda t: (t.casefold(), t))
        for name, titles in worklist.items() if titles}
```

That is the whole functional change: `titles` becomes
`sorted(titles, key=...)`. The dict comprehension, the `if titles` filter
that drops sources no item type asked for, and the keys are untouched.

### Why a Python sort rather than `ORDER BY`

`ORDER BY name` would make the SQL row order defined, but the worklist is
keyed on the *cleaned* title, not on `name` — `clean_title` strips
edition suffixes, `: A Novel`, and trailing parentheticals, any of which
can change a title's position. The promise would still be one derivation
removed from what the list actually holds.

Sorting the finished lists makes the order a pure function of the item
set. It needs nothing from SQLite, so no `reset`, `reparse`, merge or
schema change can reshuffle it, and the guarantee is testable without
reasoning about query plans.

### Why the key is a two-part tuple

`sorted(titles)` alone is codepoint order, which places every capital
before every lowercase — `Zebra` before `apple` — which is unhelpful in
a log line and looks like a bug.

`key=str.casefold` alone would reintroduce the exact defect being fixed.
Python's sort is stable, so two cleaned titles differing only in case
would tie on the key and fall back to the input order — which is the
unordered `SELECT`. The bug would survive inside its own fix, narrowed
to case-differing pairs. `clean_title` preserves case (it only strips
`" ,-"` from the ends), so such pairs are two distinct entries in `seen`
and both reach the list; this is reachable, not theoretical.

`(t.casefold(), t)` is a total order over content alone. Tuples compare
lexicographically, so the casefolded form decides and the raw string
breaks ties.

`casefold()` rather than `lower()` because it is Unicode's caseless
matching — German `ß` folds to `ss`, Greek final sigma to plain sigma —
and costs nothing over `lower()`. The `key=` form also means it is
evaluated once per title rather than once per comparison.

### Accents are left alone

`casefold()` is not accent-folding. An accented character sorts by its
codepoint, so it lands past `z` — but only when it is the *deciding*
character. `Café of Broken Clocks` sorts at C as expected, because
position 0 settles it against every title not starting with `Ca`. A
title whose *first* letter is accented would sort after `Wings of
Autumn Dusk`.

This is accepted, not fixed. The property the change needs is
determinism — the same item set always yields the same order — and
codepoint order delivers that exactly. Reading alphabetically to a human
would need `unicodedata.normalize("NFKD", …)` with combining marks
stripped, which nothing else in the project has reason to do.
`static/fuzzy.js` does hand-roll accent folding, because there it is
load-bearing (a search for `Cafe` must match `Café`) and it must keep an
index map back to the original string so highlight spans do not shift.
Nobody searches the worklist; it is walked front to back.

## Worked example

Five items, inserted in this order, all contributing to one source's
list:

| Item name | Cleaned title | Sort key |
|---|---|---|
| `Wings of Autumn Dusk (Book 1)` | `Wings of Autumn Dusk` | `("wings of autumn dusk", …)` |
| `gray waters` | `gray waters` | `("gray waters", "gray waters")` |
| `Gray Waters` | `Gray Waters` | `("gray waters", "Gray Waters")` |
| `Café of Broken Clocks` | `Café of Broken Clocks` | `("café of broken clocks", …)` |
| `Axebearer (Grim & Fell)` | `Axebearer` | `("axebearer", …)` |

Result: `Axebearer`, `Café of Broken Clocks`, `Gray Waters`,
`gray waters`, `Wings of Autumn Dusk`.

Two things the trace shows. The accented title sorts at C, because its
accent is not the deciding character. And the two Gray Waters tie on the
first key element, so the second decides — `G` is codepoint 71 and `g` is
103, so the capitalised one comes first. Which one wins does not matter;
that a *content* rule and not the SQL row order decides it does.

## Side effect, stated plainly

This moves google_books' frontier from insertion order to alphabetical.
Nothing already cached is re-fetched — the cache is keyed on the title,
not on a position — so no quota is wasted and progress stays monotone.

The observable consequence is that the roughly two remaining catch-up
days enrich a different set of titles than they would have, in a
different sequence. Once the uncached remainder drops below a day's
quota the reordering has no observable effect at all, by the same
argument that makes this a tidiness fix rather than a performance one.
Worth naming because it is a behaviour change, and worth keeping in
proportion: it is two days of different ordering, not two days of lost
work.

## Explicitly not in scope

**Prioritising new purchases.** Newest-purchase-first looks like the
better answer — a bundle bought today enriched today rather than in
several days — and it was considered and rejected on measurement, not
postponed for convenience. Recording why, so it is not re-derived later:

- **Its benefit expires before it could ship.** Order only matters while
  the uncached remainder exceeds the daily quota (see *What actually
  depends on it*), which is about two more days. After that a new
  bundle's titles are fetched the same day at any position, because
  every uncached title fits inside one day's budget. No realistic
  purchase reopens the window: the largest bundle in the catalog is
  ~150 items against a ~1,000/day quota.
- **It is a superset of this change, not an alternative.**
  `purchased_at` lives on `bundles`, so every item in one bundle shares
  a key — up to ~150 identical keys. Newest-first therefore needs a
  content tiebreak underneath it, which is exactly the sort designed
  here. Building it later means adding a join above this, not replacing
  it.
- **It costs more than it looks.** The purchase date is not on `items`
  at all, so it needs `item_bundles` joined to
  `MIN(bundles.purchased_at)` — an item can sit in several bundles, the
  reason `export.py` takes `min(purchased)` — plus a defined slot for
  items with no bundle row. Neither case exists in the catalog today
  (measured: no bundle has a null date, no item lacks a bundle), so both
  would be defensive code with no live example to test against.

Revisit only if the quota tightens or the catalog grows enough that a
single day's purchases can leave more than a day's quota uncached.

**A sweep for sibling cases.** Other queries may have consumers that
assume an order SQL does not promise. Out of scope; this entry is about
`build_worklist`.

## Tests

In `tests/test_harvest.py`, which currently pins nothing about order:

- **`test_worklist_is_sorted_regardless_of_row_order`** — seed items in
  deliberately non-alphabetical order, assert each source's list comes
  back sorted by casefolded title. This is the assertion the docstring
  has been claiming all along.
- **`test_worklist_order_breaks_case_ties_by_content`** — seed
  `Gray Waters` and `gray waters` in each insertion order, and assert
  both runs produce the same sequence. Pins the second key element: with
  `key=str.casefold` alone the two orderings would differ, so this test
  fails against the stable-sort accident and passes against the tuple.

The three existing worklist tests stay green unchanged — they assert
membership and counts, not positions.

Verification is `scripts/windows/verify.ps1` — the full suite plus both
privacy checks, the latter because this change adds names to
`docs/TEST-DATA.md` and to a test. No fixture or cache change is
involved, and the sort is a pure function of its input, so a live
harvest is not needed to prove the change.

## Also in this change

- **`docs/TEST-DATA.md`** — add the case-only pair
  `Gray Waters` / `gray waters` used by the tie test. (`Gray Waters` is
  already used in `test_harvest.py` but was never recorded there.)
- **`docs/BACKLOG.md`** — move two entries to **Done**: this one, and
  "Retries spend quota, and google_books is where that hurts", which
  shipped in `82d178b` without being moved. Newest-purchase-first goes
  under **"Explicitly out of scope (decided against, not merely
  postponed)"**, not under Open — it was measured and rejected, and
  filing it as Open would invite a future session to re-derive the join
  the measurement rules out. The entry carries the expiry argument and
  the ~150-item/~1,000-quota figures, so the rejection can be re-checked
  rather than taken on trust.
- **The docstring itself** — restated to promise what the code now makes
  true, and to say the order is a pure function of the item set rather
  than a property of the query.
