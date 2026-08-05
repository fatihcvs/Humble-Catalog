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
