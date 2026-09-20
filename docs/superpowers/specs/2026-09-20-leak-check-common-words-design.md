# Common words in the leak check — design

Date: 2026-09-20
Issue: #62

## Problem

`scripts/leak_check.py` searches the repo for every name, author,
narrator, genre, series, publisher and bundle name in the catalog, and
fails on any whole-word hit not in `ALLOWED`. The term set is derived at
runtime, so it grows with the library: a large harvest adds on the order
of a couple of hundred terms.

Two consequences, both already visible.

**Ordinary words become forbidden retroactively.** A word that is
perfectly good English, in code that was clean when it was written,
starts failing the gate the moment the catalog happens to contain a term
equal to it. On 2026-09-20 a JavaScript operator used to discard the
value of a forced layout read did exactly this, in a line written that
afternoon, and had to be reworded to a method call. Nothing about the
code referred to the library. The check was defending against the wrong
thing.

**The allowlist is itself a disclosure.** `ALLOWED` is tracked and
public. Measured the day this was written: of its 79 entries, **71 are
current catalog terms**. Each one asserts "some term in this catalog
equals this string", and the explanatory comments do worse — they record
which *kind* of term each was, turning a weak signal into a usable one.
The list is the oracle it was meant to avoid, and it grows every time a
harvest introduces a new collision.

So the two obvious fixes pull against each other: accepting common words
wholesale blinds the gate, and writing every exception down publishes a
little more of the library each time.

## Threat model

Settled before the design, because it decides what is permissible.

**What the check defends against is someone reconstructing the library.**
Individual weak signals are acceptable: that some term here contains the
word "space", or that the owner owns something published by O'Reilly,
tells a reader essentially nothing. What is not acceptable is a title, an
author, a bundle name, or a set of words distinctive enough to name one
work.

Two things follow directly.

A commonness rule is permitted, because a lone common word is a weak
signal by definition. And the rule must judge the **whole term**, never
token by token: "space" is weak, but a phrase of five common words can
name exactly one book.

## The asymmetry this rests on

| | |
|---|---|
| Terms the gate searches for | 5,675 |
| Single-word terms | 409 (7%) |
| Multi-word terms | 5,266 (92%) |
| `ALLOWED` entries that are catalog terms | 71 of 79 |
| Of those, single words | 49 (69%) |

A frequency rule can only judge single words. That is **7% of the
catalog** — but **69% of the collisions that have actually happened**,
because collisions happen with common words and common words are usually
one word.

So the rule buys a small blind spot and retires most of the maintenance.

## Decisions

| Question | Decision | Rejected |
|---|---|---|
| Source of "common"? | `wordfreq`, pinned exactly | A vendored wordlist (a large data file someone must curate); a structural heuristic (exempts rare single words too) |
| What may be exempted? | Single-word terms only | Phrases by combined score — `wordfreq` scores a phrase by combining tokens, so a three-common-word title scores like any other three common words, which is exactly what the threat model forbids |
| Where do phrase exceptions live? | `ALLOWED`, as today | An untracked local file: not reproducible on a clone or in CI, and a reviewer cannot see what is exempted |
| Existing single-word entries? | Removed from `ALLOWED`, but only those the calibrated rule actually exempts | Removing every one-word entry on shape alone — a rare brand name is one word and scores nowhere near the cutoff |
| Gate behaviour | Unchanged: exit 1 on any unexplained hit | A warn tier; a check that can be ignored stops being read |

## Design

### The rule

One predicate, applied where `build_terms()` already subtracts `ALLOWED`:

    a term is exempt if it is a single token
      AND zipf_frequency(term, "en") >= COMMON_ZIPF

`ALLOWED` continues to apply, unchanged, to everything else. Nothing
about the scan, the word-boundary matching, the file exclusions or the
exit code changes.

`COMMON_ZIPF` is calibrated in step 1 of implementation rather than
guessed. The calibration is a measurement, not a preference: score all
409 single-word terms, and pick the lowest threshold at which every
word that has ever needed an `ALLOWED` entry is exempt while the count
of newly-exempt terms stays small. Record the chosen number, the date,
and both counts in a comment beside it.

### Pinning, and the version-drift risk

`wordfreq` is a dev dependency, pinned to an exact version rather than a
floor:

    dev = ["pytest>=8.0", "wordfreq==3.1.1"]

A floor would let a future release move a word across that cutoff and
silently widen or narrow the gate. The pin makes that a deliberate
upgrade.

To make it loud as well as deliberate, a test asserts the scores of a
handful of fixed words on either side of that cutoff. A version bump
that moves them fails in CI with a diff, rather than changing what the
privacy gate permits without anyone noticing. This is the one test here
that exists to catch a *dependency* changing, not our code.

