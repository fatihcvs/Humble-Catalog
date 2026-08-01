import json
import sys
from humble_catalog import db
from humble_catalog.matching import score, status_for
from humble_catalog.progress import Progress
from humble_catalog.sources.base import CacheMiss
from humble_catalog.titles import clean_title, parse_series

SOURCE_ORDER = {
    "ebook": ["hardcover", "google_books", "oreilly", "open_library"],
    "audiobook": ["audible", "hardcover", "google_books"],
    "comic": ["comicvine", "google_books"],
}

def _source_classes():
    from humble_catalog.sources.audible import Audible
    from humble_catalog.sources.comicvine import ComicVine
    from humble_catalog.sources.google_books import GoogleBooks
    from humble_catalog.sources.hardcover import Hardcover
    from humble_catalog.sources.open_library import OpenLibrary
    from humble_catalog.sources.oreilly import OReilly
    return {"hardcover": Hardcover, "google_books": GoogleBooks,
            "oreilly": OReilly, "open_library": OpenLibrary,
            "audible": Audible, "comicvine": ComicVine}

SOURCE_CLASSES = _source_classes()

def _default_sources(conn, offline=False):
    return {name: cls(conn, offline=offline)
            for name, cls in SOURCE_CLASSES.items()}

EDITABLE_FIELDS = db.EDITABLE_FIELDS

def apply_candidate(conn, item_id, cand, confidence, status):
    # pre_edit always means "what Revert returns you to". Overwriting a
    # hand-edited row therefore re-snapshots the typed values first, so an
    # override - or a Review approval - stays undoable instead of stranding
    # the older enriched snapshot as the revert target. A row that is not
    # hand-edited keeps whatever pre_edit it has: for a plain enriched row
    # that is NULL, and for a row overridden twice it is still the hand
    # edit, which is exactly what Revert should return.
    row = conn.execute(
        "SELECT hand_edited, " + ", ".join(EDITABLE_FIELDS)
        + " FROM enrichment WHERE item_id=?", (item_id,)).fetchone()
    if row is not None and row["hand_edited"]:
        conn.execute(
            "UPDATE enrichment SET pre_edit=? WHERE item_id=?",
            (json.dumps({f: row[f] for f in EDITABLE_FIELDS}), item_id))
    conn.execute(
        "UPDATE enrichment SET genre=?, series=?, series_number=?, authors=?, "
        "narrator=?, illustrator=?, external_rating=?, rating_source=?, "
        "match_confidence=?, status=?, source_url=?, "
        "hand_edited=0, enrich_override=0 "
        "WHERE item_id=?",
        (db.tags_to_json(db.normalize_tags(conn, db.GENRE, cand.get("genre"))),
         cand.get("series"),
         cand.get("series_number"), db.tags_to_json(cand.get("authors")),
         db.tags_to_json(cand.get("narrator")),
         db.tags_to_json(cand.get("illustrator")),
         cand.get("rating"), cand["source"] if cand.get("rating") is not None else None,
         confidence, status, cand.get("url"), item_id))
    conn.commit()

def series_from_title(cleaned, num_hint=None):
    """The series name and number an item's OWN title states, or (None, None).

    Takes clean_title's two return values. The number is read by
    parse_series, which understands the bare "Vol. 3" spelling that
    covers 675 items -- clean_title's own hint understands only the
    parenthesized "(Book 1)" one and fires on 3. Widening clean_title
    instead was measured and rejected: it strips the marker from the
    cleaned title, which is what feeds every source lookup and score, and
    collapses 2,308 distinct enrichable titles to 1,894. See
    docs/superpowers/specs/2026-08-01-series-number-fill-design.md.

    Only a numbered volume answers. A collection word states no number,
    so an omnibus gets (None, None) rather than an invented denominator.
    """
    found = parse_series(cleaned, num_hint)
    if found.kind != "volume" or found.number is None:
        return None, None
    return found.display, float(found.number)

_RESET_FIELDS = ("genre", "series", "series_number", "authors", "narrator",
                 "illustrator", "external_rating", "rating_source",
                 "match_confidence", "source_url", "candidates", "pre_edit")

def reset(db_path="catalog.db", reviews_only=False, _conn=None):
    """Wipe enrichment back to pending; never touches the items table,
    so my_rating and type overrides always survive. --reset-reviews also
    spares hand-edited rows (hand_edited=1) so typed-in work is kept;
    re-enriched rows are swept, since their values came from a source."""
    conn = _conn or db.connect(db_path)
    where = "status='manually_fixed' AND hand_edited=0" if reviews_only \
            else "status != 'pending'"
    # hand_edited/enrich_override are NOT NULL, so they are set explicitly
    # here and must never join _RESET_FIELDS.
    n = conn.execute(
        "UPDATE enrichment SET status='pending', "
        "hand_edited=0, enrich_override=0, "
        + ", ".join(f"{f}=NULL" for f in _RESET_FIELDS)
        + f" WHERE {where}").rowcount
    conn.commit()
    what = "manual review choices" if reviews_only else "enriched items"
    print(f"Reset {n} {what} to pending; run 'enrich' to re-match them.")
    if _conn is None:
        conn.close()
    return n

