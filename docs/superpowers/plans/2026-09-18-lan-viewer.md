# LAN Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m humble_catalog serve --lan` makes a read-only copy of the viewer reachable over HTTPS from phones paired with a token link, with a card layout below ~600 px.

**Architecture:** `create_app` is split into read and write route groups. A new `create_lan_app` registers only the read group, behind a host check and a pairing-cookie check. `humble_catalog/lan.py` owns everything on disk under `lan/`: the pairing token, a name-constrained local certificate authority, and a per-start server certificate. `serve` runs the loopback app and the LAN app side by side with `werkzeug.serving.make_server`. The front end reads `read_only` from `/api/status` and hides writes.

**Tech Stack:** Python 3.12, Flask 3.1 / Werkzeug 3.1, `cryptography` (new), `qrcode` (new), vanilla JS with the Node test harness (`tests/js/harness.mjs`).

**Spec:** `docs/superpowers/specs/2026-09-18-lan-viewer-design.md` (issue #6, sub-project 1).

## Global Constraints

- **Privacy standing order (`CLAUDE.md`).** Committed text uses only invented titles from `docs/TEST-DATA.md`. Any screenshot is taken on the demo catalog (`scripts/demo_catalog.py`, port 8099), never the real one, and is reviewed by eye.
- The pre-commit hook runs `scripts/leak_check.py --staged`. If it flags a word, reword it; never bypass the hook.
- Never pipe `leak_check.py` into a commit (`… | tail && git commit`): the pipe hides its exit code.
- Use `.venv/Scripts/python -m pip`, never `.venv/Scripts/pip` (the shim is broken).
- **Installing packages downloads files: ask the owner before running any `pip install`.**
- One branch for the whole plan, `feat/lan-viewer`, from `main`.
- Without `--lan`, `serve` must behave exactly as today. The existing tests `test_serve_uses_default_port` and `test_serve_accepts_a_port` pin this and must pass unchanged.
- The LAN app never gains a POST route. Task 4's class test enforces it.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Spec amendments made by this plan

Two details in the spec are wrong as written. The tasks named below correct both the code and the spec text.

1. **Name constraints must also constrain DNS names (Task 3).** Under RFC 5280, a `NameConstraints` extension that lists only `iPAddress` subtrees leaves `dNSName` entirely unconstrained. The authority as specified could therefore still vouch for any website by name, which is exactly the leak the constraint exists to prevent. The fix is to also permit only `dNSName` `invalid`, a reserved TLD (RFC 6761) that no real site can use.
2. **`/pair` answers with a self-refreshing page, not a 303 (Task 4).** A link opened from a QR-scanner app has no initiating site, and Chrome may withhold a `SameSite=Strict` cookie on the redirected request, so the first page would say "not paired". A 200 page whose `<meta http-equiv="refresh">` goes to `/` makes the next navigation same-origin, so `Strict` works. The token still leaves the address bar, and `Referrer-Policy: no-referrer` keeps it out of any referrer.

## File map

| File | Change | Responsibility |
|---|---|---|
| `humble_catalog/webapp/__init__.py` | modify | Route split; `create_lan_app`; `serve` with `--lan` |
| `humble_catalog/lan.py` | create | Token, certificate authority, server certificate, SSL context, LAN address, CA-download app, printed instructions |
| `humble_catalog/__main__.py` | modify | `serve` flags |
| `humble_catalog/webapp/static/app.js` | modify | `READ_ONLY` flag; `load()` skips write-only loaders |
| `humble_catalog/webapp/static/shell.js` | modify | Boot reads `/api/status`; `applyMode`; section gating; narrow re-render |
| `humble_catalog/webapp/static/catalog.js` | modify | `nameExtras`, `statusCell`, read-only stars, `renderCards`, narrow switch |
| `humble_catalog/webapp/static/keys.js` | modify | No hide/unhide buttons in read-only mode |
| `humble_catalog/webapp/static/index.html` | modify | `#card-list` container |
| `humble_catalog/webapp/static/style.css` | modify | Read-only hiding, cards, scrollable tab bar |
| `tests/js/harness.mjs` | modify | Publish the new bindings |
| `tests/test_lan.py` | create | Token, certificates, address, CA-download app |
| `tests/test_webapp.py` | modify | `read_only` flag, LAN app, pairing, `serve` wiring |
| `tests/test_webapp_js.py` | modify | Read-only rendering, cards |
| `tests/test_main.py` | modify | `serve` flag validation |
| `pyproject.toml` | modify | `cryptography`, `qrcode` |
| `.gitignore`, `scripts/check_no_data_tracked.py` | modify | `lan/` |
| `README.md`, `CLAUDE.md`, `docs/BACKLOG.md`, the spec | modify | Documentation |

---

### Task 1: Split `create_app` into read and write route groups

A pure refactor plus one new response field. Every existing test must still pass.

**Files:**
- Modify: `humble_catalog/webapp/__init__.py:11` (imports), `:126-849` (`create_app`)
- Test: `tests/test_webapp.py`

**Interfaces:**
- Produces:
  - `_conn()`: the request's `sqlite3` connection, opened lazily from `current_app.config["DB_PATH"]`.
  - `_new_app(db_path, covers_dir, read_only: bool) -> Flask`: sets `DB_PATH`, `COVERS_DIR` (a resolved `Path`) and `READ_ONLY`, and registers the connection teardown.
  - `_register_read_routes(app) -> None`: registers `/`, `/covers/<path:filename>`, `GET /api/items`, `GET /api/stats`, `GET /api/keys` and `GET /api/status`.
  - `_register_write_routes(app) -> None`: registers every other route.
  - `GET /api/status` now returns `{"runs": [...], "read_only": <bool>}`.

- [ ] **Step 1: Create the branch**

```bash
git switch -c feat/lan-viewer main
```

- [ ] **Step 2: Write the failing test** (append to `tests/test_webapp.py`)

```python
def test_status_reports_the_loopback_app_is_not_read_only(tmp_path):
    # The front end decides whether to render editing controls from this
    # flag, so the full viewer must say false, explicitly.
    dbp = tmp_path / "t.db"
    _seed(dbp)
    client = create_app(db_path=str(dbp)).test_client()
    body = client.get("/api/status").get_json()
    assert body["read_only"] is False
    assert body["runs"] == []
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py::test_status_reports_the_loopback_app_is_not_read_only -v`
Expected: FAIL with `KeyError: 'read_only'`.

- [ ] **Step 4: Restructure the module**

In the Flask import on line 11, add `current_app`:

```python
from flask import (Flask, Response, current_app, g, jsonify, request,
                   send_from_directory)
```

Directly above `def create_app`, add:

```python
def _conn():
    """The request's catalog connection, opened on first use.

    Module-level rather than a closure inside create_app, so the read and
    write route groups -- registered by separate functions, and on two
    different apps -- share one definition of "the connection".
    """
    if "conn" not in g:
        g.conn = db.connect(current_app.config["DB_PATH"])
    return g.conn


def _new_app(db_path, covers_dir, read_only):
    """A bare app: config and connection teardown, no routes, no guards."""
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["DB_PATH"] = db_path
    app.config["COVERS_DIR"] = Path(covers_dir).resolve()
    app.config["READ_ONLY"] = read_only

    @app.teardown_appcontext
    def close(_exc):
        c = g.pop("conn", None)
        if c is not None:
            c.close()

    return app


def _register_read_routes(app):
    """The routes a read-only viewer needs, and nothing else.

    This is the whole of what the LAN app serves (create_lan_app), so a
    route belongs here only if it reads and a paired phone should reach
    it. The maintenance reads (/api/review, /api/duplicates) are
    deliberately NOT here: they are only useful beside the writes they
    feed. test_lan_app_serves_only_the_pinned_read_routes pins this list.
    """
    conn = _conn
    covers = app.config["COVERS_DIR"]
```

Then **move, verbatim**, the current lines `156-204` (from `@app.get("/")` through the end of `key_report`) so they follow `covers = app.config["COVERS_DIR"]` inside `_register_read_routes`. The indentation stays at four spaces. After them, add the status route, now reporting `read_only`:

```python
    @app.get("/api/status")
    def status():
        rows = conn().execute("SELECT * FROM run_status WHERE phase != 'done'").fetchall()
        return jsonify({"runs": [dict(r) for r in rows],
                        "read_only": app.config["READ_ONLY"]})


def _register_write_routes(app):
    """Every route that writes, runs a job, reaches the network, or feeds one
    of those. Registered only by create_app, never on the LAN app."""
    conn = _conn
```

Then **move, verbatim**, the current lines `206-842` (from `def _key_ref():` through the end of `job_state`) into `_register_write_routes`, after `conn = _conn`. Delete the old `status` route (lines `844-847`), which now lives in the read group.

Replace what remains of `create_app` with:

```python
def create_app(db_path="catalog.db", covers_dir="covers"):
    app = _new_app(db_path, covers_dir, read_only=False)
    # One runner per app. Held in config rather than a module global so a
    # test can swap in a stub, and so two apps in one process (the suite
    # makes several) never share a job slot.
    app.config["JOB_RUNNER"] = jobs.JobRunner(db_path=db_path)

    @app.before_request
    def refuse_foreign_hosts():
        # Before routing, so a foreign caller cannot reach any handler --
        # not even by getting the content type right on a write.
        if not host_is_loopback(request.headers.get("Host")):
            return Response(
                "Refused: the catalog viewer only answers requests "
                "addressed to localhost.\n",
                status=403, mimetype="text/plain")

    _register_read_routes(app)
    _register_write_routes(app)
    return app
```

The moved code still calls `conn()`, `app`, `_json_object()` and `_text_field()`, which the `conn = _conn` alias, the `app` parameter and the module scope all provide. `_runner()` reads `app.config["JOB_RUNNER"]` exactly as before.

- [ ] **Step 5: Run the new test and the whole web suite**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py tests/test_webapp_js.py -q`
Expected: all pass, including the new test.

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py
git commit -m "refactor(viewer): register read and write routes in two groups

A read-only LAN app will register only the first group. /api/status
now reports read_only, false on the loopback viewer.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The pairing token, and keeping `lan/` out of git

**Files:**
- Create: `humble_catalog/lan.py`
- Create: `tests/test_lan.py`
- Modify: `.gitignore`, `scripts/check_no_data_tracked.py:30-41` (`FORBIDDEN`)

**Interfaces:**
- Produces:
  - `LAN_DIR = "lan"`
  - `class LanStateError(Exception)`: raised for any `lan/` state that must not be repaired silently. Its message says what to run.
  - `lan_dir_for(db_path) -> Path`: `Path(db_path).resolve().parent / "lan"`.
  - `load_or_create_token(lan_dir) -> str`
  - `rotate_token(lan_dir) -> str`

- [ ] **Step 1: Write the failing tests** (`tests/test_lan.py`)

```python
import importlib.util
import subprocess
from pathlib import Path

import pytest

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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_lan.py -v`
Expected: collection error, `ModuleNotFoundError: No module named 'humble_catalog.lan'`.

- [ ] **Step 3: Implement**

Create `humble_catalog/lan.py`:

```python
"""What `serve --lan` keeps on disk, and how each piece is made.

Everything lives in a `lan/` folder beside catalog.db: the pairing token,
the private certificate authority, and the server certificate issued
from it. Deliberately NOT inside catalog.db: `restore` would otherwise
bring back an old token and silently re-pair a phone that had been
unpaired. Backups and `reset` never touch this folder, and deleting it
resets the whole feature.

See docs/superpowers/specs/2026-09-18-lan-viewer-design.md.
"""
import secrets
from pathlib import Path

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
```

In `.gitignore`, under `# Runtime data`, add:

```
# serve --lan: pairing token, certificate authority and its private key
lan/
```

In `scripts/check_no_data_tracked.py`, add to `FORBIDDEN` after `".playwright-profile/*",`:

```python
    "lan/*", "**/lan/*",               # serve --lan: token, CA private key
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_lan.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add humble_catalog/lan.py tests/test_lan.py .gitignore scripts/check_no_data_tracked.py
git commit -m "feat(lan): a pairing token kept in a gitignored lan/ folder

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The certificate authority and the server certificate

**Files:**
- Modify: `pyproject.toml:18` (dependencies)
- Modify: `humble_catalog/lan.py`
- Modify: `tests/test_lan.py`
- Modify: `docs/superpowers/specs/2026-09-18-lan-viewer-design.md` (spec amendment 1)

**Interfaces:**
- Produces:
  - `PRIVATE_NETWORKS`: a list of the three `ipaddress.IPv4Network`s.
  - `ensure_ca(lan_dir) -> (private_key, x509.Certificate)`: loads the authority, or creates it on first use. Raises `LanStateError` when only one of `ca.key` and `ca.crt` exists.
  - `issue_server_cert(lan_dir, ip: str) -> (Path crt, Path key)`: always reissues. Raises `LanStateError` for a non-private IP.
  - `ca_fingerprint(cert) -> str`: SHA-256 as colon-separated uppercase hex.
  - `ssl_context(crt, key) -> ssl.SSLContext`

- [ ] **Step 1: Install the new dependencies (ask the owner first)**

In `pyproject.toml`, change line 18 to:

```toml
dependencies = ["requests>=2.31", "flask>=3.0", "playwright>=1.40", "rapidfuzz>=3.5", "openpyxl>=3.1", "cryptography>=42", "qrcode>=7.4"]
```

**Ask the owner** before downloading anything: "Task 3 needs `cryptography` and `qrcode` from PyPI. OK to run `.venv/Scripts/python -m pip install -e .`?" Once they say yes:

Run: `.venv/Scripts/python -m pip install -e .`
Expected: installs `cryptography` and `qrcode`.

- [ ] **Step 2: Write the failing tests** (append to `tests/test_lan.py`)

```python
import datetime as dt
import ipaddress
import ssl

from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID


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
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_lan.py -v`
Expected: the new tests fail with `AttributeError: module 'humble_catalog.lan' has no attribute 'ensure_ca'`.

- [ ] **Step 4: Implement** (add to `humble_catalog/lan.py`)

Extend the imports at the top:

```python
import datetime as dt
import ipaddress
import secrets
import ssl
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
```

Then add below `load_or_create_token`:

```python
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
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                                     str(addr))]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(addr)]),
                       critical=False)
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_lan.py -v`
Expected: 13 passed.

- [ ] **Step 6: Amend the spec**

In `docs/superpowers/specs/2026-09-18-lan-viewer-design.md`, in "The certificate authority", replace the **Name constraints** bullet with:

```markdown
- **Name constraints** permitting only `10.0.0.0/8`, `172.16.0.0/12` and
  `192.168.0.0/16`, plus the DNS name `invalid`. An installed authority
  can normally vouch for any site, so a leaked `ca.key` would let someone
  impersonate any website to that phone. With the constraints, which
  Chrome enforces, it can vouch only for private addresses. The DNS entry
  is needed because RFC 5280 leaves a name type unconstrained when no
  subtree of that type is listed; `invalid` is a reserved TLD, so
  permitting only it permits no real name.
