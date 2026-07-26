"""Run the viewer's JavaScript for real, instead of grepping app.js.

The other JS tests in this suite are text assertions: they pin that code
exists, not that it behaves. That gap let a regression through once --
`tagBadges` threw on a missing field and blanked the whole page while
every text assertion still passed.

Node is optional. Without it these tests skip, so the suite still runs on
a machine that only has Python.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_HARNESS = Path(__file__).parent / "js" / "harness.mjs"
_APP_JS = _ROOT / "humble_catalog" / "webapp" / "static" / "app.js"


def eval_js(expression):
    """Evaluate `expression` with app.js loaded in a stubbed DOM.

    `app` holds app.js's top-level bindings (plus setItems/getItems/
    setFetch to drive state); `dom` records innerHTML writes by selector,
    so a test can ask which renderers actually ran. The expression is
    awaited, so it may be async. Returns the JSON-decoded result.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed; JS behaviour tests skipped")
    # encoding is explicit: text=True alone decodes with the locale
    # codepage, which on Windows is cp1252, and Node writes UTF-8. That
    # silently mangled every non-ASCII character -- a euro sign came back
    # as its own trailing byte -- so no test could assert on rendered
    # currency, punctuation or an accented title.
    proc = subprocess.run(
        [node, str(_HARNESS), str(_APP_JS), expression],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    if proc.returncode != 0:
        raise AssertionError(
            f"JS harness failed:\n{proc.stderr.strip()}")
    return json.loads(proc.stdout)


def eval_js_error(expression):
    """Return the error message `expression` throws, or None if it doesn't.

    Lets a test assert that something no longer throws without the harness
    itself failing when it still does.
    """
    return eval_js(
        "(async () => { try { await (%s); return null; }"
        " catch (e) { return e.constructor.name + ': ' + e.message; } })()"
        % expression)
