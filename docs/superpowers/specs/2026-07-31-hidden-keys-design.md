# Hiding a resolved key — design

Date: 2026-07-31.
Implements the **External keys → Hiding a resolved row** entry in
`docs/BACKLOG.md` (requested 2026-07-30), and carries out that entry's
instruction to fix `external_keys`'s primary key in the same migration.
Follows `specs/2026-07-30-unredeemed-key-report-design.md`, which shipped
the report this feature makes quiet.

## The problem

`keys` lists the Humble store keys whose game appears in none of the
imported store libraries. It is read-only and stateless, so it says the
same thing every run — which is correct for the rows the owner has not
looked at yet, and wrong for the ones they have.

Some rows cannot be resolved by any evidence on this machine. A key
redeemed on an account the importer does not read, a key gifted away, a
key for a storefront that will never have an importer: the owner knows
the answer, the catalog cannot. Today those rows come back every run and
sit in the same list as the rows that still need work, which is the
failure mode a to-do list has when nothing can be crossed off.

So the feature is one assertion the owner can make: *wherever this one
ended up, I know it is resolved.* Nothing is deleted and nothing is
recomputed; the row stops being reported.

### The other problem, in the same table

`external_keys` is keyed `PRIMARY KEY (gamekey, human_name)`, and
`store.py` writes it with `INSERT OR REPLACE`. That pair is not unique.
Measured 2026-07-31: `raw_orders` holds **2,278** tpks, `external_keys`
holds **2,275** rows. Three keys are silently dropped at write time.

The cause is structural rather than corrupt data. Humble sells one
product redeemable on several storefronts and ships each storefront as
its own tpk. `human_name` is the **game**; `machine_name` is the game
**and its store**. A multi-store product therefore produces several tpks
with byte-identical `human_name`s by design, and the primary key asserts
one key per game per order, which was never true. `INSERT OR REPLACE`
turns the violated constraint into a silent overwrite: last write wins,
on whatever order `all_tpks` happens to be in.

Two orders in this catalog collide, losing three keys between them. The
count understates the damage, because the survivor is arbitrary and in
both cases it is the less useful key:

- One product ships steam, gog and a dead-console key. The **gog** key
  survived and the **steam** key was dropped, so if the game sits in the
  Steam library and not GOG, the report checks it against the wrong
  store's pool. That is exactly the "a steam key whose game sits only in
  GOG is still an unactivated steam key" case `keys.py`'s module
  docstring exists for, arriving through the back door.
- One product ships a steam key and an expired gift key typed `generic`.
  The **gift** key survived. `store_for("generic")` returns `generic`,
  which matches no `game_imports` row, so that key reports as
  **uncheckable** — while the real steam key, the one that could have
  been checked, is not in the table at all.

So the fix is not only three recovered rows; it corrects two rows that
currently answer the report's central question against the wrong store.

The two problems share a solution. A hide has to name a key, and
`machine_name` is the identifier that both is unique and survives a
rebuild. Migrating the primary key once rather than twice is why the
backlog entry put them together.

## The change

### `external_keys` gains `machine_name` and is re-keyed

```sql
CREATE TABLE IF NOT EXISTS external_keys (
  gamekey TEXT NOT NULL REFERENCES bundles(gamekey),
  machine_name TEXT NOT NULL,
  human_name TEXT, key_type TEXT, raw TEXT,
  PRIMARY KEY (gamekey, machine_name));
```

`(gamekey, machine_name)` is unique across all 2,275 existing rows,
measured. It is also the rebuild-stable identifier convention
`user_item_data` follows: the row id is regenerated on every rebuild,
`machine_name` is not.

`NOT NULL` with no default, and the measurement earns it — **all 2,275
rows and all 2,278 tpks carry a `machine_name`**. There is no "Humble
omitted it" case in the data, so there is no fallback branch to write
and no test that could exercise one. `parse_order` therefore subscripts
`tpk["machine_name"]` rather than `.get()`ing it: a genuinely malformed
order should raise where it is parsed, not write a NULL that fails a
constraint two layers later.

### `hidden_keys` is new

```sql
CREATE TABLE IF NOT EXISTS hidden_keys (
  gamekey TEXT NOT NULL, machine_name TEXT NOT NULL,
  hidden_at TEXT NOT NULL,
  PRIMARY KEY (gamekey, machine_name));
```

