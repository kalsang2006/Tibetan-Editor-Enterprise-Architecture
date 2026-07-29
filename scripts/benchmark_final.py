import time
import os
import psutil
from teea.persistence import default_dictionary
from teea.plugins.builtin.correction import CorrectionProvider
from teea.ai.tibert_engine import TiBERTInferenceEngine
from teea.ai.models import ModelDescriptor, ExecutionContext, CapabilityKind, InferenceRequest

def print_mem():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024

def run_benchmark():
    mem_start = print_mem()
    print(f"Initial memory: {mem_start:.2f} MB")

    print("Loading dictionary...")
    t0 = time.perf_counter()
    dictionary = default_dictionary()
    t1 = time.perf_counter()
    print(f"Dictionary load time: {t1-t0:.2f} s")

    print("Loading TiBERT engine...")
    t0 = time.perf_counter()
    engine = TiBERTInferenceEngine()
    descriptor = ModelDescriptor(name="tibert", version="1", provides=frozenset({CapabilityKind.SPELLING}))
    engine.load(descriptor, ExecutionContext())
    t1 = time.perf_counter()
    mem_loaded = print_mem()
    print(f"TiBERT load time: {t1-t0:.2f} s")
    print(f"Memory after loading model: {mem_loaded:.2f} MB (Delta: {mem_loaded - mem_start:.2f} MB)")

    def score_fn(sentence, ws, we, cands):
        req = InferenceRequest(
            capability=CapabilityKind.SPELLING,
            inputs={"sentence": sentence, "word_start": ws, "word_end": we, "candidates": cands}
        )
        t0_inf = time.perf_counter()
        res = engine.infer(descriptor, req)
        t1_inf = time.perf_counter()
        print(f"  [Metric] TiBERT inference ({len(cands)} cands): {((t1_inf-t0_inf)*1000):.2f} ms")
        return res["scores"]

    provider = CorrectionProvider(
        score_candidates=score_fn,
        vocabulary=dictionary.vocabulary,
        confidence_threshold=0.0
    )

    examples = [
        ("བཀྲ་ཤིམ་", "ང་བཀྲ་ཤིམ་ཟེར།", 2),
        ("བདེ་ལེག", "ང་བདེ་ལེགཟེར།", 2),
        ("མངོན་སུམ", "ང་མངོན་སུམཟེར།", 2),
    ]

    for word, sentence, ws in examples:
        we = ws + len(word)
        print(f"\nBenchmarking correction for unknown word: {word}")
        
        t0_cand = time.perf_counter()
        candidates = provider._find_candidates(word)
        t1_cand = time.perf_counter()
        print(f"  [Metric] Candidate generation: {((t1_cand-t0_cand)*1000):.2f} ms (found {len(candidates)})")

        t_start = time.perf_counter()
        result = provider.correct(word, sentence, ws, we)
        t_end = time.perf_counter()
        
        print(f"  [Metric] Total correction latency: {((t_end-t_start)*1000):.2f} ms")
        print(f"  Result: {result}")

    mem_final = print_mem()
    print(f"\nFinal memory: {mem_final:.2f} MB")

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    run_benchmark()
