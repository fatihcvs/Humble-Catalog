# Backlog

Postponed features and ideas, consolidated from the design docs' "future
extensions" / "out of scope" sections. When an item ships, move it to the
**Done** list at the bottom with its version. When a new design doc defers
something, record it here so the deferral has a home.

Last updated: 2026-07-30.

## Privacy

Not a backlog item — the rule itself is the standing order in
`CLAUDE.md` ("nothing that reveals what the owner actually owns"). This
is its operational side: what enforces it, and when.

Three checks, cheapest first:

| Check | Asks | When |
|---|---|---|
| `scripts/check_no_data_tracked.py` | Is a data *file* tracked, now or anywhere in history? | Every `verify`, and in CI |
| `scripts/leak_check.py` | Does a private *term* appear in the working tree? | Every `verify` |
| `scripts/leak_check_history.py` | Do those terms appear in any git object or commit message? | Before a first public push; after any history rewrite |

Only the first needs no catalog to do its job — it reads path names, so
it works on a clone or a CI runner. The other two derive their terms
from `catalog.db` and the reference spreadsheets and report `SKIPPED`
without them, which is why CI cannot be the real gate for either.

Acting on a hit:

- **A term in the working tree** — reword it, drawing invented names
  from `docs/TEST-DATA.md`. If it is ordinary English matching as a
  substring rather than a real reference, add it to `ALLOWED` in
  `leak_check.py` with a comment saying why.
- **A term or file in history** — cannot be edited away. It needs
  `git filter-repo` before anything is pushed.

Two things that stay true regardless:

- **`main` starts at a squashed initial commit (2026-07-26).** The
  development history was bundled to
  `../humble-catalog-pre-public-history-2026-07-26.bundle` (367
  commits, outside the repo) and its branch deleted, so this repo
  holds no unpublished history at all. The reason is structural: the
  term list is derived from the live catalog, so every substantial
  harvest can reveal older commits whose test data happens to name
  something now owned — successive rewrites would each fix only that
  day's snapshot. A history beginning at a verified clean tree cannot
  reopen the question. Read the bundle by restoring it to a throwaway
  clone (`git clone <bundle> tmp`); never fetch or merge it back here.
- **History was also rewritten on 2026-07-18** to purge the pre-scrub
  commits. Never merge or restore a clone predating that date; it would
  put the old history back.
- **Deleting a file does not unpublish it.** Anything already pushed
  should be treated as public, whatever HEAD says afterwards.

## Open

### User tags and comments (deferred from user tags, `specs/2026-07-19-user-tags-and-comments-design.md`)

