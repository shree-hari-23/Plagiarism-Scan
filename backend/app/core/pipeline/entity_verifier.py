"""
PlagiaScan Pipeline — Entity & Topic Consistency Verifier

Enforces conceptual consistency between document sentences and candidate webpages:
- Generic extraction of named entities, technical acronyms, and domain noun phrases
- Calculates entity and domain keyword overlap
- Prevents promoting conceptually disjoint candidates (e.g. Flask WSGI docs for Agentic AI)
- Operates entirely on generic lexical/structural heuristics with zero hardcoded domains.
"""

import re
from typing import Set, Tuple, List, Dict, Any
from app.core.pipeline.text_normalizer import TextNormalizer


# Standard generic English stop words (not domain-specific)
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's", "where",
    "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with",
    "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've",
    "your", "yours", "yourself", "yourselves", "type", "sort", "kind", "also",
    "well", "like", "using", "used", "make", "makes", "made", "runs"
}


class EntityVerifier:
    """
    Computes generic entity and topic consistency scores between document units
    and candidate web sources.
    """

    @classmethod
    def extract_salient_concepts(cls, text: str) -> Tuple[Set[str], Set[str]]:
        """
        Extract:
        1. Named entities & technical terms (capitalized multi-word phrases, acronyms, CamelCase)
        2. Salient content keywords (nouns, domain words with stopwords removed)
        """
        if not text:
            return set(), set()

        entities: Set[str] = set()

        # 1. Acronyms (e.g. AI, WSGI, API, LLM, NLP, HTTP)
        acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
        for acr in acronyms:
            entities.add(acr.lower())

        # 2. Capitalized phrases (e.g. "Agentic AI", "Autonomous AI", "WSGI Application")
        cap_phrases = re.findall(r'\b[A-Z][a-zA-Z0-9_-]+(?:\s+[A-Z][a-zA-Z0-9_-]+)+\b', text)
        for phrase in cap_phrases:
            phrase_norm = TextNormalizer.normalize(phrase)
            if phrase_norm and len(phrase_norm.split()) >= 2:
                entities.add(phrase_norm)

        # 3. CamelCase or tech symbols (e.g. Werkzeug, Jinja, FastEmbed, Pallets)
        tech_words = re.findall(r'\b[A-Z][a-z0-9]+[A-Z][a-zA-Z0-9]*\b', text)
        for tw in tech_words:
            entities.add(tw.lower())

        # 4. Individual salient content keywords
        norm_text = TextNormalizer.normalize(text)
        tokens = norm_text.split()
        keywords: Set[str] = set()
        for tok in tokens:
            cleaned = re.sub(r'[^a-zA-Z0-9]', '', tok)
            if len(cleaned) >= 3 and cleaned not in STOP_WORDS:
                keywords.add(cleaned)

        return entities, keywords

    @classmethod
    def compute_overlap(cls, doc_text: str, candidate_text: str, candidate_title: str = "") -> float:
        """
        Calculate generic entity and topic overlap ratio (0.0 to 1.0) of doc_text in candidate.
        Higher ratio = higher conceptual consistency.
        """
        doc_entities, doc_keywords = cls.extract_salient_concepts(doc_text)

        if not doc_keywords and not doc_entities:
            return 1.0

        full_candidate_haystack = TextNormalizer.normalize(f"{candidate_title} {candidate_text}")
        candidate_words_set = set(full_candidate_haystack.split())

        # 1. Entity containment
        entity_score = 0.0
        if doc_entities:
            matched_entities = 0
            for ent in doc_entities:
                if len(ent.split()) == 1:
                    # Single-word acronym or term: check token set
                    if ent in candidate_words_set:
                        matched_entities += 1
                else:
                    # Multi-word phrase: match with word boundaries
                    ent_pattern = r'\b' + r'\s+'.join(re.escape(w) for w in ent.split()) + r'\b'
                    if re.search(ent_pattern, full_candidate_haystack):
                        matched_entities += 1
                    else:
                        ent_tokens = set(ent.split())
                        if ent_tokens and ent_tokens.issubset(candidate_words_set):
                            matched_entities += 1
            entity_score = matched_entities / len(doc_entities)


        # 2. Keyword containment
        keyword_score = 0.0
        if doc_keywords:
            matched_keywords = sum(1 for kw in doc_keywords if kw in candidate_words_set)
            keyword_score = matched_keywords / len(doc_keywords)

        # Combine scores
        if doc_entities and doc_keywords:
            overlap = 0.60 * entity_score + 0.40 * keyword_score
        elif doc_entities:
            overlap = entity_score
        else:
            overlap = keyword_score

        return round(max(0.0, min(1.0, overlap)), 4)
