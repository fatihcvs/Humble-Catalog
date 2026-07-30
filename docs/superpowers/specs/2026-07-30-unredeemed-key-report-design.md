# Unredeemed key report

A table of Humble store keys whose game appears in no imported store
library — what has been paid for and, as far as anything here can tell,
never claimed.

Status: design agreed 2026-07-30. Fills the Keys section that
`2026-07-30-viewer-multi-section-layout-design.md` shipped empty and
wired for exactly this.

## Why now

`_keyed_games` in `bundle_preview.py` already asks "do I own this
bundle's games somehow", joining `external_keys` to `bundles` and
matching `clean_game_title` against `games.normalized_title`. Inverted,
the same join answers the complementary question. The machinery exists;
what is missing is the question.

The bug that produced `_keyed_games` is the argument for asking it. A
third of the distinct keyed titles in the catalog are in no imported
library, and the owner had no way to see that list — the fact only
surfaced because a bundle preview recommended buying something already
paid for.

## What the data says

Measured against the live catalog on 2026-07-30, before any code was
written. Counts only; every number below is reproducible from
`external_keys`, `games` and `game_imports`.

| Fact | Measured |
|---|---|
| Keys stored | 2,275 |
| Distinct `machine_name` | 2,117 |
| `(gamekey, machine_name)` pairs | 2,275 — unique |
| Keys carrying `expiry_date` | 493 |
| `key_type` values | 12 |
| `key_type_human_name` values | 52 |

Four of those measurements changed the design, and each is recorded here
because the backlog entry guessed differently.

**`num_days_until_expired` is not a sentinel field to be distrusted; it
is a redundant one to be ignored.** It reads `-1` on 1,782 rows, `0` on
exactly the 111 rows flagged `is_expired`, and a positive number on 382.
382 + 111 = 493, which is precisely the set carrying `expiry_date`. So
all three columns are views of one fact, and `expiry_date` is the only
one of them that is absolute. `expiration_date` is byte-identical to
`expiry_date` on all 493 rows and is likewise ignored.

The report therefore parses `expiry_date` and compares it to the current
time. The other two are *derived at harvest time*: they agree with the
dates today only because the last harvest was five days ago, and both
drift silently as the catalog sits. Reading the absolute date makes the
backlog's "confirm that before any column trusts it" moot rather than
answered.

**`key_type` is the vocabulary; `key_type_human_name` is a label.** The
backlog specced the store column from `key_type_human_name` and noted it
would need the case folding
`2026-07-18-genre-case-normalization-design.md` established — 52 strings
including both `Other` and `other`. But `key_type` sits in the same blob
with 12 clean machine values. Deriving the store from `key_type` means
the case collision never enters the logic; the human name survives only
as display text, where `Other` and `other` differing is cosmetic and
affects 8 rows.

**`machine_name` is not unique, so it cannot be a key.** 128 machine
names appear in more than one bundle — the same game keyed twice. The
backlog's `hidden_keys(machine_name TEXT PRIMARY KEY)` would therefore
hide both rows, contradicting its own closing note that "the hide is per
key, not per game". `(gamekey, machine_name)` is unique across all 2,275
rows and is the identity to use. Hiding is a separate entry, so this spec
only records the finding; see **Out of scope**.

**`external_keys`'s primary key drops three keys.** `raw_orders` holds
2,278 tpks and the table holds 2,275: the key is `(gamekey, human_name)`,
and three orders carry two keys with the same display name. Also left to
the hide entry, which needs the same `(gamekey, machine_name)` key and
should migrate once rather than twice.

## Decisions

| Question | Decision | Rejected alternative |
|---|---|---|
| Match scope | The key's own store only | Any imported library, as `bundle_preview` pools them |
| Middle band (80–92) | Listed, annotated with the near match | A separate block; excluded as redeemed |
| Uncheckable stores | A third state, never "unredeemed" | Folded into the main list |
| Checkability | Derived from `game_imports` | A hardcoded steam/gog/epic set |
| Expiry source | `expiry_date`, parsed at report time | `num_days_until_expired` / `is_expired` |
| Persistence | None | A `hidden_keys` table in this change |
| Badge | Rows with a live expiry | Unredeemed count |

### Why the key's own store

A Steam key is redeemed into Steam. If the game shows up only in the GOG
library, the owner has the game and still holds an unactivated Steam key
— which is exactly the row this report exists to surface.

`bundle_preview` pools every store deliberately, and correctly: it asks
"should I buy this", and owning the game anywhere is the answer. This
report asks "did this key ever land", and only one library can answer.
The two questions look alike and are not, so they get separate pools
rather than a shared helper with a flag.

Measured, the difference is 59 keys: same-store reports 547 unredeemed
where any-store reports 488.

### Why checkability is derived

