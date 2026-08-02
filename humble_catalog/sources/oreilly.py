from humble_catalog.sources.base import (Source, candidate, as_list, as_mapping,
                                         as_number, as_text, text_list)

# The catalog stores ratings on a 0-5 scale; learning.oreilly's search API
# reports the average multiplied by 1000, so 4667 means 4.667.
RATING_MAX = 5
RATING_SCALE = 1000

def _rating(value):
    """The 0-5 rating a search result carries, or None.

    The field has been observed on both scales, so a value already inside
    the 0-5 domain is taken as it is and a value at or above the x1000
    factor is divided by it.

    Anything between the two - too large to be a rating, too small to be a
    scaled one - is not interpretable and is dropped rather than divided.
    That gap is the whole point of the function: dividing it produced a
    near-zero rating for every value an upstream on a 0-10 or 0-100 scale
    would serve, and `enrich.apply_candidate` writes the result straight
    into `external_rating`, so the catalog would have been silently
    rescored instead of failing. An absent rating is honest; a fabricated
    one is shown to the user as fact.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if 0 < value <= RATING_MAX:
        return float(value)
    scaled = value / RATING_SCALE
    if value >= RATING_SCALE and 0 < scaled <= RATING_MAX:
        return round(scaled, 2)
    return None

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
            out.append(candidate(
                source=self.name, title=as_text(r.get("title")) or "",
                authors=text_list(r.get("authors")),
                rating=_rating(as_number(r.get("average_rating"))),
                url=("https://learning.oreilly.com" + web)
                    if web.startswith("/") else (web or None),
                extra={"isbn": r.get("isbn")}))
        return out
