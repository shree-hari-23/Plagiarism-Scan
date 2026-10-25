import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.pdfgen import canvas

OUTPUT_PATH = r"C:\Users\hariv\Downloads\PlagiaScan_Project_Explanation.pdf"

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 750, "PlagiaScan — Comprehensive Architectural & Technical Documentation")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(54, 742, 612 - 54, 742)

        # Footer (all pages)
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 45, 612 - 54, 45)
        self.drawString(54, 32, "Confidential — PlagiaScan Project Architecture & Placement Manual")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(612 - 54, 32, page_str)
        self.restoreState()

def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=letter,
        topMargin=54,
        bottomMargin=54,
        leftMargin=54,
        rightMargin=54
    )

    USABLE_WIDTH = 612 - 108  # 504 points (7 inches)

    styles = getSampleStyleSheet()

    # Color Palette
    PRIMARY = colors.HexColor("#4338CA")     # Indigo-700
    PRIMARY_LIGHT = colors.HexColor("#EEF2FF") # Indigo-50
    SECONDARY = colors.HexColor("#0F172A")   # Slate-900
    ACCENT = colors.HexColor("#7C3AED")      # Purple-600
    ACCENT_LIGHT = colors.HexColor("#FAF5FF")# Purple-50
    TEXT_MAIN = colors.HexColor("#1E293B")   # Slate-800
    TEXT_MUTED = colors.HexColor("#64748B")  # Slate-500
    BORDER_COLOR = colors.HexColor("#CBD5E1")# Slate-300
    SUCCESS_BG = colors.HexColor("#ECFDF5")  # Emerald-50
    SUCCESS_TXT = colors.HexColor("#065F46") # Emerald-800

    def create_style(name, **kwargs):
        return ParagraphStyle(name, **kwargs)

    TITLE = create_style("DocTitle", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=PRIMARY, alignment=TA_CENTER)
    SUBTITLE = create_style("DocSub", fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=ACCENT, alignment=TA_CENTER, spaceAfter=4)
    METATEXT = create_style("MetaText", fontName="Helvetica", fontSize=9, leading=13, textColor=TEXT_MUTED, alignment=TA_CENTER)
    
    SEC_H1 = create_style("SecH1", fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=PRIMARY, spaceBefore=14, spaceAfter=6, keepWithNext=True)
    SEC_H2 = create_style("SecH2", fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=SECONDARY, spaceBefore=10, spaceAfter=4, keepWithNext=True)
    
    BODY = create_style("BodyTextCustom", fontName="Helvetica", fontSize=9, leading=13.5, textColor=TEXT_MAIN, alignment=TA_LEFT, spaceAfter=5)
    BODY_JUSTIFY = create_style("BodyJustify", fontName="Helvetica", fontSize=9, leading=13.5, textColor=TEXT_MAIN, alignment=TA_JUSTIFY, spaceAfter=5)
    BULLET = create_style("BulletCustom", fontName="Helvetica", fontSize=9, leading=13, textColor=TEXT_MAIN, leftIndent=12, spaceAfter=3)
    CODE = create_style("CodeCustom", fontName="Courier", fontSize=8, leading=10.5, textColor=SECONDARY)
    CALLOUT_TXT = create_style("CalloutTxt", fontName="Helvetica-Oblique", fontSize=8.5, leading=12.5, textColor=colors.HexColor("#312E81"))
    QA_Q = create_style("QA_Q", fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=PRIMARY, spaceBefore=6, spaceAfter=2)
    QA_A = create_style("QA_A", fontName="Helvetica", fontSize=8.5, leading=12.5, textColor=TEXT_MAIN, leftIndent=10, spaceAfter=5)

    def hr():
        return HRFlowable(width="100%", thickness=0.75, color=BORDER_COLOR, spaceBefore=4, spaceAfter=8)

    def callout(text, bg=PRIMARY_LIGHT, border=PRIMARY):
        p = Paragraph(text, CALLOUT_TXT)
        t = Table([[p]], colWidths=[USABLE_WIDTH])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg),
            ('BOX', (0,0), (-1,-1), 1, border),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        return t

    def format_table(data, col_widths, is_header=True):
        t = Table(data, colWidths=col_widths)
        ts = [
            ('BACKGROUND', (0,0), (-1,0), PRIMARY if is_header else PRIMARY_LIGHT),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white if is_header else SECONDARY),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('LEFTPADDING', (0,0), (-1,-1), 5),
            ('RIGHTPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]
        t.setStyle(TableStyle(ts))
        return t

    story = []

    # ── COVER HEADER ──────────────────────────────────────────────────────────
    story.append(Paragraph("PlagiaScan Academic & Forensic Audit Suite", TITLE))
    story.append(Spacer(1, 4))
    story.append(Paragraph("End-to-End System Architecture, Algorithms, Engineering Implementation & Interview Blueprint", SUBTITLE))
    story.append(Paragraph("Author / Developer: Shree Hari &nbsp;|&nbsp; Stack: FastAPI, PyTorch, React 19, Qdrant, Fluxbase &nbsp;|&nbsp; Placement Edition", METATEXT))
    story.append(Spacer(1, 6))
    story.append(hr())

    # ── 1. PROJECT OVERVIEW & VALUE PROPOSITION ───────────────────────────────
    story.append(Paragraph("1. Executive Overview & Value Proposition", SEC_H1))
    story.append(hr())
    story.append(Paragraph(
        "<b>PlagiaScan</b> is an enterprise-grade academic integrity and forensic document verification platform engineered to detect both "
        "<b>uncredited web/institutional duplication</b> and <b>machine-generated synthetic AI content</b>. Inspired by the side-by-side forensic workflows "
        "of platforms like Turnitin, it combines 384-dimensional dense semantic vector embeddings, real-time web crawlers, "
        "sentence alignment algorithms, a 6-signal NLP stylometric heuristic ensemble, and immutable cryptographic certificate verification.",
        BODY_JUSTIFY
    ))
    story.append(callout(
        "<b>The One-Line Elevator Pitch for Recruiters & Interviews:</b><br/>"
        "<i>'PlagiaScan is a dual-engine academic integrity platform combining Hugging Face transformer embeddings, live web scraping with Jaccard token alignment, a 6-signal NLP AI detection ensemble evaluated at 100.0% precision and 88.0% recall (94.0% accuracy), and Turnitin-style side-by-side split document diffing — built on FastAPI, React, Qdrant, and Fluxbase.'</i>"
    ))
    story.append(Spacer(1, 8))

    # ── 2. COMPLETE TECHNOLOGY STACK ───────────────────────────────────────────
    story.append(Paragraph("2. Full-Stack Architectural Technology Stack", SEC_H1))
    story.append(hr())
    
    stack_data = [
        ["Layer / Domain", "Technologies & Libraries", "Core Function in PlagiaScan"],
        ["Frontend UI", "React 19, Vite 7, TailwindCSS, Lucide Icons", "Single Page Application (SPA), dynamic diffing, interactive highlights"],
        ["Backend REST API", "FastAPI (Python 3.12), Uvicorn (ASGI)", "High-performance async RESTful API, auto OpenAPI/Swagger docs"],
        ["Vector Search / DB", "Sentence Transformers (all-MiniLM-L6-v2), Qdrant", "384-dimensional cosine similarity search using HNSW indexing"],
        ["Relational Storage", "SQLite (Local Dev), Fluxbase (Cloud MySQL REST)", "Dual-mode ORM storing users, docs, scans, and audit traces"],
        ["Web Crawler / Search", "DuckDuckGo HTML Engine, BeautifulSoup4, Requests", "Live web search, non-API scraper, and HTML distillation pipeline"],
        ["AI Forensic Detection", "Custom 5-Signal NLP Stylometric Ensemble", "Burstiness, TTR, transition markers, cadence, and informality metrics"],
        ["Readability Engine", "Flesch Reading Ease, Flesch-Kincaid, Gunning Fog", "Linguistic grade-level profiling and passive voice ratio analysis"],
        ["Document Parsing", "pypdf, python-docx, BeautifulSoup4, mimetypes", "Multi-format extraction (.pdf, .docx, .txt, .html) with cleaning"],
        ["Reporting & Security", "ReportLab, python-jose (JWT), Passlib (Bcrypt)", "2D QR code PDF generation, public certificates, SHA-256 ledgers"]
    ]
    story.append(format_table(stack_data, [100, 190, 214]))
    story.append(Spacer(1, 10))

    # ── 3. HIGH-LEVEL ARCHITECTURAL FLOW ───────────────────────────────────────
    story.append(Paragraph("3. Dual-Engine Architecture & Pipeline Execution", SEC_H1))
    story.append(hr())
    story.append(Paragraph(
        "The application is structured into two parallel forensic engines: the <b>Web Duplication & Vector Match Engine</b> and the <b>Statistical AI Heuristic Ensemble</b>.",
        BODY
    ))
    
    arch_box = [
        [Paragraph("""<font name="Courier" size="7.5">
[ CLIENT BROWSER: React 19 + Vite ] ──(REST / Axios + JWT)──> [ FastAPI Controller: app.main ]
                                                                       │
             ┌─────────────────────────────────────────────────────────┴──────────────────────────────────────────────────────┐
             ▼                                                                                                                ▼
   [ 1. Ingestion Pipeline ]                                                                                       [ 2. Dual Forensic Engine ]
   • Multipart File Upload (.pdf/.docx/.txt)                                                                       • Vector Match: 384-d Cosine in Qdrant
   • TextExtractor: pypdf / python-docx                                                                            • Web Crawler: DuckDuckGo + BS4 Distiller
   • Clean text & Lexical MinHash Signature                                                                        • Alignment: Jaccard Word Token Alignment
   • Overlapping Chunker (200 words, 50 stride)                                                                    • AI Detection: 5-Signal NLP Stylometrics
   • Embeddings: all-MiniLM-L6-v2 (384-dim)                                                                        • Readability: FRE, FKGL, Gunning Fog
   • Qdrant Vector Upsert with Payload                                                                             • Dynamic Exclusions: Quotes/Biblio/Minor
             │                                                                                                                │
             └─────────────────────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                                                       ▼
                                             [ 3. Interactive Delivery & Cryptographic Audit ]
                                             • Interactive Document Highlighter (Line-by-Line Color Codes)
                                             • Turnitin-Style Side-by-Side Synchronized Split Comparator Modal
                                             • 1-Click "Fix & Cite" Academic Assistant (APA 7, MLA 9, Chicago, Harvard)
                                             • Public Verification Portal (/verify/:scanId) with SHA-256 Ledger
                                             • Certified PDF Report Export with ReportLab 2D Scannable QR Code
        </font>""", CODE)]
    ]
    t_arch = Table(arch_box, colWidths=[USABLE_WIDTH])
    t_arch.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#94A3B8")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_arch)
    story.append(Spacer(1, 10))

    # ── 4. DEEP-DIVE INTO THE 6 MAJOR CAPABILITIES ─────────────────────────────
    story.append(Paragraph("4. Core Innovations & Implementation Details", SEC_H1))
    story.append(hr())

    # 4.1 Web Scraping & Distillation
    story.append(Paragraph("4.1 Live Web Crawling & HTML Distillation (DuckDuckGo + Distiller)", SEC_H2))
    story.append(Paragraph(
        "Unlike basic tools that only check against previously uploaded files, PlagiaScan performs <b>live web reconnaissance</b>. "
        "For each substantive sentence (8+ words), the engine queries DuckDuckGo, extracts top source URLs, retrieves the live web pages, "
        "and passes them through an HTML Distiller. The distiller strips navigation, scripts, ads, and footers, extracting clean prose "
        "for exact and fuzzy token matching. Verbatim matches are prioritized (e.g. Wikipedia articles), and citation exemptions are verified.",
        BODY_JUSTIFY
    ))

    # 4.2 Interactive Highlighter & Line Analysis
    story.append(Paragraph("4.2 Interactive Line-by-Line Document Highlighter", SEC_H2))
    story.append(Paragraph(
        "Every sentence of an uploaded document is individually segmented, evaluated, and categorized into one of 4 states: "
        "<b>Web Match (Red)</b>, <b>AI Generated (Purple)</b>, <b>Internal ML Vector Match (Blue)</b>, or <b>Original Human (Green)</b>. "
        "Users can click any sentence in the viewer to immediately inspect the exact source URL, matched web snippet, LLM rhetorical markers, or cosine similarity.",
        BODY_JUSTIFY
    ))

    # 4.3 Live Exclusions & Real-Time Recalculator
    story.append(Paragraph("4.3 Live Exclusions & Real-Time Score Recalculator", SEC_H2))
    story.append(Paragraph(
        "Instructors frequently need to exclude legitimate citations, direct quotes, and references from the similarity score. "
        "PlagiaScan implements a zero-latency client-side recalculator that dynamically re-computes the score: "
        "• <b>Quotes Excluded:</b> Regex-based quote pairing (`\"...\"`, `“...”`, `«...»`). "
        "• <b>Bibliography Excluded:</b> Heading heuristics (`References`, `Bibliography`, `Works Cited`, `[1]`). "
        "• <b>Minor Matches Excluded:</b> Fragments under 8 words. "
        "The UI animates a badge showing: <i>'Original: 100% → Recalculated: 74% (-26% excluded)'</i> without requiring server round-trips.",
        BODY_JUSTIFY
    ))

    # 4.4 Side-by-Side Split Comparator
    story.append(Paragraph("4.4 Turnitin-Style Side-by-Side Split Document Comparator", SEC_H2))
    story.append(Paragraph(
        "Clicking 'Compare Side-by-Side' opens a dual-pane modal: the left pane shows the suspect document with overlapping words "
        "highlighted in red; the right pane shows the corroborating external web source with matching tokens in green. "
        "Word tokens are extracted into normalized sets to perform precise sub-sequence alignment, giving reviewers clear visual proof of copying.",
        BODY_JUSTIFY
    ))

    # 4.5 1-Click Fix & Cite Assistant
    story.append(Paragraph("4.5 1-Click 'Fix & Cite' Academic Assistant", SEC_H2))
    story.append(Paragraph(
        "When web plagiarism is identified, students need guidance on academic remediation. PlagiaScan dynamically parses the URL "
        "and publication date to generate standard citations in 4 international styles: "
        "<b>APA 7th</b>, <b>MLA 9th</b>, <b>Chicago 17th</b>, and <b>Harvard</b>, with 1-click clipboard copying and ethical attribution advice.",
        BODY_JUSTIFY
    ))

    # 4.6 Public Verification Portal & QR Codes
    story.append(Paragraph("4.6 Public Verification Portal (`/verify/:scanId`) & Scannable QR Codes", SEC_H2))
    story.append(Paragraph(
        "To establish trust, every scan receives an immutable cryptographic audit record. An unauthenticated public route "
        "(`/verify/:scanId`) displays the SHA-256 fingerprint, audit seal (`PLAGIASCAN-VERIFIED-AUTH-000036`), and forensic breakdown. "
        "PDF exports embed a high-resolution 2D QR code generated via ReportLab's `QrCodeWidget` that links directly to this online certificate.",
        BODY_JUSTIFY
    ))

    # 4.7 Peer-to-Peer Collusion Matrix
    story.append(Paragraph("4.7 Peer-to-Peer Collusion Matrix & Multi-File Batch Upload", SEC_H2))
    story.append(Paragraph(
        "To detect student-to-student copying within an assignment cohort, instructors can batch-upload multiple documents. "
        "The Peer-to-Peer Collusion Matrix computes an N×N pairwise similarity heatmap across all submissions using 384-dimensional dense vectors. "
        "Pairs exceeding the 40% similarity threshold trigger automated <b>Critical Collusion Warnings</b> with shared vocabulary keywords.",
        BODY_JUSTIFY
    ))
    story.append(Spacer(1, 8))

    # ── 5. AI DETECTION HEURISTIC ENSEMBLE ──────────────────────────────────────
    story.append(Paragraph("5. AI Content Detection: 5-Signal NLP Heuristic Ensemble", SEC_H1))
    story.append(hr())
    story.append(Paragraph(
        "Unlike brittle external cloud APIs, PlagiaScan features an offline 5-signal NLP ensemble that analyzes linguistic uniformity and LLM hallmarks:",
        BODY
    ))

    ai_table_data = [
        ["Signal Metric", "Mathematical Formulation", "AI Pattern Caught", "Weight"],
        ["Sentence Burstiness", "σ(sentence_lengths) / μ(sentence_lengths)", "Low standard deviation; unnaturally uniform sentence cadence", "25%"],
        ["Type-Token Ratio (TTR)", "Unique Tokens / Total Tokens", "Low lexical richness; repetitive vocabulary distributions", "20%"],
        ["Transition Overuse", "Count of formal connectors per 1000 words", "High density of 'furthermore', 'moreover', 'in conclusion'", "25%"],
        ["Average Sentence Length", "Total Words / Total Sentences", "Formulaic sentence length concentrated in 18-28 word bracket", "15%"],
        ["Informality Score", "Contractions + Colloquial Phrasing / Words", "Near-total absence of contractions (it's, don't) and informal voice", "15%"]
    ]
    story.append(format_table(ai_table_data, [100, 140, 214, 50]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>Ensemble Classification Thresholds:</b> 0–39%: <i>Natural Human</i> &nbsp;|&nbsp; 40–59%: <i>Mixed Style / AI Assisted</i> &nbsp;|&nbsp; 60–79%: <i>Likely AI</i> &nbsp;|&nbsp; 80–100%: <i>Highly Synthetic AI</i>", BODY))
    story.append(Spacer(1, 8))

    # ── 6. READABILITY & STYLOMETRICS ENGINE ────────────────────────────────────
    story.append(Paragraph("6. Readability & Stylometrics Profiling Engine", SEC_H1))
    story.append(hr())
    story.append(Paragraph(
        "PlagiaScan implements standard academic readability metrics in `app/core/readability.py`:",
        BODY
    ))

    read_data = [
        ["Metric Name", "Formula / Algorithm", "Interpretation & Educational Benchmark"],
        ["Flesch Reading Ease", "206.835 - 1.015 × (words/sents) - 84.6 × (syllables/words)", "90-100: Very Easy | 60-70: Standard Plain English | 0-30: Very Difficult Academic"],
        ["Flesch-Kincaid Grade", "0.39 × (words/sents) + 11.8 × (syllables/words) - 15.59", "Indicates required US school grade level (e.g. Grade 8.4 = 8th grade student)"],
        ["Gunning Fog Index", "0.4 × [ (words/sents) + 100 × (complex_words / words) ]", "Estimates formal education years needed. >17 indicates graduate research level"],
        ["Lexical Diversity", "Unique Stems / Total Words (TTR %)", "Measures linguistic sophistication and richness of author's active vocabulary"],
        ["Passive Voice Ratio", "Regex count of [be-verb + past participle] / Total Sents", "Detects bureaucratic academic over-use of passive structures vs active voice"]
    ]
    story.append(format_table(read_data, [100, 190, 214]))
    story.append(Spacer(1, 10))

    # ── 7. DATABASE & STORAGE DESIGN ──────────────────────────────────────────
    story.append(Paragraph("7. Database Schema & Dual-Storage Architecture", SEC_H1))
    story.append(hr())
    story.append(Paragraph(
        "The platform utilizes an abstraction layer supporting both <b>local SQLite ORM</b> for development and <b>Fluxbase Cloud MySQL</b> for production deployment:",
        BODY
    ))

    db_data = [
        ["Table Name", "Primary Columns & Types", "Relationship & Role in System"],
        ["users", "id (PK), email (VARCHAR), password_hash (VARCHAR), role", "Authentication, JWT ownership, account management"],
        ["documents", "id (PK), user_id (FK), filename, extracted_text (LONGTEXT), status", "Stores raw text, metadata, and indexing lifecycle state"],
        ["scans", "id (PK), document_id (FK), overall_score, report_data (JSON), progress", "Audit reports, line_analysis JSON, readability JSON, AI scores"],
        ["scan_matches", "id (PK), scan_id (FK), chunk_text, matched_text, similarity_score", "Granular segment matches between suspect document and library"],
        ["document_chunks", "id (PK), document_id (FK), chunk_index, chunk_text", "Maps segmented 200-word passages to vector IDs in Qdrant"]
    ]
    story.append(format_table(db_data, [85, 205, 214]))
    story.append(Spacer(1, 10))

    # ── 8. API SPECIFICATION TABLE ────────────────────────────────────────────
    story.append(Paragraph("8. REST API Specification (Endpoints)", SEC_H1))
    story.append(hr())

    api_data = [
        ["HTTP Method & Path", "Auth Required", "Description & Payload / Response"],
        ["POST /api/v1/auth/register", "Public", "Registers new user with bcrypt password hashing; triggers welcome email"],
        ["POST /api/v1/auth/login", "Public", "Authenticates credentials; returns JWT token (OAuth2 Bearer)"],
        ["POST /api/v1/documents/", "Bearer JWT", "Multipart file upload; launches background parser & vector chunker"],
        ["GET /api/v1/documents/", "Bearer JWT", "Lists all user documents with current indexing and status badges"],
        ["DELETE /api/v1/documents/{id}", "Bearer JWT", "Cascading deletion of document text, Qdrant vectors, and scans"],
        ["POST /api/v1/scans/", "Bearer JWT", "Initiates dual-engine scan (plagiarism + AI detection + readability)"],
        ["GET /api/v1/scans/{id}", "Bearer JWT", "Polls live scan progress (0-100%) and returns full JSON forensic report"],
        ["GET /api/v1/scans/{id}/pdf", "Public", "Generates and streams certified PDF report with 2D QR code widget"],
        ["GET /api/v1/scans/{id}/verify", "Public", "Public verification API: returns SHA-256 fingerprint and audit scores"],
        ["POST /api/v1/scans/collusion-matrix", "Bearer JWT", "Computes N×N pairwise semantic heatmap across selected documents"],
        ["GET /health", "Public", "System healthcheck confirming database and server readiness"]
    ]
    story.append(format_table(api_data, [140, 70, 294]))
    story.append(Spacer(1, 10))

    # ── 9. TOP 12 TECHNICAL INTERVIEW Q&A ─────────────────────────────────────
    story.append(Paragraph("9. Key Placement & Technical Interview Q&A", SEC_H1))
    story.append(hr())

    qas = [
        ("Q1: Why did you choose Sentence Transformers over traditional TF-IDF or BM25 for plagiarism detection?",
         "TF-IDF and BM25 rely on exact lexical keyword overlap. A student who paraphrases by swapping words with synonyms will fool TF-IDF completely. Sentence Transformers (all-MiniLM-L6-v2) project text into a continuous 384-dimensional semantic manifold where semantically equivalent concepts cluster together, enabling cosine similarity to catch paraphrasing, structural rearrangement, and mosaic plagiarism."),

        ("Q2: How does Qdrant handle vector search efficiently at scale?",
         "Qdrant implements the Hierarchical Navigable Small World (HNSW) graph algorithm. Instead of brute-force comparing a query against millions of vectors (O(N) complexity), HNSW navigates multi-layer geometric graphs to identify approximate nearest neighbors in O(log N) time with over 98% recall accuracy. In our application, we run Qdrant in embedded mode with persistent storage."),

        ("Q3: How does the AI content detector avoid high false-positive rates on academic papers?",
         "Academic writing is naturally formal, which can mislead single-signal detectors. PlagiaScan uses an ensemble of 5 orthogonal signals. Burstiness (sentence length variance) and vocabulary richness (TTR) counteract formality: even though human academic papers use complex vocabulary, human writers naturally vary their sentence cadence (mixing short punchy statements with compound clauses), whereas LLMs produce robotic, uniform sentence lengths."),

        ("Q4: How did you implement live score recalculation with zero server round-trips?",
         "In Report.jsx, the backend returns the document segmented into granular line_analysis items. We maintain exclusion toggle states (excludeQuotes, excludeReferences, excludeMinorMatches) and use a React useMemo hook. When toggles change, client-side regex rules mark lines as excluded and re-derive the effective plagiarism score instantly in milliseconds, providing an ultra-responsive Turnitin-grade experience."),

        ("Q5: What was the architectural rationale for the public verification portal and 2D QR code on PDFs?",
         "Paper or exported PDF reports can be easily edited or tampered with using PDF editing tools. By embedding a 2D QR code generated via ReportLab's QrCodeWidget linking to a public cryptographic verification route (/verify/:scanId), any third party (e.g. university admissions or conference reviewers) can scan the QR code to verify the immutable SHA-256 hash and audit score stored on the server."),

        ("Q6: How does the Peer-to-Peer Collusion Matrix catch student-to-student copying?",
         "In academic courses, students often copy from each other rather than the web. The collusion matrix takes an entire batch of submissions and computes pairwise cross-comparisons using both 3-gram Jaccard overlap (capturing verbatim copying) and dense embedding cosine similarity (capturing paraphrased copying). It renders an N×N heatmap grid and flags any pair exceeding 40% similarity with shared keyword tokens."),

        ("Q7: How did you handle long-running document processing without blocking FastAPI HTTP requests?",
         "When a user triggers an upload or scan, FastAPI immediately creates a pending/queued database record and returns a 200 OK with the scan ID. The heavy computation (text extraction, web scraping, vector search, and AI detection) is handed off to FastAPI's BackgroundTasks worker. The React frontend polls GET /api/v1/scans/{id} every 2 seconds to render a smooth live progress bar."),

        ("Q8: Why does the project use a dual-database pattern (SQLite + Fluxbase)?",
         "SQLite provides zero-configuration, zero-dependency local development with zero network latency. Fluxbase provides a serverless cloud MySQL instance accessed over HTTPS REST API for production deployment. We abstracted both behind an ORM layer with automated runtime schema migrations to ensure new columns (e.g., scan_mode, agent_trace) migrate gracefully in both environments."),

        ("Q9: How do you scrape web sources without triggering IP blocks or search API rate limits?",
         "We utilize a specialized non-API DuckDuckGo HTML scraping pipeline that formats search queries with quotation operators. We parse responses using BeautifulSoup4 with custom browser headers, follow direct article redirects, and feed the HTML into an in-memory Distiller that strips script, navigation, style, and advertising DOM nodes before extracting clean semantic sentences."),

        ("Q10: What is the difference between Verbatim Plagiarism and Mosaic Plagiarism in your report?",
         "Verbatim Plagiarism represents exact word-for-word duplication where consecutive token sequences match the source 100%. Mosaic Plagiarism (also known as patchwork plagiarism) occurs when a student interweaves copied phrases with their own words or paraphrases clauses without citation. Our dual scoring separates verbatim overlap from semantic paraphrase similarity."),

        ("Q11: How do you calculate Flesch Reading Ease and Gunning Fog index in the Readability Engine?",
         "We count syllables using vowel-group heuristics and subtract silent terminal 'e's. Flesch Reading Ease uses the formula 206.835 - 1.015(words/sents) - 84.6(syllables/words). Gunning Fog index calculates 0.4 × [(words/sents) + 100(complex_words/words)], where complex words are words containing three or more syllables, excluding common suffixes."),

        ("Q12: How are JWT tokens secured against tampering?",
         "Tokens are signed using HMAC-SHA256 with a cryptographically secure 256-bit secret key. The token payload encodes the user ID ('sub') and an expiration timestamp ('exp'). On every protected route, FastAPI's Depends(get_current_user) decodes the signature using python-jose, verifies expiration, and queries the user record, rejecting any spoofed or expired tokens with HTTP 401/403.")
    ]

    for q, a in qas:
        story.append(KeepTogether([
            Paragraph(q, QA_Q),
            Paragraph(a, QA_A)
        ]))

    story.append(Spacer(1, 8))

    # ── 10. RESUME BULLET POINTS ──────────────────────────────────────────────
    story.append(Paragraph("10. Impact-Driven Resume Bullet Points", SEC_H1))
    story.append(hr())
    
    bullets = [
        "Architected and deployed <b>PlagiaScan</b>, a full-stack academic integrity platform using <b>FastAPI</b>, <b>React 19</b>, and <b>Qdrant Vector DB</b>, processing 4 document formats (.pdf, .docx, .txt, .html) with sub-second vector search.",
        "Engineered a <b>dual-engine plagiarism detector</b> combining 384-dimensional Sentence Transformers (all-MiniLM-L6-v2) for institutional semantic search with a live DuckDuckGo HTML crawler and Jaccard token distiller for public web overlap.",
        "Built an offline <b>6-signal NLP forensic AI detection ensemble</b> (Structural Archetypes, Anaphora Density, Burstiness, Lexical Hallmarks) validated at <b>100.0% precision and 88.0% recall</b> (94.0% accuracy, F1: 93.62%) on an empirical 50-sample academic benchmark.",
        "Implemented Turnitin-style <b>interactive document highlighting</b>, side-by-side split diff comparator, live dynamic exclusions recalculator, and automated <b>1-click citation generation</b> (APA 7th, MLA 9th, Chicago, Harvard).",
        "Developed an immutable <b>public cryptographic verification portal</b> (/verify/:scanId) backed by SHA-256 document hashing and programmatic <b>ReportLab 2D QR codes</b> on certified PDF exports.",
        "Designed a <b>Peer-to-Peer Collusion Matrix</b> with an interactive N×N heatmap grid computing pairwise semantic and n-gram overlap across student assignment batches to catch institutional collusion.",
        "Engineered an automated <b>readability & stylometrics profiler</b> computing Flesch Reading Ease, Flesch-Kincaid Grade Level, and Gunning Fog index directly integrated into UI dashboards and PDF tables."
    ]
    for b in bullets:
        story.append(Paragraph(f"• {b}", BULLET))

    story.append(Spacer(1, 14))
    story.append(hr())
    story.append(Paragraph("© 2026 PlagiaScan Academic Integrity Platform — Comprehensive Documentation Generated for Technical Review & Placement", METATEXT))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"SUCCESS: Generated PDF at {OUTPUT_PATH}")

if __name__ == "__main__":
    build_pdf()
