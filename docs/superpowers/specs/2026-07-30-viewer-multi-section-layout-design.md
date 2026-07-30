# Viewer multi-section layout

Breaking the viewer's one-page model into four hash-routed sections, and
folding the filter bar into a collapsible sidebar.

Status: design agreed 2026-07-30. Supersedes the implicit "everything on
one page" arrangement that has held since the viewer shipped.

## Why now

Two pressures, one structural and one already paid for.

**The backlog no longer fits.** The unredeemed key report is specced as a
viewer panel, and its hide/unhide companion as a second view carrying the
*same columns*. Stacked panels cannot express that: two views with
identical columns, both auto-showing above the table, read as one
duplicated table. The key report is the first backlog item the current
layout cannot absorb, and it is the next thing to be built.

**Stacking has already cost a redesign.** The bundle preview's own
retrospective records a layout reversed by measurement — content pushed
the three numbers the panel existed to compare off the screen, 537px of
content in a 229px panel, fixed by adding `#bundle-panel` to a shared
`max-height: 50%` rule and going multi-column. That rule exists only
because four panels compete for one viewport. Removing the competition
removes the class of bug, not just the instance.

The filter bar is a separate crowding: `index.html` holds roughly fifteen
controls in one flat wrapping row — search, type, rating, eight chip
filters, a flag select, five status chips, the column picker, export
format and the download button. Sections do not help it, because all of
it belongs to the table.

## Decisions

| Question | Decision | Rejected alternative |
|---|---|---|
| Split mechanism | Hash-routed sections in one page load | Separate Flask routes per page |
| Sections | Library, Maintenance, Keys, Bundles | Three sections merging Keys into Bundles |
| Panel notifications | Badge counts on the tabs | Keep panels auto-expanding; silent tabs |
| Filter bar | Collapsible sidebar in Library | "More filters" disclosure; leave as is |
| Module system | Classic scripts, shared global scope | ES modules with real exports |
| Versioning | `v0.1.0` marks the last one-page commit; `v0.2.0` lands the sections | A single tag; a descriptive non-version tag |

### Why hash routing rather than real pages

`load()` fetches the entire catalog from `/api/items` once and holds it in
an `items` array; every filter, sort and fuzzy search then runs
client-side over that array. Separate Flask routes would refetch and
re-fold the whole catalog on each navigation and re-initialise the shared
machinery — autocomplete, fuzzy, theme, chip-filter registry — per page.
The single in-memory catalog is the assumption the viewer's whole
interaction model rests on, so the split has to preserve it.

Hash routing also adds **no new server routes**. The exposure model
described in the README's "The viewer's exposure" section, and enforced by
the loopback-host check in `webapp/__init__.py`, is untouched by this
change.

### Why classic scripts rather than modules

Classic `<script>` tags share one global lexical environment. That is
already how `fuzzy.js` and `autocomplete.js` reach `app.js` — no imports
appear anywhere in the viewer. Splitting `app.js` along the same seam
therefore needs no export machinery.

It also keeps the test harness working. `tests/js/harness.mjs`
concatenates the viewer's sources into a single `vm` context and publishes
the top-level bindings with an appended string; `type="module"` would
break both halves of that at once. Staying classic is what makes this
refactor small.

## Architecture

### Sections

| Section | Route | Contents | Origin |
|---|---|---|---|
| Library | `#/library` | filter sidebar, table, bulk bar, columns/export toolbar, statistics as a collapsed `<details>` | today's `#controls`, `#bulk-bar`, `#catalog`, `#stats-panel` |
| Maintenance | `#/maintenance` | review queue, duplicates | `#review-panel`, `#dupes-panel` |
| Keys | `#/keys` | empty placeholder; future unredeemed key report and its hidden-rows companion | new |
| Bundles | `#/bundles` | URL form, preview panel | `#bundle-form`, `#bundle-panel` |

Keys ships **empty but wired**: the tab, the route and the badge hook
exist; the report itself is separate work. This is deliberate. A section
that is not the table exercises the shell's assumptions before the
feature that motivated the shell is built on top of it.

Statistics folds into Library as a collapsed `<details>` rather than
taking a section. It describes the catalog the table shows, and reading it
next to the table is the point.

### Routing

A `hashchange` listener maps the hash to exactly one visible section by
toggling `hidden` on the others. An unknown or absent hash falls back to
`#/library` without rewriting the URL. Back and forward work by
construction; a section is bookmarkable.

The current section is one new module-level variable, alongside the
existing `sortKey` and `sortAsc`. There is no prior notion of "which view
am I in" in the codebase, so this is genuinely new state rather than a
rename.

### Badges

