"""Known-answer battery for the bundle-preview tier walk.

Covers the `bundle-preview-tiers` inventory row: `preview()` itself, the
`_overlaps`/`_series_note`/`format_report` helpers it feeds, and the
counting rules a purchase decision rests on. Also carries the H1 cases -
the bundle page blob read without a type check.

The counting cases are known-answer, not liveness: every one states the
number the report MUST show for a hand-built bundle, because the defect
this row was filed for returns a confident wrong count rather than
raising. A run-without-crash sweep passes over exactly that.

Every title here is invented, from docs/TEST-DATA.md.

Fresh database per case: reusing one carries the previous case's rows
into the next and trips the machine_name UNIQUE constraint.
"""
import io
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import bundle_preview, db  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def check_no_raise(label, fn):
    try:
        fn()
    except Exception as exc:                                # noqa: BLE001
        FAIL.append(label)
        print(f"  FAIL {label}: {type(exc).__name__}: {exc}")
        return None
    PASS.append(label)
    return True


def fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return db.connect(pathlib.Path(tmp.name))


def add_item(conn, machine_name, name, type_="ebook"):
    cur = conn.execute(
        "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
        (machine_name, name, type_))
    conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                 (cur.lastrowid,))
    return cur.lastrowid


def add_game(conn, store, store_id, title):
    from humble_catalog.titles import clean_game_title
    conn.execute(
        "INSERT INTO games (store, store_id, title, normalized_title, "
        "imported_at) VALUES (?,?,?,?,?)",
        (store, store_id, title, clean_game_title(title), "2026-01-01T00:00:00"))


def add_import(conn, store, count=1):
    conn.execute(
        "INSERT INTO game_imports (store, imported_at, count, source) "
        "VALUES (?,?,?,?)", (store, "2026-01-01T00:00:00", count, "api"))


def add_key(conn, gamekey, bundle_name, machine_name, human_name, key_type):
    conn.execute(
        "INSERT OR IGNORE INTO bundles (gamekey, name, url) VALUES (?,?,?)",
        (gamekey, bundle_name, f"https://example.invalid/{gamekey}"))
    conn.execute(
        "INSERT INTO external_keys (gamekey, machine_name, human_name, "
        "key_type) VALUES (?,?,?,?)",
        (gamekey, machine_name, human_name, key_type))


def tier(names, price=10.0, key="t1"):
    """One tier_display_data entry plus its pricing entry."""
    return ({key: {"tier_item_machine_names": names}},
            {key: {"price|money": {"amount": price}}})


def book(human_name):
    return {"human_name": human_name}


def game(human_name, stores=("steam",)):
    return {"human_name": human_name,
            "platforms_and_oses": {"game": {s: ["windows"] for s in stores}}}


# ---------------------------------------------------------------- counting

def case_owned_book_counted():
    conn = fresh()
    add_item(conn, "widget_svc", "Building Widget Services")
    display, pricing = tier(["widget_svc", "quiet_harbor"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"widget_svc": book("Building Widget Services"),
                           "quiet_harbor": book("The Quiet Harbor: A Novel")}})
    t = r["tiers"][0]
    check("owned book is counted owned, the other new",
          (t["total"], t["owned"], t["new"]), (2, 1, 1))
    check("adds lists the unowned title by human_name",
          t["adds"], ["The Quiet Harbor: A Novel"])
    conn.close()


def case_merged_away_name_is_owned():
    # _owned unions merges: a duplicate merged away is not an items row
    # but still names a book in the library.
    conn = fresh()
    kept = add_item(conn, "widget_svc", "Building Widget Services")
    conn.execute("INSERT INTO merges (dropped_machine_name, kept_item_id) "
                 "VALUES (?,?)", ("widget_svc_2e", kept))
    display, pricing = tier(["widget_svc_2e"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"widget_svc_2e": book("Building Widget Services 2e")}})
    check("a merged-away machine_name counts as owned",
          (r["tiers"][0]["owned"], r["tiers"][0]["new"]), (1, 0))
    conn.close()


