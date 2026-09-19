"""What each harvest run cost, one row per source.

`source_failure` says which titles keep failing; this says how many
requests a run spent and how many succeeded, so the failure rate is a
measurement rather than an inference drawn from throttle arithmetic.

It exists because two facts decay. `source_failure.last_failed_at` is
overwritten, so failures-per-run can be counted right after a run and
never again. And `quota.blocked` cannot tell a run that exhausted the
budget from one that started with it already spent - the same condition
for the advice a run prints, opposite meanings for a measured rate.

A run is recorded when it finishes, so a run that dies never gets
there. `open_run` leaves a marker in harvest_open as a run starts, and
`record` removes it in the same commit: a marker still present when the
next run starts belongs to a run that was interrupted, and harvest
rebuilds its row from the rows it had already written (see
`harvest._recover_interrupted`). Such a row is flagged `interrupted`
and its `answered` is NULL - that count lived only in the dead process.

Bounded by construction: `record` trims to the newest KEEP_RUNS runs, so
the table cannot grow without limit even if nobody ever prunes it.

Imports nothing from the package, as `quota` and `failures` do.
"""

KEEP_RUNS = 500

def open_run(conn, started_at):
    """Note that a run began at `started_at`. Commits.

    Written before the run does anything, so however it ends - Ctrl+C, a
    closed window, a cancelled viewer job, a crash - the marker survives
    unless `record` got to run.
    """
    conn.execute("INSERT OR IGNORE INTO harvest_open (started_at) VALUES (?)",
                 (started_at,))
    conn.commit()

def open_runs(conn):
    """started_at of every run that began and has no row yet, oldest first."""
    return [r[0] for r in conn.execute(
        "SELECT started_at FROM harvest_open ORDER BY started_at")]

def close(conn, started_at):
    """Drop a marker without recording anything. Commits."""
    conn.execute("DELETE FROM harvest_open WHERE started_at=?", (started_at,))
    conn.commit()

def record(conn, started_at, ended_at, tallies, keep=KEEP_RUNS,
           interrupted=False):
    """Write one row per source for a run, close its marker, trim. Commits.

    `tallies` maps a source name to
    (answered, succeeded, failed, quota_died). `answered` is None for an
    `interrupted` run, whose row was rebuilt after the fact.

    `keep` is a parameter rather than a constant read in here purely so a
    test can prove the trim with three runs instead of five hundred.
    """
    conn.executemany(
        "INSERT OR REPLACE INTO harvest_run (started_at, source, ended_at, "
        "answered, succeeded, failed, quota_died, interrupted) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(started_at, source, ended_at, answered, succeeded, failed, int(died),
          int(interrupted))
         for source, (answered, succeeded, failed, died) in tallies.items()])
    conn.execute("DELETE FROM harvest_open WHERE started_at=?", (started_at,))
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
        "quota_died, interrupted FROM harvest_run ORDER BY started_at DESC, source").fetchall()

def forget(conn):
    """Delete every row and marker. Returns how many runs were dropped.
    Commits.

    Markers go too: kept, they would put back a row for a run from before
    the forget the next time harvest starts.
    """
    n = conn.execute(
        "SELECT COUNT(DISTINCT started_at) FROM harvest_run").fetchone()[0]
    conn.execute("DELETE FROM harvest_run")
    conn.execute("DELETE FROM harvest_open")
    conn.commit()
    return n
