import pytest
from app.core.pipeline.schemas import DocumentSentence
from app.core.pipeline.phrase_extractor import DistinctivePhraseExtractor


def test_score_distinctiveness():
    extractor = DistinctivePhraseExtractor()

    # Highly technical and specific sentence with entities and acronyms
    tech_sent = "Flask is a lightweight WSGI web application framework in Python."
    # Generic, vague sentence
    generic_sent = "In conclusion, this is a very good and nice thing for everyone."

    score_tech = extractor.score_distinctiveness(tech_sent)
    score_gen = extractor.score_distinctiveness(generic_sent)

    assert score_tech > score_gen


def test_phrase_extraction_windows():
    extractor = DistinctivePhraseExtractor()
    doc_sent = DocumentSentence(
        sentence_id="s_001",
        text="Agentic AI, or autonomous AI, is a type of artificial intelligence that can take action without human input.",
        normalized_text="agentic ai or autonomous ai is a type of artificial intelligence that can take action without human input",
        word_count=18
    )

    phrases = extractor.extract_phrases_for_sentence(doc_sent, max_phrases=3)
    assert len(phrases) >= 1
    assert any("agentic" in p.phrase.lower() for p in phrases)


def test_wikipedia_query_extraction():
    extractor = DistinctivePhraseExtractor()
    sent = "The Werkzeug WSGI toolkit is used inside the Flask framework."
    wiki_kw = extractor.extract_wikipedia_query(sent)
    assert len(wiki_kw.split()) >= 1
    assert any(term in wiki_kw for term in ["Werkzeug", "WSGI", "Flask"])
