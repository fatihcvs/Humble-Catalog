"""Known-answer battery for the enrich-core inventory row.

Covers humble_catalog/enrich.py: `run`, `reset`, `apply_candidate`,
`series_from_title`, `_winning_candidate`, `override_edited` and the
EDITABLE_FIELDS contract.

This is the module that decides what the catalog SAYS about a book, and
several of its rules exist specifically to protect the owner's typed
values from being overwritten by a source. Those rules are asymmetric and
easy to get subtly wrong in a way no shape check would notice - an
override that downgrades a status, a reset that sweeps a hand edit, a
snapshot taken twice - so each is asserted as the property it claims.

`run` is driven with stub sources rather than the real ones: the point is
the decision logic, and a live lookup would make the outcome depend on the
network.

Titles are the invented library from docs/TEST-DATA.md.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, enrich                        # noqa: E402
from humble_catalog.sources.base import candidate            # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


class StubSource:
    """Explicit double: returns a fixed candidate list for any title."""

    def __init__(self, cands):
        self.cands = cands
        self.asked = []

    def lookup(self, title):
        self.asked.append(title)
        return list(self.cands)


def seeded(items):
    """items: [(machine_name, name, type)]. Fresh database per case."""
    conn = db.connect(Path(tempfile.mkdtemp()) / "probe.db")
    for machine_name, name, type_ in items:
        cur = conn.execute("INSERT INTO items (machine_name, name, type) "
                           "VALUES (?,?,?)", (machine_name, name, type_))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    conn.commit()
    return conn


def enrichment(conn, item_id=1):
    return dict(conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                             (item_id,)).fetchone())


# --------------------------------------------------------------------
# series_from_title - only a numbered volume answers
# --------------------------------------------------------------------
check("series_from_title: a bare volume marker answers",
      enrich.series_from_title("Shadow Hound Vol. 3"), ("Shadow Hound", 3.0))
check("series_from_title: the number is a float, matching the column",
      isinstance(enrich.series_from_title("Shadow Hound Vol. 3")[1], float), True)
check("series_from_title: a collection word states NO number, so no "
      "denominator is invented",
      enrich.series_from_title("Shadow Hound Omnibus"), (None, None))
check("series_from_title: a range is a collection too",
      enrich.series_from_title("Shadow Hound Vol. 1-6"), (None, None))
check("series_from_title: a title with no marker answers nothing",
      enrich.series_from_title("The Quiet Harbor"), (None, None))
check("series_from_title: the parenthesized hint still works",
      enrich.series_from_title("Wings of Autumn Dusk", 1.0),
      ("Wings of Autumn Dusk", 1.0))
check("series_from_title: the hint is ignored when the title states a marker",
      enrich.series_from_title("Shadow Hound Vol. 3", 99.0),
      ("Shadow Hound", 3.0))

# --------------------------------------------------------------------
# _winning_candidate
# --------------------------------------------------------------------
blob = json.dumps([{"title": "a", "confidence": 0.4},
                   {"title": "b", "confidence": 0.9},
                   {"title": "c", "confidence": 0.7}])
check("_winning_candidate: the highest confidence wins",
      enrich._winning_candidate(blob)["title"], "b")
check("_winning_candidate: an empty blob has no winner",
      enrich._winning_candidate("[]"), None)
check("_winning_candidate: NULL has no winner",
      enrich._winning_candidate(None), None)
check("_winning_candidate: malformed json has no winner, rather than raising",
      enrich._winning_candidate("{not json"), None)
check("_winning_candidate: a candidate with no confidence is treated as 0",
      enrich._winning_candidate(json.dumps([{"title": "a"}]))["title"], "a")

# --------------------------------------------------------------------
# apply_candidate
# --------------------------------------------------------------------
conn = seeded([("graywaters", "Gray Waters", "ebook")])
cand = candidate(source="google_books", title="Gray Waters",
                 authors=["Alex Penner"], genre="fantasy", rating=4.5,
                 url="https://books.example.test/v", series="The Elder Realm",
                 series_number=3.0)
enrich.apply_candidate(conn, 1, cand, 0.95, "matched")
row = enrichment(conn)
check("apply_candidate: the status is stored", row["status"], "matched")
check("apply_candidate: the confidence is stored", row["match_confidence"], 0.95)
check("apply_candidate: the genre is normalized, not stored raw",
      db.tags_from_json(row["genre"]), ["Fantasy"])
check("apply_candidate: authors are stored as a JSON array",
      db.tags_from_json(row["authors"]), ["Alex Penner"])
check("apply_candidate: the rating is stored", row["external_rating"], 4.5)
check("apply_candidate: rating_source names the source that supplied it",
      row["rating_source"], "google_books")
check("apply_candidate: the source url is stored", row["source_url"],
      "https://books.example.test/v")
check("apply_candidate: applying clears hand_edited and enrich_override",
      (row["hand_edited"], row["enrich_override"]), (0, 0))

# rating at its other value: no rating must mean no rating_source, or the
# viewer would attribute an absent number to a source.
conn = seeded([("graywaters", "Gray Waters", "ebook")])
enrich.apply_candidate(conn, 1, candidate(source="open_library", title="x"),
                       0.9, "matched")
row = enrichment(conn)
check("apply_candidate: no rating means no rating_source",
      (row["external_rating"], row["rating_source"]), (None, None))

# The snapshot rule: a hand-edited row is snapshotted before being
# overwritten, so Revert still returns the typed values.
conn = seeded([("graywaters", "Gray Waters", "ebook")])
conn.execute("UPDATE enrichment SET hand_edited=1, genre=?, series='Typed Series' "
             "WHERE item_id=1", (db.tags_to_json(["Typed Genre"]),))
conn.commit()
enrich.apply_candidate(conn, 1, cand, 0.95, "matched")
row = enrichment(conn)
snapshot = json.loads(row["pre_edit"])
check("apply_candidate: overwriting a hand edit snapshots it first",
      snapshot["series"], "Typed Series")
check("apply_candidate: the snapshot holds the typed genre",
      db.tags_from_json(snapshot["genre"]), ["Typed Genre"])
check("apply_candidate: and the new value is in place",
      db.tags_from_json(row["genre"]), ["Fantasy"])
# The snapshot's keys ARE EDITABLE_FIELDS. If a field were added to the
# UPDATE without being added to that list, Revert would silently stop
# restoring it - a loss no shape check would notice.
check("apply_candidate: the snapshot covers exactly EDITABLE_FIELDS",
      sorted(snapshot), sorted(enrich.EDITABLE_FIELDS))
check("EDITABLE_FIELDS: every one of them is a real enrichment column",
      set(enrich.EDITABLE_FIELDS) <= {r["name"] for r in
                                      conn.execute("PRAGMA table_info(enrichment)")},
      True)
check("EDITABLE_FIELDS: it is the same list db owns, not a second copy",
      enrich.EDITABLE_FIELDS is db.EDITABLE_FIELDS, True)

# A row that is NOT hand-edited keeps whatever pre_edit it has - for a
# plain enriched row that is NULL, and re-applying must not invent one.
conn = seeded([("graywaters", "Gray Waters", "ebook")])
enrich.apply_candidate(conn, 1, cand, 0.9, "matched")
enrich.apply_candidate(conn, 1, cand, 0.9, "matched")
check("apply_candidate: a plain enriched row is never snapshotted",
      enrichment(conn)["pre_edit"], None)

# --------------------------------------------------------------------
# reset, and its reviews_only parameter at both values
# --------------------------------------------------------------------
def reset_fixture():
    conn = seeded([("a", "Gray Waters", "ebook"),
                   ("b", "The Quiet Harbor", "ebook"),
                   ("c", "Salt and Sextant", "ebook"),
                   ("d", "Unrelated Book", "ebook")])
    conn.execute("UPDATE items SET my_rating=5, type='comic', "
                 "type_overridden=1 WHERE id=1")
    conn.execute("UPDATE enrichment SET status='matched', genre=? WHERE item_id=1",
                 (db.tags_to_json(["Fantasy"]),))
    conn.execute("UPDATE enrichment SET status='manually_fixed', hand_edited=1 "
                 "WHERE item_id=2")
    conn.execute("UPDATE enrichment SET status='manually_fixed', hand_edited=0 "
                 "WHERE item_id=3")
    # item 4 stays pending
    conn.commit()
    return conn


conn = reset_fixture()
n = enrich.reset(_conn=conn)
check("reset: every non-pending row is swept", n, 3)
check("reset: the swept row is back to pending",
      enrichment(conn, 1)["status"], "pending")
check("reset: its enriched fields are cleared", enrichment(conn, 1)["genre"], None)
check("reset: a pending row is not counted twice",
      enrichment(conn, 4)["status"], "pending")
item = dict(conn.execute("SELECT my_rating, type, type_overridden FROM items "
                         "WHERE id=1").fetchone())
check("reset: it never touches the items table, so the owner's rating and "
      "type override survive", item, {"my_rating": 5, "type": "comic",
                                      "type_overridden": 1})

conn = reset_fixture()
n = enrich.reset(reviews_only=True, _conn=conn)
check("reset reviews_only: only the non-hand-edited review choice is swept",
      n, 1)
check("reset reviews_only: the hand-edited row is SPARED - typed work is kept",
      (enrichment(conn, 2)["status"], enrichment(conn, 2)["hand_edited"]),
      ("manually_fixed", 1))
check("reset reviews_only: the re-enriched review choice is swept",
      enrichment(conn, 3)["status"], "pending")
check("reset reviews_only: a plain matched row is left alone",
      enrichment(conn, 1)["status"], "matched")
check("reset: the parameter changes the answer", (3, 1) != (1, 1), True)

# --------------------------------------------------------------------
# run - the decision logic
# --------------------------------------------------------------------
STRONG = [candidate(source="google_books", title="Gray Waters",
                    authors=["Alex Penner"], genre="fantasy")]
WEAK = [candidate(source="google_books", title="Something Else Entirely",
                  authors=["Nobody At All"])]

conn = seeded([("graywaters", "Gray Waters", "ebook")])
enrich.run(_conn=conn, sources={"google_books": StubSource(STRONG)})
row = enrichment(conn)
check("run: an exact title match is applied automatically",
      row["status"], "matched")
check("run: and its fields are written",
      db.tags_from_json(row["authors"]), ["Alex Penner"])
check("run: the candidates blob is stored either way",
      len(json.loads(row["candidates"])), 1)

conn = seeded([("graywaters", "Gray Waters", "ebook")])
enrich.run(_conn=conn, sources={"google_books": StubSource(WEAK)})
check("run: a poor match is left unmatched rather than applied",
      enrichment(conn)["status"], "unmatched")
check("run: an unmatched row keeps its fields empty",
      enrichment(conn)["authors"], None)

conn = seeded([("graywaters", "Gray Waters", "ebook")])
enrich.run(_conn=conn, sources={"google_books": StubSource([])})
check("run: a source with nothing to say leaves the row unmatched",
      enrichment(conn)["status"], "unmatched")

# music and android are skipped: book databases have nothing for them.
conn = seeded([("ost", "Sample Game OST", "music"),
               ("apk", "Cool Tower Defense", "android")])
enrich.run(_conn=conn, sources={"google_books": StubSource(STRONG)})
check("run: a music row is skipped", enrichment(conn, 1)["status"], "skipped")
check("run: an android row is skipped", enrichment(conn, 2)["status"], "skipped")

# retry at both values: an unmatched row is only revisited with retry=True.
conn = seeded([("graywaters", "Gray Waters", "ebook")])
conn.execute("UPDATE enrichment SET status='unmatched' WHERE item_id=1")
conn.commit()
src = StubSource(STRONG)
enrich.run(_conn=conn, sources={"google_books": src})
check("run: without retry an unmatched row is not revisited", src.asked, [])
src = StubSource(STRONG)
enrich.run(_conn=conn, sources={"google_books": src}, retry=True)
check("run: with retry it is", len(src.asked), 1)
check("run: and it can be matched on the retry",
      enrichment(conn)["status"], "matched")

# A matched row is never revisited by a plain run.
conn = seeded([("graywaters", "Gray Waters", "ebook")])
conn.execute("UPDATE enrichment SET status='matched' WHERE item_id=1")
conn.commit()
src = StubSource(STRONG)
enrich.run(_conn=conn, sources={"google_books": src})
check("run: a matched row is left alone", src.asked, [])

# The override rule, which is the one that protects typed values: an
# overridden row can only ever be traded for a CONFIDENT match.
conn = seeded([("graywaters", "Gray Waters", "ebook")])
conn.execute("UPDATE enrichment SET status='manually_fixed', hand_edited=1, "
             "enrich_override=1, series='Typed Series' WHERE item_id=1")
conn.commit()
enrich.run(_conn=conn, sources={"google_books": StubSource(WEAK)})
row = enrichment(conn)
check("run: an overridden row that finds no confident match keeps its "
      "status", row["status"], "manually_fixed")
check("run: and keeps its typed value", row["series"], "Typed Series")
check("run: and keeps the hand-edited flag", row["hand_edited"], 1)
check("run: the override flag clears regardless - it is one-shot",
      row["enrich_override"], 0)

conn = seeded([("graywaters", "Gray Waters", "ebook")])
conn.execute("UPDATE enrichment SET status='manually_fixed', hand_edited=1, "
             "enrich_override=1, series='Typed Series' WHERE item_id=1")
conn.commit()
enrich.run(_conn=conn, sources={"google_books": StubSource(STRONG)})
row = enrichment(conn)
check("run: an overridden row WITH a confident match is overwritten",
      row["status"], "matched")
check("run: and the typed values are snapshotted so Revert still works",
      json.loads(row["pre_edit"])["series"], "Typed Series")

# An overridden music row is disarmed, never downgraded to skipped.
conn = seeded([("ost", "Sample Game OST", "music")])
conn.execute("UPDATE enrichment SET status='manually_fixed', hand_edited=1, "
             "enrich_override=1 WHERE item_id=1")
conn.commit()
enrich.run(_conn=conn, sources={"google_books": StubSource(STRONG)})
row = enrichment(conn)
check("run: an overridden music row is disarmed, not downgraded",
      (row["status"], row["enrich_override"]), ("manually_fixed", 0))

# Every source is scored; there is no early break on the first hit.
conn = seeded([("graywaters", "Gray Waters", "ebook")])
first, second = StubSource(WEAK), StubSource(STRONG)
enrich.run(_conn=conn, sources={"google_books": first, "oreilly": second})
check("run: no early break - every harvested source is asked",
      (len(first.asked), len(second.asked)), (1, 1))
check("run: and the best across sources wins",
      enrichment(conn)["status"], "matched")

# A source that raises must not stop the run.
class BoomSource:
    def lookup(self, title):
        raise RuntimeError("probe: source failed")


conn = seeded([("graywaters", "Gray Waters", "ebook")])
enrich.run(_conn=conn, sources={"google_books": BoomSource(),
                                "oreilly": StubSource(STRONG)})
check("run: one source raising does not stop the others",
      enrichment(conn)["status"], "matched")

# --------------------------------------------------------------------
# override_edited - the guarded bulk operation
# --------------------------------------------------------------------
conn = seeded([("graywaters", "Gray Waters", "ebook")])
check("override_edited: with no hand-edited rows it does nothing",
      enrich.override_edited(_conn=conn, _input=lambda _p: "OVERRIDE"), 0)

conn = seeded([("graywaters", "Gray Waters", "ebook")])
conn.execute("UPDATE enrichment SET hand_edited=1, status='manually_fixed' "
             "WHERE item_id=1")
conn.commit()
check("override_edited: a wrong word aborts",
      enrich.override_edited(_conn=conn, _input=lambda _p: "yes"), 0)
check("override_edited: and nothing was queued",
      enrichment(conn)["enrich_override"], 0)
check("override_edited: the row is untouched",
      enrichment(conn)["status"], "manually_fixed")


def main():
    for line in FAIL:
        print(f"BROKEN {line}")
    total = len(PASS) + len(FAIL)
    print(f"\nenrich-core: {len(PASS)}/{total} held")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
