# Humble Choice ownership check — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `choice` command and viewer panel answering "how much of this month's Humble Choice do I already own?", the Choice counterpart to the existing `bundle` check.

**Architecture:** A new `humble_catalog/choice_preview.py` split at the network seam exactly as `bundle_preview.py` is — `fetch_choice()` does the authenticated HTTP, `preview()` is pure and testable from a committed fixture. Game ownership is decided by title through the existing `game_match` cutoffs, against imported libraries and unclaimed Humble keys. The pool builders those two modules share move into `game_match` first, so neither module reaches into the other's private names.

**Tech Stack:** Python 3, `pytest`, `rapidfuzz`, `requests`, Flask (viewer), vanilla JS (viewer panel, tested through the node harness in `tests/js_harness.py`).

**Spec:** `docs/superpowers/specs/2026-08-04-humble-choice-check-design.md`

## Global Constraints

- **Privacy is non-negotiable.** Every committed fixture, test, doc and commit message uses invented names only, drawn from `docs/TEST-DATA.md`. Never paste a real owned title anywhere. New invented names must be added to `docs/TEST-DATA.md` in the same commit that first uses them.
- **Run `.venv/Scripts/python scripts/leak_check.py` directly** after any commit that adds tests, fixtures or docs naming books, bundles or people. Never pipe it — its exit status is the result. It matches substrings, so it can flag ordinary prose; reword the prose rather than weakening the check.
- **The full gate is `.\scripts\windows\verify.ps1`** (tests + both privacy checks). It must pass before the branch is considered done.
- **`preview()` is pure**: no network, no writes to `catalog.db`, ever.
- **Every read of the fetched blob goes through `humble_catalog.shapes`.** It is third-party content. Use `shapes.text_list` for list-of-string fields, never `as_list` — a list field arriving as a bare string is one name, never its characters.
- **`possible` is counted as neither owned nor new.** `owned + possible + new == total` must hold in every test.
- Work on branch `humble-choice-check` (already created, spec already committed).
- Python: use the repo venv, `.venv/Scripts/python`. `.venv/Scripts/pip` is broken — use `python -m pip` if a dependency is ever needed (none is).

---

## File Structure

| File | Responsibility |
|---|---|
| `humble_catalog/game_match.py` | **Modified.** Gains `owned_games(conn)` and `keyed_games(conn)`, moved from `bundle_preview`. Already owns the ownership cutoffs; now owns the pools too. |
| `humble_catalog/bundle_preview.py` | **Modified.** Calls the moved helpers; `_SYMBOLS` promoted to `SYMBOLS` so `choice_preview` can share one currency table. |
| `humble_catalog/choice_preview.py` | **Created.** `fetch_choice`, `preview`, `format_report`, `run`. The whole feature's logic. |
| `humble_catalog/humble_api.py` | **Modified.** `_wait()` extracted from `_get`; new `get_page(path)` for HTML. |
| `humble_catalog/__main__.py` | **Modified.** The `choice` subcommand. |
| `humble_catalog/webapp/__init__.py` | **Modified.** `POST /api/choice-preview`. |
| `humble_catalog/webapp/static/bundles.js` | **Modified.** The Choice panel joins the Bundles section it belongs to. Already in the JS harness's script list, so no harness change. |
| `humble_catalog/webapp/static/index.html` | **Modified.** Button and panel div in `#section-bundles`. |
| `tests/fixtures/choice_hub.json` | **Created.** The hub blob `preview()` consumes. |
| `tests/fixtures/choice_page.html` | **Created.** Minimal page wrapping it, for the parse test. |
| `tests/test_choice_preview.py` | **Created.** Counting, formatting and fetch tests. |
| `docs/TEST-DATA.md` | **Modified.** The invented month and any new rows. |
| `README.md`, `docs/BACKLOG.md` | **Modified.** Document the command; record what was left out. |

---

### Task 1: Move the shared ownership pools into `game_match`

Pure refactor, no behaviour change. Doing it first means `choice_preview` never imports another module's underscore names.

**Files:**
- Modify: `humble_catalog/game_match.py` (append after `classify_game`)
- Modify: `humble_catalog/bundle_preview.py:176-231` (delete both functions), `:249`, `:254`
- Test: `tests/test_bundle_preview.py` (unchanged — it must still pass untouched)

**Interfaces:**
- Consumes: nothing.
- Produces: `game_match.owned_games(conn) -> [(normalized_title, display_title)]` and `game_match.keyed_games(conn) -> [(normalized_title, display_title, key_type, bundle_name)]`.

- [ ] **Step 1: Confirm the suite is green before touching anything**

Run: `.venv/Scripts/python -m pytest tests/test_bundle_preview.py tests/test_game_match.py -q`
Expected: PASS (this is the baseline the refactor must preserve)

- [ ] **Step 2: Move both functions into `game_match.py`**

Cut `_owned_games` and `_keyed_games` from `bundle_preview.py` (lines 176-231, including their docstrings — the docstrings carry the reasoning and must survive the move intact) and paste them at the end of `game_match.py`, renamed without the leading underscore. `game_match.py` needs `from humble_catalog.titles import clean_game_title` — it already imports `clean_game_title` at line 24, so no new import.

```python
def owned_games(conn):
    """[(normalized_title, display_title)] across every imported store.

    Deduped on the normalized title, so a game owned on two stores is one
    row here and can only be counted once.
    """
    rows = conn.execute(
        "SELECT normalized_title, title FROM games "
        "ORDER BY normalized_title").fetchall()
    seen, out = set(), []
    for row in rows:
        if row["normalized_title"] and row["normalized_title"] not in seen:
            seen.add(row["normalized_title"])
            out.append((row["normalized_title"], row["title"]))
    return out
```

Paste `keyed_games` the same way, keeping its full docstring (the expired-key paragraph is the reasoning most likely to be "simplified" away later).

- [ ] **Step 3: Point `bundle_preview` at the moved names**

In `bundle_preview.py`, change the import line 20 and the two call sites:

```python
from humble_catalog.game_match import (classify_game, keyed_games,
                                       owned_games, prepare_pool)
```

```python
    games = prepare_pool(owned_games(conn))
```

```python
    keyed = keyed_games(conn)
```

- [ ] **Step 4: Run the full suite — the refactor must be invisible**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS, same count as Step 1's baseline plus the rest of the suite. Any failure here is the refactor, not the feature.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/game_match.py humble_catalog/bundle_preview.py
git commit -m "refactor: move the game-ownership pools into game_match

game_match already owns the cutoffs and the Pool type; it now owns the
two queries that build the pools. The Choice check is a third caller and
would otherwise have to import another module's private names."
```

---

### Task 2: Fixture, test data, and the three-way partition

**Files:**
- Create: `tests/fixtures/choice_hub.json`
- Create: `humble_catalog/choice_preview.py`
- Create: `tests/test_choice_preview.py`
- Modify: `docs/TEST-DATA.md`

**Interfaces:**
- Consumes: `game_match.owned_games`, `game_match.prepare_pool`, `game_match.classify_game` (Task 1).
- Produces: `choice_preview.preview(conn, hub) -> dict` with keys `name`, `price`, `currency`, `total`, `owned`, `possible`, `new`, `owned_items` (list of str), `possible_items` (list of dict), `new_items` (list of str).

- [ ] **Step 1: Add the invented names to `docs/TEST-DATA.md`**

In the "Owned game libraries (Steam / Heroic imports)" table, append:

```markdown
| Humble Choice: January 2031 | — | invented Choice month for the choice-preview fixture (`choice_hub.json`); an invented future month so it can never collide with a real one |
```

- [ ] **Step 2: Write the fixture `tests/fixtures/choice_hub.json`**

Six games chosen so every branch of the classifier is exercised exactly once: an outright library match, an edition suffix over an owned base, a sequel foil, the ambiguous band, a plain new title, and a game held only as a key. `delivery_methods` is set so `gog` is the one unimported store with an unmatched item, and `other-key` rides along on a `new` game to prove it is excluded from that warning.

```json
{
  "baseSubscriptionPrice|money": {"currency": "EUR", "amount": 11.99},
  "contentChoiceOptions": {
    "gamekey": "choicejan2031",
    "title": "January 2031",
    "contentChoiceState": {"initial": {"choices_made": []}},
    "contentChoiceData": {
      "display_order": [
        "widgetquest2_choice", "neondrifter_choice", "cindervale_choice",
        "widgetquest_de_choice", "starfallrallyturbo_choice",
        "lanternlockpick_choice"
      ],
      "extras": [
        {"human_name": "Sample Ambience Pack",
         "machine_name": "ambiencepack_choice", "class": "coupon",
         "icon_path": "https://example.invalid/ambience.png", "types": []},
        {"human_name": "Bonus Wallpaper",
         "machine_name": "bonuswallpaper_choice", "class": "coupon",
         "icon_path": "https://example.invalid/wallpaper.png", "types": []}
      ],
      "game_data": {
        "neondrifter_choice": {
          "title": "Neon Drifter",
          "display_item_machine_name": "neondrifter_choice_di",
          "delivery_methods": ["steam"], "tpkds": [],
          "msrp|money": {"currency": "EUR", "amount": 19.99}},
        "widgetquest_de_choice": {
          "title": "Widget Quest: Definitive Edition",
          "display_item_machine_name": "widgetquest_de_choice_di",
          "delivery_methods": ["steam"], "tpkds": [],
          "msrp|money": {"currency": "EUR", "amount": 24.99}},
        "widgetquest2_choice": {
          "title": "Widget Quest II",
          "display_item_machine_name": "widgetquest2_choice_di",
          "delivery_methods": ["steam", "other-key"], "tpkds": [],
          "msrp|money": {"currency": "EUR", "amount": 29.99}},
        "starfallrallyturbo_choice": {
          "title": "Starfall Rally Turbo",
          "display_item_machine_name": "starfallrallyturbo_choice_di",
          "delivery_methods": ["steam"], "tpkds": [],
          "msrp|money": {"currency": "EUR", "amount": 14.99}},
        "lanternlockpick_choice": {
          "title": "Lantern & Lockpick",
          "display_item_machine_name": "lanternlockpick_choice_di",
          "delivery_methods": ["gog"], "tpkds": [],
          "msrp|money": {"currency": "EUR", "amount": 9.99}},
        "cindervale_choice": {
          "title": "Cinder Vale",
          "display_item_machine_name": "cindervale_choice_di",
          "delivery_methods": ["steam"], "tpkds": [],
          "msrp|money": {"currency": "EUR", "amount": 12.99}}
      }
    }
  }
}
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_choice_preview.py`:

```python
import json
from pathlib import Path

