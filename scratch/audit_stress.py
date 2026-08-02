import sys
from pathlib import Path

# Add src to pythonpath
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from teea.nlp.snapshot.builder import LanguageServerSnapshotBuilder
from teea.plugins.builtin.spelling import SpellCheckerPlugin

def stress_test_inputs():
    print("\n--- Extreme Input Stress Test ---")
    builder = LanguageServerSnapshotBuilder()
    speller = SpellCheckerPlugin()
    
    inputs = {
        "Empty String": "",
        "Whitespace Only": "    \t\n   ",
        "Emoji Only": "😊🚀🔥",
        "Mixed Scripts": "བཀྲ་ཤིས་བདེ་ལེགས hello world སློབ་སྦྱོང 123",
        "Invalid UTF-8 / Surrogate": "\ud83d",  # Python handles this as lone surrogate
        "Repeated characters": "བ" * 5000,
        "No syllables (just Tsheg)": "་" * 5000,
        "Binary Data String": bytes(range(256)).decode('latin1')
    }
    
    for name, text in inputs.items():
        try:
            snap = builder.analyze(text)
            # Try to run spellcheck on it
            sugs = list(speller.examine(snap))
            print(f"[{name}] -> SUCCESS (Generated {len(snap.sentences)} sentences, {len(sugs)} suggestions)")
        except Exception as e:
            print(f"[{name}] -> FAILED: {type(e).__name__} - {e}")

if __name__ == "__main__":
    stress_test_inputs()
