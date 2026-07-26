from unittest.mock import Mock
from humble_catalog import db
from humble_catalog.sources.comicvine import ComicVine

def _http(payload):
    http = Mock()
    resp = Mock(status_code=200)
    resp.json = Mock(return_value=payload)
    resp.raise_for_status = Mock()
    http.request.return_value = resp
    return http

def _http_seq(*payloads):
    """One canned response per request, in order."""
    http = Mock()
    def request(method, url, **kw):
        resp = Mock(status_code=200)
        resp.json = Mock(return_value=payloads[request.n])
        resp.raise_for_status = Mock()
        request.n += 1
        return resp
    request.n = 0
    http.request = Mock(side_effect=request)
    return http

def test_comicvine_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    payload = {"results": [{
        "name": "Shadow Hound", "start_year": "1994",
        "publisher": {"name": "Example Comics"},
        "api_detail_url": "https://comicvine.gamespot.com/api/volume/4050-123/",
        "site_detail_url": "https://comicvine.gamespot.com/shadow-hound/4050-123/",
        "first_issue": {
            "api_detail_url": "https://comicvine.gamespot.com/api/issue/4000-9/"}}]}
    cands = ComicVine(conn, http=_http(payload), key="k").lookup("Shadow Hound")
    assert cands[0]["series"] == "Shadow Hound"
    assert cands[0]["extra"]["volume_api_url"].endswith("/4050-123/")
    # credits live on the ISSUE resource, so the search must carry the first
    # issue's URL forward or enrichment has nothing to fetch roles from.
    assert cands[0]["extra"]["first_issue_api_url"].endswith("/issue/4000-9/")
    assert cands[0]["url"] == "https://comicvine.gamespot.com/shadow-hound/4050-123/"

def test_comicvine_credits_reads_the_issue_resource(tmp_path, monkeypatch):
    # Regression: credits() used to ask the VOLUME endpoint for
    # `person_credits`, a field volume records do not have. Comic Vine
    # answers that with error "OK" and an empty results object, so every
    # comic silently landed with no authors and no illustrator.
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    payload = {"results": {"person_credits": [
        {"name": "Bo Writer", "role": "writer"},
        {"name": "Ann Inker", "role": "penciler, inker, cover"},
        {"name": "Cy Multi", "role": "writer, penciler"},
        {"name": "Dee Letters", "role": "letterer"},
        {"name": "Eve Editor", "role": "editor"}]}}
    http = _http(payload)
    writers, artists = ComicVine(conn, http=http, key="k") \
        .credits("https://comicvine.gamespot.com/api/issue/4000-9/")
    assert "/api/issue/4000-9/" in http.request.call_args[0][1]
    assert writers == "Bo Writer, Cy Multi"
    assert artists == "Ann Inker, Cy Multi"

def test_comicvine_credits_without_issue_url(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert ComicVine(conn, http=Mock(), key="k").credits(None) == (None, None)

def test_comicvine_disabled_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("COMICVINE_API_KEY", raising=False)
    conn = db.connect(tmp_path / "t.db")
    assert ComicVine(conn, http=Mock()).lookup("Shadow Hound") == []

def test_split_credits_keeps_illustrator_narrow():
    # Policy test, not a behaviour discovery: illustrator means penciler or
    # artist. Roles below are the real Comic Vine vocabulary. If a future
    # change widens this, it should have to delete an assertion to do it.
    from humble_catalog.sources.comicvine import split_credits
    writers, artists = split_credits([
        {"name": "Bo Writer", "role": "writer"},
        {"name": "Pat Pencil", "role": "penciler, inker"},
        {"name": "Ann Art", "role": "artist, cover"},
        {"name": "Ink Only", "role": "inker"},
        {"name": "Col Only", "role": "colorist"},
        {"name": "Cov Only", "role": "cover"},
        {"name": "Let Only", "role": "letterer"},
        {"name": "Ed Only", "role": "editor"},
        {"name": "Jo Journo", "role": "journalist"}])
    assert writers == ["Bo Writer"]
    assert artists == ["Pat Pencil", "Ann Art"]

def test_quota_resets_after_the_documented_hour(tmp_path, monkeypatch):
    # 200 requests per resource per hour. The base class's fallback happens
    # to be an hour too, so asserting the value alone would pass without
    # the source declaring anything. Moving the fallback proves the hour is
    # Comic Vine's own documented window rather than a coincidence - and it
    # is the only source likely to 429 in normal use, at 180/hr of 200.
    from datetime import datetime, timedelta, timezone
    from humble_catalog.sources.base import Source
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(Source, "quota_resets_at",
                        lambda self, now=None: now + timedelta(days=99))
    src = ComicVine(db.connect(tmp_path / "t.db"), key="k")
    assert src.quota_resets_at(now=now) == now + timedelta(hours=1)
