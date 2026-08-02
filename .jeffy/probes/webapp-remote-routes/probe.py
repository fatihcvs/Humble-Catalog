"""Known-answer battery for the webapp-remote-routes inventory row.

Covers POST `/api/items/<id>/fetch_url` and POST `/api/bundle-preview` -
the two viewer routes that reach the network.

Scope, stated because it decides what this battery may claim. The NETWORK
behaviour of these routes belongs to rows already swept: `url-import`
(46/46) and `outbound-guard` (49/49) own the scheme allowlist, the
redirect re-check and the routability test, and `bundle-preview-parts`
and `bundle-preview-tiers` own `fetch_bundle`'s host gate and the report.
What is left, and what this row certifies, is the ROUTE's own contract:
how it maps each outcome of those collaborators onto a status code and a
response body.

That is why the collaborators are replaced at the seam here rather than
driven through a real server. A local `http.server` cannot be reached by
either route anyway - `url_import` refuses a loopback address by design
and `fetch_bundle` refuses a non-HumbleBundle host - so a real server
would exercise the refusal path already swept elsewhere and could not
reach the success mapping this row exists to pin. The Lessons rule about
probing a network GUARD with a real server still stands; the guard is
just not what this row covers.

Every title is invented, from docs/TEST-DATA.md. Fresh database per case.
"""
import pathlib
import sys
import tempfile

import requests

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import bundle_preview, db, url_import  # noqa: E402
from humble_catalog.webapp import create_app  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def seeded():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = pathlib.Path(tmp.name)
    conn = db.connect(path)
    cur = conn.execute(
        "INSERT INTO items (machine_name, name) VALUES (?,?)",
        ("salt_sextant", "Salt and Sextant"))
    item_id = cur.lastrowid
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (item_id,))
    conn.commit()
    conn.close()
    return create_app(db_path=str(path)).test_client(), item_id


class Seam:
    """Replace a collaborator for one case, and always put it back."""

    def __init__(self, module, name, fn):
        self.module, self.name, self.fn = module, name, fn

    def __enter__(self):
        self.original = getattr(self.module, self.name)
        setattr(self.module, self.name, self.fn)
        return self

    def __exit__(self, *exc):
        setattr(self.module, self.name, self.original)
        return False


GOOD = {"source": "example_source", "title": "Salt and Sextant",
        "url": "https://example.invalid/x", "confidence": 0.9}


def raises(exc):
    def fn(*args, **kwargs):
        raise exc
    return fn


# ----------------------------------------------------- fetch_url: success

def case_a_resolved_url_comes_back_as_a_candidate():
    client, item_id = seeded()
    with Seam(url_import, "resolve", lambda conn, url: dict(GOOD)):
        resp = client.post(f"/api/items/{item_id}/fetch_url",
                           json={"url": "https://example.invalid/x"})
    check("a resolved url answers 200", resp.status_code, 200)
    check("and returns the candidate the resolver produced",
          resp.get_json()["candidate"]["title"], "Salt and Sextant")
    check("with no link_only marker on the success path",
          "link_only" in resp.get_json()["candidate"], False)


def case_the_route_passes_the_stripped_url_through():
    seen = {}

    def resolve(conn, url):
        seen["url"] = url
        return dict(GOOD)

    client, item_id = seeded()
    with Seam(url_import, "resolve", resolve):
        client.post(f"/api/items/{item_id}/fetch_url",
                    json={"url": "  https://example.invalid/x  "})
    check("surrounding whitespace is stripped before the resolver sees it",
          seen.get("url"), "https://example.invalid/x")


# --------------------------------------------- fetch_url: the link-only path

def case_metadata_unavailable_degrades_to_a_link_only_candidate():
    # Documented: a source that cannot answer must still let the owner
    # keep the url, so the route synthesises a candidate from the item's
    # own name rather than failing the request.
    client, item_id = seeded()
    with Seam(url_import, "resolve",
              raises(url_import.MetadataUnavailable("no metadata here"))):
        resp = client.post(f"/api/items/{item_id}/fetch_url",
                           json={"url": "https://example.invalid/x"})
    cand = resp.get_json()["candidate"]
    check("the request still succeeds", resp.status_code, 200)
    check("the candidate is marked link_only", cand["link_only"], True)
    check("it carries the ITEM's title, not the source's",
          cand["title"], "Salt and Sextant")
    check("the url is preserved", cand["url"], "https://example.invalid/x")
    check("and the reason names the failure",
          "no metadata here" in cand["reason"], True)


