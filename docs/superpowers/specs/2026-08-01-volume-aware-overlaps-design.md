# Volume-aware overlaps

Replaces the backlog's **Volume-range resolution** entry, which asked for
`Vol. 1-6` to be parsed into a set of volumes and reported as "you own 1
of 6". Measurement rejected the mechanism and kept the goal.

## What the measurement found

The deferral said to revisit "once the overlap list has shown how often
ranges appear in practice". Counted across all 2,729 items:

| Pattern | Count |
|---|---|
| `Vol. 1-6` — noun plus range, the spelling the entry names | **0** |
| Bare issue range `#N-M` | 11, all comics, all parenthetical |
| Single volume number (`Vol. 3`) | 687 (672 comic, 12 ebook, 3 audiobook) |
| A collection word (*complete*, *anthology*, *omnibus*, …) | 24 |

**Volume ranges as specified do not occur.** The only ranges present are
*issue* ranges, and 8 of the 11 sit inside a single-volume title:

```
Shadow Hound Vol. 22 (#127-132)
```

That range is not an offer of six things. Volume 22 *collects* issues
127-132; issue numbers and volume numbers are different axes. Parsing it
as a range would report a one-volume product as a six-volume one — wrong
in the confident direction, which is the direction a buy/don't-buy tool
must never be wrong in.

The token is also already gone before any of this could run.
`titles._TRAILING_PAREN` strips a trailing parenthetical, and all 11
ranges are parenthetical, so `Shadow Hound Vol. 22 (#127-132)` reaches
`_overlaps` as `Shadow Hound Vol. 22`.

The premise appears to have come from the anonymized example rather than
from the data. `specs/2026-07-25-bundle-preview-design.md` illustrates the
case with `Shadow Hound Vol. 1-6`, and `docs/TEST-DATA.md` records that
same invented title as "omnibus offered by a bundle". Under the privacy
standing order the illustration is invented by necessity; the cost is
that it can become the thing later work reasons from. Recorded here
because it is a general hazard of the rule, not a one-off: **cite counts
alongside invented examples**, so the example carries its own evidence.

### The overlap list is currently backwards

`bundle_preview.OVERLAP` is 90.0. Scored with the same
`token_set_ratio` the module uses:

| Offered | Owned | Score | Today |
|---|---|---|---|
| `Shadow Hound Vol. 7` | `Shadow Hound Vol. 3` | **94.7** | listed as possibly owned — but it is **not** owned |
| `Shadow Hound Vol. 7` | `Shadow Hound Vol. 17` | **97.4** | listed, and more confidently wrong |
| `Shadow Hound Omnibus` | `Shadow Hound Vol. 3` | **77.4** | **not listed** — yet this is genuine partial ownership |

The list shows the pairs it should not and hides the pair it exists for,
and the error grows with the score. Same shape as `titles.sequel_mismatch`:
the near-identical pair is the one that is definitely a *different*
product, so it needs a rule rather than a threshold.

### The owner collects series densely

172 volume-numbered series; 115 held at two or more volumes; 614 items
among them. Only 2 of 115 have a gap in their run, so "you own Vol. 1-6"
is almost always a truthful contiguous statement.

### Exact base keys fragment a series; stripping punctuation fixes it

Five pairs of distinct bases scored >=85 against each other. Four were
one series split by punctuation drift — a trailing period on an
initialism (`A.B.C.D` / `A.B.C.D.` / `A.B.C.D.:`) or a space where
another row used a hyphen. Their volume sets were disjoint and
contiguous once joined, which is what identified them.

Normalizing the base the way `clean_game_title` already does — non-word
characters to spaces, runs collapsed, lowercased — takes 172 bases to
**169**, merging exactly those four and nothing else. The one surviving
>=85 pair differs by a trailing plural `s` and its two halves hold
*identical* volume sets [1-6]; overlapping volumes are evidence of two
different series, and it correctly stays split. Series-with-gaps also
drops from 2 to 1: one "gap" was one series filed under two spellings.

So **no fuzzy matching and no threshold appears anywhere in this
feature**. Same conclusion the edition-linking entry reached, from the
same direction: exact keys plus a marker strip find every genuine pair
and invent none.

## Scope

In:

- A bare volume marker parsed off an offered title, and the owned volumes
  of that series reported.
- Collection words handled by the same mechanism.
- Volume-differing pairs removed from the overlap list, where they are a
  false claim of partial ownership.

Out, deliberately:

- **Expanding a range into a set of volumes.** Zero occurrences among
  owned titles, and the issue ranges that do occur are stripped upstream.

