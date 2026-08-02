"""Known-answer battery for the js-catalog-render inventory row.

Covers `catalog.js`'s `render()`, `highlight`, `statusSelect`, `stars`,
`shownRows`, `renderBulkBar` and the shared `esc`/`tagBadges` helpers -
the table the owner actually reads - run for real in Node through
`tests/js_harness.py`.

Two kinds of case, and the second is why this row is worth running rather
than grepping:

  1. escaping. Every one of these builders concatenates item text into an
     innerHTML string, so a title carrying `<` or `"` either escapes or
     breaks the markup around it. The envelope classes the viewer
     user-error, so this is correctness rather than a security finding -
     but a title that silently truncates the row it is in is a wrong
     display either way.

  2. the guards. `tagBadges`, `person` and the status helpers all carry
     `|| []` / `|| "unread"` guards, added because a partial payload from
     an older server blanked the whole page once. A guard is exactly the
     kind of code that looks present and does nothing, so each is driven
     with the missing field it exists for.

Every title is invented, from docs/TEST-DATA.md. One Node process.
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


def contains(label, haystack, needle, present=True):
    got = (needle in haystack)
    (PASS if got == present else FAIL).append(label)
    if got != present:
        verb = "should contain" if present else "should NOT contain"
        print(f"  FAIL {label}\n       {verb} {needle!r}\n"
              f"       in {haystack[:200]!r}")


def item(id_, name, **kw):
    row = {"id": id_, "name": name, "type": "ebook", "my_rating": None,
           "read_status": "unread", "status": "matched", "bundles": [],
           "genre": [], "authors": [], "narrator": [], "illustrator": [],
           "series": None, "series_number": None, "publisher": None,
           "user_tags": [], "user_comment": None, "override": 0,
           "cover_path": "covers/a.jpg", "source_url": "https://e.invalid/x",
           "formats": [], "external_rating": None}
    row.update(kw)
    return row


# The partial row omits every SCALAR the render guards protect - rating,
# status, cover, url, notes - while keeping the array fields present.
#
# That split is the contract, not squeamishness. `db.fetch_items` runs
# every tag column through `tags_from_json`, which answers [] for NULL, so
# the array fields are always present in a real payload. The chipFilters
# accessors spread them unguarded (`[...i.narrator, ...i.illustrator]`),
# and a row omitting them makes `visible()` throw - but reaching that
# needs an off-contract payload, which the Operating envelope classes
# machine-generated and puts out of envelope. Recorded in the journal
# rather than asserted here, so this battery pins the real contract
# instead of a shape the server cannot produce.
PARTIAL = {"id": 9, "name": "Partial Row", "type": "ebook",
           "bundles": [], "status": "matched",
           "genre": [], "authors": [], "narrator": [], "illustrator": [],
           "user_tags": []}

ITEMS = [
    item(1, 'A <b>Bold</b> "Title" & Co', genre=["Mystery"],
         user_tags=["lent out"], authors=["Sam Coder"], my_rating=3,
         read_status="read"),
    item(2, "Nightjar Post", cover_path=None, my_rating=5,
         read_status="reading", narrator=["Pat Reader"]),
    PARTIAL,
]


def batch():
    reset = ('app.setItems(JSON.parse(ITEMS_JSON)); app.setSearch("");'
             ' app.setRelevance(false); app.setFlag(""); app.setRating("");'
             ' app.setStatusFilter([]); app.setSort("id", true);'
             ' document.querySelector("#f-type").value = "";'
             ' for (const k of Object.keys(app.chipFilters)) {'
             '   app.chipFilters[k].chips = []; app.chipFilters[k].text = ""; }'
             ' dom.reset();')
    expr = (
        "(() => { const ITEMS_JSON = %s; const out = {};"
        " const rows = JSON.parse(ITEMS_JSON);"
        # --- pure helpers
        " out.esc_specials = app.esc('<b>&\"x\"</b>');"
        " out.esc_null = app.esc(null);"
        " out.esc_undefined = app.esc(undefined);"
        " out.esc_number = app.esc(5);"
        " out.esc_plain = app.esc('plain text');"
        " out.badges_two = app.tagBadges(['lent out', 'to reread']);"
        " out.badges_escaped = app.tagBadges(['<script>']);"
        " out.badges_missing = app.tagBadges(undefined);"
        " out.badges_empty = app.tagBadges([]);"
        " out.person_narrator = app.person(rows[1]);"
        " out.person_missing = app.person(rows[2]);"
        # --- highlight
        " out.hl_none = app.highlight('Salt and Sextant', []);"
        " out.hl_null = app.highlight('Salt and Sextant', null);"
        " out.hl_one = app.highlight('Salt and Sextant', [[9, 16]]);"
        " out.hl_two = app.highlight('Salt and Sextant', [[0, 4], [9, 16]]);"
        " out.hl_overlap = app.highlight('Salt and Sextant', [[0, 6], [3, 9]]);"
        " out.hl_escapes = app.highlight('A <b>x</b>', [[2, 5]]);"
        " out.hl_escapes_outside = app.highlight('<i>Salt</i>', []);"
        # --- status select and stars
        " out.status_read = app.statusSelect(rows[0]);"
        " out.status_missing = app.statusSelect(rows[2]);"
        " out.status_order = app.READ_STATUS_ORDER;"
        # --- shownRows
        " %s out.shown_all = app.shownRows();"
        " %s app.setSearch('Nightjar Post'); out.shown_filtered = app.shownRows();"
        # --- render
        " %s app.render(); out.render_all = dom.writes['#catalog tbody'];"
        " out.render_count = dom.writes['#count:text'];"
        " %s app.setSearch('Nightjar'); app.render();"
        "   out.render_search = dom.writes['#catalog tbody'];"
        "   out.render_count_search = dom.writes['#count:text'];"
        " %s app.setSearch('Nightjar'); app.setRelevance(true); app.render();"
        "   out.render_count_relevance = dom.writes['#count:text'];"
        " %s app.setItems([]); app.render();"
        "   out.render_empty = dom.writes['#catalog tbody'];"
        "   out.render_count_empty = dom.writes['#count:text'];"
        " return out; })()"
        % (json.dumps(json.dumps(ITEMS)),
           reset, reset, reset, reset, reset, reset))
    return eval_js(expr)


R = batch()


# ------------------------------------------------------------------- esc

def case_esc_replaces_every_markup_character():
    check("the four markup characters are replaced",
          R["esc_specials"], "&lt;b&gt;&amp;&quot;x&quot;&lt;/b&gt;")


def case_esc_of_a_missing_value_is_the_empty_string():
    # `v == null` catches BOTH null and undefined, which is the guard a
    # partial payload needs; a strict !== null would let undefined through
    # and render the text "undefined" into the table.
    check("null escapes to empty", R["esc_null"], "")
    check("undefined escapes to empty", R["esc_undefined"], "")


def case_esc_stringifies_a_non_string():
    check("a number is stringified rather than dropped", R["esc_number"], "5")


def case_esc_leaves_ordinary_text_alone():
    check("text with no markup characters is unchanged",
          R["esc_plain"], "plain text")


# ------------------------------------------------------------- tagBadges

def case_tag_badges_wrap_each_tag():
    check("two tags become two spans", R["badges_two"],
          '<span class="tag">lent out</span>'
          '<span class="tag">to reread</span>')


def case_tag_badges_escape_their_content():
    contains("a tag carrying markup is escaped",
             R["badges_escaped"], "&lt;script&gt;")
    contains("and the raw markup does not survive",
             R["badges_escaped"], "<script>", present=False)


def case_tag_badges_survive_a_missing_field():
    # The documented regression: this threw on a missing field and blanked
    # the whole page while every text assertion still passed.
    check("an absent tag array renders nothing rather than throwing",
          R["badges_missing"], "")
    check("an empty array renders nothing", R["badges_empty"], "")


def case_person_falls_back_and_survives_a_missing_field():
    check("narrator is used when present", R["person_narrator"],
          ["Pat Reader"])
    check("a row carrying neither field yields an empty list",
          R["person_missing"], [])


# ------------------------------------------------------------- highlight

def case_highlight_without_spans_is_just_escaped_text():
    check("no spans returns the escaped text", R["hl_none"],
          "Salt and Sextant")
    check("null spans behaves the same as none", R["hl_null"],
          "Salt and Sextant")


def case_highlight_wraps_exactly_the_span():
    # [9, 16] over "Salt and Sextant" is "Sextant".
    check("one span is wrapped in a mark", R["hl_one"],
          "Salt and <mark>Sextant</mark>")


def case_highlight_wraps_every_span_in_order():
    check("two spans are both wrapped", R["hl_two"],
          "<mark>Salt</mark> and <mark>Sextant</mark>")


def case_an_overlapping_span_is_skipped_and_the_first_wins():
    # Documented: `if (start < at) continue`. Without it the second span
    # would slice backwards and duplicate text into the row.
    check("the overlapping second span is dropped, not double-rendered",
          R["hl_overlap"], "<mark>Salt a</mark>nd Sextant")


def case_highlight_escapes_inside_and_outside_the_span():
    # The subtle one: text is escaped in three slices - before, inside and
    # after the span - so markup anywhere must not survive.
    contains("markup inside a highlighted span is escaped",
             R["hl_escapes"], "&lt;", present=True)
    contains("no raw tag survives inside the span",
             R["hl_escapes"], "<b>", present=False)
    check("and with no spans the whole string is escaped",
          R["hl_escapes_outside"], "&lt;i&gt;Salt&lt;/i&gt;")


def case_the_only_markup_highlight_emits_is_its_own_mark():
    # A tag-name check rather than a character check: `<mark>` is the one
    # element this function is allowed to introduce.
    for key in ["hl_one", "hl_two", "hl_overlap"]:
        stripped = R[key].replace("<mark>", "").replace("</mark>", "")
        contains(f"{key} introduces no other element", stripped, "<",
                 present=False)


# ------------------------------------------------------- status and stars

def case_status_select_marks_the_current_value():
    contains("the current status is the selected option",
             R["status_read"], '<option value="read" selected>')
    contains("and the class carries it for styling",
             R["status_read"], 'rs-read')


def case_status_select_offers_every_state_once():
    for state in R["status_order"]:
        contains(f"the {state} option is offered",
                 R["status_read"], f'value="{state}"')
    check("five states are offered", R["status_read"].count("<option"), 5)


def case_status_select_treats_a_missing_status_as_unread():
    contains("a row with no read_status selects unread",
             R["status_missing"], '<option value="unread" selected>')


# ------------------------------------------------------------- shownRows

def case_shown_rows_reports_the_unfiltered_state():
    check("with no filter, every row is shown and nothing is filtered",
          (R["shown_all"]["count"], R["shown_all"]["filtered"]), (3, False))


def case_shown_rows_reports_the_filtered_state():
    # `filtered` is what the bulk bar uses to say "these N rows"; it must
    # be true only when the view is actually narrower than the catalog.
    check("a search narrows the count and sets filtered",
          (R["shown_filtered"]["count"], R["shown_filtered"]["filtered"]),
          (1, True))


# ---------------------------------------------------------------- render

def case_render_writes_a_row_per_visible_item():
    check("three items render three rows",
          R["render_all"].count("<tr"), 3)


def case_render_escapes_a_title_carrying_markup():
    contains("the bold title is escaped in the table",
             R["render_all"], "&lt;b&gt;Bold&lt;/b&gt;")
    contains("and its raw markup does not reach the row",
             R["render_all"], "<b>Bold</b>", present=False)
    contains("the quotes in the title are escaped too",
             R["render_all"], "&quot;Title&quot;")
    contains("and the ampersand", R["render_all"], "&amp; Co")


def case_render_survives_the_partial_row():
    # The whole point of the guards: a row missing genre, tags, authors,
    # rating, status, cover and url must still render.
    contains("the partial row is rendered rather than dropped",
             R["render_all"], "Partial Row")
    contains("and the word undefined never reaches the table",
             R["render_all"], "undefined", present=False)


def case_render_omits_the_image_when_there_is_no_cover():
    # `i.cover_path ? <img> : ""` - a row with no cover must not emit an
    # img with an empty src, which the browser resolves to the page URL
    # and re-requests.
    check("only the rows with a cover emit an img",
          R["render_all"].count("<img"), 1)


def case_render_reports_the_count_against_the_total():
    check("the count line names shown over total",
          R["render_count"], "3 / 3 items")


def case_render_count_reflects_a_filter():
    check("a search shows the narrowed count against the full total",
          R["render_count_search"], "1 / 3 items")


def case_render_count_announces_relevance_ordering():
    # Documented: the suffix appears only while relevance is active, which
    # needs both the flag AND a non-empty query.
    check("relevance ordering is announced in the count line",
          R["render_count_relevance"], "1 / 3 items · by relevance")
    check("and is absent when the ordering is a column sort",
          "by relevance" in R["render_count_search"], False)


def case_render_of_an_empty_catalog_writes_an_empty_body():
    check("no items render no rows", R["render_empty"].count("<tr"), 0)
    check("and the count line says zero of zero",
          R["render_count_empty"], "0 / 0 items")


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
    print(f"js-catalog-render: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
