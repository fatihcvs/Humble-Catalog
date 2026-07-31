# Key Report Matching Cost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut `/api/keys` from ~2.4 s to ~0.36 s by sorting each match pool's tokens once instead of on every comparison, with byte-identical output.

**Architecture:** `fuzz.token_sort_ratio(a, b)` is `fuzz.ratio(sort(a), sort(b))` by definition. A new `titles.sort_tokens` plus a `game_match.prepare_pool` let a caller sort a pool once, outside its loop, and score with the much cheaper `fuzz.ratio`. The sorted string is a *scoring key only*: `classify_game` indexes back to the unsorted entry before consulting `sequel_mismatch`, which reads the trailing token and would silently stop firing on a sorted string.

**Tech Stack:** Python 3.12, rapidfuzz, pytest. No new dependencies.

## Global Constraints

- **Privacy standing order (`CLAUDE.md`).** Committed text uses only invented names from `docs/TEST-DATA.md` — never a real title from the owner's library. Aggregate counts (key totals, pool sizes) are fine; they appear in `BACKLOG.md` already.
- **Run `scripts/windows/verify.ps1` before every commit.** It runs pytest, then `check_no_data_tracked.py`, then `leak_check.py`. Never pipe `leak_check.py` — it is a commit gate and its exit code must be read directly.
- **No type annotations.** The package carries none; use `collections.namedtuple`, not `typing.NamedTuple`.
- **Matching policy does not change.** `GAME_OWNED = 92.0` and `GAME_POSSIBLE = 80.0` keep their values, the sequel rule stays, and the two callers keep treating the middle band in opposite directions.
- **`test_keys.py` and `test_bundle_preview.py` must pass unchanged.** If either needs editing, behaviour moved — stop and report rather than updating the test.
- Python is `.venv/Scripts/python`. The `pip.exe` shim is broken; use `python -m pip` if you ever need it.

---

### Task 1: `sort_tokens`

**Files:**
- Modify: `humble_catalog/titles.py` (append after `sequel_mismatch`, ends line 67)
- Test: `tests/test_titles.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `titles.sort_tokens(cleaned)` -> `str`. Takes an **already-cleaned** title (output of `clean_game_title`), returns its whitespace-separated tokens joined in sorted order.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_titles.py`:

```python
def test_sort_tokens_orders_a_cleaned_title():
    assert sort_tokens("widget quest") == "quest widget"
    assert sort_tokens("quest widget") == "quest widget"


def test_sort_tokens_moves_a_trailing_numeral_off_the_end():
    # Exactly the hazard game_match.classify_game guards against: the
    # numeral sequel_mismatch relies on finding last is no longer last.
    assert sort_tokens("widget quest ii") == "ii quest widget"


def test_sort_tokens_of_empty_is_empty():
    assert sort_tokens("") == ""
```

Add `sort_tokens` to the existing `from humble_catalog.titles import ...` line at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/Scripts/python -m pytest tests/test_titles.py -k sort_tokens -q
```

Expected: `ImportError: cannot import name 'sort_tokens'` (collection error).

- [ ] **Step 3: Write minimal implementation**

Append to `humble_catalog/titles.py`:

```python
def sort_tokens(cleaned):
    """A cleaned title's tokens in sorted order -- a scoring key.

    token_sort_ratio(a, b) is ratio(sort_tokens(a), sort_tokens(b)) by
    definition. So sorting a match pool ONCE here and scoring with the
    much cheaper fuzz.ratio computes the same number as scoring the
    unsorted pool with token_sort_ratio -- measured identical on every
    key in the catalog, and 8x faster, because the pool's half of that
    sorting was otherwise redone on all ~6.1M comparisons.

    ONLY ever a scoring key. It must not reach sequel_mismatch, which
    decides on the TRAILING token: sorted, "widget quest ii" becomes
    "ii quest widget", the numeral is no longer last, nothing is popped,
    and the rule that stops a game matching its own sequel silently stops
    firing. See game_match.classify_game, which indexes back to the
    unsorted title before asking.

    Takes an ALREADY-cleaned title. clean_game_title has collapsed runs
    of whitespace, which is what makes split()/join here reproduce
    exactly what token_sort_ratio does internally.
    """
    return " ".join(sorted(cleaned.split()))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/Scripts/python -m pytest tests/test_titles.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/titles.py tests/test_titles.py
