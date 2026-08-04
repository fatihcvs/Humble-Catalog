# Running catalog operations from the viewer — design

Date: 2026-08-04

## Problem

Every operation that builds or changes the catalog is a CLI subcommand.
`extract`, `reparse`, `harvest`, `enrich`, `import-sheets`,
`import-games`, `backup`, `restore` and `reset` exist only as things
typed at a terminal. The viewer reads the result and can edit single
rows, but it cannot cause any of that work to happen.

That is a wall for anyone who does not live in a shell. They can be
walked through installing the project once and running `serve`, and from
then on the catalog is a website — right up to the moment it needs new
data, at which point the answer is "open a terminal and type this".

Half the plumbing is already there. `Progress` writes a `run_status` row
for every command, and `GET /api/status` reports the rows that are not
finished, which is what draws the viewer's banner. The viewer therefore
already *watches* work it cannot *start*. This spec adds the starting.

## Scope

Every catalog-changing command becomes reachable from the viewer,
including the three destructive ones. Five commands are deliberately
excluded — `stats`, `export`, `keys`, `bundle` and `choice` — because
the viewer already does all five natively, and a button that shelled out
to the CLI for them would create a second implementation of an answer
the viewer already computes.

Out of scope: packaging, an installer, or any attempt to remove the
terminal from first-time setup. The user still runs `pip install` and
`python -m humble_catalog serve` themselves, so a console window exists
and is theirs — which the handoff below depends on.

## Two classes of command

| In-page (subprocess) | Handoff (terminal) |
| --- | --- |
| `reparse`, `harvest`, `enrich`, `extract`, `import-games`, `import-sheets`, `backup`, `check` | `login`, `reset`, `restore` |

The split is not a matter of taste. Each of the three on the right needs
something a background job cannot have:

- **`login`** must open a foreground browser window the user can click
  through. `manual_login` launches a *non-automated* Chromium — Google
  refuses sign-in inside an automated one — and then blocks on
  `proc.wait()` until the window is closed.
- **`restore`** swaps `catalog.db` under the process. It refuses to run
  while `serve` holds the file, and that refusal is correct.
- **`reset`** is guarded by a word typed at an interactive terminal, and
  that guard is kept rather than reimplemented (see Safety).

Everything else is headless and runs perfectly well as a child process
with its output piped somewhere.

### `extract` needs a `--no-login` flag

`extract` calls `humble_api.ensure_login()`, which checks the saved
session and, if it has expired, *silently* calls `manual_login()` and
blocks. Spawned as a background job that is a job which hangs forever on
a browser window the page never mentioned, with no output and no way to
tell it from a slow fetch.

So `extract` grows `--no-login`, which raises `NotLoggedIn` instead of
attempting the login. The web runner always passes it. The routine case
— an unattended fetch of new bundles against a live session — then runs
in-page like everything else, and only an expired session degrades into
the handoff: the page reports the expiry and offers a **Log in** button
that hands off to the terminal.

This follows a decision the project already made. `/api/choice-preview`
answers 409 on `NotLoggedIn` rather than logging in, with the comment
"The server must not attempt the login itself -- manual_login blocks on
a browser window it cannot see."

## Execution: a subprocess per job

A new `humble_catalog/jobs.py` owns a **single job slot**. One job at a
time: each of these commands is a whole-catalog operation, two at once
is never what a user means, and a second start request answers 409
naming what is already running.

`start(command, options)` spawns

```
[sys.executable, "-m", "humble_catalog", <command>, *flags]
```

in the viewer's working directory, with `stdout` and `stderr` merged and
piped. Argv is assembled from a whitelist table mapping each command to
the options it accepts; nothing from the request body is ever
interpolated into it, and no shell is involved.

**Why subprocesses rather than a worker thread.** Cancellation decides
it. `harvest` runs for hours, and a user who starts one must be able to
stop it; a Python thread cannot be safely killed, a process always can.
Isolation follows: a wedged network call or a crash costs the job, not
the viewer. And running the CLI literally keeps one definition of each
command, which is the rule stated verbatim in three existing route
comments — "the CLI and this route must not be able to disagree".

