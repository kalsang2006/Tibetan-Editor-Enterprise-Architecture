import json
from teea.engine import TEEAEngine
engine = TEEAEngine()

candidates = engine._correction_provider._find_candidates('ཤེས')
scores = engine._correction_provider._score('བཀྲ་ཤེས་བདེ་ལེགས།', 4, 7, candidates)

out = {
    "scores": scores,
    "best": engine._correction_provider.correct_with_score('ཤེས', 'བཀྲ་ཤེས་བདེ་ལེགས།', 4, 7)
}

with open('scratch/debug_tibert.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
