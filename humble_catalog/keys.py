"""Which Humble store keys have a game that is in no imported library.

Read-only: nothing here writes to catalog.db. The question is "what have I
paid for and never claimed", and the answer is derived from the two tables
that already hold it -- external_keys, filed by harvest, and games, filed
by import-games.

Split like stats.py: report() is the only place a key's state is decided,
format_report() prints it, and /api/keys reshapes it. The CLI and the
viewer panel therefore cannot disagree.

This is bundle_preview._keyed_games inverted. That helper asks "do I own
this bundle's games somehow" and pools every library, because owning the
game anywhere answers it. This asks "did this key ever land", which only
the key's OWN store can answer -- a steam key whose game sits in the gog
library is still an unactivated steam key.
"""
import datetime as dt
import json
import sys

from humble_catalog import db, game_match, import_games, stats

# Every key lands in exactly one of these, so the counts partition
# external_keys. `matched` is the only one not reported.
STATES = ("unredeemed", "uncertain", "uncheckable", "matched")

# classify_game's verdicts, in this report's vocabulary. The middle band is
# `uncertain` and IS reported, the reverse of bundle_preview's treatment --
# see game_match's module docstring for why.
_VERDICTS = {"owned": "matched", "possible": "uncertain", "new": "unredeemed"}


def store_for(key_type):
    """The `games.store` name a key of this type redeems into, or None.

    Humble spells the keyless variants of a store as "<store>_keyless"
    (gog_keyless, epic_keyless, blizzard_keyless), which is a delivery
    detail and not a different storefront.

    Checkability is NOT decided here: a store is checkable when
    game_imports holds a row for it, so a machine that has never imported
    Epic reports its Epic keys as uncheckable rather than as unredeemed.
    Deriving it that way also means a store gaining an importer later
    needs no edit in this file.
    """
    normalized = (key_type or "").strip().lower().removesuffix("_keyless")
    return normalized or None


def parse_expiry(value):
    """`expiry_date` as a tz-aware UTC datetime, or None.

    The only expiry field read. `num_days_until_expired` and `is_expired`
    are harvest-time derivatives of this one -- measured to agree with it
    exactly on all 2,275 keys, and to go stale on their own as the catalog
    sits -- and `expiration_date` was byte-identical on all 493 rows
    carrying it. An absolute timestamp compared against now needs none of
    them.
    """
    if not value:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def _store_pools(conn):
    """{store: Pool}, deduped per store and ready to score against.

    One pool per store rather than one pooled list: see the module
    docstring. Ordered so the dedupe is deterministic rather than dependent
    on the order sqlite happens to return rows in -- the same reason
    build_worklist sorts.

    Prepared here rather than by the caller because this is the pool
    builder: sorting each title's tokens is part of building a pool that
    can be scored against, and doing it once per store instead of once per
    key is what makes the report fast.
    """
    pools = {}
    for row in conn.execute(
            "SELECT store, normalized_title, title FROM games "
            "WHERE normalized_title IS NOT NULL AND normalized_title != '' "
            "ORDER BY store, normalized_title"):
        pool = pools.setdefault(row["store"], [])
        if pool and pool[-1][0] == row["normalized_title"]:
            continue
        pool.append((row["normalized_title"], row["title"]))
    return {store: game_match.prepare_pool(entries)
            for store, entries in pools.items()}


def _key_rows(conn):
    """Every key joined to its bundle and any hide, blob already parsed.

    Parsed in Python rather than with SQL json_extract: one parse yields
    expiry_date, redeemed_key_val and key_type_human_name, where SQL would
    need three calls, and a blob that is not JSON skips its row instead of
    failing the whole query. machine_name used to come out of the blob too
    and is now a column, so the field that decides a key's identity is no
    longer read out of JSON.
    """
    for row in conn.execute(
            "SELECT k.human_name AS product, k.key_type AS key_type, "
            "       k.gamekey AS gamekey, k.machine_name AS machine_name, "
            "       k.raw AS raw, h.hidden_at AS hidden_at, "
            "       b.name AS bundle, b.url AS bundle_url, "
            "       b.purchased_at AS purchased_at "
            "FROM external_keys k JOIN bundles b ON b.gamekey = k.gamekey "
            "LEFT JOIN hidden_keys h ON h.gamekey = k.gamekey "
            "                       AND h.machine_name = k.machine_name"):
        try:
            raw = json.loads(row["raw"]) if row["raw"] else {}
        except ValueError:
            raw = {}
        yield row, raw


