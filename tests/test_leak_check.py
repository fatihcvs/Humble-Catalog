import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    # scripts/ is not a package, so the checker is loaded by path.
    spec = importlib.util.spec_from_file_location(
        "leak_check", ROOT / "scripts" / "leak_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lc = _load()


# --- should_scan: shared by the staged check and the full sweep, so the
# two cannot disagree about what a data file is. ---

def test_ordinary_source_and_docs_are_scanned():
    assert lc.should_scan("humble_catalog/webapp/__init__.py")
    assert lc.should_scan("docs/TEST-DATA.md")
    assert lc.should_scan("README.md")


def test_the_checker_does_not_scan_itself():
    # It holds the allowlist, so every allowed term appears in it verbatim.
    assert not lc.should_scan("scripts/leak_check.py")


@pytest.mark.parametrize("path", [
    "catalog.db",
    "catalog.db-wal",       # raw database pages; matched on suffix, not
    "catalog.db-shm",       # Path.suffix, which would miss these
    "catalog.db-journal",
    "backups/catalog.bak",
    "Reference spreadsheets/library.xlsx",
])
def test_data_files_are_never_scanned(path):
    assert not lc.should_scan(path)


@pytest.mark.parametrize("path", [
    "covers/abc.jpg",
    "cache/x.json",
    "backups/anything.txt",
    ".venv/lib/site-packages/x.py",
    ".git/COMMIT_EDITMSG",
    "humble_catalog/__pycache__/db.cpython-312.pyc",
])
def test_excluded_directories_are_never_scanned(path):
    # These legitimately hold the private library, so scanning them only
    # ever cries wolf.
    assert not lc.should_scan(path)


# --- scan: the matching itself. ---

def test_scan_finds_a_term_case_insensitively():
    hits, n = lc.scan([("a.md", "The Gilded MYCELIUM is here")],
                      {"the gilded mycelium"})
    assert n == 1
    assert hits == {"the gilded mycelium": ["a.md"]}


def test_scan_matches_substrings_which_is_why_prose_trips_it():
    # Documented behaviour, not an accident: it is what catches a title
    # buried mid-sentence, and also what makes ordinary words collide.
    hits, _ = lc.scan([("a.md", "a monkey wrench")], {"monkey"})
    assert hits == {"monkey": ["a.md"]}


def test_scan_reports_every_file_a_term_appears_in():
    hits, n = lc.scan([("a.md", "widget"), ("b.md", "widget"), ("c.md", "x")],
                      {"widget"})
    assert n == 3
    assert hits["widget"] == ["a.md", "b.md"]


def test_scan_of_nothing_is_clean_not_an_error():
    assert lc.scan([], {"widget"}) == ({}, 0)


# --- the staged mode, against a real repository. ---

def _git(repo, *args):
    return subprocess.run(("git",) + args, cwd=repo, capture_output=True,
                          text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "seed.txt")
    _git(tmp_path, "commit", "-qm", "seed")
    return tmp_path


def test_staged_paths_lists_only_what_is_staged(repo):
    (repo / "staged.md").write_text("in the index\n", encoding="utf-8")
    (repo / "untracked.md").write_text("not staged\n", encoding="utf-8")
    _git(repo, "add", "staged.md")
    assert lc.staged_paths(repo) == ["staged.md"]


def test_staged_paths_survives_a_space_in_the_path(repo):
    # Without -z git quotes such a path, and the quotes end up in the name.
    folder = repo / "a folder"
    folder.mkdir()
    (folder / "note.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "a folder/note.md")
    assert lc.staged_paths(repo) == ["a folder/note.md"]


def test_a_staged_deletion_is_not_scanned(repo):
    # It carries no content; a file being removed cannot leak anything.
    _git(repo, "rm", "-q", "seed.txt")
    assert lc.staged_paths(repo) == []


def test_staged_sources_reads_the_INDEX_not_the_working_tree(repo):
    # The case the whole mode exists for: stage a clean version, then edit
    # the file further. What ships is the staged text, so that is what has
    # to be checked -- reading from disk would scan a version nobody is
    # committing, and would miss a leak staged a moment earlier.
    target = repo / "note.md"
    target.write_text("The Gilded Mycelium\n", encoding="utf-8")
    _git(repo, "add", "note.md")
    target.write_text("something else entirely\n", encoding="utf-8")

    sources = dict(lc.staged_sources(repo))
    assert sources["note.md"] == "The Gilded Mycelium\n"
    assert "something else" not in sources["note.md"]


def test_staged_sources_skips_data_files(repo):
    # -f because .gitignore is not in play here; the point is that the
    # scanner refuses the path even when git would carry it.
    (repo / "catalog.db").write_bytes(b"not really a database")
    _git(repo, "add", "-f", "catalog.db")
    assert dict(lc.staged_sources(repo)) == {}


def test_staged_sources_tolerates_binary_content(repo):
    # errors="ignore", so an image staged alongside code cannot crash the
    # hook and block a commit.
    (repo / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe binary")
    _git(repo, "add", "pic.png")
    assert "pic.png" in dict(lc.staged_sources(repo))
