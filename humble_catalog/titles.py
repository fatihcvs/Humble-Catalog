import re
from typing import NamedTuple

_NUMBERED_PAREN = re.compile(r"\s*\((?:book|vol\.?|volume|part)\s*(\d+)\)\s*$", re.I)
_A_NOVEL = re.compile(r":\s*a\s+novel\s*$", re.I)
_EDITION = re.compile(r"[,:]?\s*\d+(?:st|nd|rd|th)?\s*(?:e|ed\.?|edition)\s*$", re.I)
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")

def clean_title(raw):
    """Strip marketing noise from a HumbleBundle item name.

    Returns (clean_title, series_number_hint_or_None)."""
    t = raw.strip()
    num = None
    m = _NUMBERED_PAREN.search(t)
    if m:
        num = float(m.group(1))
        t = t[:m.start()]
    t = _A_NOVEL.sub("", t)
    t = _EDITION.sub("", t)
    t = _TRAILING_PAREN.sub("", t)
    return t.strip(" ,-"), num

# Game-title normalization. Deliberately NOT clean_title: that one is tuned
# for publisher noise (": A Novel", "2nd Edition") and returns a series-number
# hint. Games carry different noise and no series numbers, and folding the two
# would make each one's rules a hazard for the other's callers.
_TRADEMARK = re.compile(r"[\u2122\u00ae\u00a9]")
_GAME_EDITION = re.compile(
    r"[\s:\u2013\u2014-]*\b(?:game of the year|goty|definitive|enhanced|"
    r"complete|deluxe|ultimate|special|anniversary)\s+edition\b\s*$", re.I)
_REMASTER = re.compile(r"[\s:\u2013\u2014-]*\b(?:remastered|redux)\b\s*$", re.I)
_NON_WORD = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
_NUMERAL = re.compile(r"^(?:\d+|[ivxlcdm]+)$", re.I)

def clean_game_title(raw):
    """A game title reduced to a match key: lowercase, no punctuation, no
    trademark symbols, no edition or remaster suffix.

    Edition suffixes fold into the base title on purpose -- owning *Widget
    Quest* means *Widget Quest: Definitive Edition* is not a new game. They
    are stripped in a loop because they stack ("Remastered: Deluxe Edition").

    Trailing numerals are never stripped: that is the whole difference
    between a game and its sequel. See sequel_mismatch.
    """
    t = _TRADEMARK.sub("", raw or "").strip()
    while True:
        stripped = _REMASTER.sub("", _GAME_EDITION.sub("", t)).strip()
        if stripped == t:
            break
        t = stripped
    t = _NON_WORD.sub(" ", t)
    return _SPACES.sub(" ", t).strip().lower()

def sequel_mismatch(a, b):
    """True when two normalized titles are the same name with different
    trailing numerals -- "widget quest" vs "widget quest ii".

    A fuzzy scorer rates that pair near-identical, because it is: one token
    differs. But it is the one near-identical pair that is definitely NOT
    the same product, so it needs a rule of its own rather than a threshold.
    """
    ta, tb = a.split(), b.split()
    na = ta.pop() if ta and _NUMERAL.match(ta[-1]) else None
    nb = tb.pop() if tb and _NUMERAL.match(tb[-1]) else None
    return ta == tb and na != nb

def sort_tokens(cleaned):
    """A cleaned title's tokens in sorted order -- a scoring key.

    token_sort_ratio(a, b) is ratio(sort_tokens(a), sort_tokens(b)) by
    definition. So sorting a match pool ONCE here and scoring with the
    much cheaper fuzz.ratio computes the same number as scoring the
    unsorted pool with token_sort_ratio -- measured identical on every
    key in the catalog, and 8x faster, because the pool's half of that
    sorting was otherwise redone on all ~6.1M comparisons.

    ONLY ever a scoring key. It must not reach sequel_mismatch, which
    decides on the TRAILING token: sorted, "widget quest ii" becomes
    "ii quest widget", the numeral is no longer last, nothing is popped,
    and the rule that stops a game matching its own sequel silently stops
    firing. See game_match.classify_game, which indexes back to the
    unsorted title before asking.

    Takes an ALREADY-cleaned title. clean_game_title has collapsed runs
    of whitespace, which is what makes split()/join here reproduce
    exactly what token_sort_ratio does internally.
    """
    return " ".join(sorted(cleaned.split()))


