# Tag counts in autocomplete dropdowns — design

Date: 2026-07-19. Backlog item: "Tag counts in autocomplete dropdowns —
show how many items carry each suggested tag" (deferred from
multi-value tags, `2026-07-18-multi-value-tags-design.md`).

## Goal

When an autocomplete dropdown suggests a tag, show next to it how many
catalog items carry that tag, e.g. `Science Fiction  12`. This helps
the user pick the canonical spelling of a tag (the popular one) and
spot near-duplicates while editing.

## Scope

Counts appear in:

- the row-editor tag inputs (genre, authors, narrators/readers) — the
  inputs wired by `wireTagInputs()`;
- the two chip-filter inputs above the table (genre, bundle).

Counts do **not** appear in the duplicate-merge item picker: its
options are items, not tags, so a count is meaningless there.

Counts are **catalog-wide**, not restricted to the currently filtered
view — the same numbers the Genres panel shows. Recomputing them per
keystroke is fine; the vocab lists are already rebuilt per keystroke
from the same `items` array.

## Design

No backend changes. All suggestion vocabularies are computed
client-side from the loaded `items` array, and the Genres panel
already derives per-tag counts the same way.

### `autocomplete.js`

`Autocomplete.attach(input, optionsFn, onPick)` gains an optional
fourth argument:

```
Autocomplete.attach(input, optionsFn, onPick, countsFn)
  countsFn(): Map(tag -> item count), recomputed on every keystroke;
              omitted/undefined = no counts shown (dupe picker).
```

Rendering: when `countsFn` is given, each `.ac-item` renders the tag
text plus `<span class="ac-count">N</span>`.

Commit-value fix: today the Enter key commits `opts[sel].textContent`.
With a count span inside the item, `textContent` would include the
number, so every `.ac-item` now stores its value in `dataset.value`
and both commit paths (mousedown and Enter) read that. This is done
unconditionally so the no-counts call sites keep working identically.

### `app.js`

A small helper computes counts for a tag field:

```
const tagCounts = (accessor) => {
  const counts = new Map();
  for (const i of items)
    for (const t of accessor(i)) counts.set(t, (counts.get(t) || 0) + 1);
  return counts;
};
```

- `wireTagInputs()` passes `() => tagCounts(i => i[field] || [])`.
- `wireChipFilter(field)` passes `() => tagCounts(f.accessor)` —
  for the bundle filter this counts items per bundle.
- The dupe picker's `attach` calls are unchanged.

### `style.css`

`.ac-count` — muted color, pushed to the right of the row
(`float: right` or flex margin-left auto), small font.

## Testing

Following the repo's frontend-test convention (static-content
assertions in `tests/test_webapp.py`):

- `autocomplete.js` uses `dataset.value` for commits and renders an
  `ac-count` span when a counts source is provided.
- `app.js` passes a counts source to the tag-editor inputs and the
  chip filters.
- `style.css` styles `.ac-count`.

Manual verification in the running viewer: type in the genre filter,
see counts; pick a suggestion, confirm the committed chip has no
digits appended; dupe picker dropdown unchanged.

## Out of scope

- Sorting suggestions by count (alphabetical order stays).
- Counts filtered to the current view.
- Counts anywhere other than the inputs listed above.
