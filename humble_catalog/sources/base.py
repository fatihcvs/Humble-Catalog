import json
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import requests
from humble_catalog import quota

class CacheMiss(Exception):
    """Raised by an offline Source when a query is not in source_cache."""

_SECRET_PARAM = re.compile(r"((?:api_?)?key)=[^&\s]+", re.IGNORECASE)

def redact(text):
    """Hide credential query params in a source's error string.

    A `requests` HTTPError message embeds the whole request URL, and for
    a keyed source that URL carries the key. Anything derived from an
    exception - printed, logged, or stored - goes through here first.
    """
    return _SECRET_PARAM.sub(r"\1=REDACTED", text)

# --------------------------------------------------------------------
# Shape-safe accessors.
#
# The Operating envelope classes metadata API responses adversarial, and
# names "a merely changed upstream shape" as the case that reaches these
# parsers. Reading a field with plain indexing therefore has two failure
# modes, and the quiet one is worse: `categories[0]` on a string field
# returns its first CHARACTER, which becomes a one-letter genre in the
# catalog with nothing logged, while a dict field raises out of lookup.
#
# These are the single boundary that rule calls for. Every field a source
# parser takes out of a payload goes through one of them, so the shape
# rules live here rather than being restated at thirty call sites, and a
# new source gets them by construction.
# --------------------------------------------------------------------

def as_text(value):
    """`value` if it is a non-blank string, else None.

    A number is deliberately not text: coercing it would turn an upstream
    type change into a plausible-looking value instead of an absent one.
    """
    return value if isinstance(value, str) and value.strip() else None


def as_mapping(value):
    """`value` if it is a dict, else an empty dict, so `.get` is always safe."""
    return value if isinstance(value, dict) else {}


def as_list(value):
    """`value` if it is a list or tuple, else an empty list.

    A string is not a list here. Iterating one yields characters, which is
    how a changed field shape becomes a sequence of one-letter records.
    """
    return list(value) if isinstance(value, (list, tuple)) else []


def first_mapping(value):
    """The first dict in a list field, or the field itself when it arrived
    unwrapped as a single dict. Empty dict when neither."""
    if isinstance(value, dict):
        return value
    for item in as_list(value):
        if isinstance(item, dict):
            return item
    return {}


def first_text(value):
    """The first string in a list field, or the field itself when it
    arrived unwrapped as a bare string. None when neither.

    The unwrapped case is the one that matters: an upstream serving
    `"Fantasy"` where it used to serve `["Fantasy"]` must yield the whole
    word, never its first letter.
    """
    if isinstance(value, str):
        return as_text(value)
    for item in as_list(value):
        text = as_text(item)
        if text is not None:
            return text
    return None


def text_list(value, key="name"):
    """A list of names from a contributor field, or None when there are none.

    Accepts a list of strings, a list of dicts carrying `key`, or a single
    bare string; entries of any other shape, and dicts missing `key`, are
    skipped rather than raising. Returns None rather than [] so a caller
    can pass the result straight to `candidate`, whose absent value is None.
    """
    if isinstance(value, str):
        value = [value]
    out = []
    for item in as_list(value):
        text = as_text(item) if isinstance(item, str) \
            else as_text(as_mapping(item).get(key))
        if text is not None:
            out.append(text)
    return out or None


