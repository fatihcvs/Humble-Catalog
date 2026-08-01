# Backlog

Postponed features and ideas, consolidated from the design docs' "future
extensions" / "out of scope" sections. When an item ships, move it to the
**Done** list at the bottom with its version. When a new design doc defers
something, record it here so the deferral has a home.

Last updated: 2026-08-01.

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

Entries under **Next up** are taken before the rest. Everything below
that heading is unordered — most of it is parked on data or on an
external change, so ordering it would be pretending. The two entries
here are neither: both are known defects with a known cause.

### Next up

1. **`load()`'s badge arithmetic is not inside its own guard** — found
   2026-08-01 while shipping the bulk-tag undo. `load()` runs its five
   panel loaders in a `try`/`catch` loop, added after one item with a
   missing field blanked the entire page. The `pending = {...}` badge
   computation immediately after that loop is *not* guarded, and it
   reads the module variables those loaders assign — `dupeGroups.length`
   and `reviewCount`. So a loader that throws before assigning its
   variable is caught and logged, and then `load()` throws anyway,
   defeating the containment the loop exists to provide. Observed with a
   malformed `/api/duplicates` response: the console showed
   `loadDupes() failed: TypeError: Cannot read properties of undefined
   (reading 'length')` and the error surfaced out of an unrelated caller
   (a bulk tag write), which is the part that makes it expensive — the
   report points nowhere near the cause. First: check how
   `badgeCount` in `shell.js` treats a missing count, since a badge
   silently reading zero for a section that failed to load is the wrong
   fix. Reachable in production by any malformed response.
2. **Thirteen buttons keep the browser's default styling in dark mode**
   — measured 2026-08-01 in a browser against `demo_catalog.py`:
   `sidebar-toggle`, `col-all`, `col-none`, `bulk-add`, `bulk-remove`,
   `bulk-undo`, `cand-btn`, `url-fetch`, `dupe-clear`, `dupe-keep`,
   `dupe-dismiss`, `bundle-go` all compute to `rgb(240, 240, 240)` with
   black text against a `rgb(22, 24, 28)` page, where every other button
   is themed to `rgb(30, 33, 39)` or deliberately transparent. Cosmetic,
   hence second, but it is the same defect the viewer visual
   improvements spec already fixed for inputs ("unstyled inputs had kept
   the browser's white default, which glared in dark mode") — these were
   missed. Widen whichever selector themes the working buttons rather
   than adding a rule per id, and check `#export`, which is transparent
   with accent text on purpose. Computed styles are invisible to the JS
   harness, so this is eyes-in-a-browser plus at most a text assertion
   that the rule exists.

### Bundle preview (deferred from `specs/2026-07-25-bundle-preview-design.md`)

- **Volume-range resolution** — parse an offered `Vol. 1-6` into a set
  of volumes, compare against the volumes actually owned, and report
  "you own 1 of 6" instead of listing the pair as a possible overlap.
  The most useful answer the feature could give and the most likely to
  be subtly wrong, since Humble's title conventions are not consistent.
  Revisit once the overlap list has shown how often ranges appear in
  practice.
- **GOG/Epic OAuth instead of Heroic's caches** (deferred from
  `specs/2026-07-25-game-library-ownership-design.md`) — talk to
  `auth.gog.com` and `galaxy-library.gog.com` directly rather than
  reading Heroic's on-disk JSON. Always fresh and drops the Heroic
  dependency, at the cost of a stored refresh token to a purchasing
  account and endpoint churn GOG has already made once. The importer
  boundary means this is a backend swap, not a rewrite: it would fill the
  same `games` table. Revisit if cache staleness or a Heroic format
  change actually bites.

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
- **Failure recording shipped as measurement only (2026-07-31)** —
  `source_failure` counts the runs in which each title failed. It exists
  to answer one question before any policy is written: are google_books'
  503s transient, or do the same titles fail every run? A title Google
  does not have returns 200 with `totalItems: 0` and is cached forever,
  so "missing from the index" is not the failure mode — only a
  non-response leaves nothing behind. A run on 2026-07-31 failed mostly
  on TTRPG supplements, comics and programming books, which share a
  query shape rather than a subject: long titles with internal colons,
  `#`, `+` and volume ranges, none of which `clean_title` strips. If a
  few runs show the same titles at a rising count, the fix is query
  normalization for this one source, not retry scheduling. If the counts
  stay at 1 and the titles keep changing, the 503s are load and nothing
  needs doing. See
  `specs/2026-07-31-harvest-failure-recording-design.md`.
