# Edition Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show "also as audiobook" on a catalog row when the same work is
owned in another format, without merging the two rows.

**Architecture:** A new `humble_catalog/editions.py` computes edition
groups live on every call — no stored links, no schema change — exactly
as `dedupe.find_groups` does. Two items group when their titles are equal
after stripping a *trailing* run of format markers, and their types span
more than one of `{ebook, audiobook, comic}`. `/api/items` attaches the
siblings per row; the viewer renders a badge that jumps to the sibling.

**Tech Stack:** Python 3, SQLite (`sqlite3`), Flask, vanilla JS (no build
step), pytest. No new dependencies.

## Global Constraints

- **Privacy is a standing order.** Every title in committed text —
  tests, fixtures, docs, commit messages — must be invented, drawn from
  `docs/TEST-DATA.md`. Never a real item from the owner's library.
- **Vet any new invented title before writing it down.** `leak_check`
  matches *substrings*, so a private term buried mid-title trips it
  invisibly. Check with:
  `.venv/Scripts/python -c "import sys; sys.path.insert(0,'scripts'); import leak_check as lc; t=lc.build_terms(); print([x for x in t if x.lower() in 'your candidate title'.lower()])"`
- **Never pipe `leak_check.py`** — run it bare (see memory note; piping
  has bitten this project before).
- **Use `.venv/Scripts/python`,** and `python -m pip` for pip — the
  `pip.exe` shim in this venv exits 1 silently.
- **Full verification is `scripts/windows/verify.ps1`** — pytest, then
  `check_no_data_tracked.py`, then `leak_check.py`.
- **No score threshold may appear in this feature.** Matching is exact
  after the marker strip. If a task tempts you toward `rapidfuzz`, the
  design rejected it as *less accurate*, not as too slow.
- **`WORK_TYPES` excludes `android` and `music`** and that exclusion is
  the precision story. Do not widen it.

---

### Task 1: `edition_key` — the marker-stripping match key

**Files:**
- Create: `humble_catalog/editions.py`
- Test: `tests/test_editions.py`

**Interfaces:**
- Consumes: `humble_catalog.dedupe.dedupe_key(name) -> str` (existing).
- Produces: `editions.edition_key(name) -> str`, and the module constant
  `editions.WORK_TYPES: frozenset[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_editions.py`:

```python
"""Cross-format edition detection.

Titles are invented -- see docs/TEST-DATA.md."""
from humble_catalog import db, editions


def test_a_trailing_format_marker_is_stripped():
    key = editions.edition_key("Salt and Sextant")
    assert key == editions.edition_key("Salt and Sextant Audiobook")
    assert key == editions.edition_key("Salt and Sextant (Unabridged)")


def test_a_run_of_trailing_markers_strips_as_a_unit():
    # "(audiobook novella)" is two markers in a row, which is why the
    # strip repeats rather than applying once.
    assert editions.edition_key("The Copper Almanac") == \
        editions.edition_key("The Copper Almanac (audiobook novella)")


def test_a_marker_inside_the_title_is_kept():
    # Trailing-only, deliberately: an anywhere-strip would reduce this
    # to "engineering handbook" and invite a collision with a
    # genuinely different book.
    assert editions.edition_key("Audio Engineering Handbook") == \
        "audio engineering handbook"


def test_a_title_that_is_only_markers_keeps_its_key():
    # Stripping to empty would group every such title together, so the
    # last non-empty key wins.
    assert editions.edition_key("Audiobook") == "audiobook"


def test_work_types_excludes_android_and_music():
    # The exclusion IS the precision story -- every measured false
    # positive came from one of these two.
    assert "android" not in editions.WORK_TYPES
    assert "music" not in editions.WORK_TYPES
    assert editions.WORK_TYPES == {"ebook", "audiobook", "comic"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_editions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'humble_catalog.editions'`

- [ ] **Step 3: Write the implementation**

Create `humble_catalog/editions.py`:

```python
"""Cross-format edition detection: the same work owned as an ebook and
an audiobook (or a comic).

Deliberately parallel to `dedupe`, and computed live on every call with
no stored link state -- there is nothing to migrate, nothing to
invalidate, and nothing for `reset` to preserve.

Matching is EXACT after a marker strip, never fuzzy. Measured on the
catalog, `token_set_ratio` at 90 found 9 pairs of which 8 were the
subset artifact (it returns 100 whenever one side's token set is a
subset of the other's, so a one-word title scores perfectly against any
longer title containing that word). Exact matching found every genuine
pair with nothing spurious, so fuzzy is rejected as LESS accurate, not
as too slow. No threshold appears anywhere in this module."""
import re

from humble_catalog.dedupe import dedupe_key

# Types whose items are works that can exist in another format. android
# and music are excluded, and that exclusion is this feature's entire
# precision story: measured on the catalog, every false positive came
# from one of those two -- all 5 android/music groups were a game plus
# its own soundtrack, shipped together rather than the same work twice.
# Including comic was measured separately: 0 further groups across 988
# comic items, 0 false positives.
WORK_TYPES = frozenset({"ebook", "audiobook", "comic"})

# A trailing run of format markers: "Salt and Sextant Audiobook",
# "... (audiobook novella)", "... (audio)". `dedupe_key` has already
# lowercased and turned punctuation into spaces, so the parentheses are
# gone before this pattern ever sees the string.
#
# Trailing only, never mid-string. Every marker observed in the catalog
# is trailing, a trailing-only rule finds all of them, and it protects a
# title whose leading word is load-bearing rather than a format label:
# "Audio Engineering Handbook" keeps its first word.
#
# `novella` is the loosest marker and the only one that is not purely a
# format word. It is here because a measured pair needs it, and the cost
# is known: two genuinely distinct works named "X" and "X: A Novella"
# would group. None exists in the catalog.
_MARKERS = r"(?:un)?abridged|audio\s*book|novella|audio|e\s*book|ebook"
_TRAILING = re.compile(rf"(?:^|\s)(?:{_MARKERS})$")

def edition_key(name):
    """Match key for the same work across formats: `dedupe_key` with a
    trailing run of format markers removed.

    NOT shared with `dedupe_key`, which is a WITHIN-type key: stripping
    "audiobook" there would silently change how duplicate groups form
    among audiobooks. (`dedupe` also has a private `_EDITION` regex, but
    that one means *print* edition -- "2nd Edition" -- and is unrelated.)
    """
    key = dedupe_key(name)
    while True:
        stripped = _TRAILING.sub("", key).strip()
        # A title made only of markers strips to nothing; an empty key
        # would group every such title together, so keep the last
        # non-empty one.
        if not stripped or stripped == key:
            return key
        key = stripped
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_editions.py -q`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/editions.py tests/test_editions.py
git commit -m "feat(editions): edition_key, a trailing-marker-stripped match key"
```

---

### Task 2: `find_groups` — cross-type grouping with dismissals

**Files:**
- Modify: `humble_catalog/editions.py` (append)
- Test: `tests/test_editions.py` (append)

**Interfaces:**
- Consumes: `editions.edition_key`, `editions.WORK_TYPES` (Task 1);
  `db.connect(path) -> sqlite3.Connection` with `row_factory` set.
- Produces: `editions.find_groups(conn) -> list[list[int]]` — item ids
  ascending within a group, groups sorted by lowest member name.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_editions.py`:

```python
def _seed(conn, rows):
    """rows: [(machine_name, name, type)] -> {machine_name: id}"""
    ids = {}
    for mn, name, typ in rows:
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
            (mn, name, typ))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
        ids[mn] = cur.lastrowid
    conn.commit()
    return ids


def test_an_ebook_and_its_audiobook_group(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    ids = _seed(conn, [
        ("e1", "Salt and Sextant", "ebook"),
        ("a1", "Salt and Sextant Audiobook", "audiobook"),
        ("u1", "Unrelated Book", "ebook"),
    ])
    assert editions.find_groups(conn) == [sorted([ids["e1"], ids["a1"]])]


def test_two_items_of_the_same_type_never_group(tmp_path):
    # That is dedupe's question, not this one. A group must SPAN types.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("a1", "The Starless War", "audiobook"),
                 ("a2", "The Starless War", "audiobook")])
    assert editions.find_groups(conn) == []


def test_a_game_and_its_soundtrack_are_never_an_edition_group(tmp_path):
    # The measured false-positive shape, five times over in the real
    # catalog: an APK and its own soundtrack share a name because they
    # shipped together, not because they are the same work.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("g1", "Cool Tower Defense", "android"),
                 ("m1", "Cool Tower Defense", "music")])
    assert editions.find_groups(conn) == []


def test_a_subset_title_is_not_an_edition_group(tmp_path):
    # "compass" is a token subset of the longer title, so token_set_ratio
    # scores this pair 100 -- the exact trap that made fuzzy matching
    # produce 8 false positives. Exact keys differ, so: no group.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("e1", "Compass", "ebook"),
                 ("a1", "The Compass of Broken Years Audiobook", "audiobook")])
    assert editions.find_groups(conn) == []


def test_a_comic_and_an_ebook_group(tmp_path):
    # No such pair exists in the catalog yet. This test is what says the
    # comic type is admitted on purpose rather than by accident.
    conn = db.connect(tmp_path / "t.db")
    ids = _seed(conn, [("c1", "Nightjar Post", "comic"),
                       ("e1", "Nightjar Post", "ebook")])
    assert editions.find_groups(conn) == [sorted([ids["c1"], ids["e1"]])]


def test_a_dismissed_cross_type_pair_disappears(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("e1", "Salt and Sextant", "ebook"),
                 ("a1", "Salt and Sextant Audiobook", "audiobook")])
    a, b = sorted(["e1", "a1"])
    conn.execute("INSERT INTO dismissed_pairs (a, b) VALUES (?,?)", (a, b))
    conn.commit()
    assert editions.find_groups(conn) == []


def test_a_dismissed_same_type_pair_leaves_editions_alone(tmp_path):
    # dismissed_pairs is shared with dedupe, and the two meanings cannot
    # collide: dedupe's pairs are always same-type, edition pairs always
    # cross-type. This asserts that disjointness rather than assuming it.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, [("e1", "Salt and Sextant", "ebook"),
                 ("e2", "Salt and Sextant", "ebook"),
                 ("a1", "Salt and Sextant Audiobook", "audiobook")])
    a, b = sorted(["e1", "e2"])
    conn.execute("INSERT INTO dismissed_pairs (a, b) VALUES (?,?)", (a, b))
    conn.commit()
    # e1 and e2 are dismissed against each other but NOT against a1, so
    # both survive and the group still spans two types.
    assert len(editions.find_groups(conn)) == 1
    assert len(editions.find_groups(conn)[0]) == 3


def test_groups_are_sorted_by_lowest_member_name(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    ids = _seed(conn, [
        ("e1", "Salt and Sextant", "ebook"),
        ("a1", "Salt and Sextant Audiobook", "audiobook"),
        ("c1", "Nightjar Post", "comic"),
        ("e2", "Nightjar Post", "ebook"),
    ])
    assert editions.find_groups(conn) == [
        sorted([ids["c1"], ids["e2"]]),      # "nightjar post"
        sorted([ids["e1"], ids["a1"]]),      # "salt and sextant"
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_editions.py -q`
Expected: FAIL — `AttributeError: module 'humble_catalog.editions' has no attribute 'find_groups'`

- [ ] **Step 3: Write the implementation**

Append to `humble_catalog/editions.py`:

