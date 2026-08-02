import os
from datetime import datetime, timedelta, timezone
from humble_catalog.sources.base import (Source, candidate, as_list, as_mapping,
                                         as_number, as_text, first_mapping,
                                         first_text, text_list)

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

    def quota_resets_at(self, now=None):
        # Hardcover documents 60 requests per *minute*, so the base class's
        # one-hour fallback would idle the source about sixty times longer
        # than the limit actually lasts. Two minutes, not one: the window
        # is not stated to be a fixed bucket, so a full minute of margin
        # costs a minute and removes the ambiguity.
        #
        # At delay=2.0 the harvest runs at 30/min, half the limit, so this
        # should never fire from a single run. It would take a concurrent
        # run or a lowered delay - which is exactly when guessing an hour
        # would be most annoying.
        return (now or datetime.now(timezone.utc)) + timedelta(minutes=2)

    def validate(self, data):
        # Truthiness decides whether to raise, exactly as before: the point
        # of this hook is that an error payload is never cached, so an
        # `errors` field of an unexpected shape must still refuse. The
        # accessors are used only to dig out a message for the text.
        errors = as_mapping(data).get("errors")
        if errors:
            message = (first_mapping(errors).get("message")
                       or as_text(errors) or repr(errors))
            raise RuntimeError(f"hardcover API error: {message}")

    def lookup(self, title):
        if not self.token:
            return []
        data = self.get_json(
            "https://api.hardcover.app/v1/graphql", method="POST",
            headers={"Authorization": f"Bearer {self.token}"},
            json_body={"query": QUERY, "variables": {"q": title}})
        results = as_mapping(as_mapping(as_mapping(data).get("data"))
                             .get("search")).get("results")
        out = []
        for hit in as_list(as_mapping(results).get("hits")):
            doc = as_mapping(as_mapping(hit).get("document"))
            featured = as_mapping(doc.get("featured_series"))
            slug = as_text(doc.get("slug"))
            out.append(candidate(
                source=self.name, title=as_text(doc.get("title")) or "",
                authors=text_list(doc.get("author_names")),
                genre=first_text(doc.get("genres")),
                url=f"https://hardcover.app/books/{slug}" if slug else None,
                series=(as_text(as_mapping(featured.get("series")).get("name"))
                        or first_text(doc.get("series_names"))),
                series_number=(as_number(featured.get("position"))
                               or as_number(doc.get("featured_series_position"))),
                rating=as_number(doc.get("rating"))))
        return out
