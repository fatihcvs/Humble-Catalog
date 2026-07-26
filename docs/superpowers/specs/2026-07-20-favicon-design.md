# Viewer favicon — design

Date: 2026-07-20. Follows the viewer visual improvements merged in
`viewer-visual-improvements` (commit `8b62460`).

## Goal

Give the viewer a favicon so the browser tab reads as a real
application rather than an unlabelled blank page.

## Constraints

- **No HumbleBundle artwork.** Not their logo, not a recolour of it,
  not a derivative. The mark is drawn from scratch in this repo, so
  there is no upstream rights-holder and nothing to attribute.
- **No new dependencies.** The project's runtime dependencies are
  `requests`, `flask`, `playwright`, `rapidfuzz`, `openpyxl`. Adding an
  imaging library for a one-off icon is disproportionate, so the
  generator writes PNG bytes using only `zlib` and `struct` from the
  standard library.
- **No build step.** `humble_catalog/webapp/static/` is served
  directly by Flask (`static_url_path="/static"`); generated icons are
  committed so `serve` works without ever running the generator.

## The mark

Three book spines standing on a shared baseline: two upright at
differing heights, one tipping over at the end of the shelf, as a
half-full bookshelf does. Legible as a single silhouette at 16&times;16,
says "catalog of books", and resembles nothing HumbleBundle uses.

Geometry lives on a 64&times;64 viewBox. Each spine is a rect standing on
`BASELINE`; a spine's `lean` rotates it about its own foot,
`(x, BASELINE)`, so the book stays planted on the shelf instead of
floating above it.

The count is three, not four. Gaps between spines are 4 user units,
which is a full device pixel at 16&times;16. A fourth spine would push the
gaps to roughly half a pixel, where they alias away and the mark
becomes a blob.

## Files

| Path | Role |
| --- | --- |
| `humble_catalog/webapp/static/favicon.svg` | The real icon. Recolours itself in dark mode. |
| `humble_catalog/webapp/static/favicon-32.png` | Fallback for browsers that ignore SVG favicons. |
| `scripts/make_favicon.py` | Generates both. Committed output; run only to re-tune. |
| `scripts/favicon_tuner.html` | Design tool. Sliders per spine, live light/dark previews, WCAG contrast readouts, and a true 16&times;16 rasterization at 8&times;. Emits the `SPINES` block. |

`favicon_tuner.html` is a dev tool, not part of the served app — it
lives in `scripts/`, fetches nothing, and opens straight from `file://`.
It installs the mark as its own favicon so the browser tab is a live
preview.

## Design

### `scripts/make_favicon.py`

A single module-level table drives everything:

```python
# (x, top_y, width, fill_light, fill_dark, lean_degrees)
# All spines stand on BASELINE; lean rotates about (x, BASELINE).
SPINES = [
    (6, 12, 13, "#2f9e28", "#63d452", 0),
    (23, 4, 13, "#d13a1e", "#ff8f70", 0),
    (40, 16, 12, "#7c3aed", "#c39cff", 17),
]
BASELINE = 58
CORNER_RADIUS = 1.5

# The PNG cannot carry a media query, so this single palette has to clear
# both a white and a dark tab strip.
PNG_FILLS = ["#3aa832", "#d6431f", "#9a5ff0"]
```

Green, red, purple — three hues, because three tints of one hue read as
a single object sliced into strips (a bar chart) rather than as three
separate books. These values satisfy every constraint below, all of
which `scripts/favicon_tuner.html` checks live.

### Palette constraints

A favicon is judged against the tab strip it sits in, not against the
page. Two backgrounds matter: white for light browser chrome and
roughly `#282b31` for dark.

1. **Every fill clears a contrast ratio of 3.0** against the background
   it will be seen on (WCAG 1.4.11, non-text contrast). Below that a
   spine starts dissolving and the silhouette loses a third of itself.
2. **Each dark fill is lighter than its light counterpart.** This is the
   entire purpose of shipping two palettes; a dark fill with lower
   relative luminance than its light-mode twin makes the icon *sink*
   into dark chrome instead of lifting off it.
3. **Dark fills stay in the same hue family as their light
   counterparts.** A hue shift between themes makes it read as a
   different mark rather than the same one relit.
4. **`PNG_FILLS` clears 3.0 against *both* backgrounds**, since the PNG
   carries no media query. That confines it to a relative-luminance band
   of roughly 0.174&ndash;0.300 — narrow, but workable.

Legibility at 16&times;16 is carried by luminance contrast against the
background, not by hue. Hue choice is therefore free within these
bounds.

### Why green / red / purple