from humble_catalog import choice_preview, db, import_games, titles

FIXTURES = Path(__file__).parent / "fixtures"


def _hub():
    return json.loads((FIXTURES / "choice_hub.json").read_text(encoding="utf-8"))


def _conn(tmp_path):
    """A catalog with a small imported steam library and one keyed game.

    Widget Quest is the base the Definitive Edition must match and the
    sequel must NOT. Starfall Rally is the foil that puts Starfall Rally
    Turbo in the ambiguous band. Cinder Vale exists only as an
    unactivated Humble key, so it is in no imported library.
    """
    conn = db.connect(tmp_path / "catalog.db")
    import_games.store_games(conn, "steam", [
        {"store_id": sid, "title": t,
         "normalized_title": titles.clean_game_title(t),
         "source_timestamp": None}
        for sid, t in (("440", "Widget Quest"), ("220", "Neon Drifter"),
                       ("330", "Starfall Rally"))], "test")
    conn.execute("INSERT INTO bundles (gamekey, name, url) VALUES "
                 "('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789')")
    conn.execute(
        "INSERT INTO external_keys "
        "(gamekey, machine_name, human_name, key_type, raw) "
        "VALUES ('kv789', 'cindervale_steam', 'Cinder Vale', 'steam', ?)",
        (json.dumps({"human_name": "Cinder Vale", "key_type": "steam"}),))
    conn.commit()
    return conn


def _report(tmp_path):
    conn = _conn(tmp_path)
    try:
        return choice_preview.preview(conn, _hub())
    finally:
        conn.close()


def test_preview_reports_the_month_and_its_price(tmp_path):
    report = _report(tmp_path)
    assert report["name"] == "Humble Choice: January 2031"
    assert report["price"] == 11.99
    assert report["currency"] == "EUR"


def test_owned_possible_and_new_partition_the_month(tmp_path):
    # The invariant the whole report rests on: `possible` is counted as
    # neither owned nor new, so the three must still sum to the total.
    report = _report(tmp_path)
    assert report["total"] == 6
    assert report["owned"] + report["possible"] + report["new"] == 6


def test_an_edition_suffix_over_an_owned_base_reads_as_owned(tmp_path):
    assert "Widget Quest: Definitive Edition" in _report(tmp_path)["owned_items"]


def test_a_sequel_reads_as_new_and_never_as_the_owned_base(tmp_path):
    # Every fuzzy scorer rates "Widget Quest" and "Widget Quest II" as
    # near-identical, and they are the one near-identical pair that is
    # definitely a different product.
    report = _report(tmp_path)
    assert "Widget Quest II" in report["new_items"]
    assert "Widget Quest II" not in report["owned_items"]


def test_the_ambiguous_band_is_counted_as_neither_owned_nor_new(tmp_path):
    report = _report(tmp_path)
    offered = [p["offered"] for p in report["possible_items"]]
    assert offered == ["Starfall Rally Turbo"]
    assert "Starfall Rally Turbo" not in report["owned_items"]
    assert "Starfall Rally Turbo" not in report["new_items"]


def test_a_title_owned_nowhere_reads_as_new(tmp_path):
    assert "Lantern & Lockpick" in _report(tmp_path)["new_items"]


def test_lists_are_sorted_case_insensitively_not_left_in_display_order(
        tmp_path):
    # display_order is Humble's marketing decision. This list gets
    # scanned -- "is the one I want in here?" -- so it sorts.
    report = _report(tmp_path)
    assert report["new_items"] == sorted(report["new_items"], key=str.lower)
    assert report["owned_items"] == sorted(report["owned_items"], key=str.lower)


def test_an_empty_catalog_reports_every_game_as_new(tmp_path):
    # The dangerous case: an empty games table must not read as "owns none
    # of it" by accident and must not crash.
    conn = db.connect(tmp_path / "empty.db")
    try:
        report = choice_preview.preview(conn, _hub())
    finally:
        conn.close()
    assert (report["total"], report["owned"], report["new"]) == (6, 0, 6)


def test_preview_survives_a_hub_that_is_not_the_expected_shape(tmp_path):
    # The blob is third-party content. A garbage payload must report a
    # month selling nothing, not raise out of a viewer route.
    conn = db.connect(tmp_path / "empty.db")
    try:
        report = choice_preview.preview(conn, {"contentChoiceOptions": "nope"})
    finally:
        conn.close()
    assert report["total"] == 0
    assert report["name"] == "Humble Choice"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -q`
Expected: FAIL — `ImportError: cannot import name 'choice_preview'`

- [ ] **Step 5: Write `humble_catalog/choice_preview.py`**

```python
"""Preview how much of this month's Humble Choice the catalog already holds.

Read-only throughout: nothing here writes to catalog.db. The report is a
question the owner asks before buying, not a fact about the library.

Split at the network seam -- fetch_choice() does the HTTP, preview() is
pure -- so every counting rule is testable from a committed fixture with
no network and no Humble session. Same split, and same reason, as
bundle_preview and harvest.

Unlike a bundle, a Choice month cannot be read exactly. A bundle re-sells
the SAME subproduct, so machine_name is a shared id and ownership is a set
intersection. Choice negotiates fresh games every month, so its ids never
collide with anything already stored -- measured during design: zero of
nine offered games matched by any id the blob carries. Ownership is
therefore decided by TITLE, and the report says so out loud.
"""
from humble_catalog import shapes
from humble_catalog.game_match import (classify_game, keyed_games,
                                       owned_games, prepare_pool)


def _month(hub):
    """(contentChoiceOptions, contentChoiceData) from a parsed hub blob.

    Both through shapes: this is the parsed page, which the envelope
    classes adversarial, and `x or {}` is not a type check -- a non-empty
    list is truthy and would reach the attribute access.
    """
    opts = shapes.as_mapping(shapes.as_mapping(hub).get("contentChoiceOptions"))
    return opts, shapes.as_mapping(opts.get("contentChoiceData"))


