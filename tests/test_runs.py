from humble_catalog import db, runs

def _tally(**kw):
    return {name: vals for name, vals in kw.items()}

def test_record_writes_one_row_per_source(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    runs.record(conn, "2026-07-30T21:00:00+00:00", "2026-07-30T22:00:00+00:00",
                _tally(google_books=(1718, 573, 427, True),
                       hardcover=(1320, 7, 0, False)))
    rows = conn.execute("SELECT * FROM harvest_run ORDER BY source").fetchall()
    assert [r["source"] for r in rows] == ["google_books", "hardcover"]
    assert rows[0]["answered"] == 1718
    assert rows[0]["succeeded"] == 573
    assert rows[0]["failed"] == 427
    assert rows[0]["quota_died"] == 1
    assert rows[1]["quota_died"] == 0
    assert rows[0]["ended_at"] == "2026-07-30T22:00:00+00:00"

def test_record_trims_to_the_newest_runs(tmp_path):
    # Without this the 500-run cap is a comment rather than a guarantee.
    conn = db.connect(tmp_path / "t.db")
    for day in ("01", "02", "03", "04"):
        runs.record(conn, f"2026-07-{day}T21:00:00+00:00",
                    f"2026-07-{day}T22:00:00+00:00",
                    _tally(google_books=(1, 1, 0, False),
                           hardcover=(1, 1, 0, False)),
                    keep=2)
    kept = sorted({r["started_at"][:10] for r in runs.history(conn)})
    assert kept == ["2026-07-03", "2026-07-04"]
    # both sources of a kept run survive - the cap counts runs, not rows
    assert len(runs.history(conn)) == 4

def test_history_is_newest_first(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for day in ("01", "02"):
        runs.record(conn, f"2026-07-{day}T21:00:00+00:00",
                    f"2026-07-{day}T22:00:00+00:00",
                    _tally(google_books=(1, 1, 0, False)))
    assert [r["started_at"][:10] for r in runs.history(conn)] == \
        ["2026-07-02", "2026-07-01"]

def test_forget_empties_the_table_and_counts_runs(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for day in ("01", "02"):
        runs.record(conn, f"2026-07-{day}T21:00:00+00:00",
                    f"2026-07-{day}T22:00:00+00:00",
                    _tally(google_books=(1, 1, 0, False),
                           hardcover=(1, 1, 0, False)))
    assert runs.forget(conn) == 2      # runs dropped, not the 4 rows
    assert runs.history(conn) == []

def test_forget_on_an_empty_table_drops_nothing(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert runs.forget(conn) == 0
