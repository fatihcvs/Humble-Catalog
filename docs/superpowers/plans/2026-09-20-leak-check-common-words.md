# Common words in the leak check — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `leak_check.py` failing on ordinary single English words,
without growing a public allowlist that describes the library.

**Architecture:** One predicate — a term is exempt if it is a single
token scoring at or above a calibrated `wordfreq` cutoff. It is applied
in `build_terms()`, beside the existing `ALLOWED` subtraction. Phrases
are untouched. `ALLOWED` then loses the single-word entries the rule
covers.

**Tech Stack:** Python 3.12, pytest, `wordfreq` (new, pinned exactly).

**Spec:** `docs/superpowers/specs/2026-09-20-leak-check-common-words-design.md`

## Global Constraints

- **`wordfreq==3.1.1`** — pinned exactly in `pyproject.toml`'s `dev`
  extra, never a floor. A floor lets a release move a word across the
  cutoff and silently change what the privacy gate permits.
- **Single tokens only.** Never exempt a multi-word term, whatever it
  scores. A phrase of common words can name exactly one work.
- **Never print an exempted term.** Counts only, in every output path.
  Printing them rebuilds in the terminal the oracle this removes.
- **`ALLOWED` and `build_terms()` stay importable** with their current
  names and signatures. `scripts/leak_check_history.py` imports both, and
  nothing at module scope may read the database or exit.
- **The gate stays a hard gate.** `main()` returns 1 on any unexplained
  hit. No warn tier.
- **Say "the cutoff" in prose, not the usual synonym for it.** The
  definite article plus that synonym (the one beginning "thresh") is
  itself a catalog term, so writing the pair in any tracked file fails
  the check — it is a two-word phrase, which this rule deliberately does
  not exempt. The bare constant name `COMMON_ZIPF` avoids the question
  entirely, and a lone occurrence of the word is a single token and fine.
  This is not a hypothetical: the design doc tripped on it and four
  sentences were reworded.
- Run `.venv/Scripts/python -m pytest -q` before every commit;
  `.venv/Scripts/python scripts/leak_check.py` is run by the pre-commit
  hook and must be clean.

## File structure

| File | Responsibility | Change |
|---|---|---|
| `pyproject.toml` | Dependency pins | Add `wordfreq==3.1.1` to `dev` |
| `scripts/leak_check.py` | The gate | Add `COMMON_ZIPF`, `is_common_word()`, `partition_terms()`; `build_terms()` delegates; `main()` reports the exempt count; `ALLOWED` pruned |
| `tests/test_leak_check.py` | Its tests | New cases for the rule, the report line, and score stability |
| `CLAUDE.md` | Standing order | Note the exemption beside the rewording instruction |
| `docs/BACKLOG.md` | Privacy section | Note it in the three-check table |
| `README.md` | Development | No change needed — `.[dev]` already installs it; verify only |

---

### Task 1: Pin `wordfreq`, and make a version bump fail loudly

**Files:**
- Modify: `pyproject.toml` (the `[project.optional-dependencies]` block)
- Test: `tests/test_leak_check.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `wordfreq.zipf_frequency(word: str, lang: str) -> float`
  available in the venv, pinned at 3.1.1.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_leak_check.py`:

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -k wordfreq_scores -q
```

Expected: FAIL, `ModuleNotFoundError: No module named 'wordfreq'`.

- [ ] **Step 3: Add the pin**

In `pyproject.toml`, change the dev extra to:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "wordfreq==3.1.1"]
```

- [ ] **Step 4: Install it**

```bash
.venv/Scripts/python -m pip install -e ".[dev]"
```

(`.venv/Scripts/pip` exits 1 silently in this venv — always use
`python -m pip`.)

- [ ] **Step 5: Run the test and watch it pass**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -k wordfreq_scores -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/test_leak_check.py
git commit -m "chore: pin wordfreq for the leak check's common-word rule (#62)"
```

---

### Task 2: `is_common_word()`, with a calibrated cutoff

**Files:**
- Modify: `scripts/leak_check.py` (new constant and function, placed
  directly below the `ALLOWED` block)
- Test: `tests/test_leak_check.py`

**Interfaces:**
- Consumes: `wordfreq.zipf_frequency` from Task 1.
- Produces: `COMMON_ZIPF: float` and
  `is_common_word(term: str) -> bool`, used by Task 3.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_leak_check.py`:

