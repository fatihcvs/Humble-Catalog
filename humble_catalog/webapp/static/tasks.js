// The Tasks section: start a catalog command and watch it run.
//
// Every card posts to /api/jobs/start, whose whitelist is the authority
// on what may run. The cards here are a menu of that whitelist, never a
// second definition of it -- a test pins the two sets equal.
//
// login, reset and restore are absent because they need a terminal, and
// the handoff that gives them one is separate work.
const TASK_CARDS = [
  {group: "Update", command: "extract", label: "Fetch new bundles",
   note: "Asks HumbleBundle for purchases you have not catalogued yet. Minutes."},
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
  {group: "Diagnose", command: "check", label: "Test every source",
   note: "One live search per metadata API, to see which keys work."},
];

const TASK_GROUPS = ["Update", "Enrich", "Import", "Backup", "Diagnose"];

function renderTasks() {
  const el = $("#task-cards");
  if (!el) return;
  el.innerHTML = TASK_GROUPS.map((group) => `
    <div class="task-group">
      <h3>${esc(group)}</h3>
      ${TASK_CARDS.filter((c) => c.group === group).map((c) => `
        <div class="task-card">
          <div class="task-label">${esc(c.label)}</div>
          <div class="task-note">${esc(c.note)}</div>
          <button class="task-go" data-command="${esc(c.command)}"
                  data-options='${esc(JSON.stringify(c.options || {}))}'
                  >Run</button>
        </div>`).join("")}
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
  const log = state.log || [];
  if (log.some((line) => EXPIRED.test(line)))
    parts.push(`<div class="job-hint">Your HumbleBundle session has expired.
      Run <code>python -m humble_catalog login</code> in the terminal running
      this viewer, then try again.</div>`);
  // esc() is not optional here: these lines are the child's stdout, which
  // names owned titles verbatim and is nobody's idea of trusted markup.
  if (log.length)
    parts.push(`<pre class="job-log">${esc(log.slice(-200).join("\n"))}</pre>`);
  el.innerHTML = parts.join("");
  el.hidden = parts.length === 0;
  return el.innerHTML;
}

async function pollJobs() {
  const state = await (await fetch("/api/jobs")).json();
  renderJobPanel(state);
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
