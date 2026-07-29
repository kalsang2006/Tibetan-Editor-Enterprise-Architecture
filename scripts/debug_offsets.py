import sys
import os
import json
import torch

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath('src'))
from transformers import AutoTokenizer
from teea.ai.tibert_engine import TiBERTInferenceEngine
from teea.ai.models import ModelDescriptor, ExecutionContext, CapabilityKind, InferenceRequest

engine = TiBERTInferenceEngine()
descriptor = ModelDescriptor(name="tibert", version="1", provides=frozenset({CapabilityKind.SPELLING}))
engine.load(descriptor, ExecutionContext())

sentence = "ང་བཀྲ་ཤིམ་ཟེར།"
word_start = 6
word_end = 9
candidates = ["ཤམ", "ཤིས"]

def test_infer():
    req = InferenceRequest(
        capability=CapabilityKind.SPELLING,
        inputs={"sentence": sentence, "word_start": word_start, "word_end": word_end, "candidates": candidates}
    )
    
    # We will basically run the infer method but print exactly what is happening
    inputs = req.inputs
    modified_sentences = [sentence[:word_start] + c + sentence[word_end:] for c in candidates]
    
    encoding = engine._tokenizer(
        modified_sentences, add_special_tokens=True, return_tensors="pt", return_offsets_mapping=True, padding=True
    )
    input_ids = encoding["input_ids"]
    
    for i, candidate in enumerate(candidates):
        print(f"--- Candidate: {candidate} ---")
        offsets = encoding["offset_mapping"][i].tolist()
        cand_char_end = word_start + len(candidate)
        print(f"char range: {word_start} to {cand_char_end}")
        
        pos_list = []
        for pos, (start, end) in enumerate(offsets):
            print(f" pos {pos}: token {engine._tokenizer.decode([input_ids[i, pos]])} (id {input_ids[i, pos]}) span {start}-{end}")
            if start != end and start >= word_start and end <= cand_char_end:
                pos_list.append(pos)
        print(f"Matched pos_list: {pos_list}")

test_infer()
