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

Checkpoint: de41baf. Not a stall: a probe battery was added under .jeffy/probes/, one inventory row changed state, and two backlog items were filed.

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

## iter 5/10 | ceea220f-162935 | 2026-08-01 | B1 | done

Task: B1 (High, runtime, security) - a page could steer an outbound fetch to any address this machine can reach, because only the redirect's scheme was checked and never its destination.

Changed: humble_catalog/url_import.py (`_publicly_routable` and `_check_redirect_target` added; `_fetch_html` now follows redirects by hand), tests/test_url_import.py (+4 regression tests), .jeffy/probes/url-import/probe.py (+16 allow-side and refuse-side cases), BACKLOG.md (B1 deleted, Settled classes line added), PLAN.md (row re-swept).

Checkpoint: 1648195. Not a stall: runtime code and tests changed, and B1 moved from open to settled. The url-import row was re-swept at this commit rather than flipped to unswept, because the battery was re-run against the changed code in this same iteration.

Verification: The battery's B1 cases all pass - the two-real-server redirect is now refused, and the address predicate answers correctly on both sides: 8.8.8.8 and a public IPv6 literal allowed; 127.0.0.1, 10.0.0.1, 192.168.1.1, 172.16.0.1, 169.254.169.254, 0.0.0.0, ::1 and fe80::1 all refused; an unresolvable name fails CLOSED, so a resolution failure cannot read as permission. The battery reports 39/40, and the single remaining failure is B2's case, which is a separate open Low and not part of this task. Verify command green: pytest 978 passed (974 before, +4 new), check_no_data_tracked exit 0, leak_check exit 0.
  Contract preserved, per change discipline: `tests/test_url_import.py` and `tests/test_bundle_preview.py` were run together first and both stayed green at 101 passed, which matters because `_fetch_html` is shared - `bundle_preview.py:60` fetches humblebundle.com pages through it, so a guard that refused ordinary public redirects would have broken the bundle preview rather than only the attack. The existing scheme test still passes: it drives a 200 response carrying a `javascript:` final URL, so the final-URL scheme check was kept rather than replaced by the per-hop one.
  Design decision, recorded because it is a judgement: the pasted URL is NOT checked, only the redirect hops. The owner may point this tool at whatever they like - that is a user-error surface by the envelope - whereas a redirect target is chosen by third-party content and is adversarial. Checking the pasted URL too would also have put a DNS lookup on every unit test's happy path, since the suite drives real code with Mock sessions.
  Residual risk, recorded rather than hidden: this resolves the name and then lets requests connect, so a DNS server answering public-then-private between the two calls would still get through. Closing that needs the connection pinned to the checked address via a custom adapter. The remaining exposure is a hostile DNS operator racing their own answers, well past the threat this guard exists for.

Learnings: `requests`' `is_redirect` must not be used in code the tests drive with Mock responses - every Mock attribute is truthy, so a 200 would read as a redirect. Compare `status_code` against an explicit set instead. A relative `Location` is legal and common, so a redirect target has to be urljoin-ed against the URL actually requested before it is judged; judging the raw header would let `/admin` read as an unparseable host and be refused for the wrong reason.

Next: B2, the last open item, a Low: `normalize_url` reports a schemeless `host:port` as an unsupported scheme named after the hostname.

## iter 6/10 | ceea220f-162935 | 2026-08-01 | B2 | done

Task: B2 (Low, runtime, error handling) - a pasted `host:port` URL was refused for an unsupported scheme named after its own hostname.

Changed: humble_catalog/url_import.py (`_HOST_AND_PORT` added, `normalize_url` recognises host:port before the scheme check and explains a dotted pseudo-scheme), tests/test_url_import.py (+3 regression tests), .jeffy/probes/url-import/probe.py (+7 cases), BACKLOG.md (B2 deleted), PLAN.md (row re-swept).

Checkpoint: 2a31136. Not a stall: runtime code and tests changed, and B2 moved from open to closed. The url-import row was re-swept at this commit, its battery re-run against the changed code in this same iteration.

