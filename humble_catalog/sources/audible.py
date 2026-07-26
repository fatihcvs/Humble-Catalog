from humble_catalog.sources.base import Source, candidate

class Audible(Source):
    name = "audible"
    delay = 2.0

    def lookup(self, title):
        data = self.get_json(
            "https://api.audible.com/1.0/catalog/products",
            params={"title": title, "num_results": 5,
                    "response_groups": "contributors,rating,series"})
        return [product_candidate(p) for p in data.get("products", [])]

def product_candidate(p):
    series = (p.get("series") or [{}])[0]
    seq = series.get("sequence")
    try:
        seq = float(seq) if seq is not None else None
    except ValueError:
        seq = None
    rating = ((p.get("rating") or {}).get("overall_distribution") or {}) \
        .get("average_rating")
    asin = p.get("asin")
    return candidate(
        source=Audible.name, title=p.get("title", ""),
        authors=[a["name"] for a in p.get("authors") or []] or None,
        narrator=", ".join(n["name"] for n in p.get("narrators") or []) or None,
        series=series.get("title"), series_number=seq, rating=rating,
        url=f"https://www.audible.com/pd/{asin}" if asin else None)
