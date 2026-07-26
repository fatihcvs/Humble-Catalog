# Game library ownership — design

Date: 2026-07-25

## Problem

`bundle` answers "how much of this do I already have?" only for books.
Pointed at a game bundle it does not degrade — it gives a confident wrong
answer.

Measured during design against a live 12-item Steam bundle whose games
are partly owned:

```
  12 items    owned 0    new 12
  Possibly already owned in part (2):    ← both nonsense
```

Two failures, not one. The counts miss every owned game, because game
items are matched by `machine_name` against a catalog that holds only
books. And the overlap pass then fuzzy-matches game titles against book
titles, inventing two "possibly already owned" hints between unrelated
media.

The owner's games live in Steam and in Heroic (GOG, Epic, Amazon, Zoom).
The catalog cannot see either, so the one question the feature exists to
answer is answered backwards for a whole class of bundle.

## Goal

Import the owned game libraries, and let `bundle` count game items
against them.

Explicitly **not** a game catalog. No enrichment, no covers, no viewer
columns, no export, no ratings, no reading status. Games never enter
`items`. The launchers already browse and filter a game library well;
this exists only to answer the ownership question at the moment of a
purchase decision.

## Ownership for games is approximate, and says so

The book path is exact because Humble names each item with the same
`machine_name` the catalog stores. **No such shared key exists for
games.** A Humble bundle item carries no Steam appid and no GOG product
id, so the only available join is the title, and the only available
method is fuzzy.

That is a real reduction in what the report can promise, and the design
treats it as a first-class fact rather than a footnote:

- Game counts are labelled approximate wherever they appear.
- The report names the age of the data behind them.
- Uncertain matches are counted as neither owned nor new.
- The README says so, and says to verify against the launcher.

This follows the rule the book path already settled on: exact facts and
labelled suspicions are never summed and never share a line. Here the
whole game half is a labelled suspicion, so the labelling is louder.

## Sources

### Heroic's on-disk caches (GOG, Epic, Amazon, Zoom)

Heroic writes each store's library to plain JSON under
`%APPDATA%\heroic\store_cache\`, verified during design:

```
gog_library.json        {"games":   [...], "__timestamp": {...}}   ~800 entries
legendary_library.json  {"library": [...], "__timestamp": {...}}   ~700 entries
nile_library.json       {"library": [], ...}        logged out → empty list
zoom-library.json       {}                          logged out → empty object
```

Entries carry `title`, `app_name`, `runner` (`gog`, `legendary`, …) and
`is_installed`. `title` is all the matcher needs.

Note the container key differs — `games` for GOG, `library` for the
rest. The reader handles both. These files are not a published contract,
which is the main cost of this route and the reason for the importer
boundary below.

**Why not implement GOG's OAuth directly.** Heroic runs GOG Galaxy's own
flow: Galaxy's hardcoded `client_id`/`client_secret`, an auth code caught
off the `embed.gog.com/on_login_success` redirect, exchanged at
`auth.gog.com/token`, then the library from
`galaxy-library.gog.com/users/{id}/releases`. Doing the same here would
mean authenticating as GOG Galaxy, storing a live refresh token to a
purchasing account beside a catalog that currently holds nothing more
sensitive than a book list, owning the endpoint churn (GOG has already
moved this once), and adding the one seam this repo cannot fixture-test.
It would buy perfect freshness — the *accurate* half of a deliberately
approximate answer. A two-week-stale library is a far smaller error
source than title matching already is. Deferred, not rejected: the
importer boundary makes it a later backend swap.

### Steam's Web API

Heroic does not manage Steam, and Steam's local files cannot answer the
question. Local `appmanifest_*.acf` files describe *installed* games
only — about 250 across two libraries on the owner's machine — while
Humble keys are typically activated and never installed. The local path
would under-report exactly the games a bundle is most likely to
duplicate.

So Steam uses the sanctioned API:

```
GET https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/
    ?key=…&steamid=…&include_appinfo=1