def stale_hides(conn):
    """How many hides name a key that is no longer in the catalog.

    `hidden_keys` has no foreign key and survives `reset`, so a hide can
    outlive the row it named -- and straight after a reset, before a
    reparse, every hide is stale.

    Its own query rather than "hides minus hidden rows shown", because
    that derivation is wrong: a hide on a key that has since become
    `matched` is not stale, but `matched` rows are not in `rows` either,
    so the cheap version would count it.
    """
    return conn.execute(
        "SELECT COUNT(*) FROM hidden_keys h WHERE NOT EXISTS ("
        "  SELECT 1 FROM external_keys k "
        "   WHERE k.gamekey = h.gamekey "
        "     AND k.machine_name = h.machine_name)").fetchone()[0]


def missing_keys(conn):
    """Products whose tpks are in raw_orders but not in external_keys.

    Non-zero only until the first `reparse` after external_keys was
    re-keyed on (gamekey, machine_name). The old (gamekey, human_name)
    key silently dropped every storefront but the last of a multi-store
    product, and a migration that copies the table cannot recover rows
    that were never in it -- only a reparse from the cached orders can.

    Reported here rather than from the migration because db.py never
    prints: connect() runs in every command, in every test, and once per
    thread in the viewer. A line in a report the owner already reads is
    also the better home, since it self-clears after the reparse where a
    one-shot migration message can be missed forever.

    One row-value NOT IN against the migrated table, measured at 33 ms on
    a 2,275-key catalog. json_each(NULL) yields no rows, so an order with
    no tpkd_dict needs no guard.

    A tpk carrying no machine_name would compare NULL and be skipped
    rather than reported. None exists -- 2,278 of 2,278, across 13 key
    types -- and parse_order subscripts the field for the same reason.
    """
    return [{"product": r["product"], "lost": r["lost"]} for r in conn.execute(
        "SELECT json_extract(t.value, '$.human_name') AS product, "
        "       COUNT(*) AS lost "
        "  FROM raw_orders r, "
        "       json_each(json_extract(r.json, '$.tpkd_dict.all_tpks')) t "
        " WHERE (r.gamekey, json_extract(t.value, '$.machine_name')) NOT IN "
        "       (SELECT gamekey, machine_name FROM external_keys) "
        " GROUP BY product ORDER BY lost DESC, product")]


