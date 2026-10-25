import pytest
from app.core.pipeline.segmenter import DocumentSegmenter
from app.core.pipeline.text_normalizer import TextNormalizer


def test_abbreviation_handling():
    segmenter = DocumentSegmenter()
    text = "Dr. Smith and Prof. Jones went to the U.S. for a conference. They arrived at 10 a.m. yesterday."
    sentences = segmenter.segment(text)
    # Should not split on Dr., Prof., U.S.
    assert len(sentences) == 2
    assert "Dr. Smith and Prof. Jones" in sentences[0].text
    assert "They arrived" in sentences[1].text


def test_decimal_and_url_handling():
    segmenter = DocumentSegmenter()
    text = "The version 3.1.4 was released on https://flask.palletsprojects.com. It improved speed by 2.5 times."
    sentences = segmenter.segment(text)
    assert len(sentences) == 2
    assert "3.1.4" in sentences[0].text
    assert "https://flask.palletsprojects.com" in sentences[0].text


def test_long_sentence_clause_extraction():
    segmenter = DocumentSegmenter(min_sentence_words=4, long_sentence_threshold=20)
    long_text = (
        "Flask is a lightweight WSGI web application framework in Python, "
        "providing useful tools and features that make creating web applications in Python easier, "
        "allowing developers to build flexible and modular architectures."
    )
    sentences = segmenter.segment(long_text)
    assert len(sentences) >= 2
    # At least one sentence should be marked as clause
    clauses = [s for s in sentences if s.is_clause]
    assert len(clauses) >= 1
    assert clauses[0].parent_sentence_id is not None


def test_citation_cleaning():
    segmenter = DocumentSegmenter()
    text = "Agentic AI refers to autonomous systems [1]. These systems plan independently [2-4]."
    sentences = segmenter.segment(text)
    assert len(sentences) == 2
    assert "[1]" not in sentences[0].text
    assert "[2-4]" not in sentences[1].text
