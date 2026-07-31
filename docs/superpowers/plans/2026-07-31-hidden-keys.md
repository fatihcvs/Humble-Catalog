# Hidden keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the owner hide a resolved key from the `keys` report so it stops
reappearing, and fix `external_keys`'s primary key in the same migration.

**Architecture:** `external_keys` is re-keyed from `(gamekey, human_name)` — not
unique, and silently dropping rows — to `(gamekey, machine_name)`. A new
`hidden_keys` table holds the owner's "this one is resolved" assertions, keyed
the same way and preserved across `reset`. `keys.report()` annotates each row
with `hidden_at` rather than filtering, so the CLI and the viewer filter the
same field and cannot disagree.

**Tech Stack:** Python 3.12, SQLite (stdlib `sqlite3`), Flask, vanilla JS
(no framework, no build step), pytest, Node for the JS harness.

**Spec:** `docs/superpowers/specs/2026-07-31-hidden-keys-design.md`

## Global Constraints

- **Privacy is a standing order.** Every name in committed text — tests,
  fixtures, docs, commit messages — must be invented, drawn from
  `docs/TEST-DATA.md`. Never a real item from the owner's library. New names go
  in `docs/TEST-DATA.md` first and must be vetted with
  `leak_check.build_terms()`, because `leak_check.py` matches **substrings**.
- **Run `.venv/Scripts/python scripts/leak_check.py` on its own, never piped**,
  after any task that adds tests or docs naming books, bundles or people.
- **Use `.venv/Scripts/python -m pytest`**, never `.venv/Scripts/pip` — the pip
  shim in this venv exits 1 silently.
- **`db.py` never prints.** `connect()` runs in every command, in every test,
  and once per thread in the viewer. No task may add a `print()` to `db.py`.
- **`machine_name` is `NOT NULL`** on `external_keys` and `hidden_keys`.
  Measured 2026-07-31 on the live catalog: all 2,275 rows and all 2,278 tpks
  across 13 key types carry one. There is no fallback branch to write.
- Full gate before declaring done: `scripts/windows/verify.ps1` (pytest, then
  `check_no_data_tracked.py`, then `leak_check.py`).

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `humble_catalog/db.py` | `SCHEMA` for both tables; migration 12 rebuilds `external_keys` | 1, 2 |
| `humble_catalog/parse_order.py` | carries `machine_name` out of each tpk | 1 |
| `humble_catalog/store.py` | writes `machine_name` | 1 |
| `tests/fixtures/order_book.json` | its one tpk gains a `machine_name` | 1 |
| `humble_catalog/keys.py` | joins `hidden_keys`; `stale_hides`, `missing_keys`; `--hidden` output | 3, 4, 5 |
| `humble_catalog/__main__.py` | `keys --hidden` flag | 5 |
| `humble_catalog/webapp/__init__.py` | `POST /api/keys/hide`, `/api/keys/unhide` | 6 |
| `humble_catalog/webapp/static/keys.js` | `displayState`, fourth chip, Hidden column, hide/unhide | 7 |
| `humble_catalog/webapp/static/style.css` | the hide/unhide control | 7 |
| `README.md`, `docs/BACKLOG.md`, `docs/TEST-DATA.md` | docs | 1, 8 |

## Deviation from the spec, decided while planning

The spec has **migration 12 print** the products whose keys are still missing.
That cannot be done: `db.py` never prints, and `connect()` runs in every
command, in every test, and once per thread in the viewer.

The check moves to `keys.report()` instead — Task 4. It is strictly better
placed there: a one-shot migration message can be missed forever, while a line
in the report the owner already reads self-clears the moment they `reparse`.
The query is unchanged (33 ms, measured). Task 8 updates the spec to match.

---

### Task 1: Re-key `external_keys` on `(gamekey, machine_name)`

The bug: Humble ships each storefront of a multi-store product as its own tpk,
all sharing one `human_name`. The primary key asserted one key per game per
order, and `store_order` writes with `INSERT OR REPLACE`, so the collision was a
silent last-write-wins. Measured: 2,278 tpks in `raw_orders`, 2,275 rows in
`external_keys`.

**Files:**
- Modify: `humble_catalog/db.py` (`SCHEMA` `external_keys`; new
  `_migrate_external_keys_to_machine_name`; new migration 12 block after the
  `< 11` block, around line 467)
- Modify: `humble_catalog/parse_order.py:30-35` (the `externals` comprehension)
- Modify: `humble_catalog/store.py:60-64` (the `INSERT OR REPLACE`)
- Modify: `tests/fixtures/order_book.json` (its one tpk)
- Modify: `docs/TEST-DATA.md`
- Test: `tests/test_store.py`, `tests/test_db.py`, `tests/test_parse_order.py`

**Interfaces:**
- Produces: `external_keys(gamekey, machine_name, human_name, key_type, raw)`
  with `PRIMARY KEY (gamekey, machine_name)`, `machine_name NOT NULL`.
  `parse_order` externals dicts gain a `"machine_name"` key.
  `db.SCHEMA` (module constant) is unchanged in name and stays importable.

- [ ] **Step 1: Add the invented collision names to `docs/TEST-DATA.md`**

Already present from the spec commit — verify both rows exist in the
"Owned game libraries (Steam / Heroic imports)" table:

```
| Twin Lantern | — (keyed only) | one product keyed on **two** storefronts in a single order (`twinlantern_steam`, `twinlantern_gog`), so both tpks share the `human_name` "Twin Lantern". The `external_keys` primary-key collision fixture: under the old `(gamekey, human_name)` key the second write silently replaced the first |
| Hollowmere | — (keyed only) | second `human_name` collision, one key lost, so the migration's "still missing" message has more than one product to name |
```

If either is missing, add it, then vet the name:

```bash
.venv/Scripts/python -c "import sys; sys.path.insert(0,'scripts'); import leak_check; t=leak_check.build_terms(); print([x for x in t if x.lower() in 'twin lantern hollowmere'])"
```

Expected: `[]`

- [ ] **Step 2: Write the failing regression test in `tests/test_store.py`**

Append to `tests/test_store.py`:

```python
def test_two_keys_for_one_product_both_survive(tmp_path):
    # Humble ships each storefront of a multi-store product as its own
    # tpk, all sharing one human_name. The old (gamekey, human_name)
    # primary key made INSERT OR REPLACE drop every one but the last, and
    # the survivor was whichever came last in all_tpks -- so the report
    # could end up checking a game against the wrong store's library.
    conn = db.connect(tmp_path / "t.db")
    raw = _raw()
    raw["tpkd_dict"] = {"all_tpks": [
        {"human_name": "Twin Lantern", "machine_name": "twinlantern_steam",
         "key_type": "steam"},
        {"human_name": "Twin Lantern", "machine_name": "twinlantern_gog",
         "key_type": "gog"},
    ]}
    store_order(conn, raw)
    got = {r["machine_name"] for r in
           conn.execute("SELECT machine_name FROM external_keys")}
    assert got == {"twinlantern_steam", "twinlantern_gog"}
```

- [ ] **Step 3: Run it to verify it fails**

Run:

```bash
.venv/Scripts/python -m pytest tests/test_store.py::test_two_keys_for_one_product_both_survive -q
```

Expected: FAIL with `sqlite3.OperationalError: no such column: machine_name`.

- [ ] **Step 4: Update `SCHEMA` in `humble_catalog/db.py`**

Replace the `external_keys` block (currently at `db.py:23-26`):

```python
CREATE TABLE IF NOT EXISTS external_keys (
  gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
  machine_name TEXT NOT NULL,
  human_name TEXT, key_type TEXT, raw TEXT,
  PRIMARY KEY (gamekey, machine_name));
```

- [ ] **Step 5: Add the migration helper to `humble_catalog/db.py`**

Add beside the other `_migrate_*` helpers (after `_migrate_cover_filenames`):

