from unittest.mock import Mock
from humble_catalog import db
from humble_catalog.sources.audible import Audible

def test_audible_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    payload = {"products": [{
        "asin": "B074MFY2Y6",
        "title": "All Systems Red",
        "authors": [{"name": "Martha Wells"}],
        "narrators": [{"name": "Kevin R. Free"}],
        "series": [{"title": "The Murderbot Diaries", "sequence": "1"}],
        "rating": {"overall_distribution": {"average_rating": 4.4}}}]}
    http = Mock()
    resp = Mock(status_code=200)
    resp.json = Mock(return_value=payload)
    resp.raise_for_status = Mock()
    http.request.return_value = resp
    cands = Audible(conn, http=http).lookup("All Systems Red")
    c = cands[0]
    assert c["narrator"] == "Kevin R. Free"
    assert c["series"] == "The Murderbot Diaries"
    assert c["series_number"] == 1.0
    assert c["rating"] == 4.4
    assert c["url"] == "https://www.audible.com/pd/B074MFY2Y6"
