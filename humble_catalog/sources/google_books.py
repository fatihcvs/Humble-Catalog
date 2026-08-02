import os
from humble_catalog import quota
from humble_catalog.sources.base import (Source, candidate, as_list, as_mapping,
                                         as_number, as_text, first_text,
                                         text_list)

class GoogleBooks(Source):
    name = "google_books"
    delay = 2.0
    secret_params = ("key",)
    # The free quota is 1,000 requests a day and the worklist is ~2,300
    # titles, so the budget - not the clock - is what decides how far a run
    # gets. Google serves `503 backendFailed` often enough that retrying
    # made the median title cost two to three requests, spending roughly
    # half the day's allowance re-asking questions that already failed.
    # A skipped title is not lost: it stays uncached, so the next run
    # asks again when the walk reaches its place in the sorted worklist -
    # ahead of every title the budget has not reached yet. Trading a
    # same-run recovery for twice as many titles per day is the right way
    # round when the source needs several days either way.
    retry_server_errors = False

    def __init__(self, conn, http=None, key=None, offline=False):
        super().__init__(conn, http=http, offline=offline)
        # Google's keyless Books quota is 0/day; a (free) API key is required.
        self.key = key if key is not None else os.environ.get("GOOGLE_BOOKS_API_KEY")

    def quota_resets_at(self, now=None):
        # Google's Cloud quotas are daily and roll over at midnight
        # Pacific, so the base class's one-hour guess would send a rerun
        # back into a 429 all day. This is the only place in the codebase
        # that knows that; harvest never names a provider.
        return quota.next_pacific_midnight(now)

    def lookup(self, title):
        if not self.key:
            return []
        data = self.get_json("https://www.googleapis.com/books/v1/volumes",
                             params={"q": f'intitle:"{title}"', "maxResults": 5,
                                     "key": self.key})
        return [volume_candidate(as_mapping(item).get("volumeInfo"))
                for item in as_list(as_mapping(data).get("items"))]

def volume_candidate(vi):
    vi = as_mapping(vi)
    return candidate(
        source=GoogleBooks.name, title=as_text(vi.get("title")) or "",
        authors=text_list(vi.get("authors")),
        genre=first_text(vi.get("categories")),
        rating=as_number(vi.get("averageRating")),
        url=as_text(vi.get("infoLink")) or as_text(vi.get("canonicalVolumeLink")))