**Progress** needs no new transport. The child writes `run_status` as it
always has, and the page reads it. Because the piped stdout is not a
tty, `LiveDisplay` goes inert by itself and `Progress` emits one plain
line per step — exactly the log format the page wants, with no change to
`progress.py`.

**The log** is a bounded in-memory deque of the last 500 lines. In
memory only: those lines name owned titles (see Privacy).

**Cancel** sends a real interrupt — `CTRL_BREAK_EVENT` on Windows, the
process having been spawned with `CREATE_NEW_PROCESS_GROUP`, and
`SIGINT` elsewhere. That is the same `KeyboardInterrupt` the README
already promises `harvest` survives and resumes from. `terminate()` only
as an escalation after a grace period.

## HTTP surface

All JSON, all behind the existing loopback and Host-header guards.

- `POST /api/jobs/start` — `{command, options}`. 202 with the job; 409
  naming the running job when the slot is taken; 400 for an unknown
  command or an option that command does not accept.
- `POST /api/jobs/cancel` — interrupts the current job.
- `GET /api/jobs` — the runner's state: the running job, its
  `run_status` row, the log tail, and how the previous job ended
  (`done` / `failed` / `cancelled`, with exit code).
- `GET /api/backups` — the snapshots in `backups/`, so `restore` is
  chosen from a list rather than typed as a path.
- `POST /api/jobs/handoff` — `{command, options}`. Records the intent,
  answers 200, and the server then steps down (see below).

`GET /api/status` is left exactly as it is. `run_status` is the
CLI-neutral channel, so the banner keeps working for a `harvest` someone
started in a terminal, which the runner knows nothing about.

### The spreadsheet upload is base64 in JSON, not multipart

`import-sheets` needs a workbook. The obvious answer — a multipart form
post — would break an invariant the README states outright: *"Every
write endpoint takes JSON only"*, because form-encoded and multipart
bodies are precisely what a cross-origin HTML form can send, and that is
what makes a page you visit unable to drive the API.

So the workbook travels base64-encoded inside the JSON body, capped
server-side at 25 MB, written to a temp file, passed to the CLI by path,
and deleted in a `finally`. Slightly inelegant, and it keeps that
sentence in the README literally true with no exceptions and no CSRF
machinery to get wrong.

## The handoff

`serve()` becomes a loop rather than one `app.run()` call. It builds a
server with `werkzeug.serving.make_server` and serves until a handoff is
requested, then `shutdown()`s it and runs the requested command as a
subprocess **inheriting stdin and stdout**. Inheriting is the whole
point: it is what makes `input()` work for the typed `RESET`, and what
puts the login window in the foreground.

When the child exits, the console prints a line, the server is rebuilt,
and the browser is reopened. The handoff is wrapped in `try/finally` —
if the command raises, the viewer still comes back, or a crash in
`reset` leaves the user with no viewer and no explanation.

The page's side is a takeover screen, shown only **after** the second
click: what is about to happen, that the viewer will close, which window
to look at, and that the page will reconnect by itself. It then polls
the root URL until the server answers and reloads. Without it the user
gets `ERR_CONNECTION_REFUSED` mid-operation, which is exactly the
confusion this feature exists to remove.

## The Tasks tab

A fifth section beside Library, Maintenance, Keys and Bundles,
addressable by URL like the others.

Action cards, grouped: **Update** (`extract`, `reparse`), **Enrich**
(`harvest`, `enrich` and its `--retry` / `--credits` / `--series`
variants), **Import** (spreadsheets, games), **Backup** (`backup`,
`restore`), **Diagnose** (`check`), and a visually separated **Danger**
group holding `reset`. Each card says in one line what it does and
roughly how long it takes.

Handoff cards carry a "uses the terminal" mark and a two-click arm,
reusing `armOrFire` from `catalog.js` — the idiom this codebase already
uses for irreversible actions — rather than a new modal.

