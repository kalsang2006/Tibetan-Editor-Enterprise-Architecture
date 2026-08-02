"""Probe: which suggestion sources emit edits on the eval's clean BoCorpus sentences?"""
from __future__ import annotations

import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = Path(__file__).with_suffix(".txt")
_fh = open(OUT, "w", encoding="utf-8")


def log(*args: object) -> None:
    print(*args, file=_fh, flush=True)


import pandas as pd  # noqa: E402
from teea.engine import TEEAEngine  # noqa: E402

SEED = 42
MAX_CLEAN_SENTENCES = 150

parquet_path = ROOT / "Data/Corpus/BoCorpus/bo_corpus.parquet"
df = pd.read_parquet(parquet_path, columns=["text"])
texts = df["text"].dropna().tolist()
rng = random.Random(SEED)
sents: list[str] = []
for t in texts:
    for s in re.split(r"[།]+", str(t)):
        s = s.strip()
        if 8 <= len(s) <= 120 and "་" in s and re.search(r"[\u0f40-\u0fbc]", s):
            sents.append(s + "།")
rng.shuffle(sents)
clean = sents[:MAX_CLEAN_SENTENCES]
log(f"clean sentences sampled: {len(clean)}")

engine = TEEAEngine()
src_counter: Counter = Counter()
err_counter: Counter = Counter()
edit_examples: list[tuple[str, str, str]] = []
for idx, s in enumerate(clean):
    unified = engine.analyze(s)
    for sug in unified.suggestions:
        if sug.replacement:
            src_counter[sug.source] += 1
            err_counter[sug.error_type] += 1
            if len(edit_examples) < 15:
                edit_examples.append((s[:40], sug.source, sug.replacement[:16]))

log("\n=== replacement edits on clean sentences ===")
log(f"by source: {dict(src_counter)}")
log(f"by error_type: {dict(err_counter)}")
log("\nexamples:")
for text, src, repl in edit_examples:
    log(f"  [{src}] {repl!r}  in {text!r}")

_fh.close()
print(f"probe written to {OUT}", flush=True)
