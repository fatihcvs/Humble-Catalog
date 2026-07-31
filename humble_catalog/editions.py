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

def find_groups(conn):
    """-> groups (lists of 2+ item ids, ascending) that share an
    `edition_key` and SPAN more than one type, with dismissed pairs
    removed; groups sorted by lowest member name.

    Computed live on every call -- no stored link state, so a rebuilt
    catalog has its links back for free.

    Spanning types is what separates this from `dedupe.find_groups`:
    two audiobooks of the same name are duplicates, which is dedupe's
    question, not this one."""
    by_key = {}
    for r in conn.execute("SELECT id, machine_name, name, type FROM items"):
        if r["type"] not in WORK_TYPES:
            continue
        by_key.setdefault(edition_key(r["name"]), []).append(r)
    dismissed = {(r["a"], r["b"]) for r in
                 conn.execute("SELECT a, b FROM dismissed_pairs")}
    groups = []
    for members in by_key.values():
        if len(members) < 2:
            continue
        # Same rule as dedupe: drop a member only if it is dismissed
        # against EVERY other member.
        kept = [m for m in members if not all(
            tuple(sorted((m["machine_name"], o["machine_name"]))) in dismissed
            for o in members if o is not m)]
        # A single surviving type is not an edition group. This also
        # subsumes dedupe's `len(kept) > 1` check: one member spans one
        # type.
        if len({m["type"] for m in kept}) < 2:
            continue
        groups.append((min(m["name"].lower() for m in kept),
                       sorted(m["id"] for m in kept)))
    return [ids for _, ids in sorted(groups)]
