# Backlog

Ledger, not narrative. Top unblocked item is next. Markers: [ ] open, [b] blocked.

Rules:
- One line per item: `- [ ] <ID> (<Severity>, <class>, <dimension>): <finding>. Acceptance: <runnable command or observable fact>.`
- Class is one of runtime, test, build-ci, docs, dev-tooling, chosen by the files the fix will touch; a line without one is read as runtime. Within a section, order by severity first, then runtime before the other classes.
- A finished task is deleted from its section and recorded as one line in the JOURNAL entry that closed it. No done markers accumulate here.
- Run context, audit scores, and DONE annotations live in JOURNAL.md only. No prose sections and no headings beyond the ones below, ever.

## Now

## Next

- [ ] A1 (Medium, runtime, error handling): four viewer write routes skip the body validation and existence check their siblings all perform, so a wrong value is stored without complaint and a malformed body is a 500 rather than a 400. `/api/items/<id>/rating` (webapp/__init__.py:181) stores any JSON value as a rating and returns 200 for an item id that does not exist; `/type` (:221) and `/choose` (:529) index `request.get_json()` directly and raise KeyError; `/choose` also raises TypeError on a non-integer index (:533) and on an item with no enrichment row (:532); `/reopen` (:323) returns 200 for an unknown item. Sibling routes read-status, comment and user-tags already 400/404 exactly as required, so this is the project's own contract being missed at four sites. Acceptance: `.venv/Scripts/python.exe .jeffy/probes/webapp-write-routes/probe.py` exits 0 with 12/12, and `grep -n "request.get_json()\[" humble_catalog/webapp/__init__.py` returns nothing.

## Later

## Proposed

Items needing a user decision before any work, one plain line each, never a checkbox task: envelope changes, audit escalations, challenges to a settled class. Never worked without explicit user approval and never counted against convergence.

## Settled classes

One line per class: the idiom or defect class, the surface it applies to, and how it was settled - fixed class-complete with its enumerating check, or declined with the reason. Audits must not file findings inside a settled class unless its implementing code changed after settlement.

## Declined

Findings judged not worth fixing, one line each with the reason. Audits must not re-file these.

## Converged

One line per convergence, appended, never rewritten: Converged: <full commit hash> - <date>. The ratchet reads the latest line here.