Verification: `.jeffy/probes/url-import/probe.py` exits 0 at 46/46 - the first fully green run of this battery. `examplegames.com:8080/p/1` now normalises to `https://examplegames.com:8080/p/1`, with the no-path and query variants covered too. Verify command green: pytest 981 passed (978 before, +3 new), check_no_data_tracked exit 0, leak_check exit 0.
  Contract preserved, and this is the part that needed care: the new rule keys on DIGITS after the colon, which is exactly what separates a port from a scheme. Every scheme the gate refused before is still refused - the probe re-runs all 9 of them plus the whitespace and control-character obfuscations, and the existing `test_normalize_url_rejects_javascript` and `test_normalize_url_rejects_data` are untouched and still pass. The one shape that changes meaning is `javascript:8080`, which now normalises to `https://javascript:8080`: an https URL whose HOST is the word javascript, not a script URL. That is harmless and is pinned by its own test so nobody later "tidies" it into a hole.
  A dotted pseudo-scheme such as `examplegames.com:notaport` still fails, but now says the offender looks like a hostname and that a URL needs http:// or https:// in front of it, instead of only naming it as an unsupported scheme.

Learnings: When a parser's failure message names the user's input as the wrong KIND of thing, the fix is usually to recognise the right shape earlier rather than to reword the message - the message was accurate about what urlparse did and useless about what the user did.

Next: The ledger is empty and 4 iterations remain. Iteration 7 replenishes with a partial audit over the remaining adversarial rows - bundle-preview, sources-base, extract-humble - which are the rows most likely to hold another finding of B1's kind.

## iter 7/10 | ceea220f-162935 | 2026-08-01 | AUDIT | audit

Task: Partial replenishing audit, continuing on the adversarial rows. Swept sources-base and parse-order: the shared request/retry/redaction path every metadata source funnels through, and the parser every HumbleBundle order passes through.

Changed: .jeffy/probes/sources-base/probe.py (new), PLAN.md (two rows swept, one Lesson).

Checkpoint: e0b77ba. Not a stall: a probe battery was added under .jeffy/probes/ and two inventory rows changed state. No BACKLOG item changed state because the sweep found nothing to file, which is a clean result rather than a no-progress iteration; the previous primary entry recorded closed work, not a stall.

Verification: 49 known-answer assertions, all held. No findings; the ledger stays empty.
  - redact: an api_key, apikey or bare key is replaced in any casing, the parameter NAME is preserved while the value is destroyed, replacement stops at the ampersand so later params survive, two keys in one string are both caught, and a string with no key is returned unchanged. Checked directly that the secret value is absent from the output rather than only that the output looks redacted.
  - candidate: every default key present, kwargs override, and `extra` is a fresh dict per call - mutating one candidate's `extra` leaves the next one empty. That is the shared-mutable-default bug this shape invites, and it is not present.
  - cache_key_params: the `secret_params` argument changes the result at both its values, and a pair sequence works as well as a dict, which matters because the db migration that rekeys old rows shares this function.
  - _with_retries: exercised by counting attempts and sleeps rather than by observing success. A 5xx retries to ATTEMPTS with backoff 5s then 10s; 404, 429 and 403 are each tried exactly once, which is the documented reasoning that a dead quota and a bot wall will not improve; connection errors and timeouts retry; a success is called exactly once. The documented `retry_server_errors` parameter changes behaviour at both values - False stops a 5xx after one attempt and sleeps not at all - and, importantly, does NOT disable connection retries, which is the distinction the docstring draws and the one a careless refactor would flatten.
  - parse_order: only ebook/audio/android subproducts become items; a subproduct with an unrecognised platform and one with no downloads are both skipped; formats are lowercased and sorted; a missing payee yields None rather than a crash; the bundle url carries the gamekey; externals are extracted with their raw JSON; and an order with no subproducts and no tpkd_dict parses to empty lists rather than raising.
  One finding was considered and NOT filed: `parse_order` subscripts `raw["gamekey"]`, `raw["product"]["human_name"]` and `tpk["machine_name"]`, so a HumbleBundle schema change would raise KeyError rather than report something readable. The rubric would call a crash on realistic in-envelope input High, and HumbleBundle JSON is adversarial-class. It is not filed because the code documents the choice at parse_order.py:33-35 with measured evidence (2,278 of 2,278 tpks carry the field, and the column is NOT NULL), and deliberately prefers to raise at the parse site over writing a NULL that fails a constraint two layers later. That is a defensible documented decision, not an oversight, and filing against it would be second-guessing a choice whose rationale is better evidenced than my objection. Recorded here so a later audit does not re-derive it as new.
  Scores, claiming ONLY the 10 swept rows of 53 - the other 43 are unswept:
  - correctness: None across all 10 swept rows.
  - security: None on sources-base (redaction and retry policy) and url-import as fixed. Still NOT SCORED for the project: extract-humble, sources-books, sources-media, bundle-preview and covers-store remain unswept and adversarial.
  - error handling: None on the swept rows.
  - architecture, code quality, documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  Partial audit; never counts toward convergence, and closeout is NOT entered - that needs a full audit, and 43 rows are unswept.
  Verify command: pytest 981 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: A retry policy is swept by counting attempts and sleeps, never by watching a call succeed - "it worked" is identical output whether the policy retried three times, once, or not at all, so a liveness probe certifies nothing about it.