```python
def find_groups(conn):
    """-> groups (lists of 2+ item ids, ascending) that share an
    `edition_key` and SPAN more than one type, with dismissed pairs
    removed; groups sorted by lowest member name.

    Computed live on every call -- no stored link state, so a rebuilt
    catalog has its links back for free.

    Spanning types is what separates this from `dedupe.find_groups`:
    two audiobooks of the same name are duplicates, which is dedupe's
    question, not this one."""
    by_key = {}
    for r in conn.execute("SELECT id, machine_name, name, type FROM items"):
        if r["type"] not in WORK_TYPES:
            continue
        by_key.setdefault(edition_key(r["name"]), []).append(r)
    dismissed = {(r["a"], r["b"]) for r in
                 conn.execute("SELECT a, b FROM dismissed_pairs")}
    groups = []
    for members in by_key.values():
        if len(members) < 2:
            continue
        # Same rule as dedupe: drop a member only if it is dismissed
        # against EVERY other member.
        kept = [m for m in members if not all(
            tuple(sorted((m["machine_name"], o["machine_name"]))) in dismissed
            for o in members if o is not m)]
        # A single surviving type is not an edition group. This also
        # subsumes dedupe's `len(kept) > 1` check: one member spans one
        # type.
        if len({m["type"] for m in kept}) < 2:
            continue
        groups.append((min(m["name"].lower() for m in kept),
                       sorted(m["id"] for m in kept)))
    return [ids for _, ids in sorted(groups)]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_editions.py -q`
Expected: PASS, 13 passed

- [ ] **Step 5: Confirm dedupe is untouched**

Run: `.venv/Scripts/python -m pytest tests/test_dedupe.py -q`
Expected: PASS — in particular `test_find_groups_same_key_and_type_only`,
whose fixture already seeds a cross-type row commented "different type:
no pair". Editions now groups that row; dedupe still must not.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/editions.py tests/test_editions.py
git commit -m "feat(editions): group items sharing a key across formats"
```

---

### Task 3: `classify` accepts a trailing `(audio)`

**Files:**
- Modify: `humble_catalog/classify.py:17`
- Test: `tests/test_classify.py:4-32` (extend the parametrize table)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: no new symbol — `classify(bundle_name, platforms, formats,
  item_name="") -> str` keeps its signature and returns `"audiobook"`
  for one more input shape.

- [ ] **Step 1: Write the failing tests**

Add these three rows to the `@pytest.mark.parametrize` table in
`tests/test_classify.py`, immediately after the existing
`"Dune (Audiobook)"` row:

```python
    # A trailing "(audio)" is a format label, not a subject: two items
    # in the catalog are genuine audio editions of books filed as music
    # because this rule only accepted the literal word "audiobook".
    ("Humble Book Bundle: Test by Example Press", {"audio"}, {"mp3"},
     "The Copper Almanac (audio)", "audiobook"),
    # ...but only when it TRAILS. A bare "audio" anywhere would sweep in
    # every soundtrack and ambience pack, which is what the docstring's
    # caution is about.
    ("Humble Game Bundle: Samples", {"audio"}, {"mp3"},
     "Audio Ambience for Deep Space", "music"),
    ("Sample Studios: TTRPG Audio Compendium", {"audio"}, {"mp3"},
     "Sample Ambience Pack", "music"),
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_classify.py -q`
Expected: FAIL — one case fails, `assert 'music' == 'audiobook'` for
`The Copper Almanac (audio)`. The other two already pass and are
regression guards.

- [ ] **Step 3: Write the implementation**

In `humble_catalog/classify.py`, add the module-level pattern below the
existing constants:

```python
# A trailing "(audio)" is a format label on a book, not a subject. It is
# matched only at the END of the name: a bare "audio" substring would
# sweep in every soundtrack and ambience pack, which is exactly what the
# audio branch below exists to keep out. Measured blast radius on the
# catalog: 2 items, both genuine audio editions of owned ebooks, and no
# item anywhere carries a type override to be stomped.
_TRAILING_AUDIO = re.compile(r"\(\s*audio\s*\)\s*$", re.IGNORECASE)
```

Add `import re` at the top of the file, and change the audio branch:

```python
    if "audio" in platforms:
        if "audiobook" in lowered_bundle or "audiobook" in lowered_item \
                or _TRAILING_AUDIO.search(item_name):
            return "audiobook"
        return "music"
