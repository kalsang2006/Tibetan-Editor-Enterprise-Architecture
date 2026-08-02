# TEEA Grammar & Spelling Engine — Data-Driven Evaluation Report

**Date:** 2026-08-01
**Engine state:** current working tree (uncommitted changes present), TiBERT loaded (`TiBERT/model.safetensors`, vocab 29,965), `TEEA_ENABLE_LLM_GEC=1` set.
**Environment:** Python 3.11.9 · pytest 9.1.1 · torch 2.13.0+cpu (no CUDA) · Windows.

> **Important context — AI grammar correction (GEC) is NOT active.** `models/llama2_gec_lora` and `models/Tibetan-Llama2-7B` do not exist on disk, so the `GrammarCorrectionPlugin` self-disables at init (`grammar_correction_plugin_disabled_model_not_ready`). Setting `TEEA_ENABLE_LLM_GEC=1` therefore had **no effect** on results. The engine that was actually evaluated is: spelling checker (7-stage) + rule-based grammar checker + contextual engine + TiBERT as spelling candidate scorer. TiBERT *is* loaded and active for candidate scoring.

---

## 1. Executive Summary

| Dimension | Verdict |
|---|---|
| **Detection (flagging errors)** | High recall (84.9%) but **catastrophically low specificity (15.3%)** — flags 127/150 (85%) of clean BoCorpus sentences. **MCC = 0.003**, i.e. effectively no discriminative power. |
| **Correction (fixing errors)** | **Broken.** Word-level precision **0.5%**, recall **1.9%**, F1 **0.8%**. Exact-match on error sentences **0%** (23 "exact" records are all untouched clean sentences). Corrections actively damage valid text (`ང`→`ངན`, `པ`→`པ༴`, `ཤེས`→`ཤེ`). |
| **Latency** | Mean **2.69 s**, median 1.07 s, **P95 8.6 s**, **P99 34.3 s** per sentence on CPU. Not usable for interactive editing. |
| **Test suite** | 2,373 tests collected (2,364 runnable + 9 integration deselected). Clean full run: **2,364 passed, 0 failed**. One earlier run showed 3 order-dependent failures + 1 stale test API (details in §2). |
| **Root cause of FP explosion** | The **Stage-4B context-detection hook** (`teea.spelling`, `CONTEXT` error type) fires on known words whenever the corpus ranker deems the context "implausible" (`suspicious_gap=2.5`), and attaches a low-confidence replacement (score 0.736) to ~every known word in real sentences. |

**Bottom line:** the current engine cannot be shipped or used for automatic correction in its present state. Detection is real but unusable because of false positives; correction is destructive. The most urgent fixes are (1) the context-detection hook thresholds/behavior, (2) guarding replacements against garbage edits, and (3) the structural-validator over-corrections. See §9.

---

## 2. Full Python Backend Test Suite (`pytest tests/`)

Target (per request): 2,299/2,299. The suite has since grown to **2,373 collected** (2,364 selected + 9 deselected integration tests).

### Run results

| Run | Result | Notes |
|---|---|---|
| Full run #1 | **3 failed, 2,361 passed**, 9 deselected (233.8 s) | Failures: `test_spelling_context.py::test_known_word_in_implausible_context_is_flagged`, `test_contextual_engine.py::test_clean_essay_zero_false_positives`, `test_contextual_engine.py::test_essay_zero_false_positives` |
| Full run #2 | **2,364 passed, 0 failed**, 9 deselected (137.2 s) | Clean run — confirms the failures are **order-dependent / flaky** |

### Analysis of the three transient failures

1. **`test_known_word_in_implausible_context_is_flagged`** — stale test API. The test constructs `SpellCheckerConfig(enable_context_check=True)`, but the config field is now named `enable_context_detection` → `TypeError: unexpected keyword argument`. Reproducible when the test file runs in isolation; masked in run #2 by execution order. Fix: update the test to use the current config API.
2. **`test_clean_essay_zero_false_positives`** and **`test_essay_zero_false_positives`** — these assert **zero false-positive edits on clean Tibetan essays**. They fail when the engine's context hook fires on the clean text (consistent with the benchmark's 127/150 clean FPs), and pass when execution order leaves the plugin in a quieter state. **They encode the exact regression the benchmark measures.**

