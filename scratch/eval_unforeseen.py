"""Evaluate the TEEA engine against an unforeseen, held-out test set.

Design
------
* Positives: ``Data/SyntheticErrors/synthetic_errors.json`` (50k records) and
  ``Data/TrainingData/grammar_correction_train.jsonl`` (46.9k pairs). A
  deterministic slice is held out *per run* by hashing the record id / incorrect
  text, so the evaluated examples were not part of any in-run tuning data.
* Negatives: real Tibetan sentences sampled from
  ``Data/Corpus/BoCorpus/bo_corpus.parquet`` (text the engine has never seen as
  error-bearing input).

Metrics
-------
* Record-level detection confusion matrix (TP/FP/FN/TN): did the engine emit an
  edit for a corrupted record, and stay silent on a clean one?
* Word-level precision/recall/F1: did the engine's patch fix the *actual* error
  words (matched replacements) without disturbing clean words?
* Sentence-level correction accuracy: does applying the engine's patch reproduce
  the gold corrected text exactly?
* Latency percentiles.

Word alignment uses difflib opcodes between the corrupted and (gold | predicted)
token sequences, so insertions/deletions do not corrupt positional matching.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from teea.engine import TEEAEngine  # noqa: E402

SEED = 42
MAX_POSITIVE_PER_TYPE = 25          # per error_type in synthetic_errors
MAX_GRAMMAR_PAIRS = 150             # held-out grammar pairs
MAX_CLEAN_SENTENCES = 150           # BoCorpus negatives
HOLDOUT_BUCKETS = 4                 # keep 1 of N buckets (bucket 0) as the test set


def held_out(key: str) -> bool:
    """Deterministic hold-out: True for records reserved as unseen test data."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % HOLDOUT_BUCKETS == 0


def tokenize(text: str) -> list[str]:
    """Split on tsheg, shad and whitespace; drop empties."""
    return [t for t in re.split(r"[་\s།]+", text) if t]


