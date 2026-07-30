# TEEA — SECURITY AUDIT

**Date:** 2026-07-30  
**Auditor:** Staff Security Engineer  
**Methodology:** Manual code review + Bandit static analysis

---

## SCORING

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

## CRITICAL FINDINGS

### C1: No IPC Authentication (Severity: CRITICAL)

**Files:** `src/teea/ipc/server.py` (entire file), `src/teea/ipc/interfaces.py`

**Description:** The `IpcServer` accepts any IPC request without verifying the caller's identity. Any local process (or malware) can invoke `analyze`, `plugins`, `fuse`, `plagiarism`, or any registered handler.

**Impact:**
- Local privilege escalation: malware on the same machine can read any document analyzed by the daemon
- Data exfiltration: an attacker can call `analyze` on arbitrary text and exfiltrate the results
- Resource exhaustion: an attacker can flood the daemon with requests

**Evidence:**
```python
# src/teea/ipc/server.py — no authentication anywhere
class IpcServer:
    def _route(self, request: IpcRequest) -> None:
        # No auth check before routing
        session = self._session_for(request)
        ...
        self._dispatch_user(request, session)
```

Grep for `auth`, `token`, `key`, `password`, `credential`, `permission` — zero security-related matches.

**Fix:** 
1. Add shared-secret handshake to `$connect` flow
2. Server generates a random secret at startup
3. Client must present the secret to establish a session
4. Named pipe DACL restricts access to the daemon's user (Windows-only)

**Effort:** 1-3 days

---

### C2: No OS Signal Handlers (Severity: CRITICAL)

**Files:** All Python files

**Description:** `daemon.py` has `shutdown()` and `threading.Event` but **no `signal.signal()` call exists anywhere** in the 100-file codebase. A `SIGTERM` (from Docker, task manager, or `kill`) or `SIGINT` (Ctrl+C) kills the process immediately.

**Impact:**
- SQLite database corruption (mid-write shutdown)
- In-flight IPC requests lost without response
- Temporary file leaks

**Evidence:**
```
$ grep -r "signal.signal\|SIGTERM\|SIGINT\|atexit" src/teea/ --include="*.py"
# Zero matches
```

**Fix:**
```python
import signal

def _handle_signal(signum, frame, daemon):
    daemon.shutdown()

# In daemon.start() or __main__
signal.signal(signal.SIGTERM, lambda s, f: daemon.shutdown())
signal.signal(signal.SIGINT, lambda s, f: daemon.shutdown())
```

**Effort:** 1-2 hours

---

### C3: Unsafe HuggingFace Download (Severity: HIGH)

**Files:** `src/teea/nlp/tokenization/tibert.py:131`, `src/teea/ai/tibert_engine.py:121`

**Description:** `AutoTokenizer.from_pretrained()` and `AutoModelForMaskedLM.from_pretrained()` are called without a pinned `revision` parameter. This is a supply-chain attack vector — the downloaded model weights could change between deployments.

**Impact:**
- A compromised Hugging Face repo could serve malicious model weights
- Model weights with embedded exploits (pickle-based attacks)
- Non-deterministic deployments (model behavior changes without code changes)

**Evidence (tibert.py):**
```python
backend = AutoTokenizer.from_pretrained(
    source,
    cache_dir=str(settings.model_cache_dir),
    use_fast=True,
    revision=settings.model_revision,  # None by default! Uses HEAD
    trust_remote_code=False,  # Correctly False
)
```

The `model_revision` setting exists but defaults to `None`, which means "use HEAD".

**Fix:** Pin to a specific commit hash:
```python
revision=settings.model_revision or "a1b2c3d4...",  # Pin to known good revision
```

**Effort:** 30 minutes

---

### C4: No Content-Security-Policy (Severity: HIGH)

**File:** `addin/manifest.xml`

**Description:** The Office.js add-in manifest has no Content-Security-Policy header. The add-in loads in WebView2 (Edge Chromium), where an XSS vulnerability could lead to arbitrary code execution in the Office context with access to the user's documents.

