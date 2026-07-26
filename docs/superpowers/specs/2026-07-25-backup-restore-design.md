# Backup & restore — design

Date: 2026-07-25

## Problem

`reset` and `enrich --override-edited` are the only guarded paths in the
catalog, and both guard the same thing: a deliberate, named destructive
operation. Nothing guards a *mistake* — a bad hand edit, a bulk tag
applied to the wrong filter, a parser change that mangles rows on the
next `reparse`, or a stray delete.

The exposure is specific. A large part of the catalog is reconstructable
offline from the preserved layer (`raw_orders`, `source_cache`, the
cover files) — that is the core invariant of the reset design. But the
hand-authored layer is not reconstructable from anything: ratings, tags,
comments, reading status, type overrides, hand-edited enrichment values
and their `pre_edit` revert targets, merges, and dismissed dedupe pairs.
Those exist in exactly one place, `catalog.db`, and there is no second
copy.

## Goal

One command that writes a consistent, self-contained, timestamped copy
of `catalog.db` (optionally with `covers/`) to a gitignored location,
and one guarded command that puts a copy back.

## Why the online backup API, not a file copy

`db.connect()` sets `PRAGMA journal_mode = WAL` ([db.py:326]). Under WAL,
committed transactions live in `catalog.db-wal` until a checkpoint folds
them into the main file, so `catalog.db` on its own is **not** a complete
database at an arbitrary moment.

This was verified rather than assumed. With a connection open, a row was
inserted and committed, then a snapshot taken via
`sqlite3.Connection.backup()`: the snapshot contained the new row while
it was still resident in the WAL. A `shutil.copy` of `catalog.db` alone
would have silently produced a database missing that commit.

`Connection.backup()` is therefore load-bearing. It also produces a
single self-contained file with no `-wal`/`-shm` sidecars, and it works
while `serve` holds the database open, so a backup never requires
stopping the viewer.

## Command surface

Two new subcommands in `__main__.py`:

- **`backup [path]`** — write a snapshot. Optional positional
  destination directory, defaulting to `backups/`, mirroring how
  `export` takes an optional positional path. `--covers` also snapshots
  the cover files.
- **`restore <file>`** — put a snapshot back, guarded by a typed
  confirmation. `--covers` also restores the paired cover directory.

### Naming

Snapshots are named `catalog-YYYYMMDD-HHMMSS.db`. The compact form sorts
chronologically as plain text, and avoids the colons that ISO-8601 would
use — illegal in Windows filenames. If the name already exists, a `-2`,
`-3`, … counter is appended, which is reachable both in tests and from
two runs inside one second.

A `--covers` snapshot goes to `covers-YYYYMMDD-HHMMSS.zip` beside the
database file, sharing its timestamp so the pair is visibly related.

### Retention

None. Snapshots accumulate until deleted by hand.

This is a deliberate choice, not an omission. Automatic pruning would
mean the backup command *deletes catalog data* as a side effect, so a
bug in the prune logic would destroy precisely what the feature exists
to protect. A database snapshot is small (the catalog is mostly text),
so the cost of keeping them is low. Age-based expiry was rejected
outright: it can delete the only remaining backup when no new one has
been taken, which is the worst possible behaviour for a safety net.

## Privacy

A snapshot is a complete copy of the library, so it falls squarely under
the standing order in `CLAUDE.md`. `.gitignore` gains `backups/` **in
the same change that adds the command**, before any snapshot can exist —
not afterwards. The default destination lives inside the working tree
alongside `catalog.db` and `covers/`, which are protected the same way.

The positional path argument exists partly for this reason: an external
drive or a directory outside the repository is one argument away for
anyone who prefers backups that no ignore rule has to protect.

## `backup`

```python
def run(db_path="catalog.db", dest="backups", covers_dir="covers",
        with_covers=False, _now=None) -> Path
```

1. Refuse, with a clear message and no files created, if `db_path` does
   not exist.
2. Create `dest` if absent.
3. Resolve the timestamped name, applying the collision counter.
4. Open the source with **plain `sqlite3.connect`, deliberately not
   `db.connect`**, and `backup()` it into the destination path.
5. With `--covers`, write `covers_dir` to `dest/covers-<stamp>.zip`
   using `ZIP_STORED`.
6. Print the path written and its size; return the `Path`.

### Why not `db.connect` for the source

