"""The outbound destination guard: humble_catalog.outbound.

Every case here uses an IP literal or a reserved-TLD name, so getaddrinfo
answers without a DNS query and the suite stays hermetic. The two cases
that must not send a request run against a real http.server on an ephemeral
port and assert the server logged nothing - the interesting answer is the
absence of a connection, which a mock cannot demonstrate.
"""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

from humble_catalog import outbound


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.seen.append(self.path)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{self.server.server_port}/private")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    srv.seen = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://8.8.8.8/x",
    "javascript:alert(1)",
    "data:text/html,x",
])
def test_only_http_and_https_are_allowed(url):
    with pytest.raises(ValueError, match="unsupported scheme"):
        outbound.check_url(url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x",
    "http://10.0.0.1/x",
    "http://192.168.1.1/x",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/x",
])
def test_private_and_link_local_addresses_are_refused(url):
    with pytest.raises(ValueError, match="private or unroutable"):
        outbound.check_url(url)


def test_a_name_that_does_not_resolve_is_refused():
    # Fails closed: a resolution failure must not read as permission.
    with pytest.raises(ValueError, match="private or unroutable"):
        outbound.check_url("http://no-such.invalid.example.test/x")


def test_allowed_hosts_refuses_a_routable_host_that_is_not_listed():
    # The credential rule, distinct from the network rule: 8.8.4.4 is
    # perfectly routable and must still be refused, because a request that
    # carries an API key may only go to the host it was issued for.
    with pytest.raises(ValueError, match="expected one of"):
        outbound.check_url("https://8.8.4.4/x", allowed_hosts=frozenset({"8.8.8.8"}))


def test_allowed_hosts_admits_a_listed_host():
    outbound.check_url("https://8.8.8.8/x", allowed_hosts=frozenset({"8.8.8.8"}))


def test_an_allowlisted_host_that_is_not_routable_is_still_refused():
    with pytest.raises(ValueError, match="private or unroutable"):
        outbound.check_url("http://127.0.0.1/x",
                           allowed_hosts=frozenset({"127.0.0.1"}))


def test_get_refuses_a_private_destination_without_connecting(server):
    sess = requests.Session()
    with pytest.raises(ValueError, match="private or unroutable"):
        outbound.get(sess, f"http://127.0.0.1:{server.server_port}/x")
    assert server.seen == []


def test_check_initial_false_sends_the_owners_own_url(server):
    # url_import's asymmetry: the pasted URL is the owner's choice.
    sess = requests.Session()
    resp = outbound.get(sess, f"http://127.0.0.1:{server.server_port}/x",
                        check_initial=False)
    assert resp.status_code == 200
    assert server.seen == ["/x"]


def test_a_redirect_hop_is_checked_before_it_is_requested(server):
    sess = requests.Session()
    with pytest.raises(ValueError, match="private or unroutable"):
        outbound.get(sess, f"http://127.0.0.1:{server.server_port}/redirect",
                     check_initial=False)
    # The redirect was answered, but /private was never asked for.
    assert server.seen == ["/redirect"]
