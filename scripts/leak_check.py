"""Privacy regression check (see CLAUDE.md).

Pulls every distinct item name, author, narrator, genre, series,
publisher, and bundle name from catalog.db and the reference
spreadsheets, then searches all non-data files in the repo for them.
Exits 1 on any hit not on the allowlist below.

Contains no personal data itself — everything is read at runtime.
Run: .venv/Scripts/python scripts/leak_check.py

`ALLOWED` and `build_terms()` are also imported by
`leak_check_history.py`, which runs the same terms against git history.
Keep them importable: nothing at module scope may read the database or
exit, or importing this file would run a second scan as a side effect.
"""
import json
import pathlib
import re
import sqlite3
import subprocess
import sys

import openpyxl

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Known-benign matches, reviewed 2026-07-18. Two kinds:
# - the deliberate public house example (All Systems Red & co.);
# - generic vocabulary that legitimately appears in code/docs
#   (genres, major publishers, platform names, common words).
# Compare case-insensitively. Anything NOT here fails the check.
#
# There used to be a third kind - titles that collided only INSIDE longer
# words - and 11 entries were removed on 2026-08-02 when matching moved to
# word boundaries. Each of those had blinded the gate to a real title
# containing that word, which is the cost this list always carries: an
# entry earns its place only if the term appears in the repo as a whole
# word. Measured before removal, by scanning the repo for each entry under
# both rules; the ones that still hit as whole words stayed.
ALLOWED = {t.lower() for t in [
    "All Systems Red", "Martha Wells", "Kevin R. Free", "Murderbot Diaries",
    "Artificial Condition", "Exit Strategy", "Fugitive Telemetry",
    "Network Effect", "Rogue Protocol",              # public API fixture data
    "Fantasy", "Fiction", "Science Fiction", "Science", "Programming",
    "Manga", "Computers", "Drama", "Finance", "Machine learning",
    "Mathematics", "Virtual Reality", "Foundation", "general",
    "O'Reilly", "Packt", "Pearson", "Wiley", "Manning Publications",
    "No Starch Press", "GraphicAudio",
    "Humble Bundle", "Humble Music Bundle",
    "Changes", "Count", "Flight", "None", "Reads",
    # Added 2026-07-25. Ordinary English used as itself throughout the
    # README and source - "Rebuild the catalog", "Framed as a working
    # surface", "a bug in the prune logic" - never as a reference to the
    # library. A fourth entry here matched only inside "over-typed" and
    # was removed with the move to word boundaries.
    "Rebuild", "Framed", "Prune",

    # Added 2026-07-26 (second pass). A large harvest/enrich grew the
    # catalog by roughly 1800 terms, and these are the ones that newly
    # collided with text already committed. Three kinds, none of them a
    # reference to the library.
    #
    # Genre labels. Categories rather than possessions, joining the dozen
    # already listed above; they arrive from the metadata sources, so the
    # set grows on its own as the catalog does.
    "Adventure", "Comics", "Cooking", "Discipline", "Dystopian",
    "Economics", "Engineering", "Games", "History", "Music", "Mystery",
    "Personal Finance", "Political Science", "Reference", "Robot",
    #
    # Ordinary vocabulary, every one of which appears in the repo as a
    # whole word - "unknown", "rules", "days", "alone", "rest", "omni",
    # "seven", "symmetry", "wings", "the score" - in prose, in identifiers
    # or in headings. Re-measured 2026-08-02 under word-boundary matching;
    # the entries that survived only as substrings were removed then.
    "Alone", "Days", "Omni", "Rest", "Rules", "Seven", "Symmetry",
    "The Score", "Unknown", "Wings",
    #
    # Added 2026-07-26 (third pass). A timezone name, not a title: the
    # harvest quota design has to say when Google's daily quota resets,
    # and that instant is midnight Pacific. It appears only in that
    # sense, in the spec and in the source that computes the time.
    "Pacific",
    #
    # Added 2026-07-31 after the history scan run before the hidden-keys
    # merge. All three appear in commit messages, and history cannot be
    # edited, so they have to be allowed rather than reworded. "The
    # Outside" matches as the whole phrase in ordinary prose ("what the
    # outside world said"); the other two are quoted verbatim by the
    # commit that added them to this list, which is a whole-word match no
    # boundary rule can remove.
    "Blek", "The Outside", "ustwo",
    #
    # Added 2026-08-02. Ordinary English in the loop template's own prose
    # -- "not done except the small stuff" -- committed by the salvage
    # that captured the bootstrapped PLAN.md before the first audit
    # reworded it. Present only in that one historical blob; the working
    # tree has said something else since. A pre-existing history hit, not
    # something the boundary change introduced: a substring rule matched
    # it too.
    "STUFF",
    #
    # Added 2026-09-18. Ordinary vocabulary that became catalog terms as
    # the library grew, each already a whole word in 15 files (132 hits)
    # and in history pushed that day, which cannot be reworded:
    # "convergence" is the jeffy loop's own term ("never counts toward
    # convergence") and returns with every run; "legacy" names old-schema
    # databases in the migration tests and the db-schema probe; and
    # "divergence" is the CSV spec's "no divergence possible". A
    # one-word title like these is indistinguishable from the prose, so
    # the blindness this buys is one the check already had.
    "Convergence", "Divergence", "Legacy",
    #
    # House examples. "The Murderbot Diaries" is the article-carrying
    # variant of an entry already here, which the catalog stores in full.
    # Dune is famous public fiction used exactly as All Systems Red is —
    # docs/TEST-DATA.md already lists "Dune (Audiobook)" as standing test
    # vocabulary — and owning it says nothing about anyone.
    "The Murderbot Diaries", "Frank Herbert", "Dune",
]}


