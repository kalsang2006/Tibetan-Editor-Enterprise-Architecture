import json
from teea.engine import TEEAEngine
engine = TEEAEngine()

candidates = engine._correction_provider._find_candidates('བཀྲ་ཤེས')

scores = engine._correction_provider._score('བཀྲ་ཤེས་བདེ་ལེགས།', 0, 7, candidates)

out = {
    "scores": scores
}

with open('scratch/debug_scores.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
