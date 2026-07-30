# Viewer Multi-Section Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the viewer's single stacked page with four hash-routed sections — Library, Maintenance, Keys, Bundles — and fold the filter bar into a collapsible sidebar.

**Architecture:** One page load and one in-memory catalog are preserved: `load()` still fetches `/api/items` once and every section reads the same `items` array. Sections are `<section>` elements toggled by a `hashchange` listener. `app.js` splits into classic `<script>` files sharing global scope — no bundler, no ES modules, no exports.

**Tech Stack:** Flask (server, unchanged), vanilla JS classic scripts, plain CSS, pytest + a Node `vm` harness for JS behaviour tests.

**Spec:** `docs/superpowers/specs/2026-07-30-viewer-multi-section-layout-design.md`

## Global Constraints

- **No new server routes, no API changes.** The exposure model in `webapp/__init__.py`'s loopback check stays untouched. Hash routing is client-side only.
- **Classic scripts only.** No `type="module"`, no `import`/`export`. Files share the global lexical environment, as `fuzzy.js` and `autocomplete.js` already do.
- **No build step, no new dependencies.** Node stays optional; JS tests skip without it.
- **Privacy standing order.** No real catalog items in any committed text. Draw invented names from `docs/TEST-DATA.md`. Run `.venv/Scripts/python scripts/leak_check.py` before any commit that adds docs, tests or fixtures. Never pipe it.
- **Do not re-shoot `docs/screenshot-viewer.png`.** It goes stale deliberately; re-shooting needs the owner's by-eye privacy pass.
- **Script load order is fixed** (see Task 4) and every `index.html` change must preserve it: `fuzzy.js`, `autocomplete.js`, `app.js`, `catalog.js`, `maintenance.js`, `bundles.js`, `shell.js`.
- **Python is `.venv/Scripts/python`**; `pip` must be invoked as `python -m pip` (the venv's `pip.exe` shim exits 1 silently).

## Deviation from the spec, decided during planning

The spec's file table says `app.js` keeps "the boot call". That cannot work: classic scripts execute in load order, and `app.js` must load **first** so its helpers and constants exist before the section files. A boot call at the bottom of `app.js` would run `load()` before `catalog.js` had defined `render`. **The boot call therefore moves to the bottom of `shell.js`, which loads last.** Everything else in the spec's table stands.

---

### Task 1: Teach the tests about more than one viewer script

Test infrastructure only — no application code changes. This lands first so every later task has a harness that survives the split.

**Files:**
- Modify: `tests/js/harness.mjs:17-23,135-136`
- Modify: `tests/js_harness.py:20,38-42`
- Modify: `tests/test_webapp.py:68-108,167,349`

**Interfaces:**
- Consumes: nothing.
- Produces: `js_harness.VIEWER_JS` (a `list[Path]` in load order) and `test_webapp._viewer_js() -> str` (every viewer script concatenated). Later tasks append filenames to `VIEWER_JS` and nothing else.

- [ ] **Step 1: Tag the last one-page commit**

The working tree must be clean and `pyproject.toml` must still read `0.1.0`.

```bash
git tag -a v0.1.0 -m "The viewer's final one-page layout, before the split into sections" && git tag
```

Expected output: `v0.1.0`

- [ ] **Step 2: Write the failing test for a multi-file harness**

Add to `tests/test_webapp_js.py`:

```python
def test_harness_loads_every_viewer_script():
    # the harness used to take one path; the split needs it to take the
    # list, in load order, or a moved function becomes an undefined name
    from tests.js_harness import VIEWER_JS
    assert [p.name for p in VIEWER_JS] == ["app.js"]
    assert eval_js("typeof app.esc") == "function"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py::test_harness_loads_every_viewer_script -v`
Expected: FAIL with `ImportError: cannot import name 'VIEWER_JS'`

- [ ] **Step 4: Make `js_harness.py` hold a list**

Replace line 20 of `tests/js_harness.py`:

```python
_APP_JS = _ROOT / "humble_catalog" / "webapp" / "static" / "app.js"
```

with:

```python
_STATIC = _ROOT / "humble_catalog" / "webapp" / "static"
# The viewer's own scripts in <script> order. fuzzy.js is loaded by the
# harness itself (it has to be published by hand), so it is not listed.
# Appending here is the whole cost of adding a viewer script.
VIEWER_JS = [_STATIC / "app.js"]
```

Then in `eval_js`, replace the subprocess argument `str(_APP_JS)` with a comma-joined list:

```python
    proc = subprocess.run(
        [node, str(_HARNESS), ",".join(str(p) for p in VIEWER_JS), expression],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
```

Apply the identical substitution in `eval_js_error` (it builds the same command).

- [ ] **Step 5: Make `harness.mjs` read the list**

Replace lines 17-23 of `tests/js/harness.mjs`:

```js
const [appPath, expr] = process.argv.slice(2);
const src = fs.readFileSync(appPath, "utf8");
// fuzzy.js is a sibling script that app.js depends on. It has to run in
// the same context and be published by hand: a top-level `const` inside
// runInContext never reaches globalThis.
const fuzzySrc = fs.readFileSync(
  path.join(path.dirname(appPath), "fuzzy.js"), "utf8");
```

with:

```js
// A comma-separated list of the viewer's scripts, in <script> order.
// They are concatenated into ONE context because that is what the browser
// does: classic scripts share the global lexical environment, which is why
// none of them import anything.
const [appPaths, expr] = process.argv.slice(2);
const paths = appPaths.split(",");
const src = paths.map((p) => fs.readFileSync(p, "utf8")).join("\n;\n");
// fuzzy.js is a sibling script the viewer depends on. It has to run in
// the same context and be published by hand: a top-level `const` inside
// runInContext never reaches globalThis.
const fuzzySrc = fs.readFileSync(
  path.join(path.dirname(paths[0]), "fuzzy.js"), "utf8");
```

Line 136 (`vm.runInContext(src + publish, sandbox);`) needs no change — `src` is now the concatenation.

- [ ] **Step 6: Run the JS tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py tests/test_fuzzy_js.py -v`
Expected: PASS, including the new test. If Node is absent every test skips — that is not a pass; install Node or run this task on a machine with it.

- [ ] **Step 7: Give `test_webapp.py` a whole-viewer reader**

Add near the top of `tests/test_webapp.py`, after the imports:

```python
def _viewer_js():
    """Every viewer script concatenated, in load order.

    These assertions pin that the viewer does something, not that one
    file does. Reading app.js alone made them break when a function moved
    between scripts, which is a fact about the file layout and not about
    the behaviour they were written to protect.
    """
    from tests.js_harness import VIEWER_JS
    return "\n".join(p.read_text(encoding="utf-8") for p in VIEWER_JS)
```

- [ ] **Step 8: Point every app.js text assertion at it**

In `tests/test_webapp.py`, replace each of these two-line reads:

```python
    js = (Path(__file__).parent.parent / "humble_catalog" / "webapp"
          / "static" / "app.js").read_text(encoding="utf-8")
```

and each single-line form:

```python
    js = (static / "app.js").read_text(encoding="utf-8")
```

with:

```python
    js = _viewer_js()
```

There are six occurrences, at lines 69-70, 79-80, 88, 104, 167 and 349. Leave every `index.html`, `style.css` and `autocomplete.js` read exactly as it is — only the `app.js` reads change.

- [ ] **Step 9: Run the full suite**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py tests/test_webapp_js.py -v`
Expected: PASS, no test edited beyond the reads.

- [ ] **Step 10: Commit**

```bash
git add tests/js/harness.mjs tests/js_harness.py tests/test_webapp.py tests/test_webapp_js.py && git commit -m "test(viewer): let the JS tests span more than one script

The harness took a single path and test_webapp.py read app.js by name,
so both encoded a fact about the file layout rather than about the
viewer's behaviour they exist to protect. VIEWER_JS is now the list, in
<script> order, concatenated into one vm context the way the browser
concatenates classic scripts into one global scope.

No application code changes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Extract `maintenance.js`

The review queue and the duplicates panel, plus the click branches that serve them. They are the cleanest seam: no other section shares a CSS class with them.

**Files:**
- Create: `humble_catalog/webapp/static/maintenance.js`
- Modify: `humble_catalog/webapp/static/app.js` (remove the moved code)
- Modify: `humble_catalog/webapp/static/index.html:116-118`
- Modify: `tests/js_harness.py` (`VIEWER_JS`)

**Interfaces:**
- Consumes from `app.js`: `$`, `esc`, `tagBadges`, `armOrFire`, `post`, `load`, `items`.
- Produces: `loadReview()`, `loadDupes()`, `renderDupes()`, `dupeMember(i)`, `dupeCard(m, other)`, `dupeGroupHtml(members, manual)`, `itemOption(i)`, `optionId(s)`; module state `reviewOpen`, `dupesOpen`, `dupeGroups`, `manualPair`.

- [ ] **Step 1: Create the file with the moved code**

Create `humble_catalog/webapp/static/maintenance.js` beginning with:

```js
// The Maintenance section: the review queue and the duplicates panel.
// Both are catalog *upkeep* rather than catalog *browsing*, which is the
// line the sections are drawn on. Everything here reads the shared
// `items` array from app.js and posts through its `post()`.
```

Then move, verbatim and in this order, from `app.js`:

1. `let reviewOpen = false, dupesOpen = false;` (from line 3 — remove only these two bindings; `items` stays in `app.js`)
2. `loadReview()` — lines 586-614
3. The duplicates block — lines 616-700, which is the `// ---- Duplicates panel ----` comment, `manualPair`, `itemOption`, `optionId`, `dupeMember`, `dupeCard`, `dupeGroupHtml`, `dupeGroups` and `renderDupes`

- [ ] **Step 2: Move the maintenance click branches into their own listener**

Append to `maintenance.js`:

```js
// Its own delegated listener rather than a branch of app.js's. The
// classes below are disjoint from every other section's, so an
// independent listener cannot change which branch wins -- unlike the
// catalog's chip-x/tag-x pair, whose order is load-bearing.
document.addEventListener("click", async (ev) => {
  const el = ev.target;
  if (el.classList.contains("cand-btn")) {
    armOrFire(el, async () => {
      await post(`/api/items/${el.dataset.id}/choose`, {candidate: +el.dataset.idx});
      await load();
    });
  } else if (el.classList.contains("url-fetch")) {
    const id = el.dataset.id;
    const box = document.querySelector(`.url-box[data-id="${id}"]`);
    const result = document.querySelector(`.url-result[data-id="${id}"]`);
    result.textContent = "Fetching...";
    const resp = await post(`/api/items/${id}/fetch_url`, {url: box.value.trim()});
    const data = await resp.json();
    if (!resp.ok) {
      result.textContent = data.error || "Could not fetch that URL.";
      return;
    }
    const c = data.candidate;
    result.innerHTML = c.link_only
      ? `<button class="apply-fetched" data-id="${id}">
          Couldn't read metadata (${esc(c.reason)}). Apply link only: ${esc(c.title)}</button>`
      : `<button class="apply-fetched" data-id="${id}">
          Apply: ${esc(c.title)} - ${esc((c.authors || []).join(", "))} (${esc(c.source)})</button>`;
    result.querySelector(".apply-fetched").dataset.candidate = JSON.stringify(c);
  } else if (el.classList.contains("apply-fetched")) {
    armOrFire(el, async () => {
      await post(`/api/items/${el.dataset.id}/apply`,
                 {candidate: JSON.parse(el.dataset.candidate)});
      await load();
    });
  } else if (el.classList.contains("dupe-keep")) {
    armOrFire(el, async () => {
      const resp = await post("/api/merge",
        {keep_id: +el.dataset.keep, drop_id: +el.dataset.drop});
      if (!resp.ok) {
        alert((await resp.json()).error || "Could not merge.");
        return;
      }
      manualPair = {a: null, b: null};
      await load();
    });
  } else if (el.classList.contains("dupe-dismiss")) {
    armOrFire(el, async () => {
      await post("/api/dismiss_pair",
        {id_a: +el.dataset.a, id_b: +el.dataset.b});
      await load();
    });
  } else if (el.id === "dupe-clear") {
    manualPair = {a: null, b: null};
    renderDupes();
  }
});
```

Delete those six branches from `app.js`'s click chain (lines 947-951, 1054-1094, 1115-1117), joining the surrounding `else if`s so the chain stays syntactically whole.

- [ ] **Step 3: Load the new script**

In `index.html`, change lines 116-118 to:

```html
<script src="/static/autocomplete.js"></script>
<script src="/static/fuzzy.js"></script>
<script src="/static/app.js"></script>
<script src="/static/maintenance.js"></script>
```

- [ ] **Step 4: Register it with the harness**

In `tests/js_harness.py`, extend the list:

```python
VIEWER_JS = [_STATIC / "app.js", _STATIC / "maintenance.js"]
```

- [ ] **Step 5: Run the suite**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py tests/test_webapp_js.py -v`
Expected: PASS, with **no test file edited in this task**. A failure here means the move dropped or reordered something.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/webapp/static/ tests/js_harness.py && git commit -m "refactor(viewer): move the review and duplicates panels to maintenance.js

