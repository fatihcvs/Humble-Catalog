"""Known-answer battery for the harvest-reports inventory row.

Covers `humble_catalog/runs.py` and `harvest.report_runs`,
`report_failures`, `forget_runs`.

Two things here are worth more than the arithmetic.

First, the trim is counted in RUNS, not rows. A run is one started_at
spread over up to six sources, so trimming rows would behead a run
mid-way and leave a partial record that reads as a complete one.

Second, this row carries a PRIVACY contract stated in the code: the runs
report holds source names, counts and timestamps and never a title, which
is what makes it safe to paste into an issue, while `report_failures`
prints real titles and is not. That distinction is asserted directly,
because it is the kind that rots silently when a column is added.

Every title is invented, from docs/TEST-DATA.md. Fresh database per case.
"""
import io
import contextlib
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, failures, harvest, runs  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return db.connect(pathlib.Path(tmp.name))


def capture(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


def tally(answered=10, succeeded=8, failed=2, died=False):
    return (answered, succeeded, failed, died)


# -------------------------------------------------------------- runs.record

def case_one_row_per_source_is_written():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "2026-08-01T10:05:00",
                {"hardcover": tally(), "google_books": tally()})
    rows = runs.history(conn)
    check("both sources are recorded", len(rows), 2)
    check("with the run's own start and end",
          {(r["started_at"], r["ended_at"]) for r in rows},
          {("2026-08-01T10:00:00", "2026-08-01T10:05:00")})
    conn.close()


def case_the_counts_round_trip():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "2026-08-01T10:05:00",
                {"hardcover": (100, 90, 10, True)})
    row = runs.history(conn)[0]
    check("answered", row["answered"], 100)
    check("succeeded", row["succeeded"], 90)
    check("failed", row["failed"], 10)
    check("and the quota flag is stored as an int", row["quota_died"], 1)
    conn.close()


def case_history_is_newest_run_first_then_source_by_name():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x", {"zulu": tally()})
    runs.record(conn, "2026-08-02T10:00:00", "x",
                {"bravo": tally(), "alpha": tally()})
    rows = runs.history(conn)
    check("the newest run leads, its sources sorted by name",
          [(r["started_at"][:10], r["source"]) for r in rows],
          [("2026-08-02", "alpha"), ("2026-08-02", "bravo"),
           ("2026-08-01", "zulu")])
    conn.close()


def case_the_trim_counts_runs_not_rows():
    """The documented reason `keep` exists as a parameter.

    A run is one started_at over up to six sources. Trimming ROWS would
    behead a run mid-way and leave a partial record reading as a whole
    one; trimming RUNS keeps each surviving run intact.
    """
    conn = fresh()
    for day in range(1, 5):
        runs.record(conn, f"2026-08-0{day}T10:00:00", "x",
                    {"alpha": tally(), "bravo": tally(), "charlie": tally()},
                    keep=2)
    rows = runs.history(conn)
    starts = sorted({r["started_at"][:10] for r in rows})
    check("only the two newest runs survive", starts,
          ["2026-08-03", "2026-08-04"])
    check("and each survives WHOLE, all three sources",
          len(rows), 6)
    conn.close()


def case_re_recording_one_run_replaces_rather_than_duplicates():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x", {"alpha": tally(10, 8, 2)})
    runs.record(conn, "2026-08-01T10:00:00", "y", {"alpha": tally(20, 20, 0)})
    rows = runs.history(conn)
    check("one row for the source", len(rows), 1)
    check("carrying the later numbers", rows[0]["answered"], 20)
    conn.close()


def case_an_empty_tally_records_nothing():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x", {})
    check("a run with no sources writes no rows", runs.history(conn), [])
    conn.close()


# ------------------------------------------------------------- runs.forget

def case_forget_counts_runs_not_rows():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x",
                {"alpha": tally(), "bravo": tally()})
    runs.record(conn, "2026-08-02T10:00:00", "x", {"alpha": tally()})
    check("two runs are reported dropped, not three rows",
          runs.forget(conn), 2)
    check("and the table is empty", runs.history(conn), [])
    conn.close()


