import pytest
from humble_catalog.titles import clean_game_title, clean_title, sequel_mismatch

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
