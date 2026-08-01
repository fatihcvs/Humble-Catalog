# Volume-aware overlaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report what the catalog holds of an offered title's *series* — "you own Vol. 1-6", "you own 1 of 6", or "ALREADY OWNED" — instead of showing a bare fuzzy score under a heading that claims partial ownership.

**Architecture:** A `parse_series` function in `titles.py` turns an already-cleaned title into a series identity (key, display, number, kind, span). A new `series.py` builds the owned-volume index from `items`, classifies an offered title against it, and collapses volume runs for display. `bundle_preview.preview` calls it, adds a `series` field, and removes series hits from `candidates` before `_overlaps` sees them. The CLI and the viewer each gain one block.

**Tech Stack:** Python 3.12, sqlite3, pytest, rapidfuzz (not used by this feature), vanilla JS tested through `tests/js_harness.py` (Node).

**Spec:** `docs/superpowers/specs/2026-08-01-volume-aware-overlaps-design.md`

**Branch:** `feat/volume-aware-overlaps`, already forked from `main`.

## Global Constraints

- **`clean_title` must not change.** `enrich.py:156` consumes its `num_hint`; widening it alters enrichment matching catalog-wide. A test pins this.
- **No fuzzy matching and no threshold in this feature.** Exact keys with punctuation stripped, measured sufficient (172 bases → 169, merging only genuine drift).
- **No persistence.** Read-only, like the rest of `bundle_preview`. Nothing for `reset` to preserve.
- **No sanity cap on a parsed volume number.** Largest real volume is 44; a cap would be a branch only a synthetic test could reach.
- **Invented names only**, drawn from `docs/TEST-DATA.md`. Add new rows there rather than inventing ad hoc.
- **Run `.venv/Scripts/python scripts/leak_check.py` before every commit, unpiped.** It matches substrings and piping it breaks the check.
- Test command prefix throughout: `.venv/Scripts/python -m pytest`.

---

### Task 1: `parse_series` in `titles.py`

**Files:**
- Modify: `humble_catalog/titles.py` (append; `clean_title` untouched)
- Test: `tests/test_titles.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `Series = NamedTuple("Series", key: str|None, display: str|None, number: int|None, kind: str|None, span: tuple[int,int]|None)`
  - `NO_SERIES: Series` — all fields `None`
  - `series_key(text: str) -> str`
  - `parse_series(cleaned: str, number_hint: float|None = None) -> Series`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_titles.py`:

```python
def test_a_bare_volume_marker_parses_to_its_number():
    found = titles.parse_series("Shadow Hound Vol. 22")
    assert (found.display, found.number, found.kind) == ("Shadow Hound", 22, "volume")


def test_every_volume_spelling_parses():
    for raw in ("Shadow Hound Vol 3", "Shadow Hound Vol. 3",
                "Shadow Hound Volume 3", "Shadow Hound Book 3"):
        assert titles.parse_series(raw).number == 3, raw


def test_a_range_is_a_collection_and_never_its_lower_bound():
    # A bare-volume pattern reads this as volume 1, which would match an
    # owned Vol. 1 and report the whole collection as already owned --
    # discouraging the purchase of five books not held.
    found = titles.parse_series("Shadow Hound Vol. 1-6")
    assert found.kind == "collection"
    assert found.number is None
    assert found.span == (1, 6)
    assert found.display == "Shadow Hound"


def test_a_collection_word_is_a_collection_with_no_span():
    # No title carries an omnibus's volume count, so there is no
    # denominator to state and none is invented.
    found = titles.parse_series("Shadow Hound Omnibus")
    assert (found.kind, found.span, found.display) == ("collection", None, "Shadow Hound")


def test_a_marker_followed_by_a_subtitle_still_parses():
    # 113 of 679 volume markers in the catalog are followed by ": Subtitle".
    # Anchoring to end-of-string alone would drop a sixth of them.
    found = titles.parse_series("Shadow Hound Vol. 1: Origins")
    assert (found.display, found.number) == ("Shadow Hound", 1)


def test_the_series_key_ignores_punctuation_so_spellings_merge():
    # Measured: one series was split three ways by a trailing period on an
    # initialism, and another by a space where a sibling used a hyphen.
    keys = {titles.parse_series(raw).key for raw in (
        "S.H.A.D.O.W Vol. 1", "S.H.A.D.O.W. Vol. 2", "S.H.A.D.O.W.: Vol. 3",
    )}
    assert len(keys) == 1
    assert titles.parse_series("Shadow-Hound Quest Vol. 1").key == \
           titles.parse_series("Shadow-Hound-Quest Vol. 2").key


def test_titles_differing_by_more_than_punctuation_stay_apart():
    # The one near-identical pair the measurement did NOT merge. Its two
    # halves hold identical volume sets, which is what says they are two
    # series rather than one spelling drift.
    assert titles.parse_series("Moonfall Vol. 1").key != \
           titles.parse_series("Moonfalls Vol. 1").key


def test_an_issue_range_in_parentheses_is_not_a_volume_range():
    # The premise this whole entry was built on. clean_title strips the
    # parenthetical first, so the issue range never reaches parse_series --
    # Vol. 22 COLLECTS issues 127-132; it is one volume, not six.
    cleaned, hint = titles.clean_title("Shadow Hound Vol. 22 (#127-132)")
    found = titles.parse_series(cleaned, hint)
    assert (found.kind, found.number, found.span) == ("volume", 22, None)


def test_clean_titles_parenthesized_hint_is_accepted_not_rediscovered():
    cleaned, hint = titles.clean_title("Wings of Autumn Dusk (Book 1)")
    found = titles.parse_series(cleaned, hint)
    assert (found.display, found.number, found.kind) == \
           ("Wings of Autumn Dusk", 1, "volume")


def test_a_title_with_no_marker_has_no_series():
    assert titles.parse_series("Unrelated Book") == titles.NO_SERIES


def test_a_marker_that_is_the_whole_title_names_no_series():
    assert titles.parse_series("Omnibus") == titles.NO_SERIES


def test_clean_title_hint_still_fires_only_on_the_parenthesized_spelling():
    # Pins the deliberate NON-widening. enrich.py consumes this hint for
    # matching, so teaching it the bare spelling would silently change
    # enrichment across the catalog. That is its own backlog entry.
    assert titles.clean_title("Wings of Autumn Dusk (Book 1)")[1] == 1.0
    assert titles.clean_title("Shadow Hound Vol. 3")[1] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_titles.py -k series -v`