```python
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
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -k common -q
```

Expected: FAIL, `AttributeError: module 'leak_check' has no attribute
'is_common_word'`.

- [ ] **Step 3: Calibrate the cutoff**

This produces the number the next step hard-codes. Run:

```bash
.venv/Scripts/python - <<'PY'
import sys, pathlib
from collections import Counter
sys.path.insert(0, str(pathlib.Path("scripts").resolve()))
from wordfreq import zipf_frequency
import leak_check as lc

raw = lc.db_terms(lc.ROOT / "catalog.db") | lc.sheet_terms(
    lc.ROOT / "Reference spreadsheets")
raw = {str(t).strip() for t in raw if t and str(t).strip()}
raw = {t for t in raw if len(t) >= 4 and not t.replace(".", "").isdigit()}
single = [t for t in raw if len(t.split()) == 1 and t.isalpha()]
allow1 = [t for t in lc.ALLOWED if len(t.split()) == 1 and t.isalpha()]

print(f"single-word terms: {len(single)}   single-word ALLOWED: {len(allow1)}")
print(f"{'cutoff':>7} {'terms exempt':>13} {'ALLOWED covered':>16}")
for i in range(25, 56):
    c = i / 10
    print(f"{c:>7.1f} {sum(zipf_frequency(t,'en') >= c for t in single):>13}"
          f" {sum(zipf_frequency(t,'en') >= c for t in allow1):>16}")
PY
```

Choose the **highest** cutoff that still covers every single-word
`ALLOWED` entry which is ordinary English — highest, because a higher
cutoff exempts fewer terms and so leaves the smaller blind spot. If no
single value covers them all, the uncovered ones are rare tokens that
keep their entries (Task 5 expects this).

Record the chosen value and both counts. Do not print any term.

- [ ] **Step 4: Write the implementation**

In `scripts/leak_check.py`, directly below the closing `]}` of `ALLOWED`:

```python
from wordfreq import zipf_frequency

# Ordinary single words are not disclosures.
#
# The term set is derived from the live catalog, so it grows as the
# library does, and a perfectly good English word becomes forbidden the
# moment some term happens to equal it -- retroactively, in code that was
# clean when it was written. Writing each one into ALLOWED instead
# published a little more of the library every time: 71 of its 79 entries
# were catalog terms when this was added.
#
# So a single token that is common English is exempt. A lone common word
# cannot reconstruct anything, and is indistinguishable from the same
# word used as itself -- which is exactly what makes it weak.
#
# SINGLE TOKENS ONLY, whatever the score. wordfreq will happily rate a
# phrase by combining its tokens, which rates a three-common-word title
# like any other three common words; a phrase can name exactly one work,
# so no phrase is ever exempt. See the design doc:
# docs/superpowers/specs/2026-09-20-leak-check-common-words-design.md
#
# Calibrated <DATE>: at this value, <N> of the <M> single-word terms in
# the catalog are exempt, and it covers every ordinary-English entry that
# ALLOWED had accumulated. Re-run the calibration in that design doc when
# upgrading wordfreq; tests/test_leak_check.py pins scores either side of
# it so a bump cannot move the gate quietly.
COMMON_ZIPF = <CHOSEN VALUE>


def is_common_word(term):
    """True if `term` is a single ordinary English word.

    `str.isalpha()` does the tokenising: it is false for anything with a
    space, hyphen, apostrophe or digit in it, so "science-fiction" and
    "o'reilly" are not single tokens however common their parts. It is
    true for non-ASCII letters, which is intended -- an accented word is
    still one word.
    """
    return term.isalpha() and zipf_frequency(term, "en") >= COMMON_ZIPF
```

Replace `<CHOSEN VALUE>`, `<DATE>`, `<N>` and `<M>` with the numbers from
Step 3. Note `zipf_frequency` is imported at module scope — that is safe
here because it reads no database and cannot exit.

