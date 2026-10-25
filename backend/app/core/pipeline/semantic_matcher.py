"""
PlagiaScan Pipeline — Semantic Matcher

Embedding-based semantic similarity and paraphrase detection:
- Uses FastEmbed all-MiniLM-L6-v2 embeddings
- Computes cosine similarity between document sentences and webpage passages
- Batch vector encoding for efficiency
- Graceful fallback if ML dependencies are unavailable
"""

import math
import logging
from typing import List, Tuple, Optional
from app.core.pipeline.schemas import SemanticMatch
from app.core.ml import EmbeddingModel

logger = logging.getLogger("plagiascan.pipeline.semantic")


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two 1D float vectors."""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm1 * norm2)))


class SemanticMatcher:
    """
    Computes dense vector embeddings and cosine similarity to detect paraphrased content.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._embedder: Optional[EmbeddingModel] = None

    def _get_embedder(self) -> Optional[EmbeddingModel]:
        """Lazy load embedding model instance."""
        if self._embedder is None:
            try:
                self._embedder = EmbeddingModel.get_instance()
            except Exception as e:
                logger.warning(f"[SEMANTIC MATCHER] Failed to initialize EmbeddingModel: {e}")
                self._embedder = None
        return self._embedder

    def match(self, text_a: str, text_b: str) -> SemanticMatch:
        """
        Compute cosine similarity between two text snippets.
        """
        if not text_a or not text_b or not text_a.strip() or not text_b.strip():
            return SemanticMatch(cosine_similarity=0.0, embedding_model=self.model_name)

        embedder = self._get_embedder()
        if not embedder:
            return SemanticMatch(cosine_similarity=0.0, embedding_model="unavailable")

        try:
            vectors = embedder.encode([text_a[:1000], text_b[:1000]])
            if len(vectors) == 2:
                sim = _cosine_similarity(vectors[0], vectors[1])
                return SemanticMatch(
                    cosine_similarity=round(sim, 4),
                    embedding_model=self.model_name
                )
        except Exception as e:
            logger.debug(f"[SEMANTIC SIMILARITY ERROR] {e}")

        return SemanticMatch(cosine_similarity=0.0, embedding_model=self.model_name)

    def find_best_semantic_match(
        self,
        query_text: str,
        candidate_passages: List[str]
    ) -> Tuple[float, str]:
        """
        Given a query text and candidate passages from a webpage,
        find the passage with highest semantic similarity.
        """
        if not query_text or not candidate_passages:
            return 0.0, ""

        embedder = self._get_embedder()
        if not embedder:
            return 0.0, ""

        valid_passages = [p.strip() for p in candidate_passages if len(p.strip().split()) >= 6][:25]
        if not valid_passages:
            return 0.0, ""

        try:
            all_texts = [query_text[:1000]] + [p[:1000] for p in valid_passages]
            vectors = embedder.encode(all_texts)
            q_vec = vectors[0]

            best_sim = 0.0
            best_passage = ""

            for p_text, p_vec in zip(valid_passages, vectors[1:]):
                sim = _cosine_similarity(q_vec, p_vec)
                if sim > best_sim:
                    best_sim = sim
                    best_passage = p_text

            return round(best_sim, 4), best_passage
        except Exception as e:
            logger.debug(f"[BATCH SEMANTIC ERROR] {e}")
            return 0.0, ""
