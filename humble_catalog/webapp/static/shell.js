// The shell: everything that belongs to the page rather than to any one
// section -- the run banner, the theme toggle, and the boot call.
//
// This file loads LAST. The boot call has to sit after every renderer it
// invokes has been defined; in app.js, where the spec first put it,
// load() would have called a render() that did not exist yet.

async function pollStatus() {
  const runs = (await (await fetch("/api/status")).json()).runs;
  const banner = $("#run-banner");
  banner.hidden = runs.length === 0;
  banner.textContent = runs.map(r =>
    `${r.command}: ${r.done}/${r.total} - ${r.current || "starting"}`).join(" | ");
}

// ---- Sections ---------------------------------------------------------
// The four sections. Order here is tab order. `keys` ships empty on
// purpose: the unredeemed key report is separate work, and a section
// that is not the table exercises the shell before the feature that
// needed it is built on top of it.
const SECTIONS = [
  {id: "library",     label: "Library"},
  {id: "maintenance", label: "Maintenance"},
  {id: "keys",        label: "Keys"},
  {id: "bundles",     label: "Bundles"},
];

const currentSection = () => {
  const name = (location.hash || "").replace(/^#\//, "");
  return SECTIONS.some((s) => s.id === name) ? name : "library";
};

// An unknown hash falls back to Library WITHOUT rewriting the URL: a
// silent rewrite would erase the evidence that a bookmark went stale.
function showSection(name) {
  const active = SECTIONS.some((s) => s.id === name) ? name : "library";
  for (const s of SECTIONS) {
    const el = $(`#section-${s.id}`);
    if (el) el.hidden = s.id !== active;
    const tab = $(`#tab-${s.id}`);
    if (tab) tab.setAttribute("aria-current", s.id === active ? "page" : "false");
  }
}

if (typeof addEventListener === "function")
  addEventListener("hashchange", () => showSection(currentSection()));

// Theme toggle. currentTheme() reads the explicit choice, falling back to
// the OS preference. Every DOM/global here is guarded so app.js still loads
// under the test harness, whose sandbox has no matchMedia/localStorage/
// documentElement.
function currentTheme() {
  const explicit = document.documentElement?.dataset?.theme;
  if (explicit) return explicit;
  return (typeof matchMedia === "function"
          && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
}
function syncThemeButton() {
  const dark = currentTheme() === "dark";
  const btn = $("#theme-toggle");
  btn.textContent = dark ? "☀" : "☾";
  btn.title = dark ? "Switch to light theme" : "Switch to dark theme";
}
$("#theme-toggle").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  if (document.documentElement) document.documentElement.dataset.theme = next;
  if (typeof localStorage !== "undefined") localStorage.setItem("hc-theme", next);
  syncThemeButton();
});

// Boot. load() runs every section's loader, so it cannot run until every
// section's script has. The section is chosen before load() so the first
// paint lands in the right place rather than flashing Library first.
showSection(currentSection());
load();
pollStatus();
setInterval(pollStatus, 5000);
syncThemeButton();
