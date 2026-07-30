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
// section's script has.
load();
pollStatus();
setInterval(pollStatus, 5000);
syncThemeButton();