class Series(NamedTuple):
    """A title's series identity.

    `key` is punctuation-insensitive and used for matching; `display` is
    the same slice as written and used for output. Two fields rather than
    one because the key must discard punctuation to match -- three
    spellings of one initialism share a key -- and the display must keep
    it to read.
    """
    key: str | None
    display: str | None
    number: int | None
    kind: str | None          # "volume" | "collection" | None
    span: tuple | None        # (lo, hi) for an explicit range only

NO_SERIES = Series(None, None, None, None, None)

_DASH = r"(?:-|\u2013|\u2014|to)"
# A marker may end the title or be followed by ": Subtitle" -- 113 of 679
# volume markers in the catalog are, so anchoring to end-of-string alone
# would drop a sixth of them. The subtitle is discarded, which correctly
# files "Vol. 1: Origins" and "Vol. 1: Endings" as the same volume.
_TAIL = r"\s*(?::.*)?$"
_VOL_WORD = r"\b(?:vol|volume|book)\b"
# Tried FIRST, and that order is the whole point: a bare-volume pattern
# reads "Vol. 1-6" as volume 1, which matches an owned Vol. 1 and reports
# a six-volume collection as already owned. A range names a product.
_VOL_RANGE = re.compile(
    r"[\s,:]*" + _VOL_WORD + r"s?\.?\s*#?(\d+)\s*" + _DASH + r"\s*#?(\d+)" + _TAIL,
    re.I)
_VOL_ONE = re.compile(r"[\s,:]*" + _VOL_WORD + r"\.?\s*#?(\d+)" + _TAIL, re.I)
_COLLECTION = re.compile(
    r"[\s,:]*\b(?:omnibus|compendium|anthology|box(?:ed)?\s+set|"
    r"complete\s+(?:collection|series)|collection)\b" + _TAIL, re.I)

def series_key(text):
    """A series name reduced to a match key: no punctuation, lowercase.

    Reuses the character classes clean_game_title uses -- they are pure
    character classes rather than policy, so sharing them couples nothing.
    Measured 2026-08-01: exact bases fragment a series on punctuation
    alone. One was split three ways by a trailing period on an initialism,
    another by a space where a sibling used a hyphen. Stripping
    punctuation takes 172 bases to 169, merging exactly those and nothing
    else -- the one near-identical pair that survives holds identical
    volume sets, which is the evidence that it is two series rather than
    one drift.
    """
    return _SPACES.sub(" ", _NON_WORD.sub(" ", text)).strip().lower()

def parse_series(cleaned, number_hint=None):
    """The series identity of an ALREADY-CLEANED title.

    Takes clean_title's output. Trailing parentheticals are gone by then,
    so the issue ranges that look like volume ranges -- "Vol. 22
    (#127-132)" -- never reach these patterns. That matters: measured
    across 2,729 items, every range in the catalog is an issue range, 8 of
    11 of them annotating a single volume. Volume 22 COLLECTS issues
    127-132; it is one volume, not six.

    `number_hint` is clean_title's own series number, which understands
    only the parenthesized "(Book 1)" spelling and fires on 3 of 2,729
    items. It stays narrow, and the reason is the cleaned title rather
    than the hint: widening it would strip the bare marker too, and
    `cleaned` is what feeds every source lookup, score and worklist
    entry. Measured 2,308 distinct enrichable titles collapsing to 1,894.
    enrich.series_from_title reads this function's own answer instead.
    """
    t = (cleaned or "").strip()
    for pattern in (_VOL_RANGE, _VOL_ONE, _COLLECTION):
        m = pattern.search(t)
        if m is None:
            continue
        display = t[:m.start()].strip(" ,:-")
        if not display:
            break            # the marker IS the title; no series to name
        if pattern is _VOL_RANGE:
            lo, hi = (int(g) for g in m.groups())
            return Series(series_key(display), display, None, "collection",
                          (lo, hi) if hi >= lo else (hi, lo))
        if pattern is _VOL_ONE:
            return Series(series_key(display), display, int(m.group(1)),
                          "volume", None)
        return Series(series_key(display), display, None, "collection", None)
    if number_hint is not None and t:
        return Series(series_key(t), t, int(number_hint), "volume", None)
    return NO_SERIES
