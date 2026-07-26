# Link-only URL fallback — design

Date: 2026-07-19.

## Problem

The review UI lets the user paste a source URL when automatic matching
fails. `url_import.resolve()` turns that URL into a candidate, and the
user confirms it with an **Apply** button.

That path dead-ends for storefronts with no public API. Pasting a URL
for an RPG supplement (say *The Hollow Crypt*) fails outright: the
storefront answers the scrape with a bot-wall status rather than
metadata, and the review item stays unresolved. The same applies to
publisher storefronts such as Pearson, which have no API and are not
registered handlers at all — `resolve()` raises `unsupported source
URL` for them.

In both cases the user has already done the hard part: they found the
right page. Losing that work because we cannot parse the page is the
wrong trade. The URL alone is worth keeping.

The backlog recorded this narrowly, as "handle a 503". That framing is
too small — an unsupported domain never returns 503, it never gets
fetched at all. This spec replaces that entry.

## Goals

- Any pasted URL can become an item's link, whatever the source.
- Where metadata *is* readable without an API, read it — a bare link is
  the consolation prize, not the target.
- Degradation is visible and confirmed, never silent.

## Non-goals

- Per-storefront scrapers. One generic path, no site-specific parsing.
- Bypassing bot protection. A site that rejects us is taken at its
  word; see "Hard rejections" below.
- Caching scraped HTML.

## Design

Three layers, tried in order.

### Layer 1 — registered handlers (unchanged)

