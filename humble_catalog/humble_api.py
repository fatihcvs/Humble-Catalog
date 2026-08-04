import subprocess
import time
from pathlib import Path
import requests
from humble_catalog.shapes import as_mapping, as_text

BASE = "https://www.humblebundle.com"
UA = {"User-Agent": "HumbleCatalog/1.0"}

class NotLoggedIn(Exception):
    pass

class MalformedOrderList(ValueError):
    """The order index came back in a shape this client cannot read.

    Distinct from NotLoggedIn on purpose: a session problem is something
    the user fixes by logging in again, and `ensure_login` acts on it,
    while this says the endpoint answered with something else entirely
    and re-logging in would not help.
    """

class HumbleClient:
    def __init__(self, cookies, delay=4.0, http=None):
        self.delay = delay
        self._last = None
        if http is None:
            http = requests.Session()
            http.headers.update(UA)
            for name, value in cookies.items():
                http.cookies.set(name, value, domain="www.humblebundle.com")
        self.http = http

    def _wait(self):
        """Hold off until `delay` has passed since the last request.

        Shared by _get and get_page so politeness toward Humble is a
        property of the client rather than something each caller
        remembers.
        """
        if self._last is not None:
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)

    def _get(self, path, **kwargs):
        self._wait()
        resp = self.http.get(f"{BASE}{path}", timeout=30, **kwargs)
        self._last = time.monotonic()
        if resp.status_code != 200 or "json" not in resp.headers.get("Content-Type", ""):
            raise NotLoggedIn(f"GET {path} -> {resp.status_code}")
        return resp.json()

    def get_page(self, path):
        """The HTML body of a page on the Humble site.

        The HTML sibling of _get, for the one page whose data is embedded
        in markup rather than served as JSON. It cannot check the content
        type the way _get does -- HTML is the expected answer -- so a
        non-200 is the only signal available here; a signed-out session is
        caught by logged_in() before this is ever called.
        """
        self._wait()
        resp = self.http.get(f"{BASE}{path}", timeout=30)
        self._last = time.monotonic()
        if resp.status_code != 200:
            raise NotLoggedIn(f"GET {path} -> {resp.status_code}")
        return resp.text

    def logged_in(self):
        try:
            self._get("/api/v1/user/order")
            return True
        except NotLoggedIn:
            return False

    def list_order_keys(self):
        """Every order key the account owns.

        One malformed entry is skipped rather than raised on: this is the
        index of the whole library, so failing here costs every bundle,
        not one. That is a different granularity from parse_order, which
        refuses a single order missing a required field and is right to.

        A payload that is not a list at all, or one whose every entry is
        unusable, does raise. Returning [] there would report an empty
        library, and a harvest would then do nothing and call it success -
        the silent-wrong-answer failure this project prefers to avoid.
        """
        orders = self._get("/api/v1/user/order")
        if not isinstance(orders, list):
            raise MalformedOrderList(
                f"GET /api/v1/user/order returned {type(orders).__name__}, "
                f"not a list of orders")
        keys = [key for key in
                (as_text(as_mapping(o).get("gamekey")) for o in orders) if key]
        if orders and not keys:
            raise MalformedOrderList(
                f"GET /api/v1/user/order returned {len(orders)} order(s), "
                f"none carrying a usable gamekey")
        return keys

    def get_order(self, gamekey):
        # all_tpkds=true is required or the API omits external keys
        # (Steam keys, DriveThruRPG/Roll20 redemption links) entirely.
        return self._get(f"/api/v1/order/{gamekey}", params={"all_tpkds": "true"})

def get_cookies(profile_dir=".playwright-profile"):
    """Read the saved session cookies from the persistent profile (headless)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile_dir, headless=True)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(f"{BASE}/home/library", wait_until="domcontentloaded")
            return {c["name"]: c["value"] for c in ctx.cookies()}
        finally:
            ctx.close()

def manual_login(profile_dir=".playwright-profile"):
    """Open a plain, NON-automated browser for the user to log in.

    Google refuses sign-in inside automation-controlled browsers ("This
    browser or app may not be secure"), so the login window must be a normal
    subprocess launch of the same Chromium binary on the same profile - no
    DevTools connection, nothing for Google to detect. The session it saves
    is then reused by the automated headless runs."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = p.chromium.executable_path
    print("A normal (non-automated) browser window is opening.")
    print("  1. Log in to HumbleBundle there - Google + TFA works normally.")
    print("  2. When you can see your Humble library, CLOSE the browser window.")
    proc = subprocess.Popen(
        [exe, f"--user-data-dir={Path(profile_dir).resolve()}",
         "--no-first-run", "--no-default-browser-check",
         f"{BASE}/login?goto=/home/library"])
    proc.wait()

def ensure_login(profile_dir=".playwright-profile", allow_login=True):
    client = HumbleClient(get_cookies(profile_dir))
    if client.logged_in():
        return client
    if not allow_login:
        # The viewer's job runner passes allow_login=False. manual_login
        # opens a browser window and then blocks on proc.wait(), which a
        # background child process can neither show nor explain -- it would
        # read as a slow fetch that never ends. Failing here lets the page
        # say "session expired" and offer the terminal handoff instead.
        # Same rule /api/choice-preview already follows.
        raise NotLoggedIn("HumbleBundle session missing or expired")
    print("HumbleBundle session missing or expired.")
    manual_login(profile_dir)
    client = HumbleClient(get_cookies(profile_dir))
    if not client.logged_in():
        raise SystemExit(
            "Still not logged in. Re-run this command and make sure you reach "
            "your Humble library page before closing the browser window.")
    print("Login saved. Future runs will not need this step.")
    return client
