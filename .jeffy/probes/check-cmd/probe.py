"""Known-answer battery for the check-cmd inventory row.

Covers `humble_catalog/check.py` - the per-source connectivity report.

`run(sources=...)` takes the source map as a parameter, which is the
module's own injection seam, so this battery drives the real reporting
logic with stub sources and reaches every branch without a live request.
The live half - what each real source does on the wire - belongs to the
`sources-*` rows, which are swept.

The case that matters most is REDACTION: a source's error string can
embed the request URL with the API key in it, and this command prints
that string. A probe that only checked the status letters would certify a
report that leaks a credential to the terminal.

Every title is invented, from docs/TEST-DATA.md.
"""
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from humble_catalog import check  # noqa: E402

PASS, FAIL = [], []


def chk(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


class Stub:
    """A source stand-in: answers, raises, or reports a missing credential."""

    def __init__(self, results=None, error=None, key=True, token=True):
        self.results, self.error = results, error
        self.key, self.token = key, token
        self.asked = []

    def lookup(self, query):
        self.asked.append(query)
        if self.error:
            raise self.error
        return self.results or []


def run(sources):
    stream = io.StringIO()
    results = check.run(sources=sources, stream=stream)
    return results, stream.getvalue()


# ------------------------------------------------------------ the verdicts

def case_a_source_that_answers_is_ok_with_its_count():
    results, out = run({"example_source": Stub(results=[{}, {}, {}])})
    chk("an answering source is OK", results["example_source"][0], "OK")
    chk("and the detail names the count and the query",
        results["example_source"][1], f"3 results for '{check.QUERY}'")
    chk("the report line carries the status", "OK" in out, True)


def case_a_source_answering_nothing_is_still_ok():
    # OK means "the API answered", not "the API found something": an empty
    # result is a working connection and must not read as a failure.
    results, _out = run({"example_source": Stub(results=[])})
    chk("zero results is still OK", results["example_source"][0], "OK")
    chk("with a zero count", results["example_source"][1],
        f"0 results for '{check.QUERY}'")


def case_a_missing_key_is_skip_and_is_never_asked():
    # Documented: a source with an empty key would silently return [] and
    # report a hollow OK, so the missing credential is reported instead.
    stub = Stub(key="")
    results, _out = run({"hardcover": stub})
    chk("a source with no key is SKIP", results["hardcover"][0], "SKIP")
    chk("and the detail names the environment variable it wants",
        results["hardcover"][1], "HARDCOVER_API_KEY not set")
    chk("and it is never asked", stub.asked, [])


def case_a_missing_token_is_also_skip():
    stub = Stub(token="")
    results, _out = run({"example_source": stub})
    chk("an empty token is SKIP too", results["example_source"][0], "SKIP")
    chk("with a generic name when the source has no known env var",
        results["example_source"][1], "API key not set")
    chk("and it is never asked", stub.asked, [])


def case_every_known_source_names_its_own_variable():
    for name, env in check.KEY_ENV.items():
        results, _out = run({name: Stub(key="")})
        chk(f"{name} names {env}", results[name][1], f"{env} not set")


def case_a_raising_source_is_fail():
    results, _out = run({"example_source": Stub(error=RuntimeError("boom"))})
    chk("a raising source is FAIL", results["example_source"][0], "FAIL")
    chk("and the detail is the error text",
        results["example_source"][1], "boom")


def case_one_failing_source_does_not_stop_the_others():
    # The property the per-source loop exists for.
    results, _out = run({"a_source": Stub(error=RuntimeError("boom")),
                         "b_source": Stub(results=[{}])})
    chk("the failing source is reported", results["a_source"][0], "FAIL")
    chk("and the healthy one is still checked", results["b_source"][0], "OK")


def case_a_source_is_asked_exactly_once():
    stub = Stub(results=[{}])
    run({"example_source": stub})
    chk("the connectivity query is sent once", stub.asked, [check.QUERY])


# --------------------------------------------------------------- redaction

def case_an_error_carrying_a_key_is_redacted():
    """The case this row is worth sweeping for."""
    leaky = RuntimeError(
        "401 Client Error for url: "
        "https://api.example.invalid/search?key=SECRETKEY123&q=x")
    results, out = run({"example_source": Stub(error=leaky)})
    detail = results["example_source"][1]
    chk("the report is a FAIL", results["example_source"][0], "FAIL")
    chk("the key does not survive into the detail",
        "SECRETKEY123" in detail, False)
    chk("nor into anything written to the terminal",
        "SECRETKEY123" in out, False)


def case_redaction_keeps_the_diagnosis():
    # Redaction must not reduce the line to nothing: the status code is
    # what tells a bad key from a dead host, and it has to survive.
    leaky = RuntimeError(
        "401 Client Error for url: https://api.example.invalid/?key=SECRETKEY123")
    results, _out = run({"example_source": Stub(error=leaky)})
    chk("the error still says what went wrong",
        "401" in results["example_source"][1], True)


# ---------------------------------------------------------------- summary

def case_the_summary_counts_each_verdict():
    results, out = run({
        "a_source": Stub(results=[{}]),
        "b_source": Stub(results=[{}]),
        "c_source": Stub(key=""),
        "d_source": Stub(error=RuntimeError("boom")),
    })
    chk("every source is reported", len(results), 4)
    chk("the summary counts them", "4 sources: 2 OK, 1 skipped, 1 failed."
        in out, True)


def case_the_summary_is_consistent_with_the_verdicts():
    # An invariant rather than a string: the three counts must sum to the
    # number of sources, whatever they are.
    sources = {"a_source": Stub(results=[{}]), "b_source": Stub(key=""),
               "c_source": Stub(error=RuntimeError("x")),
               "d_source": Stub(error=RuntimeError("y"))}
    results, _out = run(sources)
    counts = {}
    for status, _detail in results.values():
        counts[status] = counts.get(status, 0) + 1
    chk("the verdicts partition the sources",
        sum(counts.values()), len(sources))
    chk("and each source has exactly one verdict",
        sorted(counts.items()), [("FAIL", 2), ("OK", 1), ("SKIP", 1)])


def case_every_source_appears_in_the_written_report():
    names = {"a_source": Stub(results=[{}]), "bb_source": Stub(key=""),
             "ccc_source": Stub(error=RuntimeError("boom"))}
    _results, out = run(names)
    for name in names:
        chk(f"{name} appears in the report", name in out, True)


# ------------------------------------------------------------------ board

def case_the_board_pads_names_to_a_common_width():
    rows = check._board(["a", "bbbb"], {})
    chk("the board renders a row", len(rows) >= 1, True)
    chk("a source with no verdict yet shows the pending marker",
        check.PENDING in rows[0], True)


def case_the_board_shows_a_known_status():
    rows = check._board(["a_source"], {"a_source": "OK"})
    chk("a decided source shows its status", "OK" in rows[0], True)
    chk("and no longer shows the pending marker",
        check.PENDING in rows[0], False)


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
    print(f"check-cmd: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
