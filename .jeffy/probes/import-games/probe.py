"""Known-answer battery for the import-games inventory row.

Covers `humble_catalog/import_games.py`: `read_heroic`, `fetch_steam`,
`store_games` and `imported_stores`.

This module is where the project reads files it did not write, and its
most important behaviour is a pair of REFUSALS. Both exist because the
same shape - an empty list - is written by two different normal states:
a logged-out Heroic store and a private Steam profile. Acting on it would
delete a good library, and the next bundle preview would then report a
whole bundle as new. So `store_games` raises on empty rather than
clearing, and `read_heroic` raises on unparseable JSON rather than
reading it as "no games".

Those two are asserted the strong way: the games table is read back after
each refusal and compared against what it held before.

Steam is exercised through the `http=` seam with a stub session, so the
private-profile branch is reached with no network.

Every title is invented, from docs/TEST-DATA.md. Fresh tmpdir and
database per case.
"""
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, import_games  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def raises(label, fn, exc=ValueError):
    try:
        fn()
    except exc:
        PASS.append(label)
        return
    except Exception as other:                              # noqa: BLE001
        FAIL.append(label)
        print(f"  FAIL {label}: raised {type(other).__name__}, wanted "
              f"{exc.__name__}")
        return
    FAIL.append(label)
    print(f"  FAIL {label}: nothing was raised")


def fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return db.connect(pathlib.Path(tmp.name))


def games_in(conn, store=None):
    sql = "SELECT store, store_id, title, normalized_title FROM games"
    args = ()
    if store:
        sql += " WHERE store=?"
        args = (store,)
    return sorted(tuple(r) for r in conn.execute(sql, args))


def heroic_dir(files):
    """files: {filename: python object to dump, or a raw string}."""
    root = pathlib.Path(tempfile.mkdtemp())
    for name, payload in files.items():
        text = payload if isinstance(payload, str) else json.dumps(payload)
        (root / name).write_text(text, encoding="utf-8")
    return root


def gog(entries, stamp=None):
    body = {"games": entries}
    if stamp:
        body["__timestamp"] = {"games": stamp}
    return body


def rows(*titles):
    from humble_catalog.titles import clean_game_title
    return [{"store_id": f"id_{i}", "title": t,
             "normalized_title": clean_game_title(t),
             "source_timestamp": None}
            for i, t in enumerate(titles)]


# ------------------------------------------------------------- read_heroic

def case_a_gog_library_is_read_from_its_games_key():
    root = heroic_dir({"gog_library.json": gog(
        [{"app_name": "1", "title": "Widget Quest"},
         {"app_name": "2", "title": "Pixel Harbor Rally"}])})
    out = import_games.read_heroic(root)
    check("the gog store is present", sorted(out), ["gog"])
    check("with both titles",
          sorted(r["title"] for r in out["gog"]),
          ["Pixel Harbor Rally", "Widget Quest"])


def case_the_other_stores_are_read_from_their_library_key():
    # Documented: GOG writes "games", the others write "library".
    root = heroic_dir({
        "legendary_library.json": {"library": [
            {"app_name": "e1", "title": "Cinder Vale Chronicles"}]},
        "nile_library.json": {"library": [
            {"app_name": "a1", "title": "Widget Quest"}]},
        "zoom-library.json": {"library": [
            {"app_name": "z1", "title": "Neon Drifter"}]},
    })
    out = import_games.read_heroic(root)
    check("each filename maps to its store name",
          sorted(out), ["amazon", "epic", "zoom"])


def case_a_missing_file_is_a_logged_out_store_not_an_error():
    # Documented: a missing file, {}, or an empty list all mean logged
    # out, which is a normal state.
    check("an empty directory yields no stores",
          import_games.read_heroic(heroic_dir({})), {})


def case_an_empty_library_yields_no_store_entry():
    root = heroic_dir({"gog_library.json": gog([]),
                       "legendary_library.json": {}})
    check("neither an empty list nor an empty object makes a store",
          import_games.read_heroic(root), {})