**Conclusion:** in a clean run the suite is green (2,364/2,364), but there is (a) one stale test API and (b) genuine order-dependence, which should be fixed by making the context hook deterministic and by updating the stale test. The two FP tests are currently catching a real quality regression, not a test bug.

---

## 3. Benchmark: `scratch/eval_unforeseen.py` (current engine)

Command: `set PYTHONPATH=src && TEEA_ENABLE_LLM_GEC=1 python scratch/eval_unforeseen.py`

### 3.1 Setup

| Setting | Value |
|---|---|
| Seed / holdout buckets | 42 / 4 (1 in 4 records held out per run) |
| Positive records (error-bearing) | 325 (150 grammar pairs + 25 each × 7 synthetic error types) |
| Clean records (BoCorpus negatives) | 150 |
| **Total records** | **475** |
| Engine faults | **0** |

### 3.2 Detection metrics (record-level)

Confusion matrix:

| | Predicted error | Predicted clean |
|---|---|---|
| **Actual error** | TP = **276** | FN = **49** |
| **Actual clean** | FP = **127** | TN = **23** |

| Metric | Value | Interpretation |
|---|---|---|
| **Accuracy** | 0.6295 | (TP+TN)/475 — dragged down by FP flood |
| **Precision** | 0.6849 | 68% of flags are real errors |
| **Recall** | 0.8492 | 85% of real errors are flagged |
| **F1** | 0.7582 | harmonic mean |
| **Specificity** | 0.1533 | **only 15% of clean sentences left untouched** |
| **False Positive Rate** | 0.8467 | 85% of clean sentences flagged |
| **False Negative Rate** | 0.1508 | 15% of errors missed |
| **MCC** | **0.0033** | ≈ no correlation between prediction and truth |

**Per-kind detection rates** (emitted / total, with gold-error count):

| Error type | Detected | Rate | vs. prior run |
|---|---|---|---|
| `WORD_DUPLICATION` | 24/25 | 96.0% | 92% |
| `VOWEL_MUTATION` | 24/25 | 96.0% | **12%** |
| `TSHEG_DROP` | 23/25 | 92.0% | 76% |
| `CASE_PARTICLE_SUBSTITUTION` | 23/25 | 92.0% | 48% |
| `PARTICLE_OMISSION` | 21/25 | 84.0% | **8%** |
| `CHARACTER_CONFUSION` | 19/25 | 76.0% | 20% |
| `SYLLABLE_SWAP` | 18/25 | 72.0% | 64% |
| `grammar` (general) | 124/150 | 82.7% | 41.3% |
| `clean` (should be 0!) | **127/150** | **84.7% flagged** | 6% |

> Detection per-type has improved enormously versus the prior cached run — but the clean rate exploding from 6% → 84.7% means the engine now **flags almost everything**, which is why MCC ≈ 0.

### 3.3 Correction metrics (word-level)

| Metric | Value |
|---|---|
| Correct edits (TP) | 8 |
| Incorrect edits (FP) | 1,655 |
| Missed gold edits (FN) | 424 |
| **Word-level precision** | **0.0048** (0.5%) |
| **Word-level recall** | **0.0185** (1.9%) |
| **Word-level F1** | **0.0076** (0.8%) |
| **Exact-match rate** (sentence reproduced exactly) | **0.0484** (23/475) |
| Over-correction rate (= 1 − w-precision) | **99.5%** of proposed edits are wrong |
| Missed-correction rate (= 1 − w-recall) | **98.1%** of gold edits are not correctly applied |

> All 23 "exact matches" are untouched *clean* sentences (i.e. the engine stayed silent). **Zero error sentences were corrected exactly** — of the 276 flagged error records, all 276 produced an incorrect or incomplete patch. The engine proposes 1,663 word-level edits in total (~4.1 per flagged record; ~6.0 per true-positive record) and almost all are wrong.

### 3.4 Latency

| Metric | Value (ms) |
|---|---|
| Mean | 2,686 |
| Median | 1,067 |
| P95 | 8,650 |
| P99 | 34,254 |

Mean is ~4.7× the prior cached run (576 ms) — consistent with TiBERT candidate scoring on CPU now being exercised for every unknown word.

