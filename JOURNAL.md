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

## iter 15/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Continuing the ranking. Swept import-games and import-sheets, the two rows that read files the project did not write - the same shape as the surface where every defect this run was found.

Changed: .jeffy/probes/import-games/probe.py (new, 35 cases), .jeffy/probes/import-sheets/probe.py (new, 62 cases), PLAN.md (two rows swept). No project code was touched.

Checkpoint: 6ecca3f. Not a stall: two probe batteries were added under .jeffy/probes/ and two inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 97 known-answer assertions across two rows, 97 held on the first run of each. No findings.
  - import-games, 35/35. This module's most important behaviour is a pair of REFUSALS, and both exist because one shape - an empty list - is written by two different NORMAL states: a logged-out Heroic store and a private Steam profile. Acting on it would delete a good library, and the next bundle preview would then report a whole bundle as new.
  - Both refusals are asserted the strong way, by reading the games table back and comparing it against what it held before: `store_games` raises on empty rather than clearing, and the library is byte-identical afterwards. `read_heroic` raises on unparseable JSON rather than reading it as "no games", with the message naming the file, because Heroic may simply be mid-write.
  - The transaction guarantee is exercised rather than assumed: a malformed row raises inside the write, AFTER the delete has run, and the previous rows are asserted to still be there. That is the one case where the `with conn:` block is doing work no other assertion would notice.
  - The private-profile branch is reached through the `http=` seam with a stub session, so the case that motivated the whole guard runs with no network, and `include_appinfo` is asserted to be sent - without it the API returns bare appids and every title would go unmatched.
  - Per-store replacement is pinned on both sides: a re-import drops a game removed upstream AND leaves every other store untouched.
  - import-sheets, 62/62. The rule this module is built around is gap-fill only, and it is asserted directly: a row whose every field the owner has already set is read back unchanged after an import that had something to say about all of them.
  - The header vocabulary carries a distinction worth pinning, and `unknown_headers` exists solely to keep it: a header mapping to None is understood and deliberately dropped, because bundles and publishers are authoritative from Humble orders, while an unrecognised header is a typo that silently imports nothing. A mixed header row is asserted to report only the typos.
  - `_cell` treating a numeric 0 as PRESENT is pinned, since the documented meaning is that a 0 rating means "unrated" and is skipped later with that meaning rather than being lost at the read.
  - `norm_title`'s float rule is pinned because it is the non-obvious one: a numeric title arrives from a sheet cell as a float, and 1632.0 must normalize to "1632" or it matches nothing.
  - `match` is asserted on all three outcomes including the one that refuses to guess: two catalog rows sharing a normalized title answer `ambiguous` rather than picking one, and an unmatched title suggests the catalog's ORIGINAL spelling rather than its normalized key.
  - Scores, claiming ONLY the two rows swept this iteration; 13 rows remain unswept:
  - correctness: None on the swept rows.
  - error handling: None on the swept rows, and this is where the weight sits - three documented refusals, each asserted to leave the stored data untouched.
  - security: None on the swept rows.
  - architecture: None. The `root=` and `http=` seams are what let both file readers be driven from fixtures.
  - documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 13 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 267 files.

Learnings: Where one input shape is produced by two different normal states, the refusal is the feature and the battery's job is to prove the stored data survived it. Both of this module's guards exist because an empty list means "logged out" as often as it means "owns nothing", and asserting only that a call raised would miss the half that matters - that nothing was deleted on the way to raising.

Next: 13 rows remain with 5 iterations, and the last is reserved for the WRAPUP handoff. Iteration 16 takes cli-dispatch and reset-cmd; harvest-reports and privacy-gates are the other Python rows worth having, and the seven front-end and scripts rows would be next after that.

## iter 16/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Continuing the ranking. Swept reset-cmd and cli-dispatch. This iteration also produced the run's only privacy near-miss, recorded in full below because it matters more than either sweep.

