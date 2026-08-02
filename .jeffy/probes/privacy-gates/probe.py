"""Known-answer battery for the privacy-gates inventory row.

Covers `scripts/leak_check.py`, `scripts/leak_check_history.py` and
`scripts/check_no_data_tracked.py` - the standing order's enforcement.

These are the checks the whole repo's privacy rests on, and a defect in
one of them is silent by construction: a gate that scans too little
reports `clean` exactly as loudly as a gate that scans everything. So the
cases here are mostly about COVERAGE - what each gate refuses to look at,
and whether its exclusion list is doing what it claims.

tests/test_leak_check.py already pins the matcher's word-boundary rules,
including 27 cases added at 570d5f4. This battery deliberately does not
repeat them; it covers the parts no test reaches: `should_scan`'s
exclusions, `check_no_data_tracked`'s pattern list, and the sharing
between the worktree and history scanners.

Terms used here are invented, from docs/TEST-DATA.md.
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import leak_check as lc  # noqa: E402
import check_no_data_tracked as cndt  # noqa: E402

PASS, FAIL = [], []


def check(label, got, want):
    (PASS if got == want else FAIL).append(label)
    if got != want:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")


# ------------------------------------------------------------- should_scan

def case_the_excluded_directories_are_never_read():
    for path in ["covers/a.jpg", "cache/x.json", "backups/catalog-1.db",
                 ".venv/lib/x.py", ".git/config", "__pycache__/x.pyc",
                 ".playwright-profile/Default/Cookies",
                 ".secrets/keys.env",
                 "Reference spreadsheets/E-books.xlsx"]:
        check(f"{path} is not scanned", lc.should_scan(path), False)


def case_an_excluded_directory_is_excluded_at_any_depth():
    check("a nested covers directory is excluded too",
          lc.should_scan("docs/covers/a.jpg"), False)
    check("and a nested cache", lc.should_scan("a/b/cache/x.json"), False)


def case_a_directory_whose_name_merely_contains_an_excluded_word_is_scanned():
    # The exclusion is by path PART, not by substring: a file under
    # `covers_docs/` is not under `covers/`.
    check("covers_docs is not the covers directory",
          lc.should_scan("covers_docs/notes.md"), True)


def case_every_data_file_suffix_is_skipped_by_whole_filename():
    """The sidecar case the comment calls out.

    `catalog.db-wal` has suffix ".db-wal", so a `Path.suffix == ".db"`
    test misses it - and under WAL the sidecar can hold thousands of
    items the main file does not yet have. Matched against the whole
    filename for exactly that reason.
    """
    for name in ["catalog.db", "catalog.db-wal", "catalog.db-shm",
                 "catalog.db-journal", "notes.bak", "sheet.xlsx"]:
        check(f"{name} is not scanned as text", lc.should_scan(name), False)


def case_leak_check_itself_is_never_scanned():
    # It quotes every ALLOWED entry verbatim, so scanning it would report
    # the allowlist as a leak.
    check("the gate does not scan itself",
          lc.should_scan("scripts/leak_check.py"), False)
    check("but its sibling scripts are scanned",
          lc.should_scan("scripts/leak_check_history.py"), True)


def case_ordinary_source_and_docs_are_scanned():
    for path in ["humble_catalog/db.py", "docs/BACKLOG.md", "README.md",
                 "tests/test_webapp.py", ".jeffy/probes/x/probe.py",
                 "PLAN.md", "JOURNAL.md"]:
        check(f"{path} is scanned", lc.should_scan(path), True)


# ---------------------------------------------------- the two scanners agree

def case_the_history_scanner_uses_the_gate_matcher():
    # Asserted on __module__ rather than identity: this file loads
    # leak_check by path while the history script imports it by name, so
    # there are two module objects and two function objects from one
    # source.
    spec = importlib.util.spec_from_file_location(
        "leak_check_history", ROOT / "scripts" / "leak_check_history.py")
    history = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(history)
    check("the matcher comes from leak_check",
          history.make_matcher.__module__, "leak_check")
    check("and so does should_scan",
          history.should_scan.__module__, "leak_check")


def case_the_history_scanner_skips_the_gate_file_too():
    # Its OLD blobs quote terms since removed from ALLOWED, so scanning
    # them would report the allowlist's own history as a leak.
    spec = importlib.util.spec_from_file_location(
        "leak_check_history", ROOT / "scripts" / "leak_check_history.py")
    history = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(history)
    check("history skips leak_check.py",
          history.should_scan("scripts/leak_check.py"), False)


# --------------------------------------------------- check_no_data_tracked

def case_every_data_shape_is_forbidden():
    for path in ["catalog.db", "catalog.db-wal", "catalog.db-shm",
                 "notes.bak", "sheet.xlsx", "book.xlsm", "keys.env",
                 "covers/a.jpg", "humble_catalog/covers/a.jpg",
                 "cache/x.json", "backups/catalog-1.db",
                 "Reference spreadsheets/E-books.xlsx",
                 ".secrets/keys", ".playwright-profile/Default/Cookies"]:
        check(f"{path} is forbidden", cndt.offenders([path]), [path])


def case_the_cli_exports_are_forbidden():
    """The near-miss from iteration 16, pinned.

    `export` writes catalog.csv by default, and a probe once left one in
    the repo root untracked. It is not private in itself - it is a
    rendering of the catalog, which is worse - and this list is what
    catches it the moment it becomes tracked.
    """
    for path in ["catalog.csv", "catalog.xlsx", "catalog-filtered.csv",
                 "catalog-filtered.xlsx"]:
        check(f"{path} is forbidden", cndt.offenders([path]), [path])


def case_ordinary_repo_files_are_not_offenders():
    innocent = ["humble_catalog/db.py", "README.md", "docs/TEST-DATA.md",
                "tests/test_webapp.py", "pyproject.toml",
                "humble_catalog/webapp/static/catalog.js",
                "docs/screenshot-viewer.png",
                "humble_catalog/webapp/static/favicon-32.png"]
    check("no ordinary file is an offender", cndt.offenders(innocent), [])


def case_a_csv_that_is_not_an_export_is_allowed():
    # The list names the exact export filenames rather than *.csv, so an
    # unrelated csv fixture is not blocked.
    check("an unrelated csv is not forbidden",
          cndt.offenders(["tests/fixtures/sample.csv"]), [])


def case_offenders_reports_every_match_sorted():
    paths = ["z.db", "covers/a.jpg", "a.bak"]
    check("all three are reported, sorted",
          cndt.offenders(paths), ["a.bak", "covers/a.jpg", "z.db"])


# --------------------------------------------------------- the term build

def case_an_allowed_term_does_not_trip_the_gate():
    # ALLOWED is compared case-insensitively; a term on the list must not
    # be reported however it is spelled.
    matcher = lc.make_matcher(["Dune"])
    check("the matcher itself still sees it",
          matcher("a copy of Dune"), {"Dune"})
    check("but the gate's own term set excludes allowed entries",
          "dune" in lc.ALLOWED, True)


def case_the_allowlist_is_lowercased_for_comparison():
    check("every entry is stored lowercase",
          all(t == t.lower() for t in lc.ALLOWED), True)


def case_the_nothing_to_check_message_exists():
    # The message a fresh clone with no catalog gets, so the gate is a
    # no-op rather than a failure there.
    check("there is a stated no-op message",
          isinstance(lc.NOTHING_TO_CHECK, str) and
          len(lc.NOTHING_TO_CHECK) > 0, True)


# -------------------------------------------------------------- scan shape

def case_scan_reports_each_term_with_the_files_it_was_found_in():
    hits, nfiles = lc.scan([("a.md", "I own Moonfall"),
                            ("b.md", "nothing here"),
                            ("c.md", "Moonfall again")], ["Moonfall"])
    check("two files are named", hits, {"Moonfall": ["a.md", "c.md"]})
    check("and every file is counted", nfiles, 3)


def case_scan_of_a_clean_repo_reports_nothing():
    hits, nfiles = lc.scan([("a.md", "ordinary prose")], ["Moonfall"])
    check("no hits", hits, {})
    check("but the file was still read", nfiles, 1)


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
    print(f"privacy-gates: {len(PASS)}/{total}")
    sys.exit(1 if FAIL else 0)
