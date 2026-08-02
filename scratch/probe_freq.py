"""Probe corpus frequencies for the targeted error words + sample bigrams."""
from __future__ import annotations

import json
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
log("=== syllable frequencies ===")
for w in ["བདི", "བདེ", "དི", "དེ", "སེས", "ཤེས", "སྦྱོབ", "སྦྱོང", "བདུ", "བདོ", "དུ", "དོ", "གི", "ཀྱི", "གྱི", "ཡི", "འི"]:
    log(f"  {w}: {vocab.get(w, 0)}  (get_syllable_frequency={r.get_syllable_frequency(w)})")

big = r.bigrams
log("\n=== skad/slob bigram keys ===")
keys = sorted(k for k in big if k.startswith("སྐད ") or k.startswith("སློབ ") or " སྐད" in k or " སློབ" in k)
log(f"  matching keys: {len(keys)}")
for k in keys[:10]:
    log(f"  {k!r}: {big[k]}")

log("\n=== particle-omission target pairs ===")
for a, b in [("སྦྱོང", "གལ"), ("སྦྱོང", "གི"), ("གི", "གལ"), ("སྐད", "སློབ"), ("སྐད", "ཀྱི"), ("ཀྱི", "སློབ")]:
    hits = [k for k in big if k.split(" ")[0].rstrip("་") == a.rstrip("་") and k.split(" ")[-1].rstrip("་") == b.rstrip("་")]
    log(f"  ('{a}','{b}'): {hits[:3]}")

_fh.close()
print(f"probe written to {OUT}", flush=True)