```python
def _migrate_external_keys_to_machine_name(conn):
    """Re-key external_keys from (gamekey, human_name) to (gamekey, machine_name).

    The old key is not unique. Humble ships each storefront of a
    multi-store product as its own tpk and every one carries the same
    human_name, so store_order's INSERT OR REPLACE turned the violated
    constraint into a silent last-write-wins. Measured on a 2,275-row
    catalog: raw_orders holds 2,278 tpks, and the three survivors of the
    two collisions were both the less useful key.

    A fresh database already has the new shape from SCHEMA, so the column
    check makes this a no-op there; only a database written by an older
    build is rebuilt. SQLite cannot alter a primary key, hence the copy.

    Rows whose `raw` will not parse are skipped rather than aborting on
    the NOT NULL column. No such row exists in the author's catalog --
    all 2,278 tpks across 13 key types carry a machine_name -- but a
    migration that leaves the database unopenable is the worst failure
    available here, so the guard is cheap insurance against future data.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(external_keys)")}
    if "machine_name" in cols:
        return
    conn.executescript("""
        CREATE TABLE external_keys_new (
          gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
          machine_name TEXT NOT NULL,
          human_name TEXT, key_type TEXT, raw TEXT,
          PRIMARY KEY (gamekey, machine_name));
        INSERT OR IGNORE INTO external_keys_new
          (gamekey, machine_name, human_name, key_type, raw)
          SELECT gamekey, json_extract(raw, '$.machine_name'),
                 human_name, key_type, raw
            FROM external_keys
           WHERE json_extract(raw, '$.machine_name') IS NOT NULL;
        DROP TABLE external_keys;
        ALTER TABLE external_keys_new RENAME TO external_keys;
    """)
```

- [ ] **Step 6: Add the migration 12 block**

In `_migrate`, immediately after the `< 11` block (ends `db.py:467`):

```python
    if conn.execute("PRAGMA user_version").fetchone()[0] < 12:
        # Re-keys external_keys on (gamekey, machine_name) and adds
        # hidden_keys. As with migrations 7 and 9-11, executescript(SCHEMA)
        # above has already created hidden_keys on this connection, so only
        # external_keys needs rebuilding here.
        _migrate_external_keys_to_machine_name(conn)
        conn.execute("PRAGMA user_version = 12")
        conn.commit()
```

- [ ] **Step 7: Carry `machine_name` through `parse_order` and `store`**

In `humble_catalog/parse_order.py`, replace the `externals` comprehension
(lines 30-35):

```python
    externals = [
        {"human_name": tpk.get("human_name"),
         # Subscripted, not .get()'d: every tpk in the catalog carries one
         # (2,278 of 2,278, across 13 key types), and the column is NOT
         # NULL. A malformed order should raise where it is parsed, not
         # write a NULL that fails a constraint two layers later.
         "machine_name": tpk["machine_name"],
         "key_type": tpk.get("key_type"),
         "raw": json.dumps(tpk)}
        for tpk in (raw.get("tpkd_dict") or {}).get("all_tpks", [])
    ]
```

In `humble_catalog/store.py`, replace the externals loop (lines 60-64):

```python
    for ext in externals:
        conn.execute(
            "INSERT OR REPLACE INTO external_keys "
            "(gamekey, machine_name, human_name, key_type, raw) "
            "VALUES (?,?,?,?,?)",
            (bundle["gamekey"], ext["machine_name"], ext["human_name"],
             ext["key_type"], ext["raw"]))
```

- [ ] **Step 8: Give the committed fixture's tpk a `machine_name`**

`tests/fixtures/order_book.json` holds one tpk with no `machine_name` — an
artifact of the anonymizer, not of real data. Without this, Step 7's subscript
raises and every `store_order` test fails.

In `tests/fixtures/order_book.json`, find the object inside
`tpkd_dict.all_tpks` (its `human_name` is `"DriveThruRPG Voucher"`) and add:

```json
      "machine_name": "drivethrurpgvoucher_coupon",
```

- [ ] **Step 9: Run the regression test and the whole store/parse suite**

```bash
.venv/Scripts/python -m pytest tests/test_store.py tests/test_parse_order.py tests/test_db.py -q
```

Expected: PASS, including `test_two_keys_for_one_product_both_survive`.

- [ ] **Step 10: Write the migration tests in `tests/test_db.py`**

Append (`import sqlite3` and `import json` are already at the top of the file —
add them if not):

```python
def _v11_with_old_external_keys(path, rows):
    """A user_version 11 database whose external_keys still has the old
    (gamekey, human_name) primary key. `rows` is [(human_name, raw_json)].
    """
    raw = sqlite3.connect(path)
    raw.executescript(db.SCHEMA)
    raw.executescript("""
        DROP TABLE external_keys;
        CREATE TABLE external_keys (
          gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
          human_name TEXT, key_type TEXT, raw TEXT,
          PRIMARY KEY (gamekey, human_name));
    """)
    raw.execute("INSERT INTO bundles (gamekey, name, url) VALUES "
                "('kv789', 'Humble Game Bundle: Key Vault', "
                "'https://example.invalid/kv789')")
    for human_name, blob in rows:
        raw.execute("INSERT INTO external_keys "
                    "(gamekey, human_name, key_type, raw) "
                    "VALUES ('kv789', ?, 'steam', ?)", (human_name, blob))
    raw.execute("PRAGMA user_version = 11")
    raw.commit()
    raw.close()


def test_migration_rekeys_external_keys_on_machine_name(tmp_path):
    path = tmp_path / "t.db"
    _v11_with_old_external_keys(path, [
        ("Twin Lantern", json.dumps({"machine_name": "twinlantern_steam"}))])
    conn = db.connect(path)
    try:
        row = conn.execute("SELECT gamekey, machine_name, human_name "
                           "FROM external_keys").fetchone()
        assert (row["gamekey"], row["machine_name"]) == \
            ("kv789", "twinlantern_steam")
        assert row["human_name"] == "Twin Lantern"
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 12
    finally:
        conn.close()


def test_the_migrated_table_admits_two_stores_of_one_product(tmp_path):
    # The point of the re-key: the old table could not hold both.
    path = tmp_path / "t.db"
    _v11_with_old_external_keys(path, [
        ("Twin Lantern", json.dumps({"machine_name": "twinlantern_steam"}))])
    conn = db.connect(path)
    try:
        conn.execute("INSERT INTO external_keys "
                     "(gamekey, machine_name, human_name, key_type, raw) "
                     "VALUES ('kv789', 'twinlantern_gog', 'Twin Lantern', "
                     "'gog', '{}')")
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) c FROM external_keys").fetchone()["c"] == 2
    finally:
        conn.close()


def test_migration_skips_a_key_whose_blob_will_not_parse(tmp_path):
    # NOT NULL would abort the whole migration on one bad row, leaving the
    # database unopenable. Skipping loses one key; aborting loses the lot.
    path = tmp_path / "t.db"
    _v11_with_old_external_keys(path, [
        ("Twin Lantern", json.dumps({"machine_name": "twinlantern_steam"})),
        ("Hollowmere", "not json at all")])
    conn = db.connect(path)
    try:
        got = [r["machine_name"] for r in
               conn.execute("SELECT machine_name FROM external_keys")]
        assert got == ["twinlantern_steam"]
    finally:
        conn.close()


def test_a_fresh_database_is_not_rebuilt_by_migration_12(tmp_path):
    # SCHEMA already makes the new shape, so the column check must make
    # this a no-op rather than dropping and recreating a populated table.
    conn = db.connect(tmp_path / "t.db")
    try:
        cols = {r["name"] for r in
                conn.execute("PRAGMA table_info(external_keys)")}
        assert "machine_name" in cols
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 12
    finally:
        conn.close()
```

- [ ] **Step 11: Run the migration tests**

```bash
.venv/Scripts/python -m pytest tests/test_db.py -q
```

Expected: PASS. Existing tests asserting `user_version == 11` will now fail —
update each to `>= 12` (they are at lines 107, 113, 181, 631, 639, 661, 671 and
assert the *current* version, which is exactly what this bumps).

- [ ] **Step 12: Run the full suite and commit**

```bash
.venv/Scripts/python -m pytest -q
```

Expected: PASS.

```bash
git add humble_catalog/db.py humble_catalog/parse_order.py humble_catalog/store.py tests/fixtures/order_book.json tests/test_db.py tests/test_store.py docs/TEST-DATA.md
git commit -m "fix(keys): re-key external_keys on (gamekey, machine_name)"
```

---

### Task 2: Add the `hidden_keys` table

**Files:**
- Modify: `humble_catalog/db.py` (`SCHEMA`, after the `external_keys` block)
- Test: `tests/test_db.py`, `tests/test_reset.py`

