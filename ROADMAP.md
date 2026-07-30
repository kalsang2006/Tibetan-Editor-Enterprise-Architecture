# TEEA — PRIORITY ROADMAP

**Date:** 2026-07-30  
**Target:** Production-ready v2.0.0

---

## PHASE 1: CRITICAL FIXES (Weeks 1-2)

**Goal:** Eliminate data loss and security risks. The project cannot be deployed without these fixes.

| # | Item | Effort | Risk | Dependencies |
|---|------|--------|------|-------------|
| 1 | Add OS signal handlers (SIGTERM/SIGINT → shutdown) | 2 hours | CRITICAL | None |
| 2 | Add IPC shared-secret authentication | 2-3 days | CRITICAL | None |
| 3 | Pin TiBERT model revision; hardcode `trust_remote_code=False` | 30 min | CRITICAL | None |
| 4 | Add Content-Security-Policy to add-in manifest | 1 hour | CRITICAL | None |
| 5 | Add configurable max input size at IPC boundary | 1-2 days | HIGH | #2 |
| 6 | Add per-session rate limiting to IPC server | 1 day | HIGH | #2 |
| 7 | Lock file: re-run with `--generate-hashes` | 30 min | MEDIUM | None |
| 8 | `.gitignore` large binary files (parquet, safetensors) | 1 day | MEDIUM | None |

**Deliverable:** Secure shutdown, authenticated IPC, supply-chain protection  
**Validation:** `pytest`, `bandit`, manual security review

---

## PHASE 2: OPERATIONAL INFRASTRUCTURE (Weeks 3-5)

**Goal:** Monitoring, metrics, backup, and operations tooling.

| # | Item | Effort | Priority | Dependencies |
|---|------|--------|----------|-------------|
| 9 | Add Prometheus metrics endpoint (`/metrics`) | 2-3 days | HIGH | None |
| 10 | Add SQLite backup (`backup()`) and restore commands | 1-2 days | HIGH | None |
| 11 | Add structured logging to JSON output (already partially done) | 1 day | HIGH | None |
| 12 | Add health check feedback loop (auto-restart on failure) | 1 day | MEDIUM | #1 |
| 13 | Add `teea vacuum` SQLite maintenance command | 1 day | MEDIUM | #10 |
| 14 | Add `teea import/export` data commands | 2-3 days | MEDIUM | #10 |
| 15 | Add memory limits (`--max-memory` flag) | 1-2 days | MEDIUM | None |
| 16 | Fix IPv6 loopback support (resolve ADR-002 conflict) | 1-2 days | MEDIUM | None |

**Deliverable:** Deployable daemon with monitoring, backup, and maintenance commands  
**Validation:** Integration tests, manual operational testing

---

## PHASE 3: TESTING & CI ENHANCEMENTS (Weeks 5-7)

**Goal:** Automated quality gates that prevent regressions.

| # | Item | Effort | Priority | Dependencies |
|---|------|--------|----------|-------------|
| 17 | Add coverage gating to CI (`--cov=teea --cov-fail-under=80`) | 30 min | HIGH | None |
| 18 | Add performance regression tests (`pytest-benchmark`) | 2-3 days | HIGH | None |
| 19 | Add load test suite (locust or custom benchmark) | 2-3 days | HIGH | #18 |
| 20 | Add smoke tests (start daemon, run `teea health`) | 1 day | MEDIUM | #1 |
| 21 | Add property-based tests (hypothesis) for models | 2-3 days | MEDIUM | None |
| 22 | Add stress tests for IPC server (100+ concurrent clients) | 2-3 days | MEDIUM | #2 |
| 23 | Add SQLite corruption recovery tests | 1-2 days | MEDIUM | None |

**Deliverable:** CI pipeline that prevents performance, coverage, and reliability regressions  
**Validation:** CI passing, benchmark baselines established

---

## PHASE 4: RELEASE AUTOMATION (Weeks 6-8)

**Goal:** Automated builds, versioning, and publishing.

| # | Item | Effort | Priority | Dependencies |
|---|------|--------|----------|-------------|
| 24 | Add `python-semantic-release` for automated versioning | 1-2 days | MEDIUM | None |
| 25 | Add Docker Hub publishing to CI | 1 day | MEDIUM | None |
| 26 | Add PyPI publishing (if open-source) | 1 day | LOW | License resolution |
| 27 | Add Dependabot or Renovate for dependency updates | 1 day | MEDIUM | None |
| 28 | Add GitHub release workflow with CHANGELOG generation | 1 day | MEDIUM | #24 |
| 29 | Add pre-commit hooks (ruff + mypy + pytest) | 1 day | LOW | None |
| 30 | Add issue/PR templates | 1 day | LOW | None |

**Deliverable:** One-command releases with automated changelog and container publishing  
**Validation:** End-to-end release dry run

---

## PHASE 5: ARCHITECTURE CONSOLIDATION (Weeks 7-10)

