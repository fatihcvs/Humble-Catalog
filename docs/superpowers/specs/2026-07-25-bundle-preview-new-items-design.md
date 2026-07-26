# Bundle preview: listing what you would gain — design

Date: 2026-07-25

Extends `2026-07-25-bundle-preview-design.md`.

## Problem

The shipped preview answers "how many" and never "which". A tier reads
`owned 21  new 1`, which settles the buying decision but leaves the
obvious next question unanswered: *what is the one new book?*

The data is already half present. `preview()` returns `new_items` per
tier — a list of machine_names — but no surface renders it, and a
machine_name (`oldmanswar_johnscalzi`) is not a thing anyone reads. So
the field costs payload without earning anything.

## Goal

Under each tier, the names of the items that tier would gain you.

Owned items are deliberately **not** listed. The `new` list is the one
the decision turns on, and it is shortest exactly when the decision is
hardest — a bundle worth buying has few owned items and many new ones,
but a bundle worth *skipping* has the reverse, so listing "new" keeps
the output short in the case where you are dithering. Listing what you
already own answers a different question (*do I trust this count?*) and
stays unbuilt until that question is actually felt.

## The tier problem

Tiers are cumulative: the €19.63 tier's item list contains the €5.45
tier's. Rendering each tier's full new-list would therefore print the
same titles once per tier — 35 + 24 + 11 = 70 lines to convey 35 books,
with no signal about which tier is responsible for what.

So each tier lists only what it **adds over every cheaper tier**. The
lists are disjoint, they sum to the top tier's `new` count, and each one
answers the question being asked at that row: *is the step from €13.13
to €19.63 worth it?* On a re-run bundle the top row shows one title, and
that single line is the entire story.

### Cumulative count, incremental list

The `new` count stays **cumulative** — it is the answer to "what do I
get for this price", which is the number being decided on. The list
beneath it is **incremental**. The two therefore disagree on every tier
but the cheapest, by design, so the list carries a heading naming what
it is rather than appearing as bare titles under a count it contradicts.

### Computing it

Walk the tiers cheapest-first, subtracting a running set of names
already listed:

```python
seen = set()
for tier in sorted(tiers, key=price):          # cheapest first
    tier["adds"] = sorted(names(tier.new_items - seen))
    seen |= set(tier.new_items)
```

Not a difference against the next tier down. Both give the same answer
while the tiers nest, but a running set also holds if Humble ever ships
a tier that is not a strict superset — a bonus tier would make the
pairwise version emit a title twice, silently. The cost is one set.

## Report shape

Each tier gains `adds` and **loses** `new_items`:

```python
{"price": 21.90, "total": 35, "owned": 12, "new": 23,
 "adds": ["Building Widget Services", "The Hollow Crypt", ...]}
```

A replacement rather than an addition. `new_items` ships machine_names
that no consumer has ever rendered; keeping both would put two lists per
tier on the wire to serve one. Names come from `tier_item_data`'s
`human_name`, falling back to the machine_name if a page ever omits it.

Sorted alphabetically, not in bundle order. The list is scanned — *is
the one I want in here?* — rather than read start to finish, and Humble's
own ordering is a marketing decision that carries no meaning for this
question.

## CLI

Indented beneath each tier, and omitted entirely where a tier adds
nothing, so a bundle you own outright still prints three clean rows:

```
Humble Book Bundle: The World of Examplia
https://www.humblebundle.com/books/the-world-of-examplia-books

  €21.90    6 items    owned 2   new 4
              adds 3 new:
                Moonfall Vol. 1-3
                The Hollow Crypt
                Unrelated Book

  €13.13    3 items    owned 2   new 1
              adds 1 new:
                Shadow Hound Vol. 1-6

   €5.47    1 item     owned 1   new 0
```

This is the committed `bundle_data.json` fixture, so the arithmetic is
checkable: 3 + 1 + 0 = 4, the top tier's cumulative `new`. The cheapest
tier adds nothing and therefore prints no block, while its `new 0` still
shows — the count and the list answer different questions.

No cap on the list. It is a terminal, and scrolling is how a long list
is read there.

## Viewer

The whole tier table first, then the lists beneath it — one `<section
class="bundle-adds">` per tier that adds anything, each headed by its own
price:

```html
<table class="bundle-tiers">…all three tier rows…</table>
<section class="bundle-adds">
  <h4>€21.90 adds 3 new</h4>
  <ul>…</ul>
</section>
```

**Revised after building it.** The first version put each list in a
`<tr class="bundle-adds"><td colspan="4">` directly beneath its own tier
row, which reads better on paper and failed in a browser: eight titles
between the first two prices pushed the cheapest tier about 500 px down,
so the three numbers the panel exists to compare were never on screen
together. Measured at 537 px of content in a 229 px panel.

The comparison is the thing that must not scroll; the detail may. So the
table stays whole at the top (~100 px, always visible) and the lists
follow. The cost is that a list is no longer adjacent to its row, which
is why each heading repeats the price.

The list is multi-column (`columns: 18rem`), not one tall column. 25
titles ran 500 px stacked; at ~1200 px of panel width with short titles
that height was self-inflicted. A column *width* rather than a column
count means the browser fits as many as the space allows and falls back
to one on a narrow window.

`#bundle-panel` joins the `max-height: 50%; overflow: auto` rule that
`#review-panel`, `#dupes-panel` and `#stats-panel` already share
(`style.css:95`). Note this alone did **not** solve the problem above —
the panel was inside its cap and still unusable, because the fault was
ordering, not total height. It is fixed here anyway: it is a latent bug
in the shipped panel, invisible only because the panel was 98 px tall.

While the panel is open the table is squeezed to roughly 40 px. Accepted:
the panel is a deliberate, collapsible analysis view, and the table is
not what is being read at that moment.

`#bundle-panel` joins the `max-height: 50%; overflow: auto` rule that
`#review-panel`, `#dupes-panel` and `#stats-panel` already share
(`style.css:95`). Its omission is invisible today because the panel is
98 px tall, but a 35-item list would push the table off screen — the
panel must scroll internally rather than growing without bound. This is
a latent bug in the shipped panel, fixed here because this change is
what would expose it.

No show-all/collapse control. The three sibling panels solve the same
problem by scrolling, and a preview-plus-expand would add module state
for a list that is already bounded by the size of a bundle.

## Testing

The incremental split is the whole risk, so it is what the tests pin:

- a tier that adds nothing renders no list (CLI prints no block, the
  viewer emits no `bundle-adds` row)
- the lists across tiers are pairwise disjoint
- they sum to the top tier's `new` count
- a non-nested tier — one carrying an item no richer tier has — does not
  cause a title to appear twice
- an owned item never appears in any list
- `adds` holds display names, never machine_names
- names sort alphabetically
- `#bundle-panel` carries the max-height rule (a CSS assertion, like the
  existing `.stat-jump` colour test, since the JS harness has no
  computed styles)

## Out of scope

- **Listing what you already own.** A different question — *do I trust
  this count?* — and the answer to it is a second list on every tier.
  Revisit if the counts ever feel unbelievable.
- **Per-item detail** (cover, author, format) in the list. Names answer
  "which books"; anything more rebuilds the catalog table inside a
  panel.
- **Linking a new item anywhere.** It is not in the catalog by
  definition, so there is no row to link to.
