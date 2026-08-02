from humble_catalog.sources.base import (Source, candidate, as_list, as_mapping,
                                         as_number, as_text, first_mapping,
                                         first_text, text_list)

class Audible(Source):
    name = "audible"
    delay = 2.0

    def lookup(self, title):
        data = self.get_json(
            "https://api.audible.com/1.0/catalog/products",
            params={"title": title, "num_results": 5,
                    "response_groups": "contributors,rating,series"})
        return [product_candidate(p)
                for p in as_list(as_mapping(data).get("products"))]

def product_candidate(p):
    p = as_mapping(p)
    series = first_mapping(p.get("series"))
    # allow_text because Audible documents `sequence` as a string ("3"),
    # unlike the rating fields, which are numbers.
    seq = as_number(series.get("sequence"), allow_text=True)
    rating = as_number(as_mapping(as_mapping(p.get("rating"))
                                  .get("overall_distribution"))
                       .get("average_rating"))
    asin = as_text(p.get("asin"))
    narrators = text_list(p.get("narrators"))
    return candidate(
        source=Audible.name, title=as_text(p.get("title")) or "",
        authors=text_list(p.get("authors")),
        narrator=", ".join(narrators) if narrators else None,
        # A series that arrived as a list of bare names rather than of
        # objects still names the series; falling back to it keeps the
        # value instead of dropping it for a shape difference.
        series=as_text(series.get("title")) or first_text(p.get("series")),
        series_number=seq, rating=rating,
        url=f"https://www.audible.com/pd/{asin}" if asin else None)