The existing `_HANDLERS` map in `humble_catalog/url_import.py`: real
APIs returning structured metadata (Comic Vine, Hardcover, Open
Library, Google Books, Audible, O'Reilly).

A *malformed* URL for a known domain — a Comic Vine link with a broken
path — still raises `ValueError` and still surfaces as HTTP 400. Those
errors are specific and useful; the fallback must not swallow them.

### Layer 2 — generic OpenGraph scrape

`_drivethrurpg` becomes `_generic_og` and is removed from `_HANDLERS`.
Instead it is what `resolve()` does when no handler matches. DriveThruRPG
stops being a special case, and unregistered publisher storefronts start
working for free.

Nothing about the existing implementation was site-specific: it issues
one GET and reads `og:title` / `og:image` through `_og_meta`, which is
plain regex over HTML. OpenGraph tags are near-universal on product
pages because they drive social link previews.

Details:

- **Scheme allowlist.** Only `http` and `https`, rejected before any
  request is issued, and rejected again on the final URL after any
  redirects. Rejection raises `ValueError` (HTTP 400) — explicitly
  **not** `MetadataUnavailable`; see "Security" for why that
  distinction is load-bearing. Redirects are capped at 5.
- **Response cap.** Stream the body and abort past ~2 MB, and skip
  responses whose `Content-Type` is not HTML. Neither limit exists
  today; `resp.text` currently reads a body of any size and any type
  into memory before the regex runs.
- **`source` is the URL's hostname** (`"examplegames.com"`), not a
  literal `"web"`. Keeps provenance visible in the UI without needing a
  registry of names. The hostname is lowercased with a leading `www.`
  stripped — the same normalization `resolve()` already applies when
  matching handlers, so the two agree on what a host is called.
- **Title cleanup.** Strip a trailing ` | Site` or ` - Site` suffix when
  the tail matches the hostname, so `The Hollow Crypt | Example Games`
  becomes `The Hollow Crypt`. Deliberately conservative: titles that
  merely contain a colon or dash are untouched.
- **No caching.** `source_cache` is keyed by source+query and holds
  JSON. One-off user-initiated scrapes do not belong in it, and staying
  out preserves the existing invariant that a failed fetch leaves no
  trace to be replayed.

### Layer 3 — link-only fallback

A new exception, `url_import.MetadataUnavailable(reason)`, is raised
when we tried and genuinely could not extract: no `og:title`, retries
exhausted, or a hard rejection.

`resolve()` has no `item_id` and cannot know what the item is called, so
it cannot build the fallback candidate itself. The webapp route can.
The `fetch_url` route in `humble_catalog/webapp/__init__.py` catches
`MetadataUnavailable` and `requests.RequestException`, looks up the
item's existing Humble name, and returns a normal candidate:

- `title` — the item's existing name
- `url` — the pasted URL
- all other metadata fields `None`
- `link_only: true` and a human-readable `reason`

HTTP 200. This is a success with less data, not a failure.

Keeping `resolve()` a pure URL-to-candidate function and putting the
policy decision in the route is the natural seam: no new coupling, and
`url_import` stays independently testable.

## Retry policy

The retry loop currently lives inside `Source.get_json`
(`humble_catalog/sources/base.py`), welded to JSON parsing,
`source_cache`, and per-source throttling. The HTML path needs the same
policy without any of that.

Extract it to a module-level `_with_retries(send)` helper that both
paths call, so backoff is defined once.

Policy:

- 3 attempts.
- Retry `ConnectionError`, `Timeout`, and 5xx.
- Sleep `5 * 2**attempt` between attempts — 5s, then 10s.
- **Hard rejections (403, 401, 429, and every other 4xx) raise
  immediately**, falling straight through to link-only.

### Hard rejections

Bot walls typically answer with 403, not 503. Retrying a 403 cannot
succeed and only makes the user wait before being told no. This matches
the reasoning already in the code, where a 429 dead quota is called out
as not improving on retry. *Delve Deeper: Companion* is the fixture for
this case.

Sending a browser-like `User-Agent` to get past such a wall was
considered and rejected: that is evading a bot block, which is a
different thing from being resilient to a flaky server.

### On "exponential"

The existing schedule is `5 * (attempt + 1)` over `range(3)`, and
`attempt == 2` raises before sleeping — so the only sleeps are 5s and
10s. Exponential with the same base gives 5s and 10s. **The two are
identical at three attempts** and do not diverge until a fourth (15s
linear vs 20s exponential).

The rewrite is therefore behaviour-preserving, and is made for honesty
rather than effect: `5 * 2**attempt` states the intended policy, so
raising the attempt cap later behaves as the name promises instead of
quietly staying linear. Attempt count stays at 3 — with hard rejections
now failing fast, the slow path only triggers on genuine 5xx and
timeouts, and 15s is already a long time to block a review click.

## UI

`humble_catalog/webapp/static/app.js` renders the degraded case
distinctly, e.g.:

> Couldn't read metadata (403 from examplegames.com).
> Apply link only: **The Hollow Crypt**

It reuses the existing `.apply-fetched` button and the `/apply` path
unchanged. The user confirms, as with any other candidate.

Confirmation is required rather than automatic because with an
unsupported domain we cannot distinguish a valid product page from a
typo. Applying silently would attach a bad link and mark the item
resolved, with no metadata present to signal that anything went wrong.

## Security

### Threat model

The risk is not the reputable storefront the user meant to reach. It is
that this feature fetches and parses **whatever page the URL actually
resolves to** — which a typosquatted domain, a compromised page, or an
open redirect can control. The code must therefore be safe for
arbitrary HTML; reputable sites are safe as a consequence, not as an
assumption.

This also marks a shift in the codebase's trust model. Until now every
candidate field came from a registered API, so candidate text was
implicitly trusted. This feature is the first to route
attacker-controllable text into the same renderer, which changes which
escaping omissions matter.

### Escape `source` in the UI (regression this feature would introduce)

`app.js` renders the source unescaped:

```js
Apply: ${esc(c.title)} - ... (${c.source})
```

That is safe today only because `source` is always a hardcoded literal
from `_HANDLERS`. Layer 2 makes it a hostname taken from a pasted URL,
and `urlparse` performs no validation — `netloc` will carry `<` and `>`
through untouched. **`c.source` must be wrapped in `esc()`**, along with
the new `reason` string.

Note also that `esc()` escapes `& < > "` but not `'`. That is sound only
because every attribute in `app.js` is double-quoted. Any new attribute
this feature adds must keep that invariant.

### Rejected schemes must 400, never become link-only

An item's URL is rendered as `<a href="${esc(i.source_url)}">`. `esc()`
prevents breaking out of the attribute but does nothing about the
scheme: `javascript:...` survives escaping intact and executes on click.

So a non-`http(s)` URL must fail as `ValueError` → HTTP 400. Were it to
fall through to the link-only path instead, the URL would be stored as
the item's permanent link — stored XSS, one click away. This is why the
scheme rejection is deliberately *not* a `MetadataUnavailable`.

### SSRF — accepted, not mitigated

The feature issues server-side GETs to arbitrary user-supplied hosts,
including — via redirect — `127.0.0.1` and link-local addresses.

Judged acceptable here rather than filtered: the app binds localhost, is
single-user, holds no cloud credentials, and only GET endpoints are
reachable, all of which are read-only. Recorded as a conscious decision
so it can be revisited if any of those premises change. Blocking private
address ranges is the mitigation if so.

### Latent: `og:image` is stored but unused

`extra={"cover": ...}` is populated from `og:image`, but
`apply_candidate` never reads `extra`, so the value currently goes
nowhere. If it were later wired to `items.cover_url`, `_download_covers`
would fetch that attacker-supplied URL and write the bytes to disk. The
filename is generated as `{id}.jpg`, so there is no path-traversal risk,
but the fetch would be a second uncapped SSRF sink. Add a comment at
the assignment so nobody wires it up without revisiting this.

> **Update (2026-07-24):** cover filenames were re-keyed to
> `{slug}-{blake2b12}.jpg` by
> `superpowers/specs/2026-07-24-catalog-reset-rebuild-design.md`. The
> slug is sanitized to `[a-z0-9_-]` and the name is not caller-derived,
> so the "no path-traversal risk" conclusion above still holds; only the
> exact filename shape changed. The unused-`og:image` SSRF caveat is
> unaffected.

## Testing

Changed:

- `test_drivethrurpg_without_og_title` **inverts**. It currently asserts
  a missing `og:title` raises `ValueError`; that is precisely the
  behaviour being reversed, so it becomes a link-only assertion. Called
  out explicitly because a test flipping from "raises" to "succeeds"
  should be a conscious change.
- `test_drivethrurpg_product_url` asserts `cand["source"] ==
  "drivethrurpg"`. With `source` becoming the normalized hostname, that
  expectation becomes `"drivethrurpg.com"`. The test otherwise stands —
  it is now exercising the generic path rather than a registered
  handler, which is exactly the point.

New:

- Generic scrape succeeds on an unregistered host.
- Hostname suffix cleanup strips ` | Example Games`, and leaves a title
  containing an unrelated dash or colon alone.
- 403 fails fast: no sleep, no retry, falls through to link-only.
- 5xx retries the full 3 attempts, then falls through to link-only.
- Non-`http(s)` scheme is rejected before any request is issued.

Security (see that section for rationale):

- A `javascript:` URL returns **400**, and specifically does *not* come
  back as a link-only candidate.
- A redirect to a non-`http(s)` scheme is rejected on the final URL too,
  not just the pasted one.
- A hostname containing HTML metacharacters reaches the renderer
  escaped — asserted against the rendered markup, not just the JSON, so
  the missing `esc()` would actually fail the test.
- A response over the size cap is abandoned rather than read whole, and
  a non-HTML `Content-Type` is skipped.
- Route returns `link_only: true` with the item's existing name.
- Malformed known-domain URL still returns 400, not a link-only
  candidate.

The retry extraction is covered by the existing source tests continuing
to pass unchanged — the behaviour is identical by construction.

Run `.venv/Scripts/python scripts/leak_check.py` after adding fixtures.

## Backlog changes

- Replace the "Graceful fallback for manually pasted URLs" entry, whose
  503 framing this spec supersedes.
- Add a new open item: **set an item's URL through a manual row edit**,
  so a link can be attached or corrected without going through the
  paste-and-fetch flow at all.
