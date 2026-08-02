import json
from teea.plugins.builtin.correction import CorrectionProvider
from teea.corpus.repository import BoCorpusRepository

corpus_repo = BoCorpusRepository()
vocab = corpus_repo.vocabulary

cp = CorrectionProvider(
    score_candidates=None,
    vocabulary=vocab,
    confidence_threshold=0.0,
    corpus_repository=corpus_repo
)
# Hack in a dummy score_candidates that returns fixed scores for debugging
def dummy_score(sentence, word_start, word_end, candidates):
    # just dummy
    return {c: 0.1 for c in candidates}

cp._score_candidates = dummy_score
candidates = cp._find_candidates('ཤེས')

hybrid = {}
for c in candidates:
    dist = 1
    raw_score = 0.5 # dummy
    context_bonus = corpus_repo.get_context_score('བཀྲ་ཤེས་བདེ་ལེགས།', 4, 7, c)
    hybrid[c] = (0.5 * raw_score) + (0.3 * context_bonus) - (dist * 0.15)

out = {
    "hybrid_shis": hybrid.get("ཤིས"),
    "hybrid_bshes": hybrid.get("བཤེས")
}

with open('scratch/debug_hybrid2.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