Ranges must still be **recognized**, which is not the same thing and is
the correction that writing the plan produced. A bare-volume pattern
reads `Shadow Hound Vol. 1-6` as volume 1; that would match an owned
Vol. 1 and print ALREADY OWNED, discouraging the purchase of five books
not held. So a range parses as `kind="collection"` carrying its span,
never as its lower bound. The failure it prevents is the expensive one,
and it costs one pattern tried before the single-volume pattern.

Handled that way, the range is also the one spelling that states its own
denominator — so **"you own 1 of 6" returns, for exactly that case**. An
omnibus word carries no size, so there the report says how many volumes
are owned and leaves the denominator unstated rather than guessed.
- **Widening `clean_title`'s series-number hint.** It fires on 3 of 2,729
  items because it understands only the parenthesized `(Vol. 1)`
  spelling, while the bare spelling covers 687. Widening it looks
  obviously right and is a separate decision: `enrich.py:156` consumes
  `num_hint` for enrichment matching, so the change would silently alter
  matching across the whole catalog. Its own backlog entry, with this
  measurement attached.
- Any persistence. Detection is live, mirroring `dedupe.find_groups` and
  edition linking — nothing to migrate, nothing for `reset` to preserve.

## Parsing and the series key

New in `titles.py`, beside `clean_title`, which is **unchanged**:

```python
parse_series(raw) -> (key, display, number, kind)
```

Runs on `clean_title`'s output, so trailing parentheticals are already
gone and the issue ranges never reach it.

- `kind` is `"volume"` for a bare `Vol.` / `Vol` / `Volume` / `Book`
  marker, `"collection"` for a range (`Vol. 1-6`) or a collection word
  (*omnibus*, *complete collection*, *compendium*, *anthology*, *box
  set*), and `None` otherwise. The range pattern is tried **first**, so a
  range can never be read as its lower bound.
- `span` is `(lo, hi)` for a range and `None` otherwise — the only source
  of a denominator.

A marker may be followed by `: Subtitle`: **113 of 679** volume markers
are, so anchoring to end-of-string alone would drop a sixth of the
population. The subtitle is discarded, which correctly files
`Vol. 1: Origins` and `Vol. 1: Endings` as the same volume of the same
series.
- `key` is everything before the marker, non-word characters replaced by
  spaces, runs collapsed, lowercased — the normalization measured above.
- `display` is that same slice left as written, for output and for the
  viewer's jump. Two returns rather than one because the key must
  discard punctuation to match and the display must keep it to read: the
  three fragmented spellings of one initialism share a key, and each
  keeps its own display.
- `number` is the volume integer, or `None` for a collection.

When `clean_title` has already returned a series-number hint — the
parenthesized `(Book 1)` spelling — `parse_series` accepts it rather than
re-deriving it. Both spellings are handled and the existing hint is used
rather than widened.

An item with no marker yields `(None, None, None)` and takes no part in
the feature.

No sanity cap on the parsed number. The catalog's largest real volume is
44, nothing in the data motivates a ceiling, and a cap would be a branch
only a synthetic test could reach.

## Lookup

New `series.py`, mirroring `editions.py` and `game_match.py`: pure
functions, testable with no bundle and no network.

**Owned side.** One pass over `items` building `{key: {volumes}}`. No
type filter — the marker was measured on comic, ebook and audiobook rows
and on **zero** android or music rows, so a filter would be a branch no
test could exercise against real data.

**Offered side.** Each book-path candidate is parsed; a hit requires an
exact `key` match.

### Three outcomes, not two

| Offered | Owned | Report |
|---|---|---|
| `Vol. 7` | 1-6 | "you own Vol. 1-6" — a series being collected |
| `Omnibus` | 1-6 | "you own 6 volumes (Vol. 1-6)" — genuine partial ownership |
| `Vol. 3` | 1-6 | **"ALREADY OWNED"** — a probable re-buy |

The third is the most valuable and was not anticipated. It can only arise
when the offered volume matched no `machine_name` yet is a volume already
held — the same book under a different Humble id, a re-issue, or another
edition. That is precisely the mistake the preview exists to prevent, and
today it prints as a bare `0.94` under a heading claiming partial
ownership. It costs one `in` test against a set the feature already
builds.

## Report shape

One new field beside `overlaps`:

```python
"series": [{"offered": str,           # display title as offered
            "series_name": str,       # parse_series' `display`, for the jump
            "kind": "volume" | "collection",
            "offered_volume": int | None,
            "span": [1, 6] | None,    # only an explicit range has one
            "owned": [1, 2, 3, 5, 6],
            "owned_display": "Vol. 1-3, 5-6",
            "already_owned": bool}]
```

