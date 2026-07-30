// The Keys section: Humble store keys whose game is in no imported
// library. Everything here reads /api/keys and nothing else -- the report
// is computed server-side by keys.py so this panel and the CLI cannot
// disagree, which is the same arrangement the statistics panel uses.
//
// Deliberately does NOT reuse catalog.js's chip-filter registry, sort or
// fuzzy search. All three are bound to the shared `items` array, and two
// views needing different column sets is the whole reason sections exist.

// The reported states, in display order, each doubling as its own chip.
// `matched` is absent on purpose: the server never sends it.
const KEY_STATES = [
  {state: "unredeemed",  label: "Not in a library"},
  {state: "uncertain",   label: "Near match"},
  {state: "uncheckable", label: "No importer"},
];

let keyRows = [], keyCounts = {}, keyLibraries = {}, keyTotal = 0;
// uncheckable is off by default: for those stores "not in any library" is
// unfalsifiable, so leaving them in would make the list mostly caveat.
let keyStates = new Set(["unredeemed", "uncertain"]);

const keysExpiring = () =>
  keyRows.filter((r) => r.expires && !r.expired).length;

const shownKeys = () => keyRows.filter((r) => keyStates.has(r.state));

function setKeyStates(states) {
  keyStates = new Set(states);
}

async function loadKeys() {
  const data = await (await fetch("/api/keys")).json();
  keyRows = data.rows || [];
  keyCounts = data.counts || {};
  keyLibraries = data.libraries || {};
  keyTotal = data.total || 0;
  renderKeys();
}

// Whole days from an ISO timestamp, so a row's urgency is computed in the
// browser rather than frozen at whatever moment the page was loaded.
// "today" rather than "in 0 days", matching what keys.py prints.
function keyWhen(row) {
  if (!row.expires) return "";
  if (row.expired) return "expired";
  const days = Math.floor((new Date(row.expires) - Date.now()) / 86400000);
  return days <= 0 ? "today" : `in ${days} days`;
}

function renderKeys() {
  const rows = shownKeys();
  const chips = KEY_STATES.map((s) => `<button class="key-chip${
    keyStates.has(s.state) ? " on" : ""}" data-state="${s.state}">${
    esc(s.label)} ${keyCounts[s.state] || 0}</button>`).join("");
  const libraries = Object.entries(keyLibraries).map(
    ([store, info]) => `${esc(store)} ${info.count} (imported ${
      esc((info.imported_at || "").slice(0, 10))})`).join(", ");
  $("#keys-panel").innerHTML = `
    <p class="keys-summary">${keyTotal} keys - ${keyCounts.matched || 0} in a
      library, ${rows.length} shown.
      Matching is by title and <strong>approximate</strong>; a revealed key
      was only displayed, which is not the same as activated.</p>
    <div id="key-chips">${chips}</div>
    ${libraries ? `<p class="keys-libraries">Libraries: ${libraries}</p>` : ""}
    <table id="key-table"><thead><tr>
      <th>Product</th><th>Store</th><th>Bundle</th><th>Purchased</th>
      <th>Expires</th><th>Revealed</th><th>State</th>
    </tr></thead><tbody>${rows.map((r) => `<tr class="key-${r.state}">
      <td>${esc(r.product || "")}${r.near_match
        ? ` <span class="key-near">~ ${esc(r.near_match.owned_title)} (${
            r.near_match.score.toFixed(2)})?</span>` : ""}</td>
      <td>${esc(r.key_type_label || "")}</td>
      <td>${r.bundle_url
        ? `<a class="tag tag-link" href="${esc(r.bundle_url)}" target="_blank"
             rel="noopener">${esc(r.bundle || "")}</a>`
        : esc(r.bundle || "")}</td>
      <td>${esc((r.purchased_at || "").slice(0, 10))}</td>
      <td>${esc(keyWhen(r))}</td>
      <td>${r.revealed ? "yes" : "no"}</td>
      <td>${esc((KEY_STATES.find((s) => s.state === r.state) || {}).label
                || r.state)}</td>
    </tr>`).join("")}</tbody></table>`;
}

// One delegated listener rather than one per chip, because renderKeys()
// rebuilds the whole panel through innerHTML and per-chip listeners would
// be detached on every redraw.
$("#keys-panel").addEventListener("click", (ev) => {
  const chip = ev.target.closest?.(".key-chip");
  if (!chip) return;
  const state = chip.dataset.state;
  if (keyStates.has(state)) keyStates.delete(state); else keyStates.add(state);
  renderKeys();
});
