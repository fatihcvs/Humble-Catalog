# Series-number fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill `enrichment.series` and `enrichment.series_number` from an item's own title where the stored value is NULL, without changing what `clean_title` returns.

**Architecture:** One helper in `enrich.py` turns a cleaned title into `(series_name, series_number)` by asking `parse_series`. Two callers use it: `enrich.run`, as a last-resort fallback on a winning candidate, and a new `enrich.fill_series` top-up pass that amends existing rows through a narrow `UPDATE … COALESCE`. Nothing in `titles.py` changes, so `cleaned` — and therefore every source lookup, score and worklist entry — is byte-identical before and after.

**Tech Stack:** Python 3, sqlite3, pytest, argparse. No new dependencies.

## Global Constraints

- **`humble_catalog/titles.py` must not change.** Widening `clean_title` collapses 2,308 distinct enrichable titles to 1,894, with 44 volumes of one series landing on a single query. The whole point of this plan is that `cleaned` is untouched.
- **Never overwrite a non-NULL stored value.** The fill is a last resort, never an override. This protects hand edits, spreadsheet imports and source-supplied values alike.
- **Never route the top-up through `apply_candidate`.** That function rewrites `status`, `match_confidence`, `hand_edited`, `enrich_override` and snapshots `pre_edit`. The top-up must issue its own narrow `UPDATE`.
- **Only a numbered volume answers.** `parse_series` also returns `kind == "collection"` (7 items); a collection states no number and must gain nothing.
- **Privacy standing order (`CLAUDE.md`).** Every title in a test, doc or commit message must be invented — draw from `docs/TEST-DATA.md`. Run `.venv/Scripts/python scripts/leak_check.py` after any task that adds titles.
- **Commit message trailer:** end every commit message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Work on branch `feat/series-number-fill`, already created and holding the design spec.

---

### Task 1: `series_from_title` and the `enrich.run` fallback

**Files:**
- Modify: `humble_catalog/enrich.py` (add helper near `apply_candidate`; replace lines 190-192)
- Test: `tests/test_enrich.py`

**Interfaces:**
- Consumes: `humble_catalog.titles.parse_series`, already imported into `titles`; `enrich.py` currently imports only `clean_title` from it, so the import line changes.
- Produces: `enrich.series_from_title(cleaned, num_hint=None) -> tuple[str | None, float | None]`. Returns `(display_name, number)` when the cleaned title parses as a numbered volume, else `(None, None)`. Task 2 calls it.

- [ ] **Step 1: Write the failing tests**

Add to the end of `tests/test_enrich.py`:

```python
def test_series_from_title_reads_the_bare_volume_spelling():
    assert enrich.series_from_title("Shadow Hound Vol. 2") == ("Shadow Hound", 2.0)


def test_series_from_title_reads_a_marker_followed_by_a_subtitle():
    # 113 of 679 volume markers in the catalog carry one.
    assert enrich.series_from_title("Shadow Hound Vol. 1: Origins") == \
           ("Shadow Hound", 1.0)


def test_series_from_title_still_honours_the_parenthesized_hint():
    # clean_title strips "(Book 1)" and hands the number over separately;
    # that path is unchanged by this work.
    assert enrich.series_from_title("Wings of Autumn Dusk", 1.0) == \
           ("Wings of Autumn Dusk", 1.0)


def test_series_from_title_answers_nothing_for_a_collection():
    # An omnibus states no volume number, and inventing one would be the
    # overclaim volume-aware overlaps removed.
    assert enrich.series_from_title("Shadow Hound Omnibus") == (None, None)


def test_series_from_title_answers_nothing_for_a_plain_title():
    assert enrich.series_from_title("Unrelated Book") == (None, None)


def test_enrich_fills_the_series_from_the_title_when_the_source_has_none(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn, name="Shadow Hound Vol. 2", typ="comic")
    bare = candidate(source="comicvine", title="Shadow Hound Vol. 2",
                     url="https://comicvine.gamespot.com/shadow-hound")
    enrich.run(db_path=tmp_path / "t.db",
               sources={"comicvine": _source([bare])}, _conn=conn)
    row = conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                       (item_id,)).fetchone()
    assert row["status"] == "matched"
    assert row["series"] == "Shadow Hound"
    assert row["series_number"] == 2.0


def test_enrich_prefers_the_source_series_over_the_title(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed(conn, name="Shadow Hound Vol. 2", typ="comic")
    named = candidate(source="comicvine", title="Shadow Hound Vol. 2",
                      series="Shadow Hound Chronicles", series_number=7.0,
                      url="https://comicvine.gamespot.com/shadow-hound")
    enrich.run(db_path=tmp_path / "t.db",
               sources={"comicvine": _source([named])}, _conn=conn)
    row = conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                       (item_id,)).fetchone()
    assert row["series"] == "Shadow Hound Chronicles"
    assert row["series_number"] == 7.0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python -m pytest tests/test_enrich.py -k "series" -v
```

