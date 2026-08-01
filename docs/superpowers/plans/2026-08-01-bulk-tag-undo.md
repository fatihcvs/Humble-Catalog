# Bulk tag undo — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the viewer a single-level undo for a bulk user-tag add or
remove, so a mis-aimed bulk operation can be reversed on exactly the rows
it changed.

**Architecture:** `bulk_user_tag` already computes the set of rows it
actually changed and throws it away, returning only a count; it returns
the id list instead, and `POST /api/user-tags/bulk` answers with `ids`.
The viewer remembers the last such operation in one module-level variable
holding the *inverse* verb, and an Undo button in the bulk bar re-posts to
the same route. No schema change, no migration, no new route.

**Tech Stack:** Python 3 + Flask + sqlite3 (stdlib); dependency-free
browser JS (classic scripts, no modules); pytest; a Node-based JS harness
(`tests/js_harness.py`) that runs the viewer's real functions in a stubbed
DOM.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-01-bulk-tag-undo-design.md`. Read
  it before starting.
- **Privacy standing order (`CLAUDE.md`).** Every title, tag, author and
  bundle name in committed text must be invented — draw from
  `docs/TEST-DATA.md`. Run `.venv/Scripts/python scripts/leak_check.py`
  before each commit; it must print `clean`.
- Never commit `catalog.db*`, `covers/`, `cache/`, `Reference
  spreadsheets/`, or any catalog export.
- `user_tags` must stay outside `pre_edit` and `EDITABLE_FIELDS`. No code
  in this plan may write `pre_edit` or set `hand_edited`.
- `delete_tag`, `rename_tag` and `_rewrite_tags` are **out of scope** and
  must not be modified. The genre routes keep their `changed` responses.
- Python on this machine is `.venv/Scripts/python`. Tests run as
  `.venv/Scripts/python -m pytest`.
- The JS harness skips silently when Node is absent. If `node --version`
  fails, say so rather than reporting the JS tests as passing.
- Each task ends green and shippable: the viewer must work at every
  commit.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `humble_catalog/db.py` | `bulk_user_tag` returns changed ids | Modify (~6 lines, one function) |
| `humble_catalog/webapp/__init__.py` | bulk route answers `{"ids": [...]}` | Modify (2 lines) |
| `humble_catalog/webapp/static/app.js` | `armOrFire` returns the fired promise | Modify (1 line + comment) |
| `humble_catalog/webapp/static/catalog.js` | the `lastTagOp` slot, `undoBulk`, bulk-bar rendering, click wiring | Modify |
| `humble_catalog/webapp/static/index.html` | the Undo button | Modify (1 line) |
| `tests/js/harness.mjs` | publish the new bindings to tests | Modify (1 line) |
| `tests/test_db.py` | db-level assertions | Modify + add |
| `tests/test_webapp.py` | route and markup assertions | Modify + add |
| `tests/test_webapp_js.py` | slot behaviour through the real JS | Add |
| `docs/TEST-DATA.md` | invented user tags | Add a section |
| `docs/BACKLOG.md` | move the entry to Done | Modify |

---

### Task 1: The route answers with the ids it changed

Server-side only, plus the one line of JS that reads the response, so the
viewer keeps working. No behaviour changes for the user yet.

**Files:**
- Modify: `humble_catalog/db.py:261-300` (`bulk_user_tag`)
- Modify: `humble_catalog/webapp/__init__.py:418-435` (bulk route)
- Modify: `humble_catalog/webapp/static/catalog.js:419-434` (`runBulk`)
- Test: `tests/test_db.py:499-545`, `tests/test_webapp.py:1041-1089`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `db.bulk_user_tag(conn, ids, tag, action) -> list[int]` — the ids of
    rows actually changed, in ascending id order (the `SELECT ... WHERE id
    IN (...)` returns rowid order). Empty list when nothing changed.
    Still raises `ValueError` on an unknown action.
  - `POST /api/user-tags/bulk` → `{"ids": [1, 2, 3]}`. The `changed` key
    is gone. Validation and status codes are unchanged.

- [ ] **Step 1: Update the existing db tests to expect ids**

These currently assert counts. Replace the five assertions in
`tests/test_db.py`. Also rename the first test, whose name says "counts".

```python
def test_bulk_add_appends_and_returns_only_changed_ids(tmp_path):
    conn = _seed_user_tags(tmp_path, [
        ("a", []), ("b", ["lent out"]), ("c", ["to reread"])])
    # c already has it, so only a and b change
    assert db.bulk_user_tag(conn, [1, 2, 3], "to reread", "add") == [1, 2]
    rows = conn.execute("SELECT user_tags FROM items ORDER BY id").fetchall()
    assert json.loads(rows[0]["user_tags"]) == ["to reread"]
    assert json.loads(rows[1]["user_tags"]) == ["lent out", "to reread"]
    assert json.loads(rows[2]["user_tags"]) == ["to reread"]