- **Run tally shipped alongside it (2026-07-31)** — `harvest_run` records
  what each run cost per source: titles answered, live fetches, failures,
  and whether the budget died in that run. It measures the *rate* and
  whether the rate is moving; it does not decide the
  transient-versus-deterministic question, which `source_failure`
  answers. Built because two facts decay: `last_failed_at` is
  overwritten, so failures-per-run can be counted once and never again,
  and `quota.blocked` cannot separate a run that exhausted the budget
  from one that began with it already spent. Capped at the newest 500
  runs by `runs.record`; `harvest --forget-runs` clears it. See
  `specs/2026-07-31-harvest-run-tally-design.md`.
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
- **Past/expired bundles as a gap-finder** — running the preview against
  bundles that have closed, to see what was missed. Measured 2026-07-31
  and rejected for want of data, not for want of value: there is nowhere
  to get a closed bundle's contents from. Three probes, each closing one
  route.
  A closed bundle does **not** 404, which is what this entry used to
  claim, and it does not redirect either — `fetch_bundle`'s error text
  said "redirects to the storefront" and was wrong about the mechanism.
  It serves its own URL with its own `<title>` and ~530 KB of marketing
  shell, carrying `main-js`, `base-webpack-json-data` and
  `overpage-json-data` but not `webpack-bundle-page-data`. The blob the
  parser reads is not merely truncated; nothing of the bundle survives,
  down to the `machine_name`, so there is not even an id left to look
  the contents up by. The shipped parser is fine — four live bundles
  still carry the blob.
  The Wayback Machine does not have it. All 11 archived captures of one
  sampled closed book bundle top out at 43 KB against a live page's
  ~610 KB, including captures taken while it was still selling, and none
  contains the blob. A crawler gets the shell.
  And there is no JSON endpoint to ask instead: `/api/v1/bundle/<mn>`,
  `/bundle/<mn>`, `/api/v1/bundles/<mn>` and `/store/api/bundle/<mn>`
  all 404 even for a **live** bundle, given the `machine_name` read out
  of that bundle's own blob. The order API this project already uses
  answers for orders, which are purchases — the opposite of the set this
  entry wanted.
  So the data exists only while a bundle is selling, which makes any
  real gap-finder *prospective*: it would have to snapshot live bundles
  and report over the ones that later closed, answering nothing about
  the past and starting from the day it is first run. That is a
  different feature from the one this entry described, and it was not
  wanted enough to build. Reopens if Humble publishes bundle contents,
  or if an archive turns up that captured the blob rather than the
  shell — one grep for `webpack-bundle-page-data` settles either.

## Done (formerly on this list)

