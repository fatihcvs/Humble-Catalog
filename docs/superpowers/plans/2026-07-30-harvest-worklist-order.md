# Harvest Worklist Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `build_worklist`'s documented ordering guarantee true by sorting each source's title list, so the order is a pure function of the item set rather than of SQLite's unordered row scan.

**Architecture:** One functional change — `build_worklist`'s return statement sorts each list with `key=lambda t: (t.casefold(), t)`. No SQL change, no new module, no new dependency. The sort happens after de-duplication, so it operates on cleaned titles, which is what the list actually holds. Two new tests pin the guarantee the docstring has been claiming; the rest is documentation bookkeeping.

**Tech Stack:** Python 3 stdlib only (`sorted`, `str.casefold`), pytest, SQLite via `humble_catalog.db`.

Spec: `docs/superpowers/specs/2026-07-30-harvest-worklist-order-design.md`.

## Global Constraints

- **Privacy standing order (`CLAUDE.md`, non-negotiable):** no real library items in committed text. Every book title in tests, docs and commit messages must come from `docs/TEST-DATA.md`; add new invented names there rather than inventing them inline.
- **Run `.venv/Scripts/python scripts/leak_check.py` after any change that names books** — Task 1 and Task 2 both do. Never pipe its output.
- **No new dependencies.** The sort uses only the stdlib.
- **ASCII hyphens in Python source**, not em dashes — matches the existing docstrings in `harvest.py` and `quota.py` (e.g. `"for when the stored guess is wrong - a paid key rotated in"`).
- **The sort key is exactly `lambda t: (t.casefold(), t)`.** Not `str.casefold` alone: Python's sort is stable, so a case-only tie would fall back to the unordered `SELECT` and the bug would survive inside its own fix.
- **Accents are deliberately not folded.** Do not add `unicodedata` normalization.
- `git commit` will print `warning: LF will be replaced by CRLF` on this repo. That is normal; not an error.

---

### Task 1: Sort the worklist, and pin the order with tests

**Files:**
- Modify: `humble_catalog/harvest.py:11-30` (docstring and return statement)
- Modify: `docs/TEST-DATA.md` (E-books table — record the case-only pair the tie test uses)
- Test: `tests/test_harvest.py` (two new tests, appended after `test_worklist_dedupes_titles_per_source` at line 43)

**Interfaces:**
- Consumes: `harvest.build_worklist(conn)` and the module-level `_seed(conn, name, typ)` helper already in `tests/test_harvest.py:11-16`. `_seed` generates a unique `machine_name` per call via a module global, so seeding two items with the same display name is safe.
- Produces: `build_worklist(conn)` keeps its exact signature and return type — `dict[str, list[str]]`, source name to cleaned titles. Only the list order changes. No later task depends on anything new.

Background the implementer needs: `build_worklist` builds `worklist` as `{source_name: [cleaned_title, ...]}`, de-duping per source with the `seen` sets, then returns a dict comprehension that filters out sources with empty lists. `clean_title` (in `humble_catalog/titles.py`) strips edition suffixes, `": A Novel"`, and trailing parentheticals, and **preserves case** — it only strips `" ,-"` from the ends. That is why case-only pairs are two distinct entries and both reach the list.

- [ ] **Step 1: Write the two failing tests**

Append to `tests/test_harvest.py`, directly after `test_worklist_dedupes_titles_per_source` (which currently ends at line 43):

```python
def test_worklist_is_sorted_regardless_of_row_order(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    # Seeded deliberately out of alphabetical order: the guarantee is that
    # the list does not inherit the row order of an ORDER BY-less SELECT.
    _seed(conn, "Wings of Autumn Dusk (Book 1)", "ebook")
    _seed(conn, "Axebearer (Grim & Fell)", "ebook")
    _seed(conn, "Café of Broken Clocks", "ebook")
    wl = harvest.build_worklist(conn)
    # clean_title strips the parentheticals; the accent is not the deciding
    # character, so this title sorts at C rather than past z.
    assert wl["hardcover"] == ["Axebearer",
                               "Café of Broken Clocks",
                               "Wings of Autumn Dusk"]
    for titles in wl.values():
        assert titles == sorted(titles, key=lambda t: (t.casefold(), t))

def test_worklist_order_breaks_case_ties_by_content(tmp_path):
    """A case-only tie must be decided by the titles, not by row order.

    With key=str.casefold alone the two seedings below return different
    lists, because Python's stable sort falls back to the input order --
    which is the unordered SELECT this change exists to stop relying on.
    """
    def worklist(dbname, first, second):
        conn = db.connect(tmp_path / dbname)
        _seed(conn, first, "ebook")
        _seed(conn, second, "ebook")
        return harvest.build_worklist(conn)["hardcover"]
    # Distinct filenames on purpose: Windows paths are case-insensitive, so
    # naming these after the titles would collide on one file.
    forwards = worklist("one.db", "Gray Waters", "gray waters")
    backwards = worklist("two.db", "gray waters", "Gray Waters")
    assert forwards == backwards == ["Gray Waters", "gray waters"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -k "sorted_regardless or case_ties" -v
```

