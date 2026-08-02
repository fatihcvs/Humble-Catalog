"""Known-answer battery for the enrich-topups inventory row.

Covers humble_catalog/enrich.py: `credits`, `fill_series` and
`override_edited` - the three passes that amend rows enrich.run has
already finished with.

Each one is a top-up over existing data, so the property that matters is
what it does NOT touch: `fill_series` owns two columns and must not
rewrite a status or a hand edit, `credits` must skip what it has already
done so a re-run is free, and `override_edited` must refuse without an
interactive confirmation. Those are asserted by reading back the columns
that should not have moved, not by checking the pass reported a number.

Titles and names are invented, from docs/TEST-DATA.md.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, enrich                        # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def seeded(items):
    conn = db.connect(Path(tempfile.mkdtemp()) / "probe.db")
    for machine_name, name, type_ in items:
        cur = conn.execute("INSERT INTO items (machine_name, name, type) "
                           "VALUES (?,?,?)", (machine_name, name, type_))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    conn.commit()
    return conn


def row(conn, item_id=1):
    return dict(conn.execute("SELECT * FROM enrichment WHERE item_id=?",
                             (item_id,)).fetchone())


def candidates_blob(first_issue_url="https://comicvine.gamespot.com/api/issue/1/",
                    title="Shadow Hound Vol 1", confidence=0.95):
    extra = {"first_issue_api_url": first_issue_url} if first_issue_url else {}
    return json.dumps([{"title": title, "confidence": confidence,
                        "extra": extra}])


class StubComicVine:
    """Explicit double for the one method credits uses."""

    def __init__(self, answer=("Bo Writer", "Alex Artist"), boom=False):
        self.answer = answer
        self.boom = boom
        self.asked = []

    def credits(self, issue_api_url):
        self.asked.append(issue_api_url)
        if self.boom:
            raise RuntimeError("probe: comicvine failed")
        return self.answer


# --------------------------------------------------------------------
# credits
# --------------------------------------------------------------------
conn = seeded([("shadowhound", "Shadow Hound Vol 1", "comic")])
conn.execute("UPDATE enrichment SET status='matched', candidates=? "
             "WHERE item_id=1", (candidates_blob(),))
conn.commit()
stub = StubComicVine()
check("credits: one comic is filled", enrich.credits(_conn=conn, comicvine=stub), 1)
check("credits: the issue url from the winning candidate is the one asked",
      stub.asked, ["https://comicvine.gamespot.com/api/issue/1/"])
check("credits: the writer lands in authors",
      db.tags_from_json(row(conn)["authors"]), ["Bo Writer"])
check("credits: the artist lands in illustrator",
      db.tags_from_json(row(conn)["illustrator"]), ["Alex Artist"])

# Resumable: a second pass must ask nothing, because the row now carries
# an illustrator. That is what makes a re-run free rather than a re-fetch.
stub2 = StubComicVine()
check("credits: a second pass fills nothing",
      enrich.credits(_conn=conn, comicvine=stub2), 0)
check("credits: and asks nothing - the pass is resumable", stub2.asked, [])
conn.close()

# The three skip conditions, each on its own.
conn = seeded([("shadowhound", "Shadow Hound Vol 1", "comic")])
conn.execute("UPDATE enrichment SET status='low_confidence', candidates=? "
             "WHERE item_id=1", (candidates_blob(),))
conn.commit()
stub = StubComicVine()
check("credits: a comic that is not matched is skipped",
      (enrich.credits(_conn=conn, comicvine=stub), stub.asked), (0, []))
conn.close()

conn = seeded([("graywaters", "Gray Waters", "ebook")])
conn.execute("UPDATE enrichment SET status='matched', candidates=? "
             "WHERE item_id=1", (candidates_blob(),))
conn.commit()
stub = StubComicVine()
check("credits: a non-comic is skipped whatever its status",
      (enrich.credits(_conn=conn, comicvine=stub), stub.asked), (0, []))
conn.close()

conn = seeded([("shadowhound", "Shadow Hound Vol 1", "comic")])
conn.execute("UPDATE enrichment SET status='matched', candidates=? "
             "WHERE item_id=1", (candidates_blob(first_issue_url=None),))
conn.commit()
stub = StubComicVine()
check("credits: a candidate with no first-issue url is skipped",
      (enrich.credits(_conn=conn, comicvine=stub), stub.asked), (0, []))
conn.close()

# A source failure must cost one comic, never the pass.
conn = seeded([("shadowhound", "Shadow Hound Vol 1", "comic"),
               ("moonfall", "Moonfall Vol. 1", "comic")])
for item_id in (1, 2):
    conn.execute("UPDATE enrichment SET status='matched', candidates=? "
                 "WHERE item_id=?", (candidates_blob(), item_id))
conn.commit()


class OneBoom:
    def __init__(self):
        self.calls = 0

    def credits(self, url):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("probe: comicvine failed")
        return ("Bo Writer", "Alex Artist")


check("credits: one failure does not stop the pass",
      enrich.credits(_conn=conn, comicvine=OneBoom()), 1)
check("credits: the failed comic is left untouched, so a re-run retries it",
      row(conn, 1)["illustrator"], None)
conn.close()

# Nothing to say means nothing written.
conn = seeded([("shadowhound", "Shadow Hound Vol 1", "comic")])
conn.execute("UPDATE enrichment SET status='matched', candidates=? "
             "WHERE item_id=1", (candidates_blob(),))
conn.commit()
check("credits: a source returning no names writes nothing",
      enrich.credits(_conn=conn, comicvine=StubComicVine(answer=(None, None))), 0)
check("credits: and the columns stay empty",
      (row(conn)["authors"], row(conn)["illustrator"]), (None, None))
conn.close()

# --------------------------------------------------------------------
# fill_series
# --------------------------------------------------------------------
conn = seeded([("sh2", "Shadow Hound Vol. 2", "comic")])
conn.execute("UPDATE enrichment SET status='matched' WHERE item_id=1")
conn.commit()
check("fill_series: a volume marker fills both cells",
      enrich.fill_series(_conn=conn), 1)
check("fill_series: the series name comes from the title",
      row(conn)["series"], "Shadow Hound")
check("fill_series: and the number", row(conn)["series_number"], 2.0)
check("fill_series: it touches nothing else about the row",
      (row(conn)["status"], row(conn)["hand_edited"], row(conn)["match_confidence"]),
      ("matched", 0, None))
check("fill_series: it is idempotent, which is the recovery path after a "
      "reset", enrich.fill_series(_conn=conn), 0)
conn.close()

# The no-override rule, stated by COALESCE: a half-filled row keeps the
# cell it already had and gains only the missing one.
conn = seeded([("sh5", "Shadow Hound Vol. 5", "comic")])
conn.execute("UPDATE enrichment SET series='Shadow Hound Legends', "
             "hand_edited=1 WHERE item_id=1")
conn.commit()
check("fill_series: a half-filled row is amended", enrich.fill_series(_conn=conn), 1)
check("fill_series: the typed series name is NOT overwritten",
      row(conn)["series"], "Shadow Hound Legends")
check("fill_series: only the missing number is added",
      row(conn)["series_number"], 5.0)
check("fill_series: and the hand-edited flag is left alone",
      row(conn)["hand_edited"], 1)
conn.close()

# Every status is visited: the value comes from the item's own name, so a
# source having failed says nothing about whether the title states a volume.
conn = seeded([("sh1", "Shadow Hound Vol. 1", "comic"),
               ("sh3", "Shadow Hound Vol. 3", "comic"),
               ("sh4", "Shadow Hound Vol. 4", "comic")])
conn.execute("UPDATE enrichment SET status='unmatched' WHERE item_id=1")
conn.execute("UPDATE enrichment SET status='skipped' WHERE item_id=2")
conn.execute("UPDATE enrichment SET status='manually_fixed' WHERE item_id=3")
conn.commit()
check("fill_series: unmatched, skipped and manually_fixed rows are all visited",
      enrich.fill_series(_conn=conn), 3)
check("fill_series: and none of their statuses moved",
      [row(conn, i)["status"] for i in (1, 2, 3)],
      ["unmatched", "skipped", "manually_fixed"])
conn.close()

# A title stating no number fills nothing - no invented denominator.
conn = seeded([("omni", "Shadow Hound Omnibus", "comic"),
               ("range", "Shadow Hound Vol. 1-6", "comic"),
               ("plain", "The Quiet Harbor", "ebook")])
check("fill_series: a collection word, a range and a plain title fill nothing",
      enrich.fill_series(_conn=conn), 0)
check("fill_series: their cells stay empty",
      [row(conn, i)["series_number"] for i in (1, 2, 3)], [None, None, None])
conn.close()

# A row with BOTH cells already set is not selected at all, which is what
# the WHERE clause is for.
conn = seeded([("sh2", "Shadow Hound Vol. 2", "comic")])
conn.execute("UPDATE enrichment SET series='Typed', series_number=9 "
             "WHERE item_id=1")
conn.commit()
check("fill_series: a fully filled row is not selected",
      enrich.fill_series(_conn=conn), 0)
check("fill_series: and keeps both of its values",
      (row(conn)["series"], row(conn)["series_number"]), ("Typed", 9.0))
conn.close()

# --------------------------------------------------------------------
# override_edited - the guarded bulk operation
# --------------------------------------------------------------------
def with_hand_edits(n=2):
    conn = seeded([(f"m{i}", f"Item {i}", "ebook") for i in range(n)])
    conn.execute("UPDATE enrichment SET hand_edited=1, status='manually_fixed'")
    conn.commit()
    return conn


conn = seeded([("graywaters", "Gray Waters", "ebook")])
check("override_edited: with nothing hand-edited it does nothing",
      enrich.override_edited(_conn=conn, _input=lambda _p: "OVERRIDE"), 0)
conn.close()

conn = with_hand_edits()
check("override_edited: a wrong word aborts",
      enrich.override_edited(_conn=conn, _input=lambda _p: "override"), 0)
check("override_edited: the confirmation is case-sensitive, so a near-miss "
      "queues nothing",
      [row(conn, i)["enrich_override"] for i in (1, 2)], [0, 0])
check("override_edited: and no status moved",
      [row(conn, i)["status"] for i in (1, 2)],
      ["manually_fixed", "manually_fixed"])
conn.close()

conn = with_hand_edits()
check("override_edited: an empty answer aborts",
      enrich.override_edited(_conn=conn, _input=lambda _p: ""), 0)
conn.close()

conn = with_hand_edits()
answers = []


def confirm(prompt):
    answers.append(prompt)
    return "  OVERRIDE  "


check("override_edited: the typed word is accepted with surrounding space, "
      "and it queues every hand-edited row",
      enrich.override_edited(_conn=conn, _input=confirm), 2)
check("override_edited: the confirmation was actually asked for",
      len(answers), 1)
# run() executes inside override_edited, so the flag is consumed by it and
# the rows come back disarmed rather than still queued.
check("override_edited: the override flag is consumed by the run it triggers",
      [row(conn, i)["enrich_override"] for i in (1, 2)], [0, 0])
conn.close()


def main():
    for line in FAIL:
        print(f"BROKEN {line}")
    total = len(PASS) + len(FAIL)
    print(f"\nenrich-topups: {len(PASS)}/{total} held")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
