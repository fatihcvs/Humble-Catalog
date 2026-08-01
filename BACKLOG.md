# Backlog

Ledger, not narrative. Top unblocked item is next. Markers: [ ] open, [b] blocked.

Rules:
- One line per item: `- [ ] <ID> (<Severity>, <class>, <dimension>): <finding>. Acceptance: <runnable command or observable fact>.`
- Class is one of runtime, test, build-ci, docs, dev-tooling, chosen by the files the fix will touch; a line without one is read as runtime. Within a section, order by severity first, then runtime before the other classes.
- A finished task is deleted from its section and recorded as one line in the JOURNAL entry that closed it. No done markers accumulate here.
- Run context, audit scores, and DONE annotations live in JOURNAL.md only. No prose sections and no headings beyond the ones below, ever.

## Now

- [ ] C1 (High, runtime, security): outbound fetches whose URL comes from third-party content are sent with no scheme or host check and follow redirects unchecked. Two reproduced sites: `sources/comicvine.py:56` sends `COMICVINE_API_KEY` to any host a prior ComicVine response names in `api_detail_url`, and `extract.py:71` fetches an order-JSON `icon` URL pointing at loopback and writes the body under `covers/`. The B1 settlement missed both because it enumerated with `grep allow_redirects`, which cannot see a site relying on the default. Acceptance: one shared guard, reusing `url_import._publicly_routable`/`ALLOWED_SCHEMES`, refuses both reproductions (a local `http.server` on an ephemeral port receives no request), plus an enumeration listing every outbound call site in `humble_catalog/` with each validated or settled in the line.

## Next

- [ ] C2 (Medium, runtime, error handling): the cover downloader buffers an uncapped third-party body into memory and writes it whole. `extract.py:71` calls `.get()` without `stream=True`, so `resp.content` at line 75 materializes whatever the upstream serves, and nothing caps the bytes or checks the content type before the write. `url_import` already caps its reads with `MAX_HTML_BYTES`. Acceptance: a cover response larger than the cap is refused and no file is written, proved against a local `http.server` that serves more than the cap.

## Later

- [ ] C3 (Low, runtime, code quality): `extract.py:28` binds the name `covers` to the download count, shadowing the `covers` module imported at line 5 for the whole body of `run`. It works today only because nothing in `run` touches the module before line 28; adding a `covers.relink` call above it would raise at runtime, because the name is local to `run` for the whole body and is not yet assigned there. Acceptance: `grep -n "^ *covers = " humble_catalog/extract.py` returns nothing and the suite stays green.

## Proposed

Items needing a user decision before any work, one plain line each, never a checkbox task: envelope changes, audit escalations, challenges to a settled class. Never worked without explicit user approval and never counted against convergence.

## Settled classes

One line per class: the idiom or defect class, the surface it applies to, and how it was settled - fixed class-complete with its enumerating check, or declined with the reason. Audits must not file findings inside a settled class unless its implementing code changed after settlement.

- Unchecked redirect destination on outbound fetches (`url_import._fetch_html`, the one path `bundle_preview` also uses): fixed class-complete in B1. Redirects are now followed by hand so every hop is validated before it is requested, not just the final URL. Enumerating check: `grep -n "allow_redirects" humble_catalog/` shows the single call site, set to False - but that enumeration is UNSOUND and this class is NOT settled: the grep can only find sites that already opted out, so it is blind to every site relying on the default, and C1 names two such sites it missed. The line stays here as the record of a bad enumeration; C1 replaces it with a sound one. Pinned by 4 tests in tests/test_url_import.py and by `.jeffy/probes/url-import/probe.py`. Residual, recorded not hidden: the check resolves the name and then lets requests connect, so a DNS answer that changes between the two would slip through; pinning the connection to the checked address needs a custom adapter.
- Unvalidated request body / missing existence check on viewer write routes (`humble_catalog/webapp/__init__.py`): fixed class-complete in A1. Enumerating check: `grep -n "request.get_json()\[" humble_catalog/webapp/__init__.py` returns nothing, so no route indexes the body directly; every `/api/items/<id>/...` write now answers 400 for a malformed body and 404 for an unknown item, pinned by 7 tests in tests/test_webapp.py and by `.jeffy/probes/webapp-write-routes/probe.py` (18/18).

## Declined

Findings judged not worth fixing, one line each with the reason. Audits must not re-file these.

## Converged

One line per convergence, appended, never rewritten: Converged: <full commit hash> - <date>. The ratchet reads the latest line here.
