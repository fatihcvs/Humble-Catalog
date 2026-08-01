"""Behavioural tests for the viewer's JavaScript.

These run the real functions from app.js (see js_harness.py). They exist
because the text assertions in test_webapp.py cannot catch a renderer
that throws -- which is how the whole page once went blank.
"""
import json
import re
from pathlib import Path

from humble_catalog import export
from tests.js_harness import eval_js, eval_js_error


def _item(**overrides):
    """A catalog item as /api/items serves it, with fields overridable."""
    item = {
        "id": 1, "name": "The Quiet Harbor: A Novel", "type": "ebook",
        "publisher": "Example Press", "cover_path": None, "my_rating": 4,
        "genre": ["Fantasy"], "series": None, "series_number": None,
        "authors": ["Sam Coder"], "narrator": [], "illustrator": [],
        "external_rating": None, "rating_source": None, "status": "matched",
        "source_url": None, "edited": False, "re_enriched": False,
        "override": False, "bundles": [], "formats": [],
        "user_tags": [], "user_comment": None, "read_status": "unread",
    }
    item.update(overrides)
    return item


def test_tag_badges_survives_a_missing_array():
    # an older server, or any partial payload, omits the field entirely
    assert eval_js_error("app.tagBadges(undefined)") is None
    assert eval_js("app.tagBadges(undefined)") == ""
    assert eval_js("app.tagBadges(null)") == ""


def test_person_survives_a_missing_name_field():
    # same shape of bug as tagBadges, one function along: person() reads
    # .length off narrator before anything has checked it exists
    item = json.dumps(_item(narrator=None, illustrator=None))
    assert eval_js_error(f"app.person({item})") is None
    assert eval_js(f"app.person({item})") == []


def test_person_still_prefers_narrator_then_illustrator():
    narrated = json.dumps(_item(narrator=["Sam Reader"], illustrator=["Ann Art"]))
    drawn = json.dumps(_item(narrator=[], illustrator=["Ann Art"]))
    assert eval_js(f"app.person({narrated})") == ["Sam Reader"]
    assert eval_js(f"app.person({drawn})") == ["Ann Art"]


def test_load_renders_every_panel_even_when_one_renderer_throws():
    # bundles is deliberately absent, so render() throws deep inside the
    # row template. The review, duplicates and genre panels are unrelated
    # to that failure and must still be rendered.
    broken = json.dumps([_item(bundles=None)])
    result = eval_js(
        """(async () => {
             dom.reset();
             app.setFetch((url) => Promise.resolve({json: () => Promise.resolve(
               url === "/api/items"      ? {items: %s} :
               url === "/api/review"     ? {items: []} :
               url === "/api/duplicates" ? {groups: []} :
               url === "/api/stats"      ? {total: 1, sections: []} : {})}));
             let threw = null;
             try { await app.load(); } catch (e) { threw = e.message; }
             return {threw, wrote: Object.keys(dom.writes).sort()};
           })()""" % broken)
    # load() itself must not propagate the failure...
    assert result["threw"] is None
    # ...and the panels a broken row cannot affect must still be written
    assert "#dupes-panel" in result["wrote"]
    assert "#stats-panel" in result["wrote"]


def test_load_survives_a_duplicates_payload_without_groups():
    # loadDupes assigned the payload field straight into dupeGroups, so a
    # response without `groups` replaced the safe [] with undefined. The
    # throw inside renderDupes() is contained by load()'s loop -- but the
    # badge arithmetic after the loop is not, and it reads dupeGroups
    # too, so load() threw anyway from wherever it had been called.
    # loadKeys already had the answer: `data.rows || []`.
    result = eval_js(
        """(async () => {
             app.setFetch((url) => Promise.resolve({json: () => Promise.resolve(
               url === "/api/items"      ? {items: []} :
               url === "/api/review"     ? {items: []} :
               url === "/api/duplicates" ? {} :
               url === "/api/stats"      ? {total: 0, sections: []} : {})}));
             let threw = null;
             try { await app.load(); } catch (e) { threw = e.message; }
             return {threw, maintenance: app.getPending().maintenance};
           })()""")
    assert result["threw"] is None
    # and the badge is a number rather than NaN or a crash
    assert result["maintenance"] == 0


def test_review_panel_collapses_with_a_count_summary():
    # The panel body must be a <details> so it collapses, and the summary
    # must carry the count so a collapsed panel still signals pending work.
    review = json.dumps([
        {"id": 1, "name": "The Quiet Harbor: A Novel", "type": "ebook",
         "status": "low_confidence", "cover_path": None, "candidates": []}])
    html = eval_js(
        """(async () => {
             dom.reset();
             app.setFetch((url) => Promise.resolve({json: () => Promise.resolve(
               url === "/api/review" ? {items: %s} : {items: []})}));
             await app.loadReview();
             return dom.writes["#review-panel"];
           })()""" % review)
    assert "<details" in html
    assert "<summary" in html
    assert "1 item" in html


def _matches(comment, query, **extra):
    """Does an item with this note pass the filters when Notes is set?"""
    item = json.dumps(_item(user_comment=comment, **extra))
    return eval_js(
        """(() => {
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.chipFilters.user_comment.text = %s;
             return app.passesChipFilters(%s);
           })()""" % (json.dumps(query), item))


def test_notes_filter_matches_a_substring_of_the_note():
    assert _matches("Gift from Sam.", "gift") is True
    assert _matches("Gift from Sam.", "borrowed") is False


def test_notes_filter_ignores_the_note_s_case():
    # The matcher lowercases the note but not the query: both places that
    # write f.text lowercase it first, so by the time it arrives here it is
    # already lowercase. Passing "REREAD" would test a state the UI cannot
    # produce, so the case difference belongs on the note side.
    assert _matches("REREAD Before The Sequel.", "reread") is True
    assert _matches("Reread before the sequel.", "sequel") is True


def test_notes_filter_never_matches_an_item_without_a_note():
    assert _matches(None, "gift") is False
    assert _matches("", "gift") is False


def test_notes_filter_empty_query_matches_everything():
    # including items that have no note at all
    assert _matches(None, "") is True
    assert _matches("Gift from Sam.", "") is True


def test_notes_filter_ands_with_a_user_tag_chip():
    item = json.dumps(_item(user_comment="Gift from Sam.",
                            user_tags=["to reread"]))
    result = eval_js(
        """(() => {
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.chipFilters.user_comment.text = "gift";
             const item = %s;
             const before = app.passesChipFilters(item);
             app.chipFilters.user_tags.chips = ["lent out"];
             return {before, afterNonMatchingChip: app.passesChipFilters(item)};
           })()""" % item)
    assert result["before"] is True
    # a non-matching tag chip must exclude the row: fields AND together
    assert result["afterNonMatchingChip"] is False


def _sorted_names(catalog, key, asc=True):
    """Names in the order visible() yields for the given sort."""
    return eval_js(
        """(() => {
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.setSort(%s, %s);
             return app.visible().map(i => i.name);
           })()""" % (json.dumps(catalog), json.dumps(key),
                      "true" if asc else "false"))


def test_sort_by_bundle_uses_the_bundle_name_not_the_object():
    # item.bundle does not exist; sorting must derive the name from bundles[].
    catalog = [
        {**_item(id=1, name="Beta"), "bundles": [{"name": "Zephyr Bundle", "url": ""}]},
        {**_item(id=2, name="Alpha"), "bundles": [{"name": "Alpine Bundle", "url": ""}]},
    ]
    assert _sorted_names(catalog, "bundle", asc=True) == ["Alpha", "Beta"]
    assert _sorted_names(catalog, "bundle", asc=False) == ["Beta", "Alpha"]


