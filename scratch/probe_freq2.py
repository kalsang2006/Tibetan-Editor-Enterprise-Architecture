"""Probe frequencies for newly-observed false-positive tokens."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = Path(__file__).with_suffix(".txt")
_fh = open(OUT, "w", encoding="utf-8")


def log(*args: object) -> None:
    print(*args, file=_fh, flush=True)


from teea.corpus.repository import BoCorpusRepository  # noqa: E402

r = BoCorpusRepository()
vocab = r.vocabulary
for w in ["ང", "ང་", "བ", "གསོན", "གསོན་", "གསོལ", "གསོལ་", "སེས", "ཤེས", "སྦྱོབ", "སྦྱོང"]:
    log(f"  {w!r}: vocab={vocab.get(w, 0)} get_freq={r.get_syllable_frequency(w)}")
_fh.close()
print("done", flush=True)
