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

Both callers prepare their pools with prepare_pool and score against the
result. The sorted form that makes that fast is a scoring key and nothing
else -- see classify_game.
"""
import collections

from rapidfuzz import fuzz, process

from humble_catalog.titles import (
    clean_game_title, sequel_mismatch, sort_tokens)

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

# A match pool with its scoring keys already computed.
#
#   keys     the sorted-token form of each entry's normalized title
#   entries  the (normalized_title, display_title) pairs, UNTOUCHED
#
# The two lists are INDEX-PARALLEL, and that is the whole mechanism:
# process.extractOne returns the index of its best choice, which is what
# carries a result from the sorted scoring key back to the real title.
#
# collections.namedtuple rather than typing.NamedTuple: the package
# carries no type annotations anywhere, and this is not the file to start.
Pool = collections.namedtuple("Pool", "keys entries")

# For a store the owner has imported that holds no games at all. Every
# offered title scores against nothing and comes back `new`.
EMPTY = Pool([], [])


def prepare_pool(owned):
    """[(normalized_title, display_title)] -> a Pool ready to score against.

    Call ONCE per pool, outside the loop over offered titles -- that is
    the entire point. Sorting each pool title's tokens here rather than
    inside the scorer took the key report's matching from 2.20s to 0.27s,
    because token_sort_ratio was re-sorting the same 3,306 pool titles
    for every one of 2,125 keys.
    """
    entries = list(owned)
    return Pool([sort_tokens(normalized) for normalized, _display in entries],
                entries)


def classify_game(offered, pool):
    """('owned'|'possible'|'new', best_match_or_None) for one offered title.

    `pool` is a Pool from prepare_pool -- one store's library, or several
    pooled, according to what the caller is asking. Deliberately NOT a
    plain list: accepting one would mean preparing it on every call,
    silently restoring the cost this design removes, and the caller would
    look correct while being slow. The AttributeError a list raises here
    is the better failure.

    A sequel is forced to 'new' whatever it scores: "widget quest" and
    "widget quest ii" differ by one token, so every fuzzy scorer rates
    them near-identical, and they are the one near-identical pair that is
    definitely a different product.
    """
    key = clean_game_title(offered)
    if not key or not pool.keys:
        return "new", None
    hit = process.extractOne(sort_tokens(key), pool.keys, scorer=fuzz.ratio,
                             score_cutoff=GAME_POSSIBLE)
    if hit is None:
        return "new", None
    # Back to the UNSORTED title before anything else looks at it.
    # sequel_mismatch reads the trailing token, and hit[0] -- the sorted
    # scoring key -- no longer has the numeral there. Do not "simplify"
    # this to hit[0]: the sequel rule would stop firing silently, and
    # owned_title would print a bag of sorted words.
    normalized, display = pool.entries[hit[2]]
    if sequel_mismatch(key, normalized):
        return "new", None
    match = {"offered": offered, "owned_title": display,
             "score": round(hit[1] / 100, 2)}
    return ("owned" if hit[1] >= GAME_OWNED else "possible"), match
