"""Cross-format edition detection: the same work owned as an ebook and
an audiobook (or a comic).

Deliberately parallel to `dedupe`, and computed live on every call with
no stored link state -- there is nothing to migrate, nothing to
invalidate, and nothing for `reset` to preserve.

Matching is EXACT after a marker strip, never fuzzy. Measured on the
catalog, `token_set_ratio` at 90 found 9 pairs of which 8 were the
subset artifact (it returns 100 whenever one side's token set is a
subset of the other's, so a one-word title scores perfectly against any
longer title containing that word). Exact matching found every genuine
pair with nothing spurious, so fuzzy is rejected as LESS accurate, not
as too slow. No threshold appears anywhere in this module."""
import re

from humble_catalog.dedupe import dedupe_key

# Types whose items are works that can exist in another format. android
# and music are excluded, and that exclusion is this feature's entire
# precision story: measured on the catalog, every false positive came
# from one of those two -- all 5 android/music groups were a game plus
# its own soundtrack, shipped together rather than the same work twice.
# Including comic was measured separately: 0 further groups across 988
# comic items, 0 false positives.
WORK_TYPES = frozenset({"ebook", "audiobook", "comic"})

# A trailing run of format markers: "Salt and Sextant Audiobook",
# "... (audiobook novella)", "... (audio)". `dedupe_key` has already
# lowercased and turned punctuation into spaces, so the parentheses are
# gone before this pattern ever sees the string.
#
# Trailing only, never mid-string. Every marker observed in the catalog
# is trailing, a trailing-only rule finds all of them, and it protects a
# title whose leading word is load-bearing rather than a format label:
# "Audio Engineering Handbook" keeps its first word.
#
# Order is load-bearing: `audio\s*book` must precede the bare `audio`,
# or "audiobook" strips down to "book".
#
# `novella` is the loosest marker and the only one that is not purely a
# format word. It is here because a measured pair needs it, and the cost
# is known: two genuinely distinct works named "X" and "X: A Novella"
# would group. None exists in the catalog.
_MARKERS = r"(?:un)?abridged|audio\s*book|novella|audio|e\s*book"
_TRAILING = re.compile(rf"(?:^|\s)(?:{_MARKERS})$")

def edition_key(name):
    """Match key for the same work across formats: `dedupe_key` with a
    trailing run of format markers removed.

    NOT shared with `dedupe_key`, which is a WITHIN-type key: stripping
    "audiobook" there would silently change how duplicate groups form
    among audiobooks. (`dedupe` also has a private `_EDITION` regex, but
    that one means *print* edition -- "2nd Edition" -- and is unrelated.)
    """
    key = dedupe_key(name)
    while True:
        stripped = _TRAILING.sub("", key).strip()
        # A title made only of markers strips to nothing; an empty key
        # would group every such title together, so keep the last
        # non-empty one.
        if not stripped or stripped == key:
            return key
        key = stripped
