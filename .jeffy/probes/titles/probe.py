"""Known-answer battery for the titles-clean and titles-series rows.

Covers humble_catalog/titles.py: clean_title, clean_game_title,
sequel_mismatch, sort_tokens, series_key, parse_series and the
volume/range/collection regex family.

These functions compute values that decide what the catalog reports as a
duplicate, a sequel, an owned game and a series, so a liveness probe
proves the least here: every defect in this file returns a plausible
string or a plausible boolean and nothing complains. tests/test_titles.py
already pins 23 documented cases; this battery is aimed at what it does
not reach - the boundaries, the negative sides, and the parameters not
varied.

Desired answers come from the docstrings and from docs/TEST-DATA.md,
which is the spec for the invented universe these examples live in.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog.titles import (                       # noqa: E402
    NO_SERIES, clean_game_title, clean_title, parse_series, sequel_mismatch,
    series_key, sort_tokens)

PASS, FAIL = [], []
GROUPS = {}


def check(label, got, want, group=None):
    if group:
        GROUPS[label] = group
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def check_no_raise(label, fn, want, group=None):
    if group:
        GROUPS[label] = group
    try:
        got = fn()
    except Exception as exc:
        FAIL.append(f"{label}: raised {type(exc).__name__}: {exc}")
        return
    check(label, got, want, group)


# --------------------------------------------------------------------
# clean_title - each stripping rule, and the hint it returns
# --------------------------------------------------------------------
for raw, want_clean, want_num, why in (
        ("Wings of Autumn Dusk (Book 1)", "Wings of Autumn Dusk", 1.0,
         "a parenthesized book number becomes the hint"),
        ("Wings of Autumn Dusk (Vol. 2)", "Wings of Autumn Dusk", 2.0,
         "vol spelling"),
        ("Wings of Autumn Dusk (Part 3)", "Wings of Autumn Dusk", 3.0,
         "part spelling"),
        ("The Quiet Harbor: A Novel", "The Quiet Harbor", None,
         "a novel subtitle is marketing noise"),
        ("Building Widget Services, 2nd Edition", "Building Widget Services",
         None, "an ordinal edition suffix"),
        ("Building Widget Services 2e", "Building Widget Services", None,
         "the compact edition spelling"),
        ("Learning Widget-Driven Design, 1st Edition",
         "Learning Widget-Driven Design", None, "hyphens in the base survive"),
        ("Dune (Audiobook)", "Dune", None, "a trailing parenthetical is noise"),
        ("The Copper Almanac (audio)", "The Copper Almanac", None,
         "the audio label"),
        ("  Gray Waters  ", "Gray Waters", None, "surrounding space"),
        ("Gray Waters", "Gray Waters", None, "a title with no noise at all"),
        ("1632", "1632", None,
         "a numeric title is not mistaken for an edition marker"),
        ("", "", None, "the empty string"),
        ("   ", "", None, "only space")):
    got = clean_title(raw)
    check(f"clean_title: {why}", got, (want_clean, want_num))

# The negative side of each rule: a near-miss must NOT be stripped.
for raw, want, why in (
        ("A Novel Idea", "A Novel Idea", "a novel NOT at the end is kept"),
        ("Edition Wars", "Edition Wars", "a leading edition word is kept"),
        ("Audio Engineering Handbook", "Audio Engineering Handbook",
         "a leading audio word is part of the title"),
        ("Shadow Hound (Vol. 1) Extra", "Shadow Hound (Vol. 1) Extra",
         "a parenthetical mid-title is not trailing")):
    check(f"clean_title negative: {why}", clean_title(raw)[0], want)

check("clean_title: only the LAST trailing parenthetical is stripped",
      clean_title("Gray Waters (Illustrated) (Audiobook)")[0],
      "Gray Waters (Illustrated)")

# --------------------------------------------------------------------
# clean_game_title
# --------------------------------------------------------------------
for raw, want, why in (
        ("Widget Quest", "widget quest", "lowercased"),
        ("Pixel Harbor™", "pixel harbor", "a trademark symbol"),
        ("Widget Quest: Definitive Edition", "widget quest", "an edition suffix"),
        ("Widget Quest - Remastered", "widget quest", "a remaster suffix"),
        ("Widget Quest Remastered: Deluxe Edition", "widget quest",
         "stacked suffixes, which is why the strip loops"),
        ("Widget Quest II", "widget quest ii",
         "a trailing numeral is NEVER stripped - it is the sequel"),
        ("Widget Quest 2", "widget quest 2", "the digit spelling likewise"),
        ("Lantern & Lockpick", "lantern lockpick", "punctuation becomes space"),
        ("  Neon   Drifter  ", "neon drifter", "runs of space collapse"),
        ("", "", "the empty string")):
    check(f"clean_game_title: {why}", clean_game_title(raw), want)
check_no_raise("clean_game_title: None is tolerated",
               lambda: clean_game_title(None), "")
check("clean_game_title: an edition word without 'edition' is kept",
      clean_game_title("Widget Quest Ultimate"), "widget quest ultimate")

# --------------------------------------------------------------------
# sort_tokens
# --------------------------------------------------------------------
check("sort_tokens: tokens are ordered", sort_tokens("widget quest"),
      "quest widget")
check("sort_tokens: empty stays empty", sort_tokens(""), "")
check("sort_tokens: a trailing numeral moves off the end - the documented "
      "reason it must never reach sequel_mismatch",
      sort_tokens("widget quest ii"), "ii quest widget")
check("sort_tokens: it is idempotent",
      sort_tokens(sort_tokens("widget quest ii")), sort_tokens("widget quest ii"))

# --------------------------------------------------------------------
# sequel_mismatch
# --------------------------------------------------------------------
for a, b, want, why in (
        ("widget quest", "widget quest ii", True, "a base against its sequel"),
        ("widget quest ii", "widget quest", True, "the same pair reversed"),
        ("widget quest ii", "widget quest iii", True, "two different sequels"),
        ("widget quest", "widget quest", False, "identical titles"),
        ("widget quest", "starfall rally", False, "unrelated titles"),
        ("widget quest", "widget quest turbo", False,
         "a trailing WORD is not a numeral, so this is not a sequel pair"),
        ("", "", False, "two empty titles"),
        ("widget quest 2", "widget quest 3", True, "digit sequels")):
    check(f"sequel_mismatch: {why}", sequel_mismatch(a, b), want)

# The numeral test is a character class, and these two cases ask what that
# costs. Desired answers come from the docstring: the rule is about "the
# same name with different trailing NUMERALS".
check("sequel_mismatch NUMERAL: 2 and ii are the same number in two "
      "notations, so this is one game, not a sequel pair",
      sequel_mismatch("widget quest 2", "widget quest ii"), False,
      group="NUM")

# This case asserted False when the battery was written, on the strength of
# the docstring alone: "mix" is an ordinary word, not a numeral. Tracing
# game_match.classify_game showed that answer would be WORSE, not better.
# True here sends a genuinely different product to "new", which is right;
# False would hand the pair to the scorer, where 88.9 lands in the possible
# band and the report would hedge about a game the user does not own. The
# mechanism is accidental and the outcome is correct, so this is asserted
# as it stands and no finding was filed for it.
check("sequel_mismatch: a trailing word spelled from roman-numeral letters "
      "is treated as a numeral, which keeps a different product out of the "
      "possible band",
      sequel_mismatch("widget quest", "widget quest mix"), True)

# --------------------------------------------------------------------
# series_key
# --------------------------------------------------------------------
check("series_key: lowercased and punctuation-free",
      series_key("Shadow Hound"), "shadow hound")
check("series_key: three spellings of one initialism share a key",
      len({series_key("S.H.A.D.O.W"), series_key("S.H.A.D.O.W."),
           series_key("S.H.A.D.O.W:")}), 1)
check("series_key: space and hyphen drift merges",
      series_key("Shadow-Hound Quest"), series_key("Shadow Hound Quest"))
check("series_key: a curly and a straight apostrophe merge",
      series_key("Innkeeper’s Ledger"), series_key("Innkeeper's Ledger"))
check("series_key: the negative - more than punctuation differs, so these "
      "must NOT merge",
      series_key("Moonfall") == series_key("Moonfalls"), False)
check("series_key: empty", series_key(""), "")

# --------------------------------------------------------------------
# parse_series
# --------------------------------------------------------------------
s = parse_series("Shadow Hound Vol. 1")
check("parse_series: a bare volume marker", (s.display, s.number, s.kind, s.span),
      ("Shadow Hound", 1, "volume", None))
for spelling in ("Shadow Hound Vol 1", "Shadow Hound Vol. 1",
                 "Shadow Hound Volume 1", "Shadow Hound Book 1",
                 "Shadow Hound, Vol. 1", "Shadow Hound: Vol. 1",
                 "Shadow Hound Vol. #1"):
    got = parse_series(spelling)
    check(f"parse_series: the spelling {spelling!r} parses to volume 1",
          (got.display, got.number, got.kind), ("Shadow Hound", 1, "volume"))

s = parse_series("Shadow Hound Vol. 1-6")
check("parse_series: a range is a collection, never its lower bound",
      (s.display, s.number, s.kind, s.span),
      ("Shadow Hound", None, "collection", (1, 6)))
check("parse_series: an en-dash range",
      parse_series("Shadow Hound Vol. 1–6").span, (1, 6))
check("parse_series: a 'to' range", parse_series("Shadow Hound Vol. 1 to 6").span,
      (1, 6))
check("parse_series: a reversed range is normalized low-to-high",
      parse_series("Shadow Hound Vol. 6-1").span, (1, 6))
check("parse_series: a single-volume range",
      parse_series("Shadow Hound Vol. 3-3").span, (3, 3))

s = parse_series("Shadow Hound Omnibus")
check("parse_series: a collection word has no span and no number",
      (s.display, s.number, s.kind, s.span),
      ("Shadow Hound", None, "collection", None))
for word in ("Compendium", "Anthology", "Box Set", "Boxed Set", "Collection",
             "Complete Collection", "Complete Series"):
    got = parse_series(f"Shadow Hound {word}")
    check(f"parse_series: the collection word {word!r}",
          (got.display, got.kind), ("Shadow Hound", "collection"))

s = parse_series("Shadow Hound Vol. 1: Origins")
check("parse_series: a marker followed by a subtitle still parses, and the "
      "subtitle is discarded so Origins and Endings are one volume",
      (s.display, s.number, s.kind), ("Shadow Hound", 1, "volume"))
check("parse_series: two subtitles of one volume agree",
      parse_series("Shadow Hound Vol. 1: Origins"),
      parse_series("Shadow Hound Vol. 1: Endings"))

check("parse_series: a title with no marker has no series",
      parse_series("The Quiet Harbor"), NO_SERIES)
check("parse_series: a marker that is the whole title names no series",
      parse_series("Vol. 1"), NO_SERIES)
check("parse_series: empty", parse_series(""), NO_SERIES)
check_no_raise("parse_series: None is tolerated", lambda: parse_series(None),
               NO_SERIES)

# number_hint at two values, which must change the answer.
check("parse_series: no hint and no marker yields no series",
      parse_series("Wings of Autumn Dusk"), NO_SERIES)
s = parse_series("Wings of Autumn Dusk", number_hint=1.0)
check("parse_series: a hint supplies the number when no marker is present",
      (s.display, s.number, s.kind), ("Wings of Autumn Dusk", 1, "volume"))
check("parse_series: the hint is ignored when the title states a marker",
      parse_series("Shadow Hound Vol. 5", number_hint=99.0).number, 5)
check("parse_series: a hint cannot invent a series for an empty title",
      parse_series("", number_hint=1.0), NO_SERIES)

# The documented range-before-volume ordering, stated as the property.
check("parse_series: an issue range in parentheses never reaches the "
      "patterns, because clean_title strips it first",
      parse_series(clean_title("Shadow Hound Vol. 22 (#127-132)")[0]).number, 22)

# The key and the display are different fields for a reason.
s = parse_series("S.H.A.D.O.W. Vol. 2")
check("parse_series: display keeps punctuation, key discards it",
      (s.display, s.key), ("S.H.A.D.O.W.", "s h a d o w"))


def group_of(line):
    for label, group in GROUPS.items():
        if line.startswith(label + ":"):
            return group
    return "BROKEN"


def main():
    for line in FAIL:
        print(f"{group_of(line):<6} {line}")
    total = len(PASS) + len(FAIL)
    counts = {}
    for line in FAIL:
        counts[group_of(line)] = counts.get(group_of(line), 0) + 1
    print(f"\ntitles: {len(PASS)}/{total} held")
    if FAIL:
        print("  " + ", ".join(f"{n} {g}" for g, n in sorted(counts.items())))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
