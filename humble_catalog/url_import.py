"""Resolve a pasted source URL into a single enrichment candidate.

Used by the review UI: the user finds the right record themselves, pastes
its URL, and we fetch that exact record instead of searching. Each handler
reuses the matching Source class so throttling and source_cache apply.
"""
import html
import ipaddress
import re
import socket
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from humble_catalog.sources.audible import Audible, product_candidate
from humble_catalog.sources.base import candidate, _with_retries
from humble_catalog.sources.comicvine import ComicVine, split_credits
from humble_catalog.sources.google_books import GoogleBooks, volume_candidate
from humble_catalog.sources.hardcover import Hardcover
from humble_catalog.sources.open_library import OpenLibrary, doc_candidate
from humble_catalog.sources.oreilly import OReilly


ALLOWED_SCHEMES = ("http", "https")
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5

# Statuses that carry a Location we would follow. Checked by number rather
# than through requests' `is_redirect`, because the tests drive this code
# with Mock responses, on which every attribute is truthy.
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class MetadataUnavailable(Exception):
    """The page was reachable but yielded no usable metadata.

    Distinct from ValueError, which means the URL itself was rejected.
    The webapp turns this into a link-only candidate; it turns ValueError
    into a 400.
    """


def host_of(url):
    """Lowercased hostname with a leading www. stripped."""
    parts = urlparse(url if "://" in url else "https://" + url)
    return parts.netloc.lower().removeprefix("www.")


# "example.com:8080/book" - a host and a port, not a scheme and a path.
# urlparse reads everything before a colon as a scheme, so this has to be
# recognised before the scheme check or a pasted host:port is refused
# under its own hostname's name. The digits are what distinguish it:
# "javascript:alert(1)" has the same shape and must NOT match.
_HOST_AND_PORT = re.compile(r"^[^/?#:\s]+:\d+(?:[/?#]|$)")


def normalize_url(url):
    """Return url with https:// prepended when it has no scheme.

    Raises ValueError for any scheme other than http/https. The raw string
    is parsed first on purpose: "javascript:alert(1)" contains no "://",
    so prepending before checking would yield
    "https://javascript:alert(1)", whose scheme reads as https and passes.

    A schemeless "host:port" is recognised as such rather than read as a
    scheme, so pasting "example.com:8080/book" works instead of being
    rejected for an unsupported scheme called "example.com".
    """
    stripped = url.strip()
    if "://" not in stripped and _HOST_AND_PORT.match(stripped):
        return "https://" + stripped
    raw_scheme = urlparse(url).scheme
    if raw_scheme and raw_scheme not in ALLOWED_SCHEMES:
        # A dot in the "scheme" means a hostname was almost certainly meant;
        # saying so is the difference between a usable error and a puzzle.
        hint = (" (that looks like a hostname - a URL needs http:// or "
                "https:// in front of it)" if "." in raw_scheme else "")
        raise ValueError(
            f"unsupported URL scheme '{raw_scheme}'; only http and https "
            f"are allowed{hint}")
    return url if "://" in url else "https://" + url


def resolve(conn, url, http=None):
    """Return a candidate dict for a supported source URL (not applied).

    Raises ValueError for unsupported/unparseable URLs or missing API keys;
    lets requests exceptions propagate for network failures.
    """
    parts = urlparse(normalize_url(url))
    host = parts.netloc.lower().removeprefix("www.")
    for domain, handler in _HANDLERS.items():
        if host == domain or host.endswith("." + domain):
            return handler(conn, parts, url, http)
    return _generic_og(conn, parts, url, http)


def _comicvine(conn, parts, url, http):
    m = re.search(r"/(4050|4000)-(\d+)", parts.path)
    if not m:
        raise ValueError(
            "expected a Comic Vine volume (.../4050-<id>/) or issue "
            "(.../4000-<id>/) URL")
    src = ComicVine(conn, http=http)
    if not src.key:
        raise ValueError("COMICVINE_API_KEY is required to import Comic Vine URLs")
    kind = "volume" if m.group(1) == "4050" else "issue"
    # Volumes carry no person_credits (that field belongs to issues), so a
    # volume URL costs one extra hop to its first issue to get roled credits.
    fields = "name,site_detail_url,volume," + (
        "first_issue" if kind == "volume" else "person_credits")
    data = src.get_json(
        f"https://comicvine.gamespot.com/api/{kind}/{m.group(1)}-{m.group(2)}/",
        params={"api_key": src.key, "format": "json", "field_list": fields})
    res = data.get("results") or {}
    title = res.get("name") or (res.get("volume") or {}).get("name")
    if not title:
        raise ValueError("Comic Vine returned no record for that URL")
    if kind == "volume":
        writer_s, artist_s = src.credits(
            (res.get("first_issue") or {}).get("api_detail_url"))
        writers = [writer_s] if writer_s else []
        artists = [artist_s] if artist_s else []
    else:
        writers, artists = split_credits(res.get("person_credits"))
    return candidate(
        source=ComicVine.name, title=title,
        series=(res.get("volume") or {}).get("name") or res.get("name"),
        authors=writers or None,
        illustrator=", ".join(artists) or None,
        url=res.get("site_detail_url") or url)


