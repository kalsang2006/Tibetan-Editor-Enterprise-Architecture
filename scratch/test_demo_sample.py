import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from teea.engine import TEEAEngine

def test_sample():
    sys.stdout.reconfigure(encoding="utf-8")
    text = "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱི། དག་གིས་པར་སྤྲོ་གསར་པ་སླབས། ང་ཚོས་ཡིག་ཆ་ཀློ་ཅིང་ཡི་གེ་བོང་བྱ། ང་རང་དགའ་སྤྲོ་ཆེན་པོ་ཡོད།"
    engine = TEEAEngine()
    result = engine.analyze(text)
    items = result.suggestions
    print("=" * 80)
    print(f"[✓] TEEA Pipeline Test Successful! {len(items)} Suggestions Detected:")
    print("=" * 80)
    for i, s in enumerate(items, 1):
        span_text = text[s.span.char_start:s.span.char_end]
        print(f" {i:2d}. [{s.source:<12}] '{span_text}' -> '{s.replacement}' (priority: {s.priority})")
        print(f"     Message : {s.message}")
        print(f"     Offsets : chars [{s.span.char_start}:{s.span.char_end}] | bytes [{s.span.byte_start}:{s.span.byte_end}]")

if __name__ == "__main__":
    test_sample()
