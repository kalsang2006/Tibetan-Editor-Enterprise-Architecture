#!/usr/bin/env python3
"""Milestone 1 Task 1: Extract Expanded Confusion Sets from Synthetic Errors.

Reads `Data/SyntheticErrors/synthetic_errors.json`, parses error -> correction pairs
across error categories, and outputs 500+ structured rules to
`Data/Processed/confusion_sets_expanded.json`.

Usage:
    python scripts/extract_expanded_confusion_sets.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
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

logger = get_logger(__name__)


def find_file(relative_paths: list[str]) -> Path | None:
    """Find first existing candidate path."""
    for rel_path in relative_paths:
        candidate = PROJECT_ROOT / rel_path
        if candidate.exists():
            return candidate
    return None


def clean_tibetan(text: str) -> str:
    """Clean Tibetan text string."""
    return text.strip("་ །\u0f0b\u0f0d ")


def extract_expanded_confusion_sets() -> dict[str, Any]:
    """Extract expanded confusion sets from synthetic_errors.json."""
    syn_path = find_file([
        "Data/SyntheticErrors/synthetic_errors.json",
        "SyntheticErrors/synthetic_errors.json",
        "synthetic_errors.json",
    ])
    out_path = PROJECT_ROOT / "Data" / "Processed" / "confusion_sets_expanded.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not syn_path or not syn_path.exists():
        print(f"[!] Error: synthetic_errors.json not found at: {syn_path}")
        return {"expanded_count": 0}

    print(f"[*] Reading synthetic errors from: {syn_path}")
    with open(syn_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        records = data.get("records", data.get("synthetic_errors", []))
    elif isinstance(data, list):
        records = data
    else:
        records = []

    print(f"[*] Processing {len(records):,} synthetic error entries...")

    confusion_dict: dict[str, list[str]] = defaultdict(list)
    pair_counts: dict[tuple[str, str], int] = defaultdict(int)

    for item in records:
        orig = item.get("original_text", "")
        corr = item.get("corrupted_text", "")
        desc = item.get("description", "")
        err_type = item.get("error_type", "")

        if not orig or not corr or orig == corr:
            continue

        # Extract replaced words from description if available
        # E.g. "Replaced 'བ' with confused character 'ཕ'" or "Substituted case particle 'ཀྱི་' with 'ཀྱིས་'"
        match_sub = re.search(r"(?:Replaced|Substituted|Swapped)\s+'([^']+)'\s+with\s+(?:confused character|case particle|'([^']+)')", desc)
        if match_sub:
            c1 = clean_tibetan(match_sub.group(1))
            c2 = clean_tibetan(match_sub.group(2) or desc.split("'")[-2] if "'" in desc else "")
            if c1 and c2 and c1 != c2:
                # c1 is original (correct), c2 is corrupted (wrong)
                pair_counts[(c2, c1)] += 1

        # Tokenize and extract aligned word pairs
        orig_words = [clean_tibetan(w) for w in orig.split() if clean_tibetan(w)]
        corr_words = [clean_tibetan(w) for w in corr.split() if clean_tibetan(w)]

        if len(orig_words) == len(corr_words):
            for w_corr, w_orig in zip(corr_words, orig_words):
                if w_corr != w_orig and len(w_corr) > 1 and len(w_orig) > 1:
                    pair_counts[(w_corr, w_orig)] += 1

    # Filter pairs with count >= 2 to remove noisy one-off typos
    for (wrong, right), count in sorted(pair_counts.items(), key=lambda x: x[1], reverse=True):
        if count >= 2 and wrong != right and len(wrong) > 1 and len(right) > 1:
            if wrong not in confusion_dict or right not in confusion_dict[wrong]:
                confusion_dict[wrong].append(right)

    # Load existing confusion_sets.json to preserve manual seed rules
    seed_path = find_file([
        "Data/Processed/confusion_sets.json",
        "Processed/confusion_sets.json",
        "confusion_sets.json",
    ])
    if seed_path and seed_path.exists():
        with open(seed_path, "r", encoding="utf-8") as f:
            seed_data = json.load(f)
            seed_dict = seed_data.get("confusion_dict", {})
            for k, v in seed_dict.items():
                k_clean = clean_tibetan(k)
                v_list = [clean_tibetan(x) for x in v] if isinstance(v, list) else [clean_tibetan(v)]
                for val in v_list:
                    if val and val not in confusion_dict[k_clean]:
                        confusion_dict[k_clean].append(val)

    expanded_payload = {
        "metadata": {
            "total_confusion_rules": len(confusion_dict),
            "description": "Expanded Tibetan confusion sets mined from synthetic_errors corpus",
        },
        "confusion_dict": dict(confusion_dict),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(expanded_payload, f, ensure_ascii=False, indent=2)

    total_rules = len(confusion_dict)
    summary = {
        "synthetic_records_processed": len(records),
        "total_confusion_rules": total_rules,
        "output_file": str(out_path),
    }

    print("=" * 60)
    print(f"[✓] Expanded Confusion Sets Extraction Complete!")
    print(f"    Synthetic Records Processed : {len(records):,}")
    print(f"    Expanded Confusion Mappings: {total_rules:,}")
    print(f"    Output Path                : {out_path}")
    print("=" * 60)

    logger.info("extract_expanded_confusion_sets_completed", **summary)
    return summary


if __name__ == "__main__":
    extract_expanded_confusion_sets()
