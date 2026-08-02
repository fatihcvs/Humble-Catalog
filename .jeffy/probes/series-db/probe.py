"""Known-answer battery for the series-db inventory row.

Covers `series.owned_volumes` and `series.describe` against a seeded
database. `collapse` and `sort_key` belong to the series-report row and
are exercised there; they appear here only where `describe` composes them.

Every title is invented, from docs/TEST-DATA.md. Fresh database per case.
"""
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, series  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def seeded(*names):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = db.connect(pathlib.Path(tmp.name))
    for i, name in enumerate(names):
        cur = conn.execute(
            "INSERT INTO items (machine_name, name) VALUES (?,?)",
            (f"mn_{i}", name))
        conn.execute("INSERT INTO enrichment (item_id) VALUES (?)",
                     (cur.lastrowid,))
    return conn


# ------------------------------------------------------------ owned_volumes

def case_volumes_are_indexed_by_series_key():
    conn = seeded("Wings of Autumn Dusk (Book 1)",
                  "Wings of Autumn Dusk (Book 3)")
    index = series.owned_volumes(conn)
    check("one series key holds both volume numbers",
          sorted(index.values(), key=len), [{1, 3}])
    conn.close()


def case_two_series_stay_apart():
    conn = seeded("Wings of Autumn Dusk (Book 1)",
                  "Salt and Sextant, Vol. 2")
    index = series.owned_volumes(conn)
    check("two different series are two keys", len(index), 2)
    conn.close()


def case_a_title_with_no_volume_marker_is_absent():
    conn = seeded("Unrelated Book", "The Quiet Harbor: A Novel")
    check("a title carrying no volume marker indexes nothing",
          series.owned_volumes(conn), {})
    conn.close()


def case_an_empty_catalog_indexes_nothing():
    conn = seeded()
    check("an empty catalog yields an empty index",
          series.owned_volumes(conn), {})
    conn.close()


def case_a_duplicate_volume_is_one_entry():
    # A set, so the same volume held twice cannot inflate the count.
    conn = seeded("Wings of Autumn Dusk (Book 2)",
                  "Wings of Autumn Dusk, Vol. 2")
    index = series.owned_volumes(conn)
    check("the same volume twice is one number",
          [sorted(v) for v in index.values()], [[2]])
    conn.close()


# ------------------------------------------------------------------ describe

def case_an_offered_volume_already_held_is_a_rebuy():
    # The valuable outcome: matched no machine_name yet IS already held.
    conn = seeded("Wings of Autumn Dusk (Book 3)")
    index = series.owned_volumes(conn)
    hit = series.describe("Wings of Autumn Dusk (Book 3)", index)
    check("an already-held volume is flagged already_owned",
          (hit["already_owned"], hit["offered_volume"], hit["owned"]),
          (True, 3, [3]))
    check("and its owned_display reads as a volume list",
          hit["owned_display"], "Vol. 3")
    conn.close()


def case_an_offered_continuation_is_not_a_rebuy():
    conn = seeded("Wings of Autumn Dusk (Book 1)",
                  "Wings of Autumn Dusk (Book 2)")
    index = series.owned_volumes(conn)
    hit = series.describe("Wings of Autumn Dusk (Book 3)", index)
    check("a volume not held is reported without the rebuy flag",
          (hit["already_owned"], hit["offered_volume"]), (False, 3))
    check("and the held run is collapsed", hit["owned_display"], "Vol. 1-2")
    conn.close()


def case_a_series_not_held_at_all_is_none():
    conn = seeded("Wings of Autumn Dusk (Book 1)")
    index = series.owned_volumes(conn)
    check("an offered volume of an unheld series has no line",
          series.describe("Salt and Sextant, Vol. 4", index), None)
    conn.close()


def case_a_title_with_no_series_key_is_none():
    conn = seeded("Wings of Autumn Dusk (Book 1)")
    index = series.owned_volumes(conn)
    check("an offered title with no series key has no line",
          series.describe("Unrelated Book", index), None)
    conn.close()


def case_a_gap_is_rendered_rather_than_smoothed():
    # Reporting an unbroken run the owner does not hold would be the
    # overclaim this feature exists to remove.
    conn = seeded("Wings of Autumn Dusk (Book 1)",
                  "Wings of Autumn Dusk (Book 2)",
                  "Wings of Autumn Dusk (Book 5)")
    index = series.owned_volumes(conn)
    hit = series.describe("Wings of Autumn Dusk (Book 4)", index)
    check("a gap is shown, not smoothed over",
          hit["owned_display"], "Vol. 1-2, 5")
    conn.close()


def case_only_a_range_states_its_own_size():
    conn = seeded("Wings of Autumn Dusk (Book 1)")
    index = series.owned_volumes(conn)
    collection = series.describe("Wings of Autumn Dusk, Vol. 1-3", index)
    check("an explicit range carries a span", collection["span"], [1, 3])
    single = series.describe("Wings of Autumn Dusk (Book 2)", index)
    check("a single volume invents no span", single["span"], None)
    conn.close()


def case_describe_reports_the_offered_title_unchanged():
    conn = seeded("Wings of Autumn Dusk (Book 1)")
    index = series.owned_volumes(conn)
    hit = series.describe("Wings of Autumn Dusk (Book 2)", index)
    check("the offered title comes back exactly as given",
          hit["offered"], "Wings of Autumn Dusk (Book 2)")
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
    print(f"series-db: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