def test_status_sort_follows_the_reading_lifecycle_not_the_alphabet():
    # Alphabetical would be dnf < read < reading < unread < want_to_read;
    # lifecycle order is want_to_read < unread < reading < read < dnf.
    catalog = [
        _item(id=1, name="All Systems Red", read_status="dnf"),
        _item(id=2, name="Unrelated Book", read_status="want_to_read"),
        _item(id=3, name="The Quiet Harbor: A Novel", read_status="reading"),
        _item(id=4, name="Cafe of Broken Clocks", read_status="unread"),
        _item(id=5, name="Wings of Autumn Dusk (Book 1)", read_status="read"),
    ]
    assert _sorted_names(catalog, "read_status", asc=True) == [
        "Unrelated Book",                 # want_to_read
        "Cafe of Broken Clocks",          # unread
        "The Quiet Harbor: A Novel",      # reading
        "Wings of Autumn Dusk (Book 1)",  # read
        "All Systems Red",                # dnf
    ]


def test_sort_by_narrator_follows_the_column_including_illustrator():
    # The column shows narrator‖illustrator; a comic with only an illustrator
    # must still sort under that name, not fall through to empty.
    catalog = [
        {**_item(id=1, name="Narrated"), "narrator": ["Sam Reader"], "illustrator": []},
        {**_item(id=2, name="Drawn", type="comic"), "narrator": [], "illustrator": ["Ann Art"]},
    ]
    # "Ann Art" < "Sam Reader", so the illustrator-only comic sorts first.
    assert _sorted_names(catalog, "narrator", asc=True) == ["Drawn", "Narrated"]


def _bulk_state(n_items, filter_text):
    """shownRows() with n_items in the catalog and an optional note filter."""
    catalog = json.dumps([
        _item(id=i, name=f"Item {i}", user_comment="keep" if i == 1 else None)
        for i in range(1, n_items + 1)])
    return eval_js(
        """(() => {
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.chipFilters.user_comment.text = %s;
             return app.shownRows();
           })()""" % (catalog, json.dumps(filter_text)))


def test_bulk_target_is_everything_when_unfiltered():
    state = _bulk_state(3, "")
    assert state["count"] == 3
    assert state["ids"] == [1, 2, 3]
    # not narrowed: removal must stay unavailable
    assert state["filtered"] is False


def test_bulk_target_follows_the_filter():
    state = _bulk_state(3, "keep")
    assert state["count"] == 1
    assert state["ids"] == [1]
    assert state["filtered"] is True


def test_bulk_target_is_empty_when_nothing_matches():
    state = _bulk_state(3, "nothing matches this")
    assert state["count"] == 0
    assert state["ids"] == []
    assert state["filtered"] is True


def test_search_now_finds_a_title_with_the_words_in_the_wrong_order():
    items = json.dumps([_item(id=1, name="The Quiet Harbor: A Novel")])
    found = eval_js(
        f"""(() => {{
              app.setItems({items});
              app.setSearch("harbor quiet");
              return app.visible().map(i => i.id);
            }})()""")
    assert found == [1]


def test_search_still_rejects_an_unrelated_query():
    items = json.dumps([_item(id=1, name="The Quiet Harbor: A Novel")])
    found = eval_js(
        f"""(() => {{
              app.setItems({items});
              app.setSearch("axebearer");
              return app.visible().map(i => i.id);
            }})()""")
    assert found == []


def test_an_empty_search_records_no_match_spans():
    items = json.dumps([_item(id=1, name="The Quiet Harbor: A Novel")])
    spans = eval_js(
        f"""(() => {{
              app.setItems({items});
              app.setSearch("");
              app.visible();
              return app.getMatchSpans().size;
            }})()""")
    assert spans == 0


def test_search_does_not_reach_into_notes_or_other_fields():
    # v1.12 narrowed the box to names; fuzzy matching must not widen it.
    # The comment is a verbatim match for the query and the name is not.
    items = json.dumps([_item(id=1, name="The Quiet Harbor: A Novel",
                              user_comment="lent to Sam Reader")])
    found = eval_js(
        f"""(() => {{
              app.setItems({items});
              app.setSearch("lent to Sam Reader");
              return app.visible().map(i => i.id);
            }})()""")
    assert found == []


def test_relevance_puts_the_exact_match_above_the_fuzzy_one():
    # sorted by name, "A Quiet Life in Harbors" would come first; by
    # relevance the verbatim match must win
    items = json.dumps([
        _item(id=1, name="A Quiet Life in Harbors"),
        _item(id=2, name="The Quiet Harbor: A Novel"),
    ])
    order = eval_js(
        f"""(() => {{
              app.setItems({items});
              app.setSort("name", true);
              app.setRelevance(true);
              app.setSearch("quiet harbor");
              return app.visible().map(i => i.id);
            }})()""")
    assert order == [2, 1]


def test_a_column_sort_overrides_relevance():
    items = json.dumps([
        _item(id=1, name="A Quiet Life in Harbors"),
        _item(id=2, name="The Quiet Harbor: A Novel"),
    ])
    order = eval_js(
        f"""(() => {{
              app.setItems({items});
              app.setSort("name", true);
              app.setRelevance(false);
              app.setSearch("quiet harbor");
              return app.visible().map(i => i.id);
            }})()""")
    assert order == [1, 2]


def test_an_empty_query_leaves_the_column_sort_alone():
    items = json.dumps([
        _item(id=2, name="The Quiet Harbor: A Novel"),
        _item(id=1, name="A Quiet Life in Harbors"),
    ])
    order = eval_js(
        f"""(() => {{
              app.setItems({items});
              app.setSort("name", true);
              app.setRelevance(true);
              app.setSearch("");
              return app.visible().map(i => i.id);
            }})()""")
    assert order == [1, 2]


def test_highlight_wraps_only_the_matched_range():
    assert eval_js('app.highlight("The Quiet Harbor", [[4, 9]])') \
        == "The <mark>Quiet</mark> Harbor"


def test_highlight_without_spans_is_plain_escaping():
    assert eval_js('app.highlight("Tom & Jerry <b>", [])') \
        == eval_js('app.esc("Tom & Jerry <b>")')
    assert eval_js('app.highlight("Tom & Jerry <b>", null)') \
        == eval_js('app.esc("Tom & Jerry <b>")')


def test_highlight_escapes_around_and_inside_a_mark():
    # the tempting implementation escapes first and matches second, which
    # displaces every span past an "&" and can split an entity in half
    assert eval_js('app.highlight("A & B <i>", [[4, 5]])') \
        == "A &amp; <mark>B</mark> &lt;i&gt;"


def test_highlight_ignores_a_span_that_overlaps_the_previous_one():
    assert eval_js('app.highlight("abcdef", [[0, 3], [1, 4]])') \
        == "<mark>abc</mark>def"


def _flagged(catalog, flag):
    """The ids visible() yields under the given #f-flag value."""
    return eval_js(
        """(() => {
             app.setItems(%s);
             app.setFlag(%s);
             return app.visible().map(i => i.id);
           })()""" % (json.dumps(catalog), json.dumps(flag)))


def test_no_flag_shows_annotated_and_un_annotated_items_alike():
    # the baseline the two flags narrow: neither reorders or drops rows
    catalog = [_item(id=1, name="The Quiet Harbor: A Novel",
                     user_comment="lent to Sam Reader", user_tags=["lent out"]),
               _item(id=2, name="Unrelated Book")]
    assert _flagged(catalog, "") == [1, 2]


def test_has_notes_keeps_only_the_commented_item():
    catalog = [_item(id=1, name="The Quiet Harbor: A Novel",
                     user_comment="lent to Sam Reader"),
               _item(id=2, name="Unrelated Book", user_comment=None)]
    assert _flagged(catalog, "notes") == [1]