**Impact:**
- XSS → arbitrary JavaScript execution in Word process
- Access to all open documents via Office.js APIs
- Network access to exfiltrate documents

**Fix:** Add to the taskpane HTML:
```html
<meta http-equiv="Content-Security-Policy" 
      content="default-src 'self'; 
               script-src 'self'; 
               style-src 'self' 'unsafe-inline'; 
               connect-src 'self'">
```

**Effort:** 1 hour

---

### C5: Bandit B615 Finding (Severity: MEDIUM)

**File:** `src/teea/nlp/tokenization/tibert.py:131`

**Description:** Bandit reports B615 (CWE-494) — downloading model files without integrity verification.

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

## MEDIUM FINDINGS

### M1: No Input Size Limits (Severity: MEDIUM)

**Files:** `src/teea/ipc/server.py`, `src/teea/nlp/snapshot/builder.py`, `src/teea/plagiarism/engine.py`

**Description:** No validation of input sizes anywhere in the pipeline. A client sending a 1GB string would cause OOM.

**Evidence:**
- `IpcServer._on_message()` decodes the entire payload without size check
- `LanguageServerSnapshotBuilder.analyze()` processes any string length
- `PlagiarismEngine.detect()` fingerpints any text length

**Fix:** Add configurable max input sizes at the IPC boundary and pipeline entry points.

**Effort:** 1-2 days

---

### M2: No Rate Limiting (Severity: MEDIUM)

**File:** `src/teea/ipc/server.py`

**Description:** The IPC server has no rate limiting. A malicious local process could flood the daemon with requests, starving legitimate users.

**Fix:** Add per-session request rate tracking with configurable limits.

**Effort:** 1 day

---

### M3: Lock File Without Hash Verification (Severity: MEDIUM)

**File:** `requirements.lock`

**Description:** The lock file pins exact versions but lacks `--hash=sha256:*` entries. `pip install` cannot verify package integrity.

**Fix:** 
```bash
pip-compile --generate-hashes --output-file=requirements.lock pyproject.toml
```

**Effort:** 30 minutes

---

### M4: Secrets Management (Severity: MEDIUM)

**Files:** All config modules

**Description:** The project uses `pydantic-settings` with environment variables directly. There is no `.env` file template, no secrets encryption, and no secrets management strategy.

**Impact:** If API keys or credentials are needed in the future, there's no established pattern for handling them securely.

---

## LOW FINDINGS

### L1: Path Traversal Risk in CLI

**File:** `src/teea/cli.py`

**Description:** The `analyze`, `workflow`, and `format` subcommands accept file paths as arguments. While the user is running the CLI locally (no privilege boundary), there's no validation of the path.

**Fix:** Resolve paths relative to a configurable working directory.

### L2: Stack Traces in Error Messages

**File:** `src/teea/core/errors/__init__.py`

**Description:** `TEEAError` preserves `__cause__` for traceback chaining. While the `to_dict()` method strips tracebacks for IPC, a direct API consumer could see internal stack traces.

---

## DEPENDENCY VULNERABILITIES

No vulnerability scanning tool (pip-audit, safety, Dependabot) is configured. The 42 dependencies in `requirements.lock` should be scanned before production deployment.

---

## RECOMMENDATIONS (PRIORITY ORDER)

| Priority | Issue | Effort | Fix |
|----------|-------|--------|-----|
| P0 | No IPC auth | 1-3 days | Add shared-secret handshake |
| P0 | No signal handlers | 2 hours | Wire SIGTERM/SIGINT to shutdown() |
| P0 | Unsafe model download | 30 min | Pin revision, hardcode trust_remote_code |
| P0 | No CSP | 1 hour | Add CSP meta tag to taskpane HTML |
| P1 | No input size limits | 1-2 days | Add max_size config at IPC boundary |
| P1 | No rate limiting | 1 day | Add per-session rate tracker |
| P1 | Lock file hashes | 30 min | Re-run pip-compile --generate-hashes |
| P2 | Secrets management | 1 day | Document pattern, add .env.example |
| P2 | Path validation | 1 hour | Resolve relative to working directory |