```

In "Testing", change "name constraints of exactly the three private ranges" to "name constraints of exactly the three private ranges and the DNS name `invalid`".

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml humble_catalog/lan.py tests/test_lan.py docs/superpowers/specs/2026-09-18-lan-viewer-design.md
git commit -m "feat(lan): a name-constrained local CA and per-start server certificates

IP subtrees alone leave DNS names unconstrained under RFC 5280, so the
authority also permits only the reserved name 'invalid'. The spec is
amended to match.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `create_lan_app`, with the host check and pairing

**Files:**
- Modify: `humble_catalog/webapp/__init__.py` (imports; new constants and `create_lan_app` after `create_app`)
- Modify: `docs/superpowers/specs/2026-09-18-lan-viewer-design.md` (spec amendment 2)
- Test: `tests/test_webapp.py`

**Interfaces:**
- Consumes: `_new_app`, `_register_read_routes` (Task 1).
- Produces:
  - `create_lan_app(db_path="catalog.db", covers_dir="covers", *, host: str, port: int, token: str) -> Flask`
  - `PAIR_COOKIE = "hc_lan"`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_webapp.py`)

```python
from humble_catalog.webapp import create_lan_app

LAN_HOST, LAN_PORT, TOKEN = "192.168.1.20", 8088, "t" * 43
LAN_BASE = f"https://{LAN_HOST}:{LAN_PORT}"
# What the LAN app may serve. Adding a route to the read group fails this
# test until the list is edited on purpose -- which is the point.
LAN_RULES = {"/", "/static/<path:filename>", "/covers/<path:filename>",
             "/api/items", "/api/stats", "/api/keys", "/api/status", "/pair"}


def _lan_client(tmp_path, token=TOKEN):
    dbp = tmp_path / "t.db"
    _seed(dbp)
    app = create_lan_app(db_path=str(dbp), host=LAN_HOST, port=LAN_PORT,
                         token=token)
    return app, app.test_client()


def _paired(client):
    return client.get(f"/pair?token={TOKEN}", base_url=LAN_BASE)


def test_lan_app_serves_only_the_pinned_read_routes(tmp_path):
    app, _client = _lan_client(tmp_path)
    rules = list(app.url_map.iter_rules())
    assert {r.rule for r in rules} == LAN_RULES
    for r in rules:
        assert r.methods <= {"GET", "HEAD", "OPTIONS"}, (r.rule, r.methods)


def test_every_lan_route_refuses_an_unpaired_request(tmp_path):
    app, client = _lan_client(tmp_path)
    for rule in app.url_map.iter_rules():
        if rule.rule == "/pair":
            continue
        path = rule.rule.replace("<path:filename>", "x")
        resp = client.get(path, base_url=LAN_BASE)
        assert resp.status_code == 403, rule.rule
        assert b"Not paired" in resp.data, rule.rule


def test_pairing_sets_a_strict_secure_cookie_and_leaves_the_token_behind(tmp_path):
    _app, client = _lan_client(tmp_path)
    resp = _paired(client)
    assert resp.status_code == 200
    cookie = resp.headers["Set-Cookie"]
    for part in ("hc_lan=" + TOKEN, "Secure", "HttpOnly", "SameSite=Strict",
                 "Max-Age=34560000", "Path=/"):
        assert part in cookie, part
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    # A page that refreshes to /, not a 303: the next navigation is then
    # same-origin, so a Strict cookie is sent even when the link came from
    # a QR-scanner app. The token must not ride along.
    assert b'http-equiv="refresh" content="0;url=/"' in resp.data
    assert TOKEN.encode() not in resp.data


def test_a_paired_phone_can_read_the_catalog(tmp_path):
    _app, client = _lan_client(tmp_path)
    _paired(client)
    items = client.get("/api/items", base_url=LAN_BASE).get_json()["items"]
    assert items[0]["name"] == "All Systems Red"
    assert client.get("/api/status", base_url=LAN_BASE).get_json()[
        "read_only"] is True


def test_a_wrong_token_does_not_pair(tmp_path, capsys):
    _app, client = _lan_client(tmp_path)
    resp = client.get("/pair?token=wrong", base_url=LAN_BASE)
    assert resp.status_code == 403
    assert "Set-Cookie" not in resp.headers
    assert "refused a pairing attempt" in capsys.readouterr().out


def test_a_rotated_token_unpairs_an_old_cookie(tmp_path):
    _app, client = _lan_client(tmp_path, token="n" * 43)
    resp = client.get("/api/items", base_url=LAN_BASE,
                      headers={"Cookie": f"hc_lan={TOKEN}"})
    assert resp.status_code == 403


def test_the_lan_app_refuses_a_foreign_host(tmp_path):
    # DNS rebinding, LAN edition: evil.example re-pointed at the LAN IP
    # still arrives with its own name in Host.
    _app, client = _lan_client(tmp_path)
    _paired(client)
    resp = client.get("/api/items", base_url="https://evil.example:8088",
                      headers={"Cookie": f"hc_lan={TOKEN}"})
    assert resp.status_code == 403
    assert b"Not paired" not in resp.data


def test_the_lan_app_has_no_write_route_to_reach(tmp_path):
    _app, client = _lan_client(tmp_path)
    _paired(client)
    resp = client.post("/api/items/1/rating", json={"rating": 5},
                       base_url=LAN_BASE)
    assert resp.status_code in (404, 405)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -k "lan or pair" -v`