def test_a_whitespace_only_comment_is_not_a_note():
    # saving an empty box can leave "" or "   " behind; neither is a note
    catalog = [_item(id=1, name="The Quiet Harbor: A Novel", user_comment="   "),
               _item(id=2, name="Unrelated Book", user_comment="")]
    assert _flagged(catalog, "notes") == []


def test_has_my_tags_keeps_only_the_tagged_item():
    catalog = [_item(id=1, name="The Quiet Harbor: A Novel", user_tags=["lent out"]),
               _item(id=2, name="Unrelated Book", user_tags=[])]
    assert _flagged(catalog, "mytags") == [1]


def test_no_cover_flag_keeps_only_the_coverless_item():
    catalog = [_item(id=1, cover_path=None),
               _item(id=2, cover_path="covers/2.jpg")]
    assert _flagged(catalog, "nocover") == [1]


def test_no_cover_flag_treats_an_empty_string_as_missing():
    catalog = [_item(id=1, cover_path=""),
               _item(id=2, cover_path="covers/2.jpg")]
    assert _flagged(catalog, "nocover") == [1]


def test_no_source_url_flag_keeps_only_the_linkless_item():
    catalog = [_item(id=1, source_url=None),
               _item(id=2, source_url="http://example.test/2")]
    assert _flagged(catalog, "nourl") == [1]


def test_the_annotation_flags_survive_a_missing_field():
    # same shape of bug as tagBadges: an older server omits the field, and
    # reading .length or .trim() off undefined blanks the whole page
    catalog = [_item(id=1, name="Unrelated Book")]
    del catalog[0]["user_tags"]
    del catalog[0]["user_comment"]
    assert _flagged(catalog, "notes") == []
    assert _flagged(catalog, "mytags") == []


def _rendered(item):
    """The table body app.js renders for a single item."""
    return eval_js(
        """(() => {
             dom.reset();
             app.setItems([%s]);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.setFlag("");
             app.render();
             return dom.writes["#catalog tbody"];
           })()""" % json.dumps(item))


def test_override_filter_keeps_only_queued_rows():
    queued = json.dumps(_item(id=1, edited=True, override=True))
    plain = json.dumps(_item(id=2, edited=True, override=False))
    assert eval_js(
        """(() => {
             app.setItems([%s, %s]);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.setFlag("override");
             return app.visible().map(i => i.id);
           })()""" % (queued, plain)) == [1]


def test_queued_row_renders_its_badge():
    assert "re-enrich queued" in _rendered(_item(edited=True, override=True))


def test_re_enriched_row_renders_a_revert_button_not_an_edited_badge():
    html = _rendered(_item(edited=False, re_enriched=True))
    assert "re-enriched" in html and "revert" in html
    assert "badge edited" not in html


def _export_button(n_items, filter_text):
    """#export's label and disabled state after renderExportButton()."""
    catalog = json.dumps([
        _item(id=i, name=f"Item {i}", user_comment="keep" if i == 1 else None)
        for i in range(1, n_items + 1)])
    return eval_js(
        """(() => {
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.chipFilters.user_comment.text = %s;
             app.renderExportButton();
             return {label: dom.writes["#export:text"],
                     disabled: document.querySelector("#export").disabled};
           })()""" % (catalog, json.dumps(filter_text)))


def test_export_button_says_download_all_when_unfiltered():
    # The format moved to the select, so the label states only what rows.
    # Unfiltered IS the whole catalog, which is what "all" reports.
    state = _export_button(3, "")
    assert state["label"] == "Download all"
    assert state["disabled"] is False


def test_export_button_shows_the_row_count_when_filtered():
    # the label doubles as the blast-radius readout, like the bulk bar
    state = _export_button(3, "keep")
    assert state["label"] == "Download 1 shown"
    assert state["disabled"] is False


def test_export_button_is_disabled_with_nothing_to_export():
    # a header-only file would look like a bug
    state = _export_button(3, "nothing matches this")
    assert state["disabled"] is True


def test_download_export_posts_visible_ids_in_screen_order():
    # Relevance ordering is part of what the viewer shows, so it must be
    # what gets posted -- not the catalog's title order.
    catalog = json.dumps([
        _item(id=1, name="A Quiet Life in Harbors"),
        _item(id=2, name="The Quiet Harbor: A Novel"),
        _item(id=3, name="Unrelated Book"),
    ])
    sent = eval_js(
        """(async () => {
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.setSearch("quiet harbor");
             app.setRelevance(true);
             let body = null;
             app.setFetch((url, opts) => {
               body = JSON.parse(opts.body);
               return Promise.resolve({ok: true, blob: () => ({})});
             });
             await app.downloadExport();
             return {body, order: app.visible().map(i => i.id)};
           })()""" % catalog)
    # the exact ranking is fuzzy.js's business; that the two agree is ours
    assert sent["body"]["ids"] == sent["order"]
    # and the closer title outranks the looser one, so this is a real order
    assert sent["body"]["ids"][0] == 2


def test_download_export_sends_nothing_when_no_rows_are_visible():
    called = eval_js(
        """(async () => {
             app.setItems([]);
             let calls = 0;
             app.setFetch(() => { calls += 1;
               return Promise.resolve({ok: true, blob: () => ({})}); });
             await app.downloadExport();
             return calls;
           })()""")
    assert called == 0


def _download_target(fmt, filter_text=""):
    """The URL posted and the filename set, for a given format select."""
    catalog = json.dumps([
        _item(id=i, name=f"Item {i}", user_comment="keep" if i == 1 else None)
        for i in range(1, 4)])
    return eval_js(
        """(async () => {
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.chipFilters.user_comment.text = %s;
             app.setExportFormat(%s);
             let url = null, anchor = null;
             const create = document.createElement;
             document.createElement = (t) => (anchor = create(t));
             app.setFetch((u) => { url = u;
               return Promise.resolve({ok: true, blob: () => ({})}); });
             await app.downloadExport();
             document.createElement = create;
             return {url, name: anchor.download};
           })()""" % (catalog, json.dumps(filter_text), json.dumps(fmt)))


def test_the_select_picks_the_route_and_the_extension():
    sent = _download_target("xlsx")
    assert sent["url"] == "/api/export.xlsx"
    assert sent["name"] == "catalog.xlsx"


def test_csv_stays_the_other_option():
    sent = _download_target("csv")
    assert sent["url"] == "/api/export.csv"
    assert sent["name"] == "catalog.csv"


def test_a_filtered_export_gets_its_own_filename_in_either_format():
    # A filtered export is a different artifact and must not silently
    # overwrite the full one in the downloads folder.
    assert _download_target("xlsx", "keep")["name"] == "catalog-filtered.xlsx"
    assert _download_target("csv", "keep")["name"] == "catalog-filtered.csv"


def test_export_columns_start_as_everything():
    assert eval_js("app.getExportColumns()") == list(export.COLUMNS)


def test_toggling_a_column_removes_it_from_the_payload():
    sent = eval_js(
        """(async () => {
             app.setItems([%s]);
             let body = null;
             app.setFetch((url, opts) => {
               body = JSON.parse(opts.body);
               return Promise.resolve({ok: true, blob: () => ({})});
             });
             app.toggleColumn("publisher", false);
             await app.downloadExport();
             return body;
           })()""" % json.dumps(_item(id=1, name="A Quiet Life in Harbors")))
    assert "publisher" not in sent["columns"]
    assert "title" in sent["columns"]


def test_a_column_only_narrowing_still_gets_the_filtered_filename():
    # The filter-aware spec pinned `filtered` to "fewer rows"; a partial
    # export must not silently overwrite catalog.csv whichever axis
    # narrowed it.
    name = eval_js(
        """(async () => {
             app.setItems([%s]);
             app.setFetch(() => Promise.resolve({ok: true, blob: () => ({})}));
             app.toggleColumn("publisher", false);
             const create = document.createElement;
             let anchor = null;
             document.createElement = () => (anchor = create());
             await app.downloadExport();
             document.createElement = create;
             return anchor.download;
           })()""" % json.dumps(_item(id=1, name="A Quiet Life in Harbors")))
    assert name == "catalog-filtered.csv"