---

## 4. Hand-Crafted Spot Check (20 sentences: 10 spelling, 10 grammar)

Script: `scratch/eval_handcrafted.py` (saved to `scratch/eval_handcrafted_results.json`). 20 hand-crafted error sentences + 2 known-clean control essays.

### 4.1 Aggregate

| Metric | Value |
|---|---|
| Detection TP/FP/FN/TN | 17 / 2 / 3 / 0 |
| Accuracy / Precision / Recall / F1 | 0.773 / 0.895 / 0.850 / 0.872 |
| Specificity / FPR / FNR | 0.0 / 1.0 / 0.15 |
| MCC | −0.126 |
| Word-level precision / recall / F1 | 0.022 / 0.069 / 0.034 |
| **Exact match** | **0 / 22** |
| Mean / median / P95 / P99 latency (ms) | 2,297 / 1,393 / 3,370 / 10,050 |

### 4.2 Per-case outcome

| # | Type | Flagged? | Gold fix | Engine output (corrected) | Verdict |
|---|---|---|---|---|---|
| S1 | WORD_DUPLICATION | ✅ | `སྦྱོང་སྦྱོང་`→`སྦྱོང་` | `ངན་བོད་སད་སྦྱོར་...` | ❌ destructive |
| S2 | TSHEG_DROP | ✅ | `བོདསྐད`→`བོད་སྐད` | `ངན་བོད་སྐད་...` | ⚠️ fixed the tsheg, then broke `ང` |
| S3 | SYLLABLE_SWAP | ✅ | swap back | `ངན་སད་བཅད་...` | ❌ destructive |
| S4 | VOWEL_MUTATION | ✅ | `བདི`→`བདེ` | `བདི་ལེ་གས` | ❌ wrong edit |
| S5 | CHARACTER_CONFUSION | ✅ | `སྦྱོབ`→`སྦྱོང` | `སླེབ་སྦྱོབ་...` | ❌ breaks `སློབ` |
| S6 | CASE_PARTICLE | ✅ | `ཀྱི`→`གི` | `སླེབ་སྦྱོར་གི་གང་གན་སྐར་...` | ⚠️ correct particle fix + 6 wrong edits |
| S7 | PARTICLE_OMISSION | ✅ | insert `གི` | `སླེབ་སྦྱོར་གང་གན་སྐར་...` | ❌ missed insertion, broke 5 words |
| S8 | CHARACTER_CONFUSION | ✅ | `སེས`→`ཤེས` | `...འགོ་བག་...` | ❌ didn't fix `སེས`, broke `འགྲོ་བ` |
| S9 | VOWEL_MUTATION | ✅ | `དི`→`དེ` | `དང་རང་ང༽་བོད་སད་སླེབ་...` | ❌ destructive |
| S10 | SYLLABLE_SWAP | ✅ | `ཚན་སློབ`→`སློབ་ཚན` | `ངན་ཚང་སློ་...དགས` | ❌ destructive |
| G1 | VERB_FORM (`བྱས་ནི`→`བྱེད་པ`) | ❌ | — | untouched | ❌ FN |
| G2 | ADJECTIVE NOMINALIZATION | ❌ | — | untouched | ❌ FN |
| G3 | VERB NOMINALIZATION | ❌ | — | untouched | ❌ FN |
| G4 | TENSE_MISMATCH (`མི་བྱས`→`མ་བྱས`) | ✅ | — | `ང་མི་བཅས།` | ❌ wrong replacement |
| G5 | CONTEXTUAL_SEMANTIC | ✅ | 4 fixes | 1 punctuation edit only | ❌ incomplete |
| G6 | TENSE_MISMATCH (`ཕྱི`→`ཕྱིན`) | ✅ | — | `ངག་བོད་སད་སླེབ་...` | ❌ destructive |
| G7 | STRUCTURAL (`སླབས`→`བསླབས`) | ✅ | — | `དག་ཡིས་བརྡ་...` | ❌ wrong edit |
| G8 | CONTEXTUAL_SEMANTIC | ✅ | 3 fixes | `ཡིག་ཆད་ཀློ་ཅི་...` | ❌ destructive |
| G9 | SPELLING_FALLBACK (`བཅང་པོ`→`ཆང་པོ`) | ✅ | — | `བཅང་པ` | ❌ wrong edit |
| G10 | PARTICLE_CASE | ✅ | insert `ལ` | `སླེབ་སྦྱང་འཆད་...` | ❌ destructive |
| C1 | clean control | ✅ (FP) | — | 16 suggestions, mangles text | ❌ FP |
| C2 | clean control | ✅ (FP) | — | 15 suggestions, mangles text | ❌ FP |

