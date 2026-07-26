# XLSX Export — Design

Date: 2026-07-20
Status: approved

## Goal

Offer the catalog export as an `.xlsx` workbook alongside the CSV, from
both the viewer and the CLI. Deferred from CSV export
(`2026-07-18-csv-export-design.md`) and again from filter-aware export
(`2026-07-20-filter-aware-export-design.md`, "Out of scope").

The complaint behind the entry is that the export is a **working
surface**: a file you open to sort, filter and skim the library, not
merely a data interchange blob. That decides the shape of the whole
feature — the workbook gets a frozen header, an autofilter, computed
column widths and typed cells, because those are what make a
spreadsheet a place to ask questions.

## Decisions

- **Both formats, chosen explicitly.** XLSX joins CSV rather than
  replacing it. A CSV is what a script or a `curl` can consume without a
  library, and the filter-aware spec deliberately kept
  `GET /api/export.csv` as "the whole catalog at a plain URL". Two
  writers, one row source.
- **No new dependency.** `openpyxl` is already required, for
  `import_sheets.py` reading the reference workbooks. The usual "is a
  binary format worth a dependency?" objection does not apply.
- **CLI infers the format from the path suffix.** `humble export
  catalog.xlsx` writes a workbook; the default path stays
  `catalog.csv`, so typing no argument changes nothing. A `--format`
  flag is deliberately absent — it can only duplicate or contradict the
  filename it sits beside.
- **Unknown suffix is an error, not a guess.** `catalog.txt` →
  `parser.error` naming the two formats. Guessing would write a
  mislabelled file.
- **A sibling route, not a `?format=` parameter.** `/api/export.xlsx`
  next to `/api/export.csv`. The URL suffix is what makes the `GET` form
  bookmarkable and self-describing in the same way the CSV route already
  is, and the shared id-parsing is four lines.
- **Format is not persisted.** The viewer's select starts fresh each
  load. Format is a decision made at the moment of clicking, not a
  standing preference, and a remembered value with no visible reasoning
  is how someone downloads the wrong thing.
- **Styling is deliberately minimal.** Frozen header, autofilter, bold
  header, computed widths, one date format. No conditional formatting,
  no colour, no wrapped text — speculative decoration that the person
  actually using the sheet is better placed to choose.

## Architecture

```
                    db.fetch_items(conn)
                            ↓
              _select(conn, ids)   ← order + unknown-id policy, ONE copy
                            ↓
                       _row(item)   ← COLUMNS, "; " joins, typed values
                       ↙         ↘
          write_csv(conn,        write_xlsx(conn,
             fh, ids)              fh, ids)
          text handle            binary handle
          utf-8-sig BOM          openpyxl owns encoding
```

### `humble_catalog/export.py`

**`_select(conn, ids)`** is the important extraction. The rule that the
caller owns row order, that unknown ids are skipped silently, and that
the returned count stays truthful currently lives inline in
`write_csv` — three lines carrying a paragraph of the filter-aware
spec's reasoning. Copied into a second writer, it is exactly how two
exports begin disagreeing about what a stale id means. Pulled into one
function, both formats inherit the policy and one test pins it.

**`_row(item)`** changes in one place: `first_purchased` becomes
`date.fromisoformat(min(purchased)[:10])` rather than the raw string
slice.

This is safe for the CSV because `csv.writer` calls `str()` on
non-string values, and `str(date(2019, 3, 2))` is exactly `"2019-03-02"`
— the same bytes the slice produced. **The CSV output stays
byte-identical.** The cost is that the CSV's correctness now rests on an
implicit coercion, so it gets a comment and a dedicated test rather than
being left to be rediscovered.

Ratings and `series_number` need no change at all: the schema already
stores `my_rating INTEGER`, `series_number REAL` and `external_rating
REAL`, and `_row` passes the dict values straight through. It is
`csv.writer` that flattens them to text on the way out, so an XLSX
writer fed by the same `_row` gets numeric, correctly-sorting cells for
free.

**`write_xlsx(conn, fh, ids=None)`** mirrors `write_csv`'s signature and
its return value (rows written), and takes a **binary** handle. That
asymmetry is unavoidable — `openpyxl` owns its own encoding — and every
caller has to know it, so it is commented at the function.

- One `Workbook`, sheet named `Catalog`.
- Header row bold; `freeze_panes = "A2"`.
- `auto_filter.ref` spans the header through the last data row.
- `number_format = "YYYY-MM-DD"` on the `first_purchased` column. The
  cell holds a real date and *displays* ISO; value and format are
  independent properties of the cell.
- Column widths computed from the materialized rows —
  `max(len(str(v)))` per column, floored at the header's own width and
  **capped at 60** so one long `user_comment` or `bundles` join cannot
  stretch a column off-screen. There is no autofit in the format; the
  width is a number someone has to compute.

Widths are why `write_xlsx` cannot be a streaming mirror of
`write_csv`: sizing requires seeing every row first. `fetch_items`
already materializes the whole list, so this costs nothing, but it is
why the two are siblings rather than one function with a switch.

### `humble_catalog/webapp/__init__.py`

`/api/export.xlsx`, `GET` + `POST`, structurally identical to
`export_csv`: `POST` reads `ids` from the JSON body, a non-list is
`400`. Writes into `io.BytesIO` and returns the OOXML mimetype
(`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`)
with an attachment `Content-Disposition`.

