# Autocomplete filters for authors/narrator/series — design

Date: 2026-07-19. Backlog item: "Autocomplete filters for
authors/series — these filters still use the old mechanism; genre and
bundle already have autocomplete inputs" (deferred from multi-value
tags, `2026-07-18-multi-value-tags-design.md`, and restated as
"authors/narrator/series" in `2026-07-18-multi-tag-filtering-design.md`).

## Goal

Give authors, narrator, and series the same chip-filter treatment
genre and bundle got in v1.8: an autocomplete input above the table
where picking a suggestion adds an exact-match chip, with free text
acting as a live substring filter on top.

Today these fields are reachable only through the `#search` box, which
substring-matches a joined haystack of every text field. That finds
`Alex Penner` but cannot express "items by Alex Penner" as a durable,
combinable filter, and it offers no vocabulary — the user must already
know how the name is spelled.

Separately, and for the same "I only half-remember it" reason, the
search box gains title suggestions.

## Scope

Chip filters are added for:

- `authors` (array)
- `narrator` (array; the column is labelled "Narrator/Artist" and also
  carries music artists, but the filter is labelled `Narrator...` to
  match the row editor's existing vocabulary)
- `series` (scalar)

The search box gains a title typeahead — suggestions only, no chips.

Out of scope: `illustrator` and `publisher` filters. `publisher` is a
low-cardinality scalar that likely wants a `<select>` rather than a
chip filter; that is a separate decision, not a sweep-in.

## Why title is not a chip filter

Chip filters are built for many-to-few: many items share a tag, so
picking one groups a set. Title is one-to-one — cardinality equals the
item count, so a title chip selects a single row. That is a
jump-to-item interaction, not a filter.

Two existing features degrade on it. The `all ⇄ any` toggle would be
unsatisfiable (no item's name is both "The Starless War" and "Circle
of Storms"), and the v1.11 counts would render a muted `1` beside
every suggestion. Chips also commit exact values, which is the
opposite of what half-remembered recall needs.

The free-text half of a title chip filter would also duplicate
`#search`, which already substring-matches `i.name` as the first
element of its haystack.

So title gets a plain typeahead over the existing search box instead.
Fuzzy/typo-tolerant matching in `#search` was considered and deferred:
it replaces the matching rule for the whole box and needs a scoring
function plus a relevance sort to avoid making results noisier. The
typeahead does not block it — they compose.

## Design

No backend changes. All vocabularies and counts are computed
client-side from the loaded `items` array, as with genre and bundle.

### Filter registry (`app.js`)

Three new `chipFilters` entries:

```js
authors:  {accessor: i => i.authors,  chips: [], mode: "all", text: ""},
narrator: {accessor: i => i.narrator, chips: [], mode: "all", text: ""},
series:   {accessor: i => i.series ? [i.series] : [],
           chips: [], mode: "any", text: "", scalar: true},
```

The `series` accessor wraps the scalar in an array, empty when unset.
That single choice keeps it working unchanged in all three consumers:
`passesChipFilters`, the vocab builder's `flatMap` (which a bare
`null` would poison), and `tagCounts`.

Everything else is already field-generic: `passesChipFilters` iterates
the whole registry, and `wireChipFilter(field)` handles vocab,
chips, free text, and the v1.11 counts. Each new field needs one
`wireChipFilter` call.

### Scalar guard

An item belongs to exactly one series, so two series chips under `all`
mode is unsatisfiable — the table empties while a toggle sits there
implying the setting is legitimate. `renderFilterChips` already
suppresses the toggle when it cannot change the result (`chips.length
>= 2`); the `scalar` flag extends that same reasoning:

```js
if (f.chips.length >= 2 && !f.scalar)
```

`series` therefore stays in `any` mode permanently and never shows the
toggle. `authors` and `narrator` are arrays where `all` is genuinely
useful (co-authored and co-narrated items), so they keep it.

### Markup (`index.html`)

Three spans following the existing pattern, placed after the genre and
bundle spans so the filters stay contiguous, leaving `#f-flag`,
`#count`, and the export link at the end:

```html
<span class="chip-filter ac-wrap" data-field="authors"><input id="f-authors" placeholder="Author..." size="16"></span>
<span class="chip-filter ac-wrap" data-field="narrator"><input id="f-narrator" placeholder="Narrator..." size="14"></span>
<span class="chip-filter ac-wrap" data-field="series"><input id="f-series" placeholder="Series..." size="14"></span>
```

`#controls` is already `display: flex; flex-wrap: wrap`, so growing
from four controls to seven needs no layout work — they wrap.

### Search typeahead (`app.js`, `index.html`, `style.css`)

The dropdown positions itself against a `position: relative` wrapper,
so `#search` must move inside an `.ac-wrap`. It currently carries
`flex: 1 1 16rem` as a direct flex child of `#controls`; wrapping it
makes the span the flex child, so the sizing moves outward:

```html
<span id="search-wrap" class="ac-wrap"><input id="search" ...></span>
```

```css
#search-wrap { flex: 1 1 16rem; }
#search { width: 100%; padding: .4rem; }
```

Without this the search box collapses to its intrinsic width and stops
growing.

```js
Autocomplete.attach(
  $("#search"),
  () => $("#search").value.trim().length < 2 ? []
        : [...new Set(items.map(i => i.name))].sort(),
  (value, viaSuggestion) => {
    if (viaSuggestion) $("#search").value = value;
    render();
  });
```

Three deliberate details:

- **The `length < 2` guard.** `Autocomplete` calls `show()` on `focus`
  as well as `input`, and `#search` has `autofocus`. Without the
  guard, every page load would drop a dropdown of twelve arbitrary
  titles over the table. Returning an empty list makes `show()` bail.
- **The `Set`.** De-dupes titles shared across bundles. Picking one
  still leaves every identically-titled item visible, which is useful
  — it surfaces the cross-bundle copies rather than hiding them.
- **No `countsFn`.** Omitted so no `1` is rendered beside every title.

Suggestions are matched with `includes`, not `startsWith`, so a
fragment from the middle of a title matches — which is what
half-remembered recall needs. Picking writes the full title into the
box; the item stays found via the existing haystack match. Typing
without picking takes the `viaSuggestion === false` path, where the
existing `#search` input listener has already updated state, so the
`render()` is idempotent.

## Testing

Following the repo's frontend-test convention (static-content
assertions in `tests/test_webapp.py`, each with an inline comment
recording why the marker matters):