def test_zero_columns_disables_the_export_button():
    disabled = eval_js(
        """(async () => {
             app.setItems([%s]);
             app.setExportColumns([]);
             app.renderExportButton();
             return document.querySelector("#export").disabled;
           })()""" % json.dumps(_item(id=1, name="A Quiet Life in Harbors")))
    assert disabled is True


def test_a_stored_selection_is_restored():
    cols = eval_js(
        """(async () => {
             app.setStored("hc-export-columns",
                           JSON.stringify(["title", "authors"]));
             app.loadColumnSelection();
             return app.getExportColumns();
           })()""")
    assert cols == ["title", "authors"]


def test_a_stored_name_that_no_longer_exists_is_dropped():
    cols = eval_js(
        """(async () => {
             app.setStored("hc-export-columns",
                           JSON.stringify(["title", "gone_column"]));
             app.loadColumnSelection();
             return app.getExportColumns();
           })()""")
    assert cols == ["title"]


def test_unparseable_stored_state_means_every_column():
    cols = eval_js(
        """(async () => {
             app.setStored("hc-export-columns", "{not json");
             app.loadColumnSelection();
             return app.getExportColumns();
           })()""")
    assert cols == list(export.COLUMNS)


def test_app_js_column_list_matches_the_exporter():
    # COLUMNS now exists twice, once per language. Duplicated constants
    # across a language boundary are fine; unpinned ones are not.
    from tests.js_harness import VIEWER_JS
    src = "\n".join(p.read_text(encoding="utf-8") for p in VIEWER_JS)
    listed = re.search(r"const EXPORT_COLUMNS = \[(.*?)\];", src, re.S).group(1)
    assert re.findall(r'"([a-z_]+)"', listed) == list(export.COLUMNS)


def test_the_picker_renders_one_checkbox_per_column():
    html = eval_js(
        """(async () => {
             app.renderColumnPicker();
             return dom.writes["#column-picker-body"];
           })()""")
    for name in export.COLUMNS:
        assert f'data-col="{name}"' in html
    assert html.count("checkbox") == len(export.COLUMNS)


def test_the_summary_counts_the_selection():
    text = eval_js(
        """(async () => {
             app.setExportColumns(%s);
             app.renderColumnPicker();
             return dom.writes["#column-picker-summary:text"];
           })()""" % json.dumps(list(export.COLUMNS)[:3]))
    assert text == "Columns (3/%d)" % len(export.COLUMNS)


def test_an_unselected_column_renders_unchecked():
    html = eval_js(
        """(async () => {
             app.toggleColumn("publisher", false);
             app.renderColumnPicker();
             return dom.writes["#column-picker-body"];
           })()""")
    checked = [line for line in html.split("<label") if "publisher" in line]
    assert checked and "checked" not in checked[0]


def test_toggling_does_not_rebuild_the_checkbox_list():
    # Rebuilding detaches the checkbox that was just clicked, and the
    # outside-click handler then measures contains() against a node no
    # longer in the document and closes the panel mid-click. The user's
    # own click already put the box in the right state, so the only thing
    # that needs redrawing is the count.
    rebuilt = eval_js(
        """(async () => {
             app.renderColumnPicker();
             dom.reset();
             app.toggleColumn("publisher", false);
             return {body: dom.writes["#column-picker-body"] ?? null,
                     summary: dom.writes["#column-picker-summary:text"]};
           })()""")
    assert rebuilt["body"] is None       # the list is left alone
    # one column toggled off from the full set: the count is redrawn
    assert rebuilt["summary"].startswith(
        "Columns (%d/" % (len(export.COLUMNS) - 1))


def test_status_select_marks_the_current_status_selected():
    item = json.dumps(_item(id=7, read_status="reading"))
    html = eval_js(f"app.statusSelect({item})")
    assert 'value="reading" selected' in html
    assert "read-status-select" in html
    assert "rs-reading" in html
    for key in ("want_to_read", "unread", "reading", "read", "dnf"):
        assert f'value="{key}"' in html


def test_status_select_defaults_a_missing_status_to_unread():
    item = json.dumps(_item(id=8))
    html = eval_js(
        "(() => { const i = %s; delete i.read_status; return app.statusSelect(i); })()"
        % item)
    assert 'value="unread" selected' in html


def _status_filtered(catalog, statuses):
    """The ids visible() yields with the given status chips ticked."""
    return eval_js(
        """(() => {
             app.setItems(%s);
             app.setStatusFilter(%s);
             return app.visible().map(i => i.id);
           })()""" % (json.dumps(catalog), json.dumps(statuses)))


def test_no_status_chips_shows_every_item():
    catalog = [_item(id=1, read_status="reading"),
               _item(id=2, read_status="unread")]
    assert _status_filtered(catalog, []) == [1, 2]


def test_status_filter_keeps_any_of_the_ticked_states():
    catalog = [_item(id=1, name="All Systems Red", read_status="reading"),
               _item(id=2, name="Unrelated Book", read_status="want_to_read"),
               _item(id=3, name="The Quiet Harbor: A Novel", read_status="read")]
    assert _status_filtered(catalog, ["reading", "want_to_read"]) == [1, 2]


def test_status_filter_treats_a_missing_status_as_unread():
    del_missing = eval_js(
        """(() => {
             const i = %s; delete i.read_status;
             app.setItems([i]); app.setStatusFilter(["unread"]);
             return app.visible().map(x => x.id);
           })()""" % json.dumps(_item(id=1, name="All Systems Red")))
    assert del_missing == [1]


def _rated(catalog, rating):
    """The ids visible() yields under the given #f-rating value."""
    return eval_js(
        """(() => {
             app.setItems(%s);
             app.setRating(%s);
             return app.visible().map(i => i.id);
           })()""" % (json.dumps(catalog), json.dumps(rating)))


def test_rating_filter_keeps_only_that_rating():
    catalog = [_item(id=1, my_rating=5), _item(id=2, my_rating=3),
               _item(id=3, my_rating=None)]
    assert _rated(catalog, "5") == [1]


def test_empty_rating_filter_keeps_everything():
    catalog = [_item(id=1, my_rating=5), _item(id=2, my_rating=None)]
    assert _rated(catalog, "") == [1, 2]


def test_matched_flag_keeps_only_matched_items():
    catalog = [_item(id=1, status="matched"), _item(id=2, status="pending")]
    assert _flagged(catalog, "matched") == [1]


def test_pending_flag_keeps_only_pending_items():
    catalog = [_item(id=1, status="matched"), _item(id=2, status="pending")]
    assert _flagged(catalog, "pending") == [2]


def test_each_enrichment_state_has_a_flag_of_its_own():
    # caught in the browser: the panel offered a row reading "Unmatched 4"
    # that jumped to #f-flag=review, which spans low_confidence too and so
    # showed 8. A row's count must be what the jump actually yields.
    catalog = [_item(id=1, status="low_confidence"),
               _item(id=2, status="unmatched")]
    assert _flagged(catalog, "low_confidence") == [1]
    assert _flagged(catalog, "unmatched") == [2]
    # the union flag stays: "what needs my attention" is its own question
    assert _flagged(catalog, "review") == [1, 2]


def _stats_payload(sections, total=3):
    return {"total": total, "sections": sections}


def _section(key, label, rows):
    return {"key": key, "label": label,
            "rows": [{"label": l, "count": n} for l, n in rows]}


