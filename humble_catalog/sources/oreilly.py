from humble_catalog.sources.base import (Source, candidate, as_list, as_mapping,
                                         as_number, as_text, text_list)

class OReilly(Source):
    name = "oreilly"
    delay = 2.0

    def lookup(self, title):
        data = self.get_json(
            "https://learning.oreilly.com/api/v2/search/",
            params={"query": title, "limit": 5, "formats": "book"})
        out = []
        for r in as_list(as_mapping(data).get("results")):
            r = as_mapping(r)
            web = as_text(r.get("web_url")) or ""
            rating = as_number(r.get("average_rating"))
            if rating and rating > 5:  # API reports x1000: 4667 means 4.667
                rating = round(rating / 1000, 2)
            out.append(candidate(
                source=self.name, title=as_text(r.get("title")) or "",
                authors=text_list(r.get("authors")),
                rating=rating or None,
                url=("https://learning.oreilly.com" + web)
                    if web.startswith("/") else (web or None),
                extra={"isbn": r.get("isbn")}))
        return out