Next: 3 iterations remain and convergence is out of reach at 43 unswept rows, so iteration 10 should be a WRAPUP with a handoff rather than a task that cannot finish. Iterations 8 and 9 keep sweeping: bundle-preview first, since it shares the fetch path B1 changed, then export-columns and stats-report.

## iter 8/10 | ceea220f-162935 | 2026-08-01 | AUDIT | audit

Task: Partial replenishing audit. Swept the bundle-preview helper families, chosen because `fetch_bundle` reuses url_import's fetch guards and is therefore where a regression from this run's own B1 change would surface.

Changed: .jeffy/probes/bundle-preview-parts/probe.py (new), PLAN.md (row split into bundle-preview-parts and bundle-preview-tiers; the helpers row swept, one Lesson).

Checkpoint: cfb97ff. Not a stall: a probe battery was added under .jeffy/probes/ and two inventory rows changed state (one split, one swept). No BACKLOG item changed state because the sweep found nothing to file; the previous primary entry was also a clean audit, but it recorded row state changes too, so this is not a second consecutive no-progress iteration.

Verification: 26 known-answer assertions, all held. No findings.
  - No B1 regression: `fetch_bundle` still admits humblebundle.com and its subdomains and still refuses the lookalikes - `humblebundle.com.evil.example`, `nothumblebundle.com`, and a URL merely containing the domain in its path - and a non-http scheme is still refused ahead of the host gate. The full suite is green at 981, including the bundle-preview tests.
  - `_adds` is the one that most deserved known answers, because it decides what a tier is described as adding and a wrong answer there costs money. Checked cheapest-first accumulation, case-insensitive sorting, and the fallback to a raw machine_name when `items` has no entry. Two invariants beyond the literal lists: the per-tier lists are disjoint, and together they account for exactly the richest tier's names. Also checked the non-nesting bonus-tier case the running-set design exists for - a pairwise difference would emit a title twice there, and the running set does not.
  - `_owned` unions the merge tombstones, so a duplicate merged away still reads as owned rather than as a new item to buy. `_owned_games` dedupes on normalized_title, so a game owned on two stores counts once.
  - `delivery_stores` returns the inner storefront keys, and yields an empty set for a book, for the observed empty `{"game": {}}` entry, and for an explicit null - the three shapes that route an item to the book path.
  Scores, claiming ONLY the 11 swept rows of 54 - the other 43 are unswept:
  - correctness: None across the swept rows.
  - security: None on the bundle-preview host and scheme gates. Still NOT SCORED for the project: extract-humble, sources-books, sources-media and covers-store remain unswept and adversarial.
  - error handling, architecture, code quality, documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  Partial audit; never counts toward convergence, and closeout is NOT entered.
  Verify command: pytest 981 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0.

