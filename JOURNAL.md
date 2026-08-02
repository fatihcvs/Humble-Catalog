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

## iter 2/10 | 84948f5f-185203 | 2026-08-01 | C1 | done

Task: C1 (High, runtime, security) - close the class of outbound requests sent to a URL named by third-party content without validating the destination.

Changed: humble_catalog/outbound.py (new, the boundary), humble_catalog/url_import.py (destination rules moved out, `_fetch_html` now runs through the boundary), humble_catalog/extract.py (cover fetch guarded), humble_catalog/sources/comicvine.py (API_HOSTS allowlist, credits checks before sending), tests/test_outbound.py (new, 12 tests), tests/test_extract.py (autouse fixture keeping the suite off live DNS), .jeffy/probes/outbound-guard/probe.py (new), PLAN.md (outbound-guard row added and swept, url-import re-swept), BACKLOG.md (C1 deleted, the unsound B1 settled-class line replaced).

Checkpoint: 45a18f4. Not a stall: runtime code, tests and a probe battery changed, and C1 moved from open to settled.

Verification: The filed reproduction was re-run first, before any edit, and both halves still reproduced.
  - Acceptance check, both halves, after the fix. `.jeffy/probes/outbound-guard/probe.py` exits 0 at 41/41. Against the UNFIXED extract.py and comicvine.py - copied aside and restored, never checked out over uncommitted work - it scores 34/41, and the 7 failures are the two reproductions: the foreign server's log shows `/api/issue/4000-1/?api_key=PROBE-KEY-VALUE&...` and two cover files written from loopback. So the check is strong enough to fail.
  - The enumeration, which is the half B1 got wrong. It lists the IDIOM, not the fix: `grep -rnE "(requests|self\.http|client\.http|http|sess|session)\.(get|post|request)\(" humble_catalog/ --include=*.py` returns 5 sites. outbound.py is the guard; url_import goes through it; humble_api and import_games build every URL from a constant host; sources/base takes its URL from callers, and every get_json call site is a literal https constant except comicvine.credits, now checked against API_HOSTS. Each site is disposed of in the Settled classes line.
  - A design point the backlog line understated, found while fixing. Routability is NOT sufficient for the ComicVine site: an attacker's own host is publicly routable and would still be handed the API key, which rides in the query string. That is why the boundary takes `allowed_hosts` and why credits passes it; the cover fetch, which carries no credential, needs only the network check. One class, two rules, one parameter.
  - Contract preserved. url_import keeps `_publicly_routable`, `_check_redirect_target`, ALLOWED_SCHEMES, MAX_REDIRECTS and REDIRECT_STATUSES as the names its tests and battery use, and `_fetch_html`'s behaviour is unchanged: the 46-case url-import battery was re-run unchanged and held 46/46, which is what re-sweeps that row rather than flipping it back. comicvine.credits gains one refusal path, recorded in its docstring in this same iteration. extract._download_covers keeps its signature; a refused cover raises ValueError into the existing handler and counts as a failed cover, so a hostile icon URL costs one cover and never the harvest.
  - A regression the fix introduced and this iteration removed: guarding the cover fetch made tests/test_extract.py resolve the fixture's imgix hostname, quietly making a hermetic test depend on live DNS. An autouse fixture now states that assumption explicitly, and every case in tests/test_outbound.py uses an IP literal or a reserved-TLD name so getaddrinfo answers without a query.
  - Verify command: pytest 1021 passed (exit 0), up from 1005 with 16 new tests; check_no_data_tracked exit 0; leak_check exit 0.

Learnings: Judge an outbound-destination guard by what the request CARRIES, not only by where it goes. A routability check answers "could this reach the LAN"; it does not answer "could this hand our credential to a stranger", and a request with a key in its query string needs a host allowlist. Separately: adding a network guard to code a test drives with a fixture URL can silently make the suite depend on DNS - state the assumption in a fixture rather than letting the resolver decide whether the suite passes.

Next: C2 (Medium) - cap the cover body. The boundary added here is where the cap belongs, since it already owns the request.

## iter 3/10 | 84948f5f-185203 | 2026-08-01 | C2 | done

Task: C2 (Medium, runtime, error handling) - cap the third-party cover body instead of buffering it whole.

Changed: humble_catalog/outbound.py (read_capped added, the cap now lives beside the request it belongs to), humble_catalog/url_import.py (`_read_capped` reduced to a decode over it), humble_catalog/extract.py (MAX_COVER_BYTES, stream=True, capped read), tests/test_outbound.py (+4), tests/test_extract.py (explicit response double, +1 end-to-end), .jeffy/probes/outbound-guard/probe.py (+8 cases), BACKLOG.md (C2 deleted, one Proposed item filed), PLAN.md (two rows re-swept, two Lessons).