Expected: ImportError, `cannot import name 'create_lan_app'`.

- [ ] **Step 3: Implement**

Add `import hmac` to the stdlib imports at the top of `humble_catalog/webapp/__init__.py`. Then, after `create_app`, add:

```python
PAIR_COOKIE = "hc_lan"
# Chrome caps cookie lifetime at 400 days; asking for more buys nothing.
PAIR_MAX_AGE = 400 * 24 * 3600
NOT_PAIRED = ("Not paired: open the pairing link that "
              "`python -m humble_catalog serve --lan` prints.\n")
# A page, not a 303. A link opened from a QR-scanner app has no initiating
# site, and Chrome may withhold a SameSite=Strict cookie on the redirected
# request; a same-origin refresh is an ordinary same-site navigation.
PAIRED_PAGE = """<!doctype html><meta charset="utf-8">
<meta http-equiv="refresh" content="0;url=/">
<title>Paired</title><p>Paired. <a href="/">Open the catalog</a>.</p>"""


def _same_token(given, token):
    # Bytes, because compare_digest refuses a str with non-ASCII in it,
    # and a hostile query string is exactly where that would arrive.
    return hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))


def create_lan_app(db_path="catalog.db", covers_dir="covers", *, host, port,
                   token):
    """The read-only viewer a paired phone reaches over the LAN.

    Registers the read group and nothing else, so a write route here is not
    blocked, it is absent. Every request must name this app's own address
    in Host (the LAN counterpart of refuse_foreign_hosts) and carry the
    pairing cookie, except /pair, which is how the cookie is obtained.
    """
    app = _new_app(db_path, covers_dir, read_only=True)
    authority = f"{host}:{port}".lower()

    @app.before_request
    def guard():
        if (request.headers.get("Host") or "").strip().lower() != authority:
            return Response(
                "Refused: this viewer only answers requests addressed to "
                f"{authority}.\n", status=403, mimetype="text/plain")
        if request.path == "/pair":
            return None
        if not _same_token(request.cookies.get(PAIR_COOKIE, ""), token):
            return Response(NOT_PAIRED, status=403, mimetype="text/plain")
        return None

    @app.get("/pair")
    def pair():
        if not _same_token(request.args.get("token", ""), token):
            print(f"serve --lan: refused a pairing attempt from "
                  f"{request.remote_addr}")
            return Response(NOT_PAIRED, status=403, mimetype="text/plain")
        resp = Response(PAIRED_PAGE, mimetype="text/html")
        resp.set_cookie(PAIR_COOKIE, token, max_age=PAIR_MAX_AGE, path="/",
                        secure=True, httponly=True, samesite="Strict")
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp

    _register_read_routes(app)
    return app
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_webapp.py -q`
Expected: all pass.

