# Statistics / overview panel — design

Date: 2026-07-24.

One collapsible viewer panel answering *what is in this library?* — counts
by type, the rating distribution, the reading-status breakdown, enrichment
coverage, the outstanding gaps, and the genre spread — with every row
clicking through to the filter that shows those items. The counting lives
in one Python module: the viewer fetches it from a new `/api/stats`, and a
widened CLI command prints the same six sections.

Supersedes the panel half of
`2026-07-24-gaps-health-report-design.md`: the gaps summary panel and the
genre tag panel are folded into this one, and the `gaps` subcommand widens
into `stats`.

## Problem

Six numbers about the library are either invisible or scattered. Three are
genuinely absent — nothing says how the catalog splits by type, how the
ratings are distributed, or how much of it enrichment actually matched.
Three exist but each in its own panel or control: gaps in `#gaps-panel`,
the genre spread in `#genres-panel`, the reading-status breakdown only as
whatever the status chips happen to select.

The result is that "state of the library" is a question the viewer can
almost answer but never in one place, and two of the three panels stacked
above the table are each showing one small table.

## Goals

- One panel, six sections, every count derived from data already in
  `db.fetch_items`. No new columns and no new stored data.
- **One implementation of the counting, in Python**, served to the viewer
  and printed by the CLI, so the two cannot disagree by construction.
- Every non-zero row clicks through to the filter that isolates those
  items, so the overview is a way *into* the catalog rather than a dead
  readout.
- Each number lives in exactly one place on the page.
- The CLI and the viewer keep answering identically, which is the property
  `gaps.py` was built to hold.

## Non-goals

- **Charts or graphs.** Counts in labelled tables. A bar chart of five
  rating buckets is decoration, and the viewer has no charting dependency
  worth adding for it.
- **Statistics over the filtered set.** The panel always counts the whole
  catalog (see the decision below).
- **Historical trends.** Nothing records catalog state over time, and
  adding that would mean storing snapshots this design has no use for.
- **New stored data.** Every section is a pure function of current rows.
  The one schema change is an index, which stores no facts.

## Decisions taken (and why)

- **Whole-catalog counts, always.** The panel never follows `visible()`.
  It is a stable "state of the library" readout, matching what the gaps
  panel and the CLI already do, and it makes click-through unambiguous:
  a row's count is what you will see after the jump, not a number that
  compounds onto filters already set. A filtered breakdown was considered
  and dropped — it re-renders on every keystroke and turns click-through
  into a feedback loop.

- **Computed once, in Python, served over `GET /api/stats`.** The counting
  lives in `stats.py`; the CLI prints its result and the viewer renders it.
  Drift between the two surfaces stops being a risk to test for and
  becomes impossible.

  Deriving in the browser was considered first, because the viewer mutates
  ratings and reading status in place and a server-computed panel goes
  stale the moment a star is clicked. Measuring settled it. Nearly every
  mutation in `app.js` *already* does `await load()`; exactly two — the
  star click and the reading-status select — update `items` in place, so
  keeping the panel fresh costs two call sites, not a sweeping change.
  What it must not cost is a full catalog refetch: `/api/items` is 1.3 MiB
  at 2000 items and re-renders the whole table, which is why those two
  handlers were written in place to begin with. A dedicated endpoint
  returning only the counts is about a kilobyte.

  So the two handlers keep their optimistic in-place update and `render()`,
  and call `refreshStats()` *after* it. The table stays instant; the panel
  trails by one round trip — measured at ~50 ms for 2000 items, under
  10 ms for 500. Nobody watches the panel while clicking stars in the
  table.

- **The counts come from `fetch_items`, not from SQL aggregates.**
  A `GROUP BY` implementation would answer in about a millisecond, but
  genre is stored as JSON inside a TEXT column and the per-item view is
  the thing the CSV export and `/api/items` already agree on. Counting a
  second way, against the tables directly, re-opens exactly the drift
  `gaps.py` was written to close. Speed is not the constraint here.

