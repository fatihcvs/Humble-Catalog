"""Known-answer battery for the sources-books inventory row.

Covers humble_catalog/sources/google_books.py, open_library.py and
hardcover.py: the three metadata parsers the Operating envelope classes
adversarial, because a compromised or merely changed upstream shape
reaches them over the network.

Every case asserts the DESIRED answer, not the observed one. The
shape-drift group therefore fails against the code as filed; those
failures are the reproduction for the backlog item, and they are listed
by name at the end of the run so the count is never mistaken for noise.

Titles and names are invented, from docs/TEST-DATA.md.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# Cleared before the sources are imported. Both classes fall back to the
# environment when no key is passed, so on a host where the owner has a
# real key exported the "unconfigured source" cases would send a request
# and the probe would certify the opposite of what it claims to test.
for _var in ("GOOGLE_BOOKS_API_KEY", "HARDCOVER_API_KEY"):
    os.environ.pop(_var, None)

from humble_catalog import db                                # noqa: E402
from humble_catalog.sources.google_books import (            # noqa: E402
    GoogleBooks, volume_candidate)
from humble_catalog.sources.open_library import (            # noqa: E402
    OpenLibrary, doc_candidate, FIELDS)
from humble_catalog.sources.hardcover import Hardcover       # noqa: E402

PASS, FAIL = [], []
DRIFT = set()


def check(label, got, want, drift=False):
    if drift:
        DRIFT.add(label)
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def check_no_raise(label, fn, want, drift=False):
    """The desired answer for an off-shape field is a value, never a raise."""
    if drift:
        DRIFT.add(label)
    try:
        got = fn()
    except Exception as exc:
        FAIL.append(f"{label}: raised {type(exc).__name__}: {exc}")
        return
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


class Response:
    """Explicit double, not a Mock: a Mock invents every attribute the code
    reaches for, so it hides which parts of the interface are depended on
    and cannot fail when a new one appears."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class Http:
    """Records the request it was given so parameters can be asserted."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def request(self, method, url, params=None, headers=None, json=None,
                timeout=None):
        self.calls.append({"method": method, "url": url, "params": params,
                           "headers": headers, "json": json})
        return Response(self._payload)


def fresh_conn():
    """A new database file per case: a shared one would serve the previous
    case's source_cache row and silently skip the request being asserted."""
    path = Path(tempfile.mkdtemp()) / "probe.db"
    return db.connect(path)


# --------------------------------------------------------------------
# google_books.volume_candidate - known answers
# --------------------------------------------------------------------
happy = {"title": "Gray Waters", "authors": ["Alex Penner"],
         "categories": ["Fantasy"], "averageRating": 4.5,
         "infoLink": "https://books.example.test/v?id=1",
         "canonicalVolumeLink": "https://books.example.test/canonical"}
c = volume_candidate(happy)
check("gb: title", c["title"], "Gray Waters")
check("gb: authors", c["authors"], ["Alex Penner"])
check("gb: genre is the first category", c["genre"], "Fantasy")
check("gb: rating", c["rating"], 4.5)
check("gb: source", c["source"], "google_books")
# url parameter at two values that must change the output: infoLink wins
# when present, canonicalVolumeLink is the documented fallback.
check("gb: url prefers infoLink", c["url"], "https://books.example.test/v?id=1")
check("gb: url falls back to canonicalVolumeLink",
      volume_candidate({k: v for k, v in happy.items() if k != "infoLink"})["url"],
      "https://books.example.test/canonical")
check("gb: url is None with neither link",
      volume_candidate({"title": "Gray Waters"})["url"], None)
check("gb: empty categories yield no genre",
      volume_candidate({"title": "Gray Waters", "categories": []})["genre"], None)
check("gb: missing title becomes the empty string",
      volume_candidate({})["title"], "")
check("gb: extra is a fresh dict per call",
      volume_candidate({}) ["extra"] is not volume_candidate({})["extra"], True)

# --------------------------------------------------------------------
# google_books.lookup - the key parameter at two values
# --------------------------------------------------------------------
conn = fresh_conn()
http = Http({"items": []})
check("gb: no key disables the source",
      GoogleBooks(conn, http=http, key=None).lookup("Gray Waters"), [])
