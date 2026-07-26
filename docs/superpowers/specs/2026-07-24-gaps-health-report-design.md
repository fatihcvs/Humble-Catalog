# Gaps / health report — design

Date: 2026-07-24.

## Problem

The catalog has no way to answer "what is left to fill in?" at a glance.
Individual gaps are visible one at a time — the `#f-flag` dropdown
already has an "Unrated by me" filter — but there is no aggregate view,
and two obvious gaps have no filter at all: items with no cover image and
items with no `source_url`. The Review panel covers enrichment gaps
(unmatched / low-confidence matches) but nothing about completeness of a
settled item.

Recorded as an open backlog item ("`gaps` / health report").

## Goals

- One aggregate summary of what is incomplete, showing counts across all
  gap types at once, on two surfaces: a CLI report and a viewer panel.
- Let the viewer drill from a summary count straight into the matching
  rows, so the summary drives fixes rather than just reporting numbers.
- Fill the two missing viewer filters ("No cover", "No source URL") so
  every gap type the summary names is also a one-click filter.

## Non-goals

- No schema change. Every gap is an existing nullable column.
- No network. Pure derivation from data already loaded / already in the
  database.
- No new `/api/gaps` endpoint. The viewer already loads every item; the
  panel derives its counts client-side, matching how the Genres panel
  works.
- No opinion on enrichment status. A gap is "this column is empty,"
  counted across all items regardless of `status`, consistent with the
  existing "Unrated" filter which also ignores status. Pending and
  needs-review items are therefore counted; that is intentional — the
  report is a complete picture of what is missing, not a to-do list
  scoped to finished work.

## Gap types

Three gaps, each the same shape ("a column is empty"), counted across all
items:

| Gap           | Rule                  | Existing filter? |
|---------------|-----------------------|------------------|
| Unrated       | `my_rating` empty     | yes (`unrated`)  |
| No cover      | `cover_path` empty    | no (new)         |
| No source URL | `source_url` empty    | no (new)         |

"Empty" means falsy: NULL, missing, or empty string. `my_rating` and
`source_url` come through `fetch_items`; `cover_path` is a column on
`items`.

## Design

### 1. Shared definition — `humble_catalog/gaps.py`

A new small module, mirroring `export.py`: a pure function plus a `run`
entry point, so the CLI stays a thin wrapper.

- `GAPS` — an ordered list of `(label, flag_key, predicate)` describing
  the three gaps. `flag_key` is the string the viewer's `#f-flag`
  dropdown uses (`"unrated"`, `"nocover"`, `"nourl"`), tying the CLI's
  labels to the viewer's filters so the two name the same things.
- `report(items)` — takes the `fetch_items` list and returns
  `(rows, total)`, where `rows` is `[(label, count), ...]` in `GAPS`
  order and `total` is `len(items)`. Pure; no connection, no I/O.
- `run(conn)` — calls `db.fetch_items(conn)`, then `report`, then prints
  an aligned table (count, label) followed by the total for context.

Counting over the `fetch_items` output — the same per-item view that
feeds `/api/items` and CSV export — is the anti-drift lever: the CLI and
the viewer count over an identical item representation, so the only thing
that can differ is the three predicate rules themselves, which the tests
pin on both sides.

### 2. CLI — `gaps` subcommand

In `humble_catalog/__main__.py`, add `sub.add_parser("gaps", help=...)`
with no arguments, and a dispatch branch:

```python
elif args.command == "gaps":
    from humble_catalog import db, gaps
    conn = db.connect()
    try:
        gaps.run(conn)
    finally:
        conn.close()
```

Output shape (illustrative counts, invented catalog size):

```
   12  Unrated
    8  No cover
   31  No source URL
  340  items total
```

### 3. Viewer flag filters

Two additions each in two files, matching the existing `unrated` filter:

- `index.html`: two `<option>`s in `#f-flag` — `nocover` ("No cover") and
  `nourl` ("No source URL").
- `app.js`, in `visible()`, beside the existing
  `if (flag === "unrated" && i.my_rating) return false;`:

  ```js
  if (flag === "nocover" && i.cover_path) return false;
  if (flag === "nourl" && i.source_url) return false;
  ```

### 4. Viewer summary panel

A collapsible `<details>` panel following the Review / Duplicates /
Genres pattern (`loadGaps` added to the boot sequence beside
`loadReview` / `renderGenres`). It derives its three counts client-side
from the loaded `items` array using the same three rules as the
predicates in step 3, and renders one row per gap: the label, the count,
and a control that sets `#f-flag` to that gap's key and re-renders — the
summary-to-fix loop. Zero gaps in a category renders the row greyed / not
clickable rather than hidden, so the panel doubles as a "these are clean"
confirmation.

## Testing

- `tests/test_gaps.py` (new) — unit-test `gaps.report` against fixtures
  with known gaps: an item missing each column, an item missing several,
  a fully-populated item, and empty-string vs NULL for each field.
  Asserts exact counts and `GAPS` ordering.
- `tests/test_webapp_js.py` — extend the existing flag-filter coverage
  with the two new predicates (`nocover`, `nourl`), including the
  empty-string-counts-as-empty case, so the JS rules are pinned to the
  same contract as the Python ones.
- A CLI smoke test asserting `gaps` runs and prints the total line.

Both language sides assert the same three rules; drift surfaces as a test
failure.

## Privacy

Fixtures use invented titles from `docs/TEST-DATA.md` (adding new ones
there if needed). Run `.venv/Scripts/python scripts/leak_check.py` after
adding tests and this doc.

## Files touched

- `humble_catalog/gaps.py` (new)
- `humble_catalog/__main__.py` (subcommand + dispatch)
- `humble_catalog/webapp/static/index.html` (two `<option>`s, panel markup)
- `humble_catalog/webapp/static/app.js` (two predicates, `loadGaps`)
- `tests/test_gaps.py` (new), `tests/test_webapp_js.py` (extend)
- `docs/BACKLOG.md` (remove the entry once shipped)