**Interfaces:**
- Produces: `hidden_keys(gamekey TEXT NOT NULL, machine_name TEXT NOT NULL,
  hidden_at TEXT NOT NULL, PRIMARY KEY (gamekey, machine_name))`. No foreign
  key. Absent from `reset.DERIVED_TABLES`, so `reset` preserves it.

- [ ] **Step 1: Write the failing test in `tests/test_reset.py`**

Append (match the file's existing fixture style for building a conn):

```python
def test_reset_keeps_hidden_keys_but_wipes_external_ones(tmp_path):
    # A hide is knowledge about what happened beyond this machine -- which
    # account a key was redeemed on, who a gift went to -- and no rebuild
    # can recover it. Dedupe dismissals can afford to be wiped because a
    # rebuild re-derives the pairs; this cannot.
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO bundles (gamekey, name, url) VALUES "
                 "('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789')")
    conn.execute("INSERT INTO external_keys "
                 "(gamekey, machine_name, human_name, key_type, raw) "
                 "VALUES ('kv789', 'twinlantern_steam', 'Twin Lantern', "
                 "'steam', '{}')")
    conn.execute("INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
                 "VALUES ('kv789', 'twinlantern_steam', "
                 "'2026-07-31T00:00:00+00:00')")
    conn.commit()
    reset.run(_conn=conn, _input=lambda _prompt: "RESET")
    assert conn.execute(
        "SELECT COUNT(*) c FROM external_keys").fetchone()["c"] == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM hidden_keys").fetchone()["c"] == 1
    conn.close()
```

- [ ] **Step 2: Run it to verify it fails**

```bash
.venv/Scripts/python -m pytest tests/test_reset.py::test_reset_keeps_hidden_keys_but_wipes_external_ones -q
```

Expected: FAIL with `sqlite3.OperationalError: no such table: hidden_keys`.

- [ ] **Step 3: Add the table to `SCHEMA`**

In `humble_catalog/db.py`, directly after the `external_keys` block:

```python
CREATE TABLE IF NOT EXISTS hidden_keys (
  gamekey TEXT NOT NULL, machine_name TEXT NOT NULL,
  hidden_at TEXT NOT NULL,
  PRIMARY KEY (gamekey, machine_name));
```

No foreign key to `external_keys`, deliberately and against the surrounding
convention: a hide has to outlive the row it names, and `reset` wipes
`external_keys` while keeping this table. An FK would either cascade the hides
away or make the reset fail. Add that as a comment above the block.

- [ ] **Step 4: Run the test**

```bash
.venv/Scripts/python -m pytest tests/test_reset.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/db.py tests/test_reset.py
git commit -m "feat(keys): add hidden_keys, preserved across reset"
```

---

### Task 3: `keys.report` annotates rows with `hidden_at`, and counts stale hides

**Files:**
- Modify: `humble_catalog/keys.py` (`_key_rows` ~line 90-108, `report` ~line
  111-200)
- Test: `tests/test_keys.py`

**Interfaces:**
- Consumes: `hidden_keys` and `external_keys.machine_name` from Tasks 1-2.
- Produces: `keys.stale_hides(conn) -> int`. Each row in `report()["rows"]`
  gains `"hidden_at"` (ISO string or `None`). `report()` gains
  `"stale_hides": int`. `report()["counts"]` and `["reported"]` are **unchanged**
  — hidden rows stay in both. `report()["expiring"]` now excludes hidden rows.

- [ ] **Step 1: Extend the test helper in `tests/test_keys.py`**

`_conn` currently takes `rows` as `[(product, key_type, raw_extra)]`. Add a
`hidden` parameter naming the products to hide. Replace the `_conn` signature
and add the hide loop before `conn.commit()`:

```python
def _conn(tmp_path, rows, library=(("steam", "Widget Quest"),),
          imported=("steam",), hidden=()):
    """A catalog holding `rows` as keys and `library` as imported games.

    `rows` is [(product, key_type, raw_extra)]; raw_extra is merged into
    the stored blob, so a test names only the fields it cares about.
    Every key belongs to one invented bundle. `hidden` names the products
    the owner has marked resolved.
    """
    conn = db.connect(tmp_path / "catalog.db")
    conn.execute("INSERT INTO bundles (gamekey, name, url, purchased_at) "
                 "VALUES ('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789', '2024-01-02T00:00:00')")
    for product, key_type, extra in rows:
        machine = product.lower().replace(" ", "") + "_ex"
        raw = {"human_name": product, "key_type": key_type,
               "machine_name": machine,
               "key_type_human_name": key_type.title()}
        raw.update(extra or {})
        conn.execute(
            "INSERT INTO external_keys "
            "(gamekey, machine_name, human_name, key_type, raw) "
            "VALUES ('kv789', ?, ?, ?, ?)",
            (machine, product, key_type, json.dumps(raw)))
    for product in hidden:
        conn.execute(
            "INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
            "VALUES ('kv789', ?, '2026-07-31T00:00:00+00:00')",
            (product.lower().replace(" ", "") + "_ex",))
    conn.commit()
```

The rest of `_conn` (the `for store in imported:` loop and `return conn`) is
unchanged.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_keys.py`:

```python
def test_a_hidden_row_is_annotated_not_removed(tmp_path):
    # report() annotates and never filters: the CLI and the viewer then
    # filter the same field, so they cannot disagree about what is hidden.
    conn = _conn(tmp_path, [("Cinder Vale", "steam", None)],
                 hidden=["Cinder Vale"])
    try:
        rows = keys.report(conn, now=NOW)["rows"]
        assert len(rows) == 1
        assert rows[0]["hidden_at"] == "2026-07-31T00:00:00+00:00"
    finally:
        conn.close()


def test_hiding_does_not_change_the_state_counts(tmp_path):
    # Hidden is an annotation on the server, not a fourth state: `counts`
    # must keep partitioning every key. The viewer's fourth chip is a
    # display choice that does not travel back across the route.
    plain = _states(tmp_path / "a", [("Cinder Vale", "steam", None)])
    hid = _states(tmp_path / "b", [("Cinder Vale", "steam", None)],
                  hidden=["Cinder Vale"])
    assert plain == hid
    assert hid["unredeemed"] == 1


def test_expiring_ignores_a_hidden_row(tmp_path):
    # The sibling of the tab badge. A hide that silences the row but
    # leaves the badge lit has not stopped the row reappearing.
    rows = [("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"})]
    conn = _conn(tmp_path, rows, hidden=["Amber Hollow"])
    try:
        assert keys.report(conn, now=NOW)["expiring"] == 0
    finally:
        conn.close()


def test_stale_hides_counts_a_hide_whose_key_is_gone(tmp_path):
    conn = _conn(tmp_path, [("Cinder Vale", "steam", None)],
                 hidden=["Cinder Vale"])
    try:
        assert keys.report(conn, now=NOW)["stale_hides"] == 0
        conn.execute("DELETE FROM external_keys")
        conn.commit()
        assert keys.report(conn, now=NOW)["stale_hides"] == 1
    finally:
        conn.close()


def test_a_hide_on_a_matched_key_is_not_stale(tmp_path):
    # The reason stale_hides is its own query rather than "hides minus
    # hidden rows shown": a matched key is not in `rows` either, so the
    # cheap derivation would call this stale and be wrong.
    conn = _conn(tmp_path, [("Widget Quest", "steam", None)],
                 hidden=["Widget Quest"])
    try:
        built = keys.report(conn, now=NOW)
        assert built["counts"]["matched"] == 1
        assert built["rows"] == []
        assert built["stale_hides"] == 0
    finally:
        conn.close()
```

- [ ] **Step 3: Run them to verify they fail**

```bash
.venv/Scripts/python -m pytest tests/test_keys.py -q -k "hidden or stale or expiring_ignores"
```

Expected: FAIL — `KeyError: 'hidden_at'` and `KeyError: 'stale_hides'`.

- [ ] **Step 4: Join `hidden_keys` in `_key_rows`**

In `humble_catalog/keys.py`, replace the query in `_key_rows` (lines 98-103):

```python
    for row in conn.execute(
            "SELECT k.human_name AS product, k.key_type AS key_type, "
            "       k.gamekey AS gamekey, k.machine_name AS machine_name, "
            "       k.raw AS raw, h.hidden_at AS hidden_at, "
            "       b.name AS bundle, b.url AS bundle_url, "
            "       b.purchased_at AS purchased_at "
            "FROM external_keys k JOIN bundles b ON b.gamekey = k.gamekey "
            "LEFT JOIN hidden_keys h ON h.gamekey = k.gamekey "
            "                       AND h.machine_name = k.machine_name"):
