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
import sqlite3
import sys

import openpyxl

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Known-benign matches, reviewed 2026-07-18. Three kinds:
# - the deliberate public house example (All Systems Red & co.);
# - generic vocabulary that legitimately appears in code/docs
#   (genres, major publishers, platform names, common words);
# - common-word titles that only match as substrings of prose.
# Compare case-insensitively. Anything NOT here fails the check.
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
    "Book M", "Changes", "Count", "Eden", "Emote", "Flight", "None",
    "Reads",
    # Added 2026-07-25. Ordinary English (and one hyphen accident) that
    # only ever matches inside unrelated prose or code, never a reference
    # to the library: "Rebuild" is used throughout the README and source,
    # "Framed as a working surface", "a bug in the prune logic", and
    # "R-TYPE" matches inside "over-typed" and "filter-type-0".
    "Rebuild", "Framed", "Prune", "R-TYPE",
    # Added 2026-07-26 after the history scan. Both are locking vocabulary
    # this codebase uses constantly — the enrichment lock, hand-edited rows
    # being "unlocked" for re-enrichment — so they match inside ordinary
    # sentences ("the migration block in connect()") and never as titles.
    "Lock In", "Unlocked",

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
    "Social Science",
    #
    # Ordinary vocabulary. Some match plain prose ("unknown", "rules",
    # "days", "adventure"), the rest only ever appear inside a longer
    # word: "asymmetry", "restore", "omnibus", "avoid", "the scorer",
    # "standalone", and — since the Steam setup notes landed — the
    # ISteamUser endpoint name.
    "Alone", "Days", "Muse", "Omni", "Rest", "Rules", "Seven", "Symmetry",
    "The Score", "Unknown", "Void", "Wings",
    #
    # Added 2026-07-26 (third pass). A timezone name, not a title: the
    # harvest quota design has to say when Google's daily quota resets,
    # and that instant is midnight Pacific. It appears only in that
    # sense, in the spec and in the source that computes the time.
    "Pacific",
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

def main():
    terms = build_terms()
    if not terms:
        # Say so loudly rather than printing "clean": with nothing to search
        # for, a pass proves nothing, and quietly succeeding would give a
        # contributor false confidence that the gate had run.
        print(NOTHING_TO_CHECK)
        return 0

    hits = {}
    nfiles = 0
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if p.name == "leak_check.py" or p.name.endswith(DATA_FILES):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        nfiles += 1
        for t in terms:
            if t.lower() in text:
                hits.setdefault(t, []).append(str(rel))

    print(f"checked {len(terms)} terms against {nfiles} files")
    if hits:
        print(f"LEAK: {len(hits)} term(s) from the private library found in the repo:")
        for t in sorted(hits):
            print(f"  {t!r}: {sorted(set(hits[t]))}")
        print("Fix: replace with invented names from docs/TEST-DATA.md, "
              "or add to ALLOWED above with a comment saying why it is benign.")
        return 1
    print("clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
