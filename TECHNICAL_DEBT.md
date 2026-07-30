# TEEA — TECHNICAL DEBT REGISTER

**Date:** 2026-07-30  
**Tracker:** Principal Software Engineer

---

## SUMMARY

| Category | Count | Effort (est.) |
|----------|-------|---------------|
| 🔴 Critical | 8 | 1-2 weeks |
| 🟡 High | 12 | 3-5 weeks |
| 🟢 Medium | 9 | 2-4 weeks |
| 🔵 Low | 6 | 1-2 weeks |
| **Total** | **35 items** | **7-13 weeks** |

---

## 🔴 CRITICAL DEBT

### C01: No Graceful Shutdown
**Files:** `src/teea/daemon.py` (all), `src/teea/__main__.py`  
**Issue:** `shutdown()` exists but is never wired to OS signals  
**Fix:** Add `signal.signal(SIGTERM, handler)` and `signal.signal(SIGINT, handler)`  
**Effort:** 2 hours  
**Risk:** SQLite corruption, in-flight data loss

### C02: No IPC Authentication
**Files:** `src/teea/ipc/server.py`, `src/teea/ipc/interfaces.py`  
**Issue:** Any local process can call any IPC method  
**Fix:** Add shared-secret handshake to `$connect`  
**Effort:** 1-3 days  
**Risk:** Local privilege escalation, data exfiltration

### C03: Unsafe HuggingFace Downloads
**Files:** `src/teea/nlp/tokenization/tibert.py:131`, `src/teea/ai/tibert_engine.py:121`  
**Issue:** `from_pretrained()` without pinned revision — supply chain attack vector  
**Fix:** Pin `revision` to a specific commit hash  
**Effort:** 30 minutes  
**Risk:** Malicious model substitution between deployments

### C04: No Content-Security-Policy
**File:** `addin/manifest.xml`  
**Issue:** No CSP in add-in WebView2 context — XSS → arbitrary execution  
**Fix:** Add CSP meta tag  
**Effort:** 1 hour  
**Risk:** Complete Office compromise via XSS

### C05: Daemon/Engine Code Duplication
**Files:** `src/teea/daemon.py`, `src/teea/engine.py`  
**Issue:** Two near-identical composition roots (~100 lines duplicated)  
**Fix:** Consolidate into single `daemon.py`, deprecate `engine.py`  
**Effort:** 2-3 days  
**Risk:** Configuration drift, maintenance burden

### C06: IPv6 Excluded
**File:** `src/teea/transport/analysis_server.py:103-166`  
**Issue:** `_validate_loopback()` rejects `::1` because `AF_INET6` conflicts with import ban  
**Fix:** Resolve ADR-002 conflict, add `AF_INET6` support  
**Effort:** 1-2 days  
**Risk:** Half of localhost traffic unsupported

### C07: No Coverage Gating in CI
**File:** `.github/workflows/ci.yml:53`  
**Issue:** `python -m pytest` without `--cov` flag  
**Fix:** Add `--cov=teea --cov-fail-under=80`  
**Effort:** 30 minutes  
**Risk:** Coverage can silently regress

### C08: typer Vendored But Unused
**File:** `requirements.lock` (typer@0.27.0), `src/teea/cli.py`  
**Issue:** `typer` is installed (157 KB) but CLI uses raw `argparse` (206 lines)  
**Fix:** Migrate CLI to typer or remove dependency  
**Effort:** 1-2 days  
**Risk:** Dependency bloat, unused code

---

## 🟡 HIGH DEBT

### H01: No Performance Regression Tests
**Issue:** Performance numbers are published but never verified in CI  
**Fix:** Add `pytest-benchmark` + CI benchmark step  
**Effort:** 2-3 days

### H02: No Load Tests
**Issue:** No `locust`, `k6`, or any load testing infrastructure  
**Fix:** Add basic load test suite  
**Effort:** 2-3 days

### H03: No SQLite Backup/Restore
**File:** `src/teea/persistence/sqlite.py`  
**Issue:** No backup function, no recovery procedure  
**Fix:** Add `backup()` and `restore()` methods  
**Effort:** 1-2 days

### H04: No API Documentation
**Files:** `src/teea/transport/analysis_server.py`  
**Issue:** No OpenAPI/Swagger specification  
**Fix:** Add OpenAPI spec  
**Effort:** 1-2 days

### H05: No Release Automation
**File:** `pyproject.toml` (hardcoded version)  
**Issue:** Version is manual; no semantic release pipeline  
**Fix:** Add `python-semantic-release`  
**Effort:** 2-3 days

### H06: No Monitoring/Metrics
**Issue:** Zero metrics instrumentation in entire codebase  
**Fix:** Add Prometheus client, expose `/metrics`  
**Effort:** 2-3 days

### H07: TiBERT Model Provenance Undocumented
**Files:** `src/teea/nlp/tokenization/tibert.py`  
**Issue:** No model card — training data, license, terms unknown  
**Fix:** Add MODEL_CARD.md  
**Effort:** 1 day

### H08: Lock File Without Hashes
**File:** `requirements.lock`  
**Issue:** No `--hash=sha256:*` entries  
**Fix:** Re-run `pip-compile --generate-hashes`  
**Effort:** 30 minutes

### H09: No Input Size Limits
**Files:** IPC server, NLP pipeline, plagiarism engine  
**Issue:** Arbitrarily large inputs accepted  
**Fix:** Add configurable max_size at all entry points  
**Effort:** 1-2 days