Expected: the five `series_from_title` tests FAIL with `AttributeError: module 'humble_catalog.enrich' has no attribute 'series_from_title'`. `test_enrich_fills_the_series_from_the_title_when_the_source_has_none` FAILS on `assert row["series"] == "Shadow Hound"` because it is `None`. `test_enrich_prefers_the_source_series_over_the_title` PASSES already — it pins behaviour that must survive, so a pass here is correct.

- [ ] **Step 3: Add the helper**

In `humble_catalog/enrich.py`, change the import on line 7 from:

```python
from humble_catalog.titles import clean_title
```

to:

```python
from humble_catalog.titles import clean_title, parse_series
```

Then add this function immediately after `apply_candidate` (which ends at the `conn.commit()` on line 62), before the `_RESET_FIELDS` tuple:

```python
def series_from_title(cleaned, num_hint=None):
    """The series name and number an item's OWN title states, or (None, None).

    Takes clean_title's two return values. The number is read by
    parse_series, which understands the bare "Vol. 3" spelling that
    covers 675 items -- clean_title's own hint understands only the
    parenthesized "(Book 1)" one and fires on 3. Widening clean_title
    instead was measured and rejected: it strips the marker from the
    cleaned title, which is what feeds every source lookup and score, and
    collapses 2,308 distinct enrichable titles to 1,894. See
    docs/superpowers/specs/2026-08-01-series-number-fill-design.md.

    Only a numbered volume answers. A collection word states no number,
    so an omnibus gets (None, None) rather than an invented denominator.
    """
    found = parse_series(cleaned, num_hint)
    if found.kind != "volume" or found.number is None:
        return None, None
    return found.display, float(found.number)
```

- [ ] **Step 4: Replace the `num_hint` fallback in `run`**

In `humble_catalog/enrich.py`, replace these two lines (currently 191-192):

```python
            if best.get("series_number") is None and num_hint is not None:
                best = {**best, "series_number": num_hint}
```

with:

```python
            # The title's own series is the LAST resort, never an override:
            # a source that named the series knows it better than a string
            # split does. Both fields, symmetric with apply_candidate.
            from_title, number = series_from_title(cleaned, num_hint)
            if number is not None:
                if best.get("series_number") is None:
                    best = {**best, "series_number": number}
                if best.get("series") is None:
                    best = {**best, "series": from_title}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/Scripts/python -m pytest tests/test_enrich.py -v
```

Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 6: Confirm the cleaned title is untouched**

```bash
.venv/Scripts/python -m pytest tests/test_titles.py tests/test_harvest.py -v
```

Expected: PASS. `test_clean_title_hint_still_fires_only_on_the_parenthesized_spelling` passing is the guarantee that `cleaned` did not move.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/enrich.py tests/test_enrich.py
git commit -F - <<'EOF'
feat(enrich): read the series from the title when no source names it

series_from_title asks parse_series, which understands the bare "Vol. 3"
spelling covering 675 items, where clean_title's own hint understands
only "(Book 1)" and fires on 3. Widening clean_title was measured and
rejected: it strips the marker from the cleaned title that feeds every
source lookup, collapsing 2,308 distinct enrichable titles to 1,894.

The fill is a last resort on both fields, never an override - a source
that named the series knows it better than a string split does.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: The `fill_series` top-up pass

**Files:**
- Modify: `humble_catalog/enrich.py` (add `fill_series` after `credits`, at end of file)
- Modify: `docs/TEST-DATA.md` (one new comic row)
- Test: `tests/test_enrich.py`

