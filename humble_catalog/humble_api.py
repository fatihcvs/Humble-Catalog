import subprocess
import time
from pathlib import Path
import requests

BASE = "https://www.humblebundle.com"
UA = {"User-Agent": "HumbleCatalog/1.0"}

class NotLoggedIn(Exception):
    pass

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

    def _get(self, path, **kwargs):
        if self._last is not None:
            wait = self._last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        resp = self.http.get(f"{BASE}{path}", timeout=30, **kwargs)
        self._last = time.monotonic()
        if resp.status_code != 200 or "json" not in resp.headers.get("Content-Type", ""):
            raise NotLoggedIn(f"GET {path} -> {resp.status_code}")
        return resp.json()

    def logged_in(self):
        try:
            self._get("/api/v1/user/order")
            return True
        except NotLoggedIn:
            return False

    def list_order_keys(self):
        return [o["gamekey"] for o in self._get("/api/v1/user/order")]

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

def ensure_login(profile_dir=".playwright-profile"):
    client = HumbleClient(get_cookies(profile_dir))
    if client.logged_in():
        return client
    print("HumbleBundle session missing or expired.")
    manual_login(profile_dir)
    client = HumbleClient(get_cookies(profile_dir))
    if not client.logged_in():
        raise SystemExit(
            "Still not logged in. Re-run this command and make sure you reach "
            "your Humble library page before closing the browser window.")
    print("Login saved. Future runs will not need this step.")
    return client
