# Filter-aware CSV Export — Design

Date: 2026-07-20
Status: approved

## Goal

Export the rows the viewer is currently showing, instead of always the
whole catalog. Deferred from CSV export
(`2026-07-18-csv-export-design.md`, "Out of scope").

## Decisions

- **Rows only, not columns.** The exported file always carries all
  `COLUMNS`. A column picker stays on the backlog as its own entry: it
  is a UI project that would dominate this spec, and the row set is the
  half with a real complaint behind it.
- **Viewer only.** The CLI keeps meaning "the whole catalog". Filtering
  is a viewer concept — there is no `--genre` flag, and inventing one
  would mean a second filter implementation in Python, either without
  fuzzy search (so the two surfaces would disagree about what a filter
  *is*) or with `fuzzy.js` ported. The CSV spec's "one implementation"
  invariant survives as: one CSV **writer**, two row **sources**.
- **One control, always filtered.** With no filters active `visible()`
  is the whole catalog, so today's behaviour is preserved by
  construction rather than by a second code path.
- **On-screen order is preserved,** relevance ordering included. Order
  is part of what the viewer shows, and the client already holds the
  ordered array, so it costs nothing.
- **The client sends an ordered id list.** Rejected alternatives:
  - *Build the CSV in JavaScript.* Needs its own copy of `COLUMNS`, the
    `"; "` joins, `first_purchased` and the BOM — a second CSV
    implementation that drifts the first time a column is added.
  - *ids in a GET query string.* Keeps the plain `<a href>`, but URLs
    cap out around 2000 characters, and — decisively — a list of item
    ids in a URL describes the private library in a query string, where
    it reaches access logs and browser history. See the `CLAUDE.md`
    standing order.

## Architecture

```
visible()  →  shownRows() {ids, count, filtered}
                   │                  │
                   │                  ├─→ renderBulkBar()   (unchanged)
                   │                  └─→ the export button's label
                   ↓
        POST /api/export.csv  {"ids": [...ordered...]}
                   ↓
        export.write_csv(conn, fh, ids=None)
                   ↓
        Blob → synthetic <a download> → click()
```

- **`humble_catalog/export.py`.** `write_csv(conn, fh, ids=None)`.
  `None` keeps today's behaviour exactly: every item, `fetch_items`
  title order. With `ids`, it indexes `fetch_items(conn)` by item id and
  emits in the caller's order. Row formatting, `COLUMNS` and the return
  count are untouched.

  The contract shift is that with `ids` the **caller** owns row order;
  `write_csv` must not re-sort. That is the seam a bug would live in, so
  it gets a dedicated test.
- **`humble_catalog/webapp/__init__.py`.** The existing
  `/api/export.csv` route accepts `POST` alongside `GET`. `POST` reads
  `ids` from the JSON body and passes them through. Same `utf-8-sig`
  bytes and same headers either way.

  `GET` is kept although the viewer stops calling it: it is the whole
  catalog at a plain URL, which is what a bookmark, a `curl`, or a
  script wants, and it is the route the webapp tests already pin as the
  full-export regression guard. Deleting it would trade a working
  public entry point for nothing.
- **`humble_catalog/webapp/static/app.js`.** `bulkTarget()` is renamed
  `shownRows()` and shared. It already returns exactly
  `{ids, count, filtered}`, and "the rows on screen" stopped being a
  bulk-tagging-specific idea the moment export needed it.

## The control

`<a id="export" href="/api/export.csv" download>` becomes a
`<button id="export">` — a POST-driven download is not a hyperlink.
Styling keeps its current header-link appearance.

- **Label:** `Download CSV` unfiltered, `Download N shown` when
  `shownRows().filtered` — the same distinction the bulk bar draws.
  Updated from `render()` alongside `renderBulkBar()`, so every
  keystroke that changes the count changes the label.
- **Disabled at zero rows,** as `bulk-add` disables on `count === 0`.
  An empty export would otherwise return a header-only file that looks
  like a bug.
- **Filename:** `catalog.csv` unfiltered, `catalog-filtered.csv` when
  narrowed — a filtered export is a different artifact and should not
  silently overwrite the full one. The client sets `a.download`:
  `Content-Disposition` is advisory once the client materializes the
  Blob itself, so the filename decision lives where the `filtered` flag
  already is.
- **No confirmation.** Exporting mutates nothing, so `armOrFire`'s
  two-click gate would be noise.

## Error handling

- **Zero visible rows** — button disabled, no request sent.
  `write_csv(ids=[])` still produces a header-only file for any other
  caller.
- **Stale ids.** The client's snapshot can predate a merge or delete.
  `write_csv` **skips unknown ids silently** rather than failing: the
  export is read-only, and losing the whole download because one row
  vanished is worse than a file one row short. The returned count
  reflects rows actually written, so it stays truthful. The opposite
  choice would be right for a mutating route — leniency here follows
  from the operation being non-mutating and idempotent.
- **Malformed body** — missing or non-list `ids` → `400`, following the
  `bad candidate index` precedent in the review route.
- **Request failure** — `alert()` with the server message, as
  `runBulk()` already does.

## Testing

`tests/test_export.py`

- `write_csv(conn, fh, ids=[c, a, b])` emits rows in that order, not
  title order — the test that fails if someone sorts inside the
  function.
- A subset id list writes only those rows; the return count matches.
- `ids=None` is byte-identical to the pre-change output.
- An unknown id is skipped, not fatal; the count reflects rows written.
- `ids=[]` → header-only, returns `0`.

`tests/test_webapp.py`

- `POST /api/export.csv` with an id list → rows in the posted order,
  `text/csv`, attachment header, BOM present.
- `GET /api/export.csv` unchanged.
- `POST` with missing or non-list `ids` → `400`.

`tests/test_webapp_js.py`

- `shownRows()` returns the same `{ids, count, filtered}` under the
  existing bulk-bar scenarios — proving the rename is only a rename.
  It earns its own test because `filtered` gates bulk tag *removal*,
  which is unrecoverable.
- The export label tracks the filter: `Download CSV` unfiltered,
  `Download N shown` narrowed, disabled at zero.
- The posted id order equals `visible()`'s order under an active fuzzy
  query — the only place the relevance-ordering decision is pinned.

Fixtures use invented titles from `docs/TEST-DATA.md`;
`.venv/Scripts/python scripts/leak_check.py` runs afterwards, unpiped.

## Out of scope

- Selected-columns export (stays on the backlog).
- XLSX output.
- CLI filtering flags.
