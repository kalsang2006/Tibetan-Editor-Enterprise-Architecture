#!/usr/bin/env python3
"""Task 1: Generate Tibetan Grammatical Error Correction (GEC) Training Dataset.

Generates parallel training data pairs (incorrect, correct) for TiBERT GEC training
by combining synthetic error corpora, particle/verb tense mutators, prefix orthographic errors,
and clean sentences from BoCorpus.

Output: Data/TrainingData/grammar_correction_train.jsonl
Usage: python scripts/generate_grammar_training_data.py --max-sentences 50000
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from teea.core.logging import get_logger

logger = get_logger(__name__)

# Common Tibetan particle mappings for error injection
PARTICLE_MUTATIONS: dict[str, str] = {
    "གིས": "གི",
    "ཀྱིས": "ཀྱི",
    "གྱིས": "གྱི",
    "ཡིས": "ཡི",
    "ལ": "ནི",
    "དུ": "སུ",
    "ཏུ": "རུ",
    "ནས": "ལས",
    "ནི": "ལ",
}

# Verb tense shifts (present/future <-> past)
VERB_TENSE_MUTATIONS: dict[str, str] = {
    "ཕྱིན": "ཕྱི",
    "ཕྱི": "ཕྱིན",
    "བྱས": "བྱ",
    "བྱ": "བྱས",
    "བསླབས": "སླབས",
    "སླབས": "བསླབས",
    "སློབ": "བསླབས",
    "བལྟས": "ལྟ",
    "ལྟ": "བལྟས",
}

# Common Tibetan prefix letters that are often mistakenly added or dropped
PREFIX_LETTERS = ["བ", "ས", "འ", "མ", "ག"]


def inject_prefix_orthographic_error(sentence: str) -> tuple[str, str] | None:
    """Inject a single-letter prefix addition or deletion error.

    Example:
        Clean:  "སློབ་སྦྱོང་གིས་..."
        Error:  "སློབ་བསྦྱོང་གིས་..." (Accidental initial 'བ' added)
    """
    syllables = sentence.split("་")
    if len(syllables) < 2:
        return None

    # Pick a random syllable that has at least one character
    candidates = [i for i, s in enumerate(syllables) if len(s.strip()) >= 2]
    if not candidates:
        return None

    idx = random.choice(candidates)
    target = syllables[idx]

    # 50% chance: add an extraneous prefix, 50% chance: strip an existing prefix
    if random.random() < 0.5:
        prefix = random.choice(PREFIX_LETTERS)
        corrupted = prefix + target
        if corrupted == target:
            return None
    else:
        if target and target[0] in PREFIX_LETTERS:
            corrupted = target[1:]
            if corrupted == target:
                return None
        else:
            # No prefix to strip, so add one instead
            prefix = random.choice(PREFIX_LETTERS)
            corrupted = prefix + target
            if corrupted == target:
                return None

    syllables[idx] = corrupted
    corrupted_sentence = "་".join(syllables)
    if corrupted_sentence != sentence:
        return corrupted_sentence, sentence
    return None


def load_synthetic_errors(path: Path, max_records: int) -> list[dict[str, str]]:
    """Load existing parallel pairs from synthetic_errors.json."""
    if not path.exists():
        logger.warning("synthetic_errors_not_found", path=str(path))
        return []

    with open(path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    records = raw_data.get("records", []) if isinstance(raw_data, dict) else (raw_data if isinstance(raw_data, list) else [])

    pairs: list[dict[str, str]] = []
    for r in records[:max_records]:
        incorrect = r.get("corrupted_text", "").strip()
        correct = r.get("original_text", "").strip()
        if incorrect and correct and incorrect != correct:
            pairs.append({"incorrect": incorrect, "correct": correct, "category": r.get("error_type", "SYNTHETIC")})

    logger.info("loaded_synthetic_errors", count=len(pairs))
    return pairs


def load_clean_corpus_sentences(parquet_path: Path, max_sentences: int) -> list[str]:
    """Extract clean sentences from BoCorpus parquet file."""
    if not parquet_path.exists():
        logger.warning("bo_corpus_parquet_not_found", path=str(parquet_path))
        return []

    sentences: list[str] = []
    try:
        import pandas as pd

        df = pd.read_parquet(parquet_path)
        col = "text" if "text" in df.columns else df.columns[-2]
        raw_texts = df[col].dropna().astype(str).tolist()

        for text in raw_texts:
            # Split by newlines and Shad delimiters །
            chunks = text.replace("\r", "").replace("།", "།\n").split("\n")
            for chunk in chunks:
                clean_s = chunk.strip()
                if len(clean_s) >= 10 and len(clean_s) <= 200:
                    sentences.append(clean_s)
                    if len(sentences) >= max_sentences:
                        break
            if len(sentences) >= max_sentences:
                break
    except Exception as e:
        logger.error("failed_reading_parquet", error=str(e))

    logger.info("loaded_clean_sentences", count=len(sentences))
    return sentences


def mutate_sentence(sentence: str) -> tuple[str, str] | None:
    """Inject a grammatical or orthographic error into a clean sentence."""
    words = sentence.split("་")
    if len(words) < 3:
        return None

    # ONLY grammar/spelling mutations, NO semantic/lexical swaps, NO word-order swaps
    mutation_type = random.choice([
        "PARTICLE",
        "TENSE",
        "PREFIX_ERROR",   # <-- Safe orthographic mutation
    ])

    corrupted_words = list(words)
    mutated = False

    if mutation_type == "PARTICLE":
        for i, w in enumerate(corrupted_words):
            if w in PARTICLE_MUTATIONS:
                corrupted_words[i] = PARTICLE_MUTATIONS[w]
                mutated = True
                break

    elif mutation_type == "TENSE":
        for i, w in enumerate(corrupted_words):
            if w in VERB_TENSE_MUTATIONS:
                corrupted_words[i] = VERB_TENSE_MUTATIONS[w]
                mutated = True
                break

    elif mutation_type == "PREFIX_ERROR":
        res = inject_prefix_orthographic_error(sentence)
        if res:
            return res

    if mutated:
        incorrect_sentence = "་".join(corrupted_words)
        if incorrect_sentence != sentence:
            return incorrect_sentence, sentence

    return None


def generate_dataset(max_total: int = 50000) -> list[dict[str, str]]:
    """Generate complete parallel GEC dataset."""
    synthetic_path = PROJECT_ROOT / "Data" / "SyntheticErrors" / "synthetic_errors.json"
    parquet_path = PROJECT_ROOT / "Data" / "Corpus" / "BoCorpus" / "bo_corpus.parquet"

    pairs: list[dict[str, str]] = []

    # 1. Synthetic errors file (contains strictly orthographic errors)
    syn_pairs = load_synthetic_errors(synthetic_path, max_records=max_total // 2)
    pairs.extend(syn_pairs)

    # 2. Mutate clean corpus sentences using only safe orthographic/grammar mutations
    if len(pairs) < max_total:
        needed = max_total - len(pairs)
        clean_sentences = load_clean_corpus_sentences(parquet_path, max_sentences=needed * 2)

        for s in clean_sentences:
            res = mutate_sentence(s)
            if res:
                incorrect, correct = res
                pairs.append({"incorrect": incorrect, "correct": correct, "category": "MUTATED_SENTENCE"})
                if len(pairs) >= max_total:
                    break

    # Shuffle for training robustness
    random.seed(42)
    random.shuffle(pairs)

    return pairs[:max_total]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Generate Tibetan GEC Training Dataset")
    parser.add_argument("--max-sentences", type=int, default=50000, help="Maximum training pairs to output")
    parser.add_argument("--output", type=str, default="Data/TrainingData/grammar_correction_train.jsonl", help="Output file path")
    args = parser.parse_args()

    out_path = PROJECT_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[*] Generating up to {args.max_sentences:,} Tibetan GEC training pairs...")
    dataset = generate_dataset(max_total=args.max_sentences)

    print(f"[*] Writing training data to: {out_path}")
    with open(out_path, "w", encoding="utf-8") as f:
        for record in dataset:
            f.write(json.dumps({"incorrect": record["incorrect"], "correct": record["correct"]}, ensure_ascii=False) + "\n")

    print("=" * 70)
    print(f"[SUCCESS] Task 1 Complete! Generated GEC Training Dataset:")
    print(f"    Total Pairs Generated : {len(dataset):,}")
    print(f"    Output File Path     : {out_path}")
    print(f"    File Size            : {out_path.stat().st_size / (1024 * 1024):.2f} MB")
    print("=" * 70)

    if dataset:
        print("\nSample Generated Pairs:")
        for sample in dataset[:3]:
            print(f"  Incorrect : {sample['incorrect']}")
            print(f"  Correct   : {sample['correct']}\n")


if __name__ == "__main__":
    main()
