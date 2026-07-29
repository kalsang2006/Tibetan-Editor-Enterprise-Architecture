import time
from teea.persistence import default_dictionary
from teea.plugins.builtin.correction import CorrectionProvider
from teea.ai.tibert_engine import TiBERTInferenceEngine
from teea.ai.models import ModelDescriptor, ExecutionContext, CapabilityKind, InferenceRequest

def run_benchmark():
    print("Loading dictionary...")
    dictionary = default_dictionary()
    
    print("Loading TiBERT engine...")
    engine = TiBERTInferenceEngine()
    descriptor = ModelDescriptor(name="tibert", version="1", provides=frozenset({CapabilityKind.SPELLING}))
    engine.load(descriptor, ExecutionContext())

    def score_fn(sentence, ws, we, cands):
        req = InferenceRequest(
            capability=CapabilityKind.SPELLING,
            inputs={"sentence": sentence, "word_start": ws, "word_end": we, "candidates": cands}
        )
        t0 = time.perf_counter()
        res = engine.infer(descriptor, req)
        t1 = time.perf_counter()
        print(f"  [Metric] TiBERT inference ({len(cands)} cands): {((t1-t0)*1000):.2f} ms")
        return res["scores"]

    provider = CorrectionProvider(
        score_candidates=score_fn,
        vocabulary=dictionary.vocabulary,
        confidence_threshold=0.0
    )

    word = "བཀྲ་ཤིམ་"
    sentence = "ང་བཀྲ་ཤིམ་ཟེར།"
    ws = 2
    we = 2 + len(word)

    print(f"\nBenchmarking correction for unknown word: {word}")
    
    # Measure candidate generation separately for metrics
    t0 = time.perf_counter()
    candidates = provider._find_candidates(word)
    t1 = time.perf_counter()
    print(f"  [Metric] Candidate generation: {((t1-t0)*1000):.2f} ms (found {len(candidates)})")

    # Measure total correction
    t_start = time.perf_counter()
    result = provider.correct(word, sentence, ws, we)
    t_end = time.perf_counter()
    
    print(f"  [Metric] Total correction latency: {((t_end-t_start)*1000):.2f} ms")
    print(f"  Result: {result}")

if __name__ == "__main__":
    run_benchmark()