def case_tiers_sort_by_price_and_adds_are_disjoint():
    conn = fresh()
    display = {
        "cheap": {"tier_item_machine_names": ["a_one"]},
        "rich": {"tier_item_machine_names": ["a_one", "b_two"]},
    }
    pricing = {"cheap": {"price|money": {"amount": 5.0}},
               "rich": {"price|money": {"amount": 20.0}}}
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"a_one": book("Salt and Sextant"),
                           "b_two": book("Nightjar Post")}})
    prices = [t["price"] for t in r["tiers"]]
    check("tiers are ordered by price, richest first", prices, [20.0, 5.0])
    rich, cheap = r["tiers"]
    check("the cheaper tier keeps its own item", cheap["adds"],
          ["Salt and Sextant"])
    check("the richer tier adds only what it gains", rich["adds"],
          ["Nightjar Post"])
    check("adds are disjoint and sum to the richest tier's new count",
          len(rich["adds"]) + len(cheap["adds"]), rich["new"])
    conn.close()


def case_adds_sorted_case_insensitively():
    conn = fresh()
    display, pricing = tier(["a_one", "b_two", "c_three"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"a_one": book("zebra crossing"),
                           "b_two": book("Alpha Signal"),
                           "c_three": book("mid stream")}})
    check("adds sort case-insensitively, not by byte value",
          r["tiers"][0]["adds"], ["Alpha Signal", "mid stream", "zebra crossing"])
    conn.close()


def case_sold_name_absent_from_item_data():
    # Counting must be exhaustive; hinting must not be. A name no
    # tier_item_data describes still counts, and falls back to itself.
    conn = fresh()
    display, pricing = tier(["described", "undescribed"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"described": book("Salt and Sextant")}})
    t = r["tiers"][0]
    check("an undescribed sold name still counts in total", t["total"], 2)
    check("it falls back to the bare machine_name in adds",
          t["adds"], ["Salt and Sextant", "undescribed"])
    conn.close()


def case_cumulative_tiers_dedupe_candidates():
    conn = fresh()
    add_item(conn, "owned_one", "Building Widget Services")
    display = {
        "cheap": {"tier_item_machine_names": ["owned_one", "new_one"]},
        "rich": {"tier_item_machine_names": ["owned_one", "new_one"]},
    }
    pricing = {"cheap": {"price|money": {"amount": 5.0}},
               "rich": {"price|money": {"amount": 20.0}}}
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"owned_one": book("Building Widget Services"),
                           "new_one": book("Nightjar Post")}})
    check("the same name in two cumulative tiers is one candidate",
          [t["owned"] for t in r["tiers"]], [1, 1])
    check("the richer tier lists it, the cheaper one does not repeat it",
          [t["adds"] for t in r["tiers"]], [[], ["Nightjar Post"]])
    conn.close()


# ------------------------------------------------------------------- games

def case_game_verdicts_route_correctly():
    conn = fresh()
    add_game(conn, "steam", "1", "Widget Quest")
    add_game(conn, "steam", "2", "Pixel Harbor Rally")
    add_import(conn, "steam", 2)
    display, pricing = tier(["exact", "band", "unrelated"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {
            "exact": game("Widget Quest"),
            "band": game("Pixel Harbor Racing"),
            "unrelated": game("Cinder Vale Chronicles")}})
    t = r["tiers"][0]
    check("an exact game title counts owned", t["owned"], 1)
    check("a band title is possible and counted as neither", t["possible"], 1)
    check("an unrelated game title is new", t["new"], 1)
    check("the possible item names both sides",
          (t["possible_items"][0]["offered"],
           t["possible_items"][0]["owned_title"]),
          ("Pixel Harbor Racing", "Pixel Harbor Rally"))
    check("game_matching is set when a game path was taken",
          r["game_matching"], True)
    conn.close()


