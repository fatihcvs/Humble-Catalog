"""Known-answer battery for the extract-humble inventory row.

Covers humble_catalog/humble_api.py (the client, its throttle and its
logged-in contract) and humble_catalog/extract.py (run, reparse,
_reparse_cached, and the cover phase's bookkeeping).

The Operating envelope classes HumbleBundle order JSON adversarial, so
the drift group holds it to the same rule as the metadata parsers: a
field arriving as another JSON type must not crash the harvest.

humble_api is probed against a real http.server on an ephemeral port
rather than a mocked session, because a mock proves only what it was
written to do; the server's own request log is the assertion for the
query-parameter and throttle cases. BASE is repointed at that server for
the duration, which is the only way to exercise the real request path
without reaching the network.

Cases assert the DESIRED answer, not the observed one, so the groups
marked DRIFT and PATH fail against the code as filed.

Titles and names are invented, from docs/TEST-DATA.md.
"""
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, extract, humble_api      # noqa: E402

PASS, FAIL = [], []
GROUPS = {}


def note(label, group):
    if group:
        GROUPS[label] = group


def check(label, got, want, group=None):
    note(label, group)
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def check_no_raise(label, fn, want, group=None):
    note(label, group)
    try:
        got = fn()
    except Exception as exc:
        FAIL.append(f"{label}: raised {type(exc).__name__}: {exc}")
        return
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def check_raises(label, fn, want_type, group=None):
    note(label, group)
    try:
        fn()
    except want_type:
        PASS.append(label)
    except Exception as exc:
        FAIL.append(f"{label}: raised {type(exc).__name__}, want {want_type.__name__}")
    else:
        FAIL.append(f"{label}: returned without raising {want_type.__name__}")


class Server:
    """A real HTTP server whose routes and request log are the assertion."""

    def __init__(self, routes):
        self.routes = routes          # path -> (status, content_type, body)
        self.log = []                 # (path, query dict)
        probe = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parts = urlparse(self.path)
                probe.log.append((parts.path, parse_qs(parts.query)))
                status, ctype, body = probe.routes.get(
                    parts.path, (404, "text/plain", "no route"))
                payload = body.encode() if isinstance(body, str) \
                    else json.dumps(body).encode()
                self.send_response(status)
                if ctype is not None:
                    self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        self._saved_base = humble_api.BASE
        humble_api.BASE = f"http://127.0.0.1:{self.port}"
        return self

    def __exit__(self, *exc):
        humble_api.BASE = self._saved_base
        self.httpd.shutdown()
        self.httpd.server_close()


JSON = "application/json"
ORDERS = [{"gamekey": "abc123"}, {"gamekey": "apk456"}]
ORDER = {"gamekey": "abc123",
         "product": {"human_name": "Humble Book Bundle: Test by Example Press"},
         "subproducts": []}


def client(delay=0.0):
    return humble_api.HumbleClient({}, delay=delay)


# --------------------------------------------------------------------
# humble_api - known answers against a real server
# --------------------------------------------------------------------
with Server({"/api/v1/user/order": (200, JSON, ORDERS),
             "/api/v1/order/abc123": (200, JSON, ORDER)}) as srv:
    c = client()
    check("api: list_order_keys returns the gamekeys in order",
          c.list_order_keys(), ["abc123", "apk456"])
    check("api: get_order returns the order body",
          c.get_order("abc123")["gamekey"], "abc123")
    # The request log, not the return value, is what pins the query param.
    check("api: get_order sends all_tpkds=true, without which external keys "
          "are omitted",
          srv.log[-1][1].get("all_tpkds"), ["true"])
    check("api: get_order asks for the keyed path",
          srv.log[-1][0], "/api/v1/order/abc123")
    check("api: logged_in is true when the order endpoint answers json",
          client().logged_in(), True)

# The logged-in contract at its other values. Each must flip the answer.
for status, ctype, why in ((200, "text/html", "html instead of json"),
                           (302, JSON, "a redirect"),
                           (403, JSON, "a refusal"),
                           (500, JSON, "a server error"),
                           (200, None, "no content-type header at all")):
    with Server({"/api/v1/user/order": (status, ctype, ORDERS)}):
        check(f"api: logged_in is false on {why}", client().logged_in(), False)
        check_raises(f"api: _get raises NotLoggedIn on {why}",
                     lambda: client().list_order_keys(), humble_api.NotLoggedIn)

# The throttle, counted rather than watched: "it worked" looks identical
# whether the delay was honoured or skipped.
with Server({"/api/v1/user/order": (200, JSON, ORDERS)}):
    slept = []
    real_sleep = time.sleep
    time.sleep = slept.append
    try:
        c = client(delay=7.0)
        c.list_order_keys()
        check("api: the first request does not wait", slept, [])
        c.list_order_keys()
        check("api: the second request waits about the delay",
              len(slept) == 1 and 0 < slept[0] <= 7.0, True)
        # delay at a second value must change the wait.
        slept.clear()
        c2 = client(delay=0.0)
        c2.list_order_keys()
        c2.list_order_keys()
        check("api: a zero delay never waits", slept, [])
    finally:
        time.sleep = real_sleep

# --------------------------------------------------------------------
# extract - known answers with a stub client, no network
# --------------------------------------------------------------------
class StubClient:
    """Explicit double, not a Mock: it states exactly what extract.run is
    entitled to use, so a new dependency shows up as an error rather than
    being invented."""

    def __init__(self, orders):
        self.orders = orders
        self.http = None
        self.fetched = []

    def list_order_keys(self):
        return list(self.orders)

    def get_order(self, key):
        self.fetched.append(key)
        return self.orders[key]


