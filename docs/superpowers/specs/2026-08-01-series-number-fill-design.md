# Filling the series number from the title

Replaces the backlog's **`clean_title`'s series-number hint understands
the wrong spelling** entry, which asked for `clean_title` to be widened
from the parenthesized `(Vol. 1)` spelling to the bare `Vol. 3` one.
Measurement rejected the mechanism and kept the goal — the same shape as
the volume-aware overlaps entry that produced this one.

## The entry's stated blocker is not the real one

The entry says widening "is not free: `enrich.py:156` consumes
`num_hint` for matching, so it would silently change enrichment across
the whole catalog". The first half is wrong.

`num_hint` never reaches matching. `enrich.run` binds it at line 156 and
reads it once, at line 191:

```python
if best.get("series_number") is None and num_hint is not None:
    best = {**best, "series_number": num_hint}
```

That runs *after* `status_for(best_conf)` has already decided the
outcome, on a candidate that has already won. It fills one field on the
way to the database. It cannot change which candidate wins, its
confidence, or its status.

**The real effect is catalog-wide, and it is larger than the entry
claimed.** Widening the hint means the marker is *stripped from the
cleaned title*, and `cleaned` — not the hint — is what feeds
`src.lookup(cleaned)`, `score(cleaned, …)` and `harvest.build_worklist`.
The entry named the harmless consumer and missed the load-bearing one.

## What the measurement found

Two candidate widenings, both scored across all 2,729 items. **A**
anchors the bare marker to end-of-string; **B** also allows a
`: Subtitle` tail, which `series.py` already needs because 113 of 679
markers carry one.

| | A: `Vol. 3` | B: also `Vol. 3: Subtitle` |
|---|---|---|
| items whose cleaned title changes | 557 | 663 |
| by type | 550 comic, 7 ebook | 650 comic, 10 ebook, 3 audiobook |
| currently `matched` among them | 468 | 558 |
| distinct enrichable titles | 2,308 → **1,894** | 2,308 → **1,811** |
| items newly sharing a title with another | 516 | 614 |
| largest collapsed group | **44** | **44** |
| new uncached queries (live fetches) | 143 | 166 |

The collapse is the finding. Stripping the volume marker merges every
volume of a series onto one query string, so enrichment asks a single
question for 44 distinct books and scores all 44 identically — every
volume receives the same candidate, and the series number becomes the
only thing distinguishing them. That is a quality regression on 468
currently-matched items, bought in exchange for a field that can be
filled without it.

**So `clean_title` is not widened.** `parse_series` already reads the
bare spelling, and it takes `clean_title`'s *output* as its input, so
the number is obtainable with `cleaned` left exactly as it is. The two
effects the entry bundled together are separable, and only one of them
is wanted.

`test_clean_title_hint_still_fires_only_on_the_parenthesized_spelling`
stays. Its comment does not: it repeats the "consumes this hint for
matching" claim, and a pinning test that misstates what it is pinning
invites the next reader to unpin it.

## What is actually gained

`parse_series` over the catalog:

| Outcome | Items |
|---|---|
| numbered volume | 675 |
| collection | 7 |
| no series | 2,047 |

Of the 675 numbered volumes:

| | Items |
|---|---|
| `series_number` is NULL | **667** |
| `series_number` already set | 8 |
| …of which agree with `parse_series` | **8** |
| …of which disagree | **0** |
| hand-edited among the 667 | **0** |

Zero disagreements across every row that can be checked. That is the
evidence the derived number is safe to write — not an assumption that it
is.

By enrichment status, the 667 are 562 `matched`, 87 `low_confidence`,
10 `manually_fixed` and 8 `unmatched`.

### The series name comes with it

The viewer renders the name and number as one cell
(`catalog.js`: `${esc(i.series)}${i.series_number ? " #" + … }`), so a
number written to a row with no name prints a bare `#3`. Among the 667:

| | Items |
|---|---|
| a source already supplied a series name | 549 |
| …whose name agrees with the title-derived base | 471 |
| …whose name differs | 78 |
| no series name at all | **118** |

**Shipped correction (the live run, same day):** the pass amended 668
rows, not 667. 667 gained a number and **119** gained a name — one more
than the 118 counted here, because one row already carried a number with
no name beside it and so is outside the 667 while still needing the name
fill. The same row is why 8 rows have a number but only 7 need nothing.

