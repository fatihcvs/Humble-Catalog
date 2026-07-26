"""Duplicate detection for cross-bundle repeats of the same book.

Conservative by design: candidates are items whose normalized names are
IDENTICAL within a type. Anything less certain goes through the manual
pair picker instead (see the v1.7 spec)."""
import re

# "2nd Edition", ", 2e", ": 2nd ed." at the end of a title -> keep the
# bare number so different edition spellings collide.
_EDITION = re.compile(r"[,:]?\s*(\d+)(?:st|nd|rd|th)?\s*(?:e|ed\.?|edition)\s*$",
                      re.IGNORECASE)
# Punctuation -> space, EXCEPT # and + ("Learn C#", "C++" stay distinct).
_PUNCT = re.compile(r"[^\w\s#+]")

def dedupe_key(name):
    """Normalized match key: two items with the same key (and type) are
    duplicate candidates."""
    text = _EDITION.sub(r" \1", name.lower().strip())
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split())

def find_groups(conn):
    """-> groups (lists of 2+ item ids, ascending) sharing (key, type),
    with dismissed pairs removed; groups sorted by lowest member name.
    Computed live on every call — no stored candidate state."""
    by_key = {}
    for r in conn.execute("SELECT id, machine_name, name, type FROM items"):
        by_key.setdefault((dedupe_key(r["name"]), r["type"]), []).append(r)
    dismissed = {(r["a"], r["b"]) for r in
                 conn.execute("SELECT a, b FROM dismissed_pairs")}
    groups = []
    for members in by_key.values():
        if len(members) < 2:
            continue
        # Drop a member only if it is dismissed against EVERY other member.
        kept = [m for m in members if not all(
            tuple(sorted((m["machine_name"], o["machine_name"]))) in dismissed
            for o in members if o is not m)]
        if len(kept) > 1:
            groups.append((min(m["name"].lower() for m in kept),
                           sorted(m["id"] for m in kept)))
    return [ids for _, ids in sorted(groups)]