First cut of the app.js split, taken at the cleanest seam: no other
section shares a CSS class with these two, so their click branches
become an independent delegated listener without changing which branch
wins for any element.

Pure refactor -- no test changed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Extract `bundles.js`

**Files:**
- Create: `humble_catalog/webapp/static/bundles.js`
- Modify: `humble_catalog/webapp/static/app.js`
- Modify: `humble_catalog/webapp/static/index.html`
- Modify: `tests/js_harness.py`

**Interfaces:**
- Consumes from `app.js`: `$`, `esc`, `post`, `items`.
- Produces: `previewBundle(url)`, `renderBundlePreview()`, `money(amount, currency)`; state `bundlePreview`, `bundlePreviewError`, `bundlePreviewOpen`.
- The `bundle-jump` click branch stays in `app.js` for now — it sets `#search` and calls `render()`, both catalog concerns. Task 6 gives it its cross-section behaviour.

- [ ] **Step 1: Create the file**

Create `humble_catalog/webapp/static/bundles.js` beginning with:

```js
// The Bundles section: paste a HumbleBundle URL, get per-tier owned/new
// counts. Read-only and unpersisted -- it answers "should I buy this",
// so it holds no state worth surviving a reload.
```

Move verbatim from `app.js` the whole bundle preview block, lines 816-918 (`// ---- Bundle preview panel ----` through the end of `renderBundlePreview`), including `money` and the `bundlePreview*` state bindings.

