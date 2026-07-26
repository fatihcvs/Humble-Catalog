import json
from humble_catalog.classify import classify

def parse_order(raw):
    gamekey = raw["gamekey"]
    bundle = {
        "gamekey": gamekey,
        "name": raw["product"]["human_name"],
        "url": f"https://www.humblebundle.com/downloads?key={gamekey}",
        "purchased_at": raw.get("created"),
    }
    items = []
    for sub in raw.get("subproducts", []):
        platforms, formats = set(), set()
        for dl in sub.get("downloads", []):
            platforms.add(dl.get("platform", ""))
            for struct in dl.get("download_struct", []):
                if struct.get("name"):
                    formats.add(struct["name"].lower())
        if not platforms & {"ebook", "audio", "android"}:
            continue
        items.append({
            "machine_name": sub["machine_name"],
            "name": sub["human_name"],
            "publisher": (sub.get("payee") or {}).get("human_name"),
            "cover_url": sub.get("icon"),
            "type": classify(bundle["name"], platforms, formats, sub["human_name"]),
            "formats": sorted(formats),
        })
    externals = [
        {"human_name": tpk.get("human_name"),
         "key_type": tpk.get("key_type"),
         "raw": json.dumps(tpk)}
        for tpk in (raw.get("tpkd_dict") or {}).get("all_tpks", [])
    ]
    return bundle, items, externals
