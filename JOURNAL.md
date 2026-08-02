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

## iter 1/10 | 84948f5f-185203 | 2026-08-01 | AUDIT | audit

Task: Opening audit of a new run. The ledger was empty and the previous run's handoff named the unswept ADVERSARIAL rows as the priority, so this audit swept covers-store and probed the two adversarial outbound-fetch paths the handoff pointed at.

Changed: .jeffy/probes/covers-store/probe.py (new), PLAN.md (covers-store swept), BACKLOG.md (C1 High, C2 Medium, C3 Low filed; the B1 Settled classes line corrected to record that its enumeration was unsound).

Checkpoint: 4ac8be3. Not a stall: a probe battery was added under .jeffy/probes/, one inventory row changed state, and three BACKLOG items were filed.

Verification: 57 known-answer assertions on covers-store, all held, and two findings reproduced against real local servers rather than mocks.
  - covers-store, no findings. cover_filename is the derived-filename hazard the handoff flagged, and it holds: the mapping is an allowlist to [a-z0-9_-] plus a digest of the RAW key, so eight separator, traversal, drive-letter, NUL and newline shapes all reduce to a bare basename, and three casings that share one slug stay distinct by digest rather than overwriting each other. relink fills only NULL paths, only for files present, and its covers_dir was exercised at two values that change the count. store_order is idempotent across a re-store, links rather than duplicates an item in two bundles, refuses to resurrect a merged-away key, never lets the no-evidence 'ebook' default demote a comic, honours type_overridden, and restores a post-reset snapshot ONLY when re-creating an item, so a live edit survives a normal re-store.
  - C1, High, reproduced twice. ComicVine.credits sends the request to whatever URL a PREVIOUS ComicVine response put in api_detail_url, with api_key attached: a local http.server on an ephemeral port received `/api/issue/4000-1/?api_key=SECRET-KEY-VALUE&...`, so the credential goes wherever that field points. Separately the cover downloader fetched `http://127.0.0.1:<port>/internal-secret` named by an order-JSON icon field, followed a 302 to a second loopback path, and wrote both bodies under covers/. Both sites are in-envelope: the envelope classes order JSON and external metadata API responses as adversarial.
  - The B1 settlement is the root of this. Its enumerating check greps for allow_redirects, which can only match a site that already opted out; a site relying on the default is invisible to it. That is why a class recorded as fixed class-complete still has two unguarded members, and it is why C1 is filed as one structural task with a sound enumeration rather than as two instance patches.
  - C2, Medium: the cover fetch omits stream=True, so resp.content buffers whatever the upstream serves before the write, with no size cap and no content-type check. url_import already caps its own reads.
  - C3, Low: `covers = _download_covers(...)` in extract.run shadows the covers module for that whole function body. Not a defect today, only because nothing above it touches the module.
  Scores, claiming ONLY the 14 swept rows of 54 - the other 40 are unswept:
  - security: HIGH, C1, at two reproduced sites. This is the first security finding scored since the adversarial rows started being swept, and it came from exactly the neighbourhood the previous run's handoff predicted it would.
  - error handling: MEDIUM, C2.
  - code quality: LOW, C3.
  - correctness: None across the swept rows.
  - architecture, documentation, testing: None on the swept rows.
  - performance, dependency hygiene, observability, UX, accessibility: NOT SCORED, rows unswept.
  This is a partial audit, not a full one: 40 rows are unswept, so it never counts toward convergence and closeout is NOT entered.
  Verify command: pytest 1005 passed (exit 0), check_no_data_tracked exit 0, leak_check exit 0 after two rewordings - two ordinary technical words in the C2 and C3 backlog lines each contain a private-library term as a substring, the fourth and fifth time the loop's own prose has tripped this check and still never a real leak.

Learnings: An enumerating check that can only match ALREADY-FIXED sites does not enumerate anything. `grep allow_redirects` finds the call that opted out and is blind to every call taking the default, so it certified a class as complete while two members of it stayed unguarded. A class enumeration must list every site of the idiom - here, every outbound request - and then show each one's disposition; enumerating the fix instead of the idiom is how a settled class hides its own gaps.

Next: Iteration 2 executes C1, the only High. Reuse url_import's `_publicly_routable` and ALLOWED_SCHEMES rather than writing a second guard, and note that unlike url_import - where the owner's pasted URL is deliberately unchecked - here the INITIAL url is third-party too, so it needs checking as well as the hops.

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

Checkpoint: <pending>

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
