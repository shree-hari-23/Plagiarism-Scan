"""
PlagiaScan Pipeline — Web Source Detection Orchestrator

Coordinates the entire multi-stage retrieval, verification, and attribution pipeline:
1. Sentence & Clause Segmentation
2. Distinctive Phrase Extraction
3. Multi-Strategy Query Generation
4. Multi-Engine Search Execution
5. URL Canonicalization & Balanced Selection
6. SSRF-Safe Webpage Fetching & Distillation
7. Multi-Engine Matching (N-gram, Fuzzy, Semantic)
8. False Positive & Boilerplate Filtering
9. Evidence Scoring & Confidence Classification
10. Source Clustering & Canonical Precedence Attribution
"""

import logging
import time
from typing import List, Dict, Optional, Tuple

from app.core.pipeline.schemas import (
    PipelineOptions,
    DocumentSentence,
    SearchQuery,
    SearchResult,
    CandidatePage,
    CandidateSource,
    CandidateAuditRecord,
    SentenceAudit,
    VerificationStatus,
    SourceMatch,
    SourceCluster,
    WebDetectionResult,
    Confidence,
    MatchType
)
from app.core.pipeline.entity_verifier import EntityVerifier

from app.core.pipeline.text_normalizer import TextNormalizer
from app.core.pipeline.segmenter import DocumentSegmenter
from app.core.pipeline.phrase_extractor import DistinctivePhraseExtractor
from app.core.pipeline.query_generator import QueryGenerator
from app.core.pipeline.search_providers import SearchProviderChain
from app.core.pipeline.url_manager import URLManager
from app.core.pipeline.page_fetcher import PageFetcher
from app.core.pipeline.ngram_matcher import NgramMatcher
from app.core.pipeline.fuzzy_matcher import FuzzyMatcher
from app.core.pipeline.semantic_matcher import SemanticMatcher
from app.core.pipeline.false_positive import FalsePositiveFilter
from app.core.pipeline.evidence_scorer import EvidenceScorer
from app.core.pipeline.source_clusterer import SourceClusterer
from app.core.pipeline.seed_extend import SeedAndExtendAligner, DocumentKgramIndex, AlignedSpan

logger = logging.getLogger("plagiascan.pipeline.orchestrator")


