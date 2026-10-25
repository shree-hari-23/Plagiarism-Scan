"""
PlagiaScan Pipeline — Seed-and-Extend Alignment Engine (v2.0)

Replaces rigid fixed N-gram matching with edit-tolerant sequence alignment:
1. Index document with k-gram hashes (k=6, adaptive for shorter units).
2. For each candidate webpage, find seed hits in O(|page|) time.
3. Group seeds by diagonal band (src_pos - doc_pos) within tolerance G=8.
4. Chain seeds within gap <= max_gap (8 tokens).
5. Extend bidirectionally with edit tolerance (theta >= 0.70 identity).
6. Emit maximal aligned spans with exact run lengths and identity scores.
"""

from typing import List, Dict, Tuple, Set, Optional
from pydantic import BaseModel, Field
from app.core.pipeline.text_normalizer import TextNormalizer
from app.core.pipeline.entity_verifier import STOP_WORDS


class AlignedSpan(BaseModel):
    """A maximal aligned span between document text and source text."""
    doc_start: int = 0          # token offset in document
    doc_end: int = 0            # token offset in document (exclusive)
    src_start: int = 0          # token offset in source
    src_end: int = 0            # token offset in source (exclusive)
    matched_tokens: int = 0     # count of identical tokens in alignment
    aligned_tokens: int = 0     # total span length
    identity: float = 0.0       # matched_tokens / aligned_tokens (0.0 to 1.0)
    longest_exact_run: int = 0  # longest unbroken exact match
    doc_excerpt: str = ""
    src_excerpt: str = ""
    edit_ops: int = 0           # substitutions + insertions + deletions


class DocumentKgramIndex:
    """
    Hash-based k-gram index for fast seed discovery in document tokens.
    """
    def __init__(self, doc_text: str, k: int = 6):
        self.doc_text = doc_text
        self.norm_text = TextNormalizer.normalize(doc_text)
        self.doc_tokens: List[str] = self.norm_text.split()
        self.k = min(k, max(3, len(self.doc_tokens))) if self.doc_tokens else k
        self.index: Dict[Tuple[str, ...], List[int]] = {}
        self._build_index()

    def _build_index(self):
        n = len(self.doc_tokens)
        if n < self.k:
            return

        for i in range(n - self.k + 1):
            gram = tuple(self.doc_tokens[i: i + self.k])
            # Ignore stopword-only k-grams to prevent noisy seed spam
            if all(tok in STOP_WORDS for tok in gram):
                continue
            self.index.setdefault(gram, []).append(i)

    def lookup(self, gram: Tuple[str, ...]) -> List[int]:
        """Look up all document token positions for a given k-gram."""
        return self.index.get(gram, [])


