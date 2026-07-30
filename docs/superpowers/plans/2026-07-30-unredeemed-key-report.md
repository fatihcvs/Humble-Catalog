# Unredeemed Key Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report which Humble store keys have a game that appears in no imported store library — i.e. what has been paid for and probably never claimed — as a CLI subcommand and a viewer panel sharing one counter.

**Architecture:** A new `keys.py` follows `stats.py`'s split exactly: `report(conn, now)` is the only place a key's state is decided, `format_report()` prints it, and `GET /api/keys` reshapes it. The game-matching primitives move out of `bundle_preview.py` into `game_match.py` so both consumers share one set of cutoffs. Read-only throughout — no schema change, no migration, no writes.

**Tech Stack:** Python 3, SQLite, rapidfuzz, Flask, classic-script JavaScript, pytest, Node (for the JS harness).

## Global Constraints

- **Privacy standing order.** Every name in committed text — tests, docs, fixtures, commit messages — must be invented, drawn from `docs/TEST-DATA.md`. Never a real item from the owner's library.
- **New invented names must be vetted before use:** `leak_check.build_terms()` matches **substrings**, so a private term buried mid-title trips it. Vet, then add the name to `docs/TEST-DATA.md`.
- **`.venv/Scripts/python scripts/leak_check.py` must pass** before any commit that adds or edits tests, fixtures or docs naming books, bundles or people. Do **not** pipe it — run it bare and read the exit code.
- **Use `.venv/Scripts/python`, never bare `python`.** `.venv/Scripts/pip.exe` is broken; use `.venv/Scripts/python -m pip` if a package is ever needed (none is).
- The four states are exactly `matched`, `unredeemed`, `uncertain`, `uncheckable`, and they partition every row of `external_keys`.
- Cutoffs are `GAME_OWNED = 92.0` and `GAME_POSSIBLE = 80.0`, unchanged from `bundle_preview`.
- Expiry comes **only** from the `expiry_date` field of the stored `raw` blob. `num_days_until_expired`, `expiration_date` and `is_expired` are never read.
- Matching is scoped to the key's **own** store. Never pool libraries.
- No new dependency, no schema change, no migration, no write to `catalog.db`.

---

## File Structure

| File | Responsibility |
|---|---|
| `humble_catalog/game_match.py` | **new** — `GAME_OWNED`, `GAME_POSSIBLE`, `classify_game`. Shared by `bundle_preview` and `keys`. |
| `humble_catalog/bundle_preview.py` | **modify** — imports the three names instead of defining them. |
| `humble_catalog/keys.py` | **new** — `store_for`, `parse_expiry`, `report`, `format_report`, `run`. |
| `humble_catalog/__main__.py` | **modify** — the `keys` subcommand and its `--all` flag. |
| `humble_catalog/webapp/__init__.py` | **modify** — `GET /api/keys`. |
| `humble_catalog/webapp/static/keys.js` | **new** — the Keys section's table and state chips. |
| `humble_catalog/webapp/static/index.html` | **modify** — Keys section markup, `keys.js` script tag. |
| `humble_catalog/webapp/static/app.js` | **modify** — `loadKeys` joins `load()`'s step list; `pending.keys`. |
| `humble_catalog/webapp/static/style.css` | **modify** — key-table and key-chip rules. |
| `tests/test_keys.py` | **new** — the report's behaviour. |
| `tests/test_webapp.py` | **modify** — `/api/keys`. |
| `tests/test_webapp_js.py` | **modify** — chips and badge. |
| `tests/js_harness.py` | **modify** — `keys.js` joins `VIEWER_JS`. |
| `tests/js/harness.mjs` | **modify** — publish the new bindings. |
| `docs/TEST-DATA.md`, `docs/BACKLOG.md`, `README.md` | **modify** — new invented rows, entry to Done, user-facing docs. |

---

### Task 1: Extract `game_match.py`

Pure refactor. No behaviour changes, so the acceptance criterion is that every existing test passes untouched.

**Files:**
- Create: `humble_catalog/game_match.py`
- Modify: `humble_catalog/bundle_preview.py:22-49` (constants), `:167-189` (`classify_game`)
- Test: `tests/test_bundle_preview.py` (unchanged — it must stay green)

**Interfaces:**
- Consumes: `humble_catalog.titles.clean_game_title`, `humble_catalog.titles.sequel_mismatch`
- Produces: `game_match.GAME_OWNED` (float `92.0`), `game_match.GAME_POSSIBLE` (float `80.0`), `game_match.classify_game(offered: str, owned: list[tuple[str, str]]) -> tuple[str, dict | None]` where the string is `"owned"`, `"possible"` or `"new"` and the dict is `{"offered": str, "owned_title": str, "score": float}`

- [ ] **Step 1: Run the existing suite to establish the baseline**

Run: `.venv/Scripts/python -m pytest tests/test_bundle_preview.py -q`
Expected: PASS (record the count; it must not change).

- [ ] **Step 2: Create `humble_catalog/game_match.py`**

Move the code verbatim, and add the paragraph explaining why two callers treat the middle band oppositely.

```python
"""Deciding whether an offered game title is one the owner already has.

Shared by two callers that use the same two cutoffs and treat the middle
band between them in OPPOSITE ways, on purpose:

  bundle_preview  asks "should I buy this bundle", where the expensive
                  mistake is recommending a second purchase. A `possible`
                  is counted as neither owned nor new.
  keys            asks "did this key ever land", where the expensive
                  mistake is suppressing a key that quietly expires. A
                  `possible` is listed, annotated with what it nearly
                  matched.

Which is why the cutoffs live here rather than in either caller.
"""
from rapidfuzz import fuzz, process

from humble_catalog.titles import clean_game_title, sequel_mismatch

# Game ownership has no shared id to lean on, so these decide it outright
# rather than deciding whether to show a hint. Two thresholds, not one: the
# band between them is where the caller refuses to guess.
#
# Scored with token_sort_ratio, NOT the token_set_ratio the book overlap
# uses. token_set_ratio scores a subset as a perfect 100, so every base
# title would be a certain match for every expansion of it -- "Starfall
# Rally" would read as owning "Starfall Rally Turbo".
#
# Measured during design: a live 12-game bundle scored against an imported
# library of 1420 distinct normalized titles. Genuine same-game pairs both
# scored 100 (one of them only because normalization strips the offered
# title's subtitle punctuation first); the highest-scoring pair that was
# NOT the same game scored 70.6. The whole span 71-99 was empty, so
# GAME_OWNED sits in the middle of a ~30-point gap rather than on a
# boundary, and GAME_POSSIBLE is above every false pair measured -- nothing
# spurious reaches the band. Widen the band, do not narrow it, if a later
# bundle lands something in between.
GAME_OWNED = 92.0
GAME_POSSIBLE = 80.0


def classify_game(offered, owned):
    """('owned'|'possible'|'new', best_match_or_None) for one offered title.

    `owned` is [(normalized_title, display_title)] -- one store's library,
    or several pooled, according to what the caller is asking.

    A sequel is forced to 'new' whatever it scores: "widget quest" and
    "widget quest ii" differ by one token, so every fuzzy scorer rates
    them near-identical, and they are the one near-identical pair that is
    definitely a different product.
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
    match = {"offered": offered, "owned_title": owned[hit[2]][1],
             "score": round(hit[1] / 100, 2)}
    return ("owned" if hit[1] >= GAME_OWNED else "possible"), match
```

- [ ] **Step 3: Delete the moved code from `bundle_preview.py` and import it**

Remove the `GAME_OWNED`/`GAME_POSSIBLE` block (the comment starting `# Game ownership has no shared id...` through `GAME_POSSIBLE = 80.0`) and the whole `classify_game` function. Then change the import block near the top from:

```python
from humble_catalog import db, import_games, stats, url_import
from humble_catalog.titles import clean_game_title, clean_title, sequel_mismatch
```

