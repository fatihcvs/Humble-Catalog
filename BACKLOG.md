# Backlog

Ledger, not narrative. Top unblocked item is next. Markers: [ ] open, [b] blocked.

Rules:
- One line per item: `- [ ] <ID> (<Severity>, <class>, <dimension>): <finding>. Acceptance: <runnable command or observable fact>.`
- Class is one of runtime, test, build-ci, docs, dev-tooling, chosen by the files the fix will touch; a line without one is read as runtime. Within a section, order by severity first, then runtime before the other classes.
- A finished task is deleted from its section and recorded as one line in the JOURNAL entry that closed it. No done markers accumulate here.
- Run context, audit scores, and DONE annotations live in JOURNAL.md only. No prose sections and no headings beyond the ones below, ever.

## Now

## Next

## Later

- [ ] B2 (Low, runtime, error handling): a schemeless `host:port` URL is misdiagnosed - `normalize_url("example.com:8080/book")` raises "unsupported URL scheme 'example.com'", naming the hostname as the scheme, because urlparse reads `example.com` as a scheme when a colon follows it. The owner pastes URLs by hand, so a wrong diagnosis costs a real minute. Acceptance: `.venv/Scripts/python.exe .jeffy/probes/url-import/probe.py` exits 0 with the host:port case no longer reporting the hostname as a scheme.

## Proposed

Items needing a user decision before any work, one plain line each, never a checkbox task: envelope changes, audit escalations, challenges to a settled class. Never worked without explicit user approval and never counted against convergence.

## Settled classes

One line per class: the idiom or defect class, the surface it applies to, and how it was settled - fixed class-complete with its enumerating check, or declined with the reason. Audits must not file findings inside a settled class unless its implementing code changed after settlement.

- Unchecked redirect destination on outbound fetches (`url_import._fetch_html`, the one path `bundle_preview` also uses): fixed class-complete in B1. Redirects are now followed by hand so every hop is validated before it is requested, not just the final URL. Enumerating check: `grep -n "allow_redirects" humble_catalog/` shows the single call site, set to False. Pinned by 4 tests in tests/test_url_import.py and by `.jeffy/probes/url-import/probe.py`. Residual, recorded not hidden: the check resolves the name and then lets requests connect, so a DNS answer that changes between the two would slip through; pinning the connection to the checked address needs a custom adapter.
- Unvalidated request body / missing existence check on viewer write routes (`humble_catalog/webapp/__init__.py`): fixed class-complete in A1. Enumerating check: `grep -n "request.get_json()\[" humble_catalog/webapp/__init__.py` returns nothing, so no route indexes the body directly; every `/api/items/<id>/...` write now answers 400 for a malformed body and 404 for an unknown item, pinned by 7 tests in tests/test_webapp.py and by `.jeffy/probes/webapp-write-routes/probe.py` (18/18).

## Declined

Findings judged not worth fixing, one line each with the reason. Audits must not re-file these.

## Converged

One line per convergence, appended, never rewritten: Converged: <full commit hash> - <date>. The ratchet reads the latest line here.
