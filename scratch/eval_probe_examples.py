"""Extract concrete false-positive / false-negative examples from the benchmark test set.

Replicates eval_unforeseen.py's deterministic sampling (same seed, same holdout
buckets) so the examples shown are genuinely from the 475-record benchmark set.
Runs the engine on a single pass over a subsample of clean sentences (to find
false positives) and a single pass over a subsample of corrupted sentences (to
find both false negatives and detected positives in one pass), then dumps
text + suggestions for the qualitative report.

NOTE: this probe re-executes the engine (it does not reuse the benchmark's
aggregate JSON, which contains no per-record detail), so its runtime is not
comparable to the benchmark's latency figures.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from teea.engine import TEEAEngine  # noqa: E402

SEED = 42
HOLDOUT_BUCKETS = 4
N_CLEAN = 8            # probe clean sentences to inspect FP behaviour
N_MISSED = 6           # probe corrupted sentences to inspect FN behaviour
MAX_CLEAN_RUNS = 40    # hard cap on engine runs over clean items
MAX_POS_RUNS = 70      # hard cap on engine runs over corrupted items
OUT_PATH = ROOT / "scratch/eval_probe_examples.json"


def held_out(key: str) -> bool:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % HOLDOUT_BUCKETS == 0


def main() -> None:
    # --- Positives: synthetic_errors.json (bucket-0 holdout) -----------------
    syn = json.load(open(ROOT / "Data/SyntheticErrors/synthetic_errors.json", encoding="utf-8"))
    records = syn.get("records", [])
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if isinstance(r, dict) and r.get("corrupted_text") and r.get("original_text"):
            if r["corrupted_text"] != r["original_text"]:
                by_type[r.get("error_type", "UNKNOWN")].append(r)

    positives: list[dict] = []
    for err_type, items in by_type.items():
        bucket0 = [r for r in items if held_out(r.get("id") or r["corrupted_text"])][:25]
        for r in bucket0:
            positives.append({
                "text": r["corrupted_text"], "gold": r["original_text"],
                "kind": f"syn:{err_type}",
            })

    # --- Grammar pairs -------------------------------------------------------
    train_path = ROOT / "Data/TrainingData/grammar_correction_train.jsonl"
    grammar_held: list[dict] = []
    if train_path.exists():
        with open(train_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                pair = json.loads(line)
                inc, cor = pair.get("incorrect", ""), pair.get("correct", "")
                if inc and cor and inc != cor and held_out(inc):
                    grammar_held.append({"text": inc, "gold": cor, "kind": "grammar"})
                if len(grammar_held) >= 150:
                    break
    positives.extend(grammar_held)

    # --- Clean: BoCorpus -----------------------------------------------------
    import pandas as pd  # noqa: PLC0415

    df = pd.read_parquet(ROOT / "Data/Corpus/BoCorpus/bo_corpus.parquet", columns=["text"])
    texts = df["text"].dropna().tolist()
    rng = random.Random(SEED)
    sents: list[str] = []
    for t in texts:
        for s in re.split(r"[།]+", str(t)):
            s = s.strip()
            if 8 <= len(s) <= 120 and "་" in s and re.search(r"[\u0f40-\u0fbc]", s):
                sents.append(s + "།")
    rng.shuffle(sents)
    clean = [{"text": s, "gold": s, "kind": "clean"} for s in sents[:150]]

    print("Initialising TEEAEngine...", flush=True)
    engine = TEEAEngine()
    print("Engine ready.", flush=True)

    def run(item: dict) -> dict:
        try:
            unified = engine.analyze(item["text"])
        except Exception as exc:  # noqa: BLE001 - record and continue
            return {"text": item["text"], "gold": item["gold"], "kind": item["kind"],
                    "emitted": False, "corrected": item["text"], "suggestions": [],
                    "fault": f"{type(exc).__name__}: {exc}"}
        edits = [s for s in unified.suggestions if s.is_edit and s.replacement]
        corrected = unified.patch.apply() if unified.patch is not None else item["text"]
        emitted = len(edits) > 0 or corrected != item["text"]
        return {
            "text": item["text"], "gold": item["gold"], "kind": item["kind"],
            "emitted": emitted, "corrected": corrected,
            "suggestions": [
                {"span": [s.span.char_start, s.span.char_end],
                 "replacement": s.replacement,
                 "score": round(float(s.score), 4),
                 "source": s.source, "error_type": s.error_type,
                 "message": s.message}
                for s in edits
            ],
            "fault": None,
        }

    out: dict[str, list] = {"false_positives": [], "false_negatives": [], "detected_positives": []}

    # --- FP probe: clean sentences the engine flags --------------------------
    fp_runs = 0
    for item in clean:
        if fp_runs >= MAX_CLEAN_RUNS or len(out["false_positives"]) >= N_CLEAN:
            break
        fp_runs += 1
        r = run(item)
        if r["emitted"]:
            out["false_positives"].append(r)
            if len(out["false_positives"]) % 4 == 0:
                print(f"  FP probe: {len(out['false_positives'])}/{N_CLEAN} found after {fp_runs} runs", flush=True)
    print(f"FP probe done: {len(out['false_positives'])}/{N_CLEAN} after {fp_runs} runs", flush=True)

    # --- FN + detected probe: one pass over corrupted items -------------------
    pos_runs = 0
    for item in positives:
        need_fn = len(out["false_negatives"]) < N_MISSED
        need_det = len(out["detected_positives"]) < N_MISSED
        if pos_runs >= MAX_POS_RUNS or (not need_fn and not need_det):
            break
        pos_runs += 1
        r = run(item)
        if r["emitted"]:
            if need_det:
                out["detected_positives"].append(r)
        else:
            if need_fn:
                out["false_negatives"].append(r)
        if pos_runs % 10 == 0:
            print(f"  pos probe: {pos_runs} runs, FN={len(out['false_negatives'])}/{N_MISSED}, "
                  f"det={len(out['detected_positives'])}/{N_MISSED}", flush=True)
    print(f"Pos probe done: {pos_runs} runs", flush=True)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Saved {OUT_PATH} (FP={len(out['false_positives'])}, "
          f"FN={len(out['false_negatives'])}, detected={len(out['detected_positives'])})", flush=True)


if __name__ == "__main__":
    main()
