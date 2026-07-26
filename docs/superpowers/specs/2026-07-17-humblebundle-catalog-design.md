# HumbleBundle Library Catalog — Design

**Date:** 2026-07-17
**Status:** Approved design, pending implementation plan

## Purpose

The user has bought many e-books, audiobooks, and comics on HumbleBundle over the
years, with no overview of what they own or where to download it. This project
extracts that library into a local, searchable catalog that answers three
questions:

1. What have I bought?
2. Do I already own this? (checked quickly, e.g. while browsing a sale)
3. Where do I download it?

Manual data entry is limited to the user's own ratings and occasional match
corrections. Extraction must be courteous to HumbleBundle: low request rate,
no re-fetching of known data, no page scraping.

## Architecture

A single Python project with three independent, resumable CLI commands sharing
one SQLite database (`catalog.db`):

| Command          | Role                                                        |
|------------------|-------------------------------------------------------------|
| `humble extract` | Pull owned bundles/items from HumbleBundle's JSON API       |
| `humble enrich`  | Fill genre/series/ratings/narrator etc. from external APIs  |
| `humble serve`   | Local web app: search, filter, review matches, set ratings  |

- **Language/stack:** Python 3.12, Playwright (login only), requests, Flask,
  SQLite, vanilla-JS single-page viewer.
- Each stage is idempotent and interruptible. `extract` fetches only unseen
  bundles; `enrich` processes only items missing data; `serve` is read/write
  for user ratings and match fixes only.

## Extraction

- **Login:** First run opens a visible Playwright browser window with a
  persistent profile. The user logs in themselves (Google SSO + TFA). The
  session is stored locally; subsequent runs are unattended. On session
  expiry, the login window reopens and the run continues afterwards.
- **API, not scraping:** Uses HumbleBundle's own JSON endpoints (the ones
  their web frontend calls):
  - `GET /api/v1/user/order` — list of purchase keys (one request)
  - `GET /api/v1/order/<gamekey>` — full bundle contents (one request per
    bundle): item names, publishers, cover URLs, download formats and links,
    external redemption links (e.g. DriveThruRPG keys)
- **Throttling:** ≥ 4 seconds between requests.
- **Caching:** Raw JSON responses are stored on disk; a bundle is never
  re-fetched once captured. Re-runs cost one listing request plus one request
  per *new* bundle.
- **Covers:** Thumbnail images downloaded once into `covers/` during
  extraction, so the viewer never hotlinks HumbleBundle's CDN.
- **Download links:** Direct file URLs are signed and expire, so the catalog
  stores stable links instead: the bundle's HumbleBundle download page, plus
  any external redemption URL. Items only available on external services
  (e.g. DriveThruRPG) link to that service; the user takes it from there.

## Data model

SQLite tables (columns abridged):

- **bundles** — gamekey (PK), name, HumbleBundle download-page URL, purchase
  date
- **items** — id, name, type (`ebook` | `audiobook` | `comic`), publisher,
  cover path, my_rating (0–5, nullable), type_overridden flag
- **item_bundles** — item ↔ bundle many-to-many. A book bought in several
  bundles links to all of them; the viewer lists the chronologically first
  bundle first.
- **downloads** — item id, kind (HB download page / external redemption),
  URL, format list (EPUB/PDF/MOBI/audio…)
- **enrichment** — item id, genre, series, series_number, authors[],
  narrator, illustrator, external_rating, rating_source, match_confidence,
  status (`matched` | `low_confidence` | `unmatched` | `manually_fixed`),
  cached candidate matches, per-source raw responses
- **raw_orders** — gamekey, fetched-at, raw JSON (the extraction cache)

**Type classification:** HumbleBundle does not cleanly distinguish comics
from books. Type is inferred from download formats (audio ⇒ audiobook) plus
bundle-name heuristics (e.g. "Comics", "Manga" ⇒ comic), and is overridable
per item in the viewer (`type_overridden` prevents re-classification).

## Enrichment

Pipeline per item: clean the marketing title (strip "(Book 1)", ": A Novel",
edition tags, series suffixes) → query sources by type → fuzzy-match results
(title + author similarity) → score confidence.

| Type                | Sources, in order                                             |
|---------------------|---------------------------------------------------------------|
| E-book / RPG book   | Hardcover → Google Books → Open Library                       |
| Audiobook           | Audnexus (narrator, Audible rating) → e-book sources for gaps |
| Comic               | Comic Vine (series, issue number, writers, artists)           |

- First confident hit wins; external rating prefers Hardcover (books) /
  Audible via Audnexus (audiobooks) / Comic Vine (comics). Any available
  edition's rating (audio, ebook, print) is acceptable for audiobooks.
- **Confidence handling:** confident matches are written automatically;
  low-confidence results are stored as candidates and flagged. The viewer's
  review queue lets the user pick the right candidate with one click, or
  search manually. `manually_fixed` items are never overwritten by re-runs.
- **Rate limits & resumability:** heavily throttled per source (Comic Vine
  200 req/h respected), all responses cached, safe to interrupt and resume;
  intended to be left running overnight.
- **API keys required (free, one-time user setup):** Hardcover, Comic Vine.
  Google Books, Open Library, and Audnexus need none at this volume.

## Viewer

`humble serve` starts a local Flask app and opens the browser:

- **Search-as-you-type** across name, authors, series, narrator, bundle.
- **Filters:** type, genre, bundle, publisher, "in multiple bundles",
  "needs review", "unrated by me".
