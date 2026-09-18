"""What `serve --lan` keeps on disk, and how each piece is made.

Everything lives in a `lan/` folder beside catalog.db: the pairing token,
the private certificate authority, and the server certificate issued
from it. Deliberately NOT inside catalog.db: `restore` would otherwise
bring back an old token and silently re-pair a phone that had been
unpaired. Backups and `reset` never touch this folder, and deleting it
resets the whole feature.

See docs/superpowers/specs/2026-09-18-lan-viewer-design.md.
"""
import datetime as dt
import io
import ipaddress
import secrets
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

LAN_DIR = "lan"
TOKEN_FILE = "token"


class LanStateError(Exception):
    """lan/ is in a state that must not be repaired silently.

    The message always says what to run next.
    """


def lan_dir_for(db_path):
    return Path(db_path).resolve().parent / LAN_DIR


def rotate_token(lan_dir):
    """Write a fresh token, unpairing every device, and return it."""
    path = Path(lan_dir) / TOKEN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token + "\n", encoding="ascii")
    return token


def load_or_create_token(lan_dir):
    """The pairing token, created on first use.

    A token file that exists but cannot be read is an error, never a
    reason to write a new one: that would unpair every phone with no
    explanation.
    """
    path = Path(lan_dir) / TOKEN_FILE
    if not path.exists():
        return rotate_token(lan_dir)
    try:
        token = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise LanStateError(
            f"cannot read the pairing token at {path} ({exc}) -- run "
            "`serve --lan --new-token` to replace it") from exc
    if not token:
        raise LanStateError(
            f"the pairing token at {path} is empty -- run "
            "`serve --lan --new-token` to replace it")
    return token


# The only addresses the authority may vouch for. An installed authority
# can normally sign for ANY site, so a leaked ca.key would let someone
# impersonate a bank to the phone; constrained, it can impersonate
# nothing outside a home network.
PRIVATE_NETWORKS = [ipaddress.ip_network(n) for n in
                    ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
# RFC 5280 leaves a name TYPE unconstrained when no subtree of that type
# is listed, so IP subtrees alone would leave every DNS name open. "invalid"
# is a reserved TLD (RFC 6761): permitting only it permits no real name.
NO_REAL_DNS_NAME = x509.DNSName("invalid")
CA_DAYS = 3650
SERVER_DAYS = 30


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _write_key(path, key):
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))


def ensure_ca(lan_dir):
    """(key, certificate) of the private authority, created on first use."""
    lan_dir = Path(lan_dir)
    key_path, crt_path = lan_dir / "ca.key", lan_dir / "ca.crt"
    if key_path.exists() != crt_path.exists():
        raise LanStateError(
            f"{lan_dir} holds only half of its certificate authority -- "
            "delete that folder and run `serve --lan --setup` again, then "
            "reinstall the certificate on the phone")
    if key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(),
                                                 password=None)
        return key, x509.load_pem_x509_certificate(crt_path.read_bytes())

    lan_dir.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                         "Humble Catalog LAN CA")])
    now = _now()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0),
                       critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False,
            key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.NameConstraints(
            permitted_subtrees=[*(x509.IPAddress(n) for n in PRIVATE_NETWORKS),
                                NO_REAL_DNS_NAME],
            excluded_subtrees=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(
            key.public_key()), critical=False)
        .sign(key, hashes.SHA256()))
    _write_key(key_path, key)
    crt_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key, cert


def issue_server_cert(lan_dir, ip):
    """Issue server.crt/server.key for `ip`; return (crt_path, key_path).

    Reissued on every start rather than reused, so a DHCP address change
    never leaves a certificate naming the old address.
    """
    addr = ipaddress.ip_address(ip)
    if not any(addr in n for n in PRIVATE_NETWORKS):
        raise LanStateError(
            f"{ip} is not a private address; the certificate authority can "
            "only vouch for 10.x, 172.16-31.x and 192.168.x -- pass one "
            "with --lan-host")
    ca_key, ca_cert = ensure_ca(lan_dir)
    key = ec.generate_private_key(ec.SECP256R1())
    now = _now()
    cert = (
        x509.CertificateBuilder()
        # An EMPTY subject: OpenSSL reads a hostname-like CN as a DNS name
        # when there is no DNS SAN, and the authority permits no real DNS
        # name, so CN=<ip> fails verification as a subtree violation.
        .subject_name(x509.Name([]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=SERVER_DAYS))
        # RFC 5280 4.2.1.6: with an empty subject the SAN must be critical.
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(addr)]),
                       critical=True)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None),
                       critical=True)
        .add_extension(x509.ExtendedKeyUsage(
            [ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
            ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256()))
    lan_dir = Path(lan_dir)
    crt_path, key_path = lan_dir / "server.crt", lan_dir / "server.key"
    _write_key(key_path, key)
    crt_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return crt_path, key_path


def ca_fingerprint(cert):
    """SHA-256, as Android shows it under Trusted credentials."""
    return cert.fingerprint(hashes.SHA256()).hex(":").upper()


def ssl_context(crt_path, key_path):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(crt_path), str(key_path))
    return ctx


@dataclass
class LanOptions:
    """What `serve --lan` was asked for. None means "work it out"."""
    host: str | None = None
    port: int | None = None
    setup: bool = False
    new_token: bool = False


def _private(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in PRIVATE_NETWORKS)


def lan_address():
    """This machine's address on the home network.

    Asks the OS which interface its default route leaves by. connect() on a
    UDP socket only picks a route; no packet is sent. 192.0.2.1 is a
    documentation address (RFC 5737), so nothing real is ever named.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
    except OSError:
        ip = None
    finally:
        s.close()
    if ip and _private(ip):
        return ip
    try:
        found = sorted({info[4][0] for info in socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET)})
    except OSError:
        found = []
    private = [a for a in found if _private(a)]
    listed = ", ".join(private) or "none"
    raise LanStateError(
        f"could not tell which address is this machine's LAN address "
        f"(private addresses found: {listed}) -- pass one with --lan-host")


def ca_download_app(lan_dir):
    """The plain-HTTP app `--setup` runs: exactly one route, /ca.crt.

    The certificate is public; what matters is that it is not swapped in
    transit, which comparing fingerprints catches.
    """
    from flask import Flask, send_file
    crt = Path(lan_dir).resolve() / "ca.crt"
    app = Flask(__name__, static_folder=None)

    @app.get("/ca.crt")
    def ca_crt():
        return send_file(crt, mimetype="application/x-x509-ca-cert",
                         as_attachment=True,
                         download_name="humble-catalog-lan-ca.crt")

    return app


def _print_qr(url):
    import qrcode
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    try:
        print(buf.getvalue())
    except UnicodeEncodeError:
        # A console that cannot draw block characters still gets the link.
        print("(this console cannot draw the QR code; use the link)")


def print_instructions(url, *, ca_url=None, fingerprint=None):
    """What `serve --lan` prints. The pairing link is a credential."""
    if ca_url:
        print("One-time setup: install this certificate on the phone.")
        print(f"  {ca_url}")
        _print_qr(ca_url)
        print("  Settings > Security > Encryption & credentials > "
              "Install a certificate > CA certificate")
        print(f"  Check its SHA-256 under Trusted credentials > User:\n"
              f"  {fingerprint}\n")
    print("Pair a phone by opening this link (keep it private -- it grants "
          "access to your catalog):")
    print(f"  {url}")
    _print_qr(url)
