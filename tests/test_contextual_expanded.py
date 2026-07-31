"""Unit & Integration Tests for Milestone 1: Expanded Confusion Sets & PMI Collocations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from teea.grammar.contextual_engine import ContextualGrammarEngine

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_expanded_confusion_sets_file_exists() -> None:
    """Verify that confusion_sets_expanded.json exists and contains >= 500 rules."""
    p = PROJECT_ROOT / "Data" / "Processed" / "confusion_sets_expanded.json"
    assert p.exists(), "confusion_sets_expanded.json file missing"

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    c_dict = data.get("confusion_dict", {})
    assert len(c_dict) >= 500, f"Expected >= 500 confusion rules, found {len(c_dict)}"


def test_expanded_collocations_file_exists() -> None:
    """Verify that collocations_expanded.json exists and contains >= 1,000 collocations."""
    p = PROJECT_ROOT / "Data" / "Processed" / "collocations_expanded.json"
    assert p.exists(), "collocations_expanded.json file missing"

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    cols = data.get("collocations", {})
    assert len(cols) >= 1000, f"Expected >= 1,000 collocations, found {len(cols)}"


def test_contextual_engine_loads_expanded_datasets() -> None:
    """Verify ContextualGrammarEngine loads expanded confusion sets and PMI collocations."""
    engine = ContextualGrammarEngine()
    assert len(engine._confusion_map) >= 500
    assert len(engine._collocations) >= 1000


def test_pmi_collocation_scoring() -> None:
    """Verify get_collocation_score returns valid non-zero PMI/t-scores for top collocations."""
    engine = ContextualGrammarEngine()
    sample_key = next(iter(engine._collocations.keys()))
    w1, w2 = sample_key.split(":", 1)

    score = engine.get_collocation_score(w1, w2)
    assert score != 0.0, f"Expected non-zero collocation score for '{w1}:{w2}'"
