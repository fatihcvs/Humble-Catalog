# Making the key report's matching cheap

Date: 2026-07-31
Status: designed

`/api/keys` takes ~2.4 s, which is why the Keys tab is visibly slow to
populate and why hiding a key patches its row in place rather than
refetching. This removes the cost without changing a single verdict.

## What the backlog guessed, and what is actually true

The entry proposed two shapes -- "caching the per-store pools or
memoizing the classification" -- and said the choice "wants measuring
before it wants fixing". Measured on the live catalog, **both are
wrong**:

| Phase | Time |
|---|---|
| `report()` total | 2.36-2.41 s |
| -- the classification loop | **2.29 s** |
| -- `_key_rows` incl. JSON parse | 0.018 s |
| -- `missing_keys` | 0.026 s |
| -- `_store_pools` | 0.006 s |
| -- `stale_hides`, `imported_stores` | ~0 s |

Caching the pools would save 6 ms of 2,400. And memoizing the
classification by title takes 2.20 s only to 1.79 s -- a 19% saving,
because the keys are nearly all *distinct* titles already: of 2,125
steam keys, 1,840 clean to different titles. Neither guess was close,
and both are recorded here so the question is not reopened on the same
two hunches.

Hoisting `classify_game`'s per-call `names` list comprehension out of
the loop -- the obvious structural suspect on reading the code -- was
also measured, and saves 0.08 s of 2.20. The list rebuild is not the
cost either.

The cost is the scorer. Work is dominated by one store: steam holds
3,306 distinct pool titles against 2,125 keys, versus gog 774/37 and
epic 689/17. That is ~6.1M title comparisons, and
`fuzz.token_sort_ratio` re-splits, re-sorts and re-joins the tokens of
**both** sides on every one of them. The pool's side of that work is
identical every time.

## The change

`token_sort_ratio(a, b)` is by definition `ratio(sort(a), sort(b))`.
So sort each pool title's tokens **once**, up front, and score with
plain `fuzz.ratio`.

Measured: the classification loop goes **2.20 s -> 0.27 s**, and
`report()` from ~2.4 s to ~0.36 s. Verified against the live catalog
across all 2,179 checkable keys: **0 verdict differences, 0
`owned_title` differences, 0 score differences.** Not "equivalent in
the cases we tried" -- byte-identical on every key the owner has.

Nothing about matching *policy* changes. `GAME_OWNED` stays 92.0,
`GAME_POSSIBLE` stays 80.0, the sequel rule stays, and the two callers
keep treating the band between the cutoffs in opposite directions. The
only thing that moves is *when* the sorting happens.

## Interface

In `titles.py`, beside `clean_game_title`, which is the only thing that
produces the strings it operates on:

```python
def sort_tokens(cleaned):
    """A cleaned title's tokens in sorted order: the scoring key."""
```

Exact rather than approximate because `clean_game_title` has already
collapsed runs of whitespace, so `" ".join(sorted(s.split()))`
reproduces what `token_sort_ratio` does internally.

In `game_match.py`:

```python
# keys:    sorted-token scoring keys
# entries: the (normalized, display) pairs, untouched
Pool = collections.namedtuple("Pool", "keys entries")

def prepare_pool(owned): ...           # [(normalized, display)] -> Pool
def classify_game(offered, pool): ...  # now takes a Pool
```

`collections.namedtuple`, not `typing.NamedTuple`: the package carries
no type annotations anywhere, and this is not the file to start.

`keys` and `entries` are **index-parallel**. That is the whole
mechanism: `process.extractOne` returns the index of its best choice,
and that index is what carries us back from the sorted scoring key to
the untouched original.

`classify_game` takes a `Pool` and only a `Pool`. It deliberately does
**not** accept a plain list as a fallback: a fallback would prepare the
pool on every call, silently restoring the exact cost this removes, and
it would do so invisibly -- the caller would look correct and be slow.
A `TypeError` at the call site is the better failure.

Three call sites, all preparing once outside their loop:

- `keys.report` -- one `Pool` per store, three in practice.
- `bundle_preview.summarize` -- two, for `games` and for `keyed_pool`.