Colour carries no *information* here — the spines are separated by gaps
and differ in height — so colour-vision deficiency costs character, not
meaning. It was still worth measuring, and the measurements were
surprising. Minimum pairwise CIE Lab ΔE under simulated deficiency
(Viénot for protanopia and deuteranopia, a linear approximation for
tritanopia):

| palette | normal | deuter. | protan. | tritan. | worst |
| --- | --- | --- | --- | --- | --- |
| green / red / **purple** (chosen) | 111.2 | 56.9 | 30.9 | 29.0 | **29.0** |
| green / red / blue | 111.2 | 71.6 | 30.9 | 28.8 | 28.8 |
| Okabe-Ito vermillion / purple / blue | 53.6 | 51.0 | 24.0 | 48.2 | 24.0 |
| **purple** / red / blue | 26.2 | 19.9 | 16.9 | 10.6 | **10.6** |

Two findings worth recording, because both contradict the obvious guess:

- **Purple must replace the blue, not the green.** Purple is red plus
  blue; placed *between* them it gives every dichromat three points on
  one compressed axis, and tritanopia — not the red/green axis everyone
  worries about — is what collapses it.
- **Red and green were never the problem.** They collide when they share
  lightness; here they do not, and lightness survives every form of
  colour blindness. Spacing hues matters less than spacing luminance.

The chosen triad also beats Okabe-Ito, which is tuned for the harder
problem of adjacent same-sized marks in a chart.

Two writers consume it:

**`write_svg(path)`** — string assembly. Emits one `<rect>` per spine
carrying a class `s0`, `s1`, … and an internal `<style>` block:

```
.s0{fill:<light>}...
@media (prefers-color-scheme:dark){.s0{fill:<dark>}...}
```

Browsers resolve that media query against the OS theme when rendering
the tab icon. This mirrors how `style.css` already themes the app, and
is the only mechanism available — a favicon renders outside the page's
CSS cascade, so it cannot read the app's custom properties or the
`data-theme` attribute the theme toggle sets.

**`write_png(path, size=32)`** — pure stdlib rasterizer:

1. Each spine's rect corners are rotated by `lean` about `(x, BASELINE)`
   into a four-point polygon.
2. Polygons are filled into an RGBA buffer at 4&times; supersampling using
   a point-in-polygon test per subsample, then box-averaged down. The
   averaging is what produces antialiased edges and partial alpha.
3. Spines composite in list order over full transparency.
4. The buffer is serialised as PNG: signature, `IHDR`, a
   `zlib.compress`ed `IDAT` of filter-type-0 scanlines, `IEND`, each
   chunk length-prefixed and CRC-suffixed via `struct` and
   `zlib.crc32`.

`CORNER_RADIUS` is deliberately ignored by the PNG path. At 32&times;32 a
radius of 1.5/64 works out to 0.75px — invisible — and implementing
rounded corners in a hand-written rasterizer buys nothing.

Determinism matters: the same `SPINES` table must produce byte-identical
files, so re-running the generator without editing values leaves the
working tree clean.

### `humble_catalog/webapp/static/index.html`

Two tags in `<head>`, after the stylesheet link:

```html
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/static/favicon-32.png" type="image/png" sizes="32x32">
```

Browsers supporting SVG favicons take the first and ignore the second.
Absolute `/static/` paths mean the bare `/favicon.ico` request path is
never involved, so no Flask route is needed — `static_url_path="/static"`
already serves both files.

## Testing

Following the repo's frontend-test convention (static-content assertions
in `tests/test_webapp.py`):

- `index.html` carries both `<link rel="icon">` tags.
- `favicon.svg` exists, is non-empty, and contains a
  `prefers-color-scheme:dark` block.
- `favicon-32.png` exists and starts with the PNG signature.

For the generator (new `tests/test_make_favicon.py`):

- `write_png` into `tmp_path` produces a file whose `IHDR` declares
  32&times;32 RGBA.
- `write_svg` emits one `<rect>` per entry in `SPINES`, and a spine with
  a non-zero `lean` gets a `rotate(... x BASELINE)` transform.
- Running both writers twice yields byte-identical output.

Manual verification: run the generator, start `serve`, confirm the tab
icon appears and flips palette when the OS theme changes.

## Out of scope

- `favicon.ico` — only needed by browsers predating SVG-favicon support
  (roughly pre-2022 Safari); the 32&times;32 PNG covers the same ground.
- `apple-touch-icon.png` — matters for iOS "Add to Home Screen"; this is
  a localhost desktop tool.
- A web app manifest / PWA install support.
- Any change to the header, the `<h1>`, or the in-page theme toggle.