```

`include_appinfo=1` is what returns `name` rather than bare appids. The
key is free to any Steam account; the profile's game details must be
public. Configured as `STEAM_API_KEY` + `STEAM_ID`, and skipped entirely
when unset — the pattern `GOOGLE_BOOKS_API_KEY` already established.

## Data model

One new table, read by nothing except the preview:

```sql
CREATE TABLE games (
  store            TEXT NOT NULL,   -- steam | gog | epic | amazon | zoom
  store_id         TEXT NOT NULL,   -- appid, or Heroic's app_name
  title            TEXT NOT NULL,
  normalized_title TEXT NOT NULL,   -- match key, see below
  imported_at      TEXT NOT NULL,
  source_timestamp TEXT,            -- Heroic's __timestamp; NULL for Steam
  PRIMARY KEY (store, store_id)
);
```

`normalized_title` is stored rather than computed per preview: the match
runs over the whole library on every game bundle, and normalization is
the expensive half.

A second table records what each run actually managed to read, which is
what makes "not imported" distinguishable from "owns nothing":

```sql
CREATE TABLE game_imports (
  store     TEXT PRIMARY KEY,
  imported_at TEXT NOT NULL,
  count     INTEGER NOT NULL,
  source    TEXT NOT NULL          -- 'heroic' | 'steam'
);
```

## Module

New `humble_catalog/import_games.py`, split at the network/filesystem
seam the way `harvest`/`enrich` and `bundle_preview` already are:

```python
read_heroic(root=None) -> list[dict]    # filesystem: parse the caches
fetch_steam(key, steamid, http=None)    # network: one API call
store_games(conn, rows, store, source)  # pure-ish: replace one store
```

`bundle_preview.py` gains only a second ownership lookup. Neither module
knows the other's internals.

## Matching

### Routing

Verified against the live bundle: items carry `platforms_and_oses`,
shaped

```json
{"game": {"steam": ["windows", "mac", "linux"]}}
```

The **inner key is the delivery store** — the routing key this design
needs. `item_content_type: "game"` corroborates it. Not every entry has
it: the same bundle had one item with `{}` and no content type, and that
item was in no tier at all.

Ownership is therefore decided in order, first answer wins:

1. Exact `machine_name` against the catalog → unchanged, so book bundles
   behave exactly as today.
2. Else, if `platforms_and_oses` names a game delivery store → match the
   title against `games`.
3. Else → today's fuzzy book-overlap hint.

Each item routes itself, so a mixed bundle needs no global "is this a
game bundle?" decision, and the non-game entry above falls through
harmlessly.

### Normalizing

`clean_title` does not transfer — it is tuned for books (`: A Novel`,
edition suffixes). A sibling `clean_game_title` handles what game titles
actually carry: `™`/`®`, `Game of the Year Edition`, `Definitive
Edition`, `Remastered`, `Enhanced Edition`, trailing punctuation.

Edition suffixes fold into the base title deliberately: owning *Widget
Quest* means a bundle offering *Widget Quest: Definitive Edition* is not
a new game to you. Sequels must not fold — *Widget Quest II* is a
different game — so trailing arabic and roman numerals are never
stripped.

### Three buckets, not two

Matched with `rapidfuzz` against `games.normalized_title`, same library
and approach as `_overlaps`:

- **owned** — above a confident threshold
- **possible** — a middle band; counted as neither owned nor new
- **new** — below the band

Threshold values are not invented here. They get measured during
implementation against a real game bundle, and the measurement is
recorded in the constant's comment — the evidence-attached style
`OVERLAP = 90.0` already sets.

The bias is deliberate: **conservative about claiming owned.** Wrongly
claiming ownership costs a bundle the owner wanted; wrongly claiming
novelty costs money. The middle band exists so the tool declines to
guess rather than picking a side, which is the same refusal the omnibus
overlap list already makes.

## Reporting

Each tier grows a `possible` count beside `owned`/`new`, and uncertain
titles are marked in the tier's `adds` list rather than silently
included or excluded.

```
Humble Game Bundle: Story Sampler

  €10.95   12 items    owned 4    possible 1    new 7
              adds 7 new:
                Lantern & Lockpick
                …
              1 possible:
                Starfall Rally Turbo  ~  Starfall Rally  (0.88)

  Game ownership is matched by title and is approximate.
  Libraries imported: steam 3d ago, gog 3d ago. Epic never imported.