`db.connect()` runs `executescript(SCHEMA)` and `_migrate()`
([db.py:328]). Both *write to the database being snapshotted* — the
opposite of what a backup should do — and `sqlite3.connect` on a
non-existent path creates an empty file, so a mistyped `db_path` would
silently produce an empty catalog and then faithfully back that up.
Plain `sqlite3.connect` after an explicit existence check avoids both.

### Why a stored zip for covers, not a directory copy

`covers/` is many small files — measured at 2509 files averaging 4.3 KB,
11.1 MB in total — so the cost is per-file overhead, not bytes.
Benchmarked warm, best of three:

| Strategy | Time | Notes |
|---|---|---|
| `shutil.copytree` | 1.57 s | 2509 directory entries |
| zip `ZIP_STORED` | **0.51 s** | one artifact |
| zip `ZIP_DEFLATED` | 0.78 s | saves ~0.5 MB (4%) |
| hardlinks (`os.link`) | 0.89 s | near-zero disk |

A stored zip is chosen: roughly 3× faster than the directory copy, and
the gap widens with the library. The absolute local-disk difference is
about a second today, so speed alone would not settle it — the stronger
reasons are that the destination may be an external or network drive,
where 2509 per-file round-trips cost far more than on a local SSD, and
that one artifact matches the single-file property the database snapshot
already has.

**Compression is off.** `ZIP_DEFLATED` costs ~0.27 s to save ~4% on
already-compressed JPEG data — a bad trade for a snapshot format.

**Hardlinks are rejected** despite being competitive on speed and nearly
free on disk. They only work within a single volume, which would break
the external-drive destination the positional path exists to enable, and
they share inodes with the live files, so any in-place rewrite would
silently mutate the backup. Cover files are in practice never rewritten
— `_download_covers` only fetches rows where `cover_path IS NULL`, after
`relink` claims what is already on disk ([extract.py:62]) — but a
snapshot whose independence rests on that invariant holding forever is a
worse guarantee than one that simply copies the bytes.

## `restore`

```python
def restore(snapshot, db_path="catalog.db", dest="backups",
            covers_dir="covers", with_covers=False,
            _input=None, _now=None) -> bool
```

`dest` is where the step-3 safety snapshot is written, defaulting to the
same `backups/` a plain `backup` uses; it is not where the snapshot
being restored is read from, which is the explicit `snapshot` path.

The ordering is the design; every alternative ordering opens a wider
data-loss window.

1. **Validate the snapshot.** It exists, opens as SQLite, and passes
   `PRAGMA quick_check`. A typo'd or truncated file is rejected before
   the live catalog is touched at all.
2. **Show both sides and confirm.** Print the item count and
   modification time of the snapshot and of the live catalog, then
   require the user to type `RESTORE` verbatim. Non-interactive
   invocation (`not sys.stdin.isatty()`) refuses. This reuses the
   `_input`/`isatty` seam and the no-`--yes` policy established by
   `reset.run` ([reset.py:20]) rather than inventing a second pattern.
3. **Take a safety snapshot of the current catalog** by calling `run()`
   — the same function, so the safety net exercises the same code path
   every backup uses — and print its path. This is the file that undoes
   a mistaken restore.

   **Best-effort, never blocking.** A catalog SQLite refuses to open is
   the likeliest reason to be restoring, so this step must not be what
   prevents recovery. On `sqlite3.Error` it falls back to a raw byte
   copy named `catalog-<stamp>.unreadable.db` (with any `-wal`/`-shm`
   beside it), preserving the damaged bytes rather than discarding them,
   and the restore continues.

   The error is caught rather than predicted from the item count:
   readability does not settle it either way. A truncated file fails
   both the count and the backup; a file with one scribbled page fails
   the count yet backs up perfectly well. Verified against truncation,
   a scribbled header, a scribbled page, an empty file, and non-database
   content.
4. **Swap atomically**: copy the snapshot to a temporary file beside
   `db_path`, then `os.replace(tmp, db_path)`.
5. **Delete the stale `catalog.db-wal` and `catalog.db-shm`.**

### Step 4: why `os.replace` specifically

Verified on Windows with a connection held open on the target:
`os.replace` fails with `PermissionError` (winerror 32), while
`open(path, "wb")` **succeeds and corrupts the open database**. The
"refuse while the viewer is running" guarantee is therefore a property
of `os.replace`, not of the design in general; a later refactor to
copy-over-in-place would silently remove it.

