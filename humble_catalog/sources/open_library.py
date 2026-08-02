from humble_catalog.sources.base import (Source, candidate, as_list, as_mapping,
                                         as_number, as_text, first_text,
                                         text_list)

class OpenLibrary(Source):
    name = "open_library"
    delay = 2.0
    # Open Library documents 1 request/second unidentified (3/s if the
    # User-Agent carries a contact address, which ours does not), so
    # delay=2.0 runs at half the allowance.
    #
    # Deliberately no quota_resets_at override, and deliberately no
    # attempt to treat its throttling as a quota: Open Library answers a
    # rate-limited caller with **403**, not 429, so _is_429 never sees it
    # and the request falls through to the ordinary failure path - logged,
    # title skipped, the walk continuing. That is the right outcome. A 403
    # is ambiguous (bot wall, auth, geo-block, rate limit), and recording
    # one as a spent quota would idle the source for an hour over what may
    # be a permanent block.

    def lookup(self, title):
        data = self.get_json(
            "https://openlibrary.org/search.json",
            params={"title": title, "limit": 5, "fields": FIELDS})
        return [doc_candidate(doc) for doc in as_list(as_mapping(data).get("docs"))]

FIELDS = "title,author_name,ratings_average,subject,key"

def doc_candidate(doc):
    doc = as_mapping(doc)
    # The key is interpolated into a URL, so a non-string one must yield no
    # URL rather than a plausible-looking address built from whatever it was.
    key = as_text(doc.get("key"))
    return candidate(
        source=OpenLibrary.name, title=as_text(doc.get("title")) or "",
        authors=text_list(doc.get("author_name")),
        genre=first_text(doc.get("subject")),
        rating=as_number(doc.get("ratings_average")),
        url=f"https://openlibrary.org{key}" if key else None)
