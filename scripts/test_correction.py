import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath('src'))
from teea.plugins.builtin.correction import CorrectionProvider
from teea.persistence import default_dictionary
from teea.ai.models import CapabilityKind, InferenceRequest, ModelDescriptor, ExecutionContext
from teea.ai.tibert_engine import TiBERTInferenceEngine

engine = TiBERTInferenceEngine()
engine.load(ModelDescriptor(name="tibert", version="1", provides=frozenset({CapabilityKind.SPELLING})), ExecutionContext())

def _score_candidates(candidates, sentence, word_start, word_end):
    req = InferenceRequest(
        capability=CapabilityKind.SPELLING,
        inputs={"sentence": sentence, "word_start": word_start, "word_end": word_end, "candidates": candidates}
    )
    res = engine.infer(req)
    return res.outputs["scores"]

provider = CorrectionProvider(
    score_candidates=_score_candidates,
    vocabulary=default_dictionary().vocabulary,
    confidence_threshold=0.0,
)

sentence = "ང་བཀྲ་ཤིམ་ཟེར།"
word = "ཤིམ"

sugg = provider.correct(word=word, sentence=sentence, word_start=6, word_end=9)
print("Suggestion:", sugg)
