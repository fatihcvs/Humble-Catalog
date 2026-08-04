# Humble Choice ownership check — design

Date: 2026-08-04

## Problem

`bundle` answers "how much of this bundle do I already own?" for a live
bundle URL. It cannot be pointed at Humble Choice, which the bundle
preview spec listed as out of scope.

Choice is sold as one price for the whole month, so the decision it
poses is binary — buy this month, or skip it — with none of the tier
arithmetic a bundle needs. The catalog holds the answer and cannot be
asked, and the month expires whether or not the question gets answered.

Ownership here is deliberately **source-agnostic**. A game already held
counts the same whether it arrived in an earlier Choice month, in an
ordinary bundle, or was bought elsewhere entirely; and a game held as a
Humble key counts whether or not that key was ever claimed, because an
unclaimed key is value already paid for and still collectable. The
report never distinguishes provenance in its counts.

Read-only. Nothing is written to `catalog.db`.

## Why this cannot reuse `fetch_bundle`

A bundle page embeds its whole catalog in
`<script id="webpack-bundle-page-data">`, server-rendered and readable
with no cookies. That is what lets `bundle` run unauthenticated through
`url_import._fetch_html`.

Choice does not. Verified during design: signed out, neither
`/membership` nor a past month page carries any `application/json` blob
at all — no `content_choice_data`, no `contentChoiceOptions`, nothing.
The visible month contents are rendered by JavaScript from data that
arrives later, so a plain `requests.get` sees a marketing shell. A naive
port of `fetch_bundle` would fail with its own "no bundle data found"
error on every run.

Authenticated, the same page carries what is needed:

```
<script id="webpack-subscriber-hub-data" type="application/json"> … </script>
  → baseSubscriptionPrice|money         # {currency, amount}
  → contentChoiceOptions
      → gamekey                         # this month's order key
      → title                           # the month
      → contentChoiceData
          → game_data       {machine_name: {title, tpkds, …}}
          → display_order   [machine_name, …]
          → extras          [{human_name, machine_name, class, …}]
      → contentChoiceState.initial.choices_made
```

Note that the price sits at the **top level**, outside
`contentChoiceOptions`. That is why `fetch_choice` returns the whole hub
mapping rather than the `contentChoiceOptions` sub-dict: returning the
narrower thing would put the price out of `preview`'s reach and force a
second read of the page to recover it.

Each `game_data` entry carries `title`, `display_item_machine_name`,
`tpkds`, `delivery_methods`, `platforms`, `msrp|money`, `genres` and
`developers`. A month measured during design offered nine games and two
extras, delivering on `steam` and `other-key`.

So this feature needs the saved Humble session — the same one `extract`
and `harvest` already use — and that is the one real architectural
difference from `bundle`.

## Why the answer is approximate, and says so

Books read exactly in a bundle because a re-run bundle resells the *same
subproduct*, so `machine_name` is a shared id and ownership is a set
intersection.

Choice has no such id to lean on. It offers freshly negotiated games
each month, so its identifiers do not collide with anything already in
the catalog. Measured against the real catalog during design: of the
nine offered games, **zero** matched by choice `machine_name`, zero by
`display_item_machine_name`, and zero of the ten distinct `tpkds`
machine names matched a stored external key. That is not a defect to be
fixed later; it is the expected result, and any implementation will see
it too. Exact matching is simply unavailable on this surface.

Ownership is therefore decided by **title**, through the existing
`game_match.classify_game` — the same scorer, the same measured cutoffs
(`GAME_OWNED` 92, `GAME_POSSIBLE` 80), and the same sequel guard that
keeps *Widget Quest II* from reading as the owned *Widget Quest*. None
of that is re-derived here; a second copy of those numbers would be a
second thing to keep true.