to:

```python
from humble_catalog import db, game_match, import_games, stats, url_import
from humble_catalog.game_match import classify_game
from humble_catalog.titles import clean_game_title, clean_title
```

`sequel_mismatch` moves with `classify_game` and is no longer used in `bundle_preview`; `clean_game_title` is still used by `_keyed_games`. `game_match` is imported as a module as well so a reader sees where the cutoffs went.

- [ ] **Step 4: Run the suite to verify nothing changed**

Run: `.venv/Scripts/python -m pytest tests/test_bundle_preview.py tests/test_titles.py -q`
Expected: PASS, with the same test count as Step 1.

- [ ] **Step 5: Verify no stale references remain**

Run: `.venv/Scripts/python -c "import humble_catalog.bundle_preview as b; print(b.classify_game('Widget Quest', [('widget quest', 'Widget Quest')]))"`
Expected: `('owned', {'offered': 'Widget Quest', 'owned_title': 'Widget Quest', 'score': 1.0})`

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/game_match.py humble_catalog/bundle_preview.py
git commit -m "refactor(games): move the game-match cutoffs to their own module"
```

---

### Task 2: `keys.py` — states and counts

**Files:**
- Create: `humble_catalog/keys.py`
- Test: `tests/test_keys.py`

**Interfaces:**
- Consumes: `game_match.classify_game`, `import_games.imported_stores`, `db.connect`
- Produces:
  - `keys.store_for(key_type: str | None) -> str | None`
  - `keys.parse_expiry(value) -> datetime | None` (always tz-aware, UTC)
  - `keys.report(conn, now: datetime | None = None) -> dict` with keys `total` (int), `counts` (dict of the four states to int), `reported` (int), `expiring` (int), `libraries` (dict), `rows` (list) — `rows` is populated in Task 3 and is `[]`-shaped from the start.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_keys.py`:

```python
import datetime as dt
import json

from humble_catalog import db, import_games, keys, titles

NOW = dt.datetime(2026, 7, 30, tzinfo=dt.timezone.utc)


def _conn(tmp_path, rows, library=(("steam", "Widget Quest"),),
          imported=("steam",)):
    """A catalog holding `rows` as keys and `library` as imported games.

    `rows` is [(product, key_type, raw_extra)]; raw_extra is merged into
    the stored blob, so a test names only the fields it cares about.
    Every key belongs to one invented bundle.
    """
    conn = db.connect(tmp_path / "catalog.db")
    conn.execute("INSERT INTO bundles (gamekey, name, url, purchased_at) "
                 "VALUES ('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789', '2024-01-02T00:00:00')")
    for product, key_type, extra in rows:
        raw = {"human_name": product, "key_type": key_type,
               "machine_name": product.lower().replace(" ", "") + "_ex",
               "key_type_human_name": key_type.title()}
        raw.update(extra or {})
        conn.execute(
            "INSERT INTO external_keys (gamekey, human_name, key_type, raw) "
            "VALUES ('kv789', ?, ?, ?)",
            (product, key_type, json.dumps(raw)))
    conn.commit()
    for store in imported:
        import_games.store_games(conn, store, [
            {"store_id": f"{store}-{n}", "title": title,
             "normalized_title": titles.clean_game_title(title),
             "source_timestamp": None}
            for n, (s, title) in enumerate(library) if s == store], "test")
    return conn


def _states(tmp_path, rows, **kw):
    conn = _conn(tmp_path, rows, **kw)
    try:
        return keys.report(conn, now=NOW)["counts"]
    finally:
        conn.close()


def test_store_for_strips_the_keyless_suffix():
    assert keys.store_for("gog_keyless") == "gog"
    assert keys.store_for("epic_keyless") == "epic"
    assert keys.store_for("steam") == "steam"
    assert keys.store_for(None) is None


def test_a_key_whose_game_is_in_its_own_library_is_matched(tmp_path):
    counts = _states(tmp_path, [("Widget Quest", "steam", None)])
    assert counts["matched"] == 1
    assert counts["unredeemed"] == 0


def test_a_key_whose_game_is_in_no_library_is_unredeemed(tmp_path):
    counts = _states(tmp_path, [("Cinder Vale", "steam", None)])
    assert counts["unredeemed"] == 1


def test_a_key_for_a_store_with_no_importer_is_never_unredeemed(tmp_path):
    # The backlog's central limit: uplay has no importer, so "not in any
    # library" is unfalsifiable there. It is a third state, not a verdict.
    counts = _states(tmp_path, [("Verdant Reach", "uplay", None)])
    assert counts["uncheckable"] == 1
    assert counts["unredeemed"] == 0


def test_a_game_owned_only_on_another_store_still_reports_unredeemed(tmp_path):
    # THE design decision. A steam key is redeemed into steam; the game
    # sitting in the gog library says nothing about whether the key landed.
    # Do not "fix" this into pooling the libraries -- bundle_preview pools
    # them because it asks a different question.
    counts = _states(tmp_path, [("Pixel Harbor", "steam", None)],
                     library=(("gog", "Pixel Harbor"),),
                     imported=("steam", "gog"))
    assert counts["unredeemed"] == 1
    assert counts["matched"] == 0


def test_a_near_match_against_its_own_store_is_uncertain(tmp_path):
    # Starfall Rally Turbo against the owned Starfall Rally: the 80-92 band.
    counts = _states(tmp_path, [("Starfall Rally Turbo", "steam", None)],
                     library=(("steam", "Starfall Rally"),))
    assert counts["uncertain"] == 1


def test_the_four_states_partition_every_key(tmp_path):
    conn = _conn(tmp_path, [("Widget Quest", "steam", None),
                            ("Cinder Vale", "steam", None),
                            ("Verdant Reach", "uplay", None),
                            ("Starfall Rally Turbo", "steam", None)],
                 library=(("steam", "Widget Quest"),
                          ("steam", "Starfall Rally")))
    try:
        report = keys.report(conn, now=NOW)
    finally:
        conn.close()
    assert sum(report["counts"].values()) == report["total"] == 4
    assert report["reported"] == 3          # everything but `matched`


def test_an_imported_store_holding_no_games_still_checks(tmp_path):
    # An imported store with an empty library is not uncheckable: the
    # import happened and found nothing, so nothing there is redeemed.
    counts = _states(tmp_path, [("Cinder Vale", "steam", None)],
                     library=(), imported=("steam",))
    assert counts["unredeemed"] == 1
    assert counts["uncheckable"] == 0


def test_parse_expiry_normalizes_to_utc():
    assert keys.parse_expiry("2026-08-11T00:00:00") == dt.datetime(
        2026, 8, 11, tzinfo=dt.timezone.utc)
    assert keys.parse_expiry("2026-08-11T00:00:00Z") == dt.datetime(
        2026, 8, 11, tzinfo=dt.timezone.utc)
    assert keys.parse_expiry(None) is None
    assert keys.parse_expiry("not a date") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_keys.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'humble_catalog.keys'`

- [ ] **Step 3: Write `humble_catalog/keys.py`**

