"""Known-answer probes for the viewer's item write routes.

Each case states the answer a correct route gives, so a wrong one fails
here rather than reading as "did not crash". The seed mirrors
tests/test_webapp.py::_seed, using titles from the canonical invented
universe in docs/TEST-DATA.md.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import db                      # noqa: E402
from humble_catalog.webapp import create_app       # noqa: E402


def seed(dbp):
    conn = db.connect(dbp)
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, type, publisher) "
        "VALUES ('sas','Salt and Sextant','ebook','Example Press')")
    item_id = cur.lastrowid
    cands = [{"source": "hardcover", "title": "Salt and Sextant",
              "authors": ["Sam Coder"], "genre": "SF", "series": None,
              "series_number": None, "rating": 4.1, "narrator": None,
              "illustrator": None, "extra": {}, "confidence": 0.6}]
    conn.execute(
        "INSERT INTO enrichment (item_id, status, candidates) VALUES (?,?,?)",
        (item_id, "low_confidence", json.dumps(cands)))
    # A second item with NO enrichment row: /choose must cope with it.
    cur2 = conn.execute(
        "INSERT INTO items (machine_name, name, type) "
        "VALUES ('ub','Unrelated Book','ebook')")
    bare_id = cur2.lastrowid
    conn.commit()
    conn.close()
    return item_id, bare_id


def main():
    results = []

    def check(name, got, want):
        ok = got == want
        results.append((ok, name, got, want))

    with tempfile.TemporaryDirectory() as td:
        dbp = str(Path(td) / "probe.db")
        item_id, bare_id = seed(dbp)
        client = create_app(db_path=dbp).test_client()

        # --- baseline: the happy paths must work, or nothing below means
        # anything ---
        check("rating happy path -> 200",
              client.post(f"/api/items/{item_id}/rating",
                          json={"rating": 5}).status_code, 200)
        check("rating happy path stored",
              client.get("/api/items").get_json()["items"][0]["my_rating"], 5)

        # --- known answers: a malformed or unknown-target write must be a
        # 4xx, never a 5xx and never a silent 200. Sibling routes
        # (read-status, comment, user-tags) already answer exactly this
        # way, so these are the project's own contract. ---
        # null clears a rating: catalog.js sends it when you click the star
        # already showing, so this is a real client action, not an edge
        # case. It must survive the validation added for the cases below.
        check("rating null clears -> 200",
              client.post(f"/api/items/{item_id}/rating",
                          json={"rating": None}).status_code, 200)
        check("rating null actually cleared the value",
              client.get("/api/items").get_json()["items"][0]["my_rating"], None)
        check("rating 1 (low end of the star domain) -> 200",
              client.post(f"/api/items/{item_id}/rating",
                          json={"rating": 1}).status_code, 200)

        check("rating on unknown item -> 404",
              client.post("/api/items/99999/rating",
                          json={"rating": 3}).status_code, 404)
        check("rating with no 'rating' key -> 400",
              client.post(f"/api/items/{item_id}/rating",
                          json={}).status_code, 400)
        check("rating with a non-numeric value -> 400",
              client.post(f"/api/items/{item_id}/rating",
                          json={"rating": "five"}).status_code, 400)
        # The widget renders stars 1..5 and clears with null, so 0 and 6 are
        # both outside the domain. Refused rather than clamped: silently
        # altering a value the user sent is the failure mode this task is
        # removing, not a nicety to preserve.
        check("rating above the star domain -> 400",
              client.post(f"/api/items/{item_id}/rating",
                          json={"rating": 99}).status_code, 400)
        check("rating below the star domain -> 400",
              client.post(f"/api/items/{item_id}/rating",
                          json={"rating": 0}).status_code, 400)
        check("rating as a bool (True is an int in Python) -> 400",
              client.post(f"/api/items/{item_id}/rating",
                          json={"rating": True}).status_code, 400)

        check("type with no 'type' key -> 400",
              client.post(f"/api/items/{item_id}/type",
                          json={}).status_code, 400)
        check("type on unknown item -> 404",
              client.post("/api/items/99999/type",
                          json={"type": "comic"}).status_code, 404)

        check("choose on an item with no enrichment row -> 404",
              client.post(f"/api/items/{bare_id}/choose",
                          json={"candidate": 0}).status_code, 404)
        check("choose with no 'candidate' key -> 400",
              client.post(f"/api/items/{item_id}/choose",
                          json={}).status_code, 400)
        check("choose with a non-integer index -> 400",
              client.post(f"/api/items/{item_id}/choose",
                          json={"candidate": "0"}).status_code, 400)

        check("reopen on unknown item -> 404",
              client.post("/api/items/99999/reopen",
                          json={}).status_code, 404)
        # tests/test_webapp.py:329 posts /reopen with NO body at all. The
        # existence check must not turn that into a 400.
        check("reopen with no body at all -> 200",
              client.post(f"/api/items/{item_id}/reopen").status_code, 200)

    width = max(len(n) for _, n, _, _ in results)
    failed = 0
    for ok, name, got, want in results:
        if not ok:
            failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  "
              f"got={got!r} want={want!r}")
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
