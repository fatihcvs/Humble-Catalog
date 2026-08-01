"""Which volumes of a series the catalog holds, and what an offered title
means against them.

Live, with no stored state -- mirroring dedupe.find_groups and edition
linking. Nothing to migrate, nothing for `reset` to preserve, and a
rebuilt catalog has its answers back for free.

No fuzzy matching and no threshold appears anywhere in this module, which
is a measured result rather than a simplification. Exact keys with
punctuation stripped merge every genuine spelling drift in the catalog
(172 bases to 169) and merge nothing else; the one near-identical pair
that survives holds identical volume sets, which is what says it is two
series. Same conclusion the edition-linking design reached, and for the
same reason: a fuzzy score here would admit pairs that exact keys prove
are distinct.
"""
from humble_catalog.titles import clean_title, parse_series


def owned_volumes(conn):
    """{series_key: {volume numbers}} across every item in the catalog.

    No type filter. The volume marker was measured on comic (672), ebook
    (12) and audiobook (3) rows and on ZERO android or music rows, so a
    filter would be a branch no test could exercise against real data.
    """
    index = {}
    for row in conn.execute("SELECT name FROM items"):
        found = parse_series(*clean_title(row[0]))
        if found.kind == "volume" and found.number is not None:
            index.setdefault(found.key, set()).add(found.number)
    return index


def collapse(numbers):
    """[1, 2, 3, 5, 6] -> "1-3, 5-6".

    A gap is rendered rather than smoothed over: only one series in the
    catalog has one today, and reporting a run you do not actually hold
    unbroken would be the same class of overclaim this whole feature
    exists to remove.
    """
    runs = []
    for n in sorted(set(numbers)):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in runs)


def describe(offered, index):
    """The series line for one offered title, or None if there is none.

    Three outcomes, and the third is the valuable one. An offered volume
    that matched no machine_name but IS a volume already held is a
    probable re-buy -- the same book under a different Humble id, a
    re-issue, or another edition. That is precisely the mistake the
    preview exists to prevent, and it costs one `in` test against a set
    this function has already built.
    """
    found = parse_series(*clean_title(offered))
    if found.key is None:
        return None
    owned = index.get(found.key)
    if not owned:
        return None
    return {
        "offered": offered,
        "series_name": found.display,
        "kind": found.kind,
        "offered_volume": found.number,
        # Only an explicit range states its own size. An omnibus word says
        # nothing about how many volumes it collects, so no denominator is
        # invented for it.
        "span": list(found.span) if found.span else None,
        "owned": sorted(owned),
        "owned_display": "Vol. " + collapse(owned),
        "already_owned": found.number is not None and found.number in owned,
    }


def sort_key(hit):
    """Re-buys first, then collections, then continuations; ties by title.

    A re-buy is the one line that should stop a purchase, so it must not
    sort below a merely informative one.
    """
    rank = 0 if hit["already_owned"] else 1 if hit["kind"] == "collection" else 2
    return (rank, hit["offered"].lower())
