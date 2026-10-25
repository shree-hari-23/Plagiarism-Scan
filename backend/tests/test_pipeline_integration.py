import pytest
from app.core.pipeline.schemas import PipelineOptions, WebDetectionResult, Confidence
from app.core.pipeline.orchestrator import WebSourceDetectionPipeline
from app.core.pipeline.search_providers import SearchProvider, SearchQueryRecord, SearchResult


class MockSearchProvider(SearchProvider):
    @property
    def name(self) -> str:
        return "mock_provider"

    def search(self, query, limit=5):
        q = query.text.lower()
        results = []
        if "flask" in q or "wsgi" in q:
            results.append(
                SearchResult(
                    url="https://flask.palletsprojects.com/en/stable/",
                    title="Welcome to Flask — Flask Documentation (3.1.x)",
                    snippet="Flask is a lightweight WSGI web application framework. It is designed to make getting started quick and easy.",
                    provider="mock_provider",
                    search_rank=1,
                    discovered_by=[query.query_id],
                    source_sentence_id=query.source_sentence_id
                )
            )
            results.append(
                SearchResult(
                    url="https://github.com/pallets/flask",
                    title="GitHub - pallets/flask",
                    snippet="Flask is a lightweight WSGI web application framework. Repository on GitHub.",
                    provider="mock_provider",
                    search_rank=2,
                    discovered_by=[query.query_id],
                    source_sentence_id=query.source_sentence_id
                )
            )
        rec = SearchQueryRecord(query=query.text, provider=self.name, result_count=len(results), latency_ms=10)
        return results, rec


def test_pipeline_end_to_end_mocked(monkeypatch):
    options = PipelineOptions(
        search_depth="quick",
        enable_semantic_matching=False,
        max_urls_to_fetch=5
    )
    pipeline = WebSourceDetectionPipeline(options=options)
    pipeline.search_chain.providers = [MockSearchProvider()]

    doc_text = (
        "Flask is a lightweight WSGI web application framework. "
        "It is designed to make getting started quick and easy, with the ability to scale up to complex applications."
    )

    result: WebDetectionResult = pipeline.run(doc_text)

    assert result.total_sentences >= 1
    assert result.sources_found >= 1

    legacy = result.to_legacy_matches()
    assert len(legacy) >= 1
    first_match = legacy[0]

    assert "sentence" in first_match
    assert "source_url" in first_match
    assert "confidence" in first_match
    assert first_match["verified"] is True

    # Check that clustering prefers official docs over github
    if result.clusters:
        first_cluster = result.clusters[0]
        assert "palletsprojects.com" in first_cluster.likely_source
