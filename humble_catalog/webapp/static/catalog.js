// The Library section: the table, its filters, sorting, the column
// picker, export, and bulk tagging -- plus the statistics summary, which
// describes the very rows the table is showing and so is read beside it
// rather than in a section of its own.
let sortKey = "name", sortAsc = true;

// Chip filters. Chips (picked from autocomplete) filter by exact tag
// membership, combined per the field's all/any mode; free text in the
// box is a live substring filter on top. A future filterable column
// joins by adding one registry entry here + one input in index.html.
// Order here mirrors the filter bar and the table columns.
const chipFilters = {
  genre:  {accessor: i => i.genre,
           chips: [], mode: "all", text: ""},
  // series and publisher are scalars, not arrays: wrap them so the
  // accessor keeps the array contract that passesChipFilters, the vocab
  // builder's flatMap, and tagCounts all rely on. scalar also hides the
  // all/any toggle, which for one-value-per-item fields is unsatisfiable.
  series: {accessor: i => i.series ? [i.series] : [],
           chips: [], mode: "any", text: "", scalar: true},
  authors: {accessor: i => i.authors,
            chips: [], mode: "all", text: ""},
  // The Narrator/Artist column shows narrator || illustrator, so the
  // filter spans both; a union rather than the column's either/or, so an
  // item carrying both stays findable under either name.
  narrator: {accessor: i => [...i.narrator, ...i.illustrator],
             chips: [], mode: "all", text: ""},
  publisher: {accessor: i => i.publisher ? [i.publisher] : [],
              chips: [], mode: "any", text: "", scalar: true},
  bundle: {accessor: i => i.bundles.map(b => b.name),
           chips: [], mode: "all", text: ""},
  // The personal vocabulary is its own pool, never merged with genre: a
  // genre "Fantasy" and a user tag "fantasy" mean different things, so
  // they stay separately selectable. Fields AND together, so picking one
  // of each narrows rather than widens.
  user_tags: {accessor: i => i.user_tags,
              chips: [], mode: "all", text: ""},
  // Free text, not a vocabulary: suggesting whole notes as chips would be
  // useless, so this filters on typed text only. scalar and textOnly mean
  // different things -- scalar marks one-value-per-item (hiding an
  // unsatisfiable all/any toggle), textOnly suppresses the vocabulary UI.
  user_comment: {accessor: i => i.user_comment ? [i.user_comment] : [],
                 chips: [], mode: "any", text: "", scalar: true, textOnly: true},
};

function passesChipFilters(item) {
  return Object.values(chipFilters).every(f => {
    const tags = f.accessor(item);
    if (f.chips.length) {
      const has = (c) => tags.includes(c);
      if (!(f.mode === "all" ? f.chips.every(has) : f.chips.some(has)))
        return false;
    }
    return !f.text || tags.some(t => t.toLowerCase().includes(f.text));
  });
}

// Match state for the current query, refilled by every visible() call
// and read by render(). Module state consumed by an innerHTML rebuild,
// the same shape as editingTags and genresOpen.
//
// Cleared inside visible() rather than in the search handler because
// shownRows() also calls visible(): spans surviving into a later render
// are exactly the kind of stale-state bug the JS harness exists to catch.
const matchScores = new Map(), matchSpans = new Map();

// Reading-status filter: an "any of the ticked states" set. Not a
// chipFilters entry -- that registry is for open-ended text vocabularies
// with an all/any toggle, and "all" is unsatisfiable for a one-value
// field. Empty means no status constraint.
const statusFilter = new Set();

// Relevance ordering is a flag rather than a sortKey value: sortValue()
// would otherwise have to answer "what is this item's relevance", which
// is a property of the item AND the current query, not of the item.
// Typing turns it on, clicking a column header turns it off.
let relevanceSort = false;
const relevanceActive = () => relevanceSort && $("#search").value.trim() !== "";

// Folding a name is the per-keystroke cost that is trivially avoidable;
// the tier matching is not. Cleared whenever the catalog reloads.
const foldCache = new Map();
const cachedFold = (item) => {
  let folded = foldCache.get(item.id);
  if (!folded) foldCache.set(item.id, folded = Fuzzy.fold(item.name));
  return folded;
};