Changed: .jeffy/probes/reset-cmd/probe.py (new, 42 cases), .jeffy/probes/cli-dispatch/probe.py (new, 62 cases), PLAN.md (two rows swept). No project code was touched.

Checkpoint: 082003f. Not a stall: two probe batteries were added under .jeffy/probes/ and two inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 104 known-answer assertions across two rows, 104 held. No findings.
  - A PRIVACY NEAR-MISS, and the most important thing in this entry. The first version of the cli-dispatch battery invoked `export` with a valid path and again with no argument at all. `export`'s path is OPTIONAL and defaults to catalog.csv, so both runs SUCCEEDED and wrote real exports of the owner's catalog into the repo root: catalog.csv at 516 KB and out.csv at 95 KB, both untracked, sitting exactly where this loop's `git add -A` checkpoint would have swept them in.
  - They were deleted before any commit, `git status` was re-checked to confirm, and the Verify command's own gates then ran clean. Nothing reached a commit and nothing reached the leak scanner's history check. But it would have, one iteration later, and no automated check in this project would have stopped it: `check_no_data_tracked` filters paths of TRACKED files, and these were untracked until the checkpoint added them.
  - The battery was rewritten so it cannot recur. The valid-column control is now checked IN-PROCESS against `export.COLUMNS` instead of by running the command; `export` is removed from the missing-argument case because its argument is optional; its default path is asserted from `--help` text rather than by invoking it; and a standing guard case now asserts that no catalog.csv, catalog.xlsx, out.csv or out.xlsx exists in the repo root after the battery runs, so a future case that writes one fails loudly.
  - The rule this teaches is narrower and sharper than "be careful": a CLI battery must never invoke a subcommand whose SUCCESS has a side effect on the owner's data. The refusal cases were always safe, because they exit before `db.connect()`; the danger was precisely the one case written to prove the happy path.
  - reset-cmd, 42/42. Same discipline as the backup row: assert what SURVIVES. The preserved layer - raw_orders, source_cache - is asserted to be intact after a wipe, because those are what a rebuild reads FROM and losing them turns a rebuild into a re-download, or into permanent loss for a bundle since retired.
  - The snapshot's DELETE-first rule is exercised end to end rather than read: reset with a rating set, rebuild the row with the rating cleared, reset again, and assert no stale snapshot remains. Without the DELETE the old rating would resurrect on the next rebuild, which is the kind of defect that looks like the feature working.
  - The delete ORDER is asserted twice, from both directions: functionally, by enabling `PRAGMA foreign_keys = ON` and resetting successfully, and structurally, by asserting every child table precedes `items` in DERIVED_TABLES and that `bundles` is last.
  - The three preserved tables are asserted to be ABSENT from DERIVED_TABLES, which is the cheapest possible guard against someone adding one to the list.
  - cli-dispatch, 62/62. The envelope classes CLI arguments user-error, where a wrong value earns a clear failure MESSAGE, so the cases assert the text the owner sees and not merely the exit code. The `--override-edited` refusal is asserted to explain that `--reset` would wipe the hand edits the override exists to carry through; the export suffix refusal to name both accepted suffixes; the unknown-column refusal to name the offending column.
  - `check_dependencies` is driven by temporarily adding an absent module to the dependency map, restoring it in a finally, and asserting the map is clean again afterwards - the one case that could otherwise leave the module poisoned for every later case.
  - One case failed first and was mine: I asserted `export` refuses without an argument. It does not; the argument is optional. That failing assertion is what surfaced the export files.
  - Scores, claiming ONLY the two rows swept this iteration; 11 rows remain unswept:
  - correctness: None on the swept rows.
  - security: None on the swept rows. The privacy near-miss above was caused by the BATTERY, not by the project - `export` writing where it is told is correct behaviour.
  - error handling: None on the swept rows; every documented refusal is asserted with its message.
  - architecture: None. The `_conn=`/`_input=` seams are what let a destructive command be driven exactly.
  - documentation, testing, UX: None on the swept rows.
  - performance, dependency hygiene, observability, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 11 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 269 files.

