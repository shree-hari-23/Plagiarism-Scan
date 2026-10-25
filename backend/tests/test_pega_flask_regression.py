"""
Regression test suite for PlagiaScan Web Source Detection Critical Bug:
Verifies that:
1. "Agentic AI..." sentence correctly matches Pega and rejects Flask (NO_MATCH).
2. Flask is NEVER selected as the source for the Agentic AI sentence.
3. "Flask is a lightweight WSGI..." sentence correctly matches Flask (VERIFIED_WEB_MATCH).
4. Unrelated candidates with non-zero semantic similarity but zero/insufficient lexical
   and entity overlap are strictly rejected as NO_MATCH or downgraded to POSSIBLE_RELATED_SOURCE.
"""

import pytest
from app.core.pipeline.schemas import (
    PipelineOptions,
    WebDetectionResult,
    SearchResult,
    SearchQueryRecord,
    CandidatePage,
    VerificationStatus
)
from app.core.pipeline.orchestrator import WebSourceDetectionPipeline
from app.core.pipeline.search_providers import SearchProvider
from app.core.pipeline.entity_verifier import EntityVerifier


PEGA_URL = "https://www.pega.com/agentic-ai"
PEGA_TITLE = "Pega — What is Agentic AI?"
PEGA_CONTENT = (
    "What is Agentic AI? Agentic AI, or autonomous AI, is a type of artificial intelligence "
    "that runs independently to design, execute, and optimize workflows. "
    "Unlike traditional generative AI that requires step-by-step human prompts, "
    "agentic systems operate with goal-driven agency across enterprise systems."
)

FLASK_URL = "https://flask.palletsprojects.com/en/stable/"
FLASK_TITLE = "Welcome to Flask — Flask Documentation (3.1.x)"
FLASK_CONTENT = (
    "Welcome to Flask. Flask is a lightweight WSGI web application framework. "
    "It is designed to make getting started quick and easy, with the ability to scale up to complex applications. "
    "It began as a simple wrapper around Werkzeug and Jinja and has become one of the most popular Python web application frameworks."
)


class MockMultiCandidateSearchProvider(SearchProvider):
    """
    Search provider that returns BOTH Pega and Flask for any search query,
    simulating the scenario where search results discover multiple URLs.
    """
    @property
    def name(self) -> str:
        return "mock_multi_provider"

    def search(self, query, limit=5):
        # Notice Flask is deliberately placed first to test that search position is NOT proof!
        results = [
            SearchResult(
                url=FLASK_URL,
                title=FLASK_TITLE,
                snippet=FLASK_CONTENT[:200],
                provider=self.name,
                search_rank=1,
                discovered_by=[query.query_id],
                source_sentence_id=query.source_sentence_id
            ),
            SearchResult(
                url=PEGA_URL,
                title=PEGA_TITLE,
                snippet=PEGA_CONTENT[:200],
                provider=self.name,
                search_rank=2,
                discovered_by=[query.query_id],
                source_sentence_id=query.source_sentence_id
            ),
        ]
        rec = SearchQueryRecord(query=query.text, provider=self.name, result_count=len(results), latency_ms=5)
        return results, rec


def test_entity_verifier_distinguishes_agentic_ai_and_flask():
    agentic_text = (
        "Agentic AI, or autonomous AI, is a type of artificial intelligence that runs independently to design, execute, and optimize workflows."
    )

    # Pega overlap should be high
    pega_overlap = EntityVerifier.compute_overlap(agentic_text, PEGA_CONTENT, candidate_title=PEGA_TITLE)
    assert pega_overlap >= 0.70, f"Expected high entity overlap for Pega, got {pega_overlap}"

    # Flask overlap should be very low / near zero
    flask_overlap = EntityVerifier.compute_overlap(agentic_text, FLASK_CONTENT, candidate_title=FLASK_TITLE)
    assert flask_overlap < 0.20, f"Expected low entity overlap for Flask, got {flask_overlap}"