def test_bulk_add_snaps_to_an_existing_spelling(tmp_path):
    conn = _seed_user_tags(tmp_path, [("a", ["to reread"]), ("b", [])])
    assert db.bulk_user_tag(conn, [1, 2], "To Reread", "add") == [2]
    assert json.loads(conn.execute(
        "SELECT user_tags FROM items WHERE id=2").fetchone()["user_tags"]) \
        == ["to reread"]

def test_bulk_remove_is_case_insensitive_and_empties_to_null(tmp_path):
    conn = _seed_user_tags(tmp_path, [
        ("a", ["to reread"]), ("b", ["lent out", "to reread"]), ("c", [])])
    assert db.bulk_user_tag(conn, [1, 2, 3], "TO REREAD", "remove") == [1, 2]
    rows = conn.execute("SELECT user_tags FROM items ORDER BY id").fetchall()
    assert rows[0]["user_tags"] is None          # emptied -> NULL
    assert json.loads(rows[1]["user_tags"]) == ["lent out"]
    assert rows[2]["user_tags"] is None

def test_bulk_only_touches_the_given_ids(tmp_path):
    conn = _seed_user_tags(tmp_path, [("a", []), ("b", [])])
    assert db.bulk_user_tag(conn, [1], "to reread", "add") == [1]
    assert conn.execute(
        "SELECT user_tags FROM items WHERE id=2").fetchone()["user_tags"] is None

def test_bulk_ignores_unknown_ids(tmp_path):
    conn = _seed_user_tags(tmp_path, [("a", [])])
    assert db.bulk_user_tag(conn, [1, 999], "to reread", "add") == [1]
```

- [ ] **Step 2: Add the two new db tests**

Append after `test_bulk_rejects_an_unknown_action` in `tests/test_db.py`:

```python
def test_bulk_returns_an_empty_list_when_nothing_changes(tmp_path):
    # An empty list and not None: the caller stores it and asks for
    # .length, and a None here would become an undo button offering to
    # restore nothing.
    conn = _seed_user_tags(tmp_path, [("a", ["to reread"])])
    assert db.bulk_user_tag(conn, [1], "to reread", "add") == []
    assert db.bulk_user_tag(conn, [], "to reread", "add") == []
    assert db.bulk_user_tag(conn, [1], "   ", "add") == []

def test_undoing_a_bulk_remove_restores_only_the_changed_rows(tmp_path):
    # The whole reason the id list is returned: b never carried the tag,
    # so undoing over the ids originally SENT would give it one it never
    # had. Undo goes over the ids that changed.
    conn = _seed_user_tags(tmp_path, [("a", ["lent out"]), ("b", [])])
    changed = db.bulk_user_tag(conn, [1, 2], "lent out", "remove")
    assert changed == [1]
    assert db.bulk_user_tag(conn, changed, "lent out", "add") == [1]
    rows = conn.execute("SELECT user_tags FROM items ORDER BY id").fetchall()
    assert json.loads(rows[0]["user_tags"]) == ["lent out"]
    assert rows[1]["user_tags"] is None
```

- [ ] **Step 3: Run the db tests and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_db.py -k bulk -v
```

Expected: FAIL. The rewritten tests fail with `assert 2 == [1, 2]` (the
function still returns an int); `test_bulk_returns_an_empty_list...`
fails with `assert 0 == []`.

- [ ] **Step 4: Make `bulk_user_tag` return the ids**

In `humble_catalog/db.py`, replace the function body's accumulator. Only
the docstring's first paragraph, the `changed` initialiser, the append,
and the return change:

```python
def bulk_user_tag(conn, ids, tag, action):
    """Add or remove one user tag across many items. Returns the ids of
    the rows actually changed; items already in the wanted state are left
    alone and absent from the list.

    The ids and not a count, because they are what an undo has to act on:
    undoing over the ids the caller SENT would strip the tag from rows
    that were carrying it beforehand.

    Deliberately USER_TAGS-only, with no TagColumn parameter. Bulk-editing
    genre would have to snapshot pre_edit and mark rows edited, because
    genre is enrichment data and editing it by hand is a hand edit. A
    generic signature would invite exactly that wrong use."""
    if action not in ("add", "remove"):
        raise ValueError(f"action must be 'add' or 'remove', got {action!r}")
    tag = (tag or "").strip()
    if not tag or not ids:
        return []
    # Snap to the spelling already in the vocabulary, so a bulk add cannot
    # fork "to reread" into a second casing.
    if action == "add":
        tag = normalize_tags(conn, USER_TAGS, [tag])[0]
    wanted = tag.lower()
    changed = []
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, user_tags FROM items WHERE id IN ({placeholders})",
        tuple(ids)).fetchall()
    for r in rows:
        current = tags_from_json(r["user_tags"])
        has = any(t.lower() == wanted for t in current)
        if action == "add":
            if has:
                continue
            updated = current + [tag]
        else:
            if not has:
                continue
            updated = [t for t in current if t.lower() != wanted]
        conn.execute("UPDATE items SET user_tags=? WHERE id=?",
                     (tags_to_json(updated), r["id"]))
        changed.append(r["id"])
    conn.commit()
    return changed
```

- [ ] **Step 5: Run the db tests and watch them pass**

```bash
.venv/Scripts/python -m pytest tests/test_db.py -k bulk -v
```

Expected: PASS, 8 tests.

- [ ] **Step 6: Update the route tests**

In `tests/test_webapp.py`, rewrite the two tests that assert on
`changed`, and add the round trip:

```python
def test_bulk_add_and_remove(tmp_path):
    dbp = tmp_path / "t.db"
    item_id = _seed(dbp)
    client = create_app(db_path=str(dbp)).test_client()
    resp = client.post("/api/user-tags/bulk", json={
        "ids": [item_id], "tag": "to reread", "action": "add"})
    assert resp.status_code == 200 and resp.get_json()["ids"] == [item_id]
    assert client.get("/api/items").get_json()["items"][0]["user_tags"] \
        == ["to reread"]
    # adding again changes nothing
    assert client.post("/api/user-tags/bulk", json={
        "ids": [item_id], "tag": "to reread",
        "action": "add"}).get_json()["ids"] == []
    resp = client.post("/api/user-tags/bulk", json={
        "ids": [item_id], "tag": "to reread", "action": "remove"})
    assert resp.get_json()["ids"] == [item_id]
    assert client.get("/api/items").get_json()["items"][0]["user_tags"] == []

def test_bulk_ignores_unknown_ids(tmp_path):
    dbp = tmp_path / "t.db"
    item_id = _seed(dbp)
    client = create_app(db_path=str(dbp)).test_client()
    # a stale page can hold ids that no longer exist; that is not an error
    resp = client.post("/api/user-tags/bulk", json={
        "ids": [item_id, 999], "tag": "to reread", "action": "add"})
    assert resp.status_code == 200 and resp.get_json()["ids"] == [item_id]

def test_undoing_a_bulk_add_leaves_rows_that_already_had_the_tag(tmp_path):
    # The add-side asymmetry. The item starts with the tag, so the bulk
    # add reports no change, and the undo over that empty list must not
    # take the tag away.
    dbp = tmp_path / "t.db"
    item_id = _seed(dbp)
    client = create_app(db_path=str(dbp)).test_client()
    client.post(f"/api/items/{item_id}/user-tags", json={"tags": ["lent out"]})
    changed = client.post("/api/user-tags/bulk", json={
        "ids": [item_id], "tag": "lent out", "action": "add"}).get_json()["ids"]
    assert changed == []
    # an undo over no ids is rejected by the route's own validation, which
    # is why the viewer never offers one -- see the JS test
    assert client.post("/api/user-tags/bulk", json={
        "ids": changed, "tag": "lent out",
        "action": "remove"}).status_code == 400
    assert client.get("/api/items").get_json()["items"][0]["user_tags"] \
        == ["lent out"]
```

