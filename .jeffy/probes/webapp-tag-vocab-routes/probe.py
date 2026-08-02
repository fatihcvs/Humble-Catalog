"""Known-answer battery for the webapp-tag-vocab-routes inventory row.

Covers POST `/api/genres/{rename,delete}` and
`/api/user-tags/{rename,delete,bulk}`, plus the `tags` entry check on
`/api/items/<id>/user-tags` that shares their boundary.

These routes rewrite a VOCABULARY across every row that uses it, so the
cases assert which rows moved and which did not, and the `changed` count
each route reports. A liveness probe would certify a rename that answered
200 and renamed nothing, or one that reported 3 while touching 1.

Genre and user tags are separate pools that must not leak into each
other - that is the whole reason these five routes exist as two families -
so every case checks the OTHER pool is untouched.

Every tag and title is invented, from docs/TEST-DATA.md. Fresh database
per case.
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


def seeded(rows):
    """rows: [(machine_name, name, genre_list, user_tag_list)]."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = pathlib.Path(tmp.name)
    conn = db.connect(path)
    ids = {}
    for machine_name, name, genres, user_tags in rows:
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, user_tags) VALUES (?,?,?)",
            (machine_name, name, db.tags_to_json(user_tags) if user_tags else None))
        ids[machine_name] = cur.lastrowid
        conn.execute(
            "INSERT INTO enrichment (item_id, genre) VALUES (?,?)",
            (cur.lastrowid, db.tags_to_json(genres) if genres else None))
    conn.commit()
    conn.close()
    return create_app(db_path=str(path)).test_client(), path, ids


def vocab(path):
    conn = db.connect(path)
    genres = {r["id"]: db.tags_from_json(r["genre"])
              for r in conn.execute("SELECT item_id AS id, genre FROM enrichment")}
    tags = {r["id"]: db.tags_from_json(r["user_tags"])
            for r in conn.execute("SELECT id, user_tags FROM items")}
    conn.close()
    return genres, tags


ROWS = [("a_one", "Salt and Sextant", ["Mystery"], ["lent out"]),
        ("b_two", "Nightjar Post", ["Mystery"], ["to reread"]),
        ("c_three", "Unrelated Book", ["Cooking"], None)]


# ------------------------------------------------------------ genre rename

def case_renaming_a_genre_moves_every_row_that_used_it():
    client, path, ids = seeded(ROWS)
    resp = client.post("/api/genres/rename",
                       json={"old": "Mystery", "new": "Detective"})
    check("the route reports how many rows moved",
          (resp.status_code, resp.get_json()["changed"]), (200, 2))
    genres, tags = vocab(path)
    check("both rows carry the new spelling",
          [genres[ids["a_one"]], genres[ids["b_two"]]],
          [["Detective"], ["Detective"]])
    check("the row that never used it is untouched",
          genres[ids["c_three"]], ["Cooking"])
    check("and the user-tag pool is untouched",
          tags[ids["a_one"]], ["lent out"])


def case_renaming_an_absent_genre_is_a_404_and_changes_nothing():
    client, path, ids = seeded(ROWS)
    resp = client.post("/api/genres/rename",
                       json={"old": "No Such Genre", "new": "Detective"})
    check("an unknown genre is a 404", resp.status_code, 404)
    genres, _tags = vocab(path)
    check("and nothing moved", genres[ids["a_one"]], ["Mystery"])


def case_deleting_a_genre_removes_it_from_every_row():
    client, path, ids = seeded(ROWS)
    resp = client.post("/api/genres/delete", json={"tag": "Mystery"})
    check("the route reports how many rows changed",
          (resp.status_code, resp.get_json()["changed"]), (200, 2))
    genres, _tags = vocab(path)
    check("the rows that used it lose it",
          [genres[ids["a_one"]], genres[ids["b_two"]]], [[], []])
    check("the other row keeps its own", genres[ids["c_three"]], ["Cooking"])


