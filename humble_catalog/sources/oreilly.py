from humble_catalog.sources.base import Source, candidate

class OReilly(Source):
    name = "oreilly"
    delay = 2.0

    def lookup(self, title):
        data = self.get_json(
            "https://learning.oreilly.com/api/v2/search/",
            params={"query": title, "limit": 5, "formats": "book"})
        out = []
        for r in data.get("results", []):
            web = r.get("web_url") or ""
            rating = r.get("average_rating")
            if rating and rating > 5:  # API reports x1000: 4667 means 4.667
                rating = round(rating / 1000, 2)
            out.append(candidate(
                source=self.name, title=r.get("title", ""),
                authors=r.get("authors") or None,
                rating=rating or None,
                url=("https://learning.oreilly.com" + web)
                    if web.startswith("/") else (web or None),
                extra={"isbn": r.get("isbn")}))
        return out
