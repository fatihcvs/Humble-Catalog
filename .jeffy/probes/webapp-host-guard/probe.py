"""Known-answer probes for the viewer's loopback Host guard.

This is the viewer's only security boundary, so the negative side matters
more than the positive one: the cases below are the shapes an attacker
would actually send. A guard that accepted everything would pass a
liveness probe, so every case states the answer explicitly.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import db                                  # noqa: E402
from humble_catalog.webapp import create_app, host_is_loopback  # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


# --- accepted: the three loopback authorities, with and without a port.
# The port is deliberately not pinned, so a --port override still works. ---
for host in ["127.0.0.1", "127.0.0.1:8087", "127.0.0.1:9999",
             "localhost", "localhost:8087", "LOCALHOST",
             "LocalHost:8087", "[::1]", "[::1]:8087"]:
    check(f"accepts {host!r}", host_is_loopback(host), True)

# Surrounding whitespace is stripped before the comparison.
check("accepts ' localhost ' (trimmed)", host_is_loopback(" localhost "), True)

# --- refused: everything else. These are the real attack shapes. ---
for host in [
        "evil.example.com",
        "evil.example.com:8087",
        # the classic suffix trick: a name that merely ENDS in a loopback
        # label, or merely starts with one
        "localhost.evil.example.com",
        "127.0.0.1.evil.example.com",
        "notlocalhost",
        "localhosts",
        # an address that resolves to loopback but is not a loopback NAME:
        # the guard is deliberately name-based, so these must be refused
        "127.0.0.2",
        "127.1",
        "0.0.0.0",
        "[::ffff:127.0.0.1]",
        # userinfo smuggling
        "localhost@evil.example.com",
        "evil.example.com#localhost",
        "evil.example.com?x=localhost",
        # an empty or absent Host fails closed
        "",
        "   ",
]:
    check(f"refuses {host!r}", host_is_loopback(host), False)

check("refuses a missing Host header (None)", host_is_loopback(None), False)

# --- the guard must run BEFORE routing, on reads and writes alike, and on
# routes that do not exist. ---
with tempfile.TemporaryDirectory() as td:
    dbp = str(Path(td) / "probe.db")
    conn = db.connect(dbp)
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('sas','Salt and Sextant','ebook')")
    conn.commit()
    conn.close()
    client = create_app(db_path=dbp).test_client()

    evil = {"Host": "evil.example.com"}
    check("foreign host is refused on a GET read",
          client.get("/api/items", headers=evil).status_code, 403)
    check("foreign host is refused on a POST write",
          client.post("/api/items/1/rating", json={"rating": 5},
                      headers=evil).status_code, 403)
    check("foreign host is refused on an unknown route (403 before routing)",
          client.get("/api/no-such-route", headers=evil).status_code, 403)
    check("foreign host is refused on the static index",
          client.get("/", headers=evil).status_code, 403)
    # and the refusal must not leak catalog contents in its body
    _body = client.get("/api/items", headers=evil).data
    check("the refusal body names no catalog item",
          b"Salt and Sextant" not in _body, True)

    for host in ["127.0.0.1:8087", "localhost:8087", "[::1]:8087"]:
        check(f"loopback caller {host} still reaches the app",
              client.get("/api/items", headers={"Host": host}).status_code, 200)

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