def case_game_matching_flag_is_false_for_a_book_bundle():
    conn = fresh()
    display, pricing = tier(["a_one"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"a_one": book("Salt and Sextant")}})
    check("game_matching is false when nothing took the game path",
          r["game_matching"], False)
    conn.close()


def case_keyed_game_counts_owned_and_is_listed_apart():
    conn = fresh()
    add_key(conn, "keyvault1", "Humble Game Bundle: Key Vault",
            "wq", "Widget Quest", "steam")
    display, pricing = tier(["offered_wq"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"offered_wq": game("Widget Quest")}})
    t = r["tiers"][0]
    check("a keyed game counts inside owned", (t["owned"], t["new"]), (1, 0))
    check("and is listed apart with its key type and bundle",
          (t["keyed"], t["keyed_items"][0]["key_type"],
           t["keyed_items"][0]["bundle"]),
          (1, "steam", "Humble Game Bundle: Key Vault"))
    conn.close()


def case_library_match_wins_over_key():
    # Keys are tried only after the libraries said new, so a game both
    # keyed and activated reports as the plain library match it is.
    conn = fresh()
    add_game(conn, "steam", "1", "Widget Quest")
    add_import(conn, "steam", 1)
    add_key(conn, "keyvault1", "Humble Game Bundle: Key Vault",
            "wq", "Widget Quest", "steam")
    display, pricing = tier(["offered_wq"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"offered_wq": game("Widget Quest")}})
    t = r["tiers"][0]
    check("an activated game is a library match, not a keyed one",
          (t["owned"], t["keyed"]), (1, 0))
    conn.close()


def case_unimported_store_warning_is_scoped_to_unmatched():
    conn = fresh()
    add_game(conn, "steam", "1", "Widget Quest")
    add_import(conn, "steam", 1)
    display, pricing = tier(["matched", "unmatched"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {
            # delivered on an unimported store but already owned by title
            "matched": game("Widget Quest", stores=("epic",)),
            "unmatched": game("Cinder Vale Chronicles", stores=("gog",))}})
    check("only a store with an unmatched item is warned about",
          r["unimported_stores"], ["gog"])
    conn.close()


def case_imported_store_is_never_warned_about():
    conn = fresh()
    add_import(conn, "steam", 0)
    display, pricing = tier(["unmatched"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"unmatched": game("Cinder Vale Chronicles")}})
    check("an imported store is never named as unimported",
          r["unimported_stores"], [])
    conn.close()


# -------------------------------------------------------- series/overlaps

def case_series_hit_is_removed_from_overlaps():
    # Series lines are computed BEFORE _overlaps and take their candidates
    # out of it, so a volume is reported once and in the accurate place.
    conn = fresh()
    add_item(conn, "wings_1", "Wings of Autumn Dusk (Book 1)")
    display, pricing = tier(["wings_3"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"wings_3": book("Wings of Autumn Dusk (Book 3)")}})
    offered_in_series = [h["offered"] for h in r["series"]]
    offered_in_overlaps = [h["offered"] for h in r["overlaps"]]
    check("an offered volume of an owned series is a series line",
          offered_in_series, ["Wings of Autumn Dusk (Book 3)"])
    check("and is NOT also listed as a suspected overlap",
          offered_in_overlaps, [])
    conn.close()


def case_owned_item_never_reaches_overlaps():
    conn = fresh()
    add_item(conn, "widget_svc", "Building Widget Services")
    display, pricing = tier(["widget_svc"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"widget_svc": book("Building Widget Services")}})
    check("an owned item is unrepresentable in overlaps", r["overlaps"], [])
    conn.close()


def case_empty_catalog_reports_everything_new():
    conn = fresh()
    display, pricing = tier(["a_one", "b_two"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"a_one": book("Salt and Sextant"),
                           "b_two": book("Nightjar Post")}})
    t = r["tiers"][0]
    check("an empty catalog owns nothing and survives the walk",
          (t["total"], t["owned"], t["new"], r["overlaps"], r["series"]),
          (2, 0, 2, [], []))
    conn.close()