On that failure, restore reports that the catalog is open in another
process and that `serve` should be stopped — and stops. It does not try
to close the other process's handle. The live database is untouched at
that point.

This guard is Windows-specific; POSIX replaces open files happily.

### Step 5: why it is automated

A stale `-wal` belongs to the *old* database. Left beside a swapped-in
file, SQLite may replay it over the restored data. This is the step a
hand-restore omits, and it does not fail loudly — which is the argument
for automating it rather than documenting it.

### Residual risk, stated

A crash between steps 4 and 5 leaves a restored database beside a stale
WAL, which SQLite may treat as recoverable and corrupt. The window is
microseconds, and both the safety snapshot from step 3 and the original
snapshot still exist on disk, so the situation is recoverable by
re-running `restore`.

Deleting the sidecars *before* the swap was considered and rejected: it
trades this window for a strictly worse one, since removing the live
`-wal` discards committed data if the swap then fails.

### Covers

With `--covers`, the paired `covers-<stamp>.zip` is extracted over
`covers_dir` after the database swap. If the flag is given and no paired
archive exists, restore reports that and makes no cover changes.

Extraction is the slower direction (measured ~1.9 s for the 2509-file
archive, against ~0.5 s to write it), which is the right way round: a
backup is routine, a restore is rare.

Entry names are written and read as bare filenames, never paths, so an
archive cannot place a file outside `covers_dir`. This matters less for
an archive the command wrote itself than for one handed to it, but
`restore` should not assume its input is safe merely because it usually
is.

## Module layout

- `humble_catalog/backup.py` — new module holding `run` and `restore`,
  mirroring how `reset.py` owns its one risky command and keeping the
  file focused.
- `__main__.py` — `backup` and `restore` subcommands.
- `.gitignore` — `backups/`.
- `README.md` — a `backup`/`restore` bullet in the Usage list.

## Testing

`tests/test_backup.py`, following `test_reset.py`'s shape: `tmp_path`
for isolation, an injected `_input` for the confirmation, a `_NoTTY`
class for the non-interactive guard, and seed rows drawn from
`docs/TEST-DATA.md` (`cooltower_android` / *Cool Tower Defense*, as
`test_reset.py` already uses). Run `.venv/Scripts/python
scripts/leak_check.py` after adding them.

- **WAL consistency** — write and commit through an open connection,
  back up, assert the snapshot sees the row. This is the test that fails
  if `backup()` is ever "simplified" into a file copy.
- **Backup does not mutate its source** — `PRAGMA user_version` and
  mtime unchanged. Pins the plain-`sqlite3.connect` choice.
- **Missing source refuses** and creates no files.
- **Name collision** within one second yields a `-2` suffix.
- **Restore round-trip** — snapshot, mutate the live catalog, restore,
  original values are back.
- **Restore takes a safety snapshot first**, containing the pre-restore
  state.
- **Restore clears stale `-wal`/`-shm`.**
- **Restore refuses** on a corrupt or non-SQLite file, on a wrong
  confirmation word, on `EOFError`, and without a TTY — each asserting
  the live catalog is unchanged.
- **Open-database guard** — with a connection held open, restore refuses
  cleanly. Marked `skipif(os.name != "nt")`, since POSIX has no
  equivalent behaviour and the project's `scripts/` target all three
  platforms.
- **Unreadable live catalog** — truncate the live catalog, then restore:
  it succeeds, keeps the damaged bytes as `*.unreadable.db`, and says
  "unreadable" rather than printing a null item count.
- **`--covers` round-trip** over a couple of dummy files: the archive is
  written beside the database snapshot with the same timestamp, and
  extracting it restores byte-identical files. Includes the
  missing-archive error.
- **Archive entries carry no path separators**, so extraction cannot
  escape `covers_dir`.

## Out of scope

- No retention or pruning of any kind.
- No `--yes` or otherwise scriptable `restore`.
- No selective/partial restore (single table, single item); a restore is
  whole-database by design.
- No covers-only restore. `--covers` is additive to the database swap,
  never an alternative to it: `items.cover_path` is the authoritative
  item-to-file mapping, so putting back cover files beside a database
  that does not reference them produces a mismatched pair rather than a
  restored state.
- No off-machine or scheduled backups; the positional destination is the
  extension point if that is ever wanted.
- No change to `reset`, `enrich --override-edited`, or any existing
  guarded path.
