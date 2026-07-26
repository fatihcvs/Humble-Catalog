# Selected-columns Export — Design

Date: 2026-07-20
Status: approved

## Goal

Choose which columns land in the exported file. Deferred twice: split
out of filter-aware export (`2026-07-20-filter-aware-export-design.md`)
on the grounds that rows and columns are independent features, and left
out of XLSX export (`2026-07-20-xlsx-export-design.md`) for the same
reason.

This is the mirror image of the filter-aware work — same feature, other
axis — and the two must stay independent: a row filter and a column
selection compose, and neither knows about the other.

## Decisions

- **Export columns only.** The on-screen table keeps its own
  hand-tuned 12 columns and its editable cells. The table's list and
  `COLUMNS` are deliberately different — the table folds `illustrator`
  into "Narrator/Artist" and omits `formats`, `status`,
  `first_purchased`, `rating_source`, `series_number` and `edited` —
  so "the columns you see" and "the columns you export" are not one
  concept, and making them one is a renderer project, not this.
- **Both surfaces.** Viewer picker and a CLI `--columns` flag. Row
  filtering was rightly viewer-only: it needed the fuzzy predicate, and
  a `--genre` flag would have meant a second filter implementation.
  A column list is just a list of names, so that objection does not
  transfer, and it makes the export scriptable.
- **The client never controls column order.** The requested list is
  normalized to `[c for c in COLUMNS if c in requested]`. One
  comprehension is simultaneously the validator (unknown names vanish),
  the de-duplicator (a repeated name cannot produce two columns) and
  the ordering policy. Honouring a caller-supplied order would need
  three separate pieces of code to buy the same guarantees, and would
  invite a reordering UI nobody asked for.

  Note this is the *opposite* choice from the row axis, where the
  caller owns the order and `_select` must never re-sort. That is not
  an inconsistency: on-screen row order is a thing the user built with
  sorting and relevance ranking, and is therefore information. Column
  order is not — nobody drags the checkboxes.
- **Unknown names: silent on the web, loud on the CLI.** Deliberately
  asymmetric, because the provenance differs. A stale
  `hc-export-columns` in someone's browser can outlive a `COLUMNS`
  rename by months, and a `500` in that situation punishes the user for
  the schema's history. A typo'd `--column authors` on a command line
  is a mistake being made right now, and quietly handing back a file
  missing authors is worse than refusing.
- **An empty selection falls back to all columns** rather than writing
  a zero-column file. Applies wherever normalization empties the list
  — including a stored selection that no longer matches anything.
- **Persisted, unlike the format.** `hc-export-columns` in
  `localStorage`, following the `hc-theme` precedent. The XLSX spec
  deliberately did not persist the format select; re-ticking a
  19-checkbox set every visit is a different order of friction, and the
  picker's `(12/19)` label keeps a non-default state permanently
  visible, which is what made the unpersisted-format argument work.
- **No reordering, no presets, no saved column sets.** A selection is a
  set of checkboxes. Everything else is speculative.

## Architecture

```
        db.fetch_items(conn)
                ↓
        _select(conn, ids)      ← ROW policy: order, stale ids
                ↓
        _row(item, columns)     ← COLUMN policy: projection
              ↙       ↘
    write_csv(conn, fh,   write_xlsx(conn, fh,
       ids, columns)         ids, columns)
                              ↓
                        _style(ws, columns)
```

The two axes meet only in the writers' signatures. `_select` is not
touched: it is the row policy, and that is exactly why the XLSX spec
extracted it. Giving it a second concern would undo that.

### `humble_catalog/export.py`

**`_columns(requested)`** — new, and it lives here rather than in the
webapp or the CLI so both callers cannot disagree about what a valid
selection is:

```python
def _columns(requested):
    if not requested:
        return COLUMNS
    chosen = tuple(c for c in COLUMNS if c in requested)
    return chosen or COLUMNS
```

`None` and `[]` both mean "everything", which is what makes every
existing caller and both existing test suites unaffected by
construction — the same trick `ids=None` already pulls.

**`_row(item, columns)`** takes the projection target explicitly. The
value-building above it is unchanged: it computes the same `values`
dict regardless, and only the final comprehension narrows. Building
just the requested values would save nothing measurable and would add a
branch per column.

**`write_csv(conn, fh, ids=None, columns=None)`** and
**`write_xlsx(conn, fh, ids=None, columns=None)`** each resolve
`cols = _columns(columns)` once and use it for the header row, every
data row, and — for XLSX — for styling. Return values and handle
contracts are untouched.

**`_style(ws, columns)`** is the one place with a real bug waiting in
it. It currently locates the date column with
`COLUMNS.index("first_purchased")`, a positional assumption against the
global that is invisible until the global stops being the whole truth
— which is precisely what this feature does to it. It becomes a lookup
in the *actual* column list, and the date formatting is skipped
entirely when `first_purchased` was not selected. `auto_filter.ref`
likewise spans `len(columns)`, not `len(COLUMNS)`.

### `humble_catalog/webapp/__init__.py`

Both `POST` routes read an optional `columns` key alongside `ids` and
pass it through. A non-list `columns` is `400`, matching the existing
`ids` precedent; a list containing unknown names is *not* an error, per
the asymmetry decision above — `_columns` drops them.

`GET` on both routes is unchanged: the whole catalog, every column, at
a plain bookmarkable URL.

### `humble_catalog/__main__.py`

`humble export [path] [--columns title,authors,my_rating]`.
Comma-separated, whitespace around names tolerated, normalized to
canonical order by `_columns` like every other caller. Unknown names →
`parser.error` listing exactly the names that were not recognized;
`--columns ""` → `parser.error` as well, since an explicitly empty
selection on a command line is a mistake, not a request for
everything.