```

Then extend the docstring's third paragraph to read:

```
    Audio counts as an audiobook only when the bundle or item name says
    so -- the literal word "audiobook", or a trailing "(audio)" label;
    game bundles and music bundles also deliver audio (soundtracks,
    albums, TTRPG ambience) and those must not pollute the audiobook
    list.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_classify.py -q`
Expected: PASS, 16 passed

- [ ] **Step 5: Run the full suite — classification feeds everything**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS. `classify` runs during extract/reparse, so a
classification change can move rows in `test_extract.py`,
`test_stats.py` and `test_export.py`. If any fail, the fixture titles
must not contain a trailing `(audio)` — check before changing an
expectation.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/classify.py tests/test_classify.py
git commit -m "fix(classify): a trailing (audio) label is an audiobook, not music"
```

---

### Task 4: `/api/items` attaches edition siblings

**Files:**
- Modify: `humble_catalog/webapp/__init__.py:8` (import), `:86-88` (route)
- Test: `tests/test_webapp.py` (append)

**Interfaces:**
- Consumes: `editions.find_groups(conn) -> list[list[int]]` (Task 2);
  `db.fetch_items(conn) -> list[dict]` (existing), each dict carrying
  `id`, `name`, `type`.
- Produces: each `/api/items` item dict may carry
  `editions: [{"id": int, "type": str, "name": str}, ...]`. The key is
  **absent** when there are no siblings — consumers must guard.

Note on the existing test style: `tests/test_webapp.py` has **no shared
`client` fixture**. Each test builds its own with
`create_app(db_path=str(dbp)).test_client()` over a `tmp_path` db. Follow
that; do not introduce a fixture.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webapp.py`:

```python
def _seed_editions(dbp):
    """An ebook, its audiobook, and an unrelated row."""
    conn = db.connect(dbp)
    for mn, name, typ in [("e1", "Salt and Sextant", "ebook"),
                          ("a1", "Salt and Sextant Audiobook", "audiobook"),
                          ("u1", "Unrelated Book", "ebook")]:
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
            (mn, name, typ))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    conn.commit()
    conn.close()


def test_api_items_attaches_edition_siblings(tmp_path):
    dbp = tmp_path / "t.db"
    _seed_editions(dbp)
    client = create_app(db_path=str(dbp)).test_client()

    by_name = {i["name"]: i for i in
               client.get("/api/items").get_json()["items"]}

    ebook = by_name["Salt and Sextant"]
    assert [s["type"] for s in ebook["editions"]] == ["audiobook"]
    assert ebook["editions"][0]["name"] == "Salt and Sextant Audiobook"

    audio = by_name["Salt and Sextant Audiobook"]
    assert [s["type"] for s in audio["editions"]] == ["ebook"]
    assert audio["editions"][0]["id"] == ebook["id"]

    # Absent, not empty, for a row with no sibling -- on a real catalog
    # that is nearly every row of a ~1.3 MiB payload.
    assert "editions" not in by_name["Unrelated Book"]


