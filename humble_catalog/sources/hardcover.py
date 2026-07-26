import os
from humble_catalog.sources.base import Source, candidate

QUERY = """
query Search($q: String!) {
  search(query: $q, query_type: "Book", per_page: 5) { results }
}"""

class Hardcover(Source):
    name = "hardcover"
    delay = 2.0

    def __init__(self, conn, http=None, token=None, offline=False):
        super().__init__(conn, http=http, offline=offline)
        if token is None:
            token = os.environ.get("HARDCOVER_API_KEY")
        # Hardcover's settings page shows the token WITH a "Bearer " prefix;
        # accept it pasted either way.
        if token and token.lower().startswith("bearer "):
            token = token[len("bearer "):]
        self.token = token

    def validate(self, data):
        errors = data.get("errors")
        if errors:
            raise RuntimeError(f"hardcover API error: {errors[0].get('message')}")

    def lookup(self, title):
        if not self.token:
            return []
        data = self.get_json(
            "https://api.hardcover.app/v1/graphql", method="POST",
            headers={"Authorization": f"Bearer {self.token}"},
            json_body={"query": QUERY, "variables": {"q": title}})
        results = ((data.get("data") or {}).get("search") or {}).get("results") or {}
        hits = results.get("hits", []) if isinstance(results, dict) else []
        out = []
        for hit in hits:
            doc = hit.get("document", {})
            featured = doc.get("featured_series") or {}
            if not isinstance(featured, dict):
                featured = {}
            series_names = doc.get("series_names") or []
            genres = doc.get("genres") or []
            slug = doc.get("slug")
            out.append(candidate(
                source=self.name, title=doc.get("title", ""),
                authors=doc.get("author_names"),
                genre=genres[0] if genres else None,
                url=f"https://hardcover.app/books/{slug}" if slug else None,
                series=((featured.get("series") or {}).get("name")
                        or (series_names[0] if series_names else None)),
                series_number=(featured.get("position")
                               or doc.get("featured_series_position")),
                rating=doc.get("rating")))
        return out
