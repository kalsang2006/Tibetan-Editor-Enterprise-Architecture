import sys
import traceback
import time
from pathlib import Path

# Add src to pythonpath
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from teea.nlp.snapshot.builder import LanguageServerSnapshotBuilder
from teea.nlp.tokenization.tibert import default_tibert_loader, TokenizationSettings


def test_tibert_limits():
    print("\n--- Testing TiBERT Limits ---")
    settings = TokenizationSettings(model_id="CMLI-NLP/TiBERT")
    tokenizer = default_tibert_loader(settings)
    
    # Generate increasingly large token strings
    sizes = [100, 500, 512, 513, 1000, 5000, 10000]
    for size in sizes:
        text = "སློབ་ " * size
        try:
            res = tokenizer(text, add_special_tokens=True, truncation=False, max_length=512, return_offsets_mapping=False)
            print(f"Tokenization size {size}: SUCCESS (generated {len(res['input_ids'])} tokens)")
        except Exception as e:
            print(f"Tokenization size {size}: FAILED -> {type(e).__name__}: {e}")

def test_document_size_limits():
    print("\n--- Testing Pipeline Document Size Limits ---")
    builder = LanguageServerSnapshotBuilder()
    sizes = [1000, 10000, 100000, 500000] # chars
    for size in sizes:
        text = "བཀྲ་ཤིས་བདེ་ལེགས། " * (size // 18)
        start = time.time()
        try:
            builder.analyze(text)
            print(f"Doc size {len(text)}: SUCCESS in {time.time() - start:.2f}s")
        except Exception as e:
            print(f"Doc size {len(text)}: FAILED -> {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_tibert_limits()
    test_document_size_limits()
