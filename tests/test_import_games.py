import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from humble_catalog import db, import_games

FIXTURES = Path(__file__).parent / "fixtures"


def _heroic(tmp_path, **files):
    """A fake Heroic store_cache directory holding the named files."""
    root = tmp_path / "store_cache"
    root.mkdir()
    for name, content in files.items():
        (root / name).write_text(json.dumps(content), encoding="utf-8")
    return root


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_read_heroic_reads_the_gog_games_container_key(tmp_path):
    root = _heroic(tmp_path, **{
        "gog_library.json": _fixture("heroic_gog_library.json")})
    rows = import_games.read_heroic(root)
    assert [r["title"] for r in rows["gog"]] == ["Pixel Harbor™", "Neon Drifter"]
    assert rows["gog"][0]["store_id"] == "1207658691"


def test_read_heroic_reads_the_epic_library_container_key(tmp_path):
    root = _heroic(tmp_path, **{
        "legendary_library.json": _fixture("heroic_legendary_library.json")})
    assert [r["title"] for r in import_games.read_heroic(root)["epic"]] == [
        "Grove of Echoes"]


def test_read_heroic_normalizes_each_title(tmp_path):
    root = _heroic(tmp_path, **{
        "gog_library.json": _fixture("heroic_gog_library.json")})
    assert import_games.read_heroic(root)["gog"][0]["normalized_title"] == "pixel harbor"


def test_read_heroic_keeps_the_cache_timestamp(tmp_path):
    root = _heroic(tmp_path, **{
        "gog_library.json": _fixture("heroic_gog_library.json")})
    assert import_games.read_heroic(root)["gog"][0]["source_timestamp"] == \
        "Sat Jul 25 2026 20:34:58 GMT+0200"


@pytest.mark.parametrize("content", [{}, {"library": []}, {"games": []}])
def test_a_logged_out_store_contributes_nothing_without_erroring(tmp_path, content):
    # Observed shapes: Zoom logged out is {}, Amazon logged out is an empty
    # list. Neither is an error -- it is simply a store with no data.
    root = _heroic(tmp_path, **{"nile_library.json": content})
    assert import_games.read_heroic(root) == {}


def test_a_missing_store_cache_directory_contributes_nothing(tmp_path):
    assert import_games.read_heroic(tmp_path / "nope") == {}


def test_a_malformed_cache_raises_rather_than_importing_nothing(tmp_path):
    # Heroic may be mid-write. Failing loudly is the point: a silent empty
    # read would later be stored, wiping good rows.
    root = tmp_path / "store_cache"
    root.mkdir()
    (root / "gog_library.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="gog_library.json"):
        import_games.read_heroic(root)


def _conn(tmp_path):
    return db.connect(tmp_path / "catalog.db")


def _rows(*titles):
    return [{"store_id": f"id{i}", "title": t,
             "normalized_title": t.lower(), "source_timestamp": "ts"}
            for i, t in enumerate(titles)]


def test_store_games_writes_rows_and_records_the_import(tmp_path):
    conn = _conn(tmp_path)
    try:
        assert import_games.store_games(conn, "gog", _rows("Neon Drifter"),
                                        "heroic") == 1
        assert conn.execute("SELECT title FROM games").fetchone()[0] == "Neon Drifter"
        row = conn.execute("SELECT * FROM game_imports WHERE store='gog'").fetchone()
        assert (row["count"], row["source"]) == (1, "heroic")
    finally:
        conn.close()


def test_store_games_replaces_that_store_only(tmp_path):
    # A game revoked or removed upstream must disappear, but another
    # store's rows must survive untouched.
    conn = _conn(tmp_path)
    try:
        import_games.store_games(conn, "gog", _rows("Neon Drifter", "Pixel Harbor"),
                                 "heroic")
        import_games.store_games(conn, "steam", _rows("Widget Quest"), "steam")
        import_games.store_games(conn, "gog", _rows("Neon Drifter"), "heroic")
        titles = {r[0] for r in conn.execute("SELECT title FROM games")}
        assert titles == {"Neon Drifter", "Widget Quest"}
    finally:
        conn.close()


def test_store_games_refuses_to_clear_a_store_with_an_empty_read(tmp_path):
    # A private Steam profile returns an empty list rather than an error.
    # Treating that as "you own nothing" would wipe the library and then
    # report a whole bundle as new.
    conn = _conn(tmp_path)
    try:
        import_games.store_games(conn, "steam", _rows("Widget Quest"), "steam")
        with pytest.raises(ValueError, match="no games"):
            import_games.store_games(conn, "steam", [], "steam")
        assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
    finally:
        conn.close()


def test_imported_stores_reports_what_has_been_imported(tmp_path):
    conn = _conn(tmp_path)
    try:
        import_games.store_games(conn, "gog", _rows("Neon Drifter"), "heroic")
        stores = import_games.imported_stores(conn)
        assert set(stores) == {"gog"}
        assert stores["gog"]["count"] == 1
        assert stores["gog"]["source_timestamp"] == "ts"
    finally:
        conn.close()


def _http(payload):
    resp = Mock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    http = Mock()
    http.request.return_value = resp
    return http


def test_fetch_steam_returns_normalized_rows():
    http = _http(_fixture("steam_owned_games.json"))
    rows = import_games.fetch_steam("KEY", "123", http=http)
    assert [r["title"] for r in rows] == [
        "Widget Quest", "Neon Drifter", "Starfall Rally"]
    assert rows[0]["store_id"] == "440"
    assert rows[0]["normalized_title"] == "widget quest"


def test_fetch_steam_asks_for_app_info():
    # Without include_appinfo the API returns bare appids and no names,
    # which would make every title unmatched.
    http = _http(_fixture("steam_owned_games.json"))
    import_games.fetch_steam("KEY", "123", http=http)
    params = http.request.call_args.kwargs["params"]
    assert params["include_appinfo"] == 1
    assert params["key"] == "KEY" and params["steamid"] == "123"


def test_fetch_steam_treats_an_empty_response_as_an_error():
    # A private profile returns {"response": {}} with HTTP 200.
    http = _http({"response": {}})
    with pytest.raises(ValueError, match="private"):
        import_games.fetch_steam("KEY", "123", http=http)
