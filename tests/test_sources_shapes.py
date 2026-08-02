"""The shape-safe accessors, and the parser sites that use them.

The Operating envelope classes metadata API responses adversarial and
names a merely changed upstream shape as the case that reaches these
parsers. Two failure modes were reproduced before these were written: a
field arriving unwrapped (`"Fantasy"` where `["Fantasy"]` was expected)
yielded its first CHARACTER as the genre, silently, and a field arriving
as another type raised out of `lookup` - survivable in harvest, but a 500
on the viewer's fetch_url route, which catches only ValueError,
MetadataUnavailable and RequestException.

Titles and names are invented, from docs/TEST-DATA.md.
"""
import pytest
from humble_catalog.sources.base import (as_list, as_mapping, as_number,
                                         as_text, first_mapping, first_text,
                                         text_list)
from humble_catalog.sources.audible import product_candidate
from humble_catalog.sources.comicvine import split_credits
from humble_catalog.sources.google_books import volume_candidate
from humble_catalog.sources.open_library import doc_candidate


@pytest.mark.parametrize("value,want", [
    ("Fantasy", "Fantasy"), ("  ", None), ("", None),
    (None, None), (5, None), (True, None), (["Fantasy"], None), ({}, None)])
def test_as_text_accepts_only_non_blank_strings(value, want):
    # A number is deliberately not text: coercing it would turn an
    # upstream type change into a plausible value instead of an absent one.
    assert as_text(value) == want


@pytest.mark.parametrize("value,want", [
    (4.5, 4.5), (5, 5.0), (0, 0.0), (None, None),
    ("4.5", None), (True, None), (False, None), ([], None), ({}, None)])
def test_as_number_rejects_text_and_bool_by_default(value, want):
    # bool is a subclass of int in Python, so a JSON true would arrive as
    # 1.0 without the explicit exclusion.
    assert as_number(value) == want


@pytest.mark.parametrize("value,want", [
    ("3", 3.0), ("2.5", 2.5), ("bonus", None), ("", None), (3, 3.0)])
def test_as_number_allow_text_accepts_numeric_strings(value, want):
    # The parameter at its other value: Audible documents `sequence` as a
    # string, unlike the rating fields, which are numbers.
    assert as_number(value, allow_text=True) == want


@pytest.mark.parametrize("value,want", [
    (["Fantasy", "Epic"], "Fantasy"),   # the documented shape
    ("Fantasy", "Fantasy"),             # unwrapped: the whole word, not "F"
    ([], None), (None, None), ({"name": "Fantasy"}, None), ([{}], None),
    ([None, "Epic"], "Epic")])
def test_first_text_never_returns_a_single_character(value, want):
    assert first_text(value) == want


@pytest.mark.parametrize("value,want", [
    ([{"name": "Alex Penner"}], ["Alex Penner"]),
    (["Alex Penner"], ["Alex Penner"]),
    ("Alex Penner", ["Alex Penner"]),
    ([{"id": 7}], None),                       # a contributor with no name
    ([{"name": "Alex Penner"}, {"id": 7}], ["Alex Penner"]),
    ([], None), (None, None), ("", None)])
def test_text_list_skips_unnamed_entries_and_returns_none_when_empty(value, want):
    # None rather than [] so the result can go straight to candidate(),
    # whose absent value is None.
    assert text_list(value) == want


def test_as_list_does_not_treat_a_string_as_a_sequence():
    # Iterating a string yields characters, which is how a changed field
    # shape becomes a run of one-letter records.
    assert as_list("Fantasy") == []
    assert as_list(["Fantasy"]) == ["Fantasy"]
    assert as_list(("Fantasy",)) == ["Fantasy"]


def test_as_mapping_and_first_mapping_always_yield_something_gettable():
    assert as_mapping("nope") == {}
    assert as_mapping({"a": 1}) == {"a": 1}
    assert first_mapping([{"a": 1}]) == {"a": 1}
    assert first_mapping({"a": 1}) == {"a": 1}      # arrived unwrapped
    assert first_mapping(["The Elder Realm"]) == {}
    assert first_mapping(None) == {}


# --- the reproduced defects, at the parser sites ---------------------

def test_a_string_category_is_the_genre_not_its_first_letter():
    got = volume_candidate({"title": "Gray Waters", "categories": "Fantasy"})
    assert got["genre"] == "Fantasy"


def test_a_string_subject_is_the_genre_not_its_first_letter():
    got = doc_candidate({"title": "The Quiet Harbor", "subject": "Fantasy"})
    assert got["genre"] == "Fantasy"


def test_a_non_string_open_library_key_yields_no_url():
    # Previously interpolated whatever it was into the address, producing
    # a url that looks real and resolves nowhere.
    assert doc_candidate({"title": "The Quiet Harbor", "key": 12345})["url"] is None


def test_a_dict_category_is_ignored_rather_than_raising():
    got = volume_candidate({"title": "Gray Waters",
                            "categories": {"name": "Fantasy"}})
    assert got["genre"] is None


def test_an_audible_author_without_a_name_is_skipped():
    assert product_candidate({"title": "Axebearer",
                              "authors": [{"id": 7}]})["authors"] is None


def test_an_audible_list_sequence_is_dropped_rather_than_raising():
    got = product_candidate({"title": "Axebearer", "series": [{"sequence": []}]})
    assert got["series_number"] is None


def test_an_audible_series_of_bare_names_still_names_the_series():
    got = product_candidate({"title": "Axebearer", "series": ["The Elder Realm"]})
    assert got["series"] == "The Elder Realm"


def test_a_credit_without_a_name_is_skipped():
    assert split_credits([{"role": "writer"}]) == ([], [])


def test_a_credit_whose_role_is_not_text_is_ignored():
    assert split_credits([{"name": "Bo Writer", "role": ["writer"]}]) == ([], [])


def test_the_documented_shapes_are_unchanged():
    # The point of the guards is that well-formed payloads parse exactly
    # as they did; a fix that quietly altered the happy path would be a
    # regression this file has to catch.
    got = volume_candidate({"title": "Gray Waters", "authors": ["Alex Penner"],
                            "categories": ["Fantasy"], "averageRating": 4.5,
                            "infoLink": "https://books.example.test/v"})
    assert (got["title"], got["authors"], got["genre"], got["rating"],
            got["url"]) == ("Gray Waters", ["Alex Penner"], "Fantasy", 4.5,
                            "https://books.example.test/v")
    aud = product_candidate({
        "title": "Axebearer", "asin": "B000000001",
        "authors": [{"name": "Alex Penner"}],
        "narrators": [{"name": "Sam Reader"}, {"name": "Pat Voice"}],
        "series": [{"title": "The Elder Realm", "sequence": "3"}],
        "rating": {"overall_distribution": {"average_rating": 4.4}}})
    assert (aud["narrator"], aud["series"], aud["series_number"],
            aud["rating"], aud["url"]) == (
        "Sam Reader, Pat Voice", "The Elder Realm", 3.0, 4.4,
        "https://www.audible.com/pd/B000000001")
