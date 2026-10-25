# PlagiaScan Web Source Detection Engine — Design & Implementation Plan

**Version:** 2.0 (optimized from the original production prompt)
**Goal:** Given a document, report (a) which passages match public web pages, (b) which pages, (c) the evidence, (d) match type (exact / modified / paraphrase), and (e) which pages are mirrors of the same content, with **measured accuracy** rather than assumed accuracy.

> The score is *source-match confidence*, never a legal finding of plagiarism.

---

## 0. What changed vs. the original spec (and why)

| # | Original spec | Problem | Optimized design |
|---|---|---|---|
| 1 | Default N=25 exact n-gram | Misses edited copies and short copied passages; one changed word every 10 words defeats it | **Seed-and-extend alignment**: short seeds (k=6–8 tokens) found by hashing, then extended with edit tolerance into maximal spans. Fixed N becomes a *reporting threshold*, not the detector. |
| 2 | Search every sentence, 2–5 phrases each | Cost explodes (120 sentences × 5 phrases × 3 variants ≈ 1,800 queries/doc) and mostly wasted | **Two-phase adaptive probing**: sparse probes across the doc, then dense probing only around regions that hit (copying is contiguous). |
| 3 | Fetch every candidate URL | Fetch cost and latency dominate | **Snippet pre-screen** before fetch; **cross-query URL voting** ranks candidates. |
| 4 | Score = 40/20/15/10/10/5 weighted sum, includes *search rank* | Weights are arbitrary; search rank measures retrieval relevance, not copying | **Rule-based confidence tiers** with an explainable feature vector; weights/thresholds **calibrated on a labeled benchmark**. Search rank is used for ordering fetches only, not as evidence. |
| 5 | Semantic similarity contributes 10% to the same score | High semantic similarity is common for unrelated pages on the same topic | Semantic path is a **separate label** ("possible paraphrase"), capped at LOW/MEDIUM, requires lexical anchors (rare terms, numbers, entities). |
| 6 | "Common phrase" filter listed but unspecified | Main source of false positives | **Rarity-weighted evidence** (IDF mass) + exclusion zones (references, quotes, code, boilerplate). |
| 7 | Assumes quoted search always does exact match | Major engines do not guarantee phrase matching | Quoted queries are **best-effort**; each query has a relaxed fallback; snippet check confirms actual overlap. |
| 8 | No privacy handling for outbound queries | Sending document text to third-party search APIs is a data-disclosure event | **Query minimization** (short phrases only, never whole docs), per-tenant opt-out, provider DPA check, redaction of emails/IDs/names in student docs where possible. |
| 9 | Accuracy asserted, not measured | Cannot know if it works | **Evaluation harness is Phase 0**: benchmark, metrics, regression gate in CI. |
| 10 | Precedence ("original source") | Easily over-claimed | Explicit evidence ladder + wording rules; Wayback capture dates as legitimate evidence. |

---

## 1. Scope and honest limitations

The engine detects matches against **publicly indexed, fetchable web pages**. It cannot see:

- paywalled, login-gated, or `noindex`/robots-blocked content
- books, journals, and student-paper repositories not on the open web
- pages not surfaced by the configured search providers
- content in images/PDF scans (unless OCR is added to the fetch path)

Every report must state this coverage limit. "No match found" means *no match found in the searched public web*, not "original."

---

## 2. Architecture

```
Upload ─► Ingest & Extract ─► Segment + Exclusion Zones ─► Probe Planner
                                                              │
                        ┌─────────────────────────────────────┘
                        ▼
              Query Builder (exact / relaxed / entity)
                        ▼
        Search Router (providers, fallback, circuit breakers)
                        ▼
      Candidate Pool: normalize URL ─► dedupe ─► vote across queries
                        ▼
              Snippet Pre-screen (cheap lexical overlap)
                        ▼
      Safe Fetcher (SSRF-guarded, robots, cache) ─► Content Extractor
                        ▼
        ┌───────────────┴────────────────┐
        ▼                                ▼
 Seed-and-Extend Aligner        Paraphrase Matcher (only unmatched
 (exact + modified spans)       passages, only fetched candidate pages)
        └───────────────┬────────────────┘
                        ▼
   Span Scoring (rarity-weighted) ─► Attribution (greedy set cover)
                        ▼
   Mirror Clustering (SimHash/MinHash) ─► Precedence Evidence
                        ▼
                  Report Builder ─► DB + API
```

**Design principle:** every stage narrows the candidate set cheaply before an expensive stage runs. Expensive = fetching, alignment, embeddings.

**Recommended stack**

