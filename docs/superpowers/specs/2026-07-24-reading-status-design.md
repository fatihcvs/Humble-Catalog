# Reading status — design

Date: 2026-07-24.

A first-class **reading status** for each catalog item: a single value per
item, chosen from a fixed five-state vocabulary, that the owner sets by
hand in the viewer. It records where a book sits in the reading lifecycle,
separate from whether it has been rated.

## Motivation

The catalog already records ownership, metadata, ratings, free-text
comments, and a personal tag vocabulary — but nothing says *have I read
this?* or *what do I want to read next?*. Today that can only be faked with
a `user_tags` entry, which carries no ordering, no fixed vocabulary, and no
dedicated filter. Reading status makes it a real, single-valued field with
its own column, filter, and sort order.

## The five states

Stored as stable snake_case keys; the viewer maps each to a display label:

| Stored key      | Display label   | Meaning                              |
|-----------------|-----------------|--------------------------------------|
| `want_to_read`  | Want to read    | Explicitly queued to read next       |
| `unread`        | Unread          | Owned, not yet read (**the default**)|
| `reading`       | Reading         | Currently in progress                |
| `read`          | Read            | Finished                             |
| `dnf`           | DNF             | Started, did not finish              |

The lifecycle order for sorting is exactly the row order above:
`want_to_read → unread → reading → read → dnf`.

`unread` is the default because it is the honest resting state of an owned
book: the whole library is "owned but not read" on day one, and the other
four are the states the owner deliberately moves a book into. There is no
separate null / "untriaged" state — a decision taken during brainstorming.

## Decisions taken (and why)

- **Fully independent of `my_rating`.** Setting a rating never changes
  status, and setting status never changes a rating. This matches the
  codebase's grain: `user_tags` and `user_comment` are likewise
  independent of everything, and the alternative (a rating silently
  bumping a book to `read`) is a hidden write against a field the owner
  may have set deliberately.
- **A user-owned field, outside enrichment.** Like `my_rating`,
  `user_tags`, and `user_comment`, `read_status` lives on `items`, sits
  *outside* `EDITABLE_FIELDS` and `pre_edit`, and is never touched by the
  matcher. Setting it is not a hand edit and never locks a row out of
  re-enrichment.
- **Survives `reset`.** Because it is owner data, it must not be lost when
  the derived catalog is wiped and rebuilt. It joins the
  `user_item_data` snapshot table and the snapshot-and-restore path, the
  same treatment `my_rating` / `user_tags` / `user_comment` already get.

## Data model

A new scalar column on `items`:

```sql
read_status TEXT NOT NULL DEFAULT 'unread'
  CHECK (read_status IN ('want_to_read','unread','reading','read','dnf'))
```

Rationale for a `CHECK` rather than validation in Python alone: the allowed
set is small, fixed, and closed, so the constraint is cheap and makes an
illegal value impossible to persist regardless of which code path writes
it. Route-level validation still runs first so the API returns a clean
`400` instead of surfacing a SQLite `IntegrityError`.

`user_item_data` gains the same column so the reset snapshot can carry it:

```sql
-- user_item_data, after migration
machine_name TEXT PRIMARY KEY, my_rating INTEGER,
user_tags TEXT, user_comment TEXT, read_status TEXT
```

`read_status` is nullable in `user_item_data` (it is a snapshot, not the
live table); the restore path writes it back only when present, defaulting
a genuinely absent snapshot to `unread` — the same shape the existing
rating/tags/comment restore uses.

## Migration

A `user_version` 4 → 5 step in `db.py`, following the existing 3 → 4
pattern:

- `ALTER TABLE items ADD COLUMN read_status TEXT NOT NULL DEFAULT 'unread'`
  — every existing row gets `unread`, exactly the chosen default.
  (SQLite `ADD COLUMN` cannot attach a `CHECK`, so the constraint lives in
  the `CREATE TABLE` in `SCHEMA` for fresh databases; migrated databases
  rely on route validation to keep values legal. This asymmetry is
  acceptable — the same value set is enforced on the write path either
  way — and is called out here so it is not read later as an oversight.)
- `ALTER TABLE user_item_data ADD COLUMN read_status TEXT` — nullable, for
  the snapshot.
- Bump `PRAGMA user_version = 5`.

The migration is idempotent under the existing guarded pattern (each step
runs only when `user_version` is below its number).

## Backend

One new route in `webapp/__init__.py`, cloned from the existing per-item
`/type` route (validate against the allowed set, `404` if the item is
missing, `UPDATE`, commit):

