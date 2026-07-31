"""What each harvest run cost, one row per source.

`source_failure` says which titles keep failing; this says how many
requests a run spent and how many succeeded, so the failure rate is a
measurement rather than an inference drawn from throttle arithmetic.

It exists because two facts decay. `source_failure.last_failed_at` is
overwritten, so failures-per-run can be counted right after a run and
never again. And `quota.blocked` cannot tell a run that exhausted the
budget from one that started with it already spent - the same condition
for the advice a run prints, opposite meanings for a measured rate.

Bounded by construction: `record` trims to the newest KEEP_RUNS runs, so
the table cannot grow without limit even if nobody ever prunes it.

Imports nothing from the package, as `quota` and `failures` do.
"""

KEEP_RUNS = 500

def record(conn, started_at, ended_at, tallies, keep=KEEP_RUNS):
    """Write one row per source for a finished run, then trim. Commits.

    `tallies` maps a source name to
    (answered, succeeded, failed, quota_died).

    `keep` is a parameter rather than a constant read in here purely so a
    test can prove the trim with three runs instead of five hundred.
    """
    conn.executemany(
        "INSERT OR REPLACE INTO harvest_run (started_at, source, ended_at, "
        "answered, succeeded, failed, quota_died) VALUES (?,?,?,?,?,?,?)",
        [(started_at, source, ended_at, answered, succeeded, failed, int(died))
         for source, (answered, succeeded, failed, died) in tallies.items()])
    # A run is a distinct started_at spread over up to six rows, so the
    # cap is counted in runs; trimming rows would behead a run mid-way.
    conn.execute(
        "DELETE FROM harvest_run WHERE started_at NOT IN ("
        "SELECT started_at FROM harvest_run "
        "GROUP BY started_at ORDER BY started_at DESC LIMIT ?)", (keep,))
    conn.commit()

def history(conn):
    """Every recorded row, newest run first then source by name.

    Named `history` rather than `all`, which would shadow the builtin.
    """
    return conn.execute(
        "SELECT started_at, source, ended_at, answered, succeeded, failed, "
        "quota_died FROM harvest_run ORDER BY started_at DESC, source").fetchall()

def forget(conn):
    """Delete every row. Returns how many runs were dropped. Commits."""
    n = conn.execute(
        "SELECT COUNT(DISTINCT started_at) FROM harvest_run").fetchone()[0]
    conn.execute("DELETE FROM harvest_run")
    conn.commit()
    return n
