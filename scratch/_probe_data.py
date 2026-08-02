"""Probe the gold-pair datasets and BoCorpus to design the unforeseen test set.

Writes a schema dump to scratch/_data_schema.json (UTF-8) so the parent agent can
read it without Windows console encoding issues.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

out: dict = {}

# --- synthetic_errors.json ---
syn_path = Path("Data/SyntheticErrors/synthetic_errors.json")
if syn_path.exists():
    with open(syn_path, encoding="utf-8") as f:
        syn = json.load(f)
    out["synthetic_errors_type"] = type(syn).__name__
    if isinstance(syn, dict):
        out["synthetic_errors_keys"] = list(syn.keys())[:10]
        records = syn.get("records") or syn.get("synthetic_errors") or []
    else:
        records = syn
    out["synthetic_errors_count"] = len(records)
    out["synthetic_errors_sample"] = records[:3] if records else None

# --- grammar_correction_train.jsonl ---
train_path = Path("Data/TrainingData/grammar_correction_train.jsonl")
if train_path.exists():
    pairs = []
    with open(train_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    pairs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    out["train_pairs_count"] = len(pairs)
    out["train_pairs_sample"] = pairs[:3]
    out["train_pair_keys"] = list(pairs[0].keys()) if pairs else None
    # overlap check: how many train incorrect strings appear as corrupted in synthetic
    syn_incorrect = set()
    for r in records[:200000] if isinstance(records, list) else []:
        if isinstance(r, dict):
            syn_incorrect.add(r.get("corrupted_text") or r.get("incorrect") or r.get("src") or r.get("source") or "")

# --- BoCorpus ---
import pandas as pd  # noqa: E402

parquet_path = Path("Data/Corpus/BoCorpus/bo_corpus.parquet")
if parquet_path.exists():
    df = pd.read_parquet(parquet_path, columns=["text"])
    out["bocorpus_rows"] = int(len(df))
    texts = df["text"].dropna().tolist()
    nonempty = [t for t in texts if isinstance(t, str) and len(t.strip()) > 10]
    out["bocorpus_nonempty"] = len(nonempty)
    out["bocorpus_sample"] = nonempty[:3]

# --- tests/data/demo_spelling_examples.json ---
demo_path = Path("tests/data/demo_spelling_examples.json")
if demo_path.exists():
    with open(demo_path, encoding="utf-8") as f:
        demo = json.load(f)
    out["demo_type"] = type(demo).__name__
    out["demo_count"] = len(demo) if isinstance(demo, list) else None
    out["demo_sample"] = demo[:3] if isinstance(demo, list) else list(demo.items())[:3]

with open("scratch/_data_schema.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("wrote scratch/_data_schema.json")