Learnings: A probe that drives a CLI must never invoke a subcommand whose SUCCESS writes. The refusal cases in this battery were safe by construction, because they exit before touching the database; the one case written to prove the happy path wrote 600 KB of the owner's catalog into the repo, untracked, one checkpoint away from being committed. Neither `check_no_data_tracked` nor `leak_check` would have caught it beforehand: the first filters paths of already-tracked files, and the second scans content only once something is staged. Assert a happy path in-process, or against `--help`, or not at all.

Next: 11 rows remain with 4 iterations, the last reserved for the WRAPUP handoff. Iteration 17 takes harvest-reports and privacy-gates, the last two Python rows with real logic; the remaining nine are five front-end and four scripts and packaging rows, which the handoff will name.

## iter 17/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Swept the last two Python rows with real logic - harvest-reports and privacy-gates. The second was chosen deliberately after iteration 16's near-miss: the gates are what the standing order rests on, and nothing had ever probed what they refuse to look at.

Changed: .jeffy/probes/harvest-reports/probe.py (new, 28 cases), .jeffy/probes/privacy-gates/probe.py (new, 59 cases), PLAN.md (two rows swept). No project code was touched.

Checkpoint: 25ac5ec. Not a stall: two probe batteries were added under .jeffy/probes/ and two inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 87 known-answer assertions across two rows, 87 held. No findings.
  - harvest-reports, 28/28. The trim is the case worth having: it is counted in RUNS, not rows, because a run is one started_at spread over up to six sources and trimming rows would behead a run mid-way, leaving a partial record that reads as a complete one. Asserted with four runs of three sources at keep=2: exactly the two newest survive, and each survives WHOLE at six rows rather than some truncated count.
  - `forget` is asserted to count runs rather than rows for the same reason, and the singular/plural forms of its message are both pinned.
  - The failure rate's missing denominator is pinned on both sides, which is the documented distinction: a cache-only source that made no live requests prints a dash, never 0%, because 0% would claim it never fails when it never tried.
  - The PRIVACY contract stated in `report_runs`' own docstring is asserted directly: the runs report holds source names, counts and timestamps and never a title, which is what makes that output safe to paste into an issue. The case seeds a failure row carrying a real-shaped title and asserts it does NOT appear in the runs output while the source name does, so a column added later that leaked one would fail here rather than in a paste.
  - privacy-gates, 59/59, and the framing matters: a defect in these is silent by construction, because a gate that scans too little reports `clean` exactly as loudly as one that scans everything. So the cases are mostly about COVERAGE - what each gate refuses to look at.
  - `should_scan`'s exclusions are pinned on both sides: the nine excluded directories are skipped at any depth, but a directory whose NAME merely contains an excluded word is still scanned, because the exclusion is by path part and not by substring.
  - The sidecar rule is pinned as the comment explains it: `catalog.db-wal` has suffix ".db-wal", so a `Path.suffix == ".db"` test misses it, and under WAL that sidecar can hold thousands of items the main file does not yet have. Matched against the whole filename, all four database shapes plus .bak and .xlsx.
  - That `leak_check.py` is not scanned by either scanner is pinned, since it quotes every ALLOWED entry verbatim and its old blobs quote entries since removed - scanning either would report the allowlist as a leak.
  - The two scanners are asserted to SHARE their matcher and their `should_scan`, on `__module__` rather than identity, because this battery loads the module by path while the history script imports it by name.
  - `check_no_data_tracked`'s pattern list is exercised on fourteen data shapes and on eight ordinary repo files that must not trip, including the two committed images. The CLI export names are pinned as a direct consequence of iteration 16: `catalog.csv` is forbidden, and an unrelated csv fixture is not, because the list names exact export filenames rather than `*.csv`.
  - This battery deliberately does NOT repeat the matcher's word-boundary cases; tests/test_leak_check.py holds 27 of those from 570d5f4, and duplicating them would be coverage that grows without protecting anything new.
  - Scores, claiming ONLY the two rows swept this iteration; 9 rows remain unswept:
  - correctness: None on the swept rows.
  - security: None on the swept rows, and this is the entry's strongest claim - the gates' coverage rules hold on both sides, and the runs report carries no title.
  - error handling: None on the swept rows; the empty-history and no-attempts paths are the ones that would have shown it.
  - architecture: None. The two scanners sharing one matcher and one `should_scan` is what makes them impossible to drift apart, and it is asserted rather than assumed.
  - documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 9 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 271 files.

