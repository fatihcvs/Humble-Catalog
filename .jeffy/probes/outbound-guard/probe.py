"""Known-answer probes for humble_catalog.outbound, plus the two C1 reproductions.

The guard's whole job is that a request is NOT sent, so every case that
expects a refusal is run against a real http.server on an ephemeral port and
asserts the server's received-request log is empty. A mocked session would
only prove what the mock was written to do, and here the interesting answer
is the absence of a connection.

Both documented parameters are exercised at two values that change the
answer: `allowed_hosts` (None admits any routable host, a set admits only
its members) and `check_initial` (True refuses before sending, False sends
the starting URL unchecked and still guards the hops).
"""
import sys
import tempfile
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import db, extract, outbound  # noqa: E402
from humble_catalog.sources.comicvine import ComicVine  # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


def refusal(fn, *a, **kw):
    """Run fn and report 'refused' for ValueError, else what came back."""
    try:
        fn(*a, **kw)
    except ValueError:
        return "refused"
    except Exception as exc:  # noqa: BLE001
        return f"other: {type(exc).__name__}"
    return "allowed"


class Handler(BaseHTTPRequestHandler):
    """Logs every path it is asked for; redirects when the path says so."""

    def do_GET(self):
        self.server.seen.append(self.path)
        if self.path.startswith("/to-loopback"):
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{self.server.server_port}/private")
            self.end_headers()
            return
        if self.path.startswith("/loop"):
            self.send_response(302)
            self.send_header("Location", "/loop")
            self.end_headers()
            return
        body = b'{"results": {"person_credits": []}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def serve():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    srv.seen = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# --------------------------------------------------------------- check_url
# Schemes: the allowed pair, then the negative side.
check("check_url: https is allowed",
      refusal(outbound.check_url, "https://8.8.8.8/x"), "allowed")
check("check_url: http is allowed",
      refusal(outbound.check_url, "http://8.8.8.8/x"), "allowed")
for bad in ("file:///etc/passwd", "ftp://8.8.8.8/x", "javascript:alert(1)",
            "data:text/html,x", "gopher://8.8.8.8/", "FILE:///etc/passwd"):
    check(f"check_url: {bad.split(':')[0]} is refused",
          refusal(outbound.check_url, bad), "refused")
check("check_url: a URL with no host is refused",
      refusal(outbound.check_url, "http:///nohost"), "refused")

# Addresses that must never be reached.
for private in ("http://127.0.0.1/x", "http://localhost/x", "http://10.0.0.1/x",
                "http://192.168.1.1/x", "http://169.254.169.254/latest/meta-data/",
                "http://[::1]/x", "http://0.0.0.0/x"):
    check(f"check_url: {private} is refused",
          refusal(outbound.check_url, private), "refused")
check("check_url: a name that does not resolve is refused (fails closed)",
      refusal(outbound.check_url, "http://no-such.invalid.example.test/x"),
      "refused")

# allowed_hosts at two values, on ONE routable URL that must flip verdict.
# This is the case that distinguishes the credential rule from the network
# rule: 8.8.4.4 is perfectly routable, and is still refused when the caller
# named a different host, because the request would carry a key.
check("check_url: allowed_hosts=None admits any routable host",
      refusal(outbound.check_url, "https://8.8.4.4/x", None), "allowed")
check("check_url: allowed_hosts set refuses a routable host not in it",
      refusal(outbound.check_url, "https://8.8.4.4/x", frozenset({"8.8.8.8"})),
      "refused")
check("check_url: allowed_hosts set admits a host in it",
      refusal(outbound.check_url, "https://8.8.8.8/x", frozenset({"8.8.8.8"})),
      "allowed")
check("check_url: allowed_hosts matching is case-insensitive",
      refusal(outbound.check_url, "https://EXAMPLE.com/x",
              frozenset({"example.com"})),
      # example.com resolves publicly; the point is the host comparison did
      # not refuse it for casing. A resolution failure would read 'refused'.
      "allowed")
check("check_url: an allowlisted host that is NOT routable is still refused",
      refusal(outbound.check_url, "http://127.0.0.1/x",
              frozenset({"127.0.0.1"})), "refused")

# ------------------------------------------------------------------- get()
srv = serve()
port = srv.server_port
sess = requests.Session()