def case_a_network_error_takes_the_same_link_only_path():
    client, item_id = seeded()
    with Seam(url_import, "resolve",
              raises(requests.ConnectionError("upstream is down"))):
        resp = client.post(f"/api/items/{item_id}/fetch_url",
                           json={"url": "https://example.invalid/x"})
    cand = resp.get_json()["candidate"]
    check("a network error still answers 200", resp.status_code, 200)
    check("and degrades to link_only rather than failing",
          cand["link_only"], True)
    check("with the network error as the reason",
          "upstream is down" in cand["reason"], True)


def case_the_link_only_source_is_the_url_host():
    client, item_id = seeded()
    with Seam(url_import, "resolve",
              raises(url_import.MetadataUnavailable("none"))):
        resp = client.post(f"/api/items/{item_id}/fetch_url",
                           json={"url": "https://books.example.invalid/x"})
    check("the synthesised candidate is attributed to the url's host",
          resp.get_json()["candidate"]["source"], "books.example.invalid")


def case_an_unknown_item_on_the_link_only_path_is_404():
    # The item row is read INSIDE the except branch, to borrow its title;
    # a missing row there is a missing target rather than a bad url.
    client, _item_id = seeded()
    with Seam(url_import, "resolve",
              raises(url_import.MetadataUnavailable("none"))):
        resp = client.post("/api/items/9999/fetch_url",
                           json={"url": "https://example.invalid/x"})
    check("an unknown item answers 404 on the degraded path",
          resp.status_code, 404)
    check("and says so", resp.get_json()["error"], "no such item")


# ------------------------------------------------ fetch_url: the refusals

def case_a_rejected_url_is_400_and_never_degrades():
    # Documented ordering: MetadataUnavailable is caught BEFORE ValueError
    # precisely so a REJECTED url cannot become a link-only candidate.
    client, item_id = seeded()
    with Seam(url_import, "resolve", raises(ValueError("unsupported scheme"))):
        resp = client.post(f"/api/items/{item_id}/fetch_url",
                           json={"url": "javascript:alert(1)"})
    check("a rejected url answers 400", resp.status_code, 400)
    check("the message is the resolver's own",
          resp.get_json()["error"], "unsupported scheme")
    check("and no candidate is offered at all",
          "candidate" in resp.get_json(), False)


def case_an_absent_or_unusable_url_never_reaches_the_resolver():
    def explode(*a, **k):
        raise AssertionError("the resolver was called for an unusable url")

    client, item_id = seeded()
    with Seam(url_import, "resolve", explode):
        for body in [{}, {"url": ""}, {"url": "   "}, {"url": 5},
                     {"url": None}, {"url": ["x"]}]:
            resp = client.post(f"/api/items/{item_id}/fetch_url", json=body)
            check(f"unusable url refused: {body}", resp.status_code, 400)


# ------------------------------------------------------- bundle-preview

def case_a_bundle_url_returns_the_report():
    client, _item_id = seeded()
    bundle = {"basic_data": {"human_name": "Bundle One", "currency": "USD"},
              "tier_display_data": {"t1": {"tier_item_machine_names": ["a"]}},
              "tier_pricing_data": {"t1": {"price|money": {"amount": 12.0}}},
              "tier_item_data": {"a": {"human_name": "Nightjar Post"}}}
    with Seam(bundle_preview, "fetch_bundle", lambda url: bundle):
        resp = client.post("/api/bundle-preview",
                           json={"url": "https://www.humblebundle.com/books/x"})
    body = resp.get_json()
    check("a bundle url answers 200", resp.status_code, 200)
    check("the report names the bundle", body["name"], "Bundle One")
    check("and counts the tier's items", body["tiers"][0]["total"], 1)
    check("the report echoes the url it was asked about",
          body["url"], "https://www.humblebundle.com/books/x")


