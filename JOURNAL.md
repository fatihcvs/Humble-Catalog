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

## iter 8/15 | affcbaff-100429 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit. The ledger emptied when E2 closed, so this iteration swept titles-clean and titles-series - pure value-computing code, where the Method's warning about liveness probes bites hardest, since every defect in that file returns a plausible string or a plausible boolean.

Changed: .jeffy/probes/titles/probe.py (new, 84 cases covering both rows), PLAN.md (two rows swept), BACKLOG.md (F1 Medium filed).

Checkpoint: cfe9b54. Not a stall: a probe battery was added under .jeffy/probes/, two inventory rows changed state, the journal rotated, and F1 was filed.

Verification: 84 known-answer assertions, 83 held.
  - The battery was aimed at what the 23 existing tests do not reach: the negative side of each stripping rule, the boundaries, and the parameters not varied. Several of those held and are worth naming, because they are the cases most likely to be wrong and are not - a reversed range normalizes low-to-high, a marker overrides `number_hint` rather than being overridden by it, a hint cannot invent a series for an empty title, and three punctuation spellings of one initialism merge while the one pair that differs by more than punctuation stays apart.
  - F1, Medium, reproduced end to end rather than at the unit. `sequel_mismatch` compares the trailing numeral as text, so `widget quest 2` and `widget quest ii` read as a sequel pair. With `Widget Quest 2` in the pool, `game_match.classify_game` reports an offered `Widget Quest II` as `new`, and `Final Chapter 4` against `Final Chapter IV` likewise.
  - The severity rests on what the rule DISPLACED, which is why the scores were measured rather than assumed: those pairs score 89.7 and 83.9, between GAME_POSSIBLE 80 and GAME_OWNED 92. Without the rule the report would say `possible` - an honest "check this one". With it the report says `new`, a confident claim about the exact question a purchase decision asks. That is a Medium: a wrong answer on a plausible in-envelope pairing, not a systematic one.
  - A second finding was written into the battery and then withdrawn, for the second time this run on the same kind of mistake. The numeral test is a character class, so an ordinary word spelled from roman-numeral letters - "mix" - is read as a numeral, and the battery asserted the contract-literal answer that it should not be. Tracing classify_game showed that answer would be WORSE: True sends a genuinely different product straight to `new`, which is correct, while False would hand the pair to the scorer, where 88.9 lands in the possible band and the report would hedge about a game the user does not own. The mechanism is accidental and the outcome is right, so the assertion was corrected to match and nothing was filed.
  - Scores, claiming ONLY the 21 swept rows of 57 - the other 36 are unswept:
  - correctness: MEDIUM, F1, on the swept rows.
  - architecture, code quality, documentation: None on the swept rows. This module is unusually well documented: several comments record the measurement that chose the rule, including why a range is tried before a bare volume and why sorted tokens must never reach the sequel test.
  - testing: None on the swept rows - the 23 existing tests are known-answer tests, not liveness probes, which is why this sweep found one finding rather than several.
  - security, error handling: not applicable to these rows; the functions take strings and return strings, reach nothing and raise nothing.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 36 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  Verify command: pytest 1115 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: Trace the consumer before asserting a desired answer, especially when the docstring gives a clean literal one. Twice this run a probe has asserted what a function's own contract says it should return, and twice the consumer showed that answer would degrade behaviour - the cover path that is a URL rather than a directory, and now a numeral test whose accidental breadth produces the right verdict. The docstring says what the function claims; only the caller says what the answer is for.

Next: Iteration 9 executes F1. Compare the trailing tokens by numeric value when both parse as numerals and keep the text comparison otherwise; the battery holds the differential at 1 NUM failure, and the acceptance check also asks for an end-to-end classify_game assertion, because the unit answer is not what the user meets.

## iter 9/15 | affcbaff-100429 | 2026-08-02 | F1 | done

Task: F1 (Medium, runtime, correctness) - a digit and a roman numeral naming the same sequel number read as a sequel PAIR, sending a game the user owns to "new".

Changed: humble_catalog/titles.py (`_numeral_value`, `sequel_mismatch` compares by value, both docstrings), tests/test_game_match.py (+11), .jeffy/probes/titles/probe.py (the NUM case now holds), PLAN.md (titles-clean re-swept), BACKLOG.md (F1 deleted).

Checkpoint: b3d8ad7. Not a stall: runtime code and tests changed, and F1 moved from open to closed.

Verification: The filed reproduction was re-run first, before any edit, and still stood at 83/84 with the one NUM failure.
  - Acceptance check, both halves. `.jeffy/probes/titles/probe.py` exits 0 at 84/84, and the end-to-end half holds: with `Widget Quest 2` in the pool an offered `Widget Quest II` now classifies as `possible` rather than `new`, and `Final Chapter IV` against `Final Chapter 4` likewise.
  - `possible` rather than `owned` is the honest outcome and was not forced further. The two titles still differ as text, so the score stays at 89.7, below the 92 the report needs to claim ownership. The band exists for exactly this: the report asks the user to check. What it must never do is state that they do not own it.
  - The rule is not blunted, which is the risk a fix like this carries. `Widget Quest III` and `Widget Quest 3` against an owned `Widget Quest 2` both still classify as `new`, and so does the bare `Widget Quest`; those three are the control and they pass against both the fixed and the unfixed code.
  - Differential: 6 of the 11 new tests fail against the unfixed titles.py, restored from HEAD. That run was possible only because the tests deliberately do not import `_numeral_value`, the one name this fix adds - the same trap that made the differential unmeasurable in iterations 3 and 6, avoided by testing through `sequel_mismatch` and `classify_game`, which existed before.
  - The roman reading is deliberately not restricted to canonical spellings, and the reason is the case withdrawn in iteration 8: an ordinary word spelled from those letters reads as some number, that number differs from the other side's, and the verdict stays `new` - which is the correct answer for a different product. Restricting to canonical spellings would have changed that outcome for no gain, and `mix` is canonical roman for 1009 anyway.
  - Contract preserved. `sequel_mismatch` keeps its signature and its meaning; only the comparison of two numerals changes, from text to value. Its docstring and `clean_game_title`'s cross-reference were updated in this iteration. `_NUMERAL` has exactly one user, `sequel_mismatch`, and `sequel_mismatch` has exactly one caller, game_match.py:108, both checked before the edit.
  - Verify command: pytest 1126 passed (exit 0), up from 1115 with 11 new tests; check_no_data_tracked exit 0; leak_check exit 0.

Learnings: When a fix adds a name, keep that name out of the regression tests if the differential is meant to run against the reverted module - test through the functions that already existed. This is the third iteration this run to meet that trap and the first to route around it deliberately.

Next: The ledger is empty with 6 iterations left. The evaluator gate still does not apply, because no FULL audit has been recorded this run - all four have been partial, with rows unswept. Iteration 10 is another replenishing audit; the largest untouched clusters are the viewer read routes, the storage layer's schema and migrations, and the enrichment family.

## iter 10/15 | affcbaff-100429 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit. The ledger emptied when F1 closed, so this iteration swept db-schema and editions-dedupe - the storage layer's migrations, where a defect destroys data the owner cannot re-derive, and the two key functions that decide what the viewer offers to merge.

Changed: .jeffy/probes/db-schema/probe.py (new, 50 cases), .jeffy/probes/editions-dedupe/probe.py (new, 54 cases), PLAN.md (two rows swept).

Checkpoint: d474518. Not a stall: two probe batteries were added under .jeffy/probes/ and two inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 104 known-answer assertions across the two rows, 104 held. No findings, and the sweeps were built so that a clean result means something.
  - db-schema, 50/50. A fresh database takes every migration as a no-op, so opening an empty file would have exercised almost none of this code and reported a clean row on no evidence. Every case therefore BUILDS a legacy database by hand - the old schema, comma-joined tag columns, external_keys keyed on human_name, no user_version - and drives it forward. The added columns land, the tag arrays and genre casing are rewritten correctly, authors are NOT titleized while genres are, hand_edited is derived from pre_edit exactly once, the external_keys re-key preserves the row's data, and three consecutive opens stay at version 12.
  - The guard that module documents as its worst-failure insurance was probed directly, because it is the one place where a bad row could leave the database unopenable: json_extract raises on malformed JSON, so the migration wraps it in a json_valid CASE. A legacy database carrying one unparseable `raw`, one row with no machine_name, and one good row migrates, keeps the good row and reaches version 12; a database where EVERY row is unparseable also migrates, leaving the table empty rather than broken.
  - editions-dedupe, 54/54. Both modules document that they match exactly after normalization and that fuzzy was rejected as measurably LESS accurate, so the negatives were probed as hard as the positives: the one-word subset pair that fuzzy scored 100 stays apart, `#` and `+` keep C, C# and C++ distinct, a leading format word is kept while a trailing one strips, `audiobook` does not strip down to `book`, a marker-only title never collapses to the empty key, and android and music stay out of edition grouping.
  - The per-pair dismissal rule is the subtle one and it holds: a member dismissed against one sibling but still live against another stays in the group, which a filter written as "drop anything dismissed" would get wrong.
  - Scores, claiming ONLY the 23 swept rows of 57 - the other 34 are unswept:
  - correctness: None on the swept rows, on 104 known answers rather than on absence of complaint.
  - error handling: None on the swept rows. The migration's skip-and-continue guard is the one error path here and it behaves as documented.
  - architecture, documentation: None. Both modules record the measurement that chose the rule, including why fuzzy matching was rejected and why android and music are excluded, which is what made the negative cases straightforward to write.
  - testing: None on the swept rows.
  - security, performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 34 rows are unswept, so it never counts toward convergence, and closeout is NOT entered - closeout requires a FULL audit, and no audit this run has been one.
  Verify command: pytest 1126 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: A migration cannot be swept by opening a fresh database. Every step is guarded by a version check or a column check, so on a new file they all no-op and the probe certifies nothing while looking thorough. The sweep has to construct the OLD state - which also means the battery doubles as the only place the legacy schema is written down.

Next: Iteration 11 audits again, because this one filed nothing and the ledger is still empty. That is the right use of the remaining budget: with 34 rows unswept the run cannot converge, so sweeping rows and leaving batteries behind is what carries forward. The largest untouched clusters are the viewer read routes, the enrichment family, and the seven front-end rows.

## iter 11/15 | affcbaff-100429 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit, the ledger still being empty after iteration 10 filed nothing. This iteration swept webapp-read-routes, the largest unswept user-facing Python surface.

Changed: .jeffy/probes/webapp-read-routes/probe.py (new, 46 cases), PLAN.md (one row swept).