**Goal:** Reduce duplication, improve maintainability, prepare for scaling.

| # | Item | Effort | Priority | Dependencies |
|---|------|--------|----------|-------------|
| 31 | Consolidate `daemon.py` and `engine.py` | 2-3 days | MEDIUM | None |
| 32 | Migrate CLI from argparse to typer | 1-2 days | LOW | None |
| 33 | Split `IpcServer` into smaller files | 1-2 days | LOW | None |
| 34 | Split `LocalAIRuntime` into smaller components | 1-2 days | LOW | None |
| 35 | Add LRU cache for analysis results | 3-5 days | MEDIUM | None |
| 36 | Parallelize sentence processing | 2-4 days | LOW | None |
| 37 | Clean up stray debug scripts | 1 day | LOW | None |
| 38 | Add pre-commit config | 1 day | LOW | None |
| 39 | Remove dead code (`http_server.py`, unused transport code) | 1 day | LOW | None |

**Deliverable:** Cleaner codebase with better performance and maintainability  
**Validation:** All existing tests pass, no regressions

---

## PHASE 6: NLP ENHANCEMENTS (Weeks 8-12)

**Goal:** Improve NLP quality metrics and fill documented gaps.

| # | Item | Effort | Priority | Dependencies |
|---|------|--------|----------|-------------|
| 40 | Create role-annotated Tibetan corpus (Stage 11 eval) | 3-6 months | HIGH | Domain expert |
| 41 | Add treebank-trained dependency parser | 2-4 months | HIGH | #40 |
| 42 | Add typed NER gazetteer | 2-4 weeks | MEDIUM | Domain expert |
| 43 | Expand terminology glossary | 2-4 weeks | MEDIUM | Domain expert |
| 44 | Add TiBERT model card (MODEL_CARD.md) | 1 day | MEDIUM | None |
| 45 | Add cross-sentence context window for tokenization | 2-4 weeks | LOW | None |
| 46 | Add streaming pipeline support | 2-4 weeks | LOW | None |

**Deliverable:** Measurably improved NLP accuracy with verified quality metrics  
**Validation:** Gold corpus evaluation, regression tests

---

## PHASE 7: ADD-IN ENHANCEMENTS (Weeks 10-12)

**Goal:** Polish the Office.js add-in for production use.

| # | Item | Effort | Priority | Dependencies |
|---|------|--------|----------|-------------|
| 47 | Add debounced typing (FR-1) | 1-2 days | MEDIUM | None |
| 48 | Add suggestion inline display | 2-3 days | MEDIUM | None |
| 49 | Add accept/reject all controls | 1 day | LOW | None |
| 50 | Add theme-aware styling | 1-2 days | LOW | None |
| 51 | Add keyboard shortcuts documentation | 1 day | LOW | None |

**Deliverable:** Polished add-in with good UX  
**Validation:** User acceptance testing

---

## EFFORT SUMMARY

| Phase | Weeks | Items | Effort |
|-------|-------|-------|--------|
| 1: Critical Fixes | 1-2 | 8 | 1-2 weeks |
| 2: Operational Infrastructure | 3-5 | 8 | 2-3 weeks |
| 3: Testing & CI | 5-7 | 7 | 2-3 weeks |
| 4: Release Automation | 6-8 | 7 | 1-2 weeks |
| 5: Architecture Consolidation | 7-10 | 9 | 2-3 weeks |
| 6: NLP Enhancements | 8-12 | 7 | 3-6 months* |
| 7: Add-in Enhancements | 10-12 | 5 | 1-2 weeks |

*NLP enhancements require domain expertise and are on a separate track

**Total for production-ready v2.0.0 (Phases 1-5):** **8-13 weeks** (2-3 engineers)  
**Total with NLP enhancements (Phase 6):** **3-6 months** (with domain expert)

---

## MILESTONE DEPENDENCY GRAPH

```
Phase 1 (Critical)
  ├── Phase 2 (Operations)
  │     └── Phase 3 (Testing)
  │           └── Phase 4 (Release)
  │                 └── Phase 5 (Architecture)
  │                       └── Phase 7 (Add-in)
  └── Phase 6 (NLP) — independent track
```

Phases 1-5 can proceed sequentially with 2-3 engineers. Phase 6 is an independent research track requiring a domain expert (Tibetan linguist/NLP researcher). Phase 7 benefits from Phase 5's architectural cleanup.

---

## RISK REGISTER

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Tibetan linguistic expertise unavailable | HIGH | HIGH | Phase 6 blocked; seek academic collaboration |
| TiBERT license incompatible with enterprise | MEDIUM | HIGH | Investigate license before Phase 1 completion |
| Named pipe transport unreliable on Windows versions | LOW | MEDIUM | Add loopback fallback transport |
| SQLite contention under high load | LOW | MEDIUM | Benchmark before Phase 3 completion |
| Dependency supply-chain compromise | LOW | HIGH | Hash-verified lock file (Phase 1, #7) |
