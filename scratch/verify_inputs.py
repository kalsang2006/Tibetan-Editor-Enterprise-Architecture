import json
import sys
from pathlib import Path

ROOT = Path(r"c:\Users\kalsa\Desktop\Tibetan Editor Enterprise Architecture")
sys.path.insert(0, str(ROOT / "src"))

from teea.engine import TEEAEngine

engine = TEEAEngine()

test_inputs = [
    "བཀྲ་ཤེས་བདེ་ལེགས།",
    "བོདསྐད",
    "ང་ཡི་ཕ་ཡུལ",
    "སློབ་སྦྱང",
    "བོད་སྐད་ནི་སྐད་ཡིག་རྙིང་པ་ཞིག་རེད།"
]

results = []

for text in test_inputs:
    res = engine.analyze(text)
    patch_ops = []
    if res.patch and hasattr(res.patch, "operations"):
        for op in res.patch.operations:
            patch_ops.append({
                "span": {"start": op.span.char_start, "end": op.span.char_end},
                "original_slice": text[op.span.char_start:op.span.char_end],
                "replacement": op.replacement
            })
    
    suggs = []
    if res.suggestions:
        for s in res.suggestions:
            suggs.append({
                "source": getattr(s, "source", ""),
                "rule_id": getattr(s, "rule_id", ""),
                "word": getattr(s, "word", ""),
                "suggestion": getattr(s, "suggestion", ""),
                "message": getattr(s, "message", ""),
                "error_type": getattr(s, "error_type", "")
            })
            
    results.append({
        "input": text,
        "patch_operations": patch_ops,
        "suggestions": suggs
    })

with open("scratch/verified_live_outputs.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Analysis complete.")