- [ ] **Step 5: Amend the spec**

In the spec's "Pairing a phone" section, replace the bullet "on a match, sets the cookie and redirects to `/`, so the token leaves the address bar and is never sent as a referrer;" with:

```markdown
- on a match, sets the cookie and answers a short page that refreshes
  itself to `/`, with `Referrer-Policy: no-referrer`. The token leaves
  the address bar and is never sent as a referrer. A page rather than a
  303: a link opened from a QR-scanner app has no initiating site, and
  Chrome may withhold a `SameSite=Strict` cookie on the redirected
  request, while a same-origin refresh is an ordinary same-site
  navigation;
```

- [ ] **Step 6: Commit**

```bash
git add humble_catalog/webapp/__init__.py tests/test_webapp.py docs/superpowers/specs/2026-09-18-lan-viewer-design.md
git commit -m "feat(lan): a read-only app for paired devices on the LAN

Only the read route group is registered, behind a host check pinned to
the LAN address and a pairing cookie. /pair answers a self-refreshing
page rather than a 303 so a SameSite=Strict cookie survives a link
opened from a QR scanner; the spec is amended to match.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `serve --lan`: address, two servers, setup listener, CLI flags

**Files:**
- Modify: `humble_catalog/lan.py` (append)
- Modify: `humble_catalog/webapp/__init__.py` (`serve`)
- Modify: `humble_catalog/__main__.py:142-144` (flags), `:290-292` (dispatch)
- Test: `tests/test_lan.py`, `tests/test_webapp.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: everything from Tasks 2-4.
- Produces:
  - `@dataclass LanOptions(host: str | None = None, port: int | None = None, setup: bool = False, new_token: bool = False)`
  - `lan_address() -> str`
  - `ca_download_app(lan_dir) -> Flask`
  - `print_instructions(url, *, ca_url=None, fingerprint=None) -> None`
  - `webapp.serve(db_path="catalog.db", port=8087, lan=None)`
  - `webapp._run_all(servers) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_lan.py`:

```python
import socket


def test_the_lan_address_comes_from_the_default_route(monkeypatch):
    class FakeSocket:
        def __init__(self, *a): pass
        def connect(self, addr): self.addr = addr
        def getsockname(self): return ("192.168.1.20", 50000)
        def close(self): pass
    monkeypatch.setattr(lan.socket, "socket", FakeSocket)
    assert lan.lan_address() == "192.168.1.20"


def test_a_public_or_missing_route_address_is_an_error(monkeypatch):
    class FakeSocket:
        def __init__(self, *a): pass
        def connect(self, addr): pass
        def getsockname(self): return ("8.8.4.4", 50000)
        def close(self): pass
    monkeypatch.setattr(lan.socket, "socket", FakeSocket)
    monkeypatch.setattr(lan.socket, "getaddrinfo",
                        lambda *a, **k: [(None, None, None, None, ("10.0.0.7", 0)),
                                         (None, None, None, None, ("172.20.0.1", 0))])
    with pytest.raises(lan.LanStateError) as exc:
        lan.lan_address()
    assert "10.0.0.7" in str(exc.value) and "--lan-host" in str(exc.value)


def test_the_setup_app_serves_only_the_ca_certificate(tmp_path):
    lan.ensure_ca(tmp_path / "lan")
    app = lan.ca_download_app(tmp_path / "lan")
    assert {r.rule for r in app.url_map.iter_rules()} == {"/ca.crt"}
    resp = app.test_client().get("/ca.crt")
    assert resp.status_code == 200
    assert resp.mimetype == "application/x-x509-ca-cert"
    assert resp.data.startswith(b"-----BEGIN CERTIFICATE-----")
```

Append to `tests/test_webapp.py`:

```python
import ssl as _ssl
from humble_catalog import lan as lanmod, webapp as webmod


def _stub_servers(monkeypatch):
    built = []

    class FakeServer:
        def __init__(self, host, port, app, **kw):
            self.host, self.port, self.app = host, port, app
            self.ssl_context = kw.get("ssl_context")
            built.append(self)
        def server_close(self): pass

    monkeypatch.setattr(webmod, "make_server",
                        lambda host, port, app, **kw: FakeServer(host, port, app, **kw))
    monkeypatch.setattr(webmod, "_run_all", lambda servers: None)
    monkeypatch.setattr(webmod.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(lanmod, "lan_address", lambda: "192.168.1.20")
    return built


def test_serve_lan_runs_the_loopback_and_lan_servers(tmp_path, monkeypatch, capsys):
    built = _stub_servers(monkeypatch)
    dbp = tmp_path / "catalog.db"
    _seed(dbp)
    webmod.serve(db_path=str(dbp), port=8087, lan=lanmod.LanOptions())
    loop, lan_srv = built
    assert (loop.host, loop.port) == ("127.0.0.1", 8087)
    assert loop.app.config["READ_ONLY"] is False and loop.ssl_context is None
    assert (lan_srv.host, lan_srv.port) == ("192.168.1.20", 8088)
    assert lan_srv.app.config["READ_ONLY"] is True
    assert isinstance(lan_srv.ssl_context, _ssl.SSLContext)
    token = (tmp_path / "lan" / "token").read_text().strip()
    assert f"https://192.168.1.20:8088/pair?token={token}" in capsys.readouterr().out


def test_serve_lan_setup_adds_the_certificate_download(tmp_path, monkeypatch, capsys):
    built = _stub_servers(monkeypatch)
    dbp = tmp_path / "catalog.db"
    _seed(dbp)
    webmod.serve(db_path=str(dbp), port=8087,
                 lan=lanmod.LanOptions(setup=True, port=9000))
    assert [(s.host, s.port) for s in built] == [
        ("127.0.0.1", 8087), ("192.168.1.20", 9000), ("192.168.1.20", 9001)]
    out = capsys.readouterr().out
    assert "http://192.168.1.20:9001/ca.crt" in out and "SHA-256" in out


def test_serve_lan_new_token_replaces_the_token(tmp_path, monkeypatch):
    _stub_servers(monkeypatch)
    dbp = tmp_path / "catalog.db"
    _seed(dbp)
    old = lanmod.load_or_create_token(tmp_path / "lan")
    webmod.serve(db_path=str(dbp), lan=lanmod.LanOptions(new_token=True))
    assert (tmp_path / "lan" / "token").read_text().strip() != old


def test_a_busy_port_closes_what_was_opened_and_says_which(tmp_path, monkeypatch):
    closed = []

    class FakeServer:
        def server_close(self): closed.append(self)

    def make(host, port, app, **kw):
        if port == 8088:
            raise OSError("address in use")
        return FakeServer()

    monkeypatch.setattr(webmod, "make_server", make)
    monkeypatch.setattr(lanmod, "lan_address", lambda: "192.168.1.20")
    dbp = tmp_path / "catalog.db"
    _seed(dbp)
    with pytest.raises(lanmod.LanStateError, match="8088.*--lan-port"):
        webmod.serve(db_path=str(dbp), lan=lanmod.LanOptions())
    assert len(closed) == 1           # the loopback server, opened first
```

Append to `tests/test_main.py`:

```python
def test_serve_lan_passes_its_options(monkeypatch):
    seen = {}
    monkeypatch.setattr("humble_catalog.webapp.serve",
                        lambda **kw: seen.update(kw))
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "serve", "--lan",
                                      "--lan-host", "10.0.0.5", "--setup"])
    main()
    assert seen["port"] == 8087
    assert (seen["lan"].host, seen["lan"].port, seen["lan"].setup,
            seen["lan"].new_token) == ("10.0.0.5", None, True, False)


@pytest.mark.parametrize("flag", [["--lan-host", "10.0.0.5"],
                                  ["--lan-port", "9000"],
                                  ["--setup"], ["--new-token"]])
def test_lan_flags_need_lan(monkeypatch, capsys, flag):
    monkeypatch.setattr("humble_catalog.webapp.serve", lambda **kw: None)
    monkeypatch.setattr(sys, "argv", ["humble_catalog", "serve", *flag])
    with pytest.raises(SystemExit):
        main()
    assert "needs --lan" in capsys.readouterr().err
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_lan.py tests/test_webapp.py tests/test_main.py -k "lan or setup or token or busy" -q`
Expected: failures on `lan.lan_address`, `lan.LanOptions`, `webmod.make_server` and the unknown `--lan` argument.

- [ ] **Step 3: Implement `lan.py` additions**

Add `import io`, `import socket` and `from dataclasses import dataclass` to the imports, then append:

```python
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
    app = Flask(__name__)

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
```

- [ ] **Step 4: Implement `serve`**

In `humble_catalog/webapp/__init__.py`, add `import threading` and `import time` to the stdlib imports, and `from werkzeug.serving import make_server`. Replace `serve` with:

```python
def _run_all(servers):
    """Serve every server on its own thread until Ctrl-C, then stop all.

    Polled with sleep() rather than join(): on Windows a bare join() is not
    interrupted by Ctrl-C, so the process would ignore it.
    """
    threads = [threading.Thread(target=s.serve_forever, daemon=True)
               for s in servers]
    for t in threads:
        t.start()
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()


def serve(db_path="catalog.db", port=8087, lan=None):
    if lan is None:
        # Unchanged from before --lan existed.
        app = create_app(db_path=db_path)
        webbrowser.open(f"http://127.0.0.1:{port}/")
        app.run(host="127.0.0.1", port=port)
        return

    from humble_catalog import lan as lanmod
    lan_dir = lanmod.lan_dir_for(db_path)
    host = lan.host or lanmod.lan_address()
    lan_port = lan.port or port + 1
    token = (lanmod.rotate_token(lan_dir) if lan.new_token
             else lanmod.load_or_create_token(lan_dir))
    _ca_key, ca_cert = lanmod.ensure_ca(lan_dir)
    crt, key = lanmod.issue_server_cert(lan_dir, host)

    # Every server is built -- and so every port bound -- before any
    # starts, so a busy port stops the whole command rather than leaving
    # half of it running.
    wanted = [
        ("127.0.0.1", port, create_app(db_path=db_path), {}),
        (host, lan_port,
         create_lan_app(db_path=db_path, host=host, port=lan_port, token=token),
         {"ssl_context": lanmod.ssl_context(crt, key)}),
    ]
    if lan.setup:
        wanted.append((host, lan_port + 1, lanmod.ca_download_app(lan_dir), {}))
    servers = []
    for h, p, app, kw in wanted:
        try:
            servers.append(make_server(h, p, app, threaded=True, **kw))
        except OSError as exc:
            for s in servers:
                s.server_close()
            raise lanmod.LanStateError(
                f"cannot listen on {h}:{p} ({exc}) -- choose another port "
                "with --lan-port (or --port for the viewer itself)") from exc

    lanmod.print_instructions(
        f"https://{host}:{lan_port}/pair?token={token}",
        ca_url=f"http://{host}:{lan_port + 1}/ca.crt" if lan.setup else None,
        fingerprint=lanmod.ca_fingerprint(ca_cert) if lan.setup else None)
    webbrowser.open(f"http://127.0.0.1:{port}/")
    _run_all(servers)
```

- [ ] **Step 5: Implement the CLI flags**

In `humble_catalog/__main__.py`, after the `--port` argument (line 144), add:

```python
    p_serve.add_argument("--lan", action="store_true",
                         help="Also serve a read-only copy to paired devices "
                              "on your home network, over HTTPS")
    p_serve.add_argument("--lan-host", metavar="IP",
                         help="The LAN address to listen on (default: "
                              "detected)")
    p_serve.add_argument("--lan-port", type=int, metavar="N",
                         help="The LAN port (default: --port + 1)")
    p_serve.add_argument("--setup", action="store_true",
                         help="With --lan: also offer the certificate to "
                              "install on a phone, once")
    p_serve.add_argument("--new-token", action="store_true",
                         help="With --lan: replace the pairing token, "
                              "unpairing every device")
```

Replace the `serve` dispatch (lines 290-292) with:

```python
    elif args.command == "serve":
        from humble_catalog import webapp
        needs_lan = [flag for flag, given in (
            ("--lan-host", args.lan_host), ("--lan-port", args.lan_port),
            ("--setup", args.setup), ("--new-token", args.new_token)) if given]
        if needs_lan and not args.lan:
            parser.error(f"{', '.join(needs_lan)} needs --lan")
        if not args.lan:
            webapp.serve(port=args.port)
        else:
            from humble_catalog.lan import LanOptions, LanStateError
            try:
                webapp.serve(port=args.port, lan=LanOptions(
                    host=args.lan_host, port=args.lan_port,
                    setup=args.setup, new_token=args.new_token))
            except LanStateError as exc:
                sys.exit(f"serve --lan: {exc}")
```

`sys` is already imported at the top of `__main__.py` (line 3).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_lan.py tests/test_webapp.py tests/test_main.py -q`
Expected: all pass, including the unchanged `test_serve_uses_default_port` and `test_serve_accepts_a_port`.

- [ ] **Step 7: Commit**

```bash
git add humble_catalog/lan.py humble_catalog/webapp/__init__.py humble_catalog/__main__.py tests/test_lan.py tests/test_webapp.py tests/test_main.py
git commit -m "feat(lan): serve --lan runs the LAN app beside the loopback viewer

Detects the LAN address from the default route, binds every port before
starting any, and prints the pairing link as text and a QR code. --setup
adds a plain-HTTP listener offering only the CA certificate.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Read-only mode in the front end

**Files:**
- Modify: `humble_catalog/webapp/static/app.js:9` (state), `:28-60` (`load`)
- Modify: `humble_catalog/webapp/static/shell.js` (sections, boot, polling)
- Modify: `humble_catalog/webapp/static/catalog.js:169-184`, `:583-622`
- Modify: `humble_catalog/webapp/static/keys.js:114-118`
- Modify: `humble_catalog/webapp/static/style.css` (append)
- Modify: `tests/js/harness.mjs` (publish list)
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Consumes: `GET /api/status` → `read_only` (Task 1).
- Produces (JS globals):
  - `READ_ONLY` (bool, in `app.js`)
  - `applyMode(readOnly)`, `sectionAllowed(id)`, `READ_ONLY_SECTIONS` (in `shell.js`)
  - `statusCell(i)`, `nameExtras(i)` (in `catalog.js`)
  - Harness: `setReadOnly(v)`, `getReadOnly()`

- [ ] **Step 1: Publish the new bindings in the harness**

In `tests/js/harness.mjs`, inside the `publish` template, after `statusSelect, READ_STATUS_ORDER,` add:

```js
  statusCell, nameExtras, applyMode, sectionAllowed, READ_ONLY_SECTIONS,
  setReadOnly: (v) => { READ_ONLY = v; },
  getReadOnly: () => READ_ONLY,
```

- [ ] **Step 2: Write the failing tests** (append to `tests/test_webapp_js.py`)