**Interfaces:**
- Consumes: `enrich.series_from_title(cleaned, num_hint) -> (str | None, float | None)` from Task 1; `humble_catalog.titles.clean_title(raw) -> (str, float | None)`.
- Produces: `enrich.fill_series(db_path="catalog.db", _conn=None) -> int`, returning the number of rows amended. Task 3 calls it from the CLI.

- [ ] **Step 1: Record the new invented fixture**

In `docs/TEST-DATA.md`, in the **Comics / manga** table, add this row immediately after the `Shadow Hound Vol. 2` row:

```markdown
| Shadow Hound Vol. 5 | — | Example Comics | a hand-edited row carrying the typed series name *Shadow Hound Legends*; pins that the `enrich --series` top-up leaves both the value and the `hand_edited` flag alone |
| _(series name only)_ Shadow Hound Chronicles | — | Example Comics | a series name a **source** supplied, deliberately unlike the *Shadow Hound* base a title split would produce — the shape of the 78 rows where the two disagree. Pins that the fill adds a number without touching the name |
```

Both series names are invented and must stay distinct from the base
`Shadow Hound` that `parse_series` derives — a fixture that agrees with
the derived value cannot show that the stored one was preferred.

- [ ] **Step 2: Write the failing tests**

Add to the end of `tests/test_enrich.py`:

```python
def _seed_enriched(conn, name, typ="comic", **fields):
    """An item plus an enrichment row with the given columns already set."""
    item_id = _seed(conn, name=name, typ=typ)
    if fields:
        conn.execute(
            "UPDATE enrichment SET " + ", ".join(f"{k}=?" for k in fields)
            + " WHERE item_id=?", (*fields.values(), item_id))
        conn.commit()
    return item_id


def _enrichment(conn, item_id):
    return conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                        (item_id,)).fetchone()


def test_fill_series_writes_both_fields_from_the_title(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_enriched(conn, "Shadow Hound Vol. 2", status="matched")
    assert enrich.fill_series(_conn=conn) == 1
    row = _enrichment(conn, item_id)
    assert row["series"] == "Shadow Hound"
    assert row["series_number"] == 2.0


def test_fill_series_keeps_a_source_supplied_name_while_adding_a_number(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_enriched(conn, "Shadow Hound Vol. 2", status="matched",
                             series="Shadow Hound Chronicles")
    assert enrich.fill_series(_conn=conn) == 1
    row = _enrichment(conn, item_id)
    assert row["series"] == "Shadow Hound Chronicles"
    assert row["series_number"] == 2.0


def test_fill_series_never_overwrites_a_disagreeing_number(tmp_path):
    # clean_title strips the issue range, so this parses as Vol. 22 -- but
    # a stored 99 is somebody's answer and outranks the title's.
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_enriched(conn, "Shadow Hound Vol. 22 (#127-132)",
                             status="matched", series="Shadow Hound",
                             series_number=99.0)
    assert enrich.fill_series(_conn=conn) == 0
    assert _enrichment(conn, item_id)["series_number"] == 99.0


def test_fill_series_leaves_a_hand_edited_row_alone(tmp_path):
    # The apply_candidate trap: that function clears hand_edited and
    # snapshots pre_edit. This pass must do neither.
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_enriched(conn, "Shadow Hound Vol. 5", status="matched",
                             series="Shadow Hound Legends", series_number=5.0,
                             hand_edited=1)
    assert enrich.fill_series(_conn=conn) == 0
    row = _enrichment(conn, item_id)
    assert row["series"] == "Shadow Hound Legends"
    assert row["hand_edited"] == 1
    assert row["pre_edit"] is None


def test_fill_series_fills_an_unmatched_row(tmp_path):
    # Deliberate: the number comes from the item's own name, so "no source
    # matched this" says nothing about whether the title states a volume.
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_enriched(conn, "Shadow Hound Vol. 2", status="unmatched")
    assert enrich.fill_series(_conn=conn) == 1
    row = _enrichment(conn, item_id)
    assert row["series_number"] == 2.0
    assert row["status"] == "unmatched"


def test_fill_series_leaves_status_and_confidence_alone(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    item_id = _seed_enriched(conn, "Shadow Hound Vol. 2",
                             status="low_confidence", match_confidence=0.62)
    enrich.fill_series(_conn=conn)
    row = _enrichment(conn, item_id)
    assert row["status"] == "low_confidence"
    assert row["match_confidence"] == 0.62
    assert row["series_number"] == 2.0


def test_fill_series_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_enriched(conn, "Shadow Hound Vol. 2", status="matched")
    assert enrich.fill_series(_conn=conn) == 1
    assert enrich.fill_series(_conn=conn) == 0


def test_fill_series_ignores_collections_and_plain_titles(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    omnibus = _seed_enriched(conn, "Shadow Hound Omnibus", status="matched")
    plain = _seed_enriched(conn, "Unrelated Book", typ="ebook", status="matched")
    assert enrich.fill_series(_conn=conn) == 0
    assert _enrichment(conn, omnibus)["series"] is None
    assert _enrichment(conn, plain)["series"] is None
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
.venv/Scripts/python -m pytest tests/test_enrich.py -k "fill_series" -v
```

