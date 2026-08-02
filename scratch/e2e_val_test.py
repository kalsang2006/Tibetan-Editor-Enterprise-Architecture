import sys
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))

from teea.engine import TEEAEngine

engine = TEEAEngine()
text = "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱི། དག་གིས་པར་སྤྲོ་གསར་པ་སླབས། ང་ཚོས་ཡིག་ཆ་ཀློ་ཅིང་ཡི་གེ་བོང་བྱ། ང་རང་དགའ་སྤྲོ་ཆེན་པོ་ཡོད།"
result = engine.analyze(text)

print("=== TOTAL SUGGESTIONS ===")
print(len(result.suggestions))
print()
for i, s in enumerate(result.suggestions):
    rule_id = getattr(s, "rule_id", "N/A")
    confidence = getattr(s, "confidence", getattr(s, "score", "N/A"))
    print(f"[{i+1}]")
    print(f"Source      : {s.source}")
    print(f"Rule ID     : {rule_id}")
    print(f"Message     : {s.message}")
    print(f"Replacement : {s.replacement}")
    print(f"Confidence  : {confidence}")
    print(f"Span        : char_start={s.span.char_start}, char_end={s.span.char_end}")
    if s.span and text:
        matched_text = text[s.span.char_start:s.span.char_end]
        print(f"Matched Text: '{matched_text}'")
    print()
