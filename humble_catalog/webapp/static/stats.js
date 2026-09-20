// The statistics panel's counting, in the browser.
//
// This is a second implementation of stats.py's counts, which is a drift
// risk the server-side arrangement was chosen to avoid. What holds the
// two together now is a test rather than an arrangement: one fixture is
// counted by both and asserted equal field for field (see
// test_the_browser_counts_agree_with_stats_py). The same invariant the
// probe battery pins for /api/stats, moved to the pair that can disagree.
//
// The counting had to move because the panel describes the rows the
// table is showing, and the browser is the only place that knows which
// rows those are: the filters never reach the server, and /api/stats
// documents that nothing about the library may travel in a query string.

// Gaps are the one vocabulary the viewer did not already hold -- it keeps
// each gap's FILTER flag, not the column the gap is in. Order matches
// stats.py's GAPS.
const GAP_FIELDS = {"Unrated": "my_rating", "No cover": "cover_path",
                    "No source URL": "source_url"};

// Count `field` against a label -> value vocabulary. Those vocabularies
// live in catalog.js, already in stats.py's order because the
// overview-to-filter jump needs them, so the viewer keeps one list and
// not two. Object key order is insertion order for string keys, which is
// what makes them usable as ordered vocabularies.
//
// A value outside the vocabulary is counted nowhere rather than
// inventing a row, so a section need not sum to the total; `dflt` stands
// in for a missing key, which is how read_status's NOT NULL DEFAULT is
// honoured for a partial payload. Both match stats.py's _tally.
function statTally(items, field, labelsToValues, dflt) {
  const counts = new Map(Object.values(labelsToValues).map((v) => [v, 0]));
  for (const item of items) {
    const value = item[field] || dflt;
    if (counts.has(value)) counts.set(value, counts.get(value) + 1);
  }
  return Object.entries(labelsToValues)
    .map(([label, value]) => ({label, count: counts.get(value)}));
}

// 1..5 only: unrated is a gap, and a row in both places would break the
// one-number-one-place rule the panel exists to restore.
const statsByRating = (items) =>
  [1, 2, 3, 4, 5].map((n) => ({label: `★${n}`,
    count: items.filter((i) => i.my_rating === n).length}));

const statsByGap = (items) =>
  Object.entries(GAP_FIELDS).map(([label, field]) =>
    ({label, count: items.filter((i) => !i[field]).length}));

// The one section ordered by its data: biggest first, ties broken
// alphabetically so the order is total and stable. Comparing with < is
// by UTF-16 code unit, which agrees with Python's code-point ordering
// for everything below the astral planes.
function statsByGenre(items) {
  const counts = new Map();
  for (const item of items)
    for (const tag of item.genre || [])
      counts.set(tag, (counts.get(tag) || 0) + 1);
  return [...counts]
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .map(([label, count]) => ({label, count}));
}

// Order and labels mirror stats.py's SECTIONS; the keys are the contract
// SECTION_FILTERS reads back when a row is clicked.
const STATS_SECTIONS = [
  ["type", "By type", (i) => statTally(i, "type", TYPE_VALUES)],
  ["rating", "Ratings", statsByRating],
  ["status", "Reading status",
   (i) => statTally(i, "read_status", STATUS_VALUES, "unread")],
  ["enrichment", "Enrichment", (i) => statTally(i, "status", ENRICHMENT_VALUES)],
  ["gaps", "Gaps", statsByGap],
  ["genre", "Genres", statsByGenre],
];

// The shape /api/stats returned, so renderStats and the panel's tests are
// untouched by where the numbers come from.
function statsReport(items) {
  return {total: items.length,
          sections: STATS_SECTIONS.map(([key, label, rows]) =>
            ({key, label, rows: rows(items)}))};
}
