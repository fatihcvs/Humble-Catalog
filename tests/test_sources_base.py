from unittest.mock import Mock
import pytest
import requests
from humble_catalog.sources import base


def _resp(status=200):
    resp = Mock(status_code=status)
    if status >= 400:
        err = requests.HTTPError(response=Mock(status_code=status))
        resp.raise_for_status = Mock(side_effect=err)
    else:
        resp.raise_for_status = Mock()
    return resp


def test_with_retries_returns_first_success(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)
    resp = _resp()
    send = Mock(return_value=resp)
    assert base._with_retries(send) is resp
    assert send.call_count == 1
    assert slept == []


def test_with_retries_backs_off_exponentially_on_5xx(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)
    send = Mock(return_value=_resp(503))
    with pytest.raises(requests.HTTPError):
        base._with_retries(send)
    assert send.call_count == 3
    assert slept == [5, 10]


def test_with_retries_does_not_retry_403(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)
    send = Mock(return_value=_resp(403))
    with pytest.raises(requests.HTTPError):
        base._with_retries(send)
    assert send.call_count == 1
    assert slept == []


def test_with_retries_retries_connection_errors(monkeypatch):
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)
    send = Mock(side_effect=requests.ConnectionError("boom"))
    with pytest.raises(requests.ConnectionError):
        base._with_retries(send)
    assert send.call_count == 3
    assert slept == [5, 10]


def _payload(data):
    resp = _resp()
    resp.json = Mock(return_value=data)
    return resp


def test_cache_key_excludes_secret_params(tmp_path):
    # The credential is sent but never keyed on: baking it into the cache
    # key means rotating the API key orphans every response already
    # fetched, and the source starts over from nothing.
    from humble_catalog import db
    from humble_catalog.sources.google_books import GoogleBooks
    conn = db.connect(tmp_path / "t.db")
    http = Mock()
    http.request.return_value = _payload({"items": []})
    GoogleBooks(conn, http=http, key="old-key").lookup("Gray Waters")
    assert http.request.call_count == 1
    assert http.request.call_args.kwargs["params"]["key"] == "old-key"  # still sent
    stored = conn.execute("SELECT query FROM source_cache").fetchone()["query"]
    assert "old-key" not in stored and "key=" not in stored

    GoogleBooks(conn, http=http, key="new-key").lookup("Gray Waters")
    assert http.request.call_count == 1        # rotated key, same cache entry


def test_cache_key_excludes_comicvine_api_key(tmp_path):
    from humble_catalog import db
    from humble_catalog.sources.comicvine import ComicVine
    conn = db.connect(tmp_path / "t.db")
    http = Mock()
    http.request.return_value = _payload({"results": []})
    ComicVine(conn, http=http, key="old-key").lookup("Shadow Hound")
    stored = conn.execute("SELECT query FROM source_cache").fetchone()["query"]
    assert "old-key" not in stored and "api_key=" not in stored
    ComicVine(conn, http=http, key="new-key").lookup("Shadow Hound")
    assert http.request.call_count == 1


def test_secret_params_do_not_collapse_distinct_queries(tmp_path):
    # Stripping must remove only the credential: two different titles are
    # still two different cache entries.
    from humble_catalog import db
    from humble_catalog.sources.google_books import GoogleBooks
    conn = db.connect(tmp_path / "t.db")
    http = Mock()
    http.request.return_value = _payload({"items": []})
    src = GoogleBooks(conn, http=http, key="k")
    src.lookup("Gray Waters")
    src.lookup("Shadow Hound")
    assert http.request.call_count == 2
    assert conn.execute("SELECT COUNT(*) c FROM source_cache").fetchone()["c"] == 2


def test_default_quota_reset_is_about_an_hour(tmp_path):
    # Deliberately short. A source whose real limit is per-minute must not
    # sit out a whole day; guessing short costs one wasted request, while
    # guessing long costs harvesting.
    from datetime import datetime, timedelta, timezone
    from humble_catalog import db
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    src = base.Source(db.connect(tmp_path / "t.db"))
    assert src.quota_resets_at(now=now) == now + timedelta(hours=1)

def test_redact_hides_key_params():
    url = "https://api.example/v1?q=x&key=SECRETKEY&maxResults=5"
    out = base.redact(f"503 Server Error for url: {url}")
    assert "SECRETKEY" not in out
    assert "key=REDACTED" in out
    assert "q=x" in out            # ordinary params survive
    assert "maxResults=5" in out

def test_redact_covers_the_other_spellings_and_any_case():
    assert "S" not in base.redact("?api_key=S")
    assert "S" not in base.redact("?apikey=S")
    assert "S" not in base.redact("?API_KEY=S")

def test_redact_leaves_a_string_without_a_key_alone():
    assert base.redact("Connection aborted") == "Connection aborted"