The 118 gain a name from `parse_series`'s `display`. The 549 keep what
the source gave them, including all 78 disagreements — 74 of those 78
share a word with the title base or are a substring of it, so they are
spelling drift where the source's prose is the better of the two, and
the 4 with nothing in common are too few to build a rule on. Reconciling
them is a separate question and is not asked here.

## The rule

One rule, applied by both write paths:

> Where an item's own title parses as a numbered volume, fill
> `series_number`, and `series`, **only where there is no value
> already**.

"Already" resolves differently on each path, and deliberately so. The
top-up reads the stored column, because the row it is amending is the
only thing that exists. `enrich.run` reads the winning candidate's
field, because it is assembling a row that is about to replace the
stored one wholesale — that is what `apply_candidate` does — so the
stored value is not the thing being defended there. Both mean the same
in effect: the title-derived value is the last resort, never an
override.

NULL-only is what makes the top-up safe to repeat and safe to run beside
hand edits, spreadsheet imports and source-supplied values. It is also
what makes it idempotent, which matters because `enrich._RESET_FIELDS`
includes both columns: a `reset` clears the fill, and re-running the
pass is the recovery path.

The fact is derived from the item's own name, so it is filled at **every
status**, including `unmatched`. Gating it on a source match would
import a boundary drawn for source candidates and apply it to a fact no
source supplied — `unmatched` means no source matched this item, not
that nothing is known about it.

## Two write paths

**1. Inside `enrich.run`.** Line 191 asks `parse_series` for the number
instead of reading `num_hint`, and gains the symmetric fallback for
`series`, matching `apply_candidate`, which already writes both fields
from the candidate. Covers every item enriched from here on, so the
top-up is genuinely one-off rather than a standing chore.

The hint keeps its place as `parse_series`'s `number_hint` argument, so
`Wings of Autumn Dusk (Book 1)` is still read by the pattern written for
it. Nothing about the parenthesized spelling changes.

**2. `enrich --series`, a top-up pass.** Follows the `--credits`
precedent — a flag on `enrich` that walks already-processed items and
fills one thing — rather than adding a sixteenth subcommand for a job
that is enrichment's own.

It must **not** route through `apply_candidate`, which rewrites
`status`, `match_confidence`, `hand_edited` and `enrich_override` and
snapshots `pre_edit`. This pass issues a narrow
`UPDATE enrichment SET …` naming only the columns it fills. Everything
else about the row is none of its business, and the difference is
observable: routing through `apply_candidate` would clear the
`hand_edited` flag on rows it was supposed to leave alone.

## Where the code lives

The fill rule is one function in `enrich.py`, beside `apply_candidate`.

Not `titles.py`: that module is pure string work with no database
access, and `parse_series` already gives it everything it needs to.

Not `series.py`: that module is deliberately live-derived with no stored
state — "nothing to migrate, nothing for `reset` to preserve" is the
first thing its docstring says — and putting a database *writer* in it
would contradict the property it was built around. It stays a reader.

## Testing

The 8 pre-existing numbers agree with `parse_series` on all 8, so the
NULL-only rule currently has no live counterexample. It is pinned by
tests rather than by that luck:

- a row whose `series_number` is already set, disagreeing with the
  title, survives the pass unchanged
- a `hand_edited` row is not touched, and its flag is still set
  afterwards — the `apply_candidate` trap, asserted rather than assumed
- `status` and `match_confidence` are unchanged by the pass
- running the pass twice changes nothing the second time
- an `unmatched` row **is** filled — the decision most likely to be read
  as a bug later, so it gets a test that says it is deliberate
- a row with a source-supplied series name keeps that name while gaining
  a number
- `clean_title` still returns no hint for the bare spelling — the
  existing pinning test, with a corrected comment

Fixtures come from `docs/TEST-DATA.md`: `Shadow Hound Vol. 2` and
`Shadow Hound Vol. 1: Origins` for the marker spellings,
`Wings of Autumn Dusk (Book 1)` for the untouched parenthesized path,
`Circle of Storms` for the hand-edited row, and `Unrelated Book` for the
control that parses as no series and must gain nothing.

## Non-goals

- Widening `clean_title`. Measured and rejected above.
- Reconciling the 78 rows where a source's series name disagrees with
  the title-derived base.
- Any change to the harvest cache, the worklist, or what a source is
  asked. `cleaned` is byte-identical before and after this work, which
  is the property that makes the whole change cheap.
- Backfilling `series` on rows that already have one, or filling either
  field on the 7 collection-kind items — a collection states no volume
  number, and inventing one is the overclaim the volume-aware overlaps
  work removed.