Expected: FAIL — `AttributeError: module 'humble_catalog.titles' has no attribute 'parse_series'`

- [ ] **Step 3: Write the implementation**

Append to `humble_catalog/titles.py`:

```python
from typing import NamedTuple


class Series(NamedTuple):
    """A title's series identity.

    `key` is punctuation-insensitive and used for matching; `display` is
    the same slice as written and used for output. Two fields rather than
    one because the key must discard punctuation to match -- three
    spellings of one initialism share a key -- and the display must keep
    it to read.
    """
    key: str | None
    display: str | None
    number: int | None
    kind: str | None          # "volume" | "collection" | None
    span: tuple | None        # (lo, hi) for an explicit range only


NO_SERIES = Series(None, None, None, None, None)

_DASH = r"(?:-|–|—|to)"
# A marker may end the title or be followed by ": Subtitle" -- 113 of 679
# volume markers in the catalog are, so anchoring to end-of-string alone
# would drop a sixth of them. The subtitle is discarded, which correctly
# files "Vol. 1: Origins" and "Vol. 1: Endings" as the same volume.
_TAIL = r"\s*(?::.*)?$"
_VOL_WORD = r"\b(?:vol|volume|book)\b"
# Tried FIRST, and that order is the whole point: a bare-volume pattern
# reads "Vol. 1-6" as volume 1, which matches an owned Vol. 1 and reports
# a six-volume collection as already owned. A range names a product.
_VOL_RANGE = re.compile(
    r"[\s,:]*" + _VOL_WORD + r"s?\.?\s*#?(\d+)\s*" + _DASH + r"\s*#?(\d+)" + _TAIL,
    re.I)
_VOL_ONE = re.compile(r"[\s,:]*" + _VOL_WORD + r"\.?\s*#?(\d+)" + _TAIL, re.I)
_COLLECTION = re.compile(
    r"[\s,:]*\b(?:omnibus|compendium|anthology|box(?:ed)?\s+set|"
    r"complete\s+(?:collection|series)|collection)\b" + _TAIL, re.I)


def series_key(text):
    """A series name reduced to a match key: no punctuation, lowercase.

    Reuses the character classes clean_game_title uses. Measured
    2026-08-01: exact bases fragment a series on punctuation alone -- one
    was split three ways by a trailing period on an initialism, another
    by a space where a sibling used a hyphen. Stripping punctuation takes
    172 bases to 169, merging exactly those and nothing else. The one
    near-identical pair that survives holds identical volume sets, which
    is the evidence that it is two series rather than one.
    """
    return _SPACES.sub(" ", _NON_WORD.sub(" ", text)).strip().lower()


def parse_series(cleaned, number_hint=None):
    """The series identity of an ALREADY-CLEANED title.

    Takes clean_title's output. Trailing parentheticals are gone by then,
    so the issue ranges that look like volume ranges -- "Vol. 22
    (#127-132)" -- never reach these patterns. That matters: measured
    across 2,729 items, every range in the catalog is an issue range, 8
    of 11 of them annotating a single volume. Volume 22 COLLECTS issues
    127-132; it is one volume, not six.

    `number_hint` is clean_title's own series number, which understands
    only the parenthesized "(Book 1)" spelling and fires on 3 of 2,729
    items. It is accepted here rather than widened: enrich.py consumes it
    for matching, so changing what it fires on changes enrichment
    catalog-wide. See the backlog.
    """
    t = (cleaned or "").strip()
    for pattern in (_VOL_RANGE, _VOL_ONE, _COLLECTION):
        m = pattern.search(t)
        if m is None:
            continue
        display = t[:m.start()].strip(" ,:-")
        if not display:
            break            # the marker IS the title; no series to name
        if pattern is _VOL_RANGE:
            lo, hi = (int(g) for g in m.groups())
            return Series(series_key(display), display, None, "collection",
                          (lo, hi) if hi >= lo else (hi, lo))
        if pattern is _VOL_ONE:
            return Series(series_key(display), display, int(m.group(1)),
                          "volume", None)
        return Series(series_key(display), display, None, "collection", None)
    if number_hint is not None and t:
        return Series(series_key(t), t, int(number_hint), "volume", None)
    return NO_SERIES
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_titles.py -v`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Leak-check and commit**

```bash
.venv/Scripts/python scripts/leak_check.py
git add humble_catalog/titles.py tests/test_titles.py
git commit -m "feat(titles): parse a title's series identity, ranges included"
```

---

### Task 2: `series.py` — the owned index and the three outcomes

**Files:**
- Create: `humble_catalog/series.py`
- Test: `tests/test_series.py`

**Interfaces:**
- Consumes: `titles.parse_series`, `titles.clean_title`, `titles.Series`, `titles.NO_SERIES` from Task 1.
- Produces:
  - `owned_volumes(conn) -> dict[str, set[int]]`
  - `collapse(numbers: Iterable[int]) -> str`
  - `describe(offered: str, index: dict) -> dict | None`
  - `sort_key(hit: dict) -> tuple`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_series.py`:

```python
import pytest