def case_unparseable_json_raises_rather_than_reading_as_no_games():
    # The guard that protects a good library: Heroic may be mid-write, and
    # treating that as "no games" would let store_games wipe good rows.
    root = heroic_dir({"gog_library.json": "{ this is not json"})
    raises("truncated json raises", lambda: import_games.read_heroic(root))


def case_the_error_names_the_file():
    root = heroic_dir({"nile_library.json": "{ broken"})
    try:
        import_games.read_heroic(root)
        FAIL.append("the error names the file")
        print("  FAIL the error names the file: nothing raised")
    except ValueError as exc:
        check("the message names which file could not be read",
              "nile_library.json" in str(exc), True)


def case_entries_missing_a_name_or_title_are_skipped():
    root = heroic_dir({"gog_library.json": gog([
        {"app_name": "1", "title": "Widget Quest"},
        {"app_name": "2"},                       # no title
        {"title": "No App Name"},                # no app_name
        {"app_name": "", "title": "Blank Name"},  # blank app_name
    ])})
    out = import_games.read_heroic(root)
    check("only the complete entry survives",
          [r["title"] for r in out["gog"]], ["Widget Quest"])


def case_a_store_id_is_stringified():
    root = heroic_dir({"gog_library.json": gog(
        [{"app_name": 12345, "title": "Widget Quest"}])})
    out = import_games.read_heroic(root)
    check("a numeric app_name becomes a string",
          out["gog"][0]["store_id"], "12345")


def case_the_normalized_title_is_computed_on_read():
    root = heroic_dir({"gog_library.json": gog(
        [{"app_name": "1", "title": "Widget Quest: Deluxe Edition"}])})
    out = import_games.read_heroic(root)
    check("the normalized form is derived, not copied",
          out["gog"][0]["normalized_title"] !=
          out["gog"][0]["title"], True)


def case_the_source_timestamp_is_carried_across():
    root = heroic_dir({"gog_library.json": gog(
        [{"app_name": "1", "title": "Widget Quest"}],
        stamp="2026-07-01T00:00:00")})
    check("the file's timestamp reaches every row",
          import_games.read_heroic(root)["gog"][0]["source_timestamp"],
          "2026-07-01T00:00:00")


# ------------------------------------------------------------ fetch_steam

class StubHTTP:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request(self, method, url, params=None, timeout=None):
        self.calls.append({"method": method, "url": url, "params": params})
        return StubResp(self.payload)


class StubResp:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def case_steam_rows_are_built_from_the_response():
    http = StubHTTP({"response": {"games": [
        {"appid": 10, "name": "Widget Quest"},
        {"appid": 20, "name": "Neon Drifter"}]}})
    out = import_games.fetch_steam("k", "1", http=http)
    check("both games become rows",
          sorted(r["title"] for r in out), ["Neon Drifter", "Widget Quest"])
    check("and the appid is stringified",
          sorted(r["store_id"] for r in out), ["10", "20"])


def case_include_appinfo_is_requested():
    # Documented: without it the API returns bare appids and every title
    # would go unmatched.
    http = StubHTTP({"response": {"games": [{"appid": 1, "name": "Widget Quest"}]}})
    import_games.fetch_steam("k", "1", http=http)
    check("include_appinfo is sent", http.calls[0]["params"]["include_appinfo"],
          1)


def case_a_private_profile_raises_rather_than_reporting_nothing():
    # A private profile answers 200 with an empty response object, which
    # is indistinguishable from owning nothing.
    for payload in [{"response": {}}, {"response": {"games": []}}, {}]:
        raises(f"private profile raises for {payload}",
               lambda p=payload: import_games.fetch_steam(
                   "k", "1", http=StubHTTP(p)))


def case_the_private_profile_message_says_how_to_fix_it():
    try:
        import_games.fetch_steam("k", "1", http=StubHTTP({"response": {}}))
        FAIL.append("the message explains the fix")
    except ValueError as exc:
        check("the message points at the privacy setting",
              "Privacy Settings" in str(exc), True)


def case_a_game_missing_its_name_is_skipped():
    http = StubHTTP({"response": {"games": [
        {"appid": 10, "name": "Widget Quest"},
        {"appid": 20},
        {"name": "No App Id"}]}})
    out = import_games.fetch_steam("k", "1", http=http)
    check("only the complete row survives",
          [r["title"] for r in out], ["Widget Quest"])