- **Table columns** (mirroring the user's existing spreadsheets): cover
  thumbnail, name, genre, series + number, authors, narrator (audiobooks),
  illustrator (comics), publisher, bundle(s) with links, external rating,
  editable ★ 0–5 my-rating (click to set; saved immediately).
- **Review queue:** page listing `low_confidence` / `unmatched` items with
  clickable candidates.
- Sortable columns. Reachable from other devices on the LAN if desired.

## Progress reporting

Long-running commands (`extract`, `enrich`) must clearly show how far along
they are, and the display must be decoupled from the work itself:

- **In the terminal:** a plain progress line per unit of work, e.g.
  `Bundle 34/120: Humble Book Bundle: Examplia…` and a summary on
  completion (fetched, skipped, failed counts). Nothing fancy.
- **In the database:** each run writes its state (phase, done/total, current
  item, started-at, last-update) to a `run_status` table as it goes.
- **In the viewer:** when a run is active, `humble serve` shows a progress
  banner/page reading from `run_status`. Closing the browser tab or the
  viewer never affects the running process — the process owns the work, the
  displays only observe it.
- Because both commands are resumable from the database/cache, even killing
  the terminal mid-run loses at most the item in flight; the next run
  continues where it left off.

## Error handling

- HumbleBundle session expired → reopen login window, then continue.
- Any HTTP failure → retry with exponential backoff; on repeated failure,
  mark the item/bundle and continue the run (nothing aborts a long batch).
- Enrichment finds nothing → status `unmatched`, visible in review queue.
- User data (`my_rating`, manual fixes, type overrides) is never modified by
  `extract` or `enrich` re-runs.

## Testing

- Unit tests for title cleaning and match scoring (the fragile logic).
- Parser tests against saved real HumbleBundle JSON fixtures, so future
  format drift surfaces as a failing test instead of silent bad data.
- Manual end-to-end verification against the user's real account for the
  first full run.

## v1.1 — Review & source-link upgrade (approved 2026-07-17)

- **Source links:** every enrichment candidate carries the URL of its source
  record (Hardcover book page, Comic Vine volume/issue, Open Library work,
  Google Books volume, Audible product, O'Reilly page). The matched item's
  name in the catalog links to its `source_url`; review-queue candidates
  link out for inspection.
- **O'Reilly source:** e-book source using O'Reilly's publicly reachable
  learning-platform search endpoint (fixture-captured like Hardcover).
  Packt/No Starch/Manning/Pearson have no public APIs and are already
  indexed by Google Books; not added. DriveThruRPG has no API; covered by
  URL import below.
- **Review queue:** sorted by best-candidate confidence descending; shows
  the item's own cover thumbnail; every apply action (candidate click or
  URL import) requires an in-page confirmation (second click) before
  writing.
- **URL import:** per review item, a textbox accepts a URL from a supported
  source (comicvine.gamespot.com, hardcover.app, openlibrary.org,
  books.google.com, audible.com, learning.oreilly.com, drivethrurpg.com);
  the system fetches that exact record (DriveThruRPG: og-meta extraction
  from the single product page) and offers it as a confirmable candidate.
- **Nothing is final:** stored candidates are kept for every item; a
  "redo" control on any item (matched or manually fixed) reopens it in the
  review queue with all candidates intact. CLI: `enrich --reset` clears all
  enrichment to pending; `enrich --reset-reviews` clears only manual
  choices. `my_rating` and type overrides always survive.

## v1.2 — Inline editing with revert-to-enriched (approved 2026-07-18)

- **Editable fields:** genre, series, series_number, authors, narrator,
  illustrator only. Name/publisher/bundles stay as HumbleBundle reports
  them; my_rating and type keep their existing dedicated controls.
- **Snapshot revert:** the first hand-edit of an item copies the six
  fields' current values into a new `enrichment.pre_edit` JSON column
  (idempotent migration). Later edits leave the snapshot alone, so revert
  always restores the last enriched (or originally empty) state.
  `pre_edit IS NOT NULL` doubles as the "hand-edited" flag.
- **API:** `POST /api/items/<id>/edit` `{fields: {...}}` (only the six
  fields; unknown keys 400; series_number numeric or null),
  `POST /api/items/<id>/revert` (400 when no snapshot), `/api/items`
  exposes `edited`. Applying any candidate (`/choose` or `/apply`) clears
  the snapshot: the candidate becomes the new revert baseline.
- **Resets:** `enrich --reset` wipes edits with everything else;
  `--reset-reviews` skips hand-edited rows so typed-in work survives.
- **UI:** a pencil control beside the redo control turns the row's four
  metadata cells into inputs with Save/Cancel; edited items show an
  "edited" badge and a revert control behind the standard two-click
  confirm.

## Future extensions (out of scope for v1)

- **Android APKs** — some bundles include Android APK rewards (platform
  `android`); currently excluded from the catalog. Low priority per user
  (2026-07-17).

- **CSV export** — export the full catalog to CSV importable into Excel,
  LibreOffice Calc, or Google Sheets (requested 2026-07-17).
- Import of the two existing reference spreadsheets' hand-entered ratings.
- Goodreads ratings, should an official API return.

## Explicitly out of scope

- Downloading the actual book/audio files (catalog links to them instead).
- Tracking non-book HumbleBundle purchases (games, software).
- Any cloud/hosted component; everything runs locally.