Learnings: A checker's own coverage rules deserve a battery more than its matching rules do. The matching was already pinned by 27 tests; what nothing had ever exercised was which files the gate declines to read - and a gate that quietly skips a directory reports `clean` in exactly the same words as one that read everything. Probe the exclusions, on both sides, or the check is trusted rather than verified.

Next: 9 rows remain - five front-end and four scripts and packaging - with 3 iterations, the last reserved for the WRAPUP handoff. Iteration 18 takes js-shell and js-panels, iteration 19 viewer-markup and js-autocomplete if they fit, and iteration 20 writes the handoff naming whatever is left.

## iter 18/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Swept js-shell and js-panels. This iteration also made a small change to shared test infrastructure, recorded below because it is the only non-probe code this run has touched outside a filed task.

Changed: tests/js/harness.mjs (the element stub now RECORDS attributes), .jeffy/probes/js-shell/probe.py (new, 27 cases), .jeffy/probes/js-panels/probe.py (new, 26 cases), PLAN.md (two rows swept, three re-swept).

Checkpoint: a5098e5. Not a stall: two probe batteries were added, test infrastructure changed, and two inventory rows changed state, though no BACKLOG item did - this audit found nothing to file.

Verification: 53 known-answer assertions across two rows, 53 held. No findings.
  - A HARNESS CHANGE, and why it was made rather than worked around. Four cases failed first because the DOM stub's `getAttribute` returned null unconditionally and `setAttribute` discarded its argument, so `showSection`'s aria-current marking was unobservable - and that is the only signal a screen reader gets about which section is showing. A battery that skipped it would have left half of `showSection` uncertified while flipping the row.
  - The change is additive and was checked to be safe before it was made: `grep getAttribute humble_catalog/webapp/static/*.js` returns nothing, so no viewer script reads attributes back, and no test in the suite referenced getAttribute or aria-current. Nothing depended on the old null.
  - Because the harness is shared, all three previously-swept JS rows were re-run against it rather than assumed unaffected: js-fuzzy 28/28, js-catalog-filter 41/41, js-catalog-render 48/48, each unchanged. All three are re-swept at this checkpoint.
  - js-shell, 27/27. The routing rule worth pinning is a refusal to be helpful: an unknown hash falls back to Library WITHOUT rewriting the URL, because a silent rewrite would erase the evidence that a bookmark went stale. Asserted on three bad hashes by reading `location.hash` back afterwards and requiring it untouched - exactly the decision a later tidy-up would reverse, with nothing else in the suite noticing.
  - The hash form is asserted to be exact in both directions: `#library` without the slash and `#/LIBRARY` in the wrong case both fall back rather than matching loosely.
  - `showSection` is pinned on panel visibility AND on aria-current, with an invariant that exactly one tab is current in every case - a state where two tabs claimed `page`, or none did, would render plausibly and mislead assistive tech silently.
  - The library's badge is asserted to stay empty even when a pending count is deliberately set for it, and a zero count is asserted to render as an empty string rather than "0".
  - js-panels, 26/26. The case this row is worth sweeping for is a counting INVARIANT the code documents as the fix for a real bug: `keyChipCounts` counts by `displayState` rather than reading the server's `counts`, because that map partitions every key - matched and hidden included - so a chip reading "Not in a library 624" would deliver fewer than 624 once hidden rows moved to their own bucket.
  - The code calls that equality true "by construction". It is checked rather than trusted: for all four chips, the count is asserted to equal the length of what selecting that chip actually shows, and the four counts are asserted to sum to every row.
  - `displayState`'s override is pinned on two rows whose server states differ - unredeemed and uncertain - both of which must collapse to the hidden chip, since an earlier design that made hidden a second axis produced exactly the mismatched chip this replaced.
  - `keysExpiring` is asserted to exclude both the hidden row that has a live expiry and the row whose expiry has passed, which is the same rule the CLI report follows.
  - Scores, claiming ONLY the two rows swept this iteration; 7 rows remain unswept:
  - correctness: None on the swept rows, on the chip-partition invariant and the routing answers.
  - accessibility: None on the swept rows, and this is the first iteration able to claim it at all - the aria-current marking is now observable, and exactly one tab is current in every case.
  - error handling: None on the swept rows; the unknown-hash and empty-selection paths are the ones that would have shown it.
  - architecture, documentation, testing, UX: None on the swept rows.
  - security, performance, dependency hygiene, observability: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 7 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - Verify command: pytest 1164 passed (exit 0), unchanged by the harness edit; check_no_data_tracked exit 0; leak_check exit 0 over 5251 terms and 273 files.

