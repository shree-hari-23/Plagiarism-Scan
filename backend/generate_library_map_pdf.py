import os
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfgen import canvas

PRIMARY_DOWNLOAD_PATH = r"C:\Users\hariv\Downloads\PlagiaScan_Library_and_Technology_Map.pdf"
WORKSPACE_PDF_PATH = r"c:\Users\hariv\Downloads\Plagiarism-Scan-main\PlagiaScan_Library_and_Technology_Map.pdf"
ARTIFACT_PDF_PATH = r"C:\Users\hariv\.gemini\antigravity-ide\brain\6d385a33-030c-4e47-bd5b-56e087a401c0\PlagiaScan_Library_and_Technology_Map.pdf"


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        if self._pageNumber > 1:
            self.drawString(54, 750, "PlagiaScan - Complete Library & Technology Stack Reference")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, 742, 612 - 54, 742)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 45, 612 - 54, 45)
        self.drawString(54, 32, "PlagiaScan Engineering - Library & Technology Stack Map")
        self.drawRightString(612 - 54, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def build_pdf():
    os.makedirs(os.path.dirname(PRIMARY_DOWNLOAD_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(ARTIFACT_PDF_PATH), exist_ok=True)

    doc = SimpleDocTemplate(
        PRIMARY_DOWNLOAD_PATH,
        pagesize=letter,
        topMargin=54, bottomMargin=54, leftMargin=54, rightMargin=54
    )

    W = 612 - 108  # 504pt usable

    # Colors
    PRIMARY = colors.HexColor("#1E3A8A")
    PRIMARY_LIGHT = colors.HexColor("#EFF6FF")
    SECONDARY = colors.HexColor("#0F172A")
    ACCENT_TEAL = colors.HexColor("#0D9488")
    TEAL_LIGHT = colors.HexColor("#F0FDFA")
    EMERALD = colors.HexColor("#059669")
    EMERALD_LIGHT = colors.HexColor("#ECFDF5")
    AMBER = colors.HexColor("#D97706")
    AMBER_LIGHT = colors.HexColor("#FFFBEB")
    TEXT_MAIN = colors.HexColor("#1E293B")
    TEXT_MUTED = colors.HexColor("#64748B")
    BORDER = colors.HexColor("#CBD5E1")

    def sty(name, **kw):
        return ParagraphStyle(name, **kw)

    TITLE = sty("T", fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=PRIMARY, alignment=TA_CENTER)
    SUBTITLE = sty("ST", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=ACCENT_TEAL, alignment=TA_CENTER, spaceAfter=4)
    META = sty("M", fontName="Helvetica", fontSize=8, leading=11, textColor=TEXT_MUTED, alignment=TA_CENTER)
    H1 = sty("H1", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=PRIMARY, spaceBefore=12, spaceAfter=4, keepWithNext=True)
    H2 = sty("H2", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=SECONDARY, spaceBefore=8, spaceAfter=3, keepWithNext=True)
    BODY = sty("B", fontName="Helvetica", fontSize=8.2, leading=12, textColor=TEXT_MAIN, alignment=TA_JUSTIFY, spaceAfter=4)
    BULLET = sty("BU", fontName="Helvetica", fontSize=8.2, leading=12, textColor=TEXT_MAIN, leftIndent=12, spaceAfter=2.5)
    CALLOUT = sty("CO", fontName="Helvetica-Oblique", fontSize=8, leading=11.5, textColor=colors.HexColor("#1E3A8A"))

    TH = sty("TH", fontName="Helvetica-Bold", fontSize=7.2, leading=9.5, textColor=colors.white, alignment=TA_LEFT)
    TC = sty("TC", fontName="Helvetica", fontSize=7.2, leading=9.5, textColor=TEXT_MAIN, alignment=TA_LEFT)
    TCB = sty("TCB", fontName="Helvetica-Bold", fontSize=7.2, leading=9.5, textColor=SECONDARY, alignment=TA_LEFT)

    def hr():
        return HRFlowable(width="100%", thickness=0.6, color=BORDER, spaceBefore=3, spaceAfter=6)

    def callout(text, bg=PRIMARY_LIGHT, border=PRIMARY):
        p = Paragraph(text, CALLOUT)
        t = Table([[p]], colWidths=[W])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg),
            ('BOX', (0,0), (-1,-1), 0.75, border),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        return t

    def make_table(data, col_widths, header_bg=PRIMARY):
        rows = []
        for ri, row in enumerate(data):
            r = []
            for ci, cell in enumerate(row):
                if isinstance(cell, str):
                    if ri == 0:
                        r.append(Paragraph(cell, TH))
                    elif ci == 0:
                        r.append(Paragraph(cell, TCB))
                    else:
                        r.append(Paragraph(cell, TC))
                else:
                    r.append(cell)
            rows.append(r)
        t = Table(rows, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), header_bg),
            ('GRID', (0,0), (-1,-1), 0.5, BORDER),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        return t

    story = []

    # ── TITLE ────────────────────────────────────────────────────────────────
    story.append(Paragraph("PlagiaScan: Complete Library & Technology Stack Map", TITLE))
    story.append(Spacer(1, 2))
    story.append(Paragraph("End-to-End Library Inventory for Web Plagiarism Engine & AI Detection Engine", SUBTITLE))
    story.append(Paragraph("Every external package, Python stdlib module, and pre-trained model traced from source code imports", META))
    story.append(Spacer(1, 4))
    story.append(hr())

    # ── OVERVIEW ─────────────────────────────────────────────────────────────
    story.append(Paragraph("1. Architectural Overview: Two Independent Engines", H1))
    story.append(hr())
    story.append(Paragraph(
        "PlagiaScan operates two fundamentally different detection engines, each with its own technology stack. "
        "Understanding which libraries belong to which engine is critical for interview discussions, "
        "because it demonstrates clear separation of concerns and deliberate engineering trade-offs.",
        BODY
    ))

    overview_table = [
        ["Dimension", "Engine 1: Web Plagiarism Detection", "Engine 2: AI Content Detection"],
        ["Core Task", "Find copied text from web/database sources", "Determine if text was written by an LLM"],
        ["External Libraries", "14 external packages", "0 external packages (zero)"],
        ["Python Stdlib Modules", "12 stdlib modules", "2 stdlib modules (re + math)"],
        ["Pre-Trained Model", "all-MiniLM-L6-v2 (22M params, via fastembed)", "None -- pure algorithmic heuristics"],
        ["Pipeline Stages", "10 sequential stages", "6 parallel signal computations"],
        ["Entry Point File", "detection.py -> pipeline/orchestrator.py", "detection.py -> detect_ai_content()"],
        ["Execution Cost", "1.2s-2.5s (network I/O bound)", "<20ms (CPU-only, zero cost)"],
    ]
    story.append(make_table(overview_table, [95, 205, 204]))
    story.append(Spacer(1, 6))

    # ══════════════════════════════════════════════════════════════════════════
    # ENGINE 1: WEB PLAGIARISM DETECTION
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("2. Engine 1: Web Plagiarism Detection -- Complete Library Inventory", H1))
    story.append(hr())
    story.append(Paragraph(
        "The web plagiarism engine is a 10-stage pipeline orchestrated by <code>WebSourceDetectionPipeline</code> "
        "in <code>app/core/pipeline/orchestrator.py</code>. Each stage uses specific libraries listed below.",
        BODY
    ))

    # Stage 1
    story.append(Paragraph("Stage 1: Document Upload & Text Extraction", H2))
    story.append(Paragraph(
        "File: <code>app/core/ingestion.py</code> -- Accepts PDF, DOCX, HTML, and scanned image documents.",
        BULLET
    ))
    s1 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["pypdf", "pypdf==3.17.1", "External", "PdfReader extracts text from uploaded PDF documents page by page"],
        ["python-docx", "python-docx==1.1.0", "External", "Reads .docx XML structure and extracts paragraph text"],
        ["beautifulsoup4", "beautifulsoup4==4.12.2", "External", "Parses uploaded HTML files and extracts visible text content"],
        ["pytesseract", "pytesseract==0.3.10", "External", "OCR engine wrapper -- extracts text from scanned/image-based PDFs"],
        ["Pillow", "Pillow>=10.1.0", "External", "Opens image files (PNG/JPEG) and passes them to pytesseract for OCR"],
        ["mimetypes", "Python stdlib", "Stdlib", "Detects file MIME type (application/pdf vs text/html) for routing"],
    ]
    story.append(make_table(s1, [80, 110, 50, 264]))
    story.append(Spacer(1, 5))

    # Stage 2
    story.append(Paragraph("Stage 2: Text Chunking (Token-Based Segmentation)", H2))
    story.append(Paragraph(
        "File: <code>app/core/ml.py</code> (Chunker class) -- Splits extracted text into 300-token overlapping windows.",
        BULLET
    ))
    s2 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["tiktoken", "tiktoken", "External", "OpenAI's BPE tokenizer (cl100k_base encoding). Splits text into 300-token chunks with 50-token overlap. Ensures chunk boundaries align with word boundaries."],
    ]
    story.append(make_table(s2, [80, 110, 50, 264]))
    story.append(Spacer(1, 5))

    # Stage 3
    story.append(Paragraph("Stage 3: Vector Embedding Generation", H2))
    story.append(Paragraph(
        "File: <code>app/core/ml.py</code> (EmbeddingModel class) -- Encodes text chunks into 384-dimensional dense vectors.",
        BULLET
    ))
    s3 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["fastembed", "fastembed", "External", "Lightweight ONNX-runtime wrapper that loads the pre-trained all-MiniLM-L6-v2 sentence transformer model. Converts each text chunk into a 384-dimensional float32 dense vector. No PyTorch/TensorFlow required."],
    ]
    story.append(make_table(s3, [80, 110, 50, 264]))
    story.append(Spacer(1, 3))
    story.append(callout(
        "<b>Pre-Trained Model:</b> sentence-transformers/all-MiniLM-L6-v2 (22M parameters). "
        "Architecture: Distilled BERT (MiniLM). Trained by Microsoft/UKP on 1B+ sentence pairs using contrastive learning. "
        "PlagiaScan uses it for inference only -- no fine-tuning or retraining was performed.",
        TEAL_LIGHT, ACCENT_TEAL
    ))
    story.append(Spacer(1, 5))

    # Stage 4
    story.append(Paragraph("Stage 4: Internal Database Semantic Search (Qdrant Vector DB)", H2))
    story.append(Paragraph(
        "File: <code>app/db/vector.py</code> -- Queries chunk vectors against previously indexed documents.",
        BULLET
    ))
    s4 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["qdrant-client", "qdrant-client", "External", "Vector database client. Stores document chunk embeddings in an HNSW graph index (M=16, efSearch=64). Performs cosine similarity search with score_threshold >= 0.65 to find semantically similar passages across the institutional document archive."],
        ["uuid", "Python stdlib", "Stdlib", "Generates unique point IDs for each vector stored in Qdrant"],
    ]
    story.append(make_table(s4, [80, 110, 50, 264]))
    story.append(Spacer(1, 5))

    # Stage 5
    story.append(Paragraph("Stage 5: Sentence Segmentation & Distinctive Phrase Extraction", H2))
    story.append(Paragraph(
        "Files: <code>pipeline/segmenter.py</code>, <code>pipeline/phrase_extractor.py</code>, <code>pipeline/text_normalizer.py</code>",
        BULLET
    ))
    s5 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["re", "Python stdlib", "Stdlib", "Regex-based sentence boundary detection (split on .!? followed by whitespace). Also used for stopword filtering and noun-phrase extraction patterns."],
        ["unicodedata", "Python stdlib", "Stdlib", "NFKC unicode normalization -- standardizes smart quotes, em-dashes, ligatures to ASCII equivalents before comparison"],
    ]
    story.append(make_table(s5, [80, 110, 50, 264]))
    story.append(Spacer(1, 5))

    # Stage 6
    story.append(Paragraph("Stage 6: Multi-Engine Web Search (Query Execution)", H2))
    story.append(Paragraph(
        "File: <code>pipeline/search_providers.py</code> -- Sends distinctive phrases to multiple search engines.",
        BULLET
    ))
    s6 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["duckduckgo-search", "duckduckgo-search", "External", "Primary search provider (DDGS class). Sends text queries to DuckDuckGo and returns ranked URLs with snippets. Handles rate-limiting and retries."],
        ["httpx", "httpx==0.25.1", "External", "Async-capable HTTP client. Used to query Bing search HTML pages, Brave Search API, Tavily API, and Wikipedia MediaWiki API as fallback providers."],
        ["lxml", "lxml", "External", "HTML DOM parser. Parses raw Bing search result pages using document_fromstring() to extract result URLs and snippets from the HTML structure."],
        ["base64", "Python stdlib", "Stdlib", "Decodes Bing redirect URLs. Bing encodes destination URLs in base64 within redirect links; this module decodes them to extract the actual target URL."],
        ["urllib.parse", "Python stdlib", "Stdlib", "URL parsing -- extracts domains, query parameters, and normalizes URLs from search results"],
    ]
    story.append(make_table(s6, [80, 110, 50, 264]))
    story.append(Spacer(1, 5))

    # Stage 7
    story.append(Paragraph("Stage 7: Web Page Fetching & HTML Content Distillation", H2))
    story.append(Paragraph(
        "Files: <code>pipeline/page_fetcher.py</code>, <code>scraper/distiller.py</code> -- Securely fetches and extracts clean article text.",
        BULLET
    ))
    s7 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["httpx", "httpx==0.25.1", "External", "HTTP client for fetching web pages. Enforces response size limits (max 5MB), connection timeouts, and compliant User-Agent headers."],
        ["trafilatura", "trafilatura", "External", "Primary article text extractor. State-of-the-art content extraction that strips navigation, ads, footers, cookie banners, and sidebars to isolate the core article body from raw HTML."],
        ["beautifulsoup4", "beautifulsoup4==4.12.2", "External", "Fallback text extractor. Multi-container content selector pipeline (article, main, div.content) when trafilatura fails on JS-heavy or Cloudflare-protected pages."],
        ["socket", "Python stdlib", "Stdlib", "SSRF defense -- resolves hostnames to IP addresses before connecting to verify the target is not a private/loopback/link-local address"],
        ["ipaddress", "Python stdlib", "Stdlib", "SSRF defense -- validates resolved IPs against RFC1918 private ranges (10.x, 172.16.x, 192.168.x) and cloud metadata endpoints (169.254.169.254)"],
        ["hashlib", "Python stdlib", "Stdlib", "Content deduplication -- SHA-256 hashes fetched page content to detect and skip duplicate pages returned from different search engines"],
    ]
    story.append(make_table(s7, [80, 110, 50, 264]))
    story.append(Spacer(1, 5))

    # Stage 8
    story.append(Paragraph("Stage 8: Multi-Engine Text Matching (N-gram, Fuzzy, Seed-Extend, Semantic)", H2))
    story.append(Paragraph(
        "Files: <code>pipeline/ngram_matcher.py</code>, <code>pipeline/fuzzy_matcher.py</code>, "
        "<code>pipeline/seed_extend.py</code>, <code>pipeline/semantic_matcher.py</code>, <code>alignment.py</code>",
        BULLET
    ))
    s8 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["difflib", "Python stdlib", "Stdlib", "SequenceMatcher -- computes token-level and character-level similarity ratios between document sentences and scraped web text. Used by FuzzyMatcher and SequenceAligner."],
        ["datasketch", "datasketch==1.6.4", "External", "MinHash and LSH (Locality-Sensitive Hashing). Approximate Jaccard similarity for rapid document-level near-duplicate detection before expensive pairwise comparison."],
        ["fastembed", "fastembed", "External", "SemanticMatcher uses the same all-MiniLM-L6-v2 model to encode both document sentences and scraped webpage passages into vectors, then computes cosine similarity."],
        ["re", "Python stdlib", "Stdlib", "k-shingle generation (splitting text into overlapping k-word windows), text normalization, and pattern-based token extraction in SeedAndExtendAligner."],
        ["math", "Python stdlib", "Stdlib", "math.sqrt() for cosine similarity denominator: cos(u,v) = dot(u,v) / (||u|| * ||v||). Used in SemanticMatcher."],
    ]
    story.append(make_table(s8, [80, 110, 50, 264]))
    story.append(Spacer(1, 5))

    # Stage 9
    story.append(Paragraph("Stage 9: False Positive Filtering & Evidence Scoring", H2))
    story.append(Paragraph(
        "Files: <code>pipeline/false_positive.py</code>, <code>pipeline/evidence_scorer.py</code>, <code>pipeline/entity_verifier.py</code>",
        BULLET
    ))
    s9 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["re", "Python stdlib", "Stdlib", "Pattern matching for boilerplate detection (cookie consent text, navigation phrases, footer disclaimers). Filters false matches from common web chrome."],
        ["urllib.parse", "Python stdlib", "Stdlib", "urlparse() extracts domain names from source URLs for domain-level confidence scoring and source clustering attribution."],
    ]
    story.append(make_table(s9, [80, 110, 50, 264]))
    story.append(Spacer(1, 5))

    # Stage 10
    story.append(Paragraph("Stage 10: Data Modeling, Pipeline Orchestration & Reporting", H2))
    story.append(Paragraph(
        "Files: <code>pipeline/schemas.py</code>, <code>pipeline/orchestrator.py</code>, <code>pipeline/source_clusterer.py</code>",
        BULLET
    ))
    s10 = [
        ["Library", "PyPI Package", "Type", "Purpose in PlagiaScan"],
        ["pydantic", "pydantic==2.5.2", "External", "Typed data schemas (BaseModel) for every pipeline stage: DocumentSentence, SearchQuery, SearchResult, CandidatePage, SourceMatch, SourceCluster, WebDetectionResult, SentenceAudit, etc."],
        ["logging", "Python stdlib", "Stdlib", "Structured pipeline logging with per-module loggers (plagiascan.pipeline.orchestrator, plagiascan.pipeline.semantic, etc.)"],
        ["enum", "Python stdlib", "Stdlib", "Enum types: MatchType (EXACT_NGRAM, FUZZY_LEXICAL, SEMANTIC), VerificationStatus, Confidence (HIGH, MEDIUM, LOW)"],
        ["datetime", "Python stdlib", "Stdlib", "Timestamps for fetch cache TTL management and audit trail recording"],
        ["time", "Python stdlib", "Stdlib", "Performance timing -- measures duration of each pipeline stage for logging and optimization"],
    ]
    story.append(make_table(s10, [80, 110, 50, 264]))
    story.append(Spacer(1, 6))

    # ══════════════════════════════════════════════════════════════════════════
    # ENGINE 2: AI CONTENT DETECTION
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("3. Engine 2: AI Content Detection -- Complete Library Inventory", H1))
    story.append(hr())
    story.append(Paragraph(
        "The AI detection engine lives entirely within the <code>detect_ai_content()</code> function in "
        "<code>app/core/detection.py</code> (lines 493-658). It uses <b>zero external libraries</b> and "
        "<b>zero pre-trained models</b>. The entire engine runs on two Python standard library modules.",
        BODY
    ))

    story.append(callout(
        "<b>Critical Interview Point:</b> The AI detector has ZERO external dependencies. No neural network, no API calls, "
        "no model weights, no training data. It is a pure hand-coded 6-signal statistical NLP heuristic ensemble "
        "using only Python's built-in regex engine and math module.",
        AMBER_LIGHT, AMBER
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("Complete Library List for AI Detection Engine:", H2))
    ai_table = [
        ["Library", "Type", "Signals Using It", "Exact Usage in detect_ai_content()"],
        [
            "re",
            "Python stdlib",
            "All 6 Signals",
            "<b>Signal 1 (Archetype):</b> re.match() for 'Term: Definition' patterns, re.search() for LLM section headers, hypothetical scenarios. "
            "<b>Signal 2 (Anaphora):</b> re.sub() strips bullet prefixes from sentence starters. "
            "<b>Signal 3 (Hallmarks):</b> Iterates 47 compiled regex patterns from HALLMARK_PATTERNS list. "
            "<b>Signal 4 (Formality):</b> re.findall() counts contractions (don't, can't, I'm). "
            "<b>Signal 5 (Burstiness):</b> re.split() on sentence boundaries, re.match() filters list items. "
            "<b>Signal 6 (Transitions):</b> string.count() on transition phrase list."
        ],
        [
            "math",
            "Python stdlib",
            "Signal 5 (Burstiness)",
            "math.sqrt() computes standard deviation for the Coefficient of Variation formula: "
            "CV = sigma / mu, where sigma = sqrt(variance) of sentence word counts. "
            "Low CV (uniform sentence lengths) indicates LLM output; high CV (varied lengths) indicates human writing."
        ],
    ]
    story.append(make_table(ai_table, [50, 60, 85, 309]))
    story.append(Spacer(1, 5))

    story.append(Paragraph("How Each Signal Maps to Its Library:", H2))
    signal_lib_table = [
        ["Signal #", "Signal Name", "Library Used", "Core Function Call", "What It Computes"],
        ["1", "Structural Archetype", "re", "re.match(), re.search()", "Counts 'Term: Definition' list items, LLM section headers, hypothetical scenarios, pipeline arrows"],
        ["2", "Anaphora Density", "re", "re.sub(), str.split()", "Frequency of identical sentence openers (first 2 words) -- measures repetitive syntax starters"],
        ["3", "Lexical Hallmarks", "re", "re.search() x 47 patterns", "Density of LLM-overused phrases: 'delve', 'testament', 'crucial role', 'furthermore', etc."],
        ["4", "Formality Score", "re", "re.findall()", "Counts contractions (don't, can't, I'm) and exclamation marks. Zero contractions = maximally suspicious"],
        ["5", "Burstiness (CV)", "re + math", "re.split(), math.sqrt()", "Coefficient of Variation of sentence lengths. CV = sqrt(variance) / mean. Low CV = LLM"],
        ["6", "Transition Overuse", "re (indirect)", "str.count(), len(re.findall())", "Transition density per 1000 words. Counts 'furthermore', 'moreover', 'consequently', etc."],
    ]
    story.append(make_table(signal_lib_table, [40, 90, 55, 110, 209]))
    story.append(Spacer(1, 6))

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY COMPARISON
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("4. Complete Side-by-Side Library Count Summary", H1))
    story.append(hr())

    summary_table = [
        ["Category", "Engine 1: Web Plagiarism", "Engine 2: AI Detection"],
        ["External Libraries", "pypdf, python-docx, beautifulsoup4, pytesseract, Pillow, tiktoken, fastembed, qdrant-client, duckduckgo-search, httpx, lxml, trafilatura, datasketch, pydantic (14 total)", "None (0 total)"],
        ["Python Stdlib Modules", "re, math, difflib, socket, ipaddress, hashlib, unicodedata, urllib.parse, base64, mimetypes, logging, enum, datetime, time, uuid (15 total)", "re, math (2 total)"],
        ["Pre-Trained ML Model", "all-MiniLM-L6-v2 (22M params, 384-dim vectors, contrastive-trained on 1B+ sentence pairs by Microsoft/UKP)", "None -- zero neural networks, zero model weights"],
        ["ML Framework", "fastembed (ONNX Runtime) -- no PyTorch or TensorFlow required", "None"],
        ["Training Performed", "None -- model used for inference only (pre-trained by Microsoft)", "None -- all 6 signals are hand-coded regex + statistics"],
        ["Dataset Used", "None for training. 50-sample benchmark is evaluation-only (eval/labeled_samples.json)", "None for training. Same 50-sample benchmark validates heuristic accuracy"],
        ["Inference Cost", "fastembed ONNX: ~5ms per chunk, Qdrant HNSW: ~2ms per query", "$0 -- zero API calls, zero model inference, pure CPU regex"],
        ["Total Execution Time", "1.2s - 2.5s (dominated by network I/O for web search + page fetching)", "<20ms on CPU (all 6 signals computed in-memory)"],
    ]
    story.append(make_table(summary_table, [110, 197, 197]))
    story.append(Spacer(1, 6))

    # ── INTERVIEW SECTION ────────────────────────────────────────────────────
    story.append(Paragraph("5. Interview-Ready Technical Responses", H1))
    story.append(hr())

    def qa(num, q, a, takeaway):
        items = []
        items.append(Paragraph(f"<b>Q{num}: {q}</b>", sty(f"Q{num}", fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=PRIMARY)))
        items.append(Spacer(1, 2))
        items.append(Paragraph(f"<b>Answer:</b> {a}", BODY))
        items.append(Spacer(1, 2))
        items.append(callout(f"<b>Key Takeaway:</b> {takeaway}", EMERALD_LIGHT, EMERALD))
        items.append(Spacer(1, 5))
        return KeepTogether(items)

    story.append(qa(
        1,
        "What libraries does your plagiarism engine use and why?",
        "The web plagiarism pipeline uses 14 external packages across 10 stages. For document ingestion: pypdf, python-docx, and pytesseract+Pillow for OCR. "
        "For chunking: tiktoken (OpenAI's BPE tokenizer). For embeddings: fastembed loads all-MiniLM-L6-v2 via ONNX runtime -- no PyTorch needed, keeping the Docker image ~500MB instead of ~4GB. "
        "For vector search: qdrant-client with HNSW indexing. For web search: duckduckgo-search as the primary provider with httpx+lxml for Bing HTML parsing as fallback. "
        "For content extraction: trafilatura (state-of-the-art article distillation) with beautifulsoup4 as fallback. "
        "For matching: datasketch provides MinHash/LSH for approximate Jaccard similarity, while difflib.SequenceMatcher handles token-level fuzzy matching. "
        "Pydantic enforces typed schemas across all 10 pipeline stages.",
        "Shows deliberate library selection -- each dependency was chosen for a specific engineering reason, not arbitrarily."
    ))

    story.append(qa(
        2,
        "Why does the AI detector use zero external libraries?",
        "The AI detection engine deliberately avoids external dependencies for three engineering reasons: "
        "(1) <b>Zero inference cost</b> -- no GPU, no API credits, no model hosting. The entire detector runs on Python's built-in re module (regex) and math.sqrt(). "
        "(2) <b>Full explainability</b> -- every flagged sentence has a human-readable reason ('Contains LLM rhetorical marker: plays a crucial role') instead of an opaque neural confidence score. "
        "(3) <b>No distribution drift</b> -- trained classifiers degrade when new LLMs (GPT-5, Claude 4) are released because their token distributions shift. "
        "Our regex hallmark patterns and burstiness statistics are model-agnostic -- they detect the structural and linguistic artifacts of autoregressive generation itself, not any specific LLM's vocabulary.",
        "Demonstrates practical engineering judgment: choosing the simplest tool that solves the problem reliably."
    ))

    story.append(qa(
        3,
        "Why fastembed instead of sentence-transformers or PyTorch directly?",
        "sentence-transformers requires PyTorch (~2GB), which bloats the Docker image to ~4GB and requires CUDA for GPU acceleration. "
        "fastembed loads the same all-MiniLM-L6-v2 model but runs inference through ONNX Runtime (~50MB), which is a CPU-optimized, cross-platform inference engine. "
        "The result is identical 384-dimensional vectors at similar speed, but the deployment footprint is 8x smaller and requires zero GPU configuration.",
        "Shows deployment-aware engineering -- optimizing for production container size and infrastructure cost."
    ))

    story.append(qa(
        4,
        "Why trafilatura for web scraping instead of just BeautifulSoup?",
        "BeautifulSoup is a general-purpose HTML parser -- it gives you the DOM tree but doesn't know what is 'content' vs 'navigation' vs 'advertisement'. "
        "You'd need to manually write CSS selector heuristics for every website layout. trafilatura is a purpose-built article text extraction library that uses "
        "machine-learned content density heuristics and DOM structure analysis to automatically identify the main article body, stripping headers, footers, "
        "cookie banners, sidebars, and ads. It handles GeeksforGeeks, Medium, WordPress, and documentation sites out of the box. "
        "We keep BeautifulSoup as a fallback for Cloudflare-protected and JS-heavy pages where trafilatura's static HTML analysis fails.",
        "Shows awareness of the web scraping problem space and a production-grade fallback strategy."
    ))

    # ── RESUME BULLETS ───────────────────────────────────────────────────────
    story.append(KeepTogether([
        Paragraph("6. Resume-Ready Technology Stack Bullet Points", H1),
        hr(),
        Paragraph(
            "<b>&bull; Plagiarism Engine Tech Stack:</b> Built a 10-stage web source detection pipeline using "
            "fastembed (MiniLM-L6-v2 ONNX), Qdrant HNSW vector search, DuckDuckGo/Bing multi-engine web retrieval, "
            "trafilatura/BeautifulSoup content distillation, and datasketch MinHash/LSH for approximate Jaccard similarity.",
            BULLET
        ),
        Paragraph(
            "<b>&bull; AI Detection Engine:</b> Engineered a zero-dependency 6-signal NLP heuristic ensemble "
            "(structural archetypes, sentence burstiness CV, lexical hallmarks, anaphora density) using only Python stdlib "
            "(re + math), achieving 94% accuracy and 0% false positives with &lt;20ms CPU-only execution.",
            BULLET
        ),
        Paragraph(
            "<b>&bull; Infrastructure & Deployment:</b> FastAPI + React 19 + SQLAlchemy + Qdrant, containerized with Docker Compose. "
            "Chose fastembed ONNX over PyTorch to reduce production image from ~4GB to ~500MB while maintaining identical embedding quality.",
            BULLET
        ),
    ]))

    # Build
    doc.build(story, canvasmaker=NumberedCanvas)

    for target in [WORKSPACE_PDF_PATH, ARTIFACT_PDF_PATH]:
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(PRIMARY_DOWNLOAD_PATH, target)
        except Exception as e:
            print(f"Warning copying to {target}: {e}")

    print(f"[SUCCESS] PDF built: {PRIMARY_DOWNLOAD_PATH}")
    print(f"[SUCCESS] Workspace: {WORKSPACE_PDF_PATH}")
    print(f"[SUCCESS] Artifact: {ARTIFACT_PDF_PATH}")


if __name__ == "__main__":
    build_pdf()
