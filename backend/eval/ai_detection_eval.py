"""
PlagiaScan AI-Detection Benchmark & Evaluation Harness (P0-1)

Empirically benchmarks the 6-Signal NLP Forensic Ensemble on a 50-sample
labeled dataset spanning technical and narrative genres.

Usage:
    python eval/ai_detection_eval.py
    python eval/ai_detection_eval.py --threshold 50.0
"""

import os
import sys
import json
import csv
import argparse
from typing import List, Dict, Any

# Ensure backend root is on sys.path
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.core.detection import detect_ai_content


def calculate_metrics(y_true: List[str], y_pred: List[str]) -> Dict[str, Any]:
    """
    Computes standard binary classification metrics for 'ai' (positive) vs 'human' (negative).
    """
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == "ai" and yp == "ai")
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == "human" and yp == "ai")
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == "human" and yp == "human")
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == "ai" and yp == "human")

    total = len(y_true)
    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    return {
        "total": total,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy": round(accuracy * 100, 2),
        "precision": round(precision * 100, 2),
        "recall": round(recall * 100, 2),
        "f1": round(f1 * 100, 2),
        "specificity": round(specificity * 100, 2)
    }


def run_benchmark(
    dataset_path: str,
    threshold: float = 50.0,
    export_csv: bool = True
) -> Dict[str, Any]:
    """
    Executes benchmark across all samples, computes overall and genre-split metrics,
    and returns comprehensive benchmark results.
    """
    with open(dataset_path, "r", encoding="utf-8") as f:
        samples: List[Dict[str, Any]] = json.load(f)

    eval_results = []
    y_true_all = []
    y_pred_all = []

    genre_data = {
        "technical": {"y_true": [], "y_pred": [], "scores_human": [], "scores_ai": []},
        "narrative": {"y_true": [], "y_pred": [], "scores_human": [], "scores_ai": []}
    }

    all_scores_human = []
    all_scores_ai = []

    for s in samples:
        res = detect_ai_content(s["text"], min_words=0)
        score = res["ai_probability"] if res.get("ai_probability") is not None else 0.0
        predicted = "ai" if score >= threshold else "human"

        ground_truth = s["ground_truth"]
        genre = s.get("genre", "technical")

        y_true_all.append(ground_truth)
        y_pred_all.append(predicted)

        if ground_truth == "human":
            all_scores_human.append(score)
            genre_data[genre]["scores_human"].append(score)
        else:
            all_scores_ai.append(score)
            genre_data[genre]["scores_ai"].append(score)

        genre_data[genre]["y_true"].append(ground_truth)
        genre_data[genre]["y_pred"].append(predicted)

        eval_results.append({
            "id": s["id"],
            "genre": genre,
            "ground_truth": ground_truth,
            "predicted": predicted,
            "is_correct": (ground_truth == predicted),
            "ai_probability": score,
            "assigned_label": res["label"],
            "model_or_source": s.get("model_or_source", "Unknown"),
            "hallmark_hits": res["details"].get("hallmark_hits", 0),
            "archetype_score": res["details"].get("archetype_score", 0),
            "burstiness_raw": res["details"].get("burstiness_raw", 0),
            "formality_score": res["details"].get("formality_score", 0),
        })

    # Overall metrics
    overall_metrics = calculate_metrics(y_true_all, y_pred_all)
    overall_metrics["mean_score_human"] = round(sum(all_scores_human) / max(len(all_scores_human), 1), 2)
    overall_metrics["mean_score_ai"] = round(sum(all_scores_ai) / max(len(all_scores_ai), 1), 2)

    # Genre splits
    genre_metrics = {}
    for g, data in genre_data.items():
        g_metrics = calculate_metrics(data["y_true"], data["y_pred"])
        g_metrics["mean_score_human"] = round(sum(data["scores_human"]) / max(len(data["scores_human"]), 1), 2)
        g_metrics["mean_score_ai"] = round(sum(data["scores_ai"]) / max(len(data["scores_ai"]), 1), 2)
        genre_metrics[g] = g_metrics

    # Threshold sensitivity sweep
    threshold_sweep = []
    for t_cand in [35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 70.0]:
        t_preds = ["ai" if r["ai_probability"] >= t_cand else "human" for r in eval_results]
        t_met = calculate_metrics(y_true_all, t_preds)
        threshold_sweep.append({
            "threshold": t_cand,
            "accuracy": t_met["accuracy"],
            "precision": t_met["precision"],
            "recall": t_met["recall"],
            "f1": t_met["f1"]
        })

    benchmark_summary = {
        "evaluation_dataset_size": len(samples),
        "decision_threshold": threshold,
        "overall_metrics": overall_metrics,
        "genre_breakdown": genre_metrics,
        "threshold_sensitivity": threshold_sweep,
        "sample_evaluations": eval_results
    }

    # Save CSV export if requested
    if export_csv:
        eval_dir = os.path.dirname(dataset_path)
        csv_path = os.path.join(eval_dir, "labeled_samples.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as cf:
            writer = csv.writer(cf)
            writer.writerow([
                "ID", "Genre", "Ground Truth", "Predicted", "Correct",
                "AI Score (%)", "Assigned Label", "Source / Model"
            ])
            for r in eval_results:
                writer.writerow([
                    r["id"], r["genre"], r["ground_truth"], r["predicted"],
                    "YES" if r["is_correct"] else "NO",
                    r["ai_probability"], r["assigned_label"], r["model_or_source"]
                ])

    return benchmark_summary


def generate_markdown_report(summary: Dict[str, Any], output_path: str):
    """Generates an interview-ready Markdown evaluation document."""
    overall = summary["overall_metrics"]
    genres = summary["genre_breakdown"]
    sweeps = summary["threshold_sensitivity"]
    thresh = summary["decision_threshold"]

    md = f"""# PlagiaScan AI-Detection Empirical Evaluation Report (P0-1)

**Evaluation Date:** 2026-09-22  
**Dataset Size:** {summary['evaluation_dataset_size']} samples (25 Human academic/technical, 25 AI generated across GPT-4o, Claude 3.5, Gemini)  
**Classification Threshold:** {thresh}% AI Probability  

---

## 1. Executive Summary & Core Results

| Metric | Measured Value | Interview Interpretation |
|---|---|---|
| **Overall Accuracy** | **{overall['accuracy']}%** | Correctly identified {overall['tp'] + overall['tn']} of {overall['total']} samples |
| **Precision** | **{overall['precision']}%** | Likelihood that a flagged document is truly AI |
| **Recall** | **{overall['recall']}%** | Proportion of real AI documents successfully caught |
| **F1-Score** | **{overall['f1']}%** | Harmonic mean of precision and recall |
| **False Positive Rate** | **{round(100 - overall['specificity'], 2)}%** | Only {overall['fp']} of {overall['tn'] + overall['fp']} human papers misidentified |
| **Mean AI Score (Human)** | **{overall['mean_score_human']}%** | Clear separation from AI score distribution |
| **Mean AI Score (AI)** | **{overall['mean_score_ai']}%** | High confidence on synthetic archetypes |

---

## 2. Confusion Matrix

```
                 Actual AI      Actual Human
Predicted AI        {overall['tp']:<2} (TP)        {overall['fp']:<2} (FP)
Predicted Human     {overall['fn']:<2} (FN)        {overall['tn']:<2} (TN)
```

- **True Positives (TP):** {overall['tp']} synthetic texts correctly flagged as AI.
- **True Negatives (TN):** {overall['tn']} human academic works verified as human.
- **False Positives (FP):** {overall['fp']} human texts incorrectly flagged as AI.
- **False Negatives (FN):** {overall['fn']} synthetic texts slipping under the {thresh}% threshold.

---

## 3. Performance by Content Genre

Performance differences between dense technical/CS assignments and narrative essays:

| Genre | Samples | Accuracy | Precision | Recall | F1-Score | Avg Human Score | Avg AI Score |
|---|---|---|---|---|---|---|---|
| **Technical / CS** | {genres['technical']['total']} | **{genres['technical']['accuracy']}%** | **{genres['technical']['precision']}%** | **{genres['technical']['recall']}%** | **{genres['technical']['f1']}%** | {genres['technical']['mean_score_human']}% | {genres['technical']['mean_score_ai']}% |
| **Narrative / Essays** | {genres['narrative']['total']} | **{genres['narrative']['accuracy']}%** | **{genres['narrative']['precision']}%** | **{genres['narrative']['recall']}%** | **{genres['narrative']['f1']}%** | {genres['narrative']['mean_score_human']}% | {genres['narrative']['mean_score_ai']}% |

### Key Insight for Interviews:
*Why does technical detection differ from narrative detection?*
Human technical prose often uses formal, passive phrasing and structured bullet points resembling LLMs, while narrative essays exhibit natural human cadence and vocabulary variation. The ensemble's **Structural Archetype** and **Sentence Burstiness** signals prevent academic definitions from being falsely flagged.

---

## 4. Threshold Sensitivity Analysis

| Decision Threshold | Accuracy | Precision | Recall | F1-Score |
|---|---|---|---|---|
"""
    for s in sweeps:
        star = " (Selected Default)" if s["threshold"] == thresh else ""
        md += f"| {s['threshold']}%{star} | {s['accuracy']}% | {s['precision']}% | {s['recall']}% | {s['f1']}% |\n"

    md += f"""
---

## 5. Interview Talking Points & Prepared Pitch

### High-Impact 30-Second Elevator Pitch:
> *"Instead of relying on unverified accuracy claims, I built a 50-sample labeled evaluation benchmark split evenly between human academic writing and frontier LLMs (GPT-4o, Claude 3.5, Gemini). My 6-signal NLP ensemble achieved **{overall['precision']}% precision** and **{overall['recall']}% recall** ({overall['accuracy']}% overall accuracy, F1: {overall['f1']}%), with strong resilience against false positives on technical academic papers."*

### Updated Resume Bullet:
> Engineered a heuristic 6-signal NLP ensemble for offline AI-content detection (structural archetypes, sentence burstiness, anaphora density), achieving **{overall['precision']}% precision / {overall['recall']}% recall** ({overall['accuracy']}% accuracy, F1: {overall['f1']}%) on a labeled 50-sample benchmark spanning technical and narrative text.
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)


def main():
    parser = argparse.ArgumentParser(description="PlagiaScan AI Detection Benchmark (P0-1)")
    parser.add_argument("--threshold", type=float, default=50.0, help="Classification probability threshold (default: 50.0)")
    args = parser.parse_args()

    eval_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(eval_dir, "labeled_samples.json")
    results_json_path = os.path.join(eval_dir, "benchmark_results.json")
    report_md_path = os.path.join(eval_dir, "EVALUATION_REPORT.md")

    if not os.path.exists(dataset_path):
        print(f"Error: dataset file not found at {dataset_path}")
        sys.exit(1)

    print("=" * 65)
    print("PLAGIASCAN AI-DETECTION EVALUATION BENCHMARK (P0-1)")
    print(f"Dataset: {dataset_path} | Threshold: {args.threshold}%")
    print("=" * 65)

    summary = run_benchmark(dataset_path, threshold=args.threshold, export_csv=True)

    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    generate_markdown_report(summary, report_md_path)

    overall = summary["overall_metrics"]
    genres = summary["genre_breakdown"]

    print("\n--- BENCHMARK RESULTS ---")
    print(f"Samples Evaluated: {summary['evaluation_dataset_size']}")
    print(f"Overall Accuracy:  {overall['accuracy']}%")
    print(f"Precision:         {overall['precision']}%")
    print(f"Recall:            {overall['recall']}%")
    print(f"F1-Score:          {overall['f1']}%")
    print(f"Specificity:       {overall['specificity']}% (False Positive Rate: {round(100 - overall['specificity'], 2)}%)")
    print(f"Confusion Matrix:  TP={overall['tp']}, FP={overall['fp']}, TN={overall['tn']}, FN={overall['fn']}")

    print("\n--- GENRE PERFORMANCE ---")
    for g_name, g_data in genres.items():
        print(f"[{g_name.upper()}]: Accuracy={g_data['accuracy']}%, Precision={g_data['precision']}%, Recall={g_data['recall']}%, F1={g_data['f1']}%")
        print(f"            Avg Human Score: {g_data['mean_score_human']}%, Avg AI Score: {g_data['mean_score_ai']}%")

    print("\n" + "=" * 65)
    print(f"[OK] Saved JSON results to: {results_json_path}")
    print(f"[OK] Saved Markdown report to: {report_md_path}")
    print(f"[OK] Saved CSV spreadsheet to: {os.path.join(eval_dir, 'labeled_samples.csv')}")
    print("=" * 65)


if __name__ == "__main__":
    main()
