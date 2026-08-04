import json
from pathlib import Path

from humble_catalog import choice_preview, db, import_games, titles

FIXTURES = Path(__file__).parent / "fixtures"


def _hub():
    return json.loads((FIXTURES / "choice_hub.json").read_text(encoding="utf-8"))


def _conn(tmp_path):
    """A catalog with a small imported steam library and one keyed game.

    Widget Quest is the base the Definitive Edition must match and the
    sequel must NOT. Starfall Rally is the foil that puts Starfall Rally
    Turbo in the ambiguous band. Cinder Vale exists only as an
    unactivated Humble key, so it is in no imported library.
    """
    conn = db.connect(tmp_path / "catalog.db")
    import_games.store_games(conn, "steam", [
        {"store_id": sid, "title": t,
         "normalized_title": titles.clean_game_title(t),
         "source_timestamp": None}
        for sid, t in (("440", "Widget Quest"), ("220", "Neon Drifter"),
                       ("330", "Starfall Rally"))], "test")
    conn.execute("INSERT INTO bundles (gamekey, name, url) VALUES "
                 "('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789')")
    conn.execute(
        "INSERT INTO external_keys "
        "(gamekey, machine_name, human_name, key_type, raw) "
        "VALUES ('kv789', 'cindervale_steam', 'Cinder Vale', 'steam', ?)",
        (json.dumps({"human_name": "Cinder Vale", "key_type": "steam"}),))
    conn.commit()
    return conn


def _report(tmp_path):
    conn = _conn(tmp_path)
    try:
        return choice_preview.preview(conn, _hub())
    finally:
        conn.close()


def test_preview_reports_the_month_and_its_price(tmp_path):
    report = _report(tmp_path)
    assert report["name"] == "Humble Choice: January 2031"
    assert report["price"] == 11.99
    assert report["currency"] == "EUR"


def test_owned_possible_and_new_partition_the_month(tmp_path):
    # The invariant the whole report rests on: `possible` is counted as
    # neither owned nor new, so the three must still sum to the total.
    report = _report(tmp_path)
    assert report["total"] == 6
    assert report["owned"] + report["possible"] + report["new"] == 6


def test_an_edition_suffix_over_an_owned_base_reads_as_owned(tmp_path):
    assert "Widget Quest: Definitive Edition" in _report(tmp_path)["owned_items"]


def test_a_sequel_reads_as_new_and_never_as_the_owned_base(tmp_path):
    # Every fuzzy scorer rates "Widget Quest" and "Widget Quest II" as
    # near-identical, and they are the one near-identical pair that is
    # definitely a different product.
    report = _report(tmp_path)
    assert "Widget Quest II" in report["new_items"]
    assert "Widget Quest II" not in report["owned_items"]


def test_the_ambiguous_band_is_counted_as_neither_owned_nor_new(tmp_path):
    report = _report(tmp_path)
    offered = [p["offered"] for p in report["possible_items"]]
    assert offered == ["Starfall Rally Turbo"]
    assert "Starfall Rally Turbo" not in report["owned_items"]
    assert "Starfall Rally Turbo" not in report["new_items"]


def test_a_title_owned_nowhere_reads_as_new(tmp_path):
    assert "Lantern & Lockpick" in _report(tmp_path)["new_items"]


def test_lists_are_sorted_case_insensitively_not_left_in_display_order(
        tmp_path):
    # display_order is Humble's marketing decision. This list gets
    # scanned -- "is the one I want in here?" -- so it sorts.
    report = _report(tmp_path)
    assert report["new_items"] == sorted(report["new_items"], key=str.lower)
    assert report["owned_items"] == sorted(report["owned_items"], key=str.lower)


def test_an_empty_catalog_reports_every_game_as_new(tmp_path):
    # The dangerous case: an empty games table must not read as "owns none
    # of it" by accident and must not crash.
    conn = db.connect(tmp_path / "empty.db")
    try:
        report = choice_preview.preview(conn, _hub())
    finally:
        conn.close()
    assert (report["total"], report["owned"], report["new"]) == (6, 0, 6)


def test_preview_survives_a_hub_that_is_not_the_expected_shape(tmp_path):
    # The blob is third-party content. A garbage payload must report a
    # month selling nothing, not raise out of a viewer route.
    conn = db.connect(tmp_path / "empty.db")
    try:
        report = choice_preview.preview(conn, {"contentChoiceOptions": "nope"})
    finally:
        conn.close()
    assert report["total"] == 0
    assert report["name"] == "Humble Choice"