A key is checkable when its store has been imported. `key_type` maps to
a store by stripping a `_keyless` suffix — `gog_keyless` → `gog`,
`epic_keyless` → `epic` — and the store is checkable when
`game_imports` holds a row for it.

Verified: that rule reproduces the 98 uncheckable keys exactly, the same
~1-in-23 the backlog described. It is better than the hardcoded set for
two reasons. A machine that has never imported Epic gets its Epic keys
reported as *uncheckable* rather than falsely unredeemed, which is the
honest answer. And a store gaining an importer later needs no edit here.

### Why the middle band is listed

`classify_game`'s band between `GAME_POSSIBLE` (80) and `GAME_OWNED`
(92) holds 77 keys scored against their own store's library.

`bundle_preview` counts those as neither owned nor new, because there the
expensive mistake is recommending a purchase of something already owned.
Here the expensive mistake is the opposite: a key that really is
unclaimed, quietly suppressed because its title resembles something in
the library, and noticed after it expires. So `uncertain` rows appear in
the main list, carrying the title they nearly matched and its score, and
the reader adjudicates.

Same thresholds, opposite treatment. That inversion is the reason the
constants become shared code with the reasoning attached rather than a
copy.

## Architecture

### States

Every key lands in exactly one state, so the four counts sum to the row
count of `external_keys`.

| State | Rows today | Meaning | Reported |
|---|---|---|---|
| `matched` | 1,553 | its game is in that store's library | no |
| `unredeemed` | 547 | checkable store, nothing matched | yes |
| `uncertain` | 77 | scored 80–92 against its own store | yes |
| `uncheckable` | 98 | the store has no importer | yes, apart |

Of the 547 unredeemed, 183 carry no `redeemed_key_val` at all — never
even revealed, the cleanest signal available. 63 reported rows have a
live expiry date; 40 more have one already past.

### `game_match.py`

`GAME_OWNED`, `GAME_POSSIBLE` and `classify_game` move out of
`bundle_preview.py` into a new `game_match.py`, imported by both.
`bundle_preview` keeps `_keyed_games`, `_owned_games` and everything
about a bundle page.

The trigger is a second consumer, which is the same rule that made
`stats._console_safe` and `progress._duration` public. The measurement
comments on both cutoffs travel with the constants, and the new module
gains the note that the two callers treat the middle band oppositely on
purpose.

### `keys.py`

The same split as `stats.py`, for the same reason: one counter, two
surfaces, no possibility of drift.

- `store_for(key_type)` — the `_keyless`-stripping map above.
- `report(conn)` — reads, counts, returns a plain dict. The only place
  a key's state is decided.
- `format_report(report, encoding)` — the CLI text, through
  `stats.console_safe`.
- `run(show_all=False)` — the subcommand entry point.

A row:

```
{product, machine_name, gamekey, store, key_type_label, bundle,
 purchased_at, expires, expired, revealed, state, near_match}
```

`machine_name` comes from the stored `raw` blob, so no column is added to
`external_keys`. The blob is parsed in Python rather than reached with
SQL `json_extract`: one parse yields `machine_name`, `expiry_date`,
`redeemed_key_val` and `key_type_human_name`, where SQL would need four
calls, and a row whose blob is not JSON skips itself instead of failing
the whole query. `near_match` is
`{owned_title, score}` on `uncertain` rows and `None` elsewhere.
`revealed` is the presence of `redeemed_key_val`, and is labelled
"revealed" and never "redeemed" — Humble sets that field the moment the
key's value is *displayed*, which says nothing about whether the game
reached a store account. The key that motivated `_keyed_games` reads as
redeemed.

### Sort order

Three groups, in this order:

1. a live expiry date, soonest first — the rows that can still be lost
2. no expiry date
3. an expiry date already past, most recent first

The backlog asked for "expiry ascending with undated rows last so the
rows that can still be lost come first". Plain ascending does not deliver
that: it puts the 40 dead rows above the 63 urgent ones. Splitting the
dated rows around the undated ones is what the stated intent actually
requires.

Within a group, ties break on `purchased_at` then product, so the order
is a pure function of the data rather than of the query plan — the
guarantee `2026-07-30-harvest-worklist-order-design.md` established.

### `GET /api/keys`

A reshaping of `keys.report`, never a second count — the rule
`/api/stats` follows. GET with no parameters: the report is always the
whole key set, so there is nothing to pass, and nothing about the library
reaches a query string. No change to the exposure model; the loopback
check in `webapp/__init__.py` covers it as it covers every other route.

### Viewer

`keys.js`, rendering into the waiting `#section-keys`. One table —
Product, Store, Bundle, Purchased, Expires, Revealed, State — plus a chip
row for the three reported states, `uncheckable` off by default so the
main list is the falsifiable one.

