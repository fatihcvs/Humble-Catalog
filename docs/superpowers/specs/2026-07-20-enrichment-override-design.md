# Enrichment override for hand-edited rows

Let re-enrichment update a hand-edited row on request. Today enrichment
never touches one: `run()` only selects `pending` rows, and a hand edit
leaves the row `manually_fixed`, so a row you corrected by hand can
never benefit from better source data later. The only escape is a full
`--reset`, which discards every hand edit in the catalog.

Deferred from multi-value tags,
`specs/2026-07-18-multi-value-tags-design.md`.

## The problem with the current flag

"Edited" is not stored. It is derived: `pre_edit IS NOT NULL`
(`db.py`, item payload assembly). That single column does two unrelated
jobs:

1. it holds the revert baseline, and
2. it locks the row against `reset(reviews_only=True)`.

An override needs to unlock a row without discarding its revert target,
so the two jobs must be split before anything else can be built.

## Data model

Two new `enrichment` columns, both added in `_migrate`:

| column | meaning |
| --- | --- |
| `hand_edited` INTEGER | 1 when the visible values were typed by hand. Becomes the source of the `edited` badge. |
| `enrich_armed` INTEGER | 1 when the row is armed for one re-enrichment pass. |

`pre_edit` keeps a single job: **the state Revert returns you to.** It
is rewritten whenever authorship of the row changes hands.

Invariant: `hand_edited=1` implies `pre_edit IS NOT NULL`; the reverse
does not hold. A re-enriched row is `hand_edited=0` with `pre_edit`
still set.

### Migration

`ALTER TABLE enrichment ADD COLUMN` for both (the existing idiom for
new nullable columns), then a backfill under a `PRAGMA user_version`
bump:

```sql
UPDATE enrichment SET hand_edited=1 WHERE pre_edit IS NOT NULL
```

Every row that reads as edited today is a hand edit today, so the
backfill reproduces current behaviour exactly. No row changes meaning
and nothing is lost. Re-running the migration is a no-op.

### The three functions that own `pre_edit`

- `db.apply_hand_edit` — additionally sets `hand_edited=1`.
- `db.revert` — additionally sets `hand_edited=1`. After a revert the
  visible values are hand-typed again.
- `enrich.apply_candidate` — see below.

## `apply_candidate`

A guard at the top, applying to **all three callers** (normal runs,
Review-panel approvals, the override path):

> If the row is `hand_edited`, `json.dumps` its current
> `EDITABLE_FIELDS` into `pre_edit` before the UPDATE runs.

The existing UPDATE then drops `pre_edit=NULL` and extends its SET
clause with `hand_edited=0, enrich_armed=0`.

Without the re-snapshot, an override would overwrite hand-typed values
`H` while `pre_edit` still held the older enriched state `E1`; Revert
would restore `E1` and `H` would be gone for good — the opposite of the
intent.

**Intended behaviour change beyond this feature.** Approving a Review
candidate on a hand-edited row currently nulls `pre_edit`, making the
typed values unrecoverable. Under the uniform guard that path gains a
revert target. This is deliberate, not a side effect of the override
work. Chosen over a scoped guard so the two callers cannot drift.

For ordinary pending rows nothing changes: `hand_edited` is 0, so no
snapshot is taken and `pre_edit` stays NULL.

## Enrichment flow

**Arming does not change `status`.** `run()` widens its selection from
`status IN ('pending')` to `status IN (…) OR e.enrich_armed=1`. Arming
therefore mutates exactly one column; the row keeps its status, values
and badge until a run actually replaces them.

Per armed item, candidates are scored as normal, then:

- **`matched`** — `apply_candidate` runs (re-snapshotting `pre_edit` to
  the hand-typed values, clearing `hand_edited` and `enrich_armed`).
  The row becomes "re-enriched" and Revert is available.
- **anything else** — `low_confidence`, `unmatched`, source errors:
  write nothing except `enrich_armed=0`. No status downgrade, no
  candidates queued, no data touched. The run prints a line saying the
  row was left alone.

