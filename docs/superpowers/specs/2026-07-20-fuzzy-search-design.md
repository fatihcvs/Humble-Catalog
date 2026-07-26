# Fuzzy search matching — design

Date: 2026-07-20. Backlog item: "Fuzzy search matching" (Viewer UI).

## Problem

`#search` matches substrings of `item.name` and nothing else
([`app.js`][app] `visible()`). Four kinds of query find nothing today,
all of them things a person actually types:

- **Wrong word order or gaps** — "harbor quiet" for *The Quiet Harbor*,
  or skipping a middle word.
- **Typos** — one wrong character and the result set is empty.
- **Punctuation and accents** — a straight apostrophe against a curly
  one, or an unaccented spelling of an accented title.
- **Abbreviations** — initials standing in for a long title.

v1.12 narrowed `#search` to names only, because every other field it
used to span now has its own chip filter. That narrowing is what makes
this tractable: there is exactly one haystack to score against.

## Approach

A tiered scorer rather than a single similarity metric. Three tiers —
exact substring, token set, acronym — each occupying a **non-overlapping
score band**, with the best tier winning. Rejected alternatives:

- **Token-set only.** Solves order, gaps, typos, punctuation; drops
  abbreviations.
- **Subsequence (fzf-style) only.** Solves abbreviations and gaps
  elegantly, but a single typo breaks the chain and it is order-bound,
  so it fails two of the four cases.

Non-overlapping bands are the point. A blended weighted score of
dissimilar signals cannot be reasoned about and gets tuned against
anecdotes; bands turn the tolerance into one policy number (the cutoff)
and make every ordering question answerable in a word — "that one is an
acronym hit". They also guarantee that any exact substring outranks any
fuzzy match, so **no search that works today loses results or drops in
rank**.

## Scope

**In:** a `fuzzy.js` scorer module with a folding index map; relevance
ordering while a query is active; match highlighting in the Name column;
per-item fold caching; JS-harness support for the new module; a case
table of tests; docs.

**Out:** fuzzy matching in the chip filters or the title typeahead (they
filter a curated vocabulary, where substring is correct); any
server-side search; a user-facing strictness toggle or slider;
highlighting outside the Name column; fuzzy matching in dedupe candidate
generation (deliberately normalized-equality only — see the cross-bundle
dedupe design).

## 1. The scorer (`static/fuzzy.js`)

A new plain script alongside `autocomplete.js`, loaded before `app.js`
in `index.html`. It is pure and DOM-free: its own file rather than more
of `app.js` (already some 700 lines of DOM and state code), so it can be
table-tested in isolation.

One public entry point:

```js
Fuzzy.score(query, text) -> {score: 0..1, spans: [[start, end], ...]}
```

`spans` are half-open ranges into the **original** `text`, so the
renderer highlights without re-deriving anything. `score === 0` means no
match. A second export, `Fuzzy.fold(text) -> {text, map}`, is public so
callers can cache the fold (§3).

### 1.1 Folding

One pass over the original string, character by character. For each
character: NFD-normalize, strip `\p{Diacritic}`, lowercase; any
character that is neither a letter nor a digit becomes a single space.
Runs of spaces collapse; the result is trimmed. Every emitted character
records the index of the original character it came from, giving
`map[normalizedIndex] === originalIndex`.

One exception: **apostrophes are elided, not spaced** — straight `'`,
curly `’`, and the backtick-like variants all vanish, so "Innkeeper's"
folds to `innkeepers` rather than `innkeeper s`. Without this the two
apostrophe forms still agree with each other but neither agrees with
the apostrophe-free spelling a person types, which is the only spelling
this case exists to serve. It mirrors the dedupe key's precedent of
exempting characters (`#`, `+`) from the blanket punctuation rule.

The index map is why folding is hand-rolled rather than a chain of
`.replace()` calls: accent stripping changes string length, so without
it every span is displaced by however many accents precede it, and the
error is invisible in ASCII-only tests.

Ligatures that NFD does not decompose (`æ`, `ß`) fold to themselves.
Accepted: they are rare in titles and degrade to a near-miss in a lower
tier, not to a wrong answer.

### 1.2 Tiers

Query and text are both folded; tokens are the folded strings split on
spaces. All three tiers run and the highest score wins.

| Tier | Condition | Band |
|---|---|---|
| T1 exact | folded query is a substring of folded text | `0.90 + 0.10 × (qlen / textlen)` |
| T2 token set | every query token matches an unused text token | `0.45 + 0.40 × mean(token scores)` |
| T3 acronym | every query character matches a **word start**, in order | `0.40 + 0.10 × min(1, qchars / words)` |

**T1** spans are the single matched range. A full-title match approaches
`1.0`, a short fragment sits near `0.90`.

**T2** per-token score against its best text token: exact `1.0`, prefix
`0.9`, substring `0.75`, Levenshtein distance ≤ `k` → `0.6`. "Prefix"
holds in **either** direction (query token a prefix of the text token,
or the reverse), so both a half-typed word and a slightly over-typed one
land in the same tier. `k` is 1
for query tokens of 5 characters or fewer and 2 above — a
one-character difference in a short word is usually a different word
("cat"/"cut"), in a long word it is a slip. Assignment is greedy
best-first and each text token is consumed at most once. If **any**
query token finds no match the tier scores 0: AND semantics, matching
every other filter in the viewer. Spans are the matched text tokens'
full ranges, including for edit-distance matches.

Levenshtein is bounded: `if (Math.abs(a.length - b.length) > k) return
k + 1` before building any matrix. A length difference alone proves the
distance exceeds `k`, and this guard skips the matrix for the large
majority of token pairs — which matters because scoring runs on every
keystroke across the whole catalog.