function visible() {
  const q = $("#search").value.trim();
  const type = $("#f-type").value, flag = $("#f-flag").value;
  const rating = $("#f-rating").value;
  matchScores.clear();
  matchSpans.clear();
  return items.filter(i => {
    // Name only: every other field it used to span now has its own
    // filter, so a catch-all here would just duplicate them. Matching is
    // fuzzy: see fuzzy.js for the tiers and the 0.4 cutoff.
    if (q) {
      const m = Fuzzy.score(q, i.name, cachedFold(i));
      if (m.score < 0.4) return false;
      matchScores.set(i.id, m.score);
      matchSpans.set(i.id, m.spans);
    }
    if (type && i.type !== type) return false;
    if (rating && i.my_rating !== +rating) return false;
    if (statusFilter.size && !statusFilter.has(i.read_status || "unread"))
      return false;
    if (!passesChipFilters(i)) return false;
    if (flag === "multi" && i.bundles.length < 2) return false;
    if (flag === "review" && !["low_confidence", "unmatched"].includes(i.status)) return false;
    // "review" deliberately spans low_confidence AND unmatched, which is
    // the workflow question. Each state also gets its own flag, named for
    // itself, so a stats panel row showing 4 unmatched jumps to exactly
    // those 4 rather than to the 8 the union holds.
    if (ENRICHMENT_STATES.includes(flag) && i.status !== flag) return false;
    // unrated / nocover / nourl all share one shape: keep only items the
    // selected gap predicate calls empty. Non-gap flags miss gapEmpty and
    // fall through to their own checks below.
    if (gapEmpty[flag] && !gapEmpty[flag](i)) return false;
    // Membership, not content: the notes text filter and the user-tag chip
    // filter both match everything on an empty query, so neither can answer
    // "what have I annotated at all?". Guards follow tagBadges/person -- a
    // partial payload from an older server has blanked this page before.
    if (flag === "notes" && !(i.user_comment || "").trim()) return false;
    if (flag === "mytags" && !(i.user_tags || []).length) return false;
    if (flag === "override" && !i.override) return false;
    return true;
  }).sort((a, b) => {
    if (relevanceActive())
      return (matchScores.get(b.id) || 0) - (matchScores.get(a.id) || 0)
          || String(a.name).localeCompare(String(b.name));
    const av = sortValue(a, sortKey), bv = sortValue(b, sortKey);
    const cmp = typeof av === "number" || typeof bv === "number"
      ? (av || 0) - (bv || 0) : String(av).localeCompare(String(bv));
    return sortAsc ? cmp : -cmp;
  });
}

// The sort value for a column. Most columns sort on the raw field, but the
// Narrator/Artist column shows narrator‖illustrator (so it sorts on the same
// via person()), and Bundle has no scalar field — it is an array of {name}.
function sortValue(item, key) {
  if (key === "narrator") return person(item).join(", ");
  if (key === "bundle") return item.bundles.map(b => b.name).join(", ");
  // Number, not the key string: alphabetical would interleave the states
  // meaninglessly. A missing status sorts as unread, matching visible().
  if (key === "read_status")
    return READ_STATUS_ORDER[item.read_status ?? "unread"] ?? READ_STATUS_ORDER.unread;
  return item[key] ?? "";
}

// Reading status. Stored as stable snake_case keys; the array is the
// single source of both the labels and the lifecycle order (used by the
// status sort in sortValue). Kept in sync with export.py's READ_STATUS_LABELS.
const READ_STATUS = [
  ["want_to_read", "Want to read"],
  ["unread", "Unread"],
  ["reading", "Reading"],
  ["read", "Read"],
  ["dnf", "DNF"],
];
const READ_STATUS_LABEL = Object.fromEntries(READ_STATUS);
const READ_STATUS_ORDER = Object.fromEntries(READ_STATUS.map(([k], n) => [k, n]));

// A missing status reads as unread: an older server, or any partial
// payload, can omit the field, and the column is NOT NULL DEFAULT 'unread'
// on the server anyway. Guards match tagBadges/person.
function statusSelect(i) {
  const cur = i.read_status || "unread";
  return `<select class="read-status-select rs-${cur}" data-id="${i.id}">`
    + READ_STATUS.map(([k, label]) =>
        `<option value="${k}"${k === cur ? " selected" : ""}>${label}</option>`
      ).join("")
    + "</select>";
}

function stars(item) {
  let html = "";
  for (let n = 1; n <= 5; n++)
    html += `<span class="star ${item.my_rating >= n ? "on" : ""}" `
          + `data-id="${item.id}" data-n="${n}">★</span>`;
  return html;
}

let editingId = null;
let editingTags = null;  // {field: [tags]} while a row is being edited

const vocab = (field) =>
  [...new Set(items.flatMap(i => i[field] || []))].sort();

const tagCounts = (accessor) => {
  const counts = new Map();
  for (const i of items)
    for (const t of accessor(i) || []) counts.set(t, (counts.get(t) || 0) + 1);
  return counts;
};

function chipCell(field) {
  return `<td class="ac-wrap">${editingTags[field].map((t, idx) =>
      `<span class="tag">${esc(t)}<button class="tag-x" data-f="${field}"
             data-i="${idx}" title="Remove">&times;</button></span>`).join("")}
    <input class="tag-input" data-f="${field}" placeholder="add...">
  </td>`;
}

// Re-attach after every render: the table is rebuilt via innerHTML.
function wireTagInputs() {
  for (const input of document.querySelectorAll(".tag-input")) {
    const field = input.dataset.f;
    Autocomplete.attach(
      input,
      () => vocab(field).filter(v => !editingTags[field].includes(v)),
      (value) => {
        if (!editingTags[field].includes(value)) editingTags[field].push(value);
        render();
        document.querySelector(`.tag-input[data-f="${field}"]`)?.focus();
      },
      () => tagCounts(i => i[field]));
  }
}