def db_terms(path):
    """Every private term held in the catalog, or none when there is no
    catalog. A fresh clone has no catalog.db, and sqlite3.connect would
    create an empty one and then fail on every query."""
    if not path.exists():
        return set()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    found = set()
    for r in conn.execute("SELECT name FROM items"):
        found.add(r["name"])
    for r in conn.execute("SELECT DISTINCT publisher AS v FROM items WHERE publisher IS NOT NULL"):
        found.add(r["v"])
    for r in conn.execute("SELECT DISTINCT series AS v FROM enrichment WHERE series IS NOT NULL"):
        found.add(r["v"])
    for r in conn.execute("SELECT DISTINCT name AS v FROM bundles"):
        found.add(r["v"])
    for col in ("authors", "narrator", "genre"):
        for r in conn.execute(f"SELECT {col} AS v FROM enrichment WHERE {col} IS NOT NULL"):
            try:
                vals = json.loads(r["v"])
                found.update(vals if isinstance(vals, list) else [vals])
            except (json.JSONDecodeError, TypeError):
                found.add(str(r["v"]))
    return found


TITLE_KEYS = {"name", "title"}
AUTHOR_KEYS = {"author", "authors"}


def sheet_terms(directory):
    """Titles and authors from the reference spreadsheets, if present."""
    found = set()
    for xlsx in directory.glob("*.xlsx"):
        wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if not header:
                continue
            cols = {i: str(h).strip().rstrip(":").lower()
                    for i, h in enumerate(header)
                    if h and str(h).strip().rstrip(":").lower() in TITLE_KEYS | AUTHOR_KEYS}
            for row in rows:
                for i in cols:
                    if i < len(row) and row[i] is not None:
                        found.add(str(row[i]).strip())
    return found


def build_terms(root=ROOT):
    """Every private term to search for, allowlist already applied.

    Empty means there is nothing to check against — no catalog.db and no
    spreadsheets — which callers must report rather than treat as a pass.
    """
    terms = db_terms(root / "catalog.db") | sheet_terms(root / "Reference spreadsheets")
    terms = {t.strip() for t in terms if t and str(t).strip()}
    return {t for t in terms
            if len(t) >= 4 and not t.replace(".", "").isdigit()
            and t.lower() not in ALLOWED}


NOTHING_TO_CHECK = (
    "SKIPPED: no catalog.db and no reference spreadsheets, so there is "
    "nothing to check against.\nThis is expected in a fresh clone. The "
    "check only means something on a machine\nholding the real library.")

# Gitignored runtime data. These legitimately contain the private library
# -- that is what they are for -- so scanning them only ever cries wolf,
# and a check that always fails is one that stops being read. "backups"
# holds snapshots written by `backup`; a cover archive's entry names are
# machine_names, so it trips on ~120 terms every time.
EXCLUDE_DIRS = {".git", ".venv", "covers", "cache", "backups", "__pycache__",
                "humble_catalog.egg-info", ".playwright-profile", ".secrets",
                "Reference spreadsheets"}

# Matched against the whole FILENAME, not Path.suffix. SQLite's sidecars
# are the reason: `catalog.db-wal` has suffix ".db-wal", so a suffix test
# for ".db" misses it, and the WAL is raw database pages -- it matched 93
# terms and buried the four real findings. Under WAL the sidecar can hold
# thousands of items the main file does not yet have, so this is not a
# small window. All of these are gitignored and can never be committed.
DATA_FILES = (".db", ".db-wal", ".db-shm", ".db-journal", ".bak", ".xlsx")

def should_scan(rel):
    """Whether a repo-relative POSIX path is one the term check reads.

    Shared by both modes so the staged check and the full sweep cannot
    disagree about what counts as a data file.
    """
    parts = pathlib.PurePosixPath(rel).parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return False
    return parts[-1] != "leak_check.py" and not parts[-1].endswith(DATA_FILES)


