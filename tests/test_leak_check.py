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


def test_scan_matches_a_term_buried_mid_sentence():
    # A title does not have to be on a line of its own to be a leak, so
    # the match is not anchored. What it IS bounded by is the word: see
    # the word-boundary section at the end of this file, which replaced
    # the older rule of matching any substring anywhere.
    hits, _ = lc.scan([("a.md", "a monkey wrench")], {"monkey"})
    assert hits == {"monkey": ["a.md"]}
    assert lc.scan([("a.md", "the monkeyshine")], {"monkey"}) == ({}, 1)


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


# --- word-boundary matching -------------------------------------------
# A term matches only where it is not buried inside a longer word. Plain
# substring matching blocked commits over ordinary code vocabulary - a
# builtin exception name, a unittest.mock class - because a catalog term
# happened to spell part of a longer identifier. The trips that could not
# be reworded had to go into ALLOWED instead, which blinds the gate to
# every genuine title containing that word.
#
# Every term below is invented, from docs/TEST-DATA.md. The real terms
# these cases were first written with are library items, and writing them
# here would be the exact leak this file tests for - which is how they
# were caught.

def _hits(term, text):
    return lc.make_matcher([term])(text)


@pytest.mark.parametrize("term,text,why", [
    ("Compass", "the survey encompasses it", "embedded at the front"),
    ("Nightjar Post", "a Nightjar Poster on the wall", "embedded at the end"),
    ("Twin Lantern", "Twin Lanterns on the shelf", "a longer plural"),
    ("Moonfall", "Moonfallen Vol. 1", "a longer word sharing the stem"),
    ("Pixel Harbor", "the Pixel Harbormaster", "a compound"),
    ("Cinder Vale", "Cinder Valence readings", "a longer word after"),
    ("Amber Hollow", "the Chamber Hollow door", "leading letters before it"),
    ("Shadow-Hound Quest", "the Shadow-Hound Quests list", "a hyphenated term"),
])
def test_a_term_buried_in_a_longer_word_is_not_a_hit(term, text, why):
    assert _hits(term, text) == set(), why


@pytest.mark.parametrize("text,why", [
    ("I own Moonfall already", "plain prose"),
    ("the moonfall_comic row", "a machine_name joins words with underscores"),
    ("covers/moonfall-abc123.jpg", "a cover filename"),
    ("MOONFALL", "a different casing"),
    ('"Moonfall",', "inside quotes and a comma"),
    ("- Moonfall", "a markdown bullet"),
    ("(Moonfall)", "inside parentheses"),
    ("Moonfall.", "ending a sentence"),
    ("x=Moonfall", "after an operator"),
    ("Moonfall\nnext line", "at end of line"),
])
def test_a_real_leak_is_still_caught(text, why):
    # The direction that matters: the rule must not have got weaker.
    assert _hits("Moonfall", text) == {"Moonfall"}, why


def test_underscore_is_a_boundary_and_not_part_of_a_word():
    # The one deliberate difference from \w. machine_names are built by
    # joining words with underscores, so treating _ as a word character
    # would hide a title inside exactly the shape a leak takes here.
    assert _hits("Moonfall", "moonfall_comic") == {"Moonfall"}
    assert _hits("Moonfall", "moonfallcomic") == set()


@pytest.mark.parametrize("term,text", [
    ("Innkeeper's Ledger", "my Innkeeper's Ledger copy"),      # apostrophe
    ("S.H.A.D.O.W", "the S.H.A.D.O.W set"),                    # dots inside
    ("Learn C++", "Learn C++ today"),                          # ends in punctuation
    ("Café of Broken Clocks", "my Café of Broken Clocks copy"),  # an accent
])
def test_terms_carrying_punctuation_still_match(term, text):
    # The assertions are added per side rather than using \b, which would
    # assert the opposite of what is meant next to punctuation.
    assert _hits(term, text) == {term}


def test_a_whole_word_collision_is_still_a_hit():
    # Honest limit: word boundaries fix the EMBEDDED collisions, not the
    # ones where an ordinary English word is also a title. Those still
    # need a reword or an ALLOWED entry.
    assert _hits("Compass", "the compass of the survey") == {"Compass"}


def test_the_matcher_is_the_one_the_history_scanner_uses():
    # Same rule in both scanners, by construction rather than by copy: a
    # divergence would mean a term the working-tree check refuses could
    # pass the history check, or the reverse.
    #
    # Asserted on __module__ rather than on identity, because this file
    # loads leak_check by PATH while the history script imports it by
    # name - two module objects, so two function objects, from one source.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "leak_check_history", ROOT / "scripts" / "leak_check_history.py")
    history = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(history)
    assert history.make_matcher.__module__ == "leak_check"
    assert history.make_matcher(["Moonfall"])("moonfall_comic") == {"Moonfall"}
    assert history.make_matcher(["Moonfall"])("Moonfallen") == set()