# -------------------------------------------------------- user tag family

def case_renaming_a_user_tag_touches_only_that_pool():
    client, path, ids = seeded(ROWS)
    resp = client.post("/api/user-tags/rename",
                       json={"old": "lent out", "new": "on loan"})
    check("the rename reports one row",
          (resp.status_code, resp.get_json()["changed"]), (200, 1))
    genres, tags = vocab(path)
    check("the user tag moved", tags[ids["a_one"]], ["on loan"])
    check("the other row's user tag is untouched",
          tags[ids["b_two"]], ["to reread"])
    check("and no genre moved", genres[ids["a_one"]], ["Mystery"])


def case_user_tags_are_not_titleized_and_genres_are():
    # The documented asymmetry between the two pools: the owner's own
    # vocabulary keeps the casing they typed.
    client, path, ids = seeded(ROWS)
    client.post("/api/user-tags/rename", json={"old": "lent out",
                                               "new": "borrowed BY sam"})
    client.post("/api/genres/rename", json={"old": "Cooking",
                                            "new": "food writing"})
    genres, tags = vocab(path)
    check("a user tag keeps the casing it was given",
          tags[ids["a_one"]], ["borrowed BY sam"])
    check("a genre is titleized", genres[ids["c_three"]], ["Food Writing"])


def case_deleting_a_user_tag_leaves_genres_alone():
    client, path, ids = seeded(ROWS)
    resp = client.post("/api/user-tags/delete", json={"tag": "lent out"})
    check("the delete reports one row",
          (resp.status_code, resp.get_json()["changed"]), (200, 1))
    genres, tags = vocab(path)
    check("the tag is gone", tags[ids["a_one"]], [])
    check("the genre pool is untouched", genres[ids["a_one"]], ["Mystery"])


def case_a_name_that_differs_only_by_case_is_the_same_tag():
    client, path, ids = seeded(ROWS)
    resp = client.post("/api/genres/delete", json={"tag": "mystery"})
    check("a differently-cased name matches the stored spelling",
          resp.status_code, 200)
    genres, _tags = vocab(path)
    check("and the rows lost it", genres[ids["a_one"]], [])


# ---------------------------------------------------------------- bulk

def case_bulk_add_and_remove_are_both_exercised():
    client, path, ids = seeded(ROWS)
    target = [ids["a_one"], ids["c_three"]]
    added = client.post("/api/user-tags/bulk",
                        json={"ids": target, "tag": "boxed", "action": "add"})
    check("add answers ok", added.status_code, 200)
    _genres, tags = vocab(path)
    check("the tag is on both targets",
          ["boxed" in (tags[i] or []) for i in target], [True, True])
    check("and not on the row that was not named",
          "boxed" in (tags[ids["b_two"]] or []), False)

    removed = client.post("/api/user-tags/bulk",
                          json={"ids": target, "tag": "boxed",
                                "action": "remove"})
    check("remove answers ok", removed.status_code, 200)
    _genres, tags = vocab(path)
    check("and the tag is gone from both",
          ["boxed" in (tags[i] or []) for i in target], [False, False])


def case_bulk_add_preserves_the_tags_already_there():
    client, path, ids = seeded(ROWS)
    client.post("/api/user-tags/bulk",
                json={"ids": [ids["a_one"]], "tag": "boxed", "action": "add"})
    _genres, tags = vocab(path)
    check("a bulk add is a union, not a replacement",
          sorted(tags[ids["a_one"]]), ["boxed", "lent out"])