**Result: 0/20 exact fixes; 3/20 grammar errors not flagged at all; every flagged sentence received at least one wrong edit.** The engine reliably *detects* that something is wrong but cannot produce a safe replacement.

---

## 5. Qualitative Analysis

### 5.1 Concrete false positives (clean BoCorpus sentences flagged)

From `scratch/eval_probe_examples.json` (probe of the same deterministic benchmark sample):

| Clean input | Engine "correction" | Bad suggestions |
|---|---|---|
| `མཚན་མོའི་མུན་ནག་སྤྲིན་རུམ་ནས།` | `མཚན་མའི་མུན་ནག་སྤྲིང་རུམ་ནས།` | `མོ`→`མ`, `སྤྲིན`→`སྤྲིང` |
| `མ་བརྐོས་པ་དང་།` | `མང་བརྐུས་པ༴་དང་།` | `མ`→`མང`, `པ`→`པ༴` (injects punctuation!) |
| `ཞེས་སོགས་མཐའ་ཡས་པར་གསུངས་པས་འདིར་མཚོན་ཙམ་མོ།` | mangles 7 tokens | `སོགས`→`སོ་གས`, `མཚོན`→`མཚན`, `ཙམ`→`ཙག`, … |
| `ཞེས་སྦྱིན་པ་བཏང་བར་མཛད་དོ།` | `ཞེ་སྦྱིན་པ༴་བཏང་བར་མཛད་དོ།` | `ཞེས`→`ཞེ`, `པ`→`པ༴` |
| `ཡེ་ཤེས་ལྔ་ལ་མཉམ་པའི་ཚུལ་གྱིས་དེ་འཇུག་གོ།` | `ཡེ་ཤིས་...པ)འི་...དག་འཇུག་ག།` | `ཤེས`→`ཤིས`, `པ`→`པ)`, `དེ`→`དག`, `གོ`→`ག` |

All of these are `CONTEXT` suggestions from `teea.spelling` with a flat **score 0.736** — the Stage-4B hook firing on perfectly valid sentences.

### 5.2 Concrete false negative (missed error)

| Input | Gold | Engine |
|---|---|---|
| `བདེན་པར་ཉོན་ལ་རང་རང་གནས་སུ་དོངས།` | `...དེངས།` (VOWEL_MUTATION) | untouched, no suggestions |

Also missed: `བྱས་ནི`→`བྱེད་པ`, `གལ་ཆེན`→`གལ་ཆེན་པོ`, `མེད`→`མེད་པ` (verb/adjective nominalization rules in §4) — short 1–2 token inputs with no corpus context never trigger the context hook, and the morphological rules did not fire.

### 5.3 Correction quality assessment

- **Not safe.** Suggestions routinely corrupt valid words: `ང`→`ངན`, `སློབ`→`སླེབ`, `གནད`→`གན`, `ཤེས`→`ཤེ/ཤིས`, and **inject punctuation glyphs** (`པ`→`པ༴`, `ང`→`ང༽`, `བ`→`བ༽`). Auto-applying these would destroy user documents.
- **Some fixes are genuinely correct** (the genitive rule `སྦྱོང`+`ཀྱི`→`གི` in S6; the tsheg-restoration `བོདསྐད`→`བོད་སྐད` in S2) — but they are buried under 5–7 wrong edits per sentence.
- **Plausibility:** the candidate pool is wrong-headed rather than merely inexact — e.g. `མཚོན`→`མཚན` is not a plausible typo correction; it is a dictionary-adjacency artifact.

---

## 6. Root-Cause Analysis

