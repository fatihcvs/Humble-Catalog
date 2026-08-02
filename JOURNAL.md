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

Checkpoint: recorded below. Not a stall: three probe batteries were added under .jeffy/probes/ and three inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

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
