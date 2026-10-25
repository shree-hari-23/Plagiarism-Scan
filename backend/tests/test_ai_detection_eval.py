"""
Unit tests for the AI-Detection Evaluation Harness (P0-1).
Verifies dataset structure, label integrity, and benchmark execution.
"""

import os
import json
import pytest
from eval.ai_detection_eval import run_benchmark, calculate_metrics
from app.core.detection import detect_ai_content


def test_labeled_dataset_structure():
    """Verify dataset contains exactly 50 balanced, valid samples."""
    dataset_path = os.path.join(os.path.dirname(__file__), "..", "eval", "labeled_samples.json")
    assert os.path.exists(dataset_path), "labeled_samples.json must exist in backend/eval/"

    with open(dataset_path, "r", encoding="utf-8") as f:
        samples = json.load(f)

    assert len(samples) == 50, "Dataset must contain exactly 50 samples"

    human_count = sum(1 for s in samples if s["ground_truth"] == "human")
    ai_count = sum(1 for s in samples if s["ground_truth"] == "ai")
    assert human_count == 25, "Must have exactly 25 human samples"
    assert ai_count == 25, "Must have exactly 25 AI samples"

    tech_count = sum(1 for s in samples if s["genre"] == "technical")
    narrative_count = sum(1 for s in samples if s["genre"] == "narrative")
    assert tech_count == 25, "Must have 25 technical samples"
    assert narrative_count == 25, "Must have 25 narrative samples"

    for s in samples:
        assert s["id"]
        assert len(s["text"].strip()) >= 50, f"Sample {s['id']} has insufficient text length"
        assert s["ground_truth"] in ("human", "ai")
        assert s["genre"] in ("technical", "narrative")


def test_calculate_metrics_math():
    """Verify calculation of precision, recall, F1, and accuracy."""
    y_true = ["ai", "ai", "human", "human"]
    y_pred = ["ai", "human", "human", "ai"]

    m = calculate_metrics(y_true, y_pred)
    assert m["total"] == 4
    assert m["tp"] == 1
    assert m["fn"] == 1
    assert m["tn"] == 1
    assert m["fp"] == 1
    assert m["accuracy"] == 50.0
    assert m["precision"] == 50.0
    assert m["recall"] == 50.0
    assert m["f1"] == 50.0


def test_run_benchmark_execution():
    """Verify full benchmark runs cleanly and returns valid metrics."""
    dataset_path = os.path.join(os.path.dirname(__file__), "..", "eval", "labeled_samples.json")
    summary = run_benchmark(dataset_path, threshold=50.0, export_csv=False)

    overall = summary["overall_metrics"]
    assert overall["total"] == 50
    # Expected performance thresholds on our benchmark
    assert overall["accuracy"] >= 90.0
    assert overall["precision"] >= 95.0
    assert overall["recall"] >= 80.0
    assert overall["f1"] >= 85.0
    assert "technical" in summary["genre_breakdown"]
    assert "narrative" in summary["genre_breakdown"]


def test_insufficient_text_gate():
    """Text under 150 words must return status 'insufficient_text' and ai_probability None."""
    short_text = "This is a brief paragraph that only contains a few dozen words. It is far too short for stylometric AI analysis."
    res = detect_ai_content(short_text)
    assert res["status"] == "insufficient_text"
    assert res["ai_probability"] is None
    assert res["score"] is None
    assert res["label"] == "Insufficient Text"
    assert res["confidence"] == "low"
    assert "fewer than 150 words" in res["description"]


def test_label_and_description_consistency():
    """Verify describe_ai_score produces consistent label, explanation, and confidence."""
    from app.core.detection import describe_ai_score
    
    # Insufficient text
    short_desc = describe_ai_score(None, 80)
    assert short_desc["status"] == "insufficient_text"
    assert short_desc["label"] == "Insufficient Text"

    # Likely Human
    human_desc = describe_ai_score(15.0, 350)
    assert human_desc["label"] == "Likely Human"
    assert "Authentic human prose" in human_desc["text"]
    assert human_desc["confidence"] == "high"

    # Inconclusive / Mixed
    mixed_desc = describe_ai_score(50.0, 250)
    assert mixed_desc["label"] == "Inconclusive / Mixed"
    assert "Mixed signals" in mixed_desc["text"]

    # Likely AI
    ai_desc = describe_ai_score(92.0, 400)
    assert ai_desc["label"] == "Likely AI"
    assert "Strong AI-style patterns detected" in ai_desc["text"]
    assert ai_desc["confidence"] == "high"


def test_scan_11_forensic_retest():
    """Re-test Scan #11's ground truth document text and verify all sub-signals populate."""
    import sqlite3
    db_path = os.path.join(os.path.dirname(__file__), "..", "plagiascan.db")
    if not os.path.exists(db_path):
        pytest.skip("plagiascan.db not found for Scan #11 test")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT extracted_text FROM documents WHERE id = (SELECT document_id FROM scans WHERE id = 11)")
    row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        pytest.skip("Scan #11 text not found in database")

    text = row[0]
    res = detect_ai_content(text)

    assert res["status"] == "ok"
    assert res["ai_probability"] is not None
    assert res["ai_probability"] >= 90.0, f"Expected Scan #11 to score >= 90%, got {res['ai_probability']}%"
    assert res["label"] == "Likely AI"
    assert "Strong AI-style patterns" in res["description"]

    # Verify granular sub-signals are all populated (no missing or zero-defaulted keys)
    details = res["details"]
    assert details["avg_sentence_length"] > 0, "avg_sentence_length must be populated"
    assert details["archetype_score"] > 0, "archetype_score must be populated"
    assert details["formality_score"] > 0, "formality_score must be populated"
    assert details["lexical_diversity"] > 0, "lexical_diversity must be populated"

