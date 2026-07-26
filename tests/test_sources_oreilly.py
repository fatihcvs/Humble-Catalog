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
    assert all(c["rating"] is None or c["rating"] <= 5 for c in cands)

def test_oreilly_in_ebook_source_order(tmp_path):
    order = SOURCE_ORDER["ebook"]
    assert order.index("oreilly") == order.index("google_books") + 1
    assert "oreilly" in _default_sources(db.connect(tmp_path / "t.db"))
