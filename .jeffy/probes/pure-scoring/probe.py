"""Known-answer probes for the pure value-computing helpers.

Hand-computed answers, not liveness checks: each case is one a wrong
implementation returns a different number for. Every documented parameter
is exercised at two or more values that must change the output, per the
sweep rule in PLAN.md. Every title, author and bundle name is drawn from
the canonical invented universe in docs/TEST-DATA.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import classify as classify_mod   # noqa: E402
from humble_catalog import matching, series           # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


def close(name, got, want, tol=1e-9):
    ok = isinstance(got, float) and abs(got - want) <= tol
    results.append((ok, name, got, want))


# --- matching.score: 0.75*title + 0.25*author when both sides have
# authors, title alone otherwise. Closed form, hand-computed. ---
close("score: exact title, no authors -> 1.0",
      matching.score("salt and sextant", [], "Salt and Sextant", []), 1.0)
close("score: exact title and author -> 1.0",
      matching.score("salt and sextant", ["Sam Coder"],
                     "Salt and Sextant", ["Sam Coder"]), 1.0)
# Title matches exactly, author does not: 0.75*1 + 0.25*a. The answer must
# be strictly between the two, which is what proves the weights are
# applied at all rather than one side being ignored.
_mixed = matching.score("salt and sextant", ["Sam Coder"],
                        "Salt and Sextant", ["Alex Dev"])
check("score: author weight actually applied (0.75 <= s < 1.0)",
      0.75 <= _mixed < 1.0, True)
check("score: empty candidate title -> 0.0",
      matching.score("salt and sextant", [], "", []), 0.0)
# The authors parameter must change the result, not merely be accepted.
check("score: authors parameter changes the output",
      matching.score("salt and sextant", ["Sam Coder"],
                     "Salt and Sextant", ["Alex Dev"])
      != matching.score("salt and sextant", [],
                        "Salt and Sextant", ["Alex Dev"]), True)

# --- matching.status_for: boundaries are inclusive at AUTO and REVIEW. ---
check("status_for: at AUTO boundary", matching.status_for(0.85), "matched")
check("status_for: just below AUTO", matching.status_for(0.8499), "low_confidence")
check("status_for: at REVIEW boundary", matching.status_for(0.60), "low_confidence")
check("status_for: just below REVIEW", matching.status_for(0.5999), "unmatched")

# --- series.collapse: runs joined, gaps preserved (docstring's own
# example first). ---
check("collapse: docstring example", series.collapse([1, 2, 3, 5, 6]), "1-3, 5-6")
check("collapse: single volume", series.collapse([4]), "4")
check("collapse: unsorted input is sorted", series.collapse([3, 1, 2]), "1-3")
check("collapse: duplicates collapse", series.collapse([1, 1, 2]), "1-2")
check("collapse: empty", series.collapse([]), "")
check("collapse: every volume isolated", series.collapse([1, 3, 5]), "1, 3, 5")

# --- classify: all four documented parameters must change the answer. ---
check("classify: android platform wins outright",
      classify_mod.classify("Humble Mobile Bundle: Indie Games",
                            {"android"}, set()), "android")
check("classify: audio without an audiobook word is music",
      classify_mod.classify("Humble Game Bundle: Samples",
                            {"audio"}, set()), "music")
check("classify: audiobook named in the BUNDLE name",
      classify_mod.classify("Humble Audiobook Bundle: Epic Tales 2020",
                            {"audio"}, set()), "audiobook")
check("classify: audiobook named in the ITEM name",
      classify_mod.classify("Sample Studios: TTRPG Audio Compendium",
                            {"audio"}, set(),
                            "Salt and Sextant Audiobook"), "audiobook")
check("classify: trailing (audio) label on the item",
      classify_mod.classify("Sample Studios: TTRPG Audio Compendium",
                            {"audio"}, set(),
                            "The Copper Almanac (audio)"), "audiobook")
# The regression guard docs/TEST-DATA.md names: a LEADING "audio" is part
# of a title and must not win the audiobook branch.
check("classify: a bare 'audio' substring must NOT win",
      classify_mod.classify("Sample Studios: TTRPG Audio Compendium",
                            {"audio"}, set(),
                            "Audio Ambience for Deep Space"), "music")
check("classify: comic by bundle hint",
      classify_mod.classify("Humble Comics Bundle: Shadow Hound",
                            set(), set()), "comic")
check("classify: comic by FORMAT alone",
      classify_mod.classify("Humble Book Bundle: Test by Example Press",
                            set(), {"cbz"}), "comic")
check("classify: plain book falls through to ebook",
      classify_mod.classify("Humble Book Bundle: Test by Example Press",
                            set(), {"pdf"}), "ebook")

# --- series.sort_key: re-buys first, then collections, then the rest. ---
_rebuy = {"already_owned": True, "kind": "volume",
          "offered": "Shadow Hound Vol. 2"}
_coll = {"already_owned": False, "kind": "collection",
         "offered": "Shadow Hound Omnibus"}
_cont = {"already_owned": False, "kind": "volume",
         "offered": "Shadow Hound Vol. 5"}
check("sort_key: re-buy sorts before a collection",
      series.sort_key(_rebuy) < series.sort_key(_coll), True)
check("sort_key: collection sorts before a continuation",
      series.sort_key(_coll) < series.sort_key(_cont), True)

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
