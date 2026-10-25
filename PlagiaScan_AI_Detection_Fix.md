# PlagiaScan: AI-Detection Accuracy Fix Plan

**Goal:** make the AI-content score trustworthy, measurable, and consistent with its label.
**Observed problem (Scan #11):** text known to be fully AI-generated scored **60% "Likely AI"**, while every sub-signal displayed **0** (LLM Hallmarks 0 hits, Burstiness 0%, Formality 0%, Avg Sentence 0 w). The label also read "Likely AI" while the explanation read "Mixed Style".

> Rules for whoever implements this (human or coding agent):
> 1. **Inspect the existing code first.** Do not rewrite auth, Qdrant, scan progress, PDF report, or email features.
> 2. Work phase by phase. Run the benchmark after each phase and record the numbers.
> 3. Never claim accuracy that was not measured on a held-out set.

---

## Phase 0: Diagnose before changing anything

The zeros suggest the signals received **empty or badly split text**, so 60% is probably a default/fallback/bias value, not a measurement.

Add temporary logging in the AI-detection service for this scan:

```
AI_INPUT:    char_count, word_count, first 200 chars
AI_SPLIT:    sentence_count, avg_words_per_sentence
AI_SIGNALS:  each raw signal value BEFORE weighting
AI_COMBINE:  weights, bias/intercept, raw sum, final score
AI_LABEL:    thresholds used, label chosen
```

Check each of these:

- [ ] Does the detector receive the **same extracted text** the plagiarism checker uses?
- [ ] Does the sentence splitter return > 0 sentences for normal prose? (Avg sentence = 0 says no.)
- [ ] Is there a hard-coded default (e.g. `score = 0.6`) used when signals are missing or text is empty?
- [ ] Do signal names in the backend response match the field names the React card reads? (A key mismatch shows `0` in the UI.)
- [ ] Is the score a weighted sum with a large bias term that dominates when signals are 0?

**Exit criterion:** you can explain exactly which line produced 60%.

---

## Phase 1: Fix input handling and failure behavior

1. **Minimum length gate.** Below ~150 words, return `status: "insufficient_text"` with no score. Short text is unreliable for every detector.
2. **No silent defaults.** If any signal cannot be computed, return `null` for it and lower confidence. Never substitute `0` or a fixed score.
3. **Robust sentence splitting.** Use a regex fallback that does not depend on a model download:

```python
import re

_SENT_SPLIT = re.compile(r'(?<=[.!?])["\')\]]*\s+(?=[A-Z0-9"\'(\[])')

def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    sents = [s.strip() for s in _SENT_SPLIT.split(text) if len(s.split()) >= 3]
    return sents
```

4. **Normalize text once**, before all signals: Unicode NFKC, collapse whitespace, strip page numbers and repeated headers/footers (common in PDFs).
5. **Return a structured result**, not a bare number:

```json
{
  "status": "ok",
  "score": 0.83,
  "label": "likely_ai",
  "confidence": "medium",
  "word_count": 412,
  "signals": { "perplexity": 31.2, "ppl_std": 0.9, "burstiness": 0.21, "lexical_diversity": 0.46, "hallmark_hits": 7, "formality": 0.71 }
}
```

---

## Phase 2: Add stronger signals

Heuristics alone (hallmark phrases, formality) are weak against modern LLMs. Keep them, but add **perplexity-based features**, which are among the strongest classic signals: AI text tends to have lower and more uniform perplexity than human text.

### 2.1 Perplexity with a small causal LM

Use `distilgpt2` (about 330 MB, CPU-friendly). Load it **once as a singleton**. Do not reload per request.

```python
import math, torch
from transformers import AutoTokenizer, AutoModelForCausalLM

_tok = _model = None

def _load():
    global _tok, _model
    if _model is None:
        _tok = AutoTokenizer.from_pretrained("distilgpt2")
        _model = AutoModelForCausalLM.from_pretrained("distilgpt2").eval()
    return _tok, _model

@torch.no_grad()
def perplexity_features(text: str, max_tokens: int = 1024):
    tok, model = _load()
    ids = tok(text, return_tensors="pt", truncation=True, max_length=max_tokens).input_ids
    if ids.shape[1] < 30:
        return None
    logits = model(ids).logits[0, :-1]
    losses = torch.nn.functional.cross_entropy(logits, ids[0, 1:], reduction="none")
    return {
        "ppl": math.exp(losses.mean().item()),      # lower tends toward AI
        "loss_std": losses.std().item(),            # lower (more uniform) tends toward AI
    }
```

For documents longer than 1024 tokens, score several windows (e.g. 3 spread across the text) and average.

> **Windows note:** the earlier RoBERTa attempt was abandoned because of library conflicts. Install CPU-only PyTorch in a clean venv, pin versions in `requirements.txt`, and test model loading **before** wiring it into the API. If it still conflicts, skip perplexity and use Phase 2.2 only; do not block the rest of the plan on it.

### 2.2 Cheap statistical signals (no model needed)

| Signal | How to compute | Typical direction for AI text |
|---|---|---|
| Sentence-length burstiness | std / mean of words per sentence | lower |
| Lexical diversity | unique words / total (use a fixed-size window, e.g. first 300 words, so length doesn't bias it) | lower |
| Repeated n-grams | share of trigrams that occur more than once | higher |
| Transition/stock-phrase density | hits of a maintained list per 100 words | higher |
| Paragraph-length uniformity | std / mean of paragraph word counts | lower |

These directions are **tendencies, not rules**. Let the model in Phase 3 learn the weights from data instead of guessing them.

---

## Phase 3: Replace hand-set weights with a trained combiner

Hand-tuned weights plus a bias term are the likely cause of a fixed 60%. Train a small logistic regression on your labelled benchmark.

```python
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict, StratifiedKFold

FEATURES = ["ppl", "loss_std", "burstiness", "lexical_diversity",
            "repeat_trigram_ratio", "hallmark_density", "formality"]

clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, C=1.0))
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
probs = cross_val_predict(clf, X[FEATURES], y, cv=cv, method="predict_proba")[:, 1]
clf.fit(X[FEATURES], y)          # final model; save with joblib
```

### Grow the benchmark (50 samples is too few to trust)

- Target **200+ samples**, balanced.
- **Human text:** your own writing, student essays, Wikipedia, technical docs, formal and informal registers. Include non-native English writing, because that is where false positives are worst.
- **AI text:** several different models and prompts, plus **lightly edited AI text** and **"write naturally" prompts**. Detectors fail hardest on these.
- Vary length: 150-300, 300-800, 800+ words.
- Keep a **held-out test set** that is never used for tuning.

---

## Phase 4: Calibrate and set thresholds

1. Logistic regression outputs are roughly calibrated already. Draw a **reliability curve** on held-out data. Add Platt/isotonic calibration only if the curve is clearly off *and* you have enough data.
2. Use your existing **threshold sweep**, but choose the threshold by the cost that matters: **false positives on human text are worse than misses** (accusing a student wrongly). Pick the threshold that keeps the human false-positive rate low (e.g. aim for ≤ 5%), then report the recall you get.
3. Use **three bands**, not a single hard cut:

| Score | Label | Explanation text |
|---|---|---|
| < 0.35 | `likely_human` | Mostly human writing patterns |
| 0.35 to 0.65 | `uncertain` | Mixed or inconclusive signals |
| > 0.65 | `likely_ai` | Strong AI-style patterns |

(Set the real cut-offs from your sweep. These numbers are placeholders.)

4. Show **confidence** (low/medium/high) based on word count and how far the score is from the band edges.

---

## Phase 5: Fix label / explanation consistency

One function must produce **both** the label and the sentence, so they can never disagree:

```python
def describe(score: float, words: int) -> dict:
    if words < 150:
        return {"label": "insufficient_text", "text": "Not enough text for a reliable estimate."}
    if score >= HI:
        return {"label": "likely_ai", "text": "Strong AI-style patterns detected."}
    if score >= LO:
        return {"label": "uncertain", "text": "Mixed signals; result is inconclusive."}
    return {"label": "likely_human", "text": "Mostly human writing patterns."}
```

The React card must render `label` and `text` from this single response, with no separate hard-coded strings.

---

## Phase 6: UI changes

- [ ] Show **real values** for each signal, and "n/a" (not `0`) when a signal could not be computed.
- [ ] Show the `insufficient_text` state instead of a percentage for short documents.
- [ ] Add a visible note: *"AI detection is probabilistic and can be wrong. Do not use it as the only evidence."*
- [ ] Rename the headline from "AI Content Probability" to something like "AI-style likelihood" if you want to avoid implying certainty.
- [ ] Optionally highlight the **most AI-like sentences**, which is more useful than one number.

---

## Phase 7: Evaluation (report these numbers)

On the **held-out** set, record:

- Accuracy, precision, recall, F1
- **False-positive rate on human text** (most important)
- ROC-AUC
- Confusion matrix at the chosen threshold
- Results **by length bucket** and **by AI source** (so weak spots are visible)
- Before/after comparison against the current heuristic ensemble

Save the results in `docs/ai_detection_eval.md` and regenerate them whenever the model or features change.

### Acceptance criteria

- [ ] No signal ever shows `0` because of missing input; missing = `null` / "n/a".
- [ ] Label and explanation always come from the same function.
- [ ] Text under 150 words returns `insufficient_text`.
- [ ] Re-running the benchmark is a **single command** and is reproducible (fixed seeds, pinned versions).
- [ ] New model beats the old heuristic ensemble on held-out ROC-AUC and does not raise human false positives.
- [ ] Scan #11's text is re-tested and the result is explained in the log.

---

## Honest limitations (say these in docs and interviews)

- No detector is reliable on short, edited, or paraphrased AI text.
- Non-native English and very formal writing can look "AI-like" and cause false positives.
- Detection of newer models can degrade over time; re-benchmark periodically.
- The score is evidence for a human reviewer, not a verdict.

## Suggested implementation order

1. Phase 0 diagnosis (find the 60% source)
2. Phase 1 input/failure fixes + Phase 5 label fix (small, high impact)
3. Phase 2.2 statistical signals + expanded benchmark
4. Phase 3 trained combiner + Phase 4 thresholds
5. Phase 2.1 perplexity (if Windows install works) and re-evaluate
6. Phase 6 UI + Phase 7 report
