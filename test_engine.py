"""Quick engine test to inspect serialized suggestion shape."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")

from teea.engine import TEEAEngine

engine = TEEAEngine()
text = (
    "དེ་རིང་ང་ཆོས་སྒོར་བོདག་ཡིནན།\n"
    "ཁྱེད་རང་ཀ་དེ་ཤེས་གི་རེད།"
)
unified = engine.analyze(text)
print(f"Total suggestions: {len(unified.suggestions)}")
for s in unified.suggestions:
    d = s.model_dump(mode="json")
    src = d["source"]
    span = d["span"]
    repl = d["replacement"]
    priority = d["priority"]
    score = d["score"]
    msg = d.get("message", "")
    print(f"  source={src!r} char={span['char_start']}-{span['char_end']} repl={repl!r} prio={priority} score={score:.2f}")
    if msg:
        print(f"    msg: {msg}")

print()
print(f"Total patch operations: {len(unified.patch.operations)}")
for op in unified.patch.operations:
    d = op.model_dump(mode="json")
    span = d["span"]
    repl = d["replacement"]
    sources = d["sources"]
    orig = text[span["char_start"]:span["char_end"]]
    print(f"  chars[{span['char_start']}-{span['char_end']}] {orig!r} => {repl!r}  (sources: {sources})")