```

Update the docstring's "one parse yields machine_name, expiry_date,
redeemed_key_val and key_type_human_name" to drop `machine_name` — it is a
column now, so the parse yields three fields, and the field that decides a
key's identity is no longer read out of a blob.

- [ ] **Step 5: Add `stale_hides` to `humble_catalog/keys.py`**

Add above `report`:

```python
def stale_hides(conn):
    """How many hides name a key that is no longer in the catalog.

    `hidden_keys` has no foreign key and survives `reset`, so a hide can
    outlive the row it named -- and straight after a reset, before a
    reparse, every hide is stale.

    Its own query rather than "hides minus hidden rows shown", because
    that derivation is wrong: a hide on a key that has since become
    `matched` is not stale, but `matched` rows are not in `rows` either,
    so the cheap version would count it.
    """
    return conn.execute(
        "SELECT COUNT(*) FROM hidden_keys h WHERE NOT EXISTS ("
        "  SELECT 1 FROM external_keys k "
        "   WHERE k.gamekey = h.gamekey "
        "     AND k.machine_name = h.machine_name)").fetchone()[0]
```

- [ ] **Step 6: Annotate the row payload and adjust `expiring`**

In `report()`, change the `machine_name` line in the payload dict (line 163)
and add `hidden_at` beside `state`:

```python
            "machine_name": row["machine_name"],
```

```python
            "state": state,
            "hidden_at": row["hidden_at"],
            "near_match": near,
```

Then replace the returned dict's tail (lines 192-200):

```python
    return {
        "total": total,
        "counts": counts,
        "reported": len(rows),
        # Excludes hidden rows, unlike `counts` and `reported`. This is the
        # sibling of the tab badge -- "what needs attention this week" --
        # and a hide that leaves the badge lit has not stopped the row
        # reappearing. `counts` stays a partition of every key.
        "expiring": sum(1 for r in rows
                        if r["expires"] is not None and not r["expired"]
                        and not r["hidden_at"]),
        "stale_hides": stale_hides(conn),
        "libraries": libraries,
        "rows": rows,
    }
```

Update `report()`'s docstring return list to
`{total, counts, reported, expiring, stale_hides, libraries, rows}`, and note
that there is deliberately no `hidden` count — `format_report` counts `rows`
and the viewer computes its own chip counts, so a stored total would be a
second copy of a derivable number.

- [ ] **Step 7: Run the tests**

```bash
.venv/Scripts/python -m pytest tests/test_keys.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add humble_catalog/keys.py tests/test_keys.py
git commit -m "feat(keys): annotate reported rows with hidden_at"
```

---

### Task 4: Report the keys still missing from the catalog

Replaces the spec's migration print — see "Deviation from the spec" above.
Non-zero only until the first `reparse` after Task 1.

**Files:**
- Modify: `humble_catalog/keys.py`
- Test: `tests/test_keys.py`

**Interfaces:**
- Produces: `keys.missing_keys(conn) -> [{"product": str, "lost": int}]`,
  ordered most-lost first then by product. `report()` gains
  `"missing_keys": [...]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_keys.py`:

```python
def test_missing_keys_names_what_the_old_primary_key_dropped(tmp_path):
    # Non-zero only until the first reparse after the re-key. Reported
    # here rather than from the migration because db.py never prints, and
    # because a line in the report the owner already reads self-clears
    # once they reparse, where a one-shot message can be missed forever.
    conn = _conn(tmp_path, [("Twin Lantern", "steam", None)])
    try:
        order = {"gamekey": "kv789", "tpkd_dict": {"all_tpks": [
            {"human_name": "Twin Lantern", "machine_name": "twinlantern_ex"},
            {"human_name": "Twin Lantern", "machine_name": "twinlantern_gog"},
            {"human_name": "Hollowmere", "machine_name": "hollowmere_gog"},
        ]}}
        conn.execute("INSERT INTO raw_orders (gamekey, fetched_at, json) "
                     "VALUES ('kv789', '2026-07-31T00:00:00', ?)",
                     (json.dumps(order),))
        conn.commit()
        assert keys.report(conn, now=NOW)["missing_keys"] == [
            {"product": "Hollowmere", "lost": 1},
            {"product": "Twin Lantern", "lost": 1}]
    finally:
        conn.close()


def test_missing_keys_is_empty_when_every_tpk_is_stored(tmp_path):
    conn = _conn(tmp_path, [("Twin Lantern", "steam", None)])
    try:
        order = {"gamekey": "kv789", "tpkd_dict": {"all_tpks": [
            {"human_name": "Twin Lantern", "machine_name": "twinlantern_ex"}]}}
        conn.execute("INSERT INTO raw_orders (gamekey, fetched_at, json) "
                     "VALUES ('kv789', '2026-07-31T00:00:00', ?)",
                     (json.dumps(order),))
        conn.commit()
        assert keys.report(conn, now=NOW)["missing_keys"] == []
    finally:
        conn.close()


def test_missing_keys_tolerates_an_order_with_no_keys(tmp_path):
    # json_each(NULL) yields no rows, so an order without tpkd_dict needs
    # no guard -- verified against SQLite 3.49.
    conn = _conn(tmp_path, [("Twin Lantern", "steam", None)])
    try:
        conn.execute("INSERT INTO raw_orders (gamekey, fetched_at, json) "
                     "VALUES ('abc123', '2026-07-31T00:00:00', '{}')")
        conn.commit()
        assert keys.report(conn, now=NOW)["missing_keys"] == []
    finally:
        conn.close()
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/Scripts/python -m pytest tests/test_keys.py -q -k missing_keys
```

Expected: FAIL with `KeyError: 'missing_keys'`.

- [ ] **Step 3: Implement `missing_keys`**

Add to `humble_catalog/keys.py`, beside `stale_hides`:

```python
def missing_keys(conn):
    """Products whose tpks are in raw_orders but not in external_keys.

    Non-zero only until the first `reparse` after external_keys was
    re-keyed on (gamekey, machine_name). The old (gamekey, human_name)
    key silently dropped every storefront but the last of a multi-store
    product, and a migration that copies the table cannot recover rows
    that were never in it -- only a reparse from the cached orders can.

    One row-value NOT IN against the migrated table, measured at 33 ms on
    a 2,275-key catalog. json_each(NULL) yields no rows, so an order with
    no tpkd_dict needs no guard.

    A tpk carrying no machine_name would compare NULL and be skipped
    rather than reported. None exists -- 2,278 of 2,278 across 13 key
    types carry one -- and parse_order subscripts the field for the same
    reason.
    """
    return [{"product": r["product"], "lost": r["lost"]} for r in conn.execute(
        "SELECT json_extract(t.value, '$.human_name') AS product, "
        "       COUNT(*) AS lost "
        "  FROM raw_orders r, "
        "       json_each(json_extract(r.json, '$.tpkd_dict.all_tpks')) t "
        " WHERE (r.gamekey, json_extract(t.value, '$.machine_name')) NOT IN "
        "       (SELECT gamekey, machine_name FROM external_keys) "
        " GROUP BY product ORDER BY lost DESC, product")]
```

- [ ] **Step 4: Add it to the returned dict**

In `report()`, beside `stale_hides`:

```python
        "stale_hides": stale_hides(conn),
        "missing_keys": missing_keys(conn),
```

Add `missing_keys` to the docstring's return list.

- [ ] **Step 5: Run the tests**

```bash
.venv/Scripts/python -m pytest tests/test_keys.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/keys.py tests/test_keys.py
git commit -m "feat(keys): report the keys the old primary key dropped"
```

---

### Task 5: CLI — filter hidden rows, and `keys --hidden`

**Files:**
- Modify: `humble_catalog/keys.py` (`_line`, `format_report`, `run`)
- Modify: `humble_catalog/__main__.py` (the `p_keys` parser ~lines 190-203, and
  the `keys` dispatch ~line 303)
- Test: `tests/test_keys.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `report()["rows"][i]["hidden_at"]`, `report()["stale_hides"]`,
  `report()["missing_keys"]` from Tasks 3-4.
