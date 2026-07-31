import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone

def _now():
    return datetime.now(timezone.utc).isoformat()

def duration(seconds):
    """Compact wall-clock: 45s, 2m07s, 1h04m. Blank when not yet knowable.

    Public since harvest started formatting how far off a quota reset is
    with it, as stats._console_safe became public on acquiring a second
    caller."""
    if seconds is None:
        return "--"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m"

class Progress:
    """Sequential one-item-at-a-time progress for a single worker.

    On a terminal this is a small tally grid repainted in place, with the
    item being worked on named underneath it; anywhere else it stays one
    appended line per step, exactly as it always was. `tallies` names the
    extra counters a caller wants shown live (see covers: downloaded and
    failed), bumped with count().

    `echo=False` drops the per-step line off the non-terminal path: a
    caller stepping thousands of times (import-sheets, once per
    spreadsheet row) would otherwise turn a piped run that used to print
    a five-line report into a flood, and name every title in the log.
    The live grid is unaffected either way.
    """
    def __init__(self, conn, command, total, phase, tallies=(), stream=None,
                 echo=True):
        self.conn, self.command, self.total, self.phase = conn, command, total, phase
        self.done = 0
        self.current = ""
        self.tallies = {name: 0 for name in tallies}
        self._echo = echo
        self._started = time.monotonic()
        self._detached = False
        self._display = LiveDisplay(stream)
        conn.execute(
            "INSERT OR REPLACE INTO run_status "
            "(command, phase, done, total, current, started_at, updated_at) "
            "VALUES (?,?,0,?,NULL,?,?)",
            (command, phase, total, _now(), _now()))
        conn.commit()
        self._paint()

    def _cells(self):
        pct = f"{100 * self.done // max(self.total, 1):>3}%"
        cells = [f"{self.phase} {self.done:>{len(str(self.total))}}/{self.total} {pct}"]
        cells += [f"{name} {n}" for name, n in self.tallies.items()]
        elapsed = time.monotonic() - self._started
        # An ETA before the first step finishes would be division by zero,
        # and one from a single sample is a lie; both show as "--".
        eta = elapsed / self.done * (self.total - self.done) if self.done else None
        cells.append(f"{duration(elapsed)} elapsed, eta {duration(eta)}")
        return cells

    def detach(self):
        """Freeze the current frame and stop drawing.

        A phase that hands off to another Progress (extract -> covers)
        must let go of its rows first, or its own finish() would later
        rewind over whatever the second one painted underneath it.
        """
        self._detached = True
        self._display.detach()

    def _paint(self):
        if not self._display.live or self._detached:
            return
        rows = grid(self._cells())
        if self.current:
            width = shutil.get_terminal_size((80, 24)).columns
            rows.append(f"  {self.current}"[:width])
        self._display.render(rows)

    def count(self, name, n=1):
        """Bump a named tally (it shows on the next repaint)."""
        self.tallies[name] += n

    def log(self, message):
        self._display.log(message)

    def step(self, current):
        self.done += 1
        self.current = str(current)
        if self._display.live:
            self._paint()
        elif self._echo:
            self._display.write(f"{self.phase} {self.done}/{self.total}: {current}")
        self.conn.execute(
            "UPDATE run_status SET done=?, current=?, updated_at=? WHERE command=?",
            (self.done, current, _now(), self.command))
        self.conn.commit()

    def finish(self, summary):
        self.current = ""  # the run is over; no item is "in progress"
        self._paint()
        self.detach()  # the final tallies stay; the summary goes below
        self._display.write(summary)
        self.conn.execute(
            "UPDATE run_status SET phase='done', updated_at=? WHERE command=?",
            (_now(), self.command))
        self.conn.commit()

MAX_COLUMNS = 3
_GAP = "   "

def _enable_ansi(stream):
    """True when stream can take cursor movement; enables VT on old consoles.

    Windows Terminal handles ANSI out of the box but legacy conhost needs
    ENABLE_VIRTUAL_TERMINAL_PROCESSING flipped on first, so try that once
    and fall back to plain line output if the console refuses.
    """
    try:
        if not stream.isatty():
            return False
    except Exception:  # noqa: BLE001 - a stub stream without isatty
        return False
    if os.environ.get("TERM") == "dumb" or os.environ.get("NO_COLOR"):
        return False
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x4))
    except Exception:  # noqa: BLE001 - no console (pythonw, redirected handle)
        return False

