# Multi-tag filtering in the catalog viewer (v1.8)

Approved 2026-07-18.

## Goal

The genre and bundle filters accept several tags at once, shown as
removable chips, with a per-field `all`/`any` toggle that decides
whether an item must carry every selected tag or at least one
(e.g. genre = Fantasy **and** Horror, or bundle = "The World of
Examplia" **or** "Humble Comics Bundle: Shadow Hound"). Entirely
client-side; no backend changes.

## Scope

**In:** chip-based multi-tag filter inputs for genre and bundle; a
per-field `all`/`any` combining toggle; a filter registry so future
fields (a planned custom user-tags column) plug in with one entry.

**Out (stay on the backlog):** autocomplete filters for
authors/narrator/series, tag counts in dropdowns, tag management,
the custom user-tags and user-notes columns themselves.

## Decisions settled

- Combining semantics within a field is a toggle, defaulting to `all`
  (match every selected tag). Across fields, filters continue to AND.
- Chips added by picking an autocomplete suggestion filter by exact
  tag membership. Free text still typed in the box acts as a live
  case-insensitive substring filter on top of the chips — the same
  dual behavior the single-tag filter has today.
- The toggle button only renders once a field has ≥ 2 chips; with
  fewer it cannot change the result.
- No URL/persistence of filter state (filters already reset on
  reload; unchanged).

## Design

### Filter registry

`app.js` replaces the hard-coded `tagFilters.genre` / `.bundle`
handling with a registry keyed by field name:

```js
const chipFilters = {
  genre:  {accessor: i => i.genre,                  chips: [], mode: "all", text: ""},
  bundle: {accessor: i => i.bundles.map(b => b.name), chips: [], mode: "all", text: ""},
};
```

`visible()` loops over `Object.values(chipFilters)` and applies, per
field, against `tags = accessor(item)`:

- if `chips.length`: `mode === "all"` → every chip in `tags`;
  `mode === "any"` → at least one chip in `tags`;
- if `text`: some tag contains `text` (case-insensitive substring).

Adding a future filterable column (custom user tags) means one new
registry entry plus its input element in `index.html` — the predicate
and the wiring loop need no changes.

### UI & wiring

- In `index.html`, each filter becomes an `.ac-wrap` container:
  selected chips (existing `.tag` style with the `.tag-x` remove
  button), the autocomplete text input, and the `all ⇄ any` toggle
  button.
- `wireFilter` generalizes to chip behavior: picking a suggestion
  appends a chip, clears the input text, and re-renders; the
  suggestion list excludes already-picked chips. Typing sets `text`
  live, as today.
- Chips and the toggle are re-rendered by a small
  `renderFilterChips()` helper (the filter bar sits outside the
  table, so `render()` calls it but the table `innerHTML` rebuild
  doesn't disturb the inputs — matching how the bar behaves today).
- Clicking `×` on a chip removes it; the toggle button flips
  `mode` and shows the current state (`all` / `any`).

## Testing

Front-end only, vanilla JS: hand-verify in the browser (chips add and
remove, `all` vs `any` on a two-genre item, substring text on top of
chips, bundle filter with a long bundle name, registry untouched by
table re-renders). This matches the project convention that the
no-harness UI is verified manually. No Python tests change.