| Concern | Choice | Notes |
|---|---|---|
| API | FastAPI + Pydantic v2 | async, OpenAPI docs free |
| Queue/workers | Celery + Redis (or `arq`) | separate queues: `search`, `fetch`, `compare` |
| DB | PostgreSQL 15+ | `pgvector` for sentence embeddings |
| Object storage | S3-compatible | raw uploads, extracted page text (short TTL) |
| HTTP | `httpx` (async) + `tenacity` + `aiolimiter` | per-domain limits |
| Extraction | `trafilatura` (primary), `readability-lxml` fallback | metadata: title/author/date |
| Segmentation | `pysbd` or spaCy sentencizer | plus custom clause splitter |
| Fuzzy | `rapidfuzz` | token-set ratio, Levenshtein |
| Fingerprinting | `datasketch` (MinHash), custom SimHash | mirror clustering |
| Embeddings | `sentence-transformers` multilingual small model | batch, CPU/GPU configurable |
| Observability | Prometheus + structured JSON logs (`structlog`) + OpenTelemetry | |

---

## 3. Stage-by-stage design

### 3.1 Ingestion and text extraction
- PDF: `pdfminer.six`/`PyMuPDF` (retain page numbers); DOCX: `python-docx`; HTML: `trafilatura`; TXT direct.
- Reject/flag: encrypted PDFs, image-only PDFs (OCR optional plugin), files over size limit.
- Produce a canonical `document_text` string; **all offsets refer to this string**. Keep a `page_map` (char range → page).

### 3.2 Normalization (two copies, always)
`original_text` (for reports) and `normalized_text` (for matching), with a **token offset map** back to original characters so highlights are exact.

Deterministic pipeline: NFKC → unify quotes/dashes/ellipses → collapse whitespace → casefold → strip zero-width/soft-hyphen chars → de-hyphenate line-break splits (`inter-\nnational`) → tokenize on Unicode word boundaries (keep numbers, keep intra-word `'` and `-`).

### 3.3 Segmentation and exclusion zones
Sentence and clause units carry `sentence_id, paragraph_id, page, char_start, char_end`.

Handle abbreviations, decimals, URLs, bullets, headings, semicolons. Long sentences (>35 tokens) also yield clauses split on `;`, `:`, coordinating lists — but **clauses are for query generation only**; matching is done on the whole document via alignment, so clause splitting cannot fragment evidence.

**Exclusion zones** (matched text inside is *tagged*, not counted toward copy score):
- reference/bibliography sections (heading detection + citation-pattern density)
- text inside quotation marks with adjacent citation → tagged `quoted_attributed`
- block quotes, code blocks, tables of contents, headers/footers (repeated across pages), URLs
- user-supplied "ignore" list (assignment prompt, template text, required boilerplate)

### 3.4 Probe planning (the biggest efficiency lever)

**Passage candidates:** sliding windows of 10–18 tokens across each paragraph, stride 4–6.

**Distinctiveness score** of a window:
```
D(w) = Σ idf(t) over non-stopword tokens  +  bonus(named entities, numbers, rare bigrams)
       − penalty(boilerplate patterns, low-information openers)
```
- `idf` from a **background frequency table** (e.g., a public word-frequency list or a corpus you build). Never use only the uploaded doc for IDF.
- Reject windows below a minimum `D`, or that consist mostly of stopwords ("this system can be used to…").

**Phase 1 — sparse coverage:** choose the highest-`D` window per ~150 words (≥1 per paragraph), non-overlapping. Run those probes.

**Phase 2 — dense expansion:** for each region with a probe that yielded a *verified* hit (Section 3.9), probe the neighboring paragraphs and the unmatched gaps. Copying is contiguous, so this recovers full spans cheaply. Regions with no Phase-1 hit get an optional Phase 3 (higher `search_depth`) with a second, different window per paragraph to reduce the chance that the single probe just missed the index.

**Query budget** (configurable per `search_depth`):

| depth | Phase 1 probes/1000 words | queries per probe | results per query | max fetches/doc |
|---|---|---|---|---|
| quick | ~4 | 1 exact | 5 | 15 |
| standard | ~7 | ≤2 | 8 | 40 |
| deep | ~12 + Phase 3 | ≤3 | 10 | 100 |

### 3.5 Query construction
For each probe (10–18 token phrase):
1. **Exact:** `"phrase"` (8–14 tokens is the sweet spot; longer phrases fail more often on stemming/index variance).
2. **Relaxed:** top 4–6 rare terms, unquoted, plus one anchor entity if present.
3. **Shifted:** a different sub-window of the same passage (handles pages where a word differs mid-phrase).

Strip characters engines treat as operators; cap length (many APIs limit to ~32 words). Every query gets a `query_id`; search results record which probe/query found them.

