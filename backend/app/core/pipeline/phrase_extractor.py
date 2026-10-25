"""
PlagiaScan Pipeline — Distinctive Phrase Extractor

Extracts and scores search-worthy phrases from DocumentSentence objects.
Uses information-content heuristics:
- Entity and technical term boosting
- Numerical and acronym boosting
- Generic starter penalties
- Multi-window slicing (start, middle, second-quarter)
"""

import re
import math
import unicodedata
from typing import List, Tuple
from app.core.pipeline.schemas import DocumentSentence, DistinctivePhrase
from app.core.pipeline.text_normalizer import TextNormalizer


class DistinctivePhraseExtractor:
    """
    Extracts high-signal phrases and queries from document sentences.
    """

    # Common English stopwords to ignore in entity extraction and scoring
    STOPWORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
        'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'that', 'this', 'these', 'those',
        'it', 'its', 'they', 'their', 'we', 'our', 'you', 'your', 'he', 'she',
        'there', 'also', 'more', 'can', 'will', 'as', 'when', 'which', 'who',
        'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some',
        'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
        'very', 'just', 'should', 'now'
    }

    # Generic sentence starters that reduce search distinctiveness
    GENERIC_STARTERS = re.compile(
        r'^(this|the|a|an|in|it is|there are|as a|by|with|for|to|of|'
        r'furthermore|moreover|however|therefore|in conclusion|in summary|'
        r'additionally|consequently|nevertheless|on the other hand|'
        r'it can be seen|it should be noted|according to|firstly|secondly)\b',
        re.IGNORECASE
    )

    def __init__(
        self,
        min_phrase_words: int = 6,
        max_phrase_words: int = 16,
        default_phrase_words: int = 12
    ):
        self.min_phrase_words = min_phrase_words
        self.max_phrase_words = max_phrase_words
        self.default_phrase_words = default_phrase_words

    @classmethod
    def calculate_phrase_entropy(cls, tokens: List[str]) -> float:
        """
        Calculates information density based on non-stopword ratio, lexical diversity,
        and token length (as specified in Section 4.2 of the Source Attribution Guide).
        Score = (len(content_tokens) / len(tokens)) * diversity * ln(1 + avg_len)
        """
        if not tokens:
            return 0.0
        content_tokens = [w.lower() for w in tokens if w.lower() not in cls.STOPWORDS]
        if not content_tokens:
            return 0.0

        diversity = len(set(content_tokens)) / len(content_tokens)
        avg_len = sum(len(w) for w in content_tokens) / len(content_tokens)
        density = len(content_tokens) / len(tokens)
        return round(density * diversity * math.log1p(avg_len), 4)

    def score_distinctiveness(self, text: str) -> float:
        """
        Calculate an information-density score for a candidate text.
        Higher score = more unique, technical, and search-effective.
        Combines mathematical entropy with entity and acronym detection.
        """
        if not text:
            return 0.0

        words = text.split()
        if len(words) < 3:
            return 0.0

        score = float(len(words))

        # Information Entropy contribution (Section 4.2 formula)
        entropy = self.calculate_phrase_entropy(words)
        score += entropy * 8.0

        # Penalize generic phrase starts
        if self.GENERIC_STARTERS.match(text.strip()):
            score -= 5.0

        # Reward capitalized words / Named Entities (excluding sentence start)
        capitalized = re.findall(r'\b[A-Z][a-zA-Z0-9-]+\b', text)
        non_first_caps = [w for idx, w in enumerate(capitalized) if idx > 0 or w.lower() not in self.STOPWORDS]
        score += len(non_first_caps) * 2.0

        # Reward acronyms / all-caps (e.g. WSGI, AI, LLM, HTTP)
        acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
        score += len(acronyms) * 2.5

        # Reward numbers and version strings (e.g. 3.1.x, 2024, 42)
        numbers = re.findall(r'\b\d+(?:\.\d+)*\b', text)
        score += len(numbers) * 1.5

        # Reward technical punctuation: hyphens in words, quotes
        hyphenated = re.findall(r'\b[a-zA-Z]+-[a-zA-Z]+\b', text)
        score += len(hyphenated) * 1.5

        return round(score, 2)

    def extract_phrases_for_sentence(
        self,
        sentence: DocumentSentence,
        max_phrases: int = 3
    ) -> List[DistinctivePhrase]:
        """
        Extract multi-window candidate search phrases from a sentence.
        Takes windows from beginning, middle, and second-quarter if sentence is long.
        """
        clean_text = TextNormalizer.normalize_for_query(sentence.text)
        words = clean_text.split()
        n = len(words)

        if n < self.min_phrase_words:
            if n >= 3:
                phrase_str = ' '.join(words)
                return [
                    DistinctivePhrase(
                        phrase=phrase_str,
                        source_sentence_id=sentence.sentence_id,
                        distinctiveness_score=self.score_distinctiveness(phrase_str),
                        word_count=n
                    )
                ]
            return []

        candidates: List[Tuple[str, float]] = []

        # Window size to target
        w_size = min(self.default_phrase_words, n)

        # 1. Full sentence or prefix
        cand_start = ' '.join(words[:w_size])
        candidates.append((cand_start, self.score_distinctiveness(cand_start)))

        # 2. Middle window if sentence is sufficiently long
        if n >= w_size + 4:
            mid_start = max(0, (n - w_size) // 2)
            cand_mid = ' '.join(words[mid_start: mid_start + w_size])
            candidates.append((cand_mid, self.score_distinctiveness(cand_mid)))

        # 3. Second quarter window for very long sentences
        if n >= w_size + 8:
            q_start = max(0, n // 4)
            cand_q = ' '.join(words[q_start: q_start + w_size])
            candidates.append((cand_q, self.score_distinctiveness(cand_q)))

        # Deduplicate candidates while preserving best score
        seen = set()
        deduped: List[DistinctivePhrase] = []
        for phrase_str, score in sorted(candidates, key=lambda x: x[1], reverse=True):
            p_norm = phrase_str.lower().strip()
            if p_norm not in seen:
                seen.add(p_norm)
                deduped.append(
                    DistinctivePhrase(
                        phrase=phrase_str,
                        source_sentence_id=sentence.sentence_id,
                        distinctiveness_score=score,
                        word_count=len(phrase_str.split())
                    )
                )

        return deduped[:max_phrases]

    def extract_wikipedia_query(self, sentence_text: str) -> str:
        """
        Extract Wikipedia-targeted entity keywords from sentence.
        Prioritizes capitalized technical entities and uncommon nouns.
        """
        clean = TextNormalizer.normalize_for_query(sentence_text)

        # Look for capitalized words
        caps = [
            w for w in re.findall(r'\b[A-Z][a-zA-Z0-9-]+\b', sentence_text)
            if w.lower() not in self.STOPWORDS and len(w) > 1
        ]
        if len(caps) >= 2:
            return ' '.join(caps[:4])

        # Fallback: extract most informative words
        words = [
            w for w in clean.split()
            if w.lower() not in self.STOPWORDS and len(w) > 2
        ]
        if words:
            return ' '.join(words[:4])

        return clean[:50]

    def select_representative_sentences(
        self,
        sentences: List[DocumentSentence],
        target_count: int = 10
    ) -> List[DocumentSentence]:
        """
        Evenly partition document sentences across sections and select
        the highest-scoring distinctive sentence in each section.
        Ensures broad coverage across the whole document.
        """
        # Filter out sub-clauses for primary search selection
        primary_sentences = [s for s in sentences if not s.is_clause]
        if not primary_sentences:
            primary_sentences = sentences

        if not primary_sentences:
            return []

        if len(primary_sentences) <= target_count:
            return sorted(
                primary_sentences,
                key=lambda s: self.score_distinctiveness(s.text),
                reverse=True
            )

        selected: List[DocumentSentence] = []
        step = len(primary_sentences) / target_count

        for i in range(target_count):
            start_idx = int(i * step)
            end_idx = int((i + 1) * step)
            section = primary_sentences[start_idx:end_idx]
            if section:
                best = max(section, key=lambda s: self.score_distinctiveness(s.text))
                selected.append(best)

        return selected
