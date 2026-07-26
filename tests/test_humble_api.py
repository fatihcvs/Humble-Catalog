import json
from unittest.mock import Mock
from humble_catalog.humble_api import HumbleClient

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
