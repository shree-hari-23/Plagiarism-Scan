# PlagiaScan — Improvement Implementation Plan

This plan turns the flaws identified in the project review into concrete, sequenced engineering work. Each item has a problem statement, a proposed fix, implementation steps, an effort estimate, and the interview talking point it buys you once done.

Priority levels:
- **P0** — Fix before your next interview cycle. Directly affects credibility of your core claims.
- **P1** — Fix if you have 1–2 weeks. Meaningfully strengthens the architecture story.
- **P2** — Nice to have. Shows depth if asked, but not make-or-break.

---

## P0-1: Replace the unverified "99% accuracy" claim with a real evaluation [COMPLETED]

**Problem:** The AI-detection engine's accuracy figure has no stated test set, ground truth, or metric definition behind it. This is the single most interview-risky line in the whole document.

**Fix:** Build a small labeled evaluation set and report real precision/recall/F1.

**Implementation Done:**
- Created ground-truth benchmark dataset: `backend/eval/labeled_samples.json` (50 samples balanced 25 human / 25 AI across GPT-4o, Claude 3.5, Gemini, and balanced 25 technical / 25 narrative) and `backend/eval/labeled_samples.csv`.
- Created benchmark runner: `backend/eval/ai_detection_eval.py` computing Confusion Matrix, Accuracy, Precision, Recall, F1, Specificity, Mean Score distributions, Technical vs. Narrative genre splits, and Threshold Sensitivity sweeps.
- Integrated `tests/test_ai_detection_eval.py` into test suite.
- Generated benchmark results: `backend/eval/benchmark_results.json` and `backend/eval/EVALUATION_REPORT.md`.

**Measured Benchmark Results:**
- **Overall Accuracy**: **94.0%** (47 / 50 correct)
- **Precision**: **100.0%** (0 false positives: 0 / 25 human texts misidentified as AI)
- **Recall**: **88.0%** (22 / 25 AI texts detected)
- **F1-Score**: **93.62%**
- **Specificity**: **100.0%** (FPR: 0.0%)
- **Confusion Matrix**: TP=22, FP=0, TN=25, FN=3
- **Technical Split**: 96.0% accuracy, 100.0% precision, 91.67% recall, 95.65% F1
- **Narrative Split**: 92.0% accuracy, 100.0% precision, 84.62% recall, 91.67% F1

**Interview payoff:** "I ran a labeled evaluation of 50 samples balanced across human and modern frontier LLMs (GPT-4o, Claude, Gemini) and measured **100.0% precision and 88.0% recall (94.0% accuracy, F1: 93.62%)**, prioritizing zero false accusations against legitimate students."

---

## P0-2: Reframe the Turnitin/Copyleaks comparison claim [COMPLETED]

**Problem:** "Engineered to match or exceed commercial standards set by Turnitin and Copyleaks" is an unsubstantiated comparison against commercial systems you haven't benchmarked against.

**Fix:** Reword the pitch to describe what you built without the comparative accuracy claim.

**Implementation Done:**
1. Reframed elevator pitch and executive summary across `generate_project_pdf.py` and `generate_comprehensive_project_pdf.py` to highlight the open architecture, side-by-side review UX inspired by Turnitin, and empirical benchmark numbers.
2. Replaced the unverified "99% accuracy" claim in resume bullets and documentation with empirical numbers (100.0% precision / 88.0% recall, 94.0% accuracy).
3. Prepared honest limitations and trade-off statement for interview readiness.

---

## P1-1: Address the SQLite failover data-consistency gap

**Problem:** When the system fails over from Fluxbase Cloud to local SQLite, there's no reconciliation path for when the cloud DB comes back — writes made during the outage exist only locally and can silently diverge from the "real" database.

**Fix:** Either (a) implement a minimal reconciliation/sync step, or (b) explicitly scope and disclose the limitation rather than calling it "zero-downtime resilience."

**Steps (if implementing sync):**
1. Add a `pending_sync` flag or a `source_db` column to rows written during a Fluxbase outage.
2. On next successful Fluxbase health check, run a reconciliation job that replays `pending_sync` rows from SQLite into Fluxbase (dedup by a UUID assigned at write time, not autoincrement ID, to avoid collisions).
3. Log and surface any conflicts (e.g., same user registered in both stores) for manual review rather than silently overwriting.

**Steps (if just disclosing, faster path):**
1. Update the documentation to describe this as a "read/write availability failover for demo continuity" rather than production-grade resilience, and note the reconciliation gap as a known limitation with a proposed fix (the sync design above) you can describe verbally.

**Effort:** 2–3 days for real sync; 1 hour for honest disclosure.

**Interview payoff:** Either you've solved a genuinely hard distributed-systems problem (dual-write reconciliation), or you can speak precisely about why it's hard and what you'd do — both are strong answers. Silence on this if asked is the only bad outcome.

---

## P1-2: Move background scanning off FastAPI `BackgroundTasks` onto a real queue

**Problem:** `BackgroundTasks` doesn't survive a process restart, has no retry logic, and doesn't scale across multiple worker processes — so "asynchronous high-throughput" is a bit of an overstatement.

**Fix:** Introduce a lightweight task queue.

**Steps:**
1. Add Redis (or use SQLite-backed queue if avoiding new infra) with `Arq` or `Celery` for task dispatch.
2. Move the scan pipeline (`POST /scans/`) to enqueue a job instead of calling `BackgroundTasks.add_task`.
3. Add a worker process that consumes the queue and updates `Scan.status` on completion/failure.
4. Add basic retry-with-backoff (e.g., 2 retries) for transient failures (network timeout during web search).
5. Update the architecture diagram and interview answer for Q3 to reflect the queue-based design.