def case_forgetting_nothing_reports_zero():
    conn = fresh()
    check("an empty table drops nothing", runs.forget(conn), 0)
    conn.close()


# --------------------------------------------------------- report_runs

def case_an_empty_history_says_so():
    conn = fresh()
    check("the empty case is stated rather than printing a bare header",
          "No harvest runs recorded." in capture(harvest.report_runs, _conn=conn),
          True)
    conn.close()


def case_the_failure_rate_is_computed_over_attempts():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x",
                {"alpha": (100, 75, 25, False)})
    out = capture(harvest.report_runs, _conn=conn)
    check("25 failures of 100 attempts prints as 25%", "25%" in out, True)
    conn.close()


def case_a_cache_only_source_has_no_rate_at_all():
    """Documented: printing 0% would claim it never fails.

    A source that made no live requests has no denominator, and the
    distinction between "never failed" and "never tried" is the whole
    point of the dash.
    """
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x", {"alpha": (50, 0, 0, False)})
    out = capture(harvest.report_runs, _conn=conn)
    check("no attempts prints a dash", " - " in out or out.rstrip().endswith("-"),
          True)
    check("and never 0%", "0%" in out, False)
    conn.close()


def case_a_spent_quota_is_marked():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x", {"alpha": (10, 8, 2, True)})
    check("a run whose quota died says so",
          "spent" in capture(harvest.report_runs, _conn=conn), True)
    conn.close()


def case_a_healthy_run_is_not_marked_spent():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x", {"alpha": (10, 10, 0, False)})
    check("a run that kept its quota is unmarked",
          "spent" in capture(harvest.report_runs, _conn=conn), False)
    conn.close()


def case_the_runs_report_names_no_title():
    """The privacy contract stated in report_runs' own docstring.

    The table holds source names, counts and timestamps and never a
    title, which is what makes this output safe to paste into an issue.
    Asserted against a catalog whose failure table DOES hold a title, so
    a column added later that leaked one would fail here.
    """
    conn = fresh()
    failures.record(conn, "hardcover", "Salt and Sextant", "timed out")
    runs.record(conn, "2026-08-01T10:00:00", "x", {"hardcover": tally()})
    out = capture(harvest.report_runs, _conn=conn)
    check("no title appears in the runs report",
          "Salt and Sextant" in out, False)
    check("while the source name does", "hardcover" in out, True)
    conn.close()


def case_forget_runs_reports_the_count_it_dropped():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x", {"alpha": tally()})
    runs.record(conn, "2026-08-02T10:00:00", "x", {"alpha": tally()})
    check("the plural form is used for two",
          "Forgot 2 recorded runs." in capture(harvest.forget_runs, _conn=conn),
          True)
    conn.close()


def case_forget_runs_uses_the_singular_for_one():
    conn = fresh()
    runs.record(conn, "2026-08-01T10:00:00", "x", {"alpha": tally()})
    check("one run is singular",
          "Forgot 1 recorded run." in capture(harvest.forget_runs, _conn=conn),
          True)
    conn.close()


# ------------------------------------------------------- report_failures

def case_report_failures_lists_the_persistent_ones_first():
    conn = fresh()
    for _ in range(3):
        failures.record(conn, "hardcover", "Nightjar Post", "timed out")
    failures.record(conn, "hardcover", "Salt and Sextant", "timed out")
    out = capture(harvest.report_failures, _conn=conn)
    check("both titles are listed",
          "Nightjar Post" in out and "Salt and Sextant" in out, True)
    check("the most persistent leads",
          out.index("Nightjar Post") < out.index("Salt and Sextant"), True)
    conn.close()


def case_report_failures_says_so_when_there_is_nothing():
    conn = fresh()
    out = capture(harvest.report_failures, _conn=conn)
    check("an empty failure table produces a stated result rather than a header",
          len(out.strip()) > 0, True)
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
    print(f"harvest-reports: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