def override_edited(db_path="catalog.db", retry=False, _conn=None, _input=None):
    """Queue every hand-edited row for re-enrichment, then run.

    Queuing without running would leave a large queued set lying around,
    which is the state this flag is riskiest in - so it does both. Gated
    behind a typed word rather than y/N: this rewrites every hand edit in
    the catalog at once, and a typed word cannot be a stray keypress.
    Returns the number of rows queued (0 if refused or nothing to do).
    """
    conn = _conn or db.connect(db_path)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM enrichment WHERE hand_edited=1").fetchone()[0]
        if n == 0:
            print("No hand-edited items to re-enrich.")
            return 0
        ask = _input
        if ask is None:
            if not sys.stdin.isatty():
                # deliberately no --yes: this must not fire from a script
                print("Refusing to re-enrich hand edits without an "
                      "interactive confirmation.")
                return 0
            ask = input
        print(f"{n} hand-edited items will be re-enriched. Confident matches\n"
              "overwrite your typed values (Revert stays available per item).")
        if ask("Type OVERRIDE to continue: ").strip() != "OVERRIDE":
            print("Aborted; nothing was changed.")
            return 0
        conn.execute("UPDATE enrichment SET enrich_override=1 WHERE hand_edited=1")
        conn.commit()
        run(db_path=db_path, retry=retry, _conn=conn)
        return n
    finally:
        if _conn is None:
            conn.close()

def run(db_path="catalog.db", sources=None, _conn=None, retry=False):
    conn = _conn or db.connect(db_path)
    if sources is None:
        sources = _default_sources(conn, offline=True)
    statuses = ("pending", "unmatched") if retry else ("pending",)
    items = conn.execute(
        "SELECT i.id, i.name, i.type, e.enrich_override FROM items i "
        "JOIN enrichment e ON e.item_id = i.id "
        "WHERE e.status IN (%s) OR e.enrich_override=1"
        % ",".join("?" * len(statuses)), statuses).fetchall()
    # The tallies are the live scoreboard *and* what the summary reports,
    # so the two can never drift apart.
    prog = Progress(conn, "enrich", total=len(items), phase="Item",
                    tallies=("matched", "review", "unmatched", "skipped", "errors"))
    for item in items:
        prog.step(item["name"])  # announce BEFORE the (slow) lookups start
        override = bool(item["enrich_override"])
        if item["type"] in ("music", "android"):
            # soundtracks/albums/APK games have nothing to gain from book databases
            if override:
                # an overridden row is never downgraded, only disarmed
                conn.execute("UPDATE enrichment SET enrich_override=0 "
                             "WHERE item_id=?", (item["id"],))
            else:
                conn.execute("UPDATE enrichment SET status='skipped' "
                             "WHERE item_id=?", (item["id"],))
                prog.count("skipped")
            conn.commit()
            continue
        cleaned, num_hint = clean_title(item["name"])
        best, best_conf, scored = None, 0.0, []
        had_error = False
        for sname in SOURCE_ORDER.get(item["type"], SOURCE_ORDER["ebook"]):
            src = sources.get(sname)
            if src is None:
                continue
            try:
                cands = src.lookup(cleaned)
            except CacheMiss:
                continue  # not harvested for this item; nothing to score
            except Exception as exc:  # noqa: BLE001
                prog.log(f"  {sname} failed for '{cleaned}': {exc}")
                had_error = True
                continue
            for cand in cands:
                conf = score(cleaned, None, cand.get("title"), cand.get("authors"))
                scored.append({**cand, "confidence": round(conf, 3)})
                if conf > best_conf:
                    best, best_conf = cand, conf
        # No early break: every harvested source is scored.
        status = status_for(best_conf)
        if override and not (best is not None and status == "matched"):
            # An overridden row can only ever be traded for a confident
            # match. Anything else leaves it exactly as it was - no status
            # downgrade, no candidates queued - so a failed re-match can
            # never cost a hand edit. One-shot: the flag clears regardless.
            conn.execute("UPDATE enrichment SET enrich_override=0 WHERE item_id=?",
                         (item["id"],))
            conn.commit()
            prog.log(f"  kept hand-edited '{item['name']}': no confident match")
            if had_error:
                prog.count("errors")
            continue
        if best is not None and status in ("matched", "low_confidence"):
            # The title's own series is the LAST resort, never an override:
            # a source that named the series knows it better than a string
            # split does. Both fields, symmetric with apply_candidate.
            from_title, number = series_from_title(cleaned, num_hint)
            if number is not None:
                if best.get("series_number") is None:
                    best = {**best, "series_number": number}
                if best.get("series") is None:
                    best = {**best, "series": from_title}
            if status == "matched":
                apply_candidate(conn, item["id"], best, best_conf, status)
                prog.count("matched")
            else:
                conn.execute(
                    "UPDATE enrichment SET match_confidence=?, status=? WHERE item_id=?",
                    (best_conf, status, item["id"]))
                prog.count("review")
        else:
            conn.execute("UPDATE enrichment SET status='unmatched' WHERE item_id=?",
                         (item["id"],))
            prog.count("unmatched")
        conn.execute("UPDATE enrichment SET candidates=? WHERE item_id=?",
                     (json.dumps(scored), item["id"]))
        conn.commit()
        if had_error:
            prog.count("errors")
    matched = prog.tallies["matched"]
    summary = (f"Enriched {len(items)} items: {matched} matched automatically, "
               f"{len(items) - matched} need review or retry.")
    if prog.tallies["errors"]:
        summary += (f"\n{prog.tallies['errors']} items hit source errors while "
                    f"matching; check the log above.")
    prog.finish(summary)
    if _conn is None:
        conn.close()