- **`downloads` gains the index it always needed.** Because every stats
  request runs `fetch_items`, its cost stopped being a once-per-page-load
  detail and got measured — and it turned out to be quadratic.
  `fetch_items` looks up formats per item with
  `WHERE item_id=? AND kind='humble'`, and `downloads` has no index on
  `item_id`, so each lookup scans the whole table. Adding
  `downloads(item_id)` took a synthetic 5000-item catalog from **701 ms to
  152 ms**, and 2000 items from 137 ms to 48 ms. This is a pre-existing
  bug, not one this feature introduces; it is fixed here because this
  feature is what exposed it, and because every `load()`, every CSV export
  and the CLI all get faster for it.

- **`Unrated` appears only under Gaps.** The ratings section shows ★1–★5
  only. Unrated is already a gap, already a `#f-flag` option, and already
  a CLI row; listing it twice in one panel would break the one-place rule
  this design exists to restore. The distribution then answers "of what I
  have rated, what is the shape", which is the more useful question.

- **Two new `#f-flag` options rather than four half-live rows.**
  `#f-flag=review` covers `low_confidence` and `unmatched` *together*, and
  `matched` / `pending` have no filter at all. Rather than ship four
  enrichment rows that look clickable and are not, `#f-flag` gains
  "Matched" and "Pending enrichment" — one `<option>` and one predicate
  each — and each enrichment row jumps to its own state.

- **Genre management survives, behind a toggle.** The genres panel's
  per-tag rename/delete controls are a shipped feature (v1.10), not a
  statistic. They move into this panel's genre section but stay hidden
  until an **Edit tags** toggle is pressed, so the default view stays a
  read-only overview.

- **`gaps` renamed rather than kept as an alias.** The subcommand shipped
  the same day as this design and the tool has exactly one user, so
  back-compat churn is nil.

## The six sections

Rendered in this order. Row order within each section is fixed by the
definition, never by count, so the panel does not reshuffle as the library
changes.

| Section        | Rows                                                    | Click-through            |
|----------------|---------------------------------------------------------|--------------------------|
| Type           | E-books, Audiobooks, Comics, Music/Soundtracks, Android apps | sets `#f-type`      |
| Ratings        | ★1 … ★5                                                 | sets `#f-rating` (new)   |
| Reading status | Want to read, Unread, Reading, Read, DNF                 | sets the status chip set |
| Enrichment     | Matched, Low confidence, Unmatched, Pending              | sets `#f-flag`           |
| Gaps           | Unrated, No cover, No source URL                         | sets `#f-flag`           |
| Genres         | top 15 by count desc, **Show all N** expands              | adds a genre chip        |

Type rows use the same five values and labels as `#f-type`'s options;
reading-status rows use the five-state vocabulary in lifecycle order
(`want_to_read → unread → reading → read → dnf`), matching the sort;
enrichment rows use the four `enrichment.status` values.

A zero count renders greyed and unclickable, following the shipped
`gap-zero` rule — so a clean category is a visible confirmation rather
than a missing row.

Genres is the one section whose rows are ordered by the data: count
descending, ties broken alphabetically so the order is total and stable.
The panel shows the top 15 and **Show all N** reveals the rest in that
same order. This is a deliberate change from the retired genres panel's
alphabetical listing — sorted by size the block reads as a statistic,
which is the job it now has.

## Design

### 1. Shared definitions — `humble_catalog/stats.py`

`gaps.py` is renamed to `stats.py` and widened from one gap list to an
ordered section list. Each section is a key, a display label, and a
function from an items list to `[(row_label, count), ...]`:

```python
SECTIONS = (
    ("type",       "By type",        _by_type),
    ("rating",     "Ratings",        _by_rating),
    ("status",     "Reading status", _by_read_status),
    ("enrichment", "Enrichment",     _by_enrichment),
    ("gaps",       "Gaps",           _by_gap),
    ("genre",      "Genres",         _by_genre),
)
```

The existing `GAPS` tuple survives verbatim as `_by_gap`'s data, so the
three-way agreement it guards — CLI, `#f-flag` values, panel — is
untouched.

