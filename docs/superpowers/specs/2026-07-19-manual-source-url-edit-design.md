# Manual source URL edit — design

Date: 2026-07-19.

## Problem

`source_url` can only be set by machinery: an enrichment match, or a
pasted URL resolved through `url_import`. There is no way to type one in
or correct one by hand.

That gap has a concrete cost. The link-only fallback
(`specs/2026-07-19-link-only-url-fallback-design.md`) attaches a URL for
pages we cannot read — a storefront answering the scrape with a 403 bot
wall, for instance — but it takes the item's existing Humble name as the
title, and there is no way to fix a link that turns out to be wrong
short of re-pasting it through the review flow. An item that is not in
review at all cannot be given a link by any route.

Recorded as an open backlog item alongside that feature.

## Goals

- Type, correct, or clear an item's `source_url` from the row editor.
- Make it obvious which items have a source link, without hijacking the
  title text.

## Non-goals

- Checking that the URL resolves. This field exists precisely for pages
  we cannot fetch; a reachability check would defeat it.
- Any change to how enrichment or `url_import` set the field.

## Design

### 1. `source_url` becomes editable

Add `source_url` to `EDITABLE_FIELDS` in `humble_catalog/db.py`. That
single list drives three consumers, so one change covers all of them:
`/edit` accepts the field, `apply_hand_edit` snapshots it into
`pre_edit`, and `/revert` restores it.

Setting the URL therefore counts as a hand edit and freezes the row from
re-enrichment, exactly as editing any other field already does
(`enrich.py` skips rows where `pre_edit` is not null, "so typed-in work
is kept").

That freeze is deliberate. Making `source_url` an exception would split
`EDITABLE_FIELDS` from `pre_edit`, which are currently the same set, and
would leave the URL unrevertable. The general complaint it invites — "I
edited a row and now enrichment ignores it" — already has its own
backlog item, the enrichment-override toggle. Solving it here would
duplicate that badly. For the case that motivates this feature, the
freeze costs nothing: a 403 bot wall was never going to enrich anyway.

### 2. Revert compatibility

`/revert` restores every field in `EDITABLE_FIELDS` from the `pre_edit`
JSON via `snapshot.get(f)`, so a key missing from the snapshot reads as
`None` and is written as `NULL`.

Snapshots already stored in a live `catalog.db` were written before
`source_url` joined the list and do not contain the key. Adding the
field naively would therefore **wipe the URL of any previously
hand-edited row on revert** — silent data loss, not an error.

Revert must write only the fields actually present in the snapshot,
leaving absent ones untouched. Snapshots written from now on contain
every field, so their behaviour is unchanged; only legacy rows differ,
and for them "leave it alone" is the correct reading of a key that was
never captured.

### 3. Validation

`/edit` validates `source_url` against `url_import.ALLOWED_SCHEMES`. A
non-`http(s)` value returns 400 with a clear message.

This is not theoretical: the value is rendered into an `href`, and
`esc()` escapes `& < > "` but does not filter schemes, so a typed
`javascript:` URL would execute on click. It is the same hole closed for
pasted URLs, reached through a different door — a hand edit rather than
a paste.

A value with no scheme gets `https://` prepended, matching `resolve()`.
An empty input clears the column to `NULL`, consistent with how `/edit`
already maps `""` to `None` for non-tag fields.

**Order matters, and is the easy thing to get wrong.** The scheme must
be read from the *raw* string before any prepending. `javascript:alert(1)`
contains no `://`, so prepending first yields
`https://javascript:alert(1)`, whose parsed scheme is `https` — a check
run after the prepend passes it. `resolve()` already handles this
correctly and carries a comment saying why.

To keep one implementation of that subtlety rather than two, extract it
from `resolve()` into a shared helper:

```python
url_import.normalize_url(url) -> str
```

It raises `ValueError` for a non-`http(s)` scheme and returns the URL
with `https://` prepended when no scheme is present. `resolve()` calls
it in place of its inline check; `/edit` calls it for `source_url`. The
existing scheme tests continue to cover `resolve()`; new tests cover the
helper directly.

### 4. UI

**Display mode.** Today the whole item name is the anchor. Instead the
name renders as plain text followed by `&#x2197;` (↗) linking to
`source_url` when one exists, with `title="Open source page"`.

This joins a cluster that already exists: the Name cell appends a
`review` badge, a redo button (`&#x27F3;`), an edit button
(`&#x270E;`), and an edited marker — each a small glyph carrying its
accessible name in a `title` attribute. The link icon is the missing
member of that set, and follows its accessibility convention. A
monochrome line glyph is used rather than a 🔗 emoji, which would render
in colour and clash with its neighbours.

The change is deliberately not scoped to hand-set URLs: every item with
a `source_url` renders this way, however the URL got there. Beyond
consistency, it means titles become ordinary selectable text — today,
selecting or copying a title risks following the link instead.

**Edit mode.** An `.edit-field` input with `data-f="source_url"` in the
Name cell, below the item name. The existing save handler collects every
`.edit-field` in the row generically, so it needs no change.

## Testing

New:

- `/edit` accepts and stores `source_url`.
- A `javascript:` URL returns 400 and does not reach the database.
- A scheme-less value is stored with `https://` prepended.
- `normalize_url` rejects `javascript:` and `data:` while accepting a
  bare host, pinning the parse-before-prepend order directly.
- An empty value clears the column to `NULL`.
- **Revert with a legacy snapshot** — a `pre_edit` JSON lacking the
  `source_url` key leaves the stored URL intact. This is the regression
  guard for the data loss described in section 2.
- `app.js` renders the `↗` link and no longer wraps the name in an
  anchor.

Changed: any existing assertion that the name renders as an anchor.
`test_webapp.py` and `test_enrich.py` already assert on `source_url`
values, but only as stored data, so they are unaffected.

Run `.venv/Scripts/python scripts/leak_check.py` after adding fixtures.

## Backlog

Move **Set an item's URL through a manual row edit** from Open to Done.