- **Undo for bulk tagging** — a single-level undo ("restored 'lent out'
  to 47 items"). Deferred from bulk tagging: `user_tags` sits outside
  `pre_edit` by design, so a bulk *remove* is unrecoverable. A bulk add
  can already be undone with catalog-wide tag delete when the tag is
  new; removal has no equivalent. Removal is gated behind an active
  filter in the meantime.

### Catalog features (identified 2026-07-24 code review)

Ideas surfaced by reading the code rather than deferred from a design
doc — several sit at boundaries the code itself calls out. Each stands on
its own; none is committed to.

- **ebook ↔ audiobook edition linking** — a soft "same work" relationship
  between an item owned in two formats, without merging them. `/api/merge`
  deliberately refuses cross-type merges ("an ebook and its audiobook stay
  separate"), which is correct, but leaves the two formats with no
  relationship at all; a link would let a row show "also owned as
  audiobook". This is the gap the merge route's own comment points at.

### Bundle preview (deferred from `specs/2026-07-25-bundle-preview-design.md`)

- **Volume-range resolution** — parse an offered `Vol. 1-6` into a set
  of volumes, compare against the volumes actually owned, and report
  "you own 1 of 6" instead of listing the pair as a possible overlap.
  The most useful answer the feature could give and the most likely to
  be subtly wrong, since Humble's title conventions are not consistent.
  Revisit once the overlap list has shown how often ranges appear in
  practice.
- **Past/expired bundles as a gap-finder** — running the preview against
  bundles that have closed, to see what was missed. The shipped feature
  aims at live purchase decisions and reports a dead page as a plain
  404.
- **`_overlaps` hints about items no tier sells** — it iterates every
  entry in `tier_item_data`, and a live bundle was observed carrying 13
  entries while its only tier listed 12. The extra entry can therefore
  surface as a possible overlap for something the bundle does not
  actually offer. Pre-existing; noticed while adding game matching.
- **GOG/Epic OAuth instead of Heroic's caches** (deferred from
  `specs/2026-07-25-game-library-ownership-design.md`) — talk to
  `auth.gog.com` and `galaxy-library.gog.com` directly rather than
  reading Heroic's on-disk JSON. Always fresh and drops the Heroic
  dependency, at the cost of a stored refresh token to a purchasing
  account and endpoint churn GOG has already made once. The importer
  boundary means this is a backend swap, not a rewrite: it would fill the
  same `games` table. Revisit if cache staleness or a Heroic format
  change actually bites.

### External keys (requested 2026-07-30)

- **Unredeemed key report** — a table of Humble store keys held whose game
  appears in no imported store library, i.e. probably never activated.
  This is [`_keyed_games`](../humble_catalog/bundle_preview.py) inverted:
  that helper answers "do I already own this bundle's games somehow", and
  the same `external_keys` → `bundles` join plus `clean_game_title`
  matching against `games.normalized_title` answers the complementary
  question, "what have I paid for and never claimed". Surfaced behind one
  shared API route rendered as both a viewer panel and a CLI subcommand,
  the way `stats` is, so the two cannot drift.

  Columns, defaulting to expiry ascending with undated rows last so the
  rows that can still be lost come first:

  | Column | Source | Note |
  |---|---|---|
  | Product | `human_name` | |
  | Key type | `key_type_human_name` | 52 distinct strings including `Other` and `other`; needs the case folding `specs/2026-07-18-genre-case-normalization-design.md` established |
  | Bundle | `bundles.name` via `gamekey` | |
  | Purchased | `bundles.purchased_at` | how long the key has sat |
  | Expires | `expiry_date` / `expiration_date`, `is_expired` as backstop | present on ~1 key in 5; blank otherwise |
  | Revealed? | `redeemed_key_val` present | the interesting row is revealed-but-unmatched |
  | Checkable? | does the key's store have an importer | see the third state below |

  Three limits belong in the report's own output, not just here:

  - **Only steam/gog/epic can be checked at all.** Those are the stores
    `import_games` covers, and about a twentieth of the keys are for
    stores with no importer — Uplay, Paizo, DriveThruRPG, Desura and a
    long tail below them. For those, "not in any library" is
    unfalsifiable. They are *unknown*, a third state, not unredeemed;
    collapsing them into the main list would make the report mostly
    noise. This is the same point the out-of-scope note on keys makes.
  - **Humble's redeemed flag means revealed, not activated** — already
    recorded under the keyed-ownership fix below. It says the key's value
    was displayed once, which is why library matching and not the flag is
    the primary signal.
  - **Title matching is fuzzy both ways.** A key can read as unredeemed
    because the store spells the game differently, and a coincidental
    match can hide a key that really is unclaimed. The report suggests
    where to look; it does not adjudicate.

  `num_days_until_expired` is non-zero on nearly every row and is
  therefore almost certainly a never-expires sentinel rather than a real
  deadline. Confirm that before any column trusts it.

- **Hiding a resolved row** — the owner asserting "wherever this one
  ended up, I know it is redeemed", so it stops reappearing. Follows the
  `dismissed_pairs` shape: `hidden_keys(machine_name TEXT PRIMARY KEY,
  hidden_at TEXT NOT NULL)`, idempotent hide and unhide routes, the main
  report excluding hidden rows behind a count, and a companion view
  listing them with `hidden_at` and an unhide control. Same columns in
  both views, so nothing is learned only by hiding it. Hiding stays
  viewer-only; the CLI subcommand gets a flag to include or show only
  hidden rows.

  Two deliberate departures from the `dismissed_pairs` precedent:

  - **Keyed on the tpk's own `machine_name`**, which every stored `raw`
    blob carries, rather than on `human_name` — the rebuild-stable
    identifier convention `user_item_data` follows. It needs either
    `json_extract` at query time or a `machine_name` column added to
    `external_keys`.
  - **Kept out of `DERIVED_TABLES`, so `reset` preserves it.** Dedupe
    dismissals can afford to be wiped because a rebuild re-derives the
    pairs and the owner re-judges them from data still on disk. A
    redeemed-key assertion is knowledge about what happened beyond this
    machine, which no rebuild can recover, so wiping it would refill
    with rows already resolved. The cost is the opposite failure: a hide
    can outlive the key it referred to, so the hidden view should mark
    rows whose key no longer exists rather than dropping them silently.
    `backup.py` copies the whole database file, so no backup work is
    needed either way.

  Note the hide is per key, not per game: the same game keyed in two
  bundles stays two rows, because one may have landed and the other not.

### Harvest (identified 2026-07-26 while debugging resume)

Surfaced by investigating a harvest that appeared to restart from
scratch on every rerun. The two bugs behind that are fixed, and three
entries have since shipped - quota budgeting, the retry spend, and the
worklist order; these are what is left.

- **Shorten the google_books worklist** — it is fetched for every type,
  so its list is roughly twice the size of any other source's, which is
  why its small daily quota takes so many days to work through. Dropping
  it from a type's `SOURCE_ORDER` would fix that, but it changes which
  candidates every affected item can ever match against, so it is a
  matching-quality decision and wants its own measurement. Split out of
  the quota-budget entry (now shipped) precisely so the two effects stay
  measurable apart.
- **A rate-limited source still walks its whole list** — after the
  quota dies the pool keeps going so cached titles still count, which
  is the point, but it does so with one cache lookup per remaining
  title. Cheap per title and correct; worth revisiting only if the
  catalog grows enough for the walk itself to be noticeable.

### Other

- **Standalone Android viewer app** — a read-only catalog viewer for
  phone use. Referenced as a "separately recorded gap" in
  `specs/2026-07-18-android-apk-items-design.md`; this entry is that
  record.
- **Goodreads ratings** — enrichment source, blocked on Goodreads
  reopening an official API (deferred from v1,
  `specs/2026-07-17-humblebundle-catalog-design.md`).

## Explicitly out of scope (decided against, not merely postponed)

- Downloading the actual book/audio files — the catalog links to them.
- Desktop game downloads and Steam/GOG keys as catalog items — keys
  stay in `external_keys`. Still true after the bundle preview began
  *reading* that table for ownership: it matches against keys, it does not
  promote them to `items` rows. The unredeemed key report under **Open**
  is the same bargain — reporting on keys is in scope, and a report is not
  a promotion.
- Game-metadata enrichment sources (Google Play/IGDB) for Android
  items — Humble's own data is all we store.
- Tracking non-book HumbleBundle purchases beyond the above.
- Any cloud/hosted component — everything runs locally.
- **Ordering the harvest worklist by newest purchase first** — measured
  2026-07-30 and rejected, not postponed. It looks like the right answer
  under a starved quota, but order only decides anything while the
  uncached remainder exceeds the daily budget: a cache hit costs no
  request, so if every uncached title fits in one day's quota they are all
  fetched today whatever position they hold. At ~2,300 eligible items and
  ~1,000 requests/day that window is days wide and closing, and reopening
  it would need one day's purchases to leave more than ~1,000 titles
  uncached when the largest bundle in the catalog is ~150 items. It is
  also a *superset* of the shipped sort rather than an alternative:
  `purchased_at` lives on `bundles`, so a large bundle gives up to ~150
  identical keys and a content tiebreak is needed underneath it anyway.
  Its two edge cases — a bundle with no date, an item in no bundle — exist
  nowhere in the catalog, so they would be defensive branches no test
  could exercise. Revisit only if the quota tightens or a single day's
  purchases can outrun a day's budget.

## Done (formerly on this list)

- **A game held only as a Humble key read as new** — fixed 2026-07-30 (no
  spec; a bug found by using the feature). `preview` decided game ownership
  from two pools, `items`+`merges` by machine_name and the `games` table
  from imported store libraries, and never looked at `external_keys` — where
  `harvest` files the store keys from past orders. A game bought in an
  earlier bundle is therefore invisible until its key is not just revealed
  but *activated* into a library the importer reads, so the report told the
  owner to buy something already paid for. Found on a live bundle every one
  of whose games came from a single past order: all but one had been
  activated on Steam and matched, and the one that had not was reported as
  the bundle's sole new item. Not an edge case — a third of the distinct
  keyed titles in the catalog are in no imported library.
  `_keyed_games` is consulted only *after* the libraries have returned
  "new", and only an outright `owned` verdict is honoured. Both halves
  matter: library-first keeps a keyed-and-activated game reporting as the
  plain library match it is, so the keyed list stays a short list of
  caveats rather than most of the library, and refusing a keyed `possible`
  avoids stacking one fuzzy guess on another.
  **Expired keys count as owned.** 111 rows carry `is_expired`, and `raw`
  could filter them; it deliberately does not. The report answers "should I
  buy this", and having already paid once is that answer whether or not the
  key can still be claimed — excluding them pushes toward a second
  purchase, the more expensive of the two available mistakes.
  The heading says "not in any imported library", never "unredeemed": Humble
  marks a key redeemed the moment its value is *revealed*, which says
  nothing about whether the game reached a store account. The key that
  started this reads as redeemed, so "unredeemed" would have been false on
  the very case the feature exists for.
  The `unimported_stores` warning was corrected in the same breath (2026-07-30,
  a follow-up commit). It was fed by every store the bundle delivered on, and
  claimed "its items are counted as new by default" — which keys made false in
  both halves at once. It now collects only stores that still hold an item with
  a `new` verdict, and says "its unmatched items". A `possible` verdict does not
  feed it either: that item was not counted as new. This matters most for the
  stores with no importer at all, where a key is the only evidence there will
  ever be: a warning that fires when everything is in fact owned is the kind
  that teaches an owner to ignore the warning that isn't.

- **Worklist order is guaranteed, not incidental** —
  `docs/superpowers/specs/2026-07-30-harvest-worklist-order-design.md`.
  `build_worklist` sorts each source's list by `(casefold, raw)`, so the
  order is a pure function of the item set instead of a property of an
  `ORDER BY`-less `SELECT` that SQLite happened to answer in insertion
  order. Sorting the finished lists rather than adding `ORDER BY`, because
  the lists hold *cleaned* titles: `clean_title` strips edition suffixes
  and trailing parentheticals, so a SQL order would still be one
  derivation away from what the list contains, and the guarantee would
  still rest on the query plan.
  The second key element is the whole subtlety. Python's sort is stable, so
  `key=str.casefold` alone would break a case-only tie by falling back to
  the unordered scan — the bug surviving inside its own fix, narrowed to
  case-differing pairs, which `clean_title` makes reachable because it
  preserves case. `test_worklist_order_breaks_case_ties_by_content` seeds
  the pair in both orders and demands the same answer, which is exactly the
  assertion `casefold` alone fails; before the fix it failed on
  `forwards == backwards` rather than on the expected value.
  Accents stay unfolded: determinism is the property wanted and codepoint
  order has it, and an accent misplaces a title only when it is the
  deciding character. `static/fuzzy.js` does fold accents, because there it
  is load-bearing and must keep an index map back to the original string;
  nobody searches the worklist.
  Framed by measurement as a **tidiness fix, not a performance one**, which
  is the opposite of how it first read. Order chooses which titles a
  rate-limited source enriches today only while the uncached remainder
  exceeds the daily quota — a cache hit costs no request — and at ~1,750
  uncached google_books titles against ~1,000/day that window was days
  wide and closing. The same measurement moved newest-purchase-first from
  a deferral to the decided-against list.

- **Retries spend quota, and google_books is where that hurts** — fixed
  2026-07-26 in `82d178b` (no spec; a one-source policy change).
  `_with_retries` retried 5xx twice more and every attempt costs a quota
  unit, so Google's frequent `503 backendFailed` made the median title cost
  two to three requests out of 1,000/day against a ~2,300-title worklist —
  roughly half the day's allowance spent re-asking questions that had
  already failed. A new `Source.retry_server_errors` gates it, so the
  policy lives in the source that has the constraint rather than in the
  shared retry helper.
  Connection errors and timeouts keep retrying everywhere, deliberately: a
  5xx came from Google and was almost certainly counted, while a connection
  error may never have reached the quota system at all. A skipped title is
  not lost — it stays uncached, so the next run has it at the head of the
  queue, trading same-run recovery for twice as many titles per day, which
  is the right way round for a source that needs several days regardless.
  The diagnosis came from cache timings rather than from any error log: 302
  rows over 85.5 minutes gave a median gap of 7.6s where the 2.0s throttle
  plus ~0.6s latency predicts 2.6s — one 5s backoff on the *median*
  request. The entry was left on the Open list by mistake and is recorded
  here on 2026-07-30.

- **Quota budgeting across harvest runs** —
  `docs/superpowers/specs/2026-07-26-harvest-quota-budget-design.md`.
  A 429 is now recorded in a new `source_quota` table together with when
  the limit is expected to lift, so the next `harvest` serves that source
  from cache without spending the one request that rediscovers a wall the
  previous run already proved. That request is the whole cost being
  removed: `_with_retries` already treats 429 as terminal rather than
  retryable, so rediscovery was never three requests — but it was one out
  of a quota whose scarcity is the entire problem.
  The source is walked cache-only rather than skipped outright, which the
  entry's own wording asked for. The walk is what keeps the progress
  number true: a 90%-cached source still reports 90% on a blocked run,
  where skipping it would report nothing and the number would appear to go
  backwards between runs. It costs one indexed cache lookup per title.
  The reset time is *derived*, never read off the response — Google states
  no reset field, and a generic "24 hours later" would place it up to a
  whole day past the real one and waste that day's quota. So the policy is
  a `Source.quota_resets_at` method, defaulting to a deliberately short
  one hour (a per-minute limit must not sit out a day) and overridden only
  in `google_books.py`, which is the single file that knows Google's
  window is daily. Pacific is a fixed UTC-8 rather than `zoneinfo`, since
  `ZoneInfo` needs `tzdata` on Windows and the project has no date
  dependency; the resulting hour of DST lateness is the safe direction,
  because waiting costs nothing and retrying early spends the request.
  It also sidesteps the `replace()`-on-a-DST-zone trap for free.
  A paused source is neither done nor failed, which is exactly the
  ambiguity `HarvestProgress`'s marks exist to resolve — and without a
  fourth state it would have read as **done**, since a cache-only walk
  raises `CacheMiss` and `CacheMiss` is not a failure. `finish` names
  paused sources on their own line rather than letting them inherit
  "rerun 'harvest' to resume", which is wrong advice for a source that
  will 429 again immediately. One rule decides it — a live record at the
  end of the run — so a source blocked before the threads started and one
  blocked by its own first 429 cannot report differently.
  Two recoveries for a wrong guess: `harvest --ignore-quota`, and any
  successful request clearing its own record in the same transaction as
  the cache insert. `check` deliberately clears nothing, because it runs
  on `:memory:` so the cache cannot fake a success.
  `progress._duration` became public on the way, having acquired a second
  caller — as `stats._console_safe` did.

- **Bundle preview** —
  `docs/superpowers/specs/2026-07-25-bundle-preview-design.md`.
  Point `bundle <url>` (or the viewer's panel) at a live HumbleBundle
  page and get, per tier, how many items it holds, how many are already
  owned, and how many would be new. Ownership is an exact set
  intersection rather than a heuristic: the page embeds its contents as
  JSON keyed by the same `machine_name` `parse_order` already stores, so
  a re-run bundle reads exactly — measured 21 of 23 items on one. The
  owned set unions `merges.dropped_machine_name`, since a duplicate
  merged away still names a book in the library and omitting it would
  report an owned item as new, which is the one direction of error a
  buy/don't-buy tool must never make. Tiers are cumulative in the source
  data, so "new at this tier" is one set difference; they sort on the
  numeric price, never `tier_order`, which was observed descending but is
  documented nowhere. Read-only, no persistence, and no Humble login —
  the page is public.
  The overlap list is the design's real content. A different publisher's
  bundle had **zero** `machine_name` hits while nine of its titles
  plainly related to owned rows, every one of them the same shape: the
  bundle sells an omnibus, the catalog holds one volume. That has no
  correct automatic answer, so it is neither counted as owned nor
  silently ignored but listed separately and labelled a suspicion —
  `owned`/`new` stay exact-id facts, and the two are never summed. Its
  threshold is a local 0.90, not `matching.REVIEW`: measurement showed
  0.60 and 0.75 both admit unrelated titles that merely share a volume
  suffix, while 0.90 caught exactly the genuine pairs.
  Three things only showed up in the doing. `url_import._read_capped`
  needed an optional limit — its 2 MiB default was sized for OpenGraph
  tags, which live in `<head>`, whereas a bundle page carries its blob
  about three-quarters of the way down (offset ~477 KB of ~656 KB), and a
  silent truncation there would have surfaced as the confusing "not a
  Humble bundle page". An unencodable currency symbol falls back to the
  ISO code rather than to `console_safe`'s replacement character, since
  "?21.90" reads as a broken price where "EUR 21.90" reads as a price —
  and the codepage that matters is cp437/cp850, the Windows *console*
  default, not cp1252, which does carry the euro. And a one-item tier
  read "1 items", which no test caught and a browser did.
  `stats._console_safe` became public on the way, having acquired a
  second caller in another module.
  Extended 2026-07-25 with the per-tier list of what you would gain
  (`specs/2026-07-25-bundle-preview-new-items-design.md`). `new_items`
  shipped machine_names no consumer rendered and is replaced by `adds`,
  display names of what each tier unlocks *over every cheaper tier* —
  tiers being cumulative, a full list per tier would print the same title
  once per tier. Computed against a running set rather than a difference
  against the next tier down, so a bonus tier that is not a strict
  superset cannot silently emit a title twice. The `new` count stays
  cumulative while the list is incremental; they disagree on every tier
  but the cheapest, which is why each list names its own price and count.
  Owned items stay unlisted — `new` is shortest exactly when the decision
  is hardest.
  The viewer layout was reversed by measurement. The spec put each list
  in a row directly beneath its own tier row, which reads better on paper
  and failed in a browser: eight titles between the first two prices
  pushed the cheapest tier ~500px down, so the three numbers the panel
  exists to compare never shared a screen (537px of content in a 229px
  panel). The table now stays whole at the top and the lists follow.
  Adding `#bundle-panel` to the shared `max-height: 50%` rule — a latent
  bug in the shipped panel — did *not* fix that on its own, because the
  fault was ordering rather than height; the lists also went multi-column
  (`columns: 18rem`), which took 25 titles from 500px to 140px.
  One bug fixed on the way out, in the test harness rather than the app:
  `js_harness.eval_js` ran Node with `text=True` and no encoding, so
  Python decoded UTF-8 output with the Windows locale codepage and a euro
  sign came back as its own trailing byte. No JS test had ever asserted
  on non-ASCII, so nothing had caught it.

- **`backup` command** —
  `docs/superpowers/specs/2026-07-25-backup-restore-design.md`.
  `backup` writes a timestamped snapshot of `catalog.db` to a gitignored
  `backups/` (or a directory you name), through SQLite's online backup
  API rather than a file copy — under WAL a copy of the main file alone
  can silently miss commits still resident in the `-wal`. `restore` puts
  one back behind a typed `RESTORE`, snapshotting the current catalog
  first and swapping with `os.replace`, which refuses while the viewer
  holds the file open where an in-place write would corrupt it. Covers
  are opt-in on both sides, as a stored zip: measured ~3x faster than
  copying ~2500 small files, and one artifact rather than thousands.
  Deliberately no retention policy — a backup command that deletes
  catalog data can destroy what it exists to protect.

- **Statistics / overview panel** —
  `docs/superpowers/specs/2026-07-24-statistics-panel-design.md`.
  One collapsible panel with six sections — type, ratings, reading
  status, enrichment, gaps, genres — replacing the separate gaps and
  genre panels so each number lives in exactly one place. Counts always
  cover the whole catalog, never the filtered set, which is what makes
  click-through unambiguous: a row's count is what you see after the jump.
  The counting lives only in `stats.py` and reaches the viewer over a new
  `GET /api/stats`, so the CLI and the panel cannot drift; `gaps` widened
  into `stats`. Deriving in the browser was the first plan and was
  reversed by measurement — only two mutations skip the existing
  `await load()`, so keeping a server-computed panel fresh cost two call
  sites, while a full `/api/items` refetch would have cost 1.3 MiB per
  star click. Both keep their optimistic render and refresh the panel
  after it, so the panel trails the table by one round trip on purpose.
  Ratings covers ★1–★5 only, since unrated is already a gap. Genre
  management survives behind an Edit tags toggle, and the genre block now
  sorts by count rather than alphabetically.
  Three things only showed up in the doing. Printing the report crashed
  on a real console — the Windows default is cp1252, which cannot encode
  the star in the rating labels, and `capsys` captures as UTF-8 so no
  test could see it; `run()` now degrades the shared labels at the CLI
  boundary rather than dulling them for the web panel too. A row reading
  "Unmatched 4" jumped to `#f-flag=review`, which spans low_confidence as
  well and returned 8, so each enrichment state gained a flag named for
  itself (the union stays — "what needs my attention" is its own
  question). And the jump counts were `<button>`s left unstyled, so they
  kept the browser's grey default and glared on the dark panel; they read
  as links via `var(--accent)` now. The last two were invisible to the JS
  harness, whose stubbed DOM has no computed styles and never compares a
  promised count against the rows actually shown.
  Measuring the endpoint also exposed a pre-existing quadratic:
  `downloads` had no index on `item_id`, so `fetch_items` scanned it once
  per item — 701 ms at 5000 items, 152 ms with the index
  (`user_version` 6), which every `load()`, export and CLI run pays too.

- **Reading status** —
  `docs/superpowers/specs/2026-07-24-reading-status-design.md`.
  A first-class five-state reading status (want_to_read / unread / reading /
  read / dnf) on `items`, default unread. A user-owned field like
  my_rating/user_tags/user_comment: outside `EDITABLE_FIELDS` and
  `pre_edit`, independent of the rating, and preserved across reset via the
  `user_item_data` snapshot (restored with `COALESCE(?, 'unread')` so a
  pre-status snapshot cannot violate the NOT NULL column). Set per-row in
  the viewer with a `<select>`, filtered by an any-of chip set, sorted by
  lifecycle order rather than alphabetically, and exported as a labelled
  20th column. The `CHECK` constraint ships on fresh DBs; migrated DBs
  (SQLite `ADD COLUMN` cannot attach it) rely on route validation for the
  same value set.

- **Catalog reset & offline rebuild** —
  `superpowers/specs/2026-07-24-catalog-reset-rebuild-design.md`.
  A `reset` command wipes the derived catalog so a parser fix can be
  re-applied from scratch, without re-downloading. The schema splits into
  a preserved layer — the two download caches (`raw_orders`,
  `source_cache`), the `covers/` files, and a new `user_item_data`
  snapshot — and a derived layer that is a pure function of it; reset
  deletes the latter in FK-safe order and keeps the former. Owner
  ratings/tags/comments survive via snapshot-and-restore keyed by
  `machine_name`: reset copies them into `user_item_data`, and
  `store_order` restores them when it re-creates an item, but only on the
  insert branch, so a normal re-run never clobbers a live edit with a
  stale snapshot. Hand edits, type overrides, and merges are deliberately
  not preserved.
  Covers were re-keyed from `covers/{id}.jpg` to
  `covers/{slug}-{blake2b12}.jpg`: the item id is regenerated on every
  rebuild, so an id-keyed file would orphan, whereas `machine_name` is
  stable — which lets a rebuild re-link existing files offline instead of
  re-fetching them. blake2b over SHA-1 because the digest is
  non-adversarial but must not trip FIPS mode or a security scan; the
  12-hex suffix also keeps Windows case-collisions and reserved names
  (`con`, `nul`) from ever producing a bad filename. A one-time
  `user_version` 3→4 migration renames legacy cover files, guarded to
  tolerate partial `items` tables. Gated behind a typed `RESET` with no
  `--yes`, and EOF at the prompt aborts cleanly rather than tracebacking.

- **Selected-columns export** —
  `superpowers/specs/2026-07-20-selected-columns-export-design.md`.
  Both the viewer and the CLI can now narrow the exported columns: a
  `<details>` panel of checkboxes beside the download button, persisted
  to `localStorage` like the theme, and `--columns title,authors` on the
  command line. The mirror image of filter-aware export, and the two
  axes stay independent — `_select` owns the rows, the new `_columns`
  owns the columns, and neither consults the other.
  `_columns` forces canonical order, which makes one comprehension the
  validator, the de-duplicator and the ordering policy at once. That is
  deliberately the *opposite* rule from rows, where the caller owns the
  order: on-screen row order is something the user built with sorting
  and relevance ranking, so it carries information, whereas nobody drags
  the checkboxes. Unknown names are likewise handled asymmetrically —
  dropped silently on the web route, fatal on the CLI — because stored
  browser state can outlive a `COLUMNS` rename by months whereas a typo
  on a command line is a mistake being made right now.
  Two things only showed up in the doing. `_style()` located the date
  column with `COLUMNS.index("first_purchased")`, correct exactly as
  long as `COLUMNS` was the whole truth, so it now looks the name up in
  the columns actually being written. And the picker closed itself
  whenever a checkbox was clicked: `toggleColumn` re-rendered the list,
  detaching the clicked box, so the dismiss handler measured
  `contains()` against a node no longer in the document. It redraws only
  the count now. That one was invisible to the JS harness, whose stubbed
  DOM cannot model detachment, and was caught in a real browser.
- **XLSX output** —
  `superpowers/specs/2026-07-20-xlsx-export-design.md`.
  The export is offered as a styled workbook alongside the CSV: frozen
  bold header, autofilter, ISO date display and widths computed from the
  data and capped at 60. Framed as a *working surface* rather than an
  interchange format, which is what decided the styling question.
  Cheaper than expected, because the schema already stores the ratings
  numerically and `_row` never stringified them — `csv.writer` did, on
  the way out — so typed, sortable cells came for free. The one type
  genuinely lost was `first_purchased`; `_row` now yields a
  `datetime.date`, and the CSV stayed byte-identical because
  `csv.writer` calls `str()` on non-strings and `str(date(2019, 3, 2))`
  is exactly the old string slice. That implicit coercion is the seam a
  future bug lives in, so it is pinned by
  `test_first_purchased_is_a_date_that_csv_stringifies`.
  `_select()` was extracted first: the caller-owns-order and
  skip-unknown-ids policy from filter-aware export could not survive
  being copied into a second writer. Two consequences went beyond the
  format itself — openpyxl refuses control characters SQLite and `csv`
  accept, so a scraped comment could have `500`ed the workbook while the
  CSV of the same row succeeded (stripped silently now, but tab, newline
  and carriage return are legal and survive), and the viewer's button
  lost `CSV` from its label, since the button reports what rows and the
  select reports what format. The CLI takes the format from the path
  suffix, with an unknown suffix now an error — it used to write a CSV
  to whatever name you gave it, so `export catalog.txt` produced a
  mislabelled file. No new dependency: `openpyxl` was already there to
  *read* the reference spreadsheets.
  Selected-columns export stays behind as its own entry.

- **Filter-aware export** —
  `superpowers/specs/2026-07-20-filter-aware-export-design.md`.
  The viewer's export now sends the rows it is showing, as an ordered id
  list, and `write_csv` grew one optional argument to honour it — one CSV
  writer, two row sources, so the CSV spec's "no divergence possible"
  survived. The row set could not be recomputed server-side: `visible()`
  owns fuzzy scoring, eight chip filters and the sort mode, so the
  browser is the only thing that knows the answer. Ids travel in a POST
  body rather than a query string because a list of item ids describes
  the library and query strings reach access logs and history — the
  privacy standing order ruled out the conventional answer. Two
  consequences: with ids the *caller* owns row order, which is the one
  thing `write_csv` must never quietly re-sort (pinned by
  `test_ids_are_written_in_the_callers_order`), and `bulkTarget()` became
  `shownRows()` once "the rows on screen" stopped being a bulk-tagging
  idea. `GET /api/export.csv` stays although the viewer no longer calls
  it — it is the whole catalog at a plain URL, for a bookmark or a
  script, and the tests' full-export regression guard.
  Selected-columns export stayed behind as its own entry.

- **Enrichment override for hand-edited rows** —
  `superpowers/specs/2026-07-20-enrichment-override-design.md`.
  The work was mostly splitting one overloaded column: `pre_edit` had
  been both the revert baseline and the enrichment lock, so "edited" was
  derived from it. `hand_edited` now carries authorship and `pre_edit`
  means only "what Revert returns you to", which lets a row reopen to
  enrichment without discarding its revert target. A one-shot `enrich_override`
  widens `run()`'s selection; the row is queued from the viewer per row
  or catalog-wide via `enrich --override-edited`, gated behind a typed
  OVERRIDE with no `--yes`.
  Only a confident match is ever applied — `low_confidence`, `unmatched`
  and source errors leave the row completely untouched and merely clear
  the flag, so a failed re-match can never cost a hand edit. That
  asymmetry is pinned by
  `test_override_without_a_match_changes_nothing_but_the_flag`.
  Two consequences went wider than the spec. `apply_candidate` now
  re-snapshots the typed values for every caller, so approving a Review
  candidate on a hand-edited row became revertible — it silently
  discarded the edit before. And `revert` had to *flip* `hand_edited`
  rather than set it: `pre_edit` always holds the other author's values,
  so reverting a hand edit shows enriched data again while reverting a
  re-enriched row hands the edit back. Setting it would have branded
  machine values as a hand edit and locked the row out of
  `--reset-reviews` forever; an existing test caught it.
  Named "override"/"queued" in the code and UI, not the spec's "armed":
  the viewer already used `armOrFire`'s armed state for two-click
  confirmation.

- **Annotation flags** —
  `superpowers/specs/2026-07-20-annotation-flags-design.md`.
  Shipped as two `#f-flag` options rather than the one the entry
  described: "Has notes" and "Has my tags". A note and a tag are
  different acts, and one merged flag would hide which of them a row
  actually has. They answer the membership question — *what have I
  annotated at all?* — that neither the notes text filter nor the
  user-tag chip filter can, since an empty query in either matches
  everything. Presence only; the symmetric absence flags stay unbuilt
  until missed. The dropdown is single-select, so the two cannot
  combine — accepted, since no flag combines with another today.

- **Fuzzy search matching** —
  `superpowers/specs/2026-07-20-fuzzy-search-design.md`.
  `#search` now tolerates wrong word order, skipped words, typos,
  accents, apostrophes and initials, via a tiered scorer in a new
  dependency-free `static/fuzzy.js`. Three tiers — exact substring,
  token set, acronym — occupy non-overlapping score bands, so any exact
  match still outranks any fuzzy one and nothing that worked before
  dropped in rank; the tolerance is one policy number (a 0.40 cutoff)
  rather than a set of tuned weights. Folding is hand-rolled to keep an
  index map back to the original string, because collapsing punctuation
  and eliding apostrophes change the string's length and every
  highlight span past such a character would otherwise be displaced.
  Apostrophes elide rather than space, so a typed "innkeepers" matches
  the punctuated spelling. Results order by score while a query is
  active, with the count line saying so and the column arrows
  suppressed, since leaving one lit would misreport the order on
  screen. Two bugs the case table caught: bidirectional prefix matching
  had no length floor, so a one-letter title token matched every query
  starting with that letter well enough to clear the cutoff on its own;
  and scores needed rounding, because `0.45 + 0.40` is
  `0.8500000000000001` and read as outside its own band.

- **Viewer favicon** —
  `superpowers/specs/2026-07-20-favicon-design.md`.
  An original book-spine mark: three spines on a 64×64 grid, two upright
  and one tipping over at the end of the shelf. Ships as a theme-aware
  `favicon.svg` carrying its own `prefers-color-scheme` block — a favicon
  renders outside the page's CSS cascade, so it cannot reuse the app's
  custom properties — plus a `favicon-32.png` fallback whose single
  palette has to clear both a white and a dark tab strip. Generated by
  `scripts/make_favicon.py` using only `zlib` and `struct`, rather than
  adding an imaging dependency for one icon; output is committed and a
  test fails if it drifts from the table. The green/red/purple palette
  was picked by measuring CIE Lab ΔE under simulated colour-vision
  deficiency: purple replaces the blue, because purple placed *between*
  red and blue collapses under tritanopia.

- **Viewer visual improvements** —
  `superpowers/specs/2026-07-19-viewer-visual-improvements-design.md`.
  A light/dark theme (every colour hoisted to CSS custom properties,
  `prefers-color-scheme` for the default, a persisted `data-theme`
  toggle to override it, applied pre-paint so there is no flash), and
  `<details>` collapse for the Review and Duplicates panels — collapsed
  by default, with the count in the summary so a closed panel still
  signals pending work. Both reuse the `genresOpen` pattern: a module
  flag written into each render, since the panels are rebuilt via
  `innerHTML`. Shipped wider than the spec: sorting turned out to be
  the real "hard to scan" complaint — it already worked but was
  invisible, so the active column now carries a `▲`/`▼` indicator, and
  Narrator and Bundle became sortable. Bundle needed a `sortValue()`
  indirection: there is no scalar `item.bundle`, only `bundles[]`, so
  the old `item[sortKey]` comparator would have silently sorted
  nothing. Narrator sorts on `person()` so it follows the column's
  narrator‖illustrator either/or. Also zebra rows, a sticky table
  header offset by the live header height, a roomier grouped filter
  bar, themed form controls (unstyled inputs had kept the browser's
  white default, which glared in dark mode), horizontal scroll
  contained to the table, and the autocomplete popup freed from the
  scroll container's clipping.
- **Enrichment harvest/match split** — parallel `harvest` (per-source
  thread pools) + local re-runnable `enrich` + `--credits` top-up, so
  repeat full runs (hours) become cache replays (seconds).
  `superpowers/specs/2026-07-19-enrichment-harvest-match-split-design.md`.
- **Android APK items** — v1.5, `specs/2026-07-18-android-apk-items-design.md`.
- **CSV export** — `specs/2026-07-18-csv-export-design.md`.
- **Spreadsheet ratings & metadata import** — v1.6,
  `specs/2026-07-18-ratings-import-design.md`.
- **Cross-bundle dedupe** — v1.7,
  `specs/2026-07-18-cross-bundle-dedupe-design.md`.
- **Multi-tag filtering** — v1.8,
  `specs/2026-07-18-multi-tag-filtering-design.md`.
- **Genre tag case normalization** — v1.9,
  `specs/2026-07-18-genre-case-normalization-design.md`.
- **Genre tag management (rename/merge/delete)** — v1.10,
  `specs/2026-07-19-tag-management-design.md`.
- **Tag counts in autocomplete dropdowns** — v1.11,
  `specs/2026-07-19-autocomplete-tag-counts-design.md`.
- **Autocomplete filters for authors/narrator/series** — v1.12,
  `specs/2026-07-19-authors-series-filters-design.md`. Shipped wider
  than the spec: also publisher, a Narrator/Artist filter spanning
  narrator+illustrator, title suggestions in the search box, and the
  search box narrowed to names only now that every other field it
  used to span has its own filter.
- **Comic credits never fetched (illustrator always empty)** — fixed
  2026-07-19. `ComicVine.credits()` asked the *volume* endpoint for
  `person_credits`, a field only *issue* records have; Comic Vine
  answers that with error "OK" and an empty result, so every
  comicvine-matched comic silently got no illustrator **and no
  authors**. Credits now come from the volume's first issue, whose
  URL the search response already carries (no extra API budget).
  `url_import` had the same bug for pasted `/4050-` volume URLs.
  The old unit test passed throughout because it mocked an
  issue-shaped payload for a volume request.
- **Link-only fallback for manually pasted URLs** —
  `specs/2026-07-19-link-only-url-fallback-design.md`. A generic
  OpenGraph scrape now covers any host without an API handler, and a
  page that still yields nothing becomes a confirmed link-only
  candidate rather than a failed review. The retry policy moved out of
  `Source.get_json` so both paths share it; 403 bot walls fall through
  immediately instead of waiting out retries that cannot succeed.
- **Bulk tagging** — `specs/2026-07-19-bulk-tagging-design.md`. Add or
  remove a user tag across every item the filters are showing. No
  checkbox column: `visible()` already computes the set, and the table
  on screen previews the blast radius. Removal is gated behind an active
  filter, since `user_tags` has no `pre_edit` snapshot to revert from.
- **Search comment text** — `specs/2026-07-19-notes-filter-design.md`.
  `user_comment` got its own text filter rather than a wider `#search`,
  which v1.12 deliberately narrowed to names only. One registry entry,
  one input, and a `textOnly` flag so the free-text field skips the chip
  autocomplete that suits a vocabulary.
- **Filter by user tags** — chip filter over `user_tags`, alongside the
  genre/authors/narrator/publisher/bundle filters. Genre and user tags
  are two **independent** pools, never one combined pool: a genre
  "Fantasy" and a personal tag "fantasy" mean different things and stay
  separately selectable. Cost was exactly what the registry design
  promised — one `chipFilters` entry plus one input in `index.html` —
  with autocomplete, tag counts, chips, and the all/any toggle all
  falling out of the existing wiring loops.
- **User tags and comments** —
  `specs/2026-07-19-user-tags-and-comments-design.md`. Two user-owned
  columns on `items`: `user_tags` (a managed tag vocabulary like genre,
  but never titleized) and `user_comment`. Both sit outside
  `EDITABLE_FIELDS` and `pre_edit`, so filling them is not a hand edit
  and never locks the row for enrichment. The genre tag machinery was
  extracted over a `TagColumn` descriptor first, so both columns share
  one implementation. `merge_items` unions `user_tags` rather than
  fill-if-empty, since a merge is irreversible. One latent bug fixed on
  the way: the viewer posted `/edit` on every save, so a note-only save
  would have marked the row edited — saving now compares the form
  against the item first.
- **Set an item's URL through a manual row edit** —
  `specs/2026-07-19-manual-source-url-edit-design.md`. `source_url`
  joined `EDITABLE_FIELDS`, so it is typed, corrected, or cleared like
  any other field and counts as a hand edit. Revert was fixed first: it
  restored every current field from the `pre_edit` snapshot, so a key
  written before the field existed read as null and would have wiped
  live URLs. The item name is no longer the anchor — a trailing `↗`
  carries the link.
