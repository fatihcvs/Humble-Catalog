"""Known-answer battery for the keys-report inventory row.

Covers `humble_catalog/keys.py`: `store_for`, `parse_expiry`, `report`'s
state machine and its three-group ordering, `stale_hides`, `missing_keys`,
and `format_report`'s `show_all` and `hidden` parameters.

`report(conn, now=...)` takes an injectable clock, so every expiry answer
below is a fixed arithmetic result rather than something that drifts with
the wall clock - the trap the harvest row's stub reset time fell into.

The ordering is the case worth the row. The rows are NOT one ascending
column: dated rows split AROUND the undated ones, because plain ascending
sorts already-dead keys above the urgent ones. Three groups, each pinned.

Every title and bundle is invented, from docs/TEST-DATA.md. Fresh
database per case.
"""
import json
import pathlib
import sys
import tempfile
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, keys  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return db.connect(pathlib.Path(tmp.name))


def add_bundle(conn, gamekey="k1", name="Humble Game Bundle: Key Vault",
               purchased_at="2026-01-01"):
    conn.execute("INSERT OR IGNORE INTO bundles (gamekey, name, url, "
                 "purchased_at) VALUES (?,?,?,?)",
                 (gamekey, name, f"https://example.invalid/{gamekey}",
                  purchased_at))


def add_key(conn, product, machine_name=None, key_type="steam",
            gamekey="k1", expiry=None, revealed=False):
    add_bundle(conn, gamekey)
    raw = {}
    if expiry:
        raw["expiry_date"] = expiry
    if revealed:
        raw["redeemed_key_val"] = "XXXX-YYYY"
    conn.execute(
        "INSERT INTO external_keys (gamekey, machine_name, human_name, "
        "key_type, raw) VALUES (?,?,?,?,?)",
        (gamekey, machine_name or product.lower().replace(" ", "_"),
         product, key_type, json.dumps(raw)))


def add_library(conn, store, titles=()):
    conn.execute("INSERT OR IGNORE INTO game_imports (store, imported_at, "
                 "count, source) VALUES (?,?,?,?)",
                 (store, "2026-01-01T00:00:00", len(titles), "api"))
    from humble_catalog.titles import clean_game_title
    for i, title in enumerate(titles):
        conn.execute(
            "INSERT INTO games (store, store_id, title, normalized_title, "
            "imported_at) VALUES (?,?,?,?,?)",
            (store, f"{store}_{i}", title, clean_game_title(title),
             "2026-01-01T00:00:00"))


def iso(days):
    return (NOW + dt.timedelta(days=days)).isoformat()


# --------------------------------------------------------------- store_for

def case_store_for_strips_the_keyless_suffix():
    # Documented: a delivery detail, not a different storefront.
    for spelling in ["gog_keyless", "GOG_KEYLESS", "  gog  "]:
        check(f"{spelling!r} is the gog store", keys.store_for(spelling), "gog")


def case_store_for_of_nothing_is_none():
    for value in [None, "", "   "]:
        check(f"{value!r} names no store", keys.store_for(value), None)


# ------------------------------------------------------------ parse_expiry

def case_parse_expiry_reads_an_iso_instant():
    check("a plain iso timestamp parses",
          keys.parse_expiry("2026-08-02T12:00:00+00:00"), NOW)


def case_a_zulu_suffix_is_accepted():
    check("a Z suffix is read as UTC",
          keys.parse_expiry("2026-08-02T12:00:00Z"), NOW)


def case_a_naive_timestamp_is_assumed_utc():
    check("a timestamp with no zone is read as UTC",
          keys.parse_expiry("2026-08-02T12:00:00"), NOW)


def case_an_unparseable_expiry_is_none():
    for value in [None, "", "not a date", "2026-13-45", 12345.6, {}]:
        check(f"{value!r} yields no expiry", keys.parse_expiry(value), None)


# ---------------------------------------------------------- the state rules

def case_a_key_for_an_unimported_store_is_uncheckable():
    # Documented: a machine that has never imported Epic reports its Epic
    # keys as uncheckable rather than as unredeemed.
    conn = fresh()
    add_key(conn, "Widget Quest", key_type="epic")
    rep = keys.report(conn, now=NOW)
    check("the state is uncheckable", rep["counts"]["uncheckable"], 1)
    check("and it is reported", rep["reported"], 1)
    conn.close()