def fresh_db():
    return Path(tempfile.mkdtemp()) / "probe.db"


def run_extract(orders, refetch=False, path=None, covers_dir=None):
    path = path or fresh_db()
    stub = StubClient(orders)
    extract.run(db_path=path, covers_dir=covers_dir or Path(tempfile.mkdtemp()),
                client=stub, refetch=refetch)
    return path, stub


path, stub = run_extract({"abc123": ORDER})
check("extract: a new bundle is fetched once", stub.fetched, ["abc123"])
conn = db.connect(path)
check("extract: the raw order is cached under its gamekey",
      [r["gamekey"] for r in conn.execute("SELECT gamekey FROM raw_orders")],
      ["abc123"])
check("extract: the cached json round-trips",
      json.loads(conn.execute("SELECT json FROM raw_orders").fetchone()["json"])
      ["gamekey"], "abc123")
conn.close()

# refetch at both values, which must change the number of fetches.
path, _ = run_extract({"abc123": ORDER})
stub = StubClient({"abc123": ORDER})
extract.run(db_path=path, covers_dir=Path(tempfile.mkdtemp()), client=stub)
check("extract: an already-cached bundle is not re-fetched", stub.fetched, [])
stub = StubClient({"abc123": ORDER})
extract.run(db_path=path, covers_dir=Path(tempfile.mkdtemp()), client=stub,
            refetch=True)
check("extract: refetch=True fetches it again", stub.fetched, ["abc123"])

# --------------------------------------------------------------------
# cover_path is a URL, not a filesystem path. This block first asserted
# that a non-default covers_dir must appear in the recorded value, and
# that was the wrong desired answer: the front end renders the column as
# `<img src="/${i.cover_path}">` against the viewer's `/covers/<filename>`
# route, so the "covers/" prefix names the ROUTE and is correct whatever
# directory the files sit in. The contract worth pinning is that the two
# halves agree - the recorded URL's last segment is the file that was
# actually written under covers_dir.
# --------------------------------------------------------------------
from humble_catalog import covers as covers_mod                # noqa: E402

covers_dir = Path(tempfile.mkdtemp()) / "artwork"
covers_dir.mkdir(parents=True)
path = fresh_db()
conn = db.connect(path)
conn.execute("INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
             ("graywaters_ebook", "Gray Waters", "ebook"))
conn.commit()
fname = covers_mod.cover_filename("graywaters_ebook")
(covers_dir / fname).write_bytes(b"not-really-an-image")
linked = covers_mod.relink(conn, covers_dir)
recorded = conn.execute(
    "SELECT cover_path FROM items WHERE machine_name='graywaters_ebook'"
).fetchone()["cover_path"]
conn.close()
check("path: relink links the row whose file is present", linked, 1)
check("path: the recorded value is rooted at the viewer's covers route",
      recorded, f"covers/{fname}")
check("path: its last segment is the file actually written under covers_dir",
      (covers_dir / recorded.split("/")[-1]).exists(), True)
check("path: the recorded value is route-rooted regardless of covers_dir",
      recorded.startswith("covers/") and covers_dir.name == "artwork", True)

# The negative side: a row whose file is absent must not be linked.
path = fresh_db()
conn = db.connect(path)
conn.execute("INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
             ("quietharbor_ebook", "The Quiet Harbor", "ebook"))
conn.commit()
check("path: relink links nothing when the file is absent",
      covers_mod.relink(conn, Path(tempfile.mkdtemp())), 0)
check("path: and leaves cover_path null",
      conn.execute("SELECT cover_path FROM items").fetchone()["cover_path"], None)
conn.close()

# --------------------------------------------------------------------
# DRIFT. HumbleBundle order JSON is adversarial per the envelope.
# --------------------------------------------------------------------
with Server({"/api/v1/user/order": (200, JSON, [{"gamekey": "abc123"},
                                                {"no_gamekey": 1}])}):
    check_no_raise("drift: an order entry without a gamekey is skipped",
                   lambda: client().list_order_keys(), ["abc123"], group="DRIFT")

with Server({"/api/v1/user/order": (200, JSON, {"orders": []})}):
    check_no_raise("drift: an order list that is not a list yields no keys",
                   lambda: client().list_order_keys(), [], group="DRIFT")

with Server({"/api/v1/user/order": (200, JSON, ["abc123"])}):
    check_no_raise("drift: an order list of bare strings yields no keys",
                   lambda: client().list_order_keys(), [], group="DRIFT")

check_no_raise(
    "drift: an order whose product is not a dict still caches",
    lambda: run_extract({"abc123": {"gamekey": "abc123", "product": "nope"}})
    and True, True, group="DRIFT")


def group_of(line):
    for label, group in GROUPS.items():
        if line.startswith(label + ":"):
            return group
    return "BROKEN"


def main():
    for line in FAIL:
        print(f"{group_of(line):<6} {line}")
    total = len(PASS) + len(FAIL)
    counts = {}
    for line in FAIL:
        counts[group_of(line)] = counts.get(group_of(line), 0) + 1
    print(f"\nextract-humble: {len(PASS)}/{total} held")
    if FAIL:
        print("  " + ", ".join(f"{n} {g}" for g, n in sorted(counts.items())))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
