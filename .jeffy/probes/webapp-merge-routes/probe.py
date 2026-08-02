"""Known-answer battery for the webapp-merge-routes inventory row.

Covers POST `/api/merge`, POST `/api/dismiss_pair` and the type-mismatch
refusal, driven through Flask's test client against a real database.

These routes DESTROY a row, so the cases that matter most are the ones
asserting what must NOT happen: a refusal has to leave both rows intact,
and a merge must move the dropped name into `merges` rather than losing
it. A liveness probe that only checked status codes would certify a
route that answered 200 and deleted the wrong row.

Every title is invented, from docs/TEST-DATA.md. Fresh database per case.
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db  # noqa: E402
from humble_catalog.webapp import create_app  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def app_with(*items):
    """(client, conn_path, {machine_name: id}) for a fresh seeded catalog."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = pathlib.Path(tmp.name)
    conn = db.connect(path)
    ids = {}
    for machine_name, name, type_ in items:
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
            (machine_name, name, type_))
        ids[machine_name] = cur.lastrowid
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    conn.commit()
    conn.close()
    return create_app(db_path=str(path)).test_client(), path, ids


def rows_of(path):
    conn = db.connect(path)
    items = {r["machine_name"]: r["id"]
             for r in conn.execute("SELECT id, machine_name FROM items")}
    merges = {r["dropped_machine_name"]: r["kept_item_id"]
              for r in conn.execute("SELECT * FROM merges")}
    pairs = [(r["a"], r["b"]) for r in conn.execute("SELECT * FROM dismissed_pairs")]
    conn.close()
    return items, merges, pairs


BOOKS = [("widget_svc", "Building Widget Services", "ebook"),
         ("widget_svc_2e", "Building Widget Services 2e", "ebook")]


# ------------------------------------------------------------------- merge

def case_a_merge_drops_one_row_and_records_it():
    client, path, ids = app_with(*BOOKS)
    resp = client.post("/api/merge", json={"keep_id": ids["widget_svc"],
                                           "drop_id": ids["widget_svc_2e"]})
    check("a valid merge answers ok", resp.status_code, 200)
    items, merges, _ = rows_of(path)
    check("the dropped row is gone and the kept one remains",
          sorted(items), ["widget_svc"])
    check("and the dropped machine_name is recorded against the kept id",
          merges, {"widget_svc_2e": ids["widget_svc"]})


def case_a_merge_of_different_types_is_refused_and_deletes_nothing():
    # The documented refusal: an ebook and its audiobook are different
    # files from different bundles and stay separate rows.
    client, path, ids = app_with(
        ("copper_ebook", "The Copper Almanac", "ebook"),
        ("copper_audio", "The Copper Almanac", "audiobook"))
    resp = client.post("/api/merge", json={"keep_id": ids["copper_ebook"],
                                           "drop_id": ids["copper_audio"]})
    check("a type mismatch is refused", resp.status_code, 400)
    check("and the message names the reason rather than being generic",
          "different types" in resp.get_json()["error"], True)
    items, merges, _ = rows_of(path)
    check("both rows survive the refusal", sorted(items),
          ["copper_audio", "copper_ebook"])
    check("and nothing is recorded in merges", merges, {})


def case_merge_refusals_delete_nothing():
    bad = [
        ("the same id twice", lambda i: {"keep_id": i, "drop_id": i}),
        ("a missing drop_id", lambda i: {"keep_id": i}),
        ("a string id", lambda i: {"keep_id": i, "drop_id": "2"}),
        ("a bool id", lambda i: {"keep_id": i, "drop_id": True}),
        ("a float id", lambda i: {"keep_id": i, "drop_id": 2.0}),
        ("an unknown id", lambda i: {"keep_id": i, "drop_id": 9999}),
    ]
    for label, build in bad:
        client, path, ids = app_with(*BOOKS)
        resp = client.post("/api/merge", json=build(ids["widget_svc"]))
        check(f"refused: {label}", resp.status_code, 400)
        items, merges, _ = rows_of(path)
        check(f"nothing deleted: {label}", len(items), 2)
        check(f"nothing recorded: {label}", merges, {})


def case_bool_is_not_an_int_here():
    # bool is a subclass of int in Python, so an unguarded isinstance
    # check would accept True as an id and merge row 1 into itself.
    client, path, _ids = app_with(*BOOKS)
    resp = client.post("/api/merge", json={"keep_id": True, "drop_id": False})
    check("True and False are not two distinct item ids", resp.status_code, 400)
    items, _merges, _ = rows_of(path)
    check("and nothing was deleted", len(items), 2)


# ------------------------------------------------------------ dismiss_pair

def case_dismissing_a_pair_records_it_without_deleting():
    client, path, ids = app_with(*BOOKS)
    resp = client.post("/api/dismiss_pair",
                       json={"id_a": ids["widget_svc"],
                             "id_b": ids["widget_svc_2e"]})
    check("a valid dismissal answers ok", resp.status_code, 200)
    items, merges, pairs = rows_of(path)
    check("both rows survive - a dismissal is not a merge", len(items), 2)
    check("nothing is recorded in merges", merges, {})
    check("and the pair is recorded once",
          [tuple(sorted(p)) for p in pairs],
          [("widget_svc", "widget_svc_2e")])


def case_a_pair_is_stored_in_a_stable_order():
    # Stored one way round, so dismissing a pair twice - in either order -
    # cannot produce two rows that a later filter would have to reconcile.
    client, path, ids = app_with(*BOOKS)
    client.post("/api/dismiss_pair", json={"id_a": ids["widget_svc"],
                                           "id_b": ids["widget_svc_2e"]})
    client.post("/api/dismiss_pair", json={"id_a": ids["widget_svc_2e"],
                                           "id_b": ids["widget_svc"]})
    _items, _merges, pairs = rows_of(path)
    check("dismissing the same pair both ways round stores one row",
          len(pairs), 1)


def case_dismiss_refusals():
    bad = [
        ("the same id twice", lambda i: {"id_a": i, "id_b": i}),
        ("a missing id_b", lambda i: {"id_a": i}),
        ("a string id", lambda i: {"id_a": i, "id_b": "2"}),
        ("a bool id", lambda i: {"id_a": i, "id_b": True}),
        ("an unknown id", lambda i: {"id_a": i, "id_b": 9999}),
    ]
    for label, build in bad:
        client, path, ids = app_with(*BOOKS)
        resp = client.post("/api/dismiss_pair", json=build(ids["widget_svc"]))
        check(f"dismissal refused: {label}", resp.status_code, 400)
        _items, _merges, pairs = rows_of(path)
        check(f"nothing recorded: {label}", pairs, [])


def case_a_dismissed_pair_stops_being_offered_as_a_duplicate():
    # The property the feature exists for, end to end through the route
    # that reads it back.
    #
    # A case-only pair, not the 2e edition pair used above: `dedupe`
    # groups on an EXACT key after normalization, and an edition suffix
    # is `editions.edition_key`'s business, so the two rows above are
    # deliberately not a duplicate group.
    client, path, ids = app_with(("gw_upper", "Gray Waters", "ebook"),
                                 ("gw_lower", "gray waters", "ebook"))
    before = client.get("/api/duplicates").get_json()["groups"]
    check("the pair is offered as a duplicate before dismissal",
          len(before), 1)
    client.post("/api/dismiss_pair", json={"id_a": ids["gw_upper"],
                                           "id_b": ids["gw_lower"]})
    after = client.get("/api/duplicates").get_json()["groups"]
    check("and is not offered after it", after, [])


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
    print(f"webapp-merge-routes: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
