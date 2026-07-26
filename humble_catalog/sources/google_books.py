import os
from humble_catalog.sources.base import Source, candidate

class GoogleBooks(Source):
    name = "google_books"
    delay = 2.0
    secret_params = ("key",)

    def __init__(self, conn, http=None, key=None, offline=False):
        super().__init__(conn, http=http, offline=offline)
        # Google's keyless Books quota is 0/day; a (free) API key is required.
        self.key = key if key is not None else os.environ.get("GOOGLE_BOOKS_API_KEY")

    def lookup(self, title):
        if not self.key:
            return []
        data = self.get_json("https://www.googleapis.com/books/v1/volumes",
                             params={"q": f'intitle:"{title}"', "maxResults": 5,
                                     "key": self.key})
        return [volume_candidate(item.get("volumeInfo", {}))
                for item in data.get("items", [])]

def volume_candidate(vi):
    cats = vi.get("categories") or []
    return candidate(
        source=GoogleBooks.name, title=vi.get("title", ""),
        authors=vi.get("authors"),
        genre=cats[0] if cats else None,
        rating=vi.get("averageRating"),
        url=vi.get("infoLink") or vi.get("canonicalVolumeLink"))
