import json
import sys
from pathlib import Path
import random

ROOT = Path(r"c:\Users\kalsa\Desktop\Tibetan Editor Enterprise Architecture")
sys.path.insert(0, str(ROOT / "src"))

from teea.engine import TEEAEngine

def apply_patch(text, patch):
    operations = getattr(patch, "operations", [])
    if not operations:
        return text
    
    # Sort operations by char_start in reverse order so applying them doesn't shift earlier offsets
    ops = sorted(operations, key=lambda op: op.span.char_start, reverse=True)
    for op in ops:
        start = op.span.char_start
        end = op.span.char_end
        rep = op.replacement
        text = text[:start] + rep + text[end:]
    return text

def main():
    print("Loading TEEA Engine...")
    engine = TEEAEngine()

    spelling_examples = []
    grammar_examples = []
    clean_examples = []

    # Load synthetic errors (positive examples)
    synth_file = ROOT / "Data" / "SyntheticErrors" / "synthetic_errors.json"
    with open(synth_file, "r", encoding="utf-8") as f:
        synthetic_data = json.load(f)
        synthetic_records = synthetic_data.get("records", [])

    print(f"Loaded {len(synthetic_records)} records. Searching for perfect matches...")

    for record in synthetic_records:
        error_type = record.get("error_type", "")
        
        is_grammar = error_type in ["PARTICLE_OMISSION", "VOWEL_MUTATION", "CHARACTER_CONFUSION", "CASE_PARTICLE_SUBSTITUTION"]
        is_spelling = error_type in ["TSHEG_DROP", "SYLLABLE_SWAP", "WORD_DUPLICATION"]

        if is_spelling and len(spelling_examples) >= 30:
            pass
        elif is_grammar and len(grammar_examples) >= 30:
            pass
        elif (not is_spelling) and (not is_grammar):
            continue
        
        if len(spelling_examples) >= 30 and len(grammar_examples) >= 30:
            break

        corrupted = record.get("corrupted_text", "")
        target = record.get("original_text", "")

        if not corrupted or not target:
            continue

        try:
            unified = engine.analyze(corrupted)
            patch = unified.patch
            
            operations = getattr(patch, "operations", [])
            if not operations:
                continue
                
            predicted = apply_patch(corrupted, patch)
            
            if predicted.strip() == target.strip():
                # Extract wrong/right for the specific operation (assume 1 main operation for demo)
                wrong_text = corrupted[operations[0].span.char_start:operations[0].span.char_end]
                right_text = operations[0].replacement
                
                example = {
                    "input": corrupted,
                    "expected": predicted,
                    "wrong": wrong_text,
                    "right": right_text,
                    "type": error_type
                }
                
                if is_spelling and len(spelling_examples) < 30:
                    spelling_examples.append(example)
                elif is_grammar and len(grammar_examples) < 30:
                    grammar_examples.append(example)
        except Exception as e:
            continue

    # 8. Add a few clean sentences from BoCorpus
    print("Collecting clean examples...")
    try:
        from teea.corpus.repository import BoCorpusRepository
        corpus_repo = BoCorpusRepository()
        if corpus_repo.is_available():
            # Get some random sentences from corpus
            df = corpus_repo.load_dataframe()
            if df is not None and "text" in df.columns:
                texts = df["text"].dropna().tolist()
                random.shuffle(texts)
                for t in texts[:20]: # Try first 20 random ones
                    unified = engine.analyze(t)
                    if not getattr(unified.patch, "operations", []):
                        clean_examples.append({
                            "input": t,
                            "expected": t,
                            "type": "CLEAN"
                        })
                        if len(clean_examples) >= 5:
                            break
    except Exception as e:
        print(f"Could not load corpus: {e}")

    # 6. Fallback if not enough examples
    if len(spelling_examples) < 30:
        print(f"Warning: Only found {len(spelling_examples)} spelling examples. Adding fallbacks.")
        spelling_examples.append({
            "input": "སློབ་སྦྱང",
            "expected": "སློབ་སྦྱོང",
            "wrong": "སློབ་སྦྱང",
            "right": "སློབ་སྦྱོང",
            "type": "FALLBACK"
        })
        
    if len(grammar_examples) < 30:
        print(f"Warning: Only found {len(grammar_examples)} grammar examples. Adding fallbacks.")
        grammar_examples.append({
            "input": "བཀྲ་ཤེས་བདེ་ལེགས།",
            "expected": "བཀྲ་ཤིས་བདེ་ལེགས།",
            "wrong": "བཀྲ་ཤེས",
            "right": "བཀྲ་ཤིས",
            "type": "FALLBACK"
        })

    out_file = ROOT / "scratch" / "demo_examples.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "spelling": spelling_examples,
            "grammar": grammar_examples,
            "clean": clean_examples
        }, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(spelling_examples)} spelling, {len(grammar_examples)} grammar, {len(clean_examples)} clean examples.")
    print(f"Output saved to {out_file}")

if __name__ == "__main__":
    main()
