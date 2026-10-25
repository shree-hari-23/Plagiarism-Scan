"""
Unit and regression tests for Seed-and-Extend Alignment Engine (v2.0)
and Snippet Pre-Screening.
"""

import pytest
from app.core.pipeline.seed_extend import (
    DocumentKgramIndex,
    SeedAndExtendAligner,
    AlignedSpan
)
from app.core.pipeline.text_normalizer import TextNormalizer
from app.core.pipeline.url_manager import URLManager
from app.core.pipeline.schemas import (
    PipelineOptions,
    SearchResult,
    SearchQueryRecord,
    CandidatePage,
    VerificationStatus,
    WebDetectionResult
)
from app.core.pipeline.orchestrator import WebSourceDetectionPipeline
from app.core.pipeline.search_providers import SearchProvider


# ---------------------------------------------------------------------------
# 1. DocumentKgramIndex Tests
# ---------------------------------------------------------------------------

def test_document_kgram_index_basic():
    doc = "Agentic AI systems operate independently to solve complex enterprise workflows."
    idx = DocumentKgramIndex(doc, k=6)

    assert len(idx.doc_tokens) > 6
    assert len(idx.index) > 0

    # Lookup first 6-gram
    first_gram = tuple(idx.doc_tokens[:6])
    positions = idx.lookup(first_gram)
    assert 0 in positions


def test_document_kgram_index_filters_stopword_spam():
    doc = "it is of the that in and on to for with"
    idx = DocumentKgramIndex(doc, k=5)
    # Stopword-only grams should be excluded
    assert len(idx.index) == 0


# ---------------------------------------------------------------------------
# 2. SeedAndExtendAligner: Verbatim Matching
# ---------------------------------------------------------------------------

def test_aligner_verbatim_match():
    doc = (
        "Agentic AI or autonomous AI is a type of artificial intelligence that runs independently "
        "to design execute and optimize workflows across enterprise environments."
    )
    page = (
        "Welcome to the portal. What is Agentic AI? Agentic AI or autonomous AI is a type of artificial "
        "intelligence that runs independently to design execute and optimize workflows across enterprise "
        "environments. Learn more today."
    )

    doc_norm = TextNormalizer.normalize(doc).split()
    page_norm = TextNormalizer.normalize(page).split()

    idx = DocumentKgramIndex(doc, k=6)
    aligner = SeedAndExtendAligner(k=6, max_gap=8, theta=0.70)

    spans = aligner.align(doc_norm, idx, page_norm)
    assert len(spans) >= 1

    best = max(spans, key=lambda s: s.matched_tokens)
    assert best.identity >= 0.95
    assert best.longest_exact_run >= 15
    assert best.matched_tokens >= 18
    assert "agentic ai or autonomous ai" in best.doc_excerpt


# ---------------------------------------------------------------------------
# 3. SeedAndExtendAligner: Edited / Obfuscated Copying
# ---------------------------------------------------------------------------

def test_aligner_catches_obfuscated_copying():
    """
    Simulates a plagiarized passage where 1 word every 7-9 words is altered
    (synonym swaps, small deletions).
    Fixed N=25 exact N-gram matcher FAILS because no 25 consecutive words match.
    Seed-and-extend MUST succeed by chaining k=6 seeds along diagonal bands
    and extending with edit tolerance (theta >= 0.70).
    """
    # Original source
    source_passage = (
        "machine learning models require substantial quantities of annotated training data "
        "to achieve high accuracy across diverse real world production tasks and operations "
        "in modern distributed cloud infrastructure."
    )

    # Obfuscated copy with modified words every 8 tokens:
    # "machine learning models require substantial quantities of annotated training data"
    # -> "machine learning algorithms require substantial quantities of labeled training data"
    # "to achieve high accuracy across diverse real world production tasks"
    # -> "to achieve exceptional accuracy across varied real world production tasks"
    doc_passage = (
        "machine learning algorithms require substantial quantities of labeled training data "
        "to achieve exceptional accuracy across varied real world production tasks and operations "
        "in modern distributed computing infrastructure."
    )

    source_tokens = TextNormalizer.normalize(source_passage).split()
    doc_tokens = TextNormalizer.normalize(doc_passage).split()

    idx = DocumentKgramIndex(doc_passage, k=5)
    aligner = SeedAndExtendAligner(k=5, max_gap=8, theta=0.70)

    spans = aligner.align(doc_tokens, idx, source_tokens)
    assert len(spans) >= 1

    best = max(spans, key=lambda s: s.matched_tokens)

    # Verify that the entire multi-sentence span was recovered
    assert best.aligned_tokens >= 20
    assert best.matched_tokens >= 15
    assert best.identity >= 0.75, f"Expected identity >= 0.75, got {best.identity}"