- Produces: `keys.format_report(report, encoding="utf-8", show_all=False,
  hidden=False) -> str`; `keys.run(show_all=False, hidden=False)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_keys.py`.

The helper takes `marked` for the products to hide and `**kw` for
`format_report`'s own flags, because `format_report`'s flag is also called
`hidden` and one call cannot pass the same keyword twice.

```python
def _text(tmp_path, rows, marked=(), **kw):
    """format_report's output for a catalog whose `marked` products are hidden.

    `marked` goes to _conn; **kw goes to format_report, whose own flag is
    also called `hidden`.
    """
    conn = _conn(tmp_path, rows, hidden=marked)
    try:
        return keys.format_report(keys.report(conn, now=NOW), **kw)
    finally:
        conn.close()


def test_the_default_report_omits_hidden_rows_and_says_how_many(tmp_path):
    rows = [("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
            ("Cinder Vale", "steam", {"expiry_date": "2026-08-12T00:00:00"})]
    text = _text(tmp_path, rows, marked=["Cinder Vale"])
    assert "Amber Hollow" in text
    assert "Cinder Vale" not in text
    assert "1 hidden" in text


def test_hidden_lists_the_hidden_rows_with_their_date(tmp_path):
    rows = [("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
            ("Cinder Vale", "steam", None)]
    text = _text(tmp_path, rows, marked=["Cinder Vale"], hidden=True)
    assert "Cinder Vale" in text
    assert "2026-07-31" in text
    assert "Amber Hollow" not in text


def test_hidden_says_so_when_nothing_is_hidden(tmp_path):
    text = _text(tmp_path, [("Cinder Vale", "steam", None)], hidden=True)
    assert "No keys are hidden." in text


def test_hidden_reports_the_hides_whose_key_is_gone(tmp_path):
    conn = _conn(tmp_path, [("Cinder Vale", "steam", None)],
                 hidden=["Cinder Vale"])
    try:
        conn.execute("DELETE FROM external_keys")
        conn.commit()
        text = keys.format_report(keys.report(conn, now=NOW), hidden=True)
        assert "1 hide" in text
        assert "reparse" in text
    finally:
        conn.close()


def test_the_report_names_the_products_whose_keys_are_missing(tmp_path):
    conn = _conn(tmp_path, [("Twin Lantern", "steam", None)])
    try:
        order = {"gamekey": "kv789", "tpkd_dict": {"all_tpks": [
            {"human_name": "Twin Lantern", "machine_name": "twinlantern_ex"},
            {"human_name": "Twin Lantern", "machine_name": "twinlantern_gog"},
        ]}}
        conn.execute("INSERT INTO raw_orders (gamekey, fetched_at, json) "
                     "VALUES ('kv789', '2026-07-31T00:00:00', ?)",
                     (json.dumps(order),))
        conn.commit()
        text = keys.format_report(keys.report(conn, now=NOW))
        assert "Twin Lantern (1)" in text
        assert "reparse" in text
    finally:
        conn.close()
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/Scripts/python -m pytest tests/test_keys.py -q -k "hidden or missing"
```

Expected: FAIL — `format_report() got an unexpected keyword argument 'hidden'`.

- [ ] **Step 3: Teach `_line` to print a hide date**

In `humble_catalog/keys.py`, replace `_line`'s opening (lines 210-217):

```python
def _line(row, width, hidden=False):
    """One reported row, as a printable line.

    `hidden` swaps the leading column from the expiry to the date the
    owner hid the row -- same columns otherwise, so the two listings stay
    comparable rather than being two different tables.
    """
    if hidden:
        when = (row["hidden_at"] or "")[:10]
    else:
        days = row["days_left"]
        # "today", not "in 0 days" -- and it matches what keys.js renders,
        # so the same key does not read differently in the two surfaces.
        when = ("" if days is None
                else ("today" if days == 0 else f"in {days} days"))
        if days is None and row["expired"]:
            when = "expired"
```

The rest of `_line` is unchanged.

- [ ] **Step 4: Thread `hidden` through `_block`**

```python
def _block(lines, heading, rows, hidden=False):
    """One headed block, padded to its OWN widest name.

    Per block rather than per report: the undated rows are the great
    majority and hold the longest names, so a shared width made the
    default report's 63 lines carry ~40 columns of padding for rows it
    was not even printing.
    """
    if not rows:
        return
    width = min(max(len(r["product"] or "") for r in rows), MAX_NAME)
    lines.append(f"  {heading} ({len(rows)}):")
    lines.extend(_line(row, width, hidden=hidden) for row in rows)
    lines.append("")
```

- [ ] **Step 5: Rewrite `format_report`**

Replace `format_report` in `humble_catalog/keys.py`:

```python
def format_report(report, encoding="utf-8", show_all=False, hidden=False):
    """The report as printable text, safe for a console using `encoding`.

    The default prints the counts plus only the rows with a live expiry --
    what needs attention this week. `--all` adds the undated and the
    already-expired rows, which together are the great majority: a report
    that leads with 700 lines is one nobody reads to the end.

    `hidden` lists the rows the owner has marked resolved *instead of*
    the report. Every hidden row, newest hide first, in one block --
    `show_all` does not apply. The main report splits into live/undated/
    expired because it is triage; a list of the owner's own dismissals is
    not, and "which of my dismissals expire soon" is not a question
    hiding leaves open.
    """
    counts = report["counts"]
    rows = report["rows"]
    if hidden:
        marked = sorted((r for r in rows if r["hidden_at"]),
                        key=lambda r: (r["hidden_at"], r["product"] or ""),
                        reverse=True)
        lines = []
        _block(lines, "Hidden", marked, hidden=True)
        if not marked:
            lines.append("  No keys are hidden.")
            lines.append("")
        stale = report["stale_hides"]
        if stale:
            noun = "hide" if stale == 1 else "hides"
            lines.append(f"  {stale:,} {noun} refer to keys no longer in the "
                         f"catalog")
            lines.append("  (run 'reparse' if you have just reset).")
        return stats.console_safe("\n".join(lines).rstrip(), encoding)
    # "1 key", not "1 keys": a one-item tier read "1 items" in the bundle
    # preview, and no test caught it -- a browser did.
    noun = "key" if report["total"] == 1 else "keys"
    lines = [f"{report['total']:,} {noun} - {counts['matched']:,} in a library, "
             f"{counts['unredeemed'] + counts['uncertain']:,} not, "
             f"{counts['uncheckable']:,} uncheckable", ""]
    shown = [r for r in rows if not r["hidden_at"]]
    live = [r for r in shown if r["expires"] and not r["expired"]]
    undated = [r for r in shown if not r["expires"]]
    expired = [r for r in shown if r["expired"]]
    _block(lines, "Expiring", live)
    if show_all:
        _block(lines, "No expiry date", undated)
        _block(lines, "Already expired", expired)
    elif undated or expired:
        lines.append(f"  ('keys --all' for the other "
                     f"{len(undated) + len(expired):,}: {len(undated):,} "
                     f"undated, {len(expired):,} already expired)")
        lines.append("")
    n_hidden = len(rows) - len(shown)
    if n_hidden:
        lines.append(f"  ({n_hidden:,} hidden; 'keys --hidden' lists them)")
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
    missing = report["missing_keys"]
    if missing:
        total_lost = sum(m["lost"] for m in missing)
        named = ", ".join(f"{m['product']} ({m['lost']})" for m in missing[:5])
        lines.append(f"  {total_lost:,} keys in your orders are missing from "
                     f"the catalog: {named}. Run 'reparse' to recover them.")
    lines.append("  Matching is by title and APPROXIMATE. A revealed key was "
                 "only displayed, which is not the same as activated.")
    # Degraded at the CLI boundary only, exactly as bundle_preview does:
    # the web route keeps the real characters, and product names are
    # arbitrary data that may hold anything.
    return stats.console_safe("\n".join(lines).rstrip(), encoding)
```

- [ ] **Step 6: Thread the flag through `run`**

