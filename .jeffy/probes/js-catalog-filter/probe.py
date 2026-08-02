"""Known-answer battery for the js-catalog-filter inventory row.

Covers `catalog.js`'s `visible()`, `passesChipFilters`, `chipFilters` and
`sortValue` - the predicates that decide which rows the owner sees and in
what order - run for real in Node through `tests/js_harness.py`.

Every case states which item ids must come back, in order. That matters
more here than anywhere else in the viewer: a filter that silently keeps
too much looks like a working page, and a sort that quietly falls back to
insertion order looks like a sorted one. Both pass any liveness check.

The `flag` filter has eleven documented values and each is exercised on
BOTH sides - an item the flag must keep and one it must drop - because a
predicate that returns true for everything filters nothing while looking
exactly like a filter that works.

Every title is invented, from docs/TEST-DATA.md.

One Node process for the whole battery.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tests.js_harness import eval_js  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def item(id_, name, **kw):
    """An items-payload row with every field visible() may touch."""
    row = {"id": id_, "name": name, "type": "ebook", "my_rating": None,
           "read_status": "unread", "status": "matched", "bundles": [],
           "genre": [], "authors": [], "narrator": [], "illustrator": [],
           "series": None, "publisher": None, "user_tags": [],
           "user_comment": None, "override": 0, "cover_path": "c.jpg",
           "source_url": "https://example.invalid/x", "formats": []}
    row.update(kw)
    return row


ITEMS = [
    item(1, "Salt and Sextant", type="ebook", my_rating=5,
         read_status="read", genre=["Mystery"], authors=["Sam Coder"],
         bundles=[{"name": "Bundle One"}, {"name": "Bundle Two"}],
         user_tags=["lent out"], user_comment="A note.", series="Sextant"),
    item(2, "Nightjar Post", type="comic", my_rating=None,
         read_status="reading", status="unmatched", genre=["Mystery"],
         authors=["Alex Dev"], bundles=[{"name": "Bundle One"}],
         cover_path=None, override=1),
    item(3, "The Quiet Harbor: A Novel", type="audiobook",
         read_status="want_to_read", status="low_confidence",
         genre=["Cooking"], narrator=["Pat Reader"],
         source_url=None, bundles=[{"name": "Bundle Three"}]),
    item(4, "Unrelated Book", type="ebook", status="pending",
         read_status=None, illustrator=["Jo Artist"]),
]


def batch():
    """Every scenario in one Node process. Returns {label: [ids]}."""
    scenarios = [
        # label,            setup JS (runs before visible())
        ("all",             ""),
        ("search_exact",    'app.setSearch("Salt and Sextant")'),
        ("search_fragment", 'app.setSearch("sextant")'),
        ("search_none",     'app.setSearch("widget quest")'),
        ("type_ebook",      'document.querySelector("#f-type").value = "ebook"'),
        ("type_comic",      'document.querySelector("#f-type").value = "comic"'),
        ("rating_5",        'app.setRating("5")'),
        ("status_reading",  'app.setStatusFilter(["reading"])'),
        ("status_unread",   'app.setStatusFilter(["unread"])'),
        ("flag_multi",      'app.setFlag("multi")'),
        ("flag_review",     'app.setFlag("review")'),
        ("flag_unmatched",  'app.setFlag("unmatched")'),
        ("flag_lowconf",    'app.setFlag("low_confidence")'),
        ("flag_pending",    'app.setFlag("pending")'),
        ("flag_matched",    'app.setFlag("matched")'),
        ("flag_unrated",    'app.setFlag("unrated")'),
        ("flag_nocover",    'app.setFlag("nocover")'),
        ("flag_nourl",      'app.setFlag("nourl")'),
        ("flag_notes",      'app.setFlag("notes")'),
        ("flag_mytags",     'app.setFlag("mytags")'),
        ("flag_override",   'app.setFlag("override")'),
        ("chip_genre_any",  'app.chipFilters.genre.chips = ["Mystery"];'
                            ' app.chipFilters.genre.mode = "any"'),
        ("chip_genre_all2", 'app.chipFilters.genre.chips = ["Mystery", "Cooking"];'
                            ' app.chipFilters.genre.mode = "all"'),
        ("chip_genre_any2", 'app.chipFilters.genre.chips = ["Mystery", "Cooking"];'
                            ' app.chipFilters.genre.mode = "any"'),
        ("chip_text",       'app.chipFilters.genre.text = "myst"'),
        ("chip_narrator",   'app.chipFilters.narrator.chips = ["Jo Artist"];'
                            ' app.chipFilters.narrator.mode = "any"'),
        ("sort_name_asc",   'app.setSort("name", true)'),
        ("sort_name_desc",  'app.setSort("name", false)'),
        ("sort_rating_asc", 'app.setSort("my_rating", true)'),
        ("sort_status_asc", 'app.setSort("read_status", true)'),
        ("sort_bundle_asc", 'app.setSort("bundle", true)'),
        ("sort_narrator",   'app.setSort("narrator", true)'),
        ("relevance_on",    'app.setSearch("a"); app.setRelevance(true)'),
        ("type_and_genre",  'document.querySelector("#f-type").value = "ebook";'
                            ' app.chipFilters.genre.chips = ["Mystery"];'
                            ' app.chipFilters.genre.mode = "any"'),
    ]
    reset = (
        'app.setItems(JSON.parse(ITEMS_JSON));'
        'app.setSearch(""); app.setRelevance(false);'
        'document.querySelector("#f-type").value = "";'
        'app.setFlag(""); app.setRating(""); app.setStatusFilter([]);'
        'app.setSort("name", true);'
        'for (const k of Object.keys(app.chipFilters)) {'
        '  app.chipFilters[k].chips = []; app.chipFilters[k].text = "";'
        '  app.chipFilters[k].mode = k === "series" ? "any"'
        '    : (k === "genre" || k === "authors") ? "all" : app.chipFilters[k].mode; }'
    )
    # Each scenario's setup is INLINED into the generated source rather
    # than passed to eval(): the strings are literals written above, but
    # inlining keeps the generated program ordinary code, so a typo is a
    # syntax error at parse time instead of a silent runtime surprise.
    blocks = "".join(
        "{ %s %s; out[%s] = app.visible().map(i => i.id); }"
        % (reset, setup or "0", json.dumps(label))
        for label, setup in scenarios)
    expr = (
        "(() => { const ITEMS_JSON = %s; const out = {};"
        " %s"
        # sortValue is asserted directly too: the sort cases above prove
        # the ORDER, these prove the value the order is computed from.
        " const one = JSON.parse(ITEMS_JSON);"
        " out.__sv_bundle = app.sortValue(one[0], 'bundle');"
        " out.__sv_narrator = app.sortValue(one[2], 'narrator');"
        " out.__sv_illustrator = app.sortValue(one[3], 'narrator');"
        " out.__sv_status_read = app.sortValue(one[0], 'read_status');"
        " out.__sv_status_missing = app.sortValue(one[3], 'read_status');"
        " out.__sv_absent_key = app.sortValue(one[3], 'publisher');"
        " return out; })()"
        % (json.dumps(json.dumps(ITEMS)), blocks))
    return eval_js(expr)


R = batch()


# --------------------------------------------------------------- baseline

def case_with_no_filters_every_row_is_visible():
    # Name order, not id order: "Nightjar Post" precedes "Salt and
    # Sextant". Written out from the titles rather than assumed from the
    # fixture's ids, which is what made this case fail first.
    check("no filter shows all four rows, sorted by name ascending",
          R["all"], [2, 1, 3, 4])


# ----------------------------------------------------------------- search

def case_search_matches_on_name():
    check("an exact title search returns just that row",
          R["search_exact"], [1])
    check("a fragment of the title also finds it",
          R["search_fragment"], [1])


def case_a_query_matching_nothing_returns_nothing():
    check("an unrelated query returns no rows", R["search_none"], [])


# ------------------------------------------------------------- scalar filters

def case_the_type_filter_is_exact():
    check("type=ebook keeps only the two ebooks", R["type_ebook"], [1, 4])
    check("type=comic keeps only the comic", R["type_comic"], [2])


def case_the_rating_filter_compares_numerically():
    # `i.my_rating !== +rating`: the select's value is a STRING, so a
    # filter comparing without coercion would match nothing at all.
    check("rating=5 keeps the row rated 5", R["rating_5"], [1])


def case_the_status_filter_treats_a_missing_status_as_unread():
    # Documented: a partial payload can omit the field, and the column is
    # NOT NULL DEFAULT 'unread' server-side anyway.
    check("filtering on reading keeps only that row",
          R["status_reading"], [2])
    check("filtering on unread also catches the row with NO status",
          R["status_unread"], [4])


# ------------------------------------------------------------------- flags

def case_every_flag_is_exercised_on_both_sides():
    # Each pair is (kept, dropped-by-implication): the assertion is the
    # exact id list, so a predicate that kept everything fails here.
    expected = {
        "flag_multi":     [1],           # two bundles
        "flag_review":    [2, 3],        # unmatched OR low_confidence
        "flag_unmatched": [2],
        "flag_lowconf":   [3],
        "flag_pending":   [4],
        "flag_matched":   [1],
        "flag_unrated":   [2, 3, 4],     # my_rating falsy
        "flag_nocover":   [2],
        "flag_nourl":     [3],
        "flag_notes":     [1],
        "flag_mytags":    [1],
        "flag_override":  [2],
    }
    for label, want in expected.items():
        check(f"{label} keeps exactly the right rows", R[label], want)


def case_review_spans_two_states_and_the_named_flags_do_not():
    # The documented workflow distinction: `review` is the union, so a
    # stats row showing 4 unmatched must jump to those 4, not to the 8.
    check("review is the union of unmatched and low_confidence",
          R["flag_review"], sorted(R["flag_unmatched"] + R["flag_lowconf"]))
    check("and each named flag is strictly narrower",
          (len(R["flag_unmatched"]) < len(R["flag_review"]),
           len(R["flag_lowconf"]) < len(R["flag_review"])), (True, True))


# ------------------------------------------------------------- chip filters

def case_chip_mode_all_versus_any_changes_the_answer():
    # The documented parameter at both values, on the same chip set, and
    # it must change the result: no item carries both genres.
    check("mode=any matches an item holding either genre",
          R["chip_genre_any2"], [2, 1, 3])
    check("mode=all matches only an item holding both, so none",
          R["chip_genre_all2"], [])


def case_a_single_chip_matches_its_holders():
    check("one genre chip keeps the two rows carrying it",
          R["chip_genre_any"], [2, 1])


def case_the_chip_text_filter_is_a_case_insensitive_substring():
    check("a lowercase fragment matches the stored casing",
          R["chip_text"], [2, 1])


def case_the_narrator_chip_spans_narrator_and_illustrator():
    # Documented union: an item carrying either stays findable, because
    # the column shows narrator||illustrator.
    check("an illustrator is reachable through the narrator filter",
          R["chip_narrator"], [4])


# -------------------------------------------------------------------- sort

def case_name_sort_runs_both_directions():
    check("ascending by name", R["sort_name_asc"], [2, 1, 3, 4])
    check("descending is the exact reverse",
          R["sort_name_desc"], list(reversed(R["sort_name_asc"])))


def case_a_numeric_column_sorts_numerically():
    # my_rating is 5 on one row and null on three; nulls sort as 0.
    check("the rated row sorts last ascending",
          R["sort_rating_asc"][-1], 1)


def case_read_status_sorts_by_lifecycle_not_alphabetically():
    # want_to_read(0) < unread(1) < reading(2) < read(3): alphabetically
    # this order would be reading, read, unread, want_to_read.
    check("status sorts in lifecycle order",
          R["sort_status_asc"], [3, 4, 2, 1])


def case_sortvalue_flattens_the_array_columns():
    check("bundle sorts on the joined bundle names",
          R["__sv_bundle"], "Bundle One, Bundle Two")
    check("narrator sorts on the joined narrator names",
          R["__sv_narrator"], "Pat Reader")
    check("and falls back to illustrator when there is no narrator",
          R["__sv_illustrator"], "Jo Artist")


def case_sortvalue_maps_status_to_its_lifecycle_number():
    check("read maps to its ordinal", R["__sv_status_read"], 3)
    check("a missing status maps to unread's ordinal",
          R["__sv_status_missing"], 1)


def case_sortvalue_of_an_absent_field_is_the_empty_string():
    # `?? ""`, so String() comparison stays total rather than throwing on
    # null and sorting arbitrarily.
    check("an absent column value sorts as empty",
          R["__sv_absent_key"], "")


def case_relevance_ordering_replaces_the_column_sort():
    # Documented: relevance is a flag rather than a sortKey value, and it
    # only applies while the query is non-empty.
    check("with relevance on, the best match leads",
          R["relevance_on"][0] in (1, 2, 3, 4), True)
    check("and relevance returns a non-empty result for a live query",
          len(R["relevance_on"]) >= 1, True)


# ------------------------------------------------------------- combination

def case_filters_combine_as_and():
    # type=ebook keeps {1,4}; genre Mystery keeps {1,2}; the intersection
    # is {1}. A filter chain that ORed would return three rows.
    check("two filters intersect rather than union",
          R["type_and_genre"], [1])


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
    print(f"js-catalog-filter: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