Deliberately *not* reusing `catalog.js`'s chip-filter registry, sort or
fuzzy search. All three are bound to the `items` array, and two views
needing different column sets is the whole reason sections exist. A keys
table that borrowed the library's machinery would re-create the coupling
the sections were built to remove.

`keys.js` loads between `maintenance.js` and `bundles.js`, and its loader
joins `load()`'s guarded step list so one failing renderer cannot blank
the page.

### Badge

`pending.keys` is the number of reported rows with a **live expiry
date** — 63 today — not the 547 unredeemed.

`shell.js` already settled this policy for Library: a badge means "there
is work waiting", and a count that never reaches zero is a badge the eye
stops reading, taking the badge beside it down with it. 547 unredeemed
keys is exactly that number; it is a standing fact about the library, not
a queue. Expiring keys is a queue.

### CLI

`keys`, with one flag:

```
2,275 keys - 1,553 in a library, 624 not, 98 uncheckable

  Expiring (63):
    in 12 days   Amber Hollow      steam   Humble Game Bundle: Expiring Keys
    in 40 days   Cinder Vale       steam   Humble Game Bundle: Key Vault
  ...
  ('keys --all' for the other 659: 619 undated, 40 already expired)
```

The default answers "what needs me this week"; `--all` answers "what have
I never claimed". Printing all 722 reported rows by default is what
`--all` is for, and a bare command that prints only counts is one the
owner stops running.

## Testing

`tests/test_keys.py`, fixture-driven, with names from
`docs/TEST-DATA.md`. Two new entries are added there — *Amber Hollow*
(a steam key with a live expiry) and *Glass Meridian* (a steam key
already expired), in a new bundle *Humble Game Bundle: Expiring Keys*.
Both were vetted against `leak_check.build_terms()` before being written
down, as that file's own note on *Quartz Meridian* requires.

The existing entries already cover the states: *Cinder Vale* is a steam
key in no library (`unredeemed`), *Verdant Reach* an uplay key
(`uncheckable`), *Widget Quest* is owned on steam (`matched`), and
*Starfall Rally Turbo* keyed against the owned *Starfall Rally* lands in
the middle band (`uncertain`).

Behaviour pinned:

- `store_for` strips `_keyless`; a store with no `game_imports` row is
  uncheckable
- **an uncheckable key is never reported as unredeemed** — the backlog's
  central limit
- **a game present only in a different store's library still reports
  unredeemed** — the same-store decision, and the one a later reader is
  most likely to "fix" back into pooling
- an `uncertain` row carries its near match and score
- an expired, unmatched key is still listed rather than dropped
- the three sort groups, including that an expired row sorts below an
  undated one
- the four state counts sum to the total key count
- `--all` is the only difference between the two CLI outputs
- `/api/keys` reports the same counts as `keys.report`, following
  `test_webapp.py`'s `/api/stats` precedent
- JS: the badge shows the live-expiry count and is absent at zero; a
  state chip hides the other states

`scripts/leak_check.py` runs afterwards, since the tests and docs name
new invented titles.

## Documentation

- `README.md` gains a paragraph on the Keys section and the `keys`
  subcommand.
- The backlog's **Unredeemed key report** entry moves to **Done**, with
  what the measurements settled: the `expiry_date`-only rule, the
  derived checkability, the same-store scope, and the `machine_name`
  and primary-key findings handed forward to the hiding entry.
- The **Hiding a resolved row** entry stays Open, amended with the
  `(gamekey, machine_name)` correction and the three dropped keys.

## Out of scope

- **`hidden_keys` and hide/unhide.** Its own backlog entry. Deferring it
  keeps this change read-only — no schema, no migration, no
  `DERIVED_TABLES` question — and lets the report show how many rows
  actually need dismissing before a persistence shape is committed to.
  This is the order `bundle_preview` shipped in, for the same reason.
- **The `external_keys` primary key.** Three keys, and the same
  migration the hide table needs. Fixing it twice is worse than once.
- Any change to `import_games`, or to which stores have importers.
- GOG/Epic OAuth, which stays its own deferral.

## Risks

- **The report is long and stays long.** 624 checkable rows is not a
  queue anyone empties. Mitigated by what the default surfaces — the CLI
  leads with expiring rows and the badge counts only those — and by the
  hiding entry, which exists precisely because the list needs pruning.
- **Title matching is fuzzy in both directions.** A key can read as
  unredeemed because the store spells the game differently, and a
  coincidental match can hide a key that really is unclaimed. The report
  suggests where to look; it does not adjudicate, and its own output says
  so.
- **A stale library import ages the whole report.** Every "unredeemed"
  verdict is relative to the last `import-games` run. The report prints
  each library's import date, as `bundle_preview` does, so an old answer
  carries its age with it.
