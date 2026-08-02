"""Known-answer battery for the import-sheets inventory row.

Covers `humble_catalog/import_sheets.py`: the header vocabulary
(`_key`, `_canon`, `unknown_headers`), `_cell`, `norm_title`,
`type_scope`, `build_index`, `match`, and `import_row`'s gap-fill rules.

The rule this module is built around is that it only FILLS GAPS: a value
the owner already has must never be overwritten by a spreadsheet. That is
asserted directly, by reading the row back after an import that had
something to say about every field.

The header vocabulary carries a distinction worth pinning: a header
mapping to None is understood and deliberately dropped ("Bundle" is
authoritative from Humble orders), while an unrecognised header is a typo
that silently imports nothing. Only the second is reported, and
conflating them is exactly what `unknown_headers` exists to prevent.

Every title is invented, from docs/TEST-DATA.md. Fresh database per case.
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, import_sheets as sheets  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def seeded(rows):
    """rows: [(name, type)] -> (conn, {name: id})."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = db.connect(pathlib.Path(tmp.name))
    ids = {}
    for i, (name, type_) in enumerate(rows):
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
            (f"mn_{i}", name, type_))
        ids[name] = cur.lastrowid
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    conn.commit()
    return conn, ids


def enrichment(conn, item_id):
    r = conn.execute(
        "SELECT genre, authors, narrator, series, series_number "
        "FROM enrichment WHERE item_id=?", (item_id,)).fetchone()
    return {k: db.tags_from_json(r[k]) if k in ("genre", "authors", "narrator")
            else r[k] for k in r.keys()}


# ------------------------------------------------------------- header keys

def case_a_header_is_lowercased_and_stripped_of_its_colon():
    for spelling in ["Name", "  name  ", "Name:", "NAME :"]:
        check(f"{spelling!r} keys as 'name'", sheets._key(spelling), "name")


def case_a_non_string_header_cell_is_not_a_header():
    for cell in [None, 5, 5.5, True]:
        check(f"{cell!r} is not a header", sheets._key(cell), None)


def case_a_blank_header_cell_is_not_a_header():
    for cell in ["", "   ", ":"]:
        check(f"{cell!r} is not a header", sheets._key(cell), None)


def case_every_known_header_maps_to_its_field():
    expected = {"name": "title", "genre": "genre", "setting": "genre",
                "series": "series", "number in the series": "series_number",
                "author": "authors", "narrator": "narrator",
                "narator": "narrator", "rating": "rating"}
    for header, field in expected.items():
        check(f"{header!r} is the {field} column", sheets._canon(header), field)


def case_the_misspelled_narrator_column_is_accepted():
    # A real sheet header, kept deliberately: the sheets are hand-authored.
    check("both spellings reach the same field",
          (sheets._canon("narator"), sheets._canon("narrator")),
          ("narrator", "narrator"))


def case_a_deliberately_dropped_header_canonicalizes_to_none():
    # Bundles and publishers are authoritative from Humble orders.
    for header in ["bundle", "humble", "publisher"]:
        check(f"{header!r} is understood and dropped",
              sheets._canon(header), None)


def case_unknown_headers_reports_typos_but_not_dropped_columns():
    """The distinction the function exists for.

    `_canon` returning None conflates two different things: a column that
    is understood and dropped, and a typo that silently imports nothing.
    Only the second is worth telling anyone about.
    """
    header = ["Name", "Bundle", "Publisher", "Ratings", "Athor", "Genre"]
    check("only the unrecognised cells are reported",
          sheets.unknown_headers(header), ["Ratings", "Athor"])


def case_unknown_headers_of_an_empty_row_is_empty():
    for header in [None, (), [], [None, "", 5]]:
        check(f"{header!r} reports nothing",
              sheets.unknown_headers(header), [])


# -------------------------------------------------------------------- cell

def case_a_cell_is_trimmed():
    check("surrounding space is removed", sheets._cell("  Widget Quest  "),
          "Widget Quest")


