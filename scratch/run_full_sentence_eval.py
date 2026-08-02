import sys
import json
import time
import math
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path("src").resolve()))

from teea.engine import TEEAEngine
from scratch.run_realworld_eval import PASSAGES

print("Initialising TEEA Engine for Full Sentence-by-Sentence Benchmark...")
engine = TEEAEngine()

# Load real sentences from BoCorpus Parquet
parquet_path = Path("Corpus/BoCorpus/bo_corpus.parquet")

eval_sentences = []

# 1. Add ground-truth sentences from our 50 real-world benchmark passages
for p in PASSAGES:
    sents = [s.strip() for s in p["text"].split("།") if s.strip()]
    error_types_list = []
    for e in p["errors"]:
        err_type = "SPELLING"
        if isinstance(e, tuple):
            err_type = e[1] if len(e) > 1 else "SPELLING"
        elif isinstance(e, dict):
            err_type = e.get("type", "SPELLING")
        error_types_list.append(str(err_type).upper())
    for s in sents:
        s_full = s + "།"
        eval_sentences.append({
            "text": s_full,
            "has_error": len(p["errors"]) > 0,
            "error_types": error_types_list,
            "source": f"eval_passage_{p['id']}"
        })

# 2. Add sentences from BoCorpus Parquet up to 500 total sentences for rigorous evaluation
if parquet_path.exists():
    df = pd.read_parquet(parquet_path)
    corpus_texts = df["text"].dropna().sample(n=min(200, len(df)), random_state=42).tolist()
    for text in corpus_texts:
        sents = [s.strip() for s in text.split("།") if s.strip()]
        for s in sents[:5]:  # Take up to 5 sentences per chunk
            if len(s) > 5:
                eval_sentences.append({
                    "text": s + "།",
                    "has_error": False,  # Natural corpus clean text
                    "error_types": [],
                    "source": "bocorpus"
                })

print(f"Total Sentences Collected for Sentence-Level Benchmark: {len(eval_sentences)}")

tp = 0
fp = 0
fn = 0
tn = 0
spelling_errors = 0
grammar_errors = 0
contextual_errors = 0
clean_sentences = 0
total_tokens = 0
latencies = []

start_eval = time.time()

for item in eval_sentences:
    sentence_text = item["text"]
    total_tokens += len(sentence_text.replace("།", "").split("་"))
    
    if item["has_error"]:
        for et in item["error_types"]:
            if et == "SPELLING": spelling_errors += 1
            elif et == "GRAMMAR": grammar_errors += 1
            elif et in ("CONTEXTUAL", "MALAPROPISM"): contextual_errors += 1
    else:
        clean_sentences += 1

    t0 = time.perf_counter()
    res = engine.analyze(sentence_text)
    t_elapsed = (time.perf_counter() - t0) * 1000.0
    latencies.append(t_elapsed)

    actionable = [s for s in res.suggestions if s.source != "teea.diagnostics"]
    has_prediction = len(actionable) > 0

    if item["has_error"]:
        if has_prediction:
            tp += 1
        else:
            fn += 1
    else:
        if has_prediction:
            fp += 1
        else:
            tn += 1

total_eval_time = time.time() - start_eval
total_sents = len(eval_sentences)

arr = np.array(latencies)
mean_lat = float(np.mean(arr))
std_lat = float(np.std(arr))
median_lat = float(np.median(arr))
p95_lat = float(np.percentile(arr, 95))
p99_lat = float(np.percentile(arr, 99))

accuracy = (tp + tn) / total_sents if total_sents > 0 else 0
precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
fnr = fn / (tp + fn) if (tp + fn) > 0 else 0

print("\n=== FULL SENTENCE-LEVEL EVALUATION COMPLETED ===")
print(f"Total Sentences Evaluated : {total_sents}")
print(f"Total Tokens Evaluated    : {total_tokens}")
print(f"Total Spelling Errors     : {spelling_errors}")
print(f"Total Grammar Errors      : {grammar_errors}")
print(f"Total Contextual Errors   : {contextual_errors}")
print(f"Total Clean Sentences     : {clean_sentences}")
print("-" * 50)
print(f"True Positives (TP)       : {tp}")
print(f"False Positives (FP)      : {fp}")
print(f"False Negatives (FN)      : {fn}")
print(f"True Negatives (TN)       : {tn}")
print(f"Confusion Matrix Total    : {tp + fp + fn + tn} (Matches Total Sentences: {tp + fp + fn + tn == total_sents})")
print("-" * 50)
print(f"Accuracy                  : {accuracy * 100:.2f}%")
print(f"Precision                 : {precision * 100:.2f}%")
print(f"Recall                    : {recall * 100:.2f}%")
print(f"F1 Score                  : {f1 * 100:.2f}%")
print(f"Specificity               : {specificity * 100:.2f}%")
print(f"False Positive Rate (FPR) : {fpr * 100:.2f}%")
print(f"False Negative Rate (FNR) : {fnr * 100:.2f}%")
print("-" * 50)
print(f"Mean Latency              : {mean_lat:.2f} ms ± {std_lat:.2f} ms")
print(f"Median Latency            : {median_lat:.2f} ms")
print(f"P95 Latency               : {p95_lat:.2f} ms")
print(f"P99 Latency               : {p99_lat:.2f} ms")
print(f"Throughput                : {total_sents / total_eval_time:.1f} sentences/sec")
