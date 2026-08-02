# TEEA Real-World Benchmark Validation Report

## 1. Dataset & Corpus Overview

- **Dataset Size:** 55 Gold-Standard Sentences (453 Tokens across 50 Passages)
- **Corpus Sources:** BoCorpus (`bo_corpus.parquet`), Monlam Corpus, BDRC Manuscripts, Tibetan News, Textbooks, Dialogues.
- **Verification Level:** 100% Manually Verified ground-truth target annotations.

---

## 2. Overall Confusion Matrix

| | **Predicted Error** | **Predicted Clean** | **Total** |
| :--- | :---: | :---: | :---: |
| **Actual Error** | **TP = 6** | **FN = 0** | **6** |
| **Actual Clean** | **FP = 4** | **TN = 45** | **49** |
| **Total** | **10** | **45** | **55** |

---

## 3. Scientific Performance Metrics

- **Accuracy:** **92.73%**
- **Precision:** **60.00%**
- **Recall:** **100.00%** (**Zero Missed Errors**)
- **F1 Score:** **75.00%**
- **Specificity:** **91.84%**
- **False Positive Rate (FPR):** **8.16%**
- **False Negative Rate (FNR):** **0.00%**
- **Matthews Correlation Coefficient (MCC):** **0.7423**
- **Cohen's Kappa ($\kappa$):** **0.7105**

---

## 4. Execution Latency & Resource Utilization

- **Mean End-to-End Latency:** **172.09 ms** ($\pm$ 62.78 ms)
- **Median Sentence Latency:** **163.67 ms**
- **P95 Latency:** **292.71 ms**
- **P99 Latency:** **305.06 ms**
- **Memory Footprint:** **1414.72 MB** (PyTorch TiBERT model loaded in RAM)
