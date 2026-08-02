"""Known-answer battery for the sources-media inventory row.

Covers humble_catalog/sources/oreilly.py, audible.py and comicvine.py:
metadata parsers the Operating envelope classes adversarial, because a
compromised or merely changed upstream shape reaches them over the
network.

Every case asserts the DESIRED answer, not the observed one, so the
groups marked DRIFT and SCALE fail against the code as filed; those
failures are the reproduction for the backlog items and are counted
separately at the end.

Not exercised here, and recorded rather than implied: the accepting side
of ComicVine.credits. Its host allowlist is checked before the
routability test, so a refusal needs no network, but an ACCEPTED host
falls through to publicly_routable(), which resolves the name - and a
probe that quietly depends on live DNS is a probe whose result the
network decides. The refusal paths and the parsing are covered; the
accepting path belongs to a row that can afford a local server.

Titles and names are invented, from docs/TEST-DATA.md.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# Cleared before import: ComicVine falls back to the environment, so on a
# host with a real key exported the "unconfigured source" cases would
# send a request and certify the opposite of what they claim.
os.environ.pop("COMICVINE_API_KEY", None)

from humble_catalog import db                                # noqa: E402
from humble_catalog.sources.oreilly import OReilly           # noqa: E402
from humble_catalog.sources.audible import (                 # noqa: E402
    Audible, product_candidate)
from humble_catalog.sources.comicvine import (               # noqa: E402
    ComicVine, split_credits)

PASS, FAIL = [], []
GROUPS = {}


def note(label, group):
    if group:
        GROUPS[label] = group


def check(label, got, want, group=None):
    note(label, group)
    if got == want:
        PASS.append(label)
    else:
        FAIL.append(f"{label}: got {got!r}, want {want!r}")


def check_no_raise(label, fn, want, group=None):
    note(label, group)
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
    """Explicit double, not a Mock."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class Http:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def request(self, method, url, params=None, headers=None, json=None,
                timeout=None):
        self.calls.append({"method": method, "url": url, "params": params,
                           "headers": headers, "json": json})
        return Response(self._payload)


def fresh_conn():
    return db.connect(Path(tempfile.mkdtemp()) / "probe.db")


def oreilly_one(result):
    conn = fresh_conn()
    http = Http({"results": [result]})
    return OReilly(conn, http=http).lookup("Gray Waters")[0], http


# --------------------------------------------------------------------
# oreilly - known answers
# --------------------------------------------------------------------
c, http = oreilly_one({
    "title": "The Widget Programming Language, 2nd Edition",
    "authors": ["Sam Coder", "Alex Dev"], "isbn": "9780000000001",
    "average_rating": 4667,
    "web_url": "/library/view/widget-language/9780000000001/"})
check("or: title", c["title"], "The Widget Programming Language, 2nd Edition")
check("or: authors", c["authors"], ["Sam Coder", "Alex Dev"])
check("or: source", c["source"], "oreilly")
check("or: isbn lands in extra", c["extra"]["isbn"], "9780000000001")
check("or: a relative web_url is made absolute",
      c["url"], "https://learning.oreilly.com/library/view/widget-language/"
                "9780000000001/")
check("or: the query is sent as the query param",
      http.calls[0]["params"]["query"], "Gray Waters")
check("or: limit is 5", http.calls[0]["params"]["limit"], 5)
check("or: formats is book", http.calls[0]["params"]["formats"], "book")

# web_url at its other documented values, each changing the output.
check("or: an absolute web_url is left alone",
      oreilly_one({"title": "x", "web_url": "https://example.test/book"})[0]["url"],
      "https://example.test/book")
check("or: an empty web_url yields no url",
      oreilly_one({"title": "x", "web_url": ""})[0]["url"], None)
check("or: a missing web_url yields no url",
      oreilly_one({"title": "x"})[0]["url"], None)

# The documented x1000 scale, at both sides of its boundary.
check("or: a scaled rating is divided and rounded",
      oreilly_one({"title": "x", "average_rating": 4667})[0]["rating"], 4.67)
check("or: a rating already in the 0-5 domain is untouched",
      oreilly_one({"title": "x", "average_rating": 4.5})[0]["rating"], 4.5)
check("or: 5 is the top of the untouched domain",
      oreilly_one({"title": "x", "average_rating": 5})[0]["rating"], 5)
check("or: a zero rating is dropped",
      oreilly_one({"title": "x", "average_rating": 0})[0]["rating"], None)
check("or: a missing rating is dropped",
      oreilly_one({"title": "x"})[0]["rating"], None)
check("or: empty authors are dropped",
      oreilly_one({"title": "x", "authors": []})[0]["authors"], None)

# --------------------------------------------------------------------
# audible.product_candidate - known answers
# --------------------------------------------------------------------
p = {"title": "Axebearer", "asin": "B000000001",
     "authors": [{"name": "Alex Penner"}],
     "narrators": [{"name": "Sam Reader"}, {"name": "Pat Voice"}],
     "series": [{"title": "The Elder Realm", "sequence": "3"}],
     "rating": {"overall_distribution": {"average_rating": 4.4}}}