```python
def run(show_all=False, hidden=False):
    """Count and print. The `keys` subcommand's entry point."""
    conn = db.connect()
    try:
        built = report(conn)
    finally:
        conn.close()
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(format_report(built, encoding, show_all=show_all, hidden=hidden))
```

- [ ] **Step 7: Add the CLI flag**

In `humble_catalog/__main__.py`, after the existing `--all` argument
(line ~203):

```python
    p_keys.add_argument(
        "--hidden", action="store_true",
        help="List the keys you have hidden in the viewer, instead of the "
             "report")
```

And the dispatch (line ~305):

```python
    elif args.command == "keys":
        from humble_catalog import keys
        keys.run(show_all=args.all, hidden=args.hidden)
```

- [ ] **Step 8: Run the tests**

```bash
.venv/Scripts/python -m pytest tests/test_keys.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add humble_catalog/keys.py humble_catalog/__main__.py tests/test_keys.py
git commit -m "feat(keys): filter hidden rows, and add 'keys --hidden'"
```

---

### Task 6: The hide and unhide routes

**Files:**
- Modify: `humble_catalog/webapp/__init__.py` (after `/api/keys`, ~line 111)
- Test: `tests/test_webapp.py`

**Interfaces:**
- Produces: `POST /api/keys/hide` and `POST /api/keys/unhide`, each taking
  `{"gamekey": str, "machine_name": str}` and returning `{"ok": true}`, or
  `{"error": str}` with 400.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_webapp.py`, following the file's existing client fixture
style:

```python
def test_hiding_a_key_records_it(client, conn):
    conn.execute("INSERT INTO bundles (gamekey, name, url) VALUES "
                 "('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789')")
    conn.execute("INSERT INTO external_keys "
                 "(gamekey, machine_name, human_name, key_type, raw) "
                 "VALUES ('kv789', 'cindervale_steam', 'Cinder Vale', "
                 "'steam', '{}')")
    conn.commit()
    resp = client.post("/api/keys/hide", json={
        "gamekey": "kv789", "machine_name": "cindervale_steam"})
    assert resp.status_code == 200
    row = conn.execute("SELECT * FROM hidden_keys").fetchone()
    assert row["machine_name"] == "cindervale_steam"
    assert row["hidden_at"].startswith("20")


def test_hiding_twice_keeps_the_first_timestamp(client, conn):
    conn.execute("INSERT INTO bundles (gamekey, name, url) VALUES "
                 "('kv789', 'Humble Game Bundle: Key Vault', 'u')")
    conn.execute("INSERT INTO external_keys "
                 "(gamekey, machine_name, human_name, key_type, raw) "
                 "VALUES ('kv789', 'cindervale_steam', 'Cinder Vale', "
                 "'steam', '{}')")
    conn.commit()
    body = {"gamekey": "kv789", "machine_name": "cindervale_steam"}
    client.post("/api/keys/hide", json=body)
    first = conn.execute("SELECT hidden_at FROM hidden_keys").fetchone()[0]
    client.post("/api/keys/hide", json=body)
    assert conn.execute(
        "SELECT hidden_at FROM hidden_keys").fetchone()[0] == first


def test_hiding_an_unknown_key_is_rejected(client, conn):
    resp = client.post("/api/keys/hide", json={
        "gamekey": "nope", "machine_name": "nothing_steam"})
    assert resp.status_code == 400


def test_unhiding_works_on_a_hide_whose_key_is_gone(client, conn):
    # Deliberately asymmetric with hide. Requiring the key to exist would
    # make exactly the stale hides un-unhideable -- the rows most in need
    # of removing, since every hide is stale straight after a reset.
    conn.execute("INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
                 "VALUES ('kv789', 'ghost_steam', '2026-07-31T00:00:00')")
    conn.commit()
    resp = client.post("/api/keys/unhide", json={
        "gamekey": "kv789", "machine_name": "ghost_steam"})
    assert resp.status_code == 200
    assert conn.execute(
        "SELECT COUNT(*) c FROM hidden_keys").fetchone()["c"] == 0


def test_unhiding_something_not_hidden_is_a_no_op(client, conn):
    resp = client.post("/api/keys/unhide", json={
        "gamekey": "kv789", "machine_name": "never_hidden"})
    assert resp.status_code == 200
```

If `tests/test_webapp.py` has no `conn` fixture exposing the app's connection,
follow whatever pattern the existing mutation-route tests (`/api/dismiss_pair`,
`/api/merge`) use to reach the database, and mirror it.

- [ ] **Step 2: Run to verify failure**

```bash
.venv/Scripts/python -m pytest tests/test_webapp.py -q -k "hiding or unhiding"
```

Expected: FAIL with 404 (route not registered).

- [ ] **Step 3: Add the routes**

In `humble_catalog/webapp/__init__.py`, after the `/api/keys` route (line ~111).
Add `import datetime as dt` at the top of the file if absent:

```python
    def _key_ref():
        """(gamekey, machine_name) from the request body, or (None, None).

        Both travel in a POST body, never a query string: machine_name is
        derived from the product title, so it names something owned, and
        query strings reach access logs and browser history. Same reason
        filter-aware export posts its id list.
        """
        data = request.get_json() or {}
        gamekey, machine_name = data.get("gamekey"), data.get("machine_name")
        if not isinstance(gamekey, str) or not gamekey \
                or not isinstance(machine_name, str) or not machine_name:
            return None, None
        return gamekey, machine_name

    @app.post("/api/keys/hide")
    def hide_key():
        gamekey, machine_name = _key_ref()
        if gamekey is None:
            return jsonify({"error": "gamekey and machine_name required"}), 400
        exists = conn().execute(
            "SELECT 1 FROM external_keys WHERE gamekey=? AND machine_name=?",
            (gamekey, machine_name)).fetchone()
        if not exists:
            return jsonify({"error": "no such key"}), 400
        # INSERT OR IGNORE, so hiding twice keeps the first timestamp
        # rather than refreshing it -- the date answers "when did I decide
        # this", and a second click is not a second decision.
        conn().execute(
            "INSERT OR IGNORE INTO hidden_keys "
            "(gamekey, machine_name, hidden_at) VALUES (?,?,?)",
            (gamekey, machine_name,
             dt.datetime.now(dt.timezone.utc).isoformat()))
        conn().commit()
        return jsonify({"ok": True})

    @app.post("/api/keys/unhide")
    def unhide_key():
        gamekey, machine_name = _key_ref()
        if gamekey is None:
            return jsonify({"error": "gamekey and machine_name required"}), 400
        # No existence check against external_keys, unlike hide. A hide
        # outlives the key it names -- every hide is stale straight after
        # a reset -- and those are the rows most in need of removing.
        conn().execute(
            "DELETE FROM hidden_keys WHERE gamekey=? AND machine_name=?",
            (gamekey, machine_name))
        conn().commit()
        return jsonify({"ok": True})
```

- [ ] **Step 4: Run the tests**

```bash
.venv/Scripts/python -m pytest tests/test_webapp.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "feat(keys): add hide and unhide routes"
```

---

### Task 7: The viewer — fourth chip, Hidden column, hide/unhide

**Files:**
- Modify: `humble_catalog/webapp/static/keys.js`
- Modify: `humble_catalog/webapp/static/style.css` (after `.key-uncheckable`,
  line ~414)
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: `POST /api/keys/hide`, `/api/keys/unhide` (Task 6);
  `row.hidden_at` (Task 3).
- Produces: `displayState(row) -> string`; `shownKeys()` filters on it;
  `keyChipCounts() -> {state: n}`; `toggleKeyHidden(row)` posts and updates.

- [ ] **Step 1: Write the failing tests**

In `tests/test_webapp_js.py`, extend `_KEY_PAYLOAD`: add `hidden_at: null` to
each of the three existing rows, add `stale_hides: 0, missing_keys: []` beside
`expiring: 1`, and append a fourth row:

```javascript
    {product: "Cinder Vale", machine_name: "cindervale_ex", gamekey: "kv789",
     store: "steam", key_type_label: "Steam",
     bundle: "Humble Game Bundle: Key Vault",
     bundle_url: "https://example.invalid/kv789", purchased_at: null,
     expires: null, expired: false, days_left: null, revealed: true,
     state: "unredeemed", hidden_at: "2026-07-31T00:00:00+00:00",
     near_match: null}