- [ ] **Step 2: Move its input wiring**

Move lines 1143-1149 from `app.js` to the bottom of `bundles.js`, verbatim:

```js
$("#bundle-go").addEventListener("click", () => {
  const url = $("#bundle-url").value.trim();
  if (url) previewBundle(url);
});
$("#bundle-url").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") $("#bundle-go").click();
});
```

- [ ] **Step 3: Load it and register it**

`index.html`, after `maintenance.js`:

```html
<script src="/static/bundles.js"></script>
```

`tests/js_harness.py`:

```python
VIEWER_JS = [_STATIC / "app.js", _STATIC / "maintenance.js",
             _STATIC / "bundles.js"]
```

- [ ] **Step 4: Run the suite**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py tests/test_webapp_js.py -v`
Expected: PASS, no test edited.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/webapp/static/ tests/js_harness.py && git commit -m "refactor(viewer): move the bundle preview to bundles.js

Pure refactor -- no test changed. The bundle-jump click branch stays in
app.js: it drives the search box and the table, which are the catalog's,
and it becomes a cross-section jump once sections exist.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Extract `catalog.js` and `shell.js`, fixing the load order

The big move. What survives in `app.js` is exactly what more than one section needs.

**Files:**
- Create: `humble_catalog/webapp/static/catalog.js`
- Create: `humble_catalog/webapp/static/shell.js`
- Modify: `humble_catalog/webapp/static/app.js`
- Modify: `humble_catalog/webapp/static/index.html`
- Modify: `tests/js_harness.py`

**Interfaces:**
- `app.js` retains and produces: `items`, `GAPS`, `gapEmpty`, `ENRICHMENT_STATES`, `$`, `esc`, `tagBadges`, `armOrFire`, `post`, `load()`.
- `catalog.js` produces: `render()`, `visible()`, `sortValue`, `chipFilters`, `passesChipFilters`, `renderFilterChips`, `wireChipFilter`, `refreshStats()`, `renderStats()`, `SECTION_FILTERS`, `EXPORT_COLUMNS`, `toggleColumn`, `loadColumnSelection`, `renderColumnPicker`, `renderExportButton`, `downloadExport`, `statusSelect`, `READ_STATUS_ORDER`, `shownRows`, `renderBulkBar`, `runBulk`, `tagCounts`, `vocab`, `person`, `personField`, `highlight`, `shouldPostEnrichmentEdit`; state `sortKey`, `sortAsc`, `relevanceSort`, `statusFilter`, `exportColumns`, `editingId`, `editingTags`, `matchSpans`, `foldCache`, `genresShowAll`, `tagEditMode`.
- `shell.js` produces: `pollStatus()`, `currentTheme()`, `syncThemeButton()`, and the boot call.

- [ ] **Step 1: Create `shell.js`**

Create `humble_catalog/webapp/static/shell.js`:

```js
// The shell: everything that belongs to the page rather than to any one
// section -- the run banner, the theme toggle, and the boot call.
//
// This file loads LAST. Classic scripts run in <script> order, so the
// boot call has to sit after every renderer it invokes has been defined;
// in app.js, where the spec first put it, load() would have called a
// render() that did not exist yet.
```

Move verbatim from `app.js`: `pollStatus` (lines 920-926), the boot trio (1235-1237), and the theme block (1239-1261).

Arrange the boot calls at the bottom of `shell.js`, after the theme functions, in this order:

```js
load();
pollStatus();
setInterval(pollStatus, 5000);
syncThemeButton();
```

- [ ] **Step 2: Create `catalog.js`**

Create `humble_catalog/webapp/static/catalog.js`:

```js
// The Library section: the table, its filters, sorting, the column
// picker, export, and bulk tagging -- plus the statistics summary, which
// describes the very rows the table is showing and so is read beside it
// rather than in a section of its own.
```

Move everything from `app.js` that is not listed in `app.js`'s retained set above and has not already moved in Tasks 2-3. That is lines 39-584 minus the shared helpers, the statistics block (702-814), and the remaining top-level wiring at 1129-1142 and 1151-1233.

**Move the click chain as one block.** Take `app.js`'s remaining `document.addEventListener("click", …)` chain — everything left after Task 2 removed the maintenance branches — into `catalog.js` unchanged, wrapped in its own listener.

> **Do not reorder the branches.** `chip-x` is tested before `tag-x`, and the filter chip's remove button carries **both** classes (`renderFilterChips` emits `class="tag-x chip-x"`). Swap them and removing a filter chip would splice `editingTags` instead — silently, and only while a row is being edited. This ordering is why the catalog's branches stay one chain in one file rather than being split further.

Also move the `change` listener (1129-1138) and the `#f-type`/`#f-flag`/`#f-rating`/`#search` input wiring (1139-1142).