- [ ] **Step 7: Run the route tests and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_webapp.py -k bulk -v
```

Expected: FAIL with `KeyError: 'ids'` — the route still returns
`changed`.

- [ ] **Step 8: Make the route answer with ids**

In `humble_catalog/webapp/__init__.py`, replace the last two lines of
`bulk_user_tags`:

```python
        # Unknown ids are ignored rather than rejected: the catalog can
        # change under a page that has been open a while.
        #
        # The ids and not a count: they are the set an undo has to act on,
        # and a count beside them would be a second derivation of one fact.
        # The client says ids.length.
        return jsonify({"ids": db.bulk_user_tag(conn(), ids, tag, action)})
```

- [ ] **Step 9: Run the route tests and watch them pass**

```bash
.venv/Scripts/python -m pytest tests/test_webapp.py -k bulk -v
```

Expected: PASS.

- [ ] **Step 10: Point the viewer at the new response shape**

`runBulk` in `humble_catalog/webapp/static/catalog.js` still destructures
`changed`. Replace its body's post-response lines:

```js
    const {ids: changedIds} = await resp.json();
    const verb = action === "add" ? "Added to" : "Removed from";
    await load();
    $("#bulk-note").textContent =
      `${verb} ${changedIds.length} of ${ids.length} items.`;
```

- [ ] **Step 11: Run the whole suite**

```bash
.venv/Scripts/python -m pytest -q
```

Expected: PASS, no failures. (Report the exact count; the suite was at
869 before this work.)

- [ ] **Step 12: Leak check and commit**

```bash
.venv/Scripts/python scripts/leak_check.py
```

Expected: `clean`.

```bash
git add humble_catalog/db.py humble_catalog/webapp/__init__.py humble_catalog/webapp/static/catalog.js tests/test_db.py tests/test_webapp.py
git commit -m "feat(tags): answer a bulk tag write with the ids it changed

bulk_user_tag already computed the changed set and returned only its
size. The set is what an undo has to act on: undoing over the ids the
caller sent would strip the tag from rows that carried it beforehand.

The route drops changed rather than carrying it beside ids, since a
count re-derived next to the set it came from is where the two quietly
stop agreeing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The undo slot and its button

**Files:**
- Modify: `humble_catalog/webapp/static/app.js:72-88` (`armOrFire`)
- Modify: `humble_catalog/webapp/static/catalog.js` (slot, `renderBulkBar`,
  `runBulk`, new `undoBulk`, click chain at ~line 874)
- Modify: `humble_catalog/webapp/static/index.html:98-104` (bulk bar)
- Modify: `tests/js/harness.mjs:114-118` (publish block)
- Test: `tests/test_webapp_js.py`, `tests/test_webapp.py`

**Interfaces:**
- Consumes: `POST /api/user-tags/bulk` → `{"ids": [...]}` from Task 1.
- Produces (published to the JS harness as `app.*`):
  - `lastTagOp` — `null` or `{ids: number[], tag: string, action: "add" | "remove"}`,
    where `action` is the **inverse** verb, ready to post.
  - `renderBulkBar()` — also renders `#bulk-undo`.
  - `undoBulk()` — async; posts the inverse, reloads, clears the slot.
  - `getLastTagOp()`, `setLastTagOp(v)` — harness accessors.

- [ ] **Step 1: Make `armOrFire` return the fired promise**

Without this the JS test cannot await a bulk operation: `armOrFire` calls
`fire()` and drops the promise, so `await runBulk(...)` resolves before
the POST has happened, and the harness's `setTimeout` is a no-op stub so a
test cannot wait it out either.

In `humble_catalog/webapp/static/app.js`, inside `armOrFire`, replace the
fire branch:

```js
  if (el.dataset.armed) {
    delete el.dataset.armed;
    el.classList.remove("armed");
    // Returned, not dropped: callers are async, and a test (or any future
    // caller that needs to know the write finished) has nothing else to
    // await. Every current caller ignores it.
    return fire();
  }
```

- [ ] **Step 2: Return it from `runBulk` too**

In `catalog.js`, `runBulk`'s `armOrFire(el, async () => {` becomes
`return armOrFire(el, async () => {`.

- [ ] **Step 3: Add the Undo button to the markup**

In `humble_catalog/webapp/static/index.html`, inside `#bulk-bar`, between
the Remove button and the note:

```html
    <button id="bulk-undo" hidden>Undo</button>
```