Expected: all eight FAIL with `AttributeError: module 'humble_catalog.enrich' has no attribute 'fill_series'`.

- [ ] **Step 4: Implement `fill_series`**

Append to `humble_catalog/enrich.py`, after `credits` ends:

```python
def fill_series(db_path="catalog.db", _conn=None):
    """Fill series/series_number from each item's own title, NULL cells only.

    A top-up for rows already processed: enrich.run only visits pending
    items and only writes on a match, so 562 of the 667 items whose title
    states a volume number were already 'matched' when the fallback
    landed and would never be revisited. Returns the number of rows
    amended.

    Deliberately not routed through apply_candidate, which rewrites
    status, match_confidence, hand_edited and enrich_override and
    snapshots pre_edit. This pass owns two columns and touches nothing
    else about the row.

    Every status is visited, including 'unmatched'. The value comes from
    the item's own name, so a source having failed to match it says
    nothing about whether its title states a volume.

    Idempotent, which is load-bearing rather than tidy: both columns are
    in _RESET_FIELDS, so a reset clears the fill and re-running this is
    the recovery path.
    """
    conn = _conn or db.connect(db_path)
    rows = conn.execute(
        "SELECT e.item_id, i.name, e.series, e.series_number FROM enrichment e "
        "JOIN items i ON i.id = e.item_id "
        "WHERE e.series IS NULL OR e.series_number IS NULL").fetchall()
    filled = 0
    for row in rows:
        name, number = series_from_title(*clean_title(row["name"]))
        if number is None:
            continue
        if row["series"] is not None and row["series_number"] is not None:
            continue          # nothing left to fill; COALESCE would no-op
        # COALESCE and not a plain SET: it states the no-override rule in
        # the one place that can enforce it, so a half-filled row keeps
        # whichever cell it already had. The Python guard above is for the
        # COUNT, not for correctness -- sqlite3's total_changes is
        # cumulative over the connection and rowcount counts rows matched
        # rather than rows altered, so neither can tell a real fill from a
        # COALESCE that wrote a value back onto itself.
        conn.execute(
            "UPDATE enrichment SET series=COALESCE(series, ?), "
            "series_number=COALESCE(series_number, ?) WHERE item_id=?",
            (name, number, row["item_id"]))
        filled += 1
    conn.commit()
    print(f"Filled the series on {filled} items from their own titles.")
    if _conn is None:
        conn.close()
    return filled
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/Scripts/python -m pytest tests/test_enrich.py -v
```

Expected: PASS, all of them.

- [ ] **Step 6: Run the privacy check**

```bash
.venv/Scripts/python scripts/leak_check.py
```

Expected: `clean`. Do not pipe this command into anything — it must run alone.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/enrich.py tests/test_enrich.py docs/TEST-DATA.md
git commit -F - <<'EOF'
feat(enrich): add fill_series, a NULL-only top-up over existing rows

enrich.run only visits pending items and only writes on a match, so 562
of the 667 items whose title states a volume number were already matched
and would never be revisited by the fallback alone.

COALESCE states the no-override rule in the one place that can enforce
it, so a half-filled row keeps whichever cell it already had. The pass
deliberately does not route through apply_candidate, which would clear
hand_edited and snapshot pre_edit on rows it is supposed to leave alone.

Every status is visited, including unmatched: the value comes from the
item's own name, so a source having failed to match it says nothing
about whether the title states a volume.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: The `enrich --series` flag

**Files:**
- Modify: `humble_catalog/__main__.py` (argument at ~line 125, dispatch at ~line 244)
- Modify: `README.md` (~line 194, after the `--credits` bullet)
- Test: `tests/test_enrich.py`