# ------------------------------------------------------------- store_games

def case_storing_games_writes_rows_and_a_import_record():
    conn = fresh()
    n = import_games.store_games(conn, "steam",
                                 rows("Widget Quest", "Neon Drifter"), "api")
    check("the count is returned", n, 2)
    check("both rows are stored", len(games_in(conn, "steam")), 2)
    check("and the store is recorded as imported",
          sorted(import_games.imported_stores(conn)), ["steam"])
    conn.close()


def case_a_reimport_replaces_only_its_own_store():
    # Per-store replace: a game removed upstream disappears, while every
    # other store is untouched.
    conn = fresh()
    import_games.store_games(conn, "steam", rows("Widget Quest", "Gone Game"),
                             "api")
    import_games.store_games(conn, "gog", rows("Cinder Vale Chronicles"),
                             "heroic")
    import_games.store_games(conn, "steam", rows("Widget Quest"), "api")
    check("the removed steam game is gone",
          [r[2] for r in games_in(conn, "steam")], ["Widget Quest"])
    check("and the gog store is untouched",
          [r[2] for r in games_in(conn, "gog")], ["Cinder Vale Chronicles"])
    conn.close()


def case_an_empty_import_refuses_and_deletes_nothing():
    """The guard this module exists around.

    A private Steam profile and a logged-out Heroic store both produce an
    empty list, and both read exactly like "sold everything". Clearing on
    that would delete a good library and the next preview would report a
    whole bundle as new.
    """
    conn = fresh()
    import_games.store_games(conn, "steam", rows("Widget Quest"), "api")
    before = games_in(conn)
    raises("an empty import raises",
           lambda: import_games.store_games(conn, "steam", [], "api"))
    check("and the library is untouched", games_in(conn), before)
    conn.close()


def case_the_refusal_message_explains_why():
    conn = fresh()
    try:
        import_games.store_games(conn, "steam", [], "api")
        FAIL.append("the refusal explains itself")
    except ValueError as exc:
        check("the message names the refusal and its reason",
              "refusing to clear" in str(exc), True)
    conn.close()


def case_a_failed_write_rolls_the_delete_back():
    # Documented: one transaction, so a failure mid-write rolls the delete
    # back. Driven with a row missing a required key, which raises inside
    # executemany AFTER the delete has run.
    conn = fresh()
    import_games.store_games(conn, "steam", rows("Widget Quest"), "api")
    before = games_in(conn)
    bad = [{"store_id": "1", "title": "Broken"}]        # no normalized_title
    raises("a malformed row raises", lambda: import_games.store_games(
        conn, "steam", bad, "api"), exc=KeyError)
    check("and the previous rows are still there", games_in(conn), before)
    conn.close()


def case_imported_stores_reports_each_store_once():
    conn = fresh()
    import_games.store_games(conn, "steam", rows("Widget Quest"), "api")
    import_games.store_games(conn, "gog", rows("Neon Drifter"), "heroic")
    out = import_games.imported_stores(conn)
    check("both stores are reported", sorted(out), ["gog", "steam"])
    check("with their counts", {k: v["count"] for k, v in out.items()},
          {"gog": 1, "steam": 1})
    check("and their sources", {k: v["source"] for k, v in out.items()},
          {"gog": "heroic", "steam": "api"})
    conn.close()


def case_a_reimport_updates_rather_than_duplicates_the_record():
    conn = fresh()
    import_games.store_games(conn, "steam", rows("Widget Quest"), "api")
    import_games.store_games(conn, "steam",
                             rows("Widget Quest", "Neon Drifter"), "api")
    out = import_games.imported_stores(conn)
    check("one record per store", sorted(out), ["steam"])
    check("carrying the latest count", out["steam"]["count"], 2)
    conn.close()


def case_a_store_never_imported_is_absent():
    # The documented distinction the bundle preview depends on: "never
    # imported" and "owns nothing here" are identical as counts.
    conn = fresh()
    check("nothing imported is an empty map",
          import_games.imported_stores(conn), {})
    conn.close()


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
    print(f"import-games: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
