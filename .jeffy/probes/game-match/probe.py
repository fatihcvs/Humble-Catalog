"""Known-answer battery for the game-match inventory row.

Covers `game_match.prepare_pool`, `classify_game` and the GAME_OWNED /
GAME_POSSIBLE thresholds.

Cases for the two cutoffs use synthetic letter strings rather than titles, on
purpose: `fuzz.ratio` is 2*M/T, so a pair like "abcdefghij" against
"abcdefghix" is 18/20 = 90.00 by hand. That makes the verdict a DERIVED
answer - the module documents the two cutoffs, so a 90.00 pair must be
`possible` and a 92.31 pair must be `owned` - instead of whatever the
scorer happens to return today. Both sides of both cutoffs are pinned.

The semantic cases use invented titles from docs/TEST-DATA.md.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog.game_match import (GAME_OWNED, GAME_POSSIBLE,  # noqa: E402
                                       classify_game, prepare_pool)
from humble_catalog.titles import clean_game_title  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def pool_of(*titles):
    return prepare_pool([(clean_game_title(t), t) for t in titles])


# ------------------------------------------------------- documented cutoffs

def case_cutoffs_are_what_the_cases_below_assume():
    # Stated as a case rather than trusted: if either cutoff moves, the
    # hand-computed verdicts below stop being derivable and this fails
    # first, naming the reason.
    check("GAME_OWNED is 92.0", GAME_OWNED, 92.0)
    check("GAME_POSSIBLE is 80.0", GAME_POSSIBLE, 80.0)


def case_exact_match_is_owned():
    verdict, match = classify_game("abcdefghij", pool_of("abcdefghij"))
    check("an identical title scores 1.0 and is owned",
          (verdict, match["score"]), ("owned", 1.0))


def case_just_above_the_owned_cutoff():
    # 13 chars vs 13 chars, 12 matching: 24/26 = 92.31, just over 92.
    verdict, match = classify_game("abcdefghijklm", pool_of("abcdefghijklx"))
    check("92.31 is at or above the owned cutoff, so owned",
          (verdict, match["score"]), ("owned", 0.92))


def case_just_below_the_owned_cutoff():
    # 10 vs 10, 9 matching: 18/20 = 90.00, under 92 and over 80.
    verdict, match = classify_game("abcdefghij", pool_of("abcdefghix"))
    check("90.00 is under the owned cutoff, so possible",
          (verdict, match["score"]), ("possible", 0.9))


def case_just_above_the_possible_cutoff():
    # 12 vs 12, 10 matching: 20/24 = 83.33, over 80.
    verdict, match = classify_game("abcdefghijkl", pool_of("abcdefghijxy"))
    check("83.33 is over the possible cutoff, so possible",
          (verdict, match["score"]), ("possible", 0.83))


def case_below_the_possible_cutoff_is_new():
    verdict, match = classify_game("abcdefghij", pool_of("abcdxyzwvu"))
    check("40.00 is under the possible cutoff, so new and unmatched",
          (verdict, match), ("new", None))


def case_the_band_is_neither_owned_nor_new():
    # The property the middle band exists for, asserted as a property:
    # a possible verdict must not be reported as either of the others.
    verdict, _ = classify_game("abcdefghij", pool_of("abcdefghix"))
    check("a band verdict is exactly 'possible'",
          (verdict == "owned", verdict == "new", verdict == "possible"),
          (False, False, True))


# ------------------------------------------------------------ sequel rule

def case_a_sequel_is_forced_new_however_it_scores():
    for offered, owned in [("Widget Quest II", "Widget Quest"),
                           ("Widget Quest 2", "Widget Quest"),
                           ("Widget Quest", "Widget Quest II")]:
        verdict, match = classify_game(offered, pool_of(owned))
        check(f"sequel forced new: {offered!r} vs {owned!r}",
              (verdict, match), ("new", None))


def case_a_digit_and_a_roman_numeral_are_the_same_sequel():
    # The F1 fix: these name one product, so they must NOT read as a
    # sequel pair and must not be forced to new.
    verdict, _ = classify_game("Widget Quest II", pool_of("Widget Quest 2"))
    check("a digit and a roman numeral for one volume are not a sequel pair",
          verdict != "new", True)


def case_an_edition_suffix_is_not_a_sequel():
    verdict, match = classify_game("Pixel Harbor Rally Deluxe Edition",
                                   pool_of("Pixel Harbor Rally"))
    check("an edition suffix still matches the base game",
          (verdict, match["owned_title"]), ("owned", "Pixel Harbor Rally"))


# -------------------------------------------------------------- pool rules

def case_prepare_pool_keeps_keys_and_entries_index_parallel():
    # The whole mechanism: extractOne returns an INDEX into keys, which is
    # used to read entries. If the two ever diverge, every match names the
    # wrong game while still looking like a match.
    titles = ["Widget Quest", "Pixel Harbor Rally", "Cinder Vale Chronicles"]
    pool = pool_of(*titles)
    check("keys and entries have the same length",
          len(pool.keys) == len(pool.entries), True)
    check("entries are the untouched input pairs",
          [display for _n, display in pool.entries], titles)
    for i, title in enumerate(titles):
        verdict, match = classify_game(title, pool)
        check(f"index {i} resolves back to {title!r}",
              (verdict, match["owned_title"]), ("owned", title))


def case_an_empty_pool_answers_new():
    verdict, match = classify_game("Widget Quest", prepare_pool([]))
    check("an empty pool cannot own anything", (verdict, match), ("new", None))


def case_an_empty_offered_title_answers_new():
    for offered in ["", "   ", "!!!"]:
        verdict, match = classify_game(offered, pool_of("Widget Quest"))
        check(f"a title that normalizes to nothing is new: {offered!r}",
              (verdict, match), ("new", None))


def case_a_plain_list_is_refused_rather_than_silently_prepared():
    # Documented contract: accepting a list would restore the per-call
    # preparation cost this design removes, and the caller would look
    # correct while being slow. The AttributeError is the better failure.
    try:
        classify_game("Widget Quest", [("widget quest", "Widget Quest")])
        FAIL.append("a plain list is refused")
        print("  FAIL a plain list is refused: no error raised")
    except AttributeError:
        PASS.append("a plain list is refused")


def case_the_match_names_both_sides_and_rounds_the_score():
    _verdict, match = classify_game("abcdefghij", pool_of("abcdefghix"))
    check("the match names the offered title, the owned title and a score",
          (match["offered"], match["owned_title"], match["score"]),
          ("abcdefghij", "abcdefghix", 0.9))


def case_the_display_title_is_returned_not_the_normalized_key():
    # normalized and display differ here - the pool's stored display keeps
    # the punctuation and casing the scoring key discarded - and the
    # caller prints display.
    pool = prepare_pool([("widget quest", "WIDGET QUEST!")])
    _verdict, match = classify_game("Widget Quest", pool)
    check("the display title comes back, never the scoring key",
          match["owned_title"], "WIDGET QUEST!")


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
    print(f"game-match: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
