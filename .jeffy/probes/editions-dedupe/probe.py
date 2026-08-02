"""Known-answer battery for the editions-dedupe inventory row.

Covers humble_catalog/dedupe.py (`dedupe_key`, `find_groups`) and
humble_catalog/editions.py (`edition_key`, `find_groups`).

These decide what the viewer offers to MERGE, so a wrong answer here
either hides a real duplicate or invites the owner to merge two different
books - and both look like a plausible list either way, which is why the
cases below are known answers rather than "the report rendered".

Both modules document that they match EXACTLY after normalization and
reject fuzzy matching as less accurate, so the negative cases matter as
much as the positive ones: the pairs that must NOT group are the measured
justification for that choice.

Titles are the invented library from docs/TEST-DATA.md.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import db, dedupe, editions              # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def same(label, a, b, key):
    check(label, key(a) == key(b), True)


def differ(label, a, b, key):
    check(label, key(a) != key(b), True)


def seeded(items, dismissed=()):
    """A fresh database per case: reusing one carries the previous case's
    rows into the next and trips the machine_name UNIQUE constraint."""
    conn = db.connect(Path(tempfile.mkdtemp()) / "probe.db")
    for machine_name, name, type_ in items:
        conn.execute("INSERT INTO items (machine_name, name, type) "
                     "VALUES (?,?,?)", (machine_name, name, type_))
    for a, b in dismissed:
        conn.execute("INSERT INTO dismissed_pairs (a, b) VALUES (?,?)",
                     tuple(sorted((a, b))))
    conn.commit()
    return conn


# --------------------------------------------------------------------
# dedupe_key - a WITHIN-type key
# --------------------------------------------------------------------
check("dedupe_key: lowercased and space-collapsed",
      dedupe.dedupe_key("  MOONFALL,   Vol. 1  "), "moonfall vol 1")
same("dedupe_key: a comma and casing difference collides",
     "MOONFALL, Vol. 1", "Moonfall Vol. 1", dedupe.dedupe_key)
same("dedupe_key: a curly and a straight apostrophe collide",
     "Innkeeper’s Ledger", "Innkeeper's Ledger", dedupe.dedupe_key)

# The edition spellings, which the regex exists to collapse onto the number.
for spelling in ("Building Widget Services 2e",
                 "Building Widget Services, 2nd Edition",
                 "Building Widget Services: 2nd ed.",
                 "Building Widget Services 2 edition"):
    same(f"dedupe_key: {spelling!r} collides with the base spelling",
         spelling, "Building Widget Services 2e", dedupe.dedupe_key)
check("dedupe_key: the edition NUMBER is kept, so editions stay distinct",
      dedupe.dedupe_key("Building Widget Services 2e")
      != dedupe.dedupe_key("Building Widget Services 3e"), True)
check("dedupe_key: the collapsed form keeps the bare number",
      dedupe.dedupe_key("Building Widget Services, 2nd Edition"),
      "building widget services 2")

# # and + survive, which is the documented exception to the punctuation rule.
differ("dedupe_key: C# is not C", "Learn C#", "Learn C", dedupe.dedupe_key)
differ("dedupe_key: C++ is not C", "Learn C++", "Learn C", dedupe.dedupe_key)
differ("dedupe_key: C# is not Java", "Learn C#", "Learn Java", dedupe.dedupe_key)
check("dedupe_key: a hash is preserved verbatim",
      dedupe.dedupe_key("Learn C#"), "learn c#")

# The negative that justifies exact matching over fuzzy.
differ("dedupe_key: a one-word title does not collide with a longer title "
       "containing it - the subset artifact fuzzy matching would produce",
       "Compass", "The Compass of Broken Years", dedupe.dedupe_key)
differ("dedupe_key: an unrelated title", "Gray Waters", "The Quiet Harbor",
       dedupe.dedupe_key)
check("dedupe_key: the empty name", dedupe.dedupe_key(""), "")

# --------------------------------------------------------------------
# edition_key - a CROSS-type key: dedupe_key plus a trailing marker strip
# --------------------------------------------------------------------
same("edition_key: a bare trailing marker collides with the base",
     "Salt and Sextant", "Salt and Sextant Audiobook", editions.edition_key)
same("edition_key: a parenthesized marker collides too",
     "The Copper Almanac", "The Copper Almanac (audio)", editions.edition_key)
for marker in ("Audiobook", "audio book", "(audiobook)", "Audio", "ebook",
               "e book", "Unabridged", "Abridged", "Novella"):
    same(f"edition_key: the marker {marker!r} strips",
         "Gray Waters", f"Gray Waters {marker}", editions.edition_key)
same("edition_key: a run of markers strips, which is why the loop exists",
     "Gray Waters", "Gray Waters Unabridged Audiobook", editions.edition_key)
check("edition_key: audiobook does not strip down to book - the alternation "
      "order is load-bearing",
      editions.edition_key("Gray Waters Audiobook"), "gray waters")

# Trailing only. A leading format word is part of the title.
check("edition_key: a leading audio word is kept",
      editions.edition_key("Audio Engineering Handbook"),
      "audio engineering handbook")
check("edition_key: and kept in a game-bundle title too",
      editions.edition_key("Audio Ambience for Deep Space"),
      "audio ambience for deep space")
check("edition_key: a mid-string marker is kept",
      editions.edition_key("The Audio Book of Widgets"),
      "the audio book of widgets")

# A title made only of markers must not strip to nothing, or every such
# title would share the empty key and group together.
for name in ("Audiobook", "Audio", "Unabridged", "audio book"):
    check(f"edition_key: {name!r} keeps its last non-empty form",
          editions.edition_key(name) != "", True)
check("edition_key: two marker-only titles do not collapse onto one key",
      editions.edition_key("Audiobook") == editions.edition_key("Novella"),
      False)

# edition_key must NOT be dedupe_key: stripping markers within a type
# would change how duplicate groups form among audiobooks.
check("edition_key and dedupe_key are different keys, deliberately",
      dedupe.dedupe_key("Salt and Sextant Audiobook")
      == dedupe.dedupe_key("Salt and Sextant"), False)

# --------------------------------------------------------------------
# dedupe.find_groups
# --------------------------------------------------------------------
conn = seeded([("starless1", "The Starless War", "audiobook"),
               ("starless2", "The Starless War", "audiobook"),
               ("unrelated", "Unrelated Book", "ebook")])
check("dedupe.find_groups: an exact within-type pair groups",
      dedupe.find_groups(conn), [[1, 2]])
conn.close()

conn = seeded([("salt_e", "Salt and Sextant", "ebook"),
               ("salt_a", "Salt and Sextant Audiobook", "audiobook")])
check("dedupe.find_groups: a cross-format pair is NOT a duplicate - that is "
      "editions' question, not this one", dedupe.find_groups(conn), [])
conn.close()

conn = seeded([("starless1", "The Starless War", "audiobook"),
               ("starless2", "The Starless War", "ebook")])
check("dedupe.find_groups: the same name in two types does not group",
      dedupe.find_groups(conn), [])
conn.close()

conn = seeded([("starless1", "The Starless War", "audiobook"),
               ("starless2", "The Starless War", "audiobook")],
              dismissed=[("starless1", "starless2")])
check("dedupe.find_groups: a dismissed pair is dropped",
      dedupe.find_groups(conn), [])
conn.close()

# Dismissal is per pair, and a member survives if it is still live against
# ANY other member - the documented rule, and the case a naive filter gets
# wrong.
conn = seeded([("s1", "The Starless War", "audiobook"),
               ("s2", "The Starless War", "audiobook"),
               ("s3", "The Starless War", "audiobook")],
              dismissed=[("s1", "s2")])
check("dedupe.find_groups: a member dismissed against one sibling but not "
      "another stays in the group", dedupe.find_groups(conn), [[1, 2, 3]])
conn.close()

conn = seeded([("m1", "MOONFALL, Vol. 1", "comic"),
               ("m2", "Moonfall Vol. 1", "comic")])
check("dedupe.find_groups: a cosmetic spelling pair groups",
      dedupe.find_groups(conn), [[1, 2]])
conn.close()

conn = seeded([("b1", "Zulu Title", "ebook"), ("b2", "Zulu Title", "ebook"),
               ("a1", "Alpha Title", "ebook"), ("a2", "Alpha Title", "ebook")])
check("dedupe.find_groups: groups are ordered by their lowest member name",
      dedupe.find_groups(conn), [[3, 4], [1, 2]])
conn.close()

check("dedupe.find_groups: an empty catalog yields no groups",
      dedupe.find_groups(seeded([])), [])

# --------------------------------------------------------------------
# editions.find_groups
# --------------------------------------------------------------------
conn = seeded([("salt_e", "Salt and Sextant", "ebook"),
               ("salt_a", "Salt and Sextant Audiobook", "audiobook")])
check("editions.find_groups: an ebook and its audiobook group",
      editions.find_groups(conn), [[1, 2]])
conn.close()

conn = seeded([("nightjar_c", "Nightjar Post", "comic"),
               ("nightjar_e", "Nightjar Post", "ebook")])
check("editions.find_groups: comic is a work type, so a comic-ebook pair "
      "groups", editions.find_groups(conn), [[1, 2]])
conn.close()

conn = seeded([("starless1", "The Starless War", "audiobook"),
               ("starless2", "The Starless War", "audiobook")])
check("editions.find_groups: two of ONE type do not span, so they are not "
      "an edition group", editions.find_groups(conn), [])
conn.close()

# The exclusion that is this feature's whole precision story.
conn = seeded([("cooltower_android", "Cool Tower Defense", "android"),
               ("cooltower_music", "Cool Tower Defense", "music")])
check("editions.find_groups: android and music are excluded, because every "
       "measured false positive was a game plus its own soundtrack",
      editions.find_groups(conn), [])
conn.close()

conn = seeded([("cooltower_android", "Cool Tower Defense", "android"),
               ("cooltower_book", "Cool Tower Defense", "ebook")])
check("editions.find_groups: an excluded type cannot pair with a work type "
      "either", editions.find_groups(conn), [])
conn.close()

# The subset trap, stated as the negative it is.
conn = seeded([("compass_e", "Compass", "ebook"),
               ("compass_a", "The Compass of Broken Years Audiobook",
                "audiobook")])
check("editions.find_groups: a one-word title does not group with a longer "
      "title containing it - the pair fuzzy matching scored 100",
      editions.find_groups(conn), [])
conn.close()

conn = seeded([("salt_e", "Salt and Sextant", "ebook"),
               ("salt_a", "Salt and Sextant Audiobook", "audiobook")],
              dismissed=[("salt_e", "salt_a")])
check("editions.find_groups: a dismissed pair is dropped",
      editions.find_groups(conn), [])
conn.close()

conn = seeded([("copper_e", "The Copper Almanac", "ebook"),
               ("copper_a", "The Copper Almanac (audio)", "audiobook"),
               ("salt_e", "Salt and Sextant", "ebook"),
               ("salt_a", "Salt and Sextant Audiobook", "audiobook")])
check("editions.find_groups: two groups, ordered by lowest member name",
      editions.find_groups(conn), [[3, 4], [1, 2]])
conn.close()


def main():
    for line in FAIL:
        print(f"BROKEN {line}")
    total = len(PASS) + len(FAIL)
    print(f"\neditions-dedupe: {len(PASS)}/{total} held")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