// Decide whether a save needs to post /edit at all.
//
// Every /edit call snapshots the row and marks it hand-edited, which
// locks it against re-enrichment. So a save that only changed the user
// tags or the note must NOT post /edit -- otherwise jotting a private
// note would silently lock the row, defeating the whole reason those
// columns live on `items` instead of `enrichment`.
//
// `item` is the pre-edit item from /api/items; `fields` is what the form
// is about to send: source_url, series, series_number (strings from the
// inputs) plus the genre/authors/narrator|illustrator tag arrays.
//
// Biased toward posting: a false negative silently drops a real edit,
// which is far worse than a false positive (an unnecessary "edited"
// badge). So anything unrecognised or ambiguous returns true.
function shouldPostEnrichmentEdit(item, fields) {
  if (!item) return true;                 // unknown row: never skip a save
  // Inputs yield trimmed strings ("2", "" when cleared) while the item
  // holds typed values (2.0, null), so compare in the form's terms.
  const asForm = (v) => v == null ? "" : String(v);
  for (const [key, value] of Object.entries(fields)) {
    if (Array.isArray(value)) {
      const before = item[key] || [];      // order counts: reordering is an edit
      if (before.length !== value.length
          || before.some((t, idx) => t !== value[idx])) return true;
    } else if (asForm(item[key]) !== asForm(value)) {
      return true;
    }
  }
  return false;
}

// The Narrator/Artist column shows narrator || illustrator; edit whichever
// has values, defaulting by type (comics get illustrator).
function personField(i) {
  if ((i.narrator || []).length) return "narrator";
  if ((i.illustrator || []).length) return "illustrator";
  return i.type === "comic" ? "illustrator" : "narrator";
}

// Same missing-array tolerance as tagBadges: this feeds it, and reading
// .length off an absent field would throw before it ever got there.
const person = (i) => (i.narrator || []).length ? i.narrator : (i.illustrator || []);

// The rows the viewer is currently showing: the bulk bar's target and the
// export's payload. `filtered` says whether the view is actually narrowed:
// bulk removal is gated on it, so "remove from every item" is never one
// click away.
function shownRows() {
  const rows = visible();
  return {ids: rows.map(i => i.id), count: rows.length,
          filtered: rows.length < items.length};
}

function renderBulkBar() {
  const {count, filtered} = shownRows();
  const tag = $("#bulk-tag").value.trim();
  const addBtn = $("#bulk-add"), removeBtn = $("#bulk-remove");
  addBtn.textContent = `Add to ${count} shown`;
  removeBtn.textContent = `Remove from ${count} shown`;
  addBtn.disabled = !tag || count === 0;
  // Removing is unrecoverable -- user_tags has no pre_edit snapshot -- so
  // it needs an actual filter, not just a confirmation.
  removeBtn.disabled = !tag || count === 0 || !filtered;
  $("#bulk-note").textContent =
    !filtered && tag ? "Narrow the view to remove." : "";
}

// The exporter's columns, mirrored here to render the picker. Duplicated
// across the language boundary on purpose -- the alternative is a request
// just to learn the column constants -- and pinned by a test that fails if
// export.py's COLUMNS and this list drift apart.
const EXPORT_COLUMNS = [
  "title", "type", "publisher", "authors", "genre", "series",
  "series_number", "narrator", "illustrator", "my_rating",
  "external_rating", "rating_source", "formats", "bundles",
  "first_purchased", "status", "edited", "user_tags", "user_comment",
  "read_status",
];

// The selection lives here, not in the checkboxes: the boxes are a
// rendering of this set. Reading state back out of the DOM would also be
// untestable, since the JS harness has no real elements.
let exportColumns = new Set(EXPORT_COLUMNS);

function saveColumnSelection() {
  // Guarded like hc-theme: the test sandbox has no localStorage.
  if (typeof localStorage === "undefined") return;
  localStorage.setItem("hc-export-columns", JSON.stringify([...exportColumns]));
}

// Stored state can outlive a COLUMNS rename by months, so this is the
// boundary where old browser state meets the current column list. Every
// way of being unusable -- absent, unparseable, not an array, or naming
// only columns that no longer exist -- collapses to the same answer:
// select everything. That is the one default that is never a silent
// surprise, since a narrowed export is what needs justifying, not a
// complete one.
function loadColumnSelection() {
  if (typeof localStorage === "undefined") return;
  let stored;
  try {
    stored = JSON.parse(localStorage.getItem("hc-export-columns"));
  } catch {
    // Corrupt JSON is not worth a message: the fallback IS the fix, and
    // the next toggle overwrites it.
    return;
  }
  if (!Array.isArray(stored)) return;
  // Filter first, then check: a stored list naming only columns that have
  // since been renamed is indistinguishable from having no preference at
  // all, and must not leave the picker empty with the button disabled and
  // no explanation.
  const known = stored.filter(c => EXPORT_COLUMNS.includes(c));
  if (known.length) exportColumns = new Set(known);
}