# check_initial at two values on the SAME loopback URL. True must refuse
# before any connection; False must reach the server. The assertion that
# matters is the server's log.
srv.seen.clear()
check("get: check_initial=True refuses a loopback URL",
      refusal(outbound.get, sess, f"http://127.0.0.1:{port}/x"), "refused")
check("get: check_initial=True sent nothing to the server", list(srv.seen), [])

srv.seen.clear()
check("get: check_initial=False sends the owner's own URL",
      refusal(outbound.get, sess, f"http://127.0.0.1:{port}/x",
              None, False), "allowed")
check("get: check_initial=False reached the server", list(srv.seen), ["/x"])

# A hop into loopback is refused, and the hop is never requested. The first
# request is the owner's URL (unchecked by design); the redirect is not.
srv.seen.clear()
check("get: a redirect into loopback is refused",
      refusal(outbound.get, sess, f"http://127.0.0.1:{port}/to-loopback",
              None, False), "refused")
check("get: the redirect target was never requested",
      list(srv.seen), ["/to-loopback"])

# A self-redirecting loop cannot reach the MAX_REDIRECTS cap here, and
# that is the stronger answer: the hop target is loopback, so it is refused
# on the FIRST hop, after exactly one request. The cap itself is pinned by
# test_url_import.py, which drives it with routable hosts.
srv.seen.clear()
check("get: a redirect cycle is refused at its first hop",
      refusal(outbound.get, sess, f"http://127.0.0.1:{port}/loop",
              None, False), "refused")
check("get: a cycle costs exactly one request, not MAX_REDIRECTS of them",
      len(srv.seen), 1)

# allowed_hosts also binds the hops, not only the first request.
srv.seen.clear()
check("get: allowed_hosts refuses a hop off the allowlist",
      refusal(outbound.get, sess, f"http://127.0.0.1:{port}/to-loopback",
              frozenset({"nowhere.example"}), False), "refused")
check("get: the off-allowlist hop was never requested",
      list(srv.seen), ["/to-loopback"])

# ------------------------------------------- C1 reproduction 1: the API key
# ComicVine.credits used to send api_key to whatever host a previous Comic
# Vine response named. The URL below is the exact shape enrich.credits pulls
# out of a stored candidate's extra["first_issue_api_url"].
with tempfile.TemporaryDirectory() as td:
    conn = db.connect(str(Path(td) / "cv.db"))
    src = ComicVine(conn, key="PROBE-KEY-VALUE")
    src.delay = 0.0
    srv.seen.clear()
    check("credits: an issue URL off Comic Vine's hosts is refused",
          refusal(src.credits, f"http://127.0.0.1:{port}/api/issue/4000-1/"),
          "refused")
    check("credits: the foreign server received no request", list(srv.seen), [])
    srv.seen.clear()
    check("credits: a routable but foreign host is refused too",
          refusal(src.credits, "https://8.8.4.4/api/issue/4000-1/"), "refused")
    check("credits: no key reached that host either", list(srv.seen), [])
    check("credits: a missing URL is still a quiet no-op, not a refusal",
          src.credits(None), (None, None))
    conn.close()

# ------------------------------------------ C1 reproduction 2: cover bytes
# The cover downloader used to fetch an order-JSON URL naming loopback and
# write the body under covers/. Both the direct URL and the redirect into
# loopback must now be refused, and nothing may be written.
with tempfile.TemporaryDirectory() as td:
    conn = db.connect(str(Path(td) / "cov.db"))
    conn.execute("INSERT INTO items (machine_name, name, type, cover_url) "
                 "VALUES ('a','Salt and Sextant','ebook',?)",
                 (f"http://127.0.0.1:{port}/internal-secret",))
    conn.execute("INSERT INTO items (machine_name, name, type, cover_url) "
                 "VALUES ('b','Gray Waters','ebook',?)",
                 (f"http://127.0.0.1:{port}/to-loopback",))
    conn.commit()
    covers_dir = Path(td) / "covers"
    srv.seen.clear()
    written = extract._download_covers(
        conn, types.SimpleNamespace(http=sess), covers_dir)
    check("covers: no cover is written from a loopback URL", written, 0)
    check("covers: nothing landed in the covers directory",
          sorted(p.name for p in covers_dir.iterdir()), [])
    check("covers: the loopback server received no request", list(srv.seen), [])
    check("covers: no cover_path was recorded",
          [r["cover_path"] for r in
           conn.execute("SELECT cover_path FROM items ORDER BY machine_name")],
          [None, None])
    conn.close()

srv.shutdown()

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