- [ ] **Step 4: Publish the new bindings to the harness**

In `tests/js/harness.mjs`, in the `publish` template, add to the object:

```js
  renderBulkBar, runBulk, undoBulk,
  getLastTagOp: () => lastTagOp,
  setLastTagOp: (v) => { lastTagOp = v; },
```

- [ ] **Step 5: Write the failing JS tests**

Append to `tests/test_webapp_js.py`:

```python
def _run_bulk(action, changed_ids, tag="lent out", n_items=2):
    """Drive runBulk to completion and report the state it leaves.

    Two calls because armOrFire arms on the first click and fires on the
    second; the fired promise is what makes the second call awaitable.
    """
    catalog = json.dumps([_item(id=i, name=f"Item {i}")
                          for i in range(1, n_items + 1)])
    return eval_js(
        """(async () => {
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.setLastTagOp(null);
             document.querySelector("#bulk-tag").value = %s;
             app.setFetch((url) => Promise.resolve({
               ok: true,
               json: () => Promise.resolve(
                 url === "/api/user-tags/bulk" ? {ids: %s} : {items: []}),
             }));
             const btn = document.querySelector("#bulk-add");
             await app.runBulk(btn, %s);
             await app.runBulk(btn, %s);
             return app.getLastTagOp();
           })()""" % (catalog, json.dumps(tag), json.dumps(changed_ids),
                      json.dumps(action), json.dumps(action)))


def test_a_bulk_add_leaves_an_undo_that_removes():
    # the slot stores the INVERSE verb, ready to post
    op = _run_bulk("add", [1, 2])
    assert op == {"ids": [1, 2], "tag": "lent out", "action": "remove"}


def test_a_bulk_remove_leaves_an_undo_that_adds():
    op = _run_bulk("remove", [1])
    assert op == {"ids": [1], "tag": "lent out", "action": "add"}


def test_an_operation_that_changed_nothing_leaves_no_undo():
    # every row already had the tag: there is nothing to offer to undo,
    # and the route rejects an empty id list anyway
    assert _run_bulk("add", []) is None


def test_a_later_operation_replaces_the_undo():
    op = eval_js(
        """(async () => {
             app.setLastTagOp({ids: [9], tag: "to reread", action: "add"});
             app.setItems([%s]);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             document.querySelector("#bulk-tag").value = "lent out";
             app.setFetch((url) => Promise.resolve({
               ok: true,
               json: () => Promise.resolve(
                 url === "/api/user-tags/bulk" ? {ids: [1]} : {items: []}),
             }));
             const btn = document.querySelector("#bulk-add");
             await app.runBulk(btn, "add");
             await app.runBulk(btn, "add");
             return app.getLastTagOp();
           })()""" % json.dumps(_item(id=1, name="Item 1")))
    assert op == {"ids": [1], "tag": "lent out", "action": "remove"}


def test_undo_posts_the_inverse_and_clears_the_slot():
    sent = eval_js(
        """(async () => {
             app.setItems([]);
             app.setLastTagOp({ids: [1, 2], tag: "lent out", action: "add"});
             let body = null, url = null;
             app.setFetch((u, opts) => {
               if (u === "/api/user-tags/bulk") {
                 url = u; body = JSON.parse(opts.body);
               }
               return Promise.resolve({
                 ok: true,
                 json: () => Promise.resolve(
                   u === "/api/user-tags/bulk" ? {ids: [1, 2]} : {items: []}),
               });
             });
             await app.undoBulk();
             return {url, body, after: app.getLastTagOp()};
           })()""")
    assert sent["url"] == "/api/user-tags/bulk"
    assert sent["body"] == {"ids": [1, 2], "tag": "lent out", "action": "add"}
    # single level: no redo, and no second undo of the same operation
    assert sent["after"] is None


def test_the_undo_button_names_the_tag_and_the_count():
    labels = eval_js(
        """(() => {
             app.setItems([]);
             const out = {};
             app.setLastTagOp({ids: [1, 2], tag: "lent out", action: "add"});
             app.renderBulkBar();
             out.afterRemove = dom.writes["#bulk-undo:text"];
             app.setLastTagOp({ids: [1], tag: "to reread", action: "remove"});
             app.renderBulkBar();
             out.afterAdd = dom.writes["#bulk-undo:text"];
             out.hiddenWithSlot = document.querySelector("#bulk-undo").hidden;
             app.setLastTagOp(null);
             app.renderBulkBar();
             out.hiddenWithoutSlot = document.querySelector("#bulk-undo").hidden;
             return out;
           })()""")
    assert labels["afterRemove"] == 'Undo: restore "lent out" to 2 items'
    assert labels["afterAdd"] == 'Undo: remove "to reread" from 1 items'
    assert labels["hiddenWithSlot"] is False
    assert labels["hiddenWithoutSlot"] is True


def test_undo_is_offered_while_remove_is_gated_off():
    # The gate exists so "remove from all N" is never one click. Undo acts
    # on a recorded id list, not on the current view, so it is available
    # precisely when Remove is not -- which is the whole point after an
    # unfiltered bulk add.
    state = eval_js(
        """(() => {
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             document.querySelector("#bulk-tag").value = "lent out";
             app.setLastTagOp({ids: [1], tag: "lent out", action: "remove"});
             app.renderBulkBar();
             return {
               removeDisabled: document.querySelector("#bulk-remove").disabled,
               undoHidden: document.querySelector("#bulk-undo").hidden,
               filtered: app.shownRows().filtered,
             };
           })()""" % json.dumps([_item(id=1, name="Item 1")]))
    assert state["filtered"] is False
    assert state["removeDisabled"] is True
    assert state["undoHidden"] is False
```

