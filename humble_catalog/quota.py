"""When a source's rate limit is spent, and when it is expected to lift.

A 429 is within-run state everywhere else: the pool flips the source
offline and the flag dies with the process. This module is the part that
survives, so tomorrow's run can serve the source from cache without
spending a request to rediscover what today's run already proved.

Imports nothing from the package, so `sources.base` can use it freely.
"""
from datetime import datetime, timedelta, timezone

# Google's Cloud quotas reset at midnight Pacific, which is a wall-clock
# time in a zone the stdlib cannot resolve on Windows without the `tzdata`
# package. A fixed UTC-8 avoids that dependency for one timestamp.
#
# The cost is exact and deliberately taken in this direction: during
# Pacific Daylight Time the true reset is an hour earlier, so the computed
# time is an hour late. Waiting an extra hour costs nothing - the source is
# served from cache either way - while retrying an hour early spends the
# request this module exists to save.
PACIFIC = timezone(timedelta(hours=-8))

def _utcnow():
    return datetime.now(timezone.utc)

def next_pacific_midnight(now=None):
    """The next instant strictly after `now` at which Pacific reads 00:00.

    Strictly after: a run starting exactly on the boundary must not read
    the instant it is standing on as still ahead, or a quota that just
    reset would be recorded as spent for another whole day.
    """
    now = now or _utcnow()
    local = now.astimezone(PACIFIC)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if midnight <= local:
        midnight += timedelta(days=1)
    return midnight.astimezone(timezone.utc)

def record(conn, source, resets_at):
    """Remember that `source` is rate-limited until `resets_at`. Commits.

    hit_at is written but never read back by the harvest. It is here for
    diagnosis: the one real risk in this design is a wrong reset guess,
    and without the time the guess was made there is no way to tell a row
    written minutes ago from one whose arithmetic was wrong yesterday.
    """
    conn.execute("INSERT OR REPLACE INTO source_quota "
                 "(source, hit_at, resets_at) VALUES (?,?,?)",
                 (source, _utcnow().isoformat(), resets_at.isoformat()))
    conn.commit()

def clear(conn, source):
    """Forget any record for `source`. Does NOT commit.

    Its caller is get_json, which deletes in the same transaction as the
    cache insert that proved the source live again.
    """
    conn.execute("DELETE FROM source_quota WHERE source=?", (source,))

def blocked(conn, source, now=None):
    """`source`'s reset time if it is still ahead, else None.

    An expired record needs no sweeping: it is simply not believed, and
    the next 429 overwrites it.
    """
    row = conn.execute("SELECT resets_at FROM source_quota WHERE source=?",
                       (source,)).fetchone()
    if row is None:
        return None
    resets_at = datetime.fromisoformat(row["resets_at"])
    return resets_at if resets_at > (now or _utcnow()) else None

def hit_at(conn, source):
    """When `source`'s limit was last recorded as spent, or None.

    `blocked` answers "is it spent now"; this answers "when did that
    happen". The difference separates a run that exhausted the budget
    from one that started with it already gone - the same condition as
    far as advice goes, opposite meanings for a measured rate.
    """
    row = conn.execute("SELECT hit_at FROM source_quota WHERE source=?",
                       (source,)).fetchone()
    return datetime.fromisoformat(row["hit_at"]) if row else None