**Interfaces:**
- Consumes: `enrich.fill_series(db_path="catalog.db", _conn=None) -> int` from Task 2.
- Produces: the CLI surface `python -m humble_catalog enrich --series`. Nothing later depends on it.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_enrich.py`:

```python
def test_fill_series_is_reachable_from_the_cli(tmp_path, monkeypatch):
    import humble_catalog.__main__ as cli
    called = {}
    monkeypatch.setattr(enrich, "fill_series",
                        lambda *a, **k: called.setdefault("ran", True))
    monkeypatch.setattr("sys.argv", ["humble_catalog", "enrich", "--series"])
    cli.main()
    assert called.get("ran")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/python -m pytest tests/test_enrich.py::test_fill_series_is_reachable_from_the_cli -v
```

Expected: FAIL with `SystemExit: 2` — argparse rejects the unrecognised `--series`.

- [ ] **Step 3: Add the argument**

In `humble_catalog/__main__.py`, immediately after the `--credits` argument (which ends with the line `help="Fill writer/illustrator for matched comics "` / `"(Comic Vine top-up; resumable)")`), add:

```python
    p_enrich.add_argument("--series", action="store_true",
                          help="Fill series name and number from each item's "
                               "own title where no source supplied them "
                               "(local, instant, safe to repeat)")
```

- [ ] **Step 4: Add the dispatch branch**

In `humble_catalog/__main__.py`, inside the `elif args.command == "enrich":` block, add a branch for `--series` immediately before the `elif args.credits:` line, so the chain reads:

```python
        if args.reset or args.reset_reviews:
            enrich.reset(reviews_only=not args.reset)
        elif args.series:
            enrich.fill_series()
        elif args.credits:
            enrich.credits()
        elif args.override_edited:
            enrich.override_edited(retry=args.retry)
        else:
            enrich.run(retry=args.retry)
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
.venv/Scripts/python -m pytest tests/test_enrich.py -v
```

Expected: PASS.

- [ ] **Step 6: Document the flag**

In `README.md`, immediately after the `enrich --credits` bullet (the one ending "Resumable."), add:

```markdown
- `python -m humble_catalog enrich --series` - fill the series name and
  number for items whose own title states a volume ("Shadow Hound Vol. 2"),
  where no source supplied them. Local and instant. Never overwrites a
  value you or a source already set, so it is safe to repeat - and you
  will want to after `enrich --reset`, which clears both fields.
```

- [ ] **Step 7: Run the full verification**

```bash
.\scripts\windows\verify.ps1
```

Expected: the whole suite passes and both privacy checks report clean.

- [ ] **Step 8: Commit**

```bash
git add humble_catalog/__main__.py README.md tests/test_enrich.py
git commit -F - <<'EOF'
feat(cli): add enrich --series to run the title-derived series fill

Follows the --credits precedent - a flag on enrich that walks
already-processed rows filling one thing - rather than adding a
sixteenth subcommand for a job that is enrichment's own.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Correct the pinning test's comment and close the backlog entry

**Files:**
- Modify: `tests/test_titles.py:153-158`
- Modify: `humble_catalog/titles.py:154-158` (the `parse_series` docstring paragraph)
- Modify: `docs/BACKLOG.md` (remove the entry from **Open → Other**; add to **Done**)

**Interfaces:**
- Consumes: nothing. Documentation only; no behaviour changes in this task.
- Produces: nothing.

- [ ] **Step 1: Correct the pinning test's comment**

In `tests/test_titles.py`, replace the comment inside `test_clean_title_hint_still_fires_only_on_the_parenthesized_spelling` (currently lines 154-156):

```python
    # Pins the deliberate NON-widening. enrich.py consumes this hint for
    # matching, so teaching it the bare spelling would silently change
    # enrichment across the catalog. That is its own backlog entry.
```

with:

```python
    # Pins the deliberate NON-widening, and the reason is NOT the hint --
    # that only fills a field on a candidate that already won. Widening
    # would strip the marker from the CLEANED TITLE, which feeds every
    # source lookup, score and worklist entry: measured at 2,308 distinct
    # enrichable titles collapsing to 1,894, with 44 volumes of one series
    # landing on a single query. enrich.series_from_title reads the bare
    # spelling instead, leaving cleaned byte-identical.
```

