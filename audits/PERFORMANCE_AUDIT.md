# TEEA — Performance Audit

**Date:** 2026-07-30
**Version:** 1.0.0
**Git Commit:** (as of audit date)
**Auditor:** Principal Software Engineer / Performance Engineering
**Source:** `PERFORMANCE_AUDIT.md` (project root), `benchmark_results.json` (project root)
**Verification:** Regenerated from existing documentation; no live tests executed.

---

## 1. Measured Performance

### Full Pipeline (Stages 02 → 12)

Measured against the 241,882-character Milarepa text (5,885 sentences, 65,925 morphemes):

| Metric | Value | Requirement | Headroom |
|--------|-------|-------------|----------|
| Incremental re-parse, p50 | 0.68 ms | — | — |
| Incremental re-parse, p99 | **2.56 ms** | **< 50 ms (NFR 5.1)** | **20×** |
| Over budget | 0 / 400 samples | — | ✅ |
| E2E throughput | ~44k chars/s | — | — |
| Incremental vs full re-parse | **2,854× faster** | — | ✅ |
| Retained document analysis | 142 MiB (2.3 KiB/morpheme) | — | — |
| Steady-state leak | 0.6 KiB / 2,000 analyses | — | ✅ |
| Cold start (TiBERT load) | ~11 s | — | ⚠️ |

### Stages 06 → 11 (Morphology through Semantics)

| Metric | Value | Requirement | Headroom |
|--------|-------|-------------|----------|
| Stages 06 → 10, p50/p99 | 0.555 / 2.841 ms | — | — |
| Stage 11 alone, p50/p99 | 0.156 / 0.604 ms | — | — |
| Stages 06 → 11, p50/p99 | **0.784 / 3.572 ms** | **< 50 ms (NFR 5.1)** | **14×** |
| Over budget | 0 / 5,885 sentences | — | ✅ |
| Throughput (Stages 06 → 11) | ~40k chars/s | — | — |
| Verb lexicon cold start | 47 ms | vs ~11 s for TiBERT | ✅ |
| Retained per graph | 2.37 KiB/node | — | — |
| Steady-state leak | 2.1 KiB / 1,000 graphs | — | ✅ |

### Verified Optimizations

| Optimization | Before | After | Improvement |
|-------------|--------|-------|-------------|
| Precomputed transition log table | 3.8 ms/morpheme (OOV) | 0.68 ms | **5.6×** |
| Backward case-particle scan | 968 ms (3,200 adjectives) | 84 ms | **11.5×** |
| Content-hash analysis reuse | Full re-parse | Incremental | **2,854×** |

---

## 2. Memory Analysis

### Current Usage

| Component | Memory | Notes |
|-----------|--------|-------|
| TiBERT tokenizer | ~200 MB (estimated) | SentencePiece model + vocabulary |
| In-memory dictionary | ~5 MB | 220 KB JSON → in-memory overhead |
| In-memory gazetteer | ~3 MB | 109 KB JSON |
| In-memory terminology | ~1 MB | 25 KB JSON |
| In-memory verb lexicon | ~15 MB | 570 KB JSON |
| Document snapshot (reference text) | 142 MB | 241K chars, 5,885 sentences |
| TiBERT model (for inference) | ~400-500 MB | BERT-base, 12 layers |
| **Total (daemon only, no model)** | **~25-50 MB** | Acceptable |
| **Total (with inference model)** | **~500-700 MB** | Manageable |

### Memory Concerns

1. **Document snapshot size scales linearly** — 142 MB for 241K characters. A 1M-character book would use ~600 MB.
2. **No streaming** — full document loaded into memory before analysis.
3. **SQLite WAL file** can grow large under write load. No WAL checkpoint scheduling.
4. **No memory limits** on the daemon process.

---

## 3. CPU Analysis

### Cold Start

| Phase | Time | Bottleneck |
|-------|------|------------|
| TiBERT tokenizer load | ~11 s | Hugging Face `from_pretrained()` |
| TiBERT model load (inference) | ~17 s | 500 MB model download + load |
| Verb lexicon load | 47 ms | JSON parse |
| Dictionary load | 15 ms | JSON parse |
| SQLite open + schema | ~5 ms | File creation + PRAGMAs |
| **Total cold start (tokenizer only)** | **~11 s** | Acceptable for daemon |
| **Total cold start (with inference)** | **~28 s** | Acceptable for daemon |

### Steady State

| Operation | CPU | Notes |
|-----------|-----|-------|
| Full pipeline per sentence | ~0.1-0.5 ms | Negligible |
| Full document analysis (241K chars) | ~0.7 s | Acceptable for background |
| Single inference call (TiBERT) | ~3-10 ms | BERT-base forward pass |
| SQLite read | <0.1 ms | Indexed lookups |

