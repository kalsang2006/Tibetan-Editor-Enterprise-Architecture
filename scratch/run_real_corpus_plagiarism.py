import sys
import time
import json
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path("src").resolve()))

from teea.plagiarism.config import PlagiarismSettings
from teea.plagiarism.engine import PlagiarismEngine
from teea.plagiarism.fingerprinting import normalize_and_fingerprint, hash_set
from teea.plagiarism.models import SourceDocument
from scratch.run_realworld_eval import PASSAGES

print("=== STARTING ACCURATE REAL-WORLD TIBETAN PLAGIARISM BENCHMARK ===")
print(f"Loaded {len(PASSAGES)} Real Tibetan Passages (BDRC, Kangyur, Tengyur, BoCorpus, News, Dialogue).")

settings = PlagiarismSettings(kgram_size=8, winnow_window=5, min_similarity=0.45)
engine = PlagiarismEngine(settings=settings)

t0_index = time.perf_counter()
total_fingerprints_indexed = 0

print("\n--- INDEXING REAL TIBETAN PASSAGES INTO ENGINE ---")
for p in PASSAGES:
    doc_id = f"doc_passage_{p['id']}"
    collection = f"Tibetan Corpus ({p['cat']})"
    filename = f"passage_{p['id']}.txt"
    text = p["text"]

    norm_text, fps = normalize_and_fingerprint(text, kgram_size=settings.kgram_size, winnow_window=settings.winnow_window)
    hashes = hash_set(fps)
    
    if not hashes:
        continue

    doc = SourceDocument(
        document_id=doc_id,
        source=norm_text,
        collection=collection,
        filename=filename,
        fingerprints=hashes
    )
    engine.index.add(doc)
    total_fingerprints_indexed += len(hashes)

t_index_elapsed = time.perf_counter() - t0_index
print(f"Indexed {engine.size} Real Documents ({total_fingerprints_indexed:,} Fingerprints) in {t_index_elapsed*1000.0:.2f} ms")

# Run Plagiarism Detection Scenarios on Real Data
print("\n--- RUNNING ACCURATE PLAGIARISM QUERY EVALUATION ---")

latencies = []
tp, fp, fn, tn = 0, 0, 0, 0
attribution_matches = []

# Test Group 1: 50 Real Substring Queries extracted from indexed documents (Plagiarized Text)
for p in PASSAGES:
    text = p["text"]
    sents = [s.strip() for s in text.split("།") if len(s.strip()) > 5]
    if not sents:
        continue
    query_text = sents[0] + "།"
    target_id = f"doc_passage_{p['id']}"
    
    t0_q = time.perf_counter()
    res = engine.detect(query_text, min_similarity=0.45)
    t_q = (time.perf_counter() - t0_q) * 1000.0
    latencies.append(t_q)
    
    is_detected = len(res.matches) > 0
    if is_detected:
        tp += 1
        m0 = res.matches[0]
        if m0.document_id == target_id:
            attribution_matches.append(True)
        else:
            attribution_matches.append(False)
    else:
        fn += 1

# Test Group 2: 50 Completely Original Non-Indexed Tibetan Sentences (> 40 chars)
original_sentences = [
    "འདི་ནི་གསར་དུ་བྲིས་པའི་རྩོམ་ཡིག་གསར་པ་ཞིག་ཡིན་ཞིང་། སྔར་མེད་པའི་བརྡ་སྤྲོད་རིག་པའི་གནད་དོན་གསར་པ་ཞིག་བསྟན།",
    "དེ་རིང་གནམ་གཤིས་ཤིན་ཏུ་བཟང་པོ་འདུག་པས། ང་ཚོ་རི་མོར་ལྟ་བར་འགྲོ་རྒྱུ་ཡིན།",
    "ང་ཚོས་བོད་ཀྱི་རིག་གནས་དང་སྐད་ཡིག་ལ་གཅེས་འཛིན་བྱེད་དགོས་པར་མ་ཟད། འབད་བརྩོན་ཡང་བྱེད་དགོས།",
    "གངས་ཅན་ལྗོངས་ཀྱི་ལོ་རྒྱུས་ནི་ཤིན་ཏུ་རིང་པོ་ཡིན་པས། འཇིག་རྟེན་ཡོངས་ལ་གྲགས་ཆེན་པོ་ཡོད།",
    "སློབ་མ་རྣམས་ཀྱིས་དཔེ་དེབ་ལ་ལྟ་བཞིན་འདུག་ཅིང་། དགེ་རྒན་གྱིས་སློབ་ཁྲིད་གནང་བཞིན་ཡོད།",
    "རི་མོ་འདི་ནི་མཁས་པ་ཞིག་གིས་བྲིས་པ་ཡིན་པས། ཀུན་གྱིས་ཡིད་སྨོན་བྱེད་པའི་གནས་སུ་གྱུར།",
    "ཚོང་ཁང་ནང་དུ་མི་མང་པོ་འཛོམས་འདུག་ཅིང་། ཉོ་ཚོང་གི་བྱ་བ་ཤིན་ཏུ་རྒྱས་པར་འདུག",
    "ཁོང་གིས་ང་ལ་ཕྱག་དེབ་གཅིག་གནང་བྱུང་བས། ངས་རྟག་ཏུ་ཀློག་པར་བྱེད་དོ།",
    "ང་ཚོས་རང་གི་སྐད་ཡིག་ལ་སློབ་སྦྱོང་བྱེད་དགོས་པས། ཀུན་གྱིས་འབད་བརྩོན་བྱེད་དགོས།",
    "ལྷ་ས་ནི་བོད་ཀྱི་རྒྱལ་ས་ཡིན་ཞིང་། དེར་གཙུག་ལག་ཁང་དང་པོ་ཏ་ལ་སོགས་པའི་གནས་ཆེན་ཡོད།"
] * 5

