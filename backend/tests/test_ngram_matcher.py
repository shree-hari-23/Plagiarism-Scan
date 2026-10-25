import pytest
from app.core.pipeline.ngram_matcher import NgramMatcher


def test_exact_25_word_match():
    matcher = NgramMatcher(default_n=25)
    passage = (
        "Agentic AI, or autonomous AI, is a type of artificial intelligence that can "
        "independently think, act, and complete complex workflows without direct human intervention "
        "by executing steps toward defined operational goals."
    )
    webpage = (
        "Here is an article about modern computing. " + passage + " This makes it very powerful."
    )

    result = matcher.match(passage, webpage)
    assert result.verified is True
    assert result.longest_exact_match_words >= 25
    assert result.match_type == "exact_phrase"


def test_short_sentence_adaptive_match():
    matcher = NgramMatcher(default_n=25, min_threshold_n=5)
    sentence = "Flask is a lightweight WSGI web application framework."
    webpage = (
        "Welcome to Flask Documentation. Flask is a lightweight WSGI web application framework. "
        "It provides useful tools and features."
    )

    result = matcher.match(sentence, webpage)
    assert result.verified is True
    assert result.longest_exact_match_words == 8
    assert "flask is a lightweight wsgi web application framework" in result.matched_phrase


def test_no_match():
    matcher = NgramMatcher(default_n=25)
    sentence = "Quantum mechanics explains the behavior of subatomic particles at low temperatures."
    webpage = "Cooking pasta requires boiling salted water in a large pot for ten minutes."

    result = matcher.match(sentence, webpage)
    assert result.verified is False
    assert result.match_length == 0


def test_longest_common_substring():
    matcher = NgramMatcher()
    s1 = "We explored deep learning techniques for natural language processing and computer vision."
    s2 = "A survey of deep learning techniques for natural language processing was published today."

    lcs = matcher.find_longest_common_substring(s1, s2)
    assert "deep learning techniques for natural language processing" in lcs
