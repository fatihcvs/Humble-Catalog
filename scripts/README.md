# Scripts

Per-OS wrappers around the project's routine commands, so the same task
has one name everywhere. Pick the folder for your platform:

| | Windows | macOS | Linux |
|---|---|---|---|
| Folder | `scripts/windows/` | `scripts/macos/` | `scripts/linux/` |
| Extension | `.ps1` (PowerShell) | `.sh` (bash) | `.sh` (bash) |

The `.py` files in this directory are tools, not wrappers: `leak_check.py`
is the privacy gate, `leak_check_history.py` is its counterpart for git
history, `check_no_data_tracked.py` refuses to let data files be
committed at all, the `capture_*.py` scripts record API fixtures, and
`make_favicon.py` regenerates the viewer's icon. Its output is committed,
so run it only after editing the palette; `favicon_tuner.html` is a
browser tool for choosing those values (open it directly, it fetches
nothing).

## The commands

| Script | What it does |
|---|---|
| `setup` | Create `.venv`, install the project with dev extras, install the Playwright browser. |
| `test` | Run the test suite. Extra arguments pass through to pytest. |
| `leak-check` | Privacy gate — fails if anything from the real library appears in the repo. |
| `verify` | Tests, then both privacy checks. Everything that must pass before a commit. |
| `serve` | Start the catalog viewer. |
| `stop` | Stop the viewer. |
| `catalog` | Passthrough to the catalog CLI (`extract`, `enrich`, `export`, …). |

## Examples

```powershell
# Windows
.\scripts\windows\setup.ps1
.\scripts\windows\verify.ps1
.\scripts\windows\serve.ps1 -Detached
.\scripts\windows\stop.ps1
.\scripts\windows\catalog.ps1 enrich --limit 20
```

```bash
# macOS / Linux
./scripts/macos/setup.sh
./scripts/macos/verify.sh
./scripts/macos/serve.sh --detached
./scripts/macos/stop.sh
./scripts/macos/catalog.sh enrich --limit 20
```

## Notes

**`serve` runs in the foreground by default** — Ctrl+C stops it. Pass
`-Detached` / `--detached` to background it, then use `stop` to shut it
down. Starting a second one is refused while the port is busy.

**`stop` targets the port, not a stored PID**, so it also catches a
server started some other way — an editor task runner, or one left over
from an earlier session.

**Restart the viewer after changing Python code.** A running server
re-reads static files from disk on every request but holds its Python in
memory. A stale process therefore pairs new JavaScript with an old API;
that mismatch once left the viewer rendering zero rows with every panel
hidden and nothing in the console to explain it.

**Port** defaults to 8087. Override with the `HUMBLE_PORT` environment
variable, which `serve` and `stop` both honour.

**`setup` expects Python 3.12** (`py -3.12` on Windows, `python3.12`
elsewhere). Edit the script if your interpreter is named differently.

**On Debian and Ubuntu, install `python3.12-venv` first.** They ship the
`venv` module without `ensurepip`, so virtualenv creation dies partway
and leaves a `.venv` with no pip in it. `setup` checks for this and says
so rather than letting you discover it at the pip step.

**`test` skips the JavaScript tests when Node is absent.** They execute
the viewer's `app.js` in a stubbed DOM (`tests/js/harness.mjs`); the rest
of the suite runs either way, so Node is optional.

**One test is Windows-only, so a macOS or Linux run reports one skip.**
`test_restore_refuses_while_the_catalog_is_open` asserts that `restore`
refuses to overwrite a catalog another process has open — a guarantee
that only exists on Windows, because POSIX replaces an open file
happily and there is no refusal to assert. With Node installed, a clean
run is therefore *zero* skips on Windows and *exactly one* elsewhere;
anything more deserves a look. (Two source tests also skip if their
fixture is missing, but both fixtures are committed, so in a normal
clone they never do.)

**`check_no_data_tracked.py` needs no catalog.** It asks whether a data
file is *tracked* — `catalog.db`, a cover, a spreadsheet, an export —
which is answerable from path names alone, so unlike the term checks it
is a real gate everywhere, including CI. It covers all of history, not
just HEAD: a data file committed and later deleted still ships with a
push. `verify` runs it first, because it is instant.

**`leak-check` reports SKIPPED on a clone with no `catalog.db`.** There
is nothing private to search for, so it exits 0 — but says so rather
than printing "clean", which would imply a check that never ran. The
same is true of `leak_check_history.py`, and of the privacy step in CI,
which runs on a runner that has no catalog either.

**`leak_check_history.py` has no wrapper and is not part of `verify`.**
It scans the commit messages and blobs reachable from one ref rather
than the working tree, which is slower and only matters at two moments:
before a push to a public remote, and after a history rewrite. Run it
directly:

```
python scripts/leak_check_history.py [ref]
```

It defaults to `HEAD` and answers "what would pushing this ref
publish?". One ref, not the whole object store, because the development
history is deliberately kept in a local-only branch — scanning
everything would report data that is never going anywhere and make the
check permanently red. It prints which local branches it did *not*
scan, and those must never be pushed: `git push --all` and `--mirror`
are the two commands that would publish them.

A hit there cannot be fixed by editing a file — the term is already in
history. Check the context first, since most hits are ordinary prose
matching as a substring (add those to `ALLOWED` in `leak_check.py`); a
genuine leak needs `git filter-repo` before anything is pushed.
