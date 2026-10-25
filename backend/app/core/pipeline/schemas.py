"""
PlagiaScan Pipeline — Pydantic Schemas

Typed data models for every stage of the web source detection pipeline.
All pipeline data flows through these schemas instead of raw dicts.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VerificationStatus(str, Enum):
    VERIFIED_WEB_MATCH = "VERIFIED_WEB_MATCH"
    POSSIBLE_RELATED_SOURCE = "POSSIBLE_RELATED_SOURCE"
    NO_MATCH = "NO_MATCH"


class MatchType(str, Enum):
    EXACT = "exact"
    PARTIAL = "partial"
    FUZZY = "fuzzy"
    SEMANTIC = "semantic"
    MOSAIC = "mosaic"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"



class SourceCategory(str, Enum):
    OFFICIAL_DOCUMENTATION = "Official documentation"
    NEWS_WEBSITE = "News website"
    ACADEMIC_WEBSITE = "Academic website"
    UNIVERSITY_WEBSITE = "University website"
    COMPANY_WEBSITE = "Company website"
    BLOG = "Blog"
    FORUM = "Forum"
    REFERENCE_SITE = "Reference site"
    CONTENT_AGGREGATOR = "Content aggregator"
    CODE_REPOSITORY = "Code repository"
    ENCYCLOPEDIA = "Encyclopedia"
    UNKNOWN = "Unknown"


class SearchStrategy(str, Enum):
    EXACT_PHRASE = "exact_phrase"
    PARTIAL_PHRASE = "partial_phrase"
    ENTITY_SEARCH = "entity_search"
    NGRAM_FRAGMENTS = "ngram_fragments"
    WIKIPEDIA_API = "wikipedia_api"


# ---------------------------------------------------------------------------
# Document-level schemas
# ---------------------------------------------------------------------------

class DocumentSentence(BaseModel):
    """A single sentence extracted from the uploaded document."""
    sentence_id: str = Field(..., description="Unique ID like 's_001'")
    text: str = Field(..., description="Original sentence text")
    normalized_text: str = Field("", description="Lowercased, normalized for comparison")
    paragraph_id: str = Field("", description="Parent paragraph ID like 'p_003'")
    char_start: int = Field(0, description="Start character offset in full document")
    char_end: int = Field(0, description="End character offset in full document")
    word_count: int = Field(0, description="Number of words")
    is_clause: bool = Field(False, description="True if this is a sub-clause of a longer sentence")
    parent_sentence_id: Optional[str] = Field(None, description="If clause, the parent sentence ID")


class DistinctivePhrase(BaseModel):
    """A search-worthy phrase extracted from a sentence."""
    phrase: str
    source_sentence_id: str
    distinctiveness_score: float = Field(0.0, description="Higher = more unique/searchable")
    word_count: int = 0


# ---------------------------------------------------------------------------
# Search-level schemas
# ---------------------------------------------------------------------------

class SearchQuery(BaseModel):
    """A search query sent to a search provider."""
    query_id: str = Field(..., description="Unique ID like 'q_001'")
    text: str = Field(..., description="The query string")
    strategy: SearchStrategy = SearchStrategy.EXACT_PHRASE
    source_sentence_id: str = Field("", description="Which document sentence generated this query")
    source_phrase: str = Field("", description="The distinctive phrase this query was derived from")


class SearchResult(BaseModel):
    """A single result returned by a search provider."""
    url: str
    canonical_url: str = ""
    title: str = "Web Source"
    snippet: str = ""
    provider: str = ""
    search_rank: int = 0
    discovered_by: List[str] = Field(default_factory=list, description="List of query_ids that found this URL")
    source_sentence_id: str = ""
    snippet_overlap: float = 0.0
    title_overlap: float = 0.0
    probe_votes: int = 1


# ---------------------------------------------------------------------------
# Retrieval-level schemas
# ---------------------------------------------------------------------------

class CandidatePage(BaseModel):
    """A fetched and extracted webpage."""
    url: str
    final_url: str = ""
    canonical_url: str = ""
    title: str = ""
    author: Optional[str] = None
    published_date: Optional[str] = None
    content: str = Field("", description="Distilled clean text")
    normalized_content: str = Field("", description="Normalized for comparison")
    word_count: int = 0
    domain: str = ""
    fetch_source: str = "full_page"  # "full_page" | "snippet_fallback"
    http_status: int = 200
    fetch_latency_ms: int = 0
    content_hash: str = ""
    extracted_at: Optional[datetime] = None
    source_sentence_ids: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Matching-level schemas
# ---------------------------------------------------------------------------

class NgramMatch(BaseModel):
    """Result of exact N-gram matching between a document unit and a source page."""
    verified: bool = False
    matched_phrase: str = ""
    match_length: int = 0  # words
    ngram_hits: int = 0
    coverage: float = 0.0  # 0.0 - 1.0
    match_type: str = "none"  # "exact_phrase" | "partial_phrase" | "none"
    longest_exact_match_words: int = 0
    longest_matching_sequence: int = 0
    exact_word_overlap: float = 0.0
    matching_sentences: int = 0
    matching_paragraphs: int = 0
    ngram_10_hit: bool = False
    ngram_15_hit: bool = False
    ngram_20_hit: bool = False
    ngram_25_hit: bool = False



class FuzzyMatch(BaseModel):
    """Result of fuzzy/approximate matching."""
    token_similarity: float = 0.0  # Jaccard
    edit_distance: float = 0.0  # normalized Levenshtein
    token_set_ratio: float = 0.0
    sequence_ratio: float = 0.0  # difflib SequenceMatcher ratio
    overall_fuzzy_score: float = 0.0


class SemanticMatch(BaseModel):
    """Result of embedding-based semantic similarity."""
    cosine_similarity: float = 0.0
    embedding_model: str = "all-MiniLM-L6-v2"


class CandidateSource(BaseModel):
    """
    An isolated candidate source evaluated for a specific document sentence.
    No shared or mutable source variables between sentences.
    """
    sentence_id: str = Field(..., description="Target document sentence ID")
    query_id: str = Field("", description="Query ID that discovered this candidate")
    url: str
    canonical_url: str = ""
    title: str = "Web Source"
    search_rank: int = 0
    provider: str = ""
    scraped_text: Optional[str] = None
    exact_ngram_score: float = 0.0
    longest_match_words: int = 0
    lexical_similarity: float = 0.0
    fuzzy_similarity: float = 0.0
    entity_overlap: float = 0.0
    semantic_similarity: float = 0.0
    verification_status: VerificationStatus = VerificationStatus.NO_MATCH
    diagnosis: str = ""
    matching_sentences: int = 0
    matching_paragraphs: int = 0
    matched_phrase: str = ""
    identity: float = 0.0
    aligned_tokens: int = 0
    evidence: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Debug and Audit schemas
# ---------------------------------------------------------------------------

class CandidateAuditRecord(BaseModel):
    """Candidate verification snapshot for developer audit/debugging."""
    url: str
    title: str = ""
    exact_ngram_score: float = 0.0
    longest_match_words: int = 0
    fuzzy_similarity: float = 0.0
    semantic_similarity: float = 0.0
    entity_overlap: float = 0.0
    identity: float = 0.0
    aligned_tokens: int = 0
    status: str = "NO_MATCH"
    diagnosis: str = ""


class SentenceAudit(BaseModel):
    """Audit record tracing sentence -> queries -> candidates -> selected source."""
    sentence_id: str
    sentence_text: str = ""
    queries: List[str] = Field(default_factory=list)
    candidates: List[CandidateAuditRecord] = Field(default_factory=list)
    selected_source: Optional[str] = None
    selected_title: Optional[str] = None
    verification_status: str = "NO_MATCH"
    diagnosis: str = ""


# ---------------------------------------------------------------------------
# Evidence and scoring schemas
# ---------------------------------------------------------------------------

class SourceEvidence(BaseModel):
    """Breakdown of evidence signals for a single source match."""
    ngram_evidence: float = Field(0.0, description="0-100: Exact N-gram match strength")
    longest_span: float = Field(0.0, description="0-100: Longest consecutive match")
    sentence_similarity: float = Field(0.0, description="0-100: Sentence-level overlap")
    search_relevance: float = Field(0.0, description="0-100: Search rank & discovery count")
    semantic_similarity: float = Field(0.0, description="0-100: Embedding cosine sim")
    source_consistency: float = Field(0.0, description="0-100: Structure/order preservation")
    composite_score: float = Field(0.0, description="Weighted composite 0-100")


class SearchQueryRecord(BaseModel):
    """Audit record for a search query execution."""
    query: str
    provider: str
    result_count: int = 0
    latency_ms: int = 0
    retrieved_at: Optional[datetime] = None


class SourceMatch(BaseModel):
    """A verified source match with full evidence."""
    document_text: str = Field("", description="The matching text from the uploaded document")
    source_text: str = Field("", description="The matching text from the source webpage")
    source_url: str = ""
    source_title: str = ""
    match_type: MatchType = MatchType.EXACT
    matched_words: int = 0
    similarity: float = 0.0  # 0-100
    confidence: Confidence = Confidence.LOW
    evidence: SourceEvidence = Field(default_factory=SourceEvidence)
    reason: List[str] = Field(default_factory=list, description="Human-readable evidence chain")
    source_category: SourceCategory = SourceCategory.UNKNOWN
    verified: bool = False
    fetch_source: str = "full_page"
    matched_sentence_count: int = 0
    matched_sentences: List[str] = Field(default_factory=list)
    total_ngram_hits: int = 0
    authority_score: float = 0.0
    source_cluster_id: Optional[str] = None
    query_records: List[SearchQueryRecord] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.VERIFIED_WEB_MATCH
    entity_overlap: float = 0.0
    identity: float = 1.0
    aligned_tokens: int = 0
    edit_ops: int = 0
    diagnosis: str = ""
    sentence_id: str = ""

    def to_legacy_dict(self) -> Dict[str, Any]:
        """Convert to the legacy dict format expected by existing frontend/report code."""
        verif_str = self.verification_status.value if hasattr(self.verification_status, "value") else str(self.verification_status)
        return {
            "sentence": self.document_text,
            "source_title": self.source_title,
            "source_url": self.source_url,
            "snippet": self.source_text[:300],
            "similarity_score": self.similarity,
            "match_type": self.match_type.value,
            "verified": self.verified,
            "fetch_source": self.fetch_source,
            "matched_sentence_count": self.matched_sentence_count,
            "matched_sentences": self.matched_sentences[:5],
            "total_ngram_hits": self.total_ngram_hits,
            "authority_score": self.authority_score,
            "confidence": self.confidence.value,
            "evidence": self.evidence.model_dump(),
            "reason": self.reason,
            "source_category": self.source_category.value,
            "verification_status": verif_str,
            "entity_overlap": self.entity_overlap,
            "identity": self.identity,
            "aligned_tokens": self.aligned_tokens,
            "diagnosis": self.diagnosis,
            "matched_words": self.matched_words,
            "sentence_id": self.sentence_id,
        }


# ---------------------------------------------------------------------------
# Clustering schemas
# ---------------------------------------------------------------------------

class SourceCluster(BaseModel):
    """A group of URLs containing substantially identical content."""
    cluster_id: str
    urls: List[str] = Field(default_factory=list)
    likely_source: str = Field("", description="Best candidate for original source")
    evidence_for_precedence: List[str] = Field(default_factory=list)
    source_category: SourceCategory = SourceCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------

class PipelineOptions(BaseModel):
    """Configuration for a pipeline run."""
    search_depth: str = "standard"  # "quick" | "standard" | "deep"
    enable_semantic_matching: bool = True
    enable_fuzzy_matching: bool = True
    enable_source_clustering: bool = True
    ngram_size: int = 25
    max_sources_per_sentence: int = 10
    max_urls_to_fetch: int = 30
    page_fetch_timeout: float = 9.0
    search_timeout: float = 7.0


# ---------------------------------------------------------------------------
# Final result schema
# ---------------------------------------------------------------------------

class WebDetectionResult(BaseModel):
    """Final output of the web source detection pipeline."""
    total_sentences: int = 0
    matched_sentences: int = 0
    sources_found: int = 0
    web_score: float = 0.0  # 0-100
    verbatim_score: float = 0.0  # 0-100
    matches: List[SourceMatch] = Field(default_factory=list)
    clusters: List[SourceCluster] = Field(default_factory=list)
    sentence_audits: List[SentenceAudit] = Field(default_factory=list)
    search_queries_executed: int = 0
    pages_fetched: int = 0
    pipeline_options: PipelineOptions = Field(default_factory=PipelineOptions)

    def to_legacy_matches(self) -> List[Dict[str, Any]]:
        """Convert matches to the legacy list-of-dicts format for backward compatibility."""
        return [m.to_legacy_dict() for m in self.matches]

