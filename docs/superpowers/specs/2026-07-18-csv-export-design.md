# CSV Export — Design (v1.3)

Date: 2026-07-18
Status: approved

## Goal

Export the full catalog to a CSV file that opens cleanly in Excel,
LibreOffice Calc, and Google Sheets. Deferred from v1
(`2026-07-17-humblebundle-catalog-design.md`, "Future extensions").

## Decisions

- **Two surfaces, one implementation:** a CLI command and a web download
  button both call the same export function. No divergence possible.
- **Full catalog only:** the export always contains every item.
  Filter-aware export (export what the viewer currently shows) is out of
  scope, matching the original spec wording.
- **Stdlib only:** Python's `csv` module; no pandas/openpyxl dependency.

## Architecture

- **Shared flattening helper.** The per-item flattening currently inlined
  in the `/api/items` route (`webapp/__init__.py`) — items ⋈ enrichment,
  plus bundle list, formats, and the `edited` flag — moves to a shared
  `fetch_items(conn)` function. `/api/items` keeps its exact current JSON
  output; it just calls the helper.
- **`humble_catalog/export.py`.** `write_csv(conn, fh)` formats
  `fetch_items()` rows as CSV and returns the number of item rows written.
- **CLI.** `python -m humble_catalog export [path]`, default
  `catalog.csv`. Prints the row count and destination. Unwritable paths
  surface the OS error.
- **Web.** `GET /api/export.csv` returns the same bytes with
  `Content-Disposition: attachment; filename=catalog.csv`. The viewer
  header gains a "Download CSV" link pointing at it.

## CSV shape

One row per item, ordered by title (same ordering as `/api/items`).
Columns, in order:

```
title, type, publisher, authors, genre, series, series_number,
narrator, illustrator, my_rating, external_rating, rating_source,
formats, bundles, first_purchased, status, edited
```

- `formats` and `bundles` (bundle names) are joined with `"; "`.
- `first_purchased` is the earliest `purchased_at` among the item's
  bundles (date part only).
- `edited` is `yes` when a hand-edit snapshot exists, else empty.
- Missing values are empty cells, never the string `None`.

## Compatibility

- Encoding `utf-8-sig` (BOM) so Excel auto-detects UTF-8.
- Comma delimiter, `csv.writer` default quoting (handles embedded
  commas/quotes/newlines in titles).
- CRLF line endings per RFC 4180 (the `csv` module default when the
  stream is opened with `newline=""`).

## Error handling

- Empty catalog → header-only CSV, exit 0 (not an error).
- CLI: OS errors (permission, bad directory) propagate with a readable
  message; no partial-file cleanup needed since rows stream top-down.

## Testing

- `write_csv`: column order, `"; "` joining for multi-bundle items,
  BOM present, quoting of a title containing a comma, empty-catalog
  header-only output, `None` → empty cell.
- Webapp: `/api/export.csv` content type, attachment header, body starts
  with the header row; `/api/items` JSON unchanged after the refactor.
- CLI: `export` writes the default file and reports the row count.

## Out of scope

- Filter-aware / selected-columns export.
- XLSX output.
- Import of the reference spreadsheets (still future work).
