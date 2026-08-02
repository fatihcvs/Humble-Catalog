"""Known-answer battery for the js-panels inventory row.

Covers `keys.js` and `bundles.js`: `displayState`, `shownKeys`,
`keyChipCounts`, `keysExpiring`, `KEY_STATES`, and `money`.

The case this row is worth sweeping for is a counting INVARIANT the code
documents as the fix for a real bug. `keyChipCounts` counts by
`displayState` rather than reading the server's `counts`, because that
map partitions every key - matched and hidden included - so a chip
reading "Not in a library 624" would deliver fewer than 624 once hidden
rows moved to their own bucket. Counting by displayState makes the four
chips partition the REPORTED rows, so a count equals what clicking it
shows, by construction. That equality is asserted directly here, which is
the only check that would catch the bug coming back.

Every title is invented, from docs/TEST-DATA.md. One Node process.
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


def key(product, state="unredeemed", hidden_at=None, expires=None,
        expired=False):
    return {"product": product, "machine_name": product.lower().replace(" ", "_"),
            "gamekey": "k1", "state": state, "hidden_at": hidden_at,
            "expires": expires, "expired": expired, "days_left": None,
            "revealed": False, "store": "steam", "key_type_label": "steam",
            "bundle": "Humble Game Bundle: Key Vault", "bundle_url": "",
            "purchased_at": "2026-01-01", "near_match": None}


ROWS = [
    key("Widget Quest", "unredeemed"),
    key("Neon Drifter", "unredeemed", expires="2026-09-01T00:00:00"),
    key("Pixel Harbor Rally", "uncertain"),
    key("Cinder Vale Chronicles", "uncheckable"),
    key("Hidden One", "unredeemed", hidden_at="2026-07-01T00:00:00"),
    key("Hidden Two", "uncertain", hidden_at="2026-07-01T00:00:00",
        expires="2026-09-01T00:00:00"),
    key("Dead Key", "unredeemed", expires="2026-01-01T00:00:00", expired=True),
]


def batch():
    rows_json = json.dumps(json.dumps(ROWS))
    expr = (
        "(() => { const out = {};"
        " const ROWS = JSON.parse(%s);"
        " app.setKeyRows(ROWS);"
        " out.states = app.KEY_STATES.map(s => s.state);"
        " out.labels = app.KEY_STATES.map(s => s.label);"
        " out.display = ROWS.map(r => app.displayState(r));"
        " out.counts = app.keyChipCounts();"
        " out.expiring = app.keysExpiring();"
        # shownKeys under several chip selections
        " const shown = {};"
        " for (const sel of [['unredeemed'], ['uncertain'], ['uncheckable'],"
        "                    ['hidden'], ['unredeemed','uncertain'],"
        "                    ['unredeemed','uncertain','uncheckable','hidden'],"
        "                    []]) {"
        "   app.setKeyStates(sel);"
        "   shown[sel.join('+') || 'none'] = app.shownKeys().map(r => r.product);"
        " }"
        " out.shown = shown;"
        # money
        " out.money = {usd: app.money(12, 'USD'), eur: app.money(21.9, 'EUR'),"
        "   gbp: app.money(5, 'GBP'), unknown: app.money(7.5, 'ZZZ'),"
        "   zero: app.money(0, 'USD'), rounds: app.money(1.005, 'USD')};"
        " return out; })()" % rows_json)
    return eval_js(expr)


R = batch()


# ------------------------------------------------------------- KEY_STATES

def case_four_chips_are_offered():
    check("the viewer offers four chips", R["states"],
          ["unredeemed", "uncertain", "uncheckable", "hidden"])
    check("each with a label", all(bool(x) for x in R["labels"]), True)


def case_the_chip_labels_avoid_claiming_more_than_is_known():
    # "Not in a library" rather than "unredeemed", and "No importer"
    # rather than "uncheckable": the viewer says what is actually known.
    check("unredeemed reads as absence from a library",
          R["labels"][0], "Not in a library")
    check("uncheckable names the missing importer",
          R["labels"][2], "No importer")


# ----------------------------------------------------------- displayState

def case_hiding_a_row_overrides_its_server_state():
    """One function reconciles the server's three states with four chips.

    The earlier design made hidden a second filter axis and cost a chip
    whose count did not match what clicking it delivered.
    """
    check("each row's chip is its state unless hidden",
          R["display"],
          ["unredeemed", "unredeemed", "uncertain", "uncheckable",
           "hidden", "hidden", "unredeemed"])


def case_a_hidden_row_never_reports_its_server_state():
    # Rows 5 and 6 are unredeemed and uncertain on the server; both must
    # read as hidden.
    check("both hidden rows collapse to the hidden chip",
          [R["display"][4], R["display"][5]], ["hidden", "hidden"])


# ---------------------------------------------------------- the invariant

def case_the_chip_counts_partition_the_rows():
    """The bug this counting exists to prevent, asserted as an equality.

    Reading the server's `counts` would make a chip promise more rows
    than clicking it delivers, because that map includes matched and
    hidden keys. Counting by displayState makes the four chips sum to
    exactly the rows the viewer holds.
    """
    check("the four counts sum to every row",
          sum(R["counts"].values()), len(ROWS))


def case_each_chip_count_equals_what_clicking_it_shows():
    # The property stated in the code as "by construction" - checked
    # rather than trusted, for all four chips.
    for state in R["states"]:
        check(f"the {state} count matches its selection",
              R["counts"][state], len(R["shown"][state]))


def case_the_counts_are_the_expected_known_answers():
    check("three unredeemed, one uncertain, one uncheckable, two hidden",
          R["counts"],
          {"unredeemed": 3, "uncertain": 1, "uncheckable": 1, "hidden": 2})


# ------------------------------------------------------------- shownKeys

def case_selecting_a_chip_shows_exactly_its_rows():
    check("unredeemed", sorted(R["shown"]["unredeemed"]),
          ["Dead Key", "Neon Drifter", "Widget Quest"])
    check("uncertain", R["shown"]["uncertain"], ["Pixel Harbor Rally"])
    check("uncheckable", R["shown"]["uncheckable"],
          ["Cinder Vale Chronicles"])
    check("hidden", sorted(R["shown"]["hidden"]), ["Hidden One", "Hidden Two"])


def case_two_chips_show_the_union():
    check("selecting two chips is their union",
          sorted(R["shown"]["unredeemed+uncertain"]),
          ["Dead Key", "Neon Drifter", "Pixel Harbor Rally", "Widget Quest"])


def case_every_chip_shows_every_row():
    check("all four chips show the whole set",
          len(R["shown"]["unredeemed+uncertain+uncheckable+hidden"]),
          len(ROWS))


def case_no_chip_shows_nothing():
    check("deselecting every chip shows no rows", R["shown"]["none"], [])


# ------------------------------------------------------------- expiring

def case_expiring_counts_only_live_unhidden_dates():
    # Neon Drifter is the only row with a live expiry that is not hidden:
    # Hidden Two has one but is hidden, and Dead Key's has passed.
    check("one key is expiring", R["expiring"], 1)


# ---------------------------------------------------------------- money

def case_a_known_currency_uses_its_symbol():
    check("usd", R["money"]["usd"], "$12.00")
    check("eur", R["money"]["eur"], "€21.90")
    check("gbp", R["money"]["gbp"], "£5.00")


def case_an_unknown_currency_prints_its_code():
    # Unambiguous if less pretty, and the same choice the CLI report makes.
    check("an unlisted currency falls back to the code",
          R["money"]["unknown"], "ZZZ 7.50")


def case_an_amount_is_always_two_decimal_places():
    check("zero renders in full", R["money"]["zero"], "$0.00")
    check("and a fractional cent is rounded to two places",
          R["money"]["rounds"] in ("$1.00", "$1.01"), True)


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
    print(f"js-panels: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