// The count is the whole justification for persisting the selection: a
// narrowed export is then never invisible.
function renderColumnCount() {
  $("#column-picker-summary").textContent =
    `Columns (${exportColumns.size}/${EXPORT_COLUMNS.length})`;
}

// Rendered from EXPORT_COLUMNS rather than hand-written into index.html,
// so a column added to export.py cannot be silently missing here.
//
// Only for the cases where the boxes disagree with the set: startup, and
// Select all/none. NOT for a plain toggle -- see toggleColumn.
function renderColumnPicker() {
  $("#column-picker-body").innerHTML = EXPORT_COLUMNS.map(c =>
    `<label><input type="checkbox" class="col-check" data-col="${c}"` +
    `${exportColumns.has(c) ? " checked" : ""}> ${esc(c)}</label>`).join("");
  renderColumnCount();
}

function toggleColumn(name, on) {
  if (on) exportColumns.add(name); else exportColumns.delete(name);
  saveColumnSelection();
  // Deliberately NOT renderColumnPicker(): rebuilding the list detaches
  // the checkbox that was just clicked, so the dismiss-on-click handler
  // then tests contains() against a node no longer in the document,
  // reads the click as landing elsewhere, and closes the panel
  // mid-click. The click already put the box in the right state, so only
  // the count is stale.
  renderColumnCount();
  renderExportButton();
}

// The label doubles as the blast-radius readout: with no filter active
// the export IS the whole catalog. It says WHAT ROWS only -- the format
// is the select's job, so each fact is stated in one place. Disabled at
// zero rows, because a header-only file reads as a bug rather than as an
// empty result.
function renderExportButton() {
  const {count, filtered} = shownRows();
  const btn = $("#export");
  btn.textContent = filtered ? `Download ${count} shown` : "Download all";
  btn.disabled = count === 0 || exportColumns.size === 0;
}

// The rows on screen, posted as ids because the filter predicate lives
// here and not on the server. A Blob rather than a plain link: the request
// has to be a POST, since ids in a query string would put a description of
// the library into access logs and browser history.
async function downloadExport() {
  const {ids, filtered} = shownRows();
  if (!ids.length) return;
  // Not persisted: format is a choice made at the moment of clicking, not
  // a standing preference. The fallback covers a stubbed or absent select.
  const fmt = $("#export-format").value || "csv";
  // Canonical order is the server's job (export._columns), so this posts
  // a set, not an order.
  const columns = EXPORT_COLUMNS.filter(c => exportColumns.has(c));
  const resp = await post(`/api/export.${fmt}`, {ids, columns});
  if (!resp.ok) {
    // Names the format: "could not build the CSV" after clicking XLSX
    // would send someone looking in the wrong place.
    alert(`Could not build the ${fmt.toUpperCase()} file.`);
    return;
  }
  // Content-Disposition stops being authoritative once we materialize the
  // file ourselves, so the filename is decided here -- which is also where
  // `filtered` already is. A filtered export is a different artifact and
  // must not silently overwrite the full one in the downloads folder.
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  // Narrowed on EITHER axis: fewer rows or fewer columns both make this a
  // different artifact, which must not overwrite the full catalog file.
  const narrowed = filtered || columns.length < EXPORT_COLUMNS.length;
  a.download = `catalog${narrowed ? "-filtered" : ""}.${fmt}`;
  a.click();
  URL.revokeObjectURL(url);
}

async function runBulk(el, action) {
  const {ids} = shownRows();
  const tag = $("#bulk-tag").value.trim();
  if (!tag || !ids.length) return;
  armOrFire(el, async () => {
    const resp = await post("/api/user-tags/bulk", {ids, tag, action});
    if (!resp.ok) {
      alert((await resp.json()).error || "Could not apply the tag.");
      return;
    }
    const {changed} = await resp.json();
    const verb = action === "add" ? "Added to" : "Removed from";
    await load();
    $("#bulk-note").textContent = `${verb} ${changed} of ${ids.length} items.`;
  });
}

