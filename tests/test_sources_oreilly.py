import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from humble_catalog import db
from humble_catalog.enrich import SOURCE_ORDER, _default_sources
from humble_catalog.sources.oreilly import OReilly

FIXTURE = Path(__file__).parent / "fixtures" / "oreilly_search.json"

def _http(payload):
    http = Mock()
    resp = Mock(status_code=200)
    resp.json = Mock(return_value=payload)
    resp.raise_for_status = Mock()
    http.request.return_value = resp
    return http

def test_oreilly_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    # real API shape: relative web_url, average_rating scaled x1000
    payload = {"results": [{
        "title": "Python Crash Course, 3rd Edition", "authors": ["Eric Matthes"],
        "isbn": "9781718502703", "average_rating": 4667,
        "web_url": "/library/view/python-crash-course/9781098156664/"}]}
    cands = OReilly(conn, http=_http(payload)).lookup("Python Crash Course")
    assert cands[0]["source"] == "oreilly"
    assert cands[0]["title"].startswith("Python Crash Course")
    assert cands[0]["authors"] == ["Eric Matthes"]
    assert cands[0]["url"] == ("https://learning.oreilly.com/library/view/"
                               "python-crash-course/9781098156664/")
    assert cands[0]["rating"] == 4.67
    assert cands[0]["extra"]["isbn"] == "9781718502703"

@pytest.mark.skipif(not FIXTURE.exists(),
                    reason="run scripts/capture_oreilly_fixture.py to create "
                           "the live fixture (keyless)")
def test_oreilly_parses_captured_response(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    cands = OReilly(conn, http=_http(json.loads(FIXTURE.read_text()))) \
        .lookup("Python Crash Course")
    assert cands, "expected at least one candidate from the captured fixture"
    assert any("python crash course" in c["title"].lower() for c in cands)
    assert any(c["authors"] for c in cands)
    assert all(c["url"] and c["url"].startswith("https://") for c in cands)
    # Deliberately NOT `rating is None or rating <= 5`: that assertion was
    # satisfied by 0.01, the exact value the scale defect produced, so it
    # sat beside the bug it was meant to pin and could not fail on it.
    # Round-tripping is the invariant a wrong scale breaks.
    raw = [r.get("average_rating") for r in json.loads(FIXTURE.read_text())["results"]]
    assert len(raw) == len(cands)
    assert any(c["rating"] is not None for c in cands), \
        "the fixture carries rated results; parsing them all to None hides a defect"
    for value, cand in zip(raw, cands):
        got = cand["rating"]
        if got is None:
            continue
        assert 0 < got <= 5
        # The parsed value must reproduce the raw field it came from. The
        # tolerance is the rounding to two places and nothing more: one
        # step there is 10 raw units, so the error can never exceed 5. A
        # mis-scaled value misses by three orders of magnitude.
        if value >= 1000:
            assert abs(got * 1000 - value) <= 5
        else:
            assert got == value

@pytest.mark.parametrize("raw,want", [
    # The documented x1000 scale, hand-computed. 4395 rounds DOWN because
    # the float nearest 4.395 sits just below the midpoint.
    (4667, 4.67), (4750, 4.75), (4395, 4.39),
    (1000, 1.0),                # the bottom of the scaled domain
    (5000, 5.0),                # the top of it
    (5001, None),               # above it: would exceed the 0-5 domain
    # Already in the 0-5 domain, taken as it is.
    (4.5, 4.5), (5, 5.0), (0.5, 0.5),
    # The gap the defect lived in. Every one of these was divided by 1000
    # and became a near-zero rating written to external_rating, so an
    # upstream moving to a 0-10 or 0-100 scale silently rescored the
    # catalog. Uninterpretable is dropped, not divided.
    (5.001, None), (7.0, None), (10, None), (50, None), (87, None),
    (999, None),
    # Non-values.
    (0, None), (None, None), (-3, None), (True, None), ("4667", None),
])
def test_oreilly_rating_scale(raw, want, tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    payload = {"results": [{"title": "The Widget Programming Language",
                            "average_rating": raw}]}
    assert OReilly(conn, http=_http(payload)).lookup("Widget")[0]["rating"] == want


def test_oreilly_in_ebook_source_order(tmp_path):
    order = SOURCE_ORDER["ebook"]
    assert order.index("oreilly") == order.index("google_books") + 1
    assert "oreilly" in _default_sources(db.connect(tmp_path / "t.db"))
