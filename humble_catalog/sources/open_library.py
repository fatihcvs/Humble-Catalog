from humble_catalog.sources.base import Source, candidate

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
        return [doc_candidate(doc) for doc in data.get("docs", [])]

FIELDS = "title,author_name,ratings_average,subject,key"

def doc_candidate(doc):
    subjects = doc.get("subject") or []
    return candidate(
        source=OpenLibrary.name, title=doc.get("title", ""),
        authors=doc.get("author_name"),
        genre=subjects[0] if subjects else None,
        rating=doc.get("ratings_average"),
        url=f"https://openlibrary.org{doc['key']}" if doc.get("key") else None)