# ---------------------------------------------------------------------------
# 4. SeedAndExtendAligner: Negative Cases
# ---------------------------------------------------------------------------

def test_aligner_rejects_unrelated_texts():
    agentic_doc = (
        "Agentic AI, or autonomous AI, is a type of artificial intelligence that runs independently "
        "to design, execute, and optimize workflows."
    )
    flask_page = (
        "Flask is a lightweight WSGI web application framework. It is designed to make getting started "
        "quick and easy, with the ability to scale up to complex applications."
    )

    doc_tokens = TextNormalizer.normalize(agentic_doc).split()
    page_tokens = TextNormalizer.normalize(flask_page).split()

    idx = DocumentKgramIndex(agentic_doc, k=6)
    aligner = SeedAndExtendAligner(k=6, max_gap=8, theta=0.70)

    spans = aligner.align(doc_tokens, idx, page_tokens)
    # Zero valid aligned spans should be emitted
    assert len(spans) == 0


# ---------------------------------------------------------------------------
# 5. Snippet Pre-Screening
# ---------------------------------------------------------------------------

def test_url_manager_snippet_overlap():
    probe = "artificial intelligence that runs independently to design execute and optimize workflows"
    matching_snippet = (
        "...agentic ai is a type of artificial intelligence that runs independently to design, execute, "
        "and optimize enterprise workflows..."
    )
    unrelated_snippet = (
        "...Flask's documentation on Request and Response objects in WSGI compliant Python servers..."
    )

    overlap_match = URLManager.compute_snippet_overlap(matching_snippet, probe)
    overlap_unrelated = URLManager.compute_snippet_overlap(unrelated_snippet, probe)

    assert overlap_match >= 0.70, f"Expected high snippet overlap, got {overlap_match}"
    assert overlap_unrelated <= 0.10, f"Expected low snippet overlap, got {overlap_unrelated}"


# ---------------------------------------------------------------------------
# 6. Pipeline Integration: Modified/Paraphrased Passage Verified Match
# ---------------------------------------------------------------------------

class MockEditedCopySearchProvider(SearchProvider):
    @property
    def name(self) -> str:
        return "mock_edited_copy_provider"

    def search(self, query, limit=5):
        results = [
            SearchResult(
                url="https://example.com/source-article",
                title="Deep Learning Architecture Guide",
                snippet="deep neural networks utilize backpropagation algorithms to optimize weight parameters across distributed clusters",
                provider=self.name,
                search_rank=1,
                discovered_by=[query.query_id],
                source_sentence_id=query.source_sentence_id
            )
        ]
        rec = SearchQueryRecord(query=query.text, provider=self.name, result_count=1, latency_ms=5)
        return results, rec


def test_pipeline_detects_edited_copy_with_seed_and_extend(monkeypatch):
    source_content = (
        "deep neural networks utilize backpropagation algorithms to optimize weight parameters "
        "across distributed clusters of graphics processing units during training cycles."
    )

    # Document has slight word modifications
    doc_text = (
        "Deep neural models employ backpropagation techniques to optimize weight parameters "
        "across distributed clusters of graphics processing chips during training cycles."
    )

    options = PipelineOptions(
        search_depth="quick",
        enable_semantic_matching=True,
        enable_fuzzy_matching=True,
        max_urls_to_fetch=5
    )
    pipeline = WebSourceDetectionPipeline(options=options)
    pipeline.search_chain.providers = [MockEditedCopySearchProvider()]

    def mock_fetch(cand):
        return CandidatePage(
            url="https://example.com/source-article",
            final_url="https://example.com/source-article",
            title="Deep Learning Architecture Guide",
            content=source_content,
            normalized_content=source_content.lower(),
            word_count=len(source_content.split()),
            domain="example.com",
            fetch_source="full_page"
        )

    monkeypatch.setattr(pipeline.fetcher, "fetch_page", mock_fetch)

    result: WebDetectionResult = pipeline.run(doc_text)

    assert result.sources_found >= 1
    assert result.matches[0].verified is True
    assert result.matches[0].verification_status == VerificationStatus.VERIFIED_WEB_MATCH
    assert result.matches[0].identity >= 0.75
