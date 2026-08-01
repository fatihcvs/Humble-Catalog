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

- [ ] C3 (Low, runtime, code quality): `extract.py:28` binds the name `covers` to the download count, shadowing the `covers` module imported at line 5 for the whole body of `run`. It works today only because nothing in `run` touches the module before line 28; adding a `covers.relink` call above it would raise at runtime, because the name is local to `run` for the whole body and is not yet assigned there. Acceptance: `grep -n "^ *covers = " humble_catalog/extract.py` returns nothing and the suite stays green.

## Proposed

Items needing a user decision before any work, one plain line each, never a checkbox task: envelope changes, audit escalations, challenges to a settled class. Never worked without explicit user approval and never counted against convergence.

- `leak_check.py` matches case-insensitive substrings, and has now blocked a commit over a STANDARD LIBRARY class name whose spelling cannot be changed - a `unittest.mock` symbol containing a private-library term. Six trips this run and the last one, every one on the loop's own prose or on Python vocabulary, none on real data. Worth deciding: match on word boundaries, or skip Python identifiers and import lines, either of which keeps the gate's real power while ending the false positives. Adding the word to ALLOWED is the one option to avoid - it would blind the gate to every genuine title containing it. Workaround in place meanwhile: `tests/test_extract.py` uses an explicit response double instead of that class, which is better test code anyway.

## Settled classes

One line per class: the idiom or defect class, the surface it applies to, and how it was settled - fixed class-complete with its enumerating check, or declined with the reason. Audits must not file findings inside a settled class unless its implementing code changed after settlement.

- Outbound request to a URL named by third-party content, sent without validating the destination (initial URL and every redirect hop): fixed class-complete in C1, superseding B1, whose enumerating check `grep -n "allow_redirects"` was unsound - it could only match sites that had already opted out and was blind to the two taking the default. Sound enumerating check, which lists the idiom rather than the fix: `grep -rnE "(requests|self\.http|client\.http|http|sess|session)\.(get|post|request)\(" humble_catalog/ --include=*.py` returns exactly 5 sites, each disposed of - `outbound.py` is the guard itself; `url_import.py` runs through it with `check_initial=False` because the pasted URL is the owner's own; `humble_api.py` and `import_games.py` build every URL from a module constant host; `sources/base.py:117` takes its URL from callers, and `grep -rn "get_json(" humble_catalog/` shows every one is a literal `https://` constant except `comicvine.credits`, which now checks against `ComicVine.API_HOSTS` before sending. Pinned by 12 tests in tests/test_outbound.py, 4 in tests/test_url_import.py, and `.jeffy/probes/outbound-guard/probe.py` (49/49; its C1 cases scored 34/41 against the unguarded code when they were written, measured then). Residual, recorded not hidden: the check resolves the name and then lets requests connect, so a DNS answer that changes between the two would slip through; pinning the connection to the checked address needs a custom adapter.
- Unvalidated request body / missing existence check on viewer write routes (`humble_catalog/webapp/__init__.py`): fixed class-complete in A1. Enumerating check: `grep -n "request.get_json()\[" humble_catalog/webapp/__init__.py` returns nothing, so no route indexes the body directly; every `/api/items/<id>/...` write now answers 400 for a malformed body and 404 for an unknown item, pinned by 7 tests in tests/test_webapp.py and by `.jeffy/probes/webapp-write-routes/probe.py` (18/18).

## Declined

Findings judged not worth fixing, one line each with the reason. Audits must not re-file these.

## Converged

One line per convergence, appended, never rewritten: Converged: <full commit hash> - <date>. The ratchet reads the latest line here.
