"""
PlagiaScan Pipeline — Sentence and Clause Segmenter

Splits document text into DocumentSentence objects with:
- Sentence boundary detection handling abbreviations, numbers, and URLs
- Paragraph tracking and character offsets
- Sub-clause extraction for long compound sentences (>30 words)
- Integration with TextNormalizer
"""

import re
from typing import List, Optional
from app.core.pipeline.schemas import DocumentSentence
from app.core.pipeline.text_normalizer import TextNormalizer


class DocumentSegmenter:
    """
    Robust sentence and clause segmenter for plagiarism detection.
    """

    # Common abbreviations that should not trigger sentence boundaries
    _ABBREVIATIONS = (
        r'\b(?:'
        r'mr|mrs|ms|dr|prof|sr|jr|rev|hon|st|'
        r'u\.s|u\.k|u\.s\.a|e\.g|i\.e|etc|vs|al|fig|dept|'
        r'inc|ltd|corp|co|approx|app|no|vol|pp|ed|gen|col|sgt'
        r')\.'
    )

    # Clause boundary connectives for splitting long sentences (>30 words)
    _CLAUSE_CONNECTIVES = re.compile(
        r'(?:[,;]\s+)(?:and|but|or|yet|so|while|whereas|although|because|since|'
        r'which|that|who|whom|whose|where|when|if|unless|allowing|including|'
        r'enabling|providing|resulting in|leading to)\b',
        re.IGNORECASE
    )

    # Citation removal pattern
    _CITATION_PATTERN = re.compile(r'\[\d+(?:\s*[-–,]\s*\d+)*\]')

    def __init__(self, min_sentence_words: int = 4, long_sentence_threshold: int = 30):
        self.min_sentence_words = min_sentence_words
        self.long_sentence_threshold = long_sentence_threshold

    def segment(self, full_text: str, fallback_chunks: Optional[List[str]] = None) -> List[DocumentSentence]:
        """
        Segment full document text into DocumentSentence objects.
        Tracks paragraphs, sentence IDs, character offsets, and sub-clauses.
        """
        if not full_text or not full_text.strip():
            if fallback_chunks:
                return self._from_fallback_chunks(fallback_chunks)
            return []

        # Split into paragraphs
        raw_paragraphs = re.split(r'\n\s*\n', full_text)
        sentences: List[DocumentSentence] = []
        sentence_counter = 1
        current_offset = 0

        for p_idx, raw_para in enumerate(raw_paragraphs):
            para_id = f"p_{p_idx + 1:03d}"
            para_text = raw_para.strip()
            if not para_text:
                current_offset += len(raw_para) + 2  # account for \n\n
                continue

            # Find actual paragraph start in full text
            p_start = full_text.find(raw_para, current_offset)
            if p_start == -1:
                p_start = current_offset
            current_offset = p_start + len(raw_para)

            # Extract sentences within paragraph
            para_sentences = self._split_paragraph_sentences(para_text, p_start)

            for s_text, s_start, s_end in para_sentences:
                cleaned_sentence = self._clean_citations(s_text)
                words = cleaned_sentence.split()
                if len(words) < self.min_sentence_words:
                    continue

                sentence_id = f"s_{sentence_counter:04d}"
                sentence_counter += 1
                normalized = TextNormalizer.normalize(cleaned_sentence)

                doc_sent = DocumentSentence(
                    sentence_id=sentence_id,
                    text=cleaned_sentence,
                    normalized_text=normalized,
                    paragraph_id=para_id,
                    char_start=s_start,
                    char_end=s_end,
                    word_count=len(words),
                    is_clause=False,
                    parent_sentence_id=None
                )
                sentences.append(doc_sent)

                # If sentence is long, extract sub-clauses as supplementary units
                if len(words) >= self.long_sentence_threshold:
                    clauses = self._extract_clauses(doc_sent)
                    sentences.extend(clauses)

        if not sentences and fallback_chunks:
            return self._from_fallback_chunks(fallback_chunks)

        return sentences

    def _split_paragraph_sentences(self, para_text: str, para_start_offset: int) -> List[tuple]:
        """
        Split a paragraph into sentences preserving offsets.
        Returns List of (sentence_text, start_offset, end_offset).
        """
        # Protect abbreviations and decimals with placeholders
        protected_text = para_text

        # Protect decimals like 3.14 or v2.0
        decimals = re.findall(r'\b\d+\.\d+\b', protected_text)
        dec_map = {}
        for idx, dec in enumerate(decimals):
            ph = f"__DEC_{idx}__"
            dec_map[ph] = dec
            protected_text = protected_text.replace(dec, ph, 1)

        # Protect common abbreviations
        abbrevs = re.findall(self._ABBREVIATIONS, protected_text, re.IGNORECASE)
        abbr_map = {}
        for idx, ab in enumerate(abbrevs):
            ph = f"__ABBR_{idx}__"
            abbr_map[ph] = ab
            protected_text = protected_text.replace(ab, ph, 1)

        # Protect URLs/emails (strip trailing sentence punctuation)
        raw_urls = re.findall(r'https?://[^\s]+|[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', protected_text)
        url_map = {}
        for idx, u in enumerate(raw_urls):
            clean_u = u.rstrip('.,;!?')
            if clean_u:
                ph = f"__URL_{idx}__"
                url_map[ph] = clean_u
                protected_text = protected_text.replace(clean_u, ph, 1)

        # Split on sentence terminals followed by whitespace (. ! ?)
        split_pattern = re.compile(r'([.!?]+)(?:\s+|\Z)')
        segments = []
        pos = 0

        for match in split_pattern.finditer(protected_text):
            end_pos = match.end()
            segment = protected_text[pos:end_pos].strip()
            if segment:
                # Restore placeholders
                for ph, orig in url_map.items():
                    segment = segment.replace(ph, orig)
                for ph, orig in abbr_map.items():
                    segment = segment.replace(ph, orig)
                for ph, orig in dec_map.items():
                    segment = segment.replace(ph, orig)

                # Locate segment in original paragraph for exact char offsets
                s_find = para_text.find(segment, pos)
                if s_find != -1:
                    s_start = para_start_offset + s_find
                    s_end = s_start + len(segment)
                else:
                    s_start = para_start_offset + pos
                    s_end = s_start + len(segment)

                segments.append((segment, s_start, s_end))
            pos = end_pos

        # Remaining trailing text
        if pos < len(protected_text):
            remainder = protected_text[pos:].strip()
            if remainder:
                for ph, orig in url_map.items():
                    remainder = remainder.replace(ph, orig)
                for ph, orig in abbr_map.items():
                    remainder = remainder.replace(ph, orig)
                for ph, orig in dec_map.items():
                    remainder = remainder.replace(ph, orig)

                s_start = para_start_offset + pos
                s_end = s_start + len(remainder)
                segments.append((remainder, s_start, s_end))

        return segments

    def _extract_clauses(self, parent: DocumentSentence) -> List[DocumentSentence]:
        """
        For a long sentence, split into coherent sub-clauses.
        Each clause inherits paragraph info and points to parent sentence ID.
        """
        clauses: List[DocumentSentence] = []
        text = parent.text

        # Split at punctuation followed by conjunctions/relative pronouns or semicolons
        splits = self._CLAUSE_CONNECTIVES.split(text)
        if len(splits) <= 1:
            # Try semicolon split
            splits = [s.strip() for s in text.split(';') if len(s.strip().split()) >= 6]

        clause_idx = 1
        for part in splits:
            part = part.strip().lstrip(',; ').strip()
            words = part.split()
            if len(words) >= 6 and len(words) < parent.word_count:
                c_id = f"{parent.sentence_id}_c{clause_idx}"
                clause_idx += 1
                normalized = TextNormalizer.normalize(part)

                c_start = parent.char_start + parent.text.find(part) if parent.text.find(part) != -1 else parent.char_start
                c_end = c_start + len(part)

                clauses.append(
                    DocumentSentence(
                        sentence_id=c_id,
                        text=part,
                        normalized_text=normalized,
                        paragraph_id=parent.paragraph_id,
                        char_start=c_start,
                        char_end=c_end,
                        word_count=len(words),
                        is_clause=True,
                        parent_sentence_id=parent.sentence_id
                    )
                )

        return clauses

    def _clean_citations(self, text: str) -> str:
        """Remove citation brackets like [1], [2-4] and extra whitespace."""
        text = self._CITATION_PATTERN.sub('', text)
        return re.sub(r'\s+', ' ', text).strip()

    def _from_fallback_chunks(self, chunks: List[str]) -> List[DocumentSentence]:
        """Fallback to raw document chunks if normal segmentation yields nothing."""
        sentences = []
        offset = 0
        for idx, c in enumerate(chunks):
            c_clean = self._clean_citations(c)
            words = c_clean.split()
            if len(words) >= self.min_sentence_words:
                s_id = f"s_{idx + 1:04d}"
                sentences.append(
                    DocumentSentence(
                        sentence_id=s_id,
                        text=c_clean,
                        normalized_text=TextNormalizer.normalize(c_clean),
                        paragraph_id=f"p_{idx + 1:03d}",
                        char_start=offset,
                        char_end=offset + len(c_clean),
                        word_count=len(words),
                        is_clause=False,
                        parent_sentence_id=None
                    )
                )
            offset += len(c) + 1
        return sentences