git commit -m "feat(titles): add sort_tokens, the prepared scoring key"
```

---

### Task 2: `prepare_pool`, and `classify_game` scoring against it

**Files:**
- Modify: `humble_catalog/game_match.py` (whole file; currently 65 lines)
- Create: `tests/test_game_match.py`

**Interfaces:**
- Consumes: `titles.sort_tokens` from Task 1.
- Produces:
  - `game_match.Pool` — `collections.namedtuple("Pool", "keys entries")`. `keys` is a list of sorted-token strings; `entries` is the list of `(normalized_title, display_title)` pairs. **Index-parallel.**
  - `game_match.EMPTY` — `Pool([], [])`, for a store with no library rows.
  - `game_match.prepare_pool(owned)` -> `Pool`, where `owned` is `[(normalized_title, display_title)]`.
  - `game_match.classify_game(offered, pool)` -> `(verdict, match_or_None)`, unchanged return shape, but the second argument is now a `Pool` and **not** a list.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_game_match.py`:

```python
"""game_match's scoring identity, and the invariant that protects it.

This module had no direct test before: it was covered only through keys
and bundle_preview. The identity below is what the prepared-pool design
rests on, and nothing else in the suite would notice if a rapidfuzz
upgrade broke it.

Titles are the invented library from docs/TEST-DATA.md.
"""
import pytest
from rapidfuzz import fuzz, process

from humble_catalog.game_match import (
    GAME_OWNED, GAME_POSSIBLE, classify_game, prepare_pool)
from humble_catalog.titles import clean_game_title, sequel_mismatch

LIBRARY = [
    ("widget quest", "Widget Quest"),
    ("pixel harbor", "Pixel Harbor™"),
    ("neon drifter", "Neon Drifter"),
    ("grove of echoes", "Grove of Echoes"),
    ("starfall rally", "Starfall Rally"),
    ("cinder vale", "Cinder Vale"),
]

OFFERED = [
    "Widget Quest",                      # exact
    "Widget Quest: Definitive Edition",  # edition suffix over the base
    "Widget Quest II",                   # sequel -- must read as new
    "Quest Widget",                      # word order
    "Starfall Rally Turbo",              # the possible band
    "Lantern & Lockpick",                # owned nowhere
    "Pixel Harbor™",                # trademark symbol
    "Café of Broken Clocks",        # accented, and owned nowhere
    "",                                  # empty offered title
]


def _reference(offered, owned):
    """classify_game as it was before pools were prepared.

    token_sort_ratio against the unsorted pool -- the oracle the prepared
    path must agree with exactly.
    """
    key = clean_game_title(offered)
    if not key or not owned:
        return "new", None
    names = [normalized for normalized, _display in owned]
    hit = process.extractOne(key, names, scorer=fuzz.token_sort_ratio,
                             score_cutoff=GAME_POSSIBLE)
    if hit is None:
        return "new", None
    if sequel_mismatch(key, hit[0]):
        return "new", None
    return (("owned" if hit[1] >= GAME_OWNED else "possible"),
            {"offered": offered, "owned_title": owned[hit[2]][1],
             "score": round(hit[1] / 100, 2)})


@pytest.mark.parametrize("offered", OFFERED)
def test_prepared_scoring_matches_token_sort_ratio(offered):
    """The identity the whole design rests on, case by case."""
    assert classify_game(offered, prepare_pool(LIBRARY)) == \
        _reference(offered, LIBRARY)


def test_sequel_rule_survives_token_sorting():
    """Widget Quest II must not match an owned Widget Quest.

    The regression this pins: sort_tokens moves the numeral off the end
    ("ii quest widget"), and sequel_mismatch decides on the TRAILING
    token, so feeding it the sorted string makes the rule silently stop
    firing -- the sequel then scores 88.9 and reports as `possible`
    rather than `new`. classify_game indexes back to the unsorted entry
    before asking, which is what keeps this ("new", None).
    """
    assert classify_game("Widget Quest II", prepare_pool(LIBRARY)) == \
        ("new", None)


def test_match_reports_the_display_title_not_the_scoring_key():
    """owned_title is user-visible, so it comes from entries.

    Fails with "harbor pixel" if anyone reports extractOne's matched
    choice, which is the sorted key, instead of indexing back.
    """
    verdict, match = classify_game("Pixel Harbor™", prepare_pool(LIBRARY))
    assert verdict == "owned"
    assert match["owned_title"] == "Pixel Harbor™"


def test_an_empty_pool_makes_everything_new():
    assert classify_game("Widget Quest", prepare_pool([])) == ("new", None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python -m pytest tests/test_game_match.py -q
```