Keyed on the pair, not on `machine_name` alone. Measured 2026-07-31:
2,275 keys hold only **2,117** distinct `machine_name`s, because 128
games are keyed in more than one bundle. A `machine_name`-keyed table
would hide both rows at once, and the hide is per key, not per game —
one bundle's key may have landed while the other's did not.

**No foreign key to `external_keys`**, against the surrounding
convention and on purpose. A hide has to *outlive* the row it refers to;
that is the whole reason the table is preserved across a reset. An FK
would make `reset`'s `DELETE FROM external_keys` either cascade the
hides away or fail outright, which is the opposite of what is wanted.
The staleness this admits is handled below.

### Migration 12

One guarded block, matching migrations 7 and 9–11 in shape. SQLite
cannot alter a primary key, so the table is rebuilt: create
`external_keys_new`, `INSERT ... SELECT gamekey,
json_extract(raw, '$.machine_name'), human_name, key_type, raw`, drop,
rename. `hidden_keys` needs no migration work — `executescript(SCHEMA)`
in `connect()` has already created it, so the block only carries the
version forward, exactly as migrations 7, 9, 10 and 11 note.

Two guards on the copy.

**A `raw` blob that will not parse is skipped and counted.**
`json_extract` returns NULL for a missing or unparseable blob, and
`NOT NULL` would abort the whole migration on one bad row — leaving the
database unopenable, which is the worst failure available here. No such
row exists in this catalog; the guard is against future data.

**The migration stays silent, and the report speaks instead.** The three
dropped keys are *not* in `external_keys` and cannot be recovered by a
migration that copies it — they exist only in `raw_orders`. So they must
be reported rather than fixed.

The first draft of this spec had the migration print them. **That is not
possible**, discovered while planning: `db.py` contains no `print` at
all, and `connect()` runs in every command, in every test, and once per
thread in the viewer. A message there would land in the middle of a
harvest progress bar and in every test's captured stdout.

It moves to `keys.report()`/`format_report()` — which is the better home
regardless. A one-shot migration message can be missed forever; a line
in the report the owner already reads self-clears the moment they
`reparse`:

```
  3 keys in your orders are missing from the catalog: Twin Lantern (2),
  Hollowmere (1). Run 'reparse' to recover them.
```

The query is **one** row-value `NOT IN` against `external_keys`, grouped
by `human_name`, measured at 33 ms on this catalog and returning the
right two products and three keys. Worth stating because it was nearly
cut as over-engineering, on a guess that a set difference would be
costly. It is not, and naming the products is what makes the line
actionable rather than a number the owner cannot check.

The migration's own guard needed a correction that only testing found.
Skipping an unparseable blob cannot be written
`WHERE json_extract(raw, '$.machine_name') IS NOT NULL`: `json_extract`
**raises** on malformed JSON rather than returning NULL, so the null test
never gets the chance to filter and one bad row takes down the whole
migration — the exact failure the guard exists to prevent. It is
`json_valid` inside a `CASE`, which is documented to evaluate lazily
where a `WHERE`-clause `AND` is not, with the projection wrapped in a
subquery so it cannot re-evaluate unguarded.

The migration deliberately does **not** re-derive `external_keys` from
`raw_orders` itself. Its job is to change the table's shape, not to
re-run the parser; `reparse` already does that, offline, from the
preserved download cache. No existing migration parses anything, and
this one should not be the first.

### `reset.py` and `backup.py` are untouched

`DERIVED_TABLES` already lists `external_keys` and does not list
`hidden_keys`, so "wipe the keys, keep the hides" is what the existing
code already does. `backup.py` copies the whole database file, so it
needs nothing either.

Both are stated here precisely *because* they are no-ops. The absence of
`hidden_keys` from that tuple is a decision, and an undocumented absence
reads as an oversight to whoever next edits it. The decision: dedupe
dismissals can afford to be wiped because a rebuild re-derives the pairs
and the owner re-judges them from data still on disk. A resolved-key
assertion is knowledge about what happened beyond this machine, which no
rebuild can recover — wiping it would refill the report with rows
already resolved.

### Stale hides

The cost of preserving hides is the opposite failure: a hide can outlive
the key it named. After a `reset` and before a `reparse`, *every* hide is
stale.