- [ ] **Step 6: Run the JS tests and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_webapp_js.py -k "undo or bulk" -v
```

Expected: FAIL — the harness raises `JS harness failed: ReferenceError:
lastTagOp is not defined` from the publish block. (If instead every test
*skips*, Node is missing: stop and report that, do not proceed.)

- [ ] **Step 7: Add the slot and the render**

In `catalog.js`, directly above `renderBulkBar` (after `shownRows`):

```js
// Single-level undo for the two bulk tag operations. `user_tags` sits
// outside pre_edit by design, so neither has a revert to reach for.
//
// Browser memory deliberately, and not a table: this exists to correct a
// mistake while its result is still on screen. A persisted undo answers a
// different question -- "undo something from last Tuesday" -- and answers
// it badly, since the catalog moves underneath a stored operation. One
// that visibly disappears on reload never promises what it cannot keep.
//
// `action` is already the INVERSE verb, stored ready to post, so firing
// the undo has no branching left to get wrong.
let lastTagOp = null;   // null | {ids, tag, action}
```

Then extend `renderBulkBar`, after the `#bulk-note` line:

```js
  // No stored label: the text is derived here, so it cannot disagree with
  // the operation the click will actually perform.
  const undoBtn = $("#bulk-undo");
  undoBtn.hidden = !lastTagOp;
  if (lastTagOp)
    undoBtn.textContent = lastTagOp.action === "add"
      ? `Undo: restore "${lastTagOp.tag}" to ${lastTagOp.ids.length} items`
      : `Undo: remove "${lastTagOp.tag}" from ${lastTagOp.ids.length} items`;
```

- [ ] **Step 8: Record the operation in `runBulk`**

Replace the response-handling lines added in Task 1 Step 10 with:

```js
    const {ids: changedIds} = await resp.json();
    // Only the rows that actually changed, and only when there are any:
    // undoing over the ids we SENT would strip the tag from rows that
    // carried it beforehand, and an empty list is nothing to offer.
    lastTagOp = changedIds.length
      ? {ids: changedIds, tag,
         action: action === "add" ? "remove" : "add"}
      : null;
    const verb = action === "add" ? "Added to" : "Removed from";
    await load();
    $("#bulk-note").textContent =
      `${verb} ${changedIds.length} of ${ids.length} items.`;
    renderBulkBar();
```

`load()` calls `render()`, which already calls `renderBulkBar()`; the
explicit call keeps the button correct even if a renderer throws, since
`load()` contains its failures.

- [ ] **Step 9: Add `undoBulk`**

Immediately after `runBulk` in `catalog.js`:

```js
// No armOrFire. The other two buttons arm-then-confirm because they are
// the destructive direction; this is the recovering one, and two clicks
// to recover from a mistake is friction pointing the wrong way.
async function undoBulk() {
  if (!lastTagOp) return;
  const {ids, tag, action} = lastTagOp;
  const resp = await post("/api/user-tags/bulk", {ids, tag, action});
  if (!resp.ok) {
    alert((await resp.json()).error || "Could not undo.");
    return;
  }
  const {ids: changedIds} = await resp.json();
  // Cleared whether or not every row came back: single level, no redo.
  // The original operation is one click away in this same bar.
  lastTagOp = null;
  await load();
  const verb = action === "add" ? "Restored" : "Removed";
  $("#bulk-note").textContent =
    `${verb} "${tag}" on ${changedIds.length} of ${ids.length} items.`;
  renderBulkBar();
}
```

- [ ] **Step 10: Wire the click**

In the delegated click listener, beside the other two bulk branches:

```js
  } else if (el.id === "bulk-undo") {
    await undoBulk();
  } else if (el.closest("#catalog th[data-sort]")) {
```

- [ ] **Step 11: Run the JS tests and watch them pass**

```bash
.venv/Scripts/python -m pytest tests/test_webapp_js.py -k "undo or bulk" -v
```

Expected: PASS.

- [ ] **Step 12: Add the markup and gating text assertions**

In `tests/test_webapp.py`, extend the existing markup test and add one:

```python
def test_bulk_bar_is_present():
    html = _index_html()
    assert '<input id="bulk-tag"' in html
    assert '<button id="bulk-add">' in html
    assert '<button id="bulk-remove">' in html
    assert '<button id="bulk-undo" hidden>' in html

def test_undo_does_not_arm_before_firing():
    # armOrFire is for the destructive direction. Requiring two clicks to
    # recover from a mistake points the friction the wrong way.
    js = _viewer_js()
    body = js[js.index("async function undoBulk()"):]
    assert "armOrFire" not in body[:body.index("\n}")]
```

- [ ] **Step 13: Run the whole suite**

```bash
.venv/Scripts/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 14: Leak check and commit**

```bash
.venv/Scripts/python scripts/leak_check.py
```

Expected: `clean`.

```bash
git add humble_catalog/webapp/static/app.js humble_catalog/webapp/static/catalog.js humble_catalog/webapp/static/index.html tests/js/harness.mjs tests/test_webapp.py tests/test_webapp_js.py
git commit -m "feat(tags): a single-level undo for a bulk tag operation

The slot holds the inverse verb and the ids that actually changed, so
the undo is one post to the route the operation used and has no
branching of its own.

It lives in the bulk bar, which is outside the table's innerHTML
rebuild, and names the tag and the count: the two operations are
opposites, so a bare 'Undo' would not say which way the click goes.
No armOrFire -- undo is the recovering direction -- and no filtered
gate, so it is available exactly when Remove is not.

armOrFire now returns the fired promise. Every caller ignores it; the
JS harness stubs setTimeout to a no-op, so without it a test cannot
wait for a two-click write to finish.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Documentation and the full gate

**Files:**
- Modify: `docs/TEST-DATA.md`
- Modify: `docs/BACKLOG.md:59-66` (the entry) and the Done list

**Interfaces:**
- Consumes: the shipped feature from Tasks 1-2.
- Produces: nothing code depends on.

- [ ] **Step 1: Record the invented user tags**

`docs/TEST-DATA.md` has no user-tag section, though `lent out` and
`to reread` are already used across the tests. Add one after the
**Bundles** table:

```markdown
## User tags

The owner's personal vocabulary is separate from genre and is never
titleized, so these keep the casing they are written with here.

| Tag | Used for |
|---|---|
| lent out | bulk tagging and bulk-undo examples; the tag whose loss has no revert |
| to reread | second tag, for asserting that an operation touches one and not the other |
| Lent Out / To Reread | title-case variants, for the snap-to-an-existing-spelling tests |
```

- [ ] **Step 2: Move the backlog entry to Done**

In `docs/BACKLOG.md`, delete the `### User tags and comments` section
under **Open** (lines 59-66, the whole heading plus its one bullet), and
add this at the top of the **Done** list:

