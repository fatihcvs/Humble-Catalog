"""Refuse to let runtime data files enter git (see CLAUDE.md).

The two leak_check scripts ask "does any private *term* appear in the
repo?", which needs the real library on disk to answer. This asks the
cheaper and complementary question: "is a file that holds private data
tracked at all?" — answerable from path names alone, so it works on any
clone, including a CI runner with no catalog.

It checks every path in history, not just the current tree. A data file
committed and later deleted is still published by a push; removing it
from HEAD does not unpublish it.

These paths are all gitignored. This is the backstop for the ways that
protection fails: `git add -f`, a stale .gitignore, or a clone whose
exclusions lived only in the developer's global config.

Run: .venv/Scripts/python scripts/check_no_data_tracked.py
"""
import fnmatch
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Matched against full repo-relative POSIX paths. Deliberately wider than
# the exact filenames in use: `*.db*` catches SQLite's -wal/-shm/-journal
# sidecars, which hold pages the main file does not yet have, and `*.xlsx`
# covers any reference spreadsheet regardless of where someone puts it.
FORBIDDEN = [
    "*.db", "*.db-*",                  # the catalog and its sidecars
    "*.xlsx", "*.xlsm",                # reference spreadsheets, exports
    "*.env", "*.bak",
    "covers/*", "**/covers/*",         # cover images (named per item)
    "cache/*", "**/cache/*",           # harvested API responses
    "backups/*", "**/backups/*",       # snapshots written by `backup`
    "Reference spreadsheets/*",
    ".secrets/*",
    ".playwright-profile/*",           # a logged-in browser session
    "lan/*", "**/lan/*",               # serve --lan: token, CA private key
]

# Exports the CLI writes at the repo root. Not private in themselves, but
# they are a rendering of the catalog, so they must never be committed.
FORBIDDEN += ["catalog.csv", "catalog-filtered.csv",
              "catalog.xlsx", "catalog-filtered.xlsx"]


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, check=True).stdout.decode(
                              "utf-8", "ignore")


def tracked_paths():
    return {p for p in git("ls-files").splitlines() if p.strip()}


def historical_paths():
    """Every path ever touched by any commit on any ref.

    Read from commit diffs rather than `rev-list --objects`, which looks
    like the natural tool and is quietly lossy: git stores one blob per
    unique *content*, and rev-list reports that blob under a single path.
    Two identical files — two copies of a placeholder cover, two empty
    files — collapse to one entry and the second path is never seen.
    Verified: a covers/*.jpg whose bytes matched a catalog.db was
    reported only as catalog.db.

    -m so merge commits diff against every parent, or a path introduced
    while resolving a conflict is invisible. --no-renames so a rename
    reports both the old and new path instead of only the new one.

    Objects unreachable from any ref have no path to report and so are
    out of scope here; leak_check_history.py reads their contents.
    """
    out = git("log", "--all", "--no-renames", "-m", "--name-only",
              "--pretty=format:")
    return {line.strip() for line in out.splitlines() if line.strip()}


def offenders(paths):
    return sorted(p for p in paths
                  if any(fnmatch.fnmatch(p, pat) for pat in FORBIDDEN))


def main():
    shallow = git("rev-parse", "--is-shallow-repository").strip() == "true"

    now = offenders(tracked_paths())
    past = offenders(historical_paths()) if not shallow else []
    gone = [p for p in past if p not in set(now)]

    if now:
        print(f"FAIL: {len(now)} data file(s) are tracked:")
        for p in now:
            print(f"  {p}")
        print("Fix: `git rm --cached <path>`, confirm .gitignore covers it, "
              "and commit.\nIf it was ever pushed, treat it as published.")
    if gone:
        print(f"FAIL: {len(gone)} data file(s) exist in history but not in "
              "HEAD:")
        for p in gone:
            print(f"  {p}")
        print("Deleting a file does not remove it from history. Rewriting "
              "history\n(git filter-repo) is the only fix before a public "
              "push.")
    if now or gone:
        return 1

    if shallow:
        # Say so rather than reporting a pass the check did not earn.
        print("WARNING: shallow clone - history not checked, only the "
              "current tree.")
    scope = "tracked files" if shallow else "tracked files and all history"
    print(f"clean: no data files in {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
