import json
from teea.engine import TEEAEngine
engine = TEEAEngine()

# Let's directly call TiBERT engine
tibert = engine._ai_runtime
from teea.ai.runtime import Request
request = Request(
    source="teea.spelling",
    task="score_candidates",
    inputs={
        "sentence": 'བཀྲ་ཤེས་བདེ་ལེགས།',
        "word_start": 4,
        "word_end": 7,
        "candidates": ['ཤིས']
    }
)
out = tibert.execute(request)
with open('scratch/debug_tibert2.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
