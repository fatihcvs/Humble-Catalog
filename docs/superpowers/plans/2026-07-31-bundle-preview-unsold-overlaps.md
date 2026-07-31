# Bundle Preview Unsold Overlaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `bundle_preview` reporting a possible overlap for an item no tier sells, and stop such an item bypassing the book/game routing on its way there.

**Architecture:** `_overlaps` is the only reader that *iterates* `tier_item_data`; every other consumer looks up a name that came from `tier_display_data`. `preview`'s tier walk already decides both questions the exclusion sets encode — owned or not, book or game — so it collects the overlap candidates as it goes and `_overlaps` takes only that dict. Owned items, games, and unsold items all become unrepresentable rather than filtered.

**Tech Stack:** Python 3.12, rapidfuzz, pytest. No new dependencies, no schema change, no migration.

**Design:** `docs/superpowers/specs/2026-07-31-bundle-preview-unsold-overlaps-design.md`

## Global Constraints

- **Privacy standing order (`CLAUDE.md`).** Committed text uses only invented names from `docs/TEST-DATA.md` — never a real title from the owner's library. The one new name is `Shadow Hound Vol 1 Bonus Art Pack`, added to that file in Task 3.
- **Run `scripts/windows/verify.ps1` before every commit.** It runs pytest, then `check_no_data_tracked.py`, then `leak_check.py`. Never pipe `leak_check.py` — it is a commit gate and its exit code must be read directly.
- **No type annotations.** The package carries none.
- **`tests/fixtures/bundle_data.json` and `game_bundle_data.json` are not edited.** They are anonymized captures and the existing tests read their counts directly. Tests mutate a parsed copy.
- **Every existing test in `tests/test_bundle_preview.py` must pass unchanged.** If one needs editing, behaviour moved further than intended — stop and report rather than updating the test.
- **No count may change.** `total`, `owned`, `possible`, `new`, `adds`, `keyed_items`, `game_matching`, `libraries` and `unimported_stores` are all derived from the sold set already. Task 1 pins this.
- Python is `.venv/Scripts/python`. The `pip.exe` shim is broken; use `python -m pip` if you ever need it.

---

### Task 1: The failing tests

**Files:**
- Modify: `tests/test_bundle_preview.py` (append after `test_overlap_threshold_is_local_and_not_borrowed_from_matching`, ends line 253)

**Interfaces:**
- Consumes: `bundle_preview.preview`, the existing `_conn` and `_bundle` helpers.
- Produces: nothing importable.

- [ ] **Step 1: Write the failing tests**

Add a helper and three tests. The helper mutates a parsed copy of the book fixture, so the committed JSON is untouched:

```python
def _bundle_with_unsold(entry, machine_name="shadowhound_bonus_examplecomics"):
    """The book fixture plus one tier_item_data entry no tier sells.

    Real bundles carry these -- a bonus wallpaper, an art pack, an item
    pulled from a tier after the page data was assembled. The game
    fixture has one already ('bonuswallpaper_examplegames').
    """
    bundle = _bundle()
    assert machine_name not in bundle["tier_item_data"]
    bundle["tier_item_data"][machine_name] = entry
    sold = {name for display in bundle["tier_display_data"].values()
            for name in display["tier_item_machine_names"]}
    assert machine_name not in sold          # the premise of every test below
    return bundle


# Scores 100.0 against the owned 'Shadow Hound Vol 1': token_set_ratio
# returns a perfect score when one side's tokens are wholly contained in
# the other's. Deliberate -- it outscores both genuine overlaps, so a
# regression appears at the HEAD of the list rather than buried in it.
_BONUS_BOOK = {"human_name": "Shadow Hound Vol 1 Bonus Art Pack",
               "platforms_and_oses": {}}


def test_an_item_no_tier_sells_is_never_an_overlap(tmp_path):
    # tier_item_data is a metadata dict, not the item list. An entry no
    # tier sells cannot be bought by buying this bundle, so hinting that
    # part of it may already be owned answers a question nobody asked.
    conn = _conn(tmp_path)
    try:
        report = bundle_preview.preview(conn, _bundle_with_unsold(_BONUS_BOOK))
    finally:
        conn.close()
    assert all("Bonus Art Pack" not in o["offered"] for o in report["overlaps"])
    assert [o["offered"] for o in report["overlaps"]] == [
        "Shadow Hound Vol. 1-6", "Moonfall Vol. 1-3"]


def test_an_item_no_tier_sells_does_not_change_any_count(tmp_path):
    # The counts were already right -- they derive from tier_display_data.
    # Pins that the fix stayed on the overlap list, which is the way this
    # change could do damage.
    conn = _conn(tmp_path)
    try:
        report = bundle_preview.preview(conn, _bundle_with_unsold(_BONUS_BOOK))
    finally:
        conn.close()
    counted = [(t["total"], t["owned"], t["new"]) for t in report["tiers"]]
    assert counted == [(6, 2, 4), (3, 2, 1), (1, 1, 0)]
    assert report["game_matching"] is False


def test_an_unsold_game_entry_is_not_matched_against_books(tmp_path):
    # The cross-media half, and it fails for a different reason than the
    # first test: game_names is accumulated by the tier walk, so a
    # phantom is never in it and the `owned | game_names` exclusion could
    # not name it. A game scored against the book catalog is exactly what
    # preview's call-site comment says was fixed.
    entry = {"human_name": "Shadow Hound Vol 1 Bonus Art Pack",
             "platforms_and_oses": {"game": {"steam": ["windows"]}}}
    conn = _conn(tmp_path)
    try:
        report = bundle_preview.preview(conn, _bundle_with_unsold(entry))
    finally:
        conn.close()
    assert all("Bonus Art Pack" not in o["offered"] for o in report["overlaps"])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python -m pytest tests/test_bundle_preview.py -k unsold -q
```