# ------------------------------------------------------- report rendering

def _sample_report(conn):
    display, pricing = tier(["a_one"], price=21.9)
    return bundle_preview.preview(conn, {
        "basic_data": {"human_name": "Bundle One", "currency": "EUR"},
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"a_one": book("Salt and Sextant")}},
        url="https://www.humblebundle.com/books/example")


def case_format_report_encoding_changes_the_symbol():
    conn = fresh()
    report = _sample_report(conn)
    utf8 = bundle_preview.format_report(report, "utf-8")
    dos = bundle_preview.format_report(report, "cp437")
    check("utf-8 keeps the currency symbol", "€21.90" in utf8, True)
    check("an encoding that cannot carry it falls back to the ISO code",
          "EUR 21.90" in dos, True)
    check("the fallback is the code, never a replacement character",
          "?21.90" in dos, False)
    conn.close()


def case_format_report_names_and_counts():
    conn = fresh()
    text = bundle_preview.format_report(_sample_report(conn), "utf-8")
    check("the bundle name heads the report",
          text.splitlines()[0], "Bundle One")
    check("a one-item tier says item, not items", " 1 item " in text, True)
    check("the adds block names its count", "adds 1 new:" in text, True)
    conn.close()


def case_preview_url_parameter_at_two_values():
    conn = fresh()
    display, pricing = tier(["a_one"])
    bundle = {"tier_display_data": display, "tier_pricing_data": pricing,
              "tier_item_data": {"a_one": book("Salt and Sextant")},
              "page_url": "https://www.humblebundle.com/books/from-blob"}
    given = bundle_preview.preview(conn, bundle, url="https://example.invalid/x")
    fallback = bundle_preview.preview(conn, bundle)
    check("an explicit url wins", given["url"], "https://example.invalid/x")
    check("otherwise the blob's page_url is used",
          fallback["url"], "https://www.humblebundle.com/books/from-blob")
    conn.close()


def case_currency_and_name_defaults():
    conn = fresh()
    r = bundle_preview.preview(conn, {})
    check("an absent name and currency fall back to documented defaults",
          (r["name"], r["currency"], r["tiers"]),
          ("Humble Bundle", "USD", []))
    conn.close()


# ------------------------------------------------------------- H1: shapes

def case_machine_names_as_a_bare_string():
    """The H1 headline: a wrong ANSWER, not a crash.

    Unfixed, `for name in names` iterates a string character by character
    and reports a 1-item tier as 10 items with single letters under adds.
    The desired reading follows the project's own precedent for a list
    field that arrived unwrapped - shapes.first_text and shapes.text_list
    both treat a bare string as one entry, never as its characters.
    """
    conn = fresh()
    display, pricing = tier("widget_svc")
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"widget_svc": book("Building Widget Services")}})
    t = r["tiers"][0]
    check("a bare-string name list is one item, never its characters",
          (t["total"], t["new"]), (1, 1))
    check("and adds names the item, not single letters",
          t["adds"], ["Building Widget Services"])


def case_delivery_stores_never_yields_letters():
    conn = fresh()
    display, pricing = tier(["odd"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"odd": {"human_name": "Widget Quest",
                                   "platforms_and_oses": {"game": "steam"}}}})
    check("an off-shape store map yields no single-letter stores",
          r["unimported_stores"], [])
    conn.close()


