import sys

from humble_catalog import db

# Each gap is "a column is falsy" (NULL, missing, or empty string),
# counted across ALL items -- consistent with the viewer's `unrated`
# filter, which also ignores enrichment status. flag_key matches the
# viewer's #f-flag values so the CLI and the viewer name the same gaps.
GAPS = (
    ("Unrated", "unrated", "my_rating"),
    ("No cover", "nocover", "cover_path"),
    ("No source URL", "nourl", "source_url"),
)

# Fixed vocabularies, each paired with its display label. Row order comes
# from these tuples and never from the counts, so the panel does not
# reshuffle as the library changes. TYPES matches index.html's #f-type
# options; READ_STATUSES is the lifecycle order the viewer also sorts by;
# ENRICHMENT is the enrichment.status vocabulary.
TYPES = (("ebook", "E-books"), ("audiobook", "Audiobooks"),
         ("comic", "Comics"), ("music", "Music/Soundtracks"),
         ("android", "Android apps"))
READ_STATUSES = (("want_to_read", "Want to read"), ("unread", "Unread"),
                 ("reading", "Reading"), ("read", "Read"), ("dnf", "DNF"))
ENRICHMENT = (("matched", "Matched"), ("low_confidence", "Low confidence"),
              ("unmatched", "Unmatched"), ("pending", "Pending"))


def _tally(items, field, vocab, default=None):
    """Count `field` over `items` against a fixed (value, label) vocab.

    A value outside the vocab is counted nowhere rather than inventing a
    row, so a section need not sum to the total. `default` stands in for a
    missing key, which is how read_status's NOT NULL DEFAULT is honoured
    for a partial payload from an older server.
    """
    counts = {value: 0 for value, _label in vocab}
    for item in items:
        value = item.get(field) or default
        if value in counts:
            counts[value] += 1
    return [(label, counts[value]) for value, label in vocab]


def _by_type(items):
    return _tally(items, "type", TYPES)


def _by_rating(items):
    # 1..5 only: unrated is a gap, and a row in both places would break the
    # one-number-one-place rule the panel exists to restore.
    return [(f"★{n}", sum(1 for i in items if i.get("my_rating") == n))
            for n in range(1, 6)]


def _by_read_status(items):
    return _tally(items, "read_status", READ_STATUSES, default="unread")


def _by_enrichment(items):
    return _tally(items, "status", ENRICHMENT)


def _by_gap(items):
    return [(label, sum(1 for i in items if not i.get(field)))
            for label, _flag, field in GAPS]


def _by_genre(items):
    # The one section ordered by its data: biggest first, ties broken
    # alphabetically so the order is total and stable across runs. Every
    # tag is returned; showing only a top N is the viewer's business.
    counts = {}
    for item in items:
        for tag in item.get("genre") or ():
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


# The report's order. Keys are the viewer's contract: each maps to the
# filter a row of that section applies (see SECTION_FILTERS in app.js).
SECTIONS = (
    ("type", "By type", _by_type),
    ("rating", "Ratings", _by_rating),
    ("status", "Reading status", _by_read_status),
    ("enrichment", "Enrichment", _by_enrichment),
    ("gaps", "Gaps", _by_gap),
    ("genre", "Genres", _by_genre),
)


def report(items):
    """Every section's counts over `items` (a db.fetch_items list).

    Returns (sections, total): sections is [(key, label, rows), ...] in
    SECTIONS order, where rows is [(label, count), ...]; total is
    len(items). Pure -- no connection, no I/O -- so the CLI and the web
    route count over the same per-item view fetch_items feeds /api/items
    and the CSV export, which is what keeps them from drifting.
    """
    return ([(key, label, rows_fn(items)) for key, label, rows_fn in SECTIONS],
            len(items))


def console_safe(text, encoding):
    """Degrade `text` to what a console using `encoding` can actually print.

    The default Windows console is cp1252, which has no ★, and genre tags
    are arbitrary user data that may hold anything. The labels are shared
    with the web panel, where the star is the right character, so the CLI
    degrades them at its own boundary rather than the vocabulary being
    dulled for every surface. ★ becomes * because "?5" reads as a
    mistake; anything else falls back to the codec's replacement.
    """
    try:
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        text = text.replace("★", "*")
        return text.encode(encoding, errors="replace").decode(encoding)


def run(conn):
    sections, total = report(db.fetch_items(conn))
    width = len(str(total))
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    for _key, label, rows in sections:
        print(f"\n{label}")
        for row_label, count in rows:
            print(f"{count:>{width}}  {console_safe(row_label, encoding)}")
    print(f"\n{total:>{width}}  items total")
