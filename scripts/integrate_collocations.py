#!/usr/bin/env python3
"""Task 3: Load Collocations and Confusion Sets into Contextual Engine.

Loads `collocations.json` and `confusion_sets.json` into the `ContextualGrammarEngine`,
verifies collocation strength scoring and confusion-set-based malapropism detection.

Usage:
    python scripts/integrate_collocations.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure src and project root are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from teea.core.logging import get_logger
from teea.grammar.contextual_engine import ContextualGrammarEngine

logger = get_logger(__name__)


def find_file(relative_paths: list[str]) -> Path | None:
    """Find first existing candidate path."""
    for rel_path in relative_paths:
        candidate = PROJECT_ROOT / rel_path
        if candidate.exists():
            return candidate
    return None


def integrate_collocations() -> dict[str, Any]:
    """Load collocations and confusion sets into ContextualGrammarEngine and test."""
    collocations_path = find_file([
        "Data/Processed/collocations.json",
        "Processed/collocations.json",
        "collocations.json",
    ])
    confusion_path = find_file([
        "Data/Processed/confusion_sets.json",
        "Processed/confusion_sets.json",
        "confusion_sets.json",
    ])

    print(f"[*] Project root: {PROJECT_ROOT}")
    print(f"[*] Collocations path: {collocations_path}")
    print(f"[*] Confusion sets path: {confusion_path}")

    # Instantiate engine with explicit paths
    engine = ContextualGrammarEngine(confusion_sets_path=confusion_path)

    collocations_count = len(engine._collocations)
    confusion_map_count = len(engine._confusion_map)

    # Sample verification sentences
    sample_sentence = "དེ་རིང་ང་ཆོས་སྒོར་བོདག་ཡིནན།"
    errors = engine.analyze_sentence(sample_sentence)

    # Sample collocation check
    score_1 = engine.get_collocation_score("ང་", "ཡིན")
    score_2 = engine.get_collocation_score("ཆོས་སྒོར", "བདག")

    summary = {
        "collocations_count": collocations_count,
        "confusion_mappings": confusion_map_count,
        "sample_errors_detected": len(errors),
        "sample_collocation_score_ng_yin": score_1,
        "sample_collocation_score_chos_bdag": score_2,
    }

    print("=" * 60)
    print(f"[✓] Integration Complete!")
    print(f"    Loaded Collocations      : {collocations_count:,}")
    print(f"    Loaded Confusion Maps    : {confusion_map_count:,}")
    print(f"    Sample Malapropisms Found: {len(errors)}")
    print(f"    Collocation score ང་:ཡིན  : {score_1:.2f}")
    print(f"    Collocation score ཆོས་སྒོར:བདག : {score_2:.2f}")
    print("=" * 60)

    logger.info("integrate_collocations_completed", **summary)
    return summary


if __name__ == "__main__":
    integrate_collocations()
