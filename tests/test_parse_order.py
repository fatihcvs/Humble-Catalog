import json
from pathlib import Path
from humble_catalog.parse_order import parse_order

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