Validation uses `export.COLUMNS` directly rather than a second list in
the CLI. The help text names the flag as taking a comma-separated
subset and points at the default (all columns).

## The viewer control

A `<details id="column-picker">` beside the existing format select,
inside the header's grouped controls so it inherits the themed styling
from the visual-improvements work. `<details>` is chosen over a modal
because nothing else in this viewer is modal, and over
`<select multiple>` because ctrl-clicking nineteen options is a bad way
to toggle a set and one stray click wipes it.

- **Summary label:** `Columns (19/19)`, updating live. The count is the
  whole justification for persisting the selection: a narrowed export
  is never invisible.
- **Body:** one checkbox per entry of `COLUMNS`, in `COLUMNS` order,
  rendered from a JS list rather than hand-written markup so a new
  column cannot be added to `export.py` and forgotten here. Plus
  `Select all` / `Select none`.
- **Closes on outside click**, the one behaviour `<details>` does not
  give for free.
- **`downloadExport()`** posts `{ids, columns}` and treats a narrowed
  column set as another way of being `filtered` for filename purposes
  — so `catalog-filtered.csv` covers fewer rows, fewer columns, or
  both. This honours the original reason for the suffix (a partial
  export must not silently overwrite the full one) without inventing a
  second filename vocabulary or a four-way matrix.
- **Export button disabled at zero columns**, exactly as it already is
  at zero rows, and for the same reason: a file with no columns reads
  as a bug rather than as an empty result. The all-columns fallback in
  `_columns` therefore never fires from the viewer's own UI — it is
  there for stale storage and for other callers.
- **Persistence:** `localStorage.setItem("hc-export-columns", ...)` on
  every toggle, guarded by `typeof localStorage !== "undefined"` like
  `hc-theme`, because the JS test harness's sandbox has neither
  `localStorage` nor `matchMedia`. On load, stored names not in
  `COLUMNS` are dropped; an empty or unparseable result means all
  columns.

## Error handling

Mostly inherited:

- **Zero visible rows** — button disabled, no request sent.
- **Zero columns selected** — button disabled, no request sent.
- **Stale ids** — `_select` skips them, unchanged.
- **Unknown column names** — dropped on the web, `parser.error` on the
  CLI. The asymmetry is the decision, not an oversight.
- **Unparseable stored selection** — treated as absent; all columns.
- **Malformed body** — missing or non-list `ids`, or non-list
  `columns` → `400`.
- **Request failure** — the existing `alert()` naming the format.

No new failure mode is introduced on the XLSX side: the control-
character sanitizer already sits in `write_xlsx`, and narrowing the
column set can only remove cells, never add ones it has not seen.

## Testing

### `tests/test_export.py`

- `_columns` directly: an unordered request comes back in `COLUMNS`
  order; duplicates collapse; unknown names vanish; `None`, `[]` and
  an all-unknown list each give the full tuple. This is the function
  three callers depend on, so it is pinned once here rather than
  three times indirectly.
- CSV with a column subset: header and rows carry exactly those
  columns, in canonical order regardless of the order requested.
- `columns=None` is byte-identical to the current output — the
  regression guard that makes the whole change safe.
- Rows and columns compose: `ids=[c, a]` with a two-column selection
  gives two rows in the posted order and two columns in canonical
  order. The test that fails if either axis starts consulting the
  other.
- XLSX with a subset: the same projection, plus `auto_filter.ref`
  spanning the *narrowed* last column, and widths still computed and
  capped.
- **XLSX with `first_purchased` deselected**: no cell carries the date
  `number_format` and nothing raises. This is the `COLUMNS.index`
  landmine, and it gets a test of its own.
- XLSX with `first_purchased` selected but not first: the date format
  lands on the column it actually occupies, not on position 15.

### `tests/test_webapp.py`

- `POST /api/export.csv` and `.xlsx` with `columns` → narrowed files,
  canonical order.
- An unknown name in `columns` is dropped, not a `400`; the rest of
  the selection still applies.
- `columns: []` and a fully-unknown list → all columns, `200`.
- Non-list `columns` → `400`.
- `GET` on both routes still yields all columns.

### `tests/test_webapp_js.py`

These run the real functions from `app.js` via `js_harness.py`, which
exists because Python route tests cannot catch a renderer that throws.

- The picker renders one checkbox per `COLUMNS` entry and the summary
  count tracks toggling.
- The posted body carries the checked names; unchecking one removes it.
- Zero checked → export button disabled.
- A narrowed column set alone (no row filter) produces
  `catalog-filtered.csv`. This is an **update** to the existing
  filename test rather than a new one: the filter-aware spec pinned
  `filtered` to mean "fewer rows", and widening it without changing
  its test would leave a stale guarantee behind.
- A stored selection is restored on load; a stored name no longer in
  `COLUMNS` is dropped rather than rendering a phantom checkbox.

### `tests/test_main.py`

- `--columns` writes the subset; whitespace around names is tolerated.
- An unknown name exits non-zero and names it.
- `--columns ""` exits non-zero.

Fixtures use invented titles from `docs/TEST-DATA.md`;
`.venv/Scripts/python scripts/leak_check.py` runs afterwards, unpiped.

## Out of scope

- Column **reordering**, saved column sets, and named presets.
- Table column visibility in the viewer — a different complaint
  (screen width) with a different solution.
- CLI row filtering; the CLI still means "the whole catalog".
- Any change to `_select`, to the stale-id policy, or to the `GET`
  routes.