`report()` counts them — `hidden_keys` rows with no matching
`external_keys` row — and both surfaces print one line:

```
3 hides refer to keys no longer in the catalog
(run 'reparse' if you have just reset).
```

A count, not rows. A stale hide holds only `gamekey`, `machine_name` and
`hidden_at`; the product name, store, bundle and expiry all lived in the
wiped table. Listing them would render a table with one populated column
per row, and after a reset it would be hundreds of them. Nothing is
deleted and nothing is silent; the count is the whole signal.

### `keys.py`

`_key_rows` selects `k.machine_name` and adds
`LEFT JOIN hidden_keys h ON h.gamekey = k.gamekey
AND h.machine_name = k.machine_name`, yielding `h.hidden_at`. The row
payload takes `machine_name` from the column instead of
`raw.get("machine_name")`, so the field that decides a key's identity
stops being read out of a blob. The docstring's "one parse yields four
fields" argument shrinks to three and is updated to say so.

`report()` returns one new number and one new per-row field:

- **`hidden_at`** on every reported row — an ISO string, or `None`.
  Rows are **not** filtered here.
- **`stale_hides`** — the count above.
- **`missing_keys`** — the products whose tpks are in `raw_orders` but
  not in `external_keys`, most-lost first. See the migration section
  above for why it lives here rather than in migration 12.

There is deliberately no `hidden` count in the payload. `format_report`
counts `rows` itself and the viewer computes its own chip counts, so a
stored total would be a second version of a number already derivable
from the rows beside it — free to let drift, and worth nothing.

`stale_hides` is the opposite case and that is why it is here: it cannot
be derived from `rows` at all. A hide on a key that has since become
`matched` is not stale, but `matched` rows are not in `rows` either, so
"hides minus hidden rows shown" would count it as stale and be wrong.
Only a query against `external_keys` answers it.

**On the server, hidden is an annotation, not a state.** A hidden row
still *is* `unredeemed`, `uncertain` or `uncheckable`. `counts` is
unchanged and still partitions all 2,275 keys, hidden included;
`reported` still means "how many keys are not matched". Both keep
exactly today's meaning, which is what lets hiding be a subset of the
report rather than a bucket carved out of it. The viewer presents it as
a fourth chip, which is a display choice made in `keys.js` and does not
travel back across the route.

`report()` annotating rather than filtering is the central structural
choice. The alternatives were a `report(hidden=...)` parameter threaded
through `format_report()` and the route, and a second
`hidden_report()`. The first makes hidden look like a fourth state at
the API boundary and forces the viewer to refetch on every chip toggle;
the second is the option that most reliably lets the two reports drift
apart, which is the failure this module's split exists to prevent. With
annotation there is one query and one definition of hidden, and the CLI
and the panel filter on the same field.

**`expiring` also excludes hidden rows**, but the behaviour that matters
is not here. Measured 2026-07-31: `expiring` and `reported` are read by
**nothing** — not `format_report`, not `keys.js`, only tests. The number
the owner actually sees is the tab badge, and that comes from
`keysExpiring()` in `keys.js`, computed in the browser from `rows`.

So the real change is the one-line filter in `keysExpiring()`, and
`expiring` is updated only so a future reader of the payload is not
handed a server-side number that disagrees with the browser's
identically-named one. It is worth recording that both fields are
currently dead weight; removing them is a tidy for another day, not part
of this feature.

### CLI

`format_report` filters hidden rows out of the live, undated and expired
blocks, and adds one line to the existing "`keys --all` for the other N"
region: `(12 hidden; 'keys --hidden' lists them)`.

`keys --hidden` lists the hidden rows *instead of* the report. Its block
prints `hidden_at` in the leading column where the ordinary report
prints the expiry — same columns otherwise, same `_line`/`_block`
machinery, same 60-character name cap — and ends with the stale count
line.

It lists **every** hidden row in one block, newest hide first, and
`--all` has no effect on it. The main report splits into live / undated
/ already-expired because it is triage, and `--all` exists to keep the
default from leading with 700 lines nobody reads. A hidden list is not
triage: the rows are there because the owner put them there, the list is
as long as the owner made it, and "which of my dismissals expire soon"
is not a question hiding leaves open.

