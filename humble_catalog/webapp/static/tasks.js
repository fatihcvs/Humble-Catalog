// The Tasks section: start a catalog command and watch it run.
//
// Every card posts to /api/jobs/start, whose whitelist (jobs.COMMANDS) is
// the authority on what may run -- except the cards marked `handoff`,
// which post to /api/jobs/handoff and are a menu of handoff.COMMANDS.
// login, reset and restore need a terminal: the viewer steps down, runs
// them in the console `serve` was started from, and comes back. The cards
// here are a menu of those two whitelists, never a second definition of
// either -- a test pins each set equal.
const TASK_CARDS = [
  {group: "Update", command: "extract", label: "Fetch new bundles",
   note: "Asks HumbleBundle for purchases you have not catalogued yet. Minutes."},
  {group: "Update", command: "login", label: "Log in to HumbleBundle",
   handoff: true,
   note: "Opens a browser window to sign in. Needed when a fetch says the session expired."},
  {group: "Update", command: "reparse", label: "Rebuild from the cache",
   note: "Re-reads bundles already downloaded. No network. Seconds."},
  {group: "Enrich", command: "harvest", label: "Harvest metadata",
   note: "Fetches every source for every title. Hours, and resumable."},
  {group: "Enrich", command: "harvest", label: "Harvest, ignoring quota",
   options: {ignore_quota: true},
   note: "Retries sources recorded as out of quota. Use after adding a key."},
  {group: "Enrich", command: "enrich", label: "Match and fill",
   note: "Matches the harvested cache to your items. Seconds."},
  {group: "Enrich", command: "enrich", label: "Match, retrying misses",
   options: {retry: true},
   note: "Also re-scores items that previously found no match."},
  {group: "Enrich", command: "enrich", label: "Fill comic credits",
   options: {credits: true},
   note: "Writer and illustrator for matched comics. Slower; resumable."},
  {group: "Enrich", command: "enrich", label: "Fill series from titles",
   options: {series: true},
   note: "Reads \"Vol. 2\" out of a title where no source supplied it."},
  {group: "Import", command: "import_sheets", label: "Import a spreadsheet",
   note: "Ratings and metadata from an .xlsx. Choose the file below."},
  {group: "Import", command: "import_games", label: "Import game libraries",
   note: "Reads Heroic's caches and Steam's Web API. No login."},
  {group: "Backup", command: "backup", label: "Back up the catalog",
   note: "A timestamped snapshot in backups/. Nothing is ever deleted."},
  {group: "Backup", command: "backup", label: "Back up with covers",
   options: {covers: true},
   note: "The snapshot plus a zip of covers/. Larger and slower."},
  {group: "Backup", command: "restore", label: "Restore a snapshot",
   handoff: true, picker: "snapshot",
   note: "Puts a backup back over the catalog, after snapshotting the current one."},
  {group: "Diagnose", command: "check", label: "Test every source",
   note: "One live search per metadata API, to see which keys work."},
  {group: "Danger", command: "reset", label: "Reset the catalog",
   handoff: true,
   note: "Wipes the derived catalog for a clean rebuild. Keeps downloads, covers and your ratings, tags and notes."},
];

// Danger is last and set apart: reset is the one card whose worst case
// is losing hand edits, merges and overrides.
const TASK_GROUPS = ["Update", "Enrich", "Import", "Backup", "Diagnose",
                     "Danger"];

function taskCard(c) {
  const picker = c.picker === "snapshot" ? `
    <div class="task-picker">
      <select id="restore-snapshot" aria-label="Snapshot to restore"></select>
      <label><input type="checkbox" id="restore-covers"> with covers</label>
    </div>` : "";
  return `
    <div class="task-card">
      <div class="task-label">${esc(c.label)}${c.handoff
        ? ` <span class="task-terminal">uses the terminal</span>` : ""}</div>
      <div class="task-note">${esc(c.note)}</div>
      ${picker}
      <button class="task-go"${c.picker === "snapshot" ? ' id="restore-go"' : ""}
              data-command="${esc(c.command)}"${c.handoff ? ' data-handoff="1"' : ""}
              data-options='${esc(JSON.stringify(c.options || {}))}'
              >Run</button>
    </div>`;
}

function renderTasks() {
  const el = $("#task-cards");
  if (!el) return;
  el.innerHTML = TASK_GROUPS.map((group) => `
    <div class="task-group${group === "Danger" ? " task-danger" : ""}">
      <h3>${esc(group)}</h3>
      ${TASK_CARDS.filter((c) => c.group === group).map(taskCard).join("")}
    </div>`).join("");
  return el.innerHTML;
}