```

The footer prints whenever any game matching happened. It carries the
approximation warning and the age of each library — so a cache three
months stale says so at the moment of the decision, and a store that was
never imported is named rather than silently treated as owning nothing.

## Failure and edge cases

The organizing principle: **never let missing data look like a confident
answer.**

- **Never imported.** A game bundle with an empty `games` table reports
  game counts as unknown, not as zero-owned, and says to run
  `import-games`.
- **Store never imported.** Checked per store via `game_imports`. A
  bundle delivering on Steam with no Steam import says so specifically.
  This is the highest-value guard here: "you own none of these" and "I
  have no idea whether you own these" are indistinguishable as counts.
- **Steam private profile.** `GetOwnedGames` returns an empty list rather
  than an error. A successful-but-empty Steam response is therefore
  treated as an error: it never replaces existing rows.
- **Heroic absent or logged out.** A missing file, `{}`, or an empty
  list contributes nothing and is reported per store. Partial success is
  normal, not an error.
- **Malformed cache.** Heroic may be mid-write. Parse everything first,
  then replace per store in a transaction, so a bad file fails loudly
  and leaves prior data intact.
- **Same game on two stores.** Counts once toward a tier: ownership is a
  property of the bundle item, not of the rows.
- **Removed or revoked games.** Per-store replace on success, so a game
  gone from a store disappears rather than lingering.

## Surface

- **`python -m humble_catalog import-games`** — runs every configured
  source, prints what each contributed. Idempotent; safe to re-run.
- **`python -m humble_catalog bundle <url>`** — unchanged interface, now
  game-aware.

No viewer panel in this design. The bundle panel already exists and
picks the new counts up through the shared `preview()`; nothing about
importing needs a UI.

## Testing

All matching and reporting is pure. Committed fixtures, invented names
only, per `docs/TEST-DATA.md`:

- `tests/fixtures/game_bundle_data.json` — an anonymized capture of a
  real game bundle's `bundleData`: `platforms_and_oses` present on most
  items, absent on one, and one item in no tier.
- `tests/fixtures/heroic_gog_library.json`, `heroic_legendary_library.json`
  — trimmed caches covering both container keys, plus the empty-list and
  `{}` logged-out shapes.

Cases:

- an owned game counts as owned; an unowned one as new
- an edition suffix over an owned base reads as owned
- a sequel does **not** match its predecessor
- an ambiguous pair lands in `possible` and in neither count
- a game owned on two stores counts once
- a mixed bundle routes book items by `machine_name` and game items by
  title, and game titles never produce book overlaps
- an item with empty `platforms_and_oses` falls through to the book path
- an empty `games` table reports unknown, never zero-owned
- a store absent from `game_imports` is named in the footer
- an empty Steam response raises and does not clear existing rows
- a malformed Heroic file leaves the previous rows intact

## Privacy

The imported library is the owner's game collection, so it is subject to
the same standing order as the book catalog. All fixtures use invented
names from `docs/TEST-DATA.md`; the captured bundle fixture is
anonymized before commit; `scripts/leak_check.py` runs before committing
fixtures or tests.

`import-games` reads Heroic's caches but never writes to them, and never
reads `gog_store/auth.json` — Heroic's tokens are out of scope entirely.
No credential is ever stored by this feature: Steam's key lives in the
environment, like every other API key here.

One consequence worth stating: because the games land in `catalog.db`, a
`backup` snapshot now also contains the game list. No credentials, but a
wider snapshot than before.

## README wording

Ships with the feature, not before it:

> Game bundles are matched differently. Steam and GOG titles have no
> shared id with your imported libraries, so ownership for games is
> matched **by title and is approximate** — a near-miss can read as
> owned, and a re-release or edition difference can read as new. Treat
> the game counts as a strong hint, not a fact, and check anything you'd
> base a purchase on against the launcher itself.

## Out of scope

- **Browsing or filtering games** in the viewer. The launchers do it.
- **Enrichment, covers, ratings, status, export** for games.
- **GOG/Epic OAuth.** Deferred; see above. The importer boundary makes it
  a backend swap rather than a rewrite.
- **Wishlists, playtime, achievements** — Heroic caches some of this and
  none of it bears on the ownership question.
- **Fixing `_overlaps` iterating items sold in no tier.** Pre-existing,
  unrelated, and now visible because the design touched that code path;
  a backlog note, not this change.

## Build order

1. `games`/`game_imports` tables + `read_heroic` + `import-games` for
   Heroic only. Immediately useful: GOG and Epic are the verified caches.
2. Matching and three-bucket counting in `preview()`, against fixtures.
3. Reporting: footer, staleness, never-imported guards.
4. Steam via `GetOwnedGames`.

Steam is last deliberately — it is the only step needing a key and a
network call, and steps 1–3 prove the matching can be relied on before
anything depends on it.