Learnings: Do not guess a table's columns when writing a probe - read the CREATE TABLE first. This battery cost a run to `games.store_id NOT NULL`, and on Windows the failed connection then held the temp file open and buried the real error under a PermissionError from the tempdir cleanup. The row total rose from 53 to 54 because a row was SPLIT rather than swept: sweeping the helpers did not exercise `preview` itself, and marking the whole row swept would have claimed ground nobody had walked.

Next: Iteration 9 is the last working iteration - sweep export-columns and stats-report, the arithmetic a user reads directly. Iteration 10 writes the WRAPUP and the handoff.

## iter 9/10 | ceea220f-162935 | 2026-08-01 | AUDIT | audit

Task: Partial replenishing audit, the last working iteration. Swept export-columns and stats-report: the cells and counts a user reads directly and would act on.

Changed: .jeffy/probes/export-stats/probe.py (new), PLAN.md (two rows swept, one recurred Lesson).

Checkpoint: c5b285b. Not a stall: a probe battery was added under .jeffy/probes/ and two inventory rows changed state.

Verification: 48 known-answer assertions, all held. No findings.
  - export `_columns`: None and empty both mean every column; a subset returns in CANONICAL order rather than the caller's, which is the documented asymmetry against `_select` (column order is not information, row order is); unknown names are dropped; duplicates collapse; an all-unknown selection falls back to every column rather than writing an empty file.
  - export `_select`: with ids the CALLER's order is preserved and never re-sorted, an unknown id is skipped rather than fatal, and an empty list selects nothing. Both the ids and columns parameters were exercised at two values each and both change the output.
  - export `_row`: list fields join with "; "; `first_purchased` is the EARLIEST of an item's bundle dates, not the first listed, checked against an item in two bundles whose earlier purchase is the second one; read_status renders its human label; None becomes an empty cell rather than the text "None"; and an item in no bundle yields an empty date instead of raising on min() of an empty sequence.
  - export `_clean`: the openpyxl illegal set is stripped while TAB, NEWLINE and CARRIAGE RETURN survive, which is the documented distinction - stripping those would silently reformat a multi-line note. Non-strings pass through.
  - stats `_tally`: a value outside the vocabulary is counted NOWHERE rather than inventing a row, so a section deliberately need not sum to the total, and that is asserted directly rather than assumed. The `default` parameter was exercised at two values and changes the counts as documented, which is how a missing read_status key is honoured.
  - stats: ratings count 1..5 only (unrated is a gap, not a row, so no item is counted twice); gaps count falsiness, so "" and None both register; genres sort biggest-first with alphabetical tie-breaking, giving a total and stable order; `report` returns sections in SECTIONS order and is pure across repeated calls. `console_safe` degrades the star to an asterisk under cp1252 and leaves it alone under utf-8 - the encoding parameter at two values, changing the output.
  Scores, claiming ONLY the 13 swept rows of 54 - the other 41 are unswept:
  - correctness: None across all 13 swept rows. This is the dimension with the most evidence behind it now: roughly 250 known-answer assertions across scoring, classification, the tag vocabulary, the item write paths, the retry policy, the order parser, the bundle helpers, the export projection and the stats counts.
  - security: None on the rows swept (host guard, url-import as fixed, source redaction, bundle-preview gates). Still NOT SCORED for the project: extract-humble, sources-books, sources-media and covers-store remain unswept and adversarial.
  - error handling, architecture, code quality, documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept. The whole viewer front end - 7 rows, about 2,600 lines of JS and CSS - is unswept, so no UX or accessibility claim is made at all.
  Partial audit; never counts toward convergence, and closeout is NOT entered.
  Verify command: pytest 981 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 after one fix - the battery's own comment used a word that is also a term in the private library, the third time this run that ordinary prose has tripped the substring check.

Learnings: The leak check has now caught the loop's own prose three times (iterations 1, 3 and 9) and never once caught a real leak. That is the check working as intended on a substring matcher, but it is a recurring cost: assume any evocative English noun in a comment may collide with the library, and prefer plain technical wording in probe files.

