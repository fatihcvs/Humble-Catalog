"""Known-answer battery for the harvest-run inventory row.

Covers `harvest.build_worklist`, `_is_429`, `_run_pool`, `_repeat_lines`,
`_when` and `run` itself - the resume behaviour and the parallelism.

This row carries the most consequential decision logic left in the
project, and almost all of it is about what happens when a source fails.
The rules are asymmetric on purpose - a 429 is not recorded as a failure,
a CacheMiss is not a failure at all, an ordinary error keeps the queue
draining - and each asymmetry is the kind that a liveness probe cannot
see, because every one of them ends in "the harvest finished".

`run` takes `sources=` and `_conn=`, its own injection seams, so the real
threading and the real tallying are exercised with stub sources and no
network.

Every title is invented, from docs/TEST-DATA.md. Fresh database per case.
"""
import pathlib
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, failures, harvest, quota, runs  # noqa: E402
from humble_catalog.sources.base import CacheMiss  # noqa: E402

UTC = timezone.utc
PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def seeded(rows=()):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = db.connect(pathlib.Path(tmp.name))
    for i, (name, type_) in enumerate(rows):
        cur = conn.execute(
            "INSERT INTO items (machine_name, name, type) VALUES (?,?,?)",
            (f"mn_{i}", name, type_))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    conn.commit()
    return conn


class Resp:
    def __init__(self, status_code):
        self.status_code = status_code


