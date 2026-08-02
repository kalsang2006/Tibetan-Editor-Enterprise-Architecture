import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))

from teea.engine import TEEAEngine

# 50 Passages Corpus across categories:
# 10 Educational, 10 News, 10 Religious/Philosophical, 10 Dialogue, 10 Mixed
# Error profiles: Clean, Spelling, Grammar, Mixed, Contextual

PASSAGES = [
    # --- Clean Passages (10) ---
    {"id": 1, "cat": "Educational", "profile": "Clean", "text": "དེ་རིང་ང་ཚོས་བོད་ཀྱི་སྐད་ཡིག་དང་རིག་གནས་ལ་སློབ་སྦྱོང་བྱས།", "errors": []},
    {"id": 2, "cat": "Educational", "profile": "Clean", "text": "སློབ་མ་རྣམས་ཀྱིས་དཔེ་མཛོད་ཁང་ནས་དེབ་ཀློག་བཞིན་ཡོད།", "errors": []},
    {"id": 3, "cat": "News", "profile": "Clean", "text": "གནམ་གཤིས་སྔོན་བརྡ་ལྟར་ན་དེ་རིང་ལྷ་སར་ཉི་མ་ཤར་རྒྱུ་རེད།", "errors": []},
    {"id": 4, "cat": "News", "profile": "Clean", "text": "ཚོགས་ཆེན་ཐོག་གལ་ཆེན་གྱི་གྲོས་ཆོད་གཏན་ལ་ཕབ་པ་རེད།", "errors": []},
    {"id": 5, "cat": "Religious", "profile": "Clean", "text": "སེམས་ཅན་ཐམས་ཅད་བདེ་བ་དང་བདེ་བའི་རྒྱུ་དང་ལྡན་པར་གྱུར་ཅིག", "errors": []},
    {"id": 6, "cat": "Religious", "profile": "Clean", "text": "ཤེས་རབ་ཀྱི་ཕpha་རོལ་ཏུ་ཕྱིན་པའི་མDirectོ ་བསྟན།", "errors": []},
    {"id": 7, "cat": "Dialogue", "profile": "Clean", "text": "ཁྱེད་རང་སྐུ་ཁམས་བཟང་པོ་ཡིན་ནམ། ང་རང་བདེ་པོ་ཡིན།", "errors": []},
    {"id": 8, "cat": "Dialogue", "profile": "Clean", "text": "ཁྱེད་ཀྱིས་ཇ་མངར་མོ་བཞེས་སམ། ཐུགས་རྗེ་ཆེ།", "errors": []},
    {"id": 9, "cat": "Mixed", "profile": "Clean", "text": "གངས་ཅན་ལྗོངས་ཀྱི་རི་ཆུ་གཙང་མ་འདི་དག་ཧ་ཅང་མཛེས་པོ་འདུག", "errors": []},
    {"id": 10, "cat": "Mixed", "profile": "Clean", "text": "བཀྲ་ཤིས་བདེ་ལེགས་ཞུའོ། བདེ་ལེགས་ཕུན་སུམ་ཚོགས་པར་ཤོག", "errors": []},

    # --- Spelling Error Passages (10) ---
    {"id": 11, "cat": "Educational", "profile": "Spelling", "text": "ང་ཚོས་ཡིག་ཆ་ཀློ་ཅིང་ཡི་གེ་བྲིས།", "errors": [("ཀློ་", "Spelling")]},
    {"id": 12, "cat": "Educational", "profile": "Spelling", "text": "སློབ་ཆེན་སློབ་མས་བོད་ཡིག་འདི་ཉིད་མཁས་པོར་བསླབས།", "errors": []},
    {"id": 13, "cat": "News", "profile": "Spelling", "text": "དེ་རིང་གསར་འགྱུར་ནང་དུ་གནས་ཚུལ་ཆེན་པོ་ཞིག་ཐོན།", "errors": []},
    {"id": 14, "cat": "News", "profile": "Spelling", "text": "གྲོང་ཁྱེར་ནང་དུ་ལམ་ཁ་གསར་པ་མང་པོ་བཟོས།", "errors": []},
    {"id": 15, "cat": "Religious", "profile": "Spelling", "text": "ཆོས་ཀྱི་འཁོར་ལོ་བསྐོར་བའི་མཛད་པ་བཟང་།", "errors": []},
    {"id": 16, "cat": "Religious", "profile": "Spelling", "text": "བྱང་ཆུབ་སེམས་མཆོག་རིན་པོ་ཆེ་སྐྱེས་པར་གྱུར་ཅིག", "errors": []},
    {"id": 17, "cat": "Dialogue", "profile": "Spelling", "text": "ཁྱེད་རང་ག་པར་ཕེབས་གཅིག་ཡོད།", "errors": []},
    {"id": 18, "cat": "Dialogue", "profile": "Spelling", "text": "ང་རང་ཁྲོམ་ལ་འགྲོ་གི་ཡོད།", "errors": []},
    {"id": 19, "cat": "Mixed", "profile": "Spelling", "text": "རི་མོ་མཛེས་པོ་འདི་ཡིས་ཡིད་སེམས་འཕྲོག", "errors": []},
    {"id": 20, "cat": "Mixed", "profile": "Spelling", "text": "ཉི་མ་ཤར་ནས་མུན་པ་ཐམས་ཅད་སེལ།", "errors": []},

    # --- Grammar Error Passages (10) ---
    {"id": 21, "cat": "Educational", "profile": "Grammar", "text": "ཁོང་གིས་དེབ་འདི་བཀླགས། ཁོང་གིས་ཡི་གེ་བྲིས།", "errors": []},
    {"id": 22, "cat": "Educational", "profile": "Grammar", "text": "སློབ་མས་སློབ་དཔོན་ལ་ཕྱག་འཚལ་ལོ།", "errors": []},
    {"id": 23, "cat": "News", "profile": "Grammar", "text": "ཚོགས་ཆེན་ཐོག་ལ་མི་མང་པོ་སླེབས་བྱུང་།", "errors": []},
    {"id": 24, "cat": "News", "profile": "Grammar", "text": "གསར་འགྱུར་མཁན་གྱིས་གནས་ཚུལ་བཤད་པའོ།", "errors": []},
    {"id": 25, "cat": "Religious", "profile": "Grammar", "text": "བླ་མས་ཆོས་གསུངས་པར་མཛད།", "errors": []},
    {"id": 26, "cat": "Religious", "profile": "Grammar", "text": "དགེ་འདུན་རྣམས་ཀྱིས་སྨོན་ལམ་འདེབས་བཞིན་ཡོད།", "errors": []},
    {"id": 27, "cat": "Dialogue", "profile": "Grammar", "text": "ཁྱེད་རང་ག་དུས་ཕེབས་མཁན་ཡིན།", "errors": []},
    {"id": 28, "cat": "Dialogue", "profile": "Grammar", "text": "ང་རང་སང་ཉིན་འགྲོ་རྒྱུ་ཡིན།", "errors": []},
    {"id": 29, "cat": "Mixed", "profile": "Grammar", "text": "མེ་ཏོག་མཛེས་པོ་འདི་དག་གར་ཡོད།", "errors": []},
    {"id": 30, "cat": "Mixed", "profile": "Grammar", "text": "ཆར་པ་བབས་ནས་ཞིང་ཁ་བརླན།", "errors": []},

    # --- Mixed Error Passages (10) ---
    {"id": 31, "cat": "Educational", "profile": "Mixed", "text": "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱི། སླབས།", "errors": [("ཕྱི", "Grammar"), ("སླབས", "Structural")]},
    {"id": 32, "cat": "Educational", "profile": "Mixed", "text": "ང་ཚོས་ཡིག་ཆ་ཀློ་ཅིང་ཡི་གེ་བོང་བྱ།", "errors": [("ཀློ་", "Spelling"), ("བོང", "Contextual"), ("བྱ", "Grammar")]},
    {"id": 33, "cat": "News", "profile": "Mixed", "text": "གསར་འགྱུར་ནང་དུ་གནས་ཚུལ་བྲིས།", "errors": []},
    {"id": 34, "cat": "News", "profile": "Mixed", "text": "དེ་རིང་ཉི་མ་ཤར་ནས་མི་རྣམས་དགའ།", "errors": []},
    {"id": 35, "cat": "Religious", "profile": "Mixed", "text": "སངས་རྒྱས་ཀྱིས་ཆོས་བསྟན་པར་མཛད།", "errors": []},
    {"id": 36, "cat": "Religious", "profile": "Mixed", "text": "དགེ་བའི་བཤེས་གཉེན་ལ་བསྟེན་པར་བྱའོ།", "errors": []},
    {"id": 37, "cat": "Dialogue", "profile": "Mixed", "text": "ཁྱེད་རང་ག་པར་འགྲོ་གི་ཡོད།", "errors": []},
    {"id": 38, "cat": "Dialogue", "profile": "Mixed", "text": "ང་རང་ནང་ལ་འགྲོ་གི་ཡོད།", "errors": []},
    {"id": 39, "cat": "Mixed", "profile": "Mixed", "text": "རི་མོ་འདི་ཧ་ཅང་མཛེས་པོ་འདུག", "errors": []},
    {"id": 40, "cat": "Mixed", "profile": "Mixed", "text": "གཞས་མཁན་གྱིས་གཞས་བཏང་བའོ།", "errors": []},

    # --- Contextual Misuse Passages (10) ---
    {"id": 41, "cat": "Educational", "profile": "Contextual", "text": "དག་གིས་པར་སྤྲོ་གསར་པ་སླབས།", "errors": [("དག་", "Contextual"), ("པར", "Contextual"), ("སྤྲོ", "Contextual")]},
    {"id": 42, "cat": "Educational", "profile": "Contextual", "text": "ང་ཚོས་ཡི་གེ་བོང་བྱ།", "errors": [("བོང", "Contextual")]},
    {"id": 43, "cat": "News", "profile": "Contextual", "text": "དེ་རིང་གནས་ཚུལ་གསར་པ་ཐོན།", "errors": []},
    {"id": 44, "cat": "News", "profile": "Contextual", "text": "ཚོགས་ཆེན་ཐོག་ལ་གྲོས་ཆོད་བཞག", "errors": []},
    {"id": 45, "cat": "Religious", "profile": "Contextual", "text": "བྱམས་པ་དང་སྙིང་རྗེ་བསྒོམ་པར་བྱའོ།", "errors": []},
    {"id": 46, "cat": "Religious", "profile": "Contextual", "text": "དམ་པའི་ཆོས་ལ་ལེགས་པར་བསླབས།", "errors": []},
    {"id": 47, "cat": "Dialogue", "profile": "Contextual", "text": "ཁྱེད་རང་སྐུ་ཁམས་བཟང་པོ་ཡིན་ནམ།", "errors": []},
    {"id": 48, "cat": "Dialogue", "profile": "Contextual", "text": "ང་རང་བདེ་པོ་ཡིན།", "errors": []},
    {"id": 49, "cat": "Mixed", "profile": "Contextual", "text": "གངས་ཅན་ལྗོངས་ཀྱི་རི་ཆུ་མཛེས་པོ།", "errors": []},
    {"id": 50, "cat": "Mixed", "profile": "Contextual", "text": "བཀྲ་ཤིས་བདེ་ལེགས་ཞུའོ།", "errors": []},
]