```python
"""Which Humble store keys have a game that is in no imported library.

Read-only: nothing here writes to catalog.db. The question is "what have I
paid for and never claimed", and the answer is derived from the two tables
that already hold it -- external_keys, filed by harvest, and games, filed
by import-games.

Split like stats.py: report() is the only place a key's state is decided,
format_report() prints it, and /api/keys reshapes it. The CLI and the
viewer panel therefore cannot disagree.

This is bundle_preview._keyed_games inverted. That helper asks "do I own
this bundle's games somehow" and pools every library, because owning the
game anywhere answers it. This asks "did this key ever land", which only
the key's OWN store can answer -- a steam key whose game sits in the gog
library is still an unactivated steam key.
"""
import datetime as dt
import json
import sys

from humble_catalog import db, game_match, import_games, stats

# Every key lands in exactly one of these, so the counts partition
# external_keys. `matched` is the only one not reported.
STATES = ("unredeemed", "uncertain", "uncheckable", "matched")

# classify_game's verdicts, in this report's vocabulary. The middle band is
# `uncertain` and IS reported, the reverse of bundle_preview's treatment --
# see game_match's module docstring for why.
_VERDICTS = {"owned": "matched", "possible": "uncertain", "new": "unredeemed"}


def store_for(key_type):
    """The `games.store` name a key of this type redeems into, or None.

    Humble spells the keyless variants of a store as "<store>_keyless"
    (gog_keyless, epic_keyless, blizzard_keyless), which is a delivery
    detail and not a different storefront.

    Checkability is NOT decided here: a store is checkable when
    game_imports holds a row for it, so a machine that has never imported
    Epic reports its Epic keys as uncheckable rather than as unredeemed.
    Deriving it that way also means a store gaining an importer later
    needs no edit in this file.
    """
    normalized = (key_type or "").strip().lower().removesuffix("_keyless")
    return normalized or None


def parse_expiry(value):
    """`expiry_date` as a tz-aware UTC datetime, or None.

    The only expiry field read. `num_days_until_expired` and `is_expired`
    are harvest-time derivatives of this one -- measured to agree with it
    exactly on all 2,275 keys, and to go stale on their own as the catalog
    sits -- and `expiration_date` was byte-identical on all 493 rows
    carrying it. An absolute timestamp compared against now needs none of
    them.
    """
    if not value:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def _store_pools(conn):
    """{store: [(normalized_title, display_title)]}, deduped per store.

    One pool per store rather than one pooled list: see the module
    docstring. Ordered so the dedupe is deterministic rather than dependent
    on the order sqlite happens to return rows in -- the same reason
    build_worklist sorts.
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
    return pools


def _key_rows(conn):
    """Every key joined to its bundle, with its raw blob already parsed.

    Parsed in Python rather than with SQL json_extract: one parse yields
    machine_name, expiry_date, redeemed_key_val and key_type_human_name,
    where SQL would need four calls, and a blob that is not JSON skips its
    row instead of failing the whole query.
    """
    for row in conn.execute(
            "SELECT k.human_name AS product, k.key_type AS key_type, "
            "       k.gamekey AS gamekey, k.raw AS raw, "
            "       b.name AS bundle, b.purchased_at AS purchased_at "
            "FROM external_keys k JOIN bundles b ON b.gamekey = k.gamekey"):
        try:
            raw = json.loads(row["raw"]) if row["raw"] else {}
        except ValueError:
            raw = {}
        yield row, raw


def report(conn, now=None):
    """Every key's state, and the reported rows in display order.

    `now` is injectable so the expiry arithmetic is testable; it defaults
    to the current UTC time.

    Returns {total, counts, reported, expiring, libraries, rows}. `rows`
    holds only the reported states -- `matched` is the answer "nothing to
    do here" and lives in `counts` alone.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    pools = _store_pools(conn)
    libraries = import_games.imported_stores(conn)
    counts = {state: 0 for state in STATES}
    total = 0
    for row, raw in _key_rows(conn):
        total += 1
        store = store_for(row["key_type"])
        if store is None or store not in libraries:
            counts["uncheckable"] += 1
            continue
        verdict, _match = game_match.classify_game(
            row["product"] or "", pools.get(store, []))
        counts[_VERDICTS[verdict]] += 1
    return {
        "total": total,
        "counts": counts,
        "reported": total - counts["matched"],
        "expiring": 0,
        "libraries": libraries,
        "rows": [],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_keys.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Check the report against the real catalog**

Run:
```bash
.venv/Scripts/python -c "from humble_catalog import db, keys; c=db.connect(); r=keys.report(c); print(r['total'], r['counts'])"
```
Expected: `2275 {'unredeemed': 547, 'uncertain': 77, 'uncheckable': 98, 'matched': 1553}` — the numbers the spec measured. A mismatch means a rule drifted, not that the data changed.

- [ ] **Step 6: Run the privacy check and commit**

Run: `.venv/Scripts/python scripts/leak_check.py`
Expected: `clean`

```bash
git add humble_catalog/keys.py tests/test_keys.py
git commit -m "feat(keys): decide each store key's redemption state"
```

---

### Task 3: `keys.py` — rows and sort order

**Files:**
- Modify: `humble_catalog/keys.py` (`report`)
- Test: `tests/test_keys.py`

**Interfaces:**
- Consumes: everything from Task 2.
- Produces: `report()["rows"]`, a list of dicts with exactly these keys:
  `product` (str), `machine_name` (str), `gamekey` (str), `store` (str | None), `key_type_label` (str), `bundle` (str), `purchased_at` (str | None), `expires` (ISO str | None), `expired` (bool), `days_left` (int | None), `revealed` (bool), `state` (str), `near_match` (`{"owned_title": str, "score": float}` | None).
  `report()["expiring"]` becomes the count of rows with `expired is False and expires is not None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_keys.py`:

```python
def _rows(tmp_path, rows, **kw):
    conn = _conn(tmp_path, rows, **kw)
    try:
        return keys.report(conn, now=NOW)["rows"]
    finally:
        conn.close()


def test_a_matched_key_is_counted_but_not_listed(tmp_path):
    # `matched` means "nothing to do here"; listing it would bury the rest.
    rows = _rows(tmp_path, [("Widget Quest", "steam", None),
                            ("Cinder Vale", "steam", None)])
    assert [r["product"] for r in rows] == ["Cinder Vale"]


def test_a_row_carries_its_bundle_machine_name_and_reveal_state(tmp_path):
    rows = _rows(tmp_path, [("Cinder Vale", "steam",
                             {"redeemed_key_val": "ABCDE-FGHIJ"})])
    row = rows[0]
    assert row["bundle"] == "Humble Game Bundle: Key Vault"
    assert row["machine_name"] == "cindervale_ex"
    assert row["gamekey"] == "kv789"
    assert row["store"] == "steam"
    assert row["purchased_at"] == "2024-01-02T00:00:00"
    # "revealed", never "redeemed": Humble sets this field the moment the
    # key's value is DISPLAYED, which says nothing about activation.
    assert row["revealed"] is True


def test_a_key_never_revealed_says_so(tmp_path):
    rows = _rows(tmp_path, [("Cinder Vale", "steam", None)])
    assert rows[0]["revealed"] is False


def test_an_uncertain_row_carries_what_it_nearly_matched(tmp_path):
    rows = _rows(tmp_path, [("Starfall Rally Turbo", "steam", None)],
                 library=(("steam", "Starfall Rally"),))
    assert rows[0]["state"] == "uncertain"
    assert rows[0]["near_match"]["owned_title"] == "Starfall Rally"
    assert 0.8 <= rows[0]["near_match"]["score"] < 0.92


def test_an_unredeemed_row_has_no_near_match(tmp_path):
    rows = _rows(tmp_path, [("Cinder Vale", "steam", None)])
    assert rows[0]["near_match"] is None


def test_an_expired_unmatched_key_is_still_listed(tmp_path):
    # Dropping it would hide that a key was lost, which is worth knowing
    # once even though nothing can be done about it.
    rows = _rows(tmp_path, [("Glass Meridian", "steam",
                             {"expiry_date": "2026-07-01T00:00:00"})])
    assert [r["product"] for r in rows] == ["Glass Meridian"]
    assert rows[0]["expired"] is True
    assert rows[0]["days_left"] is None


def test_a_live_expiry_reports_the_days_left(tmp_path):
    rows = _rows(tmp_path, [("Amber Hollow", "steam",
                             {"expiry_date": "2026-08-11T00:00:00"})])
    assert rows[0]["expired"] is False
    assert rows[0]["days_left"] == 12