class WebSourceDetectionPipeline:
    """
    Production-grade multi-stage plagiarism detection and source attribution engine.
    """

    def __init__(self, options: Optional[PipelineOptions] = None):
        self.options = options or PipelineOptions()

        # Initialize sub-modules
        self.segmenter = DocumentSegmenter()
        self.phrase_extractor = DistinctivePhraseExtractor()
        self.query_generator = QueryGenerator(phrase_extractor=self.phrase_extractor)
        self.search_chain = SearchProviderChain()
        self.url_manager = URLManager()
        self.fetcher = PageFetcher(timeout=self.options.page_fetch_timeout)
        self.ngram_matcher = NgramMatcher(default_n=self.options.ngram_size)
        self.aligner = SeedAndExtendAligner(k=6, max_gap=8, theta=0.70)
        self.fuzzy_matcher = FuzzyMatcher() if self.options.enable_fuzzy_matching else None
        self.semantic_matcher = SemanticMatcher() if self.options.enable_semantic_matching else None
        self.evidence_scorer = EvidenceScorer()
        self.clusterer = SourceClusterer() if self.options.enable_source_clustering else None

    def run(self, full_text: str, chunks: Optional[List[str]] = None) -> WebDetectionResult:
        """
        Execute full detection and attribution pipeline on document text.
        """
        pipeline_start = time.time()
        logger.info("=" * 60)
        logger.info("[PIPELINE START] Beginning web source detection pipeline")
        logger.info("=" * 60)

        # -------------------------------------------------------------
        # STAGE 1: Segmentation
        # -------------------------------------------------------------
        doc_sentences = self.segmenter.segment(full_text, fallback_chunks=chunks)
        total_sentences = len(doc_sentences)
        logger.info(f"[STAGE 1] Segmented {total_sentences} document sentences and clauses")
        if not doc_sentences:
            return WebDetectionResult(pipeline_options=self.options)

        # -------------------------------------------------------------
        # STAGE 2: Query Generation
        # -------------------------------------------------------------
        num_query_sentences = 10 if self.options.search_depth != "deep" else 15
        queries: List[SearchQuery] = self.query_generator.generate_queries_for_document(
            doc_sentences,
            target_sentence_count=num_query_sentences
        )
        logger.info(f"[STAGE 2] Formulated {len(queries)} multi-strategy search queries")

        # -------------------------------------------------------------
        # STAGE 3: Multi-Provider Search Execution
        # -------------------------------------------------------------
        raw_search_results: List[SearchResult] = []
        all_query_records = []

        for q in queries:
            results, records = self.search_chain.execute_query(q, limit=4)
            raw_search_results.extend(results)
            all_query_records.extend(records)

        logger.info(f"[STAGE 3] Executed {len(queries)} queries, discovered {len(raw_search_results)} raw search hits")

        if not raw_search_results:
            empty_audits = [
                SentenceAudit(
                    sentence_id=s.sentence_id,
                    sentence_text=s.text,
                    queries=[q.text for q in queries if q.source_sentence_id == s.sentence_id],
                    candidates=[],
                    selected_source=None,
                    verification_status="NO_MATCH",
                    diagnosis="No search results discovered."
                ) for s in doc_sentences if not s.is_clause and s.word_count >= 5
            ]
            return WebDetectionResult(
                total_sentences=total_sentences,
                search_queries_executed=len(queries),
                sentence_audits=empty_audits,
                pipeline_options=self.options
            )

        # -------------------------------------------------------------
        # STAGE 4: URL Canonicalization & Balanced Selection
        # -------------------------------------------------------------
        selected_candidates = self.url_manager.select_balanced_candidates(
            raw_search_results,
            max_urls=self.options.max_urls_to_fetch,
            queries=queries
        )
        logger.info(f"[STAGE 4] Selected {len(selected_candidates)} unique canonical candidate URLs for verification")

        # -------------------------------------------------------------
        # STAGE 5: SSRF-Safe Concurrent Webpage Fetching & Distillation
        # -------------------------------------------------------------
        fetched_pages: List[CandidatePage] = self.fetcher.fetch_pages_concurrent(
            selected_candidates,
            max_workers=min(6, len(selected_candidates) or 1)
        )

        logger.info(f"[STAGE 5] Successfully fetched and distilled {len(fetched_pages)} candidate pages")
        if not fetched_pages:
            empty_audits = [
                SentenceAudit(
                    sentence_id=s.sentence_id,
                    sentence_text=s.text,
                    queries=[q.text for q in queries if q.source_sentence_id == s.sentence_id],
                    candidates=[],
                    selected_source=None,
                    verification_status="NO_MATCH",
                    diagnosis="No candidate pages successfully retrieved."
                ) for s in doc_sentences if not s.is_clause and s.word_count >= 5
            ]
            return WebDetectionResult(
                total_sentences=total_sentences,
                search_queries_executed=len(queries),
                pages_fetched=0,
                sentence_audits=empty_audits,
                pipeline_options=self.options
            )


        # -------------------------------------------------------------
        # STAGE 6: Isolated Candidate Source Verification Per Sentence
        # -------------------------------------------------------------
        # Comparison units: all primary sentences with >= 5 words
        comparison_units = [s for s in doc_sentences if not s.is_clause and s.word_count >= 5]
        if not comparison_units:
            comparison_units = doc_sentences

        sentence_queries_map: Dict[str, List[SearchQuery]] = {}
        for q in queries:
            sentence_queries_map.setdefault(q.source_sentence_id, []).append(q)

        sentence_audits: List[SentenceAudit] = []
        # Group attribution: url -> list of {sentence, cand, page, ng_match, fuz_match, sem_match}
        url_attribution_map: Dict[str, List[Dict[str, Any]]] = {}

        # Pre-tokenize page contents for seed-and-extend alignment
        page_tokens_map: Dict[str, List[str]] = {
            page.url: TextNormalizer.normalize(page.content).split()
            for page in fetched_pages
        }

        for unit in comparison_units:
            cand_audit_records: List[CandidateAuditRecord] = []
            evaluated_candidates: List[CandidateSource] = []
            candidate_details: Dict[str, Dict[str, Any]] = {}

            unit_index = DocumentKgramIndex(unit.text, k=min(6, max(3, unit.word_count)))

            for page in fetched_pages:
                page_rank = 1
                query_id = ""
                for sr in raw_search_results:
                    if sr.url == page.url or sr.canonical_url == page.canonical_url:
                        page_rank = sr.search_rank or 1
                        query_id = sr.discovered_by[0] if sr.discovered_by else ""
                        break

                # 4. CANDIDATE OBJECT: Isolated object per candidate
                cand = CandidateSource(
                    sentence_id=unit.sentence_id,
                    query_id=query_id,
                    url=page.url,
                    canonical_url=page.canonical_url or page.url,
                    title=page.title or "Web Source",
                    search_rank=page_rank,
                    provider=getattr(page, "fetch_source", "web"),
                    scraped_text=page.content
                )

                # 7. EXACT TEXT & SEED-AND-EXTEND VERIFICATION
                ng_match = self.ngram_matcher.match(unit.text, page.content)
                cand.exact_ngram_score = ng_match.coverage
                cand.longest_match_words = ng_match.longest_exact_match_words
                cand.matching_sentences = ng_match.matching_sentences
                cand.matching_paragraphs = ng_match.matching_paragraphs
                cand.matched_phrase = ng_match.matched_phrase

                # Seed-and-Extend Alignment (Edit-Tolerant)
                page_tokens = page_tokens_map.get(page.url, [])
                aligned_spans = self.aligner.align(unit_index.doc_tokens, unit_index, page_tokens) if page_tokens else []
                best_span = max(aligned_spans, key=lambda s: (s.identity, s.matched_tokens, s.longest_exact_run)) if aligned_spans else None

                if best_span:
                    cand.longest_match_words = max(cand.longest_match_words, best_span.longest_exact_run)
                    cand.identity = best_span.identity
                    cand.aligned_tokens = best_span.aligned_tokens
                    if best_span.matched_tokens >= 8:
                        cand.exact_ngram_score = max(cand.exact_ngram_score, best_span.identity)
                    if best_span.src_excerpt and (not cand.matched_phrase or len(best_span.src_excerpt) > len(cand.matched_phrase)):
                        cand.matched_phrase = best_span.src_excerpt

                    # Update ng_match metrics so downstream evidence scoring incorporates seed-and-extend
                    ng_match.longest_exact_match_words = max(ng_match.longest_exact_match_words, best_span.longest_exact_run)
                    ng_match.longest_matching_sequence = max(ng_match.longest_matching_sequence, best_span.matched_tokens)
                    if best_span.identity >= 0.70 and best_span.matched_tokens >= 8:
                        ng_match.coverage = max(ng_match.coverage, best_span.identity)
                        ng_match.matched_phrase = best_span.src_excerpt or ng_match.matched_phrase

                # Fuzzy lexical matching
                fuz_match = None
                if self.fuzzy_matcher:
                    fuz_match = self.fuzzy_matcher.match(unit.text, page.content[:4000])
                    cand.fuzzy_similarity = fuz_match.overall_fuzzy_score
                    cand.lexical_similarity = fuz_match.token_similarity

                # 11. ENTITY AND TOPIC CONSISTENCY
                entity_overlap = EntityVerifier.compute_overlap(unit.text, page.content, candidate_title=page.title)
                cand.entity_overlap = entity_overlap

                # 8. SEMANTIC SIMILARITY (Supporting signal only, never standalone proof)
                sem_match = None
                if self.semantic_matcher and (ng_match.verified or cand.fuzzy_similarity >= 0.35 or entity_overlap >= 0.20):
                    sem_match = self.semantic_matcher.match(unit.text, page.content[:1500])
                    cand.semantic_similarity = sem_match.cosine_similarity

                # 9 & 10. VERIFICATION RULES
                # Priority:
                # 1. Exact N-gram overlap
                # 2. Seed-and-Extend edit-tolerant alignment span
                # 3. Long consecutive textual overlap
                # 4. Strong fuzzy lexical overlap
                # 5. Entity/topic overlap
                # 6. Semantic similarity

                is_exact_overlap = (
                    (cand.longest_match_words >= 8 and cand.exact_ngram_score >= 0.35) or
                    (cand.longest_match_words >= 12) or
                    (ng_match.ngram_10_hit and cand.entity_overlap >= 0.15) or
                    (cand.longest_match_words >= min(unit.word_count, 8) and ng_match.exact_word_overlap >= 0.65)
                ) and (cand.entity_overlap >= 0.15 or cand.longest_match_words >= 15)

                is_aligned_overlap = (
                    best_span is not None and
                    best_span.matched_tokens >= 8 and
                    (
                        (best_span.longest_exact_run >= 10 and (cand.entity_overlap >= 0.15 or best_span.longest_exact_run >= 14)) or
                        (best_span.aligned_tokens >= 15 and best_span.identity >= 0.75 and cand.entity_overlap >= 0.20) or
                        (best_span.matched_tokens >= min(unit.word_count, 8) and best_span.identity >= 0.70 and cand.entity_overlap >= 0.15)
                    )
                )

                is_fuzzy_overlap = (
                    cand.fuzzy_similarity >= 0.65 and
                    cand.lexical_similarity >= 0.40 and
                    cand.entity_overlap >= 0.35
                )

                if is_exact_overlap or is_aligned_overlap:
                    cand.verification_status = VerificationStatus.VERIFIED_WEB_MATCH
                    ng_match.verified = True
                    if best_span and best_span.identity < 0.95 and best_span.longest_exact_run < 14:
                        cand.diagnosis = f"Modified textual overlap verified ({best_span.matched_tokens}/{best_span.aligned_tokens} tokens, {int(best_span.identity*100)}% identity)."
                    else:
                        cand.diagnosis = f"Direct textual overlap verified ({cand.longest_match_words} words continuous match)."
                elif is_fuzzy_overlap:
                    cand.verification_status = VerificationStatus.VERIFIED_WEB_MATCH
                    cand.diagnosis = "Strong textual similarity detected."
                elif cand.semantic_similarity >= 0.72 and cand.entity_overlap >= 0.25:
                    cand.verification_status = VerificationStatus.POSSIBLE_RELATED_SOURCE
                    cand.diagnosis = "Semantic similarity detected; direct textual copying was not verified."
                else:
                    cand.verification_status = VerificationStatus.NO_MATCH
                    cand.diagnosis = "No significant overlap detected."

                # False positive / boilerplate filter
                if cand.verification_status == VerificationStatus.VERIFIED_WEB_MATCH:
                    suppress, reason_supp = FalsePositiveFilter.should_suppress_match(
                        cand.matched_phrase or unit.text,
                        cand.longest_match_words,
                        page.final_url or page.url
                    )
                    if suppress:
                        cand.verification_status = VerificationStatus.NO_MATCH
                        cand.diagnosis = f"Filtered: {reason_supp}"

                cand_audit_records.append(CandidateAuditRecord(
                    url=cand.url,
                    title=cand.title,
                    exact_ngram_score=round(cand.exact_ngram_score, 4),
                    longest_match_words=cand.longest_match_words,
                    fuzzy_similarity=round(cand.fuzzy_similarity, 4),
                    semantic_similarity=round(cand.semantic_similarity, 4),
                    entity_overlap=round(cand.entity_overlap, 4),
                    identity=round(cand.identity, 4),
                    aligned_tokens=cand.aligned_tokens,
                    status=cand.verification_status.value,
                    diagnosis=cand.diagnosis
                ))

                evaluated_candidates.append(cand)
                candidate_details[cand.url] = {
                    "sentence": unit,
                    "cand": cand,
                    "page": page,
                    "ng_match": ng_match,
                    "fuz_match": fuz_match,
                    "sem_match": sem_match
                }

            # 15. SOURCE RANKING per sentence
            valid_candidates = [c for c in evaluated_candidates if c.verification_status != VerificationStatus.NO_MATCH]
            best_candidate: Optional[CandidateSource] = None

            if valid_candidates:
                def _cand_rank_score(c: CandidateSource) -> float:
                    rank = 0.0
                    if c.verification_status == VerificationStatus.VERIFIED_WEB_MATCH:
                        rank += 1000.0
                    elif c.verification_status == VerificationStatus.POSSIBLE_RELATED_SOURCE:
                        rank += 100.0
                    else:
                        return -1.0

                    # Lexical & alignment evidence dominates
                    rank += c.longest_match_words * 15.0
                    rank += c.exact_ngram_score * 50.0
                    rank += c.identity * 25.0
                    rank += c.entity_overlap * 30.0
                    rank += c.fuzzy_similarity * 20.0
                    rank += EvidenceScorer.compute_authority_score(c.url) * 0.1
                    # Semantic & rank are tie-breakers only
                    rank += c.semantic_similarity * 5.0
                    rank -= min(c.search_rank, 10) * 0.2
                    return rank

                valid_candidates.sort(key=_cand_rank_score, reverse=True)

                # Automated 'Fetch & Verify' Gate: loop through candidates in rank order
                # Never display or attribute a link without programmatically confirming
                # it is alive (HTTP 200) and contains the document text.
                for cand_item in valid_candidates:
                    cand_page = candidate_details[cand_item.url]["page"]
                    if PageFetcher.verify_source_url(unit.text, cand_item.url, page=cand_page):
                        best_candidate = cand_item
                        break
                    else:
                        logger.info(f"[FETCH & VERIFY REJECTED] {cand_item.url} for sentence {unit.sentence_id} (broken link or missing text)")

            # 21. DEBUGGING / AUDIT RECORD
            unit_queries = [q.text for q in sentence_queries_map.get(unit.sentence_id, [])]
            sentence_audits.append(SentenceAudit(
                sentence_id=unit.sentence_id,
                sentence_text=unit.text,
                queries=unit_queries,
                candidates=cand_audit_records,
                selected_source=best_candidate.url if best_candidate else None,
                selected_title=best_candidate.title if best_candidate else None,
                verification_status=best_candidate.verification_status.value if best_candidate else "NO_MATCH",
                diagnosis=best_candidate.diagnosis if best_candidate else "No significant overlap detected."
            ))

            if best_candidate and best_candidate.verification_status != VerificationStatus.NO_MATCH:
                target_url = best_candidate.url
                url_attribution_map.setdefault(target_url, []).append(candidate_details[target_url])

        # -------------------------------------------------------------
        # STAGE 6.5: Adaptive Probing — Phase 2 Dense Expansion
        # -------------------------------------------------------------
        verified_unit_indices = set()
        for idx, unit in enumerate(comparison_units):
            if any(unit.sentence_id == item["sentence"].sentence_id for items in url_attribution_map.values() for item in items):
                verified_unit_indices.add(idx)

        if (
            verified_unit_indices and
            len(fetched_pages) < self.options.max_urls_to_fetch and
            self.options.search_depth != "quick"
        ):
            adjacent_unmatched = []
            for v_idx in sorted(verified_unit_indices):
                for adj_idx in [v_idx - 1, v_idx + 1]:
                    if 0 <= adj_idx < len(comparison_units) and adj_idx not in verified_unit_indices:
                        if adj_idx not in adjacent_unmatched:
                            adjacent_unmatched.append(adj_idx)

            if adjacent_unmatched and len(queries) < (num_query_sentences + 4):
                probes_to_run = adjacent_unmatched[:2]
                logger.info(f"[STAGE 6.5] Phase 2 Dense Expansion: probing {len(probes_to_run)} adjacent sentences")
                p2_queries = []
                for adj_i in probes_to_run:
                    adj_unit = comparison_units[adj_i]
                    gen_q = self.query_generator.generate_queries_for_sentence(adj_unit, sentence_idx=100 + adj_i)
                    p2_queries.extend(gen_q[:1])

                p2_raw_results = []
                for q in p2_queries:
                    res, recs = self.search_chain.execute_query(q, limit=3)
                    p2_raw_results.extend(res)
                    all_query_records.extend(recs)
                queries.extend(p2_queries)

                if p2_raw_results:
                    p2_selected = self.url_manager.select_balanced_candidates(
                        p2_raw_results,
                        max_urls=max(1, self.options.max_urls_to_fetch - len(fetched_pages)),
                        queries=p2_queries
                    )
                    for cand_res in p2_selected:
                        if not any(fp.url == cand_res.url or fp.canonical_url == cand_res.canonical_url for fp in fetched_pages):
                            page = self.fetcher.fetch_page(cand_res)
                            if page and page.word_count >= 10:
                                fetched_pages.append(page)
                                page_tokens_map[page.url] = TextNormalizer.normalize(page.content).split()

        logger.info(f"[STAGE 6] Verified and attributed sentences across {len(url_attribution_map)} web sources")

        # -------------------------------------------------------------
        # STAGE 7 & 8: Evidence Scoring & Source Attribution
        # -------------------------------------------------------------
        raw_source_matches: List[SourceMatch] = []

        for url, items in url_attribution_map.items():
            # Pick item with highest continuous match length
            best_item = max(items, key=lambda x: (
                1 if x["cand"].verification_status == VerificationStatus.VERIFIED_WEB_MATCH else 0,
                x["cand"].longest_match_words,
                x["cand"].exact_ngram_score
            ))

            page: CandidatePage = best_item["page"]
            cand: CandidateSource = best_item["cand"]
            ng_match: NgramMatch = best_item["ng_match"]
            fuz_match: Optional[FuzzyMatch] = best_item["fuz_match"]
            sem_match: Optional[SemanticMatch] = best_item["sem_match"]

            matched_sentences = [it["sentence"].text for it in items]
            best_doc_sent = best_item["sentence"].text
            best_phrase = cand.matched_phrase or page.content[:300]
            total_ngram_hits = sum(it["ng_match"].ngram_hits for it in items if it["ng_match"])

            search_rank = cand.search_rank
            disco_count = len(page.source_sentence_ids)

            # Canonical inspection: If candidate page header links to an authoritative origin, attribute that target
            target_source_url = page.final_url or url
            if page.canonical_url and page.canonical_url.startswith("http"):
                from urllib.parse import urlparse
                parsed_canon = urlparse(page.canonical_url)
                parsed_curr = urlparse(target_source_url)
                if parsed_canon.netloc and parsed_canon.netloc != parsed_curr.netloc:
                    canon_auth = EvidenceScorer.compute_authority_score(page.canonical_url)
                    curr_auth = EvidenceScorer.compute_authority_score(target_source_url)
                    if canon_auth >= curr_auth or any(ind in page.canonical_url.lower() for ind in ['.org', '.edu', 'docs.', 'palletsprojects.com']):
                        logger.info(f"[CANONICAL REDIRECT] Attributing canonical origin {page.canonical_url} instead of mirror {target_source_url}")
                        target_source_url = page.canonical_url

            authority_score = EvidenceScorer.compute_authority_score(
                target_source_url,
                fetch_source=page.fetch_source
            )
            source_cat = EvidenceScorer.categorize_source(target_source_url)

            evidence, confidence, match_type, similarity, reasons = self.evidence_scorer.evaluate_match(
                ngram_match=ng_match,
                fuzzy_match=fuz_match,
                semantic_match=sem_match,
                matched_sentences_count=len(matched_sentences),
                search_rank=search_rank,
                discovered_by_count=disco_count,
                url=target_source_url,
                fetch_source=page.fetch_source
            )

            is_verified = (cand.verification_status == VerificationStatus.VERIFIED_WEB_MATCH)
            if not is_verified and cand.verification_status == VerificationStatus.POSSIBLE_RELATED_SOURCE:
                match_type = MatchType.SEMANTIC
                confidence = Confidence.LOW

            source_match = SourceMatch(
                document_text=best_doc_sent,
                source_text=best_phrase[:400],
                source_url=target_source_url,
                source_title=page.title or cand.title or "Web Source",
                match_type=match_type,
                matched_words=cand.longest_match_words,
                similarity=similarity,
                confidence=confidence,
                evidence=evidence,
                reason=reasons,
                source_category=source_cat,
                verified=is_verified,
                verification_status=cand.verification_status,
                entity_overlap=cand.entity_overlap,
                identity=cand.identity if cand.identity > 0 else 1.0,
                aligned_tokens=cand.aligned_tokens,
                edit_ops=max(0, cand.aligned_tokens - cand.longest_match_words),
                diagnosis=cand.diagnosis,
                fetch_source=page.fetch_source,
                matched_sentence_count=len(matched_sentences),
                matched_sentences=matched_sentences[:5],
                total_ngram_hits=total_ngram_hits,
                authority_score=round(authority_score, 2),
                query_records=all_query_records,
                sentence_id=best_item["sentence"].sentence_id
            )
            raw_source_matches.append(source_match)


        # -------------------------------------------------------------
        # STAGE 9: Source Clustering & Precedence Attribution
        # -------------------------------------------------------------
        clusters: List[SourceCluster] = []
        if self.clusterer and raw_source_matches:
            clusters = self.clusterer.cluster_matches(raw_source_matches)

        # Sort matches by authority score and confidence
        def _sort_key(m: SourceMatch) -> float:
            score = m.authority_score
            if m.confidence == Confidence.HIGH:
                score += 50.0
            elif m.confidence == Confidence.MEDIUM:
                score += 25.0
            score += m.matched_words * 1.0
            return score

        raw_source_matches.sort(key=_sort_key, reverse=True)

        # -------------------------------------------------------------
        # STAGE 10: Overall Score Calculation & Final Result
        # -------------------------------------------------------------
        total_chunks = max(len(chunks) if chunks else len(comparison_units), 1)
        matched_chunk_count = 0
        verbatim_chunk_count = 0

        eval_units = chunks if chunks else [u.text for u in comparison_units]

        for chunk_text in eval_units:
            norm_chunk = TextNormalizer.normalize(chunk_text)
            chunk_matched = False
            chunk_verbatim = False

            for m in raw_source_matches:
                for ms in m.matched_sentences:
                    norm_ms = TextNormalizer.normalize(ms)
                    tokens_ms = norm_ms.split()
                    sample = ' '.join(tokens_ms[:min(10, len(tokens_ms))])
                    if sample and sample in norm_chunk:
                        chunk_matched = True
                        if m.confidence == Confidence.HIGH or m.matched_words >= 20:
                            chunk_verbatim = True
                        break
                if chunk_matched:
                    break

            if chunk_matched:
                matched_chunk_count += 1
            if chunk_verbatim:
                verbatim_chunk_count += 1

        if matched_chunk_count == 0 and raw_source_matches:
            matched_chunk_count = min(len(raw_source_matches), total_chunks)
            verbatim_chunk_count = matched_chunk_count

        web_score = round(min(100.0, (matched_chunk_count / total_chunks) * 100), 2)
        verbatim_score = round(min(100.0, (verbatim_chunk_count / total_chunks) * 100), 2)

        elapsed = round(time.time() - pipeline_start, 2)
        logger.info("=" * 60)
        logger.info(
            f"[PIPELINE COMPLETED] Elapsed: {elapsed}s | Matches: {len(raw_source_matches)} | "
            f"Web Score: {web_score}% | Verbatim: {verbatim_score}%"
        )
        logger.info("=" * 60)

        return WebDetectionResult(
            total_sentences=total_sentences,
            matched_sentences=matched_chunk_count,
            sources_found=len(raw_source_matches),
            web_score=web_score,
            verbatim_score=verbatim_score,
            matches=raw_source_matches,
            clusters=clusters,
            sentence_audits=sentence_audits,
            search_queries_executed=len(queries),
            pages_fetched=len(fetched_pages),
            pipeline_options=self.options
        )