### `humble_catalog/__main__.py`

`humble export [path]` dispatches on the suffix: `.xlsx` → `write_xlsx`
opened `"wb"`, `.csv` → `write_csv` opened `"w"` with
`encoding="utf-8-sig", newline=""` as today, anything else →
`parser.error`. The help text gains the workbook option.

## The viewer control

A `<select id="export-format">` with `CSV` / `XLSX` beside the existing
button, inside the header's grouped form controls so it picks up the
themed styling from the visual-improvements work.

`downloadExport()` changes minimally: read the select into `fmt`, post
to `` `/api/export.${fmt}` ``, set `a.download` to
`` `catalog${filtered ? "-filtered" : ""}.${fmt}` ``. The `shownRows()`
payload, the POST-not-GET reasoning and the Blob dance are untouched.

**The button label drops the format.** `Download CSV` hardcoded a
choice that is now the select's job, so unfiltered it becomes `Download
all`; filtered it stays `Download N shown`. The button says *what
rows*, the select says *what format*, each fact stated once. Keeping
`Download CSV`/`Download XLSX` in sync with the select was rejected: it
states the format twice unfiltered and still loses it the moment you
filter, so the redundancy buys nothing durable.

Everything else is unchanged — disabled at `count === 0`, label updated
from `render()`, and no `armOrFire` confirmation, since exporting
mutates nothing.

## Error handling

Mostly inherited rather than invented:

- **Zero visible rows** — button disabled, no request sent.
- **Stale ids** — `_select` skips them for both formats, so a row that
  vanished since the page loaded costs one row, not the download.
- **Malformed body** — missing or non-list `ids` → `400`.
- **Request failure** — the existing `alert()`, with its message
  generalized to name the chosen format. "Could not build the CSV"
  after clicking XLSX would send someone looking in the wrong place.

The one genuinely new failure mode is **openpyxl refusing a cell
value**. It rejects control characters that both SQLite and `csv`
accept, so a stray `\x00` or `\x1b` in a scraped `user_comment` or
title would `500` the XLSX route while the CSV route succeeded.
`write_xlsx` strips the forbidden control characters and keeps every
printable one. Silently: the alternative is a download that fails for a
reason the user can neither see nor fix, over data the catalog
legitimately holds.

## Testing

### `tests/test_export.py`

The existing `_seed()` fixture already supplies what the new assertions
need — two bundles with purchase dates, a numeric `my_rating` and an
`external_rating` — so the XLSX tests reuse it through an
`_export_xlsx()` sibling to `_export()`, reading back with
`load_workbook`.

- **CSV byte-identity**, first: `write_csv` output is unchanged and
  `first_purchased` still reads `"2019-03-02"` (the *earlier* of the
  fixture's two bundles — `_row` takes `min`). This guards the
  `date`-object change and fails if anyone "fixes" the implicit `str()`
  coercion.
- `my_rating` and `external_rating` are numbers, not strings
  (`isinstance(cell.value, (int, float))`) — the point of the working-
  surface decision, and the assertion that fails if `_row` starts
  stringifying.
- `first_purchased` is a date value **and** carries
  `number_format == "YYYY-MM-DD"`, checked separately: they are
  independent cell properties.
- Header row bold; `freeze_panes == "A2"`; `auto_filter.ref` covers
  header through last data row.
- A column holding an over-long value gets width `60`, not more; a
  narrow column is at least as wide as its own header.
- **`_select`'s policy, per format**: `ids=[c, a, b]` emits that order;
  an unknown id is skipped and the count reflects rows written;
  `ids=[]` gives a header-only file returning `0`. Testing these
  per-format is what catches the two exports drifting apart.
- A control character in a `user_comment` produces a sanitized cell
  rather than raising.

### `tests/test_webapp.py`

- `POST /api/export.xlsx` with an id list → OOXML mimetype, attachment
  header, and bytes that load as a workbook whose rows are in the
  posted order.
- `GET /api/export.xlsx` → the whole catalog.
- Missing or non-list `ids` → `400`.
- The CSV route's existing assertions still pass — the point being that
  adding a format broke nothing.

### `tests/test_webapp_js.py`

These run the real functions from `app.js` via `js_harness.py`, which
exists because Python route tests cannot catch a renderer that throws.

- The select drives both route and extension: `XLSX` →
  `/api/export.xlsx` and `catalog.xlsx`; filtered → `catalog-filtered.xlsx`.
- The button label reads `Download all` unfiltered, `Download N shown`
  filtered, disabled at zero. These are **updates to existing tests**,
  not new ones: the filter-aware spec pinned the old wording, and
  changing it without changing its test would leave a stale guarantee
  behind.

Fixtures use invented titles from `docs/TEST-DATA.md`;
`.venv/Scripts/python scripts/leak_check.py` runs afterwards, unpiped.

## Out of scope

- **Selected-columns export** — stays on the backlog as its own entry.
  Both formats carry all of `COLUMNS`.
- **CLI filtering flags** — the CLI still means "the whole catalog";
  filtering remains a viewer concept.
- Conditional formatting, colour, wrapped text, multiple sheets,
  embedded cover images, and any form of XLSX *import* (that is
  `import-sheets`, and it is unrelated).
