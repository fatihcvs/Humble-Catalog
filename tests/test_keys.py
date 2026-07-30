import datetime as dt
import json

from humble_catalog import db, import_games, keys, titles

NOW = dt.datetime(2026, 7, 30, tzinfo=dt.timezone.utc)


def _conn(tmp_path, rows, library=(("steam", "Widget Quest"),),
          imported=("steam",)):
    """A catalog holding `rows` as keys and `library` as imported games.

    `rows` is [(product, key_type, raw_extra)]; raw_extra is merged into
    the stored blob, so a test names only the fields it cares about.
    Every key belongs to one invented bundle.
    """
    conn = db.connect(tmp_path / "catalog.db")
    conn.execute("INSERT INTO bundles (gamekey, name, url, purchased_at) "
                 "VALUES ('kv789', 'Humble Game Bundle: Key Vault', "
                 "'https://example.invalid/kv789', '2024-01-02T00:00:00')")
    for product, key_type, extra in rows:
        raw = {"human_name": product, "key_type": key_type,
               "machine_name": product.lower().replace(" ", "") + "_ex",
               "key_type_human_name": key_type.title()}
        raw.update(extra or {})
        conn.execute(
            "INSERT INTO external_keys (gamekey, human_name, key_type, raw) "
            "VALUES ('kv789', ?, ?, ?)",
            (product, key_type, json.dumps(raw)))
    conn.commit()
    for store in imported:
        games = [{"store_id": f"{store}-{n}", "title": title,
                  "normalized_title": titles.clean_game_title(title),
                  "source_timestamp": None}
                 for n, (owner, title) in enumerate(library) if owner == store]
        if games:
            import_games.store_games(conn, store, games, "test")
        else:
            # store_games refuses to write an empty import on purpose -- a
            # private Steam profile and a logged-out Heroic store both look
            # like "sold everything". So the one test that needs an imported
            # store with no games writes the game_imports row by hand.
            conn.execute("INSERT INTO game_imports (store, imported_at, "
                         "count, source) VALUES (?, ?, 0, 'test')",
                         (store, "2026-07-25T00:00:00+00:00"))
            conn.commit()
    return conn


def _states(tmp_path, rows, **kw):
    conn = _conn(tmp_path, rows, **kw)
    try:
        return keys.report(conn, now=NOW)["counts"]
    finally:
        conn.close()


def test_store_for_strips_the_keyless_suffix():
    assert keys.store_for("gog_keyless") == "gog"
    assert keys.store_for("epic_keyless") == "epic"
    assert keys.store_for("steam") == "steam"
    assert keys.store_for(None) is None


def test_a_key_whose_game_is_in_its_own_library_is_matched(tmp_path):
    counts = _states(tmp_path, [("Widget Quest", "steam", None)])
    assert counts["matched"] == 1
    assert counts["unredeemed"] == 0


def test_a_key_whose_game_is_in_no_library_is_unredeemed(tmp_path):
    counts = _states(tmp_path, [("Cinder Vale", "steam", None)])
    assert counts["unredeemed"] == 1


def test_a_key_for_a_store_with_no_importer_is_never_unredeemed(tmp_path):
    # The backlog's central limit: uplay has no importer, so "not in any
    # library" is unfalsifiable there. It is a third state, not a verdict.
    counts = _states(tmp_path, [("Verdant Reach", "uplay", None)])
    assert counts["uncheckable"] == 1
    assert counts["unredeemed"] == 0


def test_a_game_owned_only_on_another_store_still_reports_unredeemed(tmp_path):
    # THE design decision. A steam key is redeemed into steam; the game
    # sitting in the gog library says nothing about whether the key landed.
    # Do not "fix" this into pooling the libraries -- bundle_preview pools
    # them because it asks a different question.
    counts = _states(tmp_path, [("Pixel Harbor", "steam", None)],
                     library=(("gog", "Pixel Harbor"),),
                     imported=("steam", "gog"))
    assert counts["unredeemed"] == 1
    assert counts["matched"] == 0


def test_a_near_match_against_its_own_store_is_uncertain(tmp_path):
    # Starfall Rally Turbo against the owned Starfall Rally: the 80-92 band.
    counts = _states(tmp_path, [("Starfall Rally Turbo", "steam", None)],
                     library=(("steam", "Starfall Rally"),))
    assert counts["uncertain"] == 1


def test_the_four_states_partition_every_key(tmp_path):
    conn = _conn(tmp_path, [("Widget Quest", "steam", None),
                            ("Cinder Vale", "steam", None),
                            ("Verdant Reach", "uplay", None),
                            ("Starfall Rally Turbo", "steam", None)],
                 library=(("steam", "Widget Quest"),
                          ("steam", "Starfall Rally")))
    try:
        report = keys.report(conn, now=NOW)
    finally:
        conn.close()
    assert sum(report["counts"].values()) == report["total"] == 4
    assert report["reported"] == 3          # everything but `matched`


def test_an_imported_store_holding_no_games_still_checks(tmp_path):
    # An imported store with an empty library is not uncheckable: the
    # import happened and found nothing, so nothing there is redeemed.
    counts = _states(tmp_path, [("Cinder Vale", "steam", None)],
                     library=(), imported=("steam",))
    assert counts["unredeemed"] == 1
    assert counts["uncheckable"] == 0