The consequence travels with the report: it carries the same
`APPROXIMATE` warning the bundle game path prints, and a `possible` is
counted as **neither owned nor new**. Same stance and same reason as
`bundle_preview` — when the question is "should I buy this", the
expensive mistake is recommending a second purchase, so the band where
the tool will not guess must not be silently resolved in either
direction.

## Module

New `humble_catalog/choice_preview.py`, split at the network seam
exactly as `bundle_preview` is, and for the same payoff:

```python
fetch_choice(client=None) -> dict    # network: GET + parse the hub blob
preview(conn, hub) -> dict           # pure: no network, no writes
format_report(report, encoding) -> str
run()
```

`hub` is the parsed `webpack-subscriber-hub-data` mapping, from which
`preview` reads the month (`contentChoiceOptions`) and the price
(`baseSubscriptionPrice|money`).

`preview` takes a plain dict, so every counting rule — an owned game, an
edition suffix over an owned base, a sequel, the middle band, a
key-only game, a store with no importer — is testable from a committed
fixture with no network and no Humble session.

Every read of the blob goes through `shapes`. It is third-party content,
the envelope classes it adversarial, and `x or {}` is not a type check:
a non-empty list is truthy and reaches the attribute access, which is
the trap `bundle_preview.preview` documents. In particular
`display_order` is read with `shapes.text_list`, never `as_list`, so a
list field arriving unwrapped as a bare string is one name and never its
characters.

The ownership pools are reused, not reimplemented:
`bundle_preview._owned_games`, `bundle_preview._keyed_games` and
`game_match.prepare_pool`. Keys are tried only after the imported
libraries have said "new", so a game both keyed and activated reports as
the plain library match it is, and the key-only list stays what it
claims to be.

### Fetching

`HumbleClient._get` requires a JSON content type and raises `NotLoggedIn`
on anything else, so it cannot fetch an HTML page. Rather than bypass it
with a bare `client.http.get` at the call site, `HumbleClient` gains:

```python
get_page(path) -> str      # HTML sibling of _get
```

which shares `_get`'s inter-request delay. Politeness toward Humble stays
a property of the client rather than something each caller remembers.

**`fetch_choice` never logs in interactively.** Given no client it builds
one from the saved cookies, checks `logged_in()`, and raises
`humble_api.NotLoggedIn` if the session is stale. This is what makes the
function safe to call from a web request; see the surface section.

A page carrying no `webpack-subscriber-hub-data` blob raises
`ValueError`, as does a response whose blob holds no `contentChoiceData`
— which is what a month with nothing on offer, or an account that is not
a subscriber, will produce.

### What counts as owned

Three pools, checked in this order:

1. the imported game libraries (`games`), via `classify_game`
2. Humble store keys (`external_keys`), via `classify_game`, only where
   the libraries returned `new`
3. nothing else — there is no exact-id pass, for the reason above

An expired key still counts, for the reason `_keyed_games` already
documents: having paid for a game once is the answer to "should I buy
this month", whether or not the key can still be claimed. Excluding
expired keys would push the report toward recommending a second
purchase, the more expensive of the two available mistakes.

### Report shape

Flat — no tiers, one price:

```python
{
  "name": "Humble Choice: January 2031",
  "price": 11.99, "currency": "EUR",
  "total": 9, "owned": 3, "possible": 1, "new": 5,
  "owned_items": [...], "possible_items": [...], "new_items": [...],
  "keyed": 1, "keyed_items": [...],   # counted in owned, listed apart
  "extras": ["…human_name…"],         # listed, never counted
  "claimed": False,                   # choices_made, for this month
  "libraries": {...},                 # as bundle_preview reports them
  "unimported_stores": [...],
}
```

`price` is `baseSubscriptionPrice|money` — the list price of a month, not
necessarily what this account pays, since other billing tiers differ and
the blob describes those separately in `userSubscriptionPlan`. It is
printed as context for the counts and never used in a calculation, so the
distinction cannot corrupt a number; modelling the personal price would
be a second source of truth for no gain.

