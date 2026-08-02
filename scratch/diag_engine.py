"""Replicate the TEEAEngine path of the two failing tests.

The direct SpellCheckerPlugin path flags the structural errors correctly, so
this script checks what changes when the engine is used (it passes a corpus
repository, enabling the §3 context hook).
"""

from __future__ import annotations

import traceback

from teea.ai.engines import DummyInferenceEngine
from teea.engine import TEEAEngine

STRUCT_TEXT = "\u0f51\u0f7a\u0f0b\u0f62\u0f72\u0f44\u0f0b\u0f44\u0f0b\u0f56\u0f7c\u0f51\u0f42\u0f0b\u0f61\u0f72\u0f53\u0f53\u0f0d"
GRAMMAR_TEXT = "\u0f51\u0f7a\u0f0b\u0f62\u0f72\u0f44\u0f0b\u0f44\u0f0b\u0f46\u0f7c\u0f66\u0f0b\u0f66\u0f92\u0f7c\u0f62\u0f0b\u0f56\u0f7c\u0f51\u0f42\u0f0b\u0f61\u0f72\u0f53\u0f53\u0f0d"

print("=== TEEAEngine structural test ===")
try:
    engine = TEEAEngine(ai_engine=DummyInferenceEngine())
    res = engine.analyze(STRUCT_TEXT)
    print("suggestions:", len(res.suggestions))
    for s in res.suggestions:
        print("   ", s.source, s.error_type, repr(s.message[:90]))
    flagged = [s.message for s in res.suggestions if "teea.spelling" in s.source]
    print("teea.spelling flagged:", len(flagged))
except Exception:
    traceback.print_exc()

print()
print("=== corpus repo availability ===")
try:
    from teea.corpus.repository import BoCorpusRepository

    repo = BoCorpusRepository()
    print("is_available:", repo.is_available())
    if repo.is_available():
        print("vocab size:", len(repo.vocabulary))
        print("bigrams:", len(repo.bigrams), "trigrams:", len(repo.trigrams))
except Exception as exc:
    print("corpus error:", type(exc).__name__, exc)

print()
print("=== SpellCheckerPlugin with corpus repo (engine equivalent) ===")
try:
    from teea.plugins.builtin.spelling import SpellCheckerPlugin

    plugin = SpellCheckerPlugin(corpus_repository=repo if repo.is_available() else None)
    from teea.nlp.snapshot import LanguageServerSnapshotBuilder

    snap = LanguageServerSnapshotBuilder().analyze(STRUCT_TEXT)
    sugs = list(plugin.examine(snap))
    print("suggestions:", len(sugs))
    for s in sugs:
        print("   ", s.source, s.error_type, repr(s.message[:90]))
except Exception:
    traceback.print_exc()
