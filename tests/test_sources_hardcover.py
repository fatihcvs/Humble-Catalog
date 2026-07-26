import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from humble_catalog import db
from humble_catalog.sources.hardcover import Hardcover

FIXTURE = Path(__file__).parent / "fixtures" / "hardcover_search.json"

@pytest.mark.skipif(not FIXTURE.exists(),
                    reason="run scripts/capture_hardcover_fixture.py with "
                           "HARDCOVER_API_KEY set to create the live fixture")
def test_hardcover_parses_captured_response(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    http = Mock()
    resp = Mock(status_code=200)
    resp.json = Mock(return_value=json.loads(FIXTURE.read_text()))
    resp.raise_for_status = Mock()
    http.request.return_value = resp
    cands = Hardcover(conn, http=http, token="test").lookup("All Systems Red")
    assert cands, "expected at least one candidate from the captured fixture"
    titles = [c["title"].lower() for c in cands]
    assert any("all systems red" in t for t in titles)
    assert any(c["authors"] for c in cands)
    assert any(c["series"] == "The Murderbot Diaries" for c in cands)
    assert any(c["genre"] for c in cands)

def test_hardcover_disabled_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("HARDCOVER_API_KEY", raising=False)
    conn = db.connect(tmp_path / "t.db")
    assert Hardcover(conn, http=Mock()).lookup("Dune") == []

def _mock_http(payload):
    http = Mock()
    resp = Mock(status_code=200)
    resp.json = Mock(return_value=payload)
    resp.raise_for_status = Mock()
    http.request.return_value = resp
    return http

def test_bearer_prefix_in_token_is_not_doubled(tmp_path, monkeypatch):
    # Hardcover's settings page shows the token WITH the "Bearer " prefix;
    # pasting it verbatim must not produce "Bearer Bearer <token>".
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    http = _mock_http({"data": {"search": {"results": {"hits": []}}}})
    Hardcover(conn, http=http, token="Bearer abc123").lookup("Dune")
    headers = http.request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer abc123"

def test_graphql_errors_raise_and_are_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    conn = db.connect(tmp_path / "t.db")
    http = _mock_http({"errors": [{"message": "Malformed Authorization header"}]})
    src = Hardcover(conn, http=http, token="abc")
    with pytest.raises(RuntimeError, match="Malformed"):
        src.lookup("Dune")
    assert conn.execute("SELECT COUNT(*) c FROM source_cache").fetchone()["c"] == 0


def test_quota_resets_within_minutes_not_the_default_hour(tmp_path):
    # Hardcover documents 60 requests per *minute*, so the base class's
    # one-hour guess would idle the source ~60x longer than the limit
    # actually lasts. Its own window is the only defensible number.
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    src = Hardcover(db.connect(tmp_path / "t.db"), token="t")
    assert src.quota_resets_at(now=now) == now + timedelta(minutes=2)
