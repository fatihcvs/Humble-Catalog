"""One-off: capture a real O'Reilly search response as a test fixture.
The learning.oreilly.com v2 search endpoint is public and keyless."""
import json, pathlib, requests

resp = requests.get(
    "https://learning.oreilly.com/api/v2/search/",
    params={"query": "Python Crash Course", "limit": 5, "formats": "book"},
    headers={"User-Agent": "HumbleCatalog/1.0"}, timeout=30)
resp.raise_for_status()
out = pathlib.Path("tests/fixtures/oreilly_search.json")
out.write_text(json.dumps(resp.json(), indent=2))
print("Wrote", out, "with", len(resp.json().get("results", [])), "results.",
      "Inspect the result field names (title/authors/isbn/web_url).")