def _render_stats(payload):
    """The #stats-panel HTML for a given /api/stats body."""
    return eval_js(
        """(async () => {
             app.setFetch(() => Promise.resolve(
               {json: () => Promise.resolve(%s)}));
             await app.refreshStats();
             return dom.writes["#stats-panel"];
           })()""" % json.dumps(payload))


def test_stats_panel_renders_every_section_with_its_label():
    html = _render_stats(_stats_payload([
        _section("type", "By type", [("E-books", 2)]),
        _section("rating", "Ratings", [("★5", 1)]),
        _section("status", "Reading status", [("Unread", 3)]),
        _section("enrichment", "Enrichment", [("Matched", 2)]),
        _section("gaps", "Gaps", [("No cover", 1)]),
        _section("genre", "Genres", [("Fantasy", 2)]),
    ]))
    assert "<details" in html            # collapsible, like the other panels
    for label in ("By type", "Ratings", "Reading status",
                  "Enrichment", "Gaps", "Genres"):
        assert label in html
    assert "E-books" in html and "Fantasy" in html


def test_stats_rows_carry_their_section_key_and_value():
    html = _render_stats(_stats_payload([
        _section("gaps", "Gaps", [("No cover", 4)]),
    ]))
    # the jump control names the section, so the click handler knows which
    # filter to apply, and the row, so it knows which value
    assert 'data-section="gaps"' in html
    assert 'data-row="No cover"' in html


def test_a_zero_row_is_not_clickable():
    html = _render_stats(_stats_payload([
        _section("gaps", "Gaps", [("No cover", 0)]),
    ]))
    assert "stat-zero" in html
    assert 'data-section="gaps"' not in html


def test_genre_section_shows_fifteen_rows_until_show_all():
    rows = [(f"Genre {i:02d}", 20 - i) for i in range(20)]
    payload = _stats_payload([_section("genre", "Genres", rows)])

    collapsed = _render_stats(payload)
    assert "Genre 14" in collapsed
    assert "Genre 15" not in collapsed
    assert "Show all 20" in collapsed

    expanded = eval_js(
        """(async () => {
             app.setFetch(() => Promise.resolve(
               {json: () => Promise.resolve(%s)}));
             await app.refreshStats();
             app.setGenresShowAll(true);
             app.renderStats();
             return dom.writes["#stats-panel"];
           })()""" % json.dumps(payload))
    assert "Genre 19" in expanded


def test_edit_tags_toggle_reveals_the_rename_controls():
    payload = _stats_payload([_section("genre", "Genres", [("Fantasy", 2)])])
    plain = _render_stats(payload)
    assert "genre-rename" not in plain      # read-only by default

    editing = eval_js(
        """(async () => {
             app.setFetch(() => Promise.resolve(
               {json: () => Promise.resolve(%s)}));
             await app.refreshStats();
             app.setTagEditMode(true);
             app.renderStats();
             return dom.writes["#stats-panel"];
           })()""" % json.dumps(payload))
    assert "genre-rename" in editing
    assert "genre-delete" in editing


def test_render_stats_before_any_fetch_draws_nothing():
    # renderStats is re-run on a toggle, so it must cope with no data yet
    # rather than throwing and blanking the panel
    assert eval_js_error("app.renderStats()") is None


_BUNDLE_REPORT = {
    "name": "Humble Book Bundle: The World of Examplia",
    "url": "https://www.humblebundle.com/books/the-world-of-examplia-books",
    "currency": "EUR",
    "tiers": [
        {"price": 21.9, "total": 6, "owned": 2, "new": 4,
         "adds": ["Moonfall Vol. 1-3", "The Hollow Crypt", "Unrelated Book"]},
        {"price": 13.13, "total": 3, "owned": 2, "new": 1,
         "adds": ["Shadow Hound Vol. 1-6"]},
        {"price": 5.47, "total": 1, "owned": 1, "new": 0, "adds": []},
    ],
    "overlaps": [
        {"offered": "Shadow Hound Vol. 1-6", "item_id": 2,
         "item_name": "Shadow Hound Vol 1", "score": 0.92},
    ],
}


def _render_bundle(report):
    """The #bundle-panel HTML for a given /api/bundle-preview body."""
    return eval_js(
        """(async () => {
             app.setFetch(() => Promise.resolve(
               {ok: true, json: () => Promise.resolve(%s)}));
             await app.previewBundle("https://www.humblebundle.com/books/x");
             return dom.writes["#bundle-panel"];
           })()""" % json.dumps(report))


def test_bundle_panel_renders_a_row_per_tier_highest_first():
    html = _render_bundle(_BUNDLE_REPORT)
    assert html.index("21.90") < html.index("13.13") < html.index("5.47")
    assert "Humble Book Bundle: The World of Examplia" in html


def test_bundle_panel_shows_owned_and_new_counts():
    html = _render_bundle(_BUNDLE_REPORT)
    assert ">2<" in html and ">4<" in html


def test_bundle_panel_never_shows_a_price_per_new_item():
    html = _render_bundle(_BUNDLE_REPORT)
    assert "/new" not in html and "per item" not in html


def test_bundle_panel_links_each_overlap_to_the_owned_row():
    # The one thing the CLI cannot offer: "you may own part of this"
    # becomes one click to WHICH part.
    html = _render_bundle(_BUNDLE_REPORT)
    assert 'data-item="2"' in html
    assert "Shadow Hound Vol 1" in html
    assert "Shadow Hound Vol. 1-6" in html


def test_bundle_panel_omits_the_overlap_block_when_there_is_none():
    report = dict(_BUNDLE_REPORT, overlaps=[])
    assert "Possibly already owned" not in _render_bundle(report)


_KEYED_REPORT = {
    "name": "Humble Game Bundle: Story Sampler",
    "url": "https://www.humblebundle.com/games/story-sampler",
    "currency": "EUR",
    "tiers": [
        {"price": 7.5, "total": 2, "owned": 2, "new": 0, "adds": [],
         "keyed": 1, "keyed_items": [
             {"offered": "Cinder Vale", "owned_title": "Cinder Vale",
              "score": 1.0, "key_type": "steam",
              "bundle": "Humble Game Bundle: Key Vault"}]},
    ],
    "overlaps": [],
}


def test_bundle_panel_lists_a_game_owned_only_via_a_key():
    # Counted in `owned` on the row above, named here: the panel must not
    # let an unactivated key pass as a library match.
    html = _render_bundle(_KEYED_REPORT)
    assert "Cinder Vale" in html
    assert "owned via a Humble key (not in any imported library)" in html
    assert "steam" in html
    assert "Humble Game Bundle: Key Vault" in html


def test_bundle_panel_omits_the_keyed_block_when_nothing_is_keyed():
    assert "Humble key" not in _render_bundle(_BUNDLE_REPORT)


def test_bundle_panel_survives_a_tier_with_no_keyed_field():
    # _BUNDLE_REPORT carries no keyed_items at all, which is exactly what a
    # response from an older server looks like. Throwing here would blank
    # the whole panel, the failure mode js_harness exists to catch.
    assert eval_js_error(
        """(async () => {
             app.setFetch(() => Promise.resolve(
               {ok: true, json: () => Promise.resolve(%s)}));
             await app.previewBundle("https://www.humblebundle.com/books/x");
           })()""" % json.dumps(_BUNDLE_REPORT)) is None


def test_bundle_panel_shows_the_error_from_a_rejected_url():
    html = eval_js(
        """(async () => {
             app.setFetch(() => Promise.resolve(
               {ok: false, json: () => Promise.resolve(
                 {error: "not a HumbleBundle URL: example.test"})}));
             await app.previewBundle("https://example.test/x");
             return dom.writes["#bundle-panel"];
           })()""")
    assert "not a HumbleBundle URL" in html


def test_render_bundle_preview_before_any_fetch_draws_nothing():
    # renderBundlePreview re-runs on every toggle, so it has to cope with
    # not having fetched yet rather than throwing and blanking the panel.
    assert eval_js_error("(async () => app.renderBundlePreview())()") is None


