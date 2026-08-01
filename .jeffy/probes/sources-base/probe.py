"""Known-answer probes for the shared source plumbing and the order parser.

Both are adversarial-class per the Operating envelope: every metadata
source's responses and every HumbleBundle order pass through here. The
retry policy is exercised by counting attempts and sleeps, not by
observing that it "worked", and `retry_server_errors` is exercised at both
its values because a documented parameter that changes nothing is a
finding. Names are invented, per docs/TEST-DATA.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import requests                                        # noqa: E402
from humble_catalog.parse_order import parse_order     # noqa: E402
from humble_catalog.sources import base                # noqa: E402

results = []


def check(name, got, want):
    results.append((got == want, name, got, want))


# --- redact: a key must never survive into a message that gets printed,
# logged or stored. ---
check("redact: api_key",
      base.redact("GET https://x/api?api_key=s3cret&format=json"),
      "GET https://x/api?api_key=REDACTED&format=json")
check("redact: apikey", base.redact("?apikey=s3cret"), "?apikey=REDACTED")
check("redact: bare key", base.redact("?key=s3cret"), "?key=REDACTED")
check("redact: uppercase, and the param name is kept",
      base.redact("?API_KEY=s3cret"), "?API_KEY=REDACTED")
check("redact: stops at the ampersand, later params survive",
      base.redact("?key=s3cret&q=widget"), "?key=REDACTED&q=widget")
check("redact: two keys in one string",
      base.redact("?key=aaa then ?api_key=bbb"),
      "?key=REDACTED then ?api_key=REDACTED")
check("redact: a string with no key is unchanged",
      base.redact("connection refused"), "connection refused")
check("redact: the secret value itself is gone",
      "s3cret" in base.redact("?api_key=s3cret"), False)

# --- candidate: defaults present, kwargs win, and `extra` is a FRESH dict
# per call (a shared one would leak between candidates). ---
c1 = base.candidate(source="hardcover", title="Salt and Sextant")
check("candidate: source kept", c1["source"], "hardcover")
check("candidate: every default key is present",
      all(k in c1 for k in base._DEFAULTS), True)
check("candidate: defaults are None", c1["authors"], None)
check("candidate: extra defaults to an empty dict", c1["extra"], {})
c2 = base.candidate(source="s", title="t", authors=["Sam Coder"])
check("candidate: a kwarg overrides the default", c2["authors"], ["Sam Coder"])
c1["extra"]["x"] = 1
check("candidate: extra is not shared between candidates",
      base.candidate(source="s", title="t")["extra"], {})

# --- cache_key_params: the secret_params argument must change the result. ---
params = {"q": "widget", "api_key": "s3cret", "format": "json"}
check("cache_key_params: with no secrets declared, everything is kept",
      sorted(base.cache_key_params(params, ())),
      [("api_key", "s3cret"), ("format", "json"), ("q", "widget")])
check("cache_key_params: a declared secret is dropped",
      sorted(base.cache_key_params(params, ("api_key",))),
      [("format", "json"), ("q", "widget")])
check("cache_key_params: None params -> []", base.cache_key_params(None, ()), [])
check("cache_key_params: accepts a pair sequence, not only a dict",
      base.cache_key_params([("q", "w"), ("key", "s")], ("key",)), [("q", "w")])

# --- _with_retries: count attempts and sleeps. ---
sleeps = []
base.time.sleep = lambda s: sleeps.append(s)      # noqa: E305


def run_policy(make_error, retry_server_errors=True):
    """(attempts, sleeps, outcome) for a send() that always fails."""
    sleeps.clear()
    attempts = [0]

    def send():
        attempts[0] += 1
        raise make_error()

    try:
        base._with_retries(send, retry_server_errors)
        return attempts[0], list(sleeps), "returned"
    except Exception as exc:                        # noqa: BLE001
        return attempts[0], list(sleeps), type(exc).__name__


def http_error(status):
    resp = requests.Response()
    resp.status_code = status
    return lambda: requests.HTTPError(response=resp)


n, s, out = run_policy(http_error(500))
check("retries: a 5xx is retried to the attempt limit", n, base.ATTEMPTS)
check("retries: backoff is exponential, 5s then 10s", s,
      [base.BACKOFF_BASE, base.BACKOFF_BASE * 2])
check("retries: the last 5xx failure propagates", out, "HTTPError")

# The documented parameter, at its other value: same error, fewer attempts.
n, s, out = run_policy(http_error(500), retry_server_errors=False)
check("retries: retry_server_errors=False stops a 5xx after one attempt", n, 1)
check("retries: and sleeps not at all", s, [])

n, _, out = run_policy(http_error(404))
check("retries: a 4xx is never retried", n, 1)
n, _, _ = run_policy(http_error(429))
check("retries: a 429 is never retried (a dead quota will not improve)", n, 1)
n, _, _ = run_policy(http_error(403))
check("retries: a 403 bot wall is never retried", n, 1)

n, _, out = run_policy(lambda: requests.ConnectionError("refused"))
check("retries: a connection error is retried", n, base.ATTEMPTS)
check("retries: and propagates at the end", out, "ConnectionError")
n, _, _ = run_policy(lambda: requests.Timeout("slow"))
check("retries: a timeout is retried", n, base.ATTEMPTS)
# Connection errors keep retrying even with 5xx retries disabled: they may
# never have reached the provider's quota system.
n, _, _ = run_policy(lambda: requests.ConnectionError("refused"),
                     retry_server_errors=False)
check("retries: retry_server_errors=False does NOT disable connection retries",
      n, base.ATTEMPTS)

# A send that succeeds is called exactly once.
calls = [0]


def ok_send():
    calls[0] += 1
    resp = requests.Response()
    resp.status_code = 200
    return resp


base._with_retries(ok_send)
check("retries: a success is not retried", calls[0], 1)

# --- parse_order: a synthetic order with every branch in it. ---
order = {
    "gamekey": "abc123",
    "created": "2020-01-01T00:00:00",
    "product": {"human_name": "Humble Book Bundle: Test by Example Press"},
    "subproducts": [
        {"machine_name": "sas", "human_name": "Salt and Sextant",
         "payee": {"human_name": "Example Press"}, "icon": "http://c/1.jpg",
         "downloads": [{"platform": "ebook",
                        "download_struct": [{"name": "PDF"}, {"name": "EPUB"}]}]},
        {"machine_name": "sga", "human_name": "Sample Game OST",
         "downloads": [{"platform": "audio",
                        "download_struct": [{"name": "MP3"}]}]},
        # no recognised platform: must be skipped entirely
        {"machine_name": "bw", "human_name": "Bonus Wallpaper",
         "downloads": [{"platform": "video", "download_struct": []}]},
        # no downloads at all: also skipped
        {"machine_name": "none", "human_name": "Unrelated Book",
         "downloads": []},
    ],
    "tpkd_dict": {"all_tpks": [
        {"human_name": "Cinder Vale", "machine_name": "cindervale_steam",
         "key_type": "steam"}]},
}
bundle, items, externals = parse_order(order)

check("parse_order: gamekey", bundle["gamekey"], "abc123")
check("parse_order: bundle name", bundle["name"],
      "Humble Book Bundle: Test by Example Press")
check("parse_order: the bundle url carries the gamekey",
      bundle["url"].endswith("key=abc123"), True)
check("parse_order: purchase date is carried through",
      bundle["purchased_at"], "2020-01-01T00:00:00")
check("parse_order: only recognised platforms become items", len(items), 2)
check("parse_order: the skipped names are absent",
      {"Bonus Wallpaper", "Unrelated Book"} & {i["name"] for i in items}, set())
check("parse_order: formats are lowercased and sorted",
      items[0]["formats"], ["epub", "pdf"])
check("parse_order: publisher comes from payee", items[0]["publisher"],
      "Example Press")
check("parse_order: a missing payee is None, not a crash",
      items[1]["publisher"], None)
check("parse_order: cover url carried", items[0]["cover_url"], "http://c/1.jpg")
check("parse_order: an ebook in a book bundle classifies as ebook",
      items[0]["type"], "ebook")
check("parse_order: audio in a book bundle is music, not audiobook",
      items[1]["type"], "music")
check("parse_order: externals are extracted", len(externals), 1)
check("parse_order: external machine_name", externals[0]["machine_name"],
      "cindervale_steam")
check("parse_order: external raw is JSON text",
      externals[0]["raw"].startswith("{"), True)

# Absent optional containers must not crash.
minimal = {"gamekey": "k", "product": {"human_name": "Bundle One"}}
b2, i2, e2 = parse_order(minimal)
check("parse_order: an order with no subproducts yields no items", i2, [])
check("parse_order: an order with no tpkd_dict yields no externals", e2, [])
check("parse_order: purchased_at is None when absent", b2["purchased_at"], None)

width = max(len(n) for _, n, _, _ in results)
failed = sum(1 for ok, _, _, _ in results if not ok)
for ok, name, got, want in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  got={got!r} want={want!r}")
print(f"\n{len(results) - failed}/{len(results)} passed")
raise SystemExit(1 if failed else 0)