c = product_candidate(p)
check("au: title", c["title"], "Axebearer")
check("au: authors are name-mapped", c["authors"], ["Alex Penner"])
check("au: narrators are comma-joined", c["narrator"], "Sam Reader, Pat Voice")
check("au: series title", c["series"], "The Elder Realm")
check("au: a numeric-string sequence becomes a float",
      c["series_number"], 3.0)
check("au: rating comes from the nested distribution", c["rating"], 4.4)
check("au: url is built from the asin",
      c["url"], "https://www.audible.com/pd/B000000001")

# sequence at values that must change the output, including the negative side.
check("au: a decimal sequence is kept",
      product_candidate({"title": "x",
                         "series": [{"sequence": "2.5"}]})["series_number"], 2.5)
check("au: a non-numeric sequence is dropped",
      product_candidate({"title": "x",
                         "series": [{"sequence": "bonus"}]})["series_number"], None)
check("au: a missing sequence is dropped",
      product_candidate({"title": "x", "series": [{}]})["series_number"], None)
check("au: no asin yields no url", product_candidate({"title": "x"})["url"], None)
check("au: no authors yield None, not an empty list",
      product_candidate({"title": "x"})["authors"], None)
check("au: no narrators yield None, not an empty string",
      product_candidate({"title": "x"})["narrator"], None)
check("au: a missing rating block is dropped",
      product_candidate({"title": "x"})["rating"], None)

conn = fresh_conn()
http = Http({"products": [p]})
got = Audible(conn, http=http).lookup("Axebearer")
check("au: one product yields one candidate", len(got), 1)
check("au: the title is sent as the title param",
      http.calls[0]["params"]["title"], "Axebearer")
check("au: num_results is 5", http.calls[0]["params"]["num_results"], 5)
check("au: the response groups name every parsed block",
      sorted(http.calls[0]["params"]["response_groups"].split(",")),
      ["contributors", "rating", "series"])

# --------------------------------------------------------------------
# comicvine - known answers
# --------------------------------------------------------------------
# The role policy is deliberately narrow: penciler and artist only.
check("cv: a writer is a writer",
      split_credits([{"name": "Bo Writer", "role": "writer"}]),
      (["Bo Writer"], []))
check("cv: a penciler is an illustrator",
      split_credits([{"name": "Pat Pencil", "role": "penciler, inker"}]),
      ([], ["Pat Pencil"]))
check("cv: an artist is an illustrator",
      split_credits([{"name": "Ann Art", "role": "artist, cover"}]),
      ([], ["Ann Art"]))
check("cv: an inker alone is neither",
      split_credits([{"name": "Ink Only", "role": "inker"}]), ([], []))
check("cv: a colorist alone is neither",
      split_credits([{"name": "Col Only", "role": "colorist"}]), ([], []))
check("cv: a cover artist alone is neither - the documented omission",
      split_credits([{"name": "Cov Only", "role": "cover"}]), ([], []))
check("cv: a letterer alone is neither",
      split_credits([{"name": "Let Only", "role": "letterer"}]), ([], []))
check("cv: an editor alone is neither",
      split_credits([{"name": "Ed Only", "role": "editor"}]), ([], []))
check("cv: roles are matched case-insensitively",
      split_credits([{"name": "Bo Writer", "role": "WRITER"}]),
      (["Bo Writer"], []))
check("cv: one person can be both",
      split_credits([{"name": "Bo Writer", "role": "writer, artist"}]),
      (["Bo Writer"], ["Bo Writer"]))
check("cv: no credits yield two empty lists", split_credits([]), ([], []))
check("cv: None credits yield two empty lists", split_credits(None), ([], []))

conn = fresh_conn()
http = Http({"results": [{
    "name": "Shadow Hound", "site_detail_url": "https://comicvine.example.test/v/1/",
    "api_detail_url": "https://comicvine.gamespot.com/api/volume/4050-1/",
    "first_issue": {"api_detail_url":
                    "https://comicvine.gamespot.com/api/issue/4000-1/"}}]})
got = ComicVine(conn, http=http, key="probe-key").lookup("Shadow Hound")
check("cv: one volume yields one candidate", len(got), 1)
check("cv: the volume name is both title and series",
      (got[0]["title"], got[0]["series"]), ("Shadow Hound", "Shadow Hound"))
check("cv: the site url is the candidate url",
      got[0]["url"], "https://comicvine.example.test/v/1/")
check("cv: the volume api url is kept in extra",
      got[0]["extra"]["volume_api_url"],
      "https://comicvine.gamespot.com/api/volume/4050-1/")
check("cv: the first issue api url is kept in extra",
      got[0]["extra"]["first_issue_api_url"],
      "https://comicvine.gamespot.com/api/issue/4000-1/")
check("cv: a volume with no first issue yields None there",
      ComicVine(fresh_conn(), http=Http({"results": [{"name": "Shadow Hound"}]}),
                key="k").lookup("Shadow Hound")[0]["extra"]["first_issue_api_url"],
      None)