- [ ] **Step 5: Run the tests and watch them pass**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -k common -q
```

Expected: PASS. If `test_an_ordinary_single_word_is_common` fails, the
cutoff came out too high for one of those three words — re-read Step 3's
rule and lower it.

- [ ] **Step 6: Commit**

```bash
git add scripts/leak_check.py tests/test_leak_check.py
git commit -m "feat(privacy): a common-word predicate for the leak check (#62)"
```

---

### Task 3: Apply the rule in `build_terms()`

**Files:**
- Modify: `scripts/leak_check.py` (`build_terms`, replaced by
  `partition_terms` plus a thin `build_terms`)
- Test: `tests/test_leak_check.py`

**Interfaces:**
- Consumes: `is_common_word()` from Task 2.
- Produces: `partition_terms(root=ROOT) -> tuple[set[str], set[str]]`
  returning `(kept, exempt)`; `build_terms(root=ROOT) -> set[str]`
  unchanged in name, signature and meaning (it is `kept`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_leak_check.py`:

```python
def test_partition_keeps_phrases_and_exempts_common_words(tmp_path,
                                                          monkeypatch):
    # Drive the real partition over a known term set rather than the
    # owner's catalog, so the assertion is about the rule and not about
    # what happens to be owned today.
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
```

- [ ] **Step 2: Run them and watch them fail**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -k "partition or kept_half or allowlist_still_wins or still_dropped" -q
```

Expected: FAIL, `AttributeError: module 'leak_check' has no attribute
'partition_terms'`.

- [ ] **Step 3: Write the implementation**

Replace the whole existing `build_terms` function with:

```python
def partition_terms(root=ROOT):
    """(terms to search for, terms exempted as common words).

    Both halves are needed: the first is the gate, the second is only
    ever counted, so the run can report how large its blind spot is
    without naming anything in it.

    Empty first half means there is nothing to check against -- no
    catalog.db and no spreadsheets -- which callers must report rather
    than treat as a pass.
    """
    terms = db_terms(root / "catalog.db") | sheet_terms(
        root / "Reference spreadsheets")
    terms = {t.strip() for t in terms if t and str(t).strip()}
    terms = {t for t in terms
             if len(t) >= 4 and not t.replace(".", "").isdigit()
             and t.lower() not in ALLOWED}
    exempt = {t for t in terms if is_common_word(t)}
    return terms - exempt, exempt


def build_terms(root=ROOT):
    """Every private term to search for, allowlist and common words
    already applied.

    Kept as its own name and signature because leak_check_history.py
    imports it.
    """
    return partition_terms(root)[0]
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -q
```

Expected: PASS, whole file.

- [ ] **Step 5: Check the real gate still runs clean**

```bash
.venv/Scripts/python scripts/leak_check.py
.venv/Scripts/python scripts/leak_check_history.py --help
```

Expected: `clean` from the first; the second must still import (it
imports `ALLOWED` and `build_terms`).

- [ ] **Step 6: Commit**

```bash
git add scripts/leak_check.py tests/test_leak_check.py
git commit -m "feat(privacy): exempt single common words from the leak check (#62)"
```

---

### Task 4: Report the size of the blind spot

**Files:**
- Modify: `scripts/leak_check.py` (`main`)
- Test: `tests/test_leak_check.py`

**Interfaces:**
- Consumes: `partition_terms()` from Task 3.
- Produces: nothing new; `main(argv=())` keeps its signature and exit
  codes.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_leak_check.py`:

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -k summary_counts -q
```

Expected: FAIL — the line is not printed.

- [ ] **Step 3: Write the implementation**

In `main()`, replace the line `terms = build_terms()` with:

```python
    terms, exempt = partition_terms()
```

and, immediately after the existing `print(f"checked {len(terms)} ...")`
call, add:

```python
    # A count, never the words. The size of the blind spot should be
    # visible rather than assumed, and it moves as the library grows.
    if exempt:
        print(f"{len(exempt)} single common words exempt by frequency")
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -q
```

Expected: PASS.

- [ ] **Step 5: See it on the real catalog**

```bash
.venv/Scripts/python scripts/leak_check.py
```

Expected: `clean`, now with the exempt count on its own line. Sanity-check
that the count is at most the single-word term total from Task 2 Step 3.

- [ ] **Step 6: Commit**

```bash
git add scripts/leak_check.py tests/test_leak_check.py
git commit -m "feat(privacy): report how many terms the common-word rule exempts (#62)"
```

---

### Task 5: Prune `ALLOWED` to what the rule does not cover

**Files:**
- Modify: `scripts/leak_check.py` (the `ALLOWED` block and its comments)
- Test: `tests/test_leak_check.py`

**Interfaces:**
- Consumes: `is_common_word()` from Task 2.
- Produces: a smaller `ALLOWED`; no signature changes.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_leak_check.py`:

