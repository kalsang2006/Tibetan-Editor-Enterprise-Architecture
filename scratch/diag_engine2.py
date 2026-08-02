"""Replicate the TEEAEngine plugin wiring exactly and capture any plugin failure."""

from __future__ import annotations

import traceback

from teea.ai.engines import DummyInferenceEngine
from teea.engine import TEEAEngine

TEXT = "\u0f51\u0f7a\u0f0b\u0f62\u0f72\u0f44\u0f0b\u0f44\u0f0b\u0f56\u0f7c\u0f51\u0f42\u0f0b\u0f61\u0f72\u0f53\u0f53\u0f0d"

engine = TEEAEngine(ai_engine=DummyInferenceEngine())

print("=== plugin runtime outcomes ===")
snapshot = engine._builder.analyze(TEXT)
results = engine._plugin_runtime.dispatch(snapshot)
print("is_healthy:", results.is_healthy)
for outcome in results.outcomes:
    print(
        f"  plugin={outcome.plugin} succeeded={outcome.succeeded} "
        f"num_suggestions={len(outcome.suggestions)}"
    )
    if outcome.failure is not None:
        print("    FAILURE:", outcome.failure)
        tb = getattr(outcome.failure, "traceback", None)
        if tb:
            print("    TRACEBACK:\n", tb)

print()
print("=== direct examine of the exact engine spell_checker plugin ===")
spell = next(p for p in engine._plugins if p.name == "teea.spelling")
print("correction_provider type:", type(spell._correction_provider).__name__)
print("has corpus:", spell._corpus_repository is not None)
print("contextual_ranker:", spell._contextual_ranker is not None)
try:
    sugs = list(spell.examine(snapshot))
    print("suggestions:", len(sugs))
    for s in sugs:
        print("   ", s.source, s.error_type, repr(s.message[:90]))
except Exception:
    traceback.print_exc()