def test_pega_vs_flask_regression_candidate_isolation(monkeypatch):
    """
    REGRESSION TEST:
    Input:
      'Agentic AI, or autonomous AI, is a type of artificial intelligence that runs independently to design, execute, and optimize workflows.'
    Candidate 1: Pega (https://www.pega.com/agentic-ai)
    Candidate 2: Flask (https://flask.palletsprojects.com/)
    Expected:
      Pega: VERIFIED_WEB_MATCH
      Flask: NO_MATCH
    Failure condition:
      The test must fail if Flask is selected as the source.
    """
    doc_text = (
        "Agentic AI, or autonomous AI, is a type of artificial intelligence that runs independently to design, execute, and optimize workflows."
    )

    options = PipelineOptions(
        search_depth="quick",
        enable_semantic_matching=True,
        enable_fuzzy_matching=True,
        max_urls_to_fetch=5
    )
    pipeline = WebSourceDetectionPipeline(options=options)
    pipeline.search_chain.providers = [MockMultiCandidateSearchProvider()]

    # Mock page fetcher so it returns pre-canned content without network requests
    def mock_fetch_page(cand):
        url = cand.url
        if "pega.com" in url:
            return CandidatePage(
                url=PEGA_URL,
                final_url=PEGA_URL,
                title=PEGA_TITLE,
                content=PEGA_CONTENT,
                normalized_content=PEGA_CONTENT.lower(),
                word_count=len(PEGA_CONTENT.split()),
                domain="pega.com",
                fetch_source="full_page"
            )
        elif "palletsprojects.com" in url:
            return CandidatePage(
                url=FLASK_URL,
                final_url=FLASK_URL,
                title=FLASK_TITLE,
                content=FLASK_CONTENT,
                normalized_content=FLASK_CONTENT.lower(),
                word_count=len(FLASK_CONTENT.split()),
                domain="palletsprojects.com",
                fetch_source="full_page"
            )
        return None

    monkeypatch.setattr(pipeline.fetcher, "fetch_page", mock_fetch_page)

    result: WebDetectionResult = pipeline.run(doc_text)

    assert result.total_sentences >= 1
    assert result.sources_found >= 1

    # Check sentence audit
    assert len(result.sentence_audits) >= 1
    audit = result.sentence_audits[0]

    # Find candidates in audit
    candidates_by_url = {c.url: c for c in audit.candidates}

    assert PEGA_URL in candidates_by_url, "Pega must be present among evaluated candidates"
    assert FLASK_URL in candidates_by_url, "Flask must be present among evaluated candidates"

    pega_audit = candidates_by_url[PEGA_URL]
    flask_audit = candidates_by_url[FLASK_URL]

    # Expected verification statuses
    assert pega_audit.status == VerificationStatus.VERIFIED_WEB_MATCH.value, (
        f"Pega expected to be VERIFIED_WEB_MATCH, got {pega_audit.status}"
    )
    assert flask_audit.status == VerificationStatus.NO_MATCH.value, (
        f"Flask expected to be NO_MATCH, got {flask_audit.status}"
    )

    # CRITICAL: Selected source must be Pega, NEVER Flask!
    assert audit.selected_source == PEGA_URL, (
        f"CRITICAL BUG: Flask was selected instead of Pega! Selected: {audit.selected_source}"
    )
    assert audit.verification_status == VerificationStatus.VERIFIED_WEB_MATCH.value

    # Matches check
    legacy = result.to_legacy_matches()
    assert len(legacy) >= 1
    selected_urls = [m["source_url"] for m in legacy]

    assert PEGA_URL in selected_urls, "Pega must be in attributed matches"
    assert FLASK_URL not in selected_urls, "Flask must NEVER be in attributed matches for Agentic AI text"


def test_flask_input_matches_flask_correctly(monkeypatch):
    """
    SECOND TEST:
    Input: 'Flask is a lightweight WSGI web application framework.'
    Candidate: Flask
    Expected: VERIFIED_WEB_MATCH
    """
    doc_text = "Flask is a lightweight WSGI web application framework."

    options = PipelineOptions(
        search_depth="quick",
        enable_semantic_matching=True,
        enable_fuzzy_matching=True,
        max_urls_to_fetch=5
    )
    pipeline = WebSourceDetectionPipeline(options=options)
    pipeline.search_chain.providers = [MockMultiCandidateSearchProvider()]

    def mock_fetch_page(cand):
        url = cand.url
        if "palletsprojects.com" in url:
            return CandidatePage(
                url=FLASK_URL,
                final_url=FLASK_URL,
                title=FLASK_TITLE,
                content=FLASK_CONTENT,
                normalized_content=FLASK_CONTENT.lower(),
                word_count=len(FLASK_CONTENT.split()),
                domain="palletsprojects.com",
                fetch_source="full_page"
            )
        elif "pega.com" in url:
            return CandidatePage(
                url=PEGA_URL,
                final_url=PEGA_URL,
                title=PEGA_TITLE,
                content=PEGA_CONTENT,
                normalized_content=PEGA_CONTENT.lower(),
                word_count=len(PEGA_CONTENT.split()),
                domain="pega.com",
                fetch_source="full_page"
            )
        return None

    monkeypatch.setattr(pipeline.fetcher, "fetch_page", mock_fetch_page)

    result: WebDetectionResult = pipeline.run(doc_text)

    assert len(result.sentence_audits) >= 1
    audit = result.sentence_audits[0]

    assert audit.selected_source == FLASK_URL
    assert audit.verification_status == VerificationStatus.VERIFIED_WEB_MATCH.value

    legacy = result.to_legacy_matches()
    selected_urls = [m["source_url"] for m in legacy]
    assert FLASK_URL in selected_urls
    assert PEGA_URL not in selected_urls