```python
def test_no_allowlist_entry_is_one_the_rule_already_covers():
    # Every redundant entry is pure disclosure: it says "a term here
    # equals this" and buys nothing, because the common-word rule would
    # have exempted it anyway. Keeping the list minimal is the point of
    # the rule.
    redundant = sorted(t for t in lc.ALLOWED if lc.is_common_word(t))
    assert redundant == [], redundant
```

- [ ] **Step 2: Run it and watch it fail**

```bash
.venv/Scripts/python -m pytest tests/test_leak_check.py -k no_allowlist_entry -q
```

Expected: FAIL, listing the entries to remove. That list is the work.

- [ ] **Step 3: Remove exactly those entries**

Delete from `ALLOWED` every entry the failure named, and nothing else.
Entries that are one word but were **not** named are rare tokens the rule
does not reach — brand names especially — and they stay.

- [ ] **Step 4: Rewrite the surviving comments**

The comments currently record which *kind* of catalog term each entry
was — a genre label, a series name, the literal word in a title. That is
the part that turns a weak signal into a usable one. Rewrite each
surviving group to say only:

- that it is an ordinary-prose collision, or a public house example;
- whether it is reachable in pushed history and so cannot be reworded;
- the date it was added.

Keep the block's existing header comment explaining the two kinds of
entry and the cost of the list, and add one line pointing at
`COMMON_ZIPF` for the single-word case.

- [ ] **Step 5: Run everything**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python scripts/leak_check.py
```

Expected: all tests pass; the gate prints `clean`. If a removed entry
causes a new hit, it was not actually covered by the rule — put it back
and work out why the test named it.

- [ ] **Step 6: Commit**

```bash
git add scripts/leak_check.py tests/test_leak_check.py
git commit -m "refactor(privacy): drop allowlist entries the common-word rule covers (#62)"
```

---

### Task 6: Documentation

**Files:**
- Modify: `CLAUDE.md` (Privacy section), `docs/BACKLOG.md` (Privacy
  section)
- Test: none of its own — see Step 3

**Interfaces:**
- Consumes: the finished behaviour from Tasks 3–5.
- Produces: nothing code depends on.

- [ ] **Step 1: Update `CLAUDE.md`**

In the Privacy standing order, the bullet that says to run
`leak_check.py` after adding tests, fixtures or docs keeps its meaning.
Add one sentence to it:

> A single ordinary English word is exempt automatically and needs no
> allowlist entry; a phrase is not, however common its words, so a fresh
> phrase collision is still reworded.

- [ ] **Step 2: Update `docs/BACKLOG.md`**

In the Privacy section's "Acting on a hit" list, the first bullet
currently says to reword a term in the working tree. Add after it:

> Single common words never reach this: `leak_check.py` exempts a term
> that is one ordinary English word above `COMMON_ZIPF`, and reports how
> many it exempted. Design:
> `docs/superpowers/specs/2026-09-20-leak-check-common-words-design.md`.

- [ ] **Step 3: Verify the docs did not themselves trip the gate**

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python scripts/leak_check.py
.venv/Scripts/python scripts/check_no_data_tracked.py
```

Expected: all clean. Writing prose about this subject is exactly how the
design doc tripped the check on a two-word phrase — if it happens again,
reword rather than adding an entry.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/BACKLOG.md
git commit -m "docs: record the common-word exemption in the privacy rules (#62)"
```

---

## Done when

- `.venv/Scripts/python -m pytest -q` passes.
- `.venv/Scripts/python scripts/leak_check.py` prints `clean` and an
  exempt count.
- `.venv/Scripts/python scripts/check_no_data_tracked.py` prints clean.
- `scripts/leak_check_history.py` still imports and runs.
- No `ALLOWED` entry satisfies `is_common_word()`.
- CI is green on both Linux and Windows. `wordfreq` installs from the
  `dev` extra, and the gate reports `SKIPPED` there for want of a
  catalog, as it does today.
