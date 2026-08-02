import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path("src").resolve()))

from teea.engine import TEEAEngine
from scratch.run_realworld_eval import PASSAGES

engine = TEEAEngine()

print("=== ALL SUGGESTIONS IN CLEAN PASSAGES (FALSE POSITIVES) ===\n")
fp_count = 0

for p in PASSAGES:
    res = engine.analyze(p["text"])
    actionable = [s for s in res.suggestions if s.source != "teea.diagnostics"]
    expected_count = len(p["errors"])
    
    # Clean passages or extra suggestions beyond expected
    if expected_count == 0 and len(actionable) > 0:
        for s in actionable:
            fp_count += 1
            matched = p["text"][s.span.char_start:s.span.char_end] if s.span else ""
            rule_id = getattr(s, "rule_id", "N/A")
            score = getattr(s, "score", getattr(s, "confidence", 0.0))
            print(f"FP #{fp_count}")
            print(f"Passage ID   : {p['id']} ({p['cat']})")
            print(f"Text         : '{p['text']}'")
            print(f"Flagged Word : '{matched}'")
            print(f"Source       : {s.source}")
            print(f"Message      : {s.message}")
            print(f"Replacement  : {s.replacement}")
            print(f"Score        : {score}")
            print("-" * 60)