`report(items)` returns `(sections, total)` where `sections` is
`[(key, label, rows), ...]` in `SECTIONS` order and `total` is
`len(items)`. It stays pure: no connection, no I/O, counting over the same
per-item view `fetch_items` feeds `/api/items` and the CSV export.

Every row function tolerates a missing key the way `gaps.report` does
today — a partial payload from an older server must not raise. A row whose
value falls outside its fixed vocabulary (an unexpected `type`, say) is
counted nowhere rather than inventing a row; section counts therefore need
not sum to the total, which is already true of Genres and Gaps.

### 2. CLI — `stats` subcommand

`run(conn)` prints each section as a heading followed by right-aligned
counts, then the catalog total, with counts padded to the width of the
total so the columns line up:

```
By type
   412  E-books
   118  Audiobooks
    23  Comics

Ratings
    41  ★1
   ...

   553  items total
```

The `gaps` parser entry in `__main__.py` becomes `stats`, with help text
covering the wider report.

### 3. Web route — `GET /api/stats`

```json
{"total": 553,
 "sections": [{"key": "type", "label": "By type",
               "rows": [{"label": "E-books", "count": 412}, ...]}, ...]}
```

The route is `stats.report(db.fetch_items(conn))` reshaped into that
object — rows become `{label, count}` pairs so the viewer never indexes
into a tuple by position. `key` is what the viewer maps to a filter; the
CLI ignores it. GET only, no parameters: the report is always the whole
catalog, so there is nothing to pass and nothing to put in a query
string.

Payload is roughly a kilobyte and does not grow with the catalog, except
for the genre section, which carries one row per tag.

### 4. Viewer — the new filters

`#f-rating` is a new `<select>` in the filter bar beside `#f-type`:
`Any rating` plus ★1–★5. `visible()` gains one comparison against
`i.my_rating`.

`#f-flag` gains two options, `matched` and `pending`, each a comparison
against `i.status`. Both follow the existing flag pattern in `visible()`.

### 5. Viewer — `refreshStats` and `renderStats`

`renderGaps` and `renderGenres` are replaced by a fetch and a renderer.
`refreshStats()` gets `/api/stats`, stores the response in a module
`statsData`, and calls `renderStats()`; `renderStats()` draws whatever is
in `statsData` and draws nothing when it is null. Splitting them means the
renderer stays synchronous and can be re-run — on a `<details>` toggle, a
**Show all** click — without re-fetching.

`refreshStats` joins the guarded step loop in `load()`, so a failed stats
fetch reports itself and leaves the rest of the page up, exactly as the
loop already protects the other renderers.

The panel is a single `<details id="stats-panel">` whose summary carries
the item total, and whose body is a CSS grid of six labelled blocks;
Genres spans the full width, and the grid collapses to one column on a
narrow viewport.

The viewer holds **no** section or row definitions — those arrive with the
data. What stays in JS is a `SECTION_FILTERS` map from a section key to
how a row of that section applies a filter (`type` sets `#f-type`,
`rating` sets `#f-rating`, `gaps` and `enrichment` set `#f-flag`, `status`
toggles the status chip set, `genre` pushes a chip). That is presentation,
not counting, and it is the only place the two languages still have to
agree — on six key names.

Genre truncation is presentational: the route returns every genre row and
`renderStats` shows the first 15 until **Show all** is pressed. The CLI
prints them all.

Three module flags carry state across the `innerHTML` rebuild, following
the shipped `genresOpen` pattern: `statsOpen` (panel open), `genresShowAll`
(full genre list vs top 15), and `tagEditMode` (rename/delete controls
visible).

Click-through extends the delegated document click handler, following
`gap-jump`: set the control's value, then call `render()` by hand, because
assigning `.value` does not fire the select's input listener.

