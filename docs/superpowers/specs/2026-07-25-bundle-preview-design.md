# Bundle preview — design

Date: 2026-07-25

## Problem

Deciding whether to buy a live bundle means answering "how much of this
do I already have?", and after several years of buying book bundles the
honest answer is often "most of it". Publishers re-run collections: the
same subproducts reappear in a new bundle with new art and a new tier
layout, and nothing on the page says which of them you already own.

The catalog knows the answer and cannot currently be asked. The only
way to check today is to read the bundle page and search the viewer
title by title, which is slow enough that it does not happen at the
moment of the decision.

## Goal

Point the app at a live bundle URL and get back, per tier, how many
items it contains, how many are already in the catalog, and how many
would be new — as exact facts, not estimates — plus a separately
labelled list of items that *may* overlap something already owned.

Read-only. Nothing is written to `catalog.db`.

## Why the page can be read at all

A Humble bundle page embeds its own contents as JSON:

```
<script id="webpack-bundle-page-data" type="application/json"> … </script>
  → bundleData.tier_item_data        # {machine_name: {human_name, …}}
  → bundleData.tier_display_data     # {tier: {tier_item_machine_names: [...]}}
  → bundleData.tier_pricing_data     # {tier: {"price|money": {currency, amount}}}
```

This was verified against live pages during design, unauthenticated: a
plain `GET` with no cookies returns the full blob. The feature needs no
Humble session and never touches `humble_api.py`.

Two properties of that blob decide the design:

**`tier_item_data` is keyed by `machine_name`** — the same identifier
`parse_order` stores in `items.machine_name` (a UNIQUE column). Ownership
is therefore an exact set intersection, not a title-matching heuristic.
Measured on a 23-item re-run bundle: 21 of 23 items matched by
`machine_name` alone.

**Tiers are already cumulative.** The top tier's
`tier_item_machine_names` contains every lower tier's entries, so "new
at this tier" is one set difference with no accumulation logic.

## What `machine_name` does and does not cover

`machine_name` is stable for the *same subproduct*, which is what makes a
re-run bundle read exactly. It is not stable across publishers: a 36-item
bundle measured during design had **zero** `machine_name` hits, while
nine of its titles were plainly related to owned rows.

Every one of those nine was the same shape — the bundle sells an omnibus,
the catalog holds a single volume:

```
  Shadow Hound Vol. 1-6      (offered)   ~   Shadow Hound Vol 1   (owned)
  Moonfall Vol. 1-3          (offered)   ~   MOONFALL, Vol. 1     (owned)
```

There is no correct automatic answer here. Counting it as owned hides
five new books; counting it as new hides that you are re-buying one.
So the report does not decide: exact hits drive the counts, and these
appear in their own labelled list.

### The overlap threshold is its own number

The first draft reused `matching.REVIEW` (0.60). Measurement rejected it.
Scoring the 36 offered titles against the whole catalog with
`fuzz.token_set_ratio`:

| Threshold | Result |
|---|---|
| 0.60 | unusable; hundreds of unrelated pairs |
| 0.75 | still junk — unrelated titles sharing a volume suffix score 75 |
| 0.90 | exactly the nine genuine omnibus/volume pairs, no false positives |

`bundle_preview.OVERLAP = 0.90` is therefore a local constant with its
own justification, not an import from `matching`. `AUTO`/`REVIEW` exist
to decide whether to *write* enrichment onto a row; this decides whether
to show a human a hint. Different question, different tolerance.

## Module

New `humble_catalog/bundle_preview.py`, split at the network seam:

```python
fetch_bundle(url, http=None) -> dict     # network: fetch + parse the blob
preview(conn, bundle) -> dict            # pure: no network, no writes
```

The split is the one `harvest`/`enrich` already made, for the same
payoff: `preview()` takes a plain dict, so the interesting cases —
cumulative tiers, exact hits, omnibus overlap, a bundle owned outright,
a bundle owned not at all — are all testable from a committed fixture
with no network and no live bundle. `fetch_bundle` keeps thin tests for
the parse and for a dead page.

### Fetching

`fetch_bundle` reuses `url_import._fetch_html`, which already carries the
guards this needs: the `http`/`https` allowlist, the re-check of the
scheme *after* redirects, `MAX_HTML_BYTES`, and the shared retry policy.
It does not reuse `_generic_og` — a bundle page needs its own parser, so
this is a new handler rather than a fallback.

The host must be `humblebundle.com` or a subdomain; anything else is a
`ValueError`. The blob is located by `<script id="webpack-bundle-page-data">`;
a page without one raises `ValueError("not a Humble bundle page")`, which
is also what an expired bundle redirected to the storefront will produce.

### What counts as owned

```sql
SELECT machine_name FROM items
UNION
SELECT dropped_machine_name FROM merges
```

The `merges` half is load-bearing. A duplicate merged away still names a
book that is in the library; omitting it would report an owned item as
new and overstate the gain — the exact direction of error this feature
exists to prevent.

### Report shape

One dict, two consumers:

```python
{
  "name": str, "url": str, "currency": "EUR",
  "tiers": [                       # sorted by price, descending
    {"price": 21.90, "total": 35, "owned": 12, "new": 23,
     "new_items": ["…machine_name…"]},
  ],
  "overlaps": [
    {"offered": "Shadow Hound Vol. 1-6", "item_id": 41,
     "item_name": "Shadow Hound Vol 1", "score": 0.97},
  ],
}
```