- [ ] **Step 3: Verify what is left in `app.js`**

`app.js` should now hold only: the `GAPS`/`gapEmpty`/`ENRICHMENT_STATES` constants with their comments, `let items = [];`, `$`, `load()`, `esc`, `tagBadges`, `armOrFire`, `post`. Nothing else, and no top-level call.

Run: `.venv/Scripts/python -c "print(sum(1 for _ in open('humble_catalog/webapp/static/app.js', encoding='utf-8')))"`
Expected: a number under 120.

- [ ] **Step 4: Set the final load order**

`index.html` scripts, in exactly this order:

```html
<script src="/static/autocomplete.js"></script>
<script src="/static/fuzzy.js"></script>
<script src="/static/app.js"></script>
<script src="/static/catalog.js"></script>
<script src="/static/maintenance.js"></script>
<script src="/static/bundles.js"></script>
<script src="/static/shell.js"></script>
```

`tests/js_harness.py`:

```python
VIEWER_JS = [_STATIC / "app.js", _STATIC / "catalog.js",
             _STATIC / "maintenance.js", _STATIC / "bundles.js",
             _STATIC / "shell.js"]
```

- [ ] **Step 5: Add a test that pins the order**

Add to `tests/test_webapp.py`:

```python
def test_index_loads_the_viewer_scripts_in_dependency_order():
    from tests.js_harness import VIEWER_JS
    html = (Path(__file__).parent.parent / "humble_catalog" / "webapp"
            / "static" / "index.html").read_text(encoding="utf-8")
    # Classic scripts run in <script> order and share one global scope,
    # so order is a real dependency, not a formatting choice: app.js's
    # helpers must exist before any section defines a renderer that calls
    # them, and shell.js boots last because load() calls every renderer.
    positions = [html.index(f'/static/{p.name}"') for p in VIEWER_JS]
    assert positions == sorted(positions)
    assert VIEWER_JS[0].name == "app.js"
    assert VIEWER_JS[-1].name == "shell.js"
```

- [ ] **Step 6: Run the whole suite**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS. Every pre-existing test must pass unmodified — that is the acceptance criterion for the entire split.

- [ ] **Step 7: Check it in a browser**

Run the viewer and confirm the table renders, a filter narrows it, sorting works, and the theme toggle flips. A load-order mistake shows as a `ReferenceError` in the console on first paint, which no test in this suite would catch.

- [ ] **Step 8: Commit**