`bundle_preview` scores only tens of items and is not slow today; it is
converted because leaving a second way into `classify_game` would mean
the invariant below is stated in one caller rather than owned by the
module.

## The invariant: the sorted form is a scoring key, nothing else

**A sorted string must never reach `sequel_mismatch`.**

`sequel_mismatch` decides on the **trailing** token -- it pops a
trailing numeral off each side and asks whether the remainder matches.
Sorted, *widget quest ii* becomes *ii quest widget*: the numeral is no
longer last, nothing is popped, and the rule that stops a game matching
its own sequel stops firing. It would fail open, quietly, and report
*Widget Quest II* as a game the owner already has.

So `classify_game` scores against `pool.keys`, then immediately indexes
back:

```python
normalized, display = pool.entries[hit[2]]
if sequel_mismatch(key, normalized):   # the UNSORTED form
    return "new", None
```

The same applies to `owned_title`, which is user-visible: it comes from
`entries`, so the report prints a real title and not a bag of sorted
words.

This is the hazard of the change and the thing most likely to be
"tidied" by someone who notices the two forms and collapses them. It
gets a comment saying so, and a test that fails if it happens.

## Testing

`game_match` has no direct test today -- it is covered only through its
two callers -- so this adds `tests/test_game_match.py`, using the
existing invented universe in `docs/TEST-DATA.md` (no new entries
needed).

1. **`test_prepared_scoring_matches_token_sort_ratio`** -- over a table
   of pairs covering word order, punctuation, accents, subtitles and
   edition suffixes, a prepared-pool `classify_game` returns the verdict,
   title and score that `token_sort_ratio` scoring returns. This is the
   identity the whole change rests on, and the thing a future rapidfuzz
   upgrade could break without any other test noticing.
2. **`test_sequel_rule_survives_token_sorting`** -- *Widget Quest II*
   offered against an owned *Widget Quest* still classifies `new`. Fails
   if the sorted form is what reaches `sequel_mismatch`.
3. **`test_match_reports_the_display_title_not_the_scoring_key`** --
   the returned `owned_title` is the display string. Fails if the
   index-back to `entries` is dropped.

`test_keys.py` and `test_bundle_preview.py` cover the call sites and
must pass **unchanged**. If either needs an edit, behaviour moved and
that is a reason to stop rather than to update the test.

## What is deliberately not done

**No caching of the report.** It was considered and declined, and the
measurement is recorded so the question can be reopened cheaply:

`report()` reads six tables, written from six places. Only two of them
-- the viewer's own hide and unhide routes -- run in the viewer's
process. `store.py` (`external_keys`, `bundles`), `import_games.py`
(`games`, `game_imports`) and `extract.py` (`raw_orders`) are separate
CLI commands in separate processes, and `import-games` is precisely the
one that flips a key from unredeemed to matched. They cannot invalidate
an in-process cache at all, however disciplined anyone is, so "remember
to invalidate" was never an available rule.

A DB-level probe would be needed instead. `PRAGMA data_version` costs
3.7 us and bumps on any commit from *another* connection -- verified --
which makes it a catch-all for all four out-of-process writers,
including ones nobody has written yet. Its one blind spot is documented
and exact: a connection's own commits do not bump its own counter, and
that is precisely hide/unhide. Adding
`SELECT COUNT(*), MAX(hidden_at) FROM hidden_keys` covers those, for
7.7 us total.

That is a workable design. It is declined anyway, on proportion: after
this change the report is 0.36 s, so a cache saves 0.35 s and buys back
a surface on which a wrong answer can be served -- where the presort is
an algebraic identity that cannot serve one. The residual risk it
carries is a future write route added to `webapp/__init__.py` touching
something other than `hidden_keys`, which is invisible from where it
would be introduced. If 0.36 s ever proves annoying, this paragraph is
the head start.

**`keys.js`'s patch-in-place stays.** Its comment cites the 2.5 s as
its reason for not refetching after a hide. The reasoning is sound
regardless of the number -- a refetch to change one field is wasteful
at 0.36 s too -- but the number becomes wrong, so the comment is
updated rather than the code.

## Expected result

`/api/keys` and the `keys` CLI: ~2.4 s -> ~0.36 s, identical output.
The `/api/keys` backlog entry closes.