```
POST /api/items/<int:item_id>/read-status
body: { "status": "reading" }
```

- Rejects any value outside the five keys with `400 {"error": "bad status"}`.
- `404` if the item does not exist.
- On success `UPDATE items SET read_status=? WHERE id=?`, commit, return
  `{"ok": True}`.

`db.fetch_items` must include `read_status` in the row it returns so the
viewer receives it (add it to the column list if the query is explicit; it
rides along automatically if the query is `SELECT i.*`).

## Viewer

### Setting it
A new **Status** column carrying a per-row `<select>` of the five labels,
wired like the existing per-row **Type** dropdown: `change` fires the POST
and updates the in-memory item; no page reload. The select's option values
are the stored keys, its text the display labels.

### Display
The five states render as distinct colored pills. The palette is chosen for
colour-vision-deficiency safety using the CIE Lab ΔE method already
established in this repo for the favicon work, so the five remain
distinguishable under simulated deficiencies rather than by hue alone.

### Filtering
A dedicated **Status** filter of five toggle chips (one per state). An item
passes if its status is in the ticked set; ticking none means no status
constraint. This is "any of these statuses", the shape chosen during
brainstorming.

It is deliberately **not** a `chipFilters` registry entry. That registry is
built for open-ended text vocabularies with autocomplete and an all/any
toggle; a fixed five-value enum is clearer as fixed toggles, and the "all"
mode is unsatisfiable for a one-value-per-item field (the registry's own
`scalar` comments already note this). The new filter slots into `visible()`
next to the existing `#f-type` check — e.g. a `Set` of ticked status keys,
and `if (statusFilter.size && !statusFilter.has(i.read_status)) return
false;`.

### Sorting
**Status** becomes a sortable column. It sorts by the lifecycle order
(`want_to_read → unread → reading → read → dnf`), not alphabetically, via a
small order-map lookup in `sortValue()` — the same indirection Bundle
already uses for its non-scalar field. (Alphabetical would interleave the
states meaninglessly: `dnf`, `read`, `reading`, `unread`, `want_to_read`.)

## Export

`read_status` joins `export.COLUMNS` and the viewer's mirrored
`EXPORT_COLUMNS`, becoming the 20th column. It is exportable to CSV and
XLSX, tickable in the Columns panel, and included by default. It is
exported as the readable label (e.g. `Want to read`), consistent with the
export favouring human-readable cells. The single source-of-truth comment
already pairing `export.COLUMNS` with `EXPORT_COLUMNS` continues to apply;
both lists gain the column so they cannot drift.

## Testing

- **Migration:** a database at `user_version` 4 gains `read_status`
  defaulting to `unread` on open, `user_version` becomes 5, and re-opening
  is a no-op (idempotent).
- **Route validation:** `POST /read-status` with a value outside the five
  keys returns `400`; a valid value persists and is reflected by
  `/api/items`; a missing item returns `404`.
- **Reset round-trip:** an item set to, say, `reading` keeps that status
  across `reset` + `reparse`, exercising the `user_item_data` snapshot and
  restore — the subtle case, matching the existing rating/tags snapshot
  tests. A book with the default `unread` also round-trips.
- **Independence:** setting `my_rating` leaves `read_status` unchanged, and
  setting `read_status` leaves `my_rating` unchanged.
- **Export:** `read_status` appears in CSV and XLSX output as its display
  label and honours a `--columns` subset (present when asked for, absent
  when not).
- **Sort order:** the viewer's status sort yields lifecycle order, not
  alphabetical (JS harness test over a small set such as *All Systems Red*
  = `read`, *Unrelated Book* = `want_to_read`, *The Quiet Harbor: A Novel*
  = `dnf`).
- Run `.venv/Scripts/python scripts/leak_check.py` after adding the spec,
  tests, and any docs, since they gain new example text.

## Out of scope (YAGNI)

Deliberately excluded; each can become its own backlog entry if missed:

- Date-read / date-finished tracking.
- Reading-progress percentage or page/chapter position.
- Per-format status (an ebook and its audiobook keep independent statuses,
  as they are already separate items).
- Any automatic coupling between status and `my_rating`.
- Status-change history or an activity log.
- A "want to read" *ordering* (a ranked queue); the state marks membership
  only.

## Documentation

- `README.md`: note the new Status column, its dropdown, the status filter,
  and that status survives `reset`.
- `docs/BACKLOG.md`: move "Reading status" out of the implicit-idea space
  into **Done** with this spec, once shipped.
