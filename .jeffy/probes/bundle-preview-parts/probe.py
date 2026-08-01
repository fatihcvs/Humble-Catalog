"""Known-answer probes for bundle_preview's helper families.

Scope is the helpers, NOT `preview` itself - see the split rows in
PLAN.md. These compute values a purchase decision rests on, so every case
is a hand-computed answer rather than a liveness check.

`fetch_bundle` is exercised on its refusal paths only, which need no
network. It shares url_import's fetch guards, so this row is also where a
regression from the B1 change would show.

Names come from the canonical invented universe in docs/TEST-DATA.md.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from humble_catalog import bundle_preview, db   # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


# --- fetch_bundle host gate: only humblebundle.com and its subdomains. ---
def host_verdict(url):
    try:
        bundle_preview.fetch_bundle(url, http=_never())
        return "fetched"
    except ValueError as exc:
        return "refused" if "not a HumbleBundle URL" in str(exc) else "other"
    except Exception:                              # noqa: BLE001
        # got past the host gate and tried to fetch
        return "fetched"


class _never:
    def request(self, *a, **k):
        raise AssertionError("network reached")


for good in ["https://www.humblebundle.com/books/example",
             "https://humblebundle.com/games/example",
             "https://sub.humblebundle.com/x"]:
    check(f"host gate admits {good[8:40]!r}", host_verdict(good), "fetched")
# The lookalikes. A suffix that merely CONTAINS the domain must not pass.
for bad in ["https://humblebundle.com.evil.example/x",
            "https://nothumblebundle.com/x",
            "https://evil.example/humblebundle.com",
            "https://example.com/books/example"]:
    check(f"host gate refuses {bad[8:42]!r}", host_verdict(bad), "refused")
# And the scheme gate still applies ahead of it.
try:
    bundle_preview.fetch_bundle("javascript:alert(1)", http=_never())
    scheme_verdict = "accepted"
except ValueError as exc:
    scheme_verdict = "scheme" if "scheme" in str(exc) else "other"
check("a non-http scheme is refused before the host gate",
      scheme_verdict, "scheme")

# --- delivery_stores: the inner key of platforms_and_oses["game"]. ---
check("delivery_stores: a single storefront",
      bundle_preview.delivery_stores(
          {"platforms_and_oses": {"game": {"steam": ["windows"]}}}), {"steam"})
check("delivery_stores: two storefronts",
      bundle_preview.delivery_stores(
          {"platforms_and_oses": {"game": {"steam": [], "gog": []}}}),
      {"steam", "gog"})
check("delivery_stores: a book has no game entry -> empty set",
      bundle_preview.delivery_stores(
          {"platforms_and_oses": {"ebook": {"pdf": []}}}), set())
check("delivery_stores: the observed empty-game entry -> empty set",
      bundle_preview.delivery_stores({"platforms_and_oses": {"game": {}}}), set())
check("delivery_stores: no platforms_and_oses at all -> empty set",
      bundle_preview.delivery_stores({}), set())
check("delivery_stores: an explicit null is tolerated",
      bundle_preview.delivery_stores({"platforms_and_oses": None}), set())

# --- _adds: disjoint, cheapest-first, case-insensitively sorted. ---
items = {
    "sas": {"human_name": "Salt and Sextant"},
    "gw": {"human_name": "Gray Waters"},
    "ub": {"human_name": "Unrelated Book"},
    "hh": {"human_name": "avondale ledger"},   # lowercase, for the sort check
}
# price DESCENDING, and the tiers nest as Humble's do
top = {"price": 18}
mid = {"price": 10}
low = {"price": 1}
ordered = [(top, {"sas", "gw", "ub", "hh"}), (mid, {"sas", "gw"}), (low, {"sas"})]
bundle_preview._adds(ordered, items)

check("_adds: the cheapest tier lists its own items", low["adds"],
      ["Salt and Sextant"])
check("_adds: a middle tier lists only what it ADDS", mid["adds"],
      ["Gray Waters"])
check("_adds: the top tier lists only what it adds, sorted case-insensitively",
      top["adds"], ["avondale ledger", "Unrelated Book"])
# The invariant that matters: the lists are disjoint and together account
# for every name in the richest tier, with nothing repeated.
_all = low["adds"] + mid["adds"] + top["adds"]
check("_adds: no title appears in two tiers", len(_all), len(set(_all)))
check("_adds: the tiers together account for the whole top tier",
      len(_all), 4)

# A non-nesting bonus tier must not emit a title twice - the running-set
# design exists for exactly this, and a pairwise difference would fail it.
a = {"price": 20}
b = {"price": 5}
bundle_preview._adds([(a, {"sas", "gw"}), (b, {"gw", "ub"})], items)
_both = a["adds"] + b["adds"]
check("_adds: a non-nesting tier still yields no duplicate",
      len(_both), len(set(_both)))
check("_adds: and still covers every distinct name", sorted(_both),
      ["Gray Waters", "Salt and Sextant", "Unrelated Book"])
# A name with no entry in `items` falls back to the machine_name itself.
c = {"price": 1}
bundle_preview._adds([(c, {"unknown_mn"})], items)
check("_adds: an unknown machine_name falls back to itself", c["adds"],
      ["unknown_mn"])

# --- _owned: items UNION the merge tombstones. ---
with tempfile.TemporaryDirectory() as td:
    conn = db.connect(str(Path(td) / "b.db"))
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('sas','Salt and Sextant','ebook')")
    conn.execute("INSERT INTO items (machine_name, name, type) "
                 "VALUES ('gw','Gray Waters','ebook')")
    conn.commit()
    check("_owned: plain rows", bundle_preview._owned(conn), {"sas", "gw"})
    # A merged-away duplicate still names a book that IS in the library.
    conn.execute("INSERT INTO merges (dropped_machine_name, kept_item_id) "
                 "VALUES ('ub', 1)")
    conn.commit()
    check("_owned: a merged-away machine_name still counts as owned",
          bundle_preview._owned(conn), {"sas", "gw", "ub"})

    # --- _owned_games: deduped on normalized_title. ---
    for title, norm, store, sid in [
            ("Neon Drifter", "neon drifter", "steam", "1"),
            ("Neon Drifter", "neon drifter", "gog", "2"),
            ("Widget Quest", "widget quest", "steam", "3")]:
        conn.execute(
            "INSERT INTO games (store, store_id, title, normalized_title, "
            "imported_at) VALUES (?,?,?,?,'2026-08-01')",
            (store, sid, title, norm))
    conn.commit()
    games = bundle_preview._owned_games(conn)
    check("_owned_games: a game owned on two stores appears once",
          len(games), 2)
    check("_owned_games: normalized titles come back sorted",
          [g[0] for g in games], ["neon drifter", "widget quest"])
    conn.close()

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
