"""One-pass semantic override tests — verify all 4 test cases from the spec."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from teea.engine import TEEAEngine

engine = TEEAEngine()

TSHEG = "\u0f0b"

cases = [
    # (description, input, expect_bdag, expect_no_suggestion)
    ("TC1 misspelled བོདག  + context",   "ང་ཆོས་སྒོར་བོདག་ཡིན།",  True,  False),
    ("TC2 correct   བོད   + context",   "ང་ཆོས་སྒོར་བོད་ཡིན།",   True,  False),
    ("TC3 3rd-person ཁོང  — no rule",  "ཁོང་ཆོས་སྒོར་བོདག་ཡིན།", False, True),
    ("TC4 missing locative — no rule", "ང་རྒྱ་ནག་བོདག་ཡིན།",     False, True),
]

all_pass = True
for desc, text, expect_bdag, expect_none in cases:
    unified = engine.analyze(text)
    semantic_sugg = [
        s for s in unified.suggestions
        if s.replacement and "བདག" in s.replacement
    ]
    double_tsheg = any(
        TSHEG * 2 in (text[:s.span.char_start] + s.replacement + text[s.span.char_end:])
        for s in unified.suggestions if s.replacement
    )

    got_bdag   = len(semantic_sugg) > 0
    got_none   = not any(s.replacement and s.source == "teea.grammar" for s in unified.suggestions
                         if s.replacement and "བདག" in s.replacement)

    ok_bdag    = (got_bdag == expect_bdag)
    ok_no_dt   = not double_tsheg
    ok_none    = (not expect_none) or (not got_bdag)   # if expect_none, must have got_bdag=False

    status = "✅" if (ok_bdag and ok_no_dt and ok_none) else "❌"
    if not (ok_bdag and ok_no_dt and ok_none):
        all_pass = False

    print(f"{status} {desc}")
    if semantic_sugg:
        s = semantic_sugg[0]
        orig = text[s.span.char_start:s.span.char_end]
        print(f"   {orig!r} → {s.replacement!r}  (score={s.score})")
    else:
        print(f"   (no བདག suggestion — {'expected' if expect_none else 'UNEXPECTED'})")
    if double_tsheg:
        print(f"   ❌ DOUBLE TSHEG DETECTED")
    print()

print("=" * 50)
print(f"{'✅ ALL PASS' if all_pass else '❌ SOME TESTS FAILED'}")
