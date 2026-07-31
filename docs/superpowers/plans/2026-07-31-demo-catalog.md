# Demo Catalog Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command that serves the catalog viewer against a throwaway
catalog of invented titles, so a visual check never has to point at the
owner's real library.

**Architecture:** A bare `.py` tool in `scripts/`, beside `leak_check.py`
and the `capture_*` scripts — what `scripts/README.md` calls "tools, not
wrappers", so it needs no per-OS wrapper trio. `seed(db_path)` builds a
catalog from a module-level row table; `main()` puts it in a temp
directory and serves it on port 8099. Splitting the two is what lets a
test exercise the seeding without binding a socket.

**Tech Stack:** Python 3.12, SQLite (`sqlite3`), Flask, pytest. No new
dependencies.

## Global Constraints

- **Every title must be invented,** drawn from `docs/TEST-DATA.md`. This
  file is tracked, so `leak_check.py` scans it like any other committed
  text — that is the safety net, and it is why the demo data belongs in
  a tracked script rather than an untracked scratch file.
- **Vet any new invented title before writing it down.** `leak_check`
  matches *substrings*, so a private term buried mid-title trips it
  invisibly:
  `.venv/Scripts/python -c "import sys; sys.path.insert(0,'scripts'); import leak_check as lc; t=lc.build_terms(); print([x for x in t if x.lower() in 'candidate title'.lower()])"`
- **Never pipe `leak_check.py`** — run it bare.
- **Use `.venv/Scripts/python`**; `python -m pip` for pip.
- **Port 8099, never 8087.** `serve` uses 8087 and `stop` targets that
  port, so a demo server on 8087 would be something `stop` silently
  kills and something that makes `serve` refuse to start.
- **The database goes in a temp directory,** never the repo. A `demo.db`
  beside `catalog.db` invites confusion, and `.gitignore`'s `catalog.db*`
  rule would **not** cover it.
- **This is a convenience, not a guard.** No in-viewer marker, no change
  to how the real catalog is served. Out of scope by decision.
- **Full verification is `scripts/windows/verify.ps1`.**

---

### Task 1: `seed` builds a demo catalog

**Files:**
- Create: `scripts/demo_catalog.py`
- Test: `tests/test_demo_catalog.py`

**Interfaces:**
- Consumes: `humble_catalog.db.connect(path) -> sqlite3.Connection`
  (row_factory set, foreign keys ON);
  `humble_catalog.db.tags_to_json(list) -> str | None`;
  `humble_catalog.db.fetch_items(conn) -> list[dict]`.
- Produces: `demo_catalog.DEMO_ROWS: list[dict]` and
  `demo_catalog.seed(db_path) -> None`.

**Why a test at all:** the script imports project internals, so without
one it rots silently and the rot is discovered the next time someone
wants a screenshot. No test binds a port.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_demo_catalog.py`:

```python
"""The demo catalog must stay loadable as the schema moves.

Titles are invented -- see docs/TEST-DATA.md. This file is what stops
scripts/demo_catalog.py rotting unnoticed between visual checks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import demo_catalog                                    # noqa: E402
from humble_catalog import db                          # noqa: E402


def test_seed_builds_a_loadable_catalog(tmp_path):
    dbp = tmp_path / "demo.db"
    demo_catalog.seed(dbp)
    items = db.fetch_items(db.connect(dbp))
    assert len(items) == len(demo_catalog.DEMO_ROWS)
    # fetch_items is what /api/items and the export both go through, so
    # loading cleanly is the property worth asserting.
    assert all(i["name"] and i["type"] for i in items)


def test_seed_covers_every_item_type(tmp_path):
    # The tool exists for visual checks in general, not one feature, so
    # a type missing here is a viewer surface nobody can eyeball.
    dbp = tmp_path / "demo.db"
    demo_catalog.seed(dbp)
    types = {i["type"] for i in db.fetch_items(db.connect(dbp))}
    assert types == {"ebook", "audiobook", "comic", "music", "android"}


def test_seed_is_rerunnable(tmp_path):
    # main() reuses one temp path across runs; a second seed must not
    # trip the machine_name UNIQUE constraint.
    dbp = tmp_path / "demo.db"
    demo_catalog.seed(dbp)
    demo_catalog.seed(dbp)
    assert len(db.fetch_items(db.connect(dbp))) == len(demo_catalog.DEMO_ROWS)


def test_every_row_lands_in_a_bundle(tmp_path):
    # An item in no bundle renders an empty Bundle cell, which is a
    # state worth being able to see deliberately rather than by accident.
    dbp = tmp_path / "demo.db"
    demo_catalog.seed(dbp)
    assert all(i["bundles"] for i in db.fetch_items(db.connect(dbp)))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_demo_catalog.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'demo_catalog'`

- [ ] **Step 3: Write the implementation**

Create `scripts/demo_catalog.py`:

```python
"""Serve the catalog viewer against a throwaway catalog of INVENTED
titles.

