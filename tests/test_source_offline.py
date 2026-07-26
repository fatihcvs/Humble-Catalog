import json
import pytest
from unittest.mock import Mock
from humble_catalog import db
from humble_catalog.sources.base import Source, CacheMiss

class Echo(Source):
    name = "echo"
    def lookup(self, title):
        return self.get_json("https://example.test/api", params={"q": title})

def test_offline_hit_returns_cache_without_sending(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    http = Mock()
    conn.execute(
        "INSERT INTO source_cache (source, query, fetched_at, json) VALUES (?,?,?,?)",
        ("echo", "https://example.test/api?q=hello", "2026-01-01", json.dumps({"ok": 1})))
    conn.commit()
    src = Echo(conn, http=http, offline=True)
    assert src.get_json("https://example.test/api", params={"q": "hello"}) == {"ok": 1}
    http.request.assert_not_called()

def test_offline_miss_raises_cachemiss_without_sending(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    http = Mock()
    src = Echo(conn, http=http, offline=True)
    with pytest.raises(CacheMiss):
        src.get_json("https://example.test/api", params={"q": "absent"})
    http.request.assert_not_called()