1. **Context-detection hook (Stage-4B) is the FP machine.** `_context_suggestions()` in `src/teea/plugins/builtin/spelling.py` flags *any dictionary-known word* whose corpus context the `ContextualRanker` judges suspicious (`context_suspicious_gap=2.5`), and attaches a replacement whenever the correction provider returns confidence ≥ 0.6 (which the provider does for almost any word). With `confidence_threshold=0.0` wired in `engine.py`'s `CorrectionProvider`, essentially every known word gets a candidate → every sentence gets flagged → 85% clean FP rate and the destructive edits above.
2. **Correction quality is dominated by this same hook + structural validator.** The structural rules (`DOUBLE_VOWEL`, `INVALID_POST_SUFFIX`) produce edits like `མཛོདསྒོ`→`མཛོདསྒ་` that are orthography-fix attempts but wrong in context. The 1,655 word-level FPs overwhelm the 8 correct edits.
3. **Grammar GEC path is dead.** The Llama2/TiBERT-GEC model files are absent, so `TEEA_ENABLE_LLM_GEC=1` changes nothing. Any plan relying on AI grammar correction is currently running on the rule-based `GrammarCheckerPlugin` + contextual engine only.
4. **Latency.** TiBERT candidate scoring runs per unknown word on CPU; sentences with many unknown tokens hit seconds-to-tens-of-seconds (P99 34 s).

---

## 7. Raw Benchmark JSON (current run)

Saved to `scratch/eval_unforeseen_results.json` (previous run backed up to `scratch/eval_unforeseen_results_BEFORE.json`). Full content:

```json
{
  "setup": {
    "seed": 42,
    "holdout_buckets": 4,
    "positive_records": 325,
    "clean_records": 150,
    "total_records": 475,
    "engine_faults": 0
  },
  "detection": {
    "tp": 276, "fp": 127, "fn": 49, "tn": 23,
    "accuracy": 0.6294736842105263,
    "precision": 0.684863523573201,
    "recall": 0.8492307692307692,
    "f1": 0.7582417582417583,
    "specificity": 0.15333333333333332,
    "fpr": 0.8466666666666667,
    "fnr": 0.15076923076923077,
    "mcc": 0.0033235631241359783
  },
  "word_level": {
    "tp": 8, "fp": 1655, "fn": 424,
    "precision": 0.004810583283223091,
    "recall": 0.018518518518518517,
    "f1": 0.0076372315035799524
  },
  "correction": {
    "exact_match": 23,
    "exact_match_rate": 0.04842105263157895
  },
  "latency_ms": {
    "mean": 2686.3134210526723,
    "median": 1067.2015000018291,
    "p95": 8649.612299999717,
    "p99": 34254.18940000236
  },
  "per_kind": {
    "clean": {"total": 150, "emitted": 127, "gold_error": 0, "exact": 23},
    "grammar": {"total": 150, "emitted": 124, "gold_error": 150, "exact": 0},
    "syn:CASE_PARTICLE_SUBSTITUTION": {"total": 25, "emitted": 23, "gold_error": 25, "exact": 0},
    "syn:CHARACTER_CONFUSION": {"total": 25, "emitted": 19, "gold_error": 25, "exact": 0},
    "syn:PARTICLE_OMISSION": {"total": 25, "emitted": 21, "gold_error": 25, "exact": 0},
    "syn:SYLLABLE_SWAP": {"total": 25, "emitted": 18, "gold_error": 25, "exact": 0},
    "syn:TSHEG_DROP": {"total": 25, "emitted": 23, "gold_error": 25, "exact": 0},
    "syn:VOWEL_MUTATION": {"total": 25, "emitted": 24, "gold_error": 25, "exact": 0},
    "syn:WORD_DUPLICATION": {"total": 25, "emitted": 24, "gold_error": 25, "exact": 0}
  }
}
```

Supporting artifacts:
- `scratch/eval_handcrafted_results.json` — 22-record hand-crafted run (per-sentence detail).
- `scratch/eval_probe_examples.json` — FP/FN/detected examples with full suggestions.
- `scratch/eval_unforeseen_results_BEFORE.json` — prior cached run for comparison.

---

## 8. Strengths & Weaknesses