def case_a_key_whose_type_names_no_store_is_uncheckable():
    conn = fresh()
    add_key(conn, "Widget Quest", key_type="")
    check("a typeless key is uncheckable",
          keys.report(conn, now=NOW)["counts"]["uncheckable"], 1)
    conn.close()


def case_a_key_matching_an_owned_game_is_matched_and_unreported():
    # `matched` is the answer "nothing to do here": counted, never listed.
    conn = fresh()
    add_key(conn, "Widget Quest")
    add_library(conn, "steam", ["Widget Quest"])
    rep = keys.report(conn, now=NOW)
    check("the key is matched", rep["counts"]["matched"], 1)
    check("and does not appear in rows", rep["rows"], [])
    check("total still counts it", rep["total"], 1)
    conn.close()


def case_a_key_matching_nothing_is_unredeemed():
    conn = fresh()
    add_key(conn, "Widget Quest")
    add_library(conn, "steam", ["Cinder Vale Chronicles"])
    rep = keys.report(conn, now=NOW)
    check("an unmatched key is unredeemed", rep["counts"]["unredeemed"], 1)
    check("and is listed", [r["product"] for r in rep["rows"]],
          ["Widget Quest"])
    conn.close()


def case_a_band_match_is_uncertain_and_names_its_near_match():
    # The reverse of bundle_preview's treatment: the middle band IS
    # reported here.
    conn = fresh()
    add_key(conn, "Pixel Harbor Racing")
    add_library(conn, "steam", ["Pixel Harbor Rally"])
    rep = keys.report(conn, now=NOW)
    check("the band verdict is uncertain", rep["counts"]["uncertain"], 1)
    near = rep["rows"][0]["near_match"]
    check("and the row names what it nearly matched",
          near["owned_title"], "Pixel Harbor Rally")
    conn.close()


def case_an_imported_store_holding_no_games_reports_unredeemed():
    # Documented: a store can have a game_imports row while holding no
    # games rows, and both cases classify every title as new.
    conn = fresh()
    add_key(conn, "Widget Quest")
    add_library(conn, "steam", [])
    check("an empty library makes its keys unredeemed",
          keys.report(conn, now=NOW)["counts"]["unredeemed"], 1)
    conn.close()


# ------------------------------------------------------- expiry arithmetic

def case_days_left_is_floored_and_absent_once_expired():
    conn = fresh()
    add_key(conn, "Alpha Key", expiry=iso(10))
    add_key(conn, "Beta Key", expiry=iso(-3))
    rep = keys.report(conn, now=NOW)
    by = {r["product"]: r for r in rep["rows"]}
    check("a live key reports whole days left", by["Alpha Key"]["days_left"], 10)
    check("and is not expired", by["Alpha Key"]["expired"], False)
    check("an expired key reports no days left",
          by["Beta Key"]["days_left"], None)
    check("and is flagged expired", by["Beta Key"]["expired"], True)
    conn.close()


def case_a_partial_day_floors_down():
    conn = fresh()
    add_key(conn, "Alpha Key",
            expiry=(NOW + dt.timedelta(days=2, hours=23)).isoformat())
    check("2 days and 23 hours reads as 2 days",
          keys.report(conn, now=NOW)["rows"][0]["days_left"], 2)
    conn.close()


def case_an_undated_key_carries_no_expiry_fields():
    conn = fresh()
    add_key(conn, "Alpha Key")
    row = keys.report(conn, now=NOW)["rows"][0]
    check("no expiry", row["expires"], None)
    check("not expired", row["expired"], False)
    check("and no days left", row["days_left"], None)
    conn.close()


# ------------------------------------------------------- the three groups

def case_rows_split_around_the_undated_ones():
    """The ordering the row exists for, written out in full.

    Group 0: a live expiry, soonest first - can still be lost.
    Group 1: no expiry date.
    Group 2: already expired, most recent first.

    Plain ascending would put the two expired keys at the top, above the
    ones the owner can still act on.
    """
    conn = fresh()
    add_key(conn, "Live Late", expiry=iso(30))
    add_key(conn, "Dead Old", expiry=iso(-40))
    add_key(conn, "Live Soon", expiry=iso(2))
    add_key(conn, "Undated One")
    add_key(conn, "Dead Recent", expiry=iso(-1))
    rows = [r["product"] for r in keys.report(conn, now=NOW)["rows"]]
    check("live soonest first, then undated, then expired most-recent first",
          rows, ["Live Soon", "Live Late", "Undated One",
                 "Dead Recent", "Dead Old"])
    conn.close()