def test_bundle_panel_says_item_not_items_for_a_single_item_tier():
    html = _render_bundle(_BUNDLE_REPORT)
    assert "1 item<" in html
    assert "1 items" not in html


def test_bundle_panel_lists_what_each_tier_adds():
    html = _render_bundle(_BUNDLE_REPORT)
    assert "adds 3 new" in html
    assert "Moonfall Vol. 1-3" in html
    assert "The Hollow Crypt" in html
    assert "adds 1 new" in html
    assert "Shadow Hound Vol. 1-6" in html


def test_bundle_panel_emits_no_adds_row_for_a_tier_that_adds_nothing():
    html = _render_bundle(_BUNDLE_REPORT)
    assert html.count('class="bundle-adds"') == 2


def test_bundle_panel_keeps_the_whole_tier_table_above_every_list():
    # The comparison is what must not scroll. Interleaving the lists
    # between the rows put eight titles between the first two prices and
    # pushed the cheapest tier off the panel entirely.
    html = _render_bundle(_BUNDLE_REPORT)
    assert html.index("5.47") < html.index("adds 3 new")
    assert html.index("21.90") < html.index("13.13") < html.index("5.47")


def test_bundle_panel_heads_each_list_with_its_own_price():
    # A list is no longer adjacent to its row, so it has to say which tier
    # it belongs to.
    html = _render_bundle(_BUNDLE_REPORT)
    assert "€21.90 adds 3 new" in html
    assert "€13.13 adds 1 new" in html


def test_bundle_panel_escapes_titles_from_the_bundle_page():
    # Names come off a remote page; the panel is built with innerHTML.
    report = dict(_BUNDLE_REPORT, tiers=[
        {"price": 1.0, "total": 1, "owned": 0, "new": 1,
         "adds": ["<img src=x onerror=alert(1)>"]}])
    html = _render_bundle(report)
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_harness_loads_every_viewer_script():
    # the harness used to take one path; the split needs it to take the
    # list, in load order, or a moved function becomes an undefined name.
    # Deliberately not a list of filenames: that pins the file layout,
    # which is the very thing VIEWER_JS exists to stop the tests caring
    # about. app.js leading is the one ordering fact worth asserting here
    # -- it holds the helpers every later script calls.
    from tests.js_harness import VIEWER_JS
    assert VIEWER_JS[0].name == "app.js"
    assert all(p.exists() for p in VIEWER_JS)
    assert eval_js("typeof app.esc") == "function"


def test_hash_selects_exactly_one_section():
    shown = eval_js("""(() => {
      app.showSection("maintenance");
      return app.SECTIONS.map((s) => [s.id, !!document.querySelector(
        `#section-${s.id}`).hidden]);
    })()""")
    assert shown == [["library", True], ["maintenance", False],
                     ["keys", True], ["bundles", True]]


def test_unknown_hash_falls_back_to_library():
    # a stale bookmark, or a hand-typed hash, must not leave a blank page
    hidden = eval_js("""(() => {
      app.showSection("nonsense");
      return document.querySelector("#section-library").hidden;
    })()""")
    assert hidden is False


def test_current_section_reads_the_hash_and_rejects_junk():
    assert eval_js('(() => { location.hash = "#/bundles";'
                   ' return app.currentSection(); })()') == "bundles"
    assert eval_js('(() => { location.hash = "#/nope";'
                   ' return app.currentSection(); })()') == "library"
    assert eval_js('(() => { location.hash = "";'
                   ' return app.currentSection(); })()') == "library"


def test_badge_shows_a_count_and_vanishes_at_zero():
    # The harness's textContent getter always returns "", so the write is
    # asserted through dom.writes rather than read back off the element.
    written = eval_js("""(() => {
      dom.reset();
      app.setPending({maintenance: 12});
      app.renderBadges();
      const shown = dom.writes["#tab-maintenance .badge-count:text"];
      app.setPending({maintenance: 0});
      app.renderBadges();
      return [shown, dom.writes["#tab-maintenance .badge-count:text"]];
    })()""")
    assert written == ["12", ""]


def test_an_optional_backlog_never_badges_the_library_tab():
    # Unrated items never reach zero, and a badge that is always lit is
    # one the eye stops reading -- which would cost the Maintenance badge
    # beside it its meaning too.
    written = eval_js("""(() => {
      dom.reset();
      app.setPending({library: 900, maintenance: 3});
      app.renderBadges();
      return [dom.writes["#tab-library .badge-count:text"],
              dom.writes["#tab-maintenance .badge-count:text"]];
    })()""")
    assert written == ["", "3"]


def test_sidebar_collapse_persists():
    stored = eval_js("""(() => {
      app.toggleSidebar();
      return [globalThis.localStorage.getItem("hc-sidebar"),
              app.sidebarCollapsed()];
    })()""")
    assert stored == ["1", True]


def test_active_filters_are_summarised_outside_the_sidebar():
    # The summary is what makes collapsing safe, so it must name every
    # kind of filter, not only the chips.
    html = eval_js("""(() => {
      dom.reset();
      for (const f of Object.values(app.chipFilters)) { f.chips = []; f.text = ""; }
      app.setItems([]);
      app.chipFilters.genre.chips = ["Fantasy"];
      app.chipFilters.user_comment.text = "gift";
      app.setStatusFilter(["reading"]);
      app.setFlag("nocover");
      app.render();
      return dom.writes["#filter-chips"];
    })()""")
    assert "genre: Fantasy" in html
    assert 'user_comment: &quot;gift&quot;' in html
    assert "Status: Reading" in html
    assert "Flag:" in html


def test_active_filter_remove_buttons_avoid_the_tag_x_class():
    # tag-x is tested after chip-x in the click chain; an element with
    # tag-x but no chip-x splices the row-edit buffer instead of clearing
    # a filter. The summary's buttons must not carry it.
    html = eval_js("""(() => {
      dom.reset();
      for (const f of Object.values(app.chipFilters)) { f.chips = []; f.text = ""; }
      app.setItems([]);
      app.chipFilters.genre.chips = ["Fantasy"];
      app.render();
      return dom.writes["#filter-chips"];
    })()""")
    assert "active-x" in html
    assert "tag-x" not in html


_KEY_PAYLOAD = """{
  total: 5, reported: 4, expiring: 1, stale_hides: 0, missing_keys: [],
  counts: {matched: 1, unredeemed: 2, uncertain: 1, uncheckable: 1},
  libraries: {steam: {count: 2, imported_at: "2026-07-25T00:00:00"}},
  rows: [
    {product: "Amber Hollow", machine_name: "amberhollow_ex", gamekey: "kv789",
     store: "steam", key_type_label: "Steam",
     bundle: "Humble Game Bundle: Expiring Keys",
     bundle_url: "https://example.invalid/kv789",
     purchased_at: "2024-01-02T00:00:00", expires: "2099-08-11T00:00:00+00:00",
     expired: false, days_left: 12, revealed: true, state: "unredeemed",
     hidden_at: null, near_match: null},
    {product: "Starfall Rally Turbo", machine_name: "srt_ex", gamekey: "kv789",
     store: "steam", key_type_label: "Steam",
     bundle: "Humble Game Bundle: Key Vault",
     bundle_url: "https://example.invalid/kv789", purchased_at: null,
     expires: null, expired: false, days_left: null, revealed: false,
     state: "uncertain", hidden_at: null,
     near_match: {owned_title: "Starfall Rally", score: 0.86}},
    {product: "Verdant Reach", machine_name: "verdantreach_ex", gamekey: "kv789",
     store: "uplay", key_type_label: "Uplay",
     bundle: "Humble Game Bundle: Key Vault", bundle_url: null,
     purchased_at: null,
     expires: null, expired: false, days_left: null, revealed: false,
     state: "uncheckable", hidden_at: null, near_match: null},
    {product: "Cinder Vale", machine_name: "cindervale_ex", gamekey: "kv789",
     store: "steam", key_type_label: "Steam",
     bundle: "Humble Game Bundle: Key Vault",
     bundle_url: "https://example.invalid/kv789", purchased_at: null,
     expires: null, expired: false, days_left: null, revealed: true,
     state: "unredeemed", hidden_at: "2026-07-31T00:00:00+00:00",
     near_match: null}
  ]
}"""