Point any visual check at this rather than the real catalog. A viewer
screenshot shows titles, counts, bundle names, ratings, tags and notes,
and no automated check reads pixels -- `leak_check.py` sees compressed
bytes and `check_no_data_tracked.py` filters paths -- so a screenshot of
the real library passes `verify` without complaint. See the Privacy
section of CLAUDE.md.

Every title here comes from docs/TEST-DATA.md. This file is tracked, so
`leak_check.py` scans it like any other committed text; that is the
point of keeping the demo data in the repo rather than in a scratch file.

    python scripts/demo_catalog.py

Serves on port 8099 -- deliberately not 8087, which `serve` uses and
`stop` targets.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from humble_catalog import db                          # noqa: E402
from humble_catalog.webapp import create_app           # noqa: E402

PORT = 8099

DEMO_BUNDLES = [
    ("bk1", "Humble Book Bundle: Test by Example Press", "2020-03-02"),
    ("au1", "Humble Audiobook Bundle: Epic Tales 2020 by Example Audio",
     "2021-06-14"),
    ("cm1", "Humble Comics Bundle: Shadow Hound", "2022-01-09"),
    ("gm1", "Humble Game Bundle: Samples", "2023-08-21"),
]

# A spread chosen to light up the viewer's surfaces, not just one
# feature: every type, a same-type duplicate pair for the Duplicates
# panel, a low-confidence row for the Review panel, a pair of
# near-titles and an accented one for search, and enough
# ratings/tags/series that the columns are not all empty.
#
# Every title is from docs/TEST-DATA.md.
DEMO_ROWS = [
    # -- a same-type duplicate pair (Duplicates panel) ----------------
    {"mn": "widget_2e", "name": "Building Widget Services 2e",
     "type": "ebook", "bundle": "bk1", "publisher": "Example Press",
     "rating": 4, "genre": ["Programming"], "status": "matched"},
    {"mn": "widget_2nd", "name": "Building Widget Services, 2nd Edition",
     "type": "ebook", "bundle": "bk1", "publisher": "Example Press",
     "status": "matched"},
    # -- a low-confidence row (Review panel) --------------------------
    {"mn": "quiet_harbor", "name": "The Quiet Harbor: A Novel",
     "type": "ebook", "bundle": "bk1", "status": "low_confidence",
     "candidates": [
         {"source": "hardcover", "title": "The Quiet Harbor",
          "authors": ["Alex Penner"], "genre": "Fiction", "series": None,
          "series_number": None, "rating": 4.1, "narrator": None,
          "illustrator": None, "extra": {}, "confidence": 0.72}]},
    # -- search foils: a near-title, and an accent ---------------------
    {"mn": "quiet_life", "name": "A Quiet Life in Harbors", "type": "ebook",
     "bundle": "bk1", "status": "matched"},
    {"mn": "cafe_clocks", "name": "Café of Broken Clocks", "type": "ebook",
     "bundle": "bk1", "rating": 3, "status": "matched"},
    # -- a fully annotated row: rating, tag, note, read status ---------
    {"mn": "unrelated", "name": "Unrelated Book", "type": "ebook",
     "bundle": "bk1", "rating": 2, "tags": ["lent out"],
     "comment": "Borrowed by a friend.", "read_status": "read",
     "status": "matched"},
    # -- audiobooks, one with the full series/narrator set -------------
    {"mn": "axebearer", "name": "Axebearer (Grim & Fell)",
     "type": "audiobook", "bundle": "au1", "rating": 5,
     "genre": ["Fantasy"], "series": "The Elder Realm", "series_number": 1,
     "authors": ["Alex Penner"], "narrator": "Sam Reader",
     "read_status": "read", "status": "matched"},
    {"mn": "starless_war", "name": "The Starless War", "type": "audiobook",
     "bundle": "au1", "genre": ["Science Fiction"],
     "read_status": "reading", "status": "matched"},
    # -- comics, one with an illustrator ------------------------------
    {"mn": "shadowhound_v1", "name": "Shadow Hound Vol 1", "type": "comic",
     "bundle": "cm1", "publisher": "Example Comics", "genre": ["Manga"],
     "authors": ["Bo Writer"], "illustrator": "Alex Artist",
     "read_status": "want_to_read", "status": "matched"},
    {"mn": "moonfall_v1", "name": "MOONFALL, Vol. 1", "type": "comic",
     "bundle": "cm1", "status": "matched"},
    # -- android and music --------------------------------------------
    {"mn": "cooltower_android", "name": "Cool Tower Defense",
     "type": "android", "bundle": "gm1", "publisher": "Indie Dev Co",
     "status": "matched"},
    {"mn": "cooltower_ost", "name": "Sample Game OST", "type": "music",
     "bundle": "gm1", "status": "matched"},
    {"mn": "some_album", "name": "Some Album", "type": "music",
     "bundle": "gm1", "status": "matched"},
]


