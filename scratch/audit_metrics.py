import sys
import json
import io
import traceback
from pathlib import Path

# Fix stdout for windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add src to pythonpath
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from teea.nlp.snapshot.builder import LanguageServerSnapshotBuilder
from teea.plugins.builtin.spelling import SpellCheckerPlugin

def evaluate_metrics():
    print("\n=========================================================")
    print("NLP ACCURACY & METRICS EVALUATION")
    print("=========================================================\n")
    
    data_path = Path(__file__).resolve().parent.parent / "Data" / "SyntheticErrors" / "synthetic_errors.json"
    if not data_path.exists():
        print("DATASET NOT FOUND.")
        return

    try:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            records = data.get("records", [])
    except Exception as e:
        print(f"FAILED TO LOAD DATASET: {e}")
        return
        
    print(f"Loaded {len(records)} test records from dataset.")
    
    builder = LanguageServerSnapshotBuilder()
    speller = SpellCheckerPlugin()
    
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    
    sample_size = min(500, len(records))
    print(f"Evaluating SpellChecker on {sample_size} records...")
    
    for i in range(sample_size):
        record = records[i]
        text = record.get("corrupted_text", "")
        
        if not text:
            continue
            
        try:
            snap = builder.analyze(text)
            suggestions = list(speller.examine(snap))
            
            # Since this is a "SyntheticErrors" dataset, every record HAS an error.
            if len(suggestions) > 0:
                true_positives += 1
            else:
                false_negatives += 1
                
        except Exception:
            pass 
            
    # To get false positives, we would need clean text. The dataset provides 'original_text'
    print(f"Evaluating False Positives on clean text...")
    for i in range(sample_size):
        record = records[i]
        clean_text = record.get("original_text", "")
        if not clean_text: continue
        try:
            snap = builder.analyze(clean_text)
            suggestions = list(speller.examine(snap))
            if len(suggestions) > 0:
                false_positives += 1 # Flagged an error on clean text!
        except Exception:
            pass

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    print("\n--- Spelling Engine Metrics ---")
    print(f"Dataset Used: synthetic_errors.json ({sample_size} samples)")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1-Score:  {f1:.4f}")
    print(f"TP: {true_positives} | FP: {false_positives} | FN: {false_negatives}")

if __name__ == "__main__":
    evaluate_metrics()
