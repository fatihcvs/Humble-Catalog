"""Behavioural tests for the viewer's fuzzy search scorer (fuzzy.js).

The scorer is a pure function, so it gets a case table rather than a
handful of examples. Titles are invented -- see docs/TEST-DATA.md.

Assertions are on score *bands*, not exact values: pinning 0.87 pins an
arithmetic accident, while pinning "this landed in the token tier" pins
the behaviour the design promises.
"""
import json

from tests.js_harness import eval_js


def _fold(text):
    return eval_js(f"Fuzzy.fold({json.dumps(text)})")


def test_fold_lowercases_and_strips_punctuation():
    assert _fold("The Quiet Harbor: A Novel")["text"] == "the quiet harbor a novel"


def test_fold_strips_accents():
    assert _fold("Café of Broken Clocks")["text"] == "cafe of broken clocks"


def test_fold_elides_apostrophes_rather_than_spacing_them():
    # both apostrophe forms must agree with the spelling a person types,
    # which has no apostrophe at all
    assert _fold("Innkeeper's Ledger")["text"] == "innkeepers ledger"
    assert _fold("Innkeeper’s Ledger")["text"] == "innkeepers ledger"


def test_fold_collapses_punctuation_runs_and_trims():
    assert _fold("  The Endless Wars: Inferno!  ")["text"] == "the endless wars inferno"


def test_fold_maps_every_character_back_to_the_original_index():
    folded = _fold("Café of Broken Clocks")
    text, index = folded["text"], folded["map"]
    assert len(index) == len(text)
    at = text.index("broken")
    assert "Café of Broken Clocks"[index[at]] == "B"


def test_fold_map_survives_an_elided_apostrophe():
    folded = _fold("Innkeeper's Ledger")
    at = folded["text"].index("ledger")
    assert "Innkeeper's Ledger"[folded["map"][at]] == "L"


def test_tokenize_reports_ranges_into_the_folded_string():
    tokens = eval_js(
        'Fuzzy.tokenize(Fuzzy.fold("The Quiet Harbor").text)')
    assert [t["text"] for t in tokens] == ["the", "quiet", "harbor"]
    assert (tokens[1]["start"], tokens[1]["end"]) == (4, 9)


def test_tokenize_handles_an_empty_string():
    assert eval_js('Fuzzy.tokenize("")') == []


QUIET = "The Quiet Harbor: A Novel"
INFERNO = "The Endless Wars: Inferno!"
MOONFALL = "MOONFALL, Vol. 1"
LEDGER = "Innkeeper's Ledger"
CAFE = "Café of Broken Clocks"
EXAMPLIA = "The World of Examplia"

# Band edges from the design. A case asserts the tier it lands in, never
# an exact score.
T1 = (0.90, 1.00)
T2 = (0.69, 0.85)
T3 = (0.40, 0.50)


def _score(query, text):
    return eval_js(f"Fuzzy.score({json.dumps(query)}, {json.dumps(text)})")


def _in_band(query, text, band):
    result = _score(query, text)
    low, high = band
    assert low <= result["score"] <= high, (
        f"{query!r} vs {text!r} scored {result['score']}, wanted {band}")
    return result


def test_exact_substring_lands_in_the_top_band():
    _in_band("quiet harbor", QUIET, T1)


def test_wrong_word_order_lands_in_the_token_band():
    _in_band("harbor quiet", QUIET, T2)


def test_skipped_middle_word_lands_in_the_token_band():
    _in_band("endless inferno", INFERNO, T2)


def test_a_typo_lands_in_the_token_band():
    # a dropped letter, not a truncation: "moonfal" is a *prefix* of
    # "moonfall" and would legitimately match as an exact substring,
    # testing nothing about typo tolerance
    _in_band("monfall", MOONFALL, T2)


def test_apostrophes_and_case_do_not_block_an_exact_match():
    _in_band("innkeepers ledger", LEDGER, T1)
    _in_band("innkeepers ledger", "Innkeeper’s Ledger", T1)


def test_an_accent_does_not_block_a_match():
    _in_band("cafe broken", CAFE, T2)


def test_initials_land_in_the_acronym_band():
    _in_band("woe", EXAMPLIA, T3)


def test_an_unrelated_query_does_not_match_at_all():
    # the failure mode of fuzzy search is not missing a result, it is
    # returning everything -- a cutoff with no test is a cutoff that drifts
    assert _score("axebearer", QUIET)["score"] == 0
    assert _score("axebearer", QUIET)["spans"] == []


def test_a_one_letter_title_word_does_not_prefix_match_a_long_query():
    # "The Quiet Harbor: A Novel" has a one-letter token, and prefix
    # matching runs in both directions, so every query starting with "a"
    # once matched it at 0.9 -- enough to carry an unrelated query over
    # the cutoff on its own
    assert eval_js('Fuzzy.score("axebearer", "A")')["score"] == 0
    assert eval_js('Fuzzy.score("novelty", "A Novel")')["score"] > 0


def test_bands_order_exact_above_token_above_acronym():
    exact = _score("quiet harbor", QUIET)["score"]
    token = _score("harbor quiet", QUIET)["score"]
    acronym = _score("woe", EXAMPLIA)["score"]
    assert exact > token > acronym


def test_short_queries_only_ever_match_as_substrings():
    # "wo" as an acronym or a token would hit a large share of a catalog
    assert _score("wo", EXAMPLIA)["score"] > 0        # substring of "world"
    assert _score("we", EXAMPLIA)["score"] == 0       # acronym-only, refused


def test_spans_point_at_the_original_string_past_collapsed_punctuation():
    # ": " folds to a single space, so every folded index past it is one
    # short of the original. This is the case an index map exists for --
    # without it the highlight slides left by one character.
    result = _score("inferno", INFERNO)
    start, end = result["spans"][0]
    assert INFERNO[start:end] == "Inferno"


def test_an_accent_does_not_disturb_the_span():
    result = _score("broken clocks", CAFE)
    start, end = result["spans"][0]
    assert CAFE[start:end] == "Broken Clocks"


def test_spans_point_at_the_original_string_through_an_apostrophe():
    result = _score("ledger", LEDGER)
    start, end = result["spans"][0]
    assert LEDGER[start:end] == "Ledger"


def test_token_spans_cover_each_matched_word_in_order():
    result = _score("harbor quiet", QUIET)
    assert [QUIET[s:e] for s, e in result["spans"]] == ["Quiet", "Harbor"]


def test_an_empty_query_matches_nothing():
    assert _score("", QUIET)["score"] == 0
    assert _score("   ", QUIET)["score"] == 0