Checkpoint: bbb46e2. Not a stall: a probe battery was added under .jeffy/probes/ and one inventory row changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 46 known-answer assertions against the real app through Flask's test client, 46 held. No findings.
  - The strongest cases are the two reshape-only routes. `/api/stats` and `/api/keys` each document that the panel and the CLI must not be able to disagree, which is an invariant rather than a shape, so the battery asserts the route's payload equals `stats.report` and `keys.report` field for field - section keys, labels, and every row's label and count in order. A route that recounted instead of reshaping would pass a shape check and fail this one.
  - Also pinned: the documented absent-not-empty editions key, that a same-type duplicate pair is NOT given an edition link, the review route's filter and its sort by confidence, that `/api/duplicates` pops the raw hand_edited column rather than leaking it, that `/api/status` hides finished phases, and that all five read routes survive an empty catalog rather than raising on the empty case.
  - Two failures were reported and both were defects in this battery, not in the viewer. The traversal case asserted a status allow-list, and `/covers//etc/passwd` answers 308 because Werkzeug normalizes the doubled slash before routing; the normalized path then 404s, which is equally safe. The assertion now states the actual property - the outside file is never SERVED - and follows redirects to prove it. The other assertion contradicted its own label: it said hand_edited must not be leaked and then asserted the key was present, when the route pops it.
  - A third candidate was investigated and NOT filed. `/api/duplicates` takes its groups from `dedupe.find_groups`, which reads `items` alone, then re-queries each member with `JOIN enrichment`; a member with no enrichment row would make `fetchone()` return None and `dict(None)` raise a 500. Reaching that needs an item without an enrichment row, and there is no supported path to one: `store.py` is the only place that inserts an item and creates the enrichment row in the same transaction, and `reset.DERIVED_TABLES` wipes both together. Hand-deleting the row is state-at-rest corruption, which the envelope puts out of envelope and Declines by default. Recorded here so a later audit does not re-derive it.
  - Scores, claiming ONLY the 24 swept rows of 57 - the other 33 are unswept:
  - correctness: None on the swept rows, on the report-equality invariant rather than on a shape check.
  - error handling: None on the swept rows; the empty-catalog cases are the ones that would have shown it.
  - security: None on the swept rows. Six traversal shapes, including percent-encoded and backslash forms, never serve a file outside the covers directory. The Host guard belongs to its own row and was not re-probed here.
  - architecture, documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 33 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  Verify command: pytest 1126 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: Assert the property, not the status code. A traversal case written as "the status is 400, 403 or 404" reported a finding against a 308 that redirects to a path which then 404s - safe behaviour, failed by an allow-list that encoded one expected mechanism instead of the outcome that matters. The assertion that survives is "the file outside the directory is never served", with redirects followed.

Next: Iteration 12 audits again; the ledger is still empty and 33 rows remain. The enrichment family is the largest untouched cluster with real computation behind it, and the seven front-end rows need `tests/js_harness.py` rather than a Python battery, which is worth noting for the handoff since they are a third of what is left.

## iter 12/15 | affcbaff-100429 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit, the ledger still empty. This iteration swept enrich-core, the module that decides what the catalog SAYS about a book and the one that carries the rules protecting the owner's typed values.

