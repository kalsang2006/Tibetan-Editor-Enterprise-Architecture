"""Diagnose the failing structural-validation integration test.

Runs the SpellCheckerPlugin directly against the sentence used by
tests/test_structural_validator.py::test_spell_checker_integration_structural_validation
so we can see which nodes reach the plugin and whether structural errors fire.
"""

from __future__ import annotations

from teea.plugins.builtin.spelling import SpellCheckerPlugin
from teea.nlp.snapshot import LanguageServerSnapshotBuilder

TEXT = "\u0f51\u0f7a\u0f0b\u0f62\u0f72\u0f44\u0f0b\u0f44\u0f0b\u0f56\u0f7c\u0f51\u0f42\u0f0b\u0f61\u0f72\u0f53\u0f53\u0f0d"

print("text:", TEXT)
print("expected:", "དེ་རིང་ང་བོདག་ཡིནན།" if TEXT == "དེ་རིང་ང་བོདག་ཡིནན།" else "(differs)")

plugin = SpellCheckerPlugin()
builder = LanguageServerSnapshotBuilder()
snap = builder.analyze(TEXT)
print("num analyses:", len(snap.analyses))
for a in snap.analyses:
    print("  analysis text:", repr(a.text), "tree empty:", a.tree.is_empty)
    for n in a.tree.nodes:
        print("    node:", repr(n.text), "rel:", n.relation)

sugs = list(plugin.examine(snap))
print("suggestions:", len(sugs))
for s in sugs:
    print("   ", s.source, s.error_type, repr(s.message[:80]))
