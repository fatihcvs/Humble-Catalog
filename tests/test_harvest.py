import json
import threading
from datetime import datetime, timedelta, timezone
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

def test_worklist_is_sorted_regardless_of_row_order(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    # Seeded deliberately out of alphabetical order: the guarantee is that
    # the list does not inherit the row order of an ORDER BY-less SELECT.
    _seed(conn, "Wings of Autumn Dusk (Book 1)", "ebook")
    _seed(conn, "Axebearer (Grim & Fell)", "ebook")
    _seed(conn, "Café of Broken Clocks", "ebook")
    wl = harvest.build_worklist(conn)
    # clean_title strips the parentheticals; the accent is not the deciding
    # character, so this title sorts at C rather than past z.
    assert wl["hardcover"] == ["Axebearer",
                               "Café of Broken Clocks",
                               "Wings of Autumn Dusk"]
    for titles in wl.values():
        assert titles == sorted(titles, key=lambda t: (t.casefold(), t))

def test_worklist_order_breaks_case_ties_by_content(tmp_path):
    """A case-only tie must be decided by the titles, not by row order.

    With key=str.casefold alone the two seedings below return different
    lists, because Python's stable sort falls back to the input order -
    which is the unordered SELECT this change exists to stop relying on.
    """
    def worklist(dbname, first, second):
        conn = db.connect(tmp_path / dbname)
        _seed(conn, first, "ebook")
        _seed(conn, second, "ebook")
        return harvest.build_worklist(conn)["hardcover"]
    # Distinct filenames on purpose: Windows paths are case-insensitive, so
    # naming these after the titles would collide on one file.
    forwards = worklist("one.db", "Gray Waters", "gray waters")
    backwards = worklist("two.db", "gray waters", "Gray Waters")
    assert forwards == backwards == ["Gray Waters", "gray waters"]

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

RESET = datetime(2099, 1, 1, 8, 0, tzinfo=timezone.utc)

class _SpentQuota:
    """A source with a warm cache whose live quota is already used up.

    Cached titles are served whatever happens; anything else costs a live
    request, which 429s - unless the pool has switched the source offline,
    in which case it raises CacheMiss the way a real Source does.

    It declares a reset time as a real Source does. There is no getattr
    fallback in the pool, deliberately, so a double that 429s must.
    """
    def __init__(self, cached):
        self.cached, self.offline = set(cached), False
        self.calls, self.live = [], 0

    def quota_resets_at(self, now=None):
        return RESET

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

# --- quota records across runs -------------------------------------------

from humble_catalog import quota

def test_a_429_records_the_sources_own_reset_time(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": _SpentQuota(cached=[])}, _conn=conn)
    assert quota.blocked(conn, "hardcover") == RESET

def test_a_blocked_rerun_makes_no_live_attempt_but_still_counts_the_cache(tmp_path):
    # The point of the whole feature. Today's rerun spends one request to
    # rediscover a 429 yesterday already proved; it must spend none, while
    # the cached titles still tick so the progress number cannot go
    # backwards between runs.
    conn = db.connect(tmp_path / "t.db")
    for i in range(5):
        _seed(conn, f"Book {i}", "ebook")
    titles = [f"Book {i}" for i in range(5)]
    src = _SpentQuota(cached=[t for t in titles if t != "Book 1"])
    quota.record(conn, "hardcover", datetime.now(timezone.utc) + timedelta(hours=6))
    incomplete = harvest.run(db_path=tmp_path / "t.db",
                             sources={"hardcover": src}, _conn=conn)
    assert src.live == 0                      # was 1 before this feature
    assert src.calls == titles                # still walked the whole list
    assert "hardcover" in incomplete
    row = conn.execute(
        "SELECT done FROM run_status WHERE command='harvest'").fetchone()
    assert row["done"] == 4                   # the four cached ones

def test_a_blocked_run_reports_the_source_as_paused(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    quota.record(conn, "hardcover", datetime.now(timezone.utc) + timedelta(hours=6))
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": _SpentQuota(cached=[])}, _conn=conn)
    out = capsys.readouterr().out
    assert "hardcover is out of quota until" in out
    assert "rerun 'harvest' to resume" not in out   # wrong advice for this case

def test_a_fresh_429_also_reports_as_paused_not_merely_incomplete(tmp_path, capsys):
    # The two ways into the same condition must agree.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": _SpentQuota(cached=[])}, _conn=conn)
    assert "hardcover is out of quota until" in capsys.readouterr().out

def test_an_expired_record_is_ignored(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    quota.record(conn, "hardcover", datetime.now(timezone.utc) - timedelta(minutes=1))
    src = _SpentQuota(cached=[])
    harvest.run(db_path=tmp_path / "t.db", sources={"hardcover": src}, _conn=conn)
    assert src.live == 1                      # went live again

def test_ignore_quota_overrides_a_live_record_without_deleting_it(tmp_path):
    # The escape hatch for a wrong guess - a rotated-in paid key, or a
    # limit that was per-minute. It asserts nothing about the future, so
    # the record stays: a genuine 429 will simply rewrite it.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    quota.record(conn, "hardcover", datetime.now(timezone.utc) + timedelta(hours=6))
    src = _SpentQuota(cached=[])
    harvest.run(db_path=tmp_path / "t.db", sources={"hardcover": src},
                _conn=conn, ignore_quota=True)
    assert src.live == 1
    assert conn.execute("SELECT COUNT(*) FROM source_quota").fetchone()[0] == 1

def _rows(conn):
    return conn.execute(
        "SELECT * FROM source_failure ORDER BY source, title").fetchall()

def test_a_failed_title_is_recorded(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError("503 backendFailed")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": boom}, _conn=conn)
    rows = _rows(conn)
    assert len(rows) == 1
    assert rows[0]["source"] == "hardcover"
    assert rows[0]["title"] == "Gray Waters"
    assert rows[0]["failures"] == 1
    assert "503 backendFailed" in rows[0]["last_error"]

def test_the_same_title_failing_again_counts_the_second_run(tmp_path):
    # The property the whole feature exists to produce: because the pool
    # visits a title once per run, the counter counts runs. If anyone
    # reintroduces per-run retries this turns into "attempts" and lies.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError("503 backendFailed")
    for _ in range(2):
        harvest.run(db_path=tmp_path / "t.db",
                    sources={"hardcover": boom}, _conn=conn)
    assert _rows(conn)[0]["failures"] == 2

def test_a_rate_limit_is_not_recorded_as_a_title_failure(tmp_path):
    # A 429 is a fact about the quota, not about the title, and
    # source_quota already holds it. Both errors arrive at the same
    # `except`, so this pins the branch that keeps them apart.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = _429()
    boom.quota_resets_at.return_value = RESET
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": boom}, _conn=conn)
    assert _rows(conn) == []
    assert conn.execute(
        "SELECT COUNT(*) FROM source_quota").fetchone()[0] == 1

def test_a_cache_miss_records_nothing(tmp_path):
    # An offline source declining to fetch is not a failure.
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    miss = Mock(); miss.lookup.side_effect = CacheMiss("x")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": miss}, _conn=conn)
    assert _rows(conn) == []

def test_a_recorded_error_never_contains_the_api_key(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "Gray Waters", "ebook")
    boom = Mock(); boom.lookup.side_effect = RuntimeError(
        "503 Server Error for url: https://api.example/v1?q=x&key=SECRETKEY")
    harvest.run(db_path=tmp_path / "t.db",
                sources={"hardcover": boom}, _conn=conn)
    assert "SECRETKEY" not in _rows(conn)[0]["last_error"]
    assert "SECRETKEY" not in capsys.readouterr().out