- **Undo for bulk tagging** —
  `docs/superpowers/specs/2026-08-01-bulk-tag-undo-design.md`.
  A bulk add or remove now leaves an Undo in the bulk bar naming the tag
  and the count, and firing it posts the inverse over exactly the rows
  that changed.
  The precondition was already there and unused: `bulk_user_tag` computed
  the changed set and returned only its size. Undoing over the ids the
  caller *sent* is the trap — bulk-add to 47 rows where 12 already carried
  the tag, undo by removing from all 47, and the tag is gone from 12 rows
  that had it beforehand. So the route answers `ids` and drops `changed`.
  Staleness needs no mechanism, which is unusual enough to record. Both
  inverse operations are per-item idempotent and the route already ignores
  unknown ids, so an undo fired after unrelated edits, or after a merge
  took some of its rows, quietly does the right thing. That is what made
  browser memory sufficient: a persisted slot would answer "undo something
  from last Tuesday", which the catalog moves underneath, and would drag
  in a `reset` decision for state that is derived but not rebuildable.
  **Scope was cut by a finding, not by taste.** The design first covered
  the catalog-wide `POST /api/user-tags/delete` too, on the strength of
  the statistics panel's tag management — which is genre-only. That route
  has no caller in the viewer or the CLI, so its undo could never have
  been reached, and `delete_tag`/`_rewrite_tags` were left alone rather
  than changed for a path no user can take. The finding widens the
  original entry rather than narrowing it: the escape hatch the bulk
  tagging spec offered for a bad bulk add is reachable by `curl` and by
  nothing else, so until now a mis-aimed bulk add had no in-app remedy at
  all. Wiring that UI is left as its own question.
  Built against **zero** user tags in the catalog, and the spec says so.
  Two questions that would normally be measured — whether case variants
  coexist, and whether array order carries meaning — have no data behind
  them and are settled by reasoning plus tests: the undo restores
  membership, not position, and collapses case variants to the spelling
  the operation was issued with.
  `armOrFire` returns the fired promise now. Every caller ignores it, but
  the JS harness stubs `setTimeout` to a no-op, so without it no test can
  wait for a two-click write to land — the arming idiom was untestable
  end to end.
  One bug only a browser found, the fourth of its kind on this list.
  `renderBulkBar()` writes `#bulk-note` unconditionally, so redrawing the
  button *after* writing the result replaced "Added to 12 of 13 items."
  with "Narrow the view to remove." the instant it appeared. Every JS test
  passed: they asserted on the slot and the label, and the stubbed DOM has
  no ordering to observe. Both writers redraw first and report second now,
  pinned by two tests that fail against the old order. The same run
  confirmed the asymmetry on live data — the demo catalog already carried
  the tag on one row, so the button offered 12 where 13 rows showed it.

- **The same work owned in two formats** —
  `docs/superpowers/specs/2026-07-31-edition-linking-design.md`.
  A row now says "also as audiobook" and jumps to it. `/api/merge` still
  refuses a cross-type merge, correctly; this is the relationship that
  refusal used to leave impossible.
  Measurement made the feature smaller, not larger. The entry reads like
  a matching problem and is not one: exact keys plus a trailing-marker
  strip find every genuine pair with nothing spurious, while
  `token_set_ratio` at the preview's own 0.90 cutoff found 9 pairs of
  which **8 were the subset artifact** — it returns 100 whenever one
  side's token set is a subset of the other's, so a one-word title
  scores perfectly against any longer title containing that word. Fuzzy
  matching is rejected here as *less accurate*, not as too slow, and no
  threshold appears anywhere in the feature. Same trap as the
  unsold-overlaps entry, reached from the opposite direction.
  The truth came from eyeballing the misses rather than the hits. The
  author gate — the strongest independent signal, populated on 101 of
  108 audiobooks — gave 70 same-author cross-type pairs, of which one
  had a matching title; reading the top three by hand showed all three
  genuine, scoring 100, 67 and 61. The scores were held down by suffixes
  `dedupe_key` does not strip. So the naive match was finding one pair
  in three, and the signal was never fuzziness — it was a suffix.
  **The type filter is the precision, not any score.** Admitting `music`
  costs six false positives to win two, because all five android/music
  groups are a game plus its own soundtrack — shipped together, not the
  same work twice. Widening to include `comic` was measured separately
  at 0 further groups across 988 comics and 0 false positives, so the
  type is admitted for a case the catalog does not yet hold, with a test
  rather than data behind it.
  The `classify.py` fix is load-bearing rather than co-located. Two
  items are genuine audio editions filed as `music` because the rule
  accepted only the literal word "audiobook"; a trailing `(audio)` now
  joins it, inside the existing platforms guard so no soundtrack can
  reach the branch. Without that fix, catching those two would mean
  admitting `music` and its six false positives — so fixing
  classification at the source is what buys the tight type filter. It
  took the population 4 → 6 of 2,729 items.
  Detection is live with no stored state, mirroring `dedupe.find_groups`
  — nothing to migrate, nothing for `reset` to preserve, and a rebuilt
  catalog has its links back for free. A stored link table was designed
  and declined: at six pairs it would mostly be a place for staleness to
  live. It reopens if a genuine pair appears that the exact key cannot
  see, which is the concrete trigger.
  Dismissal reuses `dismissed_pairs` on a disjointness argument —
  dedupe's pairs are always same-type and edition pairs always
  cross-type, so the key spaces cannot collide — and a test asserts that
  rather than assuming it. Nothing needs dismissing today.
  The siblings are attached in the `/api/items` route and not in
  `fetch_items`, which is shared with CSV and XLSX export: a link is a
  derived view, the export stays a serialization of stored facts, and a
  test asserts that boundary from the export side so tidying the
  computation inward fails rather than silently widening the export.
  The jump clears the type filter, which is the whole reason it is more
  than filling the search box — the sibling is by definition the type
  the filter is currently excluding, so leaving it set lands the jump on
  an empty table. Verified in a browser against a seeded catalog of
  invented titles, the JS harness having neither computed styles nor a
  filter to interact with.

