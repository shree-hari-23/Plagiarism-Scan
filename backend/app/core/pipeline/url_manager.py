"""
PlagiaScan Pipeline — URL Manager

URL canonicalization, tracking parameter stripping, deduplication,
and balanced round-robin source selection across document sections.
"""

import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import List, Dict, Set, Optional
from app.core.pipeline.schemas import SearchResult, SearchQuery
from app.core.pipeline.text_normalizer import TextNormalizer
from app.core.pipeline.entity_verifier import STOP_WORDS


class URLManager:
    """
    Manages URL canonicalization, deduplication, and budget selection.
    """

    # Tracking parameters to strip from URLs
    TRACKING_PARAMS = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'gclid', 'gclsrc', 'msclkid', 'fbclid', 'ref', 'ref_', 'referrer',
        'source', 'spm', 'igshid', 'mc_cid', 'mc_eid', 'yclid', '_hsenc',
        '_hsmi', 'mkt_tok'
    }

    # Domains to penalize during candidate selection (generic republishers, scraper blogs, social aggregators)
    PENALIZED_DOMAINS = {
        'pinterest.com', 'quora.com', 'facebook.com', 'twitter.com',
        'instagram.com', 'linkedin.com', 'tiktok.com', 'medium.com',
        'blogspot.com', 'wordpress.com', 'substack.com'
    }

    # Domains / paths that indicate authoritative documentation
    DOCUMENTATION_INDICATORS = [
        '/docs/', '/doc/', '/documentation/', '/stable/', '/latest/',
        '/en/stable/', '/en/latest/', '/api/', '/wiki/', '/tutorial/',
        'palletsprojects.com', 'pega.com', 'python.org', 'readthedocs.io',
        'docs.', 'devdocs.io', 'agentic-ai'
    ]

    @classmethod
    def canonicalize_url(cls, raw_url: str) -> str:
        """
        Produce a canonical representation of a URL.
        1. Remove fragments (#section)
        2. Lowercase scheme and netloc
        3. Remove trailing slashes (except root '/')
        4. Strip tracking parameters (utm_*, gclid, msclkid, etc.)
        5. Sort remaining query parameters
        """
        if not raw_url:
            return ""

        try:
            parsed = urlparse(raw_url.strip())
            scheme = parsed.scheme.lower() if parsed.scheme else "https"
            netloc = parsed.netloc.lower()

            # Strip default ports
            if netloc.endswith(":80"):
                netloc = netloc[:-3]
            elif netloc.endswith(":443"):
                netloc = netloc[:-4]

            # Clean path
            path = parsed.path
            if len(path) > 1 and path.endswith('/'):
                path = path.rstrip('/')

            # Strip tracking query params
            filtered_query = []
            if parsed.query:
                for k, v in parse_qsl(parsed.query, keep_blank_values=True):
                    if k.lower() not in cls.TRACKING_PARAMS and not k.lower().startswith('utm_'):
                        filtered_query.append((k, v))
                filtered_query.sort(key=lambda x: x[0])

            clean_query = urlencode(filtered_query)

            # Reconstruct URL without fragment
            clean_url = urlunparse((scheme, netloc, path, parsed.params, clean_query, ''))
            return clean_url
        except Exception:
            return raw_url.strip()

    @classmethod
    def compute_snippet_overlap(cls, snippet: str, probe_text: str) -> float:
        """
        Compute token-level lexical overlap ratio between search snippet and probe phrase/sentence.
        Ignores stopwords to measure substantive semantic overlap.
        """
        if not snippet or not probe_text:
            return 0.0

        snip_norm = TextNormalizer.normalize(snippet)
        probe_norm = TextNormalizer.normalize(probe_text)

        snip_tokens = set(snip_norm.split())
        probe_tokens = [t for t in probe_norm.split() if t not in STOP_WORDS]
        if not probe_tokens:
            probe_tokens = probe_norm.split()
        if not probe_tokens:
            return 0.0

        matched = sum(1 for t in probe_tokens if t in snip_tokens)
        return round(matched / len(probe_tokens), 4)

    @classmethod
    def compute_title_overlap(cls, title: str, probe_text: str) -> float:
        """
        Compute token-level lexical overlap ratio between search result title and probe phrase/sentence.
        Ignores stopwords to measure substantive semantic overlap.
        """
        if not title or not probe_text:
            return 0.0

        title_norm = TextNormalizer.normalize(title)
        probe_norm = TextNormalizer.normalize(probe_text)

        title_tokens = set(title_norm.split())
        probe_tokens = [t for t in probe_norm.split() if t not in STOP_WORDS]
        if not probe_tokens:
            probe_tokens = probe_norm.split()
        if not probe_tokens:
            return 0.0

        matched = sum(1 for t in probe_tokens if t in title_tokens)
        return round(matched / len(probe_tokens), 4)

    @classmethod
    def deduplicate_results(cls, results: List[SearchResult]) -> List[SearchResult]:
        """
        Deduplicate search results by canonical URL while merging discovered_by metadata.
        """
        deduped_map: Dict[str, SearchResult] = {}

        for r in results:
            canon = cls.canonicalize_url(r.url)
            r.canonical_url = canon

            if canon in deduped_map:
                existing = deduped_map[canon]
                for q_id in r.discovered_by:
                    if q_id not in existing.discovered_by:
                        existing.discovered_by.append(q_id)
                # Keep earliest search rank or higher relevance
                if r.search_rank > 0 and (existing.search_rank == 0 or r.search_rank < existing.search_rank):
                    existing.search_rank = r.search_rank
                if not existing.snippet and r.snippet:
                    existing.snippet = r.snippet
            else:
                deduped_map[canon] = r

        return list(deduped_map.values())

    @classmethod
    def select_balanced_candidates(
        cls,
        results: List[SearchResult],
        max_urls: int = 35,
        queries: Optional[List[SearchQuery]] = None
    ) -> List[SearchResult]:
        """
        Select up to max_urls candidate pages using cross-query URL voting,
        snippet pre-screening, title overlap, and balanced round-robin across document sentences.
        """
        deduped = cls.deduplicate_results(results)

        # Map query_id -> probe phrase / sentence info for snippet pre-screening
        query_probe_map: Dict[str, str] = {}
        query_sentence_map: Dict[str, str] = {}
        if queries:
            for q in queries:
                probe = q.source_phrase or q.text.replace('"', '')
                query_probe_map[q.query_id] = probe
                if q.source_sentence_id:
                    query_sentence_map[q.query_id] = q.source_sentence_id

        # Always compute probe votes, snippet overlap, and title overlap per candidate
        for r in deduped:
            # Determine distinct probe sentences that hit this URL
            probes: Set[str] = set()
            if r.source_sentence_id:
                probes.add(r.source_sentence_id)
            for q_id in r.discovered_by:
                if q_id in query_sentence_map:
                    probes.add(query_sentence_map[q_id])
                elif q_id:
                    probes.add(q_id)
            r.probe_votes = max(1, len(probes))

            # Snippet & title pre-screen overlap
            max_snip_overlap = 0.0
            max_title_overlap = 0.0
            if query_probe_map:
                for q_id in r.discovered_by:
                    if q_id in query_probe_map:
                        probe_str = query_probe_map[q_id]
                        if r.snippet:
                            overlap = cls.compute_snippet_overlap(r.snippet, probe_str)
                            max_snip_overlap = max(max_snip_overlap, overlap)
                        if r.title:
                            t_overlap = cls.compute_title_overlap(r.title, probe_str)
                            max_title_overlap = max(max_title_overlap, t_overlap)
            r.snippet_overlap = max_snip_overlap
            r.title_overlap = max_title_overlap

        # Hard filter: Eliminate obvious false positives (0 snippet AND 0 title overlap, low rank, single probe)
        # Authoritative documentation domains are protected from overly aggressive filtering
        filtered_deduped: List[SearchResult] = []
        for r in deduped:
            is_doc_site = any(ind in r.url.lower() for ind in cls.DOCUMENTATION_INDICATORS)
            if (
                r.snippet_overlap == 0.0
                and r.title_overlap == 0.0
                and r.probe_votes == 1
                and r.search_rank > 2
                and not is_doc_site
            ):
                continue
            filtered_deduped.append(r)

        if filtered_deduped:
            deduped = filtered_deduped

        # Sort each candidate using cross-query votes, snippet pre-screen, title overlap, and domain authority
        def _candidate_priority(res: SearchResult) -> float:
            score = 10.0
            url_lower = res.url.lower()

            for doc_ind in cls.DOCUMENTATION_INDICATORS:
                if doc_ind in url_lower:
                    score += 20.0
                    break

            parsed = urlparse(url_lower)
            domain = parsed.netloc

            # Official project sites & documentation domains
            if any(term in domain for term in ['palletsprojects.com', 'pega.com', 'python.org', 'readthedocs.io', 'gitbook.io', 'docs.', 'devdocs.io']):
                score += 25.0

            if any(pen in domain for pen in cls.PENALIZED_DOMAINS):
                score -= 25.0
            if 'wikipedia.org' in domain:
                score += 8.0
            if 'github.com' in domain or 'gitlab.com' in domain:
                score += 12.0
            if domain.endswith('.edu') or domain.endswith('.gov') or domain.endswith('.org'):
                score += 5.0

            # Rank bonus
            if res.search_rank > 0:
                score += max(0, 5 - res.search_rank) * 2.0

            # Cross-query voting bonus (multiple independent probes hitting the same URL)
            score += res.probe_votes * 12.0

            # Title overlap bonus
            if res.title_overlap >= 0.50:
                score += 15.0
            elif res.title_overlap >= 0.25:
                score += 8.0

            # Snippet pre-screen bonus / penalty
            if res.snippet_overlap >= 0.70:
                score += 20.0
            elif res.snippet_overlap >= 0.40:
                score += 10.0
            elif res.snippet_overlap == 0.0 and res.title_overlap == 0.0 and res.probe_votes == 1 and res.search_rank > 3:
                # Uncorroborated, low-rank, zero snippet and title overlap -> deprioritize
                score -= 30.0

            return score

        if len(deduped) <= max_urls:
            deduped.sort(key=_candidate_priority, reverse=True)
            return deduped

        # Group by source sentence
        by_sentence: Dict[str, List[SearchResult]] = {}
        no_sentence: List[SearchResult] = []

        for r in deduped:
            s_id = r.source_sentence_id or (r.discovered_by[0] if r.discovered_by else "unknown")
            if s_id:
                by_sentence.setdefault(s_id, []).append(r)
            else:
                no_sentence.append(r)

        for s_id in by_sentence:
            by_sentence[s_id].sort(key=_candidate_priority, reverse=True)

        # Round-robin selection with domain diversity cap
        selected: List[SearchResult] = []
        selected_urls: Set[str] = set()
        domain_counts: Dict[str, int] = {}
        max_per_domain = 3

        active_keys = list(by_sentence.keys())
        round_num = 0

        while len(selected) < max_urls and active_keys:
            next_keys = []
            for k in active_keys:
                items = by_sentence[k]
                if round_num < len(items):
                    item = items[round_num]
                    dom = urlparse(item.canonical_url.lower()).netloc
                    # If this domain already reached the round-robin cap, skip to allow other sources
                    if item.canonical_url not in selected_urls and domain_counts.get(dom, 0) < max_per_domain:
                        selected.append(item)
                        selected_urls.add(item.canonical_url)
                        domain_counts[dom] = domain_counts.get(dom, 0) + 1
                        if len(selected) >= max_urls:
                            break
                    next_keys.append(k)
            active_keys = next_keys
            round_num += 1

        # If budget remains, fill with remaining high-priority items regardless of domain cap
        if len(selected) < max_urls:
            remaining = [r for r in deduped if r.canonical_url not in selected_urls]
            remaining.sort(key=_candidate_priority, reverse=True)
            for r in remaining:
                if len(selected) >= max_urls:
                    break
                selected.append(r)
                selected_urls.add(r.canonical_url)

        return selected