Checkpoint: 0a5816b. Not a stall: runtime code, tests and a probe battery changed, and C2 moved from open to closed.

Verification: Acceptance check run after the fix, against a real server serving one byte past the shipped cap.
  - `.jeffy/probes/outbound-guard/probe.py` exits 0 at 49/49. Against the uncapped downloader - copied aside and restored - it scores 45/49, and the four failures are the point: `covers: an oversized cover is not written` got 1, and an 8 MiB file was left on disk under the name a real cover would have.
  - That differential only became real after a defect in my own probe. The oversized handler read `extract.MAX_COVER_BYTES`, which does not exist in code predating the fix, so the handler raised, the request failed for the wrong reason, and the case PASSED against the unfixed downloader while measuring nothing - 48/48 both sides. Holding the size as a literal and asserting it equals the shipped constant separately is what made the check able to fail.
  - The overflow policy is a parameter, not an assumption, because the two callers want opposite answers: the page reader truncates (OpenGraph tags live in <head>, so a partial read still parses) and the cover writer refuses (half a JPEG on disk looks like a real cover and would never be re-fetched). Exercised at both values on the same oversized body.
  - Contract preserved. `_read_capped` keeps its name, signature and truncating behaviour, including that it stops on a chunk boundary and may return up to one chunk past the limit - deliberately not tightened, because bundle_preview passes a larger limit precisely to reach a blob near the end of a page, and slicing to the byte would have shortened it. The 46-case url-import battery held 46/46 unchanged, which is what re-sweeps that row.
  - Replacing the mocked cover response with an explicit double immediately exposed a dependency the mock had been satisfying invisibly: outbound.get reads `resp.url`, and the mock invented it. The double now states the four things the downloader is entitled to use.
  - Verify command: pytest 1026 passed (exit 0), up from 1021; check_no_data_tracked exit 0; leak_check exit 0 after replacing that mock class - it is spelled with a private-library term inside it and cannot be reworded, which is now a Proposed item.
  - One claim in BACKLOG.md was corrected before this checkpoint: the settled-class line briefly quoted a differential score for a combination never actually run. It now states only the two differentials that were measured.

Learnings: A probe's own fixtures must not read anything the unfixed code lacks. A helper that raises makes the request fail for the wrong reason, the case goes green against broken code, and the differential run - the one step meant to prove the check can fail - reports success while measuring nothing. Hold such values as literals and assert them against the shipped constant in a separate case. Also: prefer an explicit test double to a mock for a response object. The mock silently invents every attribute the code reaches for, so it hides which parts of the interface are actually depended on, and it cannot fail when a new one appears.

Next: C3 (Low) is the only item left on the ledger. After it the ledger is empty with 6 iterations remaining, which is the point the evaluator gate should run early rather than at the declaration - but a full fresh-evidence audit has not happened this run, and 40 of 55 rows are unswept, so convergence is not in reach and the budget is better spent sweeping adversarial rows.

## iter 1/15 | affcbaff-100429 | 2026-08-02 | SALVAGE | salvage

Task: The working tree was dirty at the start of this run. The previous session (84948f5f) ended between its iteration 3 bookkeeping commit and its next re-feed, leaving one uncommitted edit and an orphaned loop state file naming that session at iteration 4.

Changed: humble_catalog/extract.py - the in-flight C3 edit, committed as found, nothing reset or discarded.

Checkpoint: e234d26.

Verification: The orphan state file recorded last_head 585656a, which matched HEAD exactly, so no checkpoint from that session was lost - only the uncommitted edit, now preserved. The state file was removed and a fresh one written for this session after the user confirmed no other session was running here. `git status --porcelain` was empty after the commit, so this iteration starts from a clean tree and its checkpoint diff carries only its own work.

Learnings: A crashed session leaves its loop state file behind because the hook deletes it only on reaching the budget or the promise. The file is inert - the hook compares session ids before re-feeding - so it blocks the next launch's pre-flight rather than capturing it, which is the intended tripwire.

Next: The salvaged edit is the fix for C3, the only item on the ledger, so this iteration executes and verifies it.

## iter 1/15 | affcbaff-100429 | 2026-08-02 | C3 | done

Task: C3 (Low, runtime, code quality) - a function-local binding shadowing a module imported in the same file.