check("gb: no key sends no request", len(http.calls), 0)

conn = fresh_conn()
http = Http({"items": [{"volumeInfo": happy}]})
got = GoogleBooks(conn, http=http, key="probe-key").lookup("Gray Waters")
check("gb: a key sends exactly one request", len(http.calls), 1)
check("gb: the key rides in the query params",
      http.calls[0]["params"]["key"], "probe-key")
check("gb: the title is quoted into an intitle query",
      http.calls[0]["params"]["q"], 'intitle:"Gray Waters"')
check("gb: maxResults is 5", http.calls[0]["params"]["maxResults"], 5)
check("gb: one item yields one candidate", len(got), 1)
check("gb: the candidate is parsed", got[0]["genre"], "Fantasy")

# The credential must not become part of the cache key, or rotating it
# orphans every response already fetched.
conn = fresh_conn()
http = Http({"items": []})
src = GoogleBooks(conn, http=http, key="key-one")
src.lookup("Gray Waters")
src.key = "key-two"
src._last = None
src.lookup("Gray Waters")
check("gb: rotating the key still hits the cache", len(http.calls), 1)

# --------------------------------------------------------------------
# open_library.doc_candidate - known answers
# --------------------------------------------------------------------
doc = {"title": "The Quiet Harbor", "author_name": ["Alex Penner"],
       "ratings_average": 4.2, "subject": ["Fantasy"], "key": "/works/OL1W"}
c = doc_candidate(doc)
check("ol: title", c["title"], "The Quiet Harbor")
check("ol: authors", c["authors"], ["Alex Penner"])
check("ol: genre is the first subject", c["genre"], "Fantasy")
check("ol: rating", c["rating"], 4.2)
check("ol: url is the site root plus the key",
      c["url"], "https://openlibrary.org/works/OL1W")
# key at two values that must change the output.
check("ol: no key yields no url",
      doc_candidate({"title": "The Quiet Harbor"})["url"], None)
check("ol: empty subject yields no genre",
      doc_candidate({"title": "x", "subject": []})["genre"], None)

conn = fresh_conn()
http = Http({"docs": [doc]})
got = OpenLibrary(conn, http=http).lookup("The Quiet Harbor")
check("ol: one doc yields one candidate", len(got), 1)
check("ol: the title is sent as the title param",
      http.calls[0]["params"]["title"], "The Quiet Harbor")
check("ol: limit is 5", http.calls[0]["params"]["limit"], 5)
check("ol: the fields param is the documented set",
      http.calls[0]["params"]["fields"], FIELDS)
check("ol: fields names every parsed key",
      all(f in FIELDS.split(",")
          for f in ("title", "author_name", "ratings_average", "subject", "key")),
      True)

# --------------------------------------------------------------------
# hardcover - the token parameter at two values, and the series rules
# --------------------------------------------------------------------
conn = fresh_conn()
check("hc: a bare token is kept",
      Hardcover(conn, token="probe-token").token, "probe-token")
check("hc: a pasted Bearer prefix is stripped",
      Hardcover(conn, token="Bearer probe-token").token, "probe-token")
check("hc: the prefix match is case-insensitive",
      Hardcover(conn, token="bearer probe-token").token, "probe-token")

conn = fresh_conn()
http = Http({})
check("hc: no token disables the source",
      Hardcover(conn, http=http, token=None).lookup("Gray Waters"), [])
check("hc: no token sends no request", len(http.calls), 0)


def hc_lookup(document):
    conn = fresh_conn()
    http = Http({"data": {"search": {"results": {"hits": [{"document": document}]}}}})
    src = Hardcover(conn, http=http, token="probe-token")
    return src.lookup("Gray Waters"), http


got, http = hc_lookup({
    "title": "Gray Waters", "author_names": ["Alex Penner"],
    "genres": ["Fantasy"], "slug": "gray-waters", "rating": 4.1,
    "featured_series": {"series": {"name": "The Elder Realm"}, "position": 3},
    "series_names": ["Ignored Series"]})
