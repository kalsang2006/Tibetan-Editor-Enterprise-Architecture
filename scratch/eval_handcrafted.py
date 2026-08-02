"""Hand-crafted spot-check evaluation for the TEEA engine.

Runs 20 hand-crafted Tibetan sentences (10 spelling errors, 10 grammar
errors) plus clean control sentences through the engine and reports
per-sentence results plus aggregate detection/correction metrics.

Word alignment uses the same difflib opcode logic as eval_unforeseen.py so
insertions/deletions (TSHEG_DROP, PARTICLE_OMISSION, WORD_DUPLICATION) are
handled without corrupting positional matching. Detection uses the same
definition as the benchmark: ``emitted = emitted_edit or corrected != text``.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console safety
except Exception:  # noqa: BLE001 - best effort
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from teea.engine import TEEAEngine  # noqa: E402


def tokenize(text: str) -> list[str]:
    """Split on tsheg, shad and whitespace; drop empties."""
    return [t for t in re.split(r"[་\s།]+", text) if t]


def diff_edits(corrupted: str, target: str) -> dict[float, str]:
    """Return the edits needed to turn `corrupted` into `target` (same as eval_unforeseen)."""
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
                edits[(i1 or 0) - 0.5 - offset * 0.01] = token
        elif tag == "replace":
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                edits[float(i1 + k)] = tgt[j1 + k]
            for k in range(i1 + n, i2):
                edits[float(k)] = ""
            for offset in range(n, j2 - j1):
                edits[float(i1 + n) - 0.5 - offset * 0.01] = tgt[j1 + offset]
    return edits


def safe_div(n: int, d: int) -> float:
    return n / d if d else 0.0


# ---------------------------------------------------------------------------
# Hand-crafted cases: (kind, error_type, corrupted, gold)
# ---------------------------------------------------------------------------
CASES: list[tuple[str, str, str, str]] = [
    # ---- Spelling (10 genuine errors) --------------------------------------
    ("spelling", "WORD_DUPLICATION",
     "ང་བོད་སྐད་སྦྱོང་སྦྱོང་བྱེད་ཀྱི་ཡོད།",
     "ང་བོད་སྐད་སྦྱོང་བྱེད་ཀྱི་ཡོད།"),
    ("spelling", "TSHEG_DROP",
     "ང་བོདསྐད་སྦྱོང་བྱེད་ཀྱི་ཡོད།",
     "ང་བོད་སྐད་སྦྱོང་བྱེད་ཀྱི་ཡོད།"),
    ("spelling", "SYLLABLE_SWAP",
     "ང་སྐད་བོད་སྦྱོང་བྱེད་ཀྱི་ཡོད།",
     "ང་བོད་སྐད་སྦྱོང་བྱེད་ཀྱི་ཡོད།"),
    ("spelling", "VOWEL_MUTATION",
     "བཀྲ་ཤིས་བདི་ལེགས།",
     "བཀྲ་ཤིས་བདེ་ལེགས།"),
    ("spelling", "CHARACTER_CONFUSION",
     "སློབ་སྦྱོབ་ནི་གལ་ཆེ་བ་ཞིག་ཡིན།",
     "སློབ་སྦྱོང་ནི་གལ་ཆེ་བ་ཞིག་ཡིན།"),
    ("spelling", "CASE_PARTICLE_SUBSTITUTION",
     "སློབ་སྦྱོང་ཀྱི་གལ་གནད་སྐོར་བཤད་པ།",
     "སློབ་སྦྱོང་གི་གལ་གནད་སྐོར་བཤད་པ།"),
    ("spelling", "PARTICLE_OMISSION",
     "སློབ་སྦྱོང་གལ་གནད་སྐོར་བཤད་པ།",
     "སློབ་སྦྱོང་གི་གལ་གནད་སྐོར་བཤད་པ།"),
    ("spelling", "CHARACTER_CONFUSION",
     "སེས་ཡོན་མེད་ན་མུན་ནག་ནང་དུ་འགྲོ་བ་དང་འདྲ།",
     "ཤེས་ཡོན་མེད་ན་མུན་ནག་ནང་དུ་འགྲོ་བ་དང་འདྲ།"),
    ("spelling", "VOWEL_MUTATION",
     "དི་རིང་ང་བོད་སྐད་སློབ་སྦྱོང་བྱེད་ཀྱི་ཡོད།",
     "དེ་རིང་ང་བོད་སྐད་སློབ་སྦྱོང་བྱེད་ཀྱི་ཡོད།"),
    ("spelling", "SYLLABLE_SWAP",
     "ང་ཚན་སློབ་ལ་དུས་ཚོད་ཆེན་པོ་སྦྱིན་དགོས།",
     "ང་སློབ་ཚན་ལ་དུས་ཚོད་ཆེན་པོ་སྦྱིན་དགོས།"),
    # ---- Grammar (10) ------------------------------------------------------
    ("grammar", "VERB_FORM",
     "བྱས་ནི",
     "བྱེད་པ"),
    ("grammar", "ADJECTIVE_NOMINALIZATION",
     "གལ་ཆེན",
     "གལ་ཆེན་པོ"),
    ("grammar", "VERB_NOMINALIZATION",
     "མེད",
     "མེད་པ"),
    ("grammar", "TENSE_MISMATCH",
     "ང་མི་བྱས།",
     "ང་མ་བྱས།"),
    ("grammar", "CONTEXTUAL_SEMANTIC",
     "དག་གིས་པར་སྤྲོ་གསར་པ་སླབས།",
     "དགེ་གིས་བརྡ་སྤྲོད་གསར་པ་བསླབས།"),
    ("grammar", "TENSE_MISMATCH",
     "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱི།",
     "དེ་རིང་ང་བོད་སྐད་སློབ་ཚན་ལ་ཕྱིན།"),
    ("grammar", "STRUCTURAL",
     "དགེ་གིས་བརྡ་སྤྲོད་སླབས།",
     "དགེ་གིས་བརྡ་སྤྲོད་བསླབས།"),
    ("grammar", "CONTEXTUAL_SEMANTIC",
     "ང་ཚོས་ཡིག་ཆ་ཀློ་ཅིང་ཡི་གེ་བོང་བྱ།",
     "ང་ཚོས་ཡིག་ཆ་ཀློག་ཅིང་ཡི་གེ་སྦྱོང་བྱས།"),
    ("grammar", "SPELLING_FALLBACK",
     "དུས་ཚོད་བཅང་པོ་མེད།",
     "དུས་ཚོད་ཆང་པོ་མེད།"),
    ("grammar", "PARTICLE_CASE",
     "སློབ་སྦྱོང་འབད་དགོས་པ་ཡིན།",
     "སློབ་སྦྱོང་ལ་འབད་དགོས་པ་ཡིན།"),
    # ---- Clean controls (for false-positive spot checks) ------------------
    ("clean", "NONE",
     "གནད་དོན་འདི་བཤད་པར་བྱའོ། འཇིག་རྟེན་གསོན་པོའི་དཔེ་དེབ་ཤེས་རིག་བཟང་པོ་འདི་ཡིས་ནུས་པ་གཏན་ཏན་ཐོན་ནོ།",
     "གནད་དོན་འདི་བཤད་པར་བྱའོ། འཇིག་རྟེན་གསོན་པོའི་དཔེ་དེབ་ཤེས་རིག་བཟང་པོ་འདི་ཡིས་ནུས་པ་གཏན་ཏན་ཐོན་ནོ།"),
    ("clean", "NONE",
     "སློབ་སྦྱོང་གི་གལ་གནད་སྐོར་བཤད་པ། དེང་དུས་ཀྱི་འཇིག་རྟེན་འདིར་མི་ཚེ་གསོན་པོར་གནས་པ་དང་མདུན་བསྐྱོད་བྱེད་ཆེད་སློབ་སྦྱོང་ནི་ཧ་ཅང་གལ་ཆེ་བ་ཞིག་ཡིན།",
     "སློབ་སྦྱོང་གི་གལ་གནད་སྐོར་བཤད་པ། དེང་དུས་ཀྱི་འཇིག་རྟེན་འདིར་མི་ཚེ་གསོན་པོར་གནས་པ་དང་མདུན་བསྐྱོད་བྱེད་ཆེད་སློབ་སྦྱོང་ནི་ཧ་ཅང་གལ་ཆེ་བ་ཞིག་ཡིན།"),
]


def main() -> None:
    print("Initialising TEEAEngine (may take a moment)...", flush=True)
    engine = TEEAEngine()
    print("Engine ready.", flush=True)

    results: list[dict] = []
    latencies: list[float] = []

    for kind, err_type, corrupted, gold in CASES:
        t0 = time.perf_counter()
        try:
            unified = engine.analyze(corrupted)
        except Exception as exc:  # noqa: BLE001 - record and continue
            results.append({
                "kind": kind, "error_type": err_type,
                "text": corrupted, "gold": gold,
                "emitted": False, "emitted_edit": False,
                "exact_match": False, "corrected": corrupted,
                "w_tp": 0, "w_fp": 0, "w_fn": 0,
                "suggestions": [], "fault": f"{type(exc).__name__}: {exc}",
            })
            continue
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(elapsed_ms)

        edits = [s for s in unified.suggestions if s.is_edit and s.replacement]
        emitted_edit = len(edits) > 0
        corrected = unified.patch.apply() if unified.patch is not None else corrupted
        emitted = emitted_edit or corrected != corrupted  # benchmark's definition

        # word-level
        gold_edits = diff_edits(corrupted, gold)
        pred_edits = diff_edits(corrupted, corrected)
        w_tp = sum(1 for pos, tok in pred_edits.items() if gold_edits.get(pos) == tok)
        w_fp = len(pred_edits) - w_tp
        w_fn = len(gold_edits) - w_tp

        results.append({
            "kind": kind, "error_type": err_type,
            "text": corrupted, "gold": gold,
            "emitted": emitted,
            "exact_match": corrected == gold,
            "corrected": corrected,
            "w_tp": w_tp, "w_fp": w_fp, "w_fn": w_fn,
            "suggestions": [
                {
                    "span": [s.span.char_start, s.span.char_end],
                    "replacement": s.replacement,
                    "score": round(float(s.score), 4),
                    "source": s.source,
                    "error_type": s.error_type,
                    "message": s.message,
                }
                for s in edits
            ],
            "fault": None,
        })

    # ---- Aggregate metrics (mirrors eval_unforeseen.py) ---------------------
    tp = fp = fn = tn = 0
    w_tp = w_fp = w_fn = 0
    exact = 0
    per_kind: dict[str, dict[str, int]] = {}

    for r in results:
        gold_error = r["gold"] != r["text"]
        emitted = r["emitted"]
        if gold_error:
            if emitted:
                tp += 1
            else:
                fn += 1
        else:
            if emitted:
                fp += 1
            else:
                tn += 1
        w_tp += r["w_tp"]
        w_fp += r["w_fp"]
        w_fn += r["w_fn"]
        exact += 1 if r["exact_match"] else 0
        k = per_kind.setdefault(r["kind"], {"total": 0, "emitted": 0, "gold_error": 0, "exact": 0})
        k["total"] += 1
        k["emitted"] += 1 if emitted else 0
        k["gold_error"] += 1 if gold_error else 0
        k["exact"] += 1 if r["exact_match"] else 0

    total = len(results)
    accuracy = (tp + tn) / total if total else 0.0
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
    specificity = safe_div(tn, tn + fp)
    fpr = safe_div(fp, fp + tn)
    fnr = safe_div(fn, fn + tp)
    num_mcc = tp * tn - fp * fn
    den_mcc = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
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
            "total_records": total,
            "error_records": sum(1 for r in results if r["gold"] != r["text"]),
            "clean_records": sum(1 for r in results if r["gold"] == r["text"]),
        },
        "detection": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1,
            "specificity": specificity, "fpr": fpr, "fnr": fnr, "mcc": mcc,
        },
        "word_level": {"tp": w_tp, "fp": w_fp, "fn": w_fn,
                       "precision": w_precision, "recall": w_recall, "f1": w_f1},
        "correction": {"exact_match": exact, "exact_match_rate": exact / total if total else 0.0},
        "latency_ms": {
            "mean": sum(latencies) / len(latencies) if latencies else 0.0,
            "median": pct(0.5), "p95": pct(0.95), "p99": pct(0.99),
        },
        "per_kind": per_kind,
        "results": results,
    }

    out_path = ROOT / "scratch/eval_handcrafted_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Saved {out_path}")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    print("--- per sentence ---")
    for r in results:
        flag = "FLAG" if r["emitted"] else "----"
        exact_m = "EXACT" if r["exact_match"] else "-----"
        print(f"[{flag}] [{exact_m}] {r['kind']:8s} {r['error_type']:24s} {r['text'][:34]} -> {r['corrected'][:34]}")


if __name__ == "__main__":
    main()
