# Journal

Append-only. One primary entry per iteration; SALVAGE and ROTATION entries are additional. Never rewrite past entries (filling the current entry's Checkpoint field is completion, not a rewrite).

Heading grammar, exactly (fenced and indented here so this example is never mistaken for an entry by anything that counts or rotates them):

```
  ## iter <i>/<N> | <run-id> | <YYYY-MM-DD> | <task-id or AUDIT or EVALUATOR or RATCHET or WRAPUP or SALVAGE or ROTATION> | <done|blocked|audit|converged|salvage|rotation>
```

Write a real heading at column zero, never indented: the indentation above belongs to the example alone, and an indented heading is invisible to the rotation anchor and to the archive counter, so the entry under it is not counted and not rotated.

SALVAGE entries take status salvage; ROTATION entries take status rotation. An EVALUATOR entry records an evaluator-gate iteration: status audit when the run continues after the verdict, blocked on a terminal second REJECT, converged when that same iteration declares.

run-id is the first 8 characters of the session id, a hyphen, then the HHMMSS of started_at from the loop state frontmatter, so two runs in one session are told apart. Body fields, in order: Task, Changed, Checkpoint (the jeffy checkpoint commit hash, or none with the reason), Verification, Learnings, Next.

The closing entry that declares convergence carries the evaluator verdict in its Verification field: `Evaluator: PASS - <one-line summary>`, or `Evaluator: unavailable (<reason>)`. An earlier EVALUATOR entry records its own verdict the same way and never stands in for the closing one: the Stop hook reads the closing entry alone, so a run that gates early and keeps working re-invokes the gate at the declaration.

Closed tasks are recorded here as one line each (ID, title, closing evidence), because BACKLOG.md deletes them. Rotation: when this file exceeds 500 lines, move all but the last 10 entries to the end of JOURNAL-archive.md, appending to whatever that file already holds and never overwriting it, because the archive accumulates across every rotation and every run; create it only when it does not already exist, and record the rotation as a ROTATION entry.

## iter 1/10 | ceea220f-162935 | 2026-08-01 | SALVAGE | salvage

Task: Working tree was dirty at the start of iteration 1 - PLAN.md, BACKLOG.md and JOURNAL.md written by the /jeffy bootstrap, plus a .gitignore line for the transient loop state. Not interrupted work, but the salvage rule is unconditional on dirtiness and committing first makes this run's baseline unambiguous.
Changed: PLAN.md, BACKLOG.md, JOURNAL.md (new), .gitignore.
Checkpoint: 70adab5
Verification: `git status --porcelain` empty after the commit.
Learnings: The pre-run baseline for this run's diffstat is 4f696f0, the commit before the salvage.
Next: The iteration 1 audit.

## iter 1/10 | ceea220f-162935 | 2026-08-01 | AUDIT | audit

Task: First audit. Fill the Operating envelope, the Verify command and the Surface inventory, then probe breadth-first and file findings.

Changed: PLAN.md (envelope surfaces, verify command, 53 inventory rows, Lessons), BACKLOG.md (A1), .jeffy/probes/webapp-write-routes/probe.py, .jeffy/probes/pure-scoring/probe.py.

Checkpoint: pending

Verification: Two known-answer batteries were written and executed, not read.
  - `.jeffy/probes/pure-scoring/probe.py`: 26/26 passed. Closed-form checks on `matching.score` (the 0.75/0.25 weighting, both threshold boundaries at 0.85 and 0.60 and just below each), `series.collapse` (the docstring's own example, the gap case, unsorted, duplicate and empty input) and `classify.classify` (all four documented parameters varied, including the negative side: a bare "audio" substring must yield music, not audiobook). Every documented parameter changes the output; none is inert.
  - `.jeffy/probes/webapp-write-routes/probe.py`: 2/12 passed. The two happy paths hold; ten known answers fail. Filed as A1.
  Scores, claiming ONLY the 4 swept rows of 53 - the other 49 are unswept and this line is not a statement about them:
  - correctness: None. 26/26 known answers held on matching-score, classify-type and series-report.
  - error handling: Medium. A1, on webapp-write-routes.
  - testing: Medium, same root cause as A1 and not filed twice - the suite's 967 tests cover these routes' happy paths and read-status's rejection cases, but no test asserts a 4xx for a malformed body or an unknown item id on rating, type, choose or reopen, which is why the gap survived.
  - documentation, code quality, architecture: None on the swept rows. The module docstrings and inline comments in the code read this iteration are unusually precise and several record measured evidence for their design choices.
  - security, performance, dependency hygiene, observability, UX and accessibility: NOT SCORED. Their rows are unswept. The webapp host guard was read and looks correct (Host-header check before routing, closing DNS rebinding), but reading is not a sweep and webapp-host-guard stays `[ ]`.
  One suspected finding was withdrawn before filing: `scripts/windows/verify.ps1` signals failure with `Write-Error`, which is non-terminating by default and would have let a red suite exit 0 - but `scripts/windows/_common.ps1:3` sets `$ErrorActionPreference = "Stop"`, so it is terminating. No finding.

Learnings: The Verify command is written as its three underlying steps joined by `&&` rather than as a call to `verify.ps1`, because the wrapper's exit status depends on `$ErrorActionPreference` being set by a dot-sourced file. This project's privacy standing order binds every iteration: probes, fixtures and docs use invented titles from docs/TEST-DATA.md, never real library items, and the Verify command's leak_check is the gate that enforces it.

Next: A1 - close the write-route validation class at all four sites, with the probe battery as its acceptance check.