A candidate that produces a series hit is **removed** from `overlaps`, so
it is reported once and accurately, and "possibly already owned in part"
keeps meaning only what it says. Collections score 77.4 and were never in
that list, so this only ever removes volume-versus-volume noise.

Gaps render honestly (`Vol. 1-3, 5-6`) through a range-collapsing helper.
One series needs it today.

## Output

### CLI

A block after the tier lists and before the overlap list, omitted
entirely when empty — as `adds` and `keyed_items` are:

```
  Series you already hold (3):
    Moonfall Vol. 1              ALREADY OWNED -- you hold Vol. 1
    Shadow Hound Omnibus         you own 6 volumes (Vol. 1-6)
    Shadow Hound Vol. 7          you own Vol. 1-6
```

Re-buys first, then collections, then continuations; ties by offered
title, case-insensitively. The caps follow the existing
`APPROXIMATE -- verify` convention: this is the one line that should stop
a purchase.

### Viewer

A `bundle-series` section in `bundles.js`, mirroring `bundle-overlaps`.
The owned-volumes text carries one jump control that sets the catalog
search to `series_name` and clears the type filter, showing the whole run
at once. One control rather than one per volume — a 26-volume series
would otherwise emit 26 buttons. Clearing the type filter follows the
edition-linking jump, for the same reason: the run may span types.

## Error handling

No volume-numbered items, or no marker on the offered title, yields an
empty list and no block. That is the only failure mode, and it degrades
to exactly today's output.

## Testing

- Each spelling parses: `Vol. 3`, `Vol 3`, `Volume 3`, `Book 2`, and
  `(Book 1)` through `clean_title`'s existing hint.
- Punctuation-stripped keys merge the initialism-with-trailing-period and
  space-versus-hyphen fragmentations.
- **The negative:** two series differing only by a trailing `s`, holding
  identical volume sets, stay two series.
- `Shadow Hound Vol. 22 (#127-132)` yields volume **22**, never a range —
  the regression test for this entry's original premise.
- `Shadow Hound Vol. 1-6` yields a **collection** spanning 1-6, never
  volume 1 — the regression test for the mis-parse that would print
  ALREADY OWNED against an owned Vol. 1.
- A marker followed by `: Subtitle` still parses.

Two committed tests change behaviour deliberately and are rewritten
rather than deleted. `test_an_omnibus_matching_an_owned_volume_becomes_an_overlap`
and `test_overlaps_carry_the_item_id_so_the_viewer_can_link_to_the_row`
both use the fixture's `Shadow Hound Vol. 1-6` and `Moonfall Vol. 1-3`,
which become series hits and leave the overlap list. The first is
rewritten to assert the richer series line; the second needs a genuine
non-series overlap, and gets one from a locally seeded catalog rather
than by editing the shared fixture — adding an item to `bundle_data.json`
would shift the tier counts and `adds` lists that a dozen other tests
assert on. The `Building Widget Services 2e` / `Building Widget Services,
2nd Edition` pair from `docs/TEST-DATA.md` scores 100 through
`clean_title` with no volume marker, so it serves exactly.
- Each of the three outcomes renders, and a series hit is absent from
  `overlaps`.
- Range collapsing renders a gap as `Vol. 1-3, 5-6`.
- `clean_title` is unchanged: its hint still fires only on the
  parenthesized spelling, pinning the deliberate non-widening so a later
  tidy-up fails loudly rather than quietly altering enrichment.
- The CLI omits the block when the list is empty.

## Privacy

No bundle URL, report, or item name is written to `catalog.db` or to any
log; the feature is read-only, like the rest of `bundle_preview`.

Fixture and documentation examples come from `docs/TEST-DATA.md`. New
rows are **added** there for the punctuation-drift pair, the
identical-volume-sets negative, and the issue-range-inside-a-volume case;
existing rows are kept because tests depend on them, and annotated with
what the measurement showed about the range spelling.

`scripts/leak_check.py` runs before commit, unpiped.

## Build order

1. `parse_series` in `titles.py`, with its tests. `clean_title` untouched.
2. `series.py`: the owned-volume index, the three-outcome classifier, and
   the range-collapsing helper, with tests.
3. Wire into `preview`: the new `series` field, and the removal of series
   hits from `candidates` before `_overlaps` sees them.
4. CLI block in `format_report`.
5. Viewer section and jump in `bundles.js` and `style.css`.
6. `docs/TEST-DATA.md` additions; `docs/BACKLOG.md` entry rewritten from
   "volume-range resolution" to what shipped, plus the new
   `clean_title`-widening entry.
