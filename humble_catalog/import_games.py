"""Import the owner's game libraries so bundle previews can count games.

Split at the filesystem/network seam, the same split harvest/enrich and
bundle_preview already make: read_heroic and fetch_steam do the I/O,
store_games is the pure write. Every parsing rule is therefore testable
from a committed fixture with no Heroic install and no Steam key.

Heroic's cache files are not a published contract -- they are read here
as an importer, not a live source, so a format change fails at import
time (loudly, once) rather than silently under-reporting mid-preview.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from humble_catalog.sources.base import _with_retries
from humble_catalog.titles import clean_game_title

STEAM_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"

# Heroic cache filename -> the store name recorded in `games.store`.
# Heroic's own word for Epic is "legendary" (its backend) and for Amazon
# "nile"; the storefront names are what a bundle page talks about, so the
# translation happens here rather than leaking into the matcher.
HEROIC_STORES = {
    "gog_library.json": "gog",
    "legendary_library.json": "epic",
    "nile_library.json": "amazon",
    "zoom-library.json": "zoom",
}


def heroic_root():
    """Heroic's store_cache directory for this platform."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "")) / "heroic"
    else:
        base = Path.home() / ".config" / "heroic"
    return base / "store_cache"


def read_heroic(root=None):
    """{store: [game rows]} from Heroic's caches. Absent stores are absent.

    A missing file, `{}`, or an empty list all mean the store is logged
    out, which is a normal state and not an error. Unparseable JSON is an
    error: Heroic may be mid-write, and treating that as "no games" would
    let store_games wipe good rows.
    """
    root = Path(root) if root is not None else heroic_root()
    out = {}
    for filename, store in HEROIC_STORES.items():
        path = root / filename
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"{filename} is not readable JSON: {exc}") from exc
        # GOG writes "games", the others write "library".
        entries = data.get("games") or data.get("library") or []
        stamps = data.get("__timestamp") or {}
        # One timestamp per file, under whichever container key it used.
        stamp = stamps.get("games") or stamps.get("library")
        rows = [{"store_id": str(e.get("app_name") or ""),
                 "title": e.get("title") or "",
                 "normalized_title": clean_game_title(e.get("title") or ""),
                 "source_timestamp": stamp}
                for e in entries
                if e.get("app_name") and e.get("title")]
        if rows:
            out[store] = rows
    return out


def fetch_steam(key, steamid, http=None):
    """The account's owned Steam games, as import rows.

    include_appinfo=1 is what makes the response carry `name`; without it
    the API returns bare appids and every title would go unmatched.

    Steam's local files cannot answer this question: appmanifest_*.acf
    describes only *installed* games, and a Humble key is typically
    activated and never installed -- exactly the games a bundle is most
    likely to duplicate.

    A private profile answers HTTP 200 with an empty `response` object
    rather than an error. That is indistinguishable from owning nothing,
    so it raises here -- store_games would otherwise clear a good library
    and the next preview would report a whole bundle as new.
    """
    if http is None:
        http = requests.Session()
        http.headers.update({"User-Agent": "HumbleCatalog/1.0"})
    params = {"key": key, "steamid": steamid, "include_appinfo": 1,
              "include_played_free_games": 1, "format": "json"}
    resp = _with_retries(
        lambda: http.request("GET", STEAM_URL, params=params, timeout=30))
    games = (resp.json().get("response") or {}).get("games")
    if not games:
        raise ValueError(
            "Steam returned no games -- the profile's game details are "
            "probably private (Steam > Profile > Privacy Settings > Game "
            "details > Public), or the SteamID is wrong")
    return [{"store_id": str(g["appid"]), "title": g.get("name") or "",
             "normalized_title": clean_game_title(g.get("name") or ""),
             "source_timestamp": None}
            for g in games if g.get("appid") and g.get("name")]


def store_games(conn, store, rows, source):
    """Replace one store's games. Returns the number of rows written.

    Per-store replace, so a game removed upstream disappears rather than
    lingering forever, while every other store is untouched.

    An empty `rows` raises instead of clearing. Steam returns an empty list
    for a private profile, and Heroic writes an empty list for a logged-out
    store; both look exactly like "sold everything", and acting on that
    would delete a good library and then report a whole bundle as new.
    """
    if not rows:
        raise ValueError(f"{store}: no games in this import -- refusing to "
                         f"clear {store} rows (a private profile or a "
                         f"logged-out store reads exactly like this)")
    now = datetime.now(timezone.utc).isoformat()
    with conn:  # one transaction: a failure mid-write rolls the delete back
        conn.execute("DELETE FROM games WHERE store=?", (store,))
        conn.executemany(
            "INSERT OR REPLACE INTO games (store, store_id, title, "
            "normalized_title, imported_at, source_timestamp) "
            "VALUES (?,?,?,?,?,?)",
            [(store, r["store_id"], r["title"], r["normalized_title"], now,
              r.get("source_timestamp")) for r in rows])
        conn.execute(
            "INSERT OR REPLACE INTO game_imports (store, imported_at, count, "
            "source) VALUES (?,?,?,?)", (store, now, len(rows), source))
    return len(rows)


def imported_stores(conn):
    """{store: {imported_at, count, source, source_timestamp}}.

    The preview asks this to tell "never imported" apart from "owns
    nothing here" -- as counts the two are identical, and confusing them
    is the error this feature exists to prevent.
    """
    out = {}
    for row in conn.execute("SELECT * FROM game_imports"):
        stamp = conn.execute(
            "SELECT source_timestamp FROM games WHERE store=? "
            "AND source_timestamp IS NOT NULL LIMIT 1", (row["store"],)).fetchone()
        out[row["store"]] = {
            "imported_at": row["imported_at"], "count": row["count"],
            "source": row["source"],
            "source_timestamp": stamp[0] if stamp else None}
    return out


def run(root=None):
    """Import every configured source. The `import-games` entry point.

    Partial success is the normal case -- a logged-out store, or no Steam
    key -- so each source reports for itself and one skip never aborts the
    others.
    """
    from humble_catalog import db
    conn = db.connect()
    try:
        try:
            heroic = read_heroic(root)
        except ValueError as exc:
            print(f"heroic  FAILED: {exc}")
            print("        (previous rows kept)")
            heroic = {}
        for store, rows in sorted(heroic.items()):
            count = store_games(conn, store, rows, "heroic")
            print(f"{store:<7} {count:>5} games (Heroic cache)")
        if not heroic:
            print("heroic  nothing found -- is Heroic installed and logged in?")
        key = os.environ.get("STEAM_API_KEY")
        steamid = os.environ.get("STEAM_ID")
        if not key or not steamid:
            print("steam   skipped (set STEAM_API_KEY and STEAM_ID)")
        else:
            try:
                rows = fetch_steam(key, steamid)
                count = store_games(conn, "steam", rows, "steam")
                print(f"steam   {count:>5} games (Web API)")
            except (ValueError, requests.RequestException) as exc:
                print(f"steam   FAILED: {exc}")
                print("        (previous rows kept)")
    finally:
        conn.close()