check("cv: the key rides in the query params",
      http.calls[0]["params"]["api_key"], "probe-key")
check("cv: resources is scoped to volume",
      http.calls[0]["params"]["resources"], "volume")

conn = fresh_conn()
http = Http({})
check("cv: no key disables lookup",
      ComicVine(conn, http=http, key=None).lookup("Shadow Hound"), [])
check("cv: no key sends no request", len(http.calls), 0)
check("cv: no key means no credits",
      ComicVine(conn, http=http, key=None).credits(
          "https://comicvine.gamespot.com/api/issue/4000-1/"), (None, None))
check("cv: no issue url means no credits",
      ComicVine(conn, http=http, key="k").credits(None), (None, None))
check("cv: credits sent no request on either refusal", len(http.calls), 0)

# credits refuses a foreign destination before any request, because the
# request would carry the API key in its query string. The allowlist is
# checked ahead of the routability test, so this needs no network.
for bad, why in (("https://evil.example.test/api/issue/1/", "a foreign host"),
                 ("file:///etc/passwd", "a non-http scheme"),
                 ("https://comicvine.gamespot.com.evil.test/api/issue/1/",
                  "a suffix-spoofed host")):
    conn = fresh_conn()
    http = Http({})
    raised = None
    try:
        ComicVine(conn, http=http, key="k").credits(bad)
    except ValueError as exc:
        raised = str(exc)
    check(f"cv: credits refuses {why}", raised is not None, True)
    check(f"cv: credits sends nothing to {why}", len(http.calls), 0)

check("cv: the allowlist holds exactly the two api hosts",
      sorted(ComicVine.API_HOSTS),
      ["comicvine.gamespot.com", "www.comicvine.com"])

# --------------------------------------------------------------------
# SCALE. oreilly infers the rating scale from the value's size. Any value
# between 5 and 1000 is divided by 1000 and rounded to two places, so an
# upstream that moves to a 0-10 or 0-100 scale yields near-zero ratings
# for the whole catalog rather than failing. Desired: divide only what is
# unambiguously x1000, and drop what cannot be interpreted, because an
# absent rating is honest and a fabricated one is not.
# --------------------------------------------------------------------
for raw in (7.0, 10, 50, 87, 5.001):
    check(f"or scale: {raw} is uninterpretable and dropped, not scaled",
          oreilly_one({"title": "x", "average_rating": raw})[0]["rating"], None,
          group="SCALE")
check("or scale: 1000 is the bottom of the x1000 domain",
      oreilly_one({"title": "x", "average_rating": 1000})[0]["rating"], 1.0,
      group="SCALE")
check("or scale: 5000 is the top of the x1000 domain",
      oreilly_one({"title": "x", "average_rating": 5000})[0]["rating"], 5.0,
      group="SCALE")

# --------------------------------------------------------------------
# DRIFT. Fields arriving as another JSON type must be ignored or read
# whole, never truncated and never raised.
# --------------------------------------------------------------------
check_no_raise("or drift: a string rating is dropped",
               lambda: oreilly_one({"title": "x",
                                    "average_rating": "4667"})[0]["rating"],
               None, group="DRIFT")
check_no_raise("au drift: an author without a name is skipped",
               lambda: product_candidate({"title": "x",
                                          "authors": [{"id": 7}]})["authors"],
               None, group="DRIFT")
check_no_raise("au drift: a list of author strings is taken as names",
               lambda: product_candidate({"title": "x",
                                          "authors": ["Alex Penner"]})["authors"],
               ["Alex Penner"], group="DRIFT")
check_no_raise("au drift: a list sequence is dropped",
               lambda: product_candidate(
                   {"title": "x", "series": [{"sequence": []}]})["series_number"],
               None, group="DRIFT")
check_no_raise("au drift: a dict series is read as one series",
               lambda: product_candidate(
                   {"title": "x", "series": {"title": "The Elder Realm"}})["series"],
               "The Elder Realm", group="DRIFT")
check_no_raise("au drift: a list of series strings is read as the name",
               lambda: product_candidate(
                   {"title": "x", "series": ["The Elder Realm"]})["series"],
               "The Elder Realm", group="DRIFT")
check_no_raise("cv drift: a person without a name is skipped",
               lambda: split_credits([{"role": "writer"}]), ([], []),
               group="DRIFT")
check_no_raise("cv drift: a list role is ignored",
               lambda: split_credits([{"name": "Bo Writer",
                                       "role": ["writer"]}]), ([], []),
               group="DRIFT")


def group_of(line):
    for label, group in GROUPS.items():
        if line.startswith(label + ":"):
            return group
    return "BROKEN"


def main():
    for line in FAIL:
        print(f"{group_of(line):<6} {line}")
    total = len(PASS) + len(FAIL)
    counts = {}
    for line in FAIL:
        counts[group_of(line)] = counts.get(group_of(line), 0) + 1
    print(f"\nsources-media: {len(PASS)}/{total} held")
    if FAIL:
        print("  " + ", ".join(f"{n} {g}" for g, n in sorted(counts.items())))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
