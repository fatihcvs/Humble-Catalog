import os
from humble_catalog import quota
from humble_catalog.sources.base import (Source, candidate, as_list, as_mapping,
                                         as_number, as_text, first_text,
                                         text_list)

class GoogleBooks(Source):
    name = "google_books"
    delay = 2.0
    secret_params = ("key",)
    # A 503 is not asked again in the same run. The reason used to be the
    # budget - 1,000 requests a day against a worklist that took days - and
    # the run tally retired it: the quota has died once, on 2026-07-31,
    # and the worklist is now fully answered, with new titles arriving a
    # purchase at a time. What still holds is timing. Google's
    # `503 backendFailed` comes in windows (76% of first attempts on
    # 2026-09-16, and every one of those titles answered on the next run
    # three days later), so a retry 5-10s on lands in the same window: the
    # one measurement taken with retries on had the median title costing
    # two to three requests. A skipped title is not lost - it stays
    # uncached and the next run asks again, which is the retry that works.
    # One request per visit also keeps harvest_run's rate a per-request
    # rate, comparable with every run since the tally began.
    # If the quota starts dying again the old reason returns on top.
    # See #1, #3 and #4.
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
