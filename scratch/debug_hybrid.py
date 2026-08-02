import json
from teea.engine import TEEAEngine
engine = TEEAEngine()

candidates = engine._correction_provider._find_candidates('བཀྲ་ཤེས')

hybrid = {}
scores = engine._correction_provider._score_candidates('བཀྲ་ཤེས་བདེ་ལེགས།', 0, 7, candidates)

for c in candidates:
    if c not in scores:
        continue
    c_norm = c
    dist = 1
    raw_score = scores[c]

    context_bonus = 0.0
    if engine._correction_provider._corpus_repository is not None:
        try:
            context_bonus = engine._correction_provider._corpus_repository.get_context_score(
                'བཀྲ་ཤེས་བདེ་ལེགས།', 0, 7, c
            )
        except Exception:
            context_bonus = 0.0

    hybrid[c] = (0.5 * raw_score) + (0.3 * context_bonus) - (dist * 0.15)

best_word = max(hybrid, key=lambda k: (hybrid[k], k))

out = {
    "hybrid": hybrid,
    "best_word": best_word
}

with open('scratch/debug_hybrid.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
