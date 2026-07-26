from unittest.mock import Mock
from humble_catalog import db
from humble_catalog.sources.base import Source, candidate
from humble_catalog.sources.google_books import GoogleBooks
from humble_catalog.sources.open_library import OpenLibrary

def _http(payload):
    http = Mock()
    resp = Mock(status_code=200)
    resp.json = Mock(return_value=payload)
    resp.raise_for_status = Mock()
    http.request.return_value = resp
    return http

def test_get_json_caches(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    src = Source(conn, http=_http({"ok": 1}))
    a = src.get_json("https://x.test/api", params={"q": "dune"})
    b = src.get_json("https://x.test/api", params={"q": "dune"})
    assert a == b == {"ok": 1}
    assert src.http.request.call_count == 1  # second hit came from cache

def test_get_json_retries_transient_5xx(tmp_path, monkeypatch):
    import requests
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    conn = db.connect(tmp_path / "t.db")
    bad = Mock(status_code=503)
    bad.raise_for_status.side_effect = requests.HTTPError("503", response=bad)
    good = Mock(status_code=200)
    good.json = Mock(return_value={"ok": 1})
    good.raise_for_status = Mock()
    http = Mock()
    http.request.side_effect = [bad, good]
    src = Source(conn, http=http)
    assert src.get_json("https://x.test/api") == {"ok": 1}
    assert http.request.call_count == 2

def test_get_json_gives_up_after_three_5xx(tmp_path, monkeypatch):
    import requests
    import pytest
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    bad = Mock(status_code=503)
    bad.raise_for_status.side_effect = requests.HTTPError("503", response=bad)
    http = Mock()
    http.request.return_value = bad
    with pytest.raises(requests.HTTPError):
        Source(conn, http=http).get_json("https://x.test/api")
    assert http.request.call_count == 3

def test_get_json_does_not_retry_429(tmp_path, monkeypatch):
    import requests
    import pytest
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    bad = Mock(status_code=429)
    bad.raise_for_status.side_effect = requests.HTTPError("429", response=bad)
    http = Mock()
    http.request.return_value = bad
    with pytest.raises(requests.HTTPError):
        Source(conn, http=http).get_json("https://x.test/api")
    assert http.request.call_count == 1  # dead quota: retrying is pointless

def test_candidate_defaults():
    c = candidate(source="s", title="T")
    assert c["authors"] is None and c["extra"] == {}

def test_google_books_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    payload = {"items": [{"volumeInfo": {
        "title": "All Systems Red", "authors": ["Martha Wells"],
        "categories": ["Fiction / Science Fiction"], "averageRating": 4.5,
        "infoLink": "https://books.google.com/books?id=abc"}}]}
    src = GoogleBooks(conn, http=_http(payload), key="test")
    cands = src.lookup("All Systems Red")
    assert cands[0]["title"] == "All Systems Red"
    assert cands[0]["authors"] == ["Martha Wells"]
    assert cands[0]["rating"] == 4.5
    assert cands[0]["source"] == "google_books"
    assert cands[0]["url"] == "https://books.google.com/books?id=abc"
    assert src.http.request.call_args.kwargs["params"]["key"] == "test"

def test_google_books_disabled_without_key(tmp_path, monkeypatch):
    # Google's keyless Books API quota is 0/day: without a key the source
    # must be silently disabled instead of erroring on every item.
    monkeypatch.delenv("GOOGLE_BOOKS_API_KEY", raising=False)
    conn = db.connect(tmp_path / "t.db")
    from unittest.mock import Mock
    assert GoogleBooks(conn, http=Mock()).lookup("Dune") == []

def test_open_library_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    payload = {"docs": [{"title": "Dune", "author_name": ["Frank Herbert"],
                         "ratings_average": 4.2, "subject": ["Science fiction"],
                         "key": "/works/OL893415W"}]}
    src = OpenLibrary(conn, http=_http(payload))
    cands = src.lookup("Dune")
    assert cands[0]["authors"] == ["Frank Herbert"]
    assert cands[0]["genre"] == "Science fiction"
    assert cands[0]["url"] == "https://openlibrary.org/works/OL893415W"