def test_scan_reports_the_file_a_hit_came_from():
    sources = [("docs/a.md", "nothing here"),
               ("docs/b.md", "I own Moonfall")]
    hits, nfiles = lc.scan(sources, ["Moonfall"])
    assert nfiles == 2
    assert hits == {"Moonfall": ["docs/b.md"]}


def test_scan_counts_every_file_even_when_nothing_hits():
    hits, nfiles = lc.scan([("a", "x"), ("b", "y")], ["Moonfall"])
    assert (hits, nfiles) == ({}, 2)


# --- the frequency source ---------------------------------------------
# These scores are the gate's calibration. A wordfreq upgrade that moves
# them changes what the privacy check permits, so it has to fail here
# rather than pass quietly. If this test breaks after a deliberate
# upgrade, re-run the calibration in leak_check.py's COMMON_ZIPF comment
# and update both together.

def test_wordfreq_scores_are_stable():
    from wordfreq import zipf_frequency
    # Ordinary English, comfortably above any usable cutoff.
    assert zipf_frequency("space", "en") > 5.0
    assert zipf_frequency("legacy", "en") > 4.0
    # A rare token, comfortably below one. Invented, so no real term can
    # ever collide with it.
    assert zipf_frequency("zzqqxv", "en") == 0.0


# --- the common-word rule ---------------------------------------------

def test_an_ordinary_single_word_is_common():
    assert lc.is_common_word("space")
    assert lc.is_common_word("legacy")
    assert lc.is_common_word("prune")


def test_a_rare_single_word_is_not_common():
    # The rule is a frequency test, not a word-count test. A publisher's
    # brand name is one token and must stay checkable.
    assert not lc.is_common_word("zzqqxv")


def test_a_phrase_is_never_common_however_ordinary_its_words():
    # The threat-model line: a phrase of common words can name exactly
    # one work, so no phrase is ever exempt.
    assert not lc.is_common_word("the way")
    assert not lc.is_common_word("all systems red")
    assert not lc.is_common_word("a quiet life in harbors")


def test_a_hyphenated_or_punctuated_term_is_not_a_single_token():
    # Splitting on whitespace alone would call these one token. They can
    # carry as much meaning as a phrase, so they stay checked.
    assert not lc.is_common_word("science-fiction")
    assert not lc.is_common_word("o'reilly")


def test_partition_keeps_phrases_and_exempts_common_words(tmp_path,
                                                          monkeypatch):
    # "table" and "a quiet life" are deliberately NOT in ALLOWED: an
    # allowlisted term never reaches the new rule, so using one here
    # would test the wrong thing.
    monkeypatch.setattr(lc, "db_terms",
                        lambda path: {"table", "zzqqxv", "a quiet life"})
    monkeypatch.setattr(lc, "sheet_terms", lambda directory: set())
    kept, exempt = lc.partition_terms(tmp_path)
    assert kept == {"zzqqxv", "a quiet life"}
    assert exempt == {"table"}


def test_build_terms_is_the_kept_half(tmp_path, monkeypatch):
    # leak_check_history imports build_terms; its contract must not move.
    monkeypatch.setattr(lc, "db_terms",
                        lambda path: {"table", "zzqqxv", "a quiet life"})
    monkeypatch.setattr(lc, "sheet_terms", lambda directory: set())
    assert lc.build_terms(tmp_path) == lc.partition_terms(tmp_path)[0]


def test_the_allowlist_still_wins_over_everything(tmp_path, monkeypatch):
    # An ALLOWED phrase stays out of the term set; the rule is additive.
    monkeypatch.setattr(lc, "db_terms", lambda path: {"All Systems Red"})
    monkeypatch.setattr(lc, "sheet_terms", lambda directory: set())
    kept, exempt = lc.partition_terms(tmp_path)
    assert kept == set() and exempt == set()


def test_short_and_numeric_terms_are_still_dropped(tmp_path, monkeypatch):
    # The pre-existing filters are unchanged: under four characters, and
    # anything that is only digits and dots.
    monkeypatch.setattr(lc, "db_terms", lambda path: {"abc", "12.5", "zzqqxv"})
    monkeypatch.setattr(lc, "sheet_terms", lambda directory: set())
    assert lc.build_terms(tmp_path) == {"zzqqxv"}


def test_the_summary_counts_exempt_words_without_naming_them(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lc, "db_terms",
                        lambda path: {"table", "window", "zzqqxv"})
    monkeypatch.setattr(lc, "sheet_terms", lambda directory: set())
    monkeypatch.setattr(lc, "worktree_sources",
                        lambda root=lc.ROOT: [("a.md", "nothing here")])
    assert lc.main(()) == 0
    out = capsys.readouterr().out
    assert "2 single common words exempt" in out
    # The words themselves must never reach the terminal: printing them
    # rebuilds exactly the oracle this rule removes.
    assert "table" not in out and "window" not in out
