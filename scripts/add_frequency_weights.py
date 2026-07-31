#!/usr/bin/env python3
"""Task 4: Use Corpus Frequencies for Suggestion Ranking.

Loads `bocorpus_vocabulary.json` and injects frequency weights into candidate correction
generation, ensuring high-frequency corpus words rank higher in suggestions.

Usage:
    python scripts/add_frequency_weights.py
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
from teea.persistence.dictionary import InMemoryDictionaryRepository
from teea.plugins.builtin.correction_providers import DictionaryOnlyCorrectionProvider

logger = get_logger(__name__)


def find_file(relative_paths: list[str]) -> Path | None:
    """Find first existing candidate path."""
    for rel_path in relative_paths:
        candidate = PROJECT_ROOT / rel_path
        if candidate.exists():
            return candidate
    return None


def add_frequency_weights() -> dict[str, Any]:
    """Execute frequency weight loading and test suggestion ranking."""
    vocab_path = find_file([
        "Data/Processed/bocorpus_vocabulary.json",
        "Processed/bocorpus_vocabulary.json",
        "bocorpus_vocabulary.json",
    ])

    print(f"[*] Project root: {PROJECT_ROOT}")
    print(f"[*] Vocabulary frequencies path: {vocab_path}")

    frequencies: dict[str, int] = {}
    if vocab_path and vocab_path.exists():
        with open(vocab_path, "r", encoding="utf-8") as f:
            raw_vocab = json.load(f)
            freq_dict = raw_vocab.get("syllable_frequencies", raw_vocab) if isinstance(raw_vocab, dict) else {}
            for k, v in freq_dict.items():
                w_clean = k.strip("་ །\u0f0b\u0f0d ")
                if w_clean:
                    freq = v.get("freq", 1) if isinstance(v, dict) else int(v)
                    frequencies[w_clean] = freq

    print(f"[+] Loaded frequencies for {len(frequencies):,} words.")

    dict_repo = InMemoryDictionaryRepository()
    provider_unweighted = DictionaryOnlyCorrectionProvider(dict_repo)
    provider_weighted = DictionaryOnlyCorrectionProvider(dict_repo, frequencies=frequencies)

    test_word = "བཀྲི"
    cands_unweighted = provider_unweighted.generate_candidates(test_word, f"ང་ཚོས་{test_word}བྱེད")
    cands_weighted = provider_weighted.generate_candidates(test_word, f"ང་ཚོས་{test_word}བྱེད")

    summary = {
        "frequency_words_count": len(frequencies),
        "test_word": test_word,
        "unweighted_candidates": [(c.word, c.confidence) for c in cands_unweighted],
        "weighted_candidates": [(c.word, c.confidence) for c in cands_weighted],
    }

    print("=" * 60)
    print(f"[✓] Frequency Weighting Applied!")
    print(f"    Total Corpus Frequencies : {len(frequencies):,}")
    print(f"    Test Word                : '{test_word}'")
    print(f"    Unweighted Candidates   : {[(c.word, c.confidence) for c in cands_unweighted]}")
    print(f"    Weighted Candidates     : {[(c.word, c.confidence) for c in cands_weighted]}")
    print("=" * 60)

    logger.info("add_frequency_weights_completed", **summary)
    return summary


if __name__ == "__main__":
    add_frequency_weights()
