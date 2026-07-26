import io
import os
import re

from humble_catalog import db
from humble_catalog.progress import HarvestProgress, Progress, _column_count

class _Tty(io.StringIO):
    """A stream that claims to be a terminal so the grid path is exercised."""
    def isatty(self):
        return True

def test_progress_writes_status_and_prints(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    prog = Progress(conn, "extract", total=2, phase="Bundle")
    prog.step("First Bundle")
    row = conn.execute("SELECT * FROM run_status WHERE command='extract'").fetchone()
    assert (row["done"], row["total"], row["current"]) == (1, 2, "First Bundle")
    assert "Bundle 1/2: First Bundle" in capsys.readouterr().out
    prog.step("Second Bundle")
    prog.finish("All done.")
    row = conn.execute("SELECT * FROM run_status WHERE command='extract'").fetchone()
    assert row["phase"] == "done" and row["done"] == 2
    assert "All done." in capsys.readouterr().out

def test_progress_grid_paints_tallies_and_the_current_item(tmp_path, monkeypatch):
    from humble_catalog import progress as mod
    monkeypatch.setattr(mod, "_enable_ansi", lambda stream: True)
    conn = db.connect(tmp_path / "t.db")
    out = _Tty()
    prog = Progress(conn, "extract", total=4, phase="Cover",
                    tallies=("saved", "failed"), stream=out)
    prog.step("Gray Waters")
    prog.count("saved")
    prog.step("Shadow Hound")
    frame = re.split(r"\x1b\[\d+A", out.getvalue())[-1]  # only the last repaint
    assert "Cover 2/4  50%" in frame
    assert "saved 1" in frame and "failed 0" in frame
    assert "  Shadow Hound" in frame          # named on its own row below

def test_progress_finish_drops_the_item_row_without_stranding_it(tmp_path, monkeypatch):
    from humble_catalog import progress as mod
    monkeypatch.setattr(mod, "_enable_ansi", lambda stream: True)
    conn = db.connect(tmp_path / "t.db")
    out = _Tty()
    prog = Progress(conn, "extract", total=1, phase="Cover", stream=out)
    prog.step("Gray Waters")
    out.truncate(0), out.seek(0)
    prog.finish("Done.")
    frame = out.getvalue()
    assert "Gray Waters" not in frame
    assert "\x1b[J" in frame                  # the vacated row is cleared, not left behind
    assert frame.endswith("Done.\n")

def test_progress_detach_stops_a_finished_phase_repainting(tmp_path, monkeypatch):
    # extract hands off to the cover phase; its finish() must not rewind
    # over the block the cover phase painted underneath it
    from humble_catalog import progress as mod
    monkeypatch.setattr(mod, "_enable_ansi", lambda stream: True)
    conn = db.connect(tmp_path / "t.db")
    out = _Tty()
    prog = Progress(conn, "extract", total=1, phase="Bundle", stream=out)
    prog.step("First Bundle")
    prog.detach()
    out.truncate(0), out.seek(0)
    prog.finish("Fetched 1 new bundle.")
    assert out.getvalue() == "Fetched 1 new bundle.\n"

def _live(monkeypatch, tmp_path, totals, width=100):
    """A HarvestProgress painting into a fake terminal of a known width."""
    import shutil
    from humble_catalog import progress as mod
    monkeypatch.setattr(mod, "_enable_ansi", lambda stream: True)
    monkeypatch.setattr(shutil, "get_terminal_size",
                        lambda fallback=(80, 24): os.terminal_size((width, 24)))
    conn = db.connect(tmp_path / "t.db")
    out = _Tty()
    return conn, out, HarvestProgress(conn, totals, stream=out)

def test_harvest_grid_paints_in_place(tmp_path, monkeypatch):
    totals = {"hardcover": 4, "google_books": 4, "oreilly": 2, "open_library": 2}
    conn, out, prog = _live(monkeypatch, tmp_path, totals)
    assert out.getvalue().count("\n") == 2      # 4 sources -> 2 rows of 2
    out.truncate(0), out.seek(0)
    prog.tick("hardcover")
    frame = out.getvalue()
    assert frame.startswith("\x1b[2A")          # rewinds over its own 2 rows
    assert frame.count("\n") == 2               # and repaints, adding no lines
    assert "hardcover    1/4  25%" in frame
    assert "google_books 0/4   0%" in frame

def _frame(out):
    """The last repaint only, with the rewind escape stripped."""
    return re.split(r"\x1b\[\d+A", out.getvalue())[-1]

def test_harvest_grid_marks_each_source_working_done_or_failed(tmp_path, monkeypatch):
    # The count says how much data we hold; the symbol says whether the
    # source is still going. A stalled source reads as failed at 40%,
    # not as a bar that mysteriously stopped climbing.
    conn, out, prog = _live(monkeypatch, tmp_path, {"oreilly": 2, "audible": 3})
    prog.tick("oreilly")
    assert "oreilly 1/2  50% ~" in _frame(out)   # still going
    prog.tick("oreilly")
    prog.settle("oreilly", failed=False)
    prog.settle("audible", failed=True)
    frame = _frame(out)
    assert "oreilly 2/2 100% +" in frame
    assert "audible 0/3   0% x" in frame

def test_harvest_finish_settles_any_source_its_pool_never_reached(tmp_path, monkeypatch):
    conn, out, prog = _live(monkeypatch, tmp_path, {"oreilly": 2, "audible": 3})
    prog.finish({"audible"})
    frame = _frame(out)
    assert "oreilly 0/2   0% +" in frame
    assert "audible 0/3   0% x" in frame

def test_grid_glyphs_fall_back_to_ascii_when_the_console_cannot_encode(tmp_path):
    from humble_catalog.progress import _glyphs
    assert _glyphs(io.StringIO()) == ("~", "+", "x", "=")     # no .encoding at all
    class _Cp1252(io.StringIO):
        encoding = "cp1252"
    class _Utf8(io.StringIO):
        encoding = "utf-8"
    # All four or none: the set is tested for encodability as a whole, so
    # a console that cannot take the paused mark loses the other three too.
    assert _glyphs(_Cp1252()) == ("~", "+", "x", "=")
    assert _glyphs(_Utf8()) == ("▸", "✓", "✗", "⏸")

def test_harvest_log_message_survives_the_repaint(tmp_path, monkeypatch):
    conn, out, prog = _live(monkeypatch, tmp_path, {"oreilly": 2, "audible": 3})
    out.truncate(0), out.seek(0)
    prog.log("  audible: rate limit hit")
    frame = out.getvalue()
    assert frame.startswith("\x1b[1A\x1b[J")    # erase the grid, then log, then repaint
    assert frame.index("rate limit hit") < frame.index("oreilly")

def test_harvest_falls_back_to_lines_without_a_terminal(tmp_path, capsys):
    conn = db.connect(tmp_path / "t.db")
    prog = HarvestProgress(conn, {"oreilly": 2, "audible": 1})
    prog.tick("oreilly")
    prog.finish(set())
    out = capsys.readouterr().out
    assert "harvest  oreilly 1/2 - audible 0/1" in out
    assert "\x1b[" not in out
    assert "harvest complete" in out

def test_column_count_prefers_even_rows_and_respects_width():
    assert _column_count(20, 6, 100) == 3       # fits three, divides evenly
    assert _column_count(20, 4, 100) == 2       # three would leave a lonely cell
    assert _column_count(20, 6, 45) == 2        # only two fit in 45 columns
    assert _column_count(20, 6, 20) == 1

def test_harvest_finish_marks_a_quota_paused_source_paused_not_done(tmp_path, monkeypatch):
    # A source out of quota is neither done nor failed, and the count
    # alone cannot say which - which is the reason the marks exist. It
    # would otherwise read as done: a cache-only walk raises CacheMiss,
    # which is not a failure, so its pool settles cleanly.
    conn, out, prog = _live(monkeypatch, tmp_path, {"oreilly": 2, "audible": 3})
    prog.settle("audible", failed=False)
    prog.finish({"audible"}, paused={"audible": "2026-07-27T08:00:00+00:00"})
    frame = _frame(out)
    assert "audible 0/3   0% =" in frame     # paused, not "+"
    assert "oreilly 0/2   0% +" in frame     # untouched

def test_harvest_finish_names_a_paused_source_with_its_reset_time(tmp_path, monkeypatch):
    # "rerun 'harvest' to resume" is wrong advice for a source that will
    # 429 again immediately, so paused sources get their own line.
    conn, out, prog = _live(monkeypatch, tmp_path, {"audible": 3})
    prog.finish({"audible"}, paused={"audible": "2026-07-27T08:00:00+00:00"})
    tail = out.getvalue()
    assert "audible" in tail and "2026-07-27T08:00" in tail
    assert "out of quota" in tail