`owned`, `possible` and `new` partition the games and sum to `total`.
`keyed` is a subset of `owned` and is never added to it — the count
answers "how much of this do I already have", the list answers "and how
sure is that", since an unactivated key can be region-locked or dead in
a way a library entry cannot.

Lists are sorted case-insensitively by title rather than left in
`display_order`. That order is Humble's marketing decision, and it means
nothing for the way this list is actually read — scanned for whether a
particular game is in it. Same reasoning as `bundle_preview._adds`.

## Surface

Both, sharing `preview()`, so the CLI and the viewer cannot drift — the
arrangement the statistics panel settled on and the bundle preview kept.

### Where interactive login is allowed to happen

`humble_api.manual_login` ends in `proc.wait()`: it blocks until a human
closes a browser window. That is correct in a terminal and unacceptable
in a request handler, where it would hang the thread on a window the
server cannot see and the user may never have noticed.

So the interactive step lives only where a human and a terminal are:

- **`python -m humble_catalog choice`** calls `humble_api.ensure_login()`
  up front, as `extract` does, and passes the client to `fetch_choice`.
  An expired session prompts through the browser and the run continues.
- **`POST /api/choice-preview`** calls `fetch_choice()` with no client,
  catches `NotLoggedIn`, and answers **409** with
  `"Humble session expired -- run `python -m humble_catalog login`, then
  try again."` The server never spawns a browser and never blocks.

409 rather than 401: nothing about the *viewer's* own authorization is
wrong, and the fix is a command the owner runs elsewhere. Reusing 401
would invite a future reader to add a login prompt to the viewer, which
is the thing this design is avoiding.

`POST`, not `GET`, matching `/api/bundle-preview`: this is a credentialed
network action whose response is a fact about what the owner holds, and
neither belongs in a query string that reaches access logs and browser
history.

### CLI output

```
Humble Choice: January 2031   EUR 11.99   6 games
  owned 3    possible 1    new 2

  new (2):
    Lantern & Lockpick
    Widget Quest II

  owned (3):
    Neon Drifter
    Widget Quest: Definitive Edition
    Cinder Vale

  1 owned via a Humble key (not in any imported library):
    Cinder Vale  (steam key, Humble Game Bundle: Key Vault)

  1 possible (counted as neither owned nor new):
    Starfall Rally Turbo  ~  Starfall Rally  (0.86)

  Extras (not counted, 1):
    Sample Ambience Pack

  Game ownership is matched by title and is APPROXIMATE -- verify
  anything you would buy on.
```

The keyed game appears twice on purpose — once in `owned`, which is the
count, and once in the key list, which is the caveat. Printing it only in
the caveat block would make the owned list disagree with the owned
number.

As in `bundle`, a heading is omitted entirely when its list is empty, and
the currency symbol degrades to its ISO code at the CLI boundary when the
console encoding cannot carry it — the Windows console defaults to
cp437/cp850, neither of which has the euro sign, and `capsys` captures as
UTF-8 so no test observes this by accident.

Deliberately **no MSRP column**, though `msrp|money` is available per
game. Same reasoning that kept price-per-new-item out of the bundle
report: it is arithmetic the reader can do, and printing a large "value"
figure invites reading it as "worth buying" — exactly the misjudgement
this feature exists to correct.

### Viewer

A panel in the Bundles section, mirroring `#bundle-panel`'s markup and
open-state pattern, and fetch-on-demand like it — so it needs no
refresh-after-mutation wiring, holding no state that can go stale.

No URL input: Choice is always "this month", so the control is a single
**Check this month's Choice** button.

The panel renders the same fields, including the `APPROXIMATE` warning.
That caveat matters *more* here than in the terminal, not less: a
coloured count in a browser reads as more authoritative than the same
number in terminal output, and the number is a title-match estimate
either way.

### Extras are listed and never counted