def _winning_candidate(candidates_json):
    """The highest-confidence candidate from a stored candidates blob."""
    try:
        cands = json.loads(candidates_json) if candidates_json else []
    except (TypeError, ValueError):
        return None
    return max(cands, key=lambda c: c.get("confidence", 0.0), default=None)

def credits(db_path="catalog.db", comicvine=None, _conn=None):
    """Fill writer/illustrator for matched comics from their first issue.

    Resumable: comics already carrying an illustrator, or whose winning
    candidate has no first_issue_api_url, are skipped. Returns the count
    updated.
    """
    conn = _conn or db.connect(db_path)
    if comicvine is None:
        comicvine = SOURCE_CLASSES["comicvine"](conn)
    rows = conn.execute(
        "SELECT e.item_id, e.candidates FROM enrichment e JOIN items i "
        "ON i.id = e.item_id WHERE i.type='comic' AND e.status='matched' "
        "AND e.illustrator IS NULL").fetchall()
    prog = Progress(conn, "credits", total=len(rows), phase="Comic")
    updated = 0
    for row in rows:
        cand = _winning_candidate(row["candidates"]) or {}
        issue_url = (cand.get("extra") or {}).get("first_issue_api_url")
        prog.step(cand.get("title", ""))
        if not issue_url:
            continue
        try:
            writers, artists = comicvine.credits(issue_url)
        except Exception as exc:  # noqa: BLE001
            print(f"  credits failed for '{cand.get('title')}': {exc}", flush=True)
            continue
        if writers or artists:
            conn.execute(
                "UPDATE enrichment SET authors=COALESCE(?, authors), "
                "illustrator=? WHERE item_id=?",
                (db.tags_to_json([writers]) if writers else None,
                 db.tags_to_json(artists) if artists else None, row["item_id"]))
            conn.commit()
            updated += 1
    prog.finish(f"Filled credits for {updated} comics.")
    if _conn is None:
        conn.close()
    return updated

def fill_series(db_path="catalog.db", _conn=None):
    """Fill series/series_number from each item's own title, NULL cells only.

    A top-up for rows already processed: enrich.run only visits pending
    items and only writes on a match, so 562 of the 667 items whose title
    states a volume number were already 'matched' when the fallback
    landed and would never be revisited. Returns the number of rows
    amended.

    Deliberately not routed through apply_candidate, which rewrites
    status, match_confidence, hand_edited and enrich_override and
    snapshots pre_edit. This pass owns two columns and touches nothing
    else about the row.

    Every status is visited, including 'unmatched'. The value comes from
    the item's own name, so a source having failed to match it says
    nothing about whether its title states a volume.

    Idempotent, which is load-bearing rather than tidy: both columns are
    in _RESET_FIELDS, so a reset clears the fill and re-running this is
    the recovery path.
    """
    conn = _conn or db.connect(db_path)
    rows = conn.execute(
        "SELECT e.item_id, i.name, e.series, e.series_number FROM enrichment e "
        "JOIN items i ON i.id = e.item_id "
        "WHERE e.series IS NULL OR e.series_number IS NULL").fetchall()
    filled = 0
    for row in rows:
        name, number = series_from_title(*clean_title(row["name"]))
        if number is None:
            continue
        if row["series"] is not None and row["series_number"] is not None:
            continue          # nothing left to fill; COALESCE would no-op
        # COALESCE and not a plain SET: it states the no-override rule in
        # the one place that can enforce it, so a half-filled row keeps
        # whichever cell it already had. The Python guard above is for the
        # COUNT, not for correctness -- sqlite3's total_changes is
        # cumulative over the connection and rowcount counts rows matched
        # rather than rows altered, so neither can tell a real fill from a
        # COALESCE that wrote a value back onto itself.
        conn.execute(
            "UPDATE enrichment SET series=COALESCE(series, ?), "
            "series_number=COALESCE(series_number, ?) WHERE item_id=?",
            (name, number, row["item_id"]))
        filled += 1
    conn.commit()
    print(f"Filled the series on {filled} items from their own titles.")
    if _conn is None:
        conn.close()
    return filled
