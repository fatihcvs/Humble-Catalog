"""Connectivity check: one tiny live search per source, reported per line.

Uses an in-memory DB so the source_cache can never fake a success and the
real cache is not polluted. OK = the API answered; SKIP = its key env var
is not set; FAIL = network/auth error (bad keys show up here).

On a terminal a status board is repainted in place while the (slow) live
requests run, then erased and replaced by the per-source detail lines -
so waiting is no longer a blank screen, but the final output is exactly
what it has always been.
"""
import re
from humble_catalog import db
from humble_catalog.progress import LiveDisplay, grid

KEY_ENV = {"hardcover": "HARDCOVER_API_KEY",
           "google_books": "GOOGLE_BOOKS_API_KEY",
           "comicvine": "COMICVINE_API_KEY"}
QUERY = "All Systems Red"

PENDING = "..."

def _board(names, statuses):
    """One cell per source: its name and where it currently stands."""
    width = max(len(n) for n in names)
    return grid([f"{n:<{width}}  {statuses.get(n, PENDING):<4}" for n in names])

def run(sources=None, _http=None, stream=None):
    if sources is None:
        conn = db.connect(":memory:")
        from humble_catalog.sources.audible import Audible
        from humble_catalog.sources.comicvine import ComicVine
        from humble_catalog.sources.google_books import GoogleBooks
        from humble_catalog.sources.hardcover import Hardcover
        from humble_catalog.sources.open_library import OpenLibrary
        from humble_catalog.sources.oreilly import OReilly
        sources = {"hardcover": Hardcover(conn, http=_http),
                   "google_books": GoogleBooks(conn, http=_http),
                   "oreilly": OReilly(conn, http=_http),
                   "open_library": OpenLibrary(conn, http=_http),
                   "audible": Audible(conn, http=_http),
                   "comicvine": ComicVine(conn, http=_http)}
    results = {}
    display = LiveDisplay(stream)
    display.render(_board(sources, {}))
    for name, src in sources.items():
        # a source with an empty key/token would silently return [] --
        # report the missing key instead of a hollow OK
        if not getattr(src, "key", True) or not getattr(src, "token", True):
            results[name] = ("SKIP", f"{KEY_ENV.get(name, 'API key')} not set")
        else:
            try:
                cands = src.lookup(QUERY)
                results[name] = ("OK", f"{len(cands)} results for '{QUERY}'")
            except Exception as exc:
                # error strings can embed the request URL, key included
                detail = re.sub(r"((?:api_?)?key)=[^&\s]+", r"\1=REDACTED",
                                str(exc), flags=re.IGNORECASE)
                results[name] = ("FAIL", detail)
        display.render(_board(sources, {n: s for n, (s, _) in results.items()}))
    display.erase()  # the board was the waiting room; the detail lines are the report
    width = max(len(n) for n in results)
    for name, (status, detail) in results.items():
        display.write(f"{name:<{width}}  {status:<4}  {detail}")
    bad = sum(1 for s, _ in results.values() if s == "FAIL")
    display.write(f"\n{len(results)} sources: "
                  f"{sum(1 for s, _ in results.values() if s == 'OK')} OK, "
                  f"{sum(1 for s, _ in results.values() if s == 'SKIP')} skipped, "
                  f"{bad} failed.")
    return results