```

Update `total: 4, reported: 3` to `total: 5, reported: 4` and
`counts: {matched: 1, unredeemed: 2, uncertain: 1, uncheckable: 1}`.

Then append the tests:

```python
def test_a_hidden_row_is_not_shown_by_default():
    shown = _with_keys('app.shownKeys().map((r) => r.product)')
    assert shown == ["Amber Hollow", "Starfall Rally Turbo"]


def test_the_hidden_chip_shows_the_hidden_rows():
    shown = _with_keys("""(() => {
      app.setKeyStates(["hidden"]);
      return app.shownKeys().map((r) => r.product);
    })()""")
    assert shown == ["Cinder Vale"]


def test_a_hidden_row_keeps_its_underlying_state_in_the_table():
    # Only chip membership changes. Nothing about why the row was
    # reported is lost from the display.
    html = _with_keys("""(() => {
      app.setKeyStates(["hidden"]);
      app.renderKeys();
      return dom.writes["#keys-panel"];
    })()""")
    assert "Not in a library" in html


def test_every_chip_count_equals_the_rows_it_delivers():
    # The statistics panel shipped a row reading "Unmatched 4" that jumped
    # to 8 rows. Counting by displayState makes the four chips partition
    # the reported rows by construction, so this cannot drift.
    pairs = _with_keys("""(() => {
      const counts = app.keyChipCounts();
      const out = {};
      for (const s of Object.keys(counts)) {
        app.setKeyStates([s]);
        out[s] = [counts[s], app.shownKeys().length];
      }
      return out;
    })()""")
    for state, (promised, delivered) in pairs.items():
        assert promised == delivered, state


def test_the_keys_badge_ignores_hidden_rows():
    written = _with_keys("""(() => {
      dom.reset();
      app.setPending({keys: app.keysExpiring()});
      app.renderBadges();
      return dom.writes["#tab-keys .badge-count:text"];
    })()""")
    assert written == "1"


def test_the_table_offers_hide_and_unhide():
    html = _with_keys("""(() => {
      app.setKeyStates(["unredeemed", "uncertain", "uncheckable", "hidden"]);
      app.renderKeys();
      return dom.writes["#keys-panel"];
    })()""")
    assert "key-hide" in html
    assert ">hide<" in html
    assert ">unhide<" in html
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/Scripts/python -m pytest tests/test_webapp_js.py -q -k "hidden or chip_count or hide"
```

Expected: FAIL — `app.keyChipCounts is not a function`, and the default-shown
list still contains `Cinder Vale`.

- [ ] **Step 3: Add the fourth state and `displayState` to `keys.js`**

Replace the `KEY_STATES` block and the state helpers at the top of
`humble_catalog/webapp/static/keys.js`:

```javascript
// The chips, in display order. The first three are the states the server
// reports; `hidden` is a display-only fourth, derived from a row's
// hidden_at. On the server hidden stays an annotation and `counts` keeps
// partitioning every key -- this fourth bucket does not travel back
// across the route.
const KEY_STATES = [
  {state: "unredeemed",  label: "Not in a library"},
  {state: "uncertain",   label: "Near match"},
  {state: "uncheckable", label: "No importer"},
  {state: "hidden",      label: "Hidden"},
];

let keyRows = [], keyCounts = {}, keyLibraries = {}, keyTotal = 0;
// uncheckable is off by default: for those stores "not in any library" is
// unfalsifiable, so leaving them in would make the list mostly caveat.
// hidden is off because that is the whole point of hiding.
let keyStates = new Set(["unredeemed", "uncertain"]);

// A row's chip, which is its server state unless the owner has hidden it.
// One function reconciles the server's three states with the viewer's
// four chips; an earlier design made hidden a second filter axis and
// needed a pool indirection plus a chip whose count did not match what
// clicking it delivered.
const displayState = (r) => (r.hidden_at ? "hidden" : r.state);

const keysExpiring = () =>
  keyRows.filter((r) => r.expires && !r.expired && !r.hidden_at).length;

const shownKeys = () =>
  keyRows.filter((r) => keyStates.has(displayState(r)));

// Counted here, not read from keyCounts: keyCounts partitions every key
// including matched and hidden ones, so a chip reading "Not in a library
// 624" would deliver fewer than 624 once hidden rows move to their own
// bucket. Counting by displayState makes the chips partition the reported
// rows, so a count always equals what clicking it shows.
function keyChipCounts() {
  const counts = {};
  for (const s of KEY_STATES) counts[s.state] = 0;
  for (const r of keyRows) counts[displayState(r)] += 1;
  return counts;
}

function setKeyStates(states) {
  keyStates = new Set(states);
}
```

- [ ] **Step 4: Render the chips, the column and the control**

In `renderKeys()`, replace the `chips` line to use `keyChipCounts()`:

```javascript
  const rows = shownKeys();
  const counts = keyChipCounts();
  const chips = KEY_STATES.map((s) => `<button class="key-chip${
    keyStates.has(s.state) ? " on" : ""}" data-state="${s.state}">${
    esc(s.label)} ${counts[s.state] || 0}</button>`).join("");
```

Add the header cell — replace the `<thead>` row:

```javascript
      <th>Product</th><th>Store</th><th>Bundle</th><th>Purchased</th>
      <th>Expires</th><th>Revealed</th><th>State</th><th>Hidden</th>
```

And the body cell — replace the final `</tr>` cell of each row, keeping the
State cell showing the *underlying* state:

```javascript
      <td>${esc((KEY_STATES.find((s) => s.state === r.state) || {}).label
                || r.state)}</td>
      <td class="key-hide-cell">${
        r.hidden_at ? esc(r.hidden_at.slice(0, 10)) + " " : ""}<button
        class="key-hide" data-gamekey="${esc(r.gamekey)}"
        data-machine="${esc(r.machine_name)}">${
        r.hidden_at ? "unhide" : "hide"}</button></td>
```

- [ ] **Step 5: Add the click branch and the mutation**

Add above the existing listener:

```javascript
// Posts, then patches the row in place. Deliberately NOT a loadKeys()
// refetch: keys.report classifies every key against the store pools and
// measures ~2.5 s, which is not a button click. Same trade the statistics
// panel made -- touch the mutation call site rather than reload
// everything.
async function toggleKeyHidden(gamekey, machine) {
  const row = keyRows.find(
    (r) => r.gamekey === gamekey && r.machine_name === machine);
  if (!row) return;
  const path = row.hidden_at ? "/api/keys/unhide" : "/api/keys/hide";
  const resp = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({gamekey, machine_name: machine}),
  });
  if (!resp.ok) return;
  row.hidden_at = row.hidden_at ? null : new Date().toISOString();
  renderKeys();
  // The badge is computed by load() in app.js, which does not run again
  // here, so the one section that changed refreshes its own count.
  setPending({keys: keysExpiring()});
  renderBadges();
}
```

Extend the delegated listener:

```javascript
$("#keys-panel").addEventListener("click", (ev) => {
  const hide = ev.target.closest?.(".key-hide");
  if (hide) {
    toggleKeyHidden(hide.dataset.gamekey, hide.dataset.machine);
    return;
  }
  const chip = ev.target.closest?.(".key-chip");
  if (!chip) return;
  const state = chip.dataset.state;
  if (keyStates.has(state)) keyStates.delete(state); else keyStates.add(state);
  renderKeys();
});
```

- [ ] **Step 6: Style the control**

In `humble_catalog/webapp/static/style.css`, after `.key-uncheckable`
(line ~414):

```css
/* Same reason as .key-chip above: an unstyled <button> keeps the browser's
   grey default, which glares in dark mode. The statistics panel shipped
   exactly that bug, and the JS harness cannot see it -- its stubbed DOM
   has no computed styles. */
.key-hide { cursor: pointer; font-size: .85em; background: none;
            border: none; padding: 0; color: var(--accent);
            text-decoration: underline; }