from humble_catalog import db, series


def _conn(tmp_path, *names):
    conn = db.connect(tmp_path / "catalog.db")
    for i, name in enumerate(names):
        conn.execute("INSERT INTO items (machine_name, name, type) "
                     "VALUES (?, ?, 'comic')", (f"mn{i}", name))
    conn.commit()
    return conn


def _index(tmp_path, *names):
    conn = _conn(tmp_path, *names)
    try:
        return series.owned_volumes(conn)
    finally:
        conn.close()


def test_collapse_renders_a_contiguous_run_as_a_range():
    assert series.collapse([1, 2, 3, 4, 5, 6]) == "1-6"


def test_collapse_renders_a_gap_honestly():
    assert series.collapse([1, 2, 3, 5, 6]) == "1-3, 5-6"


def test_collapse_renders_a_lone_volume_as_a_bare_number():
    assert series.collapse([3]) == "3"


def test_owned_volumes_indexes_a_series_by_key(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1", "Shadow Hound Vol. 2")
    assert index == {"shadow hound": {1, 2}}


def test_owned_volumes_merges_spellings_that_differ_only_in_punctuation(tmp_path):
    index = _index(tmp_path, "MOONFALL, Vol. 1", "Moonfall Vol. 2")
    assert index == {"moonfall": {1, 2}}


def test_owned_volumes_ignores_items_with_no_marker(tmp_path):
    assert _index(tmp_path, "Unrelated Book") == {}


def test_an_offered_volume_you_do_not_hold_reports_the_run(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1", "Shadow Hound Vol. 2")
    hit = series.describe("Shadow Hound Vol. 7", index)
    assert hit["kind"] == "volume"
    assert hit["already_owned"] is False
    assert hit["owned_display"] == "Vol. 1-2"
    assert hit["series_name"] == "Shadow Hound"


def test_an_offered_volume_you_already_hold_is_flagged_as_a_re_buy(tmp_path):
    # It matched no machine_name yet is a volume already held: a re-issue
    # or another edition of the same book. The mistake this report exists
    # to prevent, and today it prints as a bare 0.94.
    index = _index(tmp_path, "Shadow Hound Vol. 1", "Shadow Hound Vol. 2")
    assert series.describe("Shadow Hound Vol. 2", index)["already_owned"] is True


def test_an_offered_collection_reports_how_many_volumes_are_held(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1", "Shadow Hound Vol. 2")
    hit = series.describe("Shadow Hound Omnibus", index)
    assert hit["kind"] == "collection"
    assert hit["span"] is None            # no denominator to state
    assert hit["owned"] == [1, 2]


def test_an_offered_range_carries_the_denominator_it_states(tmp_path):
    index = _index(tmp_path, "Shadow Hound Vol. 1")
    hit = series.describe("Shadow Hound Vol. 1-6", index)
    assert hit["kind"] == "collection"
    assert hit["span"] == [1, 6]
    assert hit["already_owned"] is False   # never read as its lower bound


def test_a_series_the_catalog_does_not_hold_is_not_described(tmp_path):
    assert series.describe("Moonfall Vol. 3", _index(tmp_path, "Shadow Hound Vol. 1")) is None


def test_a_title_with_no_marker_is_not_described(tmp_path):
    assert series.describe("Unrelated Book", _index(tmp_path, "Shadow Hound Vol. 1")) is None


def test_sort_puts_re_buys_first_then_collections_then_continuations():
    hits = [{"already_owned": False, "kind": "volume", "offered": "b"},
            {"already_owned": False, "kind": "collection", "offered": "c"},
            {"already_owned": True, "kind": "volume", "offered": "a"}]
    assert [h["offered"] for h in sorted(hits, key=series.sort_key)] == ["a", "c", "b"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_series.py -v`
Expected: FAIL — `ImportError: cannot import name 'series' from 'humble_catalog'`

- [ ] **Step 3: Write the implementation**

Create `humble_catalog/series.py`:

```python
"""Which volumes of a series the catalog holds, and what an offered title
means against them.

Live, with no stored state -- mirroring dedupe.find_groups and edition
linking. Nothing to migrate, nothing for `reset` to preserve, and a
rebuilt catalog has its answers back for free.

No fuzzy matching and no threshold appears anywhere in this module, which
is a measured result rather than a simplification. Exact keys with
punctuation stripped merge every genuine spelling drift in the catalog
(172 bases to 169) and merge nothing else; the one near-identical pair
that survives holds identical volume sets, which is what says it is two
series. Same conclusion the edition-linking design reached, and for the
same reason: a fuzzy score here would admit pairs that exact keys prove
are distinct.
"""
from humble_catalog.titles import clean_title, parse_series


def owned_volumes(conn):
    """{series_key: {volume numbers}} across every item in the catalog.

    No type filter. The volume marker was measured on comic (672), ebook
    (12) and audiobook (3) rows and on ZERO android or music rows, so a
    filter would be a branch no test could exercise against real data.
    """
    index = {}
    for row in conn.execute("SELECT name FROM items"):
        cleaned, hint = clean_title(row[0])
        found = parse_series(cleaned, hint)
        if found.kind == "volume" and found.number is not None:
            index.setdefault(found.key, set()).add(found.number)
    return index


def collapse(numbers):
    """[1, 2, 3, 5, 6] -> "1-3, 5-6".

    A gap is rendered rather than smoothed over: only one series in the
    catalog has one today, and reporting a run you do not actually hold
    unbroken would be the same class of overclaim this whole feature
    exists to remove.
    """
    runs = []
    for n in sorted(set(numbers)):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in runs)


def describe(offered, index):
    """The series line for one offered title, or None if there is none.

    Three outcomes, and the third is the valuable one. An offered volume
    that matched no machine_name but IS a volume already held is a
    probable re-buy -- the same book under a different Humble id, a
    re-issue, or another edition. That is precisely the mistake the
    preview exists to prevent, and it costs one `in` test against a set
    this function has already built.
    """
    cleaned, hint = clean_title(offered)
    found = parse_series(cleaned, hint)
    if found.key is None:
        return None
    owned = index.get(found.key)
    if not owned:
        return None
    return {
        "offered": offered,
        "series_name": found.display,
        "kind": found.kind,
        "offered_volume": found.number,
        # Only an explicit range states its own size. An omnibus word says
        # nothing about how many volumes it collects, so no denominator is
        # invented for it.
        "span": list(found.span) if found.span else None,
        "owned": sorted(owned),
        "owned_display": "Vol. " + collapse(owned),
        "already_owned": found.number is not None and found.number in owned,
    }


def sort_key(hit):
    """Re-buys first, then collections, then continuations; ties by title.

    A re-buy is the one line that should stop a purchase, so it must not
    sort below a merely informative one.
    """
    rank = 0 if hit["already_owned"] else 1 if hit["kind"] == "collection" else 2
    return (rank, hit["offered"].lower())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_series.py -v`
Expected: PASS, 14 tests.

- [ ] **Step 5: Leak-check and commit**

```bash
.venv/Scripts/python scripts/leak_check.py
git add humble_catalog/series.py tests/test_series.py
git commit -m "feat(series): index owned volumes and classify an offered title"
```

---

### Task 3: Wire into `preview`, and rewrite the two tests whose behaviour changes

**Files:**
- Modify: `humble_catalog/bundle_preview.py:220-354` (`preview`)
- Modify: `tests/test_bundle_preview.py:183-209` (two existing tests)
- Test: `tests/test_bundle_preview.py`

**Interfaces:**
- Consumes: `series.owned_volumes`, `series.describe`, `series.sort_key` from Task 2.
- Produces: `preview(...)["series"]` — a list of `describe()` dicts, sorted by `series.sort_key`. `preview(...)["overlaps"]` no longer contains any offered title that produced a series hit.

**Context the implementer needs:** the fixture `tests/fixtures/bundle_data.json` offers `Shadow Hound Vol. 1-6` and `Moonfall Vol. 1-3` against owned `Shadow Hound Vol 1` and `MOONFALL, Vol. 1`. Both become series hits and therefore leave `overlaps`, which is what breaks the two existing tests. **Do not edit the fixture** — adding an item shifts the tier counts and `adds` lists that a dozen other tests assert on.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bundle_preview.py`:

```python
def _series(tmp_path):
    conn = _conn(tmp_path)
    try:
        return bundle_preview.preview(conn, _bundle())["series"]
    finally:
        conn.close()


def test_an_offered_range_reports_the_denominator_it_states(tmp_path):
    # The bundle sells Vol. 1-6 and the catalog holds Vol 1. This is the
    # one spelling that carries its own size, so it is the one case where
    # "you own 1 of 6" is derivable rather than guessed.
    hit = next(h for h in _series(tmp_path)
               if h["offered"] == "Shadow Hound Vol. 1-6")
    assert hit["kind"] == "collection"
    assert hit["span"] == [1, 6]
    assert hit["owned"] == [1]
    assert hit["already_owned"] is False


def test_a_series_hit_is_not_also_an_overlap(tmp_path):
    # Reported once, and accurately. Leaving it in `overlaps` too would
    # claim partial ownership under a heading beside a richer line saying
    # the same thing better.
    conn = _conn(tmp_path)
    try:
        report = bundle_preview.preview(conn, _bundle())
    finally:
        conn.close()
    offered = {h["offered"] for h in report["series"]}
    assert "Shadow Hound Vol. 1-6" in offered
    assert all(o["offered"] not in offered for o in report["overlaps"])


def test_a_series_the_catalog_does_not_hold_produces_no_line(tmp_path):
    assert all(h["offered"] != "Unrelated Book" for h in _series(tmp_path))


def test_series_lines_are_sorted_re_buys_first(tmp_path):
    keys = [series.sort_key(h) for h in _series(tmp_path)]
    assert keys == sorted(keys)


def test_an_offered_volume_already_held_is_flagged_on_a_live_report(tmp_path):
    # Seeded locally rather than through the shared fixture: this needs an
    # offered volume that matches no machine_name but IS a held volume.
    conn = db.connect(tmp_path / "rebuy.db")
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('shadowhound_vol1_examplecomics', "
                 "'Shadow Hound Vol 1', 'comic')")
    conn.commit()
    bundle = {
        "basic_data": {"human_name": "Humble Comics Bundle: Shadow Hound"},
        "tier_pricing_data": {"initial": {"price|money": {"amount": 5.0}}},
        "tier_item_data": {
            "shadowhound_vol1_reissue_examplecomics": {
                "human_name": "Shadow Hound Vol. 1"}},
        "tier_display_data": {"initial": {
            "tier_item_machine_names": ["shadowhound_vol1_reissue_examplecomics"]}},
    }
    try:
        report = bundle_preview.preview(conn, bundle)
    finally:
        conn.close()
    hit = report["series"][0]
    assert hit["already_owned"] is True
    assert hit["offered_volume"] == 1
```

Now **rewrite** the two tests at `tests/test_bundle_preview.py:183` and `:204`. Replace `test_an_omnibus_matching_an_owned_volume_becomes_an_overlap` with:

```python
def test_an_omnibus_matching_an_owned_volume_becomes_a_series_line(tmp_path):
    # Was an overlap scored 0.92 under "possibly already owned in part".
    # It is now a series line, which says strictly more: which volumes are
    # held, and -- because this spelling states its span -- out of how many.
    conn = _conn(tmp_path)
    try:
        report = bundle_preview.preview(conn, _bundle())
    finally:
        conn.close()
    hit = next(h for h in report["series"]
               if h["offered"] == "Shadow Hound Vol. 1-6")
    assert hit["owned_display"] == "Vol. 1"
    assert hit["span"] == [1, 6]
    # and it is still counted as new, because it is not owned. Read off the
    # same report: the two facts must hold together, and re-seeding the
    # same tmp_path database twice would violate items.machine_name.
    assert "Shadow Hound Vol. 1-6" in report["tiers"][1]["adds"]
```

Replace `test_overlaps_carry_the_item_id_so_the_viewer_can_link_to_the_row` with:

```python
def test_overlaps_carry_the_item_id_so_the_viewer_can_link_to_the_row(tmp_path):
    # The fixture's two omnibus titles are series lines now, so this needs
    # a genuine overlap with no volume marker anywhere. The edition-variant
    # pair from docs/TEST-DATA.md scores 100 through clean_title.
    conn = db.connect(tmp_path / "overlap.db")
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('widgetservices_examplepress', "
                 "'Building Widget Services, 2nd Edition', 'ebook')")
    conn.commit()
    bundle = {
        "basic_data": {"human_name": "The World of Examplia by Example Press"},
        "tier_pricing_data": {"initial": {"price|money": {"amount": 5.0}}},
        "tier_item_data": {"widgetservices_2e_examplepress": {
            "human_name": "Building Widget Services 2e"}},
        "tier_display_data": {"initial": {
            "tier_item_machine_names": ["widgetservices_2e_examplepress"]}},
    }
    try:
        overlaps = bundle_preview.preview(conn, bundle)["overlaps"]
    finally:
        conn.close()
    assert overlaps[0]["item_id"] == 1
    assert overlaps[0]["item_name"] == "Building Widget Services, 2nd Edition"
```

Add `series` to the import at `tests/test_bundle_preview.py:8`:

```python
from humble_catalog import bundle_preview, db, import_games, series, titles
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_bundle_preview.py -v`
Expected: FAIL — `KeyError: 'series'` on the new tests and on the two rewritten ones.

- [ ] **Step 3: Write the implementation**

In `humble_catalog/bundle_preview.py`, add `series` to the import at line 19:

```python
from humble_catalog import db, import_games, series, stats, url_import
```

Then in `preview`, immediately after the tier loop's `ordered.sort(...)` at line 326 and before `_adds(ordered, items)`:

```python
    # Series lines are computed before _overlaps runs, and take their
    # candidates OUT of it. An offered Vol. 7 scores 94.7 against an owned
    # Vol. 3 -- over the 0.90 cutoff -- so today it prints as "possibly
    # already owned in part" when it is certainly not owned at all. The
    # score even rises with the error: Vol. 7 against Vol. 17 scores 97.4.
    # Meanwhile an omnibus scores 77.4 against an owned volume and never
    # appeared, though that is the genuine partial-ownership case. So the
    # list showed the wrong pairs and hid the right ones; this reports each
    # once, in the place that describes it accurately.
    volumes = series.owned_volumes(conn)
    series_hits = []
    for machine_name, offered in list(candidates.items()):
        hit = series.describe(offered, volumes)
        if hit is None:
            continue
        series_hits.append(hit)
        del candidates[machine_name]
    series_hits.sort(key=series.sort_key)
```

And add the field to the returned dict, immediately before `"overlaps"`:

```python
        "series": series_hits,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_bundle_preview.py -v`
Expected: PASS, every test in the file.

- [ ] **Step 5: Leak-check and commit**

```bash
.venv/Scripts/python scripts/leak_check.py
git add humble_catalog/bundle_preview.py tests/test_bundle_preview.py
git commit -m "feat(preview): report series ownership and drop it from overlaps"
```

---

### Task 4: The CLI block

**Files:**
- Modify: `humble_catalog/bundle_preview.py` (`format_report`, and a new `_series_note` above it)
- Test: `tests/test_bundle_preview.py`

**Interfaces:**
- Consumes: `preview(...)["series"]` from Task 3.
- Produces: `_series_note(hit: dict) -> str`; `format_report` emits a `Series you already hold (N):` block between the tier lists and the overlap list, omitted when the list is empty.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bundle_preview.py`:

```python
def _report_text(tmp_path):
    conn = _conn(tmp_path)
    try:
        return bundle_preview.format_report(
            bundle_preview.preview(conn, _bundle()))
    finally:
        conn.close()


def test_the_cli_prints_a_series_block(tmp_path):
    text = _report_text(tmp_path)
    assert "Series you already hold (2):" in text
    assert "you own 1 of 6" in text


def test_the_cli_omits_the_series_block_when_there_is_nothing_to_say():
    report = {"name": "Bundle One", "url": "", "currency": "USD", "tiers": [],
              "series": [], "overlaps": [], "game_matching": False}
    assert "Series you already hold" not in bundle_preview.format_report(report)


def test_a_re_buy_is_shouted_because_it_should_stop_a_purchase():
    assert bundle_preview._series_note({
        "already_owned": True, "kind": "volume", "offered_volume": 2,
        "owned": [1, 2], "owned_display": "Vol. 1-2", "span": None,
    }) == "ALREADY OWNED -- you hold Vol. 2"


def test_a_continuation_names_the_run_you_hold():
    assert bundle_preview._series_note({
        "already_owned": False, "kind": "volume", "offered_volume": 7,
        "owned": [1, 2, 3, 5, 6], "owned_display": "Vol. 1-3, 5-6", "span": None,
    }) == "you own Vol. 1-3, 5-6"


def test_a_collection_without_a_span_states_no_denominator():
    # No title carries an omnibus's volume count, so none is invented.
    assert bundle_preview._series_note({
        "already_owned": False, "kind": "collection", "offered_volume": None,
        "owned": [1, 2], "owned_display": "Vol. 1-2", "span": None,
    }) == "you own 2 volumes (Vol. 1-2)"


def test_a_collection_of_one_volume_reads_as_a_volume():
    assert "you own 1 volume (" in bundle_preview._series_note({
        "already_owned": False, "kind": "collection", "offered_volume": None,
        "owned": [1], "owned_display": "Vol. 1", "span": None,
    })


def test_a_range_counts_only_the_volumes_inside_it():
    # Owning Vol. 9 says nothing about a bundle selling Vol. 1-6.
    assert bundle_preview._series_note({
        "already_owned": False, "kind": "collection", "offered_volume": None,
        "owned": [1, 2, 9], "owned_display": "Vol. 1-2, 9", "span": [1, 6],
    }) == "you own 2 of 6 (Vol. 1-2, 9)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_bundle_preview.py -k series -v`
Expected: FAIL — `AttributeError: module 'humble_catalog.bundle_preview' has no attribute '_series_note'`

- [ ] **Step 3: Write the implementation**

Add above `format_report` in `humble_catalog/bundle_preview.py`:

```python
def _series_note(hit):
    """The right-hand side of one series line."""
    if hit["already_owned"]:
        # Shouted, like the APPROXIMATE warning below. This is the one
        # line in the whole report that should stop a purchase: the
        # offered volume matched no machine_name yet is already held, so
        # it is a re-issue or another edition of a book on the shelf.
        return f"ALREADY OWNED -- you hold Vol. {hit['offered_volume']}"
    if hit["kind"] == "collection":
        span = hit["span"]
        if span:
            # A range states its own size, so this is the one case where a
            # denominator is known rather than guessed. Counted over the
            # volumes INSIDE the range: owning Vol. 9 says nothing about a
            # collection selling Vol. 1-6.
            inside = sum(1 for v in hit["owned"] if span[0] <= v <= span[1])
            return (f"you own {inside} of {span[1] - span[0] + 1} "
                    f"({hit['owned_display']})")
        noun = "volume" if len(hit["owned"]) == 1 else "volumes"
        return f"you own {len(hit['owned'])} {noun} ({hit['owned_display']})"
    return f"you own {hit['owned_display']}"
```

In `format_report`, insert immediately before the `if report["overlaps"]:` block:

```python
    # Before the overlap list and after the tiers: these are facts about
    # which volumes are held, where an overlap is a suspicion. Omitted
    # entirely when empty, as `adds` and `keyed_items` are.
    if report.get("series"):
        lines += ["", f"  Series you already hold ({len(report['series'])}):"]
        width = max(len(hit["offered"]) for hit in report["series"])
        for hit in report["series"]:
            lines.append(f"    {hit['offered']:<{width}}  {_series_note(hit)}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_bundle_preview.py -v`
Expected: PASS.

- [ ] **Step 5: Leak-check and commit**

```bash
.venv/Scripts/python scripts/leak_check.py
git add humble_catalog/bundle_preview.py tests/test_bundle_preview.py
git commit -m "feat(preview): print the series block in the CLI report"
```

---

### Task 5: The viewer section and its jump

**Files:**
- Modify: `humble_catalog/webapp/static/bundles.js:88-104`
- Modify: `humble_catalog/webapp/static/catalog.js:831` (add a branch beside `edition-jump`)
- Modify: `humble_catalog/webapp/static/style.css:383-384`
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: the `series` field on the `/api/bundle-preview` payload from Task 3.
- Produces: a `.bundle-series` section whose jump buttons carry `class="bundle-series-jump"` and `data-series="<series_name>"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webapp_js.py`, using the file's existing
`_render_bundle(report)` helper (defined at line 973) — it stubs the fetch,
awaits `previewBundle`, and returns the `#bundle-panel` HTML:

```python
_SERIES_REPORT = dict(_BUNDLE_REPORT, overlaps=[], series=[
    {"offered": "Shadow Hound Vol. 1-6", "series_name": "Shadow Hound",
     "kind": "collection", "offered_volume": None, "span": [1, 6],
     "owned": [1], "owned_display": "Vol. 1", "already_owned": False},
])


def test_bundle_panel_renders_a_series_section():
    html = _render_bundle(_SERIES_REPORT)
    assert "Series you already hold (1)" in html
    assert "you own 1 of 6" in html
    assert 'data-series="Shadow Hound"' in html


def test_bundle_panel_omits_the_series_block_when_there_is_none():
    assert "Series you already hold" not in _render_bundle(
        dict(_BUNDLE_REPORT, series=[]))


def test_bundle_panel_survives_a_payload_carrying_no_series_field():
    # The `|| []` guard, same as keyed_items: an older server sends no
    # series key at all, and a renderer that throws blanks the page.
    assert "The World of Examplia" in _render_bundle(_BUNDLE_REPORT)


def test_bundle_panel_shouts_a_re_buy():
    html = _render_bundle(dict(_BUNDLE_REPORT, overlaps=[], series=[
        {"offered": "Shadow Hound Vol. 1", "series_name": "Shadow Hound",
         "kind": "volume", "offered_volume": 1, "span": None,
         "owned": [1], "owned_display": "Vol. 1", "already_owned": True}]))
    assert "ALREADY OWNED" in html


def test_a_collection_with_no_span_states_no_denominator_in_the_panel():
    html = _render_bundle(dict(_BUNDLE_REPORT, overlaps=[], series=[
        {"offered": "Shadow Hound Omnibus", "series_name": "Shadow Hound",
         "kind": "collection", "offered_volume": None, "span": None,
         "owned": [1, 2], "owned_display": "Vol. 1-2", "already_owned": False}]))
    assert "you own 2 volumes (Vol. 1-2)" in html
    assert " of " not in html.split("Series you already hold")[1]
```

Note `_BUNDLE_REPORT` (line 955) deliberately keeps its `overlaps` entry
for `Shadow Hound Vol. 1-6`. That payload is static rather than produced
by `preview`, so the existing overlap tests keep working unchanged — the
removal happens server-side, in Task 3.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k series -v`
Expected: FAIL — the rendered HTML contains no `Series you already hold`.

- [ ] **Step 3: Write the implementation**

In `humble_catalog/webapp/static/bundles.js`, add above the `overlaps` const:

```js
  // Mirrors the CLI's _series_note. Facts about which volumes are held,
  // so this sits above the overlap list, which is a list of suspicions.
  const seriesNote = (s) => {
    if (s.already_owned) return `ALREADY OWNED — you hold Vol. ${s.offered_volume}`;
    if (s.kind === "collection") {
      if (s.span) {
        // A range states its own size; an omnibus word does not, so only
        // this branch has a denominator to print.
        const inside = s.owned.filter((v) => v >= s.span[0] && v <= s.span[1]).length;
        return `you own ${inside} of ${s.span[1] - s.span[0] + 1} (${s.owned_display})`;
      }
      return `you own ${s.owned.length} ${s.owned.length === 1 ? "volume" : "volumes"}`
        + ` (${s.owned_display})`;
    }
    return `you own ${s.owned_display}`;
  };
  // `|| []` because a payload from an older server carries no series field.
  const seriesHits = bundlePreview.series || [];
  const series = seriesHits.length ? `
    <section class="bundle-series">
      <h4>Series you already hold (${seriesHits.length})</h4>
      <ul>${seriesHits.map((s) => `<li>
        ${esc(s.offered)} —
        <button class="bundle-series-jump" data-series="${esc(s.series_name)}"
          >${esc(seriesNote(s))}</button></li>`).join("")}</ul>
    </section>` : "";
```

Change the panel assignment to include it, before `overlaps`:

```js
    ${lists}${keyed}${series}${overlaps}</details>`;
```

In `humble_catalog/webapp/static/catalog.js`, add a branch immediately after the `edition-jump` branch (line 838):

```js
  } else if (el.classList.contains("bundle-series-jump")) {
    // One control for the whole run, not one per volume: a 26-volume
    // series would otherwise emit 26 buttons. The type filter is cleared
    // for the same reason the edition jump clears it -- a series can span
    // comic and ebook, and an active filter would hide half the run.
    $("#f-type").value = "";
    $("#search").value = el.dataset.series;
    relevanceSort = true;
    location.hash = "#/library";
    render();
```

In `humble_catalog/webapp/static/style.css`, beside the existing `.bundle-overlaps` rules at line 383:

```css
.bundle-series h4 { margin: .6rem 0 .2rem; font-size: 1em; }
.bundle-series ul { margin: 0; padding-left: 1.2rem; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -v`
Expected: PASS.

- [ ] **Step 5: Verify in a browser against the demo catalog**

The JS harness has no computed styles and no filter to interact with — four bugs on the backlog's Done list reached a browser to be found for exactly that reason. Serve the **demo** catalog, never the real one:

```bash
.venv/Scripts/python scripts/demo_catalog.py
```

Open `http://localhost:8099`, preview a bundle, and confirm: the series block renders above the overlap list; the jump lands on the series with the type filter cleared; the block is absent when there are no hits.

- [ ] **Step 6: Leak-check and commit**

```bash
.venv/Scripts/python scripts/leak_check.py
git add humble_catalog/webapp/static/bundles.js humble_catalog/webapp/static/catalog.js humble_catalog/webapp/static/style.css tests/test_webapp_js.py
git commit -m "feat(viewer): show series ownership beside the bundle preview"
```

---

### Task 6: Documentation

**Files:**
- Modify: `docs/TEST-DATA.md` (Comics / manga table; E-books table)
- Modify: `docs/BACKLOG.md` (rewrite the volume-range entry; add the `clean_title` entry)

**Interfaces:**
- Consumes: everything above. Produces no code.

- [ ] **Step 1: Add the new invented rows to `docs/TEST-DATA.md`**

In the Comics / manga table, append:

```markdown
| Shadow Hound Vol. 22 (#127-132) | — | Example Comics | an issue range annotating a SINGLE volume — the shape every real range in the catalog has. `clean_title` strips the parenthetical, so `parse_series` sees `Vol. 22`; pins that an issue range never becomes a volume count |
| S.H.A.D.O.W Vol. 1 / S.H.A.D.O.W. Vol. 2 / S.H.A.D.O.W.: Vol. 3 | — | — | one series split three ways by punctuation drift; pins that `series_key` merges them |
| Shadow-Hound Quest Vol. 1 / Shadow-Hound-Quest Vol. 2 | — | — | space-versus-hyphen drift, the second measured fragmentation |
| Moonfalls Vol. 1 | — | — | the negative: differs from *Moonfall* by more than punctuation and holds an overlapping volume set, so it must **not** merge |
| Shadow Hound Vol. 1: Origins | — | — | a marker followed by a subtitle — 17% of volume markers in the catalog |
| Shadow Hound Omnibus | — | Example Comics | a collection word, which carries no volume count and so states no denominator |
```

Annotate the two existing rows so the measurement travels with them. Change the `Shadow Hound Vol. 1-6` and `Moonfall Vol. 1-3` notes to end with:

```markdown
 **Measured 2026-08-01: this spelling occurs zero times among owned titles.** Kept because tests depend on it and because a range must still be *recognized* — parsed as its lower bound it would report an owned Vol. 1 as owning the whole collection.
```

- [ ] **Step 2: Rewrite the backlog entry**

In `docs/BACKLOG.md`, delete the **Volume-range resolution** bullet from
the Bundle preview section, and add this at the top of the **Done** list:

```markdown
- **Volume-range resolution, which became volume-aware overlaps** —
  `docs/superpowers/specs/2026-08-01-volume-aware-overlaps-design.md`.
  A row now says "you own Vol. 1-6", "you own 1 of 6", or ALREADY OWNED,
  instead of a bare fuzzy score under a heading claiming partial
  ownership.
  **The entry's premise was false and the measurement it asked for is
  what showed it.** `Vol. 1-6` occurs **zero** times across 2,729 items.
  The only ranges present are *issue* ranges, 8 of 11 annotating a single
  volume — `Vol. 22 (#127-132)` is one volume collecting six issues, so
  "you own 1 of 6" applied to it would report a one-item product as a
  six-item one. `clean_title` strips them anyway, all 11 being
  parenthetical.
  **Where the wrong premise came from is worth recording.** The design
  spec illustrates the case with `Shadow Hound Vol. 1-6` and
  `docs/TEST-DATA.md` carries the same row. Under the privacy standing
  order the illustration is invented by necessity — and the anonymized
  stand-in became the thing later work reasoned from. The lesson is
  cheap: **cite counts alongside invented examples**, so the example
  carries its own evidence.
  **The overlap list was backwards, and the error grew with the score.**
  An offered Vol. 7 scores 94.7 against an owned Vol. 3 — over the 0.90
  cutoff, so it printed as possibly owned when it was not owned at all —
  and Vol. 7 against Vol. 17 scores 97.4. Meanwhile an omnibus scores
  77.4 against an owned volume and never appeared, though that is the
  genuine partial-ownership case. Same shape as `sequel_mismatch`: the
  near-identical pair is the one that is definitely a different product,
  so it needs a rule rather than a threshold.
  **No threshold appears anywhere in the feature**, which is measured
  rather than asserted. Exact bases fragment a series on punctuation
  alone — one was split three ways by a trailing period on an initialism,
  another by a space where a sibling used a hyphen — and stripping
  punctuation takes 172 bases to 169, merging exactly those. The one
  surviving near-identical pair holds *identical* volume sets, which is
  the evidence that it is two series rather than one drift. Same
  conclusion as the edition-linking entry, reached the same way.
  **A range must still be recognized even though it is never expanded**,
  and that correction came from writing the plan rather than the spec. A
  bare-volume pattern reads `Vol. 1-6` as volume 1, matches an owned
  Vol. 1, and prints ALREADY OWNED — discouraging the purchase of five
  books not held. Parsed as a collection it is also the one spelling
  stating its own denominator, so "you own 1 of 6" survives for exactly
  that case and stays unstated for an omnibus word.
  **The re-buy case was not anticipated and is the most valuable line.**
  An offered volume that matched no `machine_name` yet is a volume
  already held is a re-issue or another edition of a book on the shelf —
  the mistake the preview exists to prevent. It costs one `in` test
  against a set the feature already builds, and it printed as a bare 0.94
  before.
  Detection is live with no stored state, mirroring `dedupe.find_groups`:
  nothing to migrate, nothing for `reset` to preserve. Two committed
  tests changed behaviour deliberately and were rewritten rather than
  deleted. `clean_title` was left alone; its hint understands the wrong
  spelling, which is now its own entry above.
```

Add a new bullet under **Open → Other**:

```markdown
- **`clean_title`'s series-number hint understands the wrong spelling** —
  it fires on 3 of 2,729 items because it matches only the parenthesized
  `(Vol. 1)`, while the bare `Vol. 3` spelling covers 687. Measured
  2026-08-01 while building volume-aware overlaps, which worked around it
  by adding `parse_series` rather than widening it. Widening looks
  obviously right and is not free: `enrich.py:156` consumes `num_hint`
  for matching, so it would silently change enrichment across the whole
  catalog, and that wants its own measurement of what changes. A test in
  `test_titles.py` pins the current behaviour so the change cannot happen
  by accident.
```

- [ ] **Step 3: Run the full verification suite**

```bash
.venv/Scripts/python -m pytest
```
Expected: PASS, all tests. Then:
```bash
.venv/Scripts/python scripts/leak_check.py
```
Expected: `clean`.
```bash
.venv/Scripts/python scripts/check_no_data_tracked.py
```
Expected: `clean: no data files in tracked files and all history`.

- [ ] **Step 4: Commit**

```bash
git add docs/TEST-DATA.md docs/BACKLOG.md
git commit -m "docs(preview): close volume-range resolution as volume-aware overlaps"
```

---

## Verification before completion

Per `superpowers:verification-before-completion`, do not claim done without:

1. `.venv/Scripts/python -m pytest` — full suite green, with the count.
2. `.venv/Scripts/python scripts/leak_check.py` — `clean`, unpiped.
3. `.venv/Scripts/python scripts/check_no_data_tracked.py` — `clean`.
4. The browser check in Task 5 Step 5, against `scripts/demo_catalog.py` and **never** the real catalog.
5. `git log --oneline main..` showing six feature commits on `feat/volume-aware-overlaps`.
