from humble_catalog.sources.base import Source, candidate

class OpenLibrary(Source):
    name = "open_library"
    delay = 2.0

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
