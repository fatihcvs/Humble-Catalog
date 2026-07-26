import re

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
