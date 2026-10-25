import pytest
from app.core.pipeline.source_clusterer import SourceClusterer
from app.core.pipeline.schemas import SourceMatch, Confidence, MatchType, SourceCategory


def test_cluster_prefers_docs_over_github_mirror():
    clusterer = SourceClusterer()

    match_github = SourceMatch(
        document_text="Flask is a lightweight WSGI web application framework.",
        source_text="Flask is a lightweight WSGI web application framework.",
        source_url="https://github.com/pallets/flask",
        source_title="GitHub - pallets/flask",
        match_type=MatchType.EXACT,
        matched_words=8,
        similarity=95.0,
        confidence=Confidence.HIGH,
        source_category=SourceCategory.CODE_REPOSITORY,
        verified=True,
        authority_score=25.0
    )

    match_docs = SourceMatch(
        document_text="Flask is a lightweight WSGI web application framework.",
        source_text="Flask is a lightweight WSGI web application framework.",
        source_url="https://flask.palletsprojects.com/en/stable/",
        source_title="Welcome to Flask — Flask Documentation (3.1.x)",
        match_type=MatchType.EXACT,
        matched_words=8,
        similarity=95.0,
        confidence=Confidence.HIGH,
        source_category=SourceCategory.OFFICIAL_DOCUMENTATION,
        verified=True,
        authority_score=95.0
    )

    clusters = clusterer.cluster_matches([match_github, match_docs])
    assert len(clusters) == 1
    cluster = clusters[0]
    # Official docs must be selected as likely_source!
    assert cluster.likely_source == "https://flask.palletsprojects.com/en/stable/"
    assert "https://github.com/pallets/flask" in cluster.urls
    assert any("Official documentation" in r for r in cluster.evidence_for_precedence)
