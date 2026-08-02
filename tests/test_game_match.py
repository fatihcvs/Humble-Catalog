"""game_match's scoring identity, and the invariant that protects it.

This module had no direct test before: it was covered only through keys
and bundle_preview. The identity below is what the prepared-pool design
rests on, and nothing else in the suite would notice if a rapidfuzz
upgrade broke it.

Titles are the invented library from docs/TEST-DATA.md.
"""
import pytest
from rapidfuzz import fuzz, process

from humble_catalog.game_match import (
    GAME_OWNED, GAME_POSSIBLE, classify_game, prepare_pool)
from humble_catalog.titles import clean_game_title, sequel_mismatch

LIBRARY = [
    ("widget quest", "Widget Quest"),
    ("pixel harbor", "Pixel Harbor™"),
    ("neon drifter", "Neon Drifter"),
    ("grove of echoes", "Grove of Echoes"),
    ("starfall rally", "Starfall Rally"),
    ("cinder vale", "Cinder Vale"),
]

OFFERED = [
    "Widget Quest",                      # exact
    "Widget Quest: Definitive Edition",  # edition suffix over the base
    "Widget Quest II",                   # sequel -- must read as new
    "Quest Widget",                      # word order
    "Starfall Rally Turbo",              # the possible band
    "Lantern & Lockpick",                # owned nowhere
    "Pixel Harbor™",                     # trademark symbol
    "Café of Broken Clocks",             # accented, and owned nowhere
    "",                                  # empty offered title
]


def _reference(offered, owned):
    """classify_game as it was before pools were prepared.

    token_sort_ratio against the unsorted pool -- the oracle the prepared
    path must agree with exactly.
    """
    key = clean_game_title(offered)
    if not key or not owned:
        return "new", None
    names = [normalized for normalized, _display in owned]
    hit = process.extractOne(key, names, scorer=fuzz.token_sort_ratio,
                             score_cutoff=GAME_POSSIBLE)
    if hit is None:
        return "new", None
    if sequel_mismatch(key, hit[0]):
        return "new", None
    return (("owned" if hit[1] >= GAME_OWNED else "possible"),
            {"offered": offered, "owned_title": owned[hit[2]][1],
             "score": round(hit[1] / 100, 2)})


@pytest.mark.parametrize("offered", OFFERED)
def test_prepared_scoring_matches_token_sort_ratio(offered):
    """The identity the whole design rests on, case by case."""
    assert classify_game(offered, prepare_pool(LIBRARY)) == \
        _reference(offered, LIBRARY)


def test_sequel_rule_survives_token_sorting():
    """Widget Quest II must not match an owned Widget Quest.

    The regression this pins: sort_tokens moves the numeral off the end
    ("ii quest widget"), and sequel_mismatch decides on the TRAILING
    token, so feeding it the sorted string makes the rule silently stop
    firing -- the sequel then scores 88.9 and reports as `possible`
    rather than `new`. classify_game indexes back to the unsorted entry
    before asking, which is what keeps this ("new", None).
    """
    assert classify_game("Widget Quest II", prepare_pool(LIBRARY)) == \
        ("new", None)


def test_match_reports_the_display_title_not_the_scoring_key():
    """owned_title is user-visible, so it comes from entries.

    Fails with "harbor pixel" if anyone reports extractOne's matched
    choice, which is the sorted key, instead of indexing back.
    """
    verdict, match = classify_game("Pixel Harbor™", prepare_pool(LIBRARY))
    assert verdict == "owned"
    assert match["owned_title"] == "Pixel Harbor™"


def test_an_empty_pool_makes_everything_new():
    assert classify_game("Widget Quest", prepare_pool([])) == ("new", None)


# --- digit and roman numerals are one number, not a sequel pair (F1) ---
# sequel_mismatch compared the trailing numeral as TEXT, so a library
# holding "Widget Quest 2" reported an offered "Widget Quest II" as new -
# a confident wrong answer to the only question a purchase decision asks.
# Both notations are real: storefronts pick either one.

NUMBERED_LIBRARY = [
    ("widget quest 2", "Widget Quest 2"),
    ("final chapter 4", "Final Chapter 4"),
]


@pytest.mark.parametrize("offered", ["Widget Quest II", "Final Chapter IV"])
def test_a_roman_spelling_of_an_owned_number_is_not_reported_as_new(offered):
    pool = prepare_pool(NUMBERED_LIBRARY)
    verdict, match = classify_game(clean_game_title(offered), pool)
    # "possible" rather than "owned" is the honest answer: the titles still
    # differ as text, so the score lands in the band where the report asks
    # the user to check. What it must never do is claim they do not own it.
    assert verdict != "new"
    assert match["owned_title"] in ("Widget Quest 2", "Final Chapter 4")


def test_a_genuine_sequel_is_still_reported_as_new():
    # The rule must not be blunted by the fix: 3 is not 2.
    pool = prepare_pool(NUMBERED_LIBRARY)
    assert classify_game(clean_game_title("Widget Quest III"), pool) == \
        ("new", None)
    assert classify_game(clean_game_title("Widget Quest 3"), pool) == \
        ("new", None)


def test_a_base_title_against_an_owned_sequel_is_still_new():
    pool = prepare_pool(NUMBERED_LIBRARY)
    assert classify_game(clean_game_title("Widget Quest"), pool) == ("new", None)


@pytest.mark.parametrize("a,b,want", [
    ("widget quest 2", "widget quest ii", False),   # one number, two notations
    ("widget quest 4", "widget quest iv", False),
    ("widget quest 9", "widget quest ix", False),   # subtractive form
    ("widget quest 14", "widget quest xiv", False),
    ("widget quest 2", "widget quest iii", True),   # genuinely different
    ("widget quest", "widget quest ii", True),      # base against sequel
    ("widget quest ii", "widget quest 3", True),
])
def test_sequel_mismatch_compares_numerals_by_value(a, b, want):
    assert sequel_mismatch(a, b) is want