// Reported through the panel rather than alert(): a refusal here is
// usually "something is already running", which is information about the
// page's own state and belongs on the page.
function taskMessage(text) {
  const el = $("#task-message");
  if (el) el.textContent = text || "";
}

async function startTask(command, options) {
  taskMessage("");
  const resp = await post("/api/jobs/start", {command, options});
  if (resp.status === 409) {
    // The one refusal with a second answer available: a run recorded as
    // active may simply be stale, so offer force rather than dead-ending.
    const {error} = await resp.json();
    taskMessage(`${error} Click Run again within 3 seconds to start anyway.`);
    return "busy";
  }
  if (!resp.ok) {
    taskMessage((await resp.json()).error || "Could not start that.");
    return "error";
  }
  await pollJobs();
  return "started";
}

if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest && ev.target.closest(".task-go");
    if (!btn) return;
    const command = btn.dataset.command;
    const options = JSON.parse(btn.dataset.options || "{}");
    if (btn.dataset.handoff) {
      // Two clicks only ARM the handoff. reset and restore still ask for
      // a word typed at the console; that, not this, is the real guard.
      armOrFire(btn, () => startHandoff(command, options));
      return;
    }
    if (command === "import_sheets") {
      // Nothing to start without a file; the picker IS this card's action.
      $("#sheet-file").click();
      return;
    }
    // Two clicks for every card, not just the risky ones: these all cost
    // real time or real network, and the arm text is the only place the
    // page can say so before it happens.
    armOrFire(btn, async () => {
      if (await startTask(command, options) === "busy")
        armOrFire(btn, () => post("/api/jobs/start",
                                  {command, options, force: true}));
    });
  });
}

// The one child failure the page translates rather than shows raw. The
// fix is a command in a terminal, and a user who is here precisely to
// avoid terminals needs to be told plainly which one.
const EXPIRED = /session (expired|missing)/i;

function renderJobPanel(state) {
  const el = $("#job-panel");
  if (!el) return;
  const running = state.running;
  // run_status is written by the CHILD, so there is a window after the
  // spawn where a job is running and no row exists yet. `|| null` keeps
  // that window a bar-less "starting" rather than a thrown renderer.
  const row = (state.progress || []).find(
    (p) => running && p.command === running.command) || null;
  const parts = [];
  if (running) {
    const bar = row
      ? `<progress value="${row.done}" max="${row.total || 1}"></progress>
         <span class="job-count">${esc(row.phase)} ${row.done}/${row.total}</span>
         <span class="job-current">${esc(row.current || "starting")}</span>`
      : `<span class="job-count">starting</span>`;
    parts.push(`<div class="job-head"><strong>${esc(running.command)}</strong>
                  ${bar}
                  <button id="job-cancel">Cancel</button></div>`);
  } else if (state.last) {
    const {command, state: how, exit_code: code} = state.last;
    // "cancelled" is its own word, never folded into failure: an
    // interrupted child exits non-zero by definition, and calling the
    // user's own deliberate stop a failure sends them hunting a fault
    // that is not there.
    const verdict = how === "done" ? "finished"
                  : how === "cancelled" ? "cancelled"
                  : `failed (exit ${esc(code)})`;
    parts.push(`<div class="job-head"><strong>${esc(command)}</strong>
                  <span class="job-verdict job-${esc(how)}">${verdict}</span></div>`);
  }
  // The terminal is where a handed-over command reports what it did (reset
  // exits 0 on an abort too), so the page only says that it ran.
  const handed = state.handoff && state.handoff.last;
  if (handed)
    parts.push(`<div class="job-handoff"><strong>${esc(handed.command)}</strong>
      ran in the terminal${handed.exit_code === null ? " and was interrupted"
        : ` (exit ${esc(handed.exit_code)})`}; the terminal shows what it did.</div>`);
  const log = state.log || [];
  if (log.some((line) => EXPIRED.test(line)))
    parts.push(`<div class="job-hint">Your HumbleBundle session has expired.
      <button class="task-go" data-command="login" data-handoff="1"
              data-options='{}'>Log in</button>
      (or run <code>python -m humble_catalog login</code> in the terminal
      running this viewer), then try again.</div>`);
  // esc() is not optional here: these lines are the child's stdout, which
  // names owned titles verbatim and is nobody's idea of trusted markup.
  if (log.length)
    parts.push(`<pre class="job-log">${esc(log.slice(-200).join("\n"))}</pre>`);
  el.innerHTML = parts.join("");
  el.hidden = parts.length === 0;
  return el.innerHTML;
}

