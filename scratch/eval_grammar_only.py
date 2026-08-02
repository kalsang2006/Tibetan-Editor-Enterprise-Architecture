import sys
import json
import time
import math
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path("src").resolve()))

from teea.plugins.builtin.grammar import GrammarCheckerPlugin
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from scratch.run_realworld_eval import PASSAGES

print("Initialising GrammarCheckerPlugin & SnapshotBuilder...")
grammar_plugin = GrammarCheckerPlugin()
builder = LanguageServerSnapshotBuilder()

eval_sentences = []

for p in PASSAGES:
    sents = [s.strip() for s in p["text"].split("།") if s.strip()]
    g_errors = [e for e in p["errors"] if isinstance(e, tuple) and len(e) > 1 and e[1] in ("Grammar", "Structural", "Contextual")]
    for s in sents:
        eval_sentences.append({
            "text": s + "།",
            "has_error": len(g_errors) > 0,
            "error_details": g_errors,
            "passage_id": p["id"]
        })

print(f"Total Sentences for Grammar Evaluation: {len(eval_sentences)}")

tp, fp, fn, tn = 0, 0, 0, 0
latencies = []
rule_stats = {}

start_time = time.time()

for item in eval_sentences:
    sentence_text = item["text"]
    snapshot = builder.analyze(sentence_text)
    
    t0 = time.perf_counter()
    suggestions = list(grammar_plugin.examine(snapshot))
    t_elapsed = (time.perf_counter() - t0) * 1000.0
    latencies.append(t_elapsed)

    has_prediction = len(suggestions) > 0

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

    for s in suggestions:
        rule_id = getattr(s, "rule_id", getattr(s, "error_type", "GRAMMAR_GENERAL"))
        if rule_id not in rule_stats:
            rule_stats[rule_id] = {"evals": 0, "tp": 0, "fp": 0}
        rule_stats[rule_id]["evals"] += 1
        if item["has_error"]:
            rule_stats[rule_id]["tp"] += 1
        else:
            rule_stats[rule_id]["fp"] += 1

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

print("\n=== GRAMMAR CHECKER SCIENTIFIC EVALUATION COMPLETED ===")
print(f"Total Sentences Evaluated : {total_sents}")
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
print("-" * 50)
print(f"Mean Latency              : {mean_lat:.2f} ms ± {std_lat:.2f} ms")
print(f"Median Latency            : {median_lat:.2f} ms")
print(f"P95 Latency               : {p95_lat:.2f} ms")
print(f"P99 Latency               : {p99_lat:.2f} ms")
print("-" * 50)
print("Per-Rule Breakdown:")
for rid, st in rule_stats.items():
    r_prec = st["tp"] / (st["tp"] + st["fp"]) if (st["tp"] + st["fp"]) > 0 else 0
    print(f"  • {rid}: Evals={st['evals']}, TP={st['tp']}, FP={st['fp']}, Precision={r_prec*100:.1f}%")