### 3.6 Search router
```python
class SearchProvider(Protocol):
    name: str
    async def search(self, query: str, limit: int, *, lang: str | None) -> list[SearchHit]: ...
    # SearchHit: url, title, snippet, rank, provider, raw_meta
```
- Router order and weights from config; **fallback on failure/timeouts**; **circuit breaker** per provider (open after N failures in window; half-open probe).
- Per-provider quota accounting and rate limiting; daily budget guard per tenant.
- **Provider availability changes often** (APIs get retired, terms change). Verify current status and ToS of each provider before committing; do not scrape SERPs directly. Candidates: Brave Search API, Tavily, Exa, Google Programmable Search, SerpAPI-style resellers (review their ToS), and any Bing-successor offering.
- Engines do not honor quotes identically — the snippet pre-screen (3.7) is the ground truth.

### 3.7 Candidate pool and pre-screen
1. Canonicalize: lowercase host, strip fragments, remove tracking params (`utm_*`, `gclid`, `fbclid`, …), resolve `rel=canonical` after fetch (store both).
2. Dedupe by `canonical_url_hash`.
3. **Vote:** `votes[url]` = number of *distinct probes* (not queries) that returned it. Independent probes hitting the same URL is strong retrieval evidence. Fetch priority = `votes` desc, then best rank.
4. **Snippet pre-screen:** compute token overlap between the snippet and the probe phrase. Snippet shows the phrase (or ≥70% of its rare tokens) → fetch. No overlap and votes==1 and rank>5 → deprioritize (fetch only if budget remains).
5. Skip known-noise domains (search-result aggregators, the user's own upload URL if any, configurable allow/deny lists).

### 3.8 Safe fetching (security-critical)
- **SSRF:** resolve DNS yourself, reject if *any* resolved IP is loopback, link-local (169.254.0.0/16 incl. cloud metadata), private (RFC1918, CGNAT, ULA), multicast, or reserved; **connect to the validated IP** (pin, to prevent DNS rebinding) and **re-validate on every redirect hop**; allow only `http/https`, ports 80/443; max 5 redirects. Run fetch workers in a network-restricted egress environment (egress proxy/firewall) as a second layer.
- **Limits:** connect/read timeouts (e.g., 5s/15s), max body (e.g., 3 MB HTML; 15 MB PDF), streaming abort at cap, `Content-Type` allowlist (`text/html`, `application/xhtml+xml`, `text/plain`, optionally `application/pdf`), decompression-ratio cap.
- **Politeness/legal:** honor `robots.txt` (cached per host), identify with a stable User-Agent and contact URL, per-domain concurrency (e.g., 2) and delay, respect `Retry-After`. No CAPTCHA/anti-bot evasion.
- **Retries:** exponential backoff with jitter on 429/5xx/timeouts, max 2–3; never retry 4xx except 429.
- **Cache:** key `sha256(canonical_url)`; store `ETag/Last-Modified`, content hash, TTL (e.g., 7–30 days); conditional requests on refresh.
- **Untrusted content:** never execute JS, never render in a browser context with credentials, parse HTML with a hardened parser, treat all text as data. (If an LLM is ever used for explanations, page text goes in a data channel and never influences decisions — the detection path itself uses **no LLM**.)

### 3.9 Content extraction
`trafilatura.extract` (favor recall for verification, `include_tables=True`, keep headings/lists) → fallback `readability-lxml`. Output `{url, canonical_url, title, author, published_date, text, extracted_at, extraction_quality}` with unknown metadata as `null`. Discard pages whose extracted text is <200 words unless the match is inside them. Keep both the extracted text (for alignment) and, briefly, a hash of the raw HTML.

Record **extraction_quality** (text/HTML ratio, link density). Low-quality extraction → also compare against a lightly cleaned full-text fallback so a boilerplate-stripping error doesn't hide a match.

### 3.10 Core matcher: seed-and-extend alignment
Replaces the "N=25" primary detector.

**Index the document once** (per job): map each k-gram hash (k=6 by default; k=5 for short docs) → list of positions in the normalized doc token stream.

**For each candidate page:**
1. **Seed:** slide a k-gram over the page tokens; look up hits → list of `(doc_pos, src_pos)`.
2. **Diagonal grouping:** `diag = src_pos − doc_pos`. Group seeds by diagonal band (±G tokens, G≈8) so insertions/deletions stay in one chain.
3. **Chain and merge:** merge seeds on the same/near diagonal when the gap between them ≤ `max_gap` (default 8 tokens, or 25% of local span).
4. **Extend:** at both ends extend token by token with a small local alignment (banded Smith-Waterman/edit-distance) until identity over a trailing window drops below θ (default 0.7). This tolerates word substitutions, insertions, and synonym swaps.
5. **Emit spans:** `{doc_start, doc_end, src_start, src_end, matched_tokens, aligned_tokens, identity, longest_exact_run, edit_ops}`.

**Complexity:** O(|page|) hashing per page + alignment only in seeded regions. A stopword-only k-gram filter prevents seed spam.

**Why this beats fixed N-grams:** a passage with a changed word every 9 tokens has *no* 25-gram matches but still chains into a 60-token span with identity ≈ 0.9.

**Output metrics per (document, source):** `matched_tokens`, `document_coverage = matched_tokens / doc_tokens (non-excluded)`, `source_coverage`, `longest_exact_run`, `span_count`, `in_order` (spans monotonic in both docs), `matching_sentences`, `matching_paragraphs`.

### 3.11 Rarity-weighted evidence (false-positive control)
A span's strength is **not** its length alone:
```
rarity_mass(span) = Σ idf(t) over matched non-stopword tokens
```
- Long span of common words (definitions, boilerplate) → low mass.
- Also compute a **phrase commonness check**: the probe result count/cross-source frequency — if the same span appears in > M unrelated sources (e.g., ≥8 distinct domains), tag `common_phrase` and cap confidence at LOW.
- Numbers, entities, and code identifiers count extra; **code/keyword-only spans** (`import flask`) are excluded by the exclusion-zone rules.
- Minimum thresholds (initial values, to be calibrated — see Section 6): `matched_tokens ≥ 12` **and** `rarity_mass ≥ R_min`, else discard as noise.

### 3.12 Fuzzy matching
Used to *rescore and characterize* spans, not to discover them: `rapidfuzz.fuzz.token_set_ratio`, normalized Levenshtein on aligned spans, and ordered-token LCS. Populates `identity` and the `match_type` ∈ {`exact`, `modified`}. Fuzzy alone never yields HIGH.

### 3.13 Paraphrase (semantic) matcher
Runs **only** for document passages *not* covered by an exact/modified span, **only** against pages already fetched and having ≥1 verified span or ≥ threshold votes (topic-relevant pages).

1. Split page text into sentences/2-sentence windows; embed (batched, cached by content hash).
2. Embed uncovered doc sentences; cosine top-k against page windows (pgvector or in-memory for small pages).
3. Keep pairs with `cos ≥ τ_sem` **and** lexical anchors: ≥ 2 shared rare terms/entities/numbers **and** length ratio within 0.5–2.0.
4. Optional re-rank with a cross-encoder/NLI check to reduce topical-but-different pairs.
5. Label `match_type = "paraphrase_candidate"`; **max confidence LOW** unless multiple consecutive sentences pair in order from the same source (then MEDIUM, wording "possible paraphrase").

### 3.14 Source scoring and confidence
Keep the per-component explainability, but classify with **rules over a feature vector** first; fit a logistic model once labeled data exists (Phase 6).

Features: `longest_exact_run`, `aligned_tokens`, `identity`, `rarity_mass`, `span_count`, `in_order`, `probe_votes`, `document_coverage`, `source_coverage`, `common_phrase`, `semantic_max`, `extraction_quality`.

**Initial tiers (calibrate before launch):**

| Confidence | Rule of thumb |
|---|---|
| HIGH | `longest_exact_run ≥ 30` **or** aligned span ≥ 50 tokens with identity ≥ 0.85; and `rarity_mass ≥ R_high`; not `common_phrase`; not excluded zone |
| MEDIUM | aligned span ≥ 20 tokens with identity ≥ 0.70 and rarity OK; or ≥ 3 in-order spans of ≥ 12 tokens from one source |
| LOW | short/common spans, or paraphrase-only candidates |
| NONE | below floors; not reported (kept in audit log) |

Also output a numeric `source_match_score` (0–100) **derived from** the features via the tier function/logistic model, always with the component breakdown. Drop "search-result relevance" from the score; `probe_votes` is the only retrieval-derived feature and is used as a mild corroborator.

### 3.15 Attribution (which source explains which text)
Multiple pages may cover the same passage. Solve as **greedy weighted set cover**:
1. Cluster mirrors first (3.16).
2. For each cluster, union its covered doc spans.
3. Iteratively pick the cluster covering the most *uncovered* rarity-weighted document text; assign spans; repeat until marginal gain < ε.
4. Report per span: primary cluster + alternates.

This yields "8 sources explain 17 matched sentences" cleanly instead of 8 overlapping page lists.

### 3.16 Mirror clustering and precedence
**Clustering:** for each fetched page, compute MinHash (128 perms over 5-token shingles) and SimHash; cluster pages with Jaccard ≥ 0.8 over the matched region (or whole page for full mirrors) using LSH; union-find. Also join by identical `rel=canonical`.

**Precedence evidence ladder** (each item is stored as evidence, none is proof alone):
1. Explicit canonical/`original source` attribution from the mirror pointing to another URL
2. Published/modified dates from schema.org/`article:published_time`/HTTP headers (note: self-reported, can be wrong)
3. **Earliest archive capture** via Internet Archive availability/CDX APIs (legitimate public API; respect rate limits)
4. Domain role (official docs, vendor, author's own domain) — tagged, not decisive
5. Author attribution match

**Wording rules:** "Earliest identified source", "Likely source", "Possible source", "Matching source". Never "original" without explicit corroboration; show `precedence_evidence[]` in the UI.

### 3.17 Source classification
Rule/heuristic categories (documentation, news, academic/university, company, blog, forum, reference, aggregator, unknown) using domain patterns (`docs.`, `.edu`, `.ac.`), schema.org types, and page structure. Purely descriptive; not used in the score.

---

## 4. Data model (PostgreSQL)

```sql
documents(id, tenant_id, filename, mime, sha256, char_count, token_count,
          language, status, created_at, retention_until);

document_units(id, document_id, unit_type,            -- sentence | clause | paragraph
               paragraph_id, page, char_start, char_end,
               original_text, normalized_text, token_start, token_end,
               excluded_reason);                       -- null | reference | quoted | code | ...

probes(id, job_id, document_id, unit_id, phase, char_start, char_end,
       phrase, distinctiveness);

search_queries(id, probe_id, strategy,                 -- exact | relaxed | shifted
               query_text, provider, status, latency_ms, created_at);

search_results(id, query_id, url, canonical_url_hash, rank, snippet_overlap,
               retrieved_at);

source_pages(id, canonical_url, canonical_url_hash UNIQUE, domain, http_status,
             content_hash, title, author, published_date, source_category,
             fetched_at, etag, robots_allowed, extraction_quality, cluster_id);

source_content(page_id, extracted_text_ref, token_count, minhash BYTEA,
               simhash BIGINT, expires_at);           -- text in object storage w/ TTL

content_clusters(id, cluster_key, representative_page_id, page_count);

match_results(id, job_id, document_id, page_id, cluster_id, match_type,
              confidence, source_match_score, features JSONB,
              reasons JSONB, precedence_evidence JSONB);

match_spans(id, match_id, doc_char_start, doc_char_end, src_char_start,
            src_char_end, matched_tokens, aligned_tokens, identity,
            longest_exact_run, excerpt_doc, excerpt_src);   -- short excerpts only

sentence_embeddings(page_id, window_idx, embedding VECTOR(384), content_hash);

plagiarism_jobs(id, document_id, tenant_id, status, options JSONB, stats JSONB,
                error, created_at, started_at, finished_at, idempotency_key);

audit_events(id, job_id, ts, event_type, provider, url, http_status, latency_ms, detail JSONB);
```

Indexes: `canonical_url_hash` (unique), `(job_id)` everywhere, `content_hash`, GIN on `features`, IVFFlat/HNSW on embeddings. Migrations via Alembic. Retention: purge `source_content` text per policy and `documents` per tenant retention setting.

---

## 5. API

```
POST /api/v1/plagiarism/web-source-detection      -> 202 {job_id, status:"queued"}
GET  /api/v1/plagiarism/jobs/{job_id}             -> status, progress {phase, %}, stats
GET  /api/v1/plagiarism/jobs/{job_id}/report      -> matches (paginated), clusters, coverage summary
GET  /api/v1/plagiarism/jobs/{job_id}/matches/{id}-> full evidence for one match
DELETE /api/v1/plagiarism/jobs/{job_id}           -> purge derived data
```

Request options: `search_depth` (quick|standard|deep), `enable_semantic_matching`, `min_span_tokens`, `ignore_ranges`, `ignore_domains`, `max_sources_per_passage`, `language`.

Requirements: `Idempotency-Key` header, auth + tenant scoping, per-tenant rate limits, optional webhook on completion, job states `queued → extracting → probing → fetching → matching → clustering → completed | failed | partial`. **`partial`** is a first-class result (provider outage): report what was found and what coverage was lost.

Match response shape:
```json
{
  "match_id": "m_01",
  "confidence": "HIGH",
  "source_match_score": 94,
  "match_type": "exact",
  "document_span": {"char_start": 421, "char_end": 900, "page": 1, "excerpt": "..."},
  "primary_source": {"url": "...", "title": "...", "category": "official_documentation",
                     "excerpt": "..."},
  "cluster": {"cluster_id": "c_3", "mirrors": ["...", "..."]},
  "evidence": {"matched_tokens": 87, "longest_exact_run": 42, "identity": 0.96,
               "span_count": 3, "in_order": true, "probe_votes": 2,
               "rarity_mass": 143.2, "document_coverage": 0.12},
  "reasons": ["87 tokens matched at 96% identity", "3 spans in the same order",
              "found by 2 independent probes"],
  "precedence": {"label": "earliest_identified_source",
                 "evidence": ["archive capture 2019-04-02", "published_date 2019-03-30"]}
}
```

---

## 6. Accuracy strategy: how we *prove* it works

### 6.1 Evaluation datasets
1. **Public text-reuse benchmarks:** PAN text-alignment / source-retrieval corpora and the Webis Text Reuse Corpus (web-based reuse with human annotation). Check each license and current availability before use.
2. **Synthetic injection set (build this):** take real web pages (Wikipedia, docs sites, blogs), inject passages into original filler text at controlled **obfuscation levels**:
   - L0 verbatim; L1 light edits (1 change per 15 words); L2 heavy edits (1 per 6 words); L3 synonym/reorder; L4 machine paraphrase; L5 translated back.
3. **Negative sets:** original student-style essays, definitions-heavy text, code/docs boilerplate, bibliographies, quotation-heavy essays, same-topic-different-text.
4. **Mirror set:** original + 3–5 scraped copies with dates.

Freeze web content via **saved snapshots** (WARC/HTML fixtures behind a fake search provider) so benchmark runs are deterministic and cheap; run a small **live** smoke set nightly.

### 6.2 Metrics
| Level | Metric |
|---|---|
| Source retrieval | Recall@k of the true source URL/cluster; queries and fetches per doc |
| Passage detection | Character-level precision/recall/F1; PAN **PlagDet** (accounts for granularity) |
| Confidence calibration | Precision per tier (HIGH target ≥ 0.98 on negatives-heavy set), reliability curve |
| False positives | FP rate on negative sets, per 1,000 words |
| Mirror clustering | Cluster purity / pairwise F1 |
| Precedence | Accuracy of earliest-source identification where ground truth known; abstention rate |
| Cost/latency | Search calls, fetches, seconds, $ per 1,000 words |

### 6.3 Targets (initial; adjust after baseline)
- HIGH-tier precision ≥ 0.98 on the negatives-heavy set.
- L0–L1 passage recall ≥ 0.95 given the source is fetchable and indexed.
- L2 recall ≥ 0.80; L3–L4 recall reported separately (paraphrase = LOW/MEDIUM by design).
- Source retrieval recall@10 ≥ 0.90 for verbatim ≥ 30-word passages on `standard`.
- Median standard job (3,000 words) < 3 minutes; ≤ 40 fetches.

### 6.4 Calibration and regression gate
- Tune `k`, `max_gap`, `θ`, `R_min`, tier thresholds with a held-out split; freeze; report on a test split.
- CI runs the fixture benchmark; a PR **fails** if HIGH precision drops, or recall on L0–L2 drops > 2 points.
- Human-review loop: reviewers label a sample of production HIGH/MEDIUM matches monthly → feeds the calibration set (with tenant consent/anonymization).

---

## 7. Security, privacy, and compliance

- **Outbound query privacy:** send only probe phrases (≤ 18 tokens), never the full document; randomize/spread probes; tenant setting to disable web search (then only bring-your-own-corpus mode); log query hashes rather than text where possible.
- **PII:** optional pre-query redaction of emails, phone numbers, IDs; don't search on phrases dominated by personal names unless enabled.
- **Data retention:** uploaded documents and extracted page text have TTLs; reports store **short excerpts** only (cap ~300 chars per side); `DELETE` purges derived data.
- **Copyright:** cache extracted text only as needed for verification, with expiry; don't redistribute page content; link to source.
- **Web ToS:** provider APIs only; robots.txt honored; no CAPTCHA/anti-bot circumvention.
- **Untrusted content:** parsers sandboxed, resource-limited, no script execution; webpage text never interpreted as instructions.
- **Secrets:** env-based config, secret manager in prod, no keys in code or logs.
- **Auth/tenancy:** row-level tenant scoping; audit log for report access.
- **Fairness/UX:** the report must not present a percentage as a verdict; show evidence, coverage limits, and "excluded (quoted/cited)" regions so instructors can judge.

---

## 8. Observability and operations

**Structured JSON logs:** `job_id, document_id, unit_id, probe_id, query_id, provider, url_hash, http_status, latency_ms, stage, extraction_status, match_tier, error_code` — **no document text** (hash or offsets only).

**Metrics (Prometheus):** search latency/success by provider, fetch latency/success/status distribution, cache hit rate (search/page/embedding), candidates per probe, verified-hit rate per probe, queries and fetches per 1,000 words, circuit-breaker state, queue depth and age per queue, job duration by phase, tier distribution, semantic-vs-exact ratio.

**Quality monitors:** weekly precision sample from human review; alert on sudden change in HIGH-rate distribution (drift or extraction regression); alert on rising `partial` job share.

**Resilience:** idempotent tasks, job checkpointing per phase (resume after worker crash), dead-letter queue, graceful degradation (provider down → fallback → `partial`).

---

## 9. Repository layout

```
plagiascan/
  api/            routers, dependencies, auth
  schemas/        Pydantic request/response/domain models
  models/         SQLAlchemy models
  database/       session, migrations (alembic/)
  services/       job orchestration, report builder
  ingestion/      pdf/docx/html/txt extractors
  text/           normalization, tokenization, segmentation, exclusion zones
  planning/       distinctiveness, probe planner, query builder
  search/         base.py, providers/, router.py, breaker.py
  retrieval/      url_canon.py, ssrf.py, fetcher.py, robots.py, cache.py
  extraction/     html_extractor.py, metadata.py, quality.py
  matching/       kgram_index.py, seed_extend.py, spans.py, fuzzy.py, rarity.py
  embeddings/     encoder.py, paraphrase_matcher.py
  scoring/        features.py, tiers.py, calibration.py, reasons.py
  clustering/     minhash.py, simhash.py, precedence.py, classify.py
  workers/        celery_app.py, tasks_*.py
  utils/          logging.py, metrics.py, config.py, hashing.py
  eval/           datasets/, snapshots/, fake_provider.py, run_benchmark.py
  tests/          unit/, integration/, security/, e2e/
  docker/         Dockerfile, docker-compose.yml
  .env.example
  README.md
```

---

## 10. Implementation plan

Assumption: 2–3 backend engineers, 1 part-time reviewer/annotator. Adjust durations proportionally.

### Phase 0 — Foundations and evaluation harness (Week 1–2)
- Repo scaffold, CI, lint/type checks, Docker Compose (API, worker, Redis, Postgres).
- Build the **benchmark first**: synthetic injection generator (L0–L5), negative sets, frozen page snapshots, `FakeSearchProvider`, metric scripts (PlagDet, precision by tier).
- Write the spec of thresholds as *configurable* values.
- **Exit:** `run_benchmark.py` produces a baseline report from a trivial exact-match baseline.

### Phase 1 — Offline core: text + matcher (Week 2–5)
- Ingestion, normalization with offset maps, segmentation, exclusion zones.
- k-gram index, seed-and-extend aligner, span metrics, rarity weighting, fuzzy rescoring.
- Feature computation + rule-based tiers + reason generation.
- **No network yet**: matches document vs fixture pages.
- **Exit:** L0 recall ≥ 0.98, L1 ≥ 0.9, HIGH precision ≥ 0.98 on negatives using fixtures; unit tests for edge cases (abbreviations, hyphenation, unicode, PDFs).

### Phase 2 — Discovery: probes, queries, search (Week 4–7)
- Background IDF table, distinctiveness scoring, two-phase probe planner, query builder.
- Provider abstraction + 2 real providers + router, fallback, circuit breaker, quota accounting.
- URL canonicalization, dedupe, cross-probe voting, snippet pre-screen.
- **Exit:** on the live smoke set, recall@10 of the true source ≥ 0.85 with ≤ budgeted queries; measure queries/1,000 words.

### Phase 3 — Safe retrieval + extraction (Week 6–8)
- SSRF guard (DNS pinning, per-hop validation), robots.txt, per-domain limiter, size/type/decompression limits, cache with conditional requests.
- trafilatura extraction + fallback + quality score + metadata (nulls, never invented).
- **Exit:** security test suite passes (metadata IP, rebinding, redirect-to-private, gzip bomb, huge body, wrong content-type); extraction fidelity checked on 200 pages.

### Phase 4 — Async pipeline, DB, API (Week 7–10)
- Schema + Alembic migrations; Celery queues (`search`, `fetch`, `compare`); phase checkpointing; `partial` handling.
- API endpoints, idempotency, tenant scoping, pagination, webhook.
- Report builder with side-by-side highlights and excerpts.
- **Exit:** end-to-end run on benchmark via API; crash-recovery test (kill worker mid-job).

### Phase 5 — Clustering, precedence, attribution, semantic (Week 9–12)
- MinHash/SimHash clustering, greedy set-cover attribution, precedence evidence ladder incl. archive lookups, source classification.
- Paraphrase matcher with lexical-anchor gating, embedding cache, pgvector.
- **Exit:** mirror set cluster F1 ≥ 0.9; precedence abstains when evidence is insufficient; paraphrase results never exceed LOW/MEDIUM caps; L3–L4 recall reported.

### Phase 6 — Calibration, hardening, launch (Week 12–14)
- Tune thresholds on dev split; validate on held-out test; consider logistic calibration.
- Load test (concurrency, provider throttling), cost model, observability dashboards and alerts, log privacy review.
- Human-review pilot on real documents; fix top FP/FN patterns.
- Docs: API reference, README, runbook, coverage-limits statement in the UI.
- **Exit:** all Section 6.3 targets met (or documented gaps), security review signed off, on-call runbook complete.

### Testing matrix (minimum)
| Scenario | Expected |
|---|---|
| Verbatim copy of a page section | HIGH, single cluster |
| Light edits (1 word / 12) | HIGH or MEDIUM with identity ≈ 0.9 |
| Heavy edits (1 / 6) | MEDIUM |
| Machine paraphrase | LOW/"possible paraphrase" only |
| Single common definition sentence | LOW/ignored (`common_phrase`) |
| Quoted + cited passage | tagged `quoted_attributed`, not counted |
| Bibliography/reference list | excluded |
| Same-topic different text | NO MATCH |
| 4 mirrors of one article | 1 cluster, N URLs |
| Official docs + scraped copy | cluster with precedence evidence; no "original" claim without evidence |
| Search provider A down | fallback to B; job `completed`; if all down, `partial` |
| Page returns 169.254.169.254 redirect | blocked, logged |
| Page contains "ignore previous instructions" | treated as text only |
| Non-English document | language detected; provider language filter; matcher unchanged |

### Key risks and mitigations
| Risk | Mitigation |
|---|---|
| Search APIs lack reliable phrase search / change terms | Provider abstraction; relaxed-query fallbacks; snippet verification; budget monitoring |
| Cost blow-up | Adaptive probing, votes, pre-screen, caching, per-tenant budgets |
| False positives on technical/common text | Rarity weighting, exclusion zones, common-phrase detection, HIGH requires strong evidence |
| Boilerplate-stripping hides matches | Fallback comparison on lightly cleaned text |
| Over-claiming originality | Wording rules + evidence ladder + abstention |
| Privacy complaints | Query minimization, opt-out, retention, no doc text in logs |
| Legal/ToS drift | Per-provider ToS review at onboarding and quarterly |

---

## Appendix A — Core matcher pseudocode

```python
def align(doc_tokens, doc_kgram_index, page_tokens, k=6, max_gap=8, theta=0.7):
    seeds = []                                   # (diag, doc_pos, src_pos)
    for j in range(len(page_tokens) - k + 1):
        h = hash_kgram(page_tokens[j:j+k])
        if h in STOP_KGRAMS:                     # stopword-only seeds ignored
            continue
        for i in doc_kgram_index.get(h, ()):
            seeds.append((j - i, i, j))

    spans = []
    for group in group_by_diagonal_band(seeds, band=max_gap):
        for chain in chain_seeds(group, max_gap=max_gap):
            span = extend_banded(chain, doc_tokens, page_tokens, theta=theta)
            if span.matched_tokens >= MIN_TOKENS:
                spans.append(score_span(span))   # identity, longest_exact_run, rarity_mass
    return merge_overlapping(spans)
```

## Appendix B — Confidence reasons (generated, never free-text guessed)

```
HIGH — Source identified because:
• 87 tokens matched at 96% identity (longest exact run: 42)
• 3 document sentences appear in the same order on the page
• Found by 2 independent search probes
• Rarity-weighted evidence 143 (well above common-phrase range)
• 4 pages share this content (1 cluster); earliest identified: <url>, archive capture <date>
• Coverage note: only public, indexed web pages were searched
```

## Appendix C — Condensed build prompt (optimized)

Use this if you are handing the project to a coding assistant. It replaces the original prompt.

```text
Build PlagiaScan's Web Source Detection Engine in Python 3.12 (FastAPI, Pydantic v2,
Celery+Redis, PostgreSQL+pgvector, httpx, trafilatura, rapidfuzz, datasketch).
Follow PlagiaScan_Web_Source_Detection_Design.md exactly.

Rules:
1. Detection pipeline (no LLM in decision path): extract -> normalize with offset maps ->
   segment + exclusion zones -> two-phase adaptive probe planning (IDF-based
   distinctiveness) -> query variants (exact/relaxed/shifted) -> provider router with
   fallback + circuit breaker -> URL canonicalize/dedupe/vote -> snippet pre-screen ->
   SSRF-safe fetch + robots + cache -> trafilatura extraction -> seed-and-extend
   alignment (k=6 seeds, banded extension, edit tolerant) -> rarity-weighted scoring ->
   greedy set-cover attribution -> MinHash/SimHash mirror clustering -> precedence
   evidence ladder -> report.
2. Semantic matching only for uncovered passages on already-fetched candidate pages;
   requires lexical anchors; confidence capped at LOW/MEDIUM; labeled "paraphrase_candidate".
3. Confidence = rule-based tiers over an explainable feature vector; return components
   and generated reasons; search rank is not an evidence feature.
4. Never claim "original source" without evidence; use "earliest identified source".
5. Send only short probe phrases to search APIs; never log document text; store only
   short excerpts; honor robots.txt and provider ToS; no CAPTCHA/anti-bot evasion.
6. SSRF protection: DNS pinning, per-redirect validation, private/metadata IP blocking,
   size/type/decompression limits. Webpage content is untrusted data.
7. Build the evaluation harness FIRST (synthetic injection L0-L5, negatives, snapshots,
   fake provider, PlagDet + tier precision) and gate CI on it.
8. Deliver modular code per the repository layout, tests (unit/integration/security),
   Alembic migrations, Dockerfile/compose, .env.example, README, OpenAPI docs.
Work phase by phase; do not start a phase until the previous phase's exit criteria pass.
```