### Blind-spot reporting

The run summary gains one line (shape, not measured numbers — the second
count can never exceed the 409 single-word terms):

    checked 5,583 terms against 309 files
    N single common words exempt by frequency

A count, never the words — printing them would rebuild the oracle in the
terminal. It makes the size of the blindness visible rather than
assumed, and it moves when the library does.

### The allowlist after this

An entry is removed **only if the rule actually exempts it**, checked
against the calibrated threshold rather than assumed from its shape.
That distinction matters: not every single word is a common one. A
publisher's brand name is a single token that scores far below any
usable threshold, so the rule does not cover it and its entry has to
stay — dropping it because it is "one word" would reopen a gap.

So, after calibration:

- **Removed** — single-word entries the rule exempts. At most 49, the
  exact number measured and recorded at calibration.
- **Kept, single word** — rare tokens the rule does not reach: brand
  names, invented words. These stay exactly as they are.
- **Kept, phrases** — the 22 multi-word entries. This is the part that
  still grows, at roughly a tenth of the old rate.
- **Kept, public house examples** — the Murderbot fixture data, Dune.
  Deliberately public, and the fixtures need them.

Comments are rewritten at the same time. They record *that* an entry is
an ordinary-prose collision and whether it is reachable in pushed
history; they stop recording which kind of catalog term it was. A future
entry follows the same rule.

The pruning shrinks the public oracle by however many of the 49 the rule
covers. It does not undo anything: those entries are in pushed history
permanently, and per the standing order in `CLAUDE.md`, anything pushed
is public. The win is that the list stops growing, not that the past is
retracted.

## What this does not protect

Stated plainly, because a gate whose limits are unwritten gets trusted
past them.

A title that is exactly one common English word is invisible to the
check, permanently. If such a title is ever written into committed text,
nothing will object. Under the threat model above this is accepted: one
common word cannot reconstruct anything, and the word is
indistinguishable from the same word used as itself — which is the very
ambiguity that makes it weak.

Multi-word titles, authors, series and bundle names are unaffected.
They are 92% of the term set and all of the distinctive disclosure.

### Worked example: this spec

Writing this document tripped the check. A two-word phrase in its own
prose — ordinary English, used as itself, about the calibration cutoff
and not about any book — matched a catalog term, and the sentences were
reworded before it would commit.

That is the residual burden, demonstrated on the first document written
after the design was agreed. The phrase is two words, so the rule
proposed here would **not** have exempted it, and the wording had to
change exactly as it does today.

It is the right outcome rather than a gap. A two-word phrase is far
closer to naming one work than a single word is, so the gate should
hesitate over it, and rewording prose costs a minute. The design's claim
is narrower than "collisions stop": single-word collisions stop, and
those were 69% of the ones that had happened.

## Testing

`leak_check` is tested by `tests/test_leak_check.py` today; this extends
it.

- A single common word in a file does not fail the check.
- A single **rare** word still fails it — the rule is a frequency test,
  not a word-count test.
- A multi-word phrase of entirely common words still fails. This is the
  test that pins the threat model: it is the "All Systems Red scores
  like any three common words" case.
- The exemption applies to the same whole-word matching as everything
  else, not to substrings.
- The summary line reports the exempt count and never the words.
- Fixed scores for a few words on either side of the cutoff, so a
  `wordfreq` upgrade fails loudly.
- `leak_check_history.py` imports `ALLOWED` and `build_terms()`; a test
  that both still import and run keeps that contract.

Calibrating `COMMON_ZIPF` is not a test. It is a measurement recorded in
a comment, and rerunning it is how a future maintainer checks it.

## Documentation

- `CLAUDE.md`, Privacy section: the standing order is unchanged, but the
  sentence about rewording collisions gains the exception — single
  common words are handled automatically and need no entry.
- `docs/BACKLOG.md`, Privacy section: the three-check table gains a note
  that `leak_check` exempts single common words by frequency, with a
  pointer here.
- `README.md`, Development: `wordfreq` is a dev dependency, so a
  contributor running `verify` needs it; the install line already covers
  it via `.[dev]`.

## Out of scope

- **Changing what the gate scans.** File exclusions, word-boundary
  matching and the term-building queries are untouched.
- **`check_no_data_tracked.py`.** It filters paths, not content, and has
  no collision problem.
- **Retroactively cleaning history.** The removed entries stay in pushed
  commits; nothing here rewrites history, and per `CLAUDE.md` nothing
  should.
- **A phrase-level commonness rule.** Rejected above on threat-model
  grounds. If the 22 phrase entries ever become a maintenance burden,
  that is a new question with a different answer.
