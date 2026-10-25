"""
PlagiaScan Pipeline — Source Clusterer

Clusters duplicate and mirror sources and determines canonical source attribution:
- Groups candidate URLs with substantially identical matching text
- Resolves conflicts between official documentation vs. GitHub mirrors/aggregators
- Selects the most authoritative likely_source with transparent precedence evidence
"""

import re
from typing import List, Dict
from difflib import SequenceMatcher

from app.core.pipeline.schemas import SourceMatch, SourceCluster
from app.core.pipeline.evidence_scorer import EvidenceScorer
from app.core.pipeline.text_normalizer import TextNormalizer


class SourceClusterer:
    """
    Identifies duplicate/mirror webpages and designates canonical source attribution.
    """

    def __init__(self, match_similarity_threshold: float = 0.80):
        self.match_similarity_threshold = match_similarity_threshold

    def cluster_matches(self, matches: List[SourceMatch]) -> List[SourceCluster]:
        """
        Group matches by text similarity and identify canonical source for each cluster.
        Updates each match with its source_cluster_id.
        """
        if not matches:
            return []

        clusters: List[SourceCluster] = []
        cluster_counter = 1
        assigned = set()

        for i, match_a in enumerate(matches):
            if i in assigned:
                continue

            current_group: List[SourceMatch] = [match_a]
            assigned.add(i)
            norm_a = TextNormalizer.normalize(match_a.source_text or match_a.document_text)

            for j, match_b in enumerate(matches[i + 1:], start=i + 1):
                if j in assigned:
                    continue

                norm_b = TextNormalizer.normalize(match_b.source_text or match_b.document_text)
                sim = SequenceMatcher(None, norm_a, norm_b).ratio()

                if sim >= self.match_similarity_threshold:
                    current_group.append(match_b)
                    assigned.add(j)

            # Determine precedence within current_group
            cluster_id = f"cluster_{cluster_counter:03d}"
            cluster_counter += 1

            best_match, precedence_reasons = self._select_canonical_source(current_group)

            for m in current_group:
                m.source_cluster_id = cluster_id

            cluster = SourceCluster(
                cluster_id=cluster_id,
                urls=[m.source_url for m in current_group],
                likely_source=best_match.source_url,
                evidence_for_precedence=precedence_reasons,
                source_category=best_match.source_category
            )
            clusters.append(cluster)

        return clusters

    def _select_canonical_source(self, group: List[SourceMatch]) -> (SourceMatch, List[str]):
        """
        Select the most authoritative source among duplicate/mirror candidates.
        """
        if len(group) == 1:
            return group[0], ["Only source in cluster"]

        # Scoring candidate precedence
        def _precedence_key(m: SourceMatch) -> float:
            score = m.authority_score

            # Boost verified matches
            if m.verified:
                score += 50.0

            # Boost longer verbatim matches
            score += min(30.0, m.matched_words * 1.5)

            # Official documentation indicator in URL
            url_lower = m.source_url.lower()
            if any(p in url_lower for p in ['/docs/', '/en/stable/', '/latest/', '/reference/', 'palletsprojects.com', 'docs.', 'readthedocs.io']):
                score += 35.0

            # Educational, encyclopedic, and authoritative domains
            if any(ext in url_lower for ext in ['.edu', '.gov', '.org', 'wikipedia.org']):
                score += 20.0

            # Code repositories (preferred over generic scraper blogs, but secondary to official docs)
            if any(repo in url_lower for repo in ['github.com', 'gitlab.com', 'bitbucket.org']):
                score -= 10.0

            # Generic republishers, scraper blogs, social mirrors penalized heavily
            if any(rep in url_lower for rep in ['medium.com', 'blogspot.com', 'wordpress.com', 'quora.com', 'pinterest.com', 'substack.com']):
                score -= 40.0

            return score

        sorted_group = sorted(group, key=_precedence_key, reverse=True)
        winner = sorted_group[0]

        reasons = []
        winner_url = winner.source_url.lower()

        if any(p in winner_url for p in ['/docs/', '/en/stable/', '/latest/', 'palletsprojects.com', 'readthedocs.io']):
            reasons.append("Official documentation path preferred over code repository or mirror")
        elif any(ext in winner_url for ext in ['.edu', '.gov', '.org', 'wikipedia.org']):
            reasons.append("Authoritative educational/reference domain preferred over generic mirrors")
        elif 'github.com' in winner_url:
            reasons.append("Source code repository preferred over third-party republishers")
        if winner.authority_score > 70.0:
            reasons.append(f"Higher domain authority score ({winner.authority_score:.1f})")
        if winner.matched_words > 0:
            reasons.append(f"Contains {winner.matched_words} verified matching words")

        return winner, reasons