check("hc: title", got[0]["title"], "Gray Waters")
check("hc: authors", got[0]["authors"], ["Alex Penner"])
check("hc: genre is the first genre", got[0]["genre"], "Fantasy")
check("hc: rating", got[0]["rating"], 4.1)
check("hc: url is built from the slug",
      got[0]["url"], "https://hardcover.app/books/gray-waters")
check("hc: featured_series wins over series_names",
      got[0]["series"], "The Elder Realm")
check("hc: series_number comes from position", got[0]["series_number"], 3)
check("hc: the token rides in the Authorization header",
      http.calls[0]["headers"]["Authorization"], "Bearer probe-token")
check("hc: the request is a POST", http.calls[0]["method"], "POST")
check("hc: the title is sent as the query variable",
      http.calls[0]["json"]["variables"]["q"], "Gray Waters")

# The same fields at their other documented values must change the output.
got, _ = hc_lookup({"title": "Gray Waters", "series_names": ["The Elder Realm"],
                    "featured_series_position": 7})
check("hc: series_names is the fallback", got[0]["series"], "The Elder Realm")
check("hc: featured_series_position is the fallback",
      got[0]["series_number"], 7)
got, _ = hc_lookup({"title": "Gray Waters"})
check("hc: no slug yields no url", got[0]["url"], None)
check("hc: no series data yields no series", got[0]["series"], None)
check("hc: no genres yield no genre", got[0]["genre"], None)

# validate() is the only override in the three, and it must raise so a
# GraphQL error payload is never written to the cache.
conn = fresh_conn()
raised = None
try:
    Hardcover(conn, token="t").validate({"errors": [{"message": "probe failure"}]})
except RuntimeError as exc:
    raised = str(exc)
check("hc: a GraphQL error payload raises",
      raised is not None and "probe failure" in raised, True)
check("hc: a clean payload does not raise",
      Hardcover(conn, token="t").validate({"data": {}}), None)

# --------------------------------------------------------------------
# Shape drift. The envelope classes these responses adversarial and names
# "a compromised or merely changed upstream shape" explicitly, so a field
# arriving as another JSON type is in envelope. Desired answer: the field
# is ignored or read whole, never truncated and never raised.
# --------------------------------------------------------------------
check("gb drift: a string category is the genre, not its first letter",
      volume_candidate({"title": "Gray Waters", "categories": "Fantasy"})["genre"],
      "Fantasy", drift=True)
check_no_raise("gb drift: a dict category is ignored",
               lambda: volume_candidate({"title": "Gray Waters",
                                         "categories": {"name": "Fantasy"}})["genre"],
               None, drift=True)
check_no_raise("gb drift: a string authors field becomes a one-name list",
               lambda: volume_candidate({"title": "Gray Waters",
                                         "authors": "Alex Penner"})["authors"],
               ["Alex Penner"], drift=True)
check("ol drift: a string subject is the genre, not its first letter",
      doc_candidate({"title": "x", "subject": "Fantasy"})["genre"],
      "Fantasy", drift=True)
check_no_raise("ol drift: a non-string key yields no url",
               lambda: doc_candidate({"title": "x", "key": 12345})["url"],
               None, drift=True)
check_no_raise("hc drift: a string hits field yields no candidates",
               lambda: Hardcover(fresh_conn(), http=Http(
                   {"data": {"search": {"results": {"hits": "nope"}}}}),
                   token="t").lookup("Gray Waters"),
               [], drift=True)
check_no_raise("hc drift: a string genres field is the genre",
               lambda: hc_lookup({"title": "x", "genres": "Fantasy"})[0][0]["genre"],
               "Fantasy", drift=True)


def is_drift(line):
    return any(line.startswith(label + ":") for label in DRIFT)


def main():
    for line in FAIL:
        print(f"{'DRIFT ' if is_drift(line) else 'BROKEN'} {line}")
    total = len(PASS) + len(FAIL)
    drift_fails = [f for f in FAIL if is_drift(f)]
    print(f"\nsources-books: {len(PASS)}/{total} held")
    if FAIL:
        print(f"  {len(drift_fails)} shape-drift failure(s), "
              f"{len(FAIL) - len(drift_fails)} other")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