def test_rows_sort_live_expiry_then_undated_then_expired(tmp_path):
    # Plain ascending would put the dead rows on top. Three groups, so the
    # rows that can still be lost come first -- what the backlog asked for.
    rows = _rows(tmp_path, [
        ("Glass Meridian", "steam", {"expiry_date": "2026-07-01T00:00:00"}),
        ("Cinder Vale", "steam", None),
        ("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
    ])
    assert [r["product"] for r in rows] == [
        "Amber Hollow", "Cinder Vale", "Glass Meridian"]


def test_the_soonest_live_expiry_comes_first(tmp_path):
    rows = _rows(tmp_path, [
        ("Cinder Vale", "steam", {"expiry_date": "2026-09-01T00:00:00"}),
        ("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
    ])
    assert [r["product"] for r in rows] == ["Amber Hollow", "Cinder Vale"]


def test_the_most_recently_expired_comes_first(tmp_path):
    rows = _rows(tmp_path, [
        ("Cinder Vale", "steam", {"expiry_date": "2025-01-01T00:00:00"}),
        ("Glass Meridian", "steam", {"expiry_date": "2026-07-01T00:00:00"}),
    ])
    assert [r["product"] for r in rows] == ["Glass Meridian", "Cinder Vale"]


def test_undated_rows_tie_break_deterministically(tmp_path):
    # A pure function of the data, never of the query plan -- the guarantee
    # the harvest worklist order design established.
    rows = _rows(tmp_path, [("Verdant Reach", "uplay", None),
                            ("Cinder Vale", "steam", None)])
    assert [r["product"] for r in rows] == ["Cinder Vale", "Verdant Reach"]


def test_expiring_counts_only_rows_that_can_still_be_lost(tmp_path):
    conn = _conn(tmp_path, [
        ("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
        ("Glass Meridian", "steam", {"expiry_date": "2026-07-01T00:00:00"}),
        ("Cinder Vale", "steam", None)])
    try:
        assert keys.report(conn, now=NOW)["expiring"] == 1
    finally:
        conn.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_keys.py -q`
Expected: FAIL — the new tests get `IndexError` or empty lists, because `rows` is still `[]`.

- [ ] **Step 3: Implement rows and the sort**

The ranking is built inline in `report` rather than in a helper, because it needs `now` and a sqlite `Row` cannot carry it — a helper taking `(row, expires, now)` would read worse than the six lines it replaced.

In `humble_catalog/keys.py`, replace the body of `report` from `counts = {state: 0 ...}` down to the `return` with:

```python
    counts = {state: 0 for state in STATES}
    ranked, total = [], 0
    for row, raw in _key_rows(conn):
        total += 1
        store = store_for(row["key_type"])
        near = None
        if store is None or store not in libraries:
            state = "uncheckable"
        else:
            verdict, match = game_match.classify_game(
                row["product"] or "", pools.get(store, []))
            state = _VERDICTS[verdict]
            if state == "uncertain":
                near = {"owned_title": match["owned_title"],
                        "score": match["score"]}
        counts[state] += 1
        if state == "matched":
            continue
        expires = parse_expiry(raw.get("expiry_date"))
        expired = expires is not None and expires < now
        # Three groups, not one ascending column. The backlog asked for
        # "expiry ascending with undated rows last so the rows that can
        # still be lost come first" -- and plain ascending does not deliver
        # that, because the already-dead rows sort above the urgent ones.
        # So the dated rows split AROUND the undated ones:
        #   0  a live expiry, soonest first -- can still be lost
        #   1  no expiry date
        #   2  already expired, most recent first
        # Ties break on purchased_at then the product name, so the order is
        # a pure function of the data rather than of the query plan.
        tie = (row["purchased_at"] or "", (row["product"] or "").lower())
        if expires is None:
            rank = (1, 0.0, *tie)
        elif expired:
            rank = (2, -expires.timestamp(), *tie)
        else:
            rank = (0, expires.timestamp(), *tie)
        ranked.append((rank, {
            "product": row["product"],
            "machine_name": raw.get("machine_name"),
            "gamekey": row["gamekey"],
            "store": store,
            # The 52-value display string, used ONLY as a label. Every
            # decision above came from key_type's 12 clean machine values,
            # so this column's `Other`/`other` collision stays cosmetic.
            "key_type_label": raw.get("key_type_human_name")
                              or row["key_type"] or "",
            "bundle": row["bundle"],
            "purchased_at": row["purchased_at"],
            "expires": expires.isoformat() if expires else None,
            "expired": expired,
            # Whole days, floored, and None once the date has passed --
            # "in -6 days" is not a thing anyone wants to read.
            "days_left": None if expires is None or expired
                         else (expires - now).days,
            # "revealed", never "redeemed": Humble sets this the moment the
            # key's value is DISPLAYED. The key that motivated this whole
            # feature reads as redeemed and had never been activated.
            "revealed": bool(raw.get("redeemed_key_val")),
            "state": state,
            "near_match": near,
        }))
    ranked.sort(key=lambda pair: pair[0])
    rows = [payload for _rank, payload in ranked]
    return {
        "total": total,
        "counts": counts,
        "reported": len(rows),
        "expiring": sum(1 for r in rows
                        if r["expires"] is not None and not r["expired"]),
        "libraries": libraries,
        "rows": rows,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_keys.py -q`
Expected: PASS (23 tests).

- [ ] **Step 5: Sanity-check against the real catalog**

Run:
```bash
.venv/Scripts/python -c "from humble_catalog import db, keys; c=db.connect(); r=keys.report(c); print(r['reported'], r['expiring'], len(r['rows']))"
```
Expected: `722 63 722`

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/keys.py tests/test_keys.py
git commit -m "feat(keys): list the reported rows, soonest-expiring first"
```

---

### Task 4: The `keys` CLI subcommand

**Files:**
- Modify: `humble_catalog/keys.py` (add `format_report`, `run`)
- Modify: `humble_catalog/__main__.py:140` (subparser), `:236` (dispatch)
- Test: `tests/test_keys.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `report()` from Task 3, `stats.console_safe`.
- Produces: `keys.format_report(report: dict, encoding: str = "utf-8", show_all: bool = False) -> str`; `keys.run(show_all: bool = False) -> None`; CLI `keys [--all]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_keys.py`:

```python
def _text(tmp_path, rows, show_all=False, **kw):
    conn = _conn(tmp_path, rows, **kw)
    try:
        report = keys.report(conn, now=NOW)
    finally:
        conn.close()
    return keys.format_report(report, show_all=show_all)


def test_the_summary_line_accounts_for_every_key(tmp_path):
    text = _text(tmp_path, [("Widget Quest", "steam", None),
                            ("Cinder Vale", "steam", None),
                            ("Verdant Reach", "uplay", None)])
    assert "3 keys - 1 in a library, 1 not, 1 uncheckable" in text


def test_the_default_prints_only_the_rows_that_can_still_be_lost(tmp_path):
    text = _text(tmp_path, [
        ("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
        ("Cinder Vale", "steam", None)])
    assert "Amber Hollow" in text
    assert "in 12 days" in text
    assert "Cinder Vale" not in text
    assert "keys --all" in text


def test_all_prints_the_undated_and_expired_rows_too(tmp_path):
    text = _text(tmp_path, [
        ("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
        ("Cinder Vale", "steam", None),
        ("Glass Meridian", "steam", {"expiry_date": "2026-07-01T00:00:00"})],
        show_all=True)
    for name in ("Amber Hollow", "Cinder Vale", "Glass Meridian"):
        assert name in text
    assert "keys --all" not in text     # nothing left to point at


def test_an_uncertain_row_prints_what_it_nearly_matched(tmp_path):
    text = _text(tmp_path, [("Starfall Rally Turbo", "steam", None)],
                 show_all=True, library=(("steam", "Starfall Rally"),))
    assert "Starfall Rally Turbo" in text
    assert "~ Starfall Rally" in text


def test_the_report_says_which_stores_it_could_not_check(tmp_path):
    # Without this the reader cannot tell "checked and absent" from
    # "unfalsifiable", which is the difference the third state exists for.
    text = _text(tmp_path, [("Verdant Reach", "uplay", None)], show_all=True)
    assert "no importer" in text
    assert "Verdant Reach" in text


def test_the_report_dates_the_libraries_it_matched_against(tmp_path):
    # An approximate answer from a stale library is the one worth
    # distrusting most, so the answer carries its age.
    text = _text(tmp_path, [("Cinder Vale", "steam", None)])
    assert "Libraries: steam" in text


def test_an_empty_catalog_prints_a_well_formed_report(tmp_path):
    text = _text(tmp_path, [], library=(), imported=())
    assert "0 keys" in text


def test_format_report_degrades_for_a_console_that_cannot_encode(tmp_path):
    # Product names are arbitrary data. cp437 is the Windows console
    # default and cannot encode most of Latin-1, let alone anything above.
    conn = _conn(tmp_path, [("Café of Broken Clocks", "steam", None)])
    try:
        report = keys.report(conn, now=NOW)
    finally:
        conn.close()
    text = keys.format_report(report, encoding="cp437", show_all=True)
    text.encode("cp437")     # must not raise
```

Append to `tests/test_main.py`, which drives the real `main()` against a catalog in `tmp_path` (`sys`, `db` and `main` are already imported there; add `import json` at the top if it is absent):

```python
def _seed_one_key(tmp_path, monkeypatch):
    """A catalog holding a single unactivated steam key."""
    monkeypatch.chdir(tmp_path)
    conn = db.connect("catalog.db")
    conn.execute("INSERT INTO bundles (gamekey, name, url, purchased_at) "
                 "VALUES ('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789', '2024-01-02T00:00:00')")
    conn.execute(
        "INSERT INTO external_keys (gamekey, human_name, key_type, raw) "
        "VALUES ('kv789', 'Cinder Vale', 'steam', ?)",
        (json.dumps({"human_name": "Cinder Vale", "key_type": "steam",
                     "machine_name": "cindervale_ex"}),))
    conn.commit()
    conn.close()


def test_keys_command_prints_the_summary(monkeypatch, tmp_path, capsys):
    _seed_one_key(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "keys"])
    main()
    out = capsys.readouterr().out
    # "1 key", not "1 keys" -- a one-item tier read "1 items" in the bundle
    # preview, which no test caught and a browser did.
    assert "1 key -" in out
    # Undated, so the default report counts it without listing it.
    assert "Cinder Vale" not in out


def test_keys_all_lists_the_undated_rows(monkeypatch, tmp_path, capsys):
    _seed_one_key(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "keys", "--all"])
    main()
    assert "Cinder Vale" in capsys.readouterr().out
```

Note the pluralisation this pins: `format_report`'s summary line must read `"key"` at a total of 1 and `"keys"` otherwise.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_keys.py tests/test_main.py -q`
Expected: FAIL — `AttributeError: module 'humble_catalog.keys' has no attribute 'format_report'`, and the CLI tests fail on an unknown `keys` command.

- [ ] **Step 3: Add `format_report` and `run` to `humble_catalog/keys.py`**

```python
def _line(row, width):
    """One reported row, as a printable line."""
    when = (f"in {row['days_left']} days" if row["days_left"] is not None
            else ("expired" if row["expired"] else ""))
    line = (f"    {when:>12}  {row['product'] or '':<{width}}  "
            f"{row['key_type_label']:<12}  {row['bundle']}")
    if row["near_match"]:
        line += (f"  ~ {row['near_match']['owned_title']}"
                 f" ({row['near_match']['score']:.2f})?")
    if row["state"] == "uncheckable":
        line += "  [no importer]"
    return line.rstrip()


def _block(lines, heading, rows, width):
    if not rows:
        return
    lines.append(f"  {heading} ({len(rows)}):")
    lines.extend(_line(row, width) for row in rows)
    lines.append("")


def format_report(report, encoding="utf-8", show_all=False):
    """The report as printable text, safe for a console using `encoding`.

    The default prints the counts plus only the rows with a live expiry --
    what needs attention this week. `--all` adds the undated and the
    already-expired rows, which together are the great majority: a report
    that leads with 700 lines is one nobody reads to the end.
    """
    counts = report["counts"]
    # "1 key", not "1 keys": a one-item tier read "1 items" in the bundle
    # preview, and no test caught it -- a browser did.
    noun = "key" if report["total"] == 1 else "keys"
    lines = [f"{report['total']:,} {noun} - {counts['matched']:,} in a library, "
             f"{counts['unredeemed'] + counts['uncertain']:,} not, "
             f"{counts['uncheckable']:,} uncheckable", ""]
    rows = report["rows"]
    live = [r for r in rows if r["expires"] and not r["expired"]]
    undated = [r for r in rows if not r["expires"]]
    expired = [r for r in rows if r["expired"]]
    width = max((len(r["product"] or "") for r in rows), default=0)
    _block(lines, "Expiring", live, width)
    if show_all:
        _block(lines, "No expiry date", undated, width)
        _block(lines, "Already expired", expired, width)
    elif undated or expired:
        lines.append(f"  ('keys --all' for the other "
                     f"{len(undated) + len(expired):,}: {len(undated):,} "
                     f"undated, {len(expired):,} already expired)")
        lines.append("")
    libraries = report["libraries"]
    if libraries:
        listed = ", ".join(
            f"{store} {info['count']:,} "
            f"{'game' if info['count'] == 1 else 'games'} "
            f"(imported {info['imported_at'][:10]})"
            for store, info in sorted(libraries.items()))
        lines.append(f"  Libraries: {listed}")
    if counts["uncheckable"]:
        lines.append(f"  {counts['uncheckable']:,} keys are for stores with "
                     f"no importer -- for those, 'in no library' cannot be "
                     f"checked at all.")
    lines.append("  Matching is by title and APPROXIMATE. A revealed key was "
                 "only displayed, which is not the same as activated.")
    # Degraded at the CLI boundary only, exactly as bundle_preview does:
    # the web route keeps the real characters, and product names are
    # arbitrary data that may hold anything.
    return stats.console_safe("\n".join(lines).rstrip(), encoding)


def run(show_all=False):
    """Count and print. The `keys` subcommand's entry point."""
    conn = db.connect()
    try:
        built = report(conn)
    finally:
        conn.close()
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(format_report(built, encoding, show_all=show_all))
```

- [ ] **Step 4: Wire the subcommand in `humble_catalog/__main__.py`**

After the `import-games` subparser (around line 140), add:

```python
    p_keys = sub.add_parser(
        "keys",
        help="Report Humble store keys whose game is in no imported "
             "library -- probably never claimed")
    p_keys.add_argument(
        "--all", action="store_true",
        help="Also list the keys with no expiry date and the ones that "
             "have already expired")
```

And in the dispatch chain, after the `bundle` branch:

```python
    elif args.command == "keys":
        from humble_catalog import keys
        keys.run(show_all=args.all)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_keys.py tests/test_main.py -q`
Expected: PASS.

- [ ] **Step 6: Run it against the real catalog**

Run: `.venv/Scripts/python -m humble_catalog keys`
Expected: the summary line reading `2,275 keys - 1,553 in a library, 624 not, 98 uncheckable`, an `Expiring (63):` block, and the `keys --all` pointer. Confirm nothing raises a `UnicodeEncodeError`.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/keys.py humble_catalog/__main__.py tests/test_keys.py tests/test_main.py
git commit -m "feat(keys): add the 'keys' subcommand"
```

---

### Task 5: `GET /api/keys`

**Files:**
- Modify: `humble_catalog/webapp/__init__.py` (beside `/api/stats`, around line 88-101)
- Test: `tests/test_webapp.py`

**Interfaces:**
- Consumes: `keys.report(conn)`.
- Produces: `GET /api/keys` → the report dict verbatim as JSON.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webapp.py`, next to the `/api/stats` tests:

```python
def test_api_keys_matches_the_report_over_the_same_db(tmp_path):
    # A reshaping of report(), never a second count -- the /api/stats rule.
    dbp = tmp_path / "t.db"
    conn = db.connect(dbp)
    conn.execute("INSERT INTO bundles (gamekey, name, url, purchased_at) "
                 "VALUES ('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789', '2024-01-02T00:00:00')")
    conn.execute(
        "INSERT INTO external_keys (gamekey, human_name, key_type, raw) "
        "VALUES ('kv789', 'Cinder Vale', 'steam', ?)",
        (json.dumps({"human_name": "Cinder Vale", "key_type": "steam",
                     "machine_name": "cindervale_ex"}),))
    conn.commit()
    conn.close()
    client = create_app(db_path=str(dbp)).test_client()

    body = client.get("/api/keys").get_json()
    assert body["total"] == 1
    assert body["counts"]["uncheckable"] == 1     # steam never imported
    assert [r["product"] for r in body["rows"]] == ["Cinder Vale"]


def test_api_keys_of_an_empty_catalog_is_well_formed(tmp_path):
    dbp = tmp_path / "t.db"
    db.connect(str(dbp)).close()
    client = create_app(db_path=str(dbp)).test_client()

    body = client.get("/api/keys").get_json()
    assert body["total"] == 0
    assert body["rows"] == []
    assert set(body["counts"]) == {
        "matched", "unredeemed", "uncertain", "uncheckable"}
```

`json` may already be imported in `tests/test_webapp.py`; check before adding the import.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k api_keys -q`
Expected: FAIL — 404, so `get_json()` returns None.

- [ ] **Step 3: Add the route**

In `humble_catalog/webapp/__init__.py`, add `keys` to the module import line, then add directly beneath `catalog_stats`:

```python
    @app.get("/api/keys")
    def key_report():
        # The same shape keys.report returns, jsonified and nothing more:
        # the CLI and this panel must not be able to disagree, which is the
        # rule /api/stats follows. GET with no parameters -- the report is
        # always the whole key set, so there is nothing to pass, and
        # nothing about the library reaches a query string.
        return jsonify(keys.report(conn()))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "feat(keys): serve the key report at /api/keys"
```

---

### Task 6: The Keys section in the viewer

**Files:**
- Create: `humble_catalog/webapp/static/keys.js`
- Modify: `humble_catalog/webapp/static/index.html` (Keys section at line 132-134; script tags at the bottom)
- Modify: `humble_catalog/webapp/static/app.js:36` (`load()`'s step list) and `:46-51` (`pending`)
- Modify: `humble_catalog/webapp/static/style.css`
- Modify: `tests/js_harness.py:22-27` (`VIEWER_JS`), `tests/js/harness.mjs` (the `publish` block)
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: `GET /api/keys`; `$`, `esc`, `load` from `app.js`.
- Produces: globals `loadKeys()`, `renderKeys()`, `shownKeys()`, `keyStates` (a `Set`), `keysExpiring` (number), `KEY_STATES` (array of `{state, label}`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webapp_js.py`:

```python
_KEY_PAYLOAD = """{
  total: 4, reported: 3, expiring: 1,
  counts: {matched: 1, unredeemed: 1, uncertain: 1, uncheckable: 1},
  libraries: {steam: {count: 2, imported_at: "2026-07-25T00:00:00"}},
  rows: [
    {product: "Amber Hollow", machine_name: "amberhollow_ex", gamekey: "kv789",
     store: "steam", key_type_label: "Steam",
     bundle: "Humble Game Bundle: Expiring Keys",
     purchased_at: "2024-01-02T00:00:00", expires: "2026-08-11T00:00:00+00:00",
     expired: false, days_left: 12, revealed: true, state: "unredeemed",
     near_match: null},
    {product: "Starfall Rally Turbo", machine_name: "srt_ex", gamekey: "kv789",
     store: "steam", key_type_label: "Steam",
     bundle: "Humble Game Bundle: Key Vault", purchased_at: null,
     expires: null, expired: false, days_left: null, revealed: false,
     state: "uncertain", near_match: {owned_title: "Starfall Rally", score: 0.86}},
    {product: "Verdant Reach", machine_name: "verdantreach_ex", gamekey: "kv789",
     store: "uplay", key_type_label: "Uplay",
     bundle: "Humble Game Bundle: Key Vault", purchased_at: null,
     expires: null, expired: false, days_left: null, revealed: false,
     state: "uncheckable", near_match: null}
  ]
}"""


def _with_keys(expression):
    """Run `expression` after loadKeys() has consumed the payload above."""
    return eval_js("""(async () => {
      app.setFetch(async () => ({json: async () => %s}));
      await app.loadKeys();
      return (%s);
    })()""" % (_KEY_PAYLOAD, expression))


def test_the_keys_panel_lists_the_reported_rows():
    html = _with_keys('(app.renderKeys(), dom.writes["#keys-panel"])')
    assert "Amber Hollow" in html
    assert "Humble Game Bundle: Expiring Keys" in html


def test_an_uncertain_row_shows_what_it_nearly_matched():
    html = _with_keys('(app.renderKeys(), dom.writes["#keys-panel"])')
    assert "Starfall Rally" in html


def test_uncheckable_rows_are_hidden_by_default():
    # The default view is the falsifiable one: a store with no importer
    # cannot be checked, so its keys are not evidence of anything.
    shown = _with_keys('app.shownKeys().map((r) => r.product)')
    assert shown == ["Amber Hollow", "Starfall Rally Turbo"]


def test_a_state_chip_toggles_its_rows():
    shown = _with_keys("""(() => {
      app.setKeyStates(["uncheckable"]);
      return app.shownKeys().map((r) => r.product);
    })()""")
    assert shown == ["Verdant Reach"]


def test_the_keys_badge_counts_expiring_rows_not_unredeemed_ones():
    # 547 unredeemed keys would light the tab permanently, which is the
    # policy shell.js already settled against for Library. Expiring keys
    # are a queue; unredeemed ones are a standing fact.
    written = _with_keys("""(() => {
      dom.reset();
      app.setPending({keys: app.keysExpiring()});
      app.renderBadges();
      return dom.writes["#tab-keys .badge-count:text"];
    })()""")
    assert written == "1"


def test_the_keys_section_markup_exists():
    html = (Path(__file__).parent.parent / "humble_catalog" / "webapp"
            / "static" / "index.html").read_text(encoding="utf-8")
    assert '<div id="keys-panel"></div>' in html
    assert '<script src="/static/keys.js"></script>' in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k key -q`
Expected: FAIL — `app.loadKeys is not a function`.

- [ ] **Step 3: Create `humble_catalog/webapp/static/keys.js`**

```js
// The Keys section: Humble store keys whose game is in no imported
// library. Everything here reads /api/keys and nothing else -- the report
// is computed server-side by keys.py so this panel and the CLI cannot
// disagree, which is the same arrangement the statistics panel uses.
//
// Deliberately does NOT reuse catalog.js's chip-filter registry, sort or
// fuzzy search. All three are bound to the shared `items` array, and two
// views needing different column sets is the whole reason sections exist.

// The reported states, in display order, each doubling as its own chip.
// `matched` is absent on purpose: the server never sends it.
const KEY_STATES = [
  {state: "unredeemed",  label: "Not in a library"},
  {state: "uncertain",   label: "Near match"},
  {state: "uncheckable", label: "No importer"},
];

let keyRows = [], keyCounts = {}, keyLibraries = {}, keyTotal = 0;
// uncheckable is off by default: for those stores "not in any library" is
// unfalsifiable, so leaving them in would make the list mostly caveat.
let keyStates = new Set(["unredeemed", "uncertain"]);

const keysExpiring = () =>
  keyRows.filter((r) => r.expires && !r.expired).length;

const shownKeys = () => keyRows.filter((r) => keyStates.has(r.state));

function setKeyStates(states) {
  keyStates = new Set(states);
}

async function loadKeys() {
  const data = await (await fetch("/api/keys")).json();
  keyRows = data.rows || [];
  keyCounts = data.counts || {};
  keyLibraries = data.libraries || {};
  keyTotal = data.total || 0;
  renderKeys();
}

// Whole days from an ISO timestamp, so a row's urgency is computed in the
// browser rather than frozen at whatever moment the page was loaded.
function keyWhen(row) {
  if (!row.expires) return "";
  if (row.expired) return "expired";
  const days = Math.floor(
    (new Date(row.expires) - Date.now()) / 86400000);
  return days <= 0 ? "today" : `in ${days} days`;
}

function renderKeys() {
  const rows = shownKeys();
  const chips = KEY_STATES.map((s) => `<button class="key-chip${
    keyStates.has(s.state) ? " on" : ""}" data-state="${s.state}">${
    esc(s.label)} ${keyCounts[s.state] || 0}</button>`).join("");
  const libraries = Object.entries(keyLibraries).map(
    ([store, info]) => `${esc(store)} ${info.count} (imported ${
      esc((info.imported_at || "").slice(0, 10))})`).join(", ");
  $("#keys-panel").innerHTML = `
    <p class="keys-summary">${keyTotal} keys - ${keyCounts.matched || 0} in a
      library, ${rows.length} shown.
      Matching is by title and <strong>approximate</strong>; a revealed key
      was only displayed, which is not the same as activated.</p>
    <div id="key-chips">${chips}</div>
    ${libraries ? `<p class="keys-libraries">Libraries: ${libraries}</p>` : ""}
    <table id="key-table"><thead><tr>
      <th>Product</th><th>Store</th><th>Bundle</th><th>Purchased</th>
      <th>Expires</th><th>Revealed</th><th>State</th>
    </tr></thead><tbody>${rows.map((r) => `<tr class="key-${r.state}">
      <td>${esc(r.product || "")}${r.near_match
        ? ` <span class="key-near">~ ${esc(r.near_match.owned_title)} (${
            r.near_match.score.toFixed(2)})?</span>` : ""}</td>
      <td>${esc(r.key_type_label || "")}</td>
      <td>${esc(r.bundle || "")}</td>
      <td>${esc((r.purchased_at || "").slice(0, 10))}</td>
      <td>${esc(keyWhen(r))}</td>
      <td>${r.revealed ? "yes" : "no"}</td>
      <td>${esc((KEY_STATES.find((s) => s.state === r.state) || {}).label
                || r.state)}</td>
    </tr>`).join("")}</tbody></table>`;
}

// One delegated listener rather than one per chip, because renderKeys()
// rebuilds the whole panel through innerHTML and per-chip listeners would
// be detached on every redraw.
$("#keys-panel").addEventListener("click", (ev) => {
  const chip = ev.target.closest?.(".key-chip");
  if (!chip) return;
  const state = chip.dataset.state;
  if (keyStates.has(state)) keyStates.delete(state); else keyStates.add(state);
  renderKeys();
});
```

- [ ] **Step 4: Wire it into `index.html`**

Replace lines 132-134:

```html
  <section id="section-keys" hidden>
    <p class="section-empty">The unredeemed key report will live here.</p>
  </section>
```

with:

```html
  <section id="section-keys" hidden>
    <div id="keys-panel"></div>
  </section>
```

And add the script tag between `maintenance.js` and `bundles.js`:

```html
<script src="/static/keys.js"></script>
```

- [ ] **Step 5: Wire it into `load()` in `app.js`**

Change the step list on line 36 from:

```js
  for (const step of [render, loadReview, loadDupes, refreshStats]) {
```

to:

```js
  for (const step of [render, loadReview, loadDupes, refreshStats, loadKeys]) {
```

and the `pending` object's `keys` line from `keys: 0,` to:

```js
    // Expiring keys, NOT the unredeemed count: see badgeCount in shell.js.
    // Unredeemed keys number in the hundreds and never reach zero, which
    // is exactly the always-lit badge that policy rules out.
    keys: keysExpiring(),
```

- [ ] **Step 6: Add the CSS**

Append to `humble_catalog/webapp/static/style.css`:

```css
/* ---- Keys section ---- */
.keys-summary, .keys-libraries { opacity: .8; font-size: .9em; }
#key-chips { display: flex; flex-wrap: wrap; gap: .3rem; margin: .5rem 0; }
.key-chip { cursor: pointer; font-size: .85em; }
.key-chip.on { outline: 2px solid var(--accent); }
#key-table { width: 100%; border-collapse: collapse; }
#key-table th, #key-table td { text-align: left; padding: .25rem .5rem; }
/* Same custom property as the catalog's zebra rows (see the
   `#catalog tbody tr:nth-child(even)` rule), so both tables stripe
   identically in light and dark. */
#key-table tbody tr:nth-child(even) { background: var(--surface-alt); }
.key-near { opacity: .7; font-size: .85em; }
.key-uncheckable td { opacity: .75; }
```

- [ ] **Step 7: Teach the test harness about the new script**

In `tests/js_harness.py`, add `keys.js` to `VIEWER_JS` in load order:

```python
VIEWER_JS = [_STATIC / "app.js", _STATIC / "catalog.js",
             _STATIC / "maintenance.js", _STATIC / "keys.js",
             _STATIC / "bundles.js", _STATIC / "shell.js"]
```

In `tests/js/harness.mjs`, add to the `publish` block (after the `previewBundle` line):

```js
  loadKeys, renderKeys, shownKeys, KEY_STATES, setKeyStates,
  keysExpiring: () => keysExpiring(),
  setKeyRows: (v) => { keyRows = v; },
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -q`
Expected: PASS — including every pre-existing test, since adding a script to the concatenation must not disturb them.

- [ ] **Step 9: Verify it in a real browser**

The JS harness has a stubbed DOM with no computed styles and cannot see a layout bug — three shipped bugs in this project's history were invisible to it and caught in a browser. So:

1. Start the viewer with the `preview_start` tool (add a `.claude/launch.json` entry running `.venv/Scripts/python -m humble_catalog serve` on port 8087 if none exists).
2. Navigate to `http://localhost:8087/#/keys`.
3. Confirm: the table renders, the three chips toggle rows, the Keys tab shows a badge of 63, and the panel does not scroll the page body horizontally.
4. Check `read_console_messages` for errors.

- [ ] **Step 10: Commit**

```bash
git add humble_catalog/webapp/static/keys.js humble_catalog/webapp/static/index.html humble_catalog/webapp/static/app.js humble_catalog/webapp/static/style.css tests/js_harness.py tests/js/harness.mjs tests/test_webapp_js.py
git commit -m "feat(viewer): fill the Keys section with the key report"
```

---

### Task 7: Documentation, invented test data, and final verification

**Files:**
- Modify: `docs/TEST-DATA.md`, `docs/BACKLOG.md`, `README.md`
- Modify: `docs/superpowers/specs/2026-07-30-unredeemed-key-report-design.md` (one sentence)

- [ ] **Step 1: Add the two new invented names to `docs/TEST-DATA.md`**

Both were vetted against `leak_check.build_terms()` during design. Add to the **Owned game libraries** table:

```markdown
| Amber Hollow | — (keyed only) | held as a Humble **steam** key carrying a live `expiry_date`; the key-report row that can still be lost |
| Glass Meridian | — (keyed only) | held as a Humble **steam** key whose `expiry_date` has passed; the key-report row that was lost |
```

And to the **Bundles** table:

```markdown
| Humble Game Bundle: Expiring Keys | an order whose keys carry expiry dates; key-report sort-order example |
```

- [ ] **Step 2: Verify the new names are still clean**

Run:
```bash
.venv/Scripts/python -c "import sys; sys.path.insert(0,'scripts'); import leak_check; t=leak_check.build_terms(); print([n for n in ['amber hollow','glass meridian','humble game bundle: expiring keys'] if any(x in n for x in t)] or 'clean')"
```
Expected: `clean`

- [ ] **Step 3: Move the backlog entry to Done**

In `docs/BACKLOG.md`, delete the **Unredeemed key report** bullet from the `### External keys` section and add to the top of the **Done** list:

```markdown
- **Unredeemed key report** —
  `docs/superpowers/specs/2026-07-30-unredeemed-key-report-design.md`.
  `keys` (and the viewer's Keys section) lists the Humble store keys whose
  game appears in no imported store library — 624 of 2,275, with 98 more
  for stores that have no importer and therefore cannot be checked at all.
  Read-only: no schema change, no migration, no writes.
  Four measurements changed the plan this entry recorded.
  `num_days_until_expired` turned out not to be a sentinel to be
  distrusted but a redundant column to ignore: it reads `-1` on the 1,782
  keys with no expiry, `0` on exactly the 111 flagged `is_expired`, and a
  positive number on the remaining 382 — 382+111 being precisely the set
  carrying `expiry_date`, which is the only absolute one of the three and
  the only one read. `key_type` carries 12 clean machine values beside
  `key_type_human_name`'s 52, so deriving the store from it sidesteps the
  case folding this entry expected to need and leaves `Other`/`other` a
  cosmetic wart on a label. Checkability is derived from `game_imports`
  rather than hardcoded to steam/gog/epic, so a machine that has never
  imported a store reports its keys there as uncheckable instead of
  falsely unredeemed.
  Matching is scoped to the key's **own** store, unlike
  `bundle_preview`'s pooled libraries — a steam key whose game sits only
  in GOG is still an unactivated steam key. Worth 59 keys, and the reason
  `classify_game` and its two cutoffs moved to a shared `game_match.py`:
  the two callers treat the 80–92 band oppositely on purpose. There a
  `possible` is excluded, because the expensive mistake is a second
  purchase; here it is listed and annotated, because the expensive mistake
  is a key that quietly expires.
  Sorting is three groups rather than one ascending column — live expiry
  soonest first, then undated, then expired most-recent-first. Plain
  ascending puts the 40 dead rows above the 63 that can still be lost,
  which is the opposite of what this entry asked for.
  The badge counts expiring keys, not unredeemed ones: 624 never reaches
  zero, and `shell.js` had already settled that an always-lit badge costs
  the badge beside it its meaning.
```

- [ ] **Step 4: Amend the hiding entry with what was learned**

In `docs/BACKLOG.md`, under **Hiding a resolved row**, replace the "Keyed on the tpk's own `machine_name`" bullet's claim with the measured correction:

```markdown
  - **Keyed on `(gamekey, machine_name)`**, not on `machine_name` alone.
    Measured 2026-07-30: 2,275 keys hold only 2,117 distinct
    `machine_name`s, because 128 games are keyed in more than one bundle —
    so a `machine_name`-keyed table would hide both rows and contradict
    this entry's own closing note that the hide is per key, not per game.
    The pair is unique across all 2,275. It needs either `json_extract` at
    query time or a `machine_name` column added to `external_keys`.
  - **Fix `external_keys`'s primary key in the same migration.** It is
    `(gamekey, human_name)`, and `raw_orders` holds 2,278 tpks against the
    table's 2,275: three orders carry two keys under one display name, and
    the third is silently dropped. `(gamekey, machine_name)` is the key
    both problems want, so it should be migrated once rather than twice.
```

- [ ] **Step 5: Document the feature in `README.md`**

In the four-sections paragraph (around line 22-30), the bare `**Keys**` gains its description. Change:

```
**Maintenance** (the review queue and possible duplicates), **Keys**, and
**Bundles** (paste a bundle URL to see what you already own).
```

to:

```
**Maintenance** (the review queue and possible duplicates), **Keys**
(store keys whose game is in none of your imported libraries), and
**Bundles** (paste a bundle URL to see what you already own).
```

Then add a command entry immediately after the `import-games` bullet (which ends the command list around line 272), matching the surrounding voice — second person, a dash after the command, limits stated rather than softened:

```markdown
- `python -m humble_catalog keys` - list the store keys from past
  bundles whose game appears in none of the libraries you have imported:
  what you have paid for and, as far as this can tell, never claimed. It
  prints the counts and the keys with an expiry date still ahead of them,
  which are the ones you can still lose; `--all` adds the undated ones
  and the ones already expired. A key is matched only against **its own
  store** - a Steam key whose game sits in your GOG library is still an
  unactivated Steam key - and the match is **by title and approximate**,
  the same warning `bundle` carries, so treat a row as somewhere to look
  rather than as a verdict. Keys for stores with no importer (Uplay,
  Paizo, DriveThruRPG and a long tail below them) are reported apart and
  never counted as unclaimed: with no library to check against, "not in
  any library" cannot be true or false there. Note also that Humble marks
  a key redeemed the moment its value is *revealed*, which says nothing
  about whether the game ever reached a store account - which is why the
  report matches libraries instead of trusting that flag. Read-only:
  nothing is written to the catalog.
```

- [ ] **Step 6: Reconcile one sentence in the spec**

The spec says `machine_name` is read "via `json_extract`". The implementation parses the blob in Python instead — one parse yields four fields where SQL would need four calls, and a non-JSON blob skips its row rather than failing the query. Edit that sentence in `docs/superpowers/specs/2026-07-30-unredeemed-key-report-design.md` to say the blob is parsed in Python, with that reason, so the spec and the code agree.

- [ ] **Step 7: Run the full verification**

```bash
.venv/Scripts/python -m pytest -q
```
Expected: PASS, with no test edited to survive this change.

```bash
.venv/Scripts/python scripts/leak_check.py
```
Expected: `clean`

```bash
.venv/Scripts/python scripts/check_no_data_tracked.py
```
Expected: `clean`

If `leak_check` reports a term that is ordinary English matching as a **substring** of your prose, reword the prose. Do not add a real library title to `ALLOWED` — that permanently blinds the check to a genuine leak of it.

- [ ] **Step 8: Commit**

```bash
git add docs README.md
git commit -m "docs(keys): record the key report and what measuring changed"
```

---

## Verification Summary

| Claim | How it is checked |
|---|---|
| States partition every key | `test_the_four_states_partition_every_key` |
| Uncheckable is never reported as unredeemed | `test_a_key_for_a_store_with_no_importer_is_never_unredeemed` |
| Same-store scope | `test_a_game_owned_only_on_another_store_still_reports_unredeemed` |
| Three sort groups | `test_rows_sort_live_expiry_then_undated_then_expired` and its two siblings |
| CLI default vs `--all` | `test_the_default_prints_only_the_rows_that_can_still_be_lost`, `test_all_prints_the_undated_and_expired_rows_too` |
| Route cannot drift from the counter | `test_api_keys_matches_the_report_over_the_same_db` |
| Badge counts expiring, not unredeemed | `test_the_keys_badge_counts_expiring_rows_not_unredeemed_ones` |
| Layout actually works | Task 6 Step 9, in a real browser |
| Nothing private committed | `leak_check.py` and `check_no_data_tracked.py` in Task 7 |
| Real-catalog numbers match the spec | Task 2 Step 5 and Task 3 Step 5 |