.key-hide-cell { white-space: nowrap; }
tr.key-is-hidden td { opacity: .6; }
```

Add `key-is-hidden` to the row's class list in `renderKeys()`:

```javascript
    ${rows.map((r) => `<tr class="key-${r.state}${
      r.hidden_at ? " key-is-hidden" : ""}">
```

- [ ] **Step 7: Run the JS tests**

```bash
.venv/Scripts/python -m pytest tests/test_webapp_js.py -q
```

Expected: PASS. If Node is not installed these skip — install Node, since this
task's central test is a JS one.

- [ ] **Step 8: Check it in a real browser**

The harness's stubbed DOM has no computed styles, so the styling is invisible
to it. Start the viewer and look at the Keys tab in **both** themes:

```bash
.venv/Scripts/python -m humble_catalog serve
```

Confirm: the four chips render and toggle; the hide link reads as a link, not
a grey default button, in light and dark; hiding a row removes it from the
default view and drops the tab badge; the Hidden chip shows it again with its
date; unhide restores it.

**Do not screenshot this for a commit** — a Keys panel frames bundle names,
product names, stores and counts at once.

- [ ] **Step 9: Commit**

```bash
git add humble_catalog/webapp/static/keys.js humble_catalog/webapp/static/style.css tests/test_webapp_js.py
git commit -m "feat(keys): hide resolved keys from the viewer"
```

---

### Task 8: Docs, spec reconciliation, and the full gate

**Files:**
- Modify: `README.md` (the `keys` entry)
- Modify: `humble_catalog/__main__.py` (the `p_keys` `description`)
- Modify: `docs/superpowers/specs/2026-07-31-hidden-keys-design.md`
- Modify: `docs/BACKLOG.md`

- [ ] **Step 1: Reconcile the spec with the migration-print deviation**

In the spec's "Migration 12" section, replace the paragraph beginning "**The
migration reports what is still missing.**" and its code block with:

```markdown
**The migration stays silent.** `db.py` never prints — `connect()` runs in
every command, in every test, and once per thread in the viewer — so the
"three keys are still missing" message cannot live here. It moves to
`keys.report()`/`format_report()` instead (see below), which is the better
home anyway: a one-shot migration message can be missed forever, while a
line in the report the owner already reads self-clears the moment they
`reparse`.
```

Then in the `keys.py` section, add `missing_keys` beside `stale_hides` in the
returned-fields list, and record the CLI line:

```markdown
- **`missing_keys`** — the products whose tpks are in `raw_orders` but not in
  `external_keys`, most-lost first. One row-value `NOT IN`, measured at 33 ms.
  Non-zero only until the first `reparse` after the re-key. `format_report`
  prints: `3 keys in your orders are missing from the catalog: Twin Lantern
  (2), Hollowmere (1). Run 'reparse' to recover them.`
```

- [ ] **Step 2: Update `README.md` and `--help`**

In `README.md`'s `keys` entry, add the flag beside `--all`:

```markdown
`--hidden` lists the keys you have hidden in the viewer, instead of the
report. Hiding is the assertion "wherever this one ended up, I know it is
resolved"; it is per key rather than per game, so the same game keyed in two
bundles stays two rows.
```

In `humble_catalog/__main__.py`, extend `p_keys`'s `description` with one
sentence:

```
"Rows you have hidden in the viewer are left out; 'keys --hidden' lists "
"those instead."
```

- [ ] **Step 3: Move the backlog entry to Done**

Cut the **External keys → Hiding a resolved row** entry from `## Open` and add
to `## Done (formerly on this list)`, recording what measurement changed:

```markdown
- **Hiding a resolved key** —
  `docs/superpowers/specs/2026-07-31-hidden-keys-design.md`.
  `hidden_keys` records the owner's "wherever this one ended up, I know it
  is resolved", keyed `(gamekey, machine_name)` and kept out of
  `DERIVED_TABLES` so a reset preserves it. The viewer hides and unhides
  per row; `keys --hidden` lists them; the CLI report and the tab badge
  both go quiet.
  Four things measurement settled. `machine_name` is present on every one
  of the 2,275 rows and all 2,278 tpks across 13 key types, so the column
  is NOT NULL with no fallback branch and no test that could reach one.
  The old `(gamekey, human_name)` key did not merely drop three rows — it
  kept an **arbitrary** one, and in both colliding orders the survivor was
  the less useful key, so the report was checking two games against the
  wrong store's library. Those three keys are not in `external_keys` at
  all, so the migration cannot recover them; `keys` now names them and
  points at `reparse`, because `db.py` never prints and a one-shot
  migration message can be missed forever. And `keys.report` measures
  ~2.5 s, which is what rules out redrawing the panel by refetching after
  every hide.
  Hidden is an annotation on the server and a fourth chip in the browser:
  `counts` still partitions every key, and the chip counts moved to the
  browser so a chip cannot promise more rows than clicking it delivers —
  the statistics panel's "Unmatched 4 returned 8" bug, pinned in advance.
  Two deliberate asymmetries. `hidden_keys` has no foreign key, because a
  hide must outlive the key it names; and hide checks that the key exists
  while unhide does not, since requiring it would make exactly the stale
  hides un-unhideable.
```

Also add a new entry under `## Open`:

```markdown
### Keys (identified 2026-07-31 while building hiding)

- **`/api/keys` takes ~2.5 s** — `keys.report` classifies all 2,275 keys
  against the store pools on every call, which is why the Keys tab is slow
  to populate and why hiding patches its row in place rather than
  refetching. Pre-existing and unrelated to hiding. The likely shape is
  caching the per-store pools or the classification, but it wants
  measuring before it wants fixing.
```

- [ ] **Step 4: Update the spec's "Deferred" section**

The spec already defers "hiding a whole game". Leave it.

- [ ] **Step 5: Run the full gate**

```bash
.venv/Scripts/python -m pytest -q
```

Expected: PASS.

```bash
.venv/Scripts/python scripts/leak_check.py
```

Expected: `clean`. Run it on its own, never piped.

```bash
.venv/Scripts/python scripts/check_no_data_tracked.py
```

Expected: `clean: no data files in tracked files and all history`.

- [ ] **Step 6: Verify against the live catalog**

```bash
.venv/Scripts/python -m humble_catalog keys
```

Expected: the migration has run; the report names the products whose keys are
missing and points at `reparse`.

```bash
.venv/Scripts/python -m humble_catalog reparse
```

Then:

```bash
.venv/Scripts/python -m humble_catalog keys
```

Expected: the missing-keys line is gone, and `external_keys` now holds 2,278
rows:

```bash
.venv/Scripts/python -c "from humble_catalog import db; c=db.connect(); print(c.execute('SELECT COUNT(*) FROM external_keys').fetchone()[0])"
```

Expected: `2278`.

**This output names owned products.** It is terminal output in the same
category as `harvest --failures` — nothing scans it, so judge it by eye before
pasting it anywhere.

- [ ] **Step 7: Commit**

```bash
git add README.md humble_catalog/__main__.py docs/BACKLOG.md docs/superpowers/specs/2026-07-31-hidden-keys-design.md
git commit -m "docs(keys): document hiding, and close the backlog entry"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| `external_keys` gains `machine_name`, re-keyed | 1 |
| `hidden_keys` table, no FK | 2 |
| Migration 12, unparseable-blob guard, fresh-DB no-op | 1 |
| Migration reports what is missing | 4 (relocated — see Deviation) |
| `reset.py`/`backup.py` untouched | 2 (test only) |
| Stale hides | 3 (count), 5 (line) |
| `keys.py` join, `hidden_at`, no `hidden` count | 3 |
| `expiring` excludes hidden | 3 |
| CLI filtering, `keys --hidden`, no include mode | 5 |
| Routes, POST body, hide/unhide asymmetry, idempotence | 6 |
| Viewer fourth chip, `displayState`, chip counts, badge, styling | 7 |
| Testing section | 1, 2, 3, 4, 5, 6, 7 |
| Privacy | Global Constraints, 1, 7, 8 |
| Verification, Docs | 8 |

**Type consistency:** `displayState`, `shownKeys`, `keyChipCounts`,
`toggleKeyHidden`, `keysExpiring` are used in Task 7's tests exactly as defined
in its steps. `stale_hides(conn)`, `missing_keys(conn)` and
`format_report(..., hidden=)` are used in Tasks 5 and 8 as defined in Tasks 3
and 4. `hidden_at` is the field name everywhere — never `hiddenAt`.

**One known ripple:** Task 1 Step 11 changes existing `user_version == 11`
assertions to `>= 12`. Seven call sites in `tests/test_db.py`.
