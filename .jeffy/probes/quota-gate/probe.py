"""Known-answer battery for the quota-gate inventory row.

Covers `quota.next_pacific_midnight`, `record`, `blocked`, `clear` and
`hit_at`.

The arithmetic is closed-form here, which is why this row is worth a
known-answer sweep rather than a liveness one: PACIFIC is a FIXED UTC-8
offset, so Pacific midnight is exactly 08:00 UTC on the same date, and
every expected instant below is written out in full rather than computed
by repeating the implementation.

The fixed offset is a documented, deliberate trade - during Pacific
Daylight Time the true reset is an hour earlier, so the computed time is
an hour late, and waiting costs nothing while retrying early spends the
request the module exists to save. It is pinned here as the documented
behaviour, not filed as a defect.
"""
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, quota  # noqa: E402

UTC = timezone.utc
PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def fresh():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    path = pathlib.Path(tmp.name)
    return db.connect(path), path


# ------------------------------------------------- next_pacific_midnight

def case_midnight_is_0800_utc_the_same_day():
    now = datetime(2026, 3, 15, 7, 0, tzinfo=UTC)      # Pacific 23:00 on 03-14
    check("an instant before the boundary reaches today's 08:00 UTC",
          quota.next_pacific_midnight(now),
          datetime(2026, 3, 15, 8, 0, tzinfo=UTC))


def case_the_boundary_itself_is_strictly_ahead():
    # Standing exactly on midnight must yield TOMORROW's, or a quota that
    # just reset would be recorded as spent for another whole day.
    now = datetime(2026, 3, 15, 8, 0, tzinfo=UTC)      # Pacific 00:00 exactly
    check("the instant of midnight yields the NEXT midnight",
          quota.next_pacific_midnight(now),
          datetime(2026, 3, 16, 8, 0, tzinfo=UTC))


def case_just_after_the_boundary():
    now = datetime(2026, 3, 15, 8, 0, 1, tzinfo=UTC)
    check("one second past midnight yields the next one",
          quota.next_pacific_midnight(now),
          datetime(2026, 3, 16, 8, 0, tzinfo=UTC))


def case_just_before_the_boundary():
    now = datetime(2026, 3, 15, 7, 59, 59, tzinfo=UTC)
    check("one second before midnight yields the imminent one",
          quota.next_pacific_midnight(now),
          datetime(2026, 3, 15, 8, 0, tzinfo=UTC))


def case_a_non_utc_input_is_converted_not_assumed():
    # Same instant as case_midnight_is_0800_utc_the_same_day, expressed in
    # a different zone: the answer must not depend on how it was spelled.
    now = datetime(2026, 3, 15, 9, 0, tzinfo=timezone(timedelta(hours=2)))
    check("an instant given in another zone gives the same answer",
          quota.next_pacific_midnight(now),
          datetime(2026, 3, 15, 8, 0, tzinfo=UTC))


def case_the_answer_is_always_ahead_and_within_a_day():
    # The invariant, over a full day of inputs at one-hour steps: the
    # result is strictly ahead and never more than 24h away. A constant
    # return, or an off-by-one-day, breaks this.
    base = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    ok = True
    for hours in range(0, 48):
        now = base + timedelta(hours=hours)
        nxt = quota.next_pacific_midnight(now)
        if not (now < nxt <= now + timedelta(days=1)):
            ok = False
            print(f"       invariant broken at {now.isoformat()}: {nxt}")
    check("every answer is strictly ahead and within 24 hours", ok, True)


def case_the_result_is_utc_and_lands_on_the_hour():
    nxt = quota.next_pacific_midnight(datetime(2026, 6, 1, 3, 17, 42,
                                               tzinfo=UTC))
    check("the answer is returned in UTC",
          nxt.utcoffset(), timedelta(0))
    check("and carries no leftover minutes or seconds",
          (nxt.minute, nxt.second, nxt.microsecond), (0, 0, 0))


# ------------------------------------------------------- record / blocked

def case_blocked_reads_back_what_record_wrote():
    conn, _ = fresh()
    resets = datetime(2026, 6, 2, 8, 0, tzinfo=UTC)
    quota.record(conn, "example_source", resets)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    check("a reset still ahead comes back as itself",
          quota.blocked(conn, "example_source", now), resets)
    conn.close()