def case_ties_break_on_purchase_then_name():
    # Documented: so the order is a pure function of the data rather than
    # of the query plan.
    conn = fresh()
    add_bundle(conn, "kA", "Bundle One", purchased_at="2026-01-01")
    add_bundle(conn, "kB", "Bundle Two", purchased_at="2026-02-01")
    add_key(conn, "Zebra Key", gamekey="kA")
    add_key(conn, "Alpha Key", gamekey="kA")
    add_key(conn, "Middle Key", gamekey="kB")
    rows = [r["product"] for r in keys.report(conn, now=NOW)["rows"]]
    check("earlier purchase first, then name within it",
          rows, ["Alpha Key", "Zebra Key", "Middle Key"])
    conn.close()


# -------------------------------------------------------- hidden and counts

def case_hiding_a_key_annotates_it_without_removing_it():
    # Documented: an annotation, not a fourth state. Rows are never
    # filtered in report, so both surfaces filter the one field.
    conn = fresh()
    add_key(conn, "Widget Quest", machine_name="wq")
    conn.execute("INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
                 "VALUES ('k1','wq','2026-07-01T00:00:00')")
    rep = keys.report(conn, now=NOW)
    check("the row is still present", len(rep["rows"]), 1)
    check("carrying its hidden_at", rep["rows"][0]["hidden_at"] is not None,
          True)
    check("and it keeps the state it earned", rep["rows"][0]["state"],
          "uncheckable")
    conn.close()


def case_expiring_excludes_hidden_rows():
    # Documented: the sibling of the tab badge. A hide that leaves the
    # badge lit has not stopped the row reappearing.
    conn = fresh()
    add_key(conn, "Shown Key", machine_name="shown", expiry=iso(5))
    add_key(conn, "Hidden Key", machine_name="hid", expiry=iso(5))
    conn.execute("INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
                 "VALUES ('k1','hid','2026-07-01T00:00:00')")
    rep = keys.report(conn, now=NOW)
    check("both rows are reported", rep["reported"], 2)
    check("but only the visible one counts as expiring", rep["expiring"], 1)
    conn.close()


def case_expiring_excludes_already_expired_rows():
    conn = fresh()
    add_key(conn, "Dead Key", expiry=iso(-5))
    check("an expired key is not 'expiring'",
          keys.report(conn, now=NOW)["expiring"], 0)
    conn.close()


def case_counts_cover_every_key_and_rows_exclude_matched():
    conn = fresh()
    add_key(conn, "Widget Quest", machine_name="wq")
    add_key(conn, "Cinder Vale Chronicles", machine_name="cvc")
    add_library(conn, "steam", ["Widget Quest"])
    rep = keys.report(conn, now=NOW)
    check("the counts partition every key",
          sum(rep["counts"].values()), rep["total"])
    check("and rows hold exactly the non-matched ones",
          rep["reported"], rep["total"] - rep["counts"]["matched"])
    conn.close()


def case_revealed_is_read_from_the_blob():
    # "revealed", never "redeemed": Humble sets this when the value is
    # DISPLAYED, which is why the distinction exists at all.
    conn = fresh()
    add_key(conn, "Shown Key", machine_name="a", revealed=True)
    add_key(conn, "Quiet Key", machine_name="b", revealed=False)
    by = {r["product"]: r for r in keys.report(conn, now=NOW)["rows"]}
    check("a revealed key is flagged", by["Shown Key"]["revealed"], True)
    check("an unrevealed one is not", by["Quiet Key"]["revealed"], False)
    conn.close()


def case_a_row_whose_blob_is_not_json_still_reports():
    # Documented: a blob that is not JSON skips its row's extras instead
    # of failing the whole query.
    conn = fresh()
    add_bundle(conn)
    conn.execute("INSERT INTO external_keys (gamekey, machine_name, "
                 "human_name, key_type, raw) VALUES "
                 "('k1','broken','Broken Key','steam','not json at all')")
    rep = keys.report(conn, now=NOW)
    check("the key is still reported", rep["total"], 1)
    check("with no expiry from the unreadable blob",
          rep["rows"][0]["expires"], None)
    conn.close()


