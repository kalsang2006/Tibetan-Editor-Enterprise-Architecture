"""Verification tests for both fixes:
1. Double tsheg fix (བོདག་ → བོད་ without creating བོད་་)
2. Malapropism override (ང་ཆོས་སྒོར་བོད་ཡིན → should suggest བདག)
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from teea.engine import TEEAEngine

engine = TEEAEngine()

print("=" * 60)
print("FIX 1: Double Tsheg Test")
print("=" * 60)
text1 = "དེ་རིང་ང་ཆོས་སྒོར་བོདག་ཡིནན།"
print(f"Input:  {text1!r}")
unified1 = engine.analyze(text1)
print(f"Suggestions: {len(unified1.suggestions)}")
has_double_tsheg = False
for s in unified1.suggestions:
    d = s.model_dump(mode="json")
    cs, ce = d["span"]["char_start"], d["span"]["char_end"]
    repl = d["replacement"]
    if repl:
        result = text1[:cs] + repl + text1[ce:]
        double = "་་" in result
        if double:
            has_double_tsheg = True
        status = "❌ DOUBLE TSHEG!" if double else "✅ OK"
        print(f"  [{cs}:{ce}] {text1[cs:ce]!r} => {repl!r}  →  {status}")
        print(f"    Result snippet: {result[max(0,cs-2):ce+5]!r}")

print(f"\nResult: {'❌ FAIL - double tsheg present' if has_double_tsheg else '✅ PASS - no double tsheg'}")

print()
print("=" * 60)
print("FIX 2: Malapropism Override Test")
print("=" * 60)
# Test with "བོད" after spelling correction (structural error fixed)
text2 = "ང་ཆོས་སྒོར་བོད་ཡིན།"
print(f"Input:  {text2!r}")
unified2 = engine.analyze(text2)
print(f"Suggestions: {len(unified2.suggestions)}")
found_bdag = False
for s in unified2.suggestions:
    d = s.model_dump(mode="json")
    cs, ce = d["span"]["char_start"], d["span"]["char_end"]
    repl = d["replacement"]
    src_word = text2[cs:ce]
    msg = d.get("message", "")[:100]
    print(f"  [{cs}:{ce}] {src_word!r} => {repl!r}")
    print(f"    msg: {msg}")
    if repl and "བདག" in repl:
        found_bdag = True

print(f"\nResult: {'✅ PASS - བདག suggested correctly' if found_bdag else '❌ FAIL - བདག not suggested'}")

print()
print("=" * 60)
print("FIX 2b: Malapropism with misspelled བོདག input")
print("=" * 60)
# This is what the user actually types: "ང་ཆོས་སྒོར་བོདག་ཡིན"
# After spell-fix བོདག → བོད, the grammar checker should then catch it
text3 = "ང་ཆོས་སྒོར་བོདག་ཡིན།"
print(f"Input:  {text3!r}")
unified3 = engine.analyze(text3)
print(f"Suggestions: {len(unified3.suggestions)}")
for s in unified3.suggestions:
    d = s.model_dump(mode="json")
    cs, ce = d["span"]["char_start"], d["span"]["char_end"]
    repl = d["replacement"]
    src_word = text3[cs:ce]
    msg = d.get("message", "")[:100]
    if repl:
        print(f"  [{cs}:{ce}] {src_word!r} => {repl!r}")
        print(f"    msg: {msg}")
