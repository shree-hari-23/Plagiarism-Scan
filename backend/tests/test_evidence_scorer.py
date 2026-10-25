import pytest
from app.core.pipeline.evidence_scorer import EvidenceScorer
from app.core.pipeline.schemas import (
    NgramMatch,
    Confidence,
    MatchType,
    SourceCategory
)


def test_categorize_source():
    assert EvidenceScorer.categorize_source("https://flask.palletsprojects.com/en/stable/") == SourceCategory.OFFICIAL_DOCUMENTATION
    assert EvidenceScorer.categorize_source("https://en.wikipedia.org/wiki/Flask_(web_framework)") == SourceCategory.ENCYCLOPEDIA
    assert EvidenceScorer.categorize_source("https://github.com/pallets/flask") == SourceCategory.CODE_REPOSITORY
    assert EvidenceScorer.categorize_source("https://cs.stanford.edu/people/") == SourceCategory.UNIVERSITY_WEBSITE


def test_authority_score_docs_over_github():
    flask_docs = "https://flask.palletsprojects.com/en/stable/"
    flask_github = "https://github.com/pallets/flask"

    score_docs = EvidenceScorer.compute_authority_score(flask_docs)
    score_github = EvidenceScorer.compute_authority_score(flask_github)

    # Official documentation MUST have significantly higher authority score than GitHub mirror
    assert score_docs > score_github
    assert score_docs - score_github >= 30.0


def test_high_confidence_for_25_word_match():
    scorer = EvidenceScorer()
    ng_match = NgramMatch(
        verified=True,
        matched_phrase="This is an exact verbatim phrase that extends for at least twenty-five words across the webpage content.",
        match_length=25,
        longest_exact_match_words=25,
        coverage=1.0,
        match_type="exact_phrase",
        ngram_hits=10
    )

    evidence, confidence, match_type, sim, reasons = scorer.evaluate_match(
        ngram_match=ng_match,
        fuzzy_match=None,
        semantic_match=None,
        matched_sentences_count=1,
        search_rank=1,
        discovered_by_count=2,
        url="https://example.com/docs/guide"
    )

    assert confidence == Confidence.HIGH
    assert match_type == MatchType.EXACT
    assert evidence.composite_score >= 60.0
    assert any("25 consecutive matching words" in r for r in reasons)