def test_parse_expiry_normalizes_to_utc():
    assert keys.parse_expiry("2026-08-11T00:00:00") == dt.datetime(
        2026, 8, 11, tzinfo=dt.timezone.utc)
    assert keys.parse_expiry("2026-08-11T00:00:00Z") == dt.datetime(
        2026, 8, 11, tzinfo=dt.timezone.utc)
    assert keys.parse_expiry(None) is None
    assert keys.parse_expiry("not a date") is None


def _rows(tmp_path, rows, **kw):
    conn = _conn(tmp_path, rows, **kw)
    try:
        return keys.report(conn, now=NOW)["rows"]
    finally:
        conn.close()


def test_a_matched_key_is_counted_but_not_listed(tmp_path):
    # `matched` means "nothing to do here"; listing it would bury the rest.
    rows = _rows(tmp_path, [("Widget Quest", "steam", None),
                            ("Cinder Vale", "steam", None)])
    assert [r["product"] for r in rows] == ["Cinder Vale"]


def test_a_row_carries_its_bundle_machine_name_and_reveal_state(tmp_path):
    rows = _rows(tmp_path, [("Cinder Vale", "steam",
                             {"redeemed_key_val": "ABCDE-FGHIJ"})])
    row = rows[0]
    assert row["bundle"] == "Humble Game Bundle: Key Vault"
    assert row["machine_name"] == "cindervale_ex"
    assert row["gamekey"] == "kv789"
    assert row["store"] == "steam"
    assert row["purchased_at"] == "2024-01-02T00:00:00"
    # "revealed", never "redeemed": Humble sets this field the moment the
    # key's value is DISPLAYED, which says nothing about activation.
    assert row["revealed"] is True


def test_a_key_never_revealed_says_so(tmp_path):
    rows = _rows(tmp_path, [("Cinder Vale", "steam", None)])
    assert rows[0]["revealed"] is False


def test_an_uncertain_row_carries_what_it_nearly_matched(tmp_path):
    rows = _rows(tmp_path, [("Starfall Rally Turbo", "steam", None)],
                 library=(("steam", "Starfall Rally"),))
    assert rows[0]["state"] == "uncertain"
    assert rows[0]["near_match"]["owned_title"] == "Starfall Rally"
    assert 0.8 <= rows[0]["near_match"]["score"] < 0.92


def test_an_unredeemed_row_has_no_near_match(tmp_path):
    rows = _rows(tmp_path, [("Cinder Vale", "steam", None)])
    assert rows[0]["near_match"] is None


def test_an_expired_unmatched_key_is_still_listed(tmp_path):
    # Dropping it would hide that a key was lost, which is worth knowing
    # once even though nothing can be done about it.
    rows = _rows(tmp_path, [("Glass Meridian", "steam",
                             {"expiry_date": "2026-07-01T00:00:00"})])
    assert [r["product"] for r in rows] == ["Glass Meridian"]
    assert rows[0]["expired"] is True
    assert rows[0]["days_left"] is None


def test_a_live_expiry_reports_the_days_left(tmp_path):
    rows = _rows(tmp_path, [("Amber Hollow", "steam",
                             {"expiry_date": "2026-08-11T00:00:00"})])
    assert rows[0]["expired"] is False
    assert rows[0]["days_left"] == 12


def test_rows_sort_live_expiry_then_undated_then_expired(tmp_path):
    # Plain ascending would put the dead rows on top. Three groups, so the
    # rows that can still be lost come first -- what the backlog asked for.
    rows = _rows(tmp_path, [
        ("Glass Meridian", "steam", {"expiry_date": "2026-07-01T00:00:00"}),
        ("Cinder Vale", "steam", None),
        ("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
    ])
    assert [r["product"] for r in rows] == [
        "Amber Hollow", "Cinder Vale", "Glass Meridian"]


def test_the_soonest_live_expiry_comes_first(tmp_path):
    rows = _rows(tmp_path, [
        ("Cinder Vale", "steam", {"expiry_date": "2026-09-01T00:00:00"}),
        ("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
    ])
    assert [r["product"] for r in rows] == ["Amber Hollow", "Cinder Vale"]


def test_the_most_recently_expired_comes_first(tmp_path):
    rows = _rows(tmp_path, [
        ("Cinder Vale", "steam", {"expiry_date": "2025-01-01T00:00:00"}),
        ("Glass Meridian", "steam", {"expiry_date": "2026-07-01T00:00:00"}),
    ])
    assert [r["product"] for r in rows] == ["Glass Meridian", "Cinder Vale"]


def test_undated_rows_tie_break_deterministically(tmp_path):
    # A pure function of the data, never of the query plan -- the guarantee
    # the harvest worklist order design established.
    rows = _rows(tmp_path, [("Verdant Reach", "uplay", None),
                            ("Cinder Vale", "steam", None)])
    assert [r["product"] for r in rows] == ["Cinder Vale", "Verdant Reach"]


def test_expiring_counts_only_rows_that_can_still_be_lost(tmp_path):
    conn = _conn(tmp_path, [
        ("Amber Hollow", "steam", {"expiry_date": "2026-08-11T00:00:00"}),
        ("Glass Meridian", "steam", {"expiry_date": "2026-07-01T00:00:00"}),
        ("Cinder Vale", "steam", None)])
    try:
        assert keys.report(conn, now=NOW)["expiring"] == 1
    finally:
        conn.close()