```bash
git add humble_catalog/webapp/static/ tests/js_harness.py tests/test_webapp.py && git commit -m "refactor(viewer): split app.js into catalog.js and shell.js

app.js keeps only what more than one section needs -- items, the GAPS
and enrichment constants, and the \$/esc/tagBadges/armOrFire/post/load
helpers -- and drops from 1261 lines to under 120.

The boot call moves to shell.js rather than staying in app.js as the
spec had it. Classic scripts run in <script> order, so a boot call in
the first-loaded file would call a render() that did not exist yet.
One new test pins that order, since it is a dependency and not a
formatting choice.

The catalog's click branches stay one chain in one file: chip-x is
tested before tag-x and the filter chip's remove button carries both
classes, so the order decides which branch wins.

Pure refactor -- every pre-existing test passes unmodified.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The section shell and hash routing

**Files:**
- Modify: `humble_catalog/webapp/static/index.html:19-115`
- Modify: `humble_catalog/webapp/static/shell.js`
- Modify: `humble_catalog/webapp/static/style.css:88-96`
- Modify: `tests/test_webapp.py:66`
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: `$` from `app.js`.
- Produces: `SECTIONS` (array of `{id, label}`), `currentSection()`, `showSection(name)`. Task 6 adds badges to the same nav.

- [ ] **Step 1: Write the failing routing tests**

Add to `tests/test_webapp_js.py`:

```python
def test_hash_selects_exactly_one_section():
    shown = eval_js("""(() => {
      app.showSection("maintenance");
      return app.SECTIONS.map((s) => [s.id, !!document.querySelector(
        `#section-${s.id}`).hidden]);
    })()""")
    assert shown == [["library", True], ["maintenance", False],
                     ["keys", True], ["bundles", True]]


def test_unknown_hash_falls_back_to_library():
    # a stale bookmark, or a hand-typed hash, must not leave a blank page
    shown = eval_js("""(() => {
      app.showSection("nonsense");
      return document.querySelector("#section-library").hidden;
    })()""")
    assert shown is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k section -v`
Expected: FAIL — `app.SECTIONS` is undefined.

- [ ] **Step 3: Add the routing to `shell.js`**

Insert into `shell.js`, above the boot calls:

```js
// The four sections. Order is tab order. `keys` ships empty on purpose:
// the unredeemed key report is separate work, and a section that is not
// the table exercises the shell before the feature that needed it is
// built on top.
const SECTIONS = [
  {id: "library",     label: "Library"},
  {id: "maintenance", label: "Maintenance"},
  {id: "keys",        label: "Keys"},
  {id: "bundles",     label: "Bundles"},
];