**T3** matches the query with spaces removed, character by character in
order, against **word-start positions only** — not "preferring" them.
An earlier draft allowed mid-word matches with a partial-credit score,
but under the 0.40 cutoff every partial result was rejected anyway, so
the leniency bought nothing and only risked the tier degenerating into
"these letters appear somewhere", which matches most of a catalog. The
strict rule is also the one a person means by initials. Minimum two
characters. Spans are the matched positions, one per character.

### 1.3 Thresholds

- Global cutoff **0.40**: anything below scores as no match.
- Queries shorter than 3 characters use **T1 only**. A two-character
  acronym or token match would hit a large fraction of the catalog.

## 2. Relevance ordering (`app.js`)

`visible()` gains two module-level maps, `matchScores` and `matchSpans`
(both id-keyed), cleared and refilled on every call. They follow the
existing pattern of module state consumed by an `innerHTML` rebuild, as
`editingTags` and `genresOpen` already do.

```js
const q = $("#search").value.trim();
matchScores.clear(); matchSpans.clear();
// inside the filter callback:
if (q) {
  const m = Fuzzy.score(q, i.name);
  if (m.score < 0.4) return false;
  matchScores.set(i.id, m.score);
  matchSpans.set(i.id, m.spans);
}
```

Clearing happens inside `visible()`, not in the search handler, because
`visible()` is also called by `bulkTarget()`. Spans surviving into a
later render is precisely the class of bug the JS harness exists to
catch.

A `relevanceSort` flag governs ordering: typing in `#search` sets it
true, clicking a column header sets it false. When it is true **and**
the query is non-empty, the comparator sorts by `matchScores`
descending with name ascending as the tiebreak; otherwise the existing
`sortValue()` path runs unchanged.

The flag is separate rather than a `sortKey = "relevance"` value, which
would force `sortValue()` to answer "what is the relevance of this
item" — a question about an item *and the current query*, not a
property of the item.

While relevance ordering is active no column header shows `▲`/`▼`, and
the count line reads `N / M items · by relevance`. Leaving a sort
indicator lit while sorting by something else would misreport what is
on screen.

## 3. Fold caching

Item names are folded once and cached in a `Map` keyed by item id,
cleared in `load()`. Folding is the per-keystroke cost that is trivially
avoidable; the tier matching is not, and is left alone.

## 4. Highlighting

A new `highlight(text, spans)` replaces `esc(i.name)` in the
non-editing row template. It walks the spans, applies `esc()` to every
piece — matched and unmatched alike — and wraps only the matched pieces
in `<mark>`. With no spans it returns exactly `esc(text)`, so the
no-query path is byte-identical to today's output.

Escaping order is load-bearing. The tempting form,
`esc(name).replace(...)`, escapes first and matches second, so spans
computed against the raw string land at wrong offsets in the escaped
one, and any title containing `&` corrupts. Splitting on raw indices and
escaping each piece is the only correct ordering. `<mark>` is generated,
never interpolated from data.

The editing-row template keeps plain `esc`: highlighting a row being
typed into is noise.

`<mark>` gets a themed rule in `style.css` using existing custom
properties, so it works on both the light and dark tab of the theme
system and on zebra rows.

## 5. Testing

`tests/js/harness.mjs` currently stubs `Autocomplete` and loads only
`app.js`. It gains a preload that runs `fuzzy.js` in the same context
first and publishes `Fuzzy`, so tests reach the scorer directly and
`visible()` exercises the real thing rather than a stub.

New `tests/test_fuzzy_js.py`, a case table — the only sane shape for a
scoring function. Titles come from `docs/TEST-DATA.md`:

| Case | Query → title | Expect |
|---|---|---|
| exact substring | `quiet harbor` → *The Quiet Harbor: A Novel* | T1 band |
| word order | `harbor quiet` → *The Quiet Harbor: A Novel* | T2 band |
| gap | `endless inferno` → *The Endless Wars: Inferno!* | T2 band |
| typo | `monfall` → *MOONFALL, Vol. 1* | T2 band |
| punctuation | `innkeepers ledger` → both *Innkeeper's Ledger* forms | T1 band |
| accent | `cafe broken` → *Café of Broken Clocks* | T2 band |
| acronym | `woe` → *The World of Examplia* | T3 band |
| negative | `axebearer` → *The Quiet Harbor: A Novel* | below cutoff |

Assertions are on **bands**, not exact scores: a literal `0.87` pins an
arithmetic accident, while "this landed in the token tier" pins the
promised behaviour.

Also covered:

- Band ordering: one query across three titles ranks T1 > T2 > T3.
- Span offsets land on correct original indices for an accented title
  and an apostrophe title. These two inputs are the only ones where the
  index map can be wrong; an ASCII-only test passes against a completely
  broken map.
- `highlight()` escapes a title containing `<` and `&` while marking a
  span, and returns `esc(text)` unchanged when given no spans.
- Queries of 1–2 characters never reach T2 or T3.
- The negative case, which is the one that matters most: fuzzy
  matching's failure mode is not missing a result, it is returning
  everything. A cutoff with no test is a cutoff that drifts.

Existing suites: `test_webapp.py` gains the `<script
src="/static/fuzzy.js">` assertion; `test_webapp_js.py` gains a
relevance-ordering test through the real `visible()` and a check that an
empty query leaves the column sort untouched.

## 6. Docs and privacy

- `docs/TEST-DATA.md` gains one accented invented e-book, **Café of
  Broken Clocks**, for accent folding and span offsets.
- README note on how search now behaves.
- `docs/BACKLOG.md`: the item moves to Done.
- `.venv/Scripts/python scripts/leak_check.py` runs before committing.
  It matches substrings, so it can flag ordinary prose; it is never
  piped.

[app]: ../../../humble_catalog/webapp/static/app.js