### Strengths
- **Detection recall per type is strong**: WORD_DUPLICATION 96%, VOWEL_MUTATION 96%, TSHEG_DROP 92%, grammar 83%. The pipelines *find* the errors.
- **Zero engine faults** across 475 + 22 + probe sentences — the pipeline is robust to bad input.
- **Some rule-based fixes are exact** (genitive particle agreement, tsheg restoration).
- **Test suite is green on a clean run** (2,364/2,364) and covers the FP regression explicitly — the tests are doing their job of catching this.
- Fully deterministic benchmark sampling (seeded holdout) makes before/after comparisons trustworthy.

### Weaknesses
- **Specificity is broken (15.3%)** — unusable false-positive rate; MCC 0.003.
- **Correction is destructive** — word-level precision 0.5%, exact-match 0% on errors, punctuation-injection edits.
- **No true AI grammar correction** — GEC model absent.
- **Latency** (mean 2.7 s, P99 34 s) blocks interactive use on CPU.
- **Flaky/order-dependent tests** and one stale test API undermine CI confidence.
- **Probe sampling bias note:** the FN/detected examples in §5 come from the earliest error types in file order (all detected examples are SYLLABLE_SWAP; only 1 FN was captured in 70 runs) — they are illustrative, not per-type evidence. Use the `per_kind` table for rates.

---

## 9. Actionable Recommendations (priority order)

| # | Priority | Action | Expected impact |
|---|---|---|---|
| 1 | **P0** | **Fix the context-detection hook.** Raise `context_suspicious_gap` (2.5 → ≥ 6), require a much higher candidate-confidence gate (≥ 0.9) before attaching a replacement, and emit context **advisories (replacement=None)** by default rather than edits. Validate on the 150-clean BoCorpus set to get FP ≤ 2%. | Restores specificity (0.15 → ~0.95+); eliminates ~90% of the 1,655 FP edits |
| 2 | **P0** | **Guard replacements against garbage edits.** Reject replacements that (a) inject punctuation (`༴`, `༽`, `)`, `་` spurious), (b) change >1 syllable on a dictionary-known word, or (c) score < 0.9. Add a "never auto-apply" contract for LOW/MEDIUM priority CONTEXT suggestions. | Stops destructive auto-corrections; word-level precision ↑ |
| 3 | **P0** | **Tighten the structural validator's replacement policy.** `DOUBLE_VOWEL` / `INVALID_POST_SUFFIX` edits (e.g. `མཛོདསྒོ`→`མཛོདསྒ་`) are wrong in context; either suppress replacements for unknown compounds or cross-check against the dictionary before editing. | Fewer wrong "orthography" edits |
| 4 | **P1** | **Decide on the GEC model.** Either ship `models/llama2_gec_lora` + base model (and enable only when present), or delete the dead `GrammarCorrectionPlugin` path so `TEEA_ENABLE_LLM_GEC=1` is not misleading. | Honest capability; real AI correction if models added |
| 5 | **P1** | **Fix test hygiene.** Rename `enable_context_check` → `enable_context_detection` in `test_spelling_context.py`; make the context hook deterministic (seed/fixtures) so the two FP tests are stable. | Restores CI determinism |
| 6 | **P1** | **Latency: cache TiBERT candidate scores** per (word, context-window) and consider disabling neural scoring below a confidence threshold or offloading to a service; benchmark P95 target < 500 ms. | Interactive usability |
| 7 | **P2** | **Strengthen the benchmark harness.** Add explicit over-correction/missed-correction rates at the suggestion level, a separate clean-corpus FP gate as a CI check, and per-type *correction* metrics (not just detection). Also report exact-match on error records only (currently conflated with untouched clean). | Early detection of regressions like this one |

---

## Appendix: How to reproduce

```bash
# 1. Full test suite
pytest tests/ -q

# 2. Unforeseen benchmark (TiBERT loaded; note GEC model is absent so the flag is a no-op)
set PYTHONPATH=src && TEEA_ENABLE_LLM_GEC=1 python scratch/eval_unforeseen.py

# 3. Hand-crafted spot check (20 sentences + 2 clean controls)
set PYTHONPATH=src && TEEA_ENABLE_LLM_GEC=1 python scratch/eval_handcrafted.py

# 4. FP/FN example probe
set PYTHONPATH=src && TEEA_ENABLE_LLM_GEC=1 python scratch/eval_probe_examples.py
```