Expected: collection error, `ImportError: cannot import name 'prepare_pool'`.

- [ ] **Step 3: Write the implementation**

In `humble_catalog/game_match.py`, change the imports at the top:

```python
import collections

from rapidfuzz import fuzz, process

from humble_catalog.titles import (
    clean_game_title, sequel_mismatch, sort_tokens)
```

Then, immediately after the `GAME_POSSIBLE = 80.0` line, add:

```python
# A match pool with its scoring keys already computed.
#
#   keys     the sorted-token form of each entry's normalized title
#   entries  the (normalized_title, display_title) pairs, UNTOUCHED
#
# The two lists are INDEX-PARALLEL, and that is the whole mechanism:
# process.extractOne returns the index of its best choice, which is what
# carries a result from the sorted scoring key back to the real title.
#
# collections.namedtuple rather than typing.NamedTuple: the package
# carries no type annotations anywhere, and this is not the file to start.
Pool = collections.namedtuple("Pool", "keys entries")

# For a store the owner has imported that holds no games at all. Every
# offered title scores against nothing and comes back `new`.
EMPTY = Pool([], [])


def prepare_pool(owned):
    """[(normalized_title, display_title)] -> a Pool ready to score against.

    Call ONCE per pool, outside the loop over offered titles -- that is
    the entire point. Sorting each pool title's tokens here rather than
    inside the scorer took the key report's matching from 2.20s to 0.27s,
    because token_sort_ratio was re-sorting the same 3,306 pool titles
    for every one of 2,125 keys.
    """
    entries = list(owned)
    return Pool([sort_tokens(normalized) for normalized, _display in entries],
                entries)


def classify_game(offered, pool):
    """('owned'|'possible'|'new', best_match_or_None) for one offered title.

    `pool` is a Pool from prepare_pool -- one store's library, or several
    pooled, according to what the caller is asking. Deliberately NOT a
    plain list: accepting one would mean preparing it on every call,
    silently restoring the cost this design removes, and the caller would
    look correct while being slow. A TypeError here is the better failure.

    A sequel is forced to 'new' whatever it scores: "widget quest" and
    "widget quest ii" differ by one token, so every fuzzy scorer rates
    them near-identical, and they are the one near-identical pair that is
    definitely a different product.
    """
    key = clean_game_title(offered)
    if not key or not pool.keys:
        return "new", None
    hit = process.extractOne(sort_tokens(key), pool.keys, scorer=fuzz.ratio,
                             score_cutoff=GAME_POSSIBLE)
    if hit is None:
        return "new", None
    # Back to the UNSORTED title before anything else looks at it.
    # sequel_mismatch reads the trailing token, and hit[0] -- the sorted
    # scoring key -- no longer has the numeral there. Do not "simplify"
    # this to hit[0]: the sequel rule would stop firing silently, and
    # owned_title would print a bag of sorted words.
    normalized, display = pool.entries[hit[2]]
    if sequel_mismatch(key, normalized):
        return "new", None
    match = {"offered": offered, "owned_title": display,
             "score": round(hit[1] / 100, 2)}
    return ("owned" if hit[1] >= GAME_OWNED else "possible"), match
```

Also update the module docstring's closing line, which currently reads
"Which is why the cutoffs live here rather than in either caller." Append:

```
Both callers prepare their pools with prepare_pool and score against the
result. The sorted form that makes that fast is a scoring key and nothing
else -- see classify_game.
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/Scripts/python -m pytest tests/test_game_match.py -q
```