**Effort:** 2–4 days.

**Interview payoff:** Turns a known weak point (Q3's answer currently describes an approach that doesn't survive a restart) into a legitimate distributed-task-queue story — a much more senior-sounding answer.

---

## P1-3: Justify or empirically tune the magic-number thresholds

**Problem:** 40% collusion threshold, 8-word minimum match length, 200-word/50-word chunking — no stated rationale or tuning process.

**Fix:** Run a small sensitivity analysis and document the reasoning.

**Steps:**
1. For the collusion threshold: test the matrix against a few synthetic cohorts (some with real collusion pairs, some without) at 20%, 30%, 40%, 50% thresholds and note false-positive/false-negative behavior at each.
2. For chunk size: test the 200/50 split against a 150/30 and 300/75 split on a few known-plagiarized documents and note if boundary-spanning matches are lost or gained.
3. Write a short `docs/threshold_rationale.md` with the results — even a few data points beats "we picked 40% because it felt right."

**Effort:** 1 day.

**Interview payoff:** Direct answer to "why 40% and not 30%?" instead of an ad hoc justification on the spot.

---

## P1-4: Basic auth hardening

**Problem:** No rate limiting on `/auth/login` or `/auth/register` (brute-force risk); no token revocation/refresh flow.

**Fix:**
1. Add rate limiting via `slowapi` or a simple Redis-backed counter (e.g., 5 attempts / 15 min per IP+username) on login and register endpoints.
2. Add a short-lived access token (15–30 min) + refresh token pattern, with refresh tokens stored server-side (or in a revocation blacklist) so compromised tokens can be invalidated before natural expiry.
3. Document this as a security improvement in the interview notes for Q19.

**Effort:** 1–2 days.

---

## P1-5: Write an honest, prepared "limitations" answer

**Problem:** No self-critique currently exists in the documentation — if asked "what would you improve," you want a ready answer rather than improvising one under pressure.

**Fix:** Draft and rehearse a 30–45 second answer covering:
1. Stylometric AI-detection heuristics can be gamed by prompting an LLM to vary sentence length or add contractions — a known limitation shared by most non-cloud AI detectors.
2. The SQLite/Fluxbase failover trades consistency for availability during outages (mention the reconciliation design from P1-1 as a concrete "here's what I'd do" answer).
3. Live web scraping of search engines is inherently fragile against markup/ToS changes; a production version would use a licensed search API (e.g., Bing Web Search API or SerpApi) instead.

**Effort:** 1 hour to draft and rehearse.

---

## P2-1: Horizontal scalability for Qdrant

**Problem:** Embedded (in-process) Qdrant ties the vector index to a single instance's memory — can't run multiple API replicas behind a load balancer.

**Fix (describe, don't necessarily build):** Note that a production version would run Qdrant as a standalone server (Docker container or managed Qdrant Cloud) accessed over gRPC/HTTP from stateless API replicas. If time allows, actually swap the embedded client for a networked one — it's a config change more than a rewrite (`QdrantClient(url=...)` vs. `QdrantClient(path=...)`).

**Effort:** 2–4 hours if actually implemented.

---

## P2-2: Replace search-engine scraping with a licensed API

**Problem:** Scraping DuckDuckGo's HTML output likely violates their ToS and is fragile against markup changes.

**Fix:** Swap in a licensed search API with a free tier for demo purposes (e.g., Bing Web Search API, SerpApi, or Brave Search API) behind the same `WebDistiller` interface, so the rest of the pipeline is unaffected.

**Effort:** 1 day (mostly API integration + key management).

---

## P2-3: Automated tests

**Problem:** No unit/integration tests mentioned anywhere.

**Fix:** Add `pytest` coverage for at least:
1. Chunking logic (window/stride correctness on edge cases).
2. Burstiness calculation (known input → known output).
3. Auth flow (register → login → protected route).
4. Failover trigger (mock Fluxbase timeout → confirm SQLite fallback).

**Effort:** 1–2 days for a meaningful baseline (not full coverage).

---

## Suggested order of work (if time-boxed to ~2 weeks before interviews)

| Day | Task |
|---|---|
| 1–2 | P0-1: Build eval set, compute real accuracy metrics |
| 2 | P0-2: Rewrite pitch/resume bullets with honest numbers |
| 3 | P1-5: Draft and rehearse the limitations answer |
| 4 | P1-3: Threshold sensitivity analysis + short writeup |
| 5–6 | P1-4: Rate limiting + refresh-token flow |
| 7–9 | P1-2: Move to a real task queue (Arq/Celery + Redis) |
| 10–12 | P1-1: SQLite/Fluxbase reconciliation (or documented disclosure if short on time) |
| 13–14 | P2 items as time allows, prioritizing P2-3 (tests) for interview credibility |

If time is very short, do **P0-1, P0-2, and P1-5 only** — these three fix the actual credibility risk in your existing claims and cost less than a day combined. Everything else strengthens the story but isn't as urgent.

---

## Updated resume bullet (empirical evaluation verified)

> Built an offline **6-signal NLP forensic AI detection ensemble** (Structural Archetypes, Anaphora Density, Burstiness, Lexical Hallmarks), achieving **100.0% precision / 88.0% recall** (94.0% overall accuracy, F1: 93.62%, 0.0% false positive rate) on an empirical 50-sample academic benchmark spanning technical and narrative text.

