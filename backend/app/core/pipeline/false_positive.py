"""
PlagiaScan Pipeline — False Positive & Boilerplate Filter

Filters out:
- Common idioms, cliches, and generic academic boilerplate
- Citations, references, and bibliography entries
- Standard web navigation / legal boilerplate
- Low-information common phrases (<8 words with only generic stopwords)
"""

import re
from typing import Set, Tuple


class FalsePositiveFilter:
    """
    Prevents false positive plagiarism attributions from common idioms,
    citations, and generic boilerplate.
    """

    # Common generic idioms and transitions
    COMMON_IDIOMS: Set[str] = {
        "in order to", "as a matter of fact", "at the end of the day",
        "in the context of", "it should be noted that", "it is important to remember",
        "it is worth noting that", "on the other hand", "for the purpose of",
        "with respect to", "as shown in the following", "in accordance with",
        "a wide range of", "plays an important role in", "as a result of",
        "in addition to", "due to the fact that", "has been shown to",
        "can be seen that", "it is clear that", "in terms of",
        "take into account", "as well as", "at the same time"
    }

    # Web, copyright, and publishing boilerplate
    BOILERPLATE_PATTERNS = [
        re.compile(r'all rights reserved', re.I),
        re.compile(r'terms of service|terms and conditions', re.I),
        re.compile(r'privacy policy', re.I),
        re.compile(r'cookie policy|accept cookies', re.I),
        re.compile(r'sign up for our newsletter', re.I),
        re.compile(r'copyright\s+(?:\(c\)|©)?\s*\d{4}', re.I),
        re.compile(r'click here to (?:read|learn|subscribe|download)', re.I),
        re.compile(r'leave a comment|post a comment', re.I),
        re.compile(r'powered by (?:wordpress|shopify|drupal)', re.I),
    ]

    # Academic citations & bibliography regex patterns
    CITATION_PATTERNS = [
        re.compile(r'\b(?:doi|doi\.org|isbn|issn|arxiv):\s*[0-9a-zA-Z./-]+', re.I),
        re.compile(r'\b(?:pp\.|pages)\s+\d+[-–]\d+\b', re.I),
        re.compile(r'\b(?:vol\.|volume)\s+\d+(?:,\s*no\.\s*\d+)?\b', re.I),
        re.compile(r'^[A-Z][a-zA-Z\'-]+,\s+[A-Z]\.(?:\s*[A-Z]\.)?\s*\(\d{4}\)', re.I),  # APA author style
        re.compile(r'\b(?:in proceedings of|ieee transactions on|acm computing surveys|journal of)\b', re.I),
        re.compile(r'\[\d+\]\s+[A-Z][a-z]+', re.I)  # IEEE [1] Author style
    ]

    @classmethod
    def is_boilerplate(cls, text: str) -> bool:
        """Check if snippet is standard website boilerplate."""
        if not text:
            return False
        for pattern in cls.BOILERPLATE_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @classmethod
    def is_citation_or_reference(cls, text: str) -> bool:
        """Check if snippet looks like an academic bibliography or reference citation."""
        if not text:
            return False
        for pattern in cls.CITATION_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @classmethod
    def is_common_idiom_only(cls, text: str) -> bool:
        """Check if snippet is purely an idiom or generic phrase without specific content."""
        clean = text.strip().lower()
        if clean in cls.COMMON_IDIOMS:
            return True
        words = clean.split()
        if len(words) < 6:
            # Check if all words are simple stopwords
            stopwords = {
                'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
                'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                'have', 'has', 'had', 'that', 'this', 'it', 'there', 'can', 'will', 'as'
            }
            if all(w in stopwords for w in words):
                return True
        return False

    @classmethod
    def should_suppress_match(
        cls,
        matched_text: str,
        match_length: int,
        source_url: str
    ) -> Tuple[bool, str]:
        """
        Determine if a match should be suppressed or downgraded.
        Returns (should_suppress, reason).
        """
        if cls.is_boilerplate(matched_text):
            return True, "Suppressed: standard website/legal boilerplate"

        if cls.is_citation_or_reference(matched_text):
            return True, "Suppressed: academic citation / bibliography reference"

        if match_length < 7 and cls.is_common_idiom_only(matched_text):
            return True, "Suppressed: generic common idiom with no technical distinctiveness"

        return False, ""
