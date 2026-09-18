# Viewing the catalog from a phone on the home network — design

Date: 2026-09-18
Issue: #6 (Standalone Android viewer app) — this is sub-project 1.

## Problem

The catalog can only be read at the PC that runs it. `serve` binds
`127.0.0.1` and refuses any request addressed to a host other than
localhost, which is the right default and also means a phone on the same
Wi-Fi cannot reach it at all.

The request behind #6 is to read the catalog, and reach the items'
download links, from a phone. A native app is one answer, but most of it
would be a second implementation of a viewer that already exists. The
phone already has a browser. Letting it reach the viewer on the home
network is a stopgap that covers the same need at a fraction of the
cost, and shows whether a native app is still wanted afterwards.

The download links need no new data. Every item's bundle chip already
links to `https://www.humblebundle.com/downloads?key=<gamekey>`, that
order's download page on Humble.

## Decomposition

#6 is split into pieces, each with its own spec, plan and branch:

1. **LAN web viewer** — this spec. `serve --lan` makes a read-only viewer
   reachable from paired devices on the home network, over HTTPS.
2. **Native Android app** — the original #6. Deferred until piece 1 has
   been used; #6 stays open for it.

## Decisions

Each was chosen during brainstorming, with the alternatives recorded.

| Question | Decision | Rejected |
|---|---|---|
| What can a LAN device do? | Read only | Light edits; the full viewer, Tasks tab included |
| Who gets in? | Pairing link / QR, exchanged for a cookie | Anyone on the network; an IP allowlist (spoofable, DHCP churn) |
| How long does a pairing last? | Until revoked with `--new-token` | One run; a fixed expiry |
| Where is read-only enforced? | A second Flask app that registers only read routes | One server bound to all interfaces with a `before_request` guard; a static export |
| Transport | HTTPS, from a local certificate authority installed on the phone once | Plain HTTP; self-signed and clicked through; a publicly trusted certificate (needs a domain or Tailscale, which is the hosted dependency #16 ruled out) |
| Phone layout | A card list below ~600 px | Trimming the table; no layout work |

## Architecture

### Two servers, one process

`python -m humble_catalog serve --lan` runs two servers on two threads:

- **Loopback** — the existing viewer, unchanged: `create_app()` on
  `127.0.0.1:<port>`, every route, the existing host check.
- **LAN** — `create_lan_app()` on `<lan-ip>:<lan-port>` over HTTPS.

Without `--lan`, `serve` behaves exactly as today. `serve` builds both
with `werkzeug.serving.make_server` (rather than `app.run`) so it can
run two, and stopping `serve` stops both.

New flags on `serve`:

| Flag | Meaning |
|---|---|
| `--lan` | Also serve the read-only LAN viewer |
| `--lan-host IP` | The address to bind, overriding detection |
| `--lan-port N` | The LAN port; defaults to `--port` + 1 |
| `--setup` | Also run the one-time certificate download listener (see Pairing) |
| `--new-token` | Replace the pairing token, unpairing every device |

`--lan-host`, `--lan-port`, `--setup` and `--new-token` are errors
without `--lan`.

### The route split

`create_app` currently registers every route inline. It is split into
two registration functions:

- `_register_read_routes(app, conn)` — `/`, `/static/*`, `/covers/*`,
  `GET /api/items`, `GET /api/stats`, `GET /api/keys`, `GET /api/status`.
- `_register_write_routes(app, conn)` — everything else, including the
  maintenance reads (`/api/review`, `/api/duplicates`), which are only
  useful next to the writes they feed, and both exports.

`create_app` calls both. `create_lan_app` calls only the first. A write
route on the LAN app is therefore not blocked: it does not exist there.
A future route reaches the phone only if someone deliberately registers
it in the read group, and the class test below makes that a visible
edit.

`GET /api/status` gains `"read_only": true` on the LAN app and
`"read_only": false` on the loopback app.

### LAN app guards

Checked in this order, in `before_request`:

1. **Host.** The Host header must name the LAN address and port the app
   is bound to, or the request gets a 403. This is the LAN counterpart of
   the loopback host check, and refuses DNS rebinding the same way.
2. **Pairing.** Every request except `GET /pair` needs a valid pairing
   cookie. Without one, it gets a short 403 page: "Not paired — open the
   link `serve --lan` prints."

## Pairing and HTTPS

### Files

Everything lives in a `lan/` folder next to `catalog.db`:

| File | What | Lifetime |
|---|---|---|
| `ca.key`, `ca.crt` | The private certificate authority | 10 years; created on first `--lan` |
| `server.key`, `server.crt` | The HTTPS certificate for the current LAN address | 30 days; reissued on every start |
| `token` | The pairing token | Until `--new-token` |

`lan/` is gitignored, and `scripts/check_no_data_tracked.py` refuses it
as a data path. It is deliberately **not** inside `catalog.db`: `restore`
would otherwise bring back an old token and silently re-pair a phone
that had been unpaired. Backups and `reset` do not touch `lan/`.
Deleting the folder resets everything.

### The certificate authority

Generated with `cryptography` (a new dependency):

- `BasicConstraints(ca=True, path_length=0)`, and key usage limited to
  certificate signing.
- **Name constraints** permitting only `10.0.0.0/8`, `172.16.0.0/12` and
  `192.168.0.0/16`, plus the DNS name `invalid`. An installed authority
  can normally vouch for any site, so a leaked `ca.key` would let someone
  impersonate any website to that phone. With the constraints, which
  Chrome enforces, it can vouch only for private addresses. The DNS entry
  is needed because RFC 5280 leaves a name type unconstrained when no
  subtree of that type is listed; `invalid` is a reserved TLD, so
  permitting only it permits no real name.

The server certificate is signed by the authority, carries the LAN IP as
a `subjectAltName` IP entry, has extended key usage `serverAuth`, and is
reissued on each start, so a changed DHCP address never leaves a stale
certificate.

### First-time setup: `serve --lan --setup`

Alongside the two servers, a plain-HTTP listener on `<lan-ip>:<lan-port
+ 1>` serves exactly one route, `/ca.crt`. `serve` prints:

- the download link, as text and a terminal QR code (`qrcode`, a new
  pure-Python dependency);
- the certificate's SHA-256 fingerprint;
- the install path: Settings → Security → Encryption & credentials →
  Install a certificate → CA certificate.

The certificate is not secret. The risk is substitution while it is
downloaded, and comparing the fingerprint Android shows under Trusted
credentials → User against the terminal catches that. The listener
exists only while `--setup` runs.

### Pairing a phone: every `serve --lan`

`serve` prints `https://<lan-ip>:<lan-port>/pair?token=<token>` as text
and a QR code.

`GET /pair?token=…`:

- compares the token with `hmac.compare_digest`;
- on a match, sets the cookie and answers a short page that refreshes
  itself to `/`, with `Referrer-Policy: no-referrer`. The token leaves
  the address bar and is never sent as a referrer. A page rather than a
  303: a link opened from a QR-scanner app has no initiating site, and
  Chrome may withhold a `SameSite=Strict` cookie on the redirected
  request, while a same-origin refresh is an ordinary same-site
  navigation;
- otherwise answers 403 and prints the failed attempt, with the client
  address, on the console.

The cookie's value is the token itself, with `Secure`, `HttpOnly`,
`SameSite=Strict`, `Path=/` and `Max-Age` 400 days (Chrome's cap). Since
the value is the token, `--new-token` invalidates every cookie with no
other state to track.

There is no rate limit on `/pair`: guessing a 256-bit token
(`secrets.token_urlsafe(32)`) is not feasible, so a limiter would be
code defending nothing.

### What remains exposed

- `ca.key` is the most sensitive file in the project. Leaked, it allows
  impersonating servers on a private network, but no real website.
- The pairing link printed at the terminal is a credential. It joins
  `harvest --failures` in `CLAUDE.md`'s list of terminal output that must
  never be pasted anywhere.
- A paired device can read the whole catalog, order keys included, for
  as long as `serve --lan` runs. Unpairing is `--new-token`.

## Front end

### Read-only mode

`shell.js` already fetches `/api/status` on load. When `read_only` is
true it sets `document.body.dataset.mode = "read-only"` and a shared
`READ_ONLY` flag that the other modules read.

In read-only mode:

- **Tabs:** only Library and Keys are shown. Maintenance and Tasks are
  writes; Bundles is hidden too, because both of its previews are
  credentialed POSTs that the LAN app does not have.
- **Rendered as text, not controls:** status and rating.
- **Not rendered:** the re-enrich and edit icons, the Keys tab's
  hide/unhide buttons, the Bulk tag bar, and the export controls.

Hiding is cosmetic. The routes are absent either way; hiding the
controls keeps a tap from turning into a 404.

### Card list below ~600 px

Measured on the demo catalog at 375 px: the table is 22 columns and
1,477 px wide, so only Name, Type and Status are visible, and the bundle
links are off-screen to the right. The tab bar runs off the edge too.

Below ~600 px, `catalog.js` renders a card list in place of the table,
from the same filtered and sorted rows, so search and filters behave
identically. Each card shows:

- the cover thumbnail, with `loading="lazy"`;
- title, authors, and series with its number;
- a type badge and the formats;
- status, rating and tags as small text;
- each bundle as a large tap target linking to its download page.

The filter sidebar keeps its existing collapse at 900 px. The tab bar
gets `overflow-x: auto`, so no tab can be pushed off the edge.

Cards appear at narrow widths on the PC too, and are display-only there
as well. Editing needs a wider window; the README says so.

## Errors

Each fails with a message that names what to run next.

| Condition | Behaviour |
|---|---|
| No LAN address found, or several | Stop; list the candidates; suggest `--lan-host` |
| LAN port (or the setup port) in use | Stop before starting any server; name the port and `--lan-port` |
| Server certificate missing or expired | Reissue silently |
| `ca.crt` without `ca.key`, or the reverse | Stop: "delete `lan/` and run `serve --lan --setup` again". Silently minting a new authority would need a reinstall on the phone anyway |
| `token` unreadable | Stop, naming the file |
| PC's address changes while running | The phone gets a connection error; restarting issues a certificate for the new address and prints the new link |
| Unpaired device, or foreign Host header | 403 page |

## Testing

No test binds a real socket or touches the network.

- **Route split (class test).** Every rule on the LAN app accepts only
  GET, HEAD and OPTIONS, and the set of rules equals a pinned list.
  Adding a route to the read group fails this test until the list is
  edited on purpose. The existing loopback tests show the full app is
  unchanged.
- **Pairing.** The right token sets a cookie with `Secure`, `HttpOnly`
  and `SameSite=Strict` and redirects to `/`. A wrong or missing token
  gets a 403. Every LAN route refuses a request without the cookie (a
  class test over all rules). Rotating the token invalidates an existing
  cookie.
- **LAN host check.** A request with a foreign Host header gets a 403.
- **Certificates** (inspected with `cryptography`). The authority has
  `CA:true` and name constraints of exactly the three private ranges and
  the DNS name `invalid`. The server certificate carries the IP, chains
  to the authority, expires in 30 days, and has `serverAuth`. A lone
  `ca.crt` or `ca.key` raises the error above.
- **`/api/status`** reports `read_only` correctly on both apps.
- **Front end** (existing JS harness). Read-only mode renders no status
  `<select>` and no edit icons, and hides Maintenance, Bundles and Tasks.
  The card renderer produces one card per filtered row, with the bundle
  links present.
- **`serve --lan` wiring**, with the server factory stubbed: both servers
  are built with the right hosts, ports and TLS context; flags that
  require `--lan` are refused without it.
- **Privacy.** `lan/` is gitignored, and `check_no_data_tracked.py`
  refuses a path inside it.
- **Visual.** A 375 px screenshot of the card list, taken on the demo
  catalog (`scripts/demo_catalog.py`, port 8099), never the real one.

## Documentation

- **README:** a "Viewing on your phone" section covering setup, the
  one-time certificate install, pairing and unpairing. "The viewer's
  exposure" gains what `--lan` adds and what bounds it.
- **`CLAUDE.md`:** the pairing link joins `harvest --failures` as
  terminal output never to paste, and `lan/` joins the never-commit list.
- **`pyproject.toml`:** `cryptography` and `qrcode` join the
  dependencies.

## Out of scope

- Any write from the LAN: ratings, tags, notes, merges, Tasks, previews.
- A native app (#6, piece 2).
- Reaching the viewer from outside the home network.
- Revoking a single device. `--new-token` unpairs all of them.
- mDNS / `.local` names. Android's support is uneven, and the printed
  link covers the need.