const currentSection = () => {
  const name = (location.hash || "").replace(/^#\//, "");
  return SECTIONS.some((s) => s.id === name) ? name : "library";
};

// An unknown hash falls back to Library WITHOUT rewriting the URL: a
// silent rewrite would erase the evidence that a bookmark went stale.
function showSection(name) {
  const active = SECTIONS.some((s) => s.id === name) ? name : "library";
  for (const s of SECTIONS) {
    const el = $(`#section-${s.id}`);
    if (el) el.hidden = s.id !== active;
    const tab = $(`#tab-${s.id}`);
    if (tab) tab.setAttribute("aria-current", s.id === active ? "page" : "false");
  }
}

if (typeof addEventListener === "function")
  addEventListener("hashchange", () => showSection(currentSection()));
```

Add `showSection(currentSection());` to the boot calls, before `load()`.

- [ ] **Step 4: Publish the new bindings to the harness**

In `tests/js/harness.mjs`, add to the `publish` template literal's object (after `SECTION_FILTERS,` on line 108):

```js
  SECTIONS, currentSection, showSection,
```

The sandbox has no `location`; add it beside `localStorage` in the `sandbox` object:

```js
  location: {hash: ""},
  addEventListener() {},
```

- [ ] **Step 5: Restructure `index.html`**

Replace the `<header>`/`<main>` body (lines 19-115) so that: the `<h1>` and `#run-banner` stay in the header, a `<nav id="tabs">` follows them, and `<main>` holds four `<section>` elements.

```html
<header>
  <h1>Humble Catalog
    <button id="theme-toggle" type="button" title="Toggle light/dark"
            aria-label="Toggle light/dark theme">☾</button></h1>
  <div id="run-banner" hidden></div>
  <nav id="tabs" aria-label="Sections">
    <a id="tab-library" href="#/library">Library<span class="badge-count"></span></a>
    <a id="tab-maintenance" href="#/maintenance">Maintenance<span class="badge-count"></span></a>
    <a id="tab-keys" href="#/keys">Keys<span class="badge-count"></span></a>
    <a id="tab-bundles" href="#/bundles">Bundles<span class="badge-count"></span></a>
  </nav>
</header>
<main>
  <section id="section-library" hidden>
    <div id="controls"><!-- unchanged: lines 25-76 of the previous index.html --></div>
    <div id="bulk-bar"><!-- unchanged --></div>
    <div id="stats-panel" hidden></div>
    <div id="table-wrap"><!-- unchanged table --></div>
  </section>
  <section id="section-maintenance" hidden>
    <div id="review-panel" hidden></div>
    <div id="dupes-panel" hidden></div>
  </section>
  <section id="section-keys" hidden>
    <p class="section-empty">The unredeemed key report will live here.</p>
  </section>
  <section id="section-bundles" hidden>
    <div id="bundle-form">
      <input id="bundle-url" type="url" size="60"
             placeholder="Paste a HumbleBundle page URL to see what you already own">
      <button id="bundle-go">Check bundle</button>
    </div>
    <div id="bundle-panel" hidden></div>
  </section>
</main>
```

Every moved element keeps its existing `id` and inner markup exactly — the ids are what `catalog.js`, `maintenance.js` and `bundles.js` query.

- [ ] **Step 6: Stop the panels auto-showing over the table**

In `maintenance.js`'s `loadReview`, the line `panel.hidden = review.length === 0;` stays — an empty panel should still be empty inside its own section. Nothing else changes: the panels are now inside `#section-maintenance`, so they cannot cover the table regardless.

In `style.css`, replace lines 92-96:

```css
/* The panels sit outside the table's scroller and so never move with it.
   They keep their natural height but cap out at half the pane and scroll
   internally, so an expanded panel cannot squeeze the table to nothing. */
#review-panel, #dupes-panel, #stats-panel, #bundle-panel { flex: 0 1 auto; max-height: 50%;
                                            overflow: auto; }
```

with:

```css
/* A section owns the viewport, so nothing competes for it and the old
   max-height cap is gone. It existed only because four panels and the
   table shared one pane -- the arrangement that once pushed the bundle
   preview's three comparable numbers off the screen. */
section[id^="section-"] { display: flex; flex-direction: column;
                          gap: 1rem; flex: 1; min-height: 0; }
#review-panel, #dupes-panel, #stats-panel, #bundle-panel { flex: 0 1 auto;
                                            overflow: auto; }
#tabs { display: flex; gap: .5rem; margin-top: .5rem; }
#tabs a { padding: .3rem .7rem; border-radius: 4px 4px 0 0;
          text-decoration: none; color: var(--fg); }
#tabs a[aria-current="page"] { background: var(--bg); font-weight: 600; }
.section-empty { color: var(--fg); opacity: .7; }
```

- [ ] **Step 7: Update the CSS assertion that pinned the old cap**

In `tests/test_webapp.py`, replace line 66:

```python
    assert "max-height: 50%" in css
```

with:

```python
    # the cap is gone with the stacking that needed it: a section owns the
    # viewport, so no panel can squeeze the table region any more
    assert "max-height: 50%" not in css
    assert 'section[id^="section-"]' in css
```

- [ ] **Step 8: Make the bundle jump cross sections**

In `app.js`'s remaining click chain — now in `catalog.js` — the `bundle-jump` branch sets `#search` and calls `render()`, but the table is in another section. Change that branch to:

```js
  } else if (el.classList.contains("bundle-jump")) {
    // Jump to the owned row, so "you may own part of this" becomes one
    // click to WHICH part. The row is in Library and the click came from
    // Bundles, so this navigates as well as filters -- setting the hash
    // rather than calling showSection, so the jump lands in history and
    // Back returns to the bundle.
    $("#search").value = el.textContent.trim();
    relevanceSort = true;
    location.hash = "#/library";
    render();
```

- [ ] **Step 9: Run everything**

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 10: Check it in a browser**

Confirm: each tab shows exactly one section; reloading on `#/keys` lands on Keys; a hand-typed `#/nonsense` shows Library; Back after a bundle jump returns to Bundles.

- [ ] **Step 11: Commit**

```bash
git add humble_catalog/webapp/static/ tests/ && git commit -m "feat(viewer): four hash-routed sections replace the stacked panels

Library, Maintenance, Keys and Bundles. An unknown hash falls back to
Library without rewriting the URL, so a stale bookmark stays visible
evidence rather than being silently corrected.

Keys ships empty but wired: the unredeemed key report is separate work,
and a section that is not the table exercises the shell before the
feature that needed it is built on top of it.

The shared max-height cap is gone with the stacking that needed it. It
existed because four panels and the table shared one pane -- the
arrangement that once pushed the bundle preview's three comparable
numbers off the screen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Tab badges

The signal the auto-showing panels used to provide, without the shove.

**Files:**
- Modify: `humble_catalog/webapp/static/shell.js`
- Modify: `humble_catalog/webapp/static/app.js` (`load()`)
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: `SECTIONS`, `$`, and the counts each section already computes.
- Produces: `badgeCount(section)` and `renderBadges()`. Task 8's key report will add a `keys` count to `badgeCount`.

- [ ] **Step 1: Write the failing badge tests**

Add to `tests/test_webapp_js.py`:

```python
def test_badge_shows_a_count_and_vanishes_at_zero():
    text = eval_js("""(() => {
      app.setPending({maintenance: 12});
      app.renderBadges();
      const shown = document.querySelector("#tab-maintenance .badge-count").textContent;
      app.setPending({maintenance: 0});
      app.renderBadges();
      const hidden = document.querySelector("#tab-maintenance .badge-count").textContent;
      return [shown, hidden];
    })()""")
    assert text == ["12", ""]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k badge -v`
Expected: FAIL — `app.setPending` is not a function.

- [ ] **Step 3: Add the badge plumbing to `shell.js`**

```js
// What each section is waiting on. Written by load(); read by
// renderBadges(). One object rather than a call into each section, so a
// section that has not loaded yet counts as zero instead of throwing.
let pending = {library: 0, maintenance: 0, keys: 0, bundles: 0};

function renderBadges() {
  for (const s of SECTIONS) {
    const el = $(`#tab-${s.id}`)?.querySelector(".badge-count");
    if (!el) continue;
    const n = badgeCount(s.id);
    el.textContent = n > 0 ? String(n) : "";
  }
}
```

- [ ] **Step 4: YOUR CONTRIBUTION — write the badge policy**

I have deliberately left `badgeCount` for you. It is a judgement about your own workflow, not a mechanical detail, and guessing it wrongly produces either a nagging UI or a silent one.

In `humble_catalog/webapp/static/shell.js`, directly above `renderBadges()`, implement:

```js
// Which pending counts are worth a badge.
//
// `pending` carries a number per section: maintenance is review items +
// duplicate groups, library is currently unrated items, keys and bundles
// are 0 until those features land.
//
// The question is what a badge MEANS. If it means "there is work here",
// an unrated item does not qualify -- rating is optional and a permanent
// badge is one you stop seeing. If it means "here is a count", it does.
//
// TODO(owner): return the number to show for `section`, or 0 for none.
function badgeCount(section) {
  return 0;
}
```

Consider: does a badge that never reaches zero still carry information? Should Maintenance badge on review items and duplicates equally, given a duplicate is a decision and a review item is a chore? Five to ten lines.

- [ ] **Step 5: Feed `pending` from `load()`**

In `app.js`'s `load()`, after the renderer loop, add:

```js
  // Badges are computed here rather than by each section, because this
  // loop is the one place that has just run every loader. A section the
  // owner has not opened still reports its count.
  pending = {
    library: items.filter((i) => !i.my_rating).length,
    maintenance: reviewCount + dupeGroups.length,
    keys: 0,
    bundles: 0,
  };
  renderBadges();
```

Add `let reviewCount = 0;` to `maintenance.js` beside `reviewOpen`, and set it in `loadReview` immediately after the fetch:

```js
  reviewCount = review.length;
```

- [ ] **Step 6: Publish the test hooks**

In `harness.mjs`'s `publish` object add:

```js
  renderBadges, badgeCount,
  setPending: (v) => { pending = {...pending, ...v}; },
```

- [ ] **Step 7: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -v`
Expected: PASS — assuming your `badgeCount` returns `pending[section]` for maintenance. If you chose a policy where maintenance does not badge, change the test's section to one that does; the test pins the mechanism, and the policy is yours.

- [ ] **Step 8: Commit**

```bash
git add humble_catalog/webapp/static/ tests/ && git commit -m "feat(viewer): badge the tabs with what each section is waiting on

Replaces the shove the auto-showing panels used to give. The counts come
from load()'s existing renderer loop, which is the one place that has
just run every loader, so a section the owner has never opened still
reports its count. No new endpoint.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: The collapsible filter sidebar

**Files:**
- Modify: `humble_catalog/webapp/static/index.html` (the Library section)
- Modify: `humble_catalog/webapp/static/style.css`
- Modify: `humble_catalog/webapp/static/catalog.js`
- Test: `tests/test_webapp_js.py`, `tests/test_webapp.py`

**Interfaces:**
- Consumes: `$`.
- Produces: `sidebarCollapsed()`, `toggleSidebar()`; `localStorage` key `hc-sidebar`.

- [ ] **Step 1: Write the failing persistence test**

Add to `tests/test_webapp_js.py`:

```python
def test_sidebar_collapse_persists():
    stored = eval_js("""(() => {
      app.toggleSidebar();
      return [globalThis.localStorage.getItem("hc-sidebar"),
              app.sidebarCollapsed()];
    })()""")
    assert stored == ["1", True]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k sidebar -v`
Expected: FAIL — `app.toggleSidebar` is not a function.

- [ ] **Step 3: Move the filters into a sidebar**

In `index.html`'s `#section-library`, wrap the table area:

```html
  <section id="section-library" hidden>
    <div id="library-layout">
      <button id="sidebar-toggle" type="button"
              aria-controls="filters" aria-expanded="true">Filters</button>
      <aside id="filters">
        <!-- everything from the old #controls EXCEPT #search-label,
             #search-wrap, #count, #export-format, #column-picker
             and #export -->
      </aside>
      <div id="library-main">
        <div id="filter-chips"></div>
        <div id="table-toolbar">
          <span id="count"></span>
          <select id="export-format" aria-label="Export format">
            <option value="csv">CSV</option>
            <option value="xlsx">XLSX</option></select>
          <details id="column-picker">
            <summary id="column-picker-summary">Columns</summary>
            <div id="column-picker-panel">
              <div id="column-picker-body"></div>
              <button id="col-all" type="button">Select all</button>
              <button id="col-none" type="button">Select none</button>
            </div>
          </details>
          <button id="export" type="button">Download all</button>
        </div>
        <div id="bulk-bar"><!-- unchanged --></div>
        <div id="stats-panel" hidden></div>
        <div id="table-wrap"><!-- unchanged --></div>
      </div>
    </div>
  </section>
```

`#search-label` and `#search-wrap` move up into the `<header>`, above `#tabs`.

> The `.chip-filter` wrappers keep their `data-field` attributes and their ids untouched — `renderFilterChips` and `wireChipFilter` query them by `.chip-filter[data-field=…]`, not by position, so moving them into the aside changes nothing for either.

- [ ] **Step 4: Add the toggle to `catalog.js`**

```js
// Sidebar collapse, persisted beside the theme. The chips in
// #filter-chips stay outside the aside, so a collapsed sidebar can never
// hide a filter that is quietly narrowing the table -- which is the only
// thing that makes collapsing safe.
const sidebarCollapsed = () =>
  (typeof localStorage !== "undefined") && localStorage.getItem("hc-sidebar") === "1";

function applySidebar() {
  const on = sidebarCollapsed();
  $("#library-layout")?.classList.toggle("collapsed", on);
  $("#sidebar-toggle")?.setAttribute("aria-expanded", String(!on));
}

function toggleSidebar() {
  if (typeof localStorage !== "undefined")
    localStorage.setItem("hc-sidebar", sidebarCollapsed() ? "0" : "1");
  applySidebar();
}
```

Add a branch to `catalog.js`'s click chain, before the final `th[data-sort]` branch:

```js
  } else if (el.id === "sidebar-toggle") {
    toggleSidebar();
```

Call `applySidebar();` at the bottom of `catalog.js`.

- [ ] **Step 5: Style it**

Append to `style.css`:

```css
#library-layout { display: grid; grid-template-columns: 16rem 1fr;
                  gap: 1rem; flex: 1; min-height: 0; }
#library-layout.collapsed { grid-template-columns: 0 1fr; }
#library-layout.collapsed #filters { display: none; }
#filters { display: flex; flex-direction: column; gap: .5rem;
           overflow-y: auto; }
#library-main { display: flex; flex-direction: column; gap: 1rem;
                min-height: 0; }
#table-toolbar { display: flex; gap: .5rem; align-items: center;
                 justify-content: flex-end; }
#sidebar-toggle { grid-column: 1; justify-self: start; }
/* Below this width the sidebar costs more than it gives, and the phone
   viewer on the backlog starts here rather than being retrofitted. */
@media (max-width: 900px) {
  #library-layout { grid-template-columns: 1fr; }
  #library-layout:not(.expanded) #filters { display: none; }
}
```

- [ ] **Step 6: Publish the hooks and run the tests**

Add to `harness.mjs`'s `publish` object:

```js
  toggleSidebar, sidebarCollapsed, applySidebar,
```

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7: Add the safety assertion**

Add to `tests/test_webapp.py`:

```python
def test_filter_chips_live_outside_the_collapsible_sidebar():
    html = (Path(__file__).parent.parent / "humble_catalog" / "webapp"
            / "static" / "index.html").read_text(encoding="utf-8")
    # a collapsed sidebar must never hide a filter that is narrowing the
    # table, so the chips render in the main column, not the aside
    aside = html[html.index('<aside id="filters"'):html.index("</aside>")]
    assert 'id="filter-chips"' not in aside
    assert 'id="filter-chips"' in html
```

- [ ] **Step 8: Check it in a browser**

Confirm: collapsing widens the table, the state survives a reload, an active chip stays visible while collapsed, and at a narrow window the sidebar starts collapsed.

- [ ] **Step 9: Commit**

```bash
git add humble_catalog/webapp/static/ tests/ && git commit -m "feat(viewer): fold the filter bar into a collapsible sidebar

Fifteen controls in one wrapping row become an aside that folds away,
with search kept in the header because it is how most sessions start.

The active-filter chips stay in the main column. That is the rule that
makes collapsing safe: a folded sidebar must never hide a filter that is
quietly narrowing the table, and a test pins the chips outside the aside.

The 900px breakpoint is the first step toward the phone viewer on the
backlog, taken now because a sidebar designed without it would be redone.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation, version bump and the release tag

**Files:**
- Modify: `README.md:18`
- Modify: `docs/BACKLOG.md` (the External keys section)
- Modify: `pyproject.toml:3`

- [ ] **Step 1: Document the sections in the README**

After the screenshot caption at `README.md:18`, add:

```markdown
The viewer has four sections, switched by the tabs and addressable by
URL: **Library** (the table, its filters and the statistics summary),
**Maintenance** (the review queue and possible duplicates), **Keys**, and
**Bundles** (paste a bundle URL to see what you already own). A tab shows
a count when its section is waiting on something.

The screenshot above predates the sections and shows the older one-page
layout.
```

- [ ] **Step 2: Annotate the backlog's key-report entry**

In `docs/BACKLOG.md`, under `### External keys (requested 2026-07-30)`, add after the first paragraph of the unredeemed key report entry:

```markdown
  The viewer half lands in the **Keys** section, which
  `specs/2026-07-30-viewer-multi-section-layout-design.md` shipped empty
  and wired for exactly this. The hidden-rows companion is the second
  view in that section rather than a sixth stacked panel — two views
  sharing a column set is what the one-page layout could not express.
```

- [ ] **Step 3: Bump the version**

`pyproject.toml` line 3: `version = "0.1.0"` becomes `version = "0.2.0"`.

- [ ] **Step 4: Run the privacy check and the suite**

```bash
.venv/Scripts/python scripts/leak_check.py
```

Expected: `clean`. Do not pipe this command.

Run: `.venv/Scripts/python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit and tag**

```bash
git add README.md docs/BACKLOG.md pyproject.toml && git commit -m "docs(viewer): describe the sections, and release 0.2.0

The screenshot is deliberately left showing the old one-page layout:
re-shooting it needs the owner's by-eye privacy pass, since item counts,
bundle names, ratings and notes are all inferable from a viewer
screenshot and no automated check reads a PNG.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

```bash
git tag -a v0.2.0 -m "Multi-section viewer: Library, Maintenance, Keys, Bundles" && git tag
```

Expected output: `v0.1.0` and `v0.2.0`.

---

## Self-review

**Spec coverage.** Hash routing → Task 5. Four sections and their membership → Task 5. Keys empty but wired → Task 5. Badges → Task 6. Filter sidebar, header chips, 900px threshold → Task 7. File split and the five files → Tasks 2-4. Harness list → Task 1. Docs, screenshot left stale, both tags, pyproject bump → Tasks 1 and 8. Out-of-scope items are absent, as intended.

**Corrections made to the spec during planning.** Two, both recorded above rather than applied silently: the boot call moves to `shell.js` (load order makes `app.js` impossible), and `test_webapp.py` *is* modified — its six text assertions read `app.js` by name, which the spec's "untouched" claim missed. Task 1 fixes those before any code moves.

**Type consistency.** `VIEWER_JS` is a `list[Path]` throughout. `showSection`/`currentSection`/`SECTIONS` are used with the same names in Tasks 5-6. `badgeCount(section)` and `pending` agree between Steps 3-5 of Task 6. `sidebarCollapsed()`/`toggleSidebar()`/`applySidebar()` agree between Task 7's Steps 4 and 6.
