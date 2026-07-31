# BoCorpus Plagiarism Indexing Architecture

This document describes the design and operational workflow for indexing the **1,039 BoCorpus Tibetan works** (`Data/Corpus/BoCorpus/bo_corpus.parquet`) into the TEEA Winnowing Plagiarism detection engine and SQLite database repository.

---

## High-Level Architecture Pipeline

```text
BoCorpus Parquet File (1,039 Works)
  │  (id, collection, filename, text, char_count)
  ▼
BoCorpusLoader [corpus.py]
  │  Streams PyArrow batches without loading full dataset into RAM
  ▼
Document Chunking [chunking.py]
  │  Paragraph splitting (\n) + fallback windowing (100,000 chars)
  ▼
Robust Winnowing Fingerprinting [fingerprinting.py]
  │  64-bit Rabin-Karp rolling hashes (k=6, w=4)
  ▼
Batch SQLite Persistence [sqlite.py / index_builder.py]
  │  executemany() transaction writes to fingerprint_documents and fingerprint_hashes
  ▼
Daemon Index Pre-loader [daemon.py]
  │  Pre-loads stored document fingerprints into InMemoryFingerprintIndex on startup
  ▼
Office.js Word Add-in Plagiarism Checker
   Displays similarity %, collection, filename, and highlights matching passages
```

---

## Database Schema Extensions

The `fingerprint_documents` SQLite table stores metadata and chunk offsets:

```sql
CREATE TABLE IF NOT EXISTS fingerprint_documents (
    document_id TEXT NOT NULL PRIMARY KEY,
    source TEXT NOT NULL,
    fingerprint_count INTEGER NOT NULL DEFAULT 0,
    collection TEXT,
    filename TEXT,
    parent_doc_id TEXT,
    chunk_index INTEGER,
    char_start INTEGER,
    char_end INTEGER
);

CREATE INDEX IF NOT EXISTS idx_fp_docs_parent ON fingerprint_documents(parent_doc_id);
```

---

## CLI Command Usage

To build or update the BoCorpus plagiarism index from the command line:

```bash
# Standard incremental build (skips already indexed documents)
teea plagiarism build-index

# Force full rebuild from scratch
teea plagiarism build-index --force

# Custom corpus parquet path and database target
teea plagiarism build-index --corpus-path "path/to/custom_corpus.parquet" --db-path "Data/Processed/teea.db"
```