- **`_overlaps` hinted about items no tier sells** —
  `docs/superpowers/specs/2026-07-31-bundle-preview-unsold-overlaps-design.md`.
  `preview` carried two notions of "the bundle's items" and `_overlaps`
  read the wrong one. Every count, the `adds` lists, `game_names` and
  `unmatched_stores` derive from `tier_display_data` — what a tier
  actually sells — while `_overlaps` iterated `tier_item_data`, the
  metadata dict, which also describes subproducts no tier lists. It was
  the only *iterating* reader of that dict; every other consumer reaches
  it by lookup, which is why nothing else was wrong and why nothing
  caught this. `tier_item_data` now has no iterating reader at all.
  **No count was ever wrong**, and a test pins that — the fix had to stay
  on the overlap list, which is the way it could have done damage.
  The open entry described a spare row. It was worse in two ways
  measurement found. `game_names` is accumulated *by the tier walk*, so
  a phantom is never in it and the `owned | game_names` exclusion was
  structurally incapable of naming one: a phantom carrying
  `platforms_and_oses` was scored against the **book** catalog, which is
  precisely the cross-media invention the call site's own comment says
  was fixed after being seen on a live bundle. The fix was complete for
  sold items and empty for unsold ones. `game_matching` is derived from
  the same walk, so that hint also printed with none of the "APPROXIMATE
  — verify anything you would buy on" warning that exists to qualify it:
  the least trustworthy hint in the report arrived with the least
  attached.
  And it is not a low-scoring curiosity. A subproduct whose title
  *contains* an owned one — "Shadow Hound Vol 1 Bonus Art Pack" — scores
  a perfect **100** under `token_set_ratio`, which returns 100 whenever
  one side's token set is a subset of the other's. Bonus packs, deluxe
  editions and art packs are exactly that shape, so the phantom sorts
  **above** both genuine overlaps. The 90.0 cutoff cannot help: the
  problem is not a weak score, it is the wrong question. That title is
  the fixture the three new tests use, chosen so a regression is the
  first line of the block rather than a row buried in it.
  The fix is to collect the candidates *in the tier walk*, which already
  decides both questions the two sets encoded, and hand `_overlaps` only
  that dict — it loses both filter parameters. A `sold` set filter was
  designed and rejected: two lines, provably result-preserving, and it
  would have left **three** exclusion rules assembled by the caller and
  re-applied by the callee, when the caller already had the answer as a
  by-product of work it had to do anyway. That arrangement is what
  produced the bug — `owned | game_names` was correct when written and
  became incomplete the moment a third exclusion was needed, because
  nothing about its shape said which items it was entitled to see. A
  fourth would have failed the same way. Same reasoning as the hidden-keys
  entry's chips partitioning by construction.
  A dict and not a set, deliberately: `_overlaps` sorts by score and
  Python's sort is stable, so tie order is input order, and set iteration
  order of strings varies between processes under hash randomization —
  the sort would have hidden that everywhere except on exact ties. Same
  trap the worklist-order entry documents. Tie order does change, from
  `tier_item_data`'s JSON order to the tier-walk order; both are
  deterministic and both come from the parsed page.
  One case decided and left alone: a name a tier sells that
  `tier_item_data` does not describe is skipped, preserving today's
  behaviour, so the collection is guarded on `name in items` rather than
  on the surrounding loop's `items.get(name) or {}`. The counts fall back
  to the bare `machine_name` there and are right to — counting must be
  exhaustive. Hinting must not be: `shadowhound_vol1_examplecomics`
  scored against real titles is a coin toss presented to a human as a
  suspicion, and the list's whole value is that its members are worth
  reading. Not observed live, and in neither fixture.
  `tests/fixtures/game_bundle_data.json` had carried a phantom all along
  — `bonuswallpaper_examplegames`, captured from a live bundle — and
  `test_game_titles_never_produce_book_overlap_hints` passed only because
  it scores 32.3 against the fixture catalog. It now passes for a
  structural reason instead.