### H10: No Property-Based Tests
**Issue:** Complex model invariants not fuzz-tested  
**Fix:** Add `hypothesis` tests for DependencyTree, SemanticGraph, etc.  
**Effort:** 2-3 days

### H11: Large Files Committed to Git
**Files:** `Data/Corpus/BoCorpus/bo_corpus.parquet`, `TiBERT/model.safetensors`  
**Issue:** Large binary files committed to repository  
**Fix:** Add to `.gitignore`, download at build time  
**Effort:** 1 day

### H12: HTTP Server Code Is Dead
**File:** `src/teea/transport/http_server.py`  
**Issue:** HTTP server exists but is never wired anywhere  
**Fix:** Either wire it to the daemon or remove it  
**Effort:** 1 day

---

## 🟢 MEDIUM DEBT

### M01: No Pre-commit Hooks
**Issue:** No automated checks before commits  
**Fix:** Add `.pre-commit-config.yaml`  
**Effort:** 1 day

### M02: No Smoke Tests in CI
**Issue:** CI builds the wheel but never starts the daemon  
**Fix:** Add `teea health` smoke test  
**Effort:** 1 hour

### M03: No Documentation for Corpus Builder
**File:** `src/teea/corpus/builder.py`  
**Issue:** Missing module-level docstring; ADR needed for design decisions  
**Effort:** 4 hours

### M04: No Documentation for Transport Module
**File:** `src/teea/transport/`  
**Issue:** Newer components (transport, SQLite, corpus) have no ADRs  
**Effort:** 1 day

### M05: Mutable State in DummyInferenceEngine
**File:** `src/teea/ai/engines.py`  
**Issue:** `load_calls`, `infer_calls` etc. are public mutable lists  
**Fix:** Make read-only properties or use tuples  
**Effort:** 1 hour

### M06: Hardcoded Version in Pyproject.toml
**File:** `pyproject.toml:7`  
**Issue:** `version = "1.0.0"` is hardcoded  
**Fix:** Use `python-semantic-release` or dynamic versioning  
**Effort:** 1 day

### M07: No Memory Limits
**Issue:** Daemon has no memory limits or OOM protection  
**Fix:** Add `--max-memory` CLI flag with enforcement  
**Effort:** 1-2 days

### M08: No Rate Limiting
**File:** `src/teea/ipc/server.py`  
**Issue:** IPC server has no request rate limits  
**Fix:** Add per-session rate tracking  
**Effort:** 1 day

### M09: Stray Debug Scripts
**Files:** `scripts/check_tashi.py`, `scripts/check_tokens.py`, `scripts/trace_*.py`  
**Issue:** Debug scripts left in repository  
**Fix:** Remove or move to a `scripts/archive/` directory  
**Effort:** 30 minutes

---

## 🔵 LOW DEBT

### L01: Inconsistent `decode()` Error Name
**File:** `src/teea/nlp/tokenization/tibert.py`  
**Issue:** `InputNotStringError` on mismatch for encode vs decode path  
**Fix:** Rename or alias  
**Effort:** 30 minutes

### L02: Non-breaking Tsheg Not Round-trippable
**File:** `src/teea/nlp/tokenization/syllable.py`  
**Issue:** `has_trailing_tsheg` is `bool`, loses U+0F0B vs U+0F0C distinction  
**Fix:** Change to enum `TshegKind.NONE / TSHEG / NON_BREAKING`  
**Effort:** 1 day

### L03: was_truncated False Positive
**File:** `src/teea/nlp/tokenization/tibert.py`  
**Issue:** Exact-length input reported as truncated  
**Fix:** Needs design decision (tracked by strict xfail)  
**Effort:** Unknown (design decision)

### L04: _PRESERVED_CONTROLS Unreachable by Default
**File:** `src/teea/nlp/tokenization/normalization.py`  
**Issue:** `collapse_whitespace=True` defeats newline preservation  
**Fix:** Document or change default  
**Effort:** 1 hour

### L05: No `--version` CLI Flag
**File:** `src/teea/cli.py`  
**Issue:** No way to query installed version  
**Fix:** Add `--version` argument  
**Effort:** 30 minutes

### L06: Lazy Import Proliferation
**Files:** ~25 instances of `# noqa: PLC0415`  
**Issue:** Lazy imports are necessary but signal tight module coupling  
**Fix:** Consider restructuring to reduce circular deps  
**Effort:** 1-2 weeks

---

## REFACTORING OPPORTUNITIES

### Architecture
1. **Consolidate `daemon.py` and `engine.py`** — remove 100 lines of duplication
2. **Add dependency injection container** — reduce manual wiring in composition root
3. **Split `IpcServer`** — routing, dispatch, sessions, lifecycle into separate files
4. **Split `LocalAIRuntime`** — 350 lines, too many responsibilities

### Code Quality
5. **Add pre-commit hooks** — ruff + mypy + pytest on commit
6. **Convert CLI to typer** — reduce 206 lines of argparse boilerplate
7. **Add strict xfail for all open defects** — ensure defects can't be silently forgotten
8. **Increase test speed** — 2,131 tests in 24s is good but could be faster

### Performance
9. **Add LRU cache for analysis results** — cache keyed on text hash + configuration
10. **Parallelize sentence processing** — sentences are independent
11. **Add streaming pipeline** — process sentences as they arrive

### NLP
12. **Add gold role-annotated data** — prerequisite for Stage 11 quality measurement
13. **Add treebank-trained dependency parser** — better attachment rules
14. **Add typed NER** — entity types from typed gazetteer

### Security
15. **Add input size limits** — at all entry points
16. **Add rate limiting** — IPC server
17. **Add secrets management pattern** — before API keys are needed