def seed(db_path):
    """Build a demo catalog at `db_path`, replacing any existing rows.

    Rerunnable: main() reuses one temp path, so a second run must not
    trip the machine_name UNIQUE constraint.
    """
    conn = db.connect(db_path)
    # Child-first, so foreign keys stay satisfied while emptying.
    for table in ("item_bundles", "enrichment", "items", "bundles"):
        conn.execute(f"DELETE FROM {table}")
    for gamekey, name, purchased in DEMO_BUNDLES:
        conn.execute(
            "INSERT INTO bundles (gamekey, name, url, purchased_at) "
            "VALUES (?,?,?,?)",
            (gamekey, name, f"https://example.invalid/{gamekey}", purchased))
    for row in DEMO_ROWS:
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type, publisher, "
            "my_rating, user_tags, user_comment, read_status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (row["mn"], row["name"], row["type"], row.get("publisher"),
             row.get("rating"), db.tags_to_json(row.get("tags")),
             row.get("comment"), row.get("read_status", "unread")))
        item_id = cur.lastrowid
        conn.execute("INSERT INTO item_bundles (item_id, gamekey) VALUES (?,?)",
                     (item_id, row["bundle"]))
        conn.execute(
            "INSERT INTO enrichment (item_id, genre, series, series_number, "
            "authors, narrator, illustrator, status, candidates) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (item_id, db.tags_to_json(row.get("genre")), row.get("series"),
             row.get("series_number"), db.tags_to_json(row.get("authors")),
             row.get("narrator"), row.get("illustrator"),
             row.get("status", "matched"),
             json.dumps(row["candidates"]) if row.get("candidates") else None))
    conn.commit()
    conn.close()


def main():
    # A fixed name inside the system temp directory: stable enough to
    # reopen between runs, and never beside catalog.db, where a stray
    # demo.db would sit outside .gitignore's `catalog.db*` rule.
    db_path = Path(tempfile.gettempdir()) / "humble-catalog-demo.db"
    seed(db_path)
    print(f"Demo catalog: {db_path}")
    print(f"Serving {len(DEMO_ROWS)} invented items on "
          f"http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    # covers_dir points at a directory with no files, so every row draws
    # its blank-cover state rather than reaching the real covers/.
    create_app(db_path=str(db_path),
               covers_dir=str(Path(tempfile.gettempdir()) /
                              "humble-catalog-demo-covers")
               ).run(host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_demo_catalog.py -q`
Expected: PASS, 4 passed

- [ ] **Step 5: Check the invented titles trip nothing**

Run (bare, never piped): `.venv/Scripts/python scripts/leak_check.py`
Expected: `clean`

Every title and person above is already in `docs/TEST-DATA.md` — no new
invented names are introduced by this change, which is deliberate: the
demo catalog is a *consumer* of that file, not another place that grows
it. `Alex Penner`, `Sam Reader`, `Bo Writer` and `Alex Artist` all come
from its tables. If the check reports a hit, the offending string is
ordinary prose matching as a substring — read the context before
touching `ALLOWED`.

- [ ] **Step 6: Start it once and confirm it serves**

Run: `.venv/Scripts/python scripts/demo_catalog.py`
Expected: prints the temp path and `Serving 13 invented items on
http://127.0.0.1:8099`. Open it, confirm 13 rows and that the four
sections load, then Ctrl+C.

- [ ] **Step 7: Commit**

```bash
git add scripts/demo_catalog.py tests/test_demo_catalog.py
git commit -m "feat(scripts): a demo catalog server for visual checks"
```

---

### Task 2: Make it the discoverable default

**Files:**
- Modify: `.claude/launch.json`
- Modify: `scripts/README.md:11-18` (the tools paragraph) and the Notes
  section
- Modify: `CLAUDE.md` (the images bullet in Privacy)

**Interfaces:**
- Consumes: `scripts/demo_catalog.py` and its port 8099 from Task 1.
- Produces: nothing executable.

- [ ] **Step 1: Add the launch entry**

`.claude/launch.json` is tracked, and currently has one entry serving the
real catalog. Replace its contents with:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "catalog-viewer",
      "runtimeExecutable": ".venv/Scripts/python",
      "runtimeArgs": [
        "-c",
        "from humble_catalog.webapp import create_app; create_app(db_path='catalog.db').run(host='127.0.0.1', port=8087)"
      ],
      "port": 8087
    },
    {
      "name": "catalog-viewer-demo",
      "runtimeExecutable": ".venv/Scripts/python",
      "runtimeArgs": ["scripts/demo_catalog.py"],
      "port": 8099
    }
  ]
}
```

JSON has no comments, so the warning that `catalog-viewer` serves the
real library lives in `scripts/README.md` and `CLAUDE.md` instead —
which is where someone reads before choosing, rather than after.

- [ ] **Step 2: Document it in `scripts/README.md`**

In the paragraph beginning "The `.py` files in this directory are tools,
not wrappers", add `demo_catalog.py` to the list:

```
the `capture_*.py` scripts record API fixtures, `demo_catalog.py` serves
the viewer against a throwaway catalog of invented titles, and
`make_favicon.py` regenerates the viewer's icon.
```

Then add this to the **Notes** section, immediately after the
`**Port** defaults to 8087` note:

```markdown
**`demo_catalog.py` serves invented data on port 8099**, deliberately
not 8087 — `serve` uses that port and `stop` targets it, so a demo
server there would be something `stop` silently kills. Use it for
anything that produces an image. A viewer screenshot shows titles,
counts, bundle names, ratings, tags and notes, and no automated check
reads pixels: `leak_check.py` sees a PNG's compressed bytes and
`check_no_data_tracked.py` filters paths, so a screenshot of the real
library passes `verify` without complaint. Its database is a single file
in the system temp directory, rebuilt on every run and never beside
`catalog.db`, where a stray `demo.db` would fall outside `.gitignore`'s
`catalog.db*` rule.
```

- [ ] **Step 3: Point CLAUDE.md's images bullet at it**

In `CLAUDE.md`, the Privacy bullet beginning **"Images are invisible to
every automated check"** ends with the sentence about
`favicon-32.png` carrying no catalog data. Append one sentence to that
bullet:

```
  For any check that produces an image, serve
  `scripts/demo_catalog.py` (port 8099) instead of the real catalog —
  it is the same viewer over invented titles.