- Extend `test_index_has_autocomplete_filters` with `<input
  id="f-authors"`, `<input id="f-narrator"`, `<input id="f-series"`,
  and assert `#search` sits inside `id="search-wrap"`.
- `app.js` registers `authors`, `narrator`, and `series` in
  `chipFilters` and calls `wireChipFilter` for each.
- `app.js` carries the `scalar` flag and `renderFilterChips` gates the
  toggle on it.
- `app.js` attaches an autocomplete to `#search` with a
  minimum-length guard and passes no counts source.

Manual verification in the running viewer, where the real behaviour
lives:

1. The search box is full-width and shows no dropdown on page load
   despite `autofocus`; typing two characters produces title
   suggestions; picking one fills the box and narrows the table.
2. Each new filter suggests values with counts; picking adds a chip.
3. Two author chips show the `all ⇄ any` toggle; two series chips show
   no toggle and behave as `any`.
4. The new filters compose with each other and with genre/bundle.

Run `.venv/Scripts/python scripts/leak_check.py` — this change touches
tests and docs.

## Out of scope

- `illustrator` and `publisher` filters.
- Fuzzy/typo-tolerant search matching.
- Title chips, and counts on title suggestions.
- Sorting suggestions by count (alphabetical order stays).
- Any backend filtering; everything remains client-side.
