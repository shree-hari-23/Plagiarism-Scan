import pytest
from app.core.pipeline.fuzzy_matcher import FuzzyMatcher


def test_jaccard_similarity():
    matcher = FuzzyMatcher()
    t1 = ["flask", "is", "a", "web", "framework"]
    t2 = ["flask", "is", "a", "wsgi", "web", "framework"]
    sim = matcher.jaccard_similarity(t1, t2)
    assert sim > 0.8


def test_token_set_ratio_reordering():
    matcher = FuzzyMatcher()
    t1 = ["autonomous", "agentic", "ai", "systems"]
    t2 = ["systems", "of", "agentic", "autonomous", "ai"]
    ratio = matcher.token_set_ratio(t1, t2)
    assert ratio >= 0.8


def test_fuzzy_match_paraphrase():
    matcher = FuzzyMatcher()
    text_a = "Flask is a lightweight WSGI framework for building web apps."
    text_b = "Flask is a lightweight WSGI web application framework."

    f_res = matcher.match(text_a, text_b)
    assert f_res.overall_fuzzy_score > 0.65
    assert f_res.sequence_ratio > 0.60
