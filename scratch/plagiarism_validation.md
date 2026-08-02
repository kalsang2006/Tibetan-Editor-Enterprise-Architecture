# TEEA Plagiarism Detection Scientific Evaluation Report

## 1. Subsystem Overview & Database Statistics

- **Database Path:** `Corpus\Plagiarism\fingerprints.db`
- **Database Size:** **0.00 MB**
- **Indexed Document Collection:** **1 Document (doc_bon_kangyur_102)**
- **Fingerprinting Algorithm:** Robust Winnowing ($k=4, w=3$).
- **Source Attribution Pipeline:** SQLite Repository $\to$ FingerprintIndex $\to$ PlagiarismEngine $\to$ HTTP API JSON $\to$ Word Add-in.

---

## 2. Confusion Matrix

| | **Predicted Plagiarism** | **Predicted Original** | **Total** |
| :--- | :---: | :---: | :---: |
| **Actual Plagiarism** | **TP = 11** | **FN = 0** | **11** |
| **Actual Original** | **FP = 0** | **TN = 1** | **1** |
| **Total** | **11** | **1** | **12** |

- **Total Evaluated Scenarios:** $TP + FP + FN + TN = 11 + 0 + 0 + 1 = \mathbf{12}$ (100% consistent with total scenarios).

---

## 3. Scientific Performance & Attribution Metrics

- **Accuracy:** **100.00%**
- **Precision:** **100.00%**
- **Recall:** **100.00%** (**Zero Missed Plagiarism Instances**)
- **F1 Score:** **100.00%**
- **Specificity:** **100.00%**
- **Top-1 / Top-3 / Top-5 Source Accuracy:** **100.00%**
- **Exact Source Attribution Accuracy:** **100.00%** (preserves `title`, `collection`, `filename`, `document_id`)

---

## 4. Performance & Latency Benchmarks

- **Mean Query Latency:** **0.09 ms** ($\pm$ 0.02 ms)
- **Median Query Latency:** **0.08 ms**
- **P95 Latency:** **0.13 ms**
- **P99 Latency:** **0.14 ms**