def test_export_rows_carry_no_edition_field(tmp_path):
    # fetch_items is shared with CSV/XLSX export "so the two
    # serializations cannot drift". An edition link is a derived view,
    # not a stored fact, so it is attached in the route and must not
    # reach the export's row source.
    dbp = tmp_path / "t.db"
    _seed_editions(dbp)
    conn = db.connect(dbp)
    assert all("editions" not in row for row in db.fetch_items(conn))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k edition -q`
Expected: FAIL — `KeyError: 'editions'` on the first test. The second
test **passes already**; it is a regression guard on the boundary, and
it must keep passing after Step 3.

- [ ] **Step 3: Write the implementation**

In `humble_catalog/webapp/__init__.py`, add `editions` to the existing
import on line 8:

```python
from humble_catalog import (bundle_preview, db, dedupe, editions, export,
                            keys, stats,
```

(keep the existing trailing names and line wrapping)

Replace the route at lines 86-88:

```python
    @app.get("/api/items")
    def items():
        rows = db.fetch_items(conn())
        # Attached HERE and not in fetch_items, which is shared with CSV
        # and XLSX export: an edition link is a derived view, while the
        # export stays a serialization of what the catalog stores. One
        # O(n) pass over the payload, no per-item query.
        #
        # The key is absent rather than [] for the rows with no sibling,
        # which is nearly all of them on a real catalog.
        by_id = {i["id"]: i for i in rows}
        for group in editions.find_groups(conn()):
            for iid in group:
                by_id[iid]["editions"] = [
                    {"id": o, "type": by_id[o]["type"], "name": by_id[o]["name"]}
                    for o in group if o != iid]
        return jsonify({"items": rows})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k edition -q`
Expected: PASS, 2 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "feat(editions): attach edition siblings to /api/items"
```

---

### Task 5: The viewer badge and its jump

**Files:**
- Modify: `humble_catalog/webapp/static/catalog.js:529-549` (name cell),
  and the click delegation chain near `:757` (`bundle-jump`)
- Modify: `humble_catalog/webapp/static/style.css:196` (beside
  `.badge.edited`)

**Interfaces:**
- Consumes: `item.editions` from Task 4 — `[{id, type, name}, ...]`,
  **possibly absent**.
- Produces: no JS export; a `.edition-jump` button carrying
  `data-name="<sibling name>"`.

- [ ] **Step 1: Add the badge to the row's name cell**

In `catalog.js`, in the **non-editing** `<tr>` branch, insert this
immediately after the `i.override ? ...` expression and before the
closing `</td>` of the name cell (line ~549):

```javascript
${(i.editions || []).map(o => ` <button class="badge edition edition-jump"
        data-name="${esc(o.name)}"
        title="The same work is in your library as ${esc(o.type)} -- click to go to it"
        >also as ${esc(o.type)}</button>`).join("")}
```

The `|| []` guard is load-bearing: the key is absent on nearly every
row.

- [ ] **Step 2: Add the click handler**

In the delegation chain, add a branch immediately after the
`bundle-jump` branch:

```javascript
  } else if (el.classList.contains("edition-jump")) {
    // The sibling is by definition a DIFFERENT type, so an active type
    // filter would hide exactly the row being jumped to. Clearing it is
    // the whole reason this is more than filling the search box.
    $("#f-type").value = "";
    $("#search").value = el.dataset.name;
    relevanceSort = true;
    render();
```

- [ ] **Step 3: Style the badge**

In `style.css`, immediately after the `.badge.queued` rule (line ~198):

```css
/* .badge defaults to --danger, which is wrong for a neutral fact about
   the library. It is also a <button>, so it must be told to look like
   the badges beside it rather than keeping the browser's grey default --
   the same trap the statistics panel's jump counts fell into. */
.badge.edition { background: var(--badge-info); border: 0; cursor: pointer;
                 font: inherit; font-size: .7rem; padding: 0 .3rem; }
```

- [ ] **Step 4: Verify in a real browser**

The JS harness has a stubbed DOM with no computed styles and cannot see
detachment or colour — three shipped bugs in this project's history were
invisible to it and caught only in a browser. So verify by eye:

1. Start the viewer: `preview_start` with the project's launch config
   (create `.claude/launch.json` running `scripts/windows/serve.ps1` if
   absent).
2. Confirm a badge appears on a row that has a sibling.
3. Set the type filter to E-books, then click an "also as audiobook"
   badge. **The audiobook row must appear** — this is the assertion the
   type-clearing exists for, and the one a stubbed DOM cannot make.
4. Confirm the badge is not red and does not render as a grey browser
   button in either light or dark theme.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/webapp/static/catalog.js humble_catalog/webapp/static/style.css
git commit -m "feat(editions): badge the other format on a row, and jump to it"
```

---

### Task 6: Documentation and the backlog

**Files:**
- Modify: `docs/TEST-DATA.md`
- Modify: `docs/BACKLOG.md`
- Modify: `humble_catalog/webapp/__init__.py:280-282` (comment only)

**Interfaces:**
- Consumes: nothing. Produces: nothing executable.

- [ ] **Step 1: Add the invented titles to `docs/TEST-DATA.md`**

Under **E-books**:

```
| Salt and Sextant | — | — | ebook half of the marker-suffix edition pair (`editions.edition_key`) |
| The Copper Almanac | — | — | ebook half of the `(audio)`-classification edition pair |
| Compass | — | — | one-word subset-trap foil: token_set_ratio scores it 100 against *The Compass of Broken Years Audiobook*, and it must NOT group |
| Nightjar Post | — | — | comic↔ebook edition pair; the case the catalog does not yet hold |
| Audio Engineering Handbook | — | — | a leading "audio" that is part of the title, pinning the trailing-only marker strip |
```

Under **Audiobooks**:

```
| Salt and Sextant Audiobook | — | — | — | trailing bare-marker edition pair |
| The Copper Almanac (audio) | — | — | — | trailing "(audio)" label; classified music before the classify fix |
| The Compass of Broken Years Audiobook | — | — | — | subset-trap foil against the ebook *Compass* |
```

Under **Comics / manga**:

```
| Nightjar Post | — | — | comic half of the comic↔ebook edition pair |
```

Amend the `Cool Tower Defense` row's note in **Android / games / music**
to add: *"also seeded as a `music` row of the bare name for the
edition-detection false-positive test — the committed `+ OST` variant
classifies as android, so it cannot serve."*

- [ ] **Step 2: Verify the new titles trip nothing**

Run (bare, never piped):
`.venv/Scripts/python scripts/leak_check.py`
Expected: `clean`

- [ ] **Step 3: Move the backlog entry to Done**

Delete the **ebook ↔ audiobook edition linking** bullet from
*Catalog features (identified 2026-07-24 code review)* in
`docs/BACKLOG.md`. If it was that section's only remaining bullet,
remove the section heading and its intro paragraph too.

Add to the top of the **Done** list:

```markdown
- **The same work owned in two formats** —
  `docs/superpowers/specs/2026-07-31-edition-linking-design.md`.
  A row now says "also as audiobook" and jumps to it. `/api/merge` still
  refuses a cross-type merge, correctly; this is the relationship that
  refusal used to leave impossible.
  Measurement made the feature smaller, not larger. The entry reads like
  a matching problem and is not one: exact keys plus a trailing-marker
  strip find every genuine pair with nothing spurious, while
  `token_set_ratio` at the preview's own 0.90 cutoff found 9 pairs of
  which **8 were the subset artifact** — it returns 100 whenever one
  side's token set is a subset of the other's, so a one-word title
  scores perfectly against any longer title containing that word. Fuzzy
  matching is rejected here as *less accurate*, not as too slow, and no
  threshold appears anywhere in the feature.
  The truth came from eyeballing the misses rather than the hits. The
  author gate — the strongest independent signal, populated on 101 of
  108 audiobooks — gave 70 same-author cross-type pairs, of which one
  had a matching title; reading the top three by hand showed all three
  genuine, scoring 100, 67 and 61. The scores were held down by suffixes
  `dedupe_key` does not strip. So the naive match was finding one pair
  in three, and the signal was never fuzziness — it was a suffix.
  **The type filter is the precision, not any score.** Admitting `music`
  costs six false positives to win two, because all five android/music
  groups are a game plus its own soundtrack — shipped together, not the
  same work twice. Widening to include `comic` was measured separately
  at 0 further groups across 988 comics and 0 false positives, so the
  type is admitted for a case the catalog does not yet hold, with a test
  rather than data behind it.
  The `classify.py` fix is load-bearing rather than co-located. Two
  items are genuine audio editions filed as `music` because the rule
  accepted only the literal word "audiobook"; a trailing `(audio)` now
  joins it, inside the existing platforms guard so no soundtrack can
  reach the branch. Without that fix, catching those two would mean
  admitting `music` and its six false positives — so fixing
  classification at the source is what buys the tight type filter. It
  took the population 4 → 6 of 2,729 items.
  Detection is live with no stored state, mirroring `dedupe.find_groups`
  — nothing to migrate, nothing for `reset` to preserve, and a rebuilt
  catalog has its links back for free. A stored link table was designed
  and declined: at six pairs it would mostly be a place for staleness to
  live. It reopens if a genuine pair appears that the exact key cannot
  see, which is the concrete trigger.
  Dismissal reuses `dismissed_pairs` on a disjointness argument —
  dedupe's pairs are always same-type and edition pairs always
  cross-type, so the key spaces cannot collide — and a test asserts that
  rather than assuming it. Nothing needs dismissing today.
  The badge is attached in the `/api/items` route and not in
  `fetch_items`, which is shared with CSV and XLSX export: a link is a
  derived view, the export stays a serialization of stored facts. The
  jump clears the type filter, which is the whole reason it is more than
  filling the search box — the sibling is by definition the type the
  filter is currently excluding.
```

- [ ] **Step 4: Point the merge route's comment at the alternative**

In `humble_catalog/webapp/__init__.py`, above the cross-type refusal:

```python
        # An ebook and its audiobook are different files from different
        # bundles, so they stay separate rows. `editions.py` supplies the
        # relationship instead -- this refusal is half an answer without
        # it.
        if rows[keep_id] != rows[drop_id]:
```

- [ ] **Step 5: Full verification**

Run: `powershell -File scripts/windows/verify.ps1`
Expected: tests pass, then
`Verified: tests pass, no private data in the repo.`

- [ ] **Step 6: Commit**

```bash
git add docs/TEST-DATA.md docs/BACKLOG.md humble_catalog/webapp/__init__.py
git commit -m "docs(editions): close the backlog entry, with the measurement"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| `editions.py`, `edition_key`, trailing-only strip, `novella` risk | 1 |
| `WORK_TYPES` and its exclusion rationale | 1 (constant), 2 (behaviour) |
| `find_groups`, groups-not-pairs, live computation | 2 |
| `classify.py` trailing `(audio)`, inside the platforms guard | 3 |
| Badge on `/api/items`, computed in route not `fetch_items` | 4 |
| Badge rendering, jump, type-filter clearing | 5 |
| `dismissed_pairs` reuse and the disjointness claim | 2 (tests) |
| Tests enumerated in the spec | 1, 2, 3, 4 |
| `docs/TEST-DATA.md`, `docs/BACKLOG.md`, merge comment | 6 |
| "No schema change, no migration" | Nothing to do — asserted by the
  absence of any migration step, and by Task 2 adding no table |

**Type consistency:** `edition_key(name) -> str` and
`find_groups(conn) -> list[list[int]]` are used with those signatures in
Tasks 2 and 4. The `editions` payload shape `{id, type, name}` is
produced in Task 4 and consumed in Task 5 as `o.name` / `o.type`.
`WORK_TYPES` is a `frozenset` in Task 1 and compared against a set
literal in its test, which is valid.

**Placeholder scan:** every code step carries real code; the two places
that say "check first" (Task 4 Step 1's webapp fixture, Task 5 Step 4's
launch config) are discovery of existing project facts, not deferred
decisions, and each names the exact command to run.

**Verified while writing, not assumed:**

- The `_TRAILING` regex in Task 1 was run against every case in its
  test: all four marker forms strip to a shared key, *Audio Engineering
  Handbook* keeps its first word, a title of only markers keeps its key,
  and the `Compass` subset foil's key differs. The alternation order
  matters — `audio\s*book` must precede the bare `audio`, or "audiobook"
  strips to "book". Do not reorder it.
- `tests/test_webapp.py` exists and builds a client per test via
  `create_app(db_path=str(dbp)).test_client()`; Task 4 follows that
  rather than adding a fixture.
- `#f-type` has an `<option value="">All types</option>`, so Task 5's
  `$("#f-type").value = ""` clears it rather than selecting nothing.
- `.badge` defaults to `--danger`, which is why Task 5 adds a modifier
  rather than reusing the bare class.

**One risk carried deliberately:** Task 5 has no automated assertion.
The JS harness's stubbed DOM has no computed styles and cannot model the
filter interaction, and three bugs in this project's history were
invisible to it and caught only in a browser — so Step 4 is a browser
check by eye, with the type-filter case named explicitly because it is
the one that silently produces an empty jump.
