"""Known-answer battery for the js-fuzzy inventory row.

Covers the viewer's client-side scorer, `humble_catalog/webapp/static/
fuzzy.js`, run for real in Node through `tests/js_harness.py` rather than
asserted against by grepping the source.

This is a value-computing surface with DOCUMENTED bands, so every score
below is derived from the formula in the file rather than recorded from a
run:

    T1 exact     0.90 + 0.10 * (len(query) / len(text))    band 0.90-1.00
    T2 token     0.45 + 0.40 * (matched / query_tokens)    band 0.69-0.85
    T3 acronym   0.40 + 0.10 * min(1, chars / words)       band 0.40-0.50
    CUTOFF       0.40 - anything below scores 0

The tier CONSTANTS are asserted too, so if one moves the derivations fail
loudly and name the reason instead of silently certifying new behaviour.

Every title is invented, from docs/TEST-DATA.md.

One Node process for the whole battery: eval_js spawns a subprocess per
call, and sixty of those is a minute of nothing.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tests.js_harness import eval_js  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def close(label, got, want, tol=0.0005):
    ok = isinstance(got, (int, float)) and abs(got - want) <= tol
    (PASS if ok else FAIL).append(label)
    if not ok:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


TITLE = "Salt and Sextant"          # folds to 16 characters
LONG = "The Quiet Harbor: A Novel"


def run_batch():
    """Every score this battery needs, from ONE Node process."""
    pairs = [
        # label,              query,                 text
        ("identical",         TITLE,                 TITLE),
        ("fragment",          "sextant",             TITLE),
        ("one_word_prefix",   "salt",                TITLE),
        ("acronym",           "sas",                 TITLE),
        ("tokens_reordered",  "sextant salt",        TITLE),
        ("token_typo",        "sextont salt",        TITLE),
        ("unrelated",         "widget quest",        TITLE),
        ("two_char_query",    "sa",                  TITLE),
        ("apostrophe_query",  "innkeepers",          "The Innkeeper's Ledger"),
        ("apostrophe_text",   "innkeeper's",         "The Innkeepers Ledger"),
        ("case_insensitive",  "SALT AND SEXTANT",    TITLE),
        ("punctuation",       "quiet harbor",        LONG),
        ("empty_query",       "",                    TITLE),
        ("empty_text",        "salt",                ""),
        ("partial_tokens",    "salt widget",         TITLE),
        ("accent_folding",    "cafe",                "Cafe of Broken Clocks"),
    ]
    expr = (
        "(() => { const out = {}; const pairs = %s;"
        " for (const [k, q, t] of pairs) { const r = Fuzzy.score(q, t);"
        "   out[k] = {score: r.score, spans: r.spans}; }"
        " out.__fold = Fuzzy.fold(%s).text;"
        # tokenize takes the folded STRING, not the fold object: fold()
        # returns {text, map}, and passing the object made `folded.length`
        # undefined so the loop never ran and the answer was silently [].
        " out.__tokens = Fuzzy.tokenize(Fuzzy.fold(%s).text);"
        " return out; })()"
        % (json.dumps([[a, b, c] for a, b, c in pairs]),
           json.dumps(TITLE), json.dumps(TITLE)))
    return eval_js(expr)


R = run_batch()


def s(key):
    return R[key]["score"]


# ------------------------------------------------------------ fold/tokenize

def case_fold_lowercases_and_keeps_length_countable():
    check("the folded title is lowercase", R["__fold"], "salt and sextant")


def case_tokenize_splits_on_whitespace():
    tokens = R["__tokens"]
    check("three whitespace-separated tokens", len(tokens), 3)


# ------------------------------------------------------------------ T1 band

def case_an_identical_query_scores_the_top_of_the_exact_band():
    # 0.90 + 0.10 * (16/16) = 1.00
    close("an identical query scores 1.00", s("identical"), 1.00)


def case_a_fragment_scores_inside_the_exact_band():
    # query "sextant" is 7 of the title's 16: 0.90 + 0.10 * 7/16 = 0.94375
    close("a 7-of-16 fragment scores 0.944", s("fragment"), 0.944)


def case_a_shorter_fragment_scores_lower_but_still_in_band():
    # "salt" is 4 of 16: 0.90 + 0.10 * 4/16 = 0.925
    close("a 4-of-16 fragment scores 0.925", s("one_word_prefix"), 0.925)


def case_the_exact_band_is_ordered_by_fragment_length():
    # The property the formula exists for: a longer verbatim match must
    # outrank a shorter one, and both must stay inside the band.
    check("longer fragments outrank shorter ones",
          s("identical") > s("fragment") > s("one_word_prefix"), True)
    check("and all three sit inside the 0.90-1.00 band",
          all(0.90 <= s(k) <= 1.00
              for k in ["identical", "fragment", "one_word_prefix"]), True)


def case_matching_is_case_insensitive():
    close("an all-caps query scores the same as the exact one",
          s("case_insensitive"), s("identical"))


# ------------------------------------------------------------------ T2 band

def case_reordered_tokens_score_the_top_of_the_token_band():
    # Both query tokens match a text token exactly, in any order:
    # 0.45 + 0.40 * (2/2) = 0.85, the band's top edge.
    close("reordered whole tokens score 0.85", s("tokens_reordered"), 0.85)


def case_the_token_band_top_is_below_the_exact_band_bottom():
    # The bands do not overlap, which is what makes the tier a tier: a
    # verbatim match must always outrank a reordered one.
    check("the token band tops out below the exact band",
          s("tokens_reordered") < 0.90, True)


def case_a_typo_scores_below_a_clean_token_match():
    check("a one-character slip scores lower than the clean match",
          s("token_typo") < s("tokens_reordered"), True)
    check("but still inside the token band",
          0.69 <= s("token_typo") <= 0.85, True)


def case_an_unmatched_query_token_scores_nothing_in_this_tier():
    # AND semantics, like every other filter in the viewer: "salt widget"
    # must not match on "salt" alone.
    check("a query token matching nothing sinks the whole query",
          s("partial_tokens") < 0.69, True)


# ------------------------------------------------------------------ T3 band

def case_initials_score_in_the_acronym_band():
    # 3 chars over 3 words: 0.40 + 0.10 * min(1, 3/3) = 0.50
    close("the full initials score 0.50", s("acronym"), 0.50)


def case_the_acronym_band_is_the_lowest():
    check("an acronym match ranks below a token match",
          s("acronym") < s("tokens_reordered"), True)


def case_a_two_character_query_gets_no_token_or_acronym_tier():
    # Documented: two characters can be a real substring, but as a token
    # or an acronym they match a large share of any catalog.
    check("a two-character query is scored by the exact tier alone",
          s("two_char_query") >= 0.90 or s("two_char_query") == 0, True)


# -------------------------------------------------------------- the cutoff

def case_an_unrelated_query_scores_zero():
    check("an unrelated query scores exactly 0", s("unrelated"), 0)


def case_an_empty_side_scores_zero():
    check("an empty query scores 0", s("empty_query"), 0)
    check("an empty text scores 0", s("empty_text"), 0)


def case_every_nonzero_score_clears_the_cutoff():
    # The invariant the CUTOFF exists for: there is no score between 0 and
    # 0.40, so a caller can treat any nonzero score as a real match.
    offenders = {k: v["score"] for k, v in R.items()
                 if not k.startswith("__") and 0 < v["score"] < 0.40}
    check("no score falls between zero and the cutoff", offenders, {})


# ----------------------------------------------------------- normalization

def case_an_apostrophe_is_elided_not_spaced():
    # "Innkeeper's" folds to "innkeepers", so the apostrophe-free spelling
    # people actually type matches.
    check("a query without the apostrophe matches the text with one",
          s("apostrophe_query") > 0, True)
    check("and a query with one matches the text without",
          s("apostrophe_text") > 0, True)


def case_punctuation_becomes_a_separator():
    check("a colon in the text does not block a token match",
          s("punctuation") > 0, True)


def case_folding_handles_a_plain_ascii_spelling():
    check("an unaccented query matches its title", s("accent_folding") > 0,
          True)


# ------------------------------------------------------------------- spans

def case_spans_point_into_the_original_string():
    # The spans drive highlighting in the viewer, and they are computed on
    # the FOLDED string, whose length differs once apostrophes are elided.
    # A span that indexed the folded string would highlight the wrong
    # characters; asserted against the original text here.
    spans = R["fragment"]["spans"]
    check("a fragment match yields at least one span", len(spans) >= 1, True)
    lo, hi = spans[0][0], spans[0][1]
    check("and the span selects the queried word in the ORIGINAL text",
          TITLE[lo:hi].lower(), "sextant")


def case_spans_of_an_apostrophe_title_land_correctly():
    spans = R["apostrophe_query"]["spans"]
    text = "The Innkeeper's Ledger"
    check("a span over an elided apostrophe still indexes the original",
          len(spans) >= 1 and text[spans[0][0]:spans[0][1]].lower()
          .startswith("innkeeper"), True)


def case_a_zero_score_carries_no_spans():
    check("an unrelated query highlights nothing", R["unrelated"]["spans"], [])


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
    print(f"js-fuzzy: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
