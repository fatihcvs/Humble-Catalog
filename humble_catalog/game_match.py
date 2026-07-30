"""Deciding whether an offered game title is one the owner already has.

Shared by two callers that use the same two cutoffs and treat the middle
band between them in OPPOSITE ways, on purpose:

  bundle_preview  asks "should I buy this bundle", where the expensive
                  mistake is recommending a second purchase. A `possible`
                  is counted as neither owned nor new.
  keys            asks "did this key ever land", where the expensive
                  mistake is suppressing a key that quietly expires. A
                  `possible` is listed, annotated with what it nearly
                  matched.

Which is why the cutoffs live here rather than in either caller.
"""
from rapidfuzz import fuzz, process

from humble_catalog.titles import clean_game_title, sequel_mismatch

# Game ownership has no shared id to lean on, so these decide it outright
# rather than deciding whether to show a hint. Two thresholds, not one: the
# band between them is where the caller refuses to guess.
#
# Scored with token_sort_ratio, NOT the token_set_ratio the book overlap
# uses. token_set_ratio scores a subset as a perfect 100, so every base
# title would be a certain match for every expansion of it -- "Starfall
# Rally" would read as owning "Starfall Rally Turbo".
#
# Measured during design: a live 12-game bundle scored against an imported
# library of 1420 distinct normalized titles. Genuine same-game pairs both
# scored 100 (one of them only because normalization strips the offered
# title's subtitle punctuation first); the highest-scoring pair that was
# NOT the same game scored 70.6. The whole span 71-99 was empty, so
# GAME_OWNED sits in the middle of a ~30-point gap rather than on a
# boundary, and GAME_POSSIBLE is above every false pair measured -- nothing
# spurious reaches the band. Widen the band, do not narrow it, if a later
# bundle lands something in between.
GAME_OWNED = 92.0
GAME_POSSIBLE = 80.0


def classify_game(offered, owned):
    """('owned'|'possible'|'new', best_match_or_None) for one offered title.

    `owned` is [(normalized_title, display_title)] -- one store's library,
    or several pooled, according to what the caller is asking.

    A sequel is forced to 'new' whatever it scores: "widget quest" and
    "widget quest ii" differ by one token, so every fuzzy scorer rates
    them near-identical, and they are the one near-identical pair that is
    definitely a different product.
    """
    key = clean_game_title(offered)
    if not key or not owned:
        return "new", None
    names = [normalized for normalized, _display in owned]
    hit = process.extractOne(key, names, scorer=fuzz.token_sort_ratio,
                             score_cutoff=GAME_POSSIBLE)
    if hit is None:
        return "new", None
    if sequel_mismatch(key, hit[0]):
        return "new", None
    match = {"offered": offered, "owned_title": owned[hit[2]][1],
             "score": round(hit[1] / 100, 2)}
    return ("owned" if hit[1] >= GAME_OWNED else "possible"), match