The two assertions below the comment do not change.

- [ ] **Step 2: Correct the `parse_series` docstring**

In `humble_catalog/titles.py`, replace this paragraph in `parse_series`'s docstring (currently lines 154-158):

```python
    `number_hint` is clean_title's own series number, which understands
    only the parenthesized "(Book 1)" spelling and fires on 3 of 2,729
    items. It is accepted here rather than widened: enrich.py consumes it
    for matching, so changing what it fires on changes enrichment
    catalog-wide. See docs/BACKLOG.md.
```

with:

```python
    `number_hint` is clean_title's own series number, which understands
    only the parenthesized "(Book 1)" spelling and fires on 3 of 2,729
    items. It stays narrow, and the reason is the cleaned title rather
    than the hint: widening it would strip the bare marker too, and
    `cleaned` is what feeds every source lookup, score and worklist
    entry. Measured 2,308 distinct enrichable titles collapsing to 1,894.
    enrich.series_from_title reads this function's own answer instead.
```

- [ ] **Step 3: Run the tests**

```bash
.venv/Scripts/python -m pytest tests/test_titles.py -v
```

Expected: PASS. Comments only — nothing executable changed.

- [ ] **Step 4: Remove the entry from the Open list**

In `docs/BACKLOG.md`, delete the entire bullet under **Open → Other** beginning `- **`clean_title`'s series-number hint understands the wrong spelling**` and ending `pins the current behaviour so the change cannot happen by accident.` The two bullets after it (**Standalone Android viewer app**, **Goodreads ratings**) stay.

- [ ] **Step 5: Add the Done entry**

In `docs/BACKLOG.md`, insert this as the **first** bullet of the **Done (formerly on this list)** section, above the volume-aware overlaps entry:

```markdown
- **`clean_title`'s series-number hint understood the wrong spelling** —
  `docs/superpowers/specs/2026-08-01-series-number-fill-design.md`.
  Shipped as `enrich.series_from_title` plus an `enrich --series` top-up,
  and `clean_title` was **not** widened.
  **The entry named the wrong consumer, and the right one is worse.** It
  said `enrich.py:156` consumes `num_hint` "for matching". It does not:
  the hint is read once, at line 191, on a candidate that has already
  won, after `status_for` has already decided. It cannot change a match.
  What widening would really have changed is the *cleaned title* — the
  marker gets stripped, and `cleaned` is what feeds `src.lookup`, `score`
  and `build_worklist`. Measured: 557 items change title, 2,308 distinct
  enrichable titles collapse to 1,894, and one series' 44 volumes land on
  a single query, so enrichment would ask one question for 44 books and
  score them identically — against 468 currently-matched rows.
  **The goal survived the mechanism**, the same way volume-aware overlaps
  did. `parse_series` already reads the bare spelling and takes
  `clean_title`'s *output*, so the number is obtainable with `cleaned`
  byte-identical: no cache churn, no worklist change, no matching change
  at all.
  675 items parse as a numbered volume and 667 had no stored number. The
  8 that did **agree with `parse_series` on all 8, zero disagreements**,
  which is the evidence the derived value is safe to write rather than a
  hope that it is — and none of the 667 is hand-edited.
  The series *name* came along by necessity, not scope creep. The viewer
  renders name and number in one cell, so a number on a nameless row
  prints a bare `#3`; 118 of the 667 had no name. The 549 that did keep
  it, including all 78 that disagree with the title-derived base — 74 of
  those are spelling drift where the source's prose is better, and the 4
  with nothing in common are too few to build a rule on.
  Two write paths because one could not reach the population: `enrich.run`
  covers everything from here on, but it only visits `pending` items and
  only writes on a match, and 562 of the 667 were already `matched`. The
  top-up is a flag on `enrich` following the `--credits` precedent, and it
  refuses to route through `apply_candidate` — that would clear
  `hand_edited` and snapshot `pre_edit` on rows it exists to leave alone.
  `COALESCE` carries the no-override rule rather than a read-then-write.
  Idempotence is load-bearing rather than tidy: both columns are in
  `_RESET_FIELDS`, so a reset clears the fill and re-running is the
  recovery path.
