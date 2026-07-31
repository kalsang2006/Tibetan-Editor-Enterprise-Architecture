#!/usr/bin/env python3
"""Task 1: Merge Vocabulary into the Dictionary.

Merges words and frequency data from BoCorpus vocabulary (`bocorpus_vocabulary.json`)
and classical lexicon (`classical-lexicon.txt`) into TEEA's SQLite database (`teea.db`).

Usage:
    python scripts/merge_vocabulary.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Ensure src directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from teea.core.logging import get_logger
from teea.persistence.sqlite import DatabaseManager

logger = get_logger(__name__)


def find_file(relative_paths: list[str]) -> Path | None:
    """Find the first existing path from candidate relative paths."""
    for rel_path in relative_paths:
        candidate = PROJECT_ROOT / rel_path
        if candidate.exists():
            return candidate
    return None


def resolve_db_path() -> Path:
    """Resolve path to teea.db SQLite database."""
    candidates = [
        "Data/Processed/teea.db",
        "Processed/teea.db",
        "teea.db",
    ]
    db_file = find_file(candidates)
    if db_file:
        return db_file
    
    mgr = DatabaseManager()
    return mgr.path


def ensure_db_schema(conn: sqlite3.Connection) -> None:
    """Ensure dictionary_entries table exists and has source/frequency columns."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dictionary_entries (
            surface TEXT NOT NULL PRIMARY KEY,
            tag_distribution TEXT NOT NULL,
            source TEXT,
            frequency INTEGER DEFAULT 0
        )
    """)
    cur.execute("PRAGMA table_info(dictionary_entries)")
    cols = {row[1] for row in cur.fetchall()}
    if "source" not in cols:
        cur.execute("ALTER TABLE dictionary_entries ADD COLUMN source TEXT")
    if "frequency" not in cols:
        cur.execute("ALTER TABLE dictionary_entries ADD COLUMN frequency INTEGER DEFAULT 0")
    conn.commit()


def merge_vocabulary() -> dict[str, int]:
    """Execute vocabulary merging logic."""
    vocab_path = find_file([
        "Data/Processed/bocorpus_vocabulary.json",
        "Processed/bocorpus_vocabulary.json",
        "bocorpus_vocabulary.json",
    ])
    classical_path = find_file([
        "Data/Lexicons/classical-lexicon.txt",
        "Lexicons/classical-lexicon.txt",
        "classical-lexicon.txt",
    ])
    db_path = resolve_db_path()

    print(f"[*] Project root: {PROJECT_ROOT}")
    print(f"[*] SQLite DB: {db_path}")

    conn = sqlite3.connect(str(db_path), timeout=60.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA busy_timeout=60000")
    ensure_db_schema(conn)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM dictionary_entries")
    initial_count = cur.fetchone()[0]

    # 1. Process BoCorpus Vocabulary
    if vocab_path and vocab_path.exists():
        print(f"[*] Reading BoCorpus vocabulary from: {vocab_path}")
        with open(vocab_path, "r", encoding="utf-8") as f:
            vocab_raw = json.load(f)
            vocab_data = vocab_raw.get("syllable_frequencies", vocab_raw) if isinstance(vocab_raw, dict) else {}

        batch: list[tuple[str, str, str, int]] = []
        for word, freq_val in vocab_data.items():
            w_clean = word.strip("་ །\u0f0b\u0f0d ")
            if not w_clean:
                continue
            freq = freq_val.get("freq", 1) if isinstance(freq_val, dict) else (int(freq_val) if isinstance(freq_val, (int, float, str)) else 1)
            batch.append((w_clean, json.dumps({"NOUN": 1}), "corpus", int(freq)))

        cur.executemany("""
            INSERT INTO dictionary_entries (surface, tag_distribution, source, frequency)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(surface) DO UPDATE SET
                frequency = MAX(dictionary_entries.frequency, excluded.frequency),
                source = COALESCE(dictionary_entries.source, excluded.source)
        """, batch)
        conn.commit()
        print(f"[+] Processed {len(batch)} words from BoCorpus vocabulary.")
    else:
        print("[!] Warning: BoCorpus vocabulary file not found.")

    # 2. Process Classical Lexicon
    if classical_path and classical_path.exists():
        print(f"[*] Reading Classical Lexicon from: {classical_path}")
        classical_words: set[str] = set()
        with open(classical_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                word = line_str.split("\t")[0].strip("་ །\u0f0b\u0f0d ")
                if word:
                    classical_words.add(word)

        batch_class: list[tuple[str, str, str, int]] = [
            (w, json.dumps({"NOUN": 1}), "classical", 1) for w in classical_words
        ]
        cur.executemany("""
            INSERT INTO dictionary_entries (surface, tag_distribution, source, frequency)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(surface) DO UPDATE SET
                source = CASE 
                    WHEN dictionary_entries.source IS NULL THEN excluded.source
                    WHEN dictionary_entries.source = 'corpus' THEN 'corpus+classical'
                    ELSE dictionary_entries.source
                END
        """, batch_class)
        conn.commit()
        print(f"[+] Processed {len(classical_words)} words from Classical Lexicon.")
    else:
        print("[!] Warning: Classical lexicon file not found.")

    cur.execute("SELECT COUNT(*) FROM dictionary_entries")
    final_count = cur.fetchone()[0]
    new_words_added = final_count - initial_count

    conn.close()

    summary = {
        "initial_words": initial_count,
        "final_words": final_count,
        "new_words_added": new_words_added,
    }

    print("=" * 60)
    print(f"[✓] Merge Complete!")
    print(f"    Initial dictionary entries : {initial_count:,}")
    print(f"    Final dictionary entries   : {final_count:,}")
    print(f"    New entries added          : {new_words_added:,}")
    print("=" * 60)

    logger.info("merge_vocabulary_completed", **summary)
    return summary


if __name__ == "__main__":
    merge_vocabulary()