def diff_edits(corrupted: str, target: str) -> dict[float, str]:
    """Return the edits needed to turn `corrupted` into `target`.

    Keys are positions into the *corrupted* token list (the coordinate space
    shared by gold and predicted edits, since both are derived from the same
    corrupted text). Insertions use fractional positions (``i1 - 0.5``) so they
    are addressable without colliding with replacements at the same anchor.
    Deletions map to an empty-string replacement.

    Covering every opcode (replace/delete/insert) matters: Tibetan error types
    like TSHEG_DROP, WORD_DUPLICATION and PARTICLE_OMISSION surface as
    insert/delete edits after tokenization, and a metric that ignored them
    would undercount gold edits and crush measured recall.
    """
    src = tokenize(corrupted)
    tgt = tokenize(target)
    edits: dict[float, str] = {}
    sm = difflib.SequenceMatcher(a=src, b=tgt, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for k in range(i1, i2):
                edits[float(k)] = ""
        elif tag == "insert":
            for offset, token in enumerate(tgt[j1:j2]):
                # Fractional positions keep multiple insertions at one anchor
                # distinct: -0.5, -0.51, ... before token 0; i1-0.5 before i1.
                edits[(i1 or 0) - 0.5 - offset * 0.01] = token
        elif tag == "replace":
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                edits[float(i1 + k)] = tgt[j1 + k]
            for k in range(i1 + n, i2):
                edits[float(k)] = ""  # surplus source tokens are deletions
            for offset in range(n, j2 - j1):
                edits[float(i1 + n) - 0.5 - offset * 0.01] = tgt[j1 + offset]
    return edits


def main() -> None:
    print("Loading data...")
    # ---- Positives: synthetic_errors.json ---------------------------------
    syn_path = ROOT / "Data/SyntheticErrors/synthetic_errors.json"
    with open(syn_path, encoding="utf-8") as f:
        syn = json.load(f)
    records = syn.get("records", [])

    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if isinstance(r, dict) and r.get("corrupted_text") and r.get("original_text"):
            if r["corrupted_text"] != r["original_text"]:
                by_type[r.get("error_type", "UNKNOWN")].append(r)

    positives: list[dict] = []
    for err_type, items in by_type.items():
        bucket0 = [r for r in items if held_out(r.get("id") or r["corrupted_text"])]
        bucket0 = bucket0[:MAX_POSITIVE_PER_TYPE]
        for r in bucket0:
            positives.append(
                {
                    "text": r["corrupted_text"],
                    "gold": r["original_text"],
                    "kind": f"syn:{err_type}",
                }
            )

    # ---- Positives: grammar_correction_train (held out slice) -------------
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
                if len(grammar_held) >= MAX_GRAMMAR_PAIRS:
                    break
    for g in grammar_held:
        positives.append(g)

    # ---- Negatives: BoCorpus real sentences -------------------------------
    import pandas as pd  # noqa: PLC0415

    parquet_path = ROOT / "Data/Corpus/BoCorpus/bo_corpus.parquet"
    clean: list[dict] = []
    if parquet_path.exists():
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
        for s in sents[:MAX_CLEAN_SENTENCES]:
            clean.append({"text": s, "gold": s, "kind": "clean"})

    test_items = positives + clean
    print(f"Test set: {len(positives)} positives + {len(clean)} clean = {len(test_items)}")

    # ---- Run the engine ----------------------------------------------------
    print("Initialising TEEAEngine (may take a moment)...")
    engine = TEEAEngine()
    print("Engine ready.")

    results: list[dict] = []
    latencies: list[float] = []
    engine_faults = 0

    for item in test_items:
        t0 = time.perf_counter()
        try:
            unified = engine.analyze(item["text"])
        except Exception as exc:  # noqa: BLE001 - record and continue
            engine_faults += 1
            results.append(
                {
                    "text": item["text"],
                    "gold": item["gold"],
                    "kind": item["kind"],
                    "emitted_edit": False,
                    "corrected": item["text"],
                    "suggestions": [],
                    "fault": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

        edits = [s for s in unified.suggestions if s.is_edit and s.replacement]
        emitted_edit = len(edits) > 0
        corrected = unified.patch.apply() if unified.patch is not None else item["text"]

        results.append(
            {
                "text": item["text"],
                "gold": item["gold"],
                "kind": item["kind"],
                "emitted_edit": emitted_edit,
                "corrected": corrected,
                "suggestions": [
                    {
                        "span": [s.span.char_start, s.span.char_end],
                        "replacement": s.replacement,
                        "score": round(float(s.score), 4),
                        "source": s.source,
                    }
                    for s in edits
                ],
                "fault": None,
            }
        )

    # ---- Compute metrics ---------------------------------------------------
    detection_tp = detection_fp = detection_fn = detection_tn = 0
    w_tp = w_fp = w_fn = 0
    exact_match = 0
    per_kind: dict[str, Counter] = defaultdict(Counter)

    for r in results:
        gold_error = r["gold"] != r["text"]
        emitted = r["emitted_edit"] or r["corrected"] != r["text"]

        if gold_error:
            if emitted:
                detection_tp += 1
            else:
                detection_fn += 1
        else:
            if emitted:
                detection_fp += 1
            else:
                detection_tn += 1

        # word-level: standard edit-set intersection. A predicted edit is
        # correct iff it matches a gold edit at the same position with the same
        # replacement; unmatched gold edits are FN, unmatched predicted are FP.
        # (No double counting: a wrong change is FP for what it produced and the
        # corresponding gold edit, if any, is a separate FN.)
        gold_edits = diff_edits(r["text"], r["gold"])
        pred_edits = diff_edits(r["text"], r["corrected"])
        correct = sum(1 for pos, token in pred_edits.items() if gold_edits.get(pos) == token)
        w_tp += correct
        w_fp += len(pred_edits) - correct
        w_fn += len(gold_edits) - correct

        if r["corrected"] == r["gold"]:
            exact_match += 1

        k = r["kind"]
        per_kind[k]["total"] += 1
        per_kind[k]["emitted"] += 1 if emitted else 0
        per_kind[k]["gold_error"] += 1 if gold_error else 0
        per_kind[k]["exact"] += 1 if r["corrected"] == r["gold"] else 0

    total = len(results)

    def safe_div(n: int, d: int) -> float:
        return n / d if d else 0.0

    accuracy = (detection_tp + detection_tn) / total if total else 0.0
    precision = safe_div(detection_tp, detection_tp + detection_fp)
    recall = safe_div(detection_tp, detection_tp + detection_fn)
    f1 = safe_div(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
    specificity = safe_div(detection_tn, detection_tn + detection_fp)
    fpr = safe_div(detection_fp, detection_fp + detection_tn)
    fnr = safe_div(detection_fn, detection_fn + detection_tp)
    num_mcc = detection_tp * detection_tn - detection_fp * detection_fn
    den_mcc = (
        (detection_tp + detection_fp)
        * (detection_tp + detection_fn)
        * (detection_tn + detection_fp)
        * (detection_tn + detection_fn)
    ) ** 0.5
    mcc = safe_div(num_mcc, den_mcc) if den_mcc else 0.0

    w_precision = safe_div(w_tp, w_tp + w_fp)
    w_recall = safe_div(w_tp, w_tp + w_fn)
    w_f1 = safe_div(2 * w_precision * w_recall, w_precision + w_recall) if (w_precision + w_recall) else 0.0

    lat = sorted(latencies)

    def pct(p: float) -> float:
        if not lat:
            return 0.0
        return lat[min(int(p * (len(lat) - 1)), len(lat) - 1)]

    report = {
        "setup": {
            "seed": SEED,
            "holdout_buckets": HOLDOUT_BUCKETS,
            "positive_records": sum(1 for r in results if r["gold"] != r["text"]),
            "clean_records": sum(1 for r in results if r["gold"] == r["text"]),
            "total_records": total,
            "engine_faults": engine_faults,
        },
        "detection": {
            "tp": detection_tp, "fp": detection_fp, "fn": detection_fn, "tn": detection_tn,
            "accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1,
            "specificity": specificity, "fpr": fpr, "fnr": fnr, "mcc": mcc,
        },
        "word_level": {"tp": w_tp, "fp": w_fp, "fn": w_fn,
                       "precision": w_precision, "recall": w_recall, "f1": w_f1},
        "correction": {
            "exact_match": exact_match,
            "exact_match_rate": exact_match / total if total else 0.0,
        },
        "latency_ms": {
            "mean": sum(latencies) / len(latencies) if latencies else 0.0,
            "median": pct(0.5), "p95": pct(0.95), "p99": pct(0.99),
        },
        "per_kind": {
            k: dict(c) for k, c in sorted(per_kind.items())
        },
    }

    out_path = ROOT / "scratch/eval_unforeseen_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