def _hardcover(conn, parts, url, http):
    m = re.search(r"/books/([^/?#]+)", parts.path)
    if not m:
        raise ValueError("expected a hardcover.app/books/<slug> URL")
    src = Hardcover(conn, http=http)
    if not src.token:
        raise ValueError("HARDCOVER_API_KEY is required to import Hardcover URLs")
    slug = m.group(1)
    for cand in src.lookup(slug.replace("-", " ")):
        if (cand.get("url") or "").rstrip("/").endswith("/" + slug):
            return cand
    raise ValueError(f"no Hardcover search result matches the slug '{slug}'")


def _open_library(conn, parts, url, http):
    from humble_catalog.sources.open_library import FIELDS
    m = re.search(r"/(works|books)/(OL\w+)", parts.path)
    if not m:
        raise ValueError("expected an Open Library /works/... or /books/... URL")
    key = f"/{m.group(1)}/{m.group(2)}"
    src = OpenLibrary(conn, http=http)
    data = src.get_json("https://openlibrary.org/search.json",
                        params={"q": f"key:{key}", "limit": 1, "fields": FIELDS})
    docs = data.get("docs") or []
    if not docs:
        raise ValueError(f"Open Library has no record for {key}")
    return doc_candidate(docs[0])


def _google_books(conn, parts, url, http):
    vid = (parse_qs(parts.query).get("id") or [None])[0]
    if not vid:
        m = re.search(r"/books/edition/[^/]+/([A-Za-z0-9_-]+)", parts.path)
        vid = m.group(1) if m else None
    if not vid:
        raise ValueError("could not find a Google Books volume id in that URL")
    src = GoogleBooks(conn, http=http)
    data = src.get_json(f"https://www.googleapis.com/books/v1/volumes/{vid}",
                        params={"key": src.key} if src.key else None)
    vi = data.get("volumeInfo") or {}
    if not vi:
        raise ValueError("Google Books returned no volume for that URL")
    return volume_candidate(vi)


def _audible(conn, parts, url, http):
    m = re.search(r"/pd/(?:[^/]+/)*([A-Z0-9]{10})(?:[/?#]|$)", parts.path)
    if not m:
        raise ValueError("expected an Audible /pd/ product URL ending in an ASIN")
    src = Audible(conn, http=http)
    data = src.get_json(
        f"https://api.audible.com/1.0/catalog/products/{m.group(1)}",
        params={"response_groups": "contributors,rating,series"})
    product = data.get("product") or {}
    if not product:
        raise ValueError("Audible returned no product for that URL")
    return product_candidate(product)


def _oreilly(conn, parts, url, http):
    m = re.search(r"/library/view/[^/]+/(\d{10,13})", parts.path)
    if not m:
        raise ValueError("expected an O'Reilly /library/view/<title>/<isbn>/ URL")
    isbn = m.group(1)
    src = OReilly(conn, http=http)
    for cand in src.lookup(isbn):
        if cand.get("extra", {}).get("isbn") == isbn or isbn in (cand.get("url") or ""):
            return cand
    raise ValueError(f"O'Reilly search found no book with ISBN {isbn}")


