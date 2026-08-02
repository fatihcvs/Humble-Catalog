"""Known-answer battery for the js-shell inventory row.

Covers `shell.js` and `app.js`'s bootstrap: `SECTIONS`, `currentSection`,
`showSection`, `badgeCount` and `renderBadges`, run for real in Node.

The routing rule worth pinning is a refusal to be helpful: an unknown
hash falls back to Library WITHOUT rewriting the URL, because a silent
rewrite would erase the evidence that a bookmark went stale. That is
exactly the kind of decision a later "tidy-up" reverses, and nothing else
in the suite would notice.

One Node process for the whole battery.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tests.js_harness import eval_js  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def batch():
    hashes = ["", "#/library", "#/maintenance", "#/keys", "#/bundles",
              "#/nosuchsection", "#library", "#/LIBRARY", "#/", "garbage"]
    blocks = "".join(
        "{ location.hash = %s;"
        " out.cur[%s] = app.currentSection();"
        " out.after[%s] = location.hash; }"
        % (json.dumps(h), json.dumps(h), json.dumps(h))
        for h in hashes)
    expr = (
        "(() => { const out = {cur: {}, after: {}, hidden: {}, aria: {}};"
        " out.sections = app.SECTIONS.map(s => s.id);"
        " out.labels = app.SECTIONS.map(s => s.label);"
        " %s"
        # showSection's effect on each panel, for a known and an unknown name
        " for (const name of ['keys', 'nosuchsection']) {"
        "   app.showSection(name);"
        "   out.hidden[name] = app.SECTIONS.map("
        "     s => document.querySelector('#section-' + s.id).hidden);"
        "   out.aria[name] = app.SECTIONS.map("
        "     s => document.querySelector('#tab-' + s.id)"
        "            .getAttribute('aria-current')); }"
        # badge counts
        " app.setPending({maintenance: 3, keys: 0, bundles: 7, library: 99});"
        " out.badges = app.SECTIONS.map(s => app.badgeCount(s.id));"
        " app.renderBadges();"
        " out.badge_text = app.SECTIONS.map("
        "   s => dom.writes['#tab-' + s.id + ' .badge-count:text']);"
        " app.setPending({maintenance: 0, bundles: 0});"
        " app.renderBadges();"
        " out.badge_cleared = app.SECTIONS.map("
        "   s => dom.writes['#tab-' + s.id + ' .badge-count:text']);"
        " return out; })()" % blocks)
    return eval_js(expr)


R = batch()


# --------------------------------------------------------------- sections

def case_the_four_sections_are_declared_in_order():
    check("the tab order is the declared order", R["sections"],
          ["library", "maintenance", "keys", "bundles"])
    check("and each carries a label",
          all(bool(x) for x in R["labels"]), True)


# ---------------------------------------------------------------- routing

def case_a_known_hash_selects_its_section():
    for name in ["library", "maintenance", "keys", "bundles"]:
        check(f"#/{name} routes to {name}", R["cur"][f"#/{name}"], name)


def case_an_empty_hash_is_the_library():
    check("no hash is the default section", R["cur"][""], "library")


def case_an_unknown_hash_falls_back_to_the_library():
    for bad in ["#/nosuchsection", "garbage", "#/"]:
        check(f"{bad!r} falls back to library", R["cur"][bad], "library")


def case_the_hash_form_is_exact():
    # `#library` without the slash is not the route; the prefix stripped
    # is `#/`, so anything else is an unknown hash.
    check("#library without the slash is not a route",
          R["cur"]["#library"], "library")
    check("and the route is case-sensitive",
          R["cur"]["#/LIBRARY"], "library")


def case_a_stale_bookmark_is_not_silently_rewritten():
    """The documented refusal, and the reason this row is worth sweeping.

    An unknown hash falls back to Library WITHOUT rewriting the URL: a
    silent rewrite would erase the evidence that a bookmark went stale.
    """
    for bad in ["#/nosuchsection", "garbage", "#/LIBRARY"]:
        check(f"{bad!r} is left in the address bar untouched",
              R["after"][bad], bad)


# ------------------------------------------------------------ showSection

def case_showing_a_section_hides_exactly_the_others():
    # SECTIONS order is library, maintenance, keys, bundles.
    check("only the keys panel is visible",
          R["hidden"]["keys"], [True, True, False, True])


def case_showing_an_unknown_section_shows_the_library():
    check("an unknown name falls back to the library panel",
          R["hidden"]["nosuchsection"], [False, True, True, True])


def case_the_active_tab_is_marked_for_assistive_tech():
    # aria-current="page" on the active tab and "false" elsewhere: the
    # only signal a screen reader gets about which section is showing.
    check("the keys tab is marked current",
          R["aria"]["keys"], ["false", "false", "page", "false"])
    check("and the fallback marks the library tab",
          R["aria"]["nosuchsection"], ["page", "false", "false", "false"])


def case_exactly_one_tab_is_ever_current():
    for name, values in R["aria"].items():
        check(f"one tab is current for {name}",
              values.count("page"), 1)


# ----------------------------------------------------------------- badges

def case_the_library_never_carries_a_badge():
    # Documented: the library is where you already are, so a count there
    # would be a number with nothing to click towards.
    check("library's badge count is always zero", R["badges"][0], 0)


def case_a_section_badge_reports_its_pending_count():
    check("maintenance and bundles carry their counts",
          [R["badges"][1], R["badges"][3]], [3, 7])


def case_a_zero_badge_renders_as_empty_rather_than_zero():
    check("a zero count writes an empty string, not '0'",
          R["badge_text"][2], "")
    check("while a non-zero count writes the number",
          R["badge_text"][1], "3")


def case_a_badge_clears_when_its_work_is_done():
    check("every badge is empty once nothing is pending",
          R["badge_cleared"], ["", "", "", ""])


def case_the_library_badge_ignores_a_pending_count_set_for_it():
    # setPending wrote library: 99 above; badgeCount must still answer 0.
    check("a pending count for the library is not rendered",
          R["badge_text"][0], "")


CASES = [v for k, v in sorted(globals().items()) if k.startswith("case_")]

if __name__ == "__main__":
    for fn in CASES:
        try:
            fn()
        except Exception as exc:                            # noqa: BLE001
            FAIL.append(fn.__name__)
            print(f"  FAIL {fn.__name__} raised: "
                  f"{type(exc).__name__}: {exc}")
    total = len(PASS) + len(FAIL)
    print(f"js-shell: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