A tab renders its pending count beside its name — `Maintenance 12` — and
shows no badge at zero. Counts come from data `load()` already gathers:
its guarded loop over `render`, `loadReview`, `loadDupes` and
`refreshStats` runs on page load and populates everything the badges need.
No new endpoint. When the key report lands it adds its count to the same
loop.

Badges replace the shove that auto-showing panels provide today. The
signal survives; the interruption does not.

### Filter sidebar

Search stays in the header — it is how most sessions start, and it is the
one control that should never be a click away. Type, rating, the eight
chip filters, the flag select and the status chips move into a left column
inside Library, collapsible by a toggle whose state persists in
`localStorage` next to the existing theme key.

Active filters continue to render as chips in the header. This is the rule
that makes collapsing safe: a folded sidebar must never hide a filter that
is silently narrowing the table.

Below roughly 900px the sidebar starts collapsed. That is the first
concrete step toward the standalone read-only phone viewer on the backlog,
taken here because a sidebar designed without it would have to be redone.

The column picker, export format select and download button group into a
right-aligned toolbar above the table — tooling, not filtering. The bulk
bar stays tied to selection where it is.

### File layout

`app.js` is 1261 lines and becomes classic scripts in load order:

| File | Responsibility |
|---|---|
| `shell.js` | routing, section visibility, badges, theme, run-status polling |
| `catalog.js` | table render, sort, chip filters, column picker, export, bulk tagging |
| `maintenance.js` | review queue, duplicates |
| `bundles.js` | bundle preview |
| `app.js` | shared helpers (`$`, `esc`, `load`, `post`), the GAPS and enrichment constants, and the boot call |

Each lands well under 500 lines. `autocomplete.js` and `fuzzy.js` are
unchanged.

The GAPS constant carries a comment requiring it to stay in step with the
flag filter's options and `stats.py`'s own list. It stays in `app.js`
because both `catalog.js` (the filter) and the statistics rendering read
it; splitting it would give the three-way agreement a fourth party.

## Testing

**The refactor's acceptance criterion is that every existing JS test
passes unchanged.** The file split is behaviour-preserving by definition,
so any test that needs editing to survive it indicates a mistake in the
split rather than a stale test.

`harness.mjs` takes an ordered list of source paths instead of one and
concatenates them; `js_harness.py`'s single-path constant becomes a list.
That is the whole test-infrastructure change.

New behaviour tests:

- a known hash shows exactly one section and hides the rest
- an unknown hash falls back to Library
- a badge renders a non-zero count and is absent at zero
- sidebar collapse persists across a reload
- an active filter still shows a header chip while the sidebar is collapsed

`test_webapp.py` is untouched: no server route changes, no new endpoints.

## Documentation and versioning

- `README.md` gains a short paragraph naming the four sections.
- `BACKLOG.md`'s key-report entry is annotated with the section it now
  lands in.
- `docs/screenshot-viewer.png` goes stale and is **left stale**.
  Re-shooting it requires the by-eye privacy pass the standing order
  demands — item counts, bundle names, ratings, tags and notes are all
  inferable from a viewer screenshot, and no automated check reads a PNG.
  That judgement belongs to the owner, so it is out of this change.

Tagging, both annotated:

- `v0.1.0` on the last one-page commit. `pyproject.toml` already reads
  `0.1.0`, so nothing is bumped; the tag is a named handle on the final
  one-page state to diff against or fall back to.
- `v0.2.0` on the commit that lands the sections, bumping
  `pyproject.toml` to `0.2.0` in that same commit so the tag and the
  package version never disagree.

These are the repository's first tags.

## Order of work

Three independently revertible steps:

1. **Split the files.** Pure refactor, no behaviour change, existing
   tests green.
2. **Add the shell.** Sections, routing, badges; panels stop
   auto-showing.
3. **Add the sidebar.** Filter bar reshaped, collapse persisted,
   responsive threshold.

## Out of scope

- The unredeemed key report itself, and its hide/unhide views. This
  change builds the section they will occupy.
- Bundle preview extensions — volume ranges, expired-bundle gap-finding.
  They grow the existing panel inside its new section.
- Any change to server routes, the exposure model, or the API.
- Re-shooting the committed screenshot.
- A full phone layout. The sidebar's collapse threshold is the only
  responsive work here.

## Risks

- **A section becomes a place things get forgotten.** Badges are the
  mitigation, which is why they are in this change rather than deferred.
- **The split makes a stale global harder to see.** Shared mutable state
  spread over five files is worse than over one. Mitigated by keeping the
  shared helpers and constants in a single `app.js` rather than letting
  each section grow its own copy.
- **The sidebar hides an active filter.** Mitigated by the header chips,
  which are already implemented and stay outside the sidebar.
