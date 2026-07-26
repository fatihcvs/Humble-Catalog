# Notes filter — design

Make `user_comment` searchable through its own text filter in the filter
bar, rather than by widening the search box.

## Why not the search box

The backlog recorded this as "`#search` does not look at
`user_comment`", which reads as an instruction to widen the search box.
That would partially reverse a deliberate decision: v1.12 narrowed
`#search` to names only, and the comment at `app.js` says why — "every
other field it used to span now has its own filter, so a catch-all here
would just duplicate them."

So notes get a filter, like every other field. `#search` stays
names-only.

The rationale still holds for a free-text field, with one adjustment:
notes are a bad fit for *chips*, because a dropdown suggesting whole
note bodies is useless. They are a fine fit for the free-text half of a
filter, which the registry already supports.

## The registry entry

`chipFilters` entries already carry `text` alongside `chips`, and
`passesChipFilters` applies it as a case-insensitive substring match. So
this is one more entry, wrapping the scalar the way `series` and
`publisher` do so the array contract every consumer relies on still
holds:

```js
// Free text, not a vocabulary: suggesting whole notes as chips would be
// useless, so this filters on typed text only.
user_comment: {accessor: i => i.user_comment ? [i.user_comment] : [],
               chips: [], mode: "any", text: "", scalar: true, textOnly: true},
```

And one input in the filter bar, after "My tags":

```html
<span class="chip-filter ac-wrap" data-field="user_comment"><input id="f-notes" placeholder="Notes..." size="16"></span>
```

## The one new behaviour

`wireChipFilter` skips `Autocomplete.attach` when `textOnly` is set,
keeping the `input` listener that drives `f.text`.

`renderFilterChips` needs no change: `chips` stays empty, so it renders
no chips, and the existing `f.chips.length >= 2` guard already withholds
the all/any toggle.

`scalar` is set as well as `textOnly`. They mean different things —
`scalar` marks one-value-per-item (already used by `series` and
`publisher` to hide a toggle that would be unsatisfiable), while
`textOnly` suppresses the vocabulary UI. A field can be scalar without
being text-only, so they do not collapse into one flag.

## Matching

The existing `f.text` path: case-insensitive substring, ANDed with every
other filter, as `passesChipFilters` already does for every field.

An item with no note yields an empty accessor result, so it never
matches a non-empty query. No special-casing, and no way for a blank
note to look like a match.

## Testing

The node harness (`tests/js/harness.mjs`) makes this behaviourally
testable, so it is tested for behaviour rather than by grepping:

- a note matches a substring of itself,
- matching ignores case,
- an item with `user_comment: null` never matches a non-empty query,
- an empty query matches everything, including un-noted items,
- the filter ANDs with a user-tag chip rather than widening the result.

Plus text assertions matching the existing convention: the registry
entry exists, and the input is present in `index.html`.

Tests use invented data from `docs/TEST-DATA.md`, and
`scripts/leak_check.py` runs before committing.

## Out of scope

- **A "Has notes" flag** in the `#f-flag` dropdown, alongside "Unrated
  by me". A plausible adjacent want and about three lines, but it is a
  new flag rather than the search this design is for. Recorded in
  `BACKLOG.md`.
- **Widening `#search`.** Covered above.
- **Fuzzy matching.** The backlog pairs comment search with fuzzy search
  on the grounds that both change what the search covers. That pairing
  was a guess, and this design does not depend on it: substring matching
  here is the same matching every other text filter already does.