def case_bulk_refusals():
    bad = [
        ("ids absent", {"tag": "boxed", "action": "add"}),
        ("ids empty", {"ids": [], "tag": "boxed", "action": "add"}),
        ("ids not a list", {"ids": 5, "tag": "boxed", "action": "add"}),
        ("a non-int id", {"ids": ["1"], "tag": "boxed", "action": "add"}),
        ("tag absent", {"ids": [1], "action": "add"}),
        ("tag blank", {"ids": [1], "tag": "   ", "action": "add"}),
        ("action absent", {"ids": [1], "tag": "boxed"}),
        ("action unknown", {"ids": [1], "tag": "boxed", "action": "toggle"}),
    ]
    for label, body in bad:
        client, path, _ids = seeded(ROWS)
        resp = client.post("/api/user-tags/bulk", json=body)
        check(f"bulk refused: {label}", resp.status_code, 400)
        _genres, tags = vocab(path)
        check(f"bulk changed nothing: {label}",
              sorted(t for v in tags.values() for t in (v or [])),
              ["lent out", "to reread"])


def case_an_unknown_id_in_bulk_is_ignored_not_refused():
    # Documented: the catalog can change under a page open a while.
    client, path, ids = seeded(ROWS)
    resp = client.post("/api/user-tags/bulk",
                       json={"ids": [ids["a_one"], 9999], "tag": "boxed",
                             "action": "add"})
    check("an unknown id does not refuse the whole request",
          resp.status_code, 200)
    _genres, tags = vocab(path)
    check("and the known row was still tagged",
          "boxed" in tags[ids["a_one"]], True)


# ---------------------------------------------------- I1: non-string fields

def case_a_non_string_field_is_refused_not_a_500():
    """I1. `(x or "").strip()` answered 500 for a number; 400 is the answer."""
    routes = [
        ("/api/genres/rename", ["old", "new"]),
        ("/api/genres/delete", ["tag"]),
        ("/api/user-tags/rename", ["old", "new"]),
        ("/api/user-tags/delete", ["tag"]),
    ]
    values = [5, 5.5, True, None, ["x"], {"a": 1}]
    for route, fields in routes:
        for field in fields:
            for value in values:
                client, _path, _ids = seeded(ROWS)
                body = {f: "Mystery" for f in fields}
                body[field] = value
                resp = client.post(route, json=body)
                check(f"{route} refuses {field}={value!r}",
                      resp.status_code, 400)


def case_bulk_refuses_a_non_string_tag():
    for value in [5, True, None, ["x"], {"a": 1}]:
        client, _path, ids = seeded(ROWS)
        resp = client.post("/api/user-tags/bulk",
                           json={"ids": [ids["a_one"]], "tag": value,
                                 "action": "add"})
        check(f"bulk refuses tag={value!r}", resp.status_code, 400)


def case_a_non_string_tag_entry_is_refused_not_coerced():
    """I1's second half: str() coercion stored a tag spelled None."""
    for value in [None, 5, True, {"a": 1}, ["nested"]]:
        client, path, ids = seeded(ROWS)
        resp = client.post(f"/api/items/{ids['a_one']}/user-tags",
                           json={"tags": [value]})
        check(f"a tags entry of {value!r} is refused", resp.status_code, 400)
        _genres, tags = vocab(path)
        check(f"and the row keeps what it had: {value!r}",
              tags[ids["a_one"]], ["lent out"])


def case_a_list_of_strings_is_still_accepted():
    # The control: the refusal above must not have closed the door on the
    # shape the viewer actually sends.
    client, path, ids = seeded(ROWS)
    resp = client.post(f"/api/items/{ids['a_one']}/user-tags",
                       json={"tags": ["lent out", "boxed"]})
    check("a list of strings is accepted", resp.status_code, 200)
    _genres, tags = vocab(path)
    check("and both tags are stored", sorted(tags[ids["a_one"]]),
          ["boxed", "lent out"])


def case_an_empty_tag_list_clears_the_row():
    client, path, ids = seeded(ROWS)
    resp = client.post(f"/api/items/{ids['a_one']}/user-tags", json={"tags": []})
    check("an empty list is accepted", resp.status_code, 200)
    _genres, tags = vocab(path)
    check("and clears the row's tags", tags[ids["a_one"]], [])


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
    print(f"webapp-tag-vocab-routes: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
