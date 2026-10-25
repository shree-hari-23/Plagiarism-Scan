"""
Unit tests for Entropy-based Query Generation, Trafilatura Distillation,
and Concurrent Page Fetching (Source Attribution Engine Guide).
"""

import pytest
from app.core.pipeline.phrase_extractor import DistinctivePhraseExtractor
from app.core.pipeline.query_generator import QueryGenerator
from app.core.scraper.distiller import WebDistiller
from app.core.pipeline.page_fetcher import PageFetcher
from app.core.pipeline.schemas import SearchResult


def test_phrase_entropy_calculation():
    """Verify that calculate_phrase_entropy distinguishes content-dense text from stopword spam."""
    extractor = DistinctivePhraseExtractor()

    technical_phrase = ["agentic", "autonomous", "artificial", "intelligence", "workflows", "optimization", "enterprise"]
    stopword_phrase = ["it", "is", "of", "the", "that", "in", "and", "on"]

    tech_score = extractor.calculate_phrase_entropy(technical_phrase)
    stop_score = extractor.calculate_phrase_entropy(stopword_phrase)

    assert tech_score >= 1.0, f"Expected high entropy for technical terminology, got {tech_score}"
    assert stop_score == 0.0, f"Expected zero entropy for stopword sequence, got {stop_score}"


def test_high_entropy_8_word_query_extraction():
    """Verify Section 4.2 sliding window 8-word entropy query extraction."""
    qg = QueryGenerator()
    document = (
        "Agentic AI, or autonomous AI, is a type of artificial intelligence "
        "that runs independently to design, execute, and optimize enterprise workflows "
        "without requiring constant human intervention or manual oversight."
    )

    queries = qg.extract_high_entropy_queries(document, phrase_length=8, max_queries=3)

    assert len(queries) >= 1
    for q in queries:
        assert q.startswith('"') and q.endswith('"'), f"Query {q} must be enclosed in quotes"
        words = q.strip('"').split()
        assert len(words) == 8, f"Query {q} expected 8 words, got {len(words)}"


def test_trafilatura_distillation():
    """Verify that WebDistiller extracts clean prose using Trafilatura."""
    raw_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Guide to Agentic AI Systems</title>
        <meta name="author" content="Dr. Jane Doe">
    </head>
    <body>
        <header>
            <nav><a href="/">Home</a><a href="/about">About Us</a></nav>
        </header>
        <main>
            <article>
                <h1>Understanding Agentic AI in Modern Computing</h1>
                <p>Agentic AI represents a fundamental paradigm shift in enterprise automation. Unlike traditional generative models that require continuous prompting, agentic systems operate with autonomy to plan sub-goals, invoke external APIs, and iteratively refine outputs until objectives are fulfilled.</p>
                <p>These agents combine reinforcement learning with tool use and persistent memory architecture to solve multi-step operational challenges across enterprise environments.</p>
            </article>
        </main>
        <footer>
            <p>Copyright 2026 Enterprise AI Inc. All rights reserved. Privacy policy and terms.</p>
        </footer>
    </body>
    </html>
    """
    distilled = WebDistiller.distill(raw_html, url="https://example.com/agentic-guide")

    assert distilled["title"] == "Guide to Agentic AI Systems" or "Agentic" in distilled["title"]
    assert "Agentic AI represents a fundamental paradigm shift" in distilled["clean_text"]
    assert "Home" not in distilled["clean_text"]
    assert "Privacy policy" not in distilled["clean_text"]
    assert distilled["word_count"] > 30


def test_concurrent_page_fetching(monkeypatch):
    """Verify that fetch_pages_concurrent retrieves candidate pages in parallel."""
    fetcher = PageFetcher()

    candidates = [
        SearchResult(
            url="https://example.com/page1",
            title="Page One",
            snippet="A substantive snippet for page one about machine learning and artificial intelligence algorithms.",
            provider="test",
            search_rank=1
        ),
        SearchResult(
            url="https://example.com/page2",
            title="Page Two",
            snippet="A substantive snippet for page two detailing autonomous agents and automated workflows.",
            provider="test",
            search_rank=2
        )
    ]

    # Mock fetch_page to return a valid CandidatePage for each candidate
    def mock_fetch_page(candidate):
        return fetcher._create_snippet_fallback(candidate, "mock_success")

    monkeypatch.setattr(fetcher, "fetch_page", mock_fetch_page)

    pages = fetcher.fetch_pages_concurrent(candidates, max_workers=2)

    assert len(pages) == 2
    assert {p.url for p in pages} == {"https://example.com/page1", "https://example.com/page2"}