Learnings: When a probe cannot observe half of what a row does, extending the harness beats narrowing the assertion - but only after checking that nothing depended on the old behaviour, and only with every battery that shares the harness re-run. The alternative was flipping a row while a documented accessibility contract stayed uncertified, which is the failure the inventory exists to prevent.

Next: Iteration 19 is the last sweeping iteration and takes js-autocomplete and viewer-markup if both fit. Iteration 20 writes the WRAPUP handoff naming whatever remains - on current pace five or six rows, all of them front-end or packaging.

## iter 19/20 | ce2620c5-151422 | 2026-08-02 | AUDIT | audit

Task: Last sweeping iteration. Swept viewer-markup, which is also the first row this run to come back with a finding since iteration 6.

Changed: .jeffy/probes/viewer-markup/probe.py (new, 40 cases), BACKLOG.md (J1 filed), PLAN.md (one row swept).

Checkpoint: 36b884c. Not a stall: a probe battery was added under .jeffy/probes/, one inventory row changed state, and J1 was filed.

Verification: 40 known-answer assertions, 39 held and 1 failed as a finding.
  - The cases that earn this row are CROSS-FILE, and they are the reason it was worth sweeping at all rather than eyeballing the markup. The scripts write into selectors the HTML must provide, and a selector that does not exist fails in the quietest way available: querySelector answers null, the write goes nowhere, and every test that checks the scripts in isolation still passes.
  - So the battery scans every `$("#id")` and `querySelector("#id")` across the viewer's scripts and asserts the markup provides each one. It also guards against that check passing vacuously, by asserting the scan found more than ten selectors - a regex that stopped matching the codebase's style would otherwise report a clean sweep over nothing.
  - The section wiring is asserted in the same direction, and the section list is READ from shell.js rather than retyped, so adding a section to one file and not the other fails here. For each of the four: a `#tab-<id>`, a `#section-<id>`, a `.badge-count` span inside the tab, an `href="#/<id>"`, and the panel starting hidden. A tab without a badge slot would drop its count silently; a panel not starting hidden would paint two sections at once.
  - No stale selector was found, and every section is wired both ways.
  - J1, filed, Low. Eleven filter controls carry no accessible name. `#f-type` and `#f-flag` are bare selects with no label, no aria-label and no aria-labelledby, so a screen reader announces each as "combo box" and their first option text is a visible cue only. Nine inputs have a placeholder and nothing else; the accname spec does fall back to it, but that name disappears exactly when the field is in use.
  - Severity was judged rather than assumed. Low, not Medium: this surface has one known user, the placeholder fallback covers nine of the eleven, and the rubric puts naming at Low. It is filed rather than declined because four sibling controls already carry aria-label, so the intent is established and these are the gaps in it - and because the Goal lists accessibility as a dimension to audit where a user-facing surface exists.
  - The row is flipped to swept anyway: a sweep that finds a defect has still swept the row, and the finding is the evidence. Fixing J1 will change index.html and stale it, which the next run re-sweeps by re-running the same battery.
  - The CSS cases assert two things a colour-only design would fail: the active filter chips are marked by an outline and weight rather than by hue alone, and every custom property used is defined - a `var(--typo)` resolving to nothing renders as an invisible or unstyled control with no error anywhere.
  - Scores, claiming ONLY the row swept this iteration; 6 rows remain unswept:
  - accessibility: LOW, J1, on the swept row.
  - correctness: None on the swept row - no stale selector, and the section wiring is complete in both directions.
  - documentation, architecture, testing, UX: None on the swept row.
  - security, error handling, performance, dependency hygiene, observability: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 6 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  - js-autocomplete was NOT attempted and is left unswept with a reason rather than half-done: `autocomplete.js` is not in the harness's VIEWER_JS list and is replaced by a stub in the sandbox, so driving it needs a second harness change on the run's last sweeping iteration. That is the wrong time to touch shared test infrastructure, and a partly covered row is unswept.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 274 files.

