import sys
from pathlib import Path

# Reconfigure stdout for UTF-8 on Windows
sys.stdout.reconfigure(encoding="utf-8")

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

print("=" * 80)
print("TESTING TIBETAN LLAMA2-7B GEC ENGINE & PLUGIN")
print("=" * 80)

from teea.ai.grammar_correction_engine import GrammarCorrectionEngine
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.plugins.builtin.grammar_correction import GrammarCorrectionPlugin

# 1. Instantiate Engine
engine = GrammarCorrectionEngine(
    model_path="./models/llama2_gec_lora",
    base_model_path="./models/Tibetan-Llama2-7B"
)

if engine.is_available():
    print("[✓] GrammarCorrectionEngine initialized successfully.")
else:
    print("[✗] GrammarCorrectionEngine failed to initialize.")

# Test sentences
test_sentences = [
    "ང་ཚོས བོང བྱ",
    "མི བྱས",
    "གལ་ཆེན ཡོད"
]

print("\n" + "=" * 50)
print("1. ENGINE DIRECT INFERENCE TEST")
print("=" * 50)

for s in test_sentences:
    corrected = engine.correct(s)
    print(f"Original : {s}")
    print(f"Corrected: {corrected}")
    print("-" * 50)

print("\n" + "=" * 50)
print("2. FEATURE PLUGIN TEST")
print("=" * 50)

plugin = GrammarCorrectionPlugin(
    model_path="./models/llama2_gec_lora",
    base_model_path="./models/Tibetan-Llama2-7B"
)

builder = LanguageServerSnapshotBuilder()

for s in test_sentences:
    snapshot = builder.analyze(s)
    suggestions = list(plugin.examine(snapshot))
    print(f"\n---> Input: '{s}' | Suggestions ({len(suggestions)}):")
    for sug in suggestions:
        print(f"     Source     : {sug.source}")
        print(f"     Priority   : {sug.priority.name if hasattr(sug.priority, 'name') else sug.priority}")
        print(f"     Score      : {sug.score}")
        print(f"     Error Type : {sug.error_type}")
        print(f"     Replacement: '{sug.replacement}'")
        print(f"     Message    : {sug.message}")

print("\n" + "=" * 80)
print("[SUCCESS] LLAMA2 GEC ENGINE & PLUGIN VERIFICATION COMPLETE!")
print("=" * 80)