# ------------------------------------------------------------ stale_hides

def case_a_hide_naming_a_live_key_is_not_stale():
    conn = fresh()
    add_key(conn, "Widget Quest", machine_name="wq")
    conn.execute("INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
                 "VALUES ('k1','wq','2026-07-01T00:00:00')")
    check("a hide on a present key is not stale", keys.stale_hides(conn), 0)
    conn.close()


def case_a_hide_naming_a_vanished_key_is_stale():
    conn = fresh()
    add_bundle(conn)
    conn.execute("INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
                 "VALUES ('k1','gone','2026-07-01T00:00:00')")
    check("a hide with no key behind it is stale", keys.stale_hides(conn), 1)
    conn.close()


def case_a_hide_on_a_matched_key_is_not_stale():
    # The documented reason stale_hides has its own query: the cheap
    # derivation - hides minus hidden rows shown - would count this one,
    # because matched rows are not in `rows` at all.
    conn = fresh()
    add_key(conn, "Widget Quest", machine_name="wq")
    add_library(conn, "steam", ["Widget Quest"])
    conn.execute("INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
                 "VALUES ('k1','wq','2026-07-01T00:00:00')")
    rep = keys.report(conn, now=NOW)
    check("the key is matched and unlisted", rep["rows"], [])
    check("yet its hide is not stale", rep["stale_hides"], 0)
    conn.close()


# ---------------------------------------------------------- format_report

def sample(conn):
    return keys.report(conn, now=NOW)


def case_show_all_changes_how_much_is_printed():
    # The documented parameter, at both values, and it must change output.
    conn = fresh()
    for n in range(30):
        add_key(conn, f"Key Number {n:02d}", machine_name=f"mn{n}")
    rep = sample(conn)
    short = keys.format_report(rep, show_all=False)
    full = keys.format_report(rep, show_all=True)
    check("show_all prints more lines",
          len(full.splitlines()) > len(short.splitlines()), True)
    conn.close()


def case_hidden_changes_which_rows_are_printed():
    conn = fresh()
    add_key(conn, "Shown Key", machine_name="a")
    add_key(conn, "Hidden Key", machine_name="b")
    conn.execute("INSERT INTO hidden_keys (gamekey, machine_name, hidden_at) "
                 "VALUES ('k1','b','2026-07-01T00:00:00')")
    rep = sample(conn)
    normal = keys.format_report(rep, show_all=True)
    hidden = keys.format_report(rep, show_all=True, hidden=True)
    check("the default view shows the visible key",
          "Shown Key" in normal, True)
    check("and omits the hidden one", "Hidden Key" in normal, False)
    check("the hidden view shows the hidden key",
          "Hidden Key" in hidden, True)
    conn.close()


def case_an_empty_catalog_formats_without_raising():
    conn = fresh()
    text = keys.format_report(sample(conn))
    check("an empty key set still produces a report",
          isinstance(text, str) and len(text) > 0, True)
    conn.close()


def case_a_long_product_name_does_not_widen_every_row():
    """MAX_NAME, asserted as the property rather than as a width bound.

    Past the cap a name overflows ITS OWN row rather than pushing every
    other row's columns off an 80-column console. The check that states
    that is differential: the short row must render identically whether
    or not the 92-character name is in the same report. A bound on the
    widest line would pass against code that padded everything, since
    the long row is legitimately long either way.
    """
    def name_field(with_long):
        """The width of the name column on the short row."""
        conn = fresh()
        if with_long:
            add_key(conn, "A" * 92, machine_name="long")
        add_key(conn, "Short Key", machine_name="short")
        text = keys.format_report(sample(conn), show_all=True)
        conn.close()
        line = next(l for l in text.splitlines() if "Short Key" in l)
        return line.index("steam") - line.index("Short Key")

    alone, beside = name_field(False), name_field(True)
    check("with only short names the column fits them",
          alone < keys.MAX_NAME, True)
    check("a 92-character neighbour widens the column only to the cap",
          beside <= keys.MAX_NAME + 2, True)
    check("and never to the full 92", beside < 92, True)


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
    print(f"keys-report: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
