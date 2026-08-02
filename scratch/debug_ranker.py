import json
from teea.engine import TEEAEngine
engine = TEEAEngine()

# Get the plugin
spell_plugin = None
for p in engine._plugins:
    if p.name == "teea.spelling":
        spell_plugin = p
        break

text = 'བཀྲ་ཤེས་བདེ་ལེགས།'
ranker = spell_plugin._contextual_ranker

if ranker:
    # བཀྲ starts at 0, ends at 4 (with tsheg)
    # ཤེས starts at 4, ends at 7
    try:
        sus_shis = ranker.is_suspicious(text, 4, 7)
        pll_shis = ranker.pll(text, 4, 7, 'ཤིས')
        pll_shes = ranker.pll(text, 4, 7, 'ཤེས')
        
        # calculate gap
        import math
        word = text[4:7].strip()
        cand_syls = ranker._syllables(word) if hasattr(ranker, '_syllables') else [word]
        baseline = ranker.unigram_log_prob(cand_syls[0]) if cand_syls else 0.0
        gap = baseline - pll_shes
        
    except Exception as e:
        sus_shis = str(e)
        pll_shis = 0
        pll_shes = 0
        baseline = 0
        gap = 0
else:
    sus_shis = False
    pll_shis = 0
    pll_shes = 0
    baseline = 0
    gap = 0
    
out = {
    "has_ranker": ranker is not None,
    "sus_shis": sus_shis,
    "pll_shis": pll_shis,
    "pll_shes": pll_shes,
    "baseline": baseline,
    "gap": gap,
    "suspicious_gap": ranker._suspicious_gap if ranker else None
}

with open('scratch/debug_ranker.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