- **Two locks over one connection in the harvest** — fixed 2026-07-31 (no
  spec; a bug the test suite coughed up once, in passing). Never on this
  list: it surfaced as a single `PytestUnhandledThreadExceptionWarning`
  during an unrelated `verify` run, on a suite that still passed 869/869.
  `_run_pool` writes `source_failure` and `source_quota` to the caller's
  connection under `lock`, and `HarvestProgress` writes `run_status` to
  **that same connection**, from those same worker threads, under a
  private `_lock` of its own. Two locks, each excluding only its own
  callers, is not mutual exclusion — and the invariant was already
  written down in `_run_pool`'s docstring ("the caller's connection, used
  under `lock`"). The implementation simply left one participant out.
  `check_same_thread=False` removes Python's guard against cross-thread
  use; it does not make a connection thread-safe. The reported symptom
  was the mild one. Reproduced 5/5 with four threads on one connection:
  `cannot commit - no transaction is active`, `bad parameter or other API
  misuse`, and a bare `SystemError: error return without exception set` —
  sqlite3's own module state being corrupted, not merely a transaction
  boundary being crossed.
  The first hypothesis was wrong and measurement caught it. A plain
  second `commit()` is a silent no-op, so "one thread's commit closed the
  other's transaction" cannot by itself raise anything — verified before
  any fix was written. The real mechanism is a check-then-act inside
  `Connection.commit()`: it tests `sqlite3_get_autocommit` and then
  issues `COMMIT`, releasing the GIL in between, so the other thread
  commits in the gap and the `COMMIT` finds nothing to commit.
  The fix is one lock, not a second mechanism: `HarvestProgress.lock` is
  public and the harvest takes it instead of making its own, because the
  lock guards the *connection* rather than the object that happens to
  hold it. It is an `RLock` deliberately — `prog.log()` takes it and is
  the obvious thing to call while already holding it, so a plain `Lock`
  would deadlock the first caller who nests rather than work. Nothing
  nests today.
  `LiveDisplay` keeps its own separate `_lock`, which is correct: that
  one guards the output stream, a different resource. `Progress`, the
  sequential class, is untouched — it commits on one thread. And
  everything after the joins (`quota.blocked`, `runs.record`,
  `prog.finish`) is main-thread only, so `finish` was never exposed.
  Pinned by `test_harvest_progress_writes_under_the_caller_s_lock`, which
  drives the real `tick` and `failures.record` rather than raw SQL — the
  bug was in which lock they took, not in what they wrote. It was checked
  against a *wrong* fix as well as the absent one: exposing a public lock
  that `tick` does not itself use still fails it, so the test pins the
  sharing and not the attribute.