Expected: both FAIL.
- `test_worklist_is_sorted_regardless_of_row_order` fails on the first assert, with the list in seeded order: `['Wings of Autumn Dusk', 'Axebearer', 'Café of Broken Clocks']`.
- `test_worklist_order_breaks_case_ties_by_content` fails on `forwards == backwards`, because `forwards` is `['Gray Waters', 'gray waters']` and `backwards` is `['gray waters', 'Gray Waters']`.

If either test *passes* at this step, stop — the sort is already present and this plan has been partly applied.

- [ ] **Step 3: Sort the returned lists**

In `humble_catalog/harvest.py`, replace line 30:

```python
    return {name: titles for name, titles in worklist.items() if titles}
```

with:

```python
    return {name: sorted(titles, key=lambda t: (t.casefold(), t))
            for name, titles in worklist.items() if titles}
```

Leave the `if titles` filter exactly as it is — it drops sources no item type asked for, so `run()` does not spawn a thread and a progress row for a source with nothing to do.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/Scripts/python -m pytest tests/test_harvest.py -v
```

Expected: PASS, all tests in the file. The three pre-existing worklist tests must stay green unchanged — they assert with `in` and `.count()`, never an index, so the sort cannot affect them.

- [ ] **Step 5: Replace the docstring so it promises what the code now delivers**

In `humble_catalog/harvest.py`, replace the docstring at lines 12-18 with:

```python
    """Map each source name to the de-duplicated cleaned titles it must fetch.

    Every non-music/android item contributes its cleaned title to each
    source in SOURCE_ORDER for its type. Titles are de-duped per source so
    two items with the same cleaned title cost one request.

    Each list is sorted by casefolded title, which makes the order a pure
    function of the item set rather than of SQLite's row order - the query
    has no ORDER BY, so a reset, reparse or merge could reshuffle the scan.
    Resume does not depend on this (it is keyed on the cache, not on
    position); what the sort buys is that two runs over an unchanged
    catalog present the same work in the same sequence, and that a test
    can assert an order at all.

    The key is (casefold, raw) rather than casefold alone because Python's
    sort is stable: a case-only tie would otherwise fall back to that same
    unordered scan. Accents are not folded, so a title whose first letter
    is accented sorts past 'z' - determinism is the property needed here
    and codepoint order has it. See
    docs/superpowers/specs/2026-07-30-harvest-worklist-order-design.md.
    """
```

Note what was dropped: the old text's `and order is preserved for stable, resumable progress`. That clause was the defect — it named resumability as the reason, which was never what the order affected.

- [ ] **Step 6: Record the invented case-pair in the shared test-data universe**

In `docs/TEST-DATA.md`, in the **E-books** table, add this row after the `Café of Broken Clocks` row:

```markdown
| Gray Waters / gray waters | — | — | case-only pair for the worklist-order tie test; `Gray Waters` alone is the plain ebook row in `test_harvest.py` |
```

This is required by the privacy standing order: the tie test names a book, so the name must come from this file.

- [ ] **Step 7: Run the full gate**

The project's own pre-commit gate — the suite, then both privacy checks
(`check_no_data_tracked.py` and `leak_check.py`). Run it from PowerShell:

```bash
powershell -File scripts/windows/verify.ps1
```

Expected last line: `Verified: tests pass, no private data in the repo.`

If PowerShell is unavailable, the equivalent three commands are
`.venv/Scripts/python -m pytest -q`, then
`.venv/Scripts/python scripts/check_no_data_tracked.py`, then
`.venv/Scripts/python scripts/leak_check.py` (expect `clean`; never pipe
it — piping has produced misleading results on this repo before).

- [ ] **Step 8: Commit**

```bash
git add humble_catalog/harvest.py tests/test_harvest.py docs/TEST-DATA.md
```

```bash
git commit -F- <<'EOF'
fix(harvest): sort the worklist so its documented order is real

