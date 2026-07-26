// Fuzzy matching for the viewer's search box.
//
// Fuzzy.score(query, text) -> {score: 0..1, spans: [[start, end], ...]}
//   spans are half-open ranges into the ORIGINAL text, so the renderer
//   can highlight without re-deriving the match. score 0 means no match.
//
// Three tiers in non-overlapping score bands (exact substring, token
// set, acronym); the best one wins. Bands rather than a blended metric
// so ordering is explainable and any exact substring outranks any fuzzy
// match -- searches that worked before fuzzy matching still rank first.
//
// Pure and DOM-free, so it can be tested as a table of cases.
const Fuzzy = (() => {
  // Straight, curly, modifier-letter and backtick apostrophes.
  const APOSTROPHES = "'’‘ʼ`";

  // Normalize for matching while remembering where each character came
  // from. Hand-rolled rather than a chain of .replace() calls precisely
  // because of that map: collapsing punctuation and eliding apostrophes
  // change the string's length, so spans computed on a separately
  // normalized string land at the wrong offsets.
  //
  // Apostrophes are elided rather than spaced, so "Innkeeper's" folds to
  // "innkeepers" and matches the apostrophe-free spelling people type.
  // Everything else that is not a letter or digit becomes a space.
  function fold(text) {
    const out = [], map = [];
    let atSpace = true;                  // true at the start: no leading space
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (APOSTROPHES.includes(ch)) continue;
      const base = ch.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
      for (const c of base) {
        if (/[\p{L}\p{N}]/u.test(c)) {
          out.push(c); map.push(i); atSpace = false;
        } else if (!atSpace) {
          out.push(" "); map.push(i); atSpace = true;
        }
      }
    }
    while (out.length && out[out.length - 1] === " ") { out.pop(); map.pop(); }
    return {text: out.join(""), map};
  }

  // Whitespace-separated tokens with half-open ranges into `folded`.
  function tokenize(folded) {
    const tokens = [];
    let start = -1;
    for (let i = 0; i <= folded.length; i++) {
      const sep = i === folded.length || folded[i] === " ";
      if (!sep && start < 0) start = i;
      else if (sep && start >= 0) {
        tokens.push({text: folded.slice(start, i), start, end: i});
        start = -1;
      }
    }
    return tokens;
  }

  const CUTOFF = 0.40;

  // A folded range -> a range in the original string. The map holds the
  // origin of each folded character, so the end is the origin of the
  // last character, plus one.
  const toOriginal = (map, start, end) => [map[start], map[end - 1] + 1];

  // Levenshtein distance <= k, bounded. The length guard is what makes
  // this affordable: scoring runs on every keystroke across the whole
  // catalog, and a length difference alone proves the distance exceeds
  // k, so the matrix is never built for most token pairs.
  function within(a, b, k) {
    if (Math.abs(a.length - b.length) > k) return false;
    let prev = Array.from({length: b.length + 1}, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      const cur = [i];
      let best = i;
      for (let j = 1; j <= b.length; j++) {
        cur[j] = a[i - 1] === b[j - 1]
          ? prev[j - 1]
          : 1 + Math.min(prev[j - 1], prev[j], cur[j - 1]);
        best = Math.min(best, cur[j]);
      }
      if (best > k) return false;          // whole row already too far
      prev = cur;
    }
    return prev[b.length] <= k;
  }

  // How well one query token matches one text token. A one-character
  // difference in a short word is usually a different word (cat/cut); in
  // a long word it is a slip, so the edit budget grows with length.
  //
  // "Prefix" holds in either direction, so a half-typed word and a
  // slightly over-typed one land in the same tier -- but only when the
  // shorter side is a real word. Without that floor a one-letter title
  // token ("A") prefix-matches every query beginning with that letter,
  // which scored an unrelated query 0.81 and would have made the whole
  // tier meaningless.
  const PREFIX_FLOOR = 3;

  function tokenScore(q, t) {
    if (q === t) return 1;
    if (Math.min(q.length, t.length) >= PREFIX_FLOOR
        && (t.startsWith(q) || q.startsWith(t))) return 0.9;
    if (t.includes(q)) return 0.75;
    if (within(q, t, q.length <= 5 ? 1 : 2)) return 0.6;
    return 0;
  }

  // T1, band 0.90-1.00: the query appears verbatim. A whole-title match
  // approaches 1.0, a short fragment sits near 0.90.
  function exactTier(q, t) {
    const at = t.text.indexOf(q.text);
    if (at < 0) return null;
    return {
      score: 0.90 + 0.10 * (q.text.length / t.text.length),
      spans: [toOriginal(t.map, at, at + q.text.length)],
    };
  }

  // T2, band 0.69-0.85: every query token finds a text token, in any
  // order. Assignment is greedy best-first and each text token is used
  // once. If any query token goes unmatched the tier scores nothing --
  // AND semantics, like every other filter in the viewer.
  function tokenTier(q, t) {
    const qs = tokenize(q.text), ts = tokenize(t.text);
    if (!qs.length || !ts.length) return null;
    const pairs = [];
    for (let a = 0; a < qs.length; a++)
      for (let b = 0; b < ts.length; b++) {
        const s = tokenScore(qs[a].text, ts[b].text);
        if (s) pairs.push({a, b, s});
      }
    pairs.sort((x, y) => y.s - x.s);
    const usedQ = new Set(), usedT = new Set(), spans = [];
    let total = 0;
    for (const p of pairs) {
      if (usedQ.has(p.a) || usedT.has(p.b)) continue;
      usedQ.add(p.a); usedT.add(p.b);
      total += p.s;
      spans.push(toOriginal(t.map, ts[p.b].start, ts[p.b].end));
    }
    if (usedQ.size !== qs.length) return null;
    spans.sort((x, y) => x[0] - y[0]);
    return {score: 0.45 + 0.40 * (total / qs.length), spans};
  }

  // T3, band 0.40-0.50: initials. Every query character must match at a
  // WORD START, in order -- a strict rule on purpose. Allowing matches
  // mid-word turns this tier into "these letters appear somewhere",
  // which matches most of a catalog and is how fuzzy search earns its
  // bad reputation.
  function acronymTier(q, t) {
    const chars = q.text.replace(/ /g, "");
    if (chars.length < 2) return null;
    const hits = [];
    let qi = 0;
    for (let i = 0; i < t.text.length && qi < chars.length; i++) {
      const isStart = i === 0 || t.text[i - 1] === " ";
      if (isStart && t.text[i] === chars[qi]) { hits.push(i); qi++; }
    }
    if (qi !== chars.length) return null;
    const words = tokenize(t.text).length;
    return {
      score: 0.40 + 0.10 * Math.min(1, chars.length / words),
      spans: hits.map((i) => toOriginal(t.map, i, i + 1)),
    };
  }

  // Best tier wins. Below the cutoff is not a match at all: the spans of
  // a near-miss would otherwise highlight noise.
  //
  // `folded` is an optional pre-computed fold(text), so a caller scoring
  // the same text on every keystroke can cache it. Omitting it is always
  // correct, just slower.
  function score(query, text, folded) {
    const q = fold(query), t = folded || fold(text);
    if (!q.text || !t.text) return {score: 0, spans: []};
    let best = {score: 0, spans: []};
    const take = (candidate) => {
      if (candidate && candidate.score > best.score) best = candidate;
    };
    take(exactTier(q, t));
    // Two characters can be a real substring, but as a token or an
    // acronym they match a large share of any catalog.
    if (q.text.replace(/ /g, "").length >= 3) {
      take(tokenTier(q, t));
      take(acronymTier(q, t));
    }
    if (best.score < CUTOFF) return {score: 0, spans: []};
    // Rounded so the bands have exact edges: 0.45 + 0.40 * 1 lands on
    // 0.8500000000000001 in binary floating point, which reads as
    // "outside the token band" to anything comparing against 0.85.
    return {score: Math.round(best.score * 1000) / 1000, spans: best.spans};
  }

  return {fold, tokenize, score};
})();