def case_an_empty_cell_is_none():
    for value in ["", "   ", None]:
        check(f"{value!r} is empty", sheets._cell(value), None)


def case_the_sheets_spelling_of_absent_is_empty():
    # The sheets use N/A for "no genre" / "no number".
    for value in ["N/A", "n/a", " N/A "]:
        check(f"{value!r} counts as empty", sheets._cell(value), None)


def case_a_numeric_zero_survives():
    # Documented: a 0 rating means "unrated" and is skipped later WITH
    # that meaning, rather than being lost here.
    check("zero is not treated as empty", sheets._cell(0), 0)


# -------------------------------------------------------------- norm_title

def case_norm_title_lowercases_and_strips_punctuation():
    check("punctuation becomes space and case is folded",
          sheets.norm_title("The Quiet Harbor: A Novel!"),
          "the quiet harbor a novel")


def case_norm_title_collapses_whitespace():
    check("runs of space collapse to one",
          sheets.norm_title("  Salt   and\tSextant  "), "salt and sextant")


def case_an_integral_float_loses_its_decimal():
    # Documented: floats like 1632.0 -> '1632'. A sheet cell holding a
    # numeric title arrives as a float, and "1632.0" would match nothing.
    check("1632.0 normalizes as an integer", sheets.norm_title(1632.0), "1632")
    check("and a non-integral float keeps its point",
          sheets.norm_title(16.5), "16 5")


def case_two_spellings_of_one_title_share_a_key():
    check("punctuation and case differences merge",
          sheets.norm_title("Salt & Sextant") ==
          sheets.norm_title("salt  and sextant"), False)
    check("but punctuation alone does merge",
          sheets.norm_title("Nightjar Post!") ==
          sheets.norm_title("nightjar post"), True)


# -------------------------------------------------------------- type_scope

def case_the_audiobook_workbook_scopes_to_audiobooks():
    check("an audiobooks sheet matches audiobook items",
          sheets.type_scope("Reference spreadsheets/Audiobooks (loose).xlsx"),
          ("audiobook",))


def case_any_other_workbook_scopes_to_ebooks_and_comics():
    for name in ["E-books (loose collection).xlsx", "anything.xlsx"]:
        check(f"{name} matches ebooks and comics",
              sheets.type_scope(name), ("ebook", "comic"))


def case_the_scope_test_is_case_insensitive():
    check("AUDIOBOOKS in caps still scopes to audiobook",
          sheets.type_scope("AUDIOBOOKS.xlsx"), ("audiobook",))


# ------------------------------------------------------- build_index/match

def case_the_index_is_scoped_to_the_workbook_type():
    conn, ids = seeded([("Salt and Sextant", "ebook"),
                        ("The Copper Almanac", "audiobook")])
    index, _display = sheets.build_index(conn, ("ebook", "comic"))
    check("only the ebook is indexed", sorted(index), ["salt and sextant"])
    conn.close()


def case_a_unique_title_matches_its_item():
    conn, ids = seeded([("Salt and Sextant", "ebook")])
    index, display = sheets.build_index(conn, ("ebook", "comic"))
    check("a unique title matches",
          sheets.match(index, display, "Salt and Sextant"),
          ("matched", ids["Salt and Sextant"], None))
    conn.close()


def case_a_differently_punctuated_title_still_matches():
    conn, ids = seeded([("The Quiet Harbor: A Novel", "ebook")])
    index, display = sheets.build_index(conn, ("ebook", "comic"))
    status, item_id, _s = sheets.match(index, display,
                                       "the quiet harbor  a novel")
    check("normalization bridges the spelling",
          (status, item_id), ("matched", ids["The Quiet Harbor: A Novel"]))
    conn.close()


def case_two_items_with_one_title_are_ambiguous():
    conn, _ids = seeded([("Gray Waters", "ebook"), ("gray waters", "ebook")])
    index, display = sheets.build_index(conn, ("ebook", "comic"))
    check("an ambiguous title is refused rather than guessed",
          sheets.match(index, display, "Gray Waters"),
          ("ambiguous", None, None))
    conn.close()


