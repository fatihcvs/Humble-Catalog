import json
from pathlib import Path
from unittest.mock import Mock
from humble_catalog import db, extract
from humble_catalog import covers as covers_mod

FIXTURE = Path(__file__).parent / "fixtures" / "order_book.json"

def _client(raw):
    client = Mock()
    client.list_order_keys.return_value = [raw["gamekey"]]
    client.get_order.return_value = raw
    cover = Mock(status_code=200, content=b"\xff\xd8fakejpg")
    client.http.get.return_value = cover
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
