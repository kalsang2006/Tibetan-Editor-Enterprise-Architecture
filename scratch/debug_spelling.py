import json
from teea.engine import TEEAEngine
engine = TEEAEngine()

# Test candidate generation
candidates = engine._correction_provider._find_candidates('བཀྲ་ཤེས')

res = engine.analyze('བཀྲ་ཤེས་བདེ་ལེགས།')
patch = res.patch.operations if res.patch else []

out = {
    "candidates": candidates,
    "patch": [op.replacement for op in patch]
}

with open('scratch/debug_spelling_out.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