def as_number(value, allow_text=False):
    """`value` as a float, or None when it is not a number.

    `bool` is excluded because it is a subclass of `int` in Python, so a
    JSON `true` would otherwise arrive as 1.0.

    `allow_text=True` also accepts a numeric string, for the fields an
    upstream documents as strings - Audible's series `sequence` is one.
    It is off by default so that a string arriving in a field documented
    as a number reads as the type change it is, rather than being quietly
    coerced into a value.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if allow_text and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


_DEFAULTS = {"authors": None, "genre": None, "series": None, "series_number": None,
             "rating": None, "narrator": None, "illustrator": None, "url": None}

def candidate(source, title, **kw):
    c = {"source": source, "title": title, **_DEFAULTS, "extra": {}}
    c.update(kw)
    return c

def cache_key_params(params, secret_params):
    """The params that identify a request, minus the ones that authorize it.

    Shared with the db migration that rekeys rows written before secrets
    were excluded, so the old rows land on exactly the key a lookup now
    builds rather than something merely similar.
    """
    pairs = params or {}
    pairs = pairs.items() if hasattr(pairs, "items") else pairs
    return [(k, v) for k, v in pairs if k not in secret_params]

ATTEMPTS = 3
BACKOFF_BASE = 5

def _with_retries(send, retry_server_errors=True):
    """Call send() under the shared retry policy and return its response.

    Retries connection errors, timeouts, and 5xx with exponential backoff
    (5s, then 10s). Every other 4xx raises immediately: a 403 bot wall and
    a 429 dead quota will not improve on retry, and waiting only delays
    the caller's fallback.

    `retry_server_errors=False` drops 5xx out of that set, for a source
    whose quota is the binding constraint: a 5xx came *from* the provider,
    so it was served and almost certainly counted, and asking three times
    spends three of the day's budget to answer one question. Connection
    errors and timeouts keep retrying either way - those may never have
    reached the provider's quota system, so the same trade does not apply.

    At three attempts this is numerically identical to the linear schedule
    it replaces; the exponential form states the intended policy so that
    raising ATTEMPTS later behaves as the name promises.
    """
    for attempt in range(ATTEMPTS):
        try:
            resp = send()
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout):
            if attempt == ATTEMPTS - 1:
                raise
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", 0)
            if attempt == ATTEMPTS - 1 or status < 500 or not retry_server_errors:
                raise
        time.sleep(BACKOFF_BASE * 2 ** attempt)

class Source:
    name = "base"
    delay = 2.0
    # Whether a 5xx is worth asking again. True everywhere except where a
    # provider's daily quota is the binding constraint - see google_books.
    retry_server_errors = True
    # Query params that authenticate the request rather than describe it.
    # They are sent, but kept out of the cache key: keying on a credential
    # makes rotating it orphan every response already fetched, so the next
    # harvest starts the source over from nothing. It also keeps the
    # credential itself out of the database.
    secret_params = ()

    def __init__(self, conn, http=None, offline=False):
        self.conn = conn
        self._last = None
        self.offline = offline
        if http is None:
            http = requests.Session()
            http.headers.update({"User-Agent": "HumbleCatalog/1.0"})
        self.http = http

    def get_json(self, url, params=None, headers=None, method="GET", json_body=None):
        key = url + "?" + urlencode(sorted(cache_key_params(params, self.secret_params)))
        if json_body is not None:
            key += "|" + json.dumps(json_body, sort_keys=True)
        row = self.conn.execute(
            "SELECT json FROM source_cache WHERE source=? AND query=?",
            (self.name, key)).fetchone()
        if row is not None:
            return json.loads(row["json"])
        if self.offline:
            raise CacheMiss(key)
        def _send():
            if self._last is not None:
                wait = self._last + self.delay - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
            try:
                return self.http.request(method, url, params=params,
                                         headers=headers, json=json_body,
                                         timeout=30)
            finally:
                # Throttle from the attempt itself, successful or not.
                self._last = time.monotonic()

        resp = _with_retries(_send, self.retry_server_errors)
        data = resp.json()
        self.validate(data)  # bad payloads must raise so they are never cached
        self.conn.execute(
            "INSERT OR REPLACE INTO source_cache (source, query, fetched_at, json) "
            "VALUES (?,?,?,?)",
            (self.name, key, datetime.now(timezone.utc).isoformat(), json.dumps(data)))
        # This request proves the source is live, so any record saying its
        # quota is spent is wrong and must not survive to block the next
        # run. Same transaction as the cache insert: the two facts are one.
        quota.clear(self.conn, self.name)
        self.conn.commit()
        return data

    def quota_resets_at(self, now=None):
        """When a 429 from this source is expected to lift.

        Default: one hour. Deliberately short - a source whose real limit
        is per-minute must not sit out a whole day, and the cost of
        guessing short is one wasted request, while the cost of guessing
        long is lost harvesting. Override where the provider's window is
        actually known.
        """
        return (now or datetime.now(timezone.utc)) + timedelta(hours=1)

    def validate(self, data):
        """Raise if the (HTTP 200) payload is actually an error response."""

    def lookup(self, title):
        raise NotImplementedError