Expected: `test_an_item_no_tier_sells_is_never_an_overlap` and
`test_an_unsold_game_entry_is_not_matched_against_books` **fail** — the
phantom appears in `overlaps`, at the head of the list in the first case.
`test_an_item_no_tier_sells_does_not_change_any_count` **passes** already;
it is a regression guard, not a bug reproduction, and the plan expects it
green from the start.

Confirm the first failure names `Shadow Hound Vol 1 Bonus Art Pack` as the
first element of the actual list. If it fails for any other reason, stop.

---

### Task 2: Collect candidates in the walk

**Files:**
- Modify: `humble_catalog/bundle_preview.py` (`_overlaps`, lines 82–111; `preview`, lines 209–322)

**Interfaces:**
- Consumes: nothing new.
- Produces: `_overlaps(conn, candidates)` — signature narrows from `(conn, items, owned)`. `candidates` is `{machine_name: offered_title}`.

- [ ] **Step 1: Narrow `_overlaps`**

Replace the signature, docstring and loop head. The body from
`process.extractOne` down is unchanged:

```python
def _overlaps(conn, candidates):
    """Offered titles that look like partial matches for owned rows.

    `candidates` is {machine_name: offered_title} for the items a tier
    actually sells that matched no owned machine_name and took the book
    path. preview's tier walk builds it, having already decided both of
    those questions -- so an owned item, a game, and an item described in
    tier_item_data but sold by no tier are all unrepresentable here
    rather than filtered out. The exclusions used to be two sets passed
    in and re-applied; both were keyed to the sold set, so neither could
    name an entry the sold set never mentioned.

    Titles are compared through clean_title, the same normalization
    enrich matches on, so ": A Novel" and edition suffixes do not depress
    a score on either side.
    """
    rows = conn.execute("SELECT id, name FROM items").fetchall()
    if not rows:
        return []
    names = [clean_title(row["name"])[0] for row in rows]
    found = []
    for offered in candidates.values():
        hit = process.extractOne(
            clean_title(offered)[0], names, scorer=fuzz.token_set_ratio,
            processor=str.lower, score_cutoff=OVERLAP)
        if hit is None:
            continue
        row = rows[hit[2]]
        found.append({"offered": offered, "item_id": row["id"],
                      "item_name": row["name"], "score": round(hit[1] / 100, 2)})
    found.sort(key=lambda o: o["score"], reverse=True)
    return found
```

The `if machine_name in owned: continue` guard and the
`item.get("human_name") or machine_name` fallback both move to the
caller.

- [ ] **Step 2: Collect in the tier walk**

In `preview`, replace the `game_names` declaration (line 238):

```python
    game_names = set()   # machine_names routed to title matching
```

with:

```python
    # Sold, unowned, book-path items, keyed by machine_name so the same
    # name in two cumulative tiers is one candidate. A dict rather than a
    # set: _overlaps sorts by score and Python's sort is stable, so tie
    # order is input order -- and set iteration order of strings varies
    # between processes under hash randomization. Same trap the harvest
    # worklist sort documents.
    candidates = {}
    game_names = set()   # machine_names routed to title matching
```

Then in the book branch of the per-name loop (lines 256–258), collect:

```python
            if not delivery_stores(item):
                new_names.append(name)
                # Guarded on membership, not on `item`: a sold name that
                # tier_item_data does not describe is skipped, which is
                # what happens today -- it is not a key of items, so the
                # old iteration never reached it. The tier counts above
                # fall back to the bare machine_name and are right to;
                # counting must be exhaustive. Hinting must not be, and a
                # machine_name is not a title.
                if name in items:
                    candidates[name] = item.get("human_name") or name
                continue
```

Finally, at the call site (line 321), replace:

```python
        # Game items are excluded from the book overlap pass. Without this
        # a game title fuzzy-matches the book catalog and invents an
        # overlap across media -- observed on a live bundle.
        "overlaps": _overlaps(conn, items, owned | game_names),
```

with:

```python
        # Collected by the tier walk above, which is the only thing that
        # knows what this bundle actually sells. Games are absent because
        # they took the other branch, owned items because they never
        # reached it, and an item no tier sells because it was never
        # walked -- all three by construction rather than by filtering.
        "overlaps": _overlaps(conn, candidates),
```

`game_names` keeps its remaining use: `"game_matching": bool(game_names)`.

- [ ] **Step 3: Run the new tests**

```bash
.venv/Scripts/python -m pytest tests/test_bundle_preview.py -k unsold -q
```

Expected: 3 passed.

- [ ] **Step 4: Run the whole preview suite unchanged**

```bash
.venv/Scripts/python -m pytest tests/test_bundle_preview.py -q
```

Expected: all pass, with no edit to any pre-existing test. In particular
`test_an_omnibus_matching_an_owned_volume_becomes_an_overlap`,
`test_overlaps_carry_the_item_id_so_the_viewer_can_link_to_the_row`,
`test_an_already_owned_item_is_never_also_an_overlap` and
`test_game_titles_never_produce_book_overlap_hints` must pass untouched —
they are the behaviour this change must preserve.

- [ ] **Step 5: Full verify**

```bash
powershell -File scripts/windows/verify.ps1
```

Expected: full suite green, both privacy checks pass.

---

### Task 3: Documentation

**Files:**
- Modify: `docs/TEST-DATA.md` (*Comics / manga* table)
- Modify: `docs/BACKLOG.md` (move the entry to **Done**)

- [ ] **Step 1: Record the invented name**

Add to the *Comics / manga* table, after the `Shadow Hound Vol. 1-6` row:

```
| Shadow Hound Vol 1 Bonus Art Pack | — | Example Comics | described in a bundle's `tier_item_data` but sold by no tier; bundle-preview phantom-item tests |
```

- [ ] **Step 2: Close the backlog entry**

Remove "**`_overlaps` hints about items no tier sells**" from **Open** →
*Bundle preview*, and add it to **Done** at the top of that list. The
entry must record, in the register the other Done entries use:

- What the bug was: two notions of "the bundle's items", `_overlaps` the
  only iterating reader of the metadata one.
- The half the open entry did not know: `game_names` is built by the
  walk, so a phantom escapes the book/game routing entirely and a
  phantom *game* is scored against the book catalog — with
  `game_matching` false, so the hint prints without its APPROXIMATE
  warning.
- That no count was ever wrong, and a test now pins that.
- Collect-versus-filter, and why: the filter would have left three
  exclusion rules where the caller already had the answer, which is the
  arrangement that produced the bug.
- That `tier_item_data` now has no iterating reader at all.

Keep the three sibling *Bundle preview* entries — volume-range
resolution, past/expired bundles, GOG/Epic OAuth — under **Open**,
untouched.

- [ ] **Step 3: Verify and commit**

```bash
powershell -File scripts/windows/verify.ps1
```

`leak_check.py` must be run directly, never piped.

---

## Verification

- `tests/test_bundle_preview.py` passes in full, with three new tests and
  no pre-existing test edited.
- The book fixture's overlap list is unchanged in content and order.
- `scripts/windows/verify.ps1` is green, both privacy checks included.
