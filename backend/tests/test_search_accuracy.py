"""
PlagiaScan Pipeline — Search and Retrieval Accuracy Unit Tests

Tests search result relevance gating, query generation quoting,
title overlap computation, and candidate filtering.
"""

from app.core.pipeline.search_providers import check_result_relevance
from app.core.pipeline.query_generator import QueryGenerator
from app.core.pipeline.url_manager import URLManager
from app.core.pipeline.schemas import DocumentSentence, SearchResult, SearchQuery, SearchStrategy


def test_relevance_gate_rejects_unrelated_results():
    """Verify that check_result_relevance rejects spurious SERP results."""
    # Pega query
    pega_q = '"Agentic AI, or autonomous AI, is a type of artificial intelligence"'
    
    # Unrelated pages should be rejected
    assert not check_result_relevance(
        title="Learn to Type | Typing.com",
        snippet="Typing.com is a one-stop shop for students to learn to type!",
        query_text=pega_q
    )
    assert not check_result_relevance(
        title="API — Flask Documentation (3.1.x)",
        snippet="Flask is a lightweight WSGI web application framework in Python...",
        query_text=pega_q
    )
    assert not check_result_relevance(
        title="Gmail - Email from Google",
        snippet="Gmail is email that's intuitive, efficient, and useful. 15 GB of storage...",
        query_text=pega_q
    )
    
    # Related page must be accepted
    assert check_result_relevance(
        title="What is agentic AI? A complete guide | Pega",
        snippet="Agentic AI, or autonomous AI, is a type of artificial intelligence that runs independently to design, execute, and optimize workflows...",
        query_text=pega_q
    )


def test_relevance_gate_on_ml_query():
    """Verify that general ML queries reject generic mechanical dictionary entries."""
    ml_q = "Machine learning is a subset of artificial intelligence"
    
    # Unrelated mechanical definition should be rejected
    assert not check_result_relevance(
        title="Machine - Wikipedia",
        snippet="A machine is a thermodynamic system that uses power to apply forces...",
        query_text=ml_q
    )
    
    # Related ML articles must be accepted
    assert check_result_relevance(
        title="AI vs. Machine Learning: How Do They Differ? | Google Cloud",
        snippet="Learn the differences between artificial intelligence and machine learning and how they work together...",
        query_text=ml_q
    )


def test_query_generator_always_quotes_phrases():
    """Verify that QueryGenerator quotes multi-word phrases to prevent search engine bag-of-words degradation."""
    qg = QueryGenerator()
    sent = DocumentSentence(
        sentence_id="s_test",
        text="Agentic AI, or autonomous AI, is a type of artificial intelligence that runs independently to design, execute, and optimize workflows without requiring human intervention.",
        word_count=23,
        char_count=155,
        position_index=0,
        is_clause=False
    )
    queries = qg.generate_queries_for_sentence(sent, sentence_idx=1)
    
    assert len(queries) >= 2
    for q in queries:
        if q.strategy in (SearchStrategy.EXACT_PHRASE, SearchStrategy.PARTIAL_PHRASE, SearchStrategy.NGRAM_FRAGMENTS):
            words = q.text.split()
            if len(words) >= 3:
                # Must be quoted or contain quotes
                assert '"' in q.text, f"Query '{q.text}' with strategy {q.strategy} should be quoted to prevent keyword degradation"


def test_url_manager_title_overlap():
    """Verify token-level title overlap computation."""
    probe = "Agentic AI autonomous workflows without human intervention"
    
    matching_title = "What is Agentic AI? Autonomous Workflows Guide | Pega"
    unrelated_title = "Flask Documentation API Reference 3.1.x"
    
    match_score = URLManager.compute_title_overlap(matching_title, probe)
    unrelated_score = URLManager.compute_title_overlap(unrelated_title, probe)
    
    assert match_score >= 0.40, f"Expected >= 0.40 title overlap, got {match_score}"
    assert unrelated_score == 0.0, f"Expected 0.0 title overlap, got {unrelated_score}"


def test_url_manager_hard_filters_garbage():
    """Verify that select_balanced_candidates hard-filters uncorroborated, low-rank zero-overlap hits."""
    queries = [
        SearchQuery(
            query_id="q1",
            text='"Agentic AI autonomous AI"',
            strategy=SearchStrategy.EXACT_PHRASE,
            source_sentence_id="s1",
            source_phrase="Agentic AI autonomous AI"
        )
    ]
    
    results = [
        SearchResult(
            url="https://www.pega.com/agentic-ai",
            title="What is agentic AI? | Pega",
            snippet="Agentic AI, or autonomous AI, is a type of artificial intelligence that runs independently...",
            provider="ddg_lite",
            search_rank=1,
            discovered_by=["q1"],
            source_sentence_id="s1"
        ),
        # Garbage result: rank > 2, probe_votes = 1, 0 snippet overlap, 0 title overlap
        SearchResult(
            url="https://www.typing.com",
            title="Learn to Type | Typing.com",
            snippet="Typing.com is a one-stop shop for students to learn to type!",
            provider="ddg_lite",
            search_rank=4,
            discovered_by=["q1"],
            source_sentence_id="s1"
        )
    ]
    
    selected = URLManager.select_balanced_candidates(results, max_urls=10, queries=queries)
    urls = [r.url for r in selected]
    
    assert "https://www.pega.com/agentic-ai" in urls
    assert "https://www.typing.com" not in urls, "Typing.com should have been hard-filtered as a zero-overlap false positive"