def preview(conn, hub):
    """The ownership report for one parsed subscriber-hub blob.

    Pure: no network, no writes. `hub` is what fetch_choice returns -- the
    whole blob, not the month, because the price sits at its top level and
    the month does not carry it.

    Every game gets exactly one verdict. `possible` is the band where the
    tool declines to guess and is counted as NEITHER owned nor new: the
    expensive mistake here is recommending a second purchase.
    """
    opts, month = _month(hub)
    offered = shapes.as_mapping(month.get("game_data"))
    library = prepare_pool(owned_games(conn))

    owned_items, possible_items, new_items = [], [], []
    for machine_name, entry in offered.items():
        entry = shapes.as_mapping(entry)
        # Falls back to the machine_name so counting stays exhaustive even
        # for an entry the page failed to title. A machine_name is not a
        # title, but a missing row would be a wrong count.
        title = shapes.as_text(entry.get("title")) or machine_name
        verdict, match = classify_game(title, library)
        if verdict == "owned":
            owned_items.append(title)
        elif verdict == "possible":
            possible_items.append(match)
        else:
            new_items.append(title)

    money = shapes.as_mapping(hub.get("baseSubscriptionPrice|money"))
    title = shapes.as_text(opts.get("title"))
    return {
        "name": f"Humble Choice: {title}" if title else "Humble Choice",
        # as_number, not a bare get: the amount is formatted with `:.2f`
        # downstream, so a string here must raise at the read that
        # accepted it rather than inside the report.
        "price": shapes.as_number(money.get("amount")) or 0.0,
        "currency": shapes.as_text(money.get("currency")) or "USD",
        "total": len(offered),
        "owned": len(owned_items),
        "possible": len(possible_items),
        "new": len(new_items),
        "owned_items": sorted(owned_items, key=str.lower),
        "possible_items": sorted(possible_items,
                                 key=lambda p: p["offered"].lower()),
        "new_items": sorted(new_items, key=str.lower),
    }
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -q`
Expected: PASS, 9 tests. If `test_owned_possible_and_new_partition_the_month` fails, a game got two verdicts or none — fix the branch, never the assertion.

- [ ] **Step 7: Run the privacy check**

Run: `.venv/Scripts/python scripts/leak_check.py`
Expected: `clean`

- [ ] **Step 8: Commit**

```bash
git add humble_catalog/choice_preview.py tests/test_choice_preview.py tests/fixtures/choice_hub.json docs/TEST-DATA.md
git commit -m "feat: count a Humble Choice month as owned, possible or new

Choice offers fresh games monthly, so no id in the blob collides with the
catalog and ownership must be decided by title. The three verdicts
partition the month; possible is counted as neither owned nor new."
```

---

### Task 3: Ownership held as an unclaimed Humble key

**Files:**
- Modify: `humble_catalog/choice_preview.py` (inside `preview`)
- Test: `tests/test_choice_preview.py`

**Interfaces:**
- Consumes: `game_match.keyed_games` (Task 1); `preview` (Task 2).
- Produces: `preview()` gains `keyed` (int) and `keyed_items` (list of dicts with `offered`, `owned_title`, `score`, `key_type`, `bundle`). `keyed` is a **subset of** `owned` and is never added to it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_choice_preview.py`:

```python
def test_a_game_held_only_as_a_humble_key_counts_as_owned(tmp_path):
    # Cinder Vale was paid for in an earlier bundle and never activated,
    # so it is in no imported library. Reporting it as new would push
    # toward paying for it twice.
    report = _report(tmp_path)
    assert "Cinder Vale" in report["owned_items"]
    assert "Cinder Vale" not in report["new_items"]


def test_a_keyed_game_is_listed_apart_from_a_library_match(tmp_path):
    # Counted inside `owned`, but named: an unactivated key can be dead or
    # region-locked in a way a library entry cannot.
    report = _report(tmp_path)
    assert report["keyed"] == 1
    hit = report["keyed_items"][0]
    assert hit["offered"] == "Cinder Vale"
    assert hit["key_type"] == "steam"
    assert hit["bundle"] == "Humble Game Bundle: Key Vault"


def test_keyed_is_a_subset_of_owned_and_is_never_added_to_it(tmp_path):
    report = _report(tmp_path)
    assert report["keyed"] <= report["owned"]
    assert report["owned"] + report["possible"] + report["new"] == report["total"]


def test_a_library_match_is_not_reported_as_keyed(tmp_path):
    # Keys are tried only after the libraries say "new", so a game both
    # keyed and activated reports as the plain library match it is.
    assert [k["offered"] for k in _report(tmp_path)["keyed_items"]] == [
        "Cinder Vale"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -k keyed -q`
Expected: FAIL with `KeyError: 'keyed'`

- [ ] **Step 3: Add the keyed pass to `preview`**

Add the pools just after `library = prepare_pool(owned_games(conn))`:

```python
    # Tried only AFTER the imported libraries have said "new", so a game
    # that is both keyed and activated reports as the plain library match
    # it is, and the keyed list stays what it claims to be: the games
    # whose only evidence is a key.
    keyed = keyed_games(conn)
    keyed_pool = prepare_pool(
        [(normalized, display) for normalized, display, _t, _b in keyed])
    # Keyed on the display title, which is what classify_game hands back.
    keyed_extra = {display: (key_type, bundle_name)
                   for _n, display, key_type, bundle_name in keyed}
```

Add `keyed_items = []` to the accumulator line, and replace the verdict block with:

```python
        verdict, match = classify_game(title, library)
        if verdict == "new":
            # Only an outright keyed 'owned' is honoured. A keyed
            # 'possible' would be a guess about a guess, so it is left to
            # fall through to whatever the libraries decided.
            keyed_verdict, keyed_match = classify_game(title, keyed_pool)
            if keyed_verdict == "owned":
                key_type, bundle_name = keyed_extra.get(
                    keyed_match["owned_title"], (None, None))
                keyed_items.append({**keyed_match, "key_type": key_type,
                                    "bundle": bundle_name})
                owned_items.append(title)
                continue
        if verdict == "owned":
            owned_items.append(title)
        elif verdict == "possible":
            possible_items.append(match)
        else:
            new_items.append(title)
```

Add to the returned dict, immediately after `"owned_items"`:

```python
        # Counted inside `owned` above, listed separately here: the count
        # answers "how much of this do I already have", the list answers
        # "and how sure is that".
        "keyed": len(keyed_items),
        "keyed_items": sorted(keyed_items,
                              key=lambda k: k["offered"].lower()),
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -q`
Expected: PASS, 13 tests

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/choice_preview.py tests/test_choice_preview.py
git commit -m "feat: count a Choice game held as an unclaimed Humble key as owned

An unclaimed key is value already paid for. Counted inside owned and
listed apart, because a key can be dead or region-locked in a way a
library entry cannot."
```

---

### Task 4: Extras, claim state, and the store warning

**Files:**
- Modify: `humble_catalog/choice_preview.py`
- Test: `tests/test_choice_preview.py`

**Interfaces:**
- Consumes: `preview` (Tasks 2-3), `import_games.imported_stores(conn)`.
- Produces: `preview()` gains `extras` (list of str), `claimed` (bool), `libraries` (dict), `unimported_stores` (list of str); and module-level `delivery_stores(game) -> set` and `NON_STORES`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_choice_preview.py`:

```python
def test_extras_are_listed_and_never_counted(tmp_path):
    # Extras are coupon-class entries, not games. Folding them into the
    # total would corrupt every count derived from it.
    report = _report(tmp_path)
    assert report["extras"] == ["Bonus Wallpaper", "Sample Ambience Pack"]
    assert report["total"] == 6
    assert report["owned"] + report["possible"] + report["new"] == 6


def test_a_month_with_no_choices_made_reads_as_unclaimed(tmp_path):
    assert _report(tmp_path)["claimed"] is False


def test_a_month_with_choices_made_reads_as_claimed(tmp_path):
    hub = _hub()
    hub["contentChoiceOptions"]["contentChoiceState"]["initial"][
        "choices_made"] = ["neondrifter_choice"]
    conn = _conn(tmp_path)
    try:
        assert choice_preview.preview(conn, hub)["claimed"] is True
    finally:
        conn.close()


def test_a_store_with_an_unmatched_game_and_no_import_is_named(tmp_path):
    # Lantern & Lockpick is delivered on gog, is owned nowhere, and gog
    # has never been imported -- so it was counted as new by DEFAULT, and
    # the report says so rather than presenting a guess as a fact.
    assert _report(tmp_path)["unimported_stores"] == ["gog"]


def test_other_key_is_never_named_as_an_unimported_store(tmp_path):
    # 'other-key' rides along on Widget Quest II, which is new. It is not
    # a storefront, so no importer could ever satisfy the advice the
    # warning gives.
    assert "other-key" not in _report(tmp_path)["unimported_stores"]


def test_a_store_whose_games_all_matched_is_not_warned_about(tmp_path):
    # Only an unmatched game earns a warning. steam is imported here, but
    # even were it not, warning about a store whose every game is already
    # owned is the noise that teaches an owner to skip the real warning.
    hub = _hub()
    del hub["contentChoiceOptions"]["contentChoiceData"]["game_data"][
        "lanternlockpick_choice"]
    conn = _conn(tmp_path)
    try:
        report = choice_preview.preview(conn, hub)
    finally:
        conn.close()
    assert report["unimported_stores"] == []


def test_delivery_stores_reads_a_bare_string_as_one_store(tmp_path):
    # shapes.text_list, not as_list: a list field that arrived unwrapped
    # is ONE name, never its characters. set() over a string yields five
    # single-letter storefronts.
    assert choice_preview.delivery_stores(
        {"delivery_methods": "steam"}) == {"steam"}
    assert choice_preview.delivery_stores({}) == set()
    assert choice_preview.delivery_stores(
        {"delivery_methods": ["steam", "other-key"]}) == {"steam"}


def test_libraries_reports_what_was_imported(tmp_path):
    assert "steam" in _report(tmp_path)["libraries"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -k "extras or claimed or store or libraries" -q`
