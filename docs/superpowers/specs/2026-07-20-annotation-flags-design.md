# Annotation flags — design

Date: 2026-07-20
Backlog item: **"Has notes" flag** (deferred from the notes filter,
`specs/2026-07-19-notes-filter-design.md`).

## Problem

`user_tags` and `user_comment` are the two user-owned columns. Both can
be *searched* — the user-tag chip filter matches named tags, the notes
text filter matches comment text — but neither can be asked the
membership question: *which items have I annotated at all?* An empty
query in either filter matches everything, un-annotated rows included,
so there is no way to see the annotated subset.

## What ships

Two new options in the `#f-flag` dropdown, after "Unrated by me":

| value | label | matches |
|---|---|---|
| `notes` | Has notes | `user_comment` is non-empty after trimming |
| `mytags` | Has my tags | `user_tags` has at least one entry |

Two separate flags rather than one combined "annotated" flag: a note and
a tag are different acts, and merging them would hide which one a row
actually has. The dropdown is single-select, so the two can never be
combined — accepted. Nothing in the flag list combines today.

Presence only. "Unrated by me" is an absence flag and the symmetric
"has no notes" is a plausible want, but an unproven one; it is two more
lines whenever it is actually missed.

## Approach

Two inline conditions in `visible()`, matching how the three existing
flags are written. The alternative considered was a `flagFilters`
predicate registry mirroring `chipFilters`. The chip filters earned
their registry by carrying autocomplete, chips, tag counts and an
all/any toggle apiece; a flag carries a one-line predicate, so
converting three working conditions buys nothing today.

## Changes

**`humble_catalog/webapp/static/index.html`** — two `<option>`s in the
`#f-flag` select. The values are new strings, so no previously selected
flag changes meaning.

**`humble_catalog/webapp/static/app.js`**, in `visible()` after the
`unrated` line:

```js
if (flag === "notes" && !(i.user_comment || "").trim()) return false;
if (flag === "mytags" && !(i.user_tags || []).length) return false;
```

Two defensive details, both earned by past bugs:

- `.trim()` — a comment saved as whitespace is not a note.
- `|| []` / `|| ""` — a partial payload from an older server has blanked
  this page before (see `tagBadges` and `person`, which carry the same
  guard).

**`tests/js/harness.mjs`** — publish a `setFlag` hook beside `setSearch`:

```js
setFlag: (v) => { document.querySelector("#f-flag").value = v; },
```

A test expression only has `app`, `dom` and `Fuzzy` in scope, so it
cannot reach `document` to set the select itself.

## Testing

`tests/test_webapp_js.py`, driving the real `visible()`:

- with flag `notes`, an item carrying a comment is returned and one with
  `user_comment: null` is not;
- a whitespace-only comment does not count as a note;
- with flag `mytags`, an item with one user tag is returned and one with
  `user_tags: []` is not;
- with no flag, every item is returned — the flags narrow, they do not
  reorder or otherwise change the baseline.

`tests/test_webapp.py` gains a text assertion that both `<option>`s are
present, matching the convention already used there for `#f-flag`.

Test data comes from `docs/TEST-DATA.md` (*The Quiet Harbor: A Novel*
and *Unrelated Book* suffice; no new entries needed). Comments and tags
in tests are invented — e.g. a comment of "lent to Sam Reader" and a
tag of "lent out", both already used in committed tests.
`.venv/Scripts/python scripts/leak_check.py` runs before committing.

## Docs

`docs/BACKLOG.md`: move the "Has notes" flag entry from Open to Done,
noting that it shipped as two flags rather than one.

## Out of scope

- **Absence flags** ("has no notes", "has no tags"). See above.
- **Combining flags.** Would mean turning the single select into a
  multi-select, which is a change to the filter bar's shape, not to
  this feature.
- **A flag registry.** See Approach.