def test_paraphrase_example(monkeypatch):
    """
    THIRD TEST — PARAPHRASE (Prompt Section 14):
    Document: 'Flask is a lightweight framework designed for creating WSGI web applications.'
    Source: 'Flask is a lightweight WSGI web application framework.'
    The system calculates semantic, fuzzy, lexical, and entity overlap.
    """
    doc_text = "Flask is a lightweight framework designed for creating WSGI web applications."

    options = PipelineOptions(
        search_depth="quick",
        enable_semantic_matching=True,
        enable_fuzzy_matching=True,
        max_urls_to_fetch=5
    )
    pipeline = WebSourceDetectionPipeline(options=options)
    pipeline.search_chain.providers = [MockMultiCandidateSearchProvider()]

    def mock_fetch_page(cand):
        if "palletsprojects.com" in cand.url:
            return CandidatePage(
                url=FLASK_URL,
                final_url=FLASK_URL,
                title=FLASK_TITLE,
                content=FLASK_CONTENT,
                normalized_content=FLASK_CONTENT.lower(),
                word_count=len(FLASK_CONTENT.split()),
                domain="palletsprojects.com",
                fetch_source="full_page"
            )
        return None

    monkeypatch.setattr(pipeline.fetcher, "fetch_page", mock_fetch_page)

    result: WebDetectionResult = pipeline.run(doc_text)
    assert len(result.sentence_audits) >= 1
    audit = result.sentence_audits[0]

    # Status must be either VERIFIED_WEB_MATCH or POSSIBLE_RELATED_SOURCE, NEVER misattributed to Pega
    candidates_by_url = {c.url: c for c in audit.candidates}
    flask_cand = candidates_by_url.get(FLASK_URL)
    assert flask_cand is not None
    assert flask_cand.status in [VerificationStatus.VERIFIED_WEB_MATCH.value, VerificationStatus.POSSIBLE_RELATED_SOURCE.value]
    assert flask_cand.entity_overlap >= 0.35


def test_semantic_similarity_without_lexical_overlap_cannot_verify_copying(monkeypatch):
    """
    Ensures that high semantic similarity alone without lexical verification
    can NEVER produce VERIFIED_WEB_MATCH or label a source as direct overlap.
    """
    doc_text = "Modern software developers frequently deploy scalable applications into cloud infrastructure."

    # Candidate has conceptually similar software terms but zero text copying
    cloud_url = "https://example.com/cloud-computing"
    cloud_content = (
        "Cloud infrastructure enables organizations to provision virtual servers, distributed networks, "
        "and managed databases on demand without maintaining physical data center hardware."
    )

    class MockCloudProvider(SearchProvider):
        @property
        def name(self):
            return "cloud_prov"
        def search(self, query, limit=5):
            return [SearchResult(url=cloud_url, title="Cloud Computing Guide", snippet=cloud_content, provider="cloud_prov", search_rank=1, discovered_by=[query.query_id], source_sentence_id=query.source_sentence_id)], SearchQueryRecord(query=query.text, provider="cloud_prov")

    options = PipelineOptions(search_depth="quick", enable_semantic_matching=True, enable_fuzzy_matching=True)
    pipeline = WebSourceDetectionPipeline(options=options)
    pipeline.search_chain.providers = [MockCloudProvider()]

    def mock_fetch_page(cand):
        return CandidatePage(
            url=cloud_url,
            title="Cloud Computing Guide",
            content=cloud_content,
            normalized_content=cloud_content.lower(),
            word_count=len(cloud_content.split()),
            domain="example.com"
        )


    monkeypatch.setattr(pipeline.fetcher, "fetch_page", mock_fetch_page)

    result = pipeline.run(doc_text)
    audit = result.sentence_audits[0]

    for cand in audit.candidates:
        # Cannot be VERIFIED_WEB_MATCH
        assert cand.status != VerificationStatus.VERIFIED_WEB_MATCH.value, (
            "Semantic similarity alone must NEVER produce VERIFIED_WEB_MATCH without lexical overlap!"
        )