Changed: .jeffy/probes/enrich-core/probe.py (new, 64 cases), PLAN.md (one row swept, one row's scope note corrected).

Checkpoint: 2359d10. Not a stall: a probe battery was added under .jeffy/probes/ and one inventory row changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 64 known-answer assertions, 64 held. No findings.
  - The value-protection rules are asymmetric and are the ones worth stating as properties rather than shapes, so each is asserted directly. An overridden row that finds no confident match keeps its status, its typed value AND its hand-edited flag, while the override flag clears anyway because it is one-shot; an overridden row that DOES find a confident match is overwritten but snapshotted first, so Revert still returns the typed values; an overridden music row is disarmed rather than downgraded to skipped.
  - `reset` was exercised at both `reviews_only` values on one fixture, and the parameter changes the answer: 3 rows swept at one value, 1 at the other, with the hand-edited review choice spared and the re-enriched one swept. It never touches the items table, asserted by reading back a rating and a type override after the wipe.
  - The strongest single assertion is that the pre_edit snapshot's keys ARE EDITABLE_FIELDS. Those two live in different modules and are joined only by convention: a field added to apply_candidate's UPDATE without being added to the list would silently stop being revertible, and nothing else in the suite would notice. It holds.
  - `run` was driven with stub sources rather than real ones, so the decision logic decides the outcome instead of the network: an exact match applies automatically, a poor match is left unmatched with its fields empty, `retry` at both values decides whether an unmatched row is revisited at all, a matched row is never revisited, every source is asked with no early break, and one source raising does not stop the others.
  - enrich-topups was NOT credited to this sweep, though three of `override_edited`'s refusal paths were incidentally covered. `credits` and `fill_series` were not touched, and a partly covered row is unswept - the same rule that split humble-login out in iteration 5. Its scope line now says so.
  - Scores, claiming ONLY the 25 swept rows of 57 - the other 32 are unswept:
  - correctness: None on the swept rows, on 64 known answers including the override and snapshot properties.
  - error handling: None on the swept rows; the raising-source case is the one that would have shown it.
  - architecture, documentation: None. The asymmetries here are documented at the point of decision, which is what made them straightforward to assert.
  - testing: None on the swept rows.
  - security, performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 32 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  Verify command: pytest 1126 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: Where two modules hold halves of one contract - a list of fields in one and the UPDATE that writes them in another - assert that they are equal rather than testing each side. The pairing is what rots, and neither side's own tests can see it.

Next: Three iterations left, and iteration 15 should be a WRAPUP rather than a task that cannot finish. Iterations 13 and 14 audit; the best remaining targets are enrich-topups and harvest-run, both of which carry real decision logic, and the seven front-end rows are worth naming in the handoff as a different kind of work needing tests/js_harness.py.

## iter 13/15 | affcbaff-100429 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit. This iteration swept enrich-topups, completing the enrichment family, and filed the one finding it produced.

Changed: .jeffy/probes/enrich-topups/probe.py (new, 36 cases), PLAN.md (one row swept), BACKLOG.md (G1 Low filed).

Checkpoint: 5cfe0e0. Not a stall: a probe battery was added under .jeffy/probes/, one inventory row changed state, and G1 was filed.

Verification: 36 known-answer assertions, 36 held. The finding came from reading the module, not from a failing case, and was then confirmed by instrumenting a run.
  - All three passes amend rows enrich.run has already finished with, so the cases assert what each does NOT touch. `fill_series` owns two columns: a filled row keeps its status, its hand_edited flag and its match_confidence, and its COALESCE keeps a typed series name while adding only the missing number. `credits` is resumable - a second pass over the same comic asks nothing at all, which is what makes a re-run free rather than a re-fetch - and one source failure costs one comic while leaving it untouched so the next run retries it. `override_edited` refuses a near-miss confirmation case-sensitively and queues nothing.
  - G1, Low. The guard at enrich.py:328 cannot fire: the query two lines above selects rows `WHERE series IS NULL OR series_number IS NULL`, so every row reaching the loop has at least one empty cell, and the guard tests for both being set. Confirmed rather than argued - a five-row fixture covering all four fill states shows the fully-filled row is not returned by the query at all, and a line trace shows the guard's body never executes.
  - The comment under it is the part worth fixing. It says the guard is "for the COUNT, not for correctness", which reads as though it keeps `filled` honest; it cannot, because it never runs. Dead code that explains itself wrongly costs a future reader more than dead code that says nothing.
  - Two things were examined and NOT filed. `credits` passes `[writers]` to tags_to_json but `artists` unwrapped, which looks like an asymmetry; tags_to_json documents that a bare string wraps as one tag, so both produce the same one-element list and the extra brackets are redundant rather than wrong. And `credits` writes authors through `COALESCE(?, authors)`, which overwrites rather than preserves - that is the intended direction for a comic whose writer ComicVine knows better than a book database does, and it is what the docstring describes.
  - Scores, claiming ONLY the 26 swept rows of 57 - the other 31 are unswept:
  - code quality: LOW, G1.
  - correctness: None on the swept rows, on 36 known answers including the no-override and resumability properties.
  - error handling: None on the swept rows; the one-source-fails case is what would have shown it.
  - documentation: None beyond G1's comment, which is filed with it rather than separately.
  - architecture, testing: None on the swept rows.
  - security, performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 31 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  Verify command: pytest 1126 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: A guard whose condition the surrounding query already excludes is invisible to every test, because no input can reach it - so it is found by reading, and confirmed by tracing rather than by a failing case. Worth the trace: reasoning alone would have been an argument, and the evidence rule asks for a reproduced fact.

Next: Iteration 14 executes G1, which is small and fits an iteration with room to spare. Iteration 15 is the WRAPUP: tidy the ledger and write the handoff, rather than starting a sweep that cannot finish.

## iter 14/15 | affcbaff-100429 | 2026-08-02 | G1 | done

Task: G1 (Low, runtime, code quality) - the unreachable guard in `fill_series` and the comment that claimed a purpose it could not serve.

Changed: humble_catalog/enrich.py (the guard deleted, the comment rewritten), BACKLOG.md (G1 deleted), PLAN.md (enrich-topups re-swept).

Checkpoint: b88a9cd. Not a stall: runtime code changed and G1 moved from open to closed.

Verification: Deleting code that cannot run should change nothing, and the evidence has to show that rather than assume it.
  - Acceptance check. The guard is gone - `grep -c 'nothing left to fill' humble_catalog/enrich.py` returns 0 - and both enrich batteries were re-run and hold at exactly their previous counts: enrich-topups 36/36, including its fully-filled-row case, and enrich-core 64/64.
  - The suite already pinned the property, which is the more interesting half. `test_fill_series_never_overwrites_a_disagreeing_number` and `test_fill_series_leaves_a_hand_edited_row_alone` both assert a fully-filled row yields 0, and both pass on either side of the deletion - because the query, not the guard, is what excludes those rows. That is precisely why the guard was dead, and it means the behaviour was already protected without it.
  - No test was added. Two existing ones cover the property and the Method prefers deletion to addition; a third asserting the same thing would have been the kind of coverage that grows without protecting anything new.
  - The comment now says what is true: `filled` is counted in Python because neither sqlite3 counter can answer the question - total_changes is cumulative over the connection and rowcount counts rows MATCHED rather than altered - and no guard against fully-filled rows is needed because the query already excludes them. The half of the old comment that was correct, about why the count is not taken from sqlite3, is kept.
  - Contract preserved. No signature, no return value, no observable behaviour; `fill_series` returns the same counts on the same inputs, which the unchanged battery scores are the evidence for.
  - Verify command: pytest 1126 passed (exit 0), unchanged; check_no_data_tracked exit 0; leak_check exit 0.

Learnings: When a fix is a deletion, the evidence that it is safe is that the numbers do NOT move - unchanged battery scores and an unchanged suite, not a new failing-then-passing test. A deletion that needs a new test to prove it was probably not dead code.

Next: Iteration 15 is the final one and is a WRAPUP: tidy the ledger, record the run's position, and write a handoff naming the 31 unswept rows and which of them need a different instrument. The run does not converge - it cannot, with 31 rows unswept - and the report should say so plainly rather than dress the budget running out as completion.

## iter 15/15 | affcbaff-100429 | 2026-08-02 | WRAPUP | done

Task: Final iteration of the run. Tidy the ledger, record the position, and write the handoff. No new sweep was started: with 31 rows unswept a fourteenth-hour battery could not have been finished or verified, and an unfinished one is worse than none.

Changed: JOURNAL.md (this entry). BACKLOG.md needed no tidying - Now, Next and Later are empty, nothing is marked [b], and no task was left half-done.

Checkpoint: 5cb9c34. Not a stall in substance, though only ledger files changed: this is the WRAPUP iteration, whose work IS the handoff, and no BACKLOG item changed state because none was left open.

Verification: The run's closing state, checked rather than recalled.
  - Ledger: 0 open, 0 blocked. Every task filed this run was completed - C3, D1, D2, E1, E2, F1, G1 - and none was Declined, so nothing was quietly dropped.
  - Surface inventory: 26 of 57 rows swept, 31 unswept, 0 unreachable. No `[~]` row exists, so there is nothing this host could not reach.
  - Verify command: pytest 1126 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.
  - The run is NOT converged and the closing rule is not satisfied on any clause but one. The Definition of done needs a FULL fresh-evidence audit scoring zero High and zero Medium; every audit this run was partial by construction, because 31 rows remain unswept. The evaluator gate was therefore never invoked - it requires that same clean full audit - and no Converged line is appended. The only clause that does hold is the empty ledger.
  - Five batteries were added this run and six existed before it; all 22 under .jeffy/probes/ are committed and re-runnable, and every one was re-run in the iteration that touched its code rather than trusted.

Learnings: A run that cannot converge is still worth its budget if what it leaves behind is re-runnable. The 11 iterations of sweeping produced 470 known-answer assertions across 9 rows, and the next run re-runs them in seconds instead of reconstructing the instrument - which is where most of a re-sweep's cost otherwise goes.

Handoff for the next run.
  - Start a NEW session. The state files carry the run forward and the context does not; relaunching in this session keeps every accumulated token and forfeits the clean-context benefit the loop is built on.
  - The 31 unswept rows split into three kinds of work, and the split matters more than the count. Nineteen are ordinary Python and take the same instrument every row this run used: cli-dispatch, four webapp route families, humble-login, bundle-preview-tiers, series-db, game-match, the four harvest and quota rows, check-cmd, import-sheets, import-games, keys-report, backup-restore and reset-cmd. Seven are front-end JavaScript - js-catalog-render, js-catalog-filter, js-fuzzy, js-autocomplete, js-panels, js-shell and viewer-markup - and need `tests/js_harness.py` rather than a Python battery, which is a different instrument and worth budgeting separately. Five are scripts and packaging: privacy-gates, demo-catalog, favicon-fixtures, os-wrappers and packaging-ci.
  - Highest value first, on this run's evidence: every defect found this run was at a boundary where third-party or upstream data enters, and the internal logic came back clean on 210 assertions across five rows. The remaining rows with that same shape are webapp-remote-routes and bundle-preview-tiers, both of which parse content the project does not control. game-match is worth a sweep for a different reason - F1 was found there through titles, and the module was never probed directly.
  - Two rows are cheap and were deliberately left: humble-login needs a real browser and a profile directory, and check-cmd makes live per-source requests. Both are reachable on this host; neither fits a battery that must not touch the network.
  - The Proposed item on `leak_check.py` is unresolved and cost this run three more rewordings, on ordinary English prose and on two Python identifiers whose spelling cannot be changed. It needs a user decision; it is not something a run should decide for itself.

Next: Nothing. This is the final iteration; the run ends here with the report to the user.

## iter 1/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Opening audit of a new run. The ledger was empty and 31 of 57 inventory rows were unswept, so this iteration probed the two rows the previous run's handoff named as highest value - bundle-preview-tiers and webapp-remote-routes, both of which parse content the project does not control - breadth-first rather than building one battery, so the worst defect would appear in the first filing.

Changed: BACKLOG.md (H1 filed in Now, H2 in Later, the resolved Proposed item deleted), PLAN.md (three Lessons corrected, one added), JOURNAL.md (this entry). No project code was touched this iteration.

Checkpoint: 0710965. Not a stall: two BACKLOG items were filed and the Proposed item changed state, though only ledger files changed - which is what an audit iteration is.

Verification: Every finding below was reproduced before it was filed; none is from reading alone.
  - H1, the one that matters, is a wrong ANSWER rather than a crash, which is why a liveness probe would have certified this row clean. `preview()` walks `tier_item_machine_names` with a bare `for name in names`, so a tier whose list arrives as a string is iterated character by character. Reproduced: a tier selling one item, `widget_svc`, reports `total: 10`, `new: 10`, and lists `_`, `c`, `d`, `e`, `g`, `i`, `s`, `t`, `v`, `w` under `adds`. The report exists to answer how much of a bundle the owner already holds, so it is a purchase decision resting on invented numbers.
  - The same absence of a type check raises `AttributeError` at four further sites, each reproduced against the real module: a blob that is not an object at `fetch_bundle` line 75; a non-empty list for `basic_data` at line 246; the same for `tier_display_data` at line 265; and a non-mapping pricing entry at line 308. Through `/api/bundle-preview` each is a 500.
  - Empty off-shape values do NOT reproduce it, and the first pass wrongly read as clean because of that: `[] or {}` is `{}`, so an empty list falls back to the default and only a NON-empty one reaches the attribute access. Recorded because the same trap will be in the battery.
  - Filed as one structural task, not five. Third-party JSON read without a type check is an idiom this project has settled twice already, both times at one boundary rather than per site, and `humble_catalog/shapes.py` is that boundary. The three-strike rule makes instance patching the wrong remedy here even though the sites are few.
  - H2 was reproduced the same way, through Flask's test client: a JSON array body, a JSON string body, and `{"url": 5}` each raise rather than answering 400, on both remote routes. Malformed JSON is fine - Werkzeug answers 400 before the handler runs.
  - H2 is Low and stays Low. The viewer API is user-error in the envelope, where a wrong value earns a clear failure message and exotic malformed shapes are Low at most. `{"url": 5}` is the one that is not exotic - a wrong value rather than a wrong shape - and it is the reason the task exists at all.
  - Checked before filing that H2 is not inside settled class A1: that class was enumerated with `grep -n "request.get_json()\[" `, which lists direct-index reads only, and these two routes read with `.get`. Neither writes to the catalog, which is why the inventory splits them from webapp-write-routes.
  - Scores, claiming ONLY the two rows probed this iteration; 31 of 57 rows remain unswept and neither row probed here is flipped, because a reproduction is not a battery and the module H1 changes would stale it anyway:
  - correctness: HIGH, on H1's reproduced wrong report.
  - error handling: MEDIUM on the bundle-preview path, folded into H1 as the same root cause; LOW on the viewer routes per the envelope.
  - security: None on what was probed. `fetch_bundle`'s host gate and the outbound guard are separate rows, already swept.
  - architecture: None. The network seam this module documents is real and is what made the pure half reproducible with no network at all.
  - documentation, testing, performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit and never counts toward convergence; closeout is NOT entered, which requires a full audit scoring zero High and zero Medium.
  - Housekeeping, recorded because it changed the gate every iteration runs: the Proposed item asking whether `leak_check.py` should match word boundaries was resolved by the owner before this run began, in commit 570d5f4, which is on `main` and is the parent of this run's first checkpoint. Matching is now whole-word, 11 ALLOWED entries that existed only to excuse embedded collisions were removed, and 234 lines of tests pin it. The item is deleted from Proposed rather than carried, and three Lessons that described substring matching were corrected in PLAN.md - a stale Lesson steers every future run wrongly.
  - Verify command: pytest 1153 passed (exit 0), up from 1126 with the 27 leak-gate tests that landed in 570d5f4; check_no_data_tracked exit 0; leak_check exit 0 over 5251 terms and 249 files. Chain exit status checked directly, never through a pipe.

Learnings: A defect that returns a wrong number outranks one that raises, and the two can share a root cause - here both come from the same missing type check, but only the silent one changes what the owner is told. When a sweep meets an unguarded read of third-party data, probe what a wrong SHAPE makes the code compute, not only what makes it raise: iterating a string instead of a list is the case that produces a confident wrong answer instead of a stack trace.

Next: Iteration 2 executes H1, the only item in Now. Its acceptance check is the bundle-preview-tiers battery, so that iteration both fixes the class and takes most of an unswept row with it; the row flips only if the battery covers the tier walk's known answers and not merely the off-shape cases.

## iter 2/20 | ce2620c5-151422 | 2026-08-02 | H1 | done

Task: H1 (High, runtime, correctness) - the bundle page blob read with no type check, whose worst outcome is a confident wrong count rather than a crash.

Changed: humble_catalog/bundle_preview.py (14 payload reads routed through `humble_catalog/shapes.py`; docstrings of `fetch_bundle` and `delivery_stores` updated to state the new contract), .jeffy/probes/bundle-preview-tiers/probe.py (new, 57 cases), BACKLOG.md (H1 deleted, the class recorded under Settled classes), PLAN.md (bundle-preview-tiers swept, bundle-preview-parts re-swept).

Checkpoint: e662825. Not a stall: runtime code changed and H1 moved from open to closed.

Verification: The filed reproduction was re-run first, before any edit, and still stood - the string case still reported a 1-item tier as 10 items.
  - Acceptance check. `.venv/Scripts/python.exe .jeffy/probes/bundle-preview-tiers/probe.py` exits 0 at 57/57.
  - Differential, measured before the edit rather than reconstructed after it: the same battery scored 41/55 against the unfixed module, and all 14 failures were H1. The total is 55 there and 57 here because two cases raised before reaching their later assertions; that is reported as it happened rather than smoothed to a common denominator.
  - The battery was written before the fix and imports no name the fix adds - it introduces none, only new CALLS to accessors `shapes` already exported - so the differential was measurable without the trap that cost three iterations of the previous run.
  - The 41 that passed unfixed are the control, and they matter as much as the failures: the counting rules - owned versus new, the merges union, price ordering, disjoint `adds` summing to the richest tier's new count, cumulative-tier dedupe, the game verdict routing, keyed-versus-activated precedence, the unimported-store scoping, and series hits leaving `overlaps` - all held on both sides. The fix changed no correct answer.
  - Two silent defects the filing had not named were found by the battery and are folded into the same class, both being the same missing check. `delivery_stores` ran `set()` over the `game` field, so a string there yielded five single-letter storefronts, each then reported as a store never imported. And a non-numeric price passed through as text into a field `format_report` renders with `:.2f`, which would raise inside the report rather than at the read that accepted it.
  - `text_list` rather than `as_list` for the machine-name list, deliberately. A list field that arrived unwrapped as a bare string is ONE entry: that is the rule `shapes.first_text` and `shapes.text_list` already document, and treating it as zero would under-report a tier while treating it as characters over-reports it tenfold. The desired answer was chosen from the project's existing precedent, not from what the code happened to do.
  - Class closed, not instances patched. Enumerating check listing the idiom: `grep -nE "(bundle|basic|pricing|items|display|item|blob|game)\.get\(" humble_catalog/bundle_preview.py` returns 14 sites, every one reading from a name bound by `shapes.as_mapping` and wrapping its result in an accessor. Recorded under Settled classes.
  - Contract preserved, and stated because two of the changed functions are public. `fetch_bundle` keeps its signature, its host gate and its ValueError for a page with no blob; it now answers `{}` for a blob that parses but is not the expected object, where it previously raised AttributeError, which is a strictly narrower failure set. `delivery_stores` keeps its signature and its meaning and now accepts any shape, answering with a set as it always documented. Both refusal paths were re-probed: `.jeffy/probes/bundle-preview-parts/probe.py` holds 26/26 unchanged, and the tiers battery re-asserts that a foreign host and a lookalike host are still refused.
  - Verify command: pytest 1153 passed (exit 0), unchanged from the previous checkpoint, so no existing test moved; check_no_data_tracked exit 0; leak_check exit 0 over 5251 terms and 250 files. Exit status checked directly, never through a pipe.

Learnings: `x or {}` is not a type check, and the gap is exactly where a sweep goes wrong. An EMPTY list is falsy and falls back to the default, so the off-shape cases written with `[]` all looked clean; only a NON-EMPTY list reaches the attribute access and raises. A probe for unguarded payload reads must use non-empty off-shape values, or it certifies the guard it was written to test.

Next: Iteration 3 has one item left on the ledger, H2 (Low), and 30 rows unswept. The ledger will fall below 3 open items, so replenishment applies; the better use of the iteration is a fresh audit sweeping rows, with H2 worked once the ledger has company - it is Low, runtime, and small enough to ride a later iteration.

## iter 2/20 | ce2620c5-151422 | 2026-08-02 | ROTATION | rotation

Task: JOURNAL.md passed 500 lines when the H1 entry was appended, so all but the last 10 entries were moved to JOURNAL-archive.md.

Changed: JOURNAL.md (11 entries removed, preamble and the last 10 entries kept), JOURNAL-archive.md (the same 11 appended to what it already held).

Checkpoint: shared with the H1 entry above; this is an additional entry, not a separate iteration.

Verification: Counted rather than assumed, because the failure mode here is silent loss.
  - JOURNAL.md held 21 entries at 509 lines; it now holds 10 entries plus this one at 271 lines, and the preamble with its heading-grammar example is untouched.
  - JOURNAL-archive.md went from 12 entries to 23, which is 12 + 11. It was appended to, never rewritten, and the count is asserted to have RISEN by exactly the number moved - the stop hook rejects an archive whose entry count fell.
  - The split matched only lines beginning `## iter` followed by a digit, so the grammar example in the preamble was never counted as an entry nor moved.

Learnings: None beyond the mechanism already written down.

Next: Continues into iteration 3 as the H1 entry describes.

## iter 3/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Replenishing partial audit. The ledger held one item, H2 (Low), which is below the replenishment line of 3, and the binding constraint on this run is 30 unswept rows rather than that single Low - so this iteration swept three rows that compute values and are small enough to sweep properly in one turn: game-match, series-db and quota-gate. H2 was deliberately not executed here; it is the next iteration's task.

Changed: .jeffy/probes/game-match/probe.py (new, 25 cases), .jeffy/probes/series-db/probe.py (new, 15 cases), .jeffy/probes/quota-gate/probe.py (new, 23 cases), PLAN.md (three rows swept), JOURNAL.md (this entry). No project code was touched.

Checkpoint: 5d5642f. Not a stall: three probe batteries were added under .jeffy/probes/ and three inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 63 known-answer assertions across three rows, 63 held. No findings, and each sweep was built so that a clean result means something.
  - game-match, 25/25. The two cutoffs are pinned on BOTH sides with derived answers rather than observed ones: `fuzz.ratio` is 2*M/T, so synthetic letter pairs give scores computable by hand - 92.31 and 100.00 must be owned, 90.00 and 83.33 must be possible, 40.00 must be new. A case asserts the two cutoff constants themselves, so if either moves the derivation fails first and names the reason instead of silently certifying whatever the scorer now returns.
  - The index-parallel invariant is the one worth asserting as a property, because breaking it makes every match name the WRONG game while still looking like a match: a three-title pool is queried for each title in turn and each must resolve back to itself.
  - Also pinned: the sequel rule forcing new in both directions, the F1 case that a digit and a roman numeral for one volume are NOT a sequel pair, an edition suffix still matching the base game, the empty pool and the title that normalizes to nothing, that the display title rather than the sorted scoring key comes back, and the documented refusal - a plain list raises rather than being silently prepared per call.
  - series-db, 15/15. The valuable outcome is the re-buy, and it is asserted directly: an offered volume already held is flagged, a continuation is not, a gap is rendered as `Vol. 1-2, 5` rather than smoothed into a run the owner does not hold, and only an explicit range carries a span while a single volume invents none. Two spellings of one volume index to a single number, so a duplicate cannot inflate the count.
  - quota-gate, 23/23. The arithmetic is closed-form because PACIFIC is a FIXED offset, so every expected instant is written out in full rather than recomputed by repeating the implementation. The strictly-after boundary is pinned at the exact instant, one second either side, and the same instant spelled in a third zone. An invariant over 48 hourly inputs asserts every answer is strictly ahead and within 24 hours, which a constant return or an off-by-one-day would break.
  - The two commit contracts are asserted the way the Lessons require - directly, not by a weaker proxy. `record` commits, checked from a SECOND connection, which is the only thing that can tell a commit from a pending write; `clear` does not commit, checked by rolling back and seeing the row return.
  - The fixed UTC-8 offset was NOT filed. During Pacific Daylight Time the computed reset is an hour late, and the module documents that as a deliberate trade taken in the safe direction - waiting costs nothing because the source is served from cache either way, while retrying early spends the request the module exists to save. Audit discipline forbids re-filing a documented decision on unchanged code; it is pinned as behaviour instead.
  - Scores, claiming ONLY the three rows swept this iteration; 27 rows remain unswept:
  - correctness: None on the swept rows, on 63 known answers including both sides of both matching cutoffs.
  - error handling: None on the swept rows. The unknown-source, empty-pool and empty-title paths are the ones that would have shown it.
  - architecture: None. Both scoring modules document the measurement that chose their rule, which is what made the negative cases straightforward to write.
  - documentation: None on the swept rows; every documented parameter checked was true of the code.
  - testing: None on the swept rows.
  - security, performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 27 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1153 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 253 files.
  - The gate fired once during this iteration, on a two-word phrase of ordinary English in a probe docstring. Reworded rather than allowed. Worth recording that it was a WHOLE-WORD hit: the word-boundary change ended the embedded-identifier collisions, not this class, and the Lessons already say so.

Learnings: A cutoff is swept by deriving the expected verdict from the documented constant, not by feeding it real-looking data and recording what comes back. Synthetic inputs whose score is computable by hand - here 2*M/T over letter strings - turn a fuzzy matcher into a known-answer surface, and asserting the constants themselves in the same battery keeps the derivation honest if they ever move.

Next: Iteration 4 executes H2, the only open item, now that the ledger has been checked rather than assumed empty of worse. After that the ledger empties again and the run returns to sweeping; 27 rows remain and the largest untouched clusters are the four harvest and progress rows, the seven front-end rows, and the five scripts and packaging rows.

## iter 4/20 | ce2620c5-151422 | 2026-08-02 | H2 | done

Task: H2 (Low, runtime, error handling) - the two viewer routes that take a URL answered 500 rather than 400 for a body that is not an object or a `url` that is not a string.

Changed: humble_catalog/webapp/__init__.py (`_url_from_body` added as one shared reader; both routes now call it), tests/test_webapp.py (+5), BACKLOG.md (H2 deleted, H3 filed), PLAN.md (three webapp rows re-swept).

Checkpoint: 5c54d77. Not a stall: runtime code and tests changed, H2 closed and H3 opened.

Verification: The filed reproduction was re-run first and still stood - both routes raised AttributeError on an array body, a bare-string body and `{"url": 5}`.
  - Acceptance check. 5 new tests in tests/test_webapp.py pass, and the suite is 1158 passed against 1153 at the last checkpoint, which is exactly the 5 added and no existing test moved.
  - Differential, run by copying the fixed file aside and restoring HEAD's version under it rather than checking out over uncommitted work: 4 of the 5 fail against the unfixed route code. The fifth is the control and passes on BOTH sides - it asserts the blank-url refusal that already worked, so it proves the fix did not trade away the behaviour it was extending.
  - One reader rather than two guards, because the two routes must not be able to disagree about what a usable body is. `silent=True` folds malformed JSON in as well, so a bad body now earns the same JSON error object as every other refusal instead of Werkzeug's HTML 400 page, which the viewer's JS cannot parse.
  - A test asserts the property that makes this a refusal rather than a slow failure: with `url_import.resolve` and `bundle_preview.fetch_bundle` replaced by functions that raise if called, every refused body still answers 400, so nothing outbound is attempted for a body that cannot supply a URL.
  - Contract preserved. Both routes keep their paths, their methods, their success shapes and their existing 400 for `{}` and for a blank url. The change is strictly a narrowing of what answers 5xx.
  - webapp/__init__.py is the implementing code of three already-swept rows, so all three batteries were re-run rather than assumed unaffected: webapp-host-guard 34/34, webapp-read-routes 46/46, webapp-write-routes 18/18, each unchanged. The rows are re-swept at this checkpoint.
  - A CORRECTION, recorded because it was very nearly written into the ledger as fact. The Settled classes line for H2 was drafted claiming `grep -n "get_json" humble_catalog/webapp/__init__.py` returned 6 sites. It returns 19. The claim was written from expectation and then checked, and the check refuted it; the line was deleted rather than repaired, because the class it claimed to settle is not settled.
  - What the real enumeration found is H3: 13 further routes carry the identical idiom and answer 500 on an array body, reproduced route by route. So H2 fixed exactly the two routes its finding named and left the class open. That is the honest reading - the finding was scoped to two routes because those were the two that had been probed, not because the others were clean.
  - `/api/items/<id>/rating`, `/type` and `/choose` are NOT affected, having already been given `get_json(silent=True)` and an isinstance check by A1. That is the shape the H3 fix generalizes.
  - Verify command: pytest 1158 passed (exit 0); check_no_data_tracked exit 0; leak_check exit 0 over 5251 terms and 253 files. Exit status checked directly, never through a pipe.

Learnings: Run the enumerating check before writing what it returns, not after. A settled-class line is a claim that a whole class is closed, and this one was drafted from the two sites the finding happened to name; the real grep returned three times as many and 13 of them were still broken. The Method already says to enumerate the idiom rather than the fix - the failure here was enumerating from memory and treating the number as known.

Next: Iteration 5 executes H3, the only open item, which is the same fix generalized to one shared body reader across every POST route. Its acceptance check drives every route in `grep -n "@app.post"` with an array body, so it closes the class by enumeration rather than by the list of routes that happen to be named today.

## iter 5/20 | ce2620c5-151422 | 2026-08-02 | H3 | done

Task: H3 (Low, runtime, error handling) - the `or {}` body-read idiom answering 500 across the viewer's POST routes, closed at one reader rather than per site.

Changed: humble_catalog/webapp/__init__.py (`_json_object` added as the single body reader; 18 read sites replaced; `_url_from_body` reduced to a caller of it; `/comment` now requires its key), tests/test_webapp.py (+3), BACKLOG.md (H3 deleted, the class recorded under Settled classes).

Checkpoint: 5fe28bf. Not a stall: runtime code and tests changed and H3 moved from open to closed.

Verification: The filed reproduction was re-run first, and it understated the defect - which is the main thing this entry has to record.
  - H3 was filed saying 13 routes, on the strength of a hand-listed set of routes probed in iteration 4. Enumerating every POST rule from `app.url_map` instead returned 24 routes, of which 19 answered 500. The six the filing missed are `/api/items/<id>/type`, `/choose`, `/keys/hide`, `/keys/unhide`, `/user-tags/delete` and `/export.xlsx`, and the filing's claim that `/type` and `/choose` were already safe was simply wrong.
  - The reason they were missed is worth stating: they use `get_json(silent=True) or {}`, which LOOKS like the guarded form. `silent=True` only stops malformed JSON from raising; the `or {}` beside it is still not a type check, so a non-empty array passes through exactly as before. Reading for the safe-looking spelling rather than running the enumeration is what produced the wrong count, for the second time in two iterations.
  - `/api/items/<id>/rating` was correctly listed as unaffected but for the wrong reason. It never calls `.get`; it tests `"rating" not in data`, and `in` against a list is a membership test that answers False rather than raising. It was safe by accident, not by validation.
  - Acceptance check, run and passing: `test_no_post_route_answers_5xx_for_a_body_that_is_not_an_object` drives all 24 POST rules with four non-object bodies and none answers 5xx. The enumeration comes from `app.url_map`, not from a list of names, so a route added later is covered without anyone remembering to add it - which is the whole point, given that a hand-kept list is what got this wrong twice.
  - Differential: 2 of the 3 new tests fail against the unfixed file, restored from HEAD under the fixed copy rather than checked out over it. The third is the control - no body at all - and passes on both sides, because that shape was already handled.
  - A REGRESSION THIS TASK INTRODUCED, caught by the acceptance check and repaired inside the iteration. Once a malformed body reads as an empty object, `/comment` answered 200 and CLEARED the note, because an absent `comment` had always meant "clear it". The previous 500 at least wrote nothing. Turning a loud failure into a silent destructive write is strictly worse than the defect being fixed, so `/comment` now requires the key, exactly as `/rating` already required its own. Clearing is still done the documented way, by sending a blank string, and a test pins that both halves hold.
  - The enumeration also settled which route may answer 2xx here: `/reopen`, whose documented contract is a bare body it never reads. The assertion was narrowed to state that rather than asserting a blanket 4xx policy the app does not have and never claimed.
  - Contract preserved, with one deliberate exception recorded here. Every route keeps its path, method, success shape and existing refusals; the change narrows what answers 5xx. The exception is `/comment`, which no longer treats an absent field as a clear - a behaviour change made because the alternative was silent data loss on malformed input, and the viewer never relied on it: `catalog.js:904` always posts `{comment}`, and the existing clear test sends a blank string.
  - webapp/__init__.py is the implementing code of three swept rows, so all three batteries were re-run: webapp-host-guard 34/34, webapp-read-routes 46/46, webapp-write-routes 18/18, each unchanged and re-swept at this checkpoint.
  - Verify command: pytest 1161 passed (exit 0), up from 1158 with the 3 added and no existing test moved; check_no_data_tracked exit 0; leak_check exit 0.

Learnings: `[recurred]` A count of affected sites written from reading rather than from running the enumeration was wrong twice in two iterations, both times UNDER-counting, and the second time the miss was caused by a safe-LOOKING spelling: `get_json(silent=True) or {}` reads as guarded and is not. Enumerate by driving the real registry - `app.url_map` here - not by grepping for a pattern a variant can dodge.

Next: The ledger is empty and 27 rows are unswept, with 15 iterations left. Iteration 6 is an audit; the evaluator gate does not apply yet, since no FULL audit has been recorded this run and it cannot be until the inventory is complete. The largest untouched clusters are the four harvest and progress rows, the seven front-end rows needing tests/js_harness.py, and the five scripts and packaging rows.

## iter 6/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit, the ledger having emptied when H3 closed. This iteration swept two viewer route families that the pending work will not touch - webapp-merge-routes and webapp-export-routes - and probed a third, webapp-tag-vocab-routes, which is left unswept because the finding it produced will change that code.

Changed: .jeffy/probes/webapp-merge-routes/probe.py (new, 44 cases), .jeffy/probes/webapp-export-routes/probe.py (new, 30 cases), BACKLOG.md (I1 filed), PLAN.md (two rows swept). No project code was touched.

Checkpoint: 9739358. Not a stall: two probe batteries were added under .jeffy/probes/, two inventory rows changed state, and I1 was filed.

Verification: 74 known-answer assertions across the two swept rows, 74 held, and one finding from the third row that was reproduced before being filed.
  - webapp-merge-routes, 44/44. These routes DESTROY a row, so the cases that carry the weight assert what must NOT happen. Every refusal - the same id twice, a missing id, a string id, a bool id, a float id, an unknown id, a type mismatch - is followed by reading the database back and asserting both rows survive and `merges` is empty. A route that answered 400 while deleting anyway would pass a status-code check and fail these.
  - The bool case is the one worth naming: bool is a subclass of int in Python, so `isinstance(x, int)` accepts True, and `{"keep_id": true, "drop_id": false}` would merge row 1 into itself. It is refused.
  - The dismissal rules are asserted as properties: a dismissal keeps both rows where a merge deletes one, dismissing the same pair in both directions stores one row rather than two, and end to end a dismissed pair stops being offered by `/api/duplicates`.
  - One case failed first on a WRONG FIXTURE and was corrected rather than filed: `Building Widget Services` and its `2e` variant are an EDITION pair, not a duplicate pair, because `dedupe` groups on an exact key after normalization and an edition suffix belongs to `editions.edition_key`. The case now uses the case-only pair, and the comment records the distinction so the next reader does not re-derive it.
  - webapp-export-routes, 30/30. These hand the owner their own catalog, so the cases assert CONTENT rather than status: which rows, in which order, under which columns. The order case matters most - the filter predicate lives in the browser, so the row order has to arrive from there, and a route that re-sorted would silently discard the sort the owner is looking at. `columns` is exercised at two values that change the header, and the documented asymmetry holds: an unknown column NAME is dropped because stored browser state outlives a schema rename, while a non-list is a 400.
  - The csv/xlsx pair is asserted to AGREE on the rows rather than each being checked alone, and both are asserted to refuse a malformed body identically, since `_export_request` is shared precisely so they cannot drift.
  - Eight cases failed first, all on the same wrong assumption of mine - that column names are capitalized. They are lowercase. The helper that read the title column had a fallback index, so it silently read the neighbouring `type` column and reported `ebook` as a title; it now asserts the column is present instead of falling back, so a renamed column fails loudly rather than reading whatever sits beside it.
  - I1, filed, reproduced route by route. `(data.get("old") or "").strip()` answers 500 whenever the field is not a string, at 6 sites in the tag-vocabulary family. This is the same defect as H2 and H3 one level down: `or` used as a type check on a FIELD rather than on the body.
  - The second half of I1 is a silent write rather than a crash, which is why it is filed with the first: `{"tags": [None, {"a": 1}]}` is accepted with 200 and stores tags spelled `None` and `{'a': 1}`, because `db.normalize_tags` coerces every entry with `str()`. Checked before filing that the remedy belongs at the viewer boundary and not in `normalize_tags`, whose coercion serves the import paths and whose row is already swept.
  - Third finding on one root cause, so the three-strike rule applies and the task is written as one shared text-field reader rather than six guards.
  - webapp-tag-vocab-routes is deliberately NOT flipped. It was probed enough to find I1, and the fix will change that code, so a sweep now would be stale by the next checkpoint; the iteration that fixes I1 sweeps it, as H1 did with bundle-preview-tiers.
  - Scores, claiming ONLY the two rows swept this iteration; 25 rows remain unswept:
  - correctness: None on the swept rows. The order, content and agreement invariants are what would have shown it.
  - error handling: LOW on the tag-vocabulary row, I1 - not on the two swept rows, whose refusals all hold and delete nothing.
  - security: None on the swept rows; the destructive routes refuse every malformed id shape without touching the database.
  - architecture: None. `_export_request` being shared by both formats is what made the identical-refusal assertion writable at all.
  - documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 25 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1161 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 255 files.

Learnings: A probe helper that FALLS BACK when it cannot find what it is looking for will read a neighbouring field and assert against it. The title lookup here defaulted to column index 1 when the name was absent, so eight cases compared titles against `ebook` and the failures pointed at the routes rather than at the probe. A locator in a battery should assert its target exists, because the alternative is a case that reports on the wrong data with full confidence.

Next: Iteration 7 executes I1, which is one shared text-field reader plus the tags-entry check, and sweeps webapp-tag-vocab-routes in the same iteration since that code is what changes. That leaves 24 rows with 13 iterations after it; the four harvest and progress rows are the largest remaining Python cluster, and the seven front-end rows need tests/js_harness.py rather than a Python battery.

## iter 7/20 | ce2620c5-151422 | 2026-08-02 | I1 | done

Task: I1 (Low, runtime, error handling) - a named text field read without checking it is a string, closed at one shared reader, plus the tag-entry coercion that stored junk vocabulary.

Changed: humble_catalog/webapp/__init__.py (`_text_field` added; 7 field sites routed through it; `/api/items/<id>/user-tags` now type-checks its entries), tests/test_webapp.py (+3), .jeffy/probes/webapp-tag-vocab-routes/probe.py (new, 99 cases), BACKLOG.md (I1 deleted, the class recorded), PLAN.md (webapp-tag-vocab-routes swept, five webapp rows re-swept).

Checkpoint: 78783eb. Not a stall: runtime code, tests and a battery changed, and I1 moved from open to closed.

Verification: The filed reproduction was re-run first and still stood - 5 routes answering 500 for a non-string field, and `{"tags": [null]}` stored as a tag spelled None.
  - Acceptance check. `.venv/Scripts/python.exe .jeffy/probes/webapp-tag-vocab-routes/probe.py` exits 0 at 99/99, and it doubles as this row's sweep.
  - Differential: 55/99 against the unfixed file, restored from HEAD under the fixed copy rather than checked out over it. The 44 failures are I1; the 55 that pass on both sides are the control and are the more interesting half, because they are the whole point of the row - renaming a genre moves exactly the rows that used it and reports the count, deleting removes it from every row, the two vocabularies never leak into each other, user tags keep the casing the owner typed while genres are titleized, a bulk add is a union rather than a replacement, and an unknown id in a bulk request is ignored because the catalog can change under a page left open. None of that moved.
  - Class closed at one reader, per the three-strike rule: this was the third finding sharing H2 and H3's root cause, so six guards would have been the wrong remedy. `_text_field` folds absent, non-string and blank-after-stripping into one None, because all six callers already treated the three identically.
  - Enumerating check, run rather than recalled: `grep -nE '\.get\("[a-z_]+"\) or ""'` over the file returns one line, and it is inside `_text_field`'s own docstring where the idiom is quoted. No live site remains.
  - The silent half was fixed at the viewer boundary and NOT in `db.normalize_tags`, deliberately. That function coerces with `str()` for the import paths it also serves, where a number in a spreadsheet cell is a genre; changing it would have altered import behaviour and staled the already-swept db-tags row to fix a viewer-only problem. The entries are type-checked where they enter instead.
  - Contract preserved, and the one narrowing recorded: every route keeps its path, method, success shape and existing refusals, and the change only narrows what answers 5xx. `/api/items/<id>/user-tags` now refuses a list containing a non-string where it previously coerced it; the control case asserts the shape the viewer actually sends still works and that an empty list still clears the row.
  - All five sibling webapp batteries were re-run because they share the file: host-guard 34/34, read-routes 46/46, write-routes 18/18, merge-routes 44/44, export-routes 30/30, every one unchanged.
  - Verify command: pytest 1164 passed (exit 0), up from 1161 with the 3 added and no existing test moved; check_no_data_tracked exit 0; leak_check exit 0 over 5251 terms and 256 files.

Learnings: When a shared helper is the right remedy but one of its callers serves a second audience, fix at the boundary the finding is about rather than in the shared helper. `db.normalize_tags` coercing with `str()` is correct for the import paths and wrong for the viewer, so the check belongs at the viewer, which also left a swept row unstaled.

Next: The ledger is empty with 24 rows unswept and 13 iterations left. The evaluator gate does NOT apply, because it requires a clean FULL audit recorded this run and no audit can be full while the inventory has unswept rows. Iteration 8 audits again; the four harvest and progress rows are the largest remaining Python cluster, and the seven front-end rows need tests/js_harness.py, which is a different instrument and worth starting before the budget is short.

## iter 8/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit, the ledger having emptied when I1 closed. This iteration swept js-fuzzy - the first of the seven front-end rows, and the one that decides whether that cluster is affordable at all - and progress-failures.

Changed: .jeffy/probes/js-fuzzy/probe.py (new, 28 cases), .jeffy/probes/progress-failures/probe.py (new, 49 cases), PLAN.md (two rows swept). No project code was touched.

Checkpoint: a4462c9. Not a stall: two probe batteries were added under .jeffy/probes/ and two inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 77 known-answer assertions across two rows, 77 held. No findings.
  - js-fuzzy, 28/28, and the instrument question is settled: node v24.18.0 is on this host, `tests/js_harness.py` runs the viewer's real scripts in a stubbed DOM, and `Fuzzy` is reachable from it. The remaining six front-end rows are therefore ordinary work rather than blocked, and none of them needs a `[~]`.
  - The scorer is the best possible first front-end row because its bands are DOCUMENTED, so every expected score is derived from the formula in the file rather than recorded from a run: T1 is `0.90 + 0.10 * len(q)/len(t)`, T2 is `0.45 + 0.40 * matched/tokens`, T3 is `0.40 + 0.10 * min(1, chars/words)`. An identical query must score 1.00, a 7-of-16 fragment 0.944, a 4-of-16 fragment 0.925, two reordered whole tokens 0.85, full initials 0.50. All five landed exactly.
  - The tier structure is asserted as ordering properties, not just numbers, because that is what the bands are for: a verbatim match must outrank a reordered one (0.90 floor above the 0.85 ceiling), a reordered one must outrank an acronym, and a longer verbatim fragment must outrank a shorter one. Also pinned: AND semantics, so a query token matching nothing sinks the whole query rather than scoring on the rest.
  - The cutoff is asserted as an invariant over every case in the battery rather than at one point - no score may fall strictly between 0 and 0.40 - so a caller can treat any nonzero score as a real match.
  - The span cases are the ones a text assertion could never reach, and they are why this row was worth running for real. Spans are computed on the FOLDED string, whose length differs from the original once apostrophes are elided, so a span that indexed the folded string would highlight the wrong characters. Asserted by slicing the ORIGINAL title with the returned span and checking it reads as the queried word, including on a title carrying an apostrophe.
  - One case failed first and it was my call, not the code: `tokenize` takes the folded STRING while `fold` returns `{text, map}`, so passing the object made `folded.length` undefined and the loop never ran, answering `[]` in silence. Fixed in the probe, with the reason recorded there - it is the same shape as this run's other quiet failures, a wrong input producing an empty answer rather than an error.
  - progress-failures, 49/49. Both modules compute values that are then printed, which is exactly where a liveness probe certifies nothing: a wrong duration or a miscounted tally looks like a right one on a terminal.
  - `duration` is pinned at all three documented shapes and at both band boundaries in each direction - 59s/1m00s and 59m59s/1h00m - plus the two examples from its own docstring, the zero-padding that keeps a column aligned, and that it TRUNCATES rather than rounding, so 119 seconds reads 1m59s and a progress line never claims more elapsed time than has elapsed.
  - `_column_count`'s documented preference for an even grid is asserted at the case the docstring describes: 4 cells that would fit 3 columns lay out as 2, because 3 would leave a lonely cell on row two. The `max(1, ...)` guard is asserted directly, since a cell wider than the terminal returning 0 columns would divide by zero in `grid`.
  - `error_kind` is asserted as the property it exists for - two titles failing the same way must group to ONE kind - rather than only as a string cut, because the whole point is that grouping on the full error would tally one of everything.
  - The failures table's identity rules are pinned: recording one title twice increments rather than duplicating, `first_failed_at` is kept while `last_failed_at` and `last_error` move, and one title failing at two sources is two independent rows. `min_failures` is exercised at the two values its docstring names plus one that excludes everything, and `count_since` is asserted to count TITLES rather than failures, to be scoped to one source, and to include the boundary instant.
  - Scores, claiming ONLY the two rows swept this iteration; 22 rows remain unswept:
  - correctness: None on the swept rows, on 77 known answers including five derived scores that matched the documented formulas exactly.
  - error handling: None on the swept rows; the empty-query, empty-text, empty-table and cell-wider-than-terminal cases are the ones that would have shown it.
  - architecture, documentation: None. Both files document the measurement or the reasoning behind each rule, which is what made deriving the expected values possible rather than guesswork.
  - testing: None on the swept rows.
  - security, performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 22 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 258 files.

Learnings: A documented score band is a known-answer surface, not an opinion. Where a module writes its formula and its band edges down, the battery derives every expected value from them and asserts the constants too, so a changed cutoff fails loudly rather than being re-blessed - and the ordering BETWEEN bands is worth asserting separately, because that is the property the tiers exist to provide and a single tier's numbers can be right while the ranking is wrong.

Next: Six front-end rows remain and are now known to be affordable. Iteration 9 continues the audit on that cluster - js-catalog-render and js-catalog-filter are the largest, sharing catalog.js - with 22 rows and 12 iterations left; that ratio is the run's real constraint and no full audit, and therefore no evaluator gate and no convergence, is possible until it closes.

## iter 9/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit, ledger still empty. This iteration swept js-catalog-filter - the predicates that decide which rows the owner sees and in what order, and the largest single behaviour in the viewer.

Changed: .jeffy/probes/js-catalog-filter/probe.py (new, 41 cases), PLAN.md (one row swept). No project code was touched.

Checkpoint: af9c881. Not a stall: a probe battery was added under .jeffy/probes/ and one inventory row changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 41 known-answer assertions, 41 held. No findings.
  - Every case states the exact id list that must come back, in order, which is the only assertion shape that works here: a filter keeping too much still renders a plausible page, and a sort falling back to insertion order still looks sorted.
  - The `flag` filter's eleven values are each exercised with their exact expected row set rather than merely being called. That is the case the Method singles out - a predicate returning true for everything filters nothing while looking exactly like a filter that works - and the id lists are what would catch it.
  - The documented union is asserted as a relation rather than as a third list: `review` must equal `unmatched` plus `low_confidence`, and each named flag must be strictly narrower. That is the distinction the workflow rests on, since a stats row showing 4 unmatched has to jump to those 4 and not to the 8 the union holds.
  - `mode` is exercised at both values on the SAME chip set, and it changes the answer: two genres under `any` return three rows, under `all` return none, because no item carries both. A documented parameter that changed nothing would be a finding.
  - The narrator chip is asserted to span illustrator too, which is the documented union - the column shows narrator||illustrator, so an item carrying either must stay findable under either name.
  - `read_status` sorting is the case most likely to be quietly wrong and is pinned directly: the lifecycle order is want_to_read, unread, reading, read, and alphabetically that would be reading, read, unread, want_to_read. It sorts by ordinal.
  - A missing `read_status` is asserted twice, on both the filter and the sort, because the two read it independently: filtering on unread catches the row with no status at all, and sortValue maps it to unread's ordinal. A partial payload from an older server is the documented reason.
  - Filters are asserted to combine as AND rather than OR: type=ebook keeps two rows, the Mystery chip keeps two, and together they keep the one row in both. A chain that ORed would return three and still look like it was filtering.
  - Five cases failed first and every one was MY expectation, not the code: I wrote the expected id lists in fixture order while the default sort is by name, and "Nightjar Post" precedes "Salt and Sextant". Corrected to the name order the code is right to produce, with the reason recorded in the battery so the next reader does not re-derive it.
  - The battery generates its scenario setup as inlined source rather than passing strings to `eval` in the sandbox: the strings are literals written in the probe, but inlining makes a typo a parse error instead of a silent runtime surprise.
  - Scores, claiming ONLY the row swept this iteration; 21 rows remain unswept:
  - correctness: None on the swept row, on 41 exact row-set and ordering answers.
  - error handling: None on the swept row; the missing-status and empty-result cases are the ones that would have shown it.
  - architecture: None. The filter registry and the separation of relevance from sortKey are both documented at the point of decision, which is what made the negative cases writable.
  - documentation, testing, UX: None on the swept row.
  - security, performance, dependency hygiene, observability, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 21 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 259 files.

Learnings: Write a battery's expected ORDER from the property that orders it, never from the order the fixture happens to be written in. Five cases here asserted id order because the fixture listed items 1,2,3,4, while the code sorts by name - the failures pointed at the sort, which was correct, and the fixture was what needed reading.

Next: 21 rows and 11 iterations after this one, so convergence is out of reach and the run's value is the batteries it leaves behind. Iteration 10 continues the front-end cluster with js-catalog-render, which shares catalog.js and can reuse this battery's fixture shape; the remaining rows after that are js-autocomplete, js-panels, js-shell, viewer-markup, the five scripts and packaging rows, and eleven Python rows led by the harvest family.

## iter 10/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit, ledger still empty. This iteration swept js-catalog-render, the table the owner actually reads, completing catalog.js alongside the filter row swept in iteration 9.

Changed: .jeffy/probes/js-catalog-render/probe.py (new, 48 cases), PLAN.md (one row swept). No project code was touched.

Checkpoint: 2e5d715. Not a stall: a probe battery was added under .jeffy/probes/ and one inventory row changed state, though no BACKLOG item did - nothing was filed at rubric severity, for the reason below.

Verification: 48 known-answer assertions, 48 held.
  - The escaping cases are exact strings rather than "contains a escaped character": `esc` must turn the four markup characters into their entities, and `highlight` must escape in all THREE slices it builds - before the span, inside it, and after - because it concatenates into innerHTML. Asserted by stripping the one element it is allowed to introduce, `<mark>`, and requiring no `<` survives.
  - The overlap rule is pinned because getting it wrong duplicates text rather than raising: with spans [0,6] and [3,9] the second is skipped and the answer is `<mark>Salt a</mark>nd Sextant`. Without the `start < at` guard the slice runs backwards and the row shows the same characters twice.
  - The guards are each driven with the field they exist for: `tagBadges(undefined)` renders nothing rather than throwing, `person` on a row carrying neither name field yields [], `esc(null)` and `esc(undefined)` both yield empty - `v == null` catches both, where a strict check would render the text "undefined" into the table - and `statusSelect` on a row with no status selects unread.
  - The render cases assert the count line as an exact string, which is the cheapest honest check of the whole pipeline: `3 / 3 items` unfiltered, `1 / 3 items` under a search, and the documented ` - by relevance` suffix present only while relevance is active AND the query non-empty.
  - Also pinned: a row without a cover emits NO img rather than one with an empty src, which a browser resolves against the page URL and re-requests; and an empty catalog renders zero rows with a `0 / 0 items` count rather than throwing.
  - INVESTIGATED AND NOT FILED, recorded so a later audit does not re-derive it. The first version of this battery crashed `visible()`: `chipFilters.narrator.accessor` is `i => [...i.narrator, ...i.illustrator]` and spreads both fields unguarded, so a row omitting them raises TypeError and blanks the page - which is exactly the failure the guards elsewhere in this file were added for, and the comments say so.
  - It is not filed because reaching it needs an off-contract payload. `db.fetch_items` runs every tag column through `tags_from_json`, which answers [] for NULL, so narrator, illustrator, genre, authors and user_tags are always present in a real response. The Operating envelope classes this surface machine-generated: the generator's real output is the contract, and hand-mangled variants are out of envelope, Low at most and Declined by default. `bundle`'s accessor has the same shape.
  - The fixture was corrected rather than the code, and the reason is written into the battery: a probe asserting a shape the server cannot produce pins a contract the project does not have. The partial row now omits only the SCALARS the guards genuinely protect.
  - Scores, claiming ONLY the row swept this iteration; 20 rows remain unswept:
  - correctness: None on the swept row, on 48 exact answers.
  - security: None on the swept row. Every innerHTML path escapes, checked by stripping the one permitted element rather than by looking for one entity.
  - error handling: None on the swept row, on the guards driven with their missing fields. The unguarded accessors above are out of envelope, not clean.
  - architecture, documentation, testing, UX: None on the swept row.
  - performance, dependency hygiene, observability, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 20 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 260 files.

Learnings: When a probe crashes the code under test, decide whether the INPUT was in envelope before deciding it is a finding. This one produced a real TypeError from a real unguarded spread, and the correct answer was still to fix the fixture: the server cannot emit that shape, so asserting against it would have pinned a contract the project never made and left a permanent false obligation in the battery.

Next: 20 rows and 10 iterations. The user has asked whether this is real progress and the answer belongs in the reply rather than here; the honest position is that findings have thinned sharply since iteration 1 while row coverage has not, so the remaining value is coverage rather than defects. Iterations 11+ should take the user's steer before continuing to spend budget the same way.

## iter 11/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit, ledger empty. The user was asked mid-run whether the remaining budget was buying anything and chose to spend it on the four highest-yield rows rather than on completing the inventory, accepting that convergence is out of reach. This iteration swept the first two of those four: webapp-remote-routes and check-cmd.

Changed: .jeffy/probes/webapp-remote-routes/probe.py (new, 40 cases), .jeffy/probes/check-cmd/probe.py (new, 34 cases), PLAN.md (two rows swept). No project code was touched.

Checkpoint: c3e734f. Not a stall: two probe batteries were added under .jeffy/probes/ and two inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 74 known-answer assertions across two rows, 74 held. No findings.
  - The steer is recorded here rather than in PLAN.md, which the template reserves for operational rules: the remaining rows are being chosen by expected defect yield, not by what would complete the table. Order is webapp-remote-routes and check-cmd (this iteration), then harvest-run, then backup-restore.
  - webapp-remote-routes, 40/40, and the scope is stated in the battery because it decides what the row may claim. The NETWORK behaviour belongs to rows already swept - url-import and outbound-guard own the scheme allowlist, the redirect re-check and the routability test; bundle-preview-parts and -tiers own the host gate and the report. What is left is the ROUTE's contract: how it maps each outcome onto a status code and a body.
  - That is why the collaborators are replaced at the seam rather than driven through a real server, and the reason is not convenience: a local http.server cannot be reached by either route, because url_import refuses a loopback address by design and fetch_bundle refuses a non-Humble host. A real server would exercise the refusal path already swept elsewhere and could not reach the success mapping this row exists to pin. The Lessons rule about probing a network GUARD with a real server still holds; the guard is not what this row covers.
  - The degradation path is asserted in full, since it is the one that invents data: a source that cannot answer yields a link_only candidate carrying the ITEM's title rather than the source's, the url preserved, the reason naming the failure, and the source attributed to the url's host. A network error takes the same path.
  - The documented catch ORDER is pinned as a property: a REJECTED url must never degrade to a link-only candidate, so a ValueError answers 400 with no candidate at all, while MetadataUnavailable answers 200 with one. Catching them in the wrong order would silently turn a refusal into an offer.
  - The two bundle-preview failure codes are asserted to DIFFER rather than each being checked alone, because the split exists to keep a retired bundle distinguishable from a url the project refused; collapsing them to one code would pass two separate assertions and still lose the distinction.
  - Both routes are asserted never to reach their collaborator for an unusable url, using a stub that raises if called - the property that makes a refusal a refusal rather than a slow failure - and a successful preview is asserted to leave the items table byte for byte unchanged, which is the module's documented promise that the report is a question and not a fact about the library.
  - check-cmd, 34/34. `run(sources=...)` is the module's own injection seam, so the real reporting logic is driven with stubs and every branch is reached without a live request.
  - The case worth sweeping this row for is REDACTION. A source's error can embed the request URL with the API key in it, and this command prints that string; the battery raises an error carrying a fake key and asserts it survives neither into the returned detail nor into anything written to the stream, while the 401 that tells a bad key from a dead host does survive. A probe checking only the status letters would certify a report that leaks a credential to the terminal.
  - The SKIP branch is asserted to be a refusal to ASK, not just a label: the stub records every call, and a source with an empty key or token is never asked. That is the documented point of it - an unkeyed source would return [] and report a hollow OK.
  - The summary is checked twice, once as its exact sentence and once as an invariant that the three counts partition the sources, so a miscount cannot hide behind a plausible-looking line.
  - Scores, claiming ONLY the two rows swept this iteration; 18 rows remain unswept:
  - correctness: None on the swept rows.
  - security: None on the swept rows, and this is the strongest claim in this entry: the credential in an error string is redacted before it reaches the report or the terminal, asserted on both.
  - error handling: None on the swept rows. Every documented failure mapping is pinned, including the two that must stay distinguishable.
  - architecture: None. Both modules take their collaborators as parameters, which is what made these sweeps reach every branch without a network.
  - documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 18 rows are unswept, so it never counts toward convergence and closeout is NOT entered. Convergence is out of reach this run by the user's explicit decision, not by oversight.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 262 files.

Learnings: State a row's scope in its battery when a neighbouring row owns part of the surface, and say what the stub stands in for. Two of this project's rows reach the network but their guards are swept elsewhere, so driving a real server here would have re-tested the refusal and never reached the mapping the row exists to certify - and without the note, a later reader would read the stubs as a shortcut rather than as the scope.

Next: Iteration 12 sweeps harvest-run, the largest remaining row and the one with real decision logic behind it - resume behaviour and parallelism. backup-restore follows. After those four the user's chosen work is done, and the remaining iterations should go to a WRAPUP with a handoff rather than to sweeping the low-risk remainder.

## iter 12/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Third of the four rows the user chose. Swept harvest-run, the largest remaining row and the one carrying the project's most consequential decision logic - resume behaviour, the 429 rules, and the parallel walk.

Changed: .jeffy/probes/harvest-run/probe.py (new, 58 cases), PLAN.md (one row swept). No project code was touched.

Checkpoint: f26460d. Not a stall: a probe battery was added under .jeffy/probes/ and one inventory row changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 58 known-answer assertions, 58 held. No findings.
  - Almost every rule in this module is about what happens when a source FAILS, and the rules are asymmetric on purpose. Each asymmetry is invisible to a liveness probe because all of them end in "the harvest finished", so each is asserted directly:
  - A CacheMiss is not a failure at all - it does not tick, does not settle the source as failed, does not mark it incomplete, and records nothing.
  - An ordinary error records a failure row, marks the source incomplete, and KEEPS DRAINING: the stub records every title it is asked for, and the queue is asserted to reach the titles below the failing one.
  - A 429 records NO failure row, because it says nothing about the title and source_quota already holds it. Asserted as an absence against a populated table, plus the positive half: the source is switched offline and the quota IS recorded.
  - A 429 keeps serving the rest from cache - the documented reason it does not stop the walk, since stopping would strand every cached title below the first uncached one. Every title is still asked for and the cached ones still tick.
  - A SECOND 429 breaks the walk, so the titles below it are never reached. The two 429 cases together are what pin the difference between "serve the rest from cache" and "stop hammering the API".
  - Redaction is asserted on BOTH consumers, which is what the code's own comment claims: the scrubbed detail is used for the log line and the stored row, so a fake key is checked to reach neither.
  - The worklist's determinism rules are pinned as the docstring states them: music and android skipped, per-type source routing, de-duplication so two items with one cleaned title cost one request, casefold sorting, and the case-only tie broken by the raw string because Python's sort is stable and a casefold-only key would fall back to SQLite's unordered scan.
  - `run`'s documented parameter is exercised at both values and changes the answer: a source with a live quota record starts offline and is reported incomplete, while `ignore_quota=True` leaves it online. An EXPIRED record is asserted not to be believed, which is the same rule from the other side.
  - A blocked source is asserted to be WALKED rather than skipped - the documented reason being that the walk is what keeps the progress number true, so a 90%-cached source still reports 90% rather than appearing to go backwards.
  - Eight cases failed first and every one was a fixture bug of mine, all three kinds worth recording. Six assumed `clean_title` lowercases - it strips edition and series noise and preserves case, and only the SORT folds case. One gave the stub source a fixed reset date in 2026-06, which is in the past, so `quota.blocked` correctly refused to believe it and the case asserted against a record that was never live. One misread the worklist docstring: "sorts past z" describes a title whose FIRST letter is accented, and a mid-word accent orders on its first letter like any other, so that case now asserts the property that actually holds for the pair - accents are not folded, so ordering is by codepoint.
  - Scores, claiming ONLY the row swept this iteration; 17 rows remain unswept:
  - correctness: None on the swept row, on 58 known answers.
  - error handling: None on the swept row, and this is where the row's weight sits: four distinct failure modes with four different documented responses, each asserted on both what it does and what it must NOT do.
  - security: None on the swept row - the credential in an error string is redacted before it reaches either the log or the stored row.
  - architecture: None. The `sources=`/`_conn=` seams are what let the real threading and tallying run with no network.
  - documentation, testing: None on the swept row.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 17 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 263 files.

Learnings: A stub's default must sit on the LIVE side of any freshness check it feeds. A stub source defaulting to a fixed past reset time made the quota assertions test nothing, because the code correctly declines to believe an expired record - the case looked like a code defect and was a fixture that had aged out. Defaults in a fixture are relative to now, or they expire.

Next: backup-restore is the last of the four the user chose, and its failure mode is the worst in the project - a restore that loses data. Iteration 13 sweeps it. After that the chosen work is done, and the remaining iterations should go to a WRAPUP handoff rather than to the low-risk remainder.

## iter 13/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Last of the four rows the user chose. Swept backup-restore, whose failure mode is the worst in the project: every other defect found this run produced a wrong answer, while a defect here destroys the only copy of data the owner cannot re-derive.

Changed: .jeffy/probes/backup-restore/probe.py (new, 73 cases), PLAN.md (one row swept). No project code was touched.

Checkpoint: 8d8d59f. Not a stall: a probe battery was added under .jeffy/probes/ and one inventory row changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 73 known-answer assertions, 73 held on the first run. No findings.
  - The cases are deliberately weighted towards what must NOT happen, because that is where the cost is. Every refusal path reads the live catalog's BYTES before and after and asserts they are identical - a missing snapshot, an unreadable snapshot, and eight wrong answers at the confirmation prompt.
  - The confirmation is the only thing between a stray command and the catalog, so it is driven with everything that is not the word: empty, lowercase, title case, `y`, `yes`, the word with a suffix, and a padded near-miss. Only the exact word after stripping is accepted, and the lowercase case is called out separately as the likeliest near-miss. Ctrl-D at the prompt is asserted to abort cleanly rather than propagate.
  - The ordering guarantee is asserted the strong way: for a bad snapshot path the confirmation function RAISES if it is called at all, so the case proves validation happens before the owner is even asked, not merely before the swap.
  - The WAL case is the one that justifies the module's central design choice, and it is exercised rather than assumed: a row is committed through a live `db.connect` connection, leaving it in catalog.db-wal, and the snapshot is asserted to contain it. A plain file copy would silently produce a database missing that row.
  - Sidecar removal is pinned for the same reason it exists: stale `-wal`/`-shm` files left beside a restored database can be replayed over it, silently undoing the restore. Asserted as their absence after a restore.
  - The safety copy is asserted to hold the REPLACED rows rather than the restored ones - the direction that makes it a safety copy at all - and exactly one is taken.
  - The damaged-catalog path is asserted on both halves of its documented promise: a catalog SQLite cannot open still yields a raw byte copy whose contents equal the damaged file verbatim, and the restore is NOT blocked by it. That is the case the whole fallback exists for, since an unopenable catalog is the likeliest reason to be restoring.
  - Traversal is checked on the extract side as an outcome rather than a mechanism: an archive carrying `../../escaped.jpg` puts every entry inside covers/ under its bare name, and the file does not appear outside the directory.
  - Scores, claiming ONLY the row swept this iteration; 16 rows remain unswept:
  - correctness: None on the swept row, on 73 known answers.
  - error handling: None on the swept row. The damaged, missing, unreadable and refused paths each have a documented response and each was asserted.
  - security: None on the swept row - the zip traversal case lands every entry inside covers/.
  - architecture: None. The `_input=` and `_now=` seams are what let the confirmation and the timestamped naming be driven exactly.
  - documentation, testing: None on the swept row.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 16 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 264 files.

Learnings: For a destructive operation, assert the bytes rather than the return value. Every refusal case here compares the live catalog's contents before and after, which is a stronger claim than "it returned False" - a function can report refusal and still have written, and on this surface that difference is the whole point of the row.

Next: The four rows the user chose are done, three iterations sooner than the budget allowed, and all four came back clean. Seven iterations remain. Their steer was about priority rather than about stopping, so iterations 14 onward continue down the same ranking - the mid-tier rows with real logic, led by keys-report, import-sheets, import-games and cli-dispatch - with the final iteration reserved for a WRAPUP handoff.

## iter 14/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Continuing down the user's ranking now that their four chosen rows are done. Swept keys-report, the largest of the mid-tier rows and the one with the most decision logic left: the four-state machine, the expiry arithmetic, and the three-group ordering.

Changed: .jeffy/probes/keys-report/probe.py (new, 60 cases), PLAN.md (one row swept). No project code was touched.

Checkpoint: cdff75b. Not a stall: a probe battery was added under .jeffy/probes/ and one inventory row changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 60 known-answer assertions, 60 held. No findings.
  - `report(conn, now=...)` takes an injectable clock, so every expiry answer is fixed arithmetic against 2026-08-02T12:00Z rather than something that drifts with the wall clock. That is the trap iteration 12 fell into with a stub reset time, avoided here by construction.
  - The ordering is the case this row is worth sweeping for, and it is written out in full. The rows are NOT one ascending column: dated rows split AROUND the undated ones, because plain ascending sorts already-dead keys above the ones the owner can still act on. Five keys - two live, one undated, two expired - are asserted to come back as live-soonest, live-later, undated, expired-most-recent, expired-oldest.
  - The tie rule is pinned for the reason the code gives: purchase date then name, so the order is a pure function of the data rather than of the query plan.
  - The state machine is exercised on all four states and on the two boundaries that decide them: a store with no importer is uncheckable rather than unredeemed, and a store WITH an importer but no games rows still classifies its keys as unredeemed - the documented case where `pools` has no entry and `EMPTY` is passed instead.
  - `matched` is asserted to be counted but never listed, and the partition is checked as an invariant: the four counts sum to `total`, and `reported` equals `total` minus `matched`. A state machine that lost a row would break the sum rather than merely looking plausible.
  - `expiring` is asserted to exclude BOTH hidden and already-expired rows, which is what makes it the tab badge's sibling: a hide that leaves the badge lit has not stopped the row reappearing.
  - `stale_hides` is pinned on the case that justifies its separate query: a hide on a key that has since become `matched` is NOT stale, and the cheap derivation - hides minus hidden rows shown - would count it, because matched rows are not in `rows` at all.
  - A key whose stored blob is not JSON is asserted to still report, with no expiry from the unreadable blob rather than a failed query.
  - `show_all` and `hidden` are each exercised at both values and each changes the output.
  - Two cases failed first, both mine, and the second correction is the more interesting. The MAX_NAME case first asserted a bound on the widest line, which was wrong because the long row is legitimately long. The second attempt asserted the short row was UNCHANGED by a long neighbour, which was also wrong: the column does pad to the widest name. The real contract is that it pads to the widest name CAPPED at MAX_NAME, so the assertion now measures the name column and checks it widens only to the cap and never to the full 92.
  - Scores, claiming ONLY the row swept this iteration; 15 rows remain unswept:
  - correctness: None on the swept row, on 60 known answers including the full ordering.
  - error handling: None on the swept row; the unparseable expiry and unreadable blob paths are the ones that would have shown it.
  - architecture: None. The injectable clock is what made the expiry arithmetic assertable at all.
  - documentation, testing, UX: None on the swept row.
  - security, performance, dependency hygiene, observability, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 15 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 265 files.

Learnings: When a first assertion fails, check whether the SECOND one is testing the same misunderstanding. Both attempts at the MAX_NAME case encoded a wrong model - once as a width bound, once as an invariance claim - and only reading the actual rendered rows settled what the cap does. A failing assertion is evidence about the model, not only about the value.

Next: 15 rows remain with 6 iterations. Iteration 15 continues with import-games and import-sheets, both of which parse files the project did not write. The final iteration is reserved for a WRAPUP handoff, so realistically 4 more sweeping iterations remain.
