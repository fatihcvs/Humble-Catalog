"""Known-answer battery for the viewer-markup inventory row.

Covers `humble_catalog/webapp/static/index.html` and `style.css` - the
document structure and the accessibility affordances.

The cases that earn this row are CROSS-FILE. The JavaScript writes into
selectors the HTML must provide, and a selector that does not exist fails
in the quietest way there is: `document.querySelector` returns null, the
renderer throws or writes nowhere, and every test that checks the JS in
isolation still passes. So the battery reads the ids the scripts actually
query and asserts the markup provides them, and reads the section ids the
shell routes between and asserts each has both a tab and a panel.

The remaining cases are the accessibility affordances a screen reader
depends on: a language, a document title, landmarks, and an accessible
name on every control that has no visible label.

No harness and no Node: this row is text, and reading it as text is the
honest instrument.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
STATIC = ROOT / "humble_catalog" / "webapp" / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


def ids_in_html():
    return set(re.findall(r'id="([^"]+)"', HTML))


def script_text():
    return "\n".join(p.read_text(encoding="utf-8")
                     for p in sorted(STATIC.glob("*.js")))


IDS = ids_in_html()
JS = script_text()

# Section ids the shell routes between, read from shell.js rather than
# retyped, so adding a section to one file and not the other fails here.
SECTION_IDS = re.findall(r'\{id:\s*"([a-z]+)"', JS)


# ------------------------------------------------------------- the document

def case_the_document_declares_a_language():
    # Without it a screen reader guesses, and guesses wrong on a catalog
    # full of proper nouns.
    check("html carries a lang attribute", 'lang="en"' in HTML, True)


def case_the_document_has_a_title():
    check("a title element is present and non-empty",
          bool(re.search(r"<title>\s*\S[^<]*</title>", HTML)), True)


def case_the_page_has_exactly_one_top_level_heading():
    check("one h1", len(re.findall(r"<h1[\s>]", HTML)), 1)


def case_the_landmarks_are_present():
    for tag in ["<nav", "<main", "<aside"]:
        check(f"{tag} landmark exists", tag in HTML, True)


def case_each_landmark_that_repeats_carries_a_name():
    # nav and aside are the two that can appear more than once and need
    # distinguishing; both are labelled.
    check("the tab strip is named",
          'id="tabs" aria-label="Sections"' in HTML, True)
    check("the filter sidebar is named",
          'id="filters" aria-label="Filters"' in HTML, True)


# ----------------------------------------------------- the section wiring

def case_the_shell_declares_the_sections_this_markup_serves():
    check("four sections are declared in the shell",
          SECTION_IDS, ["library", "maintenance", "keys", "bundles"])


def case_every_section_has_a_tab_and_a_panel():
    """The cross-file invariant.

    `showSection` queries `#tab-<id>` and `#section-<id>` for every entry
    in SECTIONS. A missing one is not an error: querySelector answers
    null, the code guards it, and the tab silently never activates.
    """
    for section in SECTION_IDS:
        check(f"#tab-{section} exists", f"tab-{section}" in IDS, True)
        check(f"#section-{section} exists", f"section-{section}" in IDS, True)


def case_every_tab_carries_a_badge_slot():
    # renderBadges writes into `#tab-<id> .badge-count`; a tab without the
    # span drops its count with no error.
    for section in SECTION_IDS:
        pattern = rf'id="tab-{section}"[^>]*>.*?class="badge-count"'
        check(f"the {section} tab has a badge slot",
              bool(re.search(pattern, HTML, re.S)), True)


def case_every_tab_links_to_its_route():
    for section in SECTION_IDS:
        check(f"the {section} tab is a real link to its hash",
              f'href="#/{section}"' in HTML, True)


def case_every_panel_starts_hidden():
    # showSection reveals exactly one; a panel that started visible would
    # render two sections at once on first paint.
    for section in SECTION_IDS:
        pattern = rf'id="section-{section}"[^>]*hidden'
        check(f"the {section} panel starts hidden",
              bool(re.search(pattern, HTML)), True)


# ------------------------------------------------- the selectors JS needs

def case_every_id_the_scripts_query_exists_in_the_markup():
    """The other half of the cross-file check.

    Any `$("#foo")` in the viewer's scripts must find something. A stale
    selector returns null and the write goes nowhere - the quietest
    possible failure, and invisible to every test that checks the scripts
    in isolation.

    Ids built by string interpolation are excluded: they are covered by
    the per-section cases above, which know what the parts expand to.
    """
    queried = set(re.findall(r'\$\("#([a-zA-Z0-9_-]+)"\)', JS))
    queried |= set(re.findall(r'querySelector\("#([a-zA-Z0-9_-]+)"\)', JS))
    missing = sorted(q for q in queried if q not in IDS)
    check("no script queries an id the markup does not provide",
          missing, [])


def case_the_scripts_query_something_at_all():
    # Guards the case above from passing vacuously if the regex ever
    # stops matching the codebase's style.
    queried = set(re.findall(r'\$\("#([a-zA-Z0-9_-]+)"\)', JS))
    check("the selector scan found real selectors", len(queried) > 10, True)


# ---------------------------------------------------------- form controls

def case_every_form_control_has_an_accessible_name():
    """A select or input with neither a label nor an aria-label is
    announced as its type alone - "combo box" - which tells the user
    nothing about what it filters."""
    labelled_for = set(re.findall(r'<label[^>]*for="([^"]+)"', HTML))
    unnamed = []
    for tag in re.findall(r"<(?:select|input|textarea)\b[^>]*>", HTML):
        if "type=\"hidden\"" in tag:
            continue
        el_id = re.search(r'id="([^"]+)"', tag)
        has_label = el_id and el_id.group(1) in labelled_for
        has_aria = "aria-label" in tag or "aria-labelledby" in tag
        has_placeholder_only = "placeholder=" in tag and not has_aria
        if not (has_label or has_aria):
            unnamed.append((el_id.group(1) if el_id else tag[:60],
                            "placeholder only" if has_placeholder_only
                            else "no name"))
    check("every control carries a name", unnamed, [])


def case_the_search_box_is_labelled_by_a_visible_label():
    check("search has a real label element",
          'for="search"' in HTML, True)


def case_the_theme_toggle_is_named():
    # A button whose only content is a glyph needs one, or it is
    # announced as the glyph.
    check("the theme button carries an aria-label",
          'aria-label="Toggle light/dark theme"' in HTML, True)


def case_the_sidebar_toggle_announces_its_state():
    # aria-expanded is what tells a screen reader the panel collapsed;
    # aria-controls is what says which panel.
    check("the filters toggle declares what it controls",
          'aria-controls="filters"' in HTML, True)
    check("and whether it is open", 'aria-expanded=' in HTML, True)


# ------------------------------------------------------------------- css

def case_the_stylesheet_supports_both_colour_schemes():
    check("a dark scheme is defined",
          "prefers-color-scheme: dark" in CSS, True)


def case_the_active_chips_are_marked_by_more_than_colour():
    # An outline plus weight, not hue alone: colour is not available to
    # every reader, and these chips are the filter state.
    check("the status chips use an outline when on",
          bool(re.search(r"\.status-chip\.on\s*\{[^}]*outline", CSS)), True)
    check("the key chips use an outline and weight when on",
          bool(re.search(r"\.key-chip\.on\s*\{[^}]*outline", CSS)) and
          bool(re.search(r"\.key-chip\.on\s*\{[^}]*font-weight", CSS)), True)


def case_the_stylesheet_defines_the_variables_it_uses():
    used = set(re.findall(r"var\((--[a-z0-9-]+)", CSS))
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", CSS))
    check("no custom property is used without being defined",
          sorted(used - defined), [])


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
    print(f"viewer-markup: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