def case_an_unmatched_title_suggests_the_closest():
    conn, _ids = seeded([("Salt and Sextant", "ebook")])
    index, display = sheets.build_index(conn, ("ebook", "comic"))
    status, item_id, suggestion = sheets.match(index, display,
                                               "Salt and Sextont")
    check("it does not match", (status, item_id), ("unmatched", None))
    check("but suggests the catalog's spelling",
          suggestion, "Salt and Sextant")
    conn.close()


def case_a_suggestion_is_the_original_spelling_not_the_key():
    conn, _ids = seeded([("The Quiet Harbor: A Novel", "ebook")])
    index, display = sheets.build_index(conn, ("ebook", "comic"))
    _s, _i, suggestion = sheets.match(index, display, "the quiet harbour a novel")
    check("the suggestion keeps the catalog's punctuation",
          suggestion, "The Quiet Harbor: A Novel")
    conn.close()


def case_an_unrelated_title_suggests_nothing():
    conn, _ids = seeded([("Salt and Sextant", "ebook")])
    index, display = sheets.build_index(conn, ("ebook", "comic"))
    check("nothing close enough yields no suggestion",
          sheets.match(index, display, "Widget Quest")[2], None)
    conn.close()


def case_an_empty_catalog_matches_nothing():
    conn, _ids = seeded([])
    index, display = sheets.build_index(conn, ("ebook", "comic"))
    check("no items means no match and no suggestion",
          sheets.match(index, display, "Salt and Sextant"),
          ("unmatched", None, None))
    conn.close()


# ------------------------------------------------------------- import_row

def case_an_empty_field_is_filled():
    conn, ids = seeded([("Salt and Sextant", "ebook")])
    item_id = ids["Salt and Sextant"]
    sheets.import_row(conn, item_id, {"genre": "Mystery",
                                      "authors": "Sam Coder",
                                      "series": "Sextant",
                                      "series_number": 2})
    got = enrichment(conn, item_id)
    check("the genre is filled", got["genre"], ["Mystery"])
    check("the author is filled", got["authors"], ["Sam Coder"])
    check("the series is filled", got["series"], "Sextant")
    conn.close()


def case_a_value_the_owner_already_has_is_never_overwritten():
    """The rule the whole module is built around: gap-fill only."""
    conn, ids = seeded([("Salt and Sextant", "ebook")])
    item_id = ids["Salt and Sextant"]
    conn.execute(
        "UPDATE enrichment SET genre=?, authors=?, series=?, series_number=? "
        "WHERE item_id=?",
        (db.tags_to_json(["Cooking"]), db.tags_to_json(["Alex Dev"]),
         "Owned Series", 9, item_id))
    conn.commit()
    before = enrichment(conn, item_id)

    sheets.import_row(conn, item_id, {"genre": "Mystery",
                                      "authors": "Sam Coder",
                                      "series": "Sheet Series",
                                      "series_number": 1})
    check("every already-set field survives the import",
          enrichment(conn, item_id), before)
    conn.close()


def case_a_sheet_with_nothing_to_say_changes_nothing():
    conn, ids = seeded([("Salt and Sextant", "ebook")])
    item_id = ids["Salt and Sextant"]
    before = enrichment(conn, item_id)
    sheets.import_row(conn, item_id, {})
    check("an empty row fills nothing", enrichment(conn, item_id), before)
    conn.close()


def case_the_fill_count_reports_what_actually_changed():
    conn, ids = seeded([("Salt and Sextant", "ebook")])
    item_id = ids["Salt and Sextant"]
    conn.execute("UPDATE enrichment SET genre=? WHERE item_id=?",
                 (db.tags_to_json(["Cooking"]), item_id))
    conn.commit()
    _ratings, filled = sheets.import_row(
        conn, item_id, {"genre": "Mystery", "authors": "Sam Coder"})
    check("only the empty field counts as filled", filled, 1)
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
    print(f"import-sheets: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
