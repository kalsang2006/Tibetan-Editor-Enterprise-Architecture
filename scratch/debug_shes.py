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

candidates = cp._find_candidates('ཤེས')
out = {
    "candidates": candidates
}

with open('scratch/debug_shes.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