That asymmetry is the safety property: an armed row can only ever be
traded for a confident match. It cannot be degraded to `unmatched` or
parked half-resolved in Review. One-shot consumption means a row armed
and forgotten will not be re-armed by a later run.

`reset(reviews_only=True)` keeps sparing hand edits, but its predicate
becomes `hand_edited=0` instead of `pre_edit IS NULL`; otherwise
re-enriched rows would stay permanently immune to it.

## Viewer

A re-enrich toggle beside the existing Revert control on each
hand-edited row. Clicking arms, clicking again disarms; nothing else
happens until a run.

One endpoint: `POST /api/items/<id>/arm` with `{"armed": true|false}`.
It rejects rows that are not `hand_edited` — a machine-enriched row is
already eligible, so arming it is meaningless.

The item payload replaces its single `edited` field with three derived
ones:

| field | derivation | badge |
| --- | --- | --- |
| `edited` | `hand_edited=1` | `edited` |
| `re_enriched` | `pre_edit IS NOT NULL AND hand_edited=0` | `re-enriched` |
| `armed` | `enrich_armed=1` | modifier on the `edited` badge |

`#f-flag` gains an `armed` option, filtered client-side alongside the
existing predicates (`if (flag === "armed" && !i.armed) return false;`).
That supports a review-and-disarm pass over the whole armed set before
running enrich.

A re-enriched row is no longer `edited`, so it drops out of the `edited`
filter — a row can leave a filter you are working through, without you
touching that row again. Accepted: arming the row is the acknowledgement
that it may stop being a hand edit.

## CLI

`enrich --override-edited` arms every `hand_edited=1` row and then runs,
in one invocation. Arming without running would leave a large armed set
lying around, which is the state the flag is riskiest in.

Before arming anything:

```
63 hand-edited items will be re-enriched. Confident matches
overwrite your typed values (Revert stays available per item).
Type OVERRIDE to continue:
```

Combining `--override-edited` with `--reset` or `--reset-reviews` is
rejected with an error before anything is written. `--reset` would wipe
the very hand edits the override exists to carry through, so the
combination can only ever be a mistake.

- Anything but exactly `OVERRIDE` aborts with nothing written.
- A non-TTY stdin aborts rather than reading a piped answer. There is
  deliberately no `--yes`, so this cannot fire from a script.
- A count of 0 reports that and exits without prompting.

## Testing

Fixture titles come from `docs/TEST-DATA.md`; `leak_check.py` runs
before committing.

- **`test_db.py`** — migration backfill (a pre-migration row with
  `pre_edit` set comes out `hand_edited=1`; idempotent on re-run);
  `apply_hand_edit` sets `hand_edited`; `revert` restores it.
- **`test_enrich.py`** — armed + confident match re-snapshots `pre_edit`
  to the hand-typed values and clears both flags; armed + no match
  leaves every column untouched except `enrich_armed`; armed + low
  confidence queues nothing; a second run leaves the row alone
  (one-shot). `reset(reviews_only=True)` spares `hand_edited=1` and
  sweeps re-enriched rows.
- **`test_webapp.py`** — arm endpoint round-trip, rejection of a
  non-hand-edited item, the three derived payload fields.
- **`test_webapp_js.py`** — the `armed` filter predicate and badge
  rendering.
- **`test_cli.py`** — confirmation accepted; confirmation refused writes
  nothing; non-TTY aborts; zero count exits without prompting.

The load-bearing test is *armed + no match changes nothing*. It fails
loudly if a future edit to `run()` lets an armed row fall through to the
ordinary `unmatched` path and silently strip a hand edit.

## Out of scope

- Bulk arming from the viewer. The CLI covers catalog-wide; the viewer
  stays per-row.
- Routing armed rows into Review on a low-confidence match. Rejected in
  favour of leaving the row untouched.
- A sticky "always re-enrich this row" property. One-shot only.
