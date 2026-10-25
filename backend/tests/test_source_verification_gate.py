"""
Unit tests for the Automated Fetch & Verify Gate, Unicode query sanitization,
canonical link extraction, and domain authority prioritization.
"""

import pytest
from app.core.pipeline.page_fetcher import PageFetcher
from app.core.pipeline.schemas import CandidatePage, SearchResult
from app.core.pipeline.text_normalizer import TextNormalizer
from app.core.pipeline.query_generator import QueryGenerator
from app.core.scraper.distiller import WebDistiller
from app.core.pipeline.source_clusterer import SourceClusterer
from app.core.pipeline.schemas import SourceMatch, Confidence, MatchType, SourceCategory


def test_verify_source_url_broken_link_rejected():
    """Broken links (status != 200) must be rejected immediately."""
    page_404 = CandidatePage(
        url="https://example.com/missing-page",
        final_url="https://example.com/missing-page",
        content="This is some content that won't matter because page is 404.",
        http_status=404
    )
    result = PageFetcher.verify_source_url(
        target_text="This is some content",
        candidate_url="https://example.com/missing-page",
        page=page_404
    )
    assert result is False


def test_verify_source_url_direct_containment():
    """Target text directly contained in the page body must pass."""
    page_200 = CandidatePage(
        url="https://example.com/article",
        final_url="https://example.com/article",
        content="Flask is a lightweight WSGI web application framework. It is designed to make getting started quick and easy.",
        http_status=200
    )
    result = PageFetcher.verify_source_url(
        target_text="Flask is a lightweight WSGI web application framework.",
        candidate_url="https://example.com/article",
        page=page_200
    )
    assert result is True


def test_verify_source_url_80_percent_word_containment():
    """If text is not direct verbatim, at least 80% distinct words must match."""
    page_200 = CandidatePage(
        url="https://example.com/article",
        final_url="https://example.com/article",
        content="Agentic AI systems can autonomously plan workflows and execute complex tasks with minimal human guidance.",
        http_status=200
    )
    # 8 of 10 words present (>=80%)
    passing_target = "Agentic AI systems autonomously plan workflows and execute complex operations seamlessly."
    result_pass = PageFetcher.verify_source_url(
        target_text=passing_target,
        candidate_url="https://example.com/article",
        min_match_ratio=0.8,
        page=page_200
    )
    assert result_pass is True

    # Less than 80% distinct words match
    failing_target = "Quantum computing employs superconducting qubits for cryptographic factoring algorithms."
    result_fail = PageFetcher.verify_source_url(
        target_text=failing_target,
        candidate_url="https://example.com/article",
        min_match_ratio=0.8,
        page=page_200
    )
    assert result_fail is False


def test_canonical_tag_extraction():
    """Extract <link rel="canonical"> and resolve relative URLs."""
    html_with_canonical = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Article Mirror</title>
        <link rel="canonical" href="https://authoritative-source.org/docs/main" />
    </head>
    <body>
        <p>This is a republished mirror article with lots of body text to pass threshold.</p>
    </body>
    </html>
    """
    canon = WebDistiller.extract_canonical_url(html_with_canonical, base_url="https://mirror.com/page")
    assert canon == "https://authoritative-source.org/docs/main"

    # Relative canonical URL
    html_relative = """
    <html>
    <head>
        <link rel="canonical" href="/stable/tutorial" />
    </head>
    <body><p>Text</p></body>
    </html>
    """
    canon_rel = WebDistiller.extract_canonical_url(html_relative, base_url="https://docs.python.org/3/tutorial")
    assert canon_rel == "https://docs.python.org/stable/tutorial"


def test_query_sanitizer_unicode_and_length():
    """Unicode smart quotes, en-dashes, and non-breaking spaces must be sanitized to clean ASCII."""
    raw_dirty = "“Welcome to Flask’s documentation – a lightweight WSGI\xa0framework.”"
    sanitized = TextNormalizer.sanitize_query_text(raw_dirty)
    assert "“" not in sanitized
    assert "”" not in sanitized
    assert "’" not in sanitized
    assert "\xa0" not in sanitized
    assert "Flask's" in sanitized or "Flask" in sanitized

    # Length Rule: 6-10 words in quotes
    qgen = QueryGenerator()
    queries = qgen.extract_high_entropy_queries(sanitized, phrase_length=8, max_queries=2)
    assert len(queries) >= 1
    for q in queries:
        words = q.strip('"').split()
        assert 6 <= len(words) <= 10


def test_candidate_looping_on_failed_verification():
    """
    When the top-ranked candidate fails verification (e.g. 404 or unrelated page),
    the verification gate must reject it and evaluate the next candidate.
    """
    target_sentence = "Machine learning algorithms learn patterns from empirical training datasets."

    cand1_404 = CandidatePage(
        url="https://broken-link.com/404",
        final_url="https://broken-link.com/404",
        content="Not found",
        http_status=404
    )

    cand2_live = CandidatePage(
        url="https://authoritative.org/ml-patterns",
        final_url="https://authoritative.org/ml-patterns",
        content="Machine learning algorithms learn patterns from empirical training datasets to make accurate predictions.",
        http_status=200
    )

    candidates = [cand1_404, cand2_live]
    verified_candidate = None

    for c in candidates:
        if PageFetcher.verify_source_url(target_sentence, c.url, page=c):
            verified_candidate = c
            break

    assert verified_candidate is not None
    assert verified_candidate.url == "https://authoritative.org/ml-patterns"
