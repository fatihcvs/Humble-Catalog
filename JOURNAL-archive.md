# Journal archive

Rotated out of JOURNAL.md, oldest first. Appended to on every rotation and never overwritten; the loop's Stop hook rejects an archive whose entry count fell.

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