**Keeping the panel fresh.** Every mutation that already ends in
`await load()` gets a refreshed panel for free, because `load()` calls
`refreshStats()`. The two that do not — the star click and the
reading-status select — keep their optimistic in-place update and
`render()`, then call `refreshStats()` afterwards. The table updates
instantly and the panel follows one round trip later. A rating row's count
is therefore briefly one behind the table it sits above; at the measured
latencies this is not perceptible, and the alternative (blocking the
star's own re-render on a server round trip) would be.

### 6. Retiring the two panels

`#genres-panel` and `#gaps-panel` are removed from `index.html` and
replaced by a single `#stats-panel` div in the same position. The genre
rename/delete click handlers keep their existing button classes and
continue to work unchanged — only the markup's origin moves. Both already
end in `await load()`, so a rename or delete refreshes the panel through
the normal path.

### 7. The `downloads` index — `user_version` 6

`SCHEMA` gains `CREATE INDEX IF NOT EXISTS ix_downloads_item_id ON
downloads(item_id)` so fresh databases get it, and `_migrate` gains a
version 6 step creating it on existing ones. Index-only: no column
changes, no data rewritten, and `IF NOT EXISTS` makes it safe to re-run.
It is the first migration in this schema that exists purely for speed,
which is worth a comment saying so.

## Testing

- `tests/test_stats.py` (from `test_gaps.py`): per-section counts; empty
  catalog gives every section its zero rows in order; a missing key counts
  as absent rather than raising; an out-of-vocabulary value is counted
  nowhere; section and row ordering is fixed.
- `tests/test_webapp.py`: `GET /api/stats` returns the documented shape;
  its counts match `stats.report()` over the same database; an empty
  catalog gives a well-formed response rather than an error.
- `tests/test_webapp_js.py`: the panel renders all six sections from a
  stubbed `/api/stats` response; each click-through sets its own filter
  and re-renders; the genre section shows 15 rows with a Show all control
  and the full list after it; the Edit tags toggle reveals and hides the
  controls; a zero row is not clickable; `renderStats` with no data yet
  draws nothing rather than throwing; a failing stats fetch leaves the
  table rendered.
- **A `SECTION_FILTERS` coverage test**: every section key the route can
  return has an entry in the viewer's map. That map is the one place the
  two languages must still agree, so it is the one thing worth pinning
  now that the counting is not duplicated.
- `tests/test_cli.py`: `stats` prints every section; `gaps` is gone.
- `tests/test_db.py`: the version 6 migration creates the index, is
  idempotent, and a fresh database built from `SCHEMA` already has it.

## Privacy

`/api/stats` is a new endpoint, so it is worth being explicit: it carries
**counts and genre tag names only** — no titles, no authors, no bundles,
nothing identifying an owned item. It is GET with no parameters, so
nothing about the library reaches a query string, which is the rule
filter-aware export was designed around. It adds no export and no logging.
Genre tags are already rendered by the panel this replaces.

Fixtures use the invented titles and tags from `docs/TEST-DATA.md`;
`scripts/leak_check.py` runs after the test fixtures land.

## Files touched

- `humble_catalog/gaps.py` → `humble_catalog/stats.py` (widened)
- `humble_catalog/__main__.py` (`gaps` parser → `stats`)
- `humble_catalog/db.py` (`SCHEMA` index; `_migrate` version 6)
- `humble_catalog/webapp/__init__.py` (`GET /api/stats`)
- `humble_catalog/webapp/static/app.js` (`refreshStats`, `renderStats`,
  `SECTION_FILTERS`, two new flag predicates, `#f-rating` in `visible()`,
  click-through, `refreshStats()` in the two in-place handlers;
  `renderGaps`/`renderGenres` removed)
- `humble_catalog/webapp/static/index.html` (`#stats-panel` replaces
  `#genres-panel` and `#gaps-panel`; `#f-rating`; two `#f-flag` options)
- `humble_catalog/webapp/static/style.css` (the section grid; the
  `#review-panel, #dupes-panel, #genres-panel` sizing rule and the
  `#genres-panel` / `#genres-table` rules re-point at `#stats-panel`)
- `tests/test_gaps.py` → `tests/test_stats.py`; `tests/test_webapp.py`;
  `tests/test_webapp_js.py`; `tests/test_cli.py`; `tests/test_db.py`
- `docs/BACKLOG.md` (entry moves to Done)