```python
def _render_row(read_only, **overrides):
    item = json.dumps(_item(
        status="matched", edited=True, source_url="https://example.com/b",
        bundles=[{"name": "Bundle One", "url": "https://www.humblebundle.com/downloads?key=k1",
                  "purchased_at": "2020-01-01"}], **overrides))
    return eval_js(
        """(() => { app.setReadOnly(%s); app.setItems([%s]); dom.reset();
                    app.render(); return dom.writes["#catalog tbody"]; })()"""
        % ("true" if read_only else "false", item))


def test_read_only_rows_have_no_editing_controls():
    html = _render_row(True)
    assert "<select" not in html
    # data-n marks the clickable star widget; read-only stars are plain
    # text (class "star-text"), so matching on a class prefix would not do.
    for marker in ('class="edit"', 'class="redo"', 'class="revert"',
                   'class="override"', 'data-n="'):
        assert marker not in html, marker
    assert "★★★★" in html                      # the rating, as text
    assert "downloads?key=k1" in html          # the download link stays
    assert "Unread" in html                    # status as text


def test_the_full_viewer_still_renders_its_controls():
    html = _render_row(False)
    assert "<select" in html and 'class="edit"' in html


def test_read_only_mode_hides_the_write_sections():
    result = eval_js("""(() => {
        app.applyMode(true);
        return ["library", "maintenance", "keys", "bundles", "tasks"]
          .map((id) => document.querySelector("#tab-" + id).hidden);
      })()""")
    assert result == [False, True, False, True, True]


def test_a_bookmark_to_a_hidden_section_lands_on_library():
    assert eval_js("""(() => { app.applyMode(true);
        location.hash = "#/tasks"; return app.currentSection(); })()""") == "library"


def test_read_only_load_does_not_ask_for_write_only_data():
    urls = eval_js("""(async () => {
        const seen = [];
        app.setReadOnly(true);
        app.setFetch((url) => { seen.push(url); return Promise.resolve({
          json: () => Promise.resolve(
            url === "/api/items" ? {items: []} :
            url === "/api/stats" ? {total: 0, sections: []} :
            url === "/api/keys"  ? {rows: []} : {})}); });
        await app.load();
        return seen;
      })()""")
    assert "/api/review" not in urls and "/api/duplicates" not in urls
    assert "/api/jobs" not in urls


def test_read_only_keys_have_no_hide_button():
    # _with_keys (defined earlier in this file) loads the standard key
    # payload; the panel is rendered again once read-only mode is on.
    html = _with_keys(
        '(app.setReadOnly(true), app.renderKeys(), dom.writes["#keys-panel"])')
    assert "Amber Hollow" in html              # the rows still render
    assert "key-hide" not in html
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k "read_only or hidden_section or bookmark or full_viewer" -v`
Expected: FAIL with a harness `ReferenceError` (`statusCell is not defined`).

- [ ] **Step 4: Implement `app.js`**

After `let items = [];` (line 9) add:

```js
// True on the LAN viewer (serve --lan), set by shell.js from /api/status
// before load() runs. Every write route is ABSENT there, not merely
// refused, so this only decides what is worth drawing.
let READ_ONLY = false;
```

In `load()`, replace the `for (const step of [render, loadReview, ...])` line with:

```js
  // The LAN viewer has no /api/review, /api/duplicates or /api/jobs, so
  // their loaders would only log 404s.
  const steps = READ_ONLY
    ? [render, refreshStats, loadKeys]
    : [render, loadReview, loadDupes, refreshStats, loadKeys, renderTasks];
  for (const step of steps) {
```

- [ ] **Step 5: Implement `shell.js`**

After the `SECTIONS` array, add:

```js
// What the LAN viewer shows. Maintenance and Tasks are writes; Bundles is
// hidden too, because both previews are credentialed POSTs the LAN app
// does not have.
const READ_ONLY_SECTIONS = ["library", "keys"];
const sectionAllowed = (id) => !READ_ONLY || READ_ONLY_SECTIONS.includes(id);

function applyMode(readOnly) {
  READ_ONLY = readOnly === true;
  if (document.body) document.body.dataset.mode = READ_ONLY ? "read-only" : "full";
  for (const s of SECTIONS) {
    const tab = $(`#tab-${s.id}`);
    if (tab) tab.hidden = !sectionAllowed(s.id);
  }
}
```

In `currentSection` and `showSection`, replace both occurrences of `SECTIONS.some((s) => s.id === name)` with `SECTIONS.some((s) => s.id === name && sectionAllowed(s.id))`.

Replace the boot block at the bottom (from `showSection(currentSection());` through `syncThemeButton();`) with:

```js
// Boot. The mode has to be known before the first paint, or the LAN
// viewer would flash editing controls it cannot use.
async function boot() {
  let status = {};
  try {
    status = await (await fetch("/api/status")).json();
  } catch (err) {
    console.error("could not read /api/status:", err);
  }
  applyMode(status.read_only);
  showSection(currentSection());
  await load();
}
// One interval for both. pollStatus draws the header banner (which must
// keep working for a run started in a terminal); pollJobs draws the Tasks
// panel, which knows only about jobs this viewer started -- and which the
// LAN viewer does not have.
async function pollAll() {
  await pollStatus();
  if (READ_ONLY) return;
  try {
    await pollJobs();
  } catch (err) {
    console.error("pollJobs() failed:", err);
  }
}
boot();
pollAll();
setInterval(pollAll, 5000);
syncThemeButton();
```

- [ ] **Step 6: Implement `catalog.js`**

After `statusSelect` (line 176), add:

```js
// The status cell: a control on the full viewer, text on the LAN one.
function statusCell(i) {
  if (!READ_ONLY) return statusSelect(i);
  const cur = i.read_status || "unread";
  return `<span class="rs-text rs-${cur}">${READ_STATUS_LABEL[cur]}</span>`;
}
```

Replace `stars(item)` (lines 178-184) with:

```js
function stars(item) {
  // Read-only: plain text, with no data-id for the click handler to act on.
  if (READ_ONLY)
    return item.my_rating ? `<span class="star-text">${"★".repeat(item.my_rating)}</span>` : "";
  let html = "";
  for (let n = 1; n <= 5; n++)
    html += `<span class="star ${item.my_rating >= n ? "on" : ""}" `
          + `data-id="${item.id}" data-n="${n}">★</span>`;
  return html;
}
```

Above `function render()`, add `nameExtras`, which holds the name cell's trailing markup (moved from the row template, lines 584-610):

```js
// Everything after the title in the name cell. Read-only keeps only what
// navigates -- the source link and the edition jumps -- and drops the
// badges and buttons that exist to drive enrichment.
function nameExtras(i) {
  const src = i.source_url
    ? ` <a class="src-link" href="${esc(i.source_url)}" target="_blank"
         rel="noopener" title="Open source page">&#x2197;</a>` : "";
  // The key is absent on nearly every row, so the || [] is load-bearing
  // rather than defensive.
  const editions = (i.editions || []).map(o => ` <button class="badge edition edition-jump"
          data-name="${esc(o.name)}"
          title="The same work is in your library as ${esc(o.type)} -- click to go to it"
          >also as ${esc(o.type)}</button>`).join("");
  if (READ_ONLY) return src + editions;
  return src + `${
      i.status === "low_confidence" || i.status === "unmatched"
        ? ' <span class="badge">review</span>' : ""}${
      i.status === "matched" || i.status === "manually_fixed"
        ? ` <button class="redo" data-id="${i.id}" title="Redo this match">&#x27F3;</button>` : ""}
      <button class="edit" data-id="${i.id}" title="Edit fields">&#x270E;</button>${
      i.edited
        ? ` <span class="badge edited">edited</span>
            <button class="revert" data-id="${i.id}"
                    title="Revert to the enriched values">&#x21A9;</button>
            <button class="override" data-id="${i.id}"
                    title="${i.override
                      ? "Cancel the queued re-enrichment"
                      : "Let the next enrich run update this row"}">&#x21BB;</button>` : ""}${
      i.re_enriched
        ? ` <span class="badge">re-enriched</span>
            <button class="revert" data-id="${i.id}"
                    title="Revert to your edited values">&#x21A9;</button>` : ""}${
      i.override ? ' <span class="badge queued">re-enrich queued</span>' : ""}` + editions;
}
```

