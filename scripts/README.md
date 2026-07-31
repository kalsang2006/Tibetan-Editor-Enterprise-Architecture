# TEEA Tibetan Language Data Integration Scripts

This directory contains standalone Python scripts for integrating existing Tibetan language resources into the **Tibetan Editor Enterprise Architecture (TEEA)** engine, dictionary database (`teea.db`), morphological analyzer, and contextual suggestion pipeline.

---

## Data Inventory Overview

Running `python scripts/data_inventory.py` inspects all datasets across `Data/` and project root:

| Resource Dataset | Entries / Tokens | File Size | Target Integration Component |
| :--- | :--- | :--- | :--- |
| **BoCorpus Vocabulary** | 178,452 unique words (154.2M tokens) | 5.17 MB | `teea.db` SQLite & `DictionaryOnlyCorrectionProvider` |
| **Classical Lexicon** | 15,643 entries | 590.9 KB | `teea.db` SQLite Dictionary Entries |
| **Verb Lexicon & Lemmas** | 1,888 verb lemmas + inflections | 1.51 MB | `irregular_verbs.json` Morphology Rules |
| **Irregular Verbs JSON** | 9,341 morphology rules | 1.27 MB | `TibetanMorphologyAnalyzer` & `spelling.py` |
| **SQLite Database (`teea.db`)**| 189,286 entries, 1,842 verb frames | 7.92 GB | `SqliteDictionaryRepository` & `DatabaseManager` |
| **Collocations & Confusion Sets**| 12 collocations, 44 confusion rules | 2.88 KB | `ContextualGrammarEngine` |
| **BoCorpus Parquet** | Full BoCorpus text dataset | 419.9 MB | Off-line Training & Corpus Validation |

---

## Scripts Guide

### 1. Merge Vocabulary into Dictionary
**Script:** `scripts/merge_vocabulary.py`
- Merges `bocorpus_vocabulary.json` and `classical-lexicon.txt` into SQLite database `teea.db`.
- Adds `source` (`corpus`, `classical`, `corpus+classical`) and `frequency` columns to `dictionary_entries`.
- **Usage:**
  ```bash
  python scripts/merge_vocabulary.py
  ```

### 2. Expand Irregular Verb Mappings
**Script:** `scripts/expand_irregular_verbs.py`
- Parses `verb_lexicon.json`, `lemmas.txt`, and `verbs-final.txt`.
- Extracts verb inflected form $\to$ stem mappings and appends them to `src/teea/resources/morphology/irregular_verbs.json`.
- Confidence scores: $0.90$ for explicit forms, $0.75$ for inferred forms.
- **Usage:**
  ```bash
  python scripts/expand_irregular_verbs.py
  ```

### 3. Integrate Collocations & Confusion Sets
**Script:** `scripts/integrate_collocations.py`
- Loads `collocations.json` and `confusion_sets.json` into `ContextualGrammarEngine`.
- Enables collocation-strength scoring and confusion-set malapropism detection.
- **Usage:**
  ```bash
  python scripts/integrate_collocations.py
  ```

### 4. Frequency-Weighted Suggestion Ranking
**Script:** `scripts/add_frequency_weights.py`
- Injects corpus word frequencies into `DictionaryOnlyCorrectionProvider`.
- Weights edit distance confidence by normalized log-frequencies ($\log(\text{freq}+1)/\log(\text{max\_freq}+1)$) to prioritize high-frequency Tibetan words.
- **Usage:**
  ```bash
  python scripts/add_frequency_weights.py
  ```

### 5. Data Inventory Dashboard
**Script:** `scripts/data_inventory.py`
- Displays a formatted ASCII dashboard of all language datasets, row counts, and file sizes across the repository.
- **Usage:**
  ```bash
  python scripts/data_inventory.py
  ```

---

## Example Execution Sequence

To execute the complete data integration pipeline from the project root:

```bash
python scripts/merge_vocabulary.py
python scripts/expand_irregular_verbs.py
python scripts/integrate_collocations.py
python scripts/add_frequency_weights.py
python scripts/data_inventory.py
```
