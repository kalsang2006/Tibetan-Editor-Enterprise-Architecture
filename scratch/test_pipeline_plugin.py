import sys
from pathlib import Path

# Reconfigure stdout for UTF-8 on Windows
sys.stdout.reconfigure(encoding="utf-8")

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

print("=" * 80)
print("1. TESTING GRAMMAR CORRECTION PLUGIN (STANDALONE FEATURE PLUGIN)")
print("=" * 80)

from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.plugins.builtin.grammar_correction import GrammarCorrectionPlugin

plugin = GrammarCorrectionPlugin(model_path="./models/tibert-grammar-correction-final")
print(f"[*] Plugin Identifier : {plugin.name}")

builder = LanguageServerSnapshotBuilder()

test_sentences = [
    "ང་ཚོས བོང བྱ",
    "མི བྱས",
    "གལ་ཆེན ཡོད"
]

for text in test_sentences:
    print(f"\n---> Input Text: '{text}'")
    snapshot = builder.analyze(text)
    suggestions = list(plugin.examine(snapshot))
    print(f"[*] Plugin returned {len(suggestions)} suggestion(s):")
    for s in suggestions:
        print(f"    - Source     : {s.source}")
        print(f"      Error Type : {s.error_type}")
        print(f"      Priority   : {s.priority.name if hasattr(s.priority, 'name') else s.priority}")
        print(f"      Score      : {s.score}")
        print(f"      Span       : (char {s.span.char_start} -> {s.span.char_end})")
        print(f"      Replacement: '{s.replacement}'")
        print(f"      Message    : {s.message}")

print("\n" + "=" * 80)
print("2. TESTING FULL TEEA PIPELINE (TEEAEngine + All 6 Plugins + Fusion Engine)")
print("=" * 80)

from teea.engine import TEEAEngine

print("[*] Initializing TEEA Core Engine...")
teea_engine = TEEAEngine()

health = teea_engine.health()
print(f"[*] Engine Health: {health}")

for text in test_sentences:
    print(f"\n" + "-" * 60)
    print(f"ANALYZING: '{text}'")
    print("-" * 60)
    unified = teea_engine.analyze(text)
    print(f"[*] Total Unified Suggestions: {len(unified.suggestions)} (Rejected: {len(unified.rejected)})")
    for i, s in enumerate(unified.suggestions, 1):
        original_slice = text[s.span.char_start:s.span.char_end] if text else ""
        print(f"  [{i}] Source: {s.source} | Priority: {s.priority.name} | Error: {s.error_type}")
        print(f"      Original Text : '{original_slice}' (Char Offset {s.span.char_start}-{s.span.char_end})")
        print(f"      Replacement   : '{s.replacement}'")
        print(f"      Score         : {s.score}")
        print(f"      Message       : {s.message}")

print("\n" + "=" * 80)
print("[SUCCESS] PIPELINE & PLUGIN TEST COMPLETED!")
print("=" * 80)