When a job is running, a panel above the cards shows the phase, the
progress bar and counts from `run_status`, elapsed time, the log tail in
a monospace pane, and Cancel.

**Tasks gets no count badge.** A tab badge in this viewer means a queue
you can empty, never an optional backlog, and "you could run a harvest"
is the definition of an optional backlog. A running job shows a live
indicator instead.

## Safety

The exposure changes and the README's "The viewer's exposure" section is
updated as part of this work, not afterwards. Today the worst a rogue
local process can do through the port is read the catalog and edit rows;
after this it can start jobs and schedule a wipe. Three things bound
that:

- Loopback binding, the Host-header check and JSON-only writes are
  untouched, so a *web page* still cannot drive any of it. The exposure
  is unchanged in kind: other processes on the same machine, which the
  README already names.
- Argv comes from the whitelist table. No shell, no body string in a
  process argument.
- **`reset` and `restore` keep their typed confirmation, at the
  terminal.** The two-click in the page only arms the handoff; a human
  still types `RESET` at a console. The destructive path's real guard is
  exactly as strong after this change as before it. Do not later
  "simplify" it into a web modal.

## Privacy

The log buffer holds owned titles — `enrich 12/300: <title>` — and so
does `/api/jobs`. That is the same exposure class as `/api/items`, which
already returns the whole library to the same loopback-only client. The
buffer is bounded, in memory, never written to a file and never part of
an export.

One consequence for the repo rather than the code: **a screenshot of the
Tasks tab with a live log is a leak**, and an invisible one —
`leak_check.py` cannot read pixels. Any screenshot of this feature is
taken against `scripts/demo_catalog.py` on port 8099.

## Error handling

A non-zero exit sets `failed` and surfaces the exit code with the last
log lines. Two cases are translated rather than shown raw:

- `extract` failing on an expired session becomes the "session expired →
  Log in" handoff prompt, not a stack trace.
- A `harvest` that stops on quota is reported as normal completion with
  when to come back. The CLI already draws that distinction and the page
  must not lose it.

Two failure modes are designed for, not merely caught:

- **Stale `run_status`.** A job that dies without writing `phase='done'`
  leaves a row that makes the banner claim a run is still going. The
  runner finalizes the row when the child exits, whatever the exit code.
  (The CLI has the same latent issue on Ctrl-C. Fixing it everywhere is
  out of scope; the runner will not add to it.)
- **A job already running in a terminal.** The runner cannot see a CLI
  `harvest`. Before starting, it checks `run_status` for a live row for
  that command and refuses, reporting when that row was last updated and
  offering an explicit "start anyway". Not airtight against a stale row,
  and it turns a silent double-run into a question.

## Testing

- `jobs.py` against a fake child (`sys.executable -c ...`): log capture,
  exit codes, cancellation, and the stale-row finalize. The signal path
  is asserted per platform.
- Route tests with the runner stubbed, so no test spawns a real command:
  whitelist rejection, 409 on a busy slot, the malformed-body cases every
  existing route covers, the upload size cap, and temp-file cleanup.
- The serve loop tested with a handoff stub that returns immediately.
- No test invokes a real `extract`, `login`, `reset` or `restore`.
- `scripts/verify` passes, and `leak_check.py` is run after the doc
  changes land.

## Delivery: two plans

Two independently mergeable branches off `main`.

**Plan 1 — in-page jobs.** `jobs.py`, `extract --no-login`,
`/api/jobs/start`, `/api/jobs/cancel`, `GET /api/jobs`, the Tasks tab
with the running-job panel, and the eight headless commands. Useful on
its own: the everyday loop — extract, harvest, enrich, import — becomes
clickable, and the three terminal commands stay exactly as they are
today.

**Plan 2 — the handoff.** The `serve` loop, `POST /api/jobs/handoff`,
`GET /api/backups`, the takeover-and-reconnect screen, and the
`login` / `reset` / `restore` cards, including the expired-session
prompt that Plan 1 leaves as a plain error.

Plan 2 has nothing to attach to without Plan 1, so the order is fixed.