There is no "include" mode producing one list of hidden and unhidden
rows together, although the backlog's wording allowed one. The two CLI
questions are "what still needs doing" and "what have I dismissed", and
both are answered; a merged list is a third question nobody has asked,
and the viewer's chips give it to anyone who wants it.

**Hiding stays viewer-only.** There is no `keys --hide`; nothing in
`keys.py` writes.

### Routes

```
POST /api/keys/hide     {gamekey, machine_name} -> {"ok": true}
POST /api/keys/unhide   {gamekey, machine_name} -> {"ok": true}
```

Both follow `dismiss_pair`'s shape: validate the body, `400` with a JSON
error on anything malformed, `INSERT OR IGNORE` / `DELETE` so a repeated
call is a no-op rather than an error. Hiding twice keeps the original
`hidden_at`. The timestamp is stamped server-side as UTC ISO — the
browser never sends one, so a wrong client clock cannot write a wrong
date.

They differ in one validation, on purpose. **Hide** checks the pair
exists in `external_keys` and `400`s if not. **Unhide** does not:
requiring existence there would make exactly the stale hides
un-unhideable, which are the rows most in need of removing. It is a rule
someone will later "tidy" into symmetry, so both halves are pinned by
tests.

Identifiers travel in a **POST body, never a query string**. This is the
filter-aware-export precedent: `machine_name` is derived from the
product title, so it names something owned, and query strings reach
access logs and browser history.

### Viewer

Hidden is a **fourth chip**, off by default, and `KEY_STATES` gains a
matching entry. Making it a chip rather than a separate sub-panel is
what makes the backlog's "same columns in both views" structural rather
than a promise: it is literally one table.

It is a fourth chip in the browser only. On the server, hidden stays an
annotation and `counts` keeps partitioning all 2,275 keys by
`unredeemed`/`uncertain`/`uncheckable`/`matched`. The two views of the
same fact are reconciled by one function:

```js
const displayState = (r) => (r.hidden_at ? "hidden" : r.state);
const shownKeys = () => keyRows.filter((r) => keyStates.has(displayState(r)));
```

One set and one filter, which is the point. An earlier draft made hidden
a second *filter axis* — a `keyHidden` boolean beside `keyStates`, with
a `keyPool()` indirection between them. It bought the ability to ask for
"hidden near-matches only", which nothing needs across a handful of
rows, and it cost a corner where the Hidden chip's count did not equal
what clicking it delivered. `displayState` is strictly less machinery.

**The chip counts are computed in the browser, from `displayState`, not
read from `keyCounts`.** `keyCounts` partitions all 2,275 keys, so a
chip reading "Not in a library 624" would deliver fewer than 624 once
hidden rows are pulled out of that bucket. That is the statistics
panel's "a row reading Unmatched 4 jumped and returned 8" bug, and a
count must equal what you see after the click. Counting by
`displayState` makes the four chips partition the reported rows by
construction, so the rule holds structurally rather than by anyone
remembering it.

A hidden row still shows its true `unredeemed`/`uncertain`/`uncheckable`
in the **State** column; only its chip membership changes. Nothing about
why the row was reported is lost from the display.

`keyCounts.matched` still feeds the panel's summary line, which is a
whole-catalog statement and correctly ignores hiding.

`keysExpiring()` filters hidden rows out, so the tab badge stops
counting a key the owner has resolved.

The table gains a **Hidden column**: `hidden_at`'s date for a hidden
row, blank otherwise, plus a `hide`/`unhide` button. The existing
delegated `#keys-panel` listener grows one branch — per-row listeners
cannot work here, because `renderKeys()` rebuilds the panel through
`innerHTML`.

After a successful POST the handler updates that row's `hidden_at` in
`keyRows` locally, re-renders, and refreshes the badge with
`pending.keys = keysExpiring(); renderBadges();`. **No refetch of
`/api/keys`** — the report classifies every one of 2,275 titles against
the store pools on each call, measured 2026-07-31 at **~2.5 s**. That is
not a button click. Same trade the statistics panel made: touch the two
mutation call sites rather than reload everything.

The 2.5 s is pre-existing and out of scope here, but it is the reason
this design cannot take the simpler refetch-and-redraw route, so it is
recorded rather than left as an assertion. It belongs on the backlog in
its own right.

