# TEEA v1.0.0 — Release Notes

## Summary

TEEA v1.0.0 is the first production release of the Tibetan Editor Enterprise
Architecture — an offline-first, production-grade Tibetan NLP platform and
Microsoft Word writing assistant.

## What's Included

### Core NLP Pipeline (Stages 02–12)
- Unicode normalization (NFC/NFKC/NFD/NFKD)
- Sentence segmentation (shad + line-break rules)
- Word tokenization (TiBERT via Hugging Face, 29,965 vocab)
- Orthographic syllable segmentation
- Morphological analysis (80.2% recall / 92.1% precision)
- Part-of-speech tagging (bigram HMM + Viterbi, 77 corpus tags)
- Structural dependency parsing (rule-based, ergative alignment)
- Named entity recognition (2,767 proper nouns, untyped spans)
- Terminology recognition (871 Buddhist terms + user dictionary)
- Semantic analysis (symbolic graph, verb lexicon with 1,877 lemmas)
- Immutable document snapshot (incremental reanalysis, blake2b hashing)

### Infrastructure Components
- **Suggestion Fusion Engine** — 7-stage pipeline, order-independent, conflict-resolving
- **Plugin Runtime** — supervised in-process execution, fault isolation (NFR 5.3)
- **AI Runtime** — capability-oriented inference orchestrator with `DummyInferenceEngine`
- **Local IPC Layer** — protocol, server, client, sessions, timeouts, cancellation
- **Windows Named Pipe Transport** — overlapped I/O for production use
- **Daemon Entrypoint** — CLI with 5 subcommands (analyze, workflow, format, config, health)
- **SQLite Persistence** — DatabaseManager + 5 repository implementations, schema migration
- **Plagiarism Detection** — Robust Winnowing algorithm, fingerprint index

### Office.js Add-in
- React/TypeScript task pane (44 files, 263 tests)
- Suggestion review, document interaction, IPC bridge
- Fluent UI components

## Test Summary

| Suite | Tests | Status |
|---|---|---|
| Python backend (hermetic) | **2,131** | ✅ All passing |
| TypeScript add-in | **263** | ✅ All passing |
| **Total** | **2,394** | ✅ All passing |

## Quality

- **mypy strict**: ✅ Clean — 100 source files, zero issues
- **ruff**: ✅ Clean — all checks passed
- **tsc --noEmit**: ✅ Clean — zero TypeScript errors
- **webpack build**: ✅ Compiles successfully (524 KB bundle)

## Performance

| Metric | Value |
|---|---|
| Full pipeline (St 02→12), p50 | ~1.2 ms per sentence |
| Full pipeline (St 02→12), p99 | ~5.1 ms (< 50 ms NFR) |
| Incremental reanalysis, p99 | **2.56 ms** (20× headroom) |
| E2E throughput | ~44k chars/s |

## File Inventory

| Category | Files |
|---|---|
| Python source | 100 files |
| Python tests | 2,131 tests |
| TypeScript source | 44 files |
| TypeScript tests | 263 tests |
| Documentation | 10+ documents |
| Docker/deployment | 3 files |

## Known Limitations

- **No production AI engine** — `DummyInferenceEngine` ships; ONNX-based engine is future work
- **No semantic-role gold data** — Stage 11 precision/recall/F1 not reported
- **No Docker Hub CI publishing** — Dockerfile created, automated push not configured
- **Stray worktrees** — `.claude/worktrees/` directory remains (gitignored)
