import datetime as dt
import importlib.util
import ipaddress
import ssl
import subprocess
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID

from humble_catalog import lan

ROOT = Path(__file__).resolve().parents[1]


def test_the_token_is_created_once_and_then_reused(tmp_path):
    first = lan.load_or_create_token(tmp_path / "lan")
    assert len(first) >= 43                       # 32 random bytes, base64url
    assert lan.load_or_create_token(tmp_path / "lan") == first


def test_rotating_the_token_replaces_it(tmp_path):
    old = lan.load_or_create_token(tmp_path / "lan")
    new = lan.rotate_token(tmp_path / "lan")
    assert new != old
    assert lan.load_or_create_token(tmp_path / "lan") == new


def test_an_unreadable_token_is_an_error_not_a_new_token(tmp_path):
    # A silently regenerated token would unpair every phone with no
    # explanation. Refusing names the file instead.
    d = tmp_path / "lan"
    d.mkdir()
    (d / "token").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(lan.LanStateError, match="token"):
        lan.load_or_create_token(d)


def test_the_lan_folder_sits_beside_the_catalog(tmp_path):
    assert lan.lan_dir_for(tmp_path / "catalog.db") == (tmp_path / "lan").resolve()


def test_git_ignores_the_lan_folder():
    out = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "lan/token"],
                         capture_output=True, text=True)
    assert out.returncode == 0, "lan/ must be gitignored"


def test_the_data_check_refuses_the_lan_folder():
    spec = importlib.util.spec_from_file_location(
        "check_no_data_tracked", ROOT / "scripts" / "check_no_data_tracked.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.offenders(["lan/token", "lan/ca.key", "README.md"]) == [
        "lan/ca.key", "lan/token"]


def test_the_authority_is_a_ca_limited_to_private_addresses(tmp_path):
    _key, ca = lan.ensure_ca(tmp_path / "lan")
    basic = ca.extensions.get_extension_for_class(x509.BasicConstraints).value
    assert basic.ca is True and basic.path_length == 0
    nc = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert nc.critical
    ips = {n.value for n in nc.value.permitted_subtrees
           if isinstance(n, x509.IPAddress)}
    assert ips == {ipaddress.ip_network("10.0.0.0/8"),
                   ipaddress.ip_network("172.16.0.0/12"),
                   ipaddress.ip_network("192.168.0.0/16")}
    # RFC 5280 leaves a name TYPE unconstrained when no subtree of that
    # type is listed. Without this entry the authority could still vouch
    # for any website by DNS name.
    dns = {n.value for n in nc.value.permitted_subtrees
           if isinstance(n, x509.DNSName)}
    assert dns == {"invalid"}


def test_the_authority_is_created_once(tmp_path):
    _k1, first = lan.ensure_ca(tmp_path / "lan")
    _k2, again = lan.ensure_ca(tmp_path / "lan")
    assert first.serial_number == again.serial_number


def test_half_an_authority_is_refused_not_replaced(tmp_path):
    # A silently minted authority would need reinstalling on the phone,
    # and the phone would just start failing with no explanation.
    lan.ensure_ca(tmp_path / "lan")
    (tmp_path / "lan" / "ca.key").unlink()
    with pytest.raises(lan.LanStateError, match="--setup"):
        lan.ensure_ca(tmp_path / "lan")


def test_the_server_certificate_names_the_ip_and_chains_to_the_authority(tmp_path):
    _key, ca = lan.ensure_ca(tmp_path / "lan")
    crt, key = lan.issue_server_cert(tmp_path / "lan", "192.168.1.20")
    cert = x509.load_pem_x509_certificate(crt.read_bytes())
    cert.verify_directly_issued_by(ca)
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert san.value.get_values_for_type(x509.IPAddress) == [
        ipaddress.ip_address("192.168.1.20")]
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.SERVER_AUTH in eku
    life = cert.not_valid_after_utc - cert.not_valid_before_utc
    assert dt.timedelta(days=29) < life <= dt.timedelta(days=31)
    assert key.exists()


def test_a_public_address_is_refused(tmp_path):
    # The authority's constraints would make such a certificate invalid
    # anyway; saying so here beats a phone that silently refuses it.
    with pytest.raises(lan.LanStateError, match="private"):
        lan.issue_server_cert(tmp_path / "lan", "8.8.8.8")


def test_the_fingerprint_is_colon_separated_sha256(tmp_path):
    _key, ca = lan.ensure_ca(tmp_path / "lan")
    fp = lan.ca_fingerprint(ca)
    assert len(fp.split(":")) == 32 and fp == fp.upper()


def test_the_ssl_context_loads_the_issued_pair(tmp_path):
    crt, key = lan.issue_server_cert(tmp_path / "lan", "10.0.0.5")
    ctx = lan.ssl_context(crt, key)
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2
