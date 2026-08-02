"""Probe which inputs produce an empty dependency tree."""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8")

from teea.nlp.snapshot import LanguageServerSnapshotBuilder

TEXTS = [
    "།།",
    "།",
    "་",
    "བཀྲ་ཤིས་བདེ་ལེགས།",
    "ང་ཚོས་སློབ་སྦྱངབྱེད།",
    "hello world",
    "123 456",
    "ང་ །",
    "ང་ཚོས་སློབ་སྦྱངབྱེད།\r",
    "ང་ཚོས་སློབ་སྦྱངབྱེད།\u2028",
]


def main() -> None:
    for text in TEXTS:
        try:
            snap = LanguageServerSnapshotBuilder().analyze(text)
            info = [
                (a.tree.is_empty, len(a.tree.nodes), [n.text for n in a.tree.nodes])
                for a in snap.analyses
            ]
            print(f"{text!r:45} -> {info}")
        except Exception as exc:  # noqa: BLE001
            print(f"{text!r:45} -> ERROR {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
