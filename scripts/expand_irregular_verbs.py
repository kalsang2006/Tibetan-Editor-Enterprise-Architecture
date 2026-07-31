#!/usr/bin/env python3
"""Task 2: Expand Irregular Verb Mappings.

Extracts verb inflected forms from `verb_lexicon.json`, `lemmas.txt`, and `verbs-final.txt`,
and appends new mappings to `src/teea/resources/morphology/irregular_verbs.json`.

Usage:
    python scripts/expand_irregular_verbs.py
"""

from __future__ import annotations

import json
import re
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

logger = get_logger(__name__)


def find_file(relative_paths: list[str]) -> Path | None:
    """Find first existing candidate path."""
    for rel_path in relative_paths:
        candidate = PROJECT_ROOT / rel_path
        if candidate.exists():
            return candidate
    return None


def clean_tibetan(text: str) -> str:
    """Clean Tibetan syllable or word string."""
    return text.strip("་ །\u0f0b\u0f0d ")


def expand_irregular_verbs() -> dict[str, int]:
    """Expand irregular verbs resource JSON."""
    target_json_path = PROJECT_ROOT / "src" / "teea" / "resources" / "morphology" / "irregular_verbs.json"
    if not target_json_path.exists():
        print(f"[!] Error: Target irregular verbs JSON not found at: {target_json_path}")
        return {"new_mappings": 0}

    with open(target_json_path, "r", encoding="utf-8") as f:
        existing_data: dict[str, dict[str, Any]] = json.load(f)

    initial_count = len(existing_data)
    new_mappings_count = 0

    # 1. Parse verb_lexicon.json
    verb_lex_path = find_file([
        "Data/Processed/verb_lexicon.json",
        "Processed/verb_lexicon.json",
        "verb_lexicon.json",
    ])

    if verb_lex_path and verb_lex_path.exists():
        print(f"[*] Parsing verb_lexicon from: {verb_lex_path}")
        with open(verb_lex_path, "r", encoding="utf-8") as f:
            v_data = json.load(f)
            verbs_map = v_data.get("verbs", {}) if isinstance(v_data, dict) else {}
            for form, info in verbs_map.items():
                w_clean = clean_tibetan(form)
                if w_clean and w_clean not in existing_data:
                    # In verb_lexicon, if tense is present/past/future/imp, stem is w_clean
                    existing_data[w_clean] = {
                        "stem": w_clean,
                        "confidence": 0.90,
                        "rule": f"VERB_LEXICON_{info.get('tense', 'FORM').upper()}",
                        "category": "verb",
                    }
                    new_mappings_count += 1

    # 2. Parse verbs-final.txt
    verbs_final_path = find_file([
        "Data/Verbs/verbs-final.txt",
        "Verbs/verbs-final.txt",
        "verbs-final.txt",
    ])

    if verbs_final_path and verbs_final_path.exists():
        print(f"[*] Parsing verbs-final.txt from: {verbs_final_path}")
        with open(verbs_final_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        # Format: word|pos_tag
        tokens = raw_content.split()
        current_stem = ""
        for token in tokens:
            if "|" in token:
                word_part, pos_part = token.split("|", 1)
                w_clean = clean_tibetan(word_part)
                if not w_clean:
                    continue

                if "v.pres" in pos_part:
                    current_stem = w_clean
                elif ("v.past" in pos_part or "v.fut" in pos_part or "v.imp" in pos_part) and current_stem:
                    if w_clean != current_stem and w_clean not in existing_data:
                        rule_tag = pos_part.replace(".", "_").upper()
                        existing_data[w_clean] = {
                            "stem": current_stem,
                            "confidence": 0.90,
                            "rule": f"VERB_{rule_tag}",
                            "category": "verb",
                        }
                        new_mappings_count += 1

    # 3. Parse lemmas.txt
    lemmas_path = find_file([
        "Data/Verbs/lemmas.txt",
        "Verbs/lemmas.txt",
        "lemmas.txt",
    ])

    if lemmas_path and lemmas_path.exists():
        print(f"[*] Parsing lemmas.txt from: {lemmas_path}")
        with open(lemmas_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                parts = line_str.split("\t")
                lemma_raw = parts[0].strip()
                # Strip √ or numeric annotations like ཀླུབ་√1 -> ཀླུབ་
                lemma_clean = clean_tibetan(re.sub(r"[√\d]", "", lemma_raw))
                if lemma_clean and lemma_clean not in existing_data:
                    existing_data[lemma_clean] = {
                        "stem": lemma_clean,
                        "confidence": 0.75,
                        "rule": "VERB_LEMMA_INFERRED",
                        "category": "verb",
                    }
                    new_mappings_count += 1

    # Save expanded JSON payload
    with open(target_json_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)

    final_count = len(existing_data)
    summary = {
        "initial_mappings": initial_count,
        "final_mappings": final_count,
        "new_mappings_added": new_mappings_count,
    }

    print("=" * 60)
    print(f"[✓] Irregular Verbs Expansion Complete!")
    print(f"    Initial mappings : {initial_count:,}")
    print(f"    Final mappings   : {final_count:,}")
    print(f"    New mappings     : {new_mappings_count:,}")
    print("=" * 60)

    logger.info("expand_irregular_verbs_completed", **summary)
    return summary


if __name__ == "__main__":
    expand_irregular_verbs()
