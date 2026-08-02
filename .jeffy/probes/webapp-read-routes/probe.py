"""Known-answer battery for the webapp-read-routes inventory row.

Covers the viewer's GET surface in humble_catalog/webapp/__init__.py:
`/`, `/covers/<path>`, `/api/items`, `/api/stats`, `/api/keys`,
`/api/review`, `/api/duplicates`, `/api/status`.

Two of these routes exist to RESHAPE a report the CLI also prints, and
both say in their comments that the CLI and the panel must not be able to
disagree. That is an invariant a wrong answer would break, so it is
asserted directly against the report function rather than by eyeballing
the JSON - which is the difference between this and a probe that only
checks a 200 came back.

The Host guard is not re-probed here; it has its own row and battery.

Titles are the invented library from docs/TEST-DATA.md.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, keys, stats                   # noqa: E402
from humble_catalog.webapp import create_app                 # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def seeded(covers_dir=None):
    """A catalog with an edition pair, a duplicate pair, a review row and a
    running phase. Fresh file per call."""
    root = Path(tempfile.mkdtemp())
    path = root / "catalog.db"
    conn = db.connect(path)
    conn.execute("INSERT INTO bundles (gamekey, name, url) VALUES "
                 "('abc123', 'Humble Book Bundle: Test by Example Press', "
                 "'https://www.humblebundle.com/downloads?key=abc123')")
    rows = [("salt_e", "Salt and Sextant", "ebook"),
            ("salt_a", "Salt and Sextant Audiobook", "audiobook"),
            ("starless1", "The Starless War", "audiobook"),
            ("starless2", "The Starless War", "audiobook"),
            ("quiet", "The Quiet Harbor", "ebook")]
    for machine_name, name, type_ in rows:
        cur = conn.execute("INSERT INTO items (machine_name, name, type) "
                           "VALUES (?,?,?)", (machine_name, name, type_))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
        conn.execute("INSERT INTO item_bundles (item_id, gamekey) "
                     "VALUES (?, 'abc123')", (cur.lastrowid,))
    conn.execute("UPDATE enrichment SET status='low_confidence', candidates=? "
                 "WHERE item_id=5",
                 (json.dumps([{"title": "The Quiet Harbor", "confidence": 0.7},
                              {"title": "A Quiet Life in Harbors",
                               "confidence": 0.4}]),))
    # run_status is keyed on `command`, and its progress label is
    # `current`; there is no `label` column.
    conn.execute("INSERT INTO run_status (command, phase, done, total, current) "
                 "VALUES ('extract', 'Bundle', 1, 3, 'Gray Waters')")
    conn.execute("INSERT INTO run_status (command, phase, done, total, current) "
                 "VALUES ('enrich', 'done', 3, 3, NULL)")
    conn.commit()
    conn.close()
    return path, root


path, root = seeded()
covers_dir = root / "covers"
covers_dir.mkdir()
(covers_dir / "graywaters.jpg").write_bytes(b"\xff\xd8not-really-a-jpeg")
(root / "secret.txt").write_text("must not be served")

app = create_app(db_path=path, covers_dir=covers_dir)
app.config["SERVER_NAME"] = None
client = app.test_client()
HOST = {"Host": "127.0.0.1:8087"}


def get(url):
    return client.get(url, headers=HOST)


# --------------------------------------------------------------------
# / and /covers
# --------------------------------------------------------------------
resp = get("/")
check("index: answers 200", resp.status_code, 200)
check("index: serves the viewer document", b"<html" in resp.data.lower(), True)

resp = get("/covers/graywaters.jpg")
check("covers: an existing file is served", resp.status_code, 200)
check("covers: the bytes are the file's", resp.data, b"\xff\xd8not-really-a-jpeg")
check("covers: a missing file is 404",
      get("/covers/nope.jpg").status_code, 404)
# The route interpolates a user-supplied path into a filesystem read, so
# the traversal cases are the ones worth stating. The property asserted is
# that the file outside the directory is never SERVED, not that a
# particular status comes back: the leading-slash attempt answers 308,
# because Werkzeug normalizes the doubled slash, and the normalized path
# then 404s - equally safe. A status allow-list called that a finding.
for attempt in ("../secret.txt", "..%2Fsecret.txt", "....//secret.txt",
                "/etc/passwd", "..\\secret.txt", "%2e%2e%2fsecret.txt"):
    resp = client.get(f"/covers/{attempt}", headers=HOST, follow_redirects=True)
    check(f"covers: {attempt!r} never serves the file outside the directory",
          resp.status_code != 200 and b"must not be served" not in resp.data,
          True)

# --------------------------------------------------------------------
# /api/items, and the editions view attached on top of it
# --------------------------------------------------------------------
payload = get("/api/items").get_json()
items = {i["name"]: i for i in payload["items"]}
check("items: every catalog row is returned", len(payload["items"]), 5)
check("items: the edition pair carries a sibling link",
      [e["name"] for e in items["Salt and Sextant"]["editions"]],
      ["Salt and Sextant Audiobook"])
check("items: the link is mutual",
      [e["name"] for e in items["Salt and Sextant Audiobook"]["editions"]],
      ["Salt and Sextant"])
check("items: the sibling link names the other item's type",
      items["Salt and Sextant"]["editions"][0]["type"], "audiobook")
# Documented: the key is ABSENT, not [], for rows with no sibling - which
# is nearly every row on a real catalog.
check("items: a row with no sibling has no editions key at all",
      "editions" in items["The Quiet Harbor"], False)
check("items: a same-type duplicate pair is NOT an edition link",
      "editions" in items["The Starless War"], False)

# --------------------------------------------------------------------
# /api/stats and /api/keys - the reshape-only routes
# --------------------------------------------------------------------
conn = db.connect(path)
sections, total = stats.report(db.fetch_items(conn))
report = get("/api/stats").get_json()
check("stats: the total is the report's total", report["total"], total)
check("stats: every section key and label is the report's",
      [(s["key"], s["label"]) for s in report["sections"]],
      [(key, label) for key, label, _rows in sections])
check("stats: every row of every section is the report's, in order - the "
      "invariant that the panel and the CLI cannot disagree",
      [[(r["label"], r["count"]) for r in s["rows"]]
       for s in report["sections"]],
      [[(row_label, count) for row_label, count in rows]
       for _key, _label, rows in sections])
check("stats: the route takes no parameters, so nothing about the library "
      "can reach a query string",
      get("/api/stats?type=ebook").get_json()["total"], total)

check("keys: the payload is exactly keys.report", get("/api/keys").get_json(),
      json.loads(json.dumps(keys.report(conn))))
conn.close()

# --------------------------------------------------------------------
# /api/review
# --------------------------------------------------------------------
review = get("/api/review").get_json()["items"]
check("review: only rows needing review are listed", len(review), 1)
check("review: the row is the low-confidence one",
      review[0]["name"], "The Quiet Harbor")
check("review: best is the top candidate's confidence", review[0]["best"], 0.7)
check("review: candidates come back sorted by confidence",
      [c["confidence"] for c in review[0]["candidates"]], [0.7, 0.4])
check("review: a matched row is not offered for review",
      all(r["status"] in ("low_confidence", "unmatched") for r in review), True)

# --------------------------------------------------------------------
# /api/duplicates
# --------------------------------------------------------------------
groups = get("/api/duplicates").get_json()["groups"]
check("duplicates: one group is reported", len(groups), 1)
check("duplicates: it holds the same-name same-type pair",
      sorted(m["name"] for m in groups[0]),
      ["The Starless War", "The Starless War"])
check("duplicates: a member carries its bundles",
      groups[0][0]["bundles"],
      ["Humble Book Bundle: Test by Example Press"])
check("duplicates: genre comes back as a list, not a JSON string",
      groups[0][0]["genre"], [])
check("duplicates: edited is a bool and the raw hand_edited column is "
      "popped rather than leaked",
      (groups[0][0]["edited"], "hand_edited" in groups[0][0]), (False, False))
check("duplicates: the cross-format pair is NOT listed here - that is the "
      "editions view's question",
      any("Salt and Sextant" in m["name"] for g in groups for m in g), False)

# --------------------------------------------------------------------
# /api/status
# --------------------------------------------------------------------
runs = get("/api/status").get_json()["runs"]
check("status: only unfinished phases are reported", len(runs), 1)
check("status: the running command is the one returned",
      runs[0]["command"], "extract")
check("status: a phase marked done is filtered out",
      all(r["phase"] != "done" for r in runs), True)

# --------------------------------------------------------------------
# An empty catalog must not break any read route.
# --------------------------------------------------------------------
empty_path, empty_root = seeded()
conn = db.connect(empty_path)
for table in ("item_bundles", "enrichment", "items", "bundles", "run_status"):
    conn.execute(f"DELETE FROM {table}")
conn.commit()
conn.close()
empty = create_app(db_path=empty_path,
                   covers_dir=empty_root / "covers").test_client()
for route, key, want in (("/api/items", "items", []),
                         ("/api/review", "items", []),
                         ("/api/duplicates", "groups", []),
                         ("/api/status", "runs", [])):
    resp = empty.get(route, headers=HOST)
    check(f"empty: {route} answers 200", resp.status_code, 200)
    check(f"empty: {route} returns an empty {key}",
          resp.get_json()[key], want)
check("empty: /api/stats still answers with a zero total",
      empty.get("/api/stats", headers=HOST).get_json()["total"], 0)
check("empty: /api/keys still answers 200",
      empty.get("/api/keys", headers=HOST).status_code, 200)


def main():
    for line in FAIL:
        print(f"BROKEN {line}")
    total = len(PASS) + len(FAIL)
    print(f"\nwebapp-read-routes: {len(PASS)}/{total} held")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
