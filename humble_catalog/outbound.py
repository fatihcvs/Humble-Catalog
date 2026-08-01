"""The one place an outbound URL chosen by third-party content is checked.

Three of this project's input surfaces are classified adversarial, and all
three can name a URL the project will then request: an order's `icon`, a
metadata API's `api_detail_url`, and any `Location` header on the way to
either. A request built from such a value has to be validated before it is
sent, and validated again at every redirect hop, because the hop after the
check is the one that reaches the internal service.

Two different things are being defended, and they need different checks:

  - Reaching the wrong NETWORK. A URL pointing at loopback, the LAN, or a
    cloud metadata address turns this project into a probe of its owner's
    machine. `publicly_routable` is the check, and it is enough here
    because the request carries nothing secret.

  - Reaching the wrong HOST. A request that carries a credential - the
    Comic Vine key rides in the query string - must additionally stay on
    the host it was issued for. Routability does not help there: an
    attacker's own server is publicly routable, and would be handed the
    key. That is what `allowed_hosts` is for, and any call carrying a
    secret must pass it.

The guard is deliberately NOT applied to a URL the owner typed. url_import
lets the owner paste whatever they like and checks only the hops after it;
that asymmetry is the reason `check_initial` exists rather than being
assumed.
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

ALLOWED_SCHEMES = ("http", "https")
MAX_REDIRECTS = 5

# Statuses that carry a Location we would follow. Checked by number rather
# than through requests' `is_redirect`, because the tests drive this code
# with Mock responses, on which every attribute is truthy.
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def publicly_routable(host):
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


def check_url(url, allowed_hosts=None, what="URL"):
    """Raise ValueError unless `url` is safe to request.

    Requires http or https, and an address that is publicly routable. When
    `allowed_hosts` is given, the host must also be one of them exactly -
    pass it for any request carrying a credential, because routability
    alone would still let an attacker's own server receive it.

    `what` names the thing being refused in the message, so a redirect and
    an initial URL read differently in the error the owner sees.
    """
    parts = urlparse(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"refused {what} with unsupported scheme "
            f"'{parts.scheme}'; only http and https are allowed")
    host = parts.hostname
    if not host:
        raise ValueError(f"refused {what} '{url}': no host in it")
    if allowed_hosts is not None and host.lower() not in allowed_hosts:
        raise ValueError(
            f"refused {what} to '{host}': expected one of "
            f"{', '.join(sorted(allowed_hosts))}")
    if not publicly_routable(host):
        raise ValueError(
            f"refused {what} to '{host}': a private or unroutable address")


def get(sess, url, allowed_hosts=None, check_initial=True, send=None, **kwargs):
    """GET `url`, validating the destination before every request.

    Redirects are followed by hand rather than by requests, so that every
    hop is checked before it is fetched. Following them inside requests
    would only expose the final URL, by which point an intermediate hop to
    an internal service has already been requested.

    `check_initial=False` skips the check on `url` itself, for the one
    caller whose starting URL is the owner's own choice rather than
    third-party content; every hop after it is still checked.

    `send` lets a caller wrap each individual request - url_import passes
    its retry policy. It takes the target URL and the keyword arguments and
    returns a response; the default sends it directly on `sess`.
    """
    if check_initial:
        check_url(url, allowed_hosts)
    if send is None:
        def send(target, **kw):
            return sess.get(target, allow_redirects=False, **kw)

    current = url
    for _ in range(MAX_REDIRECTS + 1):
        resp = send(current, **kwargs)
        location = resp.headers.get("Location")
        if resp.status_code not in REDIRECT_STATUSES or not location:
            break
        # Relative Locations are legal and common, so resolve against the
        # URL we actually requested before judging the destination.
        current = urljoin(current, location)
        check_url(current, allowed_hosts, what="redirect")
    else:
        raise ValueError(f"too many redirects (more than {MAX_REDIRECTS})")

    # Kept for the response we ended on: a server can answer 200 while
    # reporting a different final URL, and that URL still has to be http(s).
    final = urlparse(str(resp.url))
    if final.scheme and final.scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"refused redirect with unsupported scheme '{final.scheme}'; "
            "only http and https are allowed")
    return resp


def read_capped(resp, limit, truncate=False):
    """Read at most `limit` bytes of `resp`, streaming rather than buffering.

    The cap exists so a hostile or broken endpoint cannot balloon memory,
    and it only means anything when the response was requested with
    stream=True - otherwise requests has already read the whole body.

    The two callers want opposite things when the body runs past the cap,
    so the overflow policy is a parameter rather than an assumption:

      truncate=True  - return the first `limit` bytes. What a page read
                       wants: OpenGraph tags live in <head>, so a partial
                       read still parses.
      truncate=False - raise ValueError and return nothing. What a file
                       download wants: half a JPEG written to disk as
                       though it were whole is worse than no cover.

    Stops at a chunk boundary rather than an exact byte count, so a
    truncating read can return up to one chunk more than `limit`. That is
    the behaviour this had before it moved here, and the callers treat the
    cap as a memory bound rather than a length contract; slicing to the
    byte would quietly shorten the bundle-page read that asks for a larger
    limit precisely to reach a blob near the end.
    """
    chunks, total = [], 0
    for chunk in resp.iter_content(65536):
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            if not truncate:
                raise ValueError(
                    f"refused a response larger than {limit} bytes")
            break
    return b"".join(chunks)
