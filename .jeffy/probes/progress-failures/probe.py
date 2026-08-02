"""Known-answer battery for the progress-failures inventory row.

Covers `humble_catalog/progress.py` (`duration`, `_column_count`, `grid`)
and `humble_catalog/failures.py` (`record`, `top`, `error_kind`,
`count_since`).

Both modules compute values that are then PRINTED, which is the case the
Method warns about hardest: a wrong duration or a miscounted failure tally
looks exactly like a right one on a terminal. Every expected string and
count below is written out by hand from the documented contract, never
recorded from a run.

Titles are invented, from docs/TEST-DATA.md. Fresh database per case.
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, failures, progress  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return db.connect(pathlib.Path(tmp.name))


# ---------------------------------------------------------------- duration

def case_duration_formats_each_documented_band():
    # The docstring gives three shapes - 45s, 2m07s, 1h04m - so all three
    # are pinned, plus the boundary between each pair.
    cases = [
        (None, "--"),          # not yet knowable
        (0, "0s"),
        (45, "45s"),
        (59, "59s"),           # last second of the bare-seconds band
        (60, "1m00s"),         # first of the minutes band
        (127, "2m07s"),        # the docstring's own example
        (3599, "59m59s"),      # last of the minutes band
        (3600, "1h00m"),       # first of the hours band
        (3840, "1h04m"),       # the docstring's other example
        (86399, "23h59m"),
        (90000, "25h00m"),     # no day rollover: hours keep accumulating
    ]
    for seconds, want in cases:
        check(f"duration({seconds!r}) is {want!r}",
              progress.duration(seconds), want)


def case_duration_pads_seconds_and_minutes_to_two_digits():
    # The padding is what keeps a column of durations aligned; without it
    # "2m7s" and "2m07s" differ in width and the grid ragged.
    check("seconds are zero-padded inside the minutes band",
          progress.duration(61), "1m01s")
    check("minutes are zero-padded inside the hours band",
          progress.duration(3660), "1h01m")


def case_duration_truncates_rather_than_rounding():
    # int() truncates, so 119 seconds is 1m59s and never 2m00s: a
    # progress line must not claim more elapsed time than has elapsed.
    check("119 seconds is 1m59s", progress.duration(119), "1m59s")
    check("a fractional second is truncated",
          progress.duration(59.9), "59s")


# ------------------------------------------------------------ column layout

def case_column_count_prefers_an_even_grid():
    # The documented rule: three columns for four cells leaves a lonely
    # cell on row two, so a count that divides evenly wins over a wider
    # ragged one. Width 10 and terminal 80 fit 3 columns comfortably.
    check("4 cells that fit 3 columns lay out as 2, which divides evenly",
          progress._column_count(10, 4, 80), 2)
    check("6 cells take the full 3 columns", progress._column_count(10, 6, 80), 3)
    check("3 cells take 3 columns", progress._column_count(10, 3, 80), 3)


def case_column_count_never_exceeds_the_cell_count():
    check("2 cells never make 3 columns",
          progress._column_count(10, 2, 80), 2)
    check("1 cell is 1 column", progress._column_count(10, 1, 80), 1)


def case_column_count_is_capped_by_the_terminal_width():
    # A narrow terminal must win over the preference for more columns.
    check("a narrow terminal forces one column",
          progress._column_count(30, 6, 40), 1)
    check("a wide cell in a wide terminal still caps at MAX_COLUMNS",
          progress._column_count(10, 12, 500), progress.MAX_COLUMNS)


def case_column_count_never_returns_zero():
    # max(1, ...) is the guard: a cell wider than the terminal must still
    # be laid out on one column rather than on none, which would divide
    # by zero in grid().
    check("a cell wider than the terminal still gets one column",
          progress._column_count(200, 3, 40), 1)


def case_grid_pads_cells_to_a_common_width():
    # Written out exactly rather than asserted structurally: the longest
    # cell (4) sets the width, cells are ljust to it, joined by a 3-space
    # gap, and the row is rstripped. Three cells fit one row of three.
    #
    # Spelled as a literal because a structural assertion here is easy to
    # get wrong - padding and the gap run together, so splitting the row
    # on the gap does NOT recover the cells.
    check("three short cells lay out as one padded row",
          progress.grid(["a", "bbbb", "cc"]), ["a      bbbb   cc"])
    check("and a single cell needs no padding at all",
          progress.grid(["only"]), ["only"])


def case_grid_of_nothing_is_nothing():
    check("an empty cell list lays out as no rows", progress.grid([]), [])


def case_grid_keeps_every_cell_and_its_order():
    cells = [f"c{i}" for i in range(7)]
    rows = progress.grid(cells)
    flat = [c for row in rows for c in row.split() if c]
    check("no cell is dropped or reordered by the layout", flat, cells)


def case_grid_rows_carry_no_trailing_space():
    # rstrip on each row: a padded final cell would leave trailing
    # whitespace that shows up in a diff and in a copied terminal buffer.
    rows = progress.grid(["a", "bbbb", "cc"])
    check("no row ends in whitespace",
          [r for r in rows if r != r.rstrip()], [])


# -------------------------------------------------------------- error_kind

def case_error_kind_cuts_the_url_that_carries_the_title():
    # The whole point: a requests HTTP error ends in " for url: <url>",
    # and that url holds the title, so grouping on the full string would
    # tally one of everything.
    error = ("503 Server Error: Service Unavailable for url: "
             "https://example.invalid/search?q=Salt+and+Sextant")
    check("the url and everything after it is cut",
          failures.error_kind(error),
          "503 Server Error: Service Unavailable")


def case_two_titles_with_the_same_fault_group_together():
    # The property the function exists for, asserted as a property.
    a = failures.error_kind("503 Server Error: x for url: https://e/?q=Alpha")
    b = failures.error_kind("503 Server Error: x for url: https://e/?q=Beta")
    check("two titles failing the same way group to one kind", a, b)


def case_an_error_without_the_marker_is_unchanged():
    check("an error carrying no url marker survives whole",
          failures.error_kind("Connection reset by peer"),
          "Connection reset by peer")


def case_error_kind_strips_surrounding_space():
    check("the result is stripped",
          failures.error_kind("  timed out  "), "timed out")


# ------------------------------------------------------- record / top / count

def case_recording_the_same_title_twice_increments_rather_than_duplicating():
    conn = fresh()
    failures.record(conn, "example_source", "Salt and Sextant", "timed out")
    failures.record(conn, "example_source", "Salt and Sextant", "timed out")
    rows = failures.top(conn)
    check("one row, not two", len(rows), 1)
    check("and the count is 2", rows[0]["failures"], 2)
    conn.close()


def case_first_failed_at_is_kept_while_last_moves():
    conn = fresh()
    failures.record(conn, "example_source", "Salt and Sextant", "timed out")
    first = failures.top(conn)[0]["first_failed_at"]
    failures.record(conn, "example_source", "Salt and Sextant", "gone")
    row = failures.top(conn)[0]
    check("the first failure time is preserved", row["first_failed_at"], first)
    check("the latest error replaces the old one", row["last_error"], "gone")
    check("and the last failure time is at or after the first",
          row["last_failed_at"] >= first, True)
    conn.close()


def case_two_sources_failing_one_title_are_two_rows():
    # The primary key is (source, title): the same book failing at two
    # sources is two independent facts.
    conn = fresh()
    failures.record(conn, "source_a", "Salt and Sextant", "timed out")
    failures.record(conn, "source_b", "Salt and Sextant", "timed out")
    check("one title failing at two sources is two rows",
          len(failures.top(conn)), 2)
    conn.close()


def case_top_orders_most_persistent_first():
    conn = fresh()
    for _ in range(3):
        failures.record(conn, "example_source", "Nightjar Post", "timed out")
    failures.record(conn, "example_source", "Salt and Sextant", "timed out")
    for _ in range(2):
        failures.record(conn, "example_source", "Unrelated Book", "timed out")
    check("rows come back by failure count, descending",
          [r["failures"] for r in failures.top(conn)], [3, 2, 1])
    conn.close()


def case_min_failures_parameter_at_two_values():
    # The documented parameter, at the two values its docstring names, and
    # it must change the answer.
    conn = fresh()
    failures.record(conn, "example_source", "Salt and Sextant", "timed out")
    for _ in range(2):
        failures.record(conn, "example_source", "Nightjar Post", "timed out")
    check("min_failures=1 is everything", len(failures.top(conn, 1)), 2)
    check("min_failures=2 is the beginning of evidence",
          [r["title"] for r in failures.top(conn, 2)], ["Nightjar Post"])
    check("min_failures=3 excludes both", failures.top(conn, 3), [])
    conn.close()


def case_min_failures_defaults_to_one():
    conn = fresh()
    failures.record(conn, "example_source", "Salt and Sextant", "timed out")
    check("the default view shows a single failure",
          len(failures.top(conn)), 1)
    conn.close()


def case_count_since_counts_titles_not_failures():
    # Documented: how many of a source's TITLES failed at or after a time.
    # A title failing three times is still one title.
    conn = fresh()
    for _ in range(3):
        failures.record(conn, "example_source", "Nightjar Post", "timed out")
    failures.record(conn, "example_source", "Salt and Sextant", "timed out")
    check("three failures of one title count once",
          failures.count_since(conn, "example_source", "1970-01-01"), 2)
    conn.close()


def case_count_since_is_scoped_to_one_source():
    conn = fresh()
    failures.record(conn, "source_a", "Salt and Sextant", "timed out")
    failures.record(conn, "source_b", "Nightjar Post", "timed out")
    check("another source's failures are not counted",
          failures.count_since(conn, "source_a", "1970-01-01"), 1)
    conn.close()


def case_count_since_boundary_is_inclusive():
    # "at or after", so the stamp of the failure itself must count.
    conn = fresh()
    failures.record(conn, "example_source", "Salt and Sextant", "timed out")
    stamp = failures.top(conn)[0]["last_failed_at"]
    check("a window starting exactly at the failure includes it",
          failures.count_since(conn, "example_source", stamp), 1)
    check("a window starting after it excludes it",
          failures.count_since(conn, "example_source", "2999-01-01"), 0)
    conn.close()


def case_an_empty_table_answers_zero_and_nothing():
    conn = fresh()
    check("top of nothing is nothing", failures.top(conn), [])
    check("count of nothing is zero",
          failures.count_since(conn, "example_source", "1970-01-01"), 0)
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
    print(f"progress-failures: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
