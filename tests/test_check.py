import io
from unittest.mock import Mock
from humble_catalog import check

class _Tty(io.StringIO):
    def isatty(self):
        return True

def _sources(*names):
    out = {}
    for n in names:
        src = Mock()
        src.lookup.return_value = [{"title": "A"}]
        src.key = src.token = "set"
        out[n] = src
    return out

def test_check_reports_ok_fail_and_skip(monkeypatch, capsys):
    monkeypatch.delenv("HARDCOVER_API_KEY", raising=False)
    ok = Mock()
    ok.lookup.return_value = [{"title": "A"}, {"title": "B"}]
    ok.token = "set"
    broken = Mock()
    broken.lookup.side_effect = RuntimeError("401 bad key")
    broken.key = "wrong"
    from humble_catalog import db
    from humble_catalog.sources.hardcover import Hardcover
    keyless = Hardcover(db.connect(":memory:"), http=Mock())  # no token -> skip
    results = check.run(sources={"open_library": ok, "comicvine": broken,
                                 "hardcover": keyless})
    assert results["open_library"][0] == "OK"
    assert "2" in results["open_library"][1]
    assert results["comicvine"][0] == "FAIL"
    assert "401" in results["comicvine"][1]
    assert results["hardcover"] == ("SKIP", "HARDCOVER_API_KEY not set")
    out = capsys.readouterr().out
    assert "open_library" in out and "OK" in out
    assert "FAIL" in out and "SKIP" in out

def test_check_never_prints_api_keys(capsys):
    # requests error strings include the full URL - keys must be redacted
    broken = Mock()
    broken.key = "SECRETKEY"
    broken.lookup.side_effect = RuntimeError(
        "503 Server Error for url: https://api.example/v1?q=x&key=SECRETKEY&n=5")
    results = check.run(sources={"google_books": broken})
    assert "SECRETKEY" not in results["google_books"][1]
    assert "SECRETKEY" not in capsys.readouterr().out
    assert "key=REDACTED" in results["google_books"][1]

def test_check_builds_real_sources_by_default(monkeypatch):
    # network calls stubbed at the session level: every source must still
    # get exercised (or skipped for a missing key), never crash
    monkeypatch.delenv("GOOGLE_BOOKS_API_KEY", raising=False)
    monkeypatch.delenv("COMICVINE_API_KEY", raising=False)
    monkeypatch.delenv("HARDCOVER_API_KEY", raising=False)
    monkeypatch.setattr("time.sleep", lambda s: None)
    resp = Mock(status_code=200)
    resp.json = Mock(return_value={"docs": [], "products": [], "results": []})
    resp.raise_for_status = Mock()
    http = Mock()
    http.request.return_value = resp
    results = check.run(_http=http)
    assert results["google_books"] == ("SKIP", "GOOGLE_BOOKS_API_KEY not set")
    assert results["comicvine"] == ("SKIP", "COMICVINE_API_KEY not set")
    assert results["hardcover"] == ("SKIP", "HARDCOVER_API_KEY not set")
    for name in ("open_library", "audible", "oreilly"):
        assert results[name][0] == "OK"

def test_check_board_repaints_in_place_then_yields_to_the_report(monkeypatch):
    from humble_catalog import progress as mod
    monkeypatch.setattr(mod, "_enable_ansi", lambda stream: True)
    out = _Tty()
    check.run(sources=_sources("hardcover", "oreilly"), stream=out)
    text = out.getvalue()
    board, report = text.split("\x1b[J", 1)
    # the board starts with everything pending and is rewritten, never re-listed
    assert board.count("hardcover") == 3            # pending + two repaints
    assert "hardcover  ...    oreilly    ..." in board
    assert board.count("\x1b[1A") == 3              # a rewind per resolution + the erase
    # and it is gone by the time the detail lines land
    assert "\x1b[" not in report
    assert "hardcover  OK    1 results" in report
    assert "2 sources: 2 OK, 0 skipped, 0 failed." in report

def test_check_without_a_terminal_prints_only_the_report(capsys):
    check.run(sources=_sources("hardcover", "oreilly"))
    out = capsys.readouterr().out
    assert "\x1b[" not in out
    assert out.count("hardcover") == 1              # no board, no repaints