def report(conn, now=None):
    """Every key's state, and the reported rows in display order.

    `now` is injectable so the expiry arithmetic is testable; it defaults
    to the current UTC time.

    Returns {total, counts, reported, expiring, stale_hides, missing_keys,
    libraries, rows}. `rows` holds only the reported states -- `matched`
    is the answer "nothing to do here" and lives in `counts` alone.

    Each row carries `hidden_at`; rows are never filtered here. Both
    surfaces filter that one field, so the CLI and the viewer cannot
    disagree about what is hidden.

    There is deliberately no `hidden` count: format_report counts `rows`
    and the viewer computes its own chip counts, so a stored total would
    be a second copy of a number derivable from the rows beside it.
    `stale_hides` is the opposite case, and that is why it is here -- it
    cannot be derived from `rows` at all.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    pools = _store_pools(conn)
    libraries = import_games.imported_stores(conn)
    counts = {state: 0 for state in STATES}
    ranked, total = [], 0
    for row, raw in _key_rows(conn):
        total += 1
        store = store_for(row["key_type"])
        near = None
        if store is None or store not in libraries:
            state = "uncheckable"
        else:
            # EMPTY, not []: a store can be in `libraries` -- it has a
            # game_imports row -- while holding no games rows at all, so
            # `pools` has no entry for it. Both classify every title as
            # `new`, which is the answer that store deserves.
            verdict, match = game_match.classify_game(
                row["product"] or "", pools.get(store, game_match.EMPTY))
            state = _VERDICTS[verdict]
            if state == "uncertain":
                near = {"owned_title": match["owned_title"],
                        "score": match["score"]}
        counts[state] += 1
        if state == "matched":
            continue
        expires = parse_expiry(raw.get("expiry_date"))
        expired = expires is not None and expires < now
        # Three groups, not one ascending column. The backlog asked for
        # "expiry ascending with undated rows last so the rows that can
        # still be lost come first" -- and plain ascending does not deliver
        # that, because the already-dead rows sort above the urgent ones.
        # So the dated rows split AROUND the undated ones:
        #   0  a live expiry, soonest first -- can still be lost
        #   1  no expiry date
        #   2  already expired, most recent first
        # Ties break on purchased_at then the product name, so the order is
        # a pure function of the data rather than of the query plan.
        tie = (row["purchased_at"] or "", (row["product"] or "").lower())
        if expires is None:
            rank = (1, 0.0, *tie)
        elif expired:
            rank = (2, -expires.timestamp(), *tie)
        else:
            rank = (0, expires.timestamp(), *tie)
        ranked.append((rank, {
            "product": row["product"],
            "machine_name": row["machine_name"],
            "gamekey": row["gamekey"],
            "store": store,
            # The 52-value display string, used ONLY as a label. Every
            # decision above came from key_type's 12 clean machine values,
            # so this column's `Other`/`other` collision stays cosmetic.
            "key_type_label": raw.get("key_type_human_name")
                              or row["key_type"] or "",
            "bundle": row["bundle"],
            # The stored bundles.url -- the same address the Library
            # table's bundle tags link to, rather than a second copy of
            # the /downloads?key= format built from the gamekey here.
            "bundle_url": row["bundle_url"],
            "purchased_at": row["purchased_at"],
            "expires": expires.isoformat() if expires else None,
            "expired": expired,
            # Whole days, floored, and None once the date has passed --
            # "in -6 days" is not a thing anyone wants to read.
            "days_left": None if expires is None or expired
                         else (expires - now).days,
            # "revealed", never "redeemed": Humble sets this the moment the
            # key's value is DISPLAYED. The key that motivated this whole
            # feature reads as redeemed and had never been activated.
            "revealed": bool(raw.get("redeemed_key_val")),
            "state": state,
            # An annotation, not a fourth state: the row keeps whichever
            # of the three it earned, and `counts` still holds it. The
            # viewer presents hidden as a fourth chip, which is a display
            # choice in keys.js and does not travel back across the route.
            "hidden_at": row["hidden_at"],
            "near_match": near,
        }))
    ranked.sort(key=lambda pair: pair[0])
    rows = [payload for _rank, payload in ranked]
    return {
        "total": total,
        "counts": counts,
        "reported": len(rows),
        # Excludes hidden rows, unlike `counts` and `reported`. This is the
        # sibling of the tab badge -- "what needs attention this week" --
        # and a hide that leaves the badge lit has not stopped the row
        # reappearing, which is the whole point of hiding.
        "expiring": sum(1 for r in rows
                        if r["expires"] is not None and not r["expired"]
                        and not r["hidden_at"]),
        "stale_hides": stale_hides(conn),
        "missing_keys": missing_keys(conn),
        "libraries": libraries,
        "rows": rows,
    }


# Longest product name the table pads to. One 92-character bundle-as-a-key
# name was pushing every other row's remaining columns off an 80-column
# console; past this a name overflows its own row rather than widening all
# of them. Same cap, and same reason, as the xlsx export's column widths.
MAX_NAME = 60


def _line(row, width, hidden=False):
    """One reported row, as a printable line.

    `hidden` swaps the leading column from the expiry to the date the
    owner hid the row -- same columns otherwise, so the two listings stay
    comparable rather than being two different tables.
    """
    if hidden:
        when = (row["hidden_at"] or "")[:10]
    else:
        days = row["days_left"]
        # "today", not "in 0 days" -- and it matches what keys.js renders,
        # so the same key does not read differently in the two surfaces.
        when = ("" if days is None
                else ("today" if days == 0 else f"in {days} days"))
        if days is None and row["expired"]:
            when = "expired"
    line = (f"    {when:>12}  {row['product'] or '':<{width}}  "
            f"{row['key_type_label']:<12}  {row['bundle']}")
    if row["near_match"]:
        line += (f"  ~ {row['near_match']['owned_title']}"
                 f" ({row['near_match']['score']:.2f})?")
    if row["state"] == "uncheckable":
        line += "  [no importer]"
    return line.rstrip()


def _block(lines, heading, rows, hidden=False):
    """One headed block, padded to its OWN widest name.

    Per block rather than per report: the undated rows are the great
    majority and hold the longest names, so a shared width made the
    default report's 63 lines carry ~40 columns of padding for rows it
    was not even printing.
    """
    if not rows:
        return
    width = min(max(len(r["product"] or "") for r in rows), MAX_NAME)
    lines.append(f"  {heading} ({len(rows)}):")
    lines.extend(_line(row, width, hidden=hidden) for row in rows)
    lines.append("")


def _hidden_report(report, encoding):
    """The owner's hidden rows, newest hide first.

    Every hidden row in one block -- `show_all` does not apply. The main
    report splits into live/undated/expired because it is triage, and
    `--all` exists to keep the default from leading with 700 lines. A list
    of the owner's own dismissals is not triage: it is as long as they
    made it, and "which of my dismissals expire soon" is not a question
    hiding leaves open.
    """
    marked = sorted((r for r in report["rows"] if r["hidden_at"]),
                    key=lambda r: (r["hidden_at"], r["product"] or ""),
                    reverse=True)
    lines = []
    if marked:
        _block(lines, "Hidden", marked, hidden=True)
    else:
        lines.append("  No keys are hidden.")
        lines.append("")
    stale = report["stale_hides"]
    if stale:
        # Named, never dropped: the hide is knowledge a rebuild cannot
        # recover. A count rather than rows, because a stale hide holds
        # only a machine name -- the product, store, bundle and expiry all
        # lived in the table that was wiped.
        noun = "hide" if stale == 1 else "hides"
        lines.append(f"  {stale:,} {noun} refer to keys no longer in the "
                     f"catalog")
        lines.append("  (run 'reparse' if you have just reset).")
    return stats.console_safe("\n".join(lines).rstrip(), encoding)


def format_report(report, encoding="utf-8", show_all=False, hidden=False):
    """The report as printable text, safe for a console using `encoding`.

    The default prints the counts plus only the rows with a live expiry --
    what needs attention this week. `--all` adds the undated and the
    already-expired rows, which together are the great majority: a report
    that leads with 700 lines is one nobody reads to the end.

    `hidden` lists the rows the owner has marked resolved *instead of*
    the report. There is no mode that merges the two: the questions are
    "what still needs doing" and "what have I dismissed", and a merged
    list is a third nobody has asked for -- the viewer's chips give it to
    anyone who wants it.
    """
    if hidden:
        return _hidden_report(report, encoding)
    counts = report["counts"]
    # "1 key", not "1 keys": a one-item tier read "1 items" in the bundle
    # preview, and no test caught it -- a browser did.
    noun = "key" if report["total"] == 1 else "keys"
    lines = [f"{report['total']:,} {noun} - {counts['matched']:,} in a library, "
             f"{counts['unredeemed'] + counts['uncertain']:,} not, "
             f"{counts['uncheckable']:,} uncheckable", ""]
    rows = report["rows"]
    shown = [r for r in rows if not r["hidden_at"]]
    live = [r for r in shown if r["expires"] and not r["expired"]]
    undated = [r for r in shown if not r["expires"]]
    expired = [r for r in shown if r["expired"]]
    _block(lines, "Expiring", live)
    if show_all:
        _block(lines, "No expiry date", undated)
        _block(lines, "Already expired", expired)
    elif undated or expired:
        lines.append(f"  ('keys --all' for the other "
                     f"{len(undated) + len(expired):,}: {len(undated):,} "
                     f"undated, {len(expired):,} already expired)")
        lines.append("")
    # Counted here rather than carried in the payload: it is derivable
    # from the rows beside it, and a stored copy is free to drift.
    n_hidden = len(rows) - len(shown)
    if n_hidden:
        lines.append(f"  ({n_hidden:,} hidden; 'keys --hidden' lists them)")
        lines.append("")
    libraries = report["libraries"]
    if libraries:
        listed = ", ".join(
            f"{store} {info['count']:,} "
            f"{'game' if info['count'] == 1 else 'games'} "
            f"(imported {info['imported_at'][:10]})"
            for store, info in sorted(libraries.items()))
        lines.append(f"  Libraries: {listed}")
    if counts["uncheckable"]:
        # "1 key is", not "1 keys are" -- the same slip the summary line
        # above already guards against, spotted by reading real output.
        n = counts["uncheckable"]
        lines.append(f"  {n:,} {'key is' if n == 1 else 'keys are'} for "
                     f"stores with no importer -- for those, 'in no "
                     f"library' cannot be checked at all.")
    missing = report["missing_keys"]
    if missing:
        total_lost = sum(m["lost"] for m in missing)
        named = ", ".join(f"{m['product']} ({m['lost']})" for m in missing[:5])
        lines.append(f"  {total_lost:,} keys in your orders are missing from "
                     f"the catalog: {named}. Run 'reparse' to recover them.")
    lines.append("  Matching is by title and APPROXIMATE. A revealed key was "
                 "only displayed, which is not the same as activated.")
    # Degraded at the CLI boundary only, exactly as bundle_preview does:
    # the web route keeps the real characters, and product names are
    # arbitrary data that may hold anything.
    return stats.console_safe("\n".join(lines).rstrip(), encoding)


def run(show_all=False, hidden=False):
    """Count and print. The `keys` subcommand's entry point."""
    conn = db.connect()
    try:
        built = report(conn)
    finally:
        conn.close()
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(format_report(built, encoding, show_all=show_all, hidden=hidden))
