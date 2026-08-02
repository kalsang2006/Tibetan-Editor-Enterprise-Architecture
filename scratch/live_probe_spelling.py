import sys
sys.path.insert(0, "src")
import os
import json
os.environ["TEEA_TOKENIZATION__MODEL_LOCAL_PATH"] = "./TiBERT"

from teea.engine import TEEAEngine

with open("tests/demo_spelling_examples.json", encoding="utf-8") as f:
    examples = json.load(f)

engine = TEEAEngine()
print("=== corpus repo available? ===", engine._corpus_repo is not None)

for ex in examples:
    text = ex["wrong"]
    print("\n--- input:", repr(text), " expected correct:", repr(ex["correct"]), "---")
    snapshot = engine._builder.analyze(text)
    results = engine._plugin_runtime.dispatch(snapshot)
    for outcome in results.outcomes:
        if outcome.failure is not None:
            print("  FAILURE", outcome.plugin, outcome.failure)
        for s in outcome.suggestions:
            print("  ", outcome.plugin, "->", s.error_type, s.replacement, s.message[:80])
