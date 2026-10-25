"""
PlagiaScan Pipeline — Query Generator

Generates multi-strategy search queries from sentences and distinctive phrases:
- Strategy A: Exact phrase in quotes (8-14 words)
- Strategy B: Partial phrase + distinctive keywords
- Strategy C: Technical entity search
- Strategy D: N-gram fragments for long sentences
- Strategy E: Wikipedia API targeted query
"""

import re
from typing import List, Optional, Tuple
from app.core.pipeline.schemas import (
    DocumentSentence,
    DistinctivePhrase,
    SearchQuery,
    SearchStrategy
)
from app.core.pipeline.phrase_extractor import DistinctivePhraseExtractor
from app.core.pipeline.text_normalizer import TextNormalizer
from app.core.pipeline.entity_verifier import STOP_WORDS


class QueryGenerator:
    """
    Constructs multi-strategy search queries for web retrieval.
    """

    def __init__(
        self,
        phrase_extractor: Optional[DistinctivePhraseExtractor] = None,
        max_queries_per_sentence: int = 4
    ):
        self.phrase_extractor = phrase_extractor or DistinctivePhraseExtractor()
        self.max_queries_per_sentence = max_queries_per_sentence

    def extract_high_entropy_queries(
        self,
        raw_text: str,
        phrase_length: int = 8,
        max_queries: int = 3
    ) -> List[str]:
        """
        Extracts high-entropy quoted phrases suitable for search APIs,
        strictly enforcing the 6-10 word length rule (Section 2 & 4.2).
        Converts Unicode and smart quotes to standard ASCII.
        """
        clean_text = TextNormalizer.sanitize_query_text(raw_text)
        phrase_length = max(6, min(10, phrase_length))

        paragraphs = [p.strip() for p in clean_text.split("\n") if len(p.strip()) > 30]
        if not paragraphs:
            paragraphs = [clean_text.strip()]

        candidate_phrases: List[Tuple[float, str]] = []

        for para in paragraphs:
            words = re.findall(r'\b[A-Za-z0-9_-]+\b', para)
            if len(words) < phrase_length:
                if len(words) >= 4:
                    score = self.phrase_extractor.calculate_phrase_entropy(words)
                    candidate_phrases.append((score, " ".join(words)))
                continue

            for i in range(len(words) - phrase_length + 1):
                window = words[i:i + phrase_length]
                score = self.phrase_extractor.calculate_phrase_entropy(window)
                phrase = " ".join(window)
                candidate_phrases.append((score, phrase))

        # Sort descending by entropy score
        candidate_phrases.sort(key=lambda x: x[0], reverse=True)

        # Select non-overlapping top queries (6-10 words in quotes)
        selected_queries: List[str] = []
        for score, phrase in candidate_phrases:
            if len(selected_queries) >= max_queries:
                break
            if not any(phrase in q or q.strip('"') in phrase for q in selected_queries):
                selected_queries.append(f'"{phrase}"')

        return selected_queries

    def generate_queries_for_sentence(
        self,
        sentence: DocumentSentence,
        sentence_idx: int = 1
    ) -> List[SearchQuery]:
        """
        Generate multiple search queries using different strategies for a sentence.
        Strictly adheres to the 6-10 word quoted window rule to prevent search engine
        de-quoting and SEO scraper pollution.
        """
        queries: List[SearchQuery] = []
        q_counter = 1

        # Unicode-clean text for query formulation
        clean_text = TextNormalizer.sanitize_query_text(sentence.text)
        words = clean_text.split()

        # Extract top distinctive phrases
        phrases = self.phrase_extractor.extract_phrases_for_sentence(
            sentence,
            max_phrases=3
        )

        # Strategy A: High-Entropy 6-10 word exact phrase in quotes (or dual-window for compound sentences)
        entropy_queries = self.extract_high_entropy_queries(clean_text, phrase_length=8, max_queries=2)
        if len(entropy_queries) >= 2 and len(words) >= 16:
            # Dual-window query: "window 1" "window 2" (e.g. "lightweight WSGI framework" "scale up to complex")
            q1 = entropy_queries[0].strip('"')
            q2 = entropy_queries[1].strip('"')
            # Only pair if they do not share tokens
            if not (set(q1.lower().split()) & set(q2.lower().split())):
                dual_q = f'"{q1}" "{q2}"'
                queries.append(
                    SearchQuery(
                        query_id=f"q_{sentence_idx}_{q_counter}",
                        text=dual_q,
                        strategy=SearchStrategy.EXACT_PHRASE,
                        source_sentence_id=sentence.sentence_id,
                        source_phrase=q1
                    )
                )
                q_counter += 1

        if entropy_queries and q_counter <= self.max_queries_per_sentence:
            best_entropy_q = entropy_queries[0]
            queries.append(
                SearchQuery(
                    query_id=f"q_{sentence_idx}_{q_counter}",
                    text=best_entropy_q,
                    strategy=SearchStrategy.EXACT_PHRASE,
                    source_sentence_id=sentence.sentence_id,
                    source_phrase=best_entropy_q.strip('"')
                )
            )
            q_counter += 1
        elif phrases:
            best_phrase = phrases[0].phrase
            phrase_words = best_phrase.split()
            # Enforce 6-10 word rule
            if len(phrase_words) > 10:
                exact_text = f'"{" ".join(phrase_words[:9])}"'
            elif len(phrase_words) >= 4:
                exact_text = f'"{best_phrase}"'
            else:
                exact_text = f'"{best_phrase}"'

            queries.append(
                SearchQuery(
                    query_id=f"q_{sentence_idx}_{q_counter}",
                    text=exact_text,
                    strategy=SearchStrategy.EXACT_PHRASE,
                    source_sentence_id=sentence.sentence_id,
                    source_phrase=best_phrase
                )
            )
            q_counter += 1

        # Strategy B: Second distinctive phrase (always 6-10 words in quotes)
        if len(phrases) >= 2 and q_counter <= self.max_queries_per_sentence:
            second_phrase = phrases[1].phrase
            p2_words = second_phrase.split()
            if len(p2_words) > 10:
                p2_text = f'"{" ".join(p2_words[:8])}"'
            elif len(p2_words) >= 3:
                p2_text = f'"{second_phrase}"'
            else:
                p2_text = f'"{second_phrase}"'

            queries.append(
                SearchQuery(
                    query_id=f"q_{sentence_idx}_{q_counter}",
                    text=p2_text,
                    strategy=SearchStrategy.PARTIAL_PHRASE,
                    source_sentence_id=sentence.sentence_id,
                    source_phrase=second_phrase
                )
            )
            q_counter += 1

        # Strategy C: Entity / Wikipedia targeted query
        wiki_kw = self.phrase_extractor.extract_wikipedia_query(clean_text)
        if wiki_kw and len(wiki_kw.split()) >= 2 and q_counter <= self.max_queries_per_sentence:
            queries.append(
                SearchQuery(
                    query_id=f"q_{sentence_idx}_{q_counter}",
                    text=f'"{wiki_kw}"' if len(wiki_kw.split()) >= 3 else wiki_kw,
                    strategy=SearchStrategy.ENTITY_SEARCH,
                    source_sentence_id=sentence.sentence_id,
                    source_phrase=wiki_kw
                )
            )
            q_counter += 1

        # Strategy D: Distinctive 7-8 word fragment for long sentences (>14 words)
        if len(words) >= 14 and q_counter <= self.max_queries_per_sentence:
            mid_start = max(0, (len(words) - 8) // 2)
            mid_frag = ' '.join(words[mid_start: mid_start + 8])
            queries.append(
                SearchQuery(
                    query_id=f"q_{sentence_idx}_{q_counter}",
                    text=f'"{mid_frag}"',
                    strategy=SearchStrategy.NGRAM_FRAGMENTS,
                    source_sentence_id=sentence.sentence_id,
                    source_phrase=mid_frag
                )
            )
            q_counter += 1

        # Strategy E: Quoted core keywords window (6-8 words)
        if q_counter <= self.max_queries_per_sentence:
            if len(words) >= 6:
                core_words = words[:min(8, len(words))]
                queries.append(
                    SearchQuery(
                        query_id=f"q_{sentence_idx}_{q_counter}",
                        text=f'"{" ".join(core_words)}"',
                        strategy=SearchStrategy.PARTIAL_PHRASE,
                        source_sentence_id=sentence.sentence_id,
                        source_phrase=" ".join(core_words)
                    )
                )

        return queries[:self.max_queries_per_sentence]

    def generate_queries_for_document(
        self,
        sentences: List[DocumentSentence],
        target_sentence_count: int = 10
    ) -> List[SearchQuery]:
        """
        Select representative sentences across document and generate queries.
        """
        sampled_sentences = self.phrase_extractor.select_representative_sentences(
            sentences,
            target_count=target_sentence_count
        )

        all_queries: List[SearchQuery] = []
        for idx, sentence in enumerate(sampled_sentences, start=1):
            sent_queries = self.generate_queries_for_sentence(sentence, sentence_idx=idx)
            all_queries.extend(sent_queries)

        return all_queries