Learnings: A cross-file assertion needs a guard against passing vacuously. The selector check scans the scripts with a regex and asserts the markup provides every hit; if that regex ever stops matching the codebase's style it would find nothing, compare nothing, and report a clean sweep. One extra case - the scan found more than ten selectors - is what keeps the check honest, and any battery that derives its inputs by scanning needs the same.

Next: Iteration 20 is the final one and is a WRAPUP. J1 is small enough to fix inside it - the acceptance check already exists and the fix is eleven attributes - so the wrapup should close J1 first if it fits cleanly, then tidy the ledger and write the handoff naming the six rows left: js-autocomplete, demo-catalog, favicon-fixtures, os-wrappers, packaging-ci, and humble-login.

## iter 20/20 | ce2620c5-151422 | 2026-08-02 | WRAPUP | done

Task: Final iteration. Closed J1, tidied the ledger, and wrote the handoff. J1 was taken rather than deferred because its acceptance check already existed and its fix was eleven attributes, so an empty ledger was reachable inside the wrapup.

Changed: humble_catalog/webapp/static/index.html (11 controls given an aria-label), tests/test_webapp.py (one assertion relaxed to its siblings' form), BACKLOG.md (J1 deleted), JOURNAL.md (this entry and the rotation).

Checkpoint: 04ab9ea for the J1 fix; the wrapup bookkeeping follows it.

Verification: J1's acceptance check passes and the run closes green.
  - Acceptance check: `.jeffy/probes/viewer-markup/probe.py` exits 0 at 40/40, up from 39/40, with `case_every_form_control_has_an_accessible_name` listing no control. `#f-type` and `#f-flag` now carry `aria-label`, as do the nine inputs that had only a placeholder.
  - THE VERIFY GATE WENT RED, and the repair is recorded rather than smoothed over. `test_index_has_autocomplete_filters` asserted the literal `'<select id="f-type">'`, closing bracket included, so adding an attribute broke it.
  - It was repaired inside the iteration rather than reverted, under the gate's stated exception: the assertion was green ONLY because the element carried no attributes, which is precisely the defect J1 fixes. The two sibling assertions immediately above it already use the open-ended form (`'<input id="f-genre"'`), so the repair makes the line match its own file's convention, and the test's stated claim - that these small closed lists stay SELECTS rather than becoming autocomplete inputs - is unchanged and still enforced.
  - Differential evidence, as the exception requires: the suite is 1164 passed both before and after the whole change, the same count as at the previous checkpoint, so exactly one assertion changed form and none was lost or skipped. All four JS batteries that read this markup were re-run and hold unchanged - js-shell 27/27, js-panels 26/26, js-catalog-render 48/48, js-catalog-filter 41/41 - and the viewer-markup battery moved only in the intended direction, 39/40 to 40/40.
  - The markup change is additive: eleven `aria-label` attributes, no element removed, renamed or restructured, and no id touched, so every selector the scripts query still resolves.
  - Verify command: pytest 1164 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 over 5251 terms and 274 files.
  - THE RUN IS NOT CONVERGED, and the reason is structural rather than an oversight. The Definition of done requires the Surface inventory to list no unswept row; six remain. No audit this run was full, so the evaluator gate never became applicable - it requires a clean FULL audit - and no Converged line is appended. The ledger being empty is one clause of convergence, not convergence.

Learnings: A test that pins a literal including its closing bracket asserts the absence of every attribute, which is almost never what it means. The claim here was "these stay selects"; the form `'<select id="f-type">'` also silently claimed "and carry nothing else", and that second claim is what broke when an accessibility attribute was added. Match the open-ended form the sibling assertions already used.

Handoff for the next run.
  - Start a NEW session. The state files carry the run forward and the context does not; relaunching in this session keeps every accumulated token and forfeits the clean-context benefit the loop is built on.
  - Six rows remain unswept, and they are the cheap tail rather than the risky part. `js-autocomplete` needs `autocomplete.js` added to the harness's VIEWER_JS list, which is a real but small change to shared test infrastructure - do it first in a run with budget to re-run the five JS batteries afterwards, as iteration 18 did. `humble-login` needs a real browser and a profile directory. `demo-catalog`, `favicon-fixtures`, `os-wrappers` and `packaging-ci` are scripts and packaging, and `os-wrappers` in particular is three shells of parity that only a probe comparing the three can check.
  - Convergence needs those six plus one FULL fresh-evidence audit in a single iteration plus the evaluator gate. On this run's pace that is roughly 8 to 10 iterations, and it is reachable: the expensive part is done, since 51 rows now have committed batteries that re-run in seconds rather than needing their instrument rebuilt.
  - What this run learned about the codebase, which is worth more than the row count: every defect found was at a boundary where outside data enters - the bundle page blob, request bodies, field values. The interior came back clean across roughly 900 fresh assertions. Nine of the ten Lessons added this run are about how to probe, not about what is broken.
  - The one real defect was H1, found in iteration 1: a bundle tier whose machine-name list arrived as a string was iterated character by character, reporting a 1-item tier as 10 and listing single letters as things to buy. Everything after it was Low.
  - Two near-misses are worth carrying forward as habits, both recorded as Lessons: a probe that invoked `export` with a valid path wrote 600 KB of the real catalog into the repo root, untracked and one `git add -A` from being committed, and neither privacy gate would have caught it beforehand; and a settled-class line was drafted claiming an enumeration returned 6 sites when it returned 19, with 13 still broken.

Next: Nothing. This is the final iteration; the run ends here with the report to the user.

## iter 20/20 | ce2620c5-151422 | 2026-08-02 | ROTATION | rotation

Task: JOURNAL.md passed 500 lines when the WRAPUP entry was appended, so all but the last 10 entries were moved to JOURNAL-archive.md.

Changed: JOURNAL.md (19 entries removed, preamble and the last 10 kept), JOURNAL-archive.md (the same 19 appended to what it already held).

Checkpoint: shared with the WRAPUP entry above; this is an additional entry, not a separate iteration.

Verification: Counted rather than assumed, because silent loss is the failure mode here.
  - JOURNAL.md held 29 entries at 842 lines; it now holds 10 plus this one at 343 lines, with the preamble and its heading-grammar example untouched.
  - JOURNAL-archive.md went from 23 entries to 42, which is 23 + 19. It was appended to, never rewritten, and the count is asserted to have RISEN by exactly the number moved - the stop hook rejects an archive whose entry count fell.
  - The split matched only lines beginning `## iter` followed by a digit, so the fenced example in the preamble was neither counted nor moved.

Learnings: None beyond the mechanism already written down.

Next: Nothing. The run ends with this iteration.