Next: The budget is spent after iteration 10, which is the WRAPUP. Nothing is left open on the ledger, so the handoff should record where the inventory stands and what the next run should sweep first.

## iter 10/10 | ceea220f-162935 | 2026-08-01 | WRAPUP | done

Task: Final iteration. Tidy the ledger and write the handoff, rather than starting a sweep that cannot finish inside one iteration.

Changed: JOURNAL.md (this entry). BACKLOG.md needed no tidying: Now, Next and Later are already empty, nothing is marked [b], and the two closed classes are recorded under Settled classes.

Checkpoint: a080543. This iteration changed only JOURNAL.md and no BACKLOG item changed state, which is a stall by the letter of the check - correctly so, because a WRAPUP does no work by design. It is not a hard blocker: the previous primary entry, iteration 9's audit, swept two rows and does not say the same.

Verification: The run is NOT converged, and this entry says so rather than declaring. Convergence requires no unswept row in the Surface inventory; 41 of 54 rows are unswept, so the Definition of done is not close to true and no evaluator gate was invoked - the gate exists to check a convergence claim, and there is no claim to check. No full audit was ever run this run either; all five audits were partial by design, and a partial audit never counts toward convergence.
  Final Verify command state, from iteration 9's gate: pytest 981 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0. The tree is clean at this entry, so that state still stands.
  Closed this run: A1 (Medium, error handling) - viewer write routes validated class-complete; B1 (High, security) - outbound fetches no longer follow a redirect to a private address; B2 (Low, error handling) - a pasted host:port URL is read as a host and a port. Nothing open, nothing blocked, nothing Declined, nothing under Proposed.

HANDOFF - what the next run should know:

  1. Start a NEW session. Relaunching /jeffy in this one keeps every accumulated token and forfeits the clean context that makes a run useful; the state files carry everything forward.

  2. The inventory is the map and the bound: 13 of 54 rows swept, 41 unswept, none marked `[~]` unreachable. Rows swept: cli-dispatch is NOT among them - the swept set is webapp-write-routes, webapp-host-guard, db-tags, db-items, matching-score, classify-type, series-report, url-import, parse-order, sources-base, bundle-preview-parts, export-columns, stats-report.

  3. Sweep next, in this order and for these reasons:
     - extract-humble, sources-books, sources-media, covers-store: the last unswept ADVERSARIAL rows. B1, the only High this run, came out of that neighbourhood, and `covers-store` writes third-party bytes to disk under a derived filename, which is the shape that hides a path-traversal defect.
     - bundle-preview-tiers: `preview()` itself was split out and never exercised. Its numbers drive a purchase decision.
     - db-schema: every migration step is unswept, and a migration defect corrupts data permanently rather than returning a wrong answer once.
     - The seven front-end rows, about 2,600 lines of JS and CSS: UX and accessibility have never been scored at all this run, and no claim about them has been made.

  4. Two residual risks are recorded, not hidden. The B1 guard resolves a hostname then lets requests connect, so a DNS answer that changes between the two would still slip through; closing that needs the connection pinned to the checked address via a custom adapter. And `parse_order` raises KeyError on a HumbleBundle schema change - considered in iteration 7 and deliberately not filed, because parse_order.py:33-35 documents that choice with measured evidence. Both are reasoned positions, not oversights; re-open either only with new evidence.

  5. The probe batteries under `.jeffy/probes/` are the instrument, not scaffolding. A re-sweep re-runs the battery rather than rebuilding it, and a battery is updated in the same iteration as the behaviour it pins. All eight are green as of c5b285b except by design - none records a known defect.

  6. `leak_check.py` tripped three times this run on the loop's own prose and never on a real leak. That Lesson is marked `[recurred]`, and the run report proposes a mechanism for the user to decide on: a pre-commit hook running the check over staged files only would catch it in a second instead of at the end of a 90-second gate.

Learnings: A run that ends out of budget should say plainly that it is not converged and hand off, rather than reaching for a weaker claim. The Definition of done here was never nearly true - 41 unswept rows - and the honest report is more useful than a qualified declaration.

Next: Nothing. The budget is spent; the loop ends with this entry.
