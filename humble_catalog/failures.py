"""Which titles a source could not fetch, and in how many runs.

`source_cache` records answers and `source_quota` records rate limits.
This is the third fact a harvest produces and the only one that used to
die with the process: a failure was printed and then forgotten, so
"did the same titles fail again?" had no way to be answered.

`failures` counts *runs*, not attempts. The pool visits each title once
per run, and google_books does not retry server errors, so one increment
per failure is one increment per run. A row at failures = 5 failed on
five separate days.

Imports nothing from the package, as `quota` does, so any layer may use
it without a cycle.
"""
from datetime import datetime, timezone

def _utcnow():
    return datetime.now(timezone.utc).isoformat()

def record(conn, source, title, error):
    """Count one more run in which `source` could not fetch `title`. Commits.

    `error` must already be scrubbed - see `sources.base.redact`. Doing it
    at the call site rather than here is what keeps this module free of
    package imports, and it means the printed and the stored text are the
    same string rather than two that could drift.
    """
    now = _utcnow()
    conn.execute(
        "INSERT INTO source_failure (source, title, failures, "
        "first_failed_at, last_failed_at, last_error) VALUES (?,?,1,?,?,?) "
        "ON CONFLICT(source, title) DO UPDATE SET "
        "failures = failures + 1, "
        "last_failed_at = excluded.last_failed_at, "
        "last_error = excluded.last_error",
        (source, title, now, now, error))
    conn.commit()

def top(conn, min_failures=1):
    """Failure rows, most persistent first.

    `min_failures=2` is the interesting view: one failure is noise, two
    in separate runs is the beginning of evidence.
    """
    return conn.execute(
        "SELECT source, title, failures, first_failed_at, last_failed_at, "
        "last_error FROM source_failure WHERE failures >= ? "
        "ORDER BY failures DESC, last_failed_at DESC, source, title",
        (min_failures,)).fetchall()

def error_kind(error):
    """The part of an error string that is the same for every title.

    A `requests` HTTP error ends in " for url: <the request URL>", and
    that URL contains the title being searched for. Grouping on the whole
    string would therefore tally one of everything; cutting at the marker
    leaves "503 Server Error: Service Unavailable", which is the thing
    worth counting.
    """
    return error.split(" for url:")[0].strip()

def count_since(conn, source, since, until=None):
    """How many of `source`'s titles failed at or after `since`, and at or
    before `until` when given.

    Exact for the run that just ended: a title fails at most once per run
    and that run stamps last_failed_at on every title that failed in it.
    Not exact for an older window, because last_failed_at moves - which
    is precisely why a run's count is written down rather than
    recomputed later. The one later recount is an interrupted run's, and
    it happens as the next run starts, before that run can move a stamp.
    """
    return conn.execute(
        "SELECT COUNT(*) FROM source_failure "
        "WHERE source=? AND last_failed_at >= ? "
        "AND last_failed_at <= COALESCE(?, last_failed_at)",
        (source, since, until)).fetchone()[0]
