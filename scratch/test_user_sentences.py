"""Live test of user's 3 Tibetan sentences against TEEA Engine & Plagiarism Engine."""

import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
sys.path.insert(0, str(Path.cwd()))

from teea.engine import TEEAEngine
from teea.plagiarism.engine import PlagiarismEngine
from teea.plagiarism.fingerprinting import hash_set, normalize_and_fingerprint
from teea.plagiarism.index import InMemoryFingerprintIndex
from teea.plagiarism.models import SourceDocument

print("=== 1. Testing NLP / Spelling / Grammar Suggestions ===")
engine = TEEAEngine()

test_cases = [
    ("ང་ལྷ་སེར་འདྲོ་ཡི་རེད།", "ང་ལྷ་སར་འགྲོ་གི་ཡིན།"),
    ("དེད་པེ་ཆ་ལེག་པོ་རེད།", "དེ་པེ་ཅ་ལེགས་པོ་ཡིན།"),
    ("ཁྱེད་རེང་གིས་ཅི་བྱེད་ཀི་འདུག", "ཁྱེད་རང་གིས་ཅི་བྱེད་ཀྱི་འདུག"),
]

for i, (input_text, expected) in enumerate(test_cases, 1):
    print(f"\n--- Sentence {i} ---")
    print(f"Input:    {input_text}")
    print(f"Expected: {expected}")
    result = engine.analyze(input_text)
    print(f"Suggestions Found: {len(result.suggestions)}")
    for s in result.suggestions:
        span_text = input_text[s.span.char_start:s.span.char_end]
        print(f"  [{s.priority.value.upper()}] source={s.source} span='{span_text}' ({s.span.char_start}:{s.span.char_end}) -> replacement='{s.replacement}' | msg='{s.message}'")

print("\n=== 2. Testing Plagiarism Detection ===")
index = InMemoryFingerprintIndex()
for i, (input_text, expected) in enumerate(test_cases, 1):
    norm_in, fps_in = normalize_and_fingerprint(input_text)
    doc_in = SourceDocument(document_id=f"corpus_input_{i}", source=input_text, fingerprints=hash_set(fps_in))
    index.add(doc_in)

    norm_exp, fps_exp = normalize_and_fingerprint(expected)
    doc_exp = SourceDocument(document_id=f"corpus_expected_{i}", source=expected, fingerprints=hash_set(fps_exp))
    index.add(doc_exp)

plag_engine = PlagiarismEngine(index=index)

for i, (input_text, expected) in enumerate(test_cases, 1):
    plag_res = plag_engine.detect(input_text, min_similarity=0.01)
    orig_score = max(0.0, round((1.0 - plag_res.max_similarity) * 100.0, 1))
    print(f"\nSentence {i} Plagiarism Check for: '{input_text}'")
    print(f"  Originality Score: {orig_score}% | Matches: {len(plag_res.matches)}")
    for m in plag_res.matches:
        print(f"    Match doc='{m.document_id}' similarity={m.similarity*100:.1f}% coverage={m.coverage*100:.1f}%")