Expected: 12 passed (9 parametrized + 3).

- [ ] **Step 5: Confirm the callers are now broken, as expected**

```bash
.venv/Scripts/python -m pytest tests/test_keys.py tests/test_bundle_preview.py -q
```

Expected: FAILURES with `AttributeError: 'list' object has no attribute 'keys'`. This is correct — Tasks 3 and 4 fix the two callers. Do not commit yet.

- [ ] **Step 6: Commit (with the callers fixed in the next two tasks)**

Hold this commit until Task 4 so the tree is never committed red. Proceed directly to Task 3.

---

### Task 3: Convert `keys.report`

**Files:**
- Modify: `humble_catalog/keys.py:70-87` (`_store_pools`) and `:189,200-201` (`report`)

**Interfaces:**
- Consumes: `game_match.prepare_pool`, `game_match.EMPTY` from Task 2.
- Produces: `keys._store_pools(conn)` now returns `{store: Pool}` rather than `{store: [(normalized, display)]}`.

- [ ] **Step 1: Change `_store_pools` to return prepared pools**

In `humble_catalog/keys.py`, replace the `_store_pools` docstring's first line and the `return`:

```python
def _store_pools(conn):
    """{store: Pool}, deduped per store and ready to score against.

    One pool per store rather than one pooled list: see the module
    docstring. Ordered so the dedupe is deterministic rather than dependent
    on the order sqlite happens to return rows in -- the same reason
    build_worklist sorts.

    Prepared here rather than by the caller because this is the pool
    builder: sorting each title's tokens is part of building a pool that
    can be scored against, and doing it once per store instead of once per
    key is what makes the report fast.
    """
    pools = {}
    for row in conn.execute(
            "SELECT store, normalized_title, title FROM games "
            "WHERE normalized_title IS NOT NULL AND normalized_title != '' "
            "ORDER BY store, normalized_title"):
        pool = pools.setdefault(row["store"], [])
        if pool and pool[-1][0] == row["normalized_title"]:
            continue
        pool.append((row["normalized_title"], row["title"]))
    return {store: game_match.prepare_pool(entries)
            for store, entries in pools.items()}
```

- [ ] **Step 2: Change the one call site in `report`**

At `humble_catalog/keys.py:200-201`, replace:

```python
            verdict, match = game_match.classify_game(
                row["product"] or "", pools.get(store, []))
```

with:

```python
            verdict, match = game_match.classify_game(
                row["product"] or "", pools.get(store, game_match.EMPTY))
```

The default matters: a store can be in `libraries` (it has a `game_imports`
row) while holding no `games` rows, so `pools` would have no entry for it.
`EMPTY` classifies every title as `new`, which is the same answer the old
`[]` gave.

- [ ] **Step 3: Run the key tests**

```bash
.venv/Scripts/python -m pytest tests/test_keys.py -q
```

Expected: all pass, **unchanged**. If any test needed editing, stop and report — behaviour moved.

- [ ] **Step 4: Proceed to Task 4 without committing**

`tests/test_bundle_preview.py` is still red until Task 4.

---

### Task 4: Convert `bundle_preview.preview`

**Files:**
- Modify: `humble_catalog/bundle_preview.py:20` (import), `:220`, `:226`

**Interfaces:**
- Consumes: `game_match.prepare_pool` from Task 2.
- Produces: nothing new. `_owned_games` and `_keyed_games` keep their existing return shapes; only what `preview` does with them changes.

- [ ] **Step 1: Update the import**

At `humble_catalog/bundle_preview.py:20`, replace:

```python
from humble_catalog.game_match import classify_game
```

with:

```python
from humble_catalog.game_match import classify_game, prepare_pool
```

- [ ] **Step 2: Prepare both pools once, outside the loop**

At `humble_catalog/bundle_preview.py:220`, replace:

```python
    games = _owned_games(conn)
```

with:

```python
    games = prepare_pool(_owned_games(conn))
```

At `:226`, replace:

```python
    keyed_pool = [(normalized, display) for normalized, display, _t, _b in keyed]
```

with:

```python
    keyed_pool = prepare_pool(
        [(normalized, display) for normalized, display, _t, _b in keyed])
```

