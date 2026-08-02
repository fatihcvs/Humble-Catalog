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

# The shape boundary lives in humble_catalog/shapes.py, because the
# acquisition path needs the same rules the metadata parsers do. It is
# re-exported here so every `from humble_catalog.sources.base import ...`
# keeps working and the settled class that owns these stays enumerable
# from this module.
from humble_catalog.shapes import (  # noqa: F401
    as_list, as_mapping, as_number, as_text, first_mapping, first_text,
    text_list)

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