# A term matches only where it is not buried inside a longer word.
#
# Plain substring matching blocked commits on `UnboundLocalError` and on a
# `unittest.mock` class name, neither of which mentions the library: a term
# happened to spell part of a longer identifier. Every such trip cost a
# reword, and the rewords that were impossible - a name that belongs to the
# language - had to go into ALLOWED instead, which blinds the gate to every
# genuine title containing that word. Word boundaries end that trade.
#
# "Word character" here is alphanumeric but NOT underscore, which is the
# one place this deliberately differs from `\w`. machine_names join words
# with underscores, so treating `_` as part of a word would stop the gate
# seeing a title inside `moonfall_comic` - exactly the shape a leak takes
# in this project. Hyphens and dots are boundaries for the same reason.
WORDISH = r"[^\W_]"
_PATTERNS = {}


def boundary_pattern(term):
    """A compiled, case-insensitive pattern for `term` as a whole word.

    The assertions are added per side rather than using `\\b`, because a
    term may begin or end with punctuation - "O'Reilly", "R-TYPE", a title
    ending in "!" - and `\\b` there asserts the opposite of what is meant.
    Cached: the callers ask for the same terms thousands of times.
    """
    pattern = _PATTERNS.get(term)
    if pattern is None:
        body = re.escape(term)
        if re.match(WORDISH, term):
            body = f"(?<!{WORDISH})" + body
        if re.match(WORDISH, term[-1]):
            body = body + f"(?!{WORDISH})"
        pattern = _PATTERNS[term] = re.compile(body, re.IGNORECASE)
    return pattern


def make_matcher(terms):
    """A callable: text -> the set of terms occurring in it as whole words.

    Shared by the worktree scan and by leak_check_history, so the two can
    never disagree about what counts as a match.

    The cheap substring test runs first and rejects almost everything; the
    pattern only runs for a term already known to be present, so the regex
    cost is paid on hits rather than on every term of every file. That
    ordering is also why this cannot be blinder than the old matcher: the
    filter is the old rule exactly, and the pattern only ever removes a
    hit that the old rule would have reported.
    """
    prepared = [(t, t.lower()) for t in terms]

    def match(text):
        lowered = text.lower()
        return {t for t, low in prepared
                if low in lowered and boundary_pattern(t).search(text)}

    return match


def scan(sources, terms):
    """({term: [label, ...]}, files_scanned) over (label, text) pairs.

    `sources` may be a generator, so the full sweep never holds the whole
    repo in memory at once.
    """
    match = make_matcher(terms)
    hits, nfiles = {}, 0
    for label, text in sources:
        nfiles += 1
        for t in match(text):
            hits.setdefault(t, []).append(label)
    return hits, nfiles


def worktree_sources(root=ROOT):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if not should_scan(rel.as_posix()):
            continue
        try:
            yield str(rel), p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue


def staged_paths(root=ROOT):
    """Repo-relative paths staged for the current commit.

    ACMR only: a staged deletion carries no content, and a file being
    removed cannot leak anything. -z because a path with a space in it --
    `Reference spreadsheets/` is one -- comes back quoted otherwise.
    """
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=root, capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split("\0") if p]


def staged_sources(root=ROOT):
    """(path, staged text) for each staged file worth scanning.

    Read from the INDEX, not the working tree. Staging a file and then
    editing it further leaves two different versions, and the one that
    ships is the staged one -- scanning the file on disk would check a
    version nobody is committing.
    """
    for rel in staged_paths(root):
        if not should_scan(rel):
            continue
        try:
            blob = subprocess.run(["git", "show", f":{rel}"], cwd=root,
                                  capture_output=True, check=True).stdout
        except subprocess.CalledProcessError:
            continue  # vanished from the index between listing and reading
        yield rel, blob.decode("utf-8", errors="ignore")


def main(argv=()):
    # --staged is the pre-commit path: same terms, same rules, but only
    # over what is about to be committed, which turns a whole-repo sweep
    # into something fast enough to run on every commit.
    staged = "--staged" in argv
    terms = build_terms()
    if not terms:
        # Say so loudly rather than printing "clean": with nothing to search
        # for, a pass proves nothing, and quietly succeeding would give a
        # contributor false confidence that the gate had run.
        print(NOTHING_TO_CHECK)
        return 0

    hits, nfiles = scan(
        staged_sources() if staged else worktree_sources(), terms)

    where = "staged file" if staged else "file"
    print(f"checked {len(terms)} terms against {nfiles} {where}"
          f"{'' if nfiles == 1 else 's'}")
    if hits:
        print(f"LEAK: {len(hits)} term(s) from the private library found "
              f"in {'the staged changes' if staged else 'the repo'}:")
        for t in sorted(hits):
            print(f"  {t!r}: {sorted(set(hits[t]))}")
        print("Fix: replace with invented names from docs/TEST-DATA.md, "
              "or add to ALLOWED above with a comment saying why it is benign.")
        return 1
    print("clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
