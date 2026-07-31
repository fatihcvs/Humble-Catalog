# Edition linking: the same work owned in two formats — design

Date: 2026-07-31.
Backlog entry: "ebook ↔ audiobook edition linking" (Catalog features,
identified 2026-07-24 code review).

## The problem

`/api/merge` refuses a cross-type merge:

```python
if rows[keep_id] != rows[drop_id]:
    return jsonify({"error": "items have different types; an ebook "
                    "and its audiobook stay separate"}), 400
```

That refusal is correct — the two rows have different files, different
bundles, and often a different narrator — but it leaves the two formats
with **no relationship at all**. Nothing in the catalog says a work is
held twice, so a row cannot say "also owned as audiobook" and the owner
has no way to find out except by searching the title again with the type
filter changed.

This entry is the gap the merge route's own comment points at.

## What the catalog actually holds

Measured before anything was designed, because the entry's central
unknown is how often the case even occurs. Four probes, each one
correcting the last.

| Probe | Result |
|---|---|
| Exact `dedupe_key`, across types | 1 pair |
| `token_set_ratio` ≥ 90 (bundle preview's cutoff) | 9 pairs |
| Same-author gate, any title | 70 pairs, 3 with related titles |
| **Exact key, trailing format markers stripped** | **4 pairs, no false positives** |

**Fuzzy matching was worse on both axes, not merely more expensive.**
Eight of its nine hits are the subset artifact the unsold-overlaps entry
documents: `token_set_ratio` returns 100 whenever one side's token set is
a subset of the other's, so a one-word ebook title scores a perfect 100
against any six-word audiobook containing that word. The measured pairs
included a one-word title against a six-word one, twice, and a nine-word
title against a one-word one. The cutoff cannot help — the problem is not
a weak score.

**The truth was found by eyeballing the misses, not the hits.** The
author gate — the strongest independent signal available, and populated
on 101 of 108 audiobooks — produced 70 same-author cross-type pairs, of
which exactly one had a matching title. Reading the three highest by
hand showed all three were genuine, scoring 100, 67 and 61. The scores
were dragged down by format-marker suffixes that `dedupe_key` does not
strip: one title carried `(audiobook novella)`, another a bare
`Audiobook`. So the naive title match was finding one of three, and the
signal was never fuzziness — it was a suffix.

Stripping trailing markers and comparing **exactly** finds all of them,
plus a fourth, with nothing spurious.

### The type filter is the entire precision story

Every cross-type exact group in the catalog, after the marker strip:

| Type pair | Groups | What they actually are |
|---|---|---|
| ebook ↔ audiobook | 4 | all genuine editions |
| android ↔ music | 5 | **all** a game plus its own soundtrack |
| ebook ↔ music | 3 | 2 genuine audio editions misfiled as music, 1 coincidence |

Admitting `music` costs six false positives to win two true ones. The
excluded types are not arbitrary: an APK and a soundtrack are things
shipped *alongside* a work, so sharing a title with one means "bundled
together", not "the same work again". Restricting to the types that are
themselves works gives **zero** false positives across the whole catalog.

Widening that set from `{ebook, audiobook}` to include `comic` was
measured separately: **0 further groups across 988 comic items, 0 false
positives**. A comic and an ebook of the same work is a real possibility
the catalog has not happened to buy yet, and admitting the type costs
nothing measurable today.

No score threshold appears anywhere in this feature.

## The change

### 1. A new `editions.py`

Mirrors `dedupe.find_groups` deliberately — **computed live on every
call, no stored candidate state** — and is the only new module.

```python
# Types whose items are works that can exist in another format. android
# and music are excluded, and that exclusion is this feature's entire
# precision story: measured on the catalog, every false positive came
# from one of those two. All 5 android/music groups are a game plus its
# own soundtrack, shipped together rather than the same work twice.
# Including comic was measured separately: 0 further groups across 988
# comics, 0 false positives.
WORK_TYPES = frozenset({"ebook", "audiobook", "comic"})

def edition_key(name): ...
def find_groups(conn): ...   # -> [[item_id, ...], ...]
```

`edition_key` is `dedupe.dedupe_key` with a **trailing run** of format
markers removed — `abridged`, `unabridged`, `audiobook`, `audio book`,
`audio`, `ebook`, `novella` — applied repeatedly until the key stops
changing, so `(audiobook novella)` strips as a unit.

Trailing-only, not anywhere in the string, and that is a deliberate
narrowing. Every marker observed in the catalog is trailing, a
trailing-only rule still finds all six groups, and it protects a title
where the word is load-bearing rather than a format label: a hypothetical
*Audio Engineering Handbook* keeps its first word, where an
anywhere-strip would reduce it to *Engineering Handbook* and invite a
collision with a genuinely different book.

`novella` is the loosest of the markers and the only one that is not
purely a format word — it is included because a measured pair needs it,
and it is worth knowing that two genuinely distinct works named *X* and
*X: A Novella* would group. None exists in the catalog.

The strip lives in `editions.py` and **not** in `dedupe_key`, because
`dedupe_key` is a within-type key: stripping "audiobook" there would
silently change how existing duplicate groups form among audiobooks.

One naming hazard, stated so nobody tidies it: `dedupe.py` already has a
private `_EDITION` regex, and it means *print* edition ("2nd Edition").
Different concept entirely. It stays private, nothing is renamed, and
that collision is why this is a new module rather than a function bolted
onto `dedupe.py`.

`find_groups` returns **groups, not pairs**, exactly as `dedupe` does —
two ebooks and one audiobook sharing a key is handled by construction. A
group qualifies when its members span more than one type.

### 2. `classify.py` accepts a trailing `(audio)`

Two items in the catalog are genuine audio editions of books the owner
also holds as ebooks, filed as `music` because `classify` accepts only
the literal word "audiobook":

```python
if "audio" in platforms:
    if "audiobook" in lowered_bundle or "audiobook" in lowered_item:
        return "audiobook"
    return "music"
```

A trailing `(audio)` parenthetical on the item name joins that condition,
**inside** the existing `"audio" in platforms` guard, so a soundtrack in
a game bundle cannot reach the branch. The docstring's caution stays
right — bare "audio" as a rule would be far too loose — and a trailing
parenthetical is a much narrower signal than a substring.

Measured blast radius: **2 items catalog-wide** carry a trailing
`(audio)`, both genuine, and **no item anywhere carries a
`type_overridden` flag**, so nothing hand-set is stomped. Takes the
population 4 → 6 on the next reparse.

This is not a separate concern that happens to be co-located. It is what
lets `WORK_TYPES` stay tight: without it, catching those two editions
would mean admitting `music` and its six false positives.

### 3. The surface: a badge on the row

`/api/items` gains an `editions` field per item — the sibling ids and
their types — absent for the ~2,717 rows that have none. The viewer
renders a small marker reading "also as audiobook" (or "as ebook", "as
comic"), and clicking it jumps to the sibling row.

A badge and not a panel. The Duplicates panel exists to prompt an action;
this is purely informational, so a panel would be a mostly-empty box with
no buttons, competing with Review, Duplicates and Keys for space. The
badge answers the question where it is actually asked — while looking at
the item.

**Computed in the route, not in `fetch_items`.** `fetch_items` is shared
with CSV and XLSX export precisely "so the two serializations cannot
drift", and an edition link is a derived view rather than a stored fact.
Putting it there would push a computed field into the export's row
source. One `O(n)` pass builds the whole map for the payload; there is no
per-item query, and nothing in the export path changes.

The cost of being wrong about that boundary is one function move, and the
export gains an edition column the day it is wanted.

### 4. Dismissal reuses `dismissed_pairs`

`/api/dismiss_pair` already takes two item ids and stores sorted
machine_names, and `editions.find_groups` filters against the same table
with `dedupe.find_groups`'s exact rule — drop a member only if it is
dismissed against *every* other member.

The two meanings cannot collide: dedupe's pairs are always same-type and
edition pairs are always cross-type, so the key spaces are **disjoint by
construction**, not by convention. A separate table would cost a
migration and a second near-identical route to enforce a separation the
type filter already guarantees.

There is nothing to dismiss today — detection has no false positives —
so this covers the case where two genuinely different works share an
exact stripped title across formats.

## What does not change

- No schema change, no migration, no writes on the read path.
- `dedupe.dedupe_key` and every existing duplicate group.
- `/api/merge` still refuses cross-type merges. A link is the
  alternative to that merge, not a step toward permitting it.
- CSV and XLSX export, and `fetch_items`.
- Nothing to preserve across `reset`: the links are recomputed, so a
  rebuilt catalog has them again for free.
- No CLI surface. Both that and an export column are deliberate
  omissions, and both are cheap to add once missed.

## Tests

New `tests/test_editions.py`:

- **`test_a_trailing_format_marker_is_stripped`** — `Salt and Sextant`
  and `Salt and Sextant Audiobook` share a key; so do `The Copper
  Almanac` and `The Copper Almanac (audio)`.
- **`test_a_marker_inside_the_title_is_kept`** — an *Audio Engineering
  Handbook*-shaped title keeps its leading word, pinning the
  trailing-only rule against a future "simplification" to strip
  anywhere.
- **`test_a_game_and_its_soundtrack_are_never_an_edition_group`** — the
  existing `Cool Tower Defense` android item against a **music** row of
  the same name, which the test constructs: the committed
  `Cool Tower Defense + OST` variant classifies as *android*, so no
  same-named music row exists to reuse. This is the measured
  false-positive shape, five times over.
- **`test_a_subset_title_is_not_an_edition_group`** — `Compass` (ebook)
  against `The Compass of Broken Years Audiobook` (audiobook), which
  scores **100** under `token_set_ratio` and must produce **no** group.
  This is the trap pinned directly, so a later move to fuzzy matching
  fails a test rather than shipping.
- **`test_a_comic_and_an_ebook_group`** — `Nightjar Post` in both types.
  The one test carrying the feature's future rather than its present:
  the catalog has no such pair, and this is what says the type is
  admitted on purpose.
- **`test_a_dismissed_cross_type_pair_disappears`**, and its companion
  that a dismissed **same-type** pair leaves edition groups untouched —
  the disjointness claim, asserted rather than assumed.

In `tests/test_classify.py`:

- **`test_a_trailing_audio_parenthetical_is_an_audiobook`**.
- **`test_a_soundtrack_in_a_game_bundle_is_still_music`** — the
  regression the narrowing exists to avoid; `Sample Game OST` and
  `Sample Ambience Pack` already cover the shape.

All fixtures use invented titles from `docs/TEST-DATA.md`. The new ones
were vetted against `leak_check.build_terms()` before being written down,
per that file's own warning — `leak_check` matches substrings, so a
private term buried mid-title trips it invisibly.

Verification is `scripts/windows/verify.ps1`: the full suite plus both
privacy checks, the latter because this change adds names to
`docs/TEST-DATA.md` and to tests. Detection is pure, so no network is
needed to prove any of it.

## Also in this change

- **`docs/TEST-DATA.md`** — add `Salt and Sextant` / `Salt and Sextant
  Audiobook` and `The Copper Almanac` / `The Copper Almanac (audio)` as
  the marker-suffix and `(audio)`-classification edition pairs,
  `Nightjar Post` as the comic↔ebook pair, and `Compass` / `The Compass
  of Broken Years Audiobook` as the subset-trap foil. `Cool Tower
  Defense`'s note gains the soundtrack-row use, since the committed
  `+ OST` variant classifies as android and the false-positive test
  needs a music row of the bare name.
- **`docs/BACKLOG.md`** — move the entry to **Done**, recording the
  measurement: that the population is 6 of 2,729 items, that fuzzy
  matching was rejected as *less* accurate rather than as too costly,
  and that the type exclusion rather than any threshold is what makes it
  precise.
- **`/api/merge`'s error text** — unchanged in behaviour, but its comment
  gains a pointer to `editions.py`, since "stay separate" is now half an
  answer.

## Explicitly not in scope

**Permitting cross-type merges.** The refusal is correct and stays. This
entry exists because the refusal is right, not to soften it.

**Any fuzzy or author-based matching.** Both were measured and both are
worse: fuzzy produced eight false positives to find one true pair, and
the author gate produced 70 same-author pairs of which 69 are different
works. Reopening either needs a title shape the exact key misses, and the
four probes above found none.

**A stored link table.** Considered and declined: with detection exact
and the population at six, a stored confirmation would mostly be a place
for staleness to live, and it would need reset-preservation semantics for
a fact that is free to recompute. Reopens if a genuine pair ever appears
that the key cannot see — that is the concrete trigger.

**Editions in the bundle preview.** Preview matches by `machine_name`,
and the two formats have different ones, so an edition link changes no
ownership verdict there. A separate question and a separate entry if it
turns out to matter.
