"""Known-answer probes for url_import: URL validation and fetch guards.

This is an adversarial-class surface per the Operating envelope: the pasted
URL is the owner's, but everything the fetch then follows - redirects,
headers, page bodies - is third-party content. The negative cases are the
point; a validator that accepted everything would pass a liveness probe.

The redirect case runs two REAL local HTTP servers rather than a mock, so
what it demonstrates is the code's actual behaviour and not a stub's.
"""
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import db, url_import   # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


# --- normalize_url: the scheme gate. The raw string is parsed BEFORE the
# https:// prefix is added, which is what stops "javascript:alert(1)" from
# becoming "https://javascript:alert(1)" and passing. ---
check("normalize_url: bare host gains https://",
      url_import.normalize_url("example.com/book"), "https://example.com/book")
check("normalize_url: http is left alone",
      url_import.normalize_url("http://example.com"), "http://example.com")
check("normalize_url: https is left alone",
      url_import.normalize_url("https://example.com"), "https://example.com")

for bad in ["javascript:alert(1)", "JAVASCRIPT:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "file:///etc/passwd", "file:///C:/Windows/win.ini",
            "ftp://example.com/x", "vbscript:msgbox(1)",
            "jar:http://example.com!/", "gopher://example.com/"]:
    try:
        got = url_import.normalize_url(bad)
    except ValueError:
        got = "ValueError"
    check(f"normalize_url rejects {bad[:34]!r}", got, "ValueError")

# Obfuscation attempts that must not slip past the scheme gate. urlparse
# strips ASCII whitespace and control characters, so these normalize to a
# rejected scheme rather than to a permitted one.
for bad in ["  javascript:alert(1)", "java\tscript:alert(1)",
            "java\nscript:alert(1)"]:
    try:
        got = url_import.normalize_url(bad)
    except ValueError:
        got = "ValueError"
    check(f"normalize_url rejects obfuscated {bad!r}", got, "ValueError")

# --- host_of ---
check("host_of: strips www.", url_import.host_of("https://www.example.com/x"),
      "example.com")
check("host_of: lowercases", url_import.host_of("https://EXAMPLE.com/x"),
      "example.com")
check("host_of: works on a schemeless string",
      url_import.host_of("example.com/x"), "example.com")

# --- handler routing: a lookalike host must NOT reach a source handler. ---
with tempfile.TemporaryDirectory() as td:
    conn = db.connect(str(Path(td) / "u.db"))

    def routes_to_handler(url):
        """True when resolve() picks a registered handler, not the OG fallback.

        Handlers all raise ValueError on a URL whose path does not match
        their pattern, and they never touch the network to decide that, so
        the exception type is the routing signal.
        """
        try:
            url_import.resolve(conn, url, http=_never_called())
        except ValueError:
            return True
        except Exception:
            return False
        return False

    class _never_called:
        def request(self, *a, **k):
            raise AssertionError("network reached during a routing probe")

    check("routing: the real host reaches its handler",
          routes_to_handler("https://comicvine.gamespot.com/not-a-volume/"), True)
    check("routing: a subdomain reaches its handler",
          routes_to_handler("https://m.comicvine.gamespot.com/nope/"), True)
    # The lookalikes: a suffix that merely CONTAINS the domain must not match.
    for evil in ["https://comicvine.gamespot.com.evil.example/x",
                 "https://evil-comicvine.gamespot.com.attacker.test/x",
                 "https://notoreilly.com/library/view/x/1234567890/"]:
        check(f"routing: lookalike is NOT treated as the real host {evil[8:38]!r}",
              routes_to_handler(evil), False)

    # --- the redirect guard. Two real servers: A stands for the external
    # page the owner pasted, B for a service that is only reachable from
    # this machine. A 302s to B. ---
    class _Internal(BaseHTTPRequestHandler):
        def do_GET(self):
            body = (b"<html><head>"
                    b"<meta property='og:title' content='INTERNAL SERVICE PAGE'>"
                    b"</head></html>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    internal = HTTPServer(("127.0.0.1", 0), _Internal)
    internal_port = internal.server_address[1]
    threading.Thread(target=internal.serve_forever, daemon=True).start()

    class _External(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location",
                             f"http://127.0.0.1:{internal_port}/admin")
            self.end_headers()

        def log_message(self, *a):
            pass

    external = HTTPServer(("127.0.0.1", 0), _External)
    external_port = external.server_address[1]
    threading.Thread(target=external.serve_forever, daemon=True).start()

    pasted = f"http://127.0.0.1:{external_port}/product"
    try:
        cand = url_import.resolve(conn, pasted)
        followed = cand.get("title")
    except Exception as exc:                     # noqa: BLE001
        followed = f"{type(exc).__name__}: {exc}"

    # The known answer is a REFUSAL. `_fetch_html` re-checks the scheme
    # after redirects but never the destination host, so a page can steer
    # the fetch at any address this machine can reach - loopback, the LAN,
    # a cloud metadata endpoint - and the og:title of the response comes
    # back into the viewer. Filed as B1. Until it is fixed this case fails
    # with the internal page's title, which is the reproduction.
    check("redirect to a private address is refused",
          str(followed).startswith("ValueError"), True)

    # The allow side, so the guard is not merely "refuse everything".
    # IP literals, so getaddrinfo does no DNS and this stays offline-safe.
    check("routable check: a public address is allowed",
          url_import._publicly_routable("8.8.8.8"), True)
    check("routable check: a public IPv6 address is allowed",
          url_import._publicly_routable("2001:4860:4860::8888"), True)
    for private in ["127.0.0.1", "10.0.0.1", "192.168.1.1", "172.16.0.1",
                    "169.254.169.254", "0.0.0.0", "::1", "fe80::1"]:
        check(f"routable check: {private} is refused",
              url_import._publicly_routable(private), False)
    check("routable check: an unresolvable name fails CLOSED",
          url_import._publicly_routable(
              "no-such-host.invalid.example.test"), False)

    def target_verdict(t):
        try:
            url_import._check_redirect_target(t)
            return "allowed"
        except ValueError:
            return "refused"

    check("redirect target: a public https URL is allowed",
          target_verdict("https://8.8.8.8/page"), "allowed")
    check("redirect target: a loopback URL is refused",
          target_verdict("http://127.0.0.1:8087/admin"), "refused")
    check("redirect target: cloud metadata is refused",
          target_verdict("http://169.254.169.254/latest/meta-data/"), "refused")
    check("redirect target: a non-http scheme is refused",
          target_verdict("file:///etc/passwd"), "refused")

    # A schemeless host:port is misdiagnosed: the hostname is reported as
    # the offending "scheme". Filed as B2.
    try:
        _got = url_import.normalize_url("example.com:8080/book")
    except ValueError as exc:
        _got = f"ValueError: {exc}"
    check("schemeless host:port is accepted or refused for the right reason",
          "unsupported URL scheme 'example.com'" not in str(_got), True)

    internal.shutdown()
    external.shutdown()
    conn.close()

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
