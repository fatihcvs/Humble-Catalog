"""Capture one real HumbleBundle order as an anonymized test fixture.

Redacts the gamekey, signed download URLs, and keys, AND replaces every
human_name/machine_name (bundle, items, publishers) with invented ones,
so the fixture reveals structure only — never which bundles are owned.
Also reports how many cached orders carry external keys (tpkd_dict)."""
import json
import pathlib
from humble_catalog import db
from humble_catalog.parse_order import parse_order

conn = db.connect("catalog.db")

with_tpks = 0
sample = None
for row in conn.execute("SELECT gamekey, json FROM raw_orders"):
    raw = json.loads(row["json"])
    if (raw.get("tpkd_dict") or {}).get("all_tpks"):
        with_tpks += 1
    # any reasonably large book order works — we only need the structure
    if sample is None and len(raw.get("subproducts", [])) >= 5:
        sample = raw
print(f"orders with external keys (all_tpks): {with_tpks}")

counter = 0

def redact(obj):
    global counter
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "gamekey":
                out[k] = "REDACTEDKEY123"
            elif k in ("web", "bittorrent") and isinstance(v, str):
                out[k] = "https://dl.humble.com/redacted?sig=x"
            elif k in ("redeemed_key_val", "keyindex", "auth"):
                out[k] = "REDACTED"
            elif k == "human_name" and isinstance(v, str):
                counter += 1
                out[k] = f"Sample Book {counter}"
            elif k == "machine_name" and isinstance(v, str):
                counter += 1
                out[k] = f"samplebook{counter}_v1"
            elif k in ("url", "icon") and isinstance(v, str):
                out[k] = "https://example.com/x"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj

sample = redact(sample)
if "product" in sample:
    sample["product"]["human_name"] = "Humble Book Bundle: Samples by Example Press"
bundle, items, externals = parse_order(sample)  # sanity: must still parse
print(f"fixture parses: bundle={bundle['name']!r}, {len(items)} items")
out = pathlib.Path("tests/fixtures/order_sample.json")
out.write_text(json.dumps(sample, indent=1))
print("wrote", out)
