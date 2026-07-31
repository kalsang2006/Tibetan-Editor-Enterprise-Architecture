#!/usr/bin/env python3
"""Milestone 1 Task 2: Extract Expanded Collocations via PMI Scoring.

Reads `Data/Corpus/BoCorpus/bo_corpus.parquet`, computes Pointwise Mutual Information (PMI)
and t-scores across bigrams, and outputs top 1,000+ collocations to
`Data/Processed/collocations_expanded.json`.

Usage:
    python scripts/extract_expanded_collocations.py
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Ensure src and project root are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
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
    """Clean Tibetan word string."""
    return text.strip("་ །\u0f0b\u0f0d ")


def extract_expanded_collocations(max_documents: int = 500) -> dict[str, Any]:
    """Extract top collocations using PMI scoring from bo_corpus.parquet."""
    pq_path = find_file([
        "Data/Corpus/BoCorpus/bo_corpus.parquet",
        "Corpus/BoCorpus/bo_corpus.parquet",
        "bo_corpus.parquet",
    ])
    out_path = PROJECT_ROOT / "Data" / "Processed" / "collocations_expanded.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not pq_path or not pq_path.exists():
        print(f"[!] Error: bo_corpus.parquet not found at: {pq_path}")
        return {"collocations_count": 0}

    print(f"[*] Reading BoCorpus parquet from: {pq_path}")
    df = pd.read_parquet(pq_path)
    print(f"[*] Corpus loaded: {len(df):,} document records.")

    unigram_counts: Counter[str] = Counter()
    bigram_counts: Counter[tuple[str, str]] = Counter()
    total_bigrams = 0

    docs_to_process = min(len(df), max_documents)
    print(f"[*] Tokenizing & counting n-grams across {docs_to_process:,} documents...")

    for i in range(docs_to_process):
        text = str(df.iloc[i].get("text", ""))
        tokens = [clean_tibetan(w) for w in text.split() if clean_tibetan(w)]
        for w in tokens:
            unigram_counts[w] += 1
        for j in range(len(tokens) - 1):
            w1, w2 = tokens[j], tokens[j + 1]
            if len(w1) > 1 and len(w2) > 1 and w1 != w2:
                bigram_counts[(w1, w2)] += 1
                total_bigrams += 1

    print(f"[+] Total unique bigrams: {len(bigram_counts):,}, total bigram occurrences: {total_bigrams:,}")

    collocations_dict: dict[str, dict[str, float]] = {}
    pmi_scores: list[tuple[str, float, float, int]] = []

    # Calculate PMI and t-score for bigrams with frequency >= 10
    N = float(total_bigrams) if total_bigrams > 0 else 1.0
    for (w1, w2), freq in bigram_counts.items():
        if freq >= 10:
            f1, f2 = float(unigram_counts[w1]), float(unigram_counts[w2])
            expected = (f1 * f2) / N
            pmi = math.log2((float(freq) * N) / (f1 * f2)) if expected > 0 else 0.0
            t_score = (float(freq) - expected) / math.sqrt(float(freq)) if freq > 0 else 0.0
            key = f"{w1}:{w2}"
            pmi_scores.append((key, round(pmi, 2), round(t_score, 2), freq))

    # Sort by PMI score descending and take top 1,500 collocations
    pmi_scores.sort(key=lambda x: (x[1], x[2]), reverse=True)
    top_collocations = pmi_scores[:1500]

    for key, pmi, t_score, freq in top_collocations:
        collocations_dict[key] = {
            "pmi": pmi,
            "t": t_score,
            "freq": freq,
        }

    # Load existing manual collocations to preserve seed entries
    seed_path = find_file([
        "Data/Processed/collocations.json",
        "Processed/collocations.json",
        "collocations.json",
    ])
    if seed_path and seed_path.exists():
        with open(seed_path, "r", encoding="utf-8") as f:
            seed_data = json.load(f)
            seed_cols = seed_data.get("collocations", {})
            for k, v in seed_cols.items():
                if k not in collocations_dict and isinstance(v, dict):
                    collocations_dict[k] = {
                        "pmi": float(v.get("mi", 4.5)),
                        "t": float(v.get("t", 7.0)),
                        "freq": int(v.get("freq", 100)),
                    }

    expanded_payload = {
        "metadata": {
            "total_collocations": len(collocations_dict),
            "description": "Expanded Tibetan bigram collocations scored via Pointwise Mutual Information (PMI) from BoCorpus",
        },
        "collocations": collocations_dict,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(expanded_payload, f, ensure_ascii=False, indent=2)

    summary = {
        "documents_processed": docs_to_process,
        "unique_bigrams_found": len(bigram_counts),
        "top_collocations_saved": len(collocations_dict),
        "output_file": str(out_path),
    }

    print("=" * 60)
    print(f"[✓] Expanded PMI Collocations Extraction Complete!")
    print(f"    Documents Processed  : {docs_to_process:,}")
    print(f"    Top PMI Collocations : {len(collocations_dict):,}")
    print(f"    Output Path          : {out_path}")
    print("=" * 60)

    logger.info("extract_expanded_collocations_completed", **summary)
    return summary


if __name__ == "__main__":
    extract_expanded_collocations()
