#!/usr/bin/env python3
"""Task 5: Data Inventory Viewer for TEEA.

A standalone script that inspects all Tibetan language data files and databases across
the repository (`Data/` and root) and prints a comprehensive summary dashboard.

Usage:
    python scripts/data_inventory.py
"""

from __future__ import annotations

import json
import os
import sqlite3
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


def format_size(bytes_size: int) -> str:
    """Format file size in human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024.0 or unit == "GB":
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} GB"


def inspect_inventory() -> dict[str, Any]:
    """Inspect all repository datasets and print formatted inventory report."""
    print("=" * 80)
    print("                TEEA TIBETAN LANGUAGE DATA INVENTORY REPORT")
    print("=" * 80)
    print(f"[*] Repository Root Path: {PROJECT_ROOT}")
    print("-" * 80)

    report_data: dict[str, Any] = {}

    # 1. BoCorpus Vocabulary
    v_path = find_file(["Data/Processed/bocorpus_vocabulary.json", "Processed/bocorpus_vocabulary.json", "bocorpus_vocabulary.json"])
    if v_path and v_path.exists():
        size_str = format_size(v_path.stat().st_size)
        with open(v_path, "r", encoding="utf-8") as f:
            v_raw = json.load(f)
            v_dict = v_raw.get("syllable_frequencies", v_raw) if isinstance(v_raw, dict) else {}
            total_sylls = v_raw.get("total_syllables", sum(int(x.get("freq", x) if isinstance(x, dict) else x) for x in v_dict.values()))
            report_data["bocorpus_vocab"] = {"count": len(v_dict), "total_syllables": total_sylls, "size": size_str}
            print(f"  [✓] BoCorpus Vocabulary   : {len(v_dict):,} unique words ({total_sylls:,} total tokens) [{size_str}]")
    else:
        print("  [×] BoCorpus Vocabulary   : Not found")

    # 2. Classical Lexicon
    c_path = find_file(["Data/Lexicons/classical-lexicon.txt", "Lexicons/classical-lexicon.txt", "classical-lexicon.txt"])
    if c_path and c_path.exists():
        size_str = format_size(c_path.stat().st_size)
        lines = [l for l in c_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        report_data["classical_lexicon"] = {"count": len(lines), "size": size_str}
        print(f"  [✓] Classical Lexicon     : {len(lines):,} entries [{size_str}]")
    else:
        print("  [×] Classical Lexicon     : Not found")

    # 3. Verb Lexicon & Verbs
    vl_path = find_file(["Data/Processed/verb_lexicon.json", "Processed/verb_lexicon.json", "verb_lexicon.json"])
    vl_count = 0
    if vl_path and vl_path.exists():
        size_str = format_size(vl_path.stat().st_size)
        v_data = json.load(open(vl_path, encoding="utf-8"))
        verbs = v_data.get("verbs", {}) if isinstance(v_data, dict) else {}
        vl_count = len(verbs)
        print(f"  [✓] Verb Lexicon (JSON)   : {vl_count:,} verb lemmas [{size_str}]")

    vf_path = find_file(["Data/Verbs/verbs-final.txt", "Verbs/verbs-final.txt", "verbs-final.txt"])
    vf_count = 0
    if vf_path and vf_path.exists():
        size_str = format_size(vf_path.stat().st_size)
        lines = [l for l in vf_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        vf_count = len(lines)
        print(f"  [✓] Verb Inflections      : {vf_count:,} inflected forms [{size_str}]")

    lem_path = find_file(["Data/Verbs/lemmas.txt", "Verbs/lemmas.txt", "lemmas.txt"])
    lem_count = 0
    if lem_path and lem_path.exists():
        size_str = format_size(lem_path.stat().st_size)
        lines = [l for l in lem_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        lem_count = len(lines)
        print(f"  [✓] Verb Lemmas           : {lem_count:,} lemmas [{size_str}]")

    # 4. Collocations
    col_path = find_file(["Data/Processed/collocations.json", "Processed/collocations.json", "collocations.json"])
    if col_path and col_path.exists():
        size_str = format_size(col_path.stat().st_size)
        c_data = json.load(open(col_path, encoding="utf-8"))
        col_dict = c_data.get("collocations", {}) if isinstance(c_data, dict) else {}
        report_data["collocations"] = {"count": len(col_dict), "size": size_str}
        print(f"  [✓] Collocations          : {len(col_dict):,} word pairs [{size_str}]")

    # 5. Confusion Sets
    cs_path = find_file(["Data/Processed/confusion_sets.json", "Processed/confusion_sets.json", "confusion_sets.json"])
    if cs_path and cs_path.exists():
        size_str = format_size(cs_path.stat().st_size)
        cs_data = json.load(open(cs_path, encoding="utf-8"))
        c_dict = len(cs_data.get("confusion_dict", {})) if isinstance(cs_data, dict) else 0
        orth = len(cs_data.get("orthographic", [])) if isinstance(cs_data, dict) else 0
        phon = len(cs_data.get("phonetic", [])) if isinstance(cs_data, dict) else 0
        vis = len(cs_data.get("visual", [])) if isinstance(cs_data, dict) else 0
        print(f"  [✓] Confusion Sets        : {c_dict:,} dict mappings, {orth+phon+vis:,} pair rules [{size_str}]")

    # 6. Sanskrit Loanwords
    sk_path = find_file(["Data/Processed/sanskrit_words.json", "Processed/sanskrit_words.json", "sanskrit_words.json"])
    if sk_path and sk_path.exists():
        size_str = format_size(sk_path.stat().st_size)
        sk_data = json.load(open(sk_path, encoding="utf-8"))
        sk_list = sk_data.get("sanskrit_words", sk_data) if isinstance(sk_data, dict) else sk_data
        sk_count = len(sk_list) if isinstance(sk_list, list) else 0
        print(f"  [✓] Sanskrit Loanwords    : {sk_count:,} loanwords [{size_str}]")

    # 7. Synthetic Errors Dataset
    syn_path = find_file(["Data/SyntheticErrors/synthetic_errors.json", "SyntheticErrors/synthetic_errors.json", "synthetic_errors.json"])
    if syn_path and syn_path.exists():
        size_str = format_size(syn_path.stat().st_size)
        syn_data = json.load(open(syn_path, encoding="utf-8"))
        syn_list = syn_data.get("synthetic_errors", syn_data) if isinstance(syn_data, dict) else syn_data
        syn_count = len(syn_list) if isinstance(syn_list, list) else 0
        print(f"  [✓] Synthetic Errors      : {syn_count:,} training error pairs [{size_str}]")

    # 8. BoCorpus Parquet File
    pq_path = find_file(["Data/Corpus/BoCorpus/bo_corpus.parquet", "Corpus/BoCorpus/bo_corpus.parquet", "bo_corpus.parquet"])
    if pq_path and pq_path.exists():
        size_str = format_size(pq_path.stat().st_size)
        print(f"  [✓] BoCorpus Parquet      : Authentic Tibetan Corpus [{size_str}]")

    # 9. SQLite Database (teea.db)
    db_path = find_file(["Data/Processed/teea.db", "Processed/teea.db", "teea.db"])
    if db_path and db_path.exists():
        size_str = format_size(db_path.stat().st_size)
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM dictionary_entries")
        dict_rows = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM verb_frames")
        verb_rows = cur.fetchone()[0]
        conn.close()
        print(f"  [✓] SQLite DB (teea.db)   : {dict_rows:,} dictionary entries, {verb_rows:,} verb frames [{size_str}]")

    # 10. Morphology JSON Resources
    irr_path = PROJECT_ROOT / "src" / "teea" / "resources" / "morphology" / "irregular_verbs.json"
    if irr_path.exists():
        size_str = format_size(irr_path.stat().st_size)
        irr_data = json.load(open(irr_path, encoding="utf-8"))
        print(f"  [✓] Irregular Verbs JSON  : {len(irr_data):,} morphology rules [{size_str}]")

    print("=" * 80)
    print("                             INVENTORY COMPLETE")
    print("=" * 80)

    return report_data


if __name__ == "__main__":
    inspect_inventory()
