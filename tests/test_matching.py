from humble_catalog.matching import score, status_for, AUTO, REVIEW

def test_exact_title_scores_high():
    assert score("All Systems Red", None, "All Systems Red", None) > 0.99

def test_unrelated_title_scores_low():
    assert score("All Systems Red", None, "Pride and Prejudice", None) < REVIEW

def test_author_agreement_raises_score():
    without = score("Dune", None, "Dune", None)
    withauth = score("Dune", ["Frank Herbert"], "Dune", ["Frank Herbert"])
    assert withauth >= without - 0.01 and withauth > 0.95

def test_status_bands():
    assert status_for(0.9) == "matched"
    assert status_for(0.7) == "low_confidence"
    assert status_for(0.3) == "unmatched"
