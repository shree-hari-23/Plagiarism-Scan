"""
PlagiaScan Pipeline — Text Normalizer

Deterministic text normalization pipeline for exact matching.
Maintains both raw_text and normalized_text.
"""

import re
import unicodedata
from typing import Tuple


class TextNormalizer:
    """
    Deterministic text normalization for plagiarism comparison.

    Normalization pipeline:
      1. Unicode NFKD normalization
      2. Smart quote → ASCII quote
      3. Em-dash / en-dash → hyphen
      4. Non-breaking space → regular space
      5. Citation bracket removal ([1], [2-4])
      6. Lowercase
      7. Strip non-alphanumeric (keep spaces)
      8. Collapse whitespace
    """

    # Pre-compiled patterns
    _CITATION_BRACKETS = re.compile(r'\[\d+(?:\s*[-–,]\s*\d+)*\]')
    _NON_ALPHANUM = re.compile(r'[^a-z0-9\s]')
    _MULTI_SPACE = re.compile(r'\s+')

    @classmethod
    def normalize(cls, text: str) -> str:
        """
        Full normalization for exact N-gram comparison.
        Returns lowercase alphanumeric-only token string.
        """
        if not text:
            return ""

        # Unicode dashes and quotes → ASCII
        text = cls._normalize_unicode_chars(text)

        # NFKD normalization (decompose accented characters)
        text = unicodedata.normalize('NFKD', text)

        # Remove citation brackets
        text = cls._CITATION_BRACKETS.sub('', text)

        # Lowercase
        text = text.lower()

        # Keep only alphanumeric and spaces
        text = cls._NON_ALPHANUM.sub(' ', text)

        # Collapse whitespace
        text = cls._MULTI_SPACE.sub(' ', text).strip()

        return text

    @classmethod
    def normalize_for_query(cls, text: str) -> str:
        """
        Lighter normalization for search query construction.
        Preserves meaningful words, converts Unicode to ASCII equivalents.
        """
        if not text:
            return ""

        text = cls._normalize_unicode_chars(text)
        text = unicodedata.normalize('NFKD', text)

        # Remove punctuation but keep hyphens and apostrophes for terms
        text = re.sub(r"[^\w\s\'-]", ' ', text, flags=re.UNICODE)
        text = cls._MULTI_SPACE.sub(' ', text).strip()

        return text

    @classmethod
    def normalize_preserving_case(cls, text: str) -> str:
        """
        Normalize whitespace and Unicode but preserve case.
        Useful for display purposes.
        """
        if not text:
            return ""

        text = cls._normalize_unicode_chars(text)
        text = unicodedata.normalize('NFKD', text)
        text = cls._MULTI_SPACE.sub(' ', text).strip()

        return text

    @classmethod
    def dual_normalize(cls, text: str) -> Tuple[str, str]:
        """
        Returns (original_cleaned, normalized) pair.
        original_cleaned: whitespace-normalized, Unicode-fixed, but case-preserved.
        normalized: fully normalized for comparison.
        """
        original_cleaned = cls.normalize_preserving_case(text)
        normalized = cls.normalize(text)
        return original_cleaned, normalized

    @classmethod
    def sanitize_query_text(cls, text: str) -> str:
        """
        Sanitize raw text for search API query construction.
        Converts Unicode quotes, dashes, and spaces to standard ASCII,
        flattens linebreaks, and collapses multiple spaces.
        """
        if not text:
            return ""

        # Flatten newlines and tabs
        text = text.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
        # Normalize unicode quotes, dashes, spaces
        text = cls._normalize_unicode_chars(text)
        # NFKD decompose
        text = unicodedata.normalize('NFKD', text)
        # Strip remaining control characters
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        # Collapse multiple spaces
        text = cls._MULTI_SPACE.sub(' ', text).strip()
        return text

    @staticmethod
    def _normalize_unicode_chars(text: str) -> str:
        """Replace Unicode dashes, quotes, and special spaces with ASCII."""
        # Dashes and hyphens → standard hyphen
        for ch in ('\u2010', '\u2011', '\u2012', '\u2013', '\u2014', '\u2015', '\u2212'):
            text = text.replace(ch, '-')
        # Soft hyphen → remove
        text = text.replace('\u00ad', '')

        # Single quotes & primes → straight single quote
        for ch in ('\u2018', '\u2019', '\u201a', '\u201b', '\u2032', '\u0060', '\u00b4'):
            text = text.replace(ch, "'")

        # Double quotes & guillemets → straight double quote
        for ch in ('\u201c', '\u201d', '\u201e', '\u201f', '\u00ab', '\u00bb', '\u2033'):
            text = text.replace(ch, '"')

        # Non-breaking space & special spaces → regular space
        for ch in ('\u00a0', '\u202f', '\u2007', '\u2008', '\u2009', '\u200a', '\u3000'):
            text = text.replace(ch, ' ')

        # Zero-width spaces & markers
        for ch in ('\u200b', '\u200c', '\u200d', '\ufeff'):
            text = text.replace(ch, '')

        return text

    @classmethod
    def tokenize(cls, text: str) -> list:
        """Tokenize normalized text into word list."""
        normalized = cls.normalize(text)
        return normalized.split() if normalized else []

    @classmethod
    def word_count(cls, text: str) -> int:
        """Count words after normalization."""
        return len(cls.tokenize(text))
