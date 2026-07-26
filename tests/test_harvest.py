import json
import threading
from unittest.mock import Mock
import requests
from humble_catalog import db, harvest
from humble_catalog.sources.base import CacheMiss, candidate

_mn = 0

def _seed(conn, name, typ):
    global _mn
    _mn += 1
    conn.execute("INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
                 (f"mn{_mn}", name, typ))
    conn.commit()

def test_worklist_covers_type_relevant_sources_only(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")     # -> hardcover, google_books, oreilly, open_library
    _seed(conn, "Shadow Hound", "comic")    # -> comicvine, google_books
    _seed(conn, "Night Signal", "audiobook")# -> audible, hardcover, google_books
    wl = harvest.build_worklist(conn)
    assert "Gray Waters" in wl["hardcover"]
    assert "Gray Waters" in wl["oreilly"]
    assert "Shadow Hound" in wl["comicvine"]
    assert "Shadow Hound" not in wl.get("oreilly", [])   # comics don't use oreilly
    assert "Night Signal" in wl["audible"]

def test_worklist_excludes_music_and_android(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Neon Drift OST", "music")
    _seed(conn, "Cool Tower Defense", "android")
    wl = harvest.build_worklist(conn)
    assert all("Neon Drift OST" not in titles for titles in wl.values())
    assert all("Cool Tower Defense" not in titles for titles in wl.values())

def test_worklist_dedupes_titles_per_source(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    _seed(conn, "Gray Waters", "ebook")  # same cleaned title, two items
    wl = harvest.build_worklist(conn)
    assert wl["hardcover"].count("Gray Waters") == 1

def _fake(cands=None):
    src = Mock()
    src.lookup.return_value = cands or []
    return src

def test_one_thread_per_source(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for i in range(4):
        _seed(conn, f"Book {i}", "ebook")
    idents = {}  # source name -> set of thread ids seen
    def make(name):
        s = Mock()
        def lookup(title):
            idents.setdefault(name, set()).add(threading.get_ident())
            return []
        s.lookup.side_effect = lookup
        return s
    sources = {n: make(n) for n in ("hardcover", "google_books",
                                    "oreilly", "open_library")}
    harvest.run(db_path=tmp_path / "t.db", sources=sources, _conn=conn)
    for name, seen in idents.items():
        assert len(seen) == 1, f"{name} used {len(seen)} threads"
    all_idents = [next(iter(s)) for s in idents.values()]
    assert len(set(all_idents)) == len(all_idents)  # distinct threads across sources

def test_one_failing_source_does_not_stop_others(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError("503")
    ok = _fake([candidate(source="google_books", title="Gray Waters")])
    incomplete = harvest.run(
        db_path=tmp_path / "t.db",
        sources={"hardcover": boom, "google_books": ok,
                 "oreilly": _fake(), "open_library": _fake()}, _conn=conn)
    ok.lookup.assert_called()          # sibling still ran
    assert "hardcover" in incomplete   # failing source reported

def _429():
    err = requests.HTTPError("429"); err.response = Mock(status_code=429)
    return err

class _SpentQuota:
    """A source with a warm cache whose live quota is already used up.

    Cached titles are served whatever happens; anything else costs a live
    request, which 429s - unless the pool has switched the source offline,
    in which case it raises CacheMiss the way a real Source does.
    """
    def __init__(self, cached):
        self.cached, self.offline = set(cached), False
        self.calls, self.live = [], 0

    def lookup(self, title):
        self.calls.append(title)
        if title in self.cached:
            return []
        if self.offline:
            raise CacheMiss(title)
        self.live += 1
        raise _429()

def test_429_stops_only_its_pool(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for i in range(3):
        _seed(conn, f"Book {i}", "ebook")
    dead = _SpentQuota(cached=[])
    ok = _fake()
    incomplete = harvest.run(
        db_path=tmp_path / "t.db",
        sources={"hardcover": dead, "google_books": ok,
                 "oreilly": _fake(), "open_library": _fake()}, _conn=conn)
    assert dead.live == 1                     # one live attempt, then no more
    assert ok.lookup.call_count == 3          # sibling drained all titles
    assert "hardcover" in incomplete

def test_429_keeps_draining_the_titles_already_cached(tmp_path):
    # A dead quota kills the network, not the cache. The pool must keep
    # walking so titles fetched by an earlier run still count, or a source
    # whose first uncached title sits near the top of the list looks like
    # it never gets anywhere however often you rerun 'harvest'.
    conn = db.connect(tmp_path / "t.db")
    for i in range(5):
        _seed(conn, f"Book {i}", "ebook")
    titles = [f"Book {i}" for i in range(5)]
    src = _SpentQuota(cached=[t for t in titles if t != "Book 1"])
    incomplete = harvest.run(db_path=tmp_path / "t.db",
                             sources={"hardcover": src}, _conn=conn)
    assert src.calls == titles                # walked the whole list
    assert src.live == 1                      # but only one live attempt
    assert "hardcover" in incomplete
    row = conn.execute("SELECT done FROM run_status WHERE command='harvest'").fetchone()
    assert row["done"] == 4                   # the four cached ones, not the miss

def test_fully_cached_harvest_sends_nothing(tmp_path):
    # Resumability: with every query already in source_cache, a real source
    # returns from cache and never touches its http session.
    from urllib.parse import urlencode
    from humble_catalog.sources.google_books import GoogleBooks
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    http = Mock()
    src = GoogleBooks(conn, http=http, key="k")
    url = "https://www.googleapis.com/books/v1/volumes"
    # no "key": the credential is sent but deliberately not part of the key
    params = {"q": 'intitle:"Gray Waters"', "maxResults": 5}
    key = url + "?" + urlencode(sorted(params.items()))
    conn.execute("INSERT INTO source_cache (source, query, fetched_at, json) "
                 "VALUES (?,?,?,?)", ("google_books", key, "2026-01-01",
                                      json.dumps({"items": []})))
    conn.commit()
    harvest.run(db_path=tmp_path / "t.db",
                sources={"google_books": src}, _conn=conn)
    http.request.assert_not_called()