Expected: FAIL with `KeyError: 'extras'`

- [ ] **Step 3: Implement**

Add near the top of `choice_preview.py`, after the imports:

```python
from humble_catalog import import_games, shapes

# Delivery methods that are not storefronts. `other-key` means a key
# redeemed somewhere that is not a store account at all, so no importer
# can ever exist for it -- and the unimported-store warning's whole
# content is "go import that store".
NON_STORES = frozenset({"other-key"})


def delivery_stores(game):
    """The storefronts a Choice game is delivered on, as a set.

    Read through shapes.text_list rather than as_list because this is
    third-party content and the quiet failure is the dangerous one:
    set() over a STRING yields its characters, so a delivery_methods
    field arriving unwrapped as "steam" would produce five single-letter
    storefronts, each read as a store the owner never imported.

    The `or ()` is REQUIRED, not defensive noise: text_list returns None
    rather than [] when there is nothing (so callers can pass it straight
    to `candidate`), and a game with no delivery_methods would otherwise
    raise TypeError here. bundle_preview writes the same `or []`.
    """
    return {store for store in (shapes.text_list(
        shapes.as_mapping(game).get("delivery_methods")) or ())
        if store and store not in NON_STORES}
```

In `preview`, add `unmatched_stores = set()` beside the accumulators, and in the `else` branch (the `new` verdict) add:

```python
            new_items.append(title)
            # Only a `new` verdict counts toward the warning. A `possible`
            # was not counted as new either, and an owned game says
            # nothing about a missing importer.
            unmatched_stores |= delivery_stores(entry)
```

Then before the return:

```python
    state = shapes.as_mapping(opts.get("contentChoiceState"))
    libraries = import_games.imported_stores(conn)
```

and add to the returned dict:

```python
        # Listed, never counted. These are coupon-class entries rather
        # than games -- nothing about them can be owned, so folding them
        # into `total` would corrupt every count derived from it. Shown so
        # the report does not appear to be hiding part of the month.
        "extras": sorted(
            (shapes.as_text(shapes.as_mapping(extra).get("human_name"))
             or shapes.as_text(shapes.as_mapping(extra).get("machine_name"))
             or "")
            for extra in shapes.as_list(month.get("extras"))),
        # Whether this month's picks have already been made. bool() rather
        # than a shape assertion: Humble has shipped this as a list, and
        # emptiness is the only property being asked about.
        "claimed": bool(shapes.as_mapping(state.get("initial")
                                          ).get("choices_made")),
        "libraries": libraries,
        # A store this month delivers on that has never been imported and
        # still has a game nothing accounted for. That game was counted as
        # new by DEFAULT, which is a guess dressed as a fact -- so the
        # report says so out loud.
        "unimported_stores": sorted(unmatched_stores - set(libraries)),
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -q`
Expected: PASS, 21 tests

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/choice_preview.py tests/test_choice_preview.py
git commit -m "feat: report Choice extras, claim state and unimported stores

Extras are listed and never counted -- they are coupon-class entries, not
games. 'other-key' is excluded from the store warning: it is not a
storefront, so no importer could satisfy the advice."
```

---

### Task 5: `format_report`

**Files:**
- Modify: `humble_catalog/bundle_preview.py:412`, `:444` (promote `_SYMBOLS` to `SYMBOLS`)
- Modify: `humble_catalog/choice_preview.py`
- Test: `tests/test_choice_preview.py`

**Interfaces:**
- Consumes: `preview` (Tasks 2-4), `stats.console_safe(text, encoding)`, `bundle_preview.SYMBOLS`.
- Produces: `choice_preview.format_report(report, encoding="utf-8") -> str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_choice_preview.py`:

```python
def _text(tmp_path):
    return choice_preview.format_report(_report(tmp_path))


def test_format_report_leads_with_the_month_and_the_three_counts(tmp_path):
    out = _text(tmp_path)
    assert "Humble Choice: January 2031" in out
    assert "owned 3" in out and "possible 1" in out and "new 2" in out


def test_format_report_lists_the_new_games(tmp_path):
    out = _text(tmp_path)
    assert "Lantern & Lockpick" in out
    assert "Widget Quest II" in out


def test_format_report_names_the_key_a_count_is_trusting(tmp_path):
    out = _text(tmp_path)
    assert "owned via a Humble key" in out
    assert "Humble Game Bundle: Key Vault" in out


def test_format_report_says_a_possible_is_counted_as_neither(tmp_path):
    out = _text(tmp_path)
    assert "counted as neither owned nor new" in out
    assert "Starfall Rally Turbo" in out
    assert "Starfall Rally" in out


def test_format_report_always_warns_that_matching_is_approximate(tmp_path):
    # Unlike the bundle report, this warning is unconditional: every
    # answer here is a title match, so there is no book path that earns
    # the warning's absence.
    assert "APPROXIMATE" in _text(tmp_path)


def test_format_report_warns_about_a_store_with_no_import(tmp_path):
    out = _text(tmp_path)
    assert "never been imported" in out
    assert "gog" in out


def test_format_report_degrades_a_symbol_the_console_cannot_encode(tmp_path):
    # cp437 is the Windows console default and has no euro sign. capsys
    # captures as UTF-8, so no other test can observe this.
    out = choice_preview.format_report(_report(tmp_path), "cp437")
    assert "EUR 11.99" in out
    assert "€" not in out


