# Humble Catalog — project rules

## Privacy (standing order, non-negotiable)

The owner's HumbleBundle purchases are private. Nothing that reveals
what they actually own may be committed to this repo:

- Never commit `catalog.db*`, `Reference spreadsheets/`, `covers/`,
  `cache/`, or any export of the catalog. They are gitignored; never
  weaken those rules or force-add them.
- In committed text — docs, specs, tests, fixtures, commit messages —
  use invented or generic book titles and bundle names, never real
  items from the owner's library. Draw invented examples from
  `docs/TEST-DATA.md` (and add new ones there). Anonymize fixtures
  captured from real API responses before committing.
- Run `.venv/Scripts/python scripts/leak_check.py` after adding tests,
  fixtures, or docs that name books, bundles, or people — it fails if
  anything from the real library appears in the repo.
  `scripts/check_no_data_tracked.py` is the companion check that no data
  *file* is tracked; `verify` runs both. Before a first push to a public
  remote, and after any history rewrite, also run
  `scripts/leak_check_history.py`, which scans git history rather than
  the working tree. See the Privacy section of `docs/BACKLOG.md`.
- **`main` is a squashed publication history, and the development
  history lives only in the local branch `pre-public-history`.** That
  branch still contains real author names in old test data, from before
  the catalog grew enough for the checks to see them. Push one ref at a
  time and only `main`: `git push --all`, `--mirror`, or pushing
  `pre-public-history` by name would publish exactly what the squash was
  for. Never merge, rebase or cherry-pick it into `main` either.
  `scripts/leak_check_history.py` scans one ref (default HEAD) for this
  reason and names the branches it did not scan.
- History was also rewritten 2026-07-18 (`git filter-repo`) to purge
  pre-scrub commits — see the Privacy section of `docs/BACKLOG.md`.
  Do not restore or merge any pre-rewrite clone or bundle into this
  repo; that would reintroduce the private history.
