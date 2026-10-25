"""
PlagiaScan Pipeline — Evidence Scorer

Computes transparent, composite evidence scores:
- Exact N-gram evidence (40%)
- Longest matching span (20%)
- Sentence overlap & count (15%)
- Search-result relevance (10%)
- Semantic similarity (10%)
- Source consistency & order (5%)

Produces:
- Confidence level: HIGH / MEDIUM / LOW
- Explainability chain: human-readable reason strings
- Source category classification
- Authority scoring for source attribution
"""

import re
from urllib.parse import urlparse
from typing import List, Dict, Optional, Tuple

from app.core.pipeline.schemas import (
    Confidence,
    MatchType,
    SourceCategory,
    SourceEvidence,
    NgramMatch,
    FuzzyMatch,
    SemanticMatch
)


class EvidenceScorer:
    """
    Evaluates multi-signal evidence to produce final match scores and attribution confidence.
    """

    # Domain heuristics for categorization
    _DOCS_INDICATORS = re.compile(
        r'docs?\.[a-z0-9-]+\.[a-z]+|/[a-z]{2}/(?:stable|latest|docs?|guide|reference)/|'
        r'documentation|readthedocs\.io|gitbook\.io|palletsprojects\.com/en/|developer\.',
        re.I
    )
    _CODE_REPO_INDICATORS = re.compile(r'github\.com|gitlab\.com|bitbucket\.org|sourceforge\.net', re.I)
    _ACADEMIC_INDICATORS = re.compile(r'arxiv\.org|ieee\.org|acm\.org|springer\.com|sciencedirect\.com|nature\.com', re.I)
    _NEWS_INDICATORS = re.compile(r'bbc\.com|cnn\.com|reuters\.com|nytimes\.com|theguardian\.com|forbes\.com|bloomberg\.com', re.I)
    _FORUM_INDICATORS = re.compile(r'stackoverflow\.com|reddit\.com|quora\.com|stackexchange\.com', re.I)
    _ENCYCLOPEDIA_INDICATORS = re.compile(r'wikipedia\.org|britannica\.com|wikimedia\.org', re.I)

    @classmethod
    def categorize_source(cls, url: str) -> SourceCategory:
        """Categorize a source URL into standard domain categories."""
        if not url:
            return SourceCategory.UNKNOWN

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        full_url = url.lower()

        if domain.endswith('.edu') or '.edu.' in domain or domain.endswith('.ac.uk'):
            return SourceCategory.UNIVERSITY_WEBSITE
        if cls._ENCYCLOPEDIA_INDICATORS.search(domain):
            return SourceCategory.ENCYCLOPEDIA
        if cls._DOCS_INDICATORS.search(full_url):
            return SourceCategory.OFFICIAL_DOCUMENTATION
        if cls._CODE_REPO_INDICATORS.search(domain):
            return SourceCategory.CODE_REPOSITORY
        if cls._ACADEMIC_INDICATORS.search(domain):
            return SourceCategory.ACADEMIC_WEBSITE
        if cls._NEWS_INDICATORS.search(domain):
            return SourceCategory.NEWS_WEBSITE
        if cls._FORUM_INDICATORS.search(domain):
            return SourceCategory.FORUM
        if domain.endswith('.gov') or domain.endswith('.org'):
            return SourceCategory.REFERENCE_SITE

        return SourceCategory.COMPANY_WEBSITE if "." in domain else SourceCategory.UNKNOWN

    @classmethod
    def compute_authority_score(cls, url: str, fetch_source: str = "full_page") -> float:
        """
        Calculate domain authority score (0 to 100).
        Prefers official docs > educational > encyclopedic > news > code repositories.
        """
        score = 50.0
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()

        # Official documentation boost
        if cls._DOCS_INDICATORS.search(url):
            score += 35.0
        if any(p in path for p in ['/docs/', '/en/stable/', '/latest/', '/reference/']):
            score += 15.0

        # Encyclopedia boost
        if 'wikipedia.org' in domain:
            score += 25.0

        # Educational / Gov / Org boost
        if domain.endswith('.edu'):
            score += 25.0
        elif domain.endswith('.gov'):
            score += 20.0
        elif domain.endswith('.org'):
            score += 10.0

        # Penalize code repositories when serving as duplicate mirrors of docs
        if cls._CODE_REPO_INDICATORS.search(domain):
            score -= 25.0

        # Penalize snippets if full page failed
        if fetch_source != "full_page":
            score -= 15.0

        return max(5.0, min(100.0, score))

    def evaluate_match(
        self,
        ngram_match: NgramMatch,
        fuzzy_match: Optional[FuzzyMatch],
        semantic_match: Optional[SemanticMatch],
        matched_sentences_count: int,
        search_rank: int,
        discovered_by_count: int,
        url: str,
        fetch_source: str = "full_page"
    ) -> Tuple[SourceEvidence, Confidence, MatchType, float, List[str]]:
        """
        Synthesizes all signals into SourceEvidence, Confidence level, MatchType,
        overall similarity percentage, and human-readable explanation chain.
        """
        reasons: List[str] = []

        # 1. Exact N-gram evidence (0-100)
        # 25 words or coverage >= 0.8 => 100
        ngram_score = 0.0
        if ngram_match.verified:
            if ngram_match.longest_exact_match_words >= 25:
                ngram_score = 100.0
            elif ngram_match.longest_exact_match_words >= 15:
                ngram_score = 85.0
            elif ngram_match.longest_exact_match_words >= 8:
                ngram_score = 70.0
            else:
                ngram_score = min(60.0, ngram_match.coverage * 100.0)
            reasons.append(f"Verified {ngram_match.longest_exact_match_words} consecutive matching words on webpage")
        else:
            ngram_score = 0.0

        # 2. Longest matching span (0-100)
        longest_span = min(100.0, (ngram_match.longest_exact_match_words / 25.0) * 100.0)

        # 3. Sentence similarity / count (0-100)
        sentence_score = min(100.0, matched_sentences_count * 33.3)
        if matched_sentences_count > 1:
            reasons.append(f"{matched_sentences_count} document sentences matched")

        # 4. Search relevance (0-100)
        rank_contrib = max(0, 10 - search_rank) * 5.0 if search_rank > 0 else 20.0
        disco_contrib = min(50.0, discovered_by_count * 20.0)
        search_relevance = min(100.0, rank_contrib + disco_contrib)

        # 5. Semantic similarity (0-100)
        sem_sim = (semantic_match.cosine_similarity * 100.0) if semantic_match else 0.0
        if sem_sim >= 75.0 and not ngram_match.verified:
            reasons.append(f"High semantic paraphrase alignment ({sem_sim:.1f}%)")

        # 6. Source consistency
        consistency = 80.0 if ngram_match.verified else (50.0 if sem_sim > 60.0 else 20.0)

        # Composite score
        composite = (
            0.40 * ngram_score +
            0.20 * longest_span +
            0.15 * sentence_score +
            0.10 * search_relevance +
            0.10 * sem_sim +
            0.05 * consistency
        )
        composite = round(max(0.0, min(100.0, composite)), 2)

        # Confidence determination
        if (
            (ngram_match.longest_exact_match_words >= 25) or
            (ngram_match.verified and matched_sentences_count >= 2) or
            (ngram_match.longest_exact_match_words >= 8 and ngram_match.coverage >= 0.80)
        ):
            confidence = Confidence.HIGH
            reasons.append("Strong consecutive verbatim match satisfies HIGH confidence criteria")
        elif (
            (ngram_match.longest_exact_match_words >= 10) or
            (ngram_match.verified) or
            (sem_sim >= 72.0 and fuzzy_match and fuzzy_match.overall_fuzzy_score >= 0.60)
        ):
            confidence = Confidence.MEDIUM
            reasons.append("Partial sequence match or modified paraphrase (MEDIUM confidence)")
        else:
            confidence = Confidence.LOW
            reasons.append("Low confidence: fragmented overlap or common wording")

        # MatchType determination
        if ngram_match.longest_exact_match_words >= 25 or (ngram_match.verified and ngram_match.coverage >= 0.85):
            match_type = MatchType.EXACT
        elif ngram_match.verified:
            match_type = MatchType.PARTIAL
        elif fuzzy_match and fuzzy_match.overall_fuzzy_score >= 0.65:
            match_type = MatchType.FUZZY
        elif sem_sim >= 65.0:
            match_type = MatchType.SEMANTIC
        else:
            match_type = MatchType.MOSAIC

        # Overall similarity percentage for reporting
        if ngram_match.verified:
            similarity = max(composite, round(ngram_match.coverage * 100.0, 1))
            similarity = max(similarity, min(100.0, ngram_match.longest_exact_match_words * 4.0))
        else:
            similarity = round(max(composite * 0.8, sem_sim), 1)

        evidence = SourceEvidence(
            ngram_evidence=round(ngram_score, 1),
            longest_span=round(longest_span, 1),
            sentence_similarity=round(sentence_score, 1),
            search_relevance=round(search_relevance, 1),
            semantic_similarity=round(sem_sim, 1),
            source_consistency=round(consistency, 1),
            composite_score=composite
        )

        return evidence, confidence, match_type, similarity, reasons