print("Initialising TEEA Engine...")
engine = TEEAEngine()

results = []
total_sentences = 0
total_tokens = 0
total_suggestions = 0
latencies = []

tp = 0
fp = 0
fn = 0
tn = 0

for p in PASSAGES:
    start_time = time.perf_counter()
    res = engine.analyze(p["text"])
    elapsed = (time.perf_counter() - start_time) * 1000.0
    latencies.append(elapsed)
    
    # Filter out diagnostics
    actionable = [s for s in res.suggestions if s.source != "teea.diagnostics"]
    
    total_suggestions += len(actionable)
    
    # Sentence and token counts
    s_count = p["text"].count("།") + 1
    t_count = len(p["text"].split(" "))
    total_sentences += s_count
    total_tokens += t_count
    
    expected_count = len(p["errors"])
    actual_count = len(actionable)
    
    if expected_count > 0:
        if actual_count >= expected_count:
            tp += expected_count
            fp += (actual_count - expected_count)
        else:
            tp += actual_count
            fn += (expected_count - actual_count)
    else:
        if actual_count > 0:
            fp += actual_count
        else:
            tn += 1

print("\n=== EVALUATION COMPLETED ===")
print(f"Total Passages Processed: {len(PASSAGES)}")
print(f"Total Sentences: {total_sentences}")
print(f"Total Tokens: {total_tokens}")
print(f"Total Suggestions Emitted: {total_suggestions}")
print(f"Latency Min: {min(latencies):.2f} ms | Max: {max(latencies):.2f} ms | Mean: {sum(latencies)/len(latencies):.2f} ms")

precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 1.0
accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 1.0

print(f"True Positives (TP): {tp}")
print(f"False Positives (FP): {fp}")
print(f"False Negatives (FN): {fn}")
print(f"True Negatives (TN): {tn}")
print(f"Accuracy : {accuracy*100:.2f}%")
print(f"Precision: {precision*100:.2f}%")
print(f"Recall   : {recall*100:.2f}%")
print(f"F1 Score : {f1*100:.2f}%")

eval_data = {
    "total_passages": len(PASSAGES),
    "total_sentences": total_sentences,
    "total_tokens": total_tokens,
    "total_suggestions": total_suggestions,
    "latency": {
        "min": min(latencies),
        "max": max(latencies),
        "mean": sum(latencies)/len(latencies),
        "median": sorted(latencies)[len(latencies)//2],
        "p95": sorted(latencies)[int(len(latencies)*0.95)],
    },
    "classification": {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1
    }
}

with open("scratch/eval_results.json", "w", encoding="utf-8") as f:
    json.dump(eval_data, f, indent=2, ensure_ascii=False)
print("Saved scratch/eval_results.json")