def test_format_report_omits_empty_headings(tmp_path):
    # A month owned outright must print as clean counts, not as a stack of
    # empty headings.
    conn = _conn(tmp_path)
    hub = _hub()
    for name in ("widgetquest2_choice", "starfallrallyturbo_choice",
                 "lanternlockpick_choice"):
        del hub["contentChoiceOptions"]["contentChoiceData"]["game_data"][name]
    try:
        out = choice_preview.format_report(choice_preview.preview(conn, hub))
    finally:
        conn.close()
    assert "new 0" in out
    assert "possible" not in out.split("APPROXIMATE")[0].split("new 0")[1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -k format -q`
Expected: FAIL with `AttributeError: module 'humble_catalog.choice_preview' has no attribute 'format_report'`

- [ ] **Step 3: Promote the currency table in `bundle_preview.py`**

Rename `_SYMBOLS` to `SYMBOLS` at line 412 and update its one use at line 444. Keep the comment above it unchanged. One table, two readers — duplicating five entries would be a second source of truth for a thing that must agree.

```python
SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CAD": "CA$", "AUD": "A$"}
```

```python
    symbol = SYMBOLS.get(report["currency"], report["currency"] + " ")
```

- [ ] **Step 4: Add `format_report` to `choice_preview.py`**

Add `from humble_catalog import bundle_preview, import_games, shapes, stats` to the imports (replacing the existing import line), then:

```python
def format_report(report, encoding="utf-8"):
    """The report as printable text, safe for a console using `encoding`.

    Deliberately no MSRP column, though the blob carries one per game.
    Same reasoning that kept price-per-new-item out of the bundle report:
    it is arithmetic the reader can do, and a large "value" figure invites
    reading it as "worth buying" -- the misjudgement this exists to correct.
    """
    symbol = bundle_preview.SYMBOLS.get(report["currency"],
                                        report["currency"] + " ")
    # A console that cannot encode the symbol falls back to the ISO code
    # rather than to console_safe's replacement character: "?11.99" reads
    # as a bug, "EUR 11.99" reads as a price. The Windows console defaults
    # to cp437/cp850 and neither carries the euro sign.
    try:
        symbol.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        symbol = report["currency"] + " "
    noun = "game" if report["total"] == 1 else "games"
    lines = [f"{report['name']}   {symbol}{report['price']:.2f}   "
             f"{report['total']} {noun}",
             f"  owned {report['owned']}    possible {report['possible']}"
             f"    new {report['new']}",
             ""]
    if report["claimed"]:
        # Stated, not acted on: the counts are the same either way, but a
        # month already claimed is not a month to decide about.
        lines += ["  You have already made your picks for this month.", ""]

    def block(heading, items):
        # Omitted entirely when empty, so a month owned outright prints as
        # clean counts rather than a stack of empty headings.
        if not items:
            return
        lines.append(f"  {heading}:")
        lines.extend(f"    {line}" for line in items)
        lines.append("")

    block(f"new ({report['new']})", report["new_items"])
    block(f"owned ({report['owned']})", report["owned_items"])
    def keyed_line(hit):
        """One key line: the game, and where the key says it came from."""
        where = ", ".join(part for part in (
            f"{hit['key_type']} key" if hit.get("key_type") else None,
            hit.get("bundle")) if part)
        return hit["offered"] + (f"  ({where})" if where else "")

    count = report["keyed"]
    if count:
        # Never "unredeemed": Humble marks a key redeemed the moment its
        # value is revealed, which says nothing about whether the game ever
        # reached a store account. Absence from every imported library is
        # what is actually known, so it is what is said.
        block(f"{count} owned via {'a Humble key' if count == 1 else 'Humble keys'}"
              f" (not in any imported library)",
              [keyed_line(hit) for hit in report["keyed_items"]])
    # Listed, never folded into owned or new. The whole point of the middle
    # band is that the tool declines to decide, so a bare count would hide
    # which title it could not decide about.
    block(f"{report['possible']} possible (counted as neither owned nor new)",
          [f"{hit['offered']}  ~  {hit['owned_title']}  ({hit['score']:.2f})"
           for hit in report["possible_items"]])
    block(f"Extras (not counted, {len(report['extras'])})", report["extras"])
    # Unconditional, unlike the bundle report's: every answer here is a
    # title match, so there is no path that earns the warning's absence.
    lines += ["  Game ownership is matched by title and is APPROXIMATE -- "
              "verify anything you would buy on."]
    libraries = report.get("libraries") or {}
    if libraries:
        lines.append("  Libraries: " + ", ".join(
            f"{store} {info['count']} "
            f"{'game' if info['count'] == 1 else 'games'} "
            f"(imported {info['imported_at'][:10]})"
            for store, info in sorted(libraries.items())))
    for store in report["unimported_stores"]:
        lines.append(f"  WARNING: this month delivers on '{store}', which has "
                     f"never been imported -- its unmatched games are counted "
                     f"as new by default.")
    if report["unimported_stores"]:
        lines.append("  Run `python -m humble_catalog import-games` first.")
    # Degraded at the CLI boundary only: the web route keeps the symbol,
    # and the game names are arbitrary data that may hold anything.
    return stats.console_safe("\n".join(lines).rstrip(), encoding)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py tests/test_bundle_preview.py -q`
Expected: PASS — both files, since `SYMBOLS` was renamed under `bundle_preview`'s tests too

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/choice_preview.py humble_catalog/bundle_preview.py tests/test_choice_preview.py
git commit -m "feat: print the Choice report

No MSRP column, for the reason the bundle report has no price-per-item:
a large value figure invites reading it as 'worth buying'. The APPROXIMATE
warning is unconditional here -- every answer is a title match."
```

---

### Task 6: `HumbleClient.get_page`

**Files:**
- Modify: `humble_catalog/humble_api.py:33-42`
- Test: `tests/test_humble_api.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `HumbleClient.get_page(path) -> str`; `HumbleClient._wait()` shared by `_get` and `get_page`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_humble_api.py` (match the stubbing style already in that file):

```python
def test_get_page_returns_the_html_body():
    http = Mock()
    resp = Mock(status_code=200)
    resp.text = "<html><body>hi</body></html>"
    http.get.return_value = resp
    client = humble_api.HumbleClient({}, delay=0, http=http)
    assert client.get_page("/membership/home") == "<html><body>hi</body></html>"


def test_get_page_raises_not_logged_in_on_a_non_200():
    # A redirect to the login page arrives as a non-200 here; treating it
    # as a page would hand the parser a login form and report "no Choice".
    http = Mock()
    http.get.return_value = Mock(status_code=302, text="")
    client = humble_api.HumbleClient({}, delay=0, http=http)
    with pytest.raises(humble_api.NotLoggedIn):
        client.get_page("/membership/home")


def test_get_page_shares_the_rate_limit_with_the_json_path():
    # Politeness toward Humble is a property of the client, not something
    # each caller remembers.
    http = Mock()
    resp = Mock(status_code=200)
    resp.text = "<html></html>"
    http.get.return_value = resp
    client = humble_api.HumbleClient({}, delay=0, http=http)
    client.get_page("/membership/home")
    assert client._last is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_humble_api.py -k get_page -q`
Expected: FAIL with `AttributeError: 'HumbleClient' object has no attribute 'get_page'`

- [ ] **Step 3: Extract `_wait` and add `get_page`**

Replace `_get`'s opening throttle block with a call to a new `_wait`, then add `get_page`:

```python
    def _wait(self):
        """Hold off until `delay` has passed since the last request.

        Shared by _get and get_page so politeness toward Humble is a
        property of the client rather than something each caller
        remembers.
        """
        if self._last is not None:
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)

    def _get(self, path, **kwargs):
        self._wait()
        resp = self.http.get(f"{BASE}{path}", timeout=30, **kwargs)
        self._last = time.monotonic()
        if resp.status_code != 200 or "json" not in resp.headers.get("Content-Type", ""):
            raise NotLoggedIn(f"GET {path} -> {resp.status_code}")
        return resp.json()

    def get_page(self, path):
        """The HTML body of a page on the Humble site.

        The HTML sibling of _get, for the one page whose data is embedded
        in markup rather than served as JSON. It cannot check the content
        type the way _get does -- HTML is the expected answer -- so a
        non-200 is the only signal available here; a signed-out session is
        caught by logged_in() before this is ever called.
        """
        self._wait()
        resp = self.http.get(f"{BASE}{path}", timeout=30)
        self._last = time.monotonic()
        if resp.status_code != 200:
            raise NotLoggedIn(f"GET {path} -> {resp.status_code}")
        return resp.text
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_humble_api.py -q`
Expected: PASS (including the pre-existing `_get` tests, which the `_wait` extraction must not disturb)

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/humble_api.py tests/test_humble_api.py
git commit -m "feat: add HumbleClient.get_page for HTML pages

The Choice month is embedded in page markup rather than served as JSON,
so it needs a fetch that does not insist on a JSON content type. The
inter-request delay is extracted so both paths share it."
```

---

### Task 7: `fetch_choice`

**Files:**
- Create: `tests/fixtures/choice_page.html`
- Modify: `humble_catalog/choice_preview.py`
- Test: `tests/test_choice_preview.py`

**Interfaces:**
- Consumes: `HumbleClient.get_page` (Task 6), `humble_api.NotLoggedIn`.
- Produces: `choice_preview.fetch_choice(client=None) -> dict` (the whole hub mapping), `choice_preview.HUB_PATH`.

- [ ] **Step 1: Create `tests/fixtures/choice_page.html`**

Minimal page wrapping the fixture blob. The live page is ~600 KB and none of the rest is read.

```html
<!doctype html>
<html><head><title>Humble Choice</title></head>
<body>
<div id="subscriber-hub"></div>
<script id="base-webpack-json-data" type="application/json">{"ignored": true}</script>
<script id="webpack-subscriber-hub-data" type="application/json">
{"baseSubscriptionPrice|money": {"currency": "EUR", "amount": 11.99},
 "contentChoiceOptions": {
   "gamekey": "choicejan2031",
   "title": "January 2031",
   "contentChoiceState": {"initial": {"choices_made": []}},
   "contentChoiceData": {
     "display_order": ["neondrifter_choice"],
     "extras": [],
     "game_data": {
       "neondrifter_choice": {
         "title": "Neon Drifter",
         "display_item_machine_name": "neondrifter_choice_di",
         "delivery_methods": ["steam"], "tpkds": [],
         "msrp|money": {"currency": "EUR", "amount": 19.99}}}}}}
</script>
</body></html>
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_choice_preview.py`:

```python
import pytest

from humble_catalog import humble_api


def _client(text, logged_in=True):
    """A stub HumbleClient whose one page carries `text`."""
    client = Mock()
    client.logged_in.return_value = logged_in
    client.get_page.return_value = text
    return client


def _page():
    return (FIXTURES / "choice_page.html").read_text(encoding="utf-8")


def test_fetch_choice_parses_the_embedded_hub_blob():
    hub = choice_preview.fetch_choice(_client(_page()))
    assert hub["contentChoiceOptions"]["title"] == "January 2031"
    assert hub["baseSubscriptionPrice|money"]["amount"] == 11.99


def test_fetch_choice_returns_the_whole_hub_not_just_the_month():
    # The price sits at the TOP level, outside contentChoiceOptions.
    # Returning the narrower dict would put it out of preview's reach.
    hub = choice_preview.fetch_choice(_client(_page()))
    assert "baseSubscriptionPrice|money" in hub


def test_fetch_choice_refuses_a_stale_session_before_fetching_anything():
    # A signed-out /membership still answers 200 with a marketing shell,
    # so a missing blob is ambiguous between "not logged in" and "no offer
    # this month". logged_in() disambiguates, and the caller needs the
    # difference: one is fixed by logging in, the other is not.
    client = _client(_page(), logged_in=False)
    with pytest.raises(humble_api.NotLoggedIn):
        choice_preview.fetch_choice(client)
    client.get_page.assert_not_called()


def test_fetch_choice_rejects_a_page_with_no_hub_blob():
    with pytest.raises(ValueError, match="no Humble Choice data"):
        choice_preview.fetch_choice(
            _client("<html><body>Nothing here</body></html>"))


def test_fetch_choice_rejects_a_blob_with_no_month_on_offer():
    with pytest.raises(ValueError, match="no Humble Choice month"):
        choice_preview.fetch_choice(_client(
            '<script id="webpack-subscriber-hub-data" '
            'type="application/json">{"contentChoiceOptions": {}}</script>'))


def test_the_fetched_page_feeds_preview_unchanged(tmp_path):
    # The seam's whole point: what fetch_choice returns is what preview
    # consumes, with nothing in between to drift.
    conn = _conn(tmp_path)
    try:
        report = choice_preview.preview(
            conn, choice_preview.fetch_choice(_client(_page())))
    finally:
        conn.close()
    assert report["name"] == "Humble Choice: January 2031"
    assert (report["total"], report["owned"]) == (1, 1)
```

Also add `from unittest.mock import Mock` to the file's imports.

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -k fetch -q`
Expected: FAIL with `AttributeError: ... has no attribute 'fetch_choice'`

- [ ] **Step 4: Implement `fetch_choice`**

Add `import json`, `import re`, and `from humble_catalog import humble_api` to the imports, then:

```python
HUB_PATH = "/membership/home"
_HUB = re.compile(
    r'<script id="webpack-subscriber-hub-data" type="application/json">'
    r'(.*?)</script>', re.S)


def fetch_choice(client=None):
    """The subscriber-hub blob for the current Choice month.

    NEVER logs in interactively. Given no client it builds one from the
    saved cookies and checks the session; a stale one raises NotLoggedIn.
    That is what makes this safe to call from a web request, where
    manual_login's proc.wait() would hang the thread on a browser window
    the server cannot see.

    The session is checked BEFORE the page is fetched, because a
    signed-out /membership answers 200 with a marketing shell carrying no
    blob -- indistinguishable from a month with nothing on offer. The two
    need different answers: one is fixed by logging in, the other is not.
    """
    if client is None:
        client = humble_api.HumbleClient(humble_api.get_cookies())
    if not client.logged_in():
        raise humble_api.NotLoggedIn(
            "no usable HumbleBundle session")
    match = _HUB.search(client.get_page(HUB_PATH))
    if not match:
        raise ValueError(
            "no Humble Choice data on that page -- the subscriber hub did "
            "not carry its blob")
    hub = shapes.as_mapping(json.loads(match.group(1)))
    _opts, month = _month(hub)
    if not month:
        raise ValueError(
            "no Humble Choice month on offer -- this account may not have "
            "an active membership")
    return hub
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_choice_preview.py -q`
Expected: PASS, 36 tests

- [ ] **Step 6: Run the privacy check**

Run: `.venv/Scripts/python scripts/leak_check.py`
Expected: `clean`

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/choice_preview.py tests/test_choice_preview.py tests/fixtures/choice_page.html
git commit -m "feat: fetch the current Humble Choice month

Checks the session before fetching, because a signed-out membership page
answers 200 with a shell carrying no blob -- indistinguishable from a
month with nothing on offer, and the two need different answers.
fetch_choice never logs in interactively, so a web route can call it."
```

---

### Task 8: The `choice` subcommand

**Files:**
- Modify: `humble_catalog/choice_preview.py` (add `run`)
- Modify: `humble_catalog/__main__.py:190` (subparser), `:318` (dispatch)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `fetch_choice`, `preview`, `format_report`, `humble_api.ensure_login`, `db.connect`.
- Produces: `choice_preview.run()`; CLI `python -m humble_catalog choice`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main.py`, mirroring the `bundle` command tests already there:

```python
def test_choice_command_prints_the_month(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    db.connect("catalog.db").close()
    fake = {
        "baseSubscriptionPrice|money": {"currency": "USD", "amount": 11.99},
        "contentChoiceOptions": {
            "title": "January 2031",
            "contentChoiceState": {"initial": {"choices_made": []}},
            "contentChoiceData": {
                "extras": [],
                "game_data": {
                    "lanternlockpick_choice": {
                        "title": "Lantern & Lockpick",
                        "delivery_methods": ["steam"]}}}},
    }
    from humble_catalog import choice_preview, humble_api
    monkeypatch.setattr(humble_api, "ensure_login", lambda *a, **k: object())
    monkeypatch.setattr(choice_preview, "fetch_choice", lambda client=None: fake)
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "choice"])
    main()
    out = capsys.readouterr().out
    assert "Humble Choice: January 2031" in out
    assert "new 1" in out


def test_choice_command_reports_a_dead_month_without_a_traceback(
        monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    db.connect("catalog.db").close()
    from humble_catalog import choice_preview, humble_api

    def boom(client=None):
        raise ValueError("no Humble Choice month on offer")

    monkeypatch.setattr(humble_api, "ensure_login", lambda *a, **k: object())
    monkeypatch.setattr(choice_preview, "fetch_choice", boom)
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "choice"])
    with pytest.raises(SystemExit):
        main()
    assert "no Humble Choice month on offer" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_main.py -k choice -q`
Expected: FAIL — argparse exits with "invalid choice: 'choice'"

- [ ] **Step 3: Add `run()` to `choice_preview.py`**

```python
def run():
    """Log in if needed, fetch, count, and print. The `choice` entry point."""
    # ensure_login, not fetch_choice's own check: this is the surface where
    # a human and a terminal are present, so an expired session is a prompt
    # rather than an error. The web route does the opposite, deliberately.
    client = humble_api.ensure_login()
    hub = fetch_choice(client)
    conn = db.connect()
    try:
        report = preview(conn, hub)
    finally:
        conn.close()
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(format_report(report, encoding))
```

Add `import sys` and `db` to the imports:
`from humble_catalog import bundle_preview, db, humble_api, import_games, shapes, stats`

- [ ] **Step 4: Register the subcommand in `__main__.py`**

After the `p_bundle.add_argument(...)` block (line 189), add:

```python
    sub.add_parser(
        "choice",
        help="Show how much of this month's Humble Choice you already own",
        description="Shows how many of this month's Humble Choice games you "
                    "already own, counting games in your imported libraries "
                    "and games you hold as an unclaimed Humble key. Games "
                    "are matched by title and only approximately, so treat "
                    "the counts as a strong hint and check anything you "
                    "would base a purchase on. Run 'import-games' first or "
                    "every game reads as new. Read-only, but it needs your "
                    "Humble login -- Choice pages carry nothing when signed "
                    "out.")
```

And in the dispatch chain, after the `bundle` branch:

```python
    elif args.command == "choice":
        from humble_catalog import choice_preview
        try:
            choice_preview.run()
        except ValueError as exc:
            # A month that cannot be read is a condition to report, not a
            # traceback -- same stance as the bundle command's bad URL.
            parser.error(str(exc))
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_main.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/choice_preview.py humble_catalog/__main__.py tests/test_main.py
git commit -m "feat: add the choice subcommand

Interactive login lives here rather than in fetch_choice: this is the
surface with a human and a terminal, so an expired session is a prompt."
```

---

### Task 9: `POST /api/choice-preview`

**Files:**
- Modify: `humble_catalog/webapp/__init__.py:8` (import), after `:616` (route)
- Test: `tests/test_webapp.py`

**Interfaces:**
- Consumes: `choice_preview.fetch_choice`, `choice_preview.preview`, `humble_api.NotLoggedIn`.
- Produces: `POST /api/choice-preview` → 200 with the report, 409 stale session, 400 unreadable month, 502 upstream failure.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_webapp.py`:

```python
def test_choice_preview_returns_the_report(tmp_path, monkeypatch):
    from humble_catalog import choice_preview
    dbp = tmp_path / "t.db"
    _seed(dbp)
    monkeypatch.setattr(choice_preview, "fetch_choice", lambda client=None: {
        "baseSubscriptionPrice|money": {"currency": "EUR", "amount": 11.99},
        "contentChoiceOptions": {
            "title": "January 2031",
            "contentChoiceState": {"initial": {"choices_made": []}},
            "contentChoiceData": {"extras": [], "game_data": {
                "lanternlockpick_choice": {"title": "Lantern & Lockpick",
                                           "delivery_methods": ["steam"]}}}}})
    client = create_app(db_path=str(dbp)).test_client()
    resp = client.post("/api/choice-preview", json={})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Humble Choice: January 2031"


def test_choice_preview_answers_409_for_a_stale_session(tmp_path, monkeypatch):
    # 409, not 401: nothing about the viewer's own authorization is wrong,
    # and the fix is a command the owner runs elsewhere. Reusing 401 would
    # invite someone to add a login prompt to the viewer -- and
    # manual_login blocks on a browser window the server cannot see.
    from humble_catalog import choice_preview, humble_api
    dbp = tmp_path / "t.db"
    _seed(dbp)

    def stale(client=None):
        raise humble_api.NotLoggedIn("no usable HumbleBundle session")

    monkeypatch.setattr(choice_preview, "fetch_choice", stale)
    client = create_app(db_path=str(dbp)).test_client()
    resp = client.post("/api/choice-preview", json={})
    assert resp.status_code == 409
    assert "login" in resp.get_json()["error"]


def test_choice_preview_answers_400_for_a_month_it_cannot_read(tmp_path,
                                                               monkeypatch):
    from humble_catalog import choice_preview
    dbp = tmp_path / "t.db"
    _seed(dbp)

    def boom(client=None):
        raise ValueError("no Humble Choice month on offer")

    monkeypatch.setattr(choice_preview, "fetch_choice", boom)
    client = create_app(db_path=str(dbp)).test_client()
    resp = client.post("/api/choice-preview", json={})
    assert resp.status_code == 400


def test_choice_preview_answers_502_for_an_upstream_failure(tmp_path,
                                                            monkeypatch):
    import requests as _requests
    from humble_catalog import choice_preview
    dbp = tmp_path / "t.db"
    _seed(dbp)

    def boom(client=None):
        raise _requests.ConnectionError("humblebundle.com unreachable")

    monkeypatch.setattr(choice_preview, "fetch_choice", boom)
    client = create_app(db_path=str(dbp)).test_client()
    assert client.post("/api/choice-preview",
                       json={}).status_code == 502
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k choice_preview -q`
Expected: FAIL with 404 (route does not exist)

- [ ] **Step 3: Add the route**

Extend the import at line 8:

```python
from humble_catalog import (bundle_preview, choice_preview, db, dedupe,
                            editions, export, humble_api, keys, stats,
                            url_import)
```

Add after the `bundle_preview_route` function:

```python
    @app.post("/api/choice-preview")
    def choice_preview_route():
        # Takes no body: Choice is always "this month". POST rather than
        # GET because this is a credentialed network action whose response
        # is a fact about what the owner holds -- neither belongs in a
        # query string that reaches access logs and browser history.
        try:
            hub = choice_preview.fetch_choice()
        except humble_api.NotLoggedIn:
            # 409, never 401: nothing about this request's authorization is
            # wrong, and the fix is a command run in a terminal. The server
            # must not attempt the login itself -- manual_login blocks on a
            # browser window it cannot see.
            return jsonify({"error": "Humble session expired -- run "
                                     "`python -m humble_catalog login`, "
                                     "then try again."}), 409
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except requests.RequestException as exc:
            return jsonify({"error": str(exc)}), 502
        return jsonify(choice_preview.preview(conn(), hub))
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "feat: add POST /api/choice-preview

The route reports a stale session as 409 and never logs in itself:
manual_login blocks on a browser window the server cannot see."
```

---

### Task 10: The viewer panel

**Files:**
- Modify: `humble_catalog/webapp/static/index.html:136-143`
- Modify: `humble_catalog/webapp/static/bundles.js` (append)
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: `POST /api/choice-preview` (Task 9); the harness helpers `$`, `esc`, `post`, `money` already in scope in `bundles.js`.
- Produces: `previewChoice()` and `renderChoicePreview()` on the `app` namespace; `#choice-go` button and `#choice-panel` div.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_webapp_js.py`, following the `_render_bundle` pattern already in that file:

```python
_CHOICE_REPORT = {
    "name": "Humble Choice: January 2031", "price": 11.99, "currency": "EUR",
    "total": 4, "owned": 2, "possible": 1, "new": 1,
    "owned_items": ["Cinder Vale", "Neon Drifter"],
    "new_items": ["Lantern & Lockpick"],
    "possible_items": [{"offered": "Starfall Rally Turbo",
                        "owned_title": "Starfall Rally", "score": 0.86}],
    "keyed": 1,
    "keyed_items": [{"offered": "Cinder Vale", "owned_title": "Cinder Vale",
                     "score": 1.0, "key_type": "steam",
                     "bundle": "Humble Game Bundle: Key Vault"}],
    "extras": ["Sample Ambience Pack"], "claimed": False,
    "libraries": {"steam": {"count": 3, "imported_at": "2026-08-01T10:00:00",
                            "source": "test", "source_timestamp": None}},
    "unimported_stores": ["gog"],
}


def _render_choice(report):
    return eval_js(
        """(async () => {
             app.setFetch(() => Promise.resolve(
               {ok: true, json: () => Promise.resolve(%s)}));
             await app.previewChoice();
             return dom.writes["#choice-panel"];
           })()""" % json.dumps(report))


def test_choice_panel_shows_the_month_and_the_three_counts():
    html = _render_choice(_CHOICE_REPORT)
    assert "Humble Choice: January 2031" in html
    assert "owned <b>2</b>" in html
    assert "new <b>1</b>" in html


def test_choice_panel_always_warns_that_matching_is_approximate():
    # A coloured count in a browser reads as more authoritative than the
    # same number in a terminal, so the caveat matters more here.
    assert "APPROXIMATE" in _render_choice(_CHOICE_REPORT)


def test_choice_panel_names_the_key_a_count_is_trusting():
    html = _render_choice(_CHOICE_REPORT)
    assert "owned via a Humble key" in html
    assert "Humble Game Bundle: Key Vault" in html


def test_choice_panel_labels_a_possible_as_counted_as_neither():
    html = _render_choice(_CHOICE_REPORT)
    assert "counted as neither owned nor new" in html
    assert "Starfall Rally Turbo" in html


def test_choice_panel_warns_about_a_store_with_no_import():
    assert "never been imported" in _render_choice(_CHOICE_REPORT)


def test_choice_panel_omits_empty_sections():
    report = dict(_CHOICE_REPORT, keyed=0, keyed_items=[], possible=0,
                  possible_items=[], extras=[], unimported_stores=[])
    html = _render_choice(report)
    assert "owned via" not in html
    assert "counted as neither" not in html
    assert "never been imported" not in html


def test_choice_panel_shows_the_error_from_a_stale_session():
    html = eval_js(
        """(async () => {
             app.setFetch(() => Promise.resolve(
               {ok: false, json: () => Promise.resolve(
                 {error: "Humble session expired -- run `python -m humble_catalog login`, then try again."})}));
             await app.previewChoice();
             return dom.writes["#choice-panel"];
           })()""")
    assert "session expired" in html


def test_render_choice_preview_before_any_fetch_draws_nothing():
    assert eval_js_error("(async () => app.renderChoicePreview())()") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k choice -q`
Expected: FAIL — `app.previewChoice is not a function`

- [ ] **Step 3: Add the markup to `index.html`**

Replace the `#section-bundles` block (lines 136-143) with:

```html
  <section id="section-bundles" hidden>
    <div id="bundle-form">
      <input id="bundle-url" aria-label="Humble bundle URL to preview" type="url" size="60"
             placeholder="Paste a HumbleBundle page URL to see what you already own">
      <button id="bundle-go">Check bundle</button>
    </div>
    <div id="bundle-panel" hidden></div>
    <div id="choice-form">
      <button id="choice-go">Check this month's Choice</button>
    </div>
    <div id="choice-panel" hidden></div>
  </section>
```

No URL input: Choice is always "this month", so there is nothing to paste.

- [ ] **Step 4: Append the panel to `bundles.js`**

```javascript
// ---- Humble Choice panel ----------------------------------------------
// One button, no URL: Choice is always "this month". The counting lives
// only in choice_preview.py, so every number arrives with the data and
// there is nothing here to drift from the CLI.
//
// Unlike the bundle panel this needs the owner's Humble login, which the
// server will NOT perform: a stale session comes back as 409 with the
// command to run, and the message is shown as-is.

let choicePreview = null, choicePreviewError = null;
let choicePreviewOpen = true;

async function previewChoice() {
  choicePreview = choicePreviewError = null;
  const resp = await post("/api/choice-preview", {});
  const body = await resp.json();
  if (resp.ok) choicePreview = body;
  else choicePreviewError = body.error || "could not read this month's Choice";
  renderChoicePreview();
}

function renderChoicePreview() {
  const panel = $("#choice-panel");
  panel.hidden = !choicePreview && !choicePreviewError;
  if (panel.hidden) return;
  if (choicePreviewError) {
    panel.innerHTML = `<p class="bundle-error">${esc(choicePreviewError)}</p>`;
    return;
  }
  const c = choicePreview;
  // The three counts on one row, so the comparison the panel exists for
  // never scrolls. Detail lists follow.
  const counts = `<table class="bundle-tiers"><tbody><tr>
    <td class="bundle-price">${esc(money(c.price, c.currency))}</td>
    <td>${c.total} ${c.total === 1 ? "game" : "games"}</td>
    <td>owned <b>${c.owned}</b></td>
    <td>possible <b>${c.possible}</b></td>
    <td>new <b>${c.new}</b></td></tr></tbody></table>`;
  // Omitted entirely when empty, so a month owned outright renders as
  // clean counts rather than a stack of empty headings.
  const list = (cls, heading, items) => items.length ? `
    <section class="${cls}">
      <h4>${esc(heading)}</h4>
      <ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>
    </section>` : "";
  const plain = (items) => items.map((n) => esc(n));
  // Never "unredeemed": Humble marks a key redeemed the moment its value
  // is revealed, which says nothing about whether the game reached a store
  // account. Absence from every imported library is what is known.
  const keyedNoun = (n) =>
    `${n} owned via ${n === 1 ? "a Humble key" : "Humble keys"}`
    + " (not in any imported library)";
  const keyed = list("bundle-keyed", keyedNoun(c.keyed),
    (c.keyed_items || []).map((k) => `${esc(k.offered)}
      <span class="bundle-score">(${esc([
        k.key_type ? k.key_type + " key" : null, k.bundle,
      ].filter(Boolean).join(", "))})</span>`));
  // Listed, never folded into owned or new: the point of the middle band
  // is that the tool declines to decide, so a bare count would hide which
  // game it could not decide about.
  const possible = list("bundle-overlaps",
    `${c.possible} possible (counted as neither owned nor new)`,
    (c.possible_items || []).map((p) => `${esc(p.offered)} ~
      ${esc(p.owned_title)}
      <span class="bundle-score">(${p.score.toFixed(2)})</span>`));
  const warnings = (c.unimported_stores || []).map((s) => `
    <p class="bundle-error">WARNING: this month delivers on ${esc(s)}, which
    has never been imported — its unmatched games are counted as new by
    default.</p>`).join("");
  panel.innerHTML = `<details${choicePreviewOpen ? " open" : ""}>
    <summary>${esc(c.name)}</summary>
    ${counts}
    ${c.claimed ? "<p>You have already made your picks for this month.</p>" : ""}
    ${list("bundle-adds", `new (${c.new})`, plain(c.new_items || []))}
    ${list("bundle-adds", `owned (${c.owned})`, plain(c.owned_items || []))}
    ${keyed}${possible}
    ${list("bundle-adds", `Extras (not counted, ${(c.extras || []).length})`,
           plain(c.extras || []))}
    <p class="bundle-approximate">Game ownership is matched by title and is
      APPROXIMATE — verify anything you would buy on.</p>
    ${warnings}</details>`;
  panel.querySelector("details").addEventListener("toggle",
    (ev) => { choicePreviewOpen = ev.target.open; });
}

$("#choice-go").addEventListener("click", () => { previewChoice(); });
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -q`
Expected: PASS. If `app.previewChoice is not a function` persists, the harness exposes top-level `let`/`function` bindings automatically — confirm the new code is at `bundles.js` top level and not nested inside another function.

- [ ] **Step 6: Verify it in a browser against the demo catalog**

Never the real catalog — a screenshot of the real viewer leaks the library, and images pass every automated check.

Run: `.venv/Scripts/python scripts/demo_catalog.py`
Then open `http://127.0.0.1:8099`, go to the Bundles section, and confirm the Choice button renders. The fetch will fail without a login; confirm the 409 message renders as readable text rather than a blank panel.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/webapp/static/index.html humble_catalog/webapp/static/bundles.js tests/test_webapp_js.py
git commit -m "feat: add the Humble Choice panel to the viewer

One button, no URL input: Choice is always this month. The APPROXIMATE
warning is unconditional -- a coloured count in a browser reads as more
authoritative than the same number in a terminal."
```

---

### Task 11: Documentation and the full gate

**Files:**
- Modify: `README.md`
- Modify: `docs/BACKLOG.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Document the command in `README.md`**

Add an entry beside the `bundle` command's, in the same style the file already uses:

```markdown
- **`choice`** — how much of this month's Humble Choice you already own.
  Counts games in your imported libraries and games you hold as an
  unclaimed Humble key. Unlike `bundle` it needs your Humble login: a
  signed-out Choice page carries no data at all. Matching is by title and
  approximate — run `import-games` first, or every game reads as new.
```

- [ ] **Step 2: Record what was deliberately left out in `docs/BACKLOG.md`**

Add to the out-of-scope section:

```markdown
- **Past or arbitrary Choice months.** The subscriber hub serves the
  current month only; addressing an arbitrary month is a different fetch
  answering a question that was explicitly not wanted.
- **Choice-specific history.** Past Choice months already harvest as
  ordinary orders and their games already count as owned through
  `external_keys`. Labelling them as Choice months would add a view, not
  an answer.
- **MSRP / value arithmetic in the Choice report.** The blob carries
  `msrp|money` per game. Omitted for the reason the bundle report has no
  price-per-new-item column: it invites reading a large value figure as
  "worth buying".
```

- [ ] **Step 3: Run the full gate**

Run: `.\scripts\windows\verify.ps1`
Expected: tests pass, `leak_check` prints `clean`, `check_no_data_tracked` prints `clean`. Nothing else counts as done.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/BACKLOG.md
git commit -m "docs: document the choice command and what it leaves out"
```

- [ ] **Step 5: Confirm the branch is clean and self-contained**

Run: `git status --short && git log --oneline main..HEAD`
Expected: no uncommitted changes; nine commits forking from `main`, independently mergeable.

---

## Self-Review Notes

Checked against the spec:

- **Fetch requires login, blob shape, `get_page`** → Tasks 6-7.
- **Approximate title matching, three-way verdict, cutoffs reused** → Tasks 2-3.
- **Keys count as owned, listed apart, expired still count** → Task 3 (the expired-key rule lives in `keyed_games`'s docstring, preserved verbatim by Task 1).
- **Extras uncounted, `claimed`, `other-key` excluded, store warning scoped to unmatched** → Task 4.
- **Report shape, sorting, no MSRP, symbol degradation** → Tasks 2-5.
- **CLI subcommand with interactive login; route with 409** → Tasks 8-9.
- **Viewer panel with unconditional warning** → Task 10.
- **Fixtures anonymized, `TEST-DATA.md` updated, `leak_check` run** → Tasks 2, 7, 11.
- **`preview` pure, `shapes` everywhere, `text_list` for lists** → Tasks 2, 4, plus the adversarial-shape test in Task 2.

Two shape traps this plan pins down, both verified against the source
rather than assumed:

- **`shapes.text_list` returns `None`, not `[]`**, when there is nothing.
  Every call site here writes `or ()`/`or []`. Missing it raises
  `TypeError` for any game with no `delivery_methods`.
- **`stats.console_safe(text, encoding)` takes both arguments** — there is
  no default — which is why `format_report` carries `encoding="utf-8"`.

Two things the spec left implicit that this plan pins down:

1. **`fetch_choice` checks `logged_in()` before fetching.** The spec said fetch and check but not the order; the order is load-bearing, because a signed-out page is a 200 with no blob and would otherwise be misreported as "no month on offer". Task 7 Step 2 tests it.
2. **`SYMBOLS` and the pool builders are shared, not copied.** The spec said reuse without saying how; Tasks 1 and 5 make it structural rather than a copy that can drift.