- **`/api/keys` took ~2.5 s** —
  `docs/superpowers/specs/2026-07-31-key-report-matching-cost-design.md`.
  Now ~0.33 s. The entry proposed caching the store pools or memoizing
  the classification, and measurement rejected **both**: the pools cost
  6 ms of 2,400, and memoizing by title buys 19%, because the keys are
  nearly all distinct titles already — 1,840 of 2,125 steam keys. The
  obvious structural suspect, `classify_game` rebuilding its `names` list
  on every call, was worth 0.08 s of 2.20.
  The cost was that `token_sort_ratio` re-splits and re-sorts **both**
  sides' tokens on each of ~6.1M comparisons, and the pool's half of that
  is identical every time. `token_sort_ratio(a, b)` is
  `ratio(sort(a), sort(b))` by definition, so `prepare_pool` sorts each
  pool title once and `classify_game` scores with `fuzz.ratio`: the
  matching went 2.20 s → 0.27 s with **zero** verdict, title or score
  differences across every checkable key in the catalog. Not an
  approximation accepted for speed — the same function, evaluated in a
  better order.
  The sorted string is a scoring key and nothing else, which is the trap.
  `sequel_mismatch` decides on the **trailing** token, so on
  "ii quest widget" the numeral is no longer last, nothing is popped, and
  a sequel reports as `possible` against the game it is a sequel to
  rather than as `new` — failing open, silently, in the one direction
  this rule exists to prevent. `classify_game` indexes back through the
  index-parallel `Pool` to the unsorted entry before asking, and
  `test_game_match.py` is the module's first direct test precisely
  because that identity had nothing watching it.
  `bundle_preview` was converted too although it scores tens of items and
  was never slow, so the invariant is owned by `game_match` rather than
  stated in one caller and not the other.
  A report cache was designed as far as `PRAGMA data_version` and then
  declined, and the measurement is in the spec so the question reopens
  cheaply: four of the six writers of the tables the report reads are
  separate CLI processes — `import-games` being the one that actually
  flips a key to matched — so they cannot invalidate an in-process cache
  at all, and "remember to invalidate" was never the available rule.
  `data_version` costs 3.7 µs and catches every out-of-process commit
  including ones not yet written; its one blind spot is a connection's
  own commits, which is exactly hide/unhide. It was declined on
  proportion — it would save 0.3 s and buy back a surface on which a
  wrong answer can be served, where the presort has none.

