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

Checkpoint: 3b9bcb8. Not a stall: this iteration added two probe batteries under .jeffy/probes/ and filed A1, so files beyond the ledger changed and a backlog item changed state.

Verification: Two known-answer batteries were written and executed, not read.
  - `.jeffy/probes/pure-scoring/probe.py`: 26/26 passed. Closed-form checks on `matching.score` (the 0.75/0.25 weighting, both threshold boundaries at 0.85 and 0.60 and just below each), `series.collapse` (the docstring's own example, the gap case, unsorted, duplicate and empty input) and `classify.classify` (all four documented parameters varied, including the negative side: a bare "audio" substring must yield music, not audiobook). Every documented parameter changes the output; none is inert.
  - `.jeffy/probes/webapp-write-routes/probe.py`: 2/12 passed. The two happy paths hold; ten known answers fail. Filed as A1.
  Scores, claiming ONLY the 4 swept rows of 53 - the other 49 are unswept and this line is not a statement about them:
  - correctness: None. 26/26 known answers held on matching-score, classify-type and series-report.
  - error handling: Medium. A1, on webapp-write-routes.
  - testing: Medium, same root cause as A1 and not filed twice - the suite's 967 tests cover these routes' happy paths and read-status's rejection cases, but no test asserts a 4xx for a malformed body or an unknown item id on rating, type, choose or reopen, which is why the gap survived.
  - documentation, code quality, architecture: None on the swept rows. The module docstrings and inline comments in the code read this iteration are unusually precise and several record measured evidence for their design choices.
  - security, performance, dependency hygiene, observability, UX and accessibility: NOT SCORED. Their rows are unswept. The webapp host guard was read and looks correct (Host-header check before routing, closing DNS rebinding), but reading is not a sweep and webapp-host-guard stays `[ ]`.
  Verify command at the end of this iteration: pytest 967 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 after two rewordings. `leak_check` first failed on ONE ordinary English noun in the bootstrapped PLAN.md prose - a substring false positive with no private data involved - and then failed again because the Lesson recording it quoted the word. Both fixed by rewording; nothing was added to `ALLOWED`, which would have blunted the gate for the whole repo.
  One suspected finding was withdrawn before filing: `scripts/windows/verify.ps1` signals failure with `Write-Error`, which is non-terminating by default and would have let a red suite exit 0 - but `scripts/windows/_common.ps1:3` sets `$ErrorActionPreference = "Stop"`, so it is terminating. No finding.

Learnings: The Verify command is written as its three underlying steps joined by `&&` rather than as a call to `verify.ps1`, because the wrapper's exit status depends on `$ErrorActionPreference` being set by a dot-sourced file. This project's privacy standing order binds every iteration: probes, fixtures and docs use invented titles from docs/TEST-DATA.md, never real library items, and the Verify command's leak_check is the gate that enforces it.

Next: A1 - close the write-route validation class at all four sites, with the probe battery as its acceptance check.

## iter 2/10 | ceea220f-162935 | 2026-08-01 | A1 | done

Task: A1 (Medium, runtime, error handling) - close the unvalidated-body / missing-existence-check class across the viewer's write routes.

Changed: humble_catalog/webapp/__init__.py (set_rating, set_type, reopen, choose; `_item_exists` moved above its first caller), tests/test_webapp.py (+7 regression tests), .jeffy/probes/webapp-write-routes/probe.py (+6 cases), BACKLOG.md (A1 deleted, Settled classes line added), PLAN.md (inventory row re-swept).

Checkpoint: b46399e. Not a stall: runtime code and tests changed, and A1 moved from open to settled. The webapp-write-routes inventory row was re-swept at this commit rather than flipped back to unswept - its implementing code changed, but the battery was re-run against the changed code in this same iteration, which is what a re-sweep is.

Verification: Acceptance check, both halves, run after the fix: `.jeffy/probes/webapp-write-routes/probe.py` exits 0 at 18/18, and `grep -n "request.get_json()\["` over the webapp returns nothing. The battery is strong enough to fail - run against the unfixed code first it scored 6/18, and the 6 that passed were the four preserved-contract guards plus the two happy paths. Verify command green: pytest 974 passed (967 before, +7 new), check_no_data_tracked exit 0, leak_check exit 0.
  Contract preserved, per change discipline: every previously-working call answers exactly as before. The star widget's 1..5 and its null-to-clear both still 200 (pinned by a new test and by the battery); `/reopen` still accepts a request with no body at all, which tests/test_webapp.py:329 depends on; `/choose` with a valid index still applies the highest-confidence candidate; the host guard still refuses foreign hosts before any body is parsed. Only three previously-unreachable-by-the-viewer outcomes changed: 500 became 400, silent 200 on a deleted id became 404, and an out-of-domain rating became 400 instead of being stored.
  Rating domain decision, recorded because it is a judgement and not a derivation: null or an int 1-5, taken from `stars()` in catalog.js, which renders 1..5 and clears with null. Out-of-domain values are refused rather than clamped - silently storing a value the user did not choose is the failure this task removes, so clamping would have reproduced it in a quieter form. Flagged to the user as the one non-mechanical choice in A1; no answer had arrived by this iteration, and 400 is also what the sibling read-status route does with a value outside its list.

Learnings: `bool` is a subclass of `int` in Python, so any range check on a JSON number has to exclude it explicitly or `true` stores as 1 star. A route that reads no body must not gain a body check when it gains an existence check - `/reopen` is posted bare by the existing suite, and requiring JSON there would have broken a caller while "fixing" it.

Next: The ledger is empty. Iteration 3 replenishes with a partial audit, sweeping unswept inventory rows - the highest-value unswept ones are webapp-host-guard, db-items and db-tags, since the storage layer is where a wrong write becomes permanent.

## iter 3/10 | ceea220f-162935 | 2026-08-01 | AUDIT | audit

Task: Partial replenishing audit. The ledger emptied when A1 closed, so this iteration sweeps the three highest-value unswept rows rather than re-probing swept ones: the storage layer, where a wrong write becomes permanent, and the host guard, which is the viewer's only security boundary.

Changed: .jeffy/probes/db-tags/probe.py, .jeffy/probes/webapp-host-guard/probe.py, .jeffy/probes/db-items/probe.py (all new), PLAN.md (three rows swept, one Lesson).

Checkpoint: e5c665d. Not a stall: three probe batteries were added under .jeffy/probes/ and three inventory rows changed state. No BACKLOG item changed state because the audit found nothing to file, which is the honest outcome of a clean sweep rather than a no-progress iteration.

Verification: 101 known-answer assertions across three rows, all executed, none a run-without-crash probe. No findings. The ledger stays empty.
  - db-tags, 42/42. Every documented promise of tags_to_json, tags_from_json, titleize, normalize_tags, rename_tag, delete_tag and bulk_user_tag. The `col` parameter is exercised at BOTH its values and changes the outcome as documented (GENRE titleizes an unknown tag, USER_TAGS keeps the typed casing), and `action` at both of its. The subtle contract held: a rename or delete rewrites the pre_edit snapshot copies too, so a later revert cannot resurrect the old spelling; an emptied array stores as NULL rather than '[]'; a bulk add snaps to the vocabulary spelling so a second casing cannot fork.
  - webapp-host-guard, 34/34. Weighted to the negative side, since a guard that accepted everything would pass a liveness probe. Refused: suffix and prefix tricks (localhost.evil.example.com, 127.0.0.1.evil.example.com, notlocalhost, localhosts), addresses that resolve to loopback but are not loopback NAMES (127.0.0.2, 127.1, 0.0.0.0, [::ffff:127.0.0.1]), userinfo and fragment smuggling, and an empty or absent Host, which fails closed. Accepted: the three loopback authorities in any casing, with or without a port, trimmed - so a `serve --port` override still works, which is why the port is deliberately unpinned. The guard runs before routing: a foreign host gets 403 on reads, writes, the static index and even an unknown route, and the refusal body names no catalog item.
  - db-items, 25/25. apply_hand_edit snapshots ONCE - a second edit does not re-snapshot, so revert returns to the enriched state rather than to the first typo, which is the difference between a recoverable and an unrecoverable edit. merge_items refuses equal or missing ids without deleting anything, fills only the survivor's EMPTY fields, and unions user_tags rather than fill-if-empty, because a merge is irreversible and hand-typed tags would otherwise be unrecoverable. The tombstone in `merges` is written so the next extract cannot resurrect the dropped machine_name.
  Scores, claiming ONLY the 7 swept rows of 53 - the other 46 are unswept and this line says nothing about them:
  - correctness: None across db-tags, db-items, webapp-host-guard, matching-score, classify-type, series-report.
  - security: None on webapp-host-guard specifically, now that it is actually swept rather than read. Still NOT SCORED for the project: the network-facing rows (extract-humble, sources-*, url-import, bundle-preview) are unswept, and they are where the adversarial surfaces live.
  - error handling: None on the swept rows. webapp-write-routes was settled in iteration 2.
  - testing: None on the swept rows - the project's own suite already covers these paths; the batteries found nothing it had missed.
  - architecture, code quality, documentation: None on the swept rows. The docstrings in db.py are precise enough to serve as the known answers directly, and every one of them proved true.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a PARTIAL audit and never counts toward convergence. Closeout is NOT entered: that requires a full fresh-evidence audit, and this one deliberately swept 3 rows of 53.
  Verify command: pytest 974 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 after one fix - the battery used a real genre name as a rename target and leak_check caught it. Replaced with an unmistakably invented one rather than widening ALLOWED.

Learnings: A plausible-sounding genre name is as dangerous as a plausible title - `leak_check` matches substrings, and the owner's genre vocabulary is private data too. Probe fixtures that need a database must use a fresh file per case; reusing one carried the previous case's rows into the next and tripped the machine_name UNIQUE constraint.

Next: Keep sweeping. 46 rows remain unswept and 7 iterations remain, so this run will end out of budget rather than converged. Highest value next: export-columns and stats-report (wrong numbers a user would act on), then the adversarial rows - parse-order, sources-base and url-import - since those are the only surfaces the envelope classes as adversarial.

## iter 4/10 | ceea220f-162935 | 2026-08-01 | AUDIT | audit

Task: Partial replenishing audit, reordered onto the adversarial rows. Iteration 3's scores left security NOT SCORED for the project because every network-facing row was unswept, and those are the only surfaces the envelope gives the full rubric. Swept url-import.

Changed: .jeffy/probes/url-import/probe.py (new), BACKLOG.md (B1, B2 filed), PLAN.md (row swept).

Checkpoint: pending

Verification: 25 known-answer assertions, 23 held, 2 failed and are filed. The two failures are reproductions, not guesses.
  - The scheme gate is solid: javascript:, data:, file:, ftp:, vbscript:, jar: and gopher: are all refused, in either casing, and so are the whitespace and control-character obfuscations (`java\tscript:`, `java\nscript:`, a leading-space variant) - urlparse strips those before the check, so they normalize to a rejected scheme rather than a permitted one. The comment at url_import.py:45 explaining why the raw string is parsed BEFORE the https:// prefix is added is exactly right, and the probe confirms the attack it describes does not work.
  - Handler routing is solid: `comicvine.gamespot.com.evil.example` and `evil-comicvine.gamespot.com.attacker.test` do NOT reach the Comic Vine handler, while a real subdomain does. The `host == domain or host.endswith("." + domain)` test is the correct shape.
  - B1 (High, security): `_fetch_html` re-checks the SCHEME after redirects but never the destination HOST. Reproduced with two real local HTTP servers rather than a mock, so this is the code's actual behaviour: server A 302s to server B on a different port, the fetch follows it, reads B's page and returns B's og:title as the candidate. A third-party page can therefore steer a GET at any address this machine can reach and get part of the response back. In envelope: the redirect Location is third-party content, which the envelope classes adversarial, so the full rubric applies and "a security vulnerability" is High by the rubric's own words. Filed rather than downgraded; the trigger does require the owner to paste a hostile or compromised URL, and that is stated in the finding rather than used to soften it.
  - B2 (Low, error handling): `normalize_url("example.com:8080/book")` raises "unsupported URL scheme 'example.com'" - urlparse reads a hostname followed by a colon as a scheme, so the diagnosis names the host as the offender.
  Scores, claiming ONLY the 8 swept rows of 53 - the other 45 are unswept:
  - security: High, on url-import (B1). This is the first iteration in which security is scored at all, and it is scored on one row, not on the project: extract-humble, sources-base, sources-books, sources-media, bundle-preview and covers-store are all still unswept and all still adversarial.
  - error handling: Low, on url-import (B2). None elsewhere among the swept rows.
  - correctness: None across the swept rows.
  - architecture, code quality, documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  Partial audit; never counts toward convergence, and closeout is NOT entered - it requires a full audit with zero High and zero Medium, and this one found a High.
  Verify command: pytest 974 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: Reproduce a network guard with real servers, not a mocked session: a mock proves what the mock was written to do, whereas two `http.server` instances on ephemeral ports prove what the code does, cost about twenty lines, and run in well under a second. A battery must assert the DESIRED answer, not the observed one - the redirect case was first written to expect the vulnerable behaviour and would then have certified the defect as correct forever.

Next: B1 is the top unblocked item and the only High. Fixing it means checking each redirect hop's resolved address, which needs `allow_redirects=False` and an explicit loop, because a final-URL-only check still lets an intermediate hop reach an internal service.
