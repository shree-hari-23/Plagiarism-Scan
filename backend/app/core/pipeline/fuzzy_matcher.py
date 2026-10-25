"""
PlagiaScan Pipeline — Fuzzy Matcher

Approximate and paraphrase matching:
- Token-level Jaccard similarity
- Normalized token edit distance
- Token set ratio (word reordering resilience)
- SequenceMatcher character/token ratio
Note: Used as supporting evidence only; never standalone plagiarism determination.
"""

from difflib import SequenceMatcher
from typing import List, Set
from app.core.pipeline.schemas import FuzzyMatch
from app.core.pipeline.text_normalizer import TextNormalizer


class FuzzyMatcher:
    """
    Computes lexical similarity and edit distances between document and web text.
    """

    @staticmethod
    def jaccard_similarity(tokens_a: List[str], tokens_b: List[str]) -> float:
        """Compute token set Jaccard similarity: |A ∩ B| / |A ∪ B|."""
        set_a: Set[str] = set(tokens_a)
        set_b: Set[str] = set(tokens_b)
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        return round(intersection / union, 4) if union > 0 else 0.0

    @staticmethod
    def token_set_ratio(tokens_a: List[str], tokens_b: List[str]) -> float:
        """
        Token set ratio: resilient against word reordering and duplicate filler words.
        """
        set_a = set(tokens_a)
        set_b = set(tokens_b)
        intersect = sorted(list(set_a.intersection(set_b)))
        if not intersect:
            return 0.0

        inter_str = " ".join(intersect)
        a_str = " ".join(sorted(tokens_a))
        b_str = " ".join(sorted(tokens_b))

        r1 = SequenceMatcher(None, inter_str, a_str).ratio()
        r2 = SequenceMatcher(None, inter_str, b_str).ratio()
        return round(max(r1, r2), 4)

    @staticmethod
    def token_levenshtein_distance(tokens_a: List[str], tokens_b: List[str]) -> float:
        """
        Normalized token Levenshtein distance: 0.0 (identical) to 1.0 (completely distinct).
        """
        m, n = len(tokens_a), len(tokens_b)
        if m == 0 and n == 0:
            return 0.0
        if m == 0:
            return 1.0
        if n == 0:
            return 1.0

        prev = list(range(n + 1))
        curr = [0] * (n + 1)

        for i in range(1, m + 1):
            curr[0] = i
            t_a = tokens_a[i - 1]
            for j in range(1, n + 1):
                cost = 0 if t_a == tokens_b[j - 1] else 1
                curr[j] = min(
                    curr[j - 1] + 1,        # insertion
                    prev[j] + 1,            # deletion
                    prev[j - 1] + cost      # substitution
                )
            prev = list(curr)

        raw_dist = prev[n]
        max_len = max(m, n)
        return round(raw_dist / max_len, 4)

    def match(self, text_a: str, text_b: str) -> FuzzyMatch:
        """
        Compute comprehensive fuzzy match metrics between two texts.
        """
        norm_a = TextNormalizer.normalize(text_a)
        norm_b = TextNormalizer.normalize(text_b)

        tokens_a = norm_a.split()
        tokens_b = norm_b.split()

        if not tokens_a or not tokens_b:
            return FuzzyMatch()

        jaccard = self.jaccard_similarity(tokens_a, tokens_b)
        t_set = self.token_set_ratio(tokens_a, tokens_b)
        norm_lev = self.token_levenshtein_distance(tokens_a, tokens_b)
        # Edit distance similarity: 1.0 - normalized distance
        edit_sim = round(max(0.0, 1.0 - norm_lev), 4)

        # difflib SequenceMatcher ratio
        seq_ratio = round(SequenceMatcher(None, norm_a, norm_b).ratio(), 4)

        # Composite fuzzy score: 35% Jaccard + 35% SequenceMatcher + 30% TokenSet
        overall = round(0.35 * jaccard + 0.35 * seq_ratio + 0.30 * t_set, 4)

        return FuzzyMatch(
            token_similarity=jaccard,
            edit_distance=edit_sim,
            token_set_ratio=t_set,
            sequence_ratio=seq_ratio,
            overall_fuzzy_score=overall
        )
