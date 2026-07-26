# Viewer visual improvements — design

Deliver the **Visual improvements** backlog item (Viewer UI section of
`docs/BACKLOG.md`): a light/dark theme, collapsible Review and Duplicates
panels, and layout work targeting three concrete grievances — panels
eating vertical space, a cramped filter bar, and a table that is hard to
scan. Approach: in-place changes to the existing zero-build vanilla stack
(`index.html` + `style.css` + `app.js`). No framework, no build step, no
new files.

## Scope and non-scope

In scope:

- OS-default-plus-toggle light/dark theme.
- Review and Duplicates panels become collapsible, collapsed by default.
- Sort affordance: a direction indicator on the active column, plus two
  more sortable columns.
- Filter bar de-cramping and table scannability (zebra rows, sticky
  header, tighter density).

Explicitly out of scope (YAGNI / deferred):

- Splitting `style.css` into multiple files or adopting a CSS framework
  (rejected approaches B and C).
- Fixing the sort comparator's array stringification (see below).
- Automated browser/UI tests. Verification is manual via the preview.
- Fuzzy search matching (separate backlog item).

## Theme system

Every color literal in `style.css` (`#fafafa`, `#222`, `#fff`,
`#d9534f`, `#f0a500`, the panel warn yellows `#c90`/`#fff8e6`, the badge
blue `#5bc0de`, tag/border greys, etc.) is hoisted to a semantic CSS
custom property on `:root` and referenced with `var(--…)`. The token set,
named by role rather than hue:

```
--bg, --surface, --surface-alt, --fg, --muted, --border,
--accent, --danger, --star, --badge,
--panel-warn-bg, --panel-warn-border, --tag-bg, --tag-border, --tag-fg
```

Two override sources, in this cascade order so an explicit choice always
wins over the OS preference:

1. `@media (prefers-color-scheme: dark) { :root { … } }` — redefines the
   tokens for dark. This is the default when the user has made no choice.
2. `:root[data-theme="dark"] { … }` and `:root[data-theme="light"] { … }`
   — redefine the tokens from an explicit toggle. Because an attribute
   selector on `:root` has higher specificity than the media query's
   `:root`, and both target the same properties, the explicit theme wins
   regardless of OS setting.

Toggle control: a single button in `<header>` (e.g. a sun/moon glyph).
On click it sets `document.documentElement.dataset.theme` to `"light"`
or `"dark"` and writes the value to `localStorage`. On load, a small
inline script in `<head>` reads `localStorage` and applies the attribute
**before first paint** to avoid a flash of the wrong theme; if no value
is stored, the attribute stays absent and the media query governs. A
third "clear" state (revert to OS) is not required — the toggle just
flips between light and dark, which is enough for the ask.

## Review and Duplicates accordions

Both panels currently render as always-open `<div>`s via `innerHTML`
(`loadReview` at `app.js`, `renderDupes` at `app.js`). The Genres panel
already solved collapse-with-`innerHTML` using a module-level flag
written back into each render and re-synced by a `toggle` listener
(`renderGenres`, the `genresOpen` variable). Review and Duplicates follow
that exact pattern:

- Add module-level `reviewOpen = false` and `dupesOpen = false`.
- Wrap each panel body in `<details${flag ? " open" : ""}><summary>…`.
- After render, attach a `toggle` listener that writes the flag back.

Both default collapsed. The `<summary>` carries a live count so a
collapsed panel still signals pending work, e.g. `⚠ 3 items need review`
and `⧉ 2 duplicate groups`. When the count is zero the panel stays
`hidden`, exactly as today — collapse never hides the zero-state signal
because there is none to show.

## Sort affordance

Column sorting already works: clicking a `th[data-sort]` toggles
`sortKey`/`sortAsc` (`app.js`) and the render sorts on it (`app.js`).
The gap is purely visual — nothing shows which column is sorted or in
which direction, so the feature is undiscoverable. Fixes:

- In `render()`, append a direction glyph (`▲` ascending / `▼`
  descending) to the active header's cell and give it a `.sorted` class
  for subtle emphasis (theme-aware via `--accent`). Only the active
  column shows a glyph; it updates as `sortKey`/`sortAsc` change.
- Add `data-sort` to two more headers in `index.html`: **Narrator/Artist**
  (`data-sort="narrator"`) and **Bundle** (`data-sort="bundle"`).
- **My tags** and **Notes** stay unsortable — they are multi-value /
  freeform and sort poorly; leaving them out is deliberate.

Noted, not fixed: the comparator stringifies arrays, so `Genre` and
`Authors` sort by a comma-joined string (`String(["Fantasy","Horror"])`
→ `"Fantasy,Horror"`). Crude but functional; out of scope here.

## Filter bar de-cramping

Keep the existing `#controls` flex-wrap layout — no markup restructure
beyond optionally wrapping logical groups in a `<span>`. Reduce the
cramped feel with: a consistent control height, slightly larger `gap`,
and light visual grouping (spacing or a subtle divider) between the three
clusters — the search field, the type/flag selects, and the chip filters
— so the nine-input row reads as clusters instead of one dense run. All
colors via tokens so it themes correctly.

## Table scannability

- Zebra striping: `tbody tr:nth-child(even)` uses `--surface-alt`.
- Sticky `<thead>` so column headers stay visible while scrolling the
  body (the `<header>` element is already sticky; the table head is not).
- Slightly tightened row padding for density without crowding.
- All theme-aware through the token set.

## Testing

`tests/test_webapp.py` is server/endpoint-focused; these changes are pure
CSS/DOM cosmetics with no Python surface, so no automated tests are added.
Verification is manual via the browser preview, covering:

- Light and dark, both via OS preference (`prefers-color-scheme`) and via
  the toggle overriding it, including reload persistence and no
  flash-of-wrong-theme on load.
- Review and Duplicates collapse/expand, default collapsed, correct
  counts in the summary, and zero-state still hides the panel.
- Sort glyph appears on the active column, flips direction on re-click,
  and the two newly sortable columns (Narrator, Bundle) sort.
- Responsive width: the filter bar still wraps sanely at narrow widths.

## Privacy

No catalog data appears in this spec, and none is introduced into the
repo by the change (styling and DOM only). The example counts and panel
labels above are invented. Complies with the standing privacy order in
`CLAUDE.md`.