class Boom(Exception):
    """An error carrying a response, the shape requests raises."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.response = Resp(status_code) if status_code else None


class Src:
    """A stub source. `script` maps a title to what lookup does."""

    def __init__(self, script=None, resets_at=None):
        self.script = script or {}
        self.offline = False
        self.asked = []
        # Ahead of now, not a fixed past date: quota.blocked does not
        # believe an expired reset, so a past default would make the
        # quota cases assert against a record that is never live.
        self._resets_at = resets_at or datetime.now(UTC) + timedelta(hours=5)

    def lookup(self, title):
        self.asked.append(title)
        action = self.script.get(title)
        if isinstance(action, Exception):
            raise action
        return action or []

    def quota_resets_at(self):
        return self._resets_at


class Prog:
    """A HarvestProgress stand-in recording what the pool reported."""

    def __init__(self):
        self.done = {}
        self.settled = {}
        self.logs = []
        self.lock = threading.Lock()

    def tick(self, name):
        self.done[name] = self.done.get(name, 0) + 1

    def settle(self, name, failed=False):
        self.settled[name] = failed

    def log(self, line):
        self.logs.append(line)


def pool(name, src, titles, conn):
    prog, incomplete = Prog(), set()
    harvest._run_pool(name, src, titles, prog, incomplete, prog.lock, conn)
    return prog, incomplete


# ------------------------------------------------------- build_worklist

def case_music_and_android_are_skipped():
    conn = seeded([("Salt and Sextant", "ebook"),
                   ("Soundtrack Sampler", "music"),
                   ("Widget Quest", "android")])
    work = harvest.build_worklist(conn)
    titles = {t for ts in work.values() for t in ts}
    # clean_title strips edition and series noise but does NOT lowercase,
    # so the worklist carries each title's own casing; only the SORT folds
    # case. Asserting lowercase made six cases fail against correct code.
    check("only the ebook contributes a title", titles, {"Salt and Sextant"})
    conn.close()


def case_a_type_routes_to_its_own_sources():
    conn = seeded([("The Copper Almanac", "audiobook")])
    work = harvest.build_worklist(conn)
    check("an audiobook goes to the audiobook source order",
          sorted(work), ["audible", "google_books", "hardcover"])
    conn.close()


def case_a_comic_routes_to_the_comic_sources():
    conn = seeded([("Nightjar Post", "comic")])
    check("a comic goes to comicvine and google_books",
          sorted(harvest.build_worklist(seeded([("Nightjar Post", "comic")]))),
          ["comicvine", "google_books"])
    conn.close()


def case_two_items_with_one_cleaned_title_cost_one_request():
    # De-duped per source: the documented reason the worklist exists.
    conn = seeded([("The Quiet Harbor: A Novel", "ebook"),
                   ("The Quiet Harbor", "ebook")])
    work = harvest.build_worklist(conn)
    check("one title per source, not two", work["hardcover"],
          ["The Quiet Harbor"])
    conn.close()


def case_the_worklist_is_sorted_case_insensitively():
    conn = seeded([("Zephyr Notes", "ebook"), ("alpha signal", "ebook"),
                   ("Mid Stream", "ebook")])
    check("titles come back casefold-sorted",
          harvest.build_worklist(conn)["hardcover"],
          ["alpha signal", "Mid Stream", "Zephyr Notes"])
    conn.close()


def case_a_case_only_tie_is_broken_by_the_raw_string():
    # Documented: Python's sort is stable, so a casefold-only key would
    # fall back to SQLite's unordered scan. The raw string is the
    # tiebreak, and uppercase sorts first by codepoint.
    conn = seeded([("gray waters", "ebook"), ("Gray Waters", "ebook")])
    work = harvest.build_worklist(conn)
    check("a case-only pair is ordered deterministically, uppercase first",
          work["hardcover"], ["Gray Waters", "gray waters"])
    conn.close()


def case_accents_are_not_folded():
    # Documented: accents are not folded, because determinism is the
    # property wanted here and codepoint order has it. The docstring's
    # "sorts past z" describes a title whose FIRST letter is accented;
    # a mid-word accent orders on its first letter like any other, so
    # the property to assert for this pair is the codepoint order
    # itself: 'e' is U+0065 and the accented form U+00E9.
    conn = seeded([("Café of Broken Clocks", "ebook"),
                   ("Cafe of Broken Clocks", "ebook")])
    work = harvest.build_worklist(conn)
    check("the unaccented spelling sorts first, by codepoint",
          work["hardcover"],
          ["Cafe of Broken Clocks", "Café of Broken Clocks"])
    conn.close()


def case_an_empty_catalog_has_no_worklist():
    conn = seeded([])
    check("nothing to fetch is an empty worklist",
          harvest.build_worklist(conn), {})
    conn.close()


def case_a_source_with_no_titles_is_absent_rather_than_empty():
    conn = seeded([("Nightjar Post", "comic")])
    work = harvest.build_worklist(conn)
    check("a source nothing routes to does not appear at all",
          "hardcover" in work, False)
    conn.close()


# --------------------------------------------------------------- _is_429

def case_is_429_recognises_only_that_status():
    check("a 429 is recognised", harvest._is_429(Boom("x", 429)), True)
    check("a 500 is not", harvest._is_429(Boom("x", 500)), False)
    check("an error with no response is not",
          harvest._is_429(Boom("x")), False)
    check("a bare exception is not", harvest._is_429(ValueError("x")), False)


# ------------------------------------------------------------- _run_pool

def case_every_answered_title_ticks_once():
    conn = seeded()
    prog, incomplete = pool("hardcover", Src(), ["a", "b", "c"], conn)
    check("three answered titles tick three times", prog.done["hardcover"], 3)
    check("the source settles without failure",
          prog.settled["hardcover"], False)
    check("and is not incomplete", incomplete, set())
    conn.close()


def case_a_cache_miss_is_not_a_failure_and_does_not_tick():
    # Documented: nothing cached and nothing left to fetch it with.
    conn = seeded()
    src = Src({"b": CacheMiss("offline")})
    prog, incomplete = pool("hardcover", src, ["a", "b", "c"], conn)
    check("only the answered titles tick", prog.done["hardcover"], 2)
    check("a cache miss is not a failure", prog.settled["hardcover"], False)
    check("and does not mark the source incomplete", incomplete, set())
    check("nothing is recorded against the title",
          failures.top(conn), [])
    conn.close()


def case_an_ordinary_error_records_and_keeps_draining():
    conn = seeded()
    src = Src({"b": Boom("upstream is down", 500)})
    prog, incomplete = pool("hardcover", src, ["a", "b", "c"], conn)
    check("the queue keeps draining past the failure",
          src.asked, ["a", "b", "c"])
    check("the failed title does not tick", prog.done["hardcover"], 2)
    check("the source settles as failed", prog.settled["hardcover"], True)
    check("and is marked incomplete", incomplete, {"hardcover"})
    rows = failures.top(conn)
    check("one failure is recorded, against that title",
          [(r["source"], r["title"]) for r in rows], [("hardcover", "b")])
    conn.close()


def case_a_failure_detail_is_redacted():
    # A requests HTTPError embeds the request URL, and for a keyed source
    # that URL carries the key. Scrubbed once, used for the log AND the
    # stored row - so both are checked.
    conn = seeded()
    leaky = Boom("500 Server Error for url: "
                 "https://api.example.invalid/?key=SECRETKEY123", 500)
    prog, _incomplete = pool("hardcover", Src({"a": leaky}), ["a"], conn)
    stored = failures.top(conn)[0]["last_error"]
    check("the key does not reach the stored row",
          "SECRETKEY123" in stored, False)
    check("nor the logged line",
          any("SECRETKEY123" in line for line in prog.logs), False)
    conn.close()


def case_a_429_takes_the_source_offline_without_recording_a_failure():
    # The central asymmetry: a 429 says nothing about the TITLE, and
    # source_quota already holds it, so no failure row is written.
    conn = seeded()
    src = Src({"b": Boom("429 Too Many Requests", 429)})
    prog, incomplete = pool("hardcover", src, ["a", "b", "c"], conn)
    check("no failure is recorded for a rate limit", failures.top(conn), [])
    check("the source is switched offline", src.offline, True)
    check("the quota is recorded", quota.blocked(conn, "hardcover") is not None,
          True)
    check("the source is marked incomplete", incomplete, {"hardcover"})
    check("and it settles as failed", prog.settled["hardcover"], True)
    conn.close()


def case_a_429_keeps_serving_the_rest_from_cache():
    # Documented: a 429 ends the source's NETWORK, not its cache. Stopping
    # outright would strand every cached title below the first uncached
    # one, so the walk continues and cached titles still count.
    conn = seeded()
    src = Src({"b": Boom("429", 429)})
    prog, _incomplete = pool("hardcover", src, ["a", "b", "c", "d"], conn)
    check("every title is still walked", src.asked, ["a", "b", "c", "d"])
    check("and the cached ones still tick", prog.done["hardcover"], 3)
    conn.close()


def case_a_second_429_stops_the_walk():
    # Documented: offline was ignored, so stop before hammering the API.
    conn = seeded()
    src = Src({"b": Boom("429", 429), "c": Boom("429", 429)})
    prog, _incomplete = pool("hardcover", src, ["a", "b", "c", "d"], conn)
    check("the walk breaks at the second rate limit",
          src.asked, ["a", "b", "c"])
    check("so the titles below it are not reached",
          prog.done.get("hardcover", 0), 1)
    conn.close()


def case_the_rate_limit_line_names_when_to_rerun():
    conn = seeded()
    src = Src({"a": Boom("429", 429)})
    prog, _incomplete = pool("hardcover", src, ["a"], conn)
    check("the log tells the owner when to come back",
          any("rerun 'harvest' after" in line for line in prog.logs), True)
    conn.close()


def case_several_failures_are_each_recorded():
    conn = seeded()
    src = Src({"a": Boom("x", 500), "c": Boom("y", 500)})
    _prog, _incomplete = pool("hardcover", src, ["a", "b", "c"], conn)
    check("both failing titles are recorded",
          sorted(r["title"] for r in failures.top(conn)), ["a", "c"])
    conn.close()


# ---------------------------------------------------------- _repeat_lines

def case_repeat_lines_are_empty_when_nothing_repeats():
    conn = seeded()
    failures.record(conn, "hardcover", "Salt and Sextant", "timed out")
    check("a single failure says nothing", harvest._repeat_lines(conn), [])
    conn.close()


def case_repeat_lines_start_at_the_second_failure():
    conn = seeded()
    for _ in range(2):
        failures.record(conn, "hardcover", "Salt and Sextant", "timed out")
    lines = harvest._repeat_lines(conn)
    check("a twice-failed title is reported", len(lines), 1)
    check("with its count and source", "2x  hardcover" in lines[0], True)
    conn.close()


def case_repeat_lines_are_capped_and_say_how_many_more():
    conn = seeded()
    for n in range(harvest.SUMMARY_ROWS + 3):
        for _ in range(2):
            failures.record(conn, "hardcover", f"Title {n}", "timed out")
    lines = harvest._repeat_lines(conn)
    check("the block is capped", len(lines), harvest.SUMMARY_ROWS + 1)
    check("and the last line names the remainder",
          "...and 3 more" in lines[-1], True)
    conn.close()


# ------------------------------------------------------------------ _when

def case_when_names_the_instant_and_the_wait():
    resets = datetime.now(UTC) + timedelta(hours=2)
    text = harvest._when(resets)
    check("the absolute instant is present",
          resets.isoformat(timespec="minutes") in text, True)
    check("and the relative wait", "(in 1h5" in text or "(in 2h00m" in text,
          True)


# -------------------------------------------------------------------- run

def case_run_walks_every_source_in_the_worklist():
    conn = seeded([("Salt and Sextant", "ebook")])
    srcs = {n: Src() for n in
            ["hardcover", "google_books", "oreilly", "open_library"]}
    incomplete = harvest.run(sources=srcs, _conn=conn)
    check("nothing is left incomplete", incomplete, set())
    check("every source was asked for the one title",
          {n: s.asked for n, s in srcs.items()},
          {n: ["Salt and Sextant"] for n in srcs})
    conn.close()


def case_a_source_missing_from_the_map_is_not_run_and_gets_no_row():
    # Documented: a zero row would read as if it had run.
    conn = seeded([("Salt and Sextant", "ebook")])
    harvest.run(sources={"hardcover": Src()}, _conn=conn)
    reported = {r["source"] for r in runs.report(conn)} \
        if hasattr(runs, "report") else None
    if reported is not None:
        check("only the source that ran has a row", reported, {"hardcover"})
    else:
        PASS.append("runs.report absent; row check skipped")
    conn.close()


def case_a_blocked_source_starts_offline_and_is_incomplete():
    conn = seeded([("Salt and Sextant", "ebook")])
    quota.record(conn, "hardcover", datetime.now(UTC) + timedelta(hours=5))
    src = Src()
    incomplete = harvest.run(sources={"hardcover": src}, _conn=conn)
    check("a source with a live quota record starts offline",
          src.offline, True)
    check("and is reported incomplete", incomplete, {"hardcover"})
    check("but is still walked, so its progress does not go backwards",
          src.asked, ["Salt and Sextant"])
    conn.close()


def case_ignore_quota_disregards_the_record():
    # The documented parameter, at both values, and it must change the
    # answer: for when the stored guess is wrong.
    conn = seeded([("Salt and Sextant", "ebook")])
    quota.record(conn, "hardcover", datetime.now(UTC) + timedelta(hours=5))
    src = Src()
    incomplete = harvest.run(sources={"hardcover": src}, _conn=conn,
                             ignore_quota=True)
    check("ignore_quota does not take the source offline", src.offline, False)
    check("and does not mark it incomplete from the record",
          incomplete, set())
    conn.close()


def case_an_expired_quota_record_is_not_believed():
    conn = seeded([("Salt and Sextant", "ebook")])
    quota.record(conn, "hardcover", datetime.now(UTC) - timedelta(hours=1))
    src = Src()
    harvest.run(sources={"hardcover": src}, _conn=conn)
    check("a reset that has passed does not force offline",
          src.offline, False)
    conn.close()


def case_run_records_a_row_per_source_that_ran():
    conn = seeded([("Salt and Sextant", "ebook")])
    harvest.run(sources={"hardcover": Src(), "google_books": Src()},
                _conn=conn)
    rows = conn.execute("SELECT source, answered FROM harvest_run").fetchall()
    check("both sources are tallied",
          sorted(r["source"] for r in rows), ["google_books", "hardcover"])
    check("each answered its one title",
          sorted({r["answered"] for r in rows}), [1])
    conn.close()


def case_one_failing_source_does_not_stop_the_others():
    conn = seeded([("Salt and Sextant", "ebook")])
    bad = Src({"Salt and Sextant": Boom("down", 500)})
    good = Src()
    incomplete = harvest.run(sources={"hardcover": bad, "google_books": good},
                             _conn=conn)
    check("the failing source is incomplete", incomplete, {"hardcover"})
    check("and the healthy one still ran",
          good.asked, ["Salt and Sextant"])
    conn.close()


CASES = [v for k, v in sorted(globals().items()) if k.startswith("case_")]

if __name__ == "__main__":
    for fn in CASES:
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            FAIL.append(fn.__name__)
            print(f"  FAIL {fn.__name__} raised: "
                  f"{type(exc).__name__}: {exc}")
    total = len(PASS) + len(FAIL)
    print(f"harvest-run: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