def case_a_refused_bundle_url_is_400():
    client, _item_id = seeded()
    with Seam(bundle_preview, "fetch_bundle",
              raises(ValueError("not a HumbleBundle URL: example.invalid"))):
        resp = client.post("/api/bundle-preview",
                           json={"url": "https://example.invalid/x"})
    check("a non-Humble url answers 400", resp.status_code, 400)
    check("with the refusal's own message",
          "not a HumbleBundle URL" in resp.get_json()["error"], True)


def case_an_upstream_failure_is_502_not_400():
    # Documented: 502 keeps a retired bundle distinguishable from a url
    # the project refused. The two must not collapse to one code.
    client, _item_id = seeded()
    with Seam(bundle_preview, "fetch_bundle",
              raises(requests.ConnectionError("upstream is down"))):
        resp = client.post("/api/bundle-preview",
                           json={"url": "https://www.humblebundle.com/books/x"})
    check("an upstream failure answers 502", resp.status_code, 502)
    check("and carries the reason",
          "upstream is down" in resp.get_json()["error"], True)


def case_the_two_failure_codes_are_distinguishable():
    # The property the split exists for, asserted as a relation.
    client, _item_id = seeded()
    with Seam(bundle_preview, "fetch_bundle", raises(ValueError("refused"))):
        refused = client.post("/api/bundle-preview",
                              json={"url": "https://www.humblebundle.com/x"})
    with Seam(bundle_preview, "fetch_bundle",
              raises(requests.ConnectionError("down"))):
        upstream = client.post("/api/bundle-preview",
                               json={"url": "https://www.humblebundle.com/x"})
    check("a refusal and an upstream failure get different codes",
          refused.status_code != upstream.status_code, True)


def case_bundle_preview_refuses_an_unusable_url_without_fetching():
    def explode(*a, **k):
        raise AssertionError("fetch_bundle was called for an unusable url")

    client, _item_id = seeded()
    with Seam(bundle_preview, "fetch_bundle", explode):
        for body in [{}, {"url": ""}, {"url": "   "}, {"url": 5},
                     {"url": None}, [1, 2, 3]]:
            resp = client.post("/api/bundle-preview", json=body)
            check(f"unusable bundle url refused: {body}", resp.status_code, 400)


def case_bundle_preview_writes_nothing_to_the_catalog():
    # The module documents that the report is a question, not a fact about
    # the library: nothing here may persist. Asserted by comparing the
    # whole items table either side of a successful preview.
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = pathlib.Path(tmp.name)
    conn = db.connect(path)
    cur = conn.execute("INSERT INTO items (machine_name, name) VALUES (?,?)",
                       ("salt_sextant", "Salt and Sextant"))
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)", (cur.lastrowid,))
    conn.commit()
    before = conn.execute("SELECT * FROM items").fetchall()
    conn.close()

    client = create_app(db_path=str(path)).test_client()
    bundle = {"basic_data": {"human_name": "Bundle One"},
              "tier_display_data": {"t1": {"tier_item_machine_names": ["a"]}},
              "tier_item_data": {"a": {"human_name": "Nightjar Post"}}}
    with Seam(bundle_preview, "fetch_bundle", lambda url: bundle):
        client.post("/api/bundle-preview",
                    json={"url": "https://www.humblebundle.com/books/x"})

    conn = db.connect(path)
    after = conn.execute("SELECT * FROM items").fetchall()
    conn.close()
    check("a preview leaves the items table byte for byte unchanged",
          [tuple(r) for r in after], [tuple(r) for r in before])


CASES = [v for k, v in sorted(globals().items()) if k.startswith("case_")]

if __name__ == "__main__":
    for fn in CASES:
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            FAIL.append(fn.__name__)
            print(f"  FAIL {fn.__name__} raised: "
                  f"{type(exc).__name__}: {exc}")
    total = len(PASS) + len(FAIL)
    print(f"webapp-remote-routes: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