def case_blocked_now_parameter_changes_the_answer():
    # The documented parameter, at two values that must flip the result.
    conn, _ = fresh()
    resets = datetime(2026, 6, 2, 8, 0, tzinfo=UTC)
    quota.record(conn, "example_source", resets)
    before = quota.blocked(conn, "example_source",
                           datetime(2026, 6, 1, 12, 0, tzinfo=UTC))
    after = quota.blocked(conn, "example_source",
                          datetime(2026, 6, 3, 12, 0, tzinfo=UTC))
    check("ahead of the reset it is blocked, past it it is not",
          (before, after), (resets, None))
    conn.close()


def case_the_boundary_of_blocked_is_strict():
    conn, _ = fresh()
    resets = datetime(2026, 6, 2, 8, 0, tzinfo=UTC)
    quota.record(conn, "example_source", resets)
    check("at exactly the reset instant the source is no longer blocked",
          quota.blocked(conn, "example_source", resets), None)
    check("one microsecond earlier it still is",
          quota.blocked(conn, "example_source",
                        resets - timedelta(microseconds=1)), resets)
    conn.close()


def case_an_unknown_source_is_never_blocked():
    conn, _ = fresh()
    check("a source with no row is not blocked",
          quota.blocked(conn, "never_seen", datetime(2026, 6, 1, tzinfo=UTC)),
          None)
    check("and has no hit_at", quota.hit_at(conn, "never_seen"), None)
    conn.close()


def case_one_source_does_not_answer_for_another():
    conn, _ = fresh()
    quota.record(conn, "source_a", datetime(2026, 6, 2, 8, 0, tzinfo=UTC))
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    check("a second source is unaffected",
          quota.blocked(conn, "source_b", now), None)
    conn.close()


def case_record_replaces_rather_than_duplicates():
    conn, _ = fresh()
    first = datetime(2026, 6, 2, 8, 0, tzinfo=UTC)
    second = datetime(2026, 6, 5, 8, 0, tzinfo=UTC)
    quota.record(conn, "example_source", first)
    quota.record(conn, "example_source", second)
    rows = conn.execute("SELECT COUNT(*) FROM source_quota WHERE source=?",
                        ("example_source",)).fetchone()[0]
    check("a second record replaces the first", rows, 1)
    check("and the later reset is what is believed",
          quota.blocked(conn, "example_source",
                        datetime(2026, 6, 1, tzinfo=UTC)), second)
    conn.close()


def case_record_commits():
    # Documented: "Commits." Asserted from a SECOND connection, which is
    # the only thing that can tell a commit from a pending write.
    conn, path = fresh()
    quota.record(conn, "example_source",
                 datetime(2026, 6, 2, 8, 0, tzinfo=UTC))
    other = db.connect(path)
    check("another connection sees the row, so it was committed",
          other.execute("SELECT COUNT(*) FROM source_quota").fetchone()[0], 1)
    other.close()
    conn.close()


def case_clear_does_not_commit():
    # Documented: does NOT commit, because its caller deletes in the same
    # transaction as the cache insert that proved the source live.
    conn, _ = fresh()
    quota.record(conn, "example_source",
                 datetime(2026, 6, 2, 8, 0, tzinfo=UTC))
    quota.clear(conn, "example_source")
    check("the delete is visible on this connection",
          conn.execute("SELECT COUNT(*) FROM source_quota").fetchone()[0], 0)
    conn.rollback()
    check("and a rollback brings the row back, so it was uncommitted",
          conn.execute("SELECT COUNT(*) FROM source_quota").fetchone()[0], 1)
    conn.close()


def case_hit_at_answers_when_not_whether():
    conn, _ = fresh()
    before = datetime.now(UTC)
    quota.record(conn, "example_source",
                 datetime(2026, 6, 2, 8, 0, tzinfo=UTC))
    after = datetime.now(UTC)
    stamp = quota.hit_at(conn, "example_source")
    check("hit_at falls between the instants surrounding the record",
          before <= stamp <= after, True)
    conn.close()


def case_hit_at_survives_the_reset_passing():
    # blocked answers "is it spent now"; hit_at answers "when did that
    # happen", and the two must not be the same question.
    conn, _ = fresh()
    quota.record(conn, "example_source",
                 datetime(2026, 6, 2, 8, 0, tzinfo=UTC))
    past_reset = datetime(2026, 6, 3, 12, 0, tzinfo=UTC)
    check("once the reset has passed the source is not blocked",
          quota.blocked(conn, "example_source", past_reset), None)
    check("but the record of when it was spent is still there",
          quota.hit_at(conn, "example_source") is not None, True)
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
    print(f"quota-gate: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