- **Hiding a resolved key** —
  `docs/superpowers/specs/2026-07-31-hidden-keys-design.md`.
  `hidden_keys` records the owner asserting "wherever this one ended up,
  I know it is resolved". Keyed `(gamekey, machine_name)` and kept out of
  `DERIVED_TABLES`, so a reset preserves it. The viewer hides and unhides
  per row behind a fourth chip; `keys --hidden` lists them; the CLI
  report and the tab badge both go quiet.
  Four measurements shaped it. `machine_name` is present on every one of
  the 2,275 rows and all 2,278 tpks across 13 key types, so the column is
  `NOT NULL` with no fallback branch and no test that could reach one.
  The old `(gamekey, human_name)` key did not merely drop three rows — it
  kept an **arbitrary** one, and in both colliding orders the survivor
  was the less useful key (a gog key over the steam one; an expired gift
  key typed `generic`, which reports as *uncheckable*, over the steam one
  that could actually be checked), so the report was answering its own
  central question against the wrong store's library for two games.
  Those three keys are in no table the migration copies, so `keys` names
  them and points at `reparse`. And `keys.report` measures ~2.5 s, which
  is what rules out redrawing the panel by refetching after every hide;
  that number became its own entry above.
  Hidden is an annotation on the server and a fourth chip in the browser.
  `counts` still partitions every key, and the chip counts moved to the
  browser and are computed from a `displayState` helper, so the four
  chips partition the reported rows *by construction* — the statistics
  panel's "Unmatched 4 jumped and returned 8" bug made unreachable
  rather than merely fixed. An earlier draft made hidden a second filter
  axis with its own boolean and a pool indirection; it bought "hidden
  near matches only", which nothing needs, and cost exactly that bug.
  Two deliberate asymmetries, both pinned by tests because both invite
  tidying. `hidden_keys` has no foreign key, because a hide must outlive
  the key it names — every hide is stale straight after a reset, and
  `stale_hides` reports them as a count rather than as rows with one
  populated column. And hide checks the key exists while unhide does
  not, since requiring it would make exactly those stale hides
  un-unhideable.
  Two things only showed up in the doing. The migration's skip-a-bad-blob
  guard cannot be `json_extract(...) IS NOT NULL`, because `json_extract`
  *raises* on malformed JSON rather than returning NULL — so one bad row
  would take down the whole migration, which is the failure the guard
  exists to prevent; it is `json_valid` inside a `CASE`. And the
  migration cannot announce anything at all: `db.py` has no `print` and
  `connect()` runs in every command, every test, and once per viewer
  thread.

- **Unredeemed key report** —
  `docs/superpowers/specs/2026-07-30-unredeemed-key-report-design.md`.
  `keys` (and the viewer's Keys section) lists the Humble store keys whose
  game appears in none of the imported store libraries — 624 of 2,275,
  with 98 more for stores that have no importer and therefore cannot be
  checked at all. Read-only: no schema change, no migration, no writes.
  Four measurements changed the plan this entry recorded.
  `num_days_until_expired` turned out not to be a sentinel to be
  distrusted but a redundant column to ignore: it reads `-1` on the 1,782
  keys with no expiry, `0` on exactly the 111 flagged `is_expired`, and a
  positive number on the remaining 382 — 382+111 being precisely the set
  carrying `expiry_date`, which is the only absolute one of the three and
  so the only one read. `key_type` carries 12 clean machine values beside
  `key_type_human_name`'s 52, so deriving the store from it sidesteps the
  case folding this entry expected to need and leaves `Other`/`other` a
  cosmetic wart on a label. Checkability is derived from `game_imports`
  rather than hardcoded to steam/gog/epic, so a machine that has never
  imported a store reports its keys there as uncheckable instead of
  falsely unredeemed. The `machine_name` and primary-key findings went to
  the hiding entry above, which needs one migration for both.
  Matching is scoped to the key's **own** store, unlike
  `bundle_preview`'s pooled libraries — a steam key whose game sits only
  in GOG is still an unactivated steam key. Worth 59 keys, and the reason
  `classify_game` and its two cutoffs moved to a shared `game_match.py`:
  the two callers treat the 80–92 band oppositely on purpose. There a
  `possible` is excluded, because the expensive mistake is a second
  purchase; here it is listed and annotated, because the expensive
  mistake is a key that quietly expires.
  Sorting is three groups rather than one ascending column — live expiry
  soonest first, then undated, then expired most-recent-first. Plain
  ascending puts the 40 dead rows above the 63 that can still be lost,
  which is the opposite of what this entry asked for.
  The badge counts expiring keys, not unredeemed ones: 624 never reaches
  zero, and `shell.js` had already settled that an always-lit badge costs
  the badge beside it its meaning.
  Two things only showed up in the doing, both in output rather than
  logic. A key expiring today printed "in 0 days", which is what the
  arithmetic produces and not what anyone says. And the CLI padded its
  name column to the widest name in the whole report, so one 92-character
  bundle-as-a-key name pushed all 63 default rows past an 80-column
  console — the padding is per printed block now, capped at the same 60
  the xlsx export uses.

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