def _with_keys(expression):
    """Run `expression` after loadKeys() has consumed the payload above."""
    # The payload is parenthesised: `async () => {...}` reads the object
    # literal as a function body and yields undefined, not a syntax error
    # you would notice from the assertion.
    return eval_js("""(async () => {
      app.setFetch(async () => ({json: async () => (%s)}));
      await app.loadKeys();
      return (%s);
    })()""" % (_KEY_PAYLOAD, expression))


def test_the_keys_panel_lists_the_reported_rows():
    html = _with_keys('(app.renderKeys(), dom.writes["#keys-panel"])')
    assert "Amber Hollow" in html
    assert "Humble Game Bundle: Expiring Keys" in html


def test_an_uncertain_row_shows_what_it_nearly_matched():
    html = _with_keys('(app.renderKeys(), dom.writes["#keys-panel"])')
    assert "Starfall Rally" in html


def test_uncheckable_rows_are_hidden_by_default():
    # The default view is the falsifiable one: a store with no importer
    # cannot be checked, so its keys are not evidence of anything.
    shown = _with_keys('app.shownKeys().map((r) => r.product)')
    assert shown == ["Amber Hollow", "Starfall Rally Turbo"]


def test_a_state_chip_toggles_its_rows():
    shown = _with_keys("""(() => {
      app.setKeyStates(["uncheckable"]);
      return app.shownKeys().map((r) => r.product);
    })()""")
    assert shown == ["Verdant Reach"]


def test_the_keys_badge_counts_expiring_rows_not_unredeemed_ones():
    # Hundreds of unredeemed keys would light the tab permanently, which is
    # the policy shell.js already settled against for Library. Expiring
    # keys are a queue; unredeemed ones are a standing fact.
    written = _with_keys("""(() => {
      dom.reset();
      app.setPending({keys: app.keysExpiring()});
      app.renderBadges();
      return dom.writes["#tab-keys .badge-count:text"];
    })()""")
    assert written == "1"


def test_the_keys_section_markup_exists():
    html = (Path(__file__).parent.parent / "humble_catalog" / "webapp"
            / "static" / "index.html").read_text(encoding="utf-8")
    assert '<div id="keys-panel"></div>' in html
    assert '<script src="/static/keys.js"></script>' in html


def test_the_bundle_column_links_to_the_bundle():
    # Same markup as the Library table's bundle tags, so a bundle name
    # behaves the same wherever it appears.
    html = _with_keys('(app.renderKeys(), dom.writes["#keys-panel"])')
    assert ('<a class="tag tag-link" href="https://example.invalid/kv789"'
            in html)
    assert 'rel="noopener"' in html


def test_a_bundle_with_no_url_renders_as_plain_text():
    # A row whose bundle carries no url must still show its name rather
    # than an <a> pointing at nothing.
    html = _with_keys("""(() => {
      app.setKeyStates(["uncheckable"]);
      app.renderKeys();
      return dom.writes["#keys-panel"];
    })()""")
    assert "Humble Game Bundle: Key Vault" in html
    assert 'href="null"' not in html


def test_the_key_table_gets_its_own_scrollport():
    # A sticky header needs a scroller of its own to stick within, and 722
    # rows must scroll inside the section rather than growing the page.
    html = _with_keys('(app.renderKeys(), dom.writes["#keys-panel"])')
    assert '<div id="key-table-wrap">' in html


def test_a_hidden_row_is_not_shown_by_default():
    # Being off by default is the entire point of hiding.
    shown = _with_keys('app.shownKeys().map((r) => r.product)')
    assert shown == ["Amber Hollow", "Starfall Rally Turbo"]


def test_the_hidden_chip_shows_the_hidden_rows():
    shown = _with_keys("""(() => {
      app.setKeyStates(["hidden"]);
      return app.shownKeys().map((r) => r.product);
    })()""")
    assert shown == ["Cinder Vale"]


def test_a_hidden_row_keeps_its_underlying_state_in_the_table():
    # Only chip membership changes. Nothing about WHY the row was reported
    # is lost from the display -- the State column still says it.
    html = _with_keys("""(() => {
      app.setKeyStates(["hidden"]);
      app.renderKeys();
      return dom.writes["#keys-panel"];
    })()""")
    assert "Cinder Vale" in html
    assert "Not in a library" in html


def test_every_chip_count_equals_the_rows_it_delivers():
    # The statistics panel shipped a row reading "Unmatched 4" that jumped
    # to 8 rows. Counting by displayState makes the four chips partition
    # the reported rows, so this holds by construction rather than by
    # anyone remembering the rule.
    pairs = _with_keys("""(() => {
      const counts = app.keyChipCounts();
      const out = {};
      for (const s of Object.keys(counts)) {
        app.setKeyStates([s]);
        out[s] = [counts[s], app.shownKeys().length];
      }
      return out;
    })()""")
    assert pairs, "no chips counted"
    for state, (promised, delivered) in pairs.items():
        assert promised == delivered, state


def test_the_chip_counts_partition_every_reported_row():
    total = _with_keys("""(() => {
      const counts = app.keyChipCounts();
      app.setKeyStates(app.KEY_STATES.map((s) => s.state));
      return [Object.values(counts).reduce((a, b) => a + b, 0),
              app.shownKeys().length];
    })()""")
    assert total[0] == total[1] == 4


def test_the_keys_badge_ignores_hidden_rows():
    # A hide that silences the row but leaves the badge lit has not
    # stopped the row reappearing.
    written = _with_keys("""(() => {
      dom.reset();
      app.setPending({keys: app.keysExpiring()});
      app.renderBadges();
      return dom.writes["#tab-keys .badge-count:text"];
    })()""")
    assert written == "1"


def test_the_table_offers_hide_and_unhide():
    html = _with_keys("""(() => {
      app.setKeyStates(["unredeemed", "uncertain", "uncheckable", "hidden"]);
      app.renderKeys();
      return dom.writes["#keys-panel"];
    })()""")
    assert "key-hide" in html
    assert ">hide</button>" in html
    assert ">unhide</button>" in html
    assert "2026-07-31" in html


# A bulk write is followed by load(), which drives every panel loader.
# Answering them all matters: loadDupes() reading the wrong shape leaves
# dupeGroups undefined, and load()'s badge arithmetic afterwards is NOT
# inside its try/catch, so the whole call throws somewhere unrelated to
# what the test is asking about.
_STUB_FETCH = """
             app.setFetch((url, opts) => {
               if (url === "/api/user-tags/bulk") {
                 posted = JSON.parse(opts.body);
                 return Promise.resolve(
                   {ok: true, json: () => Promise.resolve({ids: %s})});
               }
               return Promise.resolve({ok: true, json: () => Promise.resolve(
                 url === "/api/items"      ? {items: []} :
                 url === "/api/review"     ? {items: []} :
                 url === "/api/duplicates" ? {groups: []} :
                 url === "/api/stats"      ? {total: 0, sections: []} : {})});
             });
"""