```

- [ ] **Step 6: Update the backlog's date stamp**

In `docs/BACKLOG.md`, confirm line 8 reads `Last updated: 2026-08-01.` — it already does, so no edit is needed unless the date has moved on.

- [ ] **Step 7: Run the full verification**

```bash
.\scripts\windows\verify.ps1
```

Expected: the whole suite passes and both privacy checks report clean.

- [ ] **Step 8: Commit**

```bash
git add tests/test_titles.py humble_catalog/titles.py docs/BACKLOG.md
git commit -F - <<'EOF'
docs(enrich): close the series-number hint entry, correcting its premise

The entry and two comments said enrich.py consumes num_hint "for
matching". It does not - the hint fills a field on a candidate that has
already won. The real catalog-wide effect runs through the cleaned
title, which widening would strip the marker from.

A pinning test that misstates what it is pinning invites the next reader
to unpin it, so the comment now names the cleaned title and carries the
2,308 -> 1,894 measurement.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Run the fill on the real catalog

**Files:** none — this task verifies against live data and changes no tracked file.

**Interfaces:**
- Consumes: the `enrich --series` CLI surface from Task 3.
- Produces: nothing.

- [ ] **Step 1: Back up the catalog first**

```bash
.venv/Scripts/python -m humble_catalog backup
```

Expected: a backup file is written. The fill is NULL-only and idempotent, but this is the first write to 667 live rows.

- [ ] **Step 2: Record the before state**

```bash
.venv/Scripts/python -c "import sqlite3; c=sqlite3.connect('catalog.db'); print('series_number set:', c.execute('SELECT COUNT(*) FROM enrichment WHERE series_number IS NOT NULL').fetchone()[0], '| series set:', c.execute('SELECT COUNT(*) FROM enrichment WHERE series IS NOT NULL').fetchone()[0])"
```

Expected: `series_number set: 8` — matching the spec's measurement. If it does not, stop and re-measure before writing anything.

- [ ] **Step 3: Run the fill**

```bash
.venv/Scripts/python -m humble_catalog enrich --series
```

Expected: `Filled the series on 667 items from their own titles.`

- [ ] **Step 4: Confirm the after state**

```bash
.venv/Scripts/python -c "import sqlite3; c=sqlite3.connect('catalog.db'); print('series_number set:', c.execute('SELECT COUNT(*) FROM enrichment WHERE series_number IS NOT NULL').fetchone()[0], '| hand_edited touched:', c.execute('SELECT COUNT(*) FROM enrichment WHERE hand_edited=1 AND pre_edit IS NOT NULL').fetchone()[0])"
```

Expected: `series_number set: 675` (8 + 667). The hand-edited count must be whatever it was before Step 3 — the fill snapshots no `pre_edit`.

- [ ] **Step 5: Confirm idempotence on live data**

```bash
.venv/Scripts/python -m humble_catalog enrich --series
```

Expected: `Filled the series on 0 items from their own titles.`

- [ ] **Step 6: Look at the result in the viewer**

```bash
.venv/Scripts/python -m humble_catalog serve
```

Sort or filter to a series and confirm rows read as `Shadow Hound #2` rather than a bare `#2` or a blank. **Do not screenshot the real catalog** — see the Privacy section of `CLAUDE.md`; if a screenshot is wanted, serve `scripts/demo_catalog.py` on port 8099 instead.

- [ ] **Step 7: No commit**

This task writes only to `catalog.db`, which is gitignored and must never be committed. Confirm with:

```bash
git status --short
```

Expected: empty.

---

## Self-Review

**Spec coverage.** Every section of the design maps to a task: the "not widened" decision to Task 4's comment corrections and the Global Constraints; the two write paths to Tasks 1 and 2; the NULL-only rule, the every-status decision and the `apply_candidate` refusal to Task 2's tests; the CLI surface to Task 3; the backlog close to Task 4; the live 667 to Task 5. The spec's testing list is covered item for item, with the "source-supplied name survives" case appearing in both Task 1 (enrich path) and Task 2 (top-up path), which is deliberate — they are different code.

**Naming.** `series_from_title` and `fill_series` are used consistently in Tasks 1-3; `fill_series` takes `(db_path, _conn)` matching `credits` and `run`, and returns `int` in every reference.

**Deliberate non-goals, all left alone:** `titles.py`'s patterns, the 78 name disagreements, the 7 collection items, and anything touching the harvest cache.
