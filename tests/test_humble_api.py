import json
from unittest.mock import Mock
import pytest
from humble_catalog.humble_api import (HumbleClient, MalformedOrderList,
                                         NotLoggedIn)

def _resp(payload, status=200, ctype="application/json"):
    r = Mock()
    r.status_code = status
    r.headers = {"Content-Type": ctype}
    r.json = Mock(return_value=payload)
    return r

def test_list_and_get_order():
    http = Mock()
    http.get.side_effect = [
        _resp([{"gamekey": "k1"}, {"gamekey": "k2"}]),
        _resp({"gamekey": "k1", "product": {}}),
    ]
    client = HumbleClient({"_simpleauth_sess": "x"}, delay=0, http=http)
    assert client.list_order_keys() == ["k1", "k2"]
    assert client.get_order("k1")["gamekey"] == "k1"
    called_urls = [c.args[0] for c in http.get.call_args_list]
    assert called_urls[1].endswith("/api/v1/order/k1")
    # Without all_tpkds=true the API omits external keys entirely.
    assert http.get.call_args_list[1].kwargs["params"] == {"all_tpkds": "true"}

def test_logged_in_false_on_html_redirect():
    http = Mock()
    http.get.return_value = _resp(None, status=200, ctype="text/html")
    client = HumbleClient({}, delay=0, http=http)
    assert client.logged_in() is False

def test_throttle_sleeps_between_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("time.monotonic", lambda: 100.0)
    http = Mock()
    http.get.return_value = _resp([])
    client = HumbleClient({}, delay=4.0, http=http)
    client.list_order_keys()
    client.list_order_keys()
    assert sleeps and abs(sleeps[0] - 4.0) < 0.01

# --- the order index's shape contract (E1) ---------------------------
# HumbleBundle order JSON is adversarial per the Operating envelope. The
# index is a different granularity from a single order: one bad entry
# must not cost every bundle, but a wholesale shape change must not read
# as an empty library either, or a harvest does nothing and reports
# success.

def test_a_malformed_entry_is_skipped_not_fatal():
    http = Mock()
    http.get.return_value = _resp([{"gamekey": "k1"}, {"no_gamekey": 1},
                                   "not-an-order", None])
    assert HumbleClient({}, delay=0, http=http).list_order_keys() == ["k1"]

def test_a_genuinely_empty_library_is_not_an_error():
    http = Mock()
    http.get.return_value = _resp([])
    assert HumbleClient({}, delay=0, http=http).list_order_keys() == []

def test_an_index_that_is_not_a_list_refuses():
    http = Mock()
    http.get.return_value = _resp({"orders": []})
    with pytest.raises(MalformedOrderList):
        HumbleClient({}, delay=0, http=http).list_order_keys()

def test_an_index_with_no_usable_entry_refuses_rather_than_reporting_empty():
    # Returning [] here would be the silent wrong answer: the harvest
    # would find nothing to do and exit successfully.
    http = Mock()
    http.get.return_value = _resp(["k1", "k2"])
    with pytest.raises(MalformedOrderList):
        HumbleClient({}, delay=0, http=http).list_order_keys()

def test_refusal_is_not_a_login_problem():
    # ensure_login acts on NotLoggedIn; a changed payload shape is not
    # something logging in again would fix, so it must not be that type.
    http = Mock()
    http.get.return_value = _resp({"orders": []})
    with pytest.raises(MalformedOrderList) as caught:
        HumbleClient({}, delay=0, http=http).list_order_keys()
    assert not isinstance(caught.value, NotLoggedIn)