def _publicly_routable(host):
    """True when every address `host` resolves to is publicly routable.

    Fails closed: a name that will not resolve is not allowed either, so a
    resolution failure cannot read as permission.

    This is a resolve-then-connect check, so a name that answers with a
    public address here and a private one when requests connects would slip
    through. Closing that needs the connection pinned to the address that
    was checked, which means a custom adapter; the remaining exposure is a
    hostile DNS server racing its own answers, which is a long way past the
    threat this guard exists for -- a page redirecting us at the LAN.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        # is_global is False for loopback, private, link-local (which
        # covers cloud metadata at 169.254.169.254), reserved, multicast
        # and unspecified addresses, so it is the whole check.
        if not ip.is_global:
            return False
    return True


def _check_redirect_target(target):
    """Refuse a redirect that leaves http(s) or points inside the network.

    The pasted URL is the owner's own choice and is not checked here: they
    may point this at whatever they like. A redirect target is different --
    it is chosen by the page, which is third-party content -- so it is the
    hop that has to be validated, and every hop, not merely the last one.
    """
    parts = urlparse(target)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"redirected to unsupported scheme '{parts.scheme}'; only http "
            "and https are allowed")
    host = parts.hostname
    if not host or not _publicly_routable(host):
        raise ValueError(
            f"refused a redirect to '{host or target}': a page may not send "
            "this fetch to a private or unroutable address")


def _fetch_html(url, http):
    """GET a page under the shared retry policy, with redirect and size guards.

    Redirects are followed by hand rather than by requests, so that every
    hop's destination can be checked before it is fetched. Following them
    inside requests would only expose the final URL, by which point an
    intermediate hop to an internal service has already been requested.
    """
    sess = http or requests.Session()
    current = url

    for _ in range(MAX_REDIRECTS + 1):
        def _send(target=current):
            return sess.request("GET", target,
                                headers={"User-Agent": "HumbleCatalog/1.0"},
                                timeout=30, stream=True, allow_redirects=False)

        resp = _with_retries(_send)
        location = resp.headers.get("Location")
        if resp.status_code not in REDIRECT_STATUSES or not location:
            break
        # Relative Locations are legal and common, so resolve against the
        # URL we actually requested before judging the destination.
        current = urljoin(current, location)
        _check_redirect_target(current)
    else:
        raise ValueError(f"too many redirects (more than {MAX_REDIRECTS})")

    # Kept for the response we ended on: a server can answer 200 while
    # reporting a different final URL, and that URL still has to be http(s).
    final = urlparse(str(resp.url))
    if final.scheme and final.scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"redirected to unsupported scheme '{final.scheme}'; only http "
            "and https are allowed")
    ctype = resp.headers.get("Content-Type", "")
    if "html" not in ctype.lower():
        raise MetadataUnavailable(
            f"{host_of(url)} served {ctype or 'no content type'}, not HTML")
    return resp


def _read_capped(resp, limit=None):
    """Read at most `limit` bytes of the body (default MAX_HTML_BYTES).

    OpenGraph tags live in <head>, so a truncated read still parses. The
    cap exists so a hostile or broken endpoint cannot balloon memory.
    Callers that need data from further down the page -- a bundle page
    carries its JSON blob about three-quarters of the way in -- pass a
    larger limit rather than raising it for every host.
    """
    cap = MAX_HTML_BYTES if limit is None else limit
    chunks, total = [], 0
    for chunk in resp.iter_content(65536):
        chunks.append(chunk)
        total += len(chunk)
        if total >= cap:
            break
    return b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")


def _generic_og(conn, parts, url, http):
    """Fallback for any host without a registered API handler.

    Product pages almost always carry OpenGraph tags, because those drive
    social link previews. One polite user-initiated GET, no search.
    """
    host = parts.netloc.lower().removeprefix("www.")
    resp = _fetch_html(url, http)
    page = _read_capped(resp)
    title = _og_meta(page, "og:title")
    if not title:
        raise MetadataUnavailable(f"{host} served no og:title")
    return candidate(source=host, title=_strip_site_suffix(title, host),
                     url=url,
                     # Stored but currently unread: apply_candidate ignores
                     # extra. Wiring this to items.cover_url would make
                     # _download_covers fetch an attacker-supplied URL - see
                     # the Security section of the design spec first.
                     extra={"cover": _og_meta(page, "og:image")})


def _strip_site_suffix(title, host):
    """Drop a trailing " | Example Games"-style site name from an og:title.

    Only strips when the tail matches the hostname's first label once both
    are reduced to letters and digits, so titles containing an unrelated
    dash or colon survive untouched.
    """
    m = re.match(r"^(.+?)\s*[|–—-]\s*([^|–—-]+)$", title)
    if not m:
        return title
    tail = re.sub(r"[^a-z0-9]", "", m.group(2).lower())
    label = re.sub(r"[^a-z0-9]", "", host.split(".")[0].lower())
    return m.group(1).strip() if tail and tail == label else title


def _og_meta(page, prop):
    for pattern in (
            rf'<meta[^>]*property=["\']{prop}["\'][^>]*content=["\']([^"\']*)["\']',
            rf'<meta[^>]*content=["\']([^"\']*)["\'][^>]*property=["\']{prop}["\']'):
        m = re.search(pattern, page, re.IGNORECASE)
        if m:
            return html.unescape(m.group(1)).strip() or None
    return None


_HANDLERS = {
    "comicvine.gamespot.com": _comicvine,
    "hardcover.app": _hardcover,
    "openlibrary.org": _open_library,
    "google.com": _google_books,
    "audible.com": _audible,
    "audible.co.uk": _audible,
    "audible.de": _audible,
    "oreilly.com": _oreilly,
}