// undefined, not null: a catalog with no job history reports last: null,
// and the first poll must still differ so it loads the list.
let lastFinished;
async function pollJobs() {
  const state = await (await fetch("/api/jobs")).json();
  renderJobPanel(state);
  // A finished job may have been a backup, which adds a snapshot.
  const finished = state.last ? state.last.finished_at : null;
  if (finished !== lastFinished) {
    lastFinished = finished;
    // Awaited so a test can count the request; still never fatal.
    await loadBackups().catch((err) =>
      console.error("loadBackups() failed:", err));
  }
}

function renderBackups(list) {
  const sel = $("#restore-snapshot");
  const go = $("#restore-go");
  if (!sel) return "";
  sel.innerHTML = list.length
    ? list.map((b) => `<option value="${esc(b.name)}">${esc(b.modified)}
        (${esc((b.size / 1e6).toFixed(1))} MB${b.covers ? ", covers" : ""})
        </option>`).join("")
    : `<option value="">No snapshots in backups/ yet</option>`;
  sel.disabled = list.length === 0;
  if (go) go.disabled = list.length === 0;
  return sel.innerHTML;
}

async function loadBackups() {
  const {backups} = await (await fetch("/api/backups")).json();
  renderBackups(backups || []);
}

// What to look at while the viewer is away. Shown only AFTER the second
// click -- the arm text on the button is the warning; this is the
// instruction.
const TAKEOVER_TEXT = {
  login: "A browser window is opening. Sign in to HumbleBundle, wait "
       + "for your library page, then close that window.",
  reset: "Switch to the terminal window you started the viewer from. "
       + "It asks you to type RESET; anything else cancels and changes "
       + "nothing.",
  restore: "Switch to the terminal window you started the viewer from. "
         + "It shows both catalogs and asks you to type RESTORE; anything "
         + "else cancels. The current catalog is snapshotted first.",
};

function renderTakeover(command) {
  const el = $("#handoff-screen");
  el.innerHTML = `<div class="handoff-box">
      <h2>${esc(command)} is running in the terminal</h2>
      <p>${esc(TAKEOVER_TEXT[command] || "")}</p>
      <p>The viewer is closed until it finishes. This page will reconnect
         by itself.</p>
    </div>`;
  el.hidden = false;
  return el.innerHTML;
}

function handoffBody(command, options) {
  if (command !== "restore") return {command, options};
  return {command,
          options: {covers: Boolean($("#restore-covers").checked)},
          snapshot: $("#restore-snapshot").value};
}

// Reload once the server answers with a generation past the one the
// request was answered with. Polling "/" alone cannot tell "back" from
// "not gone down yet": the first poll can land before the server steps
// down, and a reload then meets a refused connection mid-handoff. There is
// no timeout: a user reading the reset prompt may take minutes.
async function reconnect(generation,
                         sleep = (ms) => new Promise((r) => setTimeout(r, ms))) {
  for (;;) {
    await sleep(1000);
    try {
      const state = await (await fetch("/api/jobs")).json();
      if (state.handoff && state.handoff.generation > generation) {
        location.reload();
        return;
      }
    } catch (err) {
      // Refused while the command runs. That is the expected state.
    }
  }
}

async function startHandoff(command, options, sleep) {
  taskMessage("");
  const resp = await post("/api/jobs/handoff", handoffBody(command, options));
  if (!resp.ok) {
    taskMessage((await resp.json()).error || "Could not hand that over.");
    return "error";
  }
  const {generation} = await resp.json();
  renderTakeover(command);
  await reconnect(generation, sleep);
  return "handed";
}

async function uploadSheet(file) {
  // FileReader gives base64 via a data: URL, whose payload sits after the
  // comma. The endpoint takes JSON only -- see its docstring for why a
  // multipart form is not an option here.
  const b64 = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  const resp = await post("/api/jobs/import-sheets",
                          {filename: file.name, content_b64: b64});
  if (!resp.ok) {
    taskMessage((await resp.json()).error || "Could not import that file.");
    return;
  }
  taskMessage(`Importing ${file.name}.`);
  await pollJobs();
}

if (typeof document !== "undefined" && document.addEventListener) {
  document.addEventListener("click", async (ev) => {
    if (ev.target && ev.target.id === "job-cancel") {
      await post("/api/jobs/cancel");
      await pollJobs();
    }
  });
  document.addEventListener("change", (ev) => {
    if (ev.target && ev.target.id === "sheet-file" && ev.target.files[0])
      uploadSheet(ev.target.files[0]);
  });
}
