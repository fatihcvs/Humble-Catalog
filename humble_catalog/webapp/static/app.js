// Shared ground for the viewer's sections. What lives here is exactly
// what more than one of them needs: the catalog itself, the vocabularies
// the table and the statistics must agree on, and the four helpers every
// section calls. Everything else belongs to a section.
//
// This file loads FIRST. Classic scripts run in <script> order and share
// one global scope, so a helper called by catalog.js has to be defined by
// a script that ran earlier.
let items = [];

// The gap flags, defined once so the #f-flag filter (visible) cannot
// disagree with what the Gaps section of the stats panel reports.
// A gap is "a column is falsy". flag values match index.html's #f-flag
// options and stats.py's GAPS; keep the three in step.
const GAPS = [
  {label: "Unrated",       flag: "unrated", empty: (i) => !i.my_rating},
  {label: "No cover",      flag: "nocover", empty: (i) => !i.cover_path},
  {label: "No source URL", flag: "nourl",   empty: (i) => !i.source_url},
];
const gapEmpty = Object.fromEntries(GAPS.map((g) => [g.flag, g.empty]));

// The enrichment.status vocabulary, each doubling as its own #f-flag
// value. Mirrors stats.py's ENRICHMENT keys.
const ENRICHMENT_STATES = ["matched", "low_confidence", "unmatched", "pending"];

const $ = (sel) => document.querySelector(sel);

async function load() {
  items = (await (await fetch("/api/items")).json()).items;
  foldCache.clear();
  // The four renderers are independent, so one failing must not take out
  // the rest. render() used to run first and unguarded: a single item
  // with a missing field threw here and left the table AND all three
  // panels empty, with nothing on screen to say why. Failures are now
  // contained and reported, so the rest of the page still comes up.
  for (const step of [render, loadReview, loadDupes, refreshStats, loadKeys]) {
    try {
      await step();
    } catch (err) {
      console.error(`${step.name}() failed:`, err);
    }
  }
  // Badges are computed here rather than by each section, because this
  // loop is the one place that has just run every loader. A section the
  // owner has never opened still reports its count.
  pending = {
    library: items.filter((i) => !i.my_rating).length,
    maintenance: reviewCount + dupeGroups.length,
    // Expiring keys, NOT the unredeemed count: see badgeCount in shell.js.
    // Unredeemed keys number in the hundreds and never reach zero, which
    // is exactly the always-lit badge that policy rules out.
    keys: keysExpiring(),
    bundles: 0,
  };
  renderBadges();
}

// Tolerates a missing array: render() runs before the review/dupes/genre
// loaders, so throwing here blanks the entire page rather than one cell --
// which is what a payload lacking a newer field (an older server, a
// partial response) would otherwise do.
const tagBadges = (arr) =>
  (arr || []).map(t => `<span class="tag">${esc(t)}</span>`).join("");

function esc(v) {
  return v == null ? "" : String(v).replace(/[&<>"]/g,
    (ch) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[ch]));
}

// Two-click confirmation: first click arms the button, second click (within
// 3 s) fires. Prevents one stray click from mis-attributing an item.
function armOrFire(el, fire) {
  if (el.dataset.armed) {
    delete el.dataset.armed;
    el.classList.remove("armed");
    fire();
    return;
  }
  el.dataset.armed = "1";
  el.classList.add("armed");
  const original = el.textContent;
  el.textContent = "Click again to confirm";
  setTimeout(() => {
    if (el.isConnected && el.dataset.armed) {
      delete el.dataset.armed;
      el.classList.remove("armed");
      el.textContent = original;
    }
  }, 3000);
}

async function post(url, body) {
  return fetch(url, {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})});
}