class SeedAndExtendAligner:
    """
    Aligns candidate webpage tokens against document tokens via Seed-and-Extend.
    """
    def __init__(self, k: int = 6, max_gap: int = 8, theta: float = 0.70, min_span_tokens: int = 8):
        self.k = k
        self.max_gap = max_gap
        self.theta = theta
        self.min_span_tokens = min_span_tokens

    def align(
        self,
        doc_tokens: List[str],
        doc_index: DocumentKgramIndex,
        page_tokens: List[str]
    ) -> List[AlignedSpan]:
        """
        Execute seed-and-extend alignment of page_tokens against doc_tokens.
        Returns maximal merged AlignedSpan objects.
        """
        if not doc_tokens or not page_tokens:
            return []

        k = min(self.k, len(doc_tokens), len(page_tokens))
        if k < 3:
            return []

        # 1. SEED: Slide k-gram across page tokens and look up hits in doc index
        seeds: List[Tuple[int, int, int]] = []  # (diag, doc_pos, src_pos)
        num_page_grams = len(page_tokens) - k + 1

        for j in range(num_page_grams):
            gram = tuple(page_tokens[j: j + k])
            if all(t in STOP_WORDS for t in gram):
                continue
            doc_positions = doc_index.lookup(gram)
            for i in doc_positions:
                diag = j - i
                seeds.append((diag, i, j))

        if not seeds:
            return []

        # Sort seeds by diagonal, then doc_pos, then src_pos
        seeds.sort(key=lambda x: (x[0], x[1], x[2]))

        # 2. DIAGONAL GROUPING: Group seeds within diagonal band of +/- G
        bands: List[List[Tuple[int, int, int]]] = []
        curr_band: List[Tuple[int, int, int]] = []
        band_base_diag = None

        for seed in seeds:
            diag, doc_p, src_p = seed
            if band_base_diag is None:
                band_base_diag = diag
                curr_band = [seed]
            elif abs(diag - band_base_diag) <= self.max_gap:
                curr_band.append(seed)
            else:
                bands.append(curr_band)
                band_base_diag = diag
                curr_band = [seed]
        if curr_band:
            bands.append(curr_band)

        # 3. CHAIN AND EXTEND
        raw_spans: List[AlignedSpan] = []

        for band in bands:
            # Sort seeds within band by document position
            band.sort(key=lambda x: (x[1], x[2]))

            chains: List[List[Tuple[int, int, int]]] = []
            curr_chain: List[Tuple[int, int, int]] = []

            for seed in band:
                if not curr_chain:
                    curr_chain = [seed]
                else:
                    last_doc_p = curr_chain[-1][1]
                    last_src_p = curr_chain[-1][2]
                    doc_gap = seed[1] - (last_doc_p + k)
                    src_gap = seed[2] - (last_src_p + k)

                    if -k <= doc_gap <= self.max_gap and -k <= src_gap <= self.max_gap:
                        curr_chain.append(seed)
                    else:
                        chains.append(curr_chain)
                        curr_chain = [seed]
            if curr_chain:
                chains.append(curr_chain)

            # 4. EXTEND each chain with edit tolerance
            for chain in chains:
                span = self._extend_chain(chain, doc_tokens, page_tokens, k)
                if span and span.matched_tokens >= self.min_span_tokens:
                    raw_spans.append(span)

        # 5. MERGE OVERLAPPING SPANS
        return self._merge_spans(raw_spans)

    def _extend_chain(
        self,
        chain: List[Tuple[int, int, int]],
        doc_tokens: List[str],
        page_tokens: List[str],
        k: int
    ) -> Optional[AlignedSpan]:
        """Extend seed chain at boundaries with local edit tolerance."""
        first_doc = chain[0][1]
        first_src = chain[0][2]
        last_doc = chain[-1][1] + k
        last_src = chain[-1][2] + k

        doc_len = len(doc_tokens)
        page_len = len(page_tokens)

        # Edit-tolerant bidirectional extension (X-drop)
        # Extend left
        d = first_doc
        s = first_src
        best_d_left = d
        best_s_left = s
        score = 0
        max_score = 0
        x_drop = 4

        while d > 0 and s > 0:
            if doc_tokens[d - 1] == page_tokens[s - 1]:
                score += 2
                d -= 1
                s -= 1
            elif d >= 2 and doc_tokens[d - 2] == page_tokens[s - 1]:
                # 1 token deletion in doc
                score += 1
                d -= 2
                s -= 1
            elif s >= 2 and doc_tokens[d - 1] == page_tokens[s - 2]:
                # 1 token insertion in doc
                score += 1
                d -= 1
                s -= 2
            else:
                # Substitution
                score -= 1
                d -= 1
                s -= 1

            if score > max_score:
                max_score = score
                best_d_left = d
                best_s_left = s

            if max_score - score >= x_drop:
                break

        d_left = best_d_left
        s_left = best_s_left

        # Extend right
        d = min(doc_len, last_doc)
        s = min(page_len, last_src)
        best_d_right = d
        best_s_right = s
        score = 0
        max_score = 0

        while d < doc_len and s < page_len:
            if doc_tokens[d] == page_tokens[s]:
                score += 2
                d += 1
                s += 1
            elif d + 1 < doc_len and doc_tokens[d + 1] == page_tokens[s]:
                # 1 token insertion in doc
                score += 1
                d += 2
                s += 1
            elif s + 1 < page_len and doc_tokens[d] == page_tokens[s + 1]:
                # 1 token deletion in doc
                score += 1
                d += 1
                s += 2
            else:
                # Substitution
                score -= 1
                d += 1
                s += 1

            if score > max_score:
                max_score = score
                best_d_right = d
                best_s_right = s

            if max_score - score >= x_drop:
                break

        d_right = best_d_right
        s_right = best_s_right

        span_doc_tokens = doc_tokens[d_left:d_right]
        span_page_tokens = page_tokens[s_left:s_right]

        if not span_doc_tokens or not span_page_tokens:
            return None

        m = len(span_doc_tokens)
        n = len(span_page_tokens)

        # Compute exact LCS length to measure true alignment identity across indels & edits
        dp = [0] * (n + 1)
        for i in range(m):
            prev = 0
            for j in range(n):
                temp = dp[j + 1]
                if span_doc_tokens[i] == span_page_tokens[j]:
                    dp[j + 1] = prev + 1
                else:
                    dp[j + 1] = max(dp[j + 1], dp[j])
                prev = temp
        lcs_matches = dp[n]

        # Compute longest unbroken exact run anywhere within the span
        longest_run = 0
        for i in range(m):
            for j in range(n):
                run = 0
                while (
                    i + run < m and
                    j + run < n and
                    span_doc_tokens[i + run] == span_page_tokens[j + run]
                ):
                    run += 1
                longest_run = max(longest_run, run)

        aligned_tokens = max(m, n)
        identity = round(lcs_matches / max(aligned_tokens, 1), 4)

        if identity < self.theta and longest_run < self.min_span_tokens:
            return None

        doc_excerpt = " ".join(span_doc_tokens)
        src_excerpt = " ".join(span_page_tokens)

        return AlignedSpan(
            doc_start=d_left,
            doc_end=d_right,
            src_start=s_left,
            src_end=s_right,
            matched_tokens=lcs_matches,
            aligned_tokens=aligned_tokens,
            identity=identity,
            longest_exact_run=longest_run,
            doc_excerpt=doc_excerpt,
            src_excerpt=src_excerpt,
            edit_ops=aligned_tokens - lcs_matches
        )

    def _merge_spans(self, spans: List[AlignedSpan]) -> List[AlignedSpan]:
        """Merge overlapping or adjacent document spans."""
        if not spans:
            return []

        spans.sort(key=lambda s: (s.doc_start, s.doc_end))
        merged: List[AlignedSpan] = []

        for span in spans:
            if not merged:
                merged.append(span)
                continue

            prev = merged[-1]
            # Check overlap or small gap in document coordinates
            if span.doc_start <= prev.doc_end + 3:
                new_doc_start = min(prev.doc_start, span.doc_start)
                new_doc_end = max(prev.doc_end, span.doc_end)
                new_src_start = min(prev.src_start, span.src_start)
                new_src_end = max(prev.src_end, span.src_end)
                new_matched = max(prev.matched_tokens, span.matched_tokens)
                new_aligned = max(new_doc_end - new_doc_start, 1)
                new_identity = round(max(prev.identity, span.identity), 4)
                new_longest_run = max(prev.longest_exact_run, span.longest_exact_run)

                merged[-1] = AlignedSpan(
                    doc_start=new_doc_start,
                    doc_end=new_doc_end,
                    src_start=new_src_start,
                    src_end=new_src_end,
                    matched_tokens=new_matched,
                    aligned_tokens=new_aligned,
                    identity=new_identity,
                    longest_exact_run=new_longest_run,
                    doc_excerpt=prev.doc_excerpt if len(prev.doc_excerpt) >= len(span.doc_excerpt) else span.doc_excerpt,
                    src_excerpt=prev.src_excerpt if len(prev.src_excerpt) >= len(span.src_excerpt) else span.src_excerpt,
                    edit_ops=prev.edit_ops + span.edit_ops
                )
            else:
                merged.append(span)

        return merged