The month's `extras` are coupon- and credit-class entries rather than
games. Nothing about them can be owned, so folding them into `total`
would corrupt every count derived from it. They are shown so the report
does not appear to be hiding part of the month.

### `other-key` is not a storefront

`delivery_methods` yields real stores alongside `other-key`. The
unimported-store warning exists to say "an item here was counted as new
by default because a store was never imported, and you should go import
it" — advice no importer can satisfy for `other-key`. It is excluded
from that warning, which is otherwise scoped exactly as
`bundle_preview` scopes it: only stores that still hold an unmatched
item, so a warning is never spent on a store whose every game was
already accounted for.

## Error handling

Thin, matching `bundle`.

- No blob, or a blob with no `contentChoiceData` → `ValueError`; the CLI
  prints it as a usage error, the route answers 400.
- Stale or missing session → `humble_api.NotLoggedIn`; the CLI logs in
  and retries, the route answers 409.
- HTTP and network failures propagate as themselves; the route answers
  502, keeping an upstream failure distinguishable from a refusal.

No caching, no persistence, no retry beyond the shared policy.

## Testing

Two committed fixtures, both built only from invented names in
`docs/TEST-DATA.md`:

- `tests/fixtures/choice_hub.json` — the `contentChoiceOptions` dict
  `fetch_choice` returns and `preview` consumes.
- `tests/fixtures/choice_page.html` — a minimal page wrapping that dict
  in the `webpack-subscriber-hub-data` script tag, for the parse test.
  Trimmed to the tag and enough markup to be realistic; the live page is
  ~600 KB and none of the rest is read.

`docs/TEST-DATA.md` gains the invented month name and any new game rows
the fixture needs, as the privacy rules require.

Cases:

- a title in an imported library reads **owned**
- an edition suffix over an owned base reads **owned**
  (*Widget Quest: Definitive Edition*)
- a sequel reads **new**, never as the owned base (*Widget Quest II*)
- the middle band reads **possible** and is counted as neither owned nor
  new (*Starfall Rally Turbo*)
- a key-only game reads **owned** and appears in `keyed_items`
  (*Cinder Vale*)
- a key on a store with no importer still reads owned (*Verdant Reach*)
- `owned + possible + new == total`, with `keyed` never added in
- extras appear in `extras` and in no count
- `other-key` never appears in `unimported_stores`
- a page with no blob raises `ValueError`
- `fetch_choice` raises `NotLoggedIn` when the session is stale, and the
  route turns that into 409 — from a stubbed `fetch_choice`, so the test
  needs no network and no session
- the CLI prints without raising when stdout cannot encode the currency
  symbol

## Privacy

No month, game title, price or report is written to `catalog.db` or to
any log. The route takes no URL and returns the report in a POST
response.

Both fixtures are anonymized to invented names before being committed —
the live blob describes a real offer and, once matched, the owner's real
library. `scripts/leak_check.py` covers them like any other fixture.

The design probes that produced the schema above printed structure only
— key names, types and container sizes, with string values redacted —
and were run from the scratchpad, never committed.

## Out of scope

- **Past or arbitrary months.** The subscriber hub serves the current
  month; addressing an arbitrary month is a different fetch and answers
  a question the owner has said they do not have.
- **Choice-specific history reporting.** Past Choice months already
  harvest as ordinary orders, and their games already count as owned
  through `external_keys`. Labelling them as Choice months would add a
  view, not an answer.
- **MSRP and value arithmetic**, per the CLI section.
- **Writing anything** — no watchlist, no preview history, no cache.
- **Acting on the month**: this reports, it never claims or buys.

## Build order

1. `preview()` + fixture tests. The counting is the risky part and is
   fully testable offline.
2. `HumbleClient.get_page`, `fetch_choice`, and the `choice` subcommand.
3. The viewer panel and `POST /api/choice-preview`.

Each step is independently useful, and the CLI proves the numbers can be
relied on before anything is spent on presentation.