Both are already built once, above the per-tier loop, so no call moves.
This module is not slow -- it scores tens of items, not thousands -- and is
converted so that `game_match` owns the sorted-key invariant rather than
having it stated in one caller and not the other.

`keyed_extra` at `:228` is untouched: it is keyed on the display title, and
`classify_game` still returns the display title.

- [ ] **Step 3: Run both callers' tests**

```bash
.venv/Scripts/python -m pytest tests/test_bundle_preview.py tests/test_keys.py -q
```

Expected: all pass, **unchanged**.

- [ ] **Step 4: Run the whole suite and the privacy gate**

```bash
pwsh -File scripts/windows/verify.ps1
```

Expected: all tests pass, no tracked data file, leak check clean.

- [ ] **Step 5: Commit the whole change**

```bash
git add humble_catalog/game_match.py humble_catalog/keys.py humble_catalog/bundle_preview.py tests/test_game_match.py
git commit -m "perf(keys): sort each match pool's tokens once, not per comparison"
```

Use this message body:

```
token_sort_ratio re-splits and re-sorts BOTH sides' tokens on every
comparison, and the key report makes ~6.1M of them -- 2,125 steam keys
against a 3,306-title pool. The pool's half of that work is identical
every time.

token_sort_ratio(a, b) is ratio(sort(a), sort(b)) by definition, so
prepare_pool sorts each pool title once and classify_game scores with
fuzz.ratio. Measured 2.20s -> 0.27s, taking the whole report from ~2.4s
to ~0.36s, with zero verdict, title or score differences across every
checkable key in the catalog.

The sorted string is a scoring key ONLY. sequel_mismatch reads the
trailing token, so on "ii quest widget" the numeral is no longer last,
nothing is popped, and Widget Quest II reports as `possible` against an
owned Widget Quest instead of `new`. classify_game indexes back to the
unsorted entry first; test_sequel_rule_survives_token_sorting pins it.

bundle_preview is converted too although it is not slow, so the
invariant is owned by game_match rather than stated in one caller.
```

---

### Task 5: Measure the result, and update the two places that cite the old number

**Files:**
- Modify: `humble_catalog/webapp/static/keys.js:123-127`
- Modify: `docs/BACKLOG.md` (the Keys entry, lines 109-118)

**Interfaces:**
- Consumes: the shipped change from Task 4.
- Produces: nothing code-facing.

- [ ] **Step 1: Measure the shipped report**

```bash
.venv/Scripts/python -c "import time; from humble_catalog import db, keys; c=db.connect(); [print(f'{time.perf_counter()-t:.3f}s') for t in [time.perf_counter()] for _ in [keys.report(c)]]; c.close()"
```

Expected: ~0.36 s. Record the number you actually get — it goes in both
edits below. If it is above ~0.6 s, stop and report: something did not take
effect.

- [ ] **Step 2: Update the keys.js comment**

At `humble_catalog/webapp/static/keys.js:123-127`, replace:

```javascript
// Posts, then patches the row in place. Deliberately NOT a loadKeys()
// refetch: keys.report classifies every key against the store pools and
// measures ~2.5s on the author's catalog, which is not a button click.
// Same trade the statistics panel made -- touch the mutation call site
// rather than reload everything.
```

with (substituting your measured number):

```javascript
// Posts, then patches the row in place. Deliberately NOT a loadKeys()
// refetch: hiding changes one field on one row, so refetching and
// reclassifying every key to learn that is wasteful at the ~0.4s the
// report now costs, as it was at the ~2.5s it used to. Same trade the
// statistics panel made -- touch the mutation call site rather than
// reload everything.
```

The reasoning is what survives here, not the number: the patch-in-place is
right regardless of how fast the report gets.

- [ ] **Step 3: Close the backlog entry**

In `docs/BACKLOG.md`, delete the `**/api/keys takes ~2.5 s**` bullet from
the "Keys (identified 2026-07-31 while building hiding)" section under
**Open**. If that leaves the section empty, delete its heading too.

Add to the top of the **Done** list:

```markdown
- **`/api/keys` took ~2.5 s** —
  `docs/superpowers/specs/2026-07-31-key-report-matching-cost-design.md`.
  Now ~0.36 s. The entry proposed caching the store pools or memoizing
  the classification, and measurement rejected **both**: the pools cost
  6 ms of 2,400, and memoizing by title buys 19%, because the keys are
  nearly all distinct titles already — 1,840 of 2,125 steam keys. The
  obvious structural suspect, `classify_game` rebuilding its `names` list
  on every call, was worth 0.08 s of 2.20.
  The cost was that `token_sort_ratio` re-splits and re-sorts **both**
  sides' tokens on each of ~6.1M comparisons, and the pool's half of that
  is identical every time. `token_sort_ratio(a, b)` is
  `ratio(sort(a), sort(b))` by definition, so `prepare_pool` sorts each
  pool title once and `classify_game` scores with `fuzz.ratio`: the
  matching went 2.20 s → 0.27 s with **zero** verdict, title or score
  differences across every checkable key in the catalog. Not an
  approximation accepted for speed — the same function, evaluated in a
  better order.
  The sorted string is a scoring key and nothing else, which is the trap.
  `sequel_mismatch` decides on the **trailing** token, so on
  "ii quest widget" the numeral is no longer last, nothing is popped, and
  a sequel reports as `possible` against the game it is a sequel to
  rather than as `new` — failing open, silently, in the one direction
  this rule exists to prevent. `classify_game` indexes back through the
  index-parallel `Pool` to the unsorted entry before asking, and
  `test_game_match.py` is the module's first direct test precisely
  because that identity had nothing watching it.
  `bundle_preview` was converted too although it scores tens of items and
  was never slow, so the invariant is owned by `game_match` rather than
  stated in one caller and not the other.
  A report cache was designed as far as `PRAGMA data_version` and then
  declined, and the measurement is in the spec so the question reopens
  cheaply: four of the six writers of the tables the report reads are
  separate CLI processes — `import-games` being the one that actually
  flips a key to matched — so they cannot invalidate an in-process cache
  at all, and "remember to invalidate" was never the available rule.
  `data_version` costs 3.7 µs and catches every out-of-process commit
  including ones not yet written; its one blind spot is a connection's
  own commits, which is exactly hide/unhide. It was declined on
  proportion — it would save 0.35 s and buy back a surface on which a
  wrong answer can be served, where the presort has none.
```

Update the `Last updated:` line at the top of `docs/BACKLOG.md` to
`2026-07-31.` if it is not already.

- [ ] **Step 4: Verify**

```bash
pwsh -File scripts/windows/verify.ps1
```

Expected: tests pass, leak check clean.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/webapp/static/keys.js docs/BACKLOG.md
git commit -m "docs(keys): close the /api/keys cost entry, and requote the number"
```

---

## Self-Review

**Spec coverage**

| Spec section | Task |
|---|---|
| `sort_tokens` in `titles.py` | 1 |
| `Pool`, `prepare_pool`, `classify_game` signature | 2 |
| No plain-list fallback | 2 (docstring + `TypeError` by construction) |
| Index-back invariant + comment | 2 |
| Test 1 equivalence | 2 |
| Test 2 sequel survives sorting | 2 |
| Test 3 display title not scoring key | 2 |
| `keys.report` call site | 3 |
| `bundle_preview` two call sites | 4 |
| `test_keys` / `test_bundle_preview` unchanged | 3, 4 (explicit stop-and-report) |
| `keys.js` comment requoted | 5 |
| Backlog entry closed, cache measurement recorded | 5 |
| No new dependency | throughout — nothing added |

**Type consistency:** `Pool(keys, entries)` is defined in Task 2 and used
in Tasks 3 (`EMPTY` default) and 4 (`prepare_pool` results). `sort_tokens`
is defined in Task 1 and used in Task 2 only. `prepare_pool` takes
`[(normalized, display)]` in all three call sites — `_store_pools` builds
that shape, `_owned_games` returns it, and `keyed_pool` is comprehended
into it.

**Commit shape:** Tasks 2–4 are one commit because `game_match`'s signature
change breaks both callers; committing between them would leave the tree
red. Tasks 1 and 5 commit separately.
