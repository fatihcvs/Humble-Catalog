import json
from pathlib import Path
import pytest
from humble_catalog.parse_order import MalformedOrder, parse_order

FIXTURE = Path(__file__).parent / "fixtures" / "order_book.json"

def test_parse_order_book_bundle():
    bundle, items, externals = parse_order(json.loads(FIXTURE.read_text()))
    assert bundle == {
        "gamekey": "abc123",
        "name": "Humble Book Bundle: Test by Example Press",
        "url": "https://www.humblebundle.com/downloads?key=abc123",
        "purchased_at": "2020-05-01T12:00:00",
    }
    assert len(items) == 1  # wallpaper skipped
    item = items[0]
    assert item["machine_name"] == "allsystemsred_ebook"
    assert item["publisher"] == "Example Press"
    assert item["type"] == "ebook"
    assert item["formats"] == ["epub", "pdf"]
    assert externals[0]["human_name"] == "DriveThruRPG Voucher"

ANDROID_FIXTURE = Path(__file__).parent / "fixtures" / "order_android.json"

def test_parse_order_keeps_android_subproduct():
    bundle, items, externals = parse_order(json.loads(ANDROID_FIXTURE.read_text()))
    assert bundle["gamekey"] == "apk456"
    assert len(items) == 1  # wallpaper still skipped
    item = items[0]
    assert item["machine_name"] == "cooltower_android"
    assert item["publisher"] == "Indie Dev Co"
    assert item["type"] == "android"
    assert item["formats"] == ["apk"]
    assert externals == []

# --- the required-field contract (E1) --------------------------------
# This module refuses a malformed order at the parse site on purpose: a
# tolerated gap becomes a NULL that fails a NOT NULL constraint two
# layers later, where nothing names the order that caused it. That stance
# is unchanged. What E1 changed is the message - these payloads used to
# raise KeyError or "string indices must be integers", neither of which
# says which order to look at.

@pytest.mark.parametrize("payload,why", [
    ({"gamekey": "abc123", "product": "nope"}, "product is not an object"),
    ({"gamekey": "abc123", "product": []}, "product is a list"),
    ({"gamekey": "abc123"}, "product is absent"),
    ({"gamekey": "abc123", "product": {}}, "the bundle name is absent"),
    ({"product": {"human_name": "Bundle One"}}, "the gamekey is absent"),
])
def test_a_malformed_order_is_refused_at_the_parse_site(payload, why):
    with pytest.raises(MalformedOrder):
        parse_order(payload)

def test_the_refusal_names_the_order_and_the_field():
    with pytest.raises(MalformedOrder) as caught:
        parse_order({"gamekey": "abc123", "product": "nope"})
    assert "abc123" in str(caught.value) and "human_name" in str(caught.value)

def test_a_required_external_key_field_still_refuses():
    # Deliberately NOT tolerated: the column is NOT NULL and every tpk in
    # the catalog carries this field.
    with pytest.raises(MalformedOrder):
        parse_order({"gamekey": "abc123", "product": {"human_name": "Bundle One"},
                     "tpkd_dict": {"all_tpks": [{"human_name": "Cinder Vale"}]}})

@pytest.mark.parametrize("subproducts", ["nope", {"a": 1}, None, 5])
def test_a_subproduct_list_of_the_wrong_shape_yields_no_items(subproducts):
    # Not a required field: an order with no readable subproducts is a
    # bundle with no items, which is a real shape (a keys-only order).
    bundle, items, externals = parse_order(
        {"gamekey": "abc123", "product": {"human_name": "Bundle One"},
         "subproducts": subproducts})
    assert items == [] and bundle["name"] == "Bundle One"

def test_a_download_entry_of_the_wrong_shape_does_not_crash():
    bundle, items, _ = parse_order({
        "gamekey": "abc123", "product": {"human_name": "Bundle One"},
        "subproducts": [{"machine_name": "graywaters_ebook",
                         "human_name": "Gray Waters",
                         "downloads": ["nope", {"platform": "ebook",
                                                "download_struct": "nope"}]}]})
    assert [i["name"] for i in items] == ["Gray Waters"]
    assert items[0]["formats"] == []