Changed: humble_catalog/extract.py (salvaged in this iteration's SALVAGE commit: the download count is now bound to `downloaded`, with a comment recording why the module name must stay free), .jeffy/probes/module-shadowing/probe.py (new, the enumerating check), BACKLOG.md (C3 deleted, one Settled classes line added).

Checkpoint: acf287f. Not a stall: runtime code was salvaged and committed, a probe battery was added under .jeffy/probes/, and C3 moved from open to settled.

Verification: The filed acceptance check was run first, on both sides, before anything else.
  - The filed check, `grep -n "^ *covers = " humble_catalog/extract.py`, returns nothing at HEAD and returns `33: covers = _download_covers(...)` against 585656a, the commit before the fix. Differential, so it can fail.
  - That check is an instance check, and the finding is an instance of an idiom, so it was replaced by an enumeration of the class. `.jeffy/probes/module-shadowing/probe.py` walks every function in the package with an AST pass and reports any name it binds that the same file imports at module level. It counts every binding form, not just assignment: augmented and annotated assignment, for and with targets, `except ... as`, walrus, comprehension targets, imports written inside a function, and parameters, which are reported separately so the hazard count stays honest. Nested defs and lambdas are skipped, because they open their own scope and are visited in their own right.
  - The enumeration is differential too, which is what distinguishes it from the check the earlier settled class got wrong: 0 hazards across the package at HEAD, exit 0; exactly 1 against the pre-fix file, `extract.py:33 run binds covers`, exit 1. It reports the idiom, so it would have found any sibling site; it found none, so the class had exactly one member and closing this instance closes the class.
  - The hazard is a scoping one rather than a naming one, which is why the fix matters at all for a Low. The assignment anywhere in the body makes the name local for the whole body at compile time, so a `covers.relink` call placed above line 33 would raise the interpreter's reference-before-assignment error rather than fall through to the module. `_download_covers` rebinds `covers_dir` in its first line and is not an instance: that name is a parameter, not an import.
  - Contract preserved. The change is a local rename inside `run` plus the same value interpolated into the same message; no signature, no return value, and no observable behavior changes, so no documentation and no inventory row is affected. The `outbound-guard` row stays swept at 0a5816b: its scope names `humble_catalog/outbound.py`, which this iteration did not touch.
  - Verify command: pytest 1026 passed (exit 0), unchanged from the previous checkpoint; check_no_data_tracked exit 0; leak_check exit 0, clean on the first run this time. Output was redirected to a file and the exit status checked, never piped.

Learnings: An instance check and a class check are different instruments, and a Low is where that difference is cheapest to install. The filed grep would have certified this fix while a second site elsewhere in the package stayed broken; the AST pass costs one iteration once and answers the question for every future audit, including binding forms a grep cannot see at all.

Next: The ledger is now empty, with 14 iterations left and 40 of 55 inventory rows unswept, so iteration 2 is a partial audit that sweeps unswept rows. The evaluator gate does not apply: it runs on an empty ledger only when a full fresh-evidence audit has already been recorded in the same run, and this run has recorded none.

## iter 2/15 | affcbaff-100429 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit. The ledger emptied when C3 closed, so this iteration swept the two unswept rows the previous run's handoff named as the priority: sources-books and sources-media, the metadata parsers the Operating envelope classes adversarial.

Changed: .jeffy/probes/sources-books/probe.py (new, 61 cases), .jeffy/probes/sources-media/probe.py (new, 82 cases), PLAN.md (both rows swept, one Lesson), BACKLOG.md (D1 High, D2 Medium filed).

Checkpoint: f0a257d. Not a stall: two probe batteries were added under .jeffy/probes/, two inventory rows changed state, and two BACKLOG items were filed.

Verification: 143 known-answer assertions across the two rows, 123 held. The 20 failures are the two findings, and both were reproduced before either was filed.
  - sources-books, 54/61. Every contract case holds: the url fallback chain at three values, the api key and the token at two values each, featured_series winning over series_names and each falling back independently, and the GraphQL error payload raising before anything is cached. The 7 failures are D1.
  - sources-media, 69/82. Every contract case holds: the web_url form at three values, the sequence parse across numeric, decimal, non-numeric and absent, every role atom of the narrow illustrator policy including the documented cover-only omission, and credits refusing a foreign host, a non-http scheme and a suffix-spoofed host with the request log as the assertion. The 13 failures are D1 and D2.
  - D1, High, 15 shapes reproduced. Two of them write wrong values into the catalog with nothing logged: a string `categories` yields a genre of one character, and a non-string `key` yields a malformed source url. Both reach the enrichment table through apply_candidate, which passes the parsed fields straight into an UPDATE. The other 13 raise out of lookup. That is survivable in harvest and enrich, which catch broadly and skip the title, but url_import does not catch, and the viewer's fetch_url route catches only ValueError, MetadataUnavailable and RequestException - so those three exception types leave the route as a 500. Filed as one structural task with a boundary in sources/base.py, per the envelope's rule that scattered per-site guards are the wrong remedy, and because these are 15 instances of one root cause rather than 15 findings.
  - D2, Medium, 5 values reproduced. The rating scale is inferred from the value's size, so anything between 5 and 1000 is divided by 1000: 7.0, 10, 50, 87 and 5.001 become 0.01 to 0.09 rather than being refused. Today's upstream serves the x1000 scale the code assumes, so this is latent - but the envelope names a changed upstream shape as in envelope, and the consequence of that change is a silently rescored catalog rather than a failure.
  - The check that should have caught D2 cannot fail on it: the fixture test asserts only that a rating is None or at most 5, and 0.09 satisfies that. This is the absence-of-badness pattern the Method warns about, sitting directly beside the defect it was meant to pin.
  - Two defects in this iteration's own probes, both found by disbelieving a pass. The unconfigured-source cases sent a real request, because both classes fall back to the environment and this host has keys exported - the case went green while asserting the opposite of its name. And the group marker split labels on the first colon, so every drift failure was reported as an ordinary breakage.
  - Scores, claiming ONLY the 17 swept rows of 55 - the other 38 are unswept:
  - correctness: HIGH, D1, at two silent-wrong-value sites and 13 raising ones.
  - error handling: MEDIUM, D2, and the uncaught path from url_import to the viewer route recorded under D1.
  - testing: MEDIUM - the fixture assertion above, folded into D2 rather than filed separately, since it is the same code and the same iteration's work.
  - security: None on the swept rows. The credential rules hold: keys stay out of the cache key, the Authorization header is not built from third-party text, and credits refuses a foreign destination before sending.
  - architecture, documentation, code quality: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 38 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  Verify command: pytest 1026 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0. Output redirected to a file and the exit status checked, never piped.

Learnings: A probe of a keyed source must clear that provider's API-key environment variable before importing it, or the host's own configuration decides the result and the unconfigured-source cases certify the opposite of what they assert. More generally, both probe defects this iteration were passes that should not have been possible - a source with no key that still sent a request, and a drift group reporting zero members - and reading the passing lines rather than only the failing ones is what found them.

Next: Iteration 3 executes D1, the only High. Build the accessors in sources/base.py first and route the five parsers through them; the two batteries already hold the differential baseline, 54/61 and 69/82, so the fix is measured rather than asserted. D2 is next and is small enough to follow in one iteration.

## iter 3/15 | affcbaff-100429 | 2026-08-02 | D1 | done

Task: D1 (High, runtime, correctness) - close the class of third-party payload fields read without checking the JSON type they arrived as, across the five source parsers.

Changed: humble_catalog/sources/base.py (7 shape-safe accessors, the boundary), google_books.py, open_library.py, hardcover.py, oreilly.py, audible.py, comicvine.py (every extraction site routed through them), tests/test_sources_shapes.py (new, 49 tests), PLAN.md (both parser rows re-swept, one row added), BACKLOG.md (D1 deleted, Settled classes line added).

Checkpoint: 3ba6109. Not a stall: runtime code across seven modules, 49 new tests, and D1 moved from open to settled.

Verification: The filed reproduction was re-run first, before any edit, and both halves still reproduced at 54/61 and 69/82.
  - Acceptance, part one. `.jeffy/probes/sources-books/probe.py` exits 0 at 61/61, up from 54/61, and `.jeffy/probes/sources-media/probe.py` reports 0 DRIFT failures, up from 8. All 15 reproduced shapes now hold.
  - The filed acceptance line was wrong and is corrected here rather than quietly satisfied: it asked for 82/82 on the media battery, which folds in the 5 SCALE cases belonging to D2. The criterion that matches the task is 0 DRIFT failures, which is what was met; the media row therefore re-sweeps at 77/82 and says why the remainder is not this task's.
  - Acceptance, part two, the enumeration. Two greps, because either alone is blind to half the idiom: indexing and coercion (`[0]`, `["name"]`, `float(`) returns only base.py, the boundary itself; dict access (`.get(`) returns 37 sites in the parsers, each called on a name bound from as_mapping or first_mapping. One deliberate exception, named rather than hidden: oreilly.py:25 puts a raw isbn into the opaque `extra` dict, where a wrong type can only fail an equality test in url_import.
  - The class is guarded in the suite as well as in the batteries, because the suite is what the Verify gate and CI run. 49 tests added; against the unfixed parsers - restored from HEAD with the new base.py kept, since the accessors are new code rather than the fix - 9 of 9 parser-site tests fail and the 40 accessor tests pass.
  - The control matters as much as the failures: test_the_documented_shapes_are_unchanged passes against BOTH the fixed and unfixed parsers, which is the evidence that this change altered no previously-correct output.
  - A first differential attempt measured nothing and was discarded: restoring base.py too made the test module fail to import, so pytest reported a collection error rather than assertion failures. Exit 2 is not a differential.
  - Contract preserved. Every well-formed payload parses exactly as before; the accessors only widen what is tolerated. Two behaviours were deliberately kept rather than tidied: hardcover.validate still decides whether to raise on the truthiness of `errors`, so an error payload of an unexpected shape still refuses to be cached, and as_number rejects numeric strings by default, with allow_text=True only where an upstream documents a string field. An early version of validate used as_list and would have let a string error payload through to the cache; that was caught and reverted before the checkpoint.
  - The boundary is new public surface, so a sources-accessors row was added UNSWEPT rather than credited to the rows that merely use it: the batteries exercise it end to end, but no probe covers the family directly, and text_list's `key` parameter is not exercised at a second value anywhere.
  - Verify command: pytest 1075 passed (exit 0), up from 1026 with 49 new tests; check_no_data_tracked exit 0; leak_check exit 0.

Learnings: A differential run needs the fix reverted and nothing else. Reverting the whole module - including code the fix ADDED but did not change - broke the import and turned the measurement into a collection error, which reports as a failure and proves nothing; the accessors had to stay while only the call sites went back. Separately, replacing a truthiness test with a typed accessor can silently narrow it: as_list on a field whose only job was to be truthy would have let a malformed error payload reach the cache, which is the opposite of what that hook exists for.

Next: D2 (Medium) - the O'Reilly rating scale. The media battery already holds its differential baseline at 5 SCALE failures, and the fix is small: divide only the unambiguous x1000 domain, drop what cannot be interpreted, and replace the fixture assertion that cannot fail on it.

## iter 4/15 | affcbaff-100429 | 2026-08-02 | D2 | done

Task: D2 (Medium, runtime, correctness) - the O'Reilly rating scale, which inferred the factor from the value's size and divided a whole band of legitimate values into near-zero ratings.

Changed: humble_catalog/sources/oreilly.py (`_rating`, RATING_MAX and RATING_SCALE named, the inline heuristic removed), tests/test_sources_oreilly.py (+20 known-answer cases, the assertion that could not fail replaced), PLAN.md (sources-media re-swept, one Lesson), BACKLOG.md (D2 deleted).

Checkpoint: 331077b. Not a stall: runtime code and tests changed, and D2 moved from open to closed.

Verification: The filed reproduction was re-run first, before any edit, and still stood at 5 SCALE failures.
  - Acceptance check. `.jeffy/probes/sources-media/probe.py` exits 0 at 82/82, up from 77/82. That is the whole row green for the first time.
  - The rule now has three named domains rather than one comparison: a value in 0-5 is taken as it is, a value at or above 1000 is divided by it and must still land inside 0-5, and everything between the two is dropped. 5001 is refused for the same reason as 7.0 - scaled it would exceed the domain - which the old code did not check either.
  - The rule is pinned by a 20-row known-answer table, hand-computed. Against the unfixed scale rule, restored from HEAD so that D1's accessors stayed in place and only this fix was reverted, 8 of the 20 fail and 15 pass; the passing ones are the control, since 4667 to 4.67, 4750 to 4.75 and 4395 to 4.39 are what the fix had to leave alone.
  - 4395 gives 4.39, not 4.40. The float nearest 4.395 sits just below the midpoint, so the value is stated in the table as the code's real answer rather than the arithmetic one.
  - The weak assertion is gone. `rating is None or rating <= 5` was satisfied by 0.01 - the exact value the defect produced - so it sat beside the bug it was meant to pin and could not fail on it. It is replaced by a round-trip against the fixture's own raw field.
  - That replacement was wrong on the first attempt and is recorded rather than smoothed over: an exact round-trip fails on CORRECT code, because parsing to two places discards information. The assertion needed a tolerance of half a rounding step, which is 5 raw units, and a mis-scaled value misses by three orders of magnitude, so the check keeps all its power.
  - Honest limit of that fixture test: it passes against both the fixed and unfixed code, because the captured fixture happens to carry no value in the 5-to-1000 gap. It guards the scale from future drift; it is not evidence for this fix. The known-answer table is.
  - Contract preserved. Every value the old code handled correctly parses identically; only the uninterpretable band changes, from a fabricated near-zero rating to None. `rating or None` was dropped from the call site because `_rating` already returns None for zero, so no caller sees a behaviour change from that.
  - Verify command: pytest 1095 passed (exit 0), up from 1075; check_no_data_tracked exit 0; leak_check exit 0.

Learnings: A round-trip invariant over a rounded value needs a tolerance of half the rounding step; asserting exact equality there fails on correct code and reads as a real defect. Separately, a test whose only assertion is that a value is absent or within a wide range cannot fail on a defect that produces a small in-range value - which is exactly what this one produced, and the assertion had been sitting next to it since the file was written.

Next: The ledger is empty with 11 iterations left. The evaluator gate does NOT run: it needs a clean full audit already recorded in this run, and both audits so far have been partial with rows unswept. Iteration 5 is therefore a replenishing audit, and the best targets are the remaining adversarial rows - extract-humble and bundle-preview-tiers - plus the sources-accessors row this run created.

## iter 5/15 | affcbaff-100429 | 2026-08-02 | AUDIT | audit

Task: Replenishing audit. The ledger emptied when D2 closed, so this iteration swept the last unswept adversarial acquisition row, extract-humble, and sources-accessors, the row this run's own D1 fix created.

Changed: .jeffy/probes/extract-humble/probe.py (new, 33 cases), .jeffy/probes/sources-accessors/probe.py (new, 75 cases), PLAN.md (two rows swept, one row split out), BACKLOG.md (E1 High, E2 Low filed).

Checkpoint: 3ea3704. Not a stall: two probe batteries were added under .jeffy/probes/, two inventory rows changed state, one row was split out, and two BACKLOG items were filed.

Verification: 108 known-answer assertions across the two rows, 104 held. The 4 failures are one root cause, reproduced before filing.
  - sources-accessors, 75/75. The boundary holds, including the two things nothing else reached: `text_list`'s `key` parameter at a second value, which changes the answer and so is not inert, and `as_number`'s `allow_text` at both values on the same input. The property the whole boundary exists for is asserted directly - 133 calls over 19 shapes and 7 functions raise nothing.
  - extract-humble, 29/33, against a real http.server on an ephemeral port with BASE repointed, never a mocked session. The logged-in contract was exercised at five failing values, each of which must flip the answer, including a 200 carrying html and a response with no Content-Type header at all. The `all_tpkds=true` parameter is asserted from the server's own request log rather than from the return value, and the throttle by counting sleeps at two delay values.
  - E1, High, 4 shapes reproduced. `humble_api.py:42` indexes `o["gamekey"]` per entry, so one order missing that field, an order list that is a dict, and an order list of bare strings each abort `extract` before a single bundle is harvested; `parse_order.py:8` indexes `raw["product"]["human_name"]`, so an order whose product is not a dict raises through store_order. Third surface with this root cause, so it is filed as one structural task extending the D1 boundary rather than as four patches.
  - Severity was checked against a claim I did not get to keep. A poison pill would have made this worse: a malformed order cached and then re-parsed at the start of every later run. It is not one - the run raises before that order is committed, and only the previously-good order was in raw_orders afterwards. Recorded because the finding reads more alarming without it.
  - E2, Low, reproduced while checking that. `extract.run` and `reparse` close the connection only on the success path, so an exception leaks the handle and, on Windows, the next in-process open fails with a locked database. A CLI run is unaffected because the process exits, which is why this is Low and not higher.
  - One finding was withdrawn before it was filed, which is the more useful part of this audit. The probe first asserted that a non-default `covers_dir` must appear in the recorded `cover_path`, and reported two failures. Tracing the consumer showed the assertion was wrong: the front end renders that column as an img src against the viewer's `/covers/<filename>` route, so the prefix names the ROUTE, not the directory, and is correct for any covers_dir. The battery now pins the real contract - the recorded URL's last segment is the file actually written under covers_dir - and no finding was filed.
  - The parse-order row stays swept rather than flipping: its code has not changed since e0b77ba. Its battery simply never probed the shape of `product`, which is why it certified clean, and E1 covers that site.
  - Scores, claiming ONLY the 19 swept rows of 57 - the other 38 are unswept:
  - correctness: HIGH, E1, at two sites reached by every harvest.
  - error handling: LOW, E2.
  - security: None on the swept rows. The client sends cookies only to the configured host, the throttle is enforced from the attempt rather than from success, and a non-json 200 is refused rather than parsed.
  - testing: None on the swept rows, with one qualification recorded rather than scored: the suite covers these paths' happy cases well and no shape case, which is the same gap the metadata parsers had.
  - architecture, documentation, code quality: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 38 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  Verify command: pytest 1095 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: Before filing a finding that a parameter fails to affect an output, trace what CONSUMES that output. The recorded cover path looked like a filesystem path that ignored its directory parameter, and it is a URL rooted at a route, which is correct as written - two assertions were wrong, not the code. Separately, a row whose sweep genuinely could not reach part of its scope must be split rather than described as swept-with-an-exception: the playwright login helpers are now their own row, so the swept count means what it says.

Next: Iteration 6 executes E1, the only High. The accessors already exist and are proven at 75/75; the work is moving them to a module both families can import, keeping sources.base re-exporting them so the D1 settled class and its imports stay intact, and applying them at humble_api.py:42 and parse_order.py:8.

## iter 6/15 | affcbaff-100429 | 2026-08-02 | E1 | done

Task: E1 - close the class of HumbleBundle order fields read without checking the JSON type they arrived as.

Changed: humble_catalog/shapes.py (new, the accessors moved here so both families share them), humble_catalog/sources/base.py (re-exports every name), humble_catalog/humble_api.py (MalformedOrderList, list_order_keys), humble_catalog/parse_order.py (MalformedOrder, _required, every payload read routed through the accessors), humble_catalog/extract.py (two product reads), tests/test_humble_api.py (+5), tests/test_parse_order.py (+11), .jeffy/probes/extract-humble/probe.py (33 cases to 39), PLAN.md (four rows re-swept, one Lesson), BACKLOG.md (E1 deleted, Settled classes line added).

Checkpoint: 9037db1. Not a stall: runtime code across five modules, 17 new tests, and E1 moved from open to settled.

Verification: The filed reproduction was re-run first, before any edit, and still stood at 29/33 with the same 4 failures.
  - Acceptance check. `.jeffy/probes/extract-humble/probe.py` exits 0 at 39/39, up from 29/33. The three sibling batteries were re-run against the moved accessors and held unchanged - sources-books 61/61, sources-media 82/82, sources-accessors 75/75 - which is what re-sweeps those rows rather than flipping them.
  - The severity this was filed at did not survive reading the code, and that is recorded rather than quietly acted on. E1 was filed High on the strength of "a crash on realistic in-envelope input". parse_order.py documents the opposite intent at the tpkd line, and keys.py:162 cites the same rule: a malformed order SHOULD raise at the parse site, because tolerating it writes a NULL that fails a constraint two layers later where nothing names the order. Refusing is the contract, not the defect. What was genuinely wrong was that the refusal said `KeyError: 'human_name'` or `string indices must be integers`, neither of which names the order to look at. So the parse_order half is really a Medium in error handling. It was still worked in full this iteration; the note exists so the ledger's history is not read as a High that turned out to be free.
  - The list_order_keys half is different in kind and keeps its weight. That endpoint is the index of the entire library, so raising there costs every bundle rather than one, and one entry missing a gamekey is now skipped. The two granularities are deliberate and stated in both docstrings.
  - A silent-empty answer was rejected as the fix for the wholesale cases. Returning [] for an index that is not a list, or whose every entry is unusable, would report an empty library, and a harvest would do nothing and exit successfully - the silent wrong answer this project consistently avoids. Both now raise MalformedOrderList, which is deliberately not NotLoggedIn: ensure_login acts on that type, and re-logging in would not fix a changed payload shape.
  - Two probe assertions from iteration 5 were CORRECTED, not satisfied. They asserted that those two cases should yield []. That was the wrong desired answer for the reason above, and the battery now asserts the refusal. The change is recorded here because a battery quietly rewritten to match new code certifies nothing.
  - The enumeration. `grep -rnE '\["(gamekey|product|human_name|machine_name)"\]' humble_catalog/*.py` returns 26 sites; every one is a sqlite Row whose columns the schema guarantees, or a dict parse_order itself built and therefore owns. It also caught two sites the backlog line had not named, extract.py:31 and 59, where `.get("product", {})` looks safe and is not - the default applies only when the key is ABSENT, so a product present as a string still reached .get and raised. Both are fixed in this iteration; a class enumerated after the fix that finds unfixed members is exactly why the enumeration is run.
  - Contract preserved. parse_order still refuses the same payloads, only with a message that names them; MalformedOrder is a ValueError, so any caller catching that still does. store.py, which consumes parse_order's output, was read and needs no change: it subscripts dicts parse_order builds, not payload fields. Every well-formed order parses byte-identically, pinned by the fixture tests that were already there.
  - Verify command: pytest 1112 passed (exit 0), up from 1095 with 17 new tests; check_no_data_tracked exit 0; leak_check exit 0.
  - The suite half of the differential could NOT be run, and is not claimed. Reverting humble_api.py and parse_order.py removes MalformedOrderList and MalformedOrder, which the new tests import, so pytest reported a collection error rather than assertion failures - exit 2, measuring nothing. This is the second time this run that a differential was attempted by reverting a module that also gained new names; it is now a Lesson. The differential that does exist is the probe battery, which names no new type and was run before the edits at 29/33.

Learnings: A backlog line's severity is a hypothesis about consequence, and reading the target module can refute it. Here the module documented that refusing malformed input was deliberate, with a second module citing the same rule, so the "crash" half of a High was the designed contract and only the opacity of the message was a defect. Record the correction in the closing entry rather than either inflating the work or silently downgrading it. Separately, `.get(key, {})` is not a shape guard: the default applies only when the key is absent, so a key present with the wrong type flows straight through it.

Next: E2 (Low) is the only item left - the connection leaked on the exception path in extract.run and reparse. After that the ledger is empty again with 8 iterations left, and the evaluator gate still will not apply, because every audit this run has been partial with rows unswept.

## iter 7/15 | affcbaff-100429 | 2026-08-02 | E2 | done

Task: E2 (Low, runtime, error handling) - the database connection left open when extract.run or extract.reparse raises.

Changed: humble_catalog/extract.py (try/finally around both function bodies), tests/test_extract.py (+3), BACKLOG.md (E2 deleted, the D1 settled-class line corrected), PLAN.md (one Lesson).

Checkpoint: 852ddce. Not a stall: runtime code and tests changed, and E2 moved from open to closed.

Verification: The filed reproduction was run first, and the first attempt at it FAILED to reproduce, which changed what the fix had to be.
  - A client raising before any write leaves no transaction open, so nothing locks the file and the second run succeeded. The defect needs an exception raised while a write is still uncommitted - a malformed order reaching store_order - and with that the second run fails with `OperationalError: database is locked`, as filed. The backlog line said "any exception in between", which was broader than the truth; the narrower condition is what the fix and its tests are built on.
  - Acceptance check, both halves. A second `run` in one process now succeeds after the first raised, and the connection object itself raises `sqlite3.ProgrammingError` on reuse after both `run` and `reparse` raise. Against the unfixed extract.py, restored from HEAD, all 3 new tests fail; 8 of the file's other tests pass on both sides, which is the control.
  - One of those tests could not fail when first written, and was replaced rather than kept. `test_reparse_closes_its_connection_when_it_raises` originally asserted that a second open still works - and it PASSED against the unfixed code, because reparse's failure path holds no pending write, so no lock is taken. That is the absence-of-badness shape the Method warns about, and it was found by running the differential rather than by reading the test. It now records the connection at db.connect and asserts that reusing it raises, which fails against the unfixed code as it must.
  - The rollback is the right outcome, not an accident of closing: the write that gets discarded is the INSERT of an order whose parse then failed, and the order that did parse stays cached. Asserted directly - after the failed run the cache holds exactly the good gamekey.
  - Contract preserved. No signature, return value or success-path behaviour changes; the only difference is on the exception path, where the connection is now closed before the exception continues to propagate unchanged. The extract-humble battery was re-run at 39/39.
  - The D1 settled-class line was corrected in the same commit: it still located the accessors in sources/base.py, which E1's move made untrue. Its two enumerating checks still read as written, which is why the move did not invalidate the settlement.
  - Verify command: pytest 1115 passed (exit 0), up from 1112; check_no_data_tracked exit 0; leak_check exit 0.

Learnings: Assert a close directly - the connection object must raise on reuse - never "a second open still works". The weaker form only fails when a write was still pending, so on any path that holds no lock it passes against the very defect it was written for, and only the differential run exposes that. Separately, a reproduction that does not reproduce is information: the narrower condition it forces you to find is usually the true statement of the defect.

Next: The ledger is empty with 8 iterations left. The evaluator gate still does not apply - it requires a clean FULL audit recorded this run, and all three audits so far have been partial with rows unswept. Iteration 8 is therefore another replenishing audit; 38 rows remain, and the untouched clusters with the most surface behind them are the viewer routes, the storage layer and the title/match logic.

## iter 8/15 | affcbaff-100429 | 2026-08-02 | ROTATION | rotation

Task: JOURNAL.md reached 519 lines, past the 500-line threshold, so the older entries were rotated into the archive.

Changed: JOURNAL-archive.md (created, 12 entries), JOURNAL.md (10 entries kept).

Checkpoint: recorded in this iteration's primary entry.

Verification: 22 entries before, 12 moved and 10 kept, so nothing was dropped. The split matched only headings beginning `## iter` followed by a digit at column zero, which is why the preamble's fenced heading example - indented for exactly this reason - was neither counted nor moved. The archive did not previously exist and was created with its header; every later rotation appends to it, because the Stop hook rejects an archive whose entry count fell.

Learnings: None beyond the mechanics; the rotation rule worked as written.

Next: The audit that is this iteration's primary work.

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