function render() {
  const rows = visible();
  $("#count").textContent = `${rows.length} / ${items.length} items`
    + (relevanceActive() ? " · by relevance" : "");
  $("#catalog tbody").innerHTML = rows.map(i => i.id === editingId ? `<tr>
    <td>${i.cover_path ? `<img src="/${i.cover_path}" alt="" loading="lazy">` : ""}</td>
    <td><strong>${esc(i.name)}</strong><br>
      <input class="edit-field edit-url" data-f="source_url" type="url"
             value="${esc(i.source_url)}" placeholder="Source URL"><br>
      <button class="edit-save" data-id="${i.id}">Save</button>
      <button class="edit-cancel">Cancel</button></td>
    <td>${i.type}</td>
    <td>${statusSelect(i)}</td>
    ${chipCell("genre")}
    <td><input class="edit-field" data-f="series" value="${esc(i.series)}">
      <input class="edit-field edit-num" data-f="series_number" type="number"
             step="any" value="${i.series_number ?? ""}" placeholder="#"></td>
    ${chipCell("authors")}
    ${chipCell(personField(i))}
    <td>${esc(i.publisher)}</td>
    <td>${i.bundles.map(b => `<a class="tag tag-link" href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.name)}</a>`)
          .join("")}</td>
    <td>${i.external_rating ? `${i.external_rating.toFixed(1)} <small>(${
          i.rating_source})</small>` : ""}</td>
    <td class="stars">${stars(i)}</td>
    ${chipCell("user_tags")}
    <td><textarea class="edit-comment" rows="2"
                  placeholder="Notes...">${esc(i.user_comment)}</textarea></td>
  </tr>` : `<tr>
    <td>${i.cover_path ? `<img src="/${i.cover_path}" alt="" loading="lazy">` : ""}</td>
    <td><strong>${highlight(i.name, matchSpans.get(i.id))}</strong>${i.source_url
        ? ` <a class="src-link" href="${esc(i.source_url)}" target="_blank"
             rel="noopener" title="Open source page">&#x2197;</a>` : ""}${
      i.status === "low_confidence" || i.status === "unmatched"
        ? ' <span class="badge">review</span>' : ""}${
      i.status === "matched" || i.status === "manually_fixed"
        ? ` <button class="redo" data-id="${i.id}" title="Redo this match">&#x27F3;</button>` : ""}
      <button class="edit" data-id="${i.id}" title="Edit fields">&#x270E;</button>${
      i.edited
        ? ` <span class="badge edited">edited</span>
            <button class="revert" data-id="${i.id}"
                    title="Revert to the enriched values">&#x21A9;</button>
            <button class="override" data-id="${i.id}"
                    title="${i.override
                      ? "Cancel the queued re-enrichment"
                      : "Let the next enrich run update this row"}">&#x21BB;</button>` : ""}${
      i.re_enriched
        ? ` <span class="badge">re-enriched</span>
            <button class="revert" data-id="${i.id}"
                    title="Revert to your edited values">&#x21A9;</button>` : ""}${
      i.override ? ' <span class="badge queued">re-enrich queued</span>' : ""}</td>
    <td>${i.type}</td>
    <td>${statusSelect(i)}</td>
    <td>${tagBadges(i.genre)}</td>
    <td>${esc(i.series)}${i.series_number ? " #" + i.series_number : ""}</td>
    <td>${tagBadges(i.authors)}</td>
    <td>${tagBadges(person(i))}</td>
    <td>${esc(i.publisher)}</td>
    <td>${i.bundles.map(b => `<a class="tag tag-link" href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.name)}</a>`)
          .join("")}</td>
    <td>${i.external_rating ? `${i.external_rating.toFixed(1)} <small>(${
          i.rating_source})</small>` : ""}</td>
    <td class="stars">${stars(i)}</td>
    <td>${tagBadges(i.user_tags)}</td>
    <td class="user-comment">${esc(i.user_comment)}</td>
  </tr>`).join("");
  wireTagInputs();
  renderBulkBar();
  renderExportButton();
  renderSortIndicators();
}

// Reflect the current sort onto the static header cells (the <thead> is not
// rebuilt by render()). querySelectorAll returns [] under the test harness,
// so this is a harmless no-op there.
function renderSortIndicators() {
  for (const th of document.querySelectorAll("#catalog th[data-sort]")) {
    const active = th.dataset.sort === sortKey;
    th.classList.toggle("sorted", active);
    const ind = th.querySelector(".sort-ind");
    // Suppressed while relevance orders the rows: a lit arrow would
    // claim the table is sorted by a column it is not sorted by.
    if (ind) ind.textContent = active && !relevanceActive()
      ? (sortAsc ? " ▲" : " ▼") : "";
  }
}

// Escaped HTML with the matched ranges wrapped in <mark>.
//
// Escaping order is load-bearing. The tempting form -- esc(text) then
// replace() -- escapes first and matches second, so spans computed
// against the raw string land at the wrong offsets in the escaped one,
// and a title containing "&" corrupts. Splitting on raw indices and
// escaping each piece is the only correct order. <mark> is generated
// here, never interpolated from data.
function highlight(text, spans) {
  if (!spans || !spans.length) return esc(text);
  let out = "", at = 0;
  for (const [start, end] of spans) {
    if (start < at) continue;            // overlapping span: first one wins
    out += esc(text.slice(at, start))
        + `<mark>${esc(text.slice(start, end))}</mark>`;
    at = end;
  }
  return out + esc(text.slice(at));
}

// ---- Statistics panel -------------------------------------------------
// Six sections -- type, ratings, reading status, enrichment, gaps, genres
// -- fetched from /api/stats. The counting lives only in stats.py: the
// labels, counts and order all arrive with the data, so there is no
// second implementation here to drift from the CLI's.

// Which filter a row of each section applies. This is the ONLY thing the
// viewer knows about the sections. Keys come from stats.py's SECTIONS.
const SECTION_FILTERS = {
  type:       (row) => { $("#f-type").value = TYPE_VALUES[row]; },
  rating:     (row) => { $("#f-rating").value = row.replace("★", ""); },
  enrichment: (row) => { $("#f-flag").value = ENRICHMENT_VALUES[row]; },
  gaps:       (row) => { $("#f-flag").value = GAP_VALUES[row]; },
  status:     (row) => { setOnlyStatus(STATUS_VALUES[row]); },
  genre:      (row) => { chipFilters.genre.chips = [row]; renderFilterChips(); },
};

// The panel sends back the row LABEL, so each section needs the label ->
// value mapping its control expects. Mirrors stats.py's vocabularies.
const TYPE_VALUES = {"E-books": "ebook", "Audiobooks": "audiobook",
                     "Comics": "comic", "Music/Soundtracks": "music",
                     "Android apps": "android"};
const ENRICHMENT_VALUES = {"Matched": "matched",
                           "Low confidence": "low_confidence",
                           "Unmatched": "unmatched", "Pending": "pending"};
const GAP_VALUES = {"Unrated": "unrated", "No cover": "nocover",
                    "No source URL": "nourl"};
const STATUS_VALUES = {"Want to read": "want_to_read", "Unread": "unread",
                       "Reading": "reading", "Read": "read", "DNF": "dnf"};

function setOnlyStatus(value) {
  statusFilter.clear();
  statusFilter.add(value);
  // The chips live in the header, which render() never rebuilds, so a jump
  // that changes the set has to re-sync their classes by hand -- including
  // lighting the one it selected, not just clearing the others.
  for (const chip of document.querySelectorAll(".status-chip"))
    chip.classList.toggle("on", chip.dataset.status === value);
}

const GENRE_PREVIEW = 15;
let statsData = null;
let statsOpen = false, genresShowAll = false, tagEditMode = false;

async function refreshStats() {
  statsData = await (await fetch("/api/stats")).json();
  renderStats();
}

function renderStats() {
  const panel = $("#stats-panel");
  // Re-run on every toggle, so it has to cope with not having fetched yet
  // rather than throwing and blanking the panel.
  panel.hidden = !statsData || !statsData.total;
  if (panel.hidden) return;
  const blocks = statsData.sections.map((s) => {
    const genre = s.key === "genre";
    const shown = genre && !genresShowAll
      ? s.rows.slice(0, GENRE_PREVIEW) : s.rows;
    const rows = shown.map((r) => statRow(s.key, r, genre)).join("");
    const more = genre && !genresShowAll && s.rows.length > GENRE_PREVIEW
      ? `<button class="stat-show-all">Show all ${s.rows.length}</button>` : "";
    const edit = genre
      ? `<button class="stat-edit-tags">${tagEditMode ? "Done" : "Edit tags"}</button>`
      : "";
    return `<section class="stat-block stat-${s.key}">
      <h3>${esc(s.label)}${edit}</h3>
      <table><tbody>${rows}</tbody></table>${more}</section>`;
  }).join("");
  panel.innerHTML = `<details${statsOpen ? " open" : ""}>
    <summary>${statsData.total} items — overview</summary>
    <div id="stats-grid">${blocks}</div></details>`;
  panel.querySelector("details").addEventListener("toggle",
    (ev) => { statsOpen = ev.target.open; });
}

function statRow(key, row, genre) {
  // A zero row renders greyed and unclickable, so the panel doubles as a
  // "this category is clean" confirmation rather than hiding the row.
  const cell = row.count
    ? `<button class="stat-jump" data-section="${esc(key)}"
        data-row="${esc(row.label)}">${row.count}</button>`
    : `<span class="stat-zero">0</span>`;
  const manage = genre && tagEditMode
    ? `<td><input class="genre-rename-input" placeholder="rename to..." size="18">
        <button class="genre-rename" data-tag="${esc(row.label)}">Rename</button>
        <button class="genre-delete" data-tag="${esc(row.label)}">Delete</button></td>`
    : "";
  return `<tr><td>${esc(row.label)}</td>
    <td class="stat-count">${cell}</td>${manage}</tr>`;
}

document.addEventListener("click", async (ev) => {
  const el = ev.target;
  if (el.classList.contains("star")) {
    const id = +el.dataset.id, n = +el.dataset.n;
    const item = items.find(i => i.id === id);
    const rating = item.my_rating === n ? null : n;  // click current rating to clear
    await post(`/api/items/${id}/rating`, {rating});
    item.my_rating = rating;
    render();
    // The table updates from the in-place edit immediately; the panel
    // trails by one round trip. Deliberate: blocking the star's own
    // re-render on the server would be the visible cost, this is not.
    refreshStats();
  } else if (el.classList.contains("edit")) {
    editingId = +el.dataset.id;
    const it = items.find(i => i.id === editingId);
    editingTags = {genre: [...it.genre], authors: [...it.authors],
                   user_tags: [...it.user_tags]};
    editingTags[personField(it)] = [...person(it)];
    render();
  } else if (el.classList.contains("edit-cancel")) {
    editingId = null;
    editingTags = null;
    render();
  } else if (el.classList.contains("chip-x")) {
    const f = chipFilters[el.dataset.field];
    f.chips.splice(+el.dataset.i, 1);
    renderFilterChips();
    render();
  } else if (el.classList.contains("stat-jump")) {
    // Setting .value does not fire the select's input listener, so
    // re-render by hand -- the overview-to-filter jump.
    SECTION_FILTERS[el.dataset.section](el.dataset.row);
    render();
  } else if (el.classList.contains("bundle-jump")) {
    // Jump to the owned row, so "you may own part of this" becomes one
    // click to WHICH part. Sets relevanceSort like the search box's own
    // input listener does, so the jumped-to row ranks first.
    //
    // The row is in Library and the click came from Bundles, so this
    // navigates as well as filters. Setting the hash rather than calling
    // showSection puts the jump in history, so Back returns to the bundle
    // the question was asked about.
    $("#search").value = el.textContent.trim();
    relevanceSort = true;
    location.hash = "#/library";
    render();
  } else if (el.classList.contains("stat-show-all")) {
    genresShowAll = true;
    renderStats();
  } else if (el.classList.contains("stat-edit-tags")) {
    tagEditMode = !tagEditMode;
    renderStats();
  } else if (el.id === "export") {
    // No armOrFire: exporting mutates nothing, so a confirmation click
    // would be pure friction.
    await downloadExport();
  } else if (el.classList.contains("col-check")) {
    toggleColumn(el.dataset.col, el.checked);
  } else if (el.id === "col-all" || el.id === "col-none") {
    exportColumns = new Set(el.id === "col-all" ? EXPORT_COLUMNS : []);
    saveColumnSelection();
    renderColumnPicker();
    renderExportButton();
  } else if (el.classList.contains("filter-mode")) {
    const f = chipFilters[el.dataset.field];
    f.mode = f.mode === "all" ? "any" : "all";
    renderFilterChips();
    render();
  } else if (el.classList.contains("status-chip")) {
    // The chips live in the header, which render() never rebuilds, so
    // toggling the class on the clicked button directly is safe.
    const s = el.dataset.status;
    if (statusFilter.has(s)) statusFilter.delete(s); else statusFilter.add(s);
    el.classList.toggle("on");
    render();
  } else if (el.classList.contains("tag-x")) {
    editingTags[el.dataset.f].splice(+el.dataset.i, 1);
    render();
  } else if (el.classList.contains("edit-save")) {
    const row = el.closest("tr"), id = el.dataset.id;
    const fields = {};
    for (const inp of row.querySelectorAll(".edit-field"))
      fields[inp.dataset.f] = inp.value.trim();
    // user_tags is deliberately held back from /edit: it is not in
    // EDITABLE_FIELDS, and /edit would snapshot the row and mark it
    // hand-edited. Same reason the note uses .edit-comment, not
    // .edit-field -- the selector above must not sweep it up.
    const {user_tags, ...enrichmentTags} = editingTags;
    Object.assign(fields, enrichmentTags);
    const comment = row.querySelector(".edit-comment").value.trim();

    if (shouldPostEnrichmentEdit(items.find(i => i.id === +id), fields)) {
      const resp = await post(`/api/items/${id}/edit`, {fields});
      if (!resp.ok) {
        alert((await resp.json()).error || "Could not save.");
        return;
      }
    }
    await post(`/api/items/${id}/user-tags`, {tags: user_tags});
    await post(`/api/items/${id}/comment`, {comment});
    editingId = null;
    editingTags = null;
    await load();
  } else if (el.classList.contains("revert")) {
    armOrFire(el, async () => {
      await post(`/api/items/${el.dataset.id}/revert`);
      await load();
    });
  } else if (el.classList.contains("redo")) {
    armOrFire(el, async () => {
      await post(`/api/items/${el.dataset.id}/reopen`);
      await load();
    });
  } else if (el.classList.contains("override")) {
    // No armOrFire here: queuing changes nothing until an enrich run, and
    // the badge plus the "Queued for re-enrich" filter make it reversible.
    const row = items.find(i => i.id === Number(el.dataset.id));
    await post(`/api/items/${el.dataset.id}/override`,
               {override: !(row && row.override)});
    await load();
  } else if (el.classList.contains("genre-rename")) {
    const input = el.closest("tr").querySelector(".genre-rename-input");
    const newName = input.value.trim();
    if (!newName || newName === el.dataset.tag) return;
    armOrFire(el, async () => {
      const resp = await post("/api/genres/rename",
                              {old: el.dataset.tag, new: newName});
      if (!resp.ok) alert((await resp.json()).error || "Could not rename.");
      await load();
    });
  } else if (el.classList.contains("genre-delete")) {
    armOrFire(el, async () => {
      const resp = await post("/api/genres/delete", {tag: el.dataset.tag});
      if (!resp.ok) alert((await resp.json()).error || "Could not delete.");
      await load();
    });
  } else if (el.id === "bulk-add") {
    await runBulk(el, "add");
  } else if (el.id === "bulk-remove") {
    await runBulk(el, "remove");
  } else if (el.closest("#catalog th[data-sort]")) {
    const th = el.closest("#catalog th[data-sort]");
    relevanceSort = false;              // an explicit sort beats relevance
    sortAsc = sortKey === th.dataset.sort ? !sortAsc : true;
    sortKey = th.dataset.sort;
    render();
  }
});
// Per-row status dropdowns fire `change`, not `click`, so they get their
// own delegated listener. read_status is a user-owned field: like rating,
// it posts to its own route and never touches /edit or the hand-edit flag.
document.addEventListener("change", async (e) => {
  const el = e.target;
  if (!el.classList || !el.classList.contains("read-status-select")) return;
  const id = +el.dataset.id, status = el.value;
  await post(`/api/items/${id}/read-status`, {status});
  const item = items.find(i => i.id === id);
  if (item) item.read_status = status;
  render();
  refreshStats();   // as with the star click: table now, panel a beat later
});
for (const id of ["#f-type", "#f-flag", "#f-rating"])
  $(id).addEventListener("input", render);
// Typing a query re-asserts relevance ordering; a header click clears it.
$("#search").addEventListener("input", () => { relevanceSort = true; render(); });

// The bulk bar lives outside the table, so the table's innerHTML rebuilds
// leave it alone; only its own input and re-renders refresh it.
$("#bulk-tag").addEventListener("input", renderBulkBar);
Autocomplete.attach(
  $("#bulk-tag"),
  () => vocab("user_tags"),
  (value, viaSuggestion) => {
    if (viaSuggestion) $("#bulk-tag").value = value;
    renderBulkBar();
  },
  () => tagCounts(i => i.user_tags));

// Filter-bar chips live outside the table, so the table's innerHTML
// rebuilds never disturb them; only chip/toggle/input events re-render.
function renderFilterChips() {
  for (const [field, f] of Object.entries(chipFilters)) {
    const wrap = document.querySelector(`.chip-filter[data-field="${field}"]`);
    for (const el of wrap.querySelectorAll(".tag, .filter-mode")) el.remove();
    const input = wrap.querySelector("input");
    input.insertAdjacentHTML("beforebegin", f.chips.map((c, idx) =>
      `<span class="tag">${esc(c)}<button class="tag-x chip-x"
             data-field="${field}" data-i="${idx}"
             title="Remove">&times;</button></span>`).join(""));
    // With 0-1 chips the all/any distinction cannot change the result;
    // for a scalar field (one value per item) "all" is unsatisfiable,
    // so the toggle could only ever empty the table.
    if (f.chips.length >= 2 && !f.scalar)
      input.insertAdjacentHTML("afterend",
        `<button class="filter-mode" data-field="${field}"
                 title="Item must match all chips, or any chip">${f.mode}</button>`);
  }
}

function wireChipFilter(field) {
  const f = chipFilters[field];
  const input = document.querySelector(`.chip-filter[data-field="${field}"] input`);
  if (!f.textOnly) Autocomplete.attach(
    input,
    () => [...new Set(items.flatMap(f.accessor))].sort()
            .filter(v => !f.chips.includes(v)),
    (value, viaSuggestion) => {
      if (viaSuggestion) {
        f.chips.push(value);
        f.text = "";
        input.value = "";
        renderFilterChips();
      } else {
        f.text = value.toLowerCase();
      }
      render();
    },
    () => tagCounts(f.accessor));
  input.addEventListener("input", () => {
    f.text = input.value.trim().toLowerCase();
    render();
  });
}
for (const field of Object.keys(chipFilters)) wireChipFilter(field);

// Title suggestions for the search box: no chips and no counts, since
// titles are one-per-item. Picking one just fills the box, and the
// name filter finds the row. The length guard keeps one stray keystroke
// from opening a list drawn from every title in the catalog.
Autocomplete.attach(
  $("#search"),
  () => $("#search").value.trim().length < 2 ? []
        : [...new Set(items.map(i => i.name))].sort(),
  (value, viaSuggestion) => {
    if (viaSuggestion) $("#search").value = value;
    render();
  });

// Before load(), so the first renderExportButton() already knows whether
// the stored selection leaves anything to download.
loadColumnSelection();
renderColumnPicker();

// Closing on an outside click is the one behaviour <details> does not give
// for free, and without it the panel stays open over the table.
document.addEventListener("click", (ev) => {
  const picker = $("#column-picker");
  if (picker?.open && !picker.contains(ev.target)) picker.open = false;
});
