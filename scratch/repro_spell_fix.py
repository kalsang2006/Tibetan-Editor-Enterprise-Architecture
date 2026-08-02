"""Reproduce the missing-tsheg spell-check behaviour at the engine level.

Run with:  .venv/Scripts/python scratch/repro_spell_fix.py
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

from teea.engine import TEEAEngine
from teea.nlp.snapshot import LanguageServerSnapshotBuilder

TEXTS = [
    "ང་ཚོས་སློབ་སྦྱངབྱེད།",   # missing tsheg after སྦྱང (user's case)
    "ང་ཚོས་སློབ་སྦྱང་བྱེད།",   # correct form
    "།།",                       # punctuation only
    "བཀྲ་ཤིས་བདེ་ལེགས།",       # well-formed
]


def main() -> None:
    for text in TEXTS:
        snap = LanguageServerSnapshotBuilder().analyze(text)
        empty = any(a.tree.is_empty for a in snap.analyses)
        node_info = [
            (a.tree.is_empty, [n.text for n in a.tree.nodes]) for a in snap.analyses
        ]
        print(f"TEXT={text!r}")
        print(f"  analyses is_empty/nodes: {node_info}")

    print("\n--- engine-level suggestions for the user's sentence ---")
    engine = TEEAEngine()
    for text in TEXTS[:2]:
        unified = engine.analyze(text)
        print(f"TEXT={text!r}")
        for s in unified.suggestions:
            if s.source in ("teea.spelling", "teea.grammar"):
                print(
                    f"  {s.source}: span=({s.span.char_start},{s.span.char_end}) "
                    f"repl={s.replacement!r} score={s.score} msg={s.message[:90]!r}"
                )


if __name__ == "__main__":
    main()
