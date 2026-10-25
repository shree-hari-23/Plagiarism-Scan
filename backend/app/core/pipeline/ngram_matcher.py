"""
PlagiaScan Pipeline — N-gram Matcher

Verbatim exact sequence detection using sliding-window N-grams:
- Configurable N-gram size (default 25 words, adaptive for shorter units >= 10 words)
- Longest unbroken consecutive matching sequence detection
- Overlap coverage and hit calculation
- Highlighting exact matching spans
"""

from typing import Set, Tuple, List, Optional
from app.core.pipeline.schemas import NgramMatch
from app.core.pipeline.text_normalizer import TextNormalizer


class NgramMatcher:
    """
    Detects verbatim matching spans between document text and candidate web content.
    """

    def __init__(self, default_n: int = 25, min_threshold_n: int = 5):
        self.default_n = default_n
        self.min_threshold_n = min_threshold_n

    @staticmethod
    def build_ngram_set(tokens: List[str], n: int) -> Set[Tuple[str, ...]]:
        """Construct set of tuple n-grams from a list of tokens."""
        if len(tokens) < n or n <= 0:
            return set()
        return {tuple(tokens[i: i + n]) for i in range(len(tokens) - n + 1)}

    def match(
        self,
        doc_text: str,
        page_text: str,
        custom_n: Optional[int] = None
    ) -> NgramMatch:
        """
        Compare doc_text against page_text.
        Computes longest consecutive matching sequence and coverage.
        """
        norm_doc = TextNormalizer.normalize(doc_text)
        norm_page = TextNormalizer.normalize(page_text)

        doc_tokens = norm_doc.split()
        page_tokens = norm_page.split()

        if not doc_tokens or not page_tokens:
            return NgramMatch(verified=False)

        target_n = custom_n or self.default_n

        # Adaptive N: if document text has fewer words than target_n,
        # adapt down to doc length if doc has at least min_threshold_n words
        if len(doc_tokens) < target_n:
            if len(doc_tokens) >= self.min_threshold_n:
                target_n = len(doc_tokens)
            else:
                return NgramMatch(verified=False)

        page_ngram_set = self.build_ngram_set(page_tokens, target_n)
        if not page_ngram_set:
            return NgramMatch(verified=False)

        # Slide through document tokens and track consecutive hits
        best_start = -1
        best_len = 0
        curr_start = -1
        curr_len = 0
        hits = 0
        matched_phrase = ""


        num_possible_grams = len(doc_tokens) - target_n + 1

        for i in range(num_possible_grams):
            gram = tuple(doc_tokens[i: i + target_n])
            if gram in page_ngram_set:
                hits += 1
                if curr_start == -1:
                    curr_start = i
                    curr_len = target_n
                else:
                    curr_len += 1

                if curr_len > best_len:
                    best_len = curr_len
                    best_start = curr_start
            else:
                curr_start = -1
                curr_len = 0

        # Compute exact word overlap
        doc_word_set = set(doc_tokens)
        page_word_set = set(page_tokens)
        exact_word_overlap = round(len(doc_word_set & page_word_set) / max(len(doc_word_set), 1), 4)

        # Multi-scale N-gram hits (10, 15, 20, 25)
        ngram_10_hit = False
        ngram_15_hit = False
        ngram_20_hit = False
        ngram_25_hit = False

        if len(doc_tokens) >= 10 and len(page_tokens) >= 10:
            set_10 = self.build_ngram_set(page_tokens, 10)
            ngram_10_hit = any(tuple(doc_tokens[i: i + 10]) in set_10 for i in range(len(doc_tokens) - 9))

        if len(doc_tokens) >= 15 and len(page_tokens) >= 15:
            set_15 = self.build_ngram_set(page_tokens, 15)
            ngram_15_hit = any(tuple(doc_tokens[i: i + 15]) in set_15 for i in range(len(doc_tokens) - 14))

        if len(doc_tokens) >= 20 and len(page_tokens) >= 20:
            set_20 = self.build_ngram_set(page_tokens, 20)
            ngram_20_hit = any(tuple(doc_tokens[i: i + 20]) in set_20 for i in range(len(doc_tokens) - 19))

        if len(doc_tokens) >= 25 and len(page_tokens) >= 25:
            set_25 = self.build_ngram_set(page_tokens, 25)
            ngram_25_hit = any(tuple(doc_tokens[i: i + 25]) in set_25 for i in range(len(doc_tokens) - 24))

        # If primary sliding-window missed due to large target_n, use find_longest_common_substring
        if hits == 0 or best_start == -1 or best_len < 6:
            longest_sub = self.find_longest_common_substring(doc_text, page_text)
            sub_tokens = longest_sub.split()
            if len(sub_tokens) >= self.min_threshold_n:
                best_len = len(sub_tokens)
                matched_phrase = longest_sub
                hits = max(hits, 1)

        if hits == 0 and best_len == 0:
            return NgramMatch(
                verified=False,
                exact_word_overlap=exact_word_overlap,
                ngram_10_hit=ngram_10_hit,
                ngram_15_hit=ngram_15_hit,
                ngram_20_hit=ngram_20_hit,
                ngram_25_hit=ngram_25_hit
            )

        coverage = min(1.0, hits / max(1, num_possible_grams)) if num_possible_grams > 0 else 0.0
        if not matched_phrase and best_start >= 0:
            matched_tokens = doc_tokens[best_start: best_start + best_len]
            matched_phrase = ' '.join(matched_tokens)

        # Count matching paragraphs in page content
        raw_paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]
        matching_paragraphs = 0
        if matched_phrase:
            norm_phrase = TextNormalizer.normalize(matched_phrase)
            for p in raw_paragraphs:
                if norm_phrase in TextNormalizer.normalize(p):
                    matching_paragraphs += 1

        # Classification
        if best_len >= 25 or coverage >= 0.70:
            match_type = "exact_phrase"
        else:
            match_type = "partial_phrase"

        verified = (best_len >= 8) or (coverage >= 0.40 and best_len >= 5) or ngram_10_hit

        return NgramMatch(
            verified=verified,
            matched_phrase=matched_phrase,
            match_length=best_len,
            ngram_hits=hits,
            coverage=round(coverage, 4),
            match_type=match_type,
            longest_exact_match_words=best_len,
            longest_matching_sequence=best_len,
            exact_word_overlap=exact_word_overlap,
            matching_sentences=1 if verified else 0,
            matching_paragraphs=matching_paragraphs,
            ngram_10_hit=ngram_10_hit,
            ngram_15_hit=ngram_15_hit,
            ngram_20_hit=ngram_20_hit,
            ngram_25_hit=ngram_25_hit
        )


    def find_longest_common_substring(self, s1: str, s2: str) -> str:
        """Helper to find longest unbroken common token substring."""
        tokens1 = TextNormalizer.tokenize(s1)
        tokens2 = TextNormalizer.tokenize(s2)

        if not tokens1 or not tokens2:
            return ""

        # Using dynamic programming on token lists
        m, n = len(tokens1), len(tokens2)
        # Memory optimization: store only previous and current row
        prev = [0] * (n + 1)
        max_len = 0
        end_idx1 = 0

        for i in range(1, m + 1):
            curr = [0] * (n + 1)
            t1 = tokens1[i - 1]
            for j in range(1, n + 1):
                if t1 == tokens2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                    if curr[j] > max_len:
                        max_len = curr[j]
                        end_idx1 = i
                else:
                    curr[j] = 0
            prev = curr

        if max_len == 0:
            return ""

        return ' '.join(tokens1[end_idx1 - max_len: end_idx1])