def _column_count(cell_width, cells, term_width):
    """Pick 1-MAX_COLUMNS columns: as many as fit, preferring even rows.

    Three columns for four sources leaves a lonely cell on row two, so a
    count that divides the cells evenly wins over a wider ragged grid.
    """
    fits = max(1, (term_width + len(_GAP)) // (cell_width + len(_GAP)))
    cap = min(MAX_COLUMNS, fits, cells)
    for cols in range(cap, 1, -1):
        if cells % cols == 0:
            return cols
    return cap

def grid(cells):
    """Lay equal-width cells out as 1-MAX_COLUMNS columns of padded rows."""
    if not cells:
        return []
    width = max(len(c) for c in cells)
    cols = _column_count(width, len(cells),
                         shutil.get_terminal_size((80, 24)).columns)
    return [_GAP.join(c.ljust(width) for c in cells[start:start + cols]).rstrip()
            for start in range(0, len(cells), cols)]

class LiveDisplay:
    """A block of terminal lines that can be rewritten where it stands.

    render() repaints over the rows the previous frame occupied, so a
    caller can call it as often as it likes without scrolling. When the
    stream is not a terminal every method is inert, which is what keeps
    piped output and pytest's capture free of escape codes - callers are
    expected to check .live and fall back to plain lines themselves.
    """
    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdout
        self.live = _enable_ansi(self.stream)
        self._rows = []
        self._painted = 0
        self._lock = threading.RLock()

    def render(self, rows):
        if not self.live:
            return
        with self._lock:
            was = self._painted
            self._rows = list(rows)
            out = [f"\x1b[{was}A"] if was else []
            out += [f"\x1b[2K{row}\n" for row in self._rows]
            if len(self._rows) < was:
                # a shorter frame would strand the old tail rows below it
                out.append("\x1b[J")
            self.stream.write("".join(out))
            self.stream.flush()
            self._painted = len(self._rows)

    def erase(self):
        """Take the block back off the screen (it may be re-rendered later)."""
        if not self.live or not self._painted:
            return
        with self._lock:
            self.stream.write(f"\x1b[{self._painted}A\x1b[J")
            self.stream.flush()
            self._painted = 0

    def detach(self):
        """Leave the current frame on screen permanently; stop owning it."""
        with self._lock:
            self._painted = 0

    def write(self, text):
        with self._lock:
            self.stream.write(text + "\n")
            self.stream.flush()

    def log(self, message):
        """Print a message without the block overwriting it, or vice versa."""
        with self._lock:
            painted = self._painted
            self.erase()
            self.write(message)
            if painted:
                self.render(self._rows)

_GLYPHS_ASCII = ("~", "+", "x", "=")
_GLYPHS_UNICODE = ("▸", "✓", "✗", "⏸")

def _glyphs(stream):
    """Per-source state marks: (working, done, failed, paused).

    Prefers the drawn glyphs, but a console that cannot encode them would
    raise mid-repaint, so anything short of a stream that accepts them
    gets the ASCII set.
    """
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return _GLYPHS_ASCII
    try:
        "".join(_GLYPHS_UNICODE).encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return _GLYPHS_ASCII
    return _GLYPHS_UNICODE

class HarvestProgress:
    """Thread-safe per-source progress for the parallel harvest.

    Each source thread calls tick(name) after each title. Updates to the
    single run_status row and to the shared counters are serialized by a
    lock; only one connection (the caller's) is ever written, off the
    worker threads' own connections.

    On a terminal the per-source counters are repainted in place as a
    2-3 column grid; anywhere else (a pipe, a test, a log file) each
    change is appended as its own line, as it always was.

    Each source also carries a state mark, because the count alone is
    ambiguous: a source that stops at 40% may still be working or may
    have given up, and only the mark can say which.
    """
    def __init__(self, conn, totals, stream=None):
        self.conn, self.totals = conn, dict(totals)
        self.done = {name: 0 for name in totals}
        self.state = {name: "working" for name in totals}
        self.total = sum(totals.values())
        self._lock = threading.Lock()
        self._display = LiveDisplay(stream)
        self._glyph = dict(zip(("working", "done", "failed", "paused"),
                               _glyphs(self._display.stream)))
        conn.execute(
            "INSERT OR REPLACE INTO run_status "
            "(command, phase, done, total, current, started_at, updated_at) "
            "VALUES ('harvest','Source',0,?,NULL,?,?)",
            (self.total, _now(), _now()))
        conn.commit()
        self._paint()

    def _cells(self):
        name_w = max((len(n) for n in self.totals), default=0)
        num_w = max((len(str(t)) for t in self.totals.values()), default=1)
        cells = []
        for name in self.totals:
            done, total = self.done[name], self.totals[name]
            pct = f"{100 * done // max(total, 1):>3}%"
            cells.append(f"{name:<{name_w}} {done:>{num_w}}/{total:<{num_w}} "
                         f"{pct} {self._glyph[self.state[name]]}")
        return cells

    def _grid(self):
        return grid(self._cells())

    def _paint(self):
        self._display.render(self._grid())

    def log(self, message):
        """Print a message without the grid overwriting it (or vice versa)."""
        with self._lock:
            self._display.log(message)

    def tick(self, source):
        with self._lock:
            self.done[source] += 1
            total_done = sum(self.done.values())
            if self._display.live:
                self._paint()
            else:
                line = " - ".join(
                    f"{n} {self.done[n]}/{self.totals[n]}"
                    + (" done" if self.done[n] >= self.totals[n] else "")
                    for n in self.totals)
                self._display.write(f"harvest  {line}")
            self.conn.execute(
                "UPDATE run_status SET done=?, current=?, updated_at=? "
                "WHERE command='harvest'", (total_done, source, _now()))
            self.conn.commit()

    def settle(self, source, failed):
        """Retire a source: its pool has stopped, cleanly or not.

        Only the mark changes - the count stays where the source actually
        got to, so a failed source shows how far it got rather than
        rounding itself up to a total it never reached.
        """
        with self._lock:
            self.state[source] = "failed" if failed else "done"
            if self._display.live:
                self._paint()

    def finish(self, incomplete, paused=None, repeats=()):
        """Retire the run. `paused` maps a source name to when its rate
        limit lifts, already formatted for display. `repeats` is a list of
        already-formatted lines naming titles that have failed in more
        than one run - the caller queries and formats them, this only
        writes them.

        A paused source is reported apart from the merely incomplete ones,
        because "rerun 'harvest' to resume" is wrong advice for a source
        that will hit the same 429 immediately.
        """
        paused = paused or {}
        with self._lock:
            for name, state in self.state.items():
                if state == "working":  # no pool ran for it, or none reported
                    self.state[name] = "failed" if name in incomplete else "done"
            # A source with a live quota record is paused however its pool
            # settled. Blocked before the threads started and blocked by
            # its own first 429 are the same condition, and one rule
            # applied here beats two paths that could drift. Without this
            # the first case would read as *done*: a cache-only walk
            # raises CacheMiss, which is not a failure.
            for name in paused:
                if name in self.state:
                    self.state[name] = "paused"
            self._paint()
            self._display.detach()  # the grid is final; the summary goes below
            stalled = sorted(set(incomplete) - set(paused))
            if stalled:
                self._display.write(
                    f"harvest incomplete for: {', '.join(stalled)} "
                    f"(rerun 'harvest' to resume)")
            for name in sorted(paused):
                self._display.write(
                    f"{name} is out of quota until {paused[name]}; "
                    f"rerun 'harvest' after that")
            if not stalled and not paused:
                self._display.write("harvest complete")
            if repeats:
                self._display.write("\nRepeat failures (2+ runs):")
                for line in repeats:
                    self._display.write(line)
            self.conn.execute(
                "UPDATE run_status SET phase='done', updated_at=? "
                "WHERE command='harvest'", (_now(),))
            self.conn.commit()