```

- [ ] **Step 4: Full verification**

Run: `powershell -File scripts/windows/verify.ps1`
Expected: tests pass, then
`Verified: tests pass, no private data in the repo.`

- [ ] **Step 5: Commit**

```bash
git add .claude/launch.json scripts/README.md CLAUDE.md
git commit -m "docs(scripts): point visual checks at the demo catalog"
```

---

## Self-Review

**Design coverage:**

| Design point | Task |
|---|---|
| `scripts/demo_catalog.py` as a bare tool, no wrappers | 1 |
| `seed(db_path)` / `main()` split so a test needs no socket | 1 |
| Temp-dir database, never the repo | 1 (`main`), asserted by comment |
| Port 8099, not 8087 | 1 (`PORT`), 2 (README note) |
| Data spread: all types, duplicate pair, review row, search foils | 1 (`DEMO_ROWS`), pinned by the type test |
| `leak_check` as the safety net for demo titles | Global constraints, Task 1 Step 5 |
| Rot-guard test | 1 |
| `.claude/launch.json` demo entry | 2 |
| `scripts/README.md` | 2 |
| `CLAUDE.md` one line | 2 |
| No per-OS wrappers, no in-viewer marker | Out of scope, stated in constraints |

**Type consistency:** `seed(db_path)` and `DEMO_ROWS` are defined in
Task 1 and referenced by those names in Task 1's tests and Task 2's
launch entry. `PORT = 8099` matches the 8099 in `launch.json`, the
README note and CLAUDE.md.

**Placeholder scan:** every step carries real content. Step 6 of Task 1
is a manual check rather than an assertion, deliberately — it confirms
the socket actually binds, which the tests avoid doing on purpose.

**Three deviations from the design worth flagging:**

- **The demo rows use only titles already in `main`'s
  `docs/TEST-DATA.md`.** The first draft seeded the edition pairs
  (*Salt and Sextant*, *Nightjar Post*), but those names were added on
  the unmerged `docs/edition-linking` branch, so this plan would have
  depended on it silently. Keeping to `main`'s vocabulary lets the two
  branches merge in either order — and the edition badge does not exist
  on `main` anyway, so those rows would have rendered nothing. Adding
  them is a one-line follow-up once edition-linking lands.

- The design said the launch entry would carry a comment. JSON has no
  comments and this file is real config that a tool parses, so the
  warning moved to `scripts/README.md` and `CLAUDE.md`. A `_comment` key
  was considered and rejected: it would be the only non-schema key in
  the file.
- `covers_dir` is pointed at a nonexistent temp directory. Not in the
  design, but `create_app` defaults it to `covers/` — the real cover
  files, which are gitignored library data. A demo server resolving
  covers out of the owner's actual `covers/` directory would defeat the
  entire point on any row whose `cover_path` happened to match.
