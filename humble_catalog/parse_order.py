import json
from humble_catalog.classify import classify
from humble_catalog.shapes import as_list, as_mapping, as_text

class MalformedOrder(ValueError):
    """An order payload missing a field this parser requires.

    Raised at the parse site on purpose, and this module keeps that stance
    rather than tolerating the gap: writing a NULL instead fails a NOT
    NULL constraint two layers later, where nothing names the order that
    caused it. What changed is only the message - the same payloads used
    to raise `KeyError: 'human_name'` or `TypeError: string indices must
    be integers`, neither of which says which order to look at.
    """

def _required(obj, key, what, gamekey="?"):
    """The value at `key`, or a refusal that names the order and the field.

    `obj` is passed through as_mapping first, so a field that arrived as
    the wrong JSON type reads as the absence it effectively is instead of
    raising an opaque TypeError from the subscript.
    """
    value = as_mapping(obj).get(key)
    if value is None:
        raise MalformedOrder(
            f"order {gamekey}: cannot parse {what} - '{key}' is missing "
            f"or is not the expected shape")
    return value

def parse_order(raw):
    raw = as_mapping(raw)
    gamekey = _required(raw, "gamekey", "the order key")
    bundle = {
        "gamekey": gamekey,
        "name": _required(raw.get("product"), "human_name", "the bundle name",
                          gamekey),
        "url": f"https://www.humblebundle.com/downloads?key={gamekey}",
        "purchased_at": raw.get("created"),
    }
    items = []
    for sub in as_list(raw.get("subproducts")):
        sub = as_mapping(sub)
        platforms, formats = set(), set()
        for dl in as_list(sub.get("downloads")):
            platforms.add(as_text(as_mapping(dl).get("platform")) or "")
            for struct in as_list(as_mapping(dl).get("download_struct")):
                name = as_text(as_mapping(struct).get("name"))
                if name:
                    formats.add(name.lower())
        if not platforms & {"ebook", "audio", "android"}:
            continue
        human_name = _required(sub, "human_name", "a subproduct name", gamekey)
        items.append({
            "machine_name": _required(sub, "machine_name",
                                      f"the machine name of '{human_name}'",
                                      gamekey),
            "name": human_name,
            "publisher": as_mapping(sub.get("payee")).get("human_name"),
            "cover_url": sub.get("icon"),
            "type": classify(bundle["name"], platforms, formats, human_name),
            "formats": sorted(formats),
        })
    externals = [
        {"human_name": as_mapping(tpk).get("human_name"),
         # Required, not optional: every tpk in the catalog carries one
         # (2,278 of 2,278, across 13 key types), and the column is NOT
         # NULL. A malformed order should raise where it is parsed, not
         # write a NULL that fails a constraint two layers later.
         "machine_name": _required(tpk, "machine_name",
                                   "an external key's machine name", gamekey),
         "key_type": as_mapping(tpk).get("key_type"),
         "raw": json.dumps(tpk)}
        for tpk in as_list(as_mapping(raw.get("tpkd_dict")).get("all_tpks"))
    ]
    return bundle, items, externals