The hide/unhide control is styled from the start, via `var(--accent)`.
The statistics panel shipped its jump counts as bare `<button>`s, which
kept the browser's grey default and glared on the dark panel; the JS
harness could not see it, because its stubbed DOM has no computed
styles. Same class of control in the same panel family, so it gets a
look in a real browser before it is called done.

## Testing

The tests carrying real weight:

**Regression.** `store_order` writing two tpks that share a `human_name`
under one `gamekey` keeps **both**. This is the three-lost-keys bug and
the reason the primary key moved; without it the change is untested
intent. Fixture: *Twin Lantern* keyed on steam and gog in one order.

**Migration.** An old-shaped `external_keys` gains populated
`machine_name`s and the new primary key. A row whose `raw` will not
parse is dropped and counted rather than aborting the migration.

**Hidden is an annotation on the server.** A hidden row keeps its state
and still appears in `counts`, so the existing "the four states
partition every key" test passes unchanged with hides present. This is
the assertion that stops the viewer's fourth chip leaking backwards into
the report as a fourth state.

**The deliberate exclusions.** `expiring` drops a hidden row;
`stale_hides` counts a hide whose key is gone; the default
`format_report` omits hidden rows and says how many; `keys --hidden`
lists them with `hidden_at` and the stale line.

**The asymmetry.** Unhide succeeds on a stale hide; hide `400`s on an
unknown pair. Two tests, because it is a rule that invites tidying.

**Idempotence.** Hiding twice leaves the original `hidden_at`.

**JS harness.** *Every chip's count equals the number of rows the table
actually renders when that chip is the only one on*, with hides present.
This is the statistics panel's bug pinned in advance, and it is the
single test most worth having. Plus `keysExpiring()` excluding hidden.

Styling and the real-browser check stay manual — the harness's stubbed
DOM has no computed styles, which is how the grey-button bug shipped
last time.

## Privacy

Nothing here changes what is stored; `hidden_keys` holds a gamekey, a
machine name and a timestamp, and `catalog.db` is gitignored as always.

Two things need judging by eye rather than by a check:

- **The migration's message names owned products.** It prints the
  colliding `human_name`s so the owner can see which store went missing.
  That is terminal output in the same category as `harvest --failures`
  and the repeat block at the end of a `harvest`: nothing tracks or
  scans it, so no automated check would notice if a paste reached a
  commit message, a doc or an issue. Judge it by eye before pasting it
  anywhere.
- **A Keys panel screenshot frames bundle names, product names, stores
  and counts at once.** No screenshot of this feature goes near a
  commit.

Examples in this spec and in the tests use invented names from
`docs/TEST-DATA.md` — *Twin Lantern* is added there for the collision
fixture, vetted against `leak_check.build_terms()` first, as that file
requires. Run `.venv/Scripts/python scripts/leak_check.py` on its own
(never piped) after the tests and docs are written.

## Verification

- `verify` passes, including `leak_check.py` and
  `check_no_data_tracked.py`.
- `keys` on the live catalog prints the same report as before the
  change, with no hides set, plus the new hidden line once one is.
- The migration runs on the live catalog and reports 2,275 carried over
  and 3 still missing; `reparse` afterwards brings `external_keys` to
  2,278.
- The Keys panel is opened in a real browser: chips, the Hidden column,
  the hide/unhide control in both themes, and a chip count checked
  against the rows it delivers.

## Docs

- `README.md`'s `keys` entry gains `--hidden`; `--help` gains the flag
  with matching wording.
- `docs/TEST-DATA.md` gains *Twin Lantern*.
- `docs/BACKLOG.md` moves the entry from Open to Done, recording what
  measurement changed: `machine_name` is universal, so the column is
  `NOT NULL` with no fallback branch; and the three recovered keys need
  a `reparse` the migration deliberately does not perform.

## Out of scope

No `keys --hide` on the CLI, no bulk hide, no reason or note field on a
hide, and no auto-expiry of hides.

## Deferred

- **Hiding a whole game rather than a key.** The 128 games keyed in more
  than one bundle each need hiding twice. Deliberate — one bundle's key
  may have landed while the other's did not — but if the two-hide case
  turns out to be the common one in practice, a "hide every key for this
  game" action is the shape that would answer it. Revisit once the
  feature has been used enough to say.
