"""One-off: capture a real Hardcover search response as a test fixture.
Requires HARDCOVER_API_KEY in the environment (free key from
hardcover.app account settings -> Hardcover API)."""
import json, os, pathlib, requests

QUERY = """
query Search($q: String!) {
  search(query: $q, query_type: "Book", per_page: 5) { results }
}"""
token = os.environ["HARDCOVER_API_KEY"]
if token.lower().startswith("bearer "):
    token = token[len("bearer "):]
resp = requests.post(
    "https://api.hardcover.app/v1/graphql",
    headers={"Authorization": f"Bearer {token}",
             "User-Agent": "HumbleCatalog/1.0"},
    json={"query": QUERY, "variables": {"q": "All Systems Red"}}, timeout=30)
resp.raise_for_status()
if resp.json().get("errors"):
    raise SystemExit(f"Hardcover API error: {resp.json()['errors']}")
resp.raise_for_status()
out = pathlib.Path("tests/fixtures/hardcover_search.json")
out.write_text(json.dumps(resp.json(), indent=2))
print("Wrote", out, "- inspect the hit documents' field names.")
