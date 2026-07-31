from datetime import datetime, timedelta, timezone
from humble_catalog import db, quota

UTC = timezone.utc

def test_morning_utc_waits_for_tomorrows_reset():
    # 09:00 UTC is 01:00 Pacific: today's reset has already passed.
    got = quota.next_pacific_midnight(datetime(2026, 7, 26, 9, 0, tzinfo=UTC))
    assert got == datetime(2026, 7, 27, 8, 0, tzinfo=UTC)

def test_before_the_reset_waits_for_todays():
    # 03:00 UTC is 19:00 Pacific the previous day: the reset is still ahead.
    got = quota.next_pacific_midnight(datetime(2026, 7, 26, 3, 0, tzinfo=UTC))
    assert got == datetime(2026, 7, 26, 8, 0, tzinfo=UTC)

def test_exactly_at_the_reset_takes_the_next_one():
    # A run that starts on the boundary must not read the instant it is
    # standing on as "still ahead", or it would treat a live quota as spent.
    got = quota.next_pacific_midnight(datetime(2026, 7, 26, 8, 0, tzinfo=UTC))
    assert got == datetime(2026, 7, 27, 8, 0, tzinfo=UTC)

def test_the_result_is_aware_utc_so_it_round_trips_through_a_column():
    got = quota.next_pacific_midnight(datetime(2026, 7, 26, 9, 0, tzinfo=UTC))
    assert got.tzinfo is not None
    assert got.utcoffset() == timedelta(0)
    assert datetime.fromisoformat(got.isoformat()) == got

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)

def test_blocked_reports_a_record_whose_time_is_still_ahead(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    resets = NOW + timedelta(hours=6)
    quota.record(conn, "google_books", resets)
    assert quota.blocked(conn, "google_books", now=NOW) == resets

def test_blocked_ignores_a_record_whose_time_has_passed(tmp_path):
    # Expiry needs no sweeping pass: a stale row is simply not believed,
    # and the next 429 overwrites it.
    conn = db.connect(tmp_path / "t.db")
    quota.record(conn, "google_books", NOW - timedelta(minutes=1))
    assert quota.blocked(conn, "google_books", now=NOW) is None

def test_blocked_is_none_for_a_source_with_no_record(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert quota.blocked(conn, "hardcover", now=NOW) is None

def test_recording_twice_leaves_one_row(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    quota.record(conn, "google_books", NOW + timedelta(hours=1))
    quota.record(conn, "google_books", NOW + timedelta(hours=9))
    rows = conn.execute("SELECT resets_at FROM source_quota "
                        "WHERE source='google_books'").fetchall()
    assert len(rows) == 1
    assert quota.blocked(conn, "google_books", now=NOW) == NOW + timedelta(hours=9)

def test_clear_removes_the_record(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    quota.record(conn, "google_books", NOW + timedelta(hours=6))
    quota.clear(conn, "google_books")
    conn.commit()  # clear leaves committing to its caller
    assert quota.blocked(conn, "google_books", now=NOW) is None

def test_clear_is_a_no_op_for_a_source_with_no_record(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    quota.clear(conn, "google_books")  # must not raise

def test_reset_preserves_the_quota_records(tmp_path):
    # source_quota is absent from reset.DERIVED_TABLES, which is an
    # allowlist - so it survives by omission, and nothing in the code says
    # so. The row describes Google's API, not the owner's catalog, and
    # wiping the catalog does not give the quota back.
    from humble_catalog import reset
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('cooltower_android','Cool Tower Defense','android')")
    conn.commit()
    quota.record(conn, "google_books", NOW + timedelta(hours=6))
    reset.run(_conn=conn, _input=lambda _: "RESET")
    assert quota.blocked(conn, "google_books", now=NOW) is not None

def test_hit_at_reports_when_the_limit_was_recorded(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert quota.hit_at(conn, "google_books") is None
    before = datetime.now(UTC)
    quota.record(conn, "google_books", datetime.now(UTC) + timedelta(hours=1))
    hit = quota.hit_at(conn, "google_books")
    assert hit is not None and hit >= before