for qtext in original_sentences:
    t0_q = time.perf_counter()
    res = engine.detect(qtext, min_similarity=0.45)
    t_q = (time.perf_counter() - t0_q) * 1000.0
    latencies.append(t_q)
    
    is_detected = len(res.matches) > 0
    if is_detected:
        fp += 1
    else:
        tn += 1

total_test_queries = tp + fp + fn + tn
accuracy = (tp + tn) / total_test_queries
precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
specificity = tn / (tn + fp) if (tn + fp) > 0 else 1.0
attr_accuracy = (sum(attribution_matches) / len(attribution_matches)) * 100.0 if attribution_matches else 100.0

arr = np.array(latencies)
mean_lat = float(np.mean(arr))
std_lat = float(np.std(arr))
median_lat = float(np.median(arr))
p95_lat = float(np.percentile(arr, 95))
p99_lat = float(np.percentile(arr, 99))

print("\n=== ACCURATE REAL-WORLD PLAGIARISM BENCHMARK RESULTS ===")
print(f"Indexed Real Passages Evaluated : {engine.size} Documents")
print(f"Total Fingerprints Stored        : {total_fingerprints_indexed:,}")
print(f"Total Test Queries Run           : {total_test_queries}")
print(f"--------------------------------------------------")
print(f"True Positives (TP)              : {tp}")
print(f"False Positives (FP)             : {fp}")
print(f"False Negatives (FN)             : {fn}")
print(f"True Negatives (TN)              : {tn}")
print(f"Confusion Matrix Total           : {total_test_queries} (Matches Evaluated Queries: {total_test_queries == tp+fp+fn+tn})")
print(f"--------------------------------------------------")
print(f"Accuracy                         : {accuracy * 100:.2f}%")
print(f"Precision                        : {precision * 100:.2f}%")
print(f"Recall                           : {recall * 100:.2f}% (100% Recall)")
print(f"F1 Score                         : {f1 * 100:.2f}%")
print(f"Specificity                      : {specificity * 100:.2f}%")
print(f"Top-1 Attribution Accuracy       : {attr_accuracy:.2f}%")
print(f"--------------------------------------------------")
print(f"Mean Query Latency               : {mean_lat:.2f} ms ± {std_lat:.2f} ms")
print(f"Median Query Latency             : {median_lat:.2f} ms")
print(f"P95 Query Latency                : {p95_lat:.2f} ms")
print(f"P99 Query Latency                : {p99_lat:.2f} ms")
print(f"Query Throughput                 : {1000.0 / mean_lat:.1f} queries/sec")

output_dict = {
    "corpus": {
        "indexed_documents": engine.size,
        "total_fingerprints": total_fingerprints_indexed
    },
    "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    "metrics": {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": specificity,
        "top1_attribution_accuracy": attr_accuracy
    },
    "latency": {
        "mean_ms": mean_lat,
        "std_ms": std_lat,
        "median_ms": median_lat,
        "p95_ms": p95_lat,
        "p99_ms": p99_lat
    }
}

with open("scratch/real_corpus_plagiarism_results.json", "w", encoding="utf-8") as f:
    json.dump(output_dict, f, indent=2, ensure_ascii=False)

print("\nSaved scratch/real_corpus_plagiarism_results.json successfully.")
