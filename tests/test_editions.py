"""Cross-format edition detection.

Titles are invented -- see docs/TEST-DATA.md."""
from humble_catalog import db, editions


def test_a_trailing_format_marker_is_stripped():
    key = editions.edition_key("Salt and Sextant")
    assert key == editions.edition_key("Salt and Sextant Audiobook")
    assert key == editions.edition_key("Salt and Sextant (Unabridged)")


def test_a_run_of_trailing_markers_strips_as_a_unit():
    # "(audiobook novella)" is two markers in a row, which is why the
    # strip repeats rather than applying once.
    assert editions.edition_key("The Copper Almanac") == \
        editions.edition_key("The Copper Almanac (audiobook novella)")


def test_a_marker_inside_the_title_is_kept():
    # Trailing-only, deliberately: an anywhere-strip would reduce this
    # to "engineering handbook" and invite a collision with a
    # genuinely different book.
    assert editions.edition_key("Audio Engineering Handbook") == \
        "audio engineering handbook"


def test_a_title_that_is_only_markers_keeps_its_key():
    # Stripping to empty would group every such title together, so the
    # last non-empty key wins.
    assert editions.edition_key("Audiobook") == "audiobook"


def test_work_types_excludes_android_and_music():
    # The exclusion IS the precision story -- every measured false
    # positive came from one of these two.
    assert "android" not in editions.WORK_TYPES
    assert "music" not in editions.WORK_TYPES
    assert editions.WORK_TYPES == {"ebook", "audiobook", "comic"}