In `render()`'s non-editing row template, replace the second `<td>` (lines 584-610, from `<td><strong>${highlight(` through `.join("")}</td>`) with:

```js
    <td><strong>${highlight(i.name, matchSpans.get(i.id))}</strong>${nameExtras(i)}</td>
```

In the same template, replace `<td>${statusSelect(i)}</td>` (line 612) with `<td>${statusCell(i)}</td>`. Leave the editing-row template (line 566) on `statusSelect`: a row can only be in edit mode on the full viewer.

- [ ] **Step 7: Implement `keys.js`**

Replace the hide cell (lines 114-118) with:

```js
      <td class="key-hide-cell">${
        r.hidden_at ? esc(r.hidden_at.slice(0, 10)) + " " : ""}${READ_ONLY ? "" : `<button
        class="key-hide" data-gamekey="${esc(r.gamekey)}"
        data-machine="${esc(r.machine_name)}">${
        r.hidden_at ? "unhide" : "hide"}</button>`}</td>
```

- [ ] **Step 8: Hide the toolbar controls in CSS** (append to `style.css`)

```css
/* The LAN viewer (serve --lan): the routes behind these are absent, so
   the controls are not worth drawing. */
body[data-mode="read-only"] #bulk-bar,
body[data-mode="read-only"] #export,
body[data-mode="read-only"] #export-format,
body[data-mode="read-only"] #column-picker { display: none; }
.star-text { color: var(--star); }
```

- [ ] **Step 9: Run the JS and web tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py tests/test_webapp.py -q`
Expected: all pass. If an existing test asserted on the exact name-cell markup and now fails, the moved markup in `nameExtras` must be byte-for-byte what the template had; diff it against `git show HEAD:humble_catalog/webapp/static/catalog.js` rather than editing the test.

- [ ] **Step 10: Commit**

```bash
git add humble_catalog/webapp/static tests/js/harness.mjs tests/test_webapp_js.py
git commit -m "feat(viewer): a read-only mode driven by /api/status

The LAN viewer shows only Library and Keys, renders status and rating as
text, and draws no edit, enrichment, bulk-tag, export or hide controls.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: The card list below 600 px

**Files:**
- Modify: `humble_catalog/webapp/static/catalog.js` (`render`, new `renderCards`, `isNarrow`)
- Modify: `humble_catalog/webapp/static/shell.js` (re-render on width change)
- Modify: `humble_catalog/webapp/static/index.html:126` (after `#table-wrap` closes)
- Modify: `humble_catalog/webapp/static/style.css` (append)
- Modify: `tests/js/harness.mjs`
- Test: `tests/test_webapp_js.py`

**Interfaces:**
- Produces: `NARROW_QUERY = "(max-width: 600px)"`, `isNarrow() -> bool`, `renderCards(rows) -> string` (all in `catalog.js`).

- [ ] **Step 1: Publish the bindings**

In `tests/js/harness.mjs`'s `publish` list, after the line added in Task 6, add:

```js
  renderCards, isNarrow, NARROW_QUERY,
```

- [ ] **Step 2: Write the failing tests** (append to `tests/test_webapp_js.py`)

```python
def test_cards_carry_the_title_series_and_download_link():
    item = json.dumps(_item(
        name="The Quiet Harbor: A Novel", series="Harbor Tales", series_number=2,
        my_rating=4, formats=["epub", "pdf"],
        bundles=[{"name": "Bundle One", "url": "https://www.humblebundle.com/downloads?key=k1",
                  "purchased_at": "2020-01-01"}]))
    html = eval_js(f"app.renderCards([{item}])")
    assert html.count('<article class="card"') == 1
    assert "The Quiet Harbor: A Novel" in html
    assert "Harbor Tales #2" in html
    assert 'class="card-link" href="https://www.humblebundle.com/downloads?key=k1"' in html
    assert "★★★★" in html and "epub, pdf" in html


def test_cards_survive_missing_fields():
    # Same tolerance tagBadges and person have: an older server or a partial
    # payload must not blank the page.
    item = json.dumps(_item(bundles=None, authors=None, user_tags=None,
                            formats=None, read_status=None))
    assert eval_js(f"app.renderCards([{item}])").count('<article class="card"') == 1


def test_a_narrow_screen_renders_cards_instead_of_the_table():
    result = eval_js("""(() => {
        globalThis.matchMedia = () => ({matches: true, addEventListener() {}});
        app.setItems([%s]); dom.reset(); app.render();
        return {cards: dom.writes["#card-list"] || "",
                table: dom.writes["#catalog tbody"] || "",
                tableHidden: document.querySelector("#table-wrap").hidden,
                cardsHidden: document.querySelector("#card-list").hidden};
      })()""" % json.dumps(_item()))
    assert '<article class="card"' in result["cards"]
    assert result["table"] == ""
    assert result["tableHidden"] is True and result["cardsHidden"] is False


def test_a_wide_screen_keeps_the_table():
    result = eval_js("""(() => {
        app.setItems([%s]); dom.reset(); app.render();
        return {table: dom.writes["#catalog tbody"] || "",
                cardsHidden: document.querySelector("#card-list").hidden};
      })()""" % json.dumps(_item()))
    assert "<tr>" in result["table"] and result["cardsHidden"] is True
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py -k "card or narrow or wide" -v`
Expected: FAIL with `ReferenceError: renderCards is not defined`.

- [ ] **Step 4: Implement `catalog.js`**

Above `function render()` add:

```js
// Below this width the 22-column table is unusable (measured at 375 px:
// 1,477 px wide, bundle links off-screen), so each row becomes a card.
const NARROW_QUERY = "(max-width: 600px)";
const isNarrow = () =>
  typeof matchMedia === "function" && matchMedia(NARROW_QUERY).matches;

// Display-only on every viewer: editing needs the table's width. Every
// field is guarded the way tagBadges and person are, so a partial payload
// renders a thinner card instead of throwing.
function renderCards(rows) {
  return rows.map((i) => {
    const status = READ_STATUS_LABEL[i.read_status || "unread"] || "";
    const series = i.series
      ? ` · ${esc(i.series)}${i.series_number ? " #" + i.series_number : ""}` : "";
    const rating = i.my_rating ? ` · ${"★".repeat(i.my_rating)}` : "";
    const tags = (i.user_tags || []).length ? ` · ${esc(i.user_tags.join(", "))}` : "";
    return `<article class="card">
    ${i.cover_path
      ? `<img class="card-cover" src="/${i.cover_path}" alt="" loading="lazy">`
      : `<div class="card-cover"></div>`}
    <div class="card-body">
      <strong class="card-title">${highlight(i.name, matchSpans.get(i.id))}</strong>
      <div class="card-meta">${esc((i.authors || []).join(", "))}${series}</div>
      <div class="card-meta"><span class="tag">${esc(i.type)}</span> ${esc((i.formats || []).join(", "))}</div>
      <div class="card-meta">${status}${rating}${tags}</div>
      <div class="card-links">${(i.bundles || []).map((b) =>
        `<a class="card-link" href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.name)}</a>`
      ).join("")}</div>
    </div>
  </article>`;
  }).join("");
}
```

In `render()`, replace the statement `$("#catalog tbody").innerHTML = rows.map(...).join("");` with the same statement wrapped:

```js
  const narrow = isNarrow();
  $("#table-wrap").hidden = narrow;
  $("#card-list").hidden = !narrow;
  if (narrow) {
    $("#catalog tbody").innerHTML = "";
    $("#card-list").innerHTML = renderCards(rows);
  } else {
    $("#card-list").innerHTML = "";
    $("#catalog tbody").innerHTML = rows.map(/* unchanged row templates */).join("");
  }
```

`/* unchanged row templates */` means the existing arrow function (`i => i.id === editingId ? … : …`) moved in exactly as it is. The template itself is not rewritten.

- [ ] **Step 5: Implement `shell.js`**

Before `boot();`, add:

```js
// Re-render when the width crosses the card breakpoint, e.g. a phone
// rotated to landscape.
if (typeof matchMedia === "function")
  matchMedia(NARROW_QUERY).addEventListener("change", () => render());
```

- [ ] **Step 6: Implement `index.html`**

After the `</div>` that closes `#table-wrap` (line 126, directly after `</table>`), add:

```html
  <div id="card-list" hidden></div>
```

- [ ] **Step 7: Implement the CSS** (append to `style.css`)

```css
/* Card list (below 600 px). :not([hidden]) because a display rule would
   otherwise override the hidden attribute. */
#card-list:not([hidden]) { display: grid; gap: .6rem; padding: .5rem 0; }
.card { display: flex; gap: .7rem; background: var(--surface);
        border: 1px solid var(--border); border-radius: 6px; padding: .6rem; }
.card-cover { width: 56px; flex: none; border-radius: 3px; }
.card-body { flex: 1; min-width: 0; }
.card-title { display: block; overflow-wrap: anywhere; }
.card-meta { font-size: .85rem; color: var(--muted); margin-top: .2rem; }
.card-links { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .4rem; }
/* 44 px: the smallest comfortable touch target. */
.card-link { display: inline-flex; align-items: center; min-height: 44px;
             box-sizing: border-box; padding: .4rem .7rem; border-radius: 4px;
             background: var(--surface-alt); color: var(--accent);
             text-decoration: none; }
@media (max-width: 600px) {
  /* Measured at 375 px: Bundles was cut in half and Tasks off-screen. */
  #tabs { overflow-x: auto; }
  #tabs a { flex: none; white-space: nowrap; }
}
```

- [ ] **Step 8: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/test_webapp_js.py tests/test_webapp.py -q`
Expected: all pass.

- [ ] **Step 9: Visual check on the demo catalog (never the real one)**

Start the demo server with the preview tool (`preview_start` name `catalog-viewer-demo`, port 8099). Resize to the `mobile` preset (375×812), open `http://localhost:8099/#/library`, and take a screenshot. Check that cards fill the width, there's no horizontal page scroll, each card shows its bundle link as a button, and the tab bar scrolls rather than clipping. Then force read-only rendering in the page (`applyMode(true); render();`) and screenshot again: only Library and Keys show, and there are no toolbar or bulk controls. Reset the viewport to `desktop` and stop the server. The demo catalog holds only invented titles. Still review both screenshots by eye before sharing them, and do not commit them.

- [ ] **Step 10: Commit**

```bash
git add humble_catalog/webapp/static tests/js/harness.mjs tests/test_webapp_js.py
git commit -m "feat(viewer): a card list below 600 px

At 375 px the table was 1,477 px wide with the bundle links off-screen.
Cards carry the cover, title, authors and series, status, rating and
each bundle's download link as a touch target. The tab bar scrolls.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation, and the final gate

**Files:**
- Modify: `README.md` (new "Viewing on your phone" section; "The viewer's exposure")
- Modify: `CLAUDE.md` (privacy bullets)
- Modify: `docs/BACKLOG.md` (Done entry)

- [ ] **Step 1: README: add a section before "The viewer's exposure"**

```markdown
### Viewing on your phone

`python -m humble_catalog serve --lan` also serves a **read-only** copy of
the viewer to your home network, over HTTPS. Phones see Library and Keys,
can search and filter, and can follow each item's bundle link to its
Humble download page. Nothing can be edited from the phone, and on a
narrow screen each item is a card rather than a table row.

**Once:** run `serve --lan --setup`. It prints a link and a QR code for a
certificate. Open it on the phone, then install it under Settings →
Security → Encryption & credentials → Install a certificate → CA
certificate. Compare the SHA-256 fingerprint shown under Trusted
credentials → User with the one printed in the terminal.

**Each device:** open the pairing link `serve --lan` prints (or scan its
QR code). The phone stays paired until you run
`serve --lan --new-token`, which unpairs every device.

The pairing link is a password to your catalog: never paste it anywhere.
Everything `--lan` keeps is in a `lan/` folder next to `catalog.db`;
delete that folder to start over, then run `--setup` again and reinstall
the certificate. Use `--lan-host` if the address it picks is wrong and
`--lan-port` if the port is taken. Editing needs the full viewer on the
PC in a window wider than 600 px.
```

- [ ] **Step 2: README: append to "The viewer's exposure"**

```markdown
`serve --lan` adds a second server on your LAN address. It is bounded by
four things. It is a separate app that **has** no write routes, rather
than one that refuses them, and a test pins the exact list it serves. It
answers only requests addressed to its own LAN address, which refuses DNS
rebinding the same way the loopback check does. Every request needs the
pairing cookie. And it is HTTPS from a certificate authority that is
constrained to private addresses, so even a leaked `lan/ca.key` could not
impersonate a real website. A paired device can read the whole catalog,
order keys included, for as long as `--lan` runs.
```

- [ ] **Step 3: CLAUDE.md**

In the list of never-committed paths in the first Privacy bullet, add `lan/`:

```markdown
- Never commit `catalog.db*`, `Reference spreadsheets/`, `covers/`,
  `cache/`, `lan/`, or any export of the catalog. They are gitignored; never
  weaken those rules or force-add them.
```

After the `harvest --failures` bullet, add:

```markdown
- **The pairing link `serve --lan` prints is a credential.** Anyone
  holding it can read the whole catalog from the home network. Like
  `harvest --failures`, it is terminal output nothing scans: never paste
  it into a commit, doc, issue or screenshot.
```

- [ ] **Step 4: BACKLOG Done entry** (top of the Done list)

```markdown
- **A read-only LAN viewer for phones (#6, piece 1)** —
  `superpowers/specs/2026-09-18-lan-viewer-design.md`.
  `serve --lan` runs a second Flask app beside the loopback viewer, built
  from the read route group only, so its write routes are absent rather
  than refused. Phones pair with a token link exchanged for a
  `SameSite=Strict` cookie, over HTTPS from a local certificate authority
  installed once.

  **Two spec corrections made while planning.** Name constraints listing
  only IP ranges leave DNS names unconstrained under RFC 5280, so the
  authority also permits only the reserved name `invalid`. And `/pair`
  answers a self-refreshing page rather than a 303, because a link opened
  from a QR scanner may lose a `Strict` cookie on the redirect.

  #6 stays open for the native app, to be revisited once this has been
  used.
```

- [ ] **Step 5: Final gate**

Run each as its own command, and read each result before continuing:

```bash
.venv/Scripts/python -m pytest -q
```
Expected: all pass.

```bash
.venv/Scripts/python scripts/leak_check.py
```
Expected: `clean`.

```bash
.venv/Scripts/python scripts/check_no_data_tracked.py
```
Expected: `clean`.

```bash
git status --short
```
Expected: no `lan/` path listed, even after the Task 7 visual check. If one shows, stop: `.gitignore` is not covering it.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md docs/BACKLOG.md
git commit -m "docs: viewing the catalog on a phone with serve --lan

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
