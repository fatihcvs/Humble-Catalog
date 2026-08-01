import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from humble_catalog import db, extract
from humble_catalog import covers as covers_mod

FIXTURE = Path(__file__).parent / "fixtures" / "order_book.json"

@pytest.fixture(autouse=True)
def _routable(monkeypatch):
    """Treat the fixture's cover host as publicly routable.

    The cover downloader now validates its destination, and that check
    resolves the hostname. Without this the suite would depend on live DNS
    for the fixture's imgix URL. The guard itself is tested against
    addresses that need no lookup, in test_outbound.py.
    """
    monkeypatch.setattr("humble_catalog.outbound.publicly_routable",
                        lambda host: True)

class _Response:
    """A stand-in for a streamed requests response.

    The cover downloader reads the body in chunks inside a `with`, so the
    double has to be a context manager that yields itself and serve
    iter_content, not merely carry a .content attribute. Written out rather
    than assembled from a mock: the explicit class says exactly which four
    things the downloader is entitled to use.
    """

    def __init__(self, body, status_code=200,
                 url="https://hb.imgix.net/cover.jpg"):
        self.body = body
        self.status_code = status_code
        self.headers = {}
        # outbound.get re-checks the scheme of the URL the response reports,
        # because a server can answer 200 while naming a different final
        # URL. A mock would have invented this attribute silently.
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_content(self, n):
        for i in range(0, len(self.body), n):
            yield self.body[i:i + n]


def _response(body, status_code=200):
    return _Response(body, status_code)


def _client(raw, cover_body=b"\xff\xd8fakejpg"):
    client = Mock()
    client.list_order_keys.return_value = [raw["gamekey"]]
    client.get_order.return_value = raw
    client.http.get.return_value = _response(cover_body)
    return client

def test_extract_stores_and_downloads_covers(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw = json.loads(FIXTURE.read_text())
    dbp, covers_dir = tmp_path / "t.db", tmp_path / "covers"
    extract.run(db_path=dbp, covers_dir=covers_dir, client=_client(raw))
    conn = db.connect(dbp)
    assert conn.execute("SELECT COUNT(*) c FROM raw_orders").fetchone()["c"] == 1
    item = conn.execute("SELECT * FROM items").fetchone()
    fname = covers_mod.cover_filename(item["machine_name"])
    assert item["cover_path"] == f"covers/{fname}"
    assert (covers_dir / fname).read_bytes().startswith(b"\xff\xd8")


def test_extract_relinks_existing_cover_without_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw = json.loads(FIXTURE.read_text())
    dbp, covers_dir = tmp_path / "t.db", tmp_path / "covers"
    covers_dir.mkdir()
    fname = covers_mod.cover_filename("allsystemsred_ebook")
    (covers_dir / fname).write_bytes(b"\xff\xd8already")
    client = _client(raw)
    extract.run(db_path=dbp, covers_dir=covers_dir, client=client)
    assert client.http.get.call_count == 0   # file on disk -> no download
    conn = db.connect(dbp)
    assert conn.execute("SELECT cover_path FROM items").fetchone()["cover_path"] \
        == f"covers/{fname}"

def test_cover_download_reports_progress(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw = json.loads(FIXTURE.read_text())
    extract.run(db_path=tmp_path / "t.db", covers_dir=tmp_path / "covers",
                client=_client(raw))
    out = capsys.readouterr().out
    assert "Cover 1/1: All Systems Red" in out

def test_extract_skips_cached_orders(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw = json.loads(FIXTURE.read_text())
    dbp = tmp_path / "t.db"
    client = _client(raw)
    extract.run(db_path=dbp, covers_dir=tmp_path / "c", client=client)
    extract.run(db_path=dbp, covers_dir=tmp_path / "c", client=client)
    assert client.get_order.call_count == 1  # second run: nothing new

def test_reparse_reclassifies_from_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw = json.loads(FIXTURE.read_text())
    dbp = tmp_path / "t.db"
    extract.run(db_path=dbp, covers_dir=tmp_path / "c", client=_client(raw))
    conn = db.connect(dbp)
    conn.execute("UPDATE items SET type='audiobook' WHERE type_overridden=0")
    conn.commit()
    conn.close()
    extract.reparse(db_path=dbp)  # local only: no client involved
    out = capsys.readouterr().out
    assert "Bundle 1/1:" in out
    conn = db.connect(dbp)
    assert conn.execute("SELECT type FROM items").fetchone()["type"] == "ebook"

def test_extract_refetch_refreshes_cached_orders(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw = json.loads(FIXTURE.read_text())
    dbp = tmp_path / "t.db"
    client = _client(raw)
    extract.run(db_path=dbp, covers_dir=tmp_path / "c", client=client)
    extract.run(db_path=dbp, covers_dir=tmp_path / "c", client=client, refetch=True)
    assert client.get_order.call_count == 2  # refetch ignores the cache

ANDROID_FIXTURE = Path(__file__).parent / "fixtures" / "order_android.json"

def test_extract_backfills_apk_items_from_cached_orders(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw = json.loads(ANDROID_FIXTURE.read_text())
    dbp = tmp_path / "t.db"
    # Simulate a cache written before the android gate: the raw order is
    # stored but its APK item never made it into the items table.
    conn = db.connect(dbp)
    conn.execute("INSERT INTO raw_orders (gamekey, fetched_at, json) VALUES (?,?,?)",
                 (raw["gamekey"], "2021-01-01T00:00:00", ANDROID_FIXTURE.read_text()))
    conn.commit()
    conn.close()
    client = _client(raw)
    extract.run(db_path=dbp, covers_dir=tmp_path / "c", client=client)
    assert client.get_order.call_count == 0  # cached: backfill is local-only
    conn = db.connect(dbp)
    item = conn.execute("SELECT * FROM items").fetchone()
    assert item is not None and item["type"] == "android"
    conn.close()
    extract.run(db_path=dbp, covers_dir=tmp_path / "c", client=client)  # idempotent
    conn = db.connect(dbp)
    assert conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM downloads").fetchone()["c"] == 1

def test_an_oversized_cover_is_refused_and_nothing_is_written(tmp_path, monkeypatch):
    """A cover past the cap must leave no file.

    Truncating instead would put half a JPEG on disk under the name a real
    cover would have, and relink would then treat it as already fetched.
    """
    monkeypatch.setattr("time.sleep", lambda s: None)
    raw = json.loads(FIXTURE.read_text())
    dbp, covers_dir = tmp_path / "t.db", tmp_path / "covers"
    oversized = b"\xff\xd8" + b"\x00" * extract.MAX_COVER_BYTES
    extract.run(db_path=dbp, covers_dir=covers_dir,
                client=_client(raw, cover_body=oversized))
    conn = db.connect(dbp)
    assert conn.execute("SELECT cover_path FROM items").fetchone()["cover_path"] is None
    assert list(covers_dir.iterdir()) == []
