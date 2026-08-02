# Backlog

Ledger, not narrative. Top unblocked item is next. Markers: [ ] open, [b] blocked.

Rules:
- One line per item: `- [ ] <ID> (<Severity>, <class>, <dimension>): <finding>. Acceptance: <runnable command or observable fact>.`
- Class is one of runtime, test, build-ci, docs, dev-tooling, chosen by the files the fix will touch; a line without one is read as runtime. Within a section, order by severity first, then runtime before the other classes.
- A finished task is deleted from its section and recorded as one line in the JOURNAL entry that closed it. No done markers accumulate here.
- Run context, audit scores, and DONE annotations live in JOURNAL.md only. No prose sections and no headings beyond the ones below, ever.

## Now

- [ ] D1 (High, runtime, correctness): the five source parsers read fields of a third-party payload without checking the JSON type they arrived as, which the envelope classes adversarial and names "a merely changed upstream shape". 15 shapes reproduced. Two write wrong values into the catalog with nothing logged - `categories: "Fantasy"` makes genre `"F"` in `google_books.py:47`, and the same slice in `open_library.py:32` and `hardcover.py:63`; a non-string `key` makes `source_url` `https://openlibrary.org12345` in `open_library.py:34` - and both reach `enrichment` through `enrich.apply_candidate`. The other 13 raise TypeError, KeyError or AttributeError out of `lookup`; `harvest.py:73` and `enrich.py:187` catch those and skip the title, but `url_import._hardcover`/`_oreilly` do not, and `webapp/__init__.py:513` catches only ValueError, MetadataUnavailable and RequestException, so the viewer's fetch_url route answers 500. Per the envelope's binding rule the remedy is one boundary, not per-site guards: shape-safe accessors in `sources/base.py` used at every extraction site. Acceptance: `.venv/Scripts/python.exe .jeffy/probes/sources-books/probe.py` and `.jeffy/probes/sources-media/probe.py` both exit 0 (61/61 and 82/82; they score 54/61 and 69/82 against the code as filed), and the enumeration `grep -rnE "\[0\]|\[.name.\]|float\(" humble_catalog/sources/*.py` lists every extraction site with each one either routed through an accessor or named as deliberate.

## Next

- [ ] D2 (Medium, runtime, correctness): `oreilly.py:15` infers the rating scale from the value, dividing anything above 5 by 1000, so a value between 5 and 1000 becomes a near-zero rating rather than a refusal - reproduced at 7.0, 10, 50, 87 and 5.001, all yielding 0.01 to 0.09, and that value is written to `external_rating` by `enrich.apply_candidate`. An upstream move to a 0-10 or 0-100 scale would therefore rescore the whole catalog silently instead of failing. The check that should catch it cannot: `tests/test_sources_oreilly.py:48` asserts only `rating is None or rating <= 5`, which 0.01 satisfies. Fix: divide only the unambiguous x1000 domain and drop what cannot be interpreted, and replace that assertion with a known-answer one. Acceptance: `.venv/Scripts/python.exe .jeffy/probes/sources-media/probe.py` reports 0 SCALE failures, and the suite stays green.

## Later

## Proposed

Items needing a user decision before any work, one plain line each, never a checkbox task: envelope changes, audit escalations, challenges to a settled class. Never worked without explicit user approval and never counted against convergence.

- `leak_check.py` matches case-insensitive substrings, and has now blocked a commit over a STANDARD LIBRARY class name whose spelling cannot be changed - a `unittest.mock` symbol containing a private-library term. Six trips this run and the last one, every one on the loop's own prose or on Python vocabulary, none on real data. Worth deciding: match on word boundaries, or skip Python identifiers and import lines, either of which keeps the gate's real power while ending the false positives. Adding the word to ALLOWED is the one option to avoid - it would blind the gate to every genuine title containing it. Workaround in place meanwhile: `tests/test_extract.py` uses an explicit response double instead of that class, which is better test code anyway. It has now blocked a BUILTIN exception class name as well, in prose merely naming the error a defect would raise, so the pattern is not confined to one library symbol: any Python identifier a document has to name can trip it, and rewording is the only remedy left once the spelling belongs to the language. That is the second distinct symbol class, which is the argument for deciding this rather than continuing to reword.

## Settled classes

One line per class: the idiom or defect class, the surface it applies to, and how it was settled - fixed class-complete with its enumerating check, or declined with the reason. Audits must not file findings inside a settled class unless its implementing code changed after settlement.

- Outbound request to a URL named by third-party content, sent without validating the destination (initial URL and every redirect hop): fixed class-complete in C1, superseding B1, whose enumerating check `grep -n "allow_redirects"` was unsound - it could only match sites that had already opted out and was blind to the two taking the default. Sound enumerating check, which lists the idiom rather than the fix: `grep -rnE "(requests|self\.http|client\.http|http|sess|session)\.(get|post|request)\(" humble_catalog/ --include=*.py` returns exactly 5 sites, each disposed of - `outbound.py` is the guard itself; `url_import.py` runs through it with `check_initial=False` because the pasted URL is the owner's own; `humble_api.py` and `import_games.py` build every URL from a module constant host; `sources/base.py:117` takes its URL from callers, and `grep -rn "get_json(" humble_catalog/` shows every one is a literal `https://` constant except `comicvine.credits`, which now checks against `ComicVine.API_HOSTS` before sending. Pinned by 12 tests in tests/test_outbound.py, 4 in tests/test_url_import.py, and `.jeffy/probes/outbound-guard/probe.py` (49/49; its C1 cases scored 34/41 against the unguarded code when they were written, measured then). Residual, recorded not hidden: the check resolves the name and then lets requests connect, so a DNS answer that changes between the two would slip through; pinning the connection to the checked address needs a custom adapter.
- A function-local binding that shadows a module imported at the top of the same file, making that name local to the whole function body, so any earlier module use raises the interpreter's reference-before-assignment error: fixed class-complete in C3. Enumerating check, listing the idiom rather than the fix: `.venv/Scripts/python.exe .jeffy/probes/module-shadowing/probe.py` walks every function in `humble_catalog/` with an AST pass and reports each name it binds that the file also imports at module level, counting assignment, augmented and annotated assignment, for and with targets, `except ... as`, walrus, comprehension targets, in-function imports and parameters. It exits 0 at 0 hazards across the package, and 1 naming `extract.py:33 run binds covers` when run against the code before the fix, so the check is strong enough to fail. The class had exactly one member.
- Unvalidated request body / missing existence check on viewer write routes (`humble_catalog/webapp/__init__.py`): fixed class-complete in A1. Enumerating check: `grep -n "request.get_json()\[" humble_catalog/webapp/__init__.py` returns nothing, so no route indexes the body directly; every `/api/items/<id>/...` write now answers 400 for a malformed body and 404 for an unknown item, pinned by 7 tests in tests/test_webapp.py and by `.jeffy/probes/webapp-write-routes/probe.py` (18/18).

## Declined

Findings judged not worth fixing, one line each with the reason. Audits must not re-file these.

## Converged

One line per convergence, appended, never rewritten: Converged: <full commit hash> - <date>. The ratchet reads the latest line here.