Tiers sort on the numeric `amount`, not on `tier_order`. `tier_order`
was observed in descending order, but nothing documents that it must
be; sorting costs one line and cannot be broken by Humble reordering a
key.

The overlap pass runs only over items that did *not* match exactly, so
work is proportional to the unowned remainder.

## Surface

Both, sharing `preview()` — the arrangement the statistics panel settled
on, so the CLI and the viewer cannot drift.

- **`python -m humble_catalog bundle <url>`** — prints the report.
- **`POST /api/bundle-preview`**, body `{"url": …}` — returns it as JSON.

`POST`, not `GET`, for the reason filter-aware export chose one: a bundle
URL in a query string reaches access logs and browser history, and which
bundles are being eyed is the same class of information as which books
are owned.

### CLI output

```
Humble Book Bundle: The World of Examplia

  €21.90   35 items    owned 12    new 23
  €13.13   24 items    owned 12    new 12
   €5.47   11 items    owned  9    new  2

  Possibly already owned in part (2):
    Shadow Hound Vol. 1-6   ~  Shadow Hound Vol 1   (0.97)
    Moonfall Vol. 1-3       ~  MOONFALL, Vol. 1     (0.93)
```

Highest tier first: that is the tier being decided against.

Deliberately **no price-per-new-item column**. It is arithmetic the
reader can do, and printing it invites reading "cheap per item" as
"worth buying" — precisely the misjudgement this feature exists to
correct, since a bundle whose top tier yields one new book has a terrible
per-item price that a good per-item price elsewhere on the page would
soften.

The currency symbol comes from `currency`. Per the statistics-panel
lesson, the CLI degrades a symbol the console cannot encode rather than
raising: the Windows default is `cp1252`, which cannot encode `€` any
more than it could encode `★`, and `capsys` captures as UTF-8 so no test
can observe this. It is handled at the CLI boundary by construction, and
the web route keeps the symbol.

### Viewer

A collapsed `<details>` panel with a URL input, following the statistics
panel's markup and open-state pattern. Submitting POSTs and renders the
same table.

The overlap list is what earns the panel its place: each row's owned
title links to that item in the table, so "you may own part of this"
becomes one click to *which* part. That link is the one thing the CLI
cannot offer.

The panel is fetch-on-demand, not rendered at page load, so unlike the
statistics panel it needs no refresh-after-mutation wiring — it holds no
state that can go stale.

### The separation is the feature

`owned`/`new` are exact-id facts. `overlaps` is a labelled suspicion.
The two are never summed and never share a line. If they ever merge into
one number, that number stops being a fact, and a number that cannot be
trusted is worse than no feature — it would be relied on for exactly
the decision it would be quietly wrong about.

## Error handling

Deliberately thin, because the feature is aimed at live pages.

- Non-Humble host, unparseable URL, no data blob → `ValueError`, which
  the CLI prints and the route returns as `400`.
- HTTP error (404 on a retired bundle, 5xx) → propagates from
  `_fetch_html`; the CLI prints `404` and the status text, the route
  returns `502` with the same message.
- Network failure → propagates, same as every other network path.

No modelling of expired bundles, no cached fallback, no retry beyond the
shared policy.

## Testing

Two committed fixtures, both using invented names from
`docs/TEST-DATA.md`:

- `tests/fixtures/bundle_data.json` — the `bundleData` dict `preview()`
  consumes: three cumulative tiers, a mix of owned and unowned
  `machine_name`s, and one omnibus that should surface as an overlap.
- `tests/fixtures/bundle_page.html` — a minimal page wrapping that dict
  in the `webpack-bundle-page-data` script tag, for `fetch_bundle`'s
  parse tests. Trimmed to the tag and enough surrounding markup to be
  realistic; the live page is ~650 KB and none of the rest is read.

- cumulative tiers produce a correct per-tier set difference
- `merges.dropped_machine_name` counts as owned
- a bundle owned outright reports `new 0` on every tier
- a bundle owned not at all reports no overlaps when no titles are close
- an omnibus/volume pair appears in `overlaps` and **not** in `owned`
- a title at 0.75 does not appear in `overlaps`
- tiers come out price-descending even when `tier_order` is shuffled
- `fetch_bundle` parses the blob; a page with no blob raises `ValueError`
- a non-Humble host raises `ValueError` before any request is made
- the CLI prints without raising when stdout cannot encode the currency
  symbol

## Privacy

No bundle URL, report, or item name is written to `catalog.db` or to any
log. The route takes the URL in a POST body. The committed fixture uses
invented names only; `scripts/leak_check.py` covers it like any other
fixture.

## Out of scope

- **Persistence** — no preview history, no watchlist, no cache. The
  report is a question, not a fact about the library; running it twice
  is cheap.
- **Volume-range resolution** — parsing `Vol. 1-6` into a set and
  reporting "you own 1 of 6". The most useful possible answer and the
  most likely to be subtly wrong, since Humble's title conventions are
  not consistent. Revisit once the overlap list shows how often ranges
  actually appear.
- **Past/expired bundles as a gap-finder** — the aim is live purchase
  decisions.
- **Non-book bundles**, tier bonus/hidden items
  (`bonus_item_machine_names`, `hidden_machine_names`), and Humble
  Choice.

## Build order

1. `preview()` + fixture tests — the report is the risky part and is
   fully testable offline.
2. `fetch_bundle` + the `bundle` subcommand.
3. The viewer panel and `POST /api/bundle-preview`.

Each step is independently useful; the CLI proves the data can be
relied on before anything is spent on presentation.