def case_off_shape_blob_fields_do_not_raise():
    shapes = [
        ("bundle itself is a list", ["x"]),
        ("basic_data is a non-empty list", {"basic_data": ["x"]}),
        ("tier_display_data is a non-empty list",
         {"tier_display_data": ["x"]}),
        ("tier_item_data is a non-empty list", {"tier_item_data": ["x"]}),
        ("one tier display is a string",
         {"tier_display_data": {"t1": "oops"}}),
        ("one item entry is a string",
         {"tier_display_data": {"t1": {"tier_item_machine_names": ["a"]}},
          "tier_item_data": {"a": "oops"}}),
        ("a pricing entry is a string",
         {"tier_display_data": {"t1": {"tier_item_machine_names": []}},
          "tier_pricing_data": {"t1": "oops"}}),
        ("a price amount is a string",
         {"tier_display_data": {"t1": {"tier_item_machine_names": []}},
          "tier_pricing_data": {"t1": {"price|money": {"amount": "free"}}}}),
    ]
    for label, payload in shapes:
        conn = fresh()
        check_no_raise(f"off-shape blob: {label}",
                       lambda p=payload: bundle_preview.preview(conn, p))
        conn.close()


def case_off_shape_price_defaults_to_zero():
    conn = fresh()
    r = bundle_preview.preview(conn, {
        "tier_display_data": {"t1": {"tier_item_machine_names": []}},
        "tier_pricing_data": {"t1": {"price|money": {"amount": "free"}}}})
    check("a non-numeric price reads as 0.0, never as text",
          r["tiers"][0]["price"], 0.0)
    conn.close()


def case_off_shape_human_name_falls_back():
    conn = fresh()
    display, pricing = tier(["a_one"])
    r = bundle_preview.preview(conn, {
        "tier_display_data": display, "tier_pricing_data": pricing,
        "tier_item_data": {"a_one": {"human_name": 5}}})
    check("a non-string human_name falls back to the machine_name",
          r["tiers"][0]["adds"], ["a_one"])
    conn.close()


class _Resp:
    """A minimal stand-in for the object _fetch_html returns."""

    def __init__(self, text):
        self.raw = io.BytesIO(text.encode("utf-8"))
        self.encoding = "utf-8"
        self.headers = {"content-type": "text/html"}
        self.status_code = 200

    def iter_content(self, chunk_size=8192, decode_unicode=False):
        while True:
            block = self.raw.read(chunk_size)
            if not block:
                return
            yield block.decode("utf-8") if decode_unicode else block

    def close(self):
        pass


def _page(blob):
    return ('<html><script id="webpack-bundle-page-data" '
            'type="application/json">' + blob + "</script></html>")


def case_fetch_bundle_blob_that_is_not_an_object():
    """fetch_bundle line 75: json.loads(...).get on a non-object blob."""
    import humble_catalog.url_import as url_import
    original = url_import._fetch_html
    for label, blob in [("a list", json.dumps([1, 2, 3])),
                        ("a string", json.dumps("nope")),
                        ("bundleData is a list",
                         json.dumps({"bundleData": ["x"]}))]:
        url_import._fetch_html = lambda url, http=None, _b=blob: _Resp(_page(_b))
        try:
            got = check_no_raise(
                f"fetch_bundle: blob is {label}",
                lambda: bundle_preview.fetch_bundle(
                    "https://www.humblebundle.com/books/example"))
            if got:
                result = bundle_preview.fetch_bundle(
                    "https://www.humblebundle.com/books/example")
                check(f"fetch_bundle: blob is {label} yields a mapping",
                      result, {})
        finally:
            url_import._fetch_html = original


def case_fetch_bundle_still_refuses_a_foreign_host():
    # The guard this row shares with bundle-preview-parts must not have
    # been weakened by the shape work.
    for url in ["https://example.invalid/books/x",
                "https://humblebundle.com.evil.invalid/x"]:
        try:
            bundle_preview.fetch_bundle(url)
            FAIL.append(f"foreign host refused: {url}")
            print(f"  FAIL foreign host refused: {url}")
        except ValueError:
            PASS.append(f"foreign host refused: {url}")
        except Exception as exc:                            # noqa: BLE001
            FAIL.append(f"foreign host refused: {url}")
            print(f"  FAIL foreign host refused: {url}: {exc!r}")


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
    print(f"bundle-preview-tiers: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
