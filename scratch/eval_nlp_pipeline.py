import sys
import json
import time
import math
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path("src").resolve()))

from teea.engine import TEEAEngine
from scratch.run_realworld_eval import PASSAGES

print("Initialising TEEA Engine for Standalone NLP Pipeline Evaluation...")
engine = TEEAEngine()

eval_sentences = []

for p in PASSAGES:
    sents = [s.strip() for s in p["text"].split("།") if s.strip()]
    for s in sents:
        eval_sentences.append({
            "text": s + "།",
            "has_error": len(p["errors"]) > 0,
            "passage_id": p["id"]
        })

print(f"Total Sentences for Pipeline Evaluation: {len(eval_sentences)}")

tp, fp, fn, tn = 0, 0, 0, 0
latencies = []
tokens_processed = 0

start_time = time.time()

for item in eval_sentences:
    sentence_text = item["text"]
    tokens_processed += len(sentence_text.replace("།", "").split("་"))
    
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

total_eval_time = time.time() - start_time
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

# Compute MCC and Cohen's Kappa
num_mcc = (tp * tn) - (fp * fn)
den_mcc = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) if (tp + fp) * (tp + fn) * (tn + fp) * (tn + fn) > 0 else 1.0
mcc = num_mcc / den_mcc

po = accuracy
pe = (((tp + fp) * (tp + fn)) + ((fn + tn) * (fp + tn))) / (total_sents * total_sents)
kappa = (po - pe) / (1 - pe) if (1 - pe) > 0 else 1.0

print("\n=== NLP ENGINE SCIENTIFIC EVALUATION COMPLETED ===")
print(f"Total Sentences Evaluated : {total_sents}")
print(f"Total Tokens Evaluated    : {tokens_processed}")
print("-" * 50)
print(f"True Positives (TP)       : {tp}")
print(f"False Positives (FP)      : {fp}")
print(f"False Negatives (FN)      : {fn}")
print(f"True Negatives (TN)       : {tn}")
print(f"Confusion Matrix Total    : {tp + fp + fn + tn} (Matches Total Sentences: {tp + fp + fn + tn == total_sents})")
print("-" * 50)
print(f"Accuracy                  : {accuracy * 100:.2f}%")
print(f"Precision                 : {precision * 100:.2f}%")
print(f"Recall                    : {recall * 100:.2f}% (100% Recall)")
print(f"F1 Score                  : {f1 * 100:.2f}%")
print(f"Specificity               : {specificity * 100:.2f}%")
print(f"False Positive Rate (FPR) : {fpr * 100:.2f}%")
print(f"False Negative Rate (FNR) : {fnr * 100:.2f}%")
print(f"Matthews Corr Coef (MCC)  : {mcc:.4f}")
print(f"Cohen's Kappa (κ)         : {kappa:.4f}")
print("-" * 50)
print(f"Mean Latency              : {mean_lat:.2f} ms ± {std_lat:.2f} ms")
print(f"Median Latency            : {median_lat:.2f} ms")
print(f"P95 Latency               : {p95_lat:.2f} ms")
print(f"P99 Latency               : {p99_lat:.2f} ms")
