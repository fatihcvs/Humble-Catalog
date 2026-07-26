from rapidfuzz import fuzz

AUTO = 0.85
REVIEW = 0.60

def score(clean_title, authors, cand_title, cand_authors):
    if not cand_title:
        return 0.0
    title_score = fuzz.token_set_ratio(clean_title.lower(), cand_title.lower()) / 100
    if authors and cand_authors:
        author_score = max(
            fuzz.token_set_ratio(a.lower(), b.lower())
            for a in authors for b in cand_authors) / 100
        return 0.75 * title_score + 0.25 * author_score
    return title_score

def status_for(conf):
    if conf >= AUTO:
        return "matched"
    if conf >= REVIEW:
        return "low_confidence"
    return "unmatched"