def _run_bulk(action, changed_ids, tag="lent out", n_items=2):
    """Drive runBulk to completion and report the state it leaves.

    Two calls because armOrFire arms on the first click and fires on the
    second; the fired promise is what makes the second call awaitable.
    """
    catalog = json.dumps([_item(id=i, name=f"Item {i}")
                          for i in range(1, n_items + 1)])
    return eval_js(
        """(async () => {
             let posted = null;
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.setLastTagOp(null);
             document.querySelector("#bulk-tag").value = %s;
             %s
             const btn = document.querySelector("#bulk-add");
             await app.runBulk(btn, %s);
             await app.runBulk(btn, %s);
             return app.getLastTagOp();
           })()""" % (catalog, json.dumps(tag),
                      _STUB_FETCH % json.dumps(changed_ids),
                      json.dumps(action), json.dumps(action)))


def test_a_bulk_add_leaves_an_undo_that_removes():
    # the slot stores the INVERSE verb, ready to post
    op = _run_bulk("add", [1, 2])
    assert op == {"ids": [1, 2], "tag": "lent out", "action": "remove"}


def test_a_bulk_remove_leaves_an_undo_that_adds():
    op = _run_bulk("remove", [1])
    assert op == {"ids": [1], "tag": "lent out", "action": "add"}


def test_an_operation_that_changed_nothing_leaves_no_undo():
    # every row already had the tag: there is nothing to offer to undo,
    # and the route rejects an empty id list anyway
    assert _run_bulk("add", []) is None


def test_a_later_operation_replaces_the_undo():
    op = eval_js(
        """(async () => {
             let posted = null;
             app.setLastTagOp({ids: [9], tag: "to reread", action: "add"});
             app.setItems([%s]);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             document.querySelector("#bulk-tag").value = "lent out";
             %s
             const btn = document.querySelector("#bulk-add");
             await app.runBulk(btn, "add");
             await app.runBulk(btn, "add");
             return app.getLastTagOp();
           })()""" % (json.dumps(_item(id=1, name="Item 1")),
                      _STUB_FETCH % "[1]"))
    assert op == {"ids": [1], "tag": "lent out", "action": "remove"}


def test_undo_posts_the_inverse_and_clears_the_slot():
    sent = eval_js(
        """(async () => {
             let posted = null;
             app.setItems([]);
             app.setLastTagOp({ids: [1, 2], tag: "lent out", action: "add"});
             %s
             await app.undoBulk();
             return {posted, after: app.getLastTagOp()};
           })()""" % (_STUB_FETCH % "[1, 2]"))
    assert sent["posted"] == {"ids": [1, 2], "tag": "lent out", "action": "add"}
    # single level: no redo, and no second undo of the same operation
    assert sent["after"] is None


def test_the_undo_button_names_the_tag_and_the_count():
    labels = eval_js(
        """(() => {
             app.setItems([]);
             const out = {};
             app.setLastTagOp({ids: [1, 2], tag: "lent out", action: "add"});
             app.renderBulkBar();
             out.afterRemove = dom.writes["#bulk-undo:text"];
             app.setLastTagOp({ids: [1], tag: "to reread", action: "remove"});
             app.renderBulkBar();
             out.afterAdd = dom.writes["#bulk-undo:text"];
             out.hiddenWithSlot = document.querySelector("#bulk-undo").hidden;
             app.setLastTagOp(null);
             app.renderBulkBar();
             out.hiddenWithoutSlot = document.querySelector("#bulk-undo").hidden;
             return out;
           })()""")
    assert labels["afterRemove"] == 'Undo: restore "lent out" to 2 items'
    assert labels["afterAdd"] == 'Undo: remove "to reread" from 1 items'
    assert labels["hiddenWithSlot"] is False
    assert labels["hiddenWithoutSlot"] is True


def test_the_result_message_survives_the_button_redraw():
    # renderBulkBar() writes #bulk-note unconditionally, so calling it
    # after the result message wipes it -- the note read "Narrow the view
    # to remove." straight after a successful add. Invisible to the DOM
    # stub until something asserted on the ordering; caught in a browser.
    note = eval_js(
        """(async () => {
             let posted = null;
             app.setItems([%s]);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             app.setLastTagOp(null);
             document.querySelector("#bulk-tag").value = "lent out";
             %s
             const btn = document.querySelector("#bulk-add");
             await app.runBulk(btn, "add");
             await app.runBulk(btn, "add");
             return dom.writes["#bulk-note:text"];
           })()""" % (json.dumps(_item(id=1, name="Item 1")),
                      _STUB_FETCH % "[1]"))
    assert note == "Added to 1 of 1 items."


def test_the_undo_result_message_survives_the_button_redraw():
    note = eval_js(
        """(async () => {
             let posted = null;
             app.setItems([]);
             app.setLastTagOp({ids: [1, 2], tag: "lent out", action: "add"});
             %s
             await app.undoBulk();
             return dom.writes["#bulk-note:text"];
           })()""" % (_STUB_FETCH % "[1, 2]"))
    assert note == 'Restored "lent out" on 2 of 2 items.'


def test_undo_is_offered_while_remove_is_gated_off():
    # The gate exists so "remove from all N" is never one click. Undo acts
    # on a recorded id list, not on the current view, so it is available
    # precisely when Remove is not -- which is the whole point after an
    # unfiltered bulk add.
    state = eval_js(
        """(() => {
             app.setItems(%s);
             for (const f of Object.values(app.chipFilters)) {
               f.chips = []; f.text = "";
             }
             document.querySelector("#bulk-tag").value = "lent out";
             app.setLastTagOp({ids: [1], tag: "lent out", action: "remove"});
             app.renderBulkBar();
             return {
               removeDisabled: document.querySelector("#bulk-remove").disabled,
               undoHidden: document.querySelector("#bulk-undo").hidden,
               filtered: app.shownRows().filtered,
             };
           })()""" % json.dumps([_item(id=1, name="Item 1")]))
    assert state["filtered"] is False
    assert state["removeDisabled"] is True
    assert state["undoHidden"] is False


_SERIES_REPORT = dict(_BUNDLE_REPORT, overlaps=[], series=[
    {"offered": "Shadow Hound Vol. 1-6", "series_name": "Shadow Hound",
     "kind": "collection", "offered_volume": None, "span": [1, 6],
     "owned": [1], "owned_display": "Vol. 1", "already_owned": False},
])


def test_bundle_panel_renders_a_series_section():
    html = _render_bundle(_SERIES_REPORT)
    assert "Series you already hold (1)" in html
    assert "you own 1 of 6" in html
    assert 'data-series="Shadow Hound"' in html


def test_bundle_panel_omits_the_series_block_when_there_is_none():
    assert "Series you already hold" not in _render_bundle(
        dict(_BUNDLE_REPORT, series=[]))


def test_bundle_panel_survives_a_payload_carrying_no_series_field():
    # The `|| []` guard, same as keyed_items: an older server sends no
    # series key at all, and a renderer that throws blanks the page.
    assert "The World of Examplia" in _render_bundle(_BUNDLE_REPORT)


def test_bundle_panel_shouts_a_re_buy():
    html = _render_bundle(dict(_BUNDLE_REPORT, overlaps=[], series=[
        {"offered": "Shadow Hound Vol. 1", "series_name": "Shadow Hound",
         "kind": "volume", "offered_volume": 1, "span": None,
         "owned": [1], "owned_display": "Vol. 1", "already_owned": True}]))
    assert "ALREADY OWNED" in html


def test_a_collection_with_no_span_states_no_denominator_in_the_panel():
    html = _render_bundle(dict(_BUNDLE_REPORT, overlaps=[], series=[
        {"offered": "Shadow Hound Omnibus", "series_name": "Shadow Hound",
         "kind": "collection", "offered_volume": None, "span": None,
         "owned": [1, 2], "owned_display": "Vol. 1-2", "already_owned": False}]))
    assert "you own 2 volumes (Vol. 1-2)" in html
    assert " of " not in html.split("Series you already hold")[1]
