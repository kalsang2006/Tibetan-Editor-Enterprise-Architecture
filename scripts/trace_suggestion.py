import os
import sys
import logging
from unittest.mock import MagicMock

# Enable UTF-8 logging and stdout
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Ensure we can import from src
sys.path.insert(0, os.path.abspath('src'))

from teea.plugins.builtin.correction import CorrectionProvider
from teea.ai.tibert_engine import TiBERTInferenceEngine
from teea.persistence import default_dictionary
import torch

def trace_pipeline():
    print("--- PIPELINE TRACE ---")
    
    # 1. Setup
    print("1. Loading dictionary...")
    vocab = default_dictionary().vocabulary
    # Hack: Inject the target words if they are missing just for this trace
    vocab = vocab | frozenset(["བཀྲ་ཤིས་", "བཀྲ་ཤམ", "བཀྲ་ཤིམ"])
        
    print("2. Loading TiBERT engine...")
    from teea.ai.models import ModelDescriptor, ExecutionContext, CapabilityKind, InferenceRequest
    engine = TiBERTInferenceEngine()
    descriptor = ModelDescriptor(name="tibert", version="1", provides=frozenset({CapabilityKind.SPELLING}))
    engine.load(descriptor, ExecutionContext())
    
    # 3. Inputs
    sentence = "ང་བཀྲ་ཤིམ་ཟེར།"
    word = "ཤིམ"
    
    # We need to compute word_start and word_end for "ཤིམ" in "ང་བཀྲ་ཤིམ་ཟེར།"
    word_start = sentence.find(word)
    word_end = word_start + len(word)
    print(f"3. Input: sentence='{sentence}', word='{word}', bounds=({word_start}, {word_end})")
    
    # We will trace CorrectionProvider internals manually
    def score_fn(sent, ws, we, cands):
        req = InferenceRequest(
            capability=CapabilityKind.SPELLING,
            inputs={"sentence": sent, "word_start": ws, "word_end": we, "candidates": cands}
        )
        res = engine.infer(descriptor, req)
        return res["scores"]
        
    # --- CANDIDATE GENERATION ---
    print("\n--- STAGE: Candidate Generation ---")
    provider = CorrectionProvider(
        score_candidates=score_fn,
        vocabulary=vocab,
        max_edit_distance=2,
        max_candidates=10,
        confidence_threshold=0.0
    )
    
    candidates = provider._find_candidates(word)
    print(f"Candidates generated: {candidates}")
    
    # --- TiBERT SCORING ---
    print("\n--- STAGE: TiBERT Scoring ---")
    # Let's manually invoke the engine to see the raw mask predictions
    masked_sentence = sentence[:word_start] + engine._tokenizer.mask_token + sentence[word_end:]
    print(f"Masked sentence: {masked_sentence}")
    
    inputs = engine._tokenizer(masked_sentence, return_tensors="pt").to(engine._device)
    mask_token_index = torch.where(inputs["input_ids"] == engine._tokenizer.mask_token_id)[1]
    
    if len(mask_token_index) == 0:
        print("ERROR: Mask token not found in inputs!")
        return
        
    with torch.no_grad():
        outputs = engine._model(**inputs)
        logits = outputs.logits
        
    mask_token_logits = logits[0, mask_token_index[0], :].squeeze()
    print("\nRaw TiBERT Top 5 predictions for the mask:")
    top_5_tokens = torch.topk(mask_token_logits, 5, dim=0).indices.tolist()
    for token in top_5_tokens:
        print(f" - {engine._tokenizer.decode([token])}")
        
    print("\nScoring candidates via score_fn:")
    scores = score_fn(sentence, word_start, word_end, candidates)
    for c, score in scores.items():
        print(f" - {c}: {score:.6f}")
        
    print("\n--- FINAL OUTCOME ---")
    if not scores:
        print("No scores returned!")
        return
    best_word = max(scores, key=lambda k: scores[k])
    best_score = scores[best_word]
    print(f"Best: {best_word} (score: {best_score:.6f})")

if __name__ == "__main__":
    trace_pipeline()