---

## 4. I/O Analysis

### File I/O
- **Text files:** UTF-8 encoded, read/write with explicit encoding
- **JSON payloads:** Read once at cold start, then fully in-memory
- **SQLite:** WAL mode, read-heavy workload, indexed queries

### Network I/O
- **Hugging Face downloads:** ~500 MB for TiBERT model (one-time)
- **HF_HUB_OFFLINE** for air-gapped deployment (set in Dockerfile)
- **No external services** at runtime (offline-first)

---

## 5. Scalability Concerns

### Vertical Scaling (Single Machine)
- Single-threaded NLP pipeline (not parallelized)
- Plugin dispatch can be parallelized with `concurrent.futures.Executor`
- SQLite supports concurrent reads (WAL mode) but serializes writes

### Horizontal Scaling (Multiple Machines)
- **Not supported** — no distributed processing
- No sharding, no worker pools, no clustering
- Named pipe transport is single-machine only

### Concurrent Users
- **Single daemon serves multiple add-in instances** — IPC server is thread-safe
- Session management exists but untested under load
- No connection pooling or resource limits

---

## 6. Hot Paths (Optimization Targets)

### Identified Hot Paths

1. **TiBERT model loading** (~11-28 s cold start) — dominates startup time
2. **Full document re-segmentation** (linear in document size) — 0.7s for 241K chars
3. **Sentence re-hashing** (linear in document size) — blake2b hash of every sentence
4. **SQLite fingerprint insertion** — batch inserts for plagiarism index
5. **Viterbi decoding for OOV text** (0.68 ms/morpheme) — 5.6× improvement done, still measurable

### Hot Path Optimizations Attempted

| Optimization | Status | Impact |
|-------------|--------|--------|
| Precomputed transition log table | ✅ Done | 5.6× OOV speedup |
| Backward case-particle scan | ✅ Done | 11.5× long-modifier speedup |
| Content-hash analysis reuse | ✅ Done | 2,854× incremental re-parse |
| Lazy model loading | ✅ Done | Tokenizer loaded on first use |

### Hot Path Optimizations Not Attempted

| Optimization | Potential | Risk |
|-------------|-----------|------|
| LRU cache for analysis results | High | Staleness (ADR-016 concern) |
| Parallel sentence processing | Medium | Thread-safety verification needed |
| Memory-mapped dictionary files | Medium | Platform-dependent |
| Pre-warmed model download in Docker | Low | Docker layer caching already works |

---

## 7. Performance Recommendations

### Critical
1. **Add automated performance regression tests** with `pytest-benchmark` in CI
2. **Add load testing** with `locust` or custom benchmark script

### High Priority
3. **Cache full-document analysis results** — LRU keyed on text hash
4. **Add streaming pipeline support** — process sentences as they arrive
5. **Reduce cold start time** — pre-download model in Docker build

### Medium Priority
6. **Parallelize sentence processing** — sentences are independent
7. **Add PyPy or alternative runtime support** — for CPU-bound paths
8. **Add memory limits and monitoring**

### Low Priority
9. **Memory-map dictionary payloads** — reduce JSON parsing overhead
10. **Add prepared statement caching in SQLite**

---

## 8. Benchmark Methodology Assessment

### Strengths
- Measured against real Tibetan text (Milarepa corpus, 241K chars)
- Real TiBERT model used for measurements
- p50 and p99 percentiles reported (not just averages)
- Concurrency stress tested (8 threads)
- Comparison against full re-parse baseline

### Weaknesses
- Benchmarks are not part of CI — must be run manually
- No regression guards — code changes could silently degrade performance
- Single corpus measured — may not represent all Tibetan text
- No memory profiling data — usage is estimated
- No disk I/O benchmarks

---

## Comparison with Previous Audit

- **Previous audit:** This is the baseline performance audit (original document)
- **Improvements since last audit:** All three verified optimizations (5.6×, 11.5×, 2,854×) are documented as completed since initial measurements
- **Regressions:** None identified
- **New measurements:** The `scripts/comprehensive_benchmark.py` (now at `audits/`) produces 57 benchmark groups covering application, NLP, data, plugin, scalability, stress, and concurrency performance

## Cross-References

- NLP pipeline accuracy data: `NLP_AUDIT.md`
- Technical debt for performance items: `TECHNICAL_DEBT.md` (H01, #9-11)
- Production readiness: `PRODUCTION_READINESS.md` §Phase 3
- Spell checker performance: `SPELLCHECK_AUDIT.md` Part 3
