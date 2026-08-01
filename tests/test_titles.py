import pytest
from humble_catalog import titles
from humble_catalog.titles import (
    clean_game_title, clean_title, sequel_mismatch, sort_tokens)

@pytest.mark.parametrize("raw,clean,num", [
    ("Wings of Autumn Dusk (Book 1)", "Wings of Autumn Dusk", 1.0),
    ("All Systems Red: The Murderbot Diaries (Book 1)", "All Systems Red: The Murderbot Diaries", 1.0),
    ("Building Widget Services 2e", "Building Widget Services", None),
    ("Learning Widget-Driven Design, 1st Edition", "Learning Widget-Driven Design", None),
    ("The Quiet Harbor: A Novel", "The Quiet Harbor", None),
    ("Axebearer (Grim & Fell)", "Axebearer", None),
    ("1632", "1632", None),
])
def test_clean_title(raw, clean, num):
    assert clean_title(raw) == (clean, num)


def test_clean_game_title_lowercases_and_strips_punctuation():
    assert clean_game_title("Lantern & Lockpick!") == "lantern lockpick"


def test_clean_game_title_strips_trademark_symbols():
    assert clean_game_title("Pixel Harbor™") == "pixel harbor"


def test_clean_game_title_strips_edition_suffixes():
    # Owning the base game means an edition re-release is not new to you.
    for offered in ("Widget Quest: Definitive Edition",
                    "Widget Quest - Game of the Year Edition",
                    "Widget Quest Deluxe Edition",
                    "Widget Quest Remastered"):
        assert clean_game_title(offered) == "widget quest"


def test_clean_game_title_strips_stacked_suffixes():
    assert clean_game_title("Widget Quest Remastered: Deluxe Edition") == "widget quest"


def test_clean_game_title_keeps_trailing_numerals():
    # Stripping these would fold every sequel into its predecessor.
    assert clean_game_title("Widget Quest II") == "widget quest ii"
    assert clean_game_title("Widget Quest 2") == "widget quest 2"


def test_sequel_mismatch_flags_a_numbered_sequel():
    assert sequel_mismatch("widget quest", "widget quest ii") is True
    assert sequel_mismatch("widget quest 2", "widget quest 3") is True


def test_sequel_mismatch_ignores_unrelated_and_identical_titles():
    assert sequel_mismatch("widget quest", "widget quest") is False
    assert sequel_mismatch("widget quest", "grove of echoes") is False
    # A trailing word that is not a numeral is a different game, but not a
    # *sequel* pair -- the fuzzy score is left to judge it.
    assert sequel_mismatch("starfall rally", "starfall rally turbo") is False


def test_sort_tokens_orders_a_cleaned_title():
    assert sort_tokens("widget quest") == "quest widget"
    assert sort_tokens("quest widget") == "quest widget"


def test_sort_tokens_moves_a_trailing_numeral_off_the_end():
    # Exactly the hazard game_match.classify_game guards against: the
    # numeral sequel_mismatch relies on finding last is no longer last.
    assert sort_tokens("widget quest ii") == "ii quest widget"


def test_sort_tokens_of_empty_is_empty():
    assert sort_tokens("") == ""


def test_a_bare_volume_marker_parses_to_its_number():
    found = titles.parse_series("Shadow Hound Vol. 22")
    assert (found.display, found.number, found.kind) == ("Shadow Hound", 22, "volume")


def test_every_volume_spelling_parses():
    for raw in ("Shadow Hound Vol 3", "Shadow Hound Vol. 3",
                "Shadow Hound Volume 3", "Shadow Hound Book 3"):
        assert titles.parse_series(raw).number == 3, raw


def test_a_range_is_a_collection_and_never_its_lower_bound():
    # A bare-volume pattern reads this as volume 1, which would match an
    # owned Vol. 1 and report the whole collection as already owned --
    # discouraging the purchase of five books not held.
    found = titles.parse_series("Shadow Hound Vol. 1-6")
    assert found.kind == "collection"
    assert found.number is None
    assert found.span == (1, 6)
    assert found.display == "Shadow Hound"


def test_a_collection_word_is_a_collection_with_no_span():
    # No title carries an omnibus's volume count, so there is no
    # denominator to state and none is invented.
    found = titles.parse_series("Shadow Hound Omnibus")
    assert (found.kind, found.span, found.display) == ("collection", None, "Shadow Hound")


def test_a_marker_followed_by_a_subtitle_still_parses():
    # 113 of 679 volume markers in the catalog are followed by ": Subtitle".
    # Anchoring to end-of-string alone would drop a sixth of them.
    found = titles.parse_series("Shadow Hound Vol. 1: Origins")
    assert (found.display, found.number) == ("Shadow Hound", 1)


def test_the_series_key_ignores_punctuation_so_spellings_merge():
    # Measured: one series was split three ways by a trailing period on an
    # initialism, and another by a space where a sibling used a hyphen.
    keys = {titles.parse_series(raw).key for raw in (
        "S.H.A.D.O.W Vol. 1", "S.H.A.D.O.W. Vol. 2", "S.H.A.D.O.W.: Vol. 3",
    )}
    assert len(keys) == 1
    assert titles.parse_series("Shadow-Hound Quest Vol. 1").key == \
           titles.parse_series("Shadow-Hound-Quest Vol. 2").key


def test_titles_differing_by_more_than_punctuation_stay_apart():
    # The one near-identical pair the measurement did NOT merge. Its two
    # halves hold identical volume sets, which is what says they are two
    # series rather than one spelling drift.
    assert titles.parse_series("Moonfall Vol. 1").key != \
           titles.parse_series("Moonfalls Vol. 1").key


def test_an_issue_range_in_parentheses_is_not_a_volume_range():
    # The premise this whole entry was built on. clean_title strips the
    # parenthetical first, so the issue range never reaches parse_series --
    # Vol. 22 COLLECTS issues 127-132; it is one volume, not six.
    cleaned, hint = titles.clean_title("Shadow Hound Vol. 22 (#127-132)")
    found = titles.parse_series(cleaned, hint)
    assert (found.kind, found.number, found.span) == ("volume", 22, None)


def test_clean_titles_parenthesized_hint_is_accepted_not_rediscovered():
    cleaned, hint = titles.clean_title("Wings of Autumn Dusk (Book 1)")
    found = titles.parse_series(cleaned, hint)
    assert (found.display, found.number, found.kind) == \
           ("Wings of Autumn Dusk", 1, "volume")


def test_a_title_with_no_marker_has_no_series():
    assert titles.parse_series("Unrelated Book") == titles.NO_SERIES


def test_a_marker_that_is_the_whole_title_names_no_series():
    assert titles.parse_series("Omnibus") == titles.NO_SERIES


def test_clean_title_hint_still_fires_only_on_the_parenthesized_spelling():
    # Pins the deliberate NON-widening, and the reason is NOT the hint --
    # that only fills a field on a candidate that already won. Widening
    # would strip the marker from the CLEANED TITLE, which feeds every
    # source lookup, score and worklist entry: measured at 2,308 distinct
    # enrichable titles collapsing to 1,894, with 44 volumes of one series
    # landing on a single query. enrich.series_from_title reads the bare
    # spelling instead, leaving cleaned byte-identical.
    assert titles.clean_title("Wings of Autumn Dusk (Book 1)")[1] == 1.0
    assert titles.clean_title("Shadow Hound Vol. 3")[1] is None
