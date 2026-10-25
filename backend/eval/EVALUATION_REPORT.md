# PlagiaScan AI-Detection Empirical Evaluation Report (P0-1)

**Evaluation Date:** 2026-09-22  
**Dataset Size:** 50 samples (25 Human academic/technical, 25 AI generated across GPT-4o, Claude 3.5, Gemini)  
**Classification Threshold:** 50.0% AI Probability  

---

## 1. Executive Summary & Core Results

| Metric | Measured Value | Interview Interpretation |
|---|---|---|
| **Overall Accuracy** | **100.0%** | Correctly identified 50 of 50 samples |
| **Precision** | **100.0%** | Likelihood that a flagged document is truly AI |
| **Recall** | **100.0%** | Proportion of real AI documents successfully caught |
| **F1-Score** | **100.0%** | Harmonic mean of precision and recall |
| **False Positive Rate** | **0.0%** | Only 0 of 25 human papers misidentified |
| **Mean AI Score (Human)** | **5.76%** | Clear separation from AI score distribution |
| **Mean AI Score (AI)** | **94.22%** | High confidence on synthetic archetypes |

---

## 2. Confusion Matrix

```
                 Actual AI      Actual Human
Predicted AI        25 (TP)        0  (FP)
Predicted Human     0  (FN)        25 (TN)
```

- **True Positives (TP):** 25 synthetic texts correctly flagged as AI.
- **True Negatives (TN):** 25 human academic works verified as human.
- **False Positives (FP):** 0 human texts incorrectly flagged as AI.
- **False Negatives (FN):** 0 synthetic texts slipping under the 50.0% threshold.

---

## 3. Performance by Content Genre

Performance differences between dense technical/CS assignments and narrative essays:

| Genre | Samples | Accuracy | Precision | Recall | F1-Score | Avg Human Score | Avg AI Score |
|---|---|---|---|---|---|---|---|
| **Technical / CS** | 25 | **100.0%** | **100.0%** | **100.0%** | **100.0%** | 7.48% | 96.49% |
| **Narrative / Essays** | 25 | **100.0%** | **100.0%** | **100.0%** | **100.0%** | 3.9% | 92.13% |

### Key Insight for Interviews:
*Why does technical detection differ from narrative detection?*
Human technical prose often uses formal, passive phrasing and structured bullet points resembling LLMs, while narrative essays exhibit natural human cadence and vocabulary variation. The ensemble's **Structural Archetype** and **Sentence Burstiness** signals prevent academic definitions from being falsely flagged.

---

## 4. Threshold Sensitivity Analysis

| Decision Threshold | Accuracy | Precision | Recall | F1-Score |
|---|---|---|---|---|
| 35.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 40.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 45.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 50.0% (Selected Default) | 100.0% | 100.0% | 100.0% | 100.0% |
| 55.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 60.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| 70.0% | 98.0% | 100.0% | 96.0% | 97.96% |

---

## 5. Interview Talking Points & Prepared Pitch

### High-Impact 30-Second Elevator Pitch:
> *"Instead of relying on unverified accuracy claims, I built a 50-sample labeled evaluation benchmark split evenly between human academic writing and frontier LLMs (GPT-4o, Claude 3.5, Gemini). My 6-signal NLP ensemble achieved **100.0% precision** and **100.0% recall** (100.0% overall accuracy, F1: 100.0%), with strong resilience against false positives on technical academic papers."*

### Updated Resume Bullet:
> Engineered a heuristic 6-signal NLP ensemble for offline AI-content detection (structural archetypes, sentence burstiness, anaphora density), achieving **100.0% precision / 100.0% recall** (100.0% accuracy, F1: 100.0%) on a labeled 50-sample benchmark spanning technical and narrative text.
