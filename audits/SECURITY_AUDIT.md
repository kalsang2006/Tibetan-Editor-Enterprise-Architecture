# TEEA — Security Audit

**Date:** 2026-07-30
**Version:** 1.0.0
**Git Commit:** (as of audit date)
**Auditor:** Staff Security Engineer
**Methodology:** Manual code review + Bandit static analysis
**Source:** `SECURITY_AUDIT.md` (project root), `bandit_report.json` (project root), `bandit_results.json` (project root)
**Verification:** Regenerated from existing documentation; no live tests executed.

---

## Scoring

| Area | Score (1-10) | Grade |
|------|-------------|-------|
| Input Validation | 5 | ★★★☆☆ |
| File Handling | 6 | ★★★☆☆ |
| Dependency Security | 4 | ★★☆☆☆ |
| IPC Security | 2 | ★★☆☆☆ |
| Supply Chain | 3 | ★★☆☆☆ |
| Secrets Management | 2 | ★★☆☆☆ |
| XSS/Injection | 4 | ★★☆☆☆ |
| **Overall** | **3.7** | **★★☆☆☆** |

---

## Critical Findings

### C1: No IPC Authentication (Severity: CRITICAL)

**Files:** `src/teea/ipc/server.py`, `src/teea/ipc/interfaces.py`

**Description:** The `IpcServer` accepts any IPC request without verifying the caller's identity. Any local process (or malware) can invoke any registered handler.

**Impact:**
- Local privilege escalation: malware on same machine can read any analyzed document
- Data exfiltration: attacker can call `analyze` on arbitrary text
- Resource exhaustion

**Evidence:** Grep for `auth`, `token`, `key`, `password`, `credential`, `permission` — zero security-related matches.

**Fix:** Add shared-secret handshake to `$connect` flow; restrict named pipe DACL.
**Effort:** 1-3 days

---

### C2: No OS Signal Handlers (Severity: CRITICAL)

**Files:** All Python files

**Description:** `daemon.py` has `shutdown()` but **no `signal.signal()` call exists anywhere**. A `SIGTERM` or `SIGINT` kills the process immediately.

**Impact:**
- SQLite database corruption (mid-write shutdown)
- In-flight IPC requests lost
- Temporary file leaks

**Evidence:** `grep -r "signal.signal\|SIGTERM\|SIGINT\|atexit" src/teea/` — zero matches.

**Fix:** Wire `signal.signal(SIGTERM, ...)` and `signal.signal(SIGINT, ...)` to `daemon.shutdown()`.
**Effort:** 1-2 hours

---

### C3: Unsafe HuggingFace Download (Severity: HIGH)

**Files:** `src/teea/nlp/tokenization/tibert.py:131`, `src/teea/ai/tibert_engine.py:121`

**Description:** `AutoTokenizer.from_pretrained()` called without pinned `revision`. Supply-chain attack vector.

**Impact:**
- Compromised model weights between deployments
- Non-deterministic deployments

**Evidence:** Bandit B615 (CWE-494) in `bandit_report.json`. `model_revision` defaults to `None`.

**Fix:** Pin to specific commit hash; hardcode `trust_remote_code=False`.
**Effort:** 30 minutes

---

### C4: No Content-Security-Policy (Severity: HIGH)

**File:** `addin/manifest.xml`

**Description:** Office.js add-in manifest has no CSP. XSS could lead to arbitrary execution in Word context.

**Impact:**
- XSS → arbitrary JavaScript in Word process
- Access to all open documents via Office.js APIs

**Evidence:** Grep for `Content-Security-Policy`, `csp`, `CSP` — zero matches.

**Fix:** Add CSP meta tag to taskpane HTML.
**Effort:** 1 hour

---

### C5: Bandit B615 Finding (Severity: MEDIUM)

**File:** `src/teea/nlp/tokenization/tibert.py:131`

**Evidence from `bandit_report.json`:**
```json
{
  "code": "B615",
  "filename": "src/teea/nlp/tokenization/tibert.py",
  "issue_confidence": "MEDIUM",
  "issue_severity": "MEDIUM",
  "cwe": ["CWE-494"]
}
```

---

## Medium Findings

### M1: No Input Size Limits (Severity: MEDIUM)
**Files:** IPC server, NLP pipeline, plagiarism engine

**Description:** No validation of input sizes anywhere. A 1GB string would cause OOM.

**Fix:** Add configurable max input sizes at IPC boundary and pipeline entry points.
**Effort:** 1-2 days

### M2: No Rate Limiting (Severity: MEDIUM)
**File:** `src/teea/ipc/server.py`

**Description:** No request rate limits. Malicious local process could flood the daemon.

**Fix:** Add per-session request rate tracking.
**Effort:** 1 day

### M3: Lock File Without Hash Verification (Severity: MEDIUM)
**File:** `requirements.lock`

**Description:** Lacks `--hash=sha256:*` entries. `pip install` cannot verify integrity.

**Fix:** Re-run `pip-compile --generate-hashes`.
**Effort:** 30 minutes

### M4: Secrets Management (Severity: MEDIUM)
**Files:** All config modules

**Description:** No `.env` file template, no secrets encryption. API keys would be stored insecurely.

**Fix:** Add `.env.example`, document secrets management pattern.
**Effort:** 1 day

---

## Low Findings

### L1: Path Traversal Risk in CLI
**File:** `src/teea/cli.py`

**Description:** File paths accepted as arguments without validation.

**Fix:** Resolve relative to configurable working directory.

### L2: Stack Traces in Error Messages
**File:** `src/teea/core/errors/__init__.py`

**Description:** `TEEAError` preserves `__cause__` for tracebacks. Direct API consumers could see internal stack traces.

---

## Dependency Vulnerabilities

No vulnerability scanning tool (pip-audit, safety, Dependabot) is configured. The 42 dependencies should be scanned before production deployment.

---

## Recommendations (Priority Order)

| Priority | Issue | Effort | Fix |
|----------|-------|--------|-----|
| P0 | No IPC auth | 1-3 days | Add shared-secret handshake |
| P0 | No signal handlers | 2 hours | Wire SIGTERM/SIGINT to shutdown() |
| P0 | Unsafe model download | 30 min | Pin revision, hardcode trust_remote_code |
| P0 | No CSP | 1 hour | Add CSP meta tag |
| P1 | No input size limits | 1-2 days | Add max_size config at IPC boundary |
| P1 | No rate limiting | 1 day | Add per-session rate tracker |
| P1 | Lock file hashes | 30 min | Re-run pip-compile --generate-hashes |
| P2 | Secrets management | 1 day | Document pattern, add .env.example |

---

## Comparison with Previous Audit

- **This is the baseline security audit**
- **Bandit findings:** Single B615 finding (CWE-494) from `bandit_report.json`
- **No prior security audit exists** for comparison

## Cross-References

- Technical debt items C01-C04 also documented in `TECHNICAL_DEBT.md`
- Production readiness critical blockers: `PRODUCTION_READINESS.md` §Red
- Independent audit findings F1-F4: `PRODUCTION_READINESS_AUDIT.md`
- Full project assessment: `PROJECT_AUDIT.md` §7