```markdown
- **Undo for bulk tagging** —
  `docs/superpowers/specs/2026-08-01-bulk-tag-undo-design.md`.
  A bulk add or remove now leaves an Undo in the bulk bar naming the tag
  and the count, and firing it posts the inverse over exactly the rows
  that changed.
  The precondition was already there and unused: `bulk_user_tag` computed
  the changed set and returned only its size. Undoing over the ids the
  caller *sent* is the trap — bulk-add to 47 rows where 12 already carried
  the tag, undo by removing from all 47, and the tag is gone from 12 rows
  that had it beforehand. So the route answers `ids` and drops `changed`.
  Staleness needs no mechanism, which is unusual enough to record. Both
  inverse operations are per-item idempotent and the route already ignores
  unknown ids, so an undo fired after unrelated edits, or after a merge
  took some of its rows, quietly does the right thing. That is what made
  browser memory sufficient: a persisted slot would answer "undo something
  from last Tuesday", which the catalog moves underneath, and would drag
  in a `reset` decision for state that is derived but not rebuildable.
  **Scope was cut by a finding, not by taste.** The design first covered
  the catalog-wide `POST /api/user-tags/delete` too, on the strength of
  the statistics panel's tag management — which is genre-only. That route
  has no caller in the viewer or the CLI, so its undo could never have
  been reached, and `delete_tag`/`_rewrite_tags` were left alone rather
  than changed for a path no user can take. The finding widens the
  original entry rather than narrowing it: the escape hatch the bulk
  tagging spec offered for a bad bulk add is reachable by `curl` and by
  nothing else, so until now a mis-aimed bulk add had no in-app remedy at
  all. Wiring that UI is left as its own question.
  Built against **zero** user tags in the catalog, and the spec says so.
  Two questions that would normally be measured — whether case variants
  coexist, and whether array order carries meaning — have no data behind
  them and are settled by reasoning plus tests: the undo restores
  membership, not position, and collapses case variants to the spelling
  the operation was issued with.
  `armOrFire` returns the fired promise now. Every caller ignores it, but
  the JS harness stubs `setTimeout` to a no-op, so without it no test can
  wait for a two-click write to land — the arming idiom was untestable
  end to end.
```

- [ ] **Step 3: Update the backlog's date line**

Change line 8 to:

```markdown
Last updated: 2026-08-01.
```

- [ ] **Step 4: Run the full verification gate**

```bash
.venv/Scripts/python -m pytest -q
```

Then the project's own gate, which also runs `leak_check.py` and
`check_no_data_tracked.py`:

```bash
powershell -File scripts/windows/verify.ps1
```

Expected: the suite passes and both privacy checks report clean. If
`leak_check.py` flags one of the invented tags as a substring of a real
term, rename the tag in `docs/TEST-DATA.md` and everywhere it is used —
do not add it to `ALLOWED`, since these are invented and a hit means the
invention was unlucky.

- [ ] **Step 5: Commit**

```bash
git add docs/TEST-DATA.md docs/BACKLOG.md
git commit -m "docs(tags): close the bulk-tag undo entry

Records what the measurement changed: the scope cut once the
catalog-wide delete turned out to have no caller, and that the whole
feature is built against zero user tags, so the case-variant and
ordering questions are reasoned rather than measured.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verify the feature in a browser**

`CLAUDE.md` requires visual checks to run against the demo catalog, never
the real one — a screenshot of the real viewer leaks the library and no
automated check would notice.

```bash
.venv/Scripts/python scripts/demo_catalog.py
```

Open `http://127.0.0.1:8099`, then: type a tag into the bulk box, click
**Add** twice to confirm, and check that the Undo button appears naming
the tag and the count. Click it, and confirm the tags are gone from the
table and the button disappears. Repeat with a filter active to see that
Remove enables and Undo still offers the inverse.

The JS harness has no computed styles, so check by eye that the button
does not inherit the browser's grey default against the dark theme — the
statistics panel's jump counts shipped with exactly that bug. If it does,
give `#bulk-undo` the same treatment in `style.css` (near the `#bulk-bar`
rules at line 273) and re-run `pytest -q` before committing the fix
separately.

---

## Notes for the implementer

- **Do not** touch `delete_tag`, `rename_tag`, `_rewrite_tags`, or any
  `/api/genres/*` route. If a change seems to require it, stop: the spec's
  **Server** section explains why they were left alone.
- **Do not** write `pre_edit` or `hand_edited` anywhere in this work.
  `test_bulk_never_marks_rows_edited` and
  `test_bulk_does_not_mark_rows_edited` already guard it; keep them green.
- The suite has a JS harness that skips when Node is absent. A run that
  reports "skipped" for the `test_webapp_js.py` tests has **not** verified
  the client half — say so explicitly rather than reporting a pass.