build_worklist's docstring promised "order is preserved for stable,
resumable progress", but the query is SELECT name, type FROM items with no
ORDER BY. SQLite returns a rowid scan, so the promise held by accident and
a reset, reparse or merge could have reshuffled it silently - no test
asserted a position.

Sorting the finished lists rather than adding ORDER BY, because the list
holds cleaned titles, not names: clean_title strips edition suffixes and
trailing parentheticals, so a SQL order would still be one derivation away
from the list's contents. Sorted, the order is a pure function of the item
set and needs nothing from SQLite.

The key is (casefold, raw), not casefold alone. Python's sort is stable, so
a case-only tie would fall back to the unordered SELECT and the bug would
survive inside its own fix; clean_title preserves case, so such pairs are
reachable rather than theoretical.

Accents stay unfolded: determinism is the property needed and codepoint
order has it. An accent only misplaces a title when it is the deciding
character, which the Café test case pins.

This is a tidiness fix by measurement, not a performance one. Order decides
which titles a rate-limited source spends its quota on only while the
uncached remainder exceeds the daily budget, and that window is closing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: Backlog bookkeeping

**Files:**
- Modify: `docs/BACKLOG.md` (line 8 `Last updated`; the Harvest section intro and two of its entries; the out-of-scope list; the Done list)

**Interfaces:**
- Consumes: nothing from Task 1 in code. Do this task *after* Task 1, because the Done entry describes a change that must already be committed.
- Produces: nothing consumed by code.

Two entries move to **Done**, and one idea is recorded as rejected. The second Done entry is a correction: `82d178b` shipped the retry change on 2026-07-26 without moving its entry, so the Open list currently describes a problem that is already fixed.

- [ ] **Step 1: Update the `Last updated` line**

`docs/BACKLOG.md` line 8, replace:

```markdown
Last updated: 2026-07-26.
```

with:

```markdown
Last updated: 2026-07-30.
```

- [ ] **Step 2: Update the Harvest section intro**

Replace:

```markdown
Surfaced by investigating a harvest that appeared to restart from
scratch on every rerun. The two bugs behind that are fixed, and the
quota-budgeting entry has since shipped; these are what is left.
```

with:

```markdown
Surfaced by investigating a harvest that appeared to restart from
scratch on every rerun. The two bugs behind that are fixed, and three
entries have since shipped - quota budgeting, the retry spend, and the
worklist order; these are what is left.
```

- [ ] **Step 3: Delete the two shipped entries from the Open list**

Delete the whole **"Retries spend quota, and google_books is where that hurts"** bullet (it runs from `- **Retries spend quota, and google_books is where that hurts**` through `Worth measuring the 503 rate over a full run before choosing.`).

Delete the whole **"`build_worklist` order is incidental, not guaranteed"** bullet (from `- **\`build_worklist\` order is incidental, not guaranteed** - the` through `docstring states a guarantee the code does not make.`).

The Harvest section keeps two Open entries: "Shorten the google_books worklist" and "A rate-limited source still walks its whole list".

- [ ] **Step 4: Record newest-purchase-first as decided against**

In the **"Explicitly out of scope (decided against, not merely postponed)"** section, add this bullet at the end of the list:

```markdown
- **Ordering the harvest worklist by newest purchase first** — measured
  2026-07-30 and rejected, not postponed. It looks like the right answer
  under a starved quota, but order only decides anything while the
  uncached remainder exceeds the daily budget: a cache hit costs no
  request, so if every uncached title fits in one day's quota they are all
  fetched today whatever position they hold. At ~2,300 eligible items and
  ~1,000 requests/day that window is days wide and closing, and reopening
  it would need one day's purchases to leave more than ~1,000 titles
  uncached when the largest bundle in the catalog is ~150 items. It is
  also a *superset* of the shipped sort rather than an alternative:
  `purchased_at` lives on `bundles`, so a large bundle gives up to ~150
  identical keys and a content tiebreak is needed underneath it anyway.
  Its two edge cases — a bundle with no date, an item in no bundle — exist
  nowhere in the catalog, so they would be defensive branches no test
  could exercise. Revisit only if the quota tightens or a single day's
  purchases can outrun a day's budget.
```

- [ ] **Step 5: Add the two Done entries**

At the top of the **"Done (formerly on this list)"** list, before the `- **Quota budgeting across harvest runs**` entry, add:

```markdown
- **Worklist order is guaranteed, not incidental** —
  `docs/superpowers/specs/2026-07-30-harvest-worklist-order-design.md`.
  `build_worklist` sorts each source's list by `(casefold, raw)`, so the
  order is a pure function of the item set instead of a property of an
  `ORDER BY`-less `SELECT` that SQLite happened to answer in insertion
  order. Sorting the finished lists rather than adding `ORDER BY`, because
  the lists hold *cleaned* titles: `clean_title` strips edition suffixes
  and trailing parentheticals, so a SQL order would still be one
  derivation away from what the list contains, and the guarantee would
  still rest on the query plan.
  The second key element is the whole subtlety. Python's sort is stable, so
  `key=str.casefold` alone would break a case-only tie by falling back to
  the unordered scan — the bug surviving inside its own fix, narrowed to
  case-differing pairs, which `clean_title` makes reachable because it
  preserves case. `test_worklist_order_breaks_case_ties_by_content` seeds
  the pair in both orders and demands the same answer, which is exactly the
  assertion `casefold` alone fails.
  Accents stay unfolded: determinism is the property wanted and codepoint
  order has it, and an accent misplaces a title only when it is the
  deciding character. `static/fuzzy.js` does fold accents, because there it
  is load-bearing and must keep an index map back to the original string;
  nobody searches the worklist.
  Framed by measurement as a **tidiness fix, not a performance one**, which
  is the opposite of how it first read. Order chooses which titles a
  rate-limited source enriches today only while the uncached remainder
  exceeds the daily quota — a cache hit costs no request — and at ~1,750
  uncached google_books titles against ~1,000/day that window was days
  wide and closing. The same measurement moved newest-purchase-first from
  a deferral to the decided-against list.

- **Retries spend quota, and google_books is where that hurts** — fixed
  2026-07-26 in `82d178b` (no spec; a one-source policy change).
  `_with_retries` retried 5xx twice more and every attempt costs a quota
  unit, so Google's frequent `503 backendFailed` made the median title cost
  two to three requests out of 1,000/day against a ~2,300-title worklist —
  roughly half the day's allowance spent re-asking questions that had
  already failed. A new `Source.retry_server_errors` gates it, so the
  policy lives in the source that has the constraint rather than in the
  shared retry helper.
  Connection errors and timeouts keep retrying everywhere, deliberately: a
  5xx came from Google and was almost certainly counted, while a connection
  error may never have reached the quota system at all. A skipped title is
  not lost — it stays uncached, so the next run has it at the head of the
  queue, trading same-run recovery for twice as many titles per day, which
  is the right way round for a source that needs several days regardless.
  The diagnosis came from cache timings rather than from any error log: 302
  rows over 85.5 minutes gave a median gap of 7.6s where the 2.0s throttle
  plus ~0.6s latency predicts 2.6s — one 5s backoff on the *median*
  request. The entry was left on the Open list by mistake and is recorded
  here on 2026-07-30.
```

- [ ] **Step 6: Verify the privacy gate**

```bash
.venv/Scripts/python scripts/leak_check.py
```

Expected: `clean` on the last line; do not pipe it. The new text names no books, but the standing order asks for this after editing docs and it is cheap.

- [ ] **Step 7: Commit**

```bash
git add docs/BACKLOG.md
```

```bash
git commit -F- <<'EOF'
docs(backlog): record the worklist order and the retry spend as done

Two entries move to Done. The worklist-order entry ships with this
change. The retry-spend entry shipped on 2026-07-26 in 82d178b and was
left on the Open list by mistake, so the backlog has been describing a
solved problem for four days.

Newest-purchase-first goes to the decided-against section rather than
Open. It was measured and rejected: order decides which titles a
rate-limited source enriches only while the uncached remainder exceeds
the daily budget, since a cache hit costs no request, and that window is
closing. Filing it as Open would invite a future session to re-derive the
bundles join the measurement rules out, so the entry carries the numbers
and can be re-checked rather than taken on trust.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

## Notes for the reviewer

- **The one line that matters** is Task 1 Step 3. Everything else is a test, a docstring, or bookkeeping.
- **The test that earns its keep** is `test_worklist_order_breaks_case_ties_by_content`. Verified before writing this plan: with `key=str.casefold` the two seedings return `['Gray Waters', 'gray waters']` and `['gray waters', 'Gray Waters']`; with the tuple key both return the former. A reviewer wanting to check the plan's central claim can reproduce that in three lines.
- **Behaviour change, stated:** this moves google_books' harvest frontier from insertion order to alphabetical. Nothing cached is re-fetched, so no quota is wasted, but the remaining catch-up days will enrich a different set of titles in a different sequence.
- **Not in scope, deliberately:** any sweep for other queries whose consumers assume an unpromised order.
