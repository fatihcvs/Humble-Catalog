// The Bundles section: paste a HumbleBundle URL, get per-tier owned/new
// counts. Read-only and unpersisted -- it answers "should I buy this",
// so it holds no state worth surviving a reload.

// ---- Bundle preview panel ---------------------------------------------
// Paste a live bundle URL, get a per-tier count of owned versus new. The
// counting lives only in bundle_preview.py, so the numbers all arrive
// with the data and there is nothing here to drift from the CLI.
//
// Unlike the statistics panel this is fetch-on-demand rather than
// rendered at page load, so it needs no refresh-after-mutation wiring: it
// holds no state that can go stale.

let bundlePreview = null, bundlePreviewError = null;
let bundlePreviewOpen = true;

const CURRENCY_SYMBOLS = {EUR: "€", USD: "$", GBP: "£",
                          CAD: "CA$", AUD: "A$"};

function money(amount, currency) {
  const symbol = CURRENCY_SYMBOLS[currency];
  return symbol ? symbol + amount.toFixed(2)
                : `${currency} ${amount.toFixed(2)}`;
}

async function previewBundle(url) {
  bundlePreview = bundlePreviewError = null;
  // POST, never GET: a bundle URL in a query string reaches access logs
  // and browser history.
  const resp = await post("/api/bundle-preview", {url});
  const body = await resp.json();
  if (resp.ok) bundlePreview = body;
  else bundlePreviewError = body.error || "could not read that bundle";
  renderBundlePreview();
}

function renderBundlePreview() {
  const panel = $("#bundle-panel");
  panel.hidden = !bundlePreview && !bundlePreviewError;
  if (panel.hidden) return;
  if (bundlePreviewError) {
    panel.innerHTML = `<p class="bundle-error">${esc(bundlePreviewError)}</p>`;
    return;
  }
  const rows = bundlePreview.tiers.map((t) => `<tr>
    <td class="bundle-price">${esc(money(t.price, bundlePreview.currency))}</td>
    <td>${t.total} ${t.total === 1 ? "item" : "items"}</td>
    <td>owned <b>${t.owned}</b></td>
    <td>new <b>${t.new}</b></td></tr>`).join("");
  // Every tier row first, then the lists. Interleaving them read fine in
  // the spec and badly in a browser: eight titles sat between the first
  // two prices and pushed the cheapest tier ~500px down, so the three
  // numbers the panel exists to compare were never on screen together.
  // The comparison is what must not scroll; the detail may.
  //
  // Each heading carries its own price, because a list is now further
  // from its row, and repeats the count: the tier's `new` is cumulative
  // while `adds` is incremental, so the two legitimately disagree.
  // Omitted entirely for a tier that adds nothing.
  const lists = bundlePreview.tiers.filter((t) => t.adds.length).map((t) => `
    <section class="bundle-adds">
      <h4>${esc(money(t.price, bundlePreview.currency))} adds ${t.adds.length} new</h4>
      <ul>${t.adds.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
    </section>`).join("");
  // Inside the owned count on the row above, not beside it -- so this
  // explains a number rather than adding a fourth one. A game reached only
  // by a key is paid for but not yet in any library, which can fail in ways
  // an owned row cannot (expired, region-locked), so the panel says which
  // games the count is trusting a key for. `|| []` because a tier from an
  // older server carries no keyed_items at all.
  // Never "unredeemed": Humble marks a key redeemed the moment its value is
  // revealed, which says nothing about whether the game ever reached a store
  // account -- the bug that started this counted a revealed-but-unactivated
  // key's game as new. Absence from every imported library is what is
  // actually known, so it is what is said. One line, not a wrapped template:
  // the heading is asserted as a substring, and indentation would split it.
  const keyedNoun = (n) =>
    `${n} owned via ${n === 1 ? "a Humble key" : "Humble keys"}`
    + " (not in any imported library)";
  const keyed = bundlePreview.tiers
    .filter((t) => (t.keyed_items || []).length).map((t) => `
    <section class="bundle-keyed">
      <h4>${esc(money(t.price, bundlePreview.currency))} — ${keyedNoun(t.keyed_items.length)}</h4>
      <ul>${t.keyed_items.map((k) => `<li>${esc(k.offered)}
        <span class="bundle-score">(${esc([
          k.key_type ? k.key_type + " key" : null, k.bundle,
        ].filter(Boolean).join(", "))})</span></li>`).join("")}</ul>
    </section>`).join("");
  // Kept visually separate from the counts above, and labelled a
  // suspicion: owned/new are exact-id facts, these are guesses. If the
  // two ever merge into one number, that number stops being a fact.
  const overlaps = bundlePreview.overlaps.length ? `
    <section class="bundle-overlaps">
      <h4>Possibly already owned in part (${bundlePreview.overlaps.length})</h4>
      <ul>${bundlePreview.overlaps.map((o) => `<li>
        ${esc(o.offered)} ~
        <button class="bundle-jump" data-item="${o.item_id}"
          >${esc(o.item_name)}</button>
        <span class="bundle-score">(${o.score.toFixed(2)})</span></li>`)
        .join("")}</ul></section>` : "";
  panel.innerHTML = `<details${bundlePreviewOpen ? " open" : ""}>
    <summary>${esc(bundlePreview.name)}</summary>
    <table class="bundle-tiers"><tbody>${rows}</tbody></table>
    ${lists}${keyed}${overlaps}</details>`;
  panel.querySelector("details").addEventListener("toggle",
    (ev) => { bundlePreviewOpen = ev.target.open; });
}

$("#bundle-go").addEventListener("click", () => {
  const url = $("#bundle-url").value.trim();
  if (url) previewBundle(url);
});
$("#bundle-url").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") $("#bundle-go").click();
});
