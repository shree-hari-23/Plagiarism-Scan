import pytest
from app.core.pipeline.false_positive import FalsePositiveFilter


def test_boilerplate_detection():
    assert FalsePositiveFilter.is_boilerplate("All rights reserved. Terms and conditions apply.") is True
    assert FalsePositiveFilter.is_boilerplate("Click here to download our privacy policy.") is True
    assert FalsePositiveFilter.is_boilerplate("Flask is a lightweight WSGI framework.") is False


def test_citation_detection():
    cite_apa = "Vaswani, A. et al. (2017). Attention Is All You Need. In Proceedings of NIPS."
    cite_doi = "For more details see doi:10.1016/j.artint.2020.103382."
    normal_text = "Transformers rely entirely on self-attention mechanisms."

    assert FalsePositiveFilter.is_citation_or_reference(cite_apa) is True
    assert FalsePositiveFilter.is_citation_or_reference(cite_doi) is True
    assert FalsePositiveFilter.is_citation_or_reference(normal_text) is False


def test_suppress_common_idiom():
    suppress, reason = FalsePositiveFilter.should_suppress_match(
        matched_text="in order to",
        match_length=3,
        source_url="https://example.com"
    )
    assert suppress is True
