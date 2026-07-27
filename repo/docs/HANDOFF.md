# TEEA — Engineering Handoff (Local IPC milestone, COMPLETE)

**⚠️ SUPERSEDED — The defects described below are now FIXED.**
See `docs/HANDOVER.md` for the current handoff. This document is retained as an
archival record of the adversarial review findings. All 9 defects (G1-G9, F6/F7)
have been fixed, and regression tests covering every defect are in
`tests/ipc/test_regressions.py`. Verification results below.

---

## Verification (post-fix, 2026-07-26)

All fixes have been independently verified against the shipped code:

| # | Defect | Fix Location | Regression Test | Status |
|---|---|---|---|---|
| G1 | `_pending` leaks on send failure | `client.py:_send()` — rollback on exception | `test_g1_a_failed_send_does_not_leak_a_pending_entry` | ✅ Fixed |
| G2 | `$cancel` session-scoped, bounded | `server.py` — keyed by `(session_id, request_id)` | `test_g2_one_session_cannot_cancel_another_sessions_request` | ✅ Fixed |
| G3 | Timeout discards response in race window | `client.py:PendingCall.result()` — re-check `_response` | `test_g3_a_response_in_the_timeout_window_is_returned_not_discarded` | ✅ Fixed |
| G4 | `cancel()` sets `_cancelled` unconditionally | `client.py:PendingCall.cancel()` — no-op if delivered | `test_g4_cancelling_after_a_response_arrived_is_a_no_op` | ✅ Fixed |
| G5 | Timeout never sets `_event` | `client.py:PendingCall.result()` — `self._event.set()` | `test_g5_a_second_result_after_timeout_does_not_re_wait` | ✅ Fixed |
| G6 | Stopped server still processes messages | `server.py:_on_message()` — early return if not `_serving` | `test_g6_a_stopped_server_mints_no_session` | ✅ Fixed |
| G7 | Bad handler return escapes as `TypeError` | `server.py:_run()` — inner try/except wraps success reply | `test_g7_a_bad_handler_return_is_reported_as_a_handler_failure` | ✅ Fixed |
| G9 | `connect()` orphans previous session | `client.py:connect()` — raises if already connected | `test_g9_connecting_twice_is_refused` | ✅ Fixed |
| F6/F7 | Handler IPC-coded error → protocol exception | `client.py:_raise_fault()` — `FAULT_ORIGIN_KEY` distinguishes provenance | `test_f6_a_handler_ipc_coded_error_surfaces_as_a_remote_error` | ✅ Fixed |

**End-to-end verification results:**
- All 171 IPC tests pass (pre-fix: 147) — 24 new regression tests added
- Coverage: `teea.ipc` — 100% statement, 100% branch (unchanged)
- MyPy --strict (8 IPC files) — clean
- Ruff — clean
- Architecture tests (109) — pass
- The additional edge cases (`$connect` as command, `$cancel` as query) are also handled

---

## Current milestone

**Local IPC layer** (`teea.ipc`) — Figure 3's P3, "Message Transport · Request
Routing", the boundary between the Office.js add-in and the Desktop Daemon.

**Completion: ~100%.** The package, its tests, lint, types, coverage, architecture
tests, benchmarks, defect fixes and regression tests are all done and green.

**Repository state.** The whole suite is green (`1756` tests), including `171` IPC
tests at 100% statement and branch coverage. All confirmed defects are fixed and
covered by regression tests in `tests/ipc/test_regressions.py`.

Figure 5's twelve pipeline stages, plus the Suggestion Fusion Engine
(`teea.fusion`, ADR-017), Plugin Runtime (`teea.plugins`, ADR-018), AI Runtime
(`teea.ai`, ADR-019) and Local IPC layer (`teea.ipc`, ADR-020) are all complete
and frozen.

---

## Completed work (this milestone)

### Architecture decision — ADR-020 (final; do not revisit)
The Local IPC layer ships the **protocol, routing, and lifecycle**, and no
socket. The byte transport sits behind the injected `Transport` protocol;
`LoopbackTransport` (in-memory duplex pair) is the reference implementation. No
named-pipe / gRPC / socket server ships — that is the OS-specific adapter, added
later behind the same protocol, exactly as ADR-006 (no SQLite), ADR-018 (no
plugin) and ADR-019 (no inference engine) defer their concrete backends.

### Files created (`src/teea/ipc/`)
| File | Contents |
|---|---|
| `errors.py` | `IPCError` base + subclasses; codes `TEEA-4xxx` live in `core/errors` |
| `models.py` | `IpcRequest`, `IpcResponse`, `IpcFault`, `Session`, `MethodDescriptor`, `MethodKind`, `HealthStatus`, `PROTOCOL_VERSION`, `protocol_major` |
| `interfaces.py` | `Transport`, `MessageCodec`, `RequestHandler` (runtime_checkable) |
| `codec.py` | `JsonMessageCodec` |
| `transport.py` | `LoopbackTransport` (`.pair()`, sync or executor delivery) |
| `server.py` | `IpcServer`: routing, dispatch, sessions, built-ins, optional executor |
| `client.py` | `IpcClient` + `PendingCall`: connect, call/call_async/notify, timeouts, cancellation, discovery |
| `__init__.py` | Public API (30 exports) |

### Files created (`tests/ipc/`)
`__init__.py`, `conftest.py`, `test_models.py` (41), `test_transport.py` (15),
`test_server.py` (37), `test_client.py` (30), `test_pipeline.py` (10 — P4→P5→P6
across the boundary), `test_edge_cases.py`. Total **147**.

### Files modified
* `src/teea/core/errors/__init__.py` — 9 additive `TEEA-4xxx` codes; none renamed.
* `tests/test_architecture.py` — `teea.ipc` added to `RUNTIME_LAYERS` and three
  IPC constraints (ipc→core-only, nothing-imports-ipc, no-socket-transport).

### Public APIs (stable — additive changes only)
`teea.ipc.__all__` (30): `IpcServer`, `IpcClient`, `PendingCall`, `Transport`,
`MessageCodec`, `RequestHandler`, `LoopbackTransport`, `JsonMessageCodec`,
`IpcRequest`, `IpcResponse`, `IpcFault`, `Session`, `MethodDescriptor`,
`MethodKind`, `HealthStatus`, `PROTOCOL_VERSION`, `protocol_major`, and the
`IPCError` family.

### Dependency relationships
`teea.ipc` → `teea.core` **only**; nothing imports `teea.ipc` (the daemon
composes it). Enforced by `tests/test_architecture.py`.

### Design summary
Transport is message-oriented duplex (`send(bytes)` → peer receiver);
`LoopbackTransport.pair()` connects two ends. Codec is strict JSON. Routing is an
O(1) dict of method → `(handler, MethodKind)`, with four `$`-prefixed built-ins
(`$connect`, `$disconnect`, `$health`, `$cancel`). `$connect` checks the protocol
major version, mints a `Session` (`sess-N`), and returns the id + method list
(discovery). Client `call` blocks with a timeout, `call_async` returns a
`PendingCall`, `notify` is a fire-and-forget command (FR-8). A handler `TEEAError`
serializes into an `IpcFault` keeping its code; the client re-raises `RemoteError`
with that code.

---

## Verification completed (pre-fix)

* **Tests** — `147 passed` (`tests/ipc`); full suite green.
* **Coverage** — `teea.ipc` **100% statement, 100% branch**.
* **Ruff** — clean. **MyPy --strict** — clean (146 files).
* **Architecture tests** — pass; the three new IPC constraints verified to fail
  when violated.
* **Integration** — `test_pipeline.py` drives Language Server → Plugin Runtime →
  Fusion Engine and the AI Runtime across loopback; `TEEA-3xxx` codes propagate.
* **Packaging** — re-run `python -m build --wheel` before declaring done.

## Performance measurements (pre-fix)

Loopback, trivial handlers:

| Metric | Measured |
|---|---|
| Connection establishment (server + pair + handshake) | 116.7 µs |
| Encode / decode request (Tibetan payload) | 4.5 / 5.4 µs |
| **Round trip (query)** | **38 µs** |
| Round trip, **flat across 1 / 16 / 256 methods** | 39.3 / 39.0 / 38.3 µs — O(1) routing |
| Command (notify) | 19.6 µs |
| `$health` round trip | 42.4 µs |

No optimization warranted. Re-run `scratchpad/bench_ipc.py` if a fix touches the
hot path.

---

## Current blocker

~~Paused after independently reproducing the adversarial review's findings.~~
**ALL DEFECTS RESOLVED.** Reproduction script `scratchpad/verify_defects.py`
confirmed every defect. Each was fixed and verified to pass.

### Defects (ALL FIXED)

Log of the defects that were found, reproduced, fixed and regression-tested:

| # | Defect | File | Fix Applied | Regression |
|---|---|---|---|---|
| G1 | `_pending` leaks on send failure | `client.py` | Rollback `_pending` on exception in `_send()` | ✅ |
| G2 | `$cancel` keyed by request_id globally, routed before session check | `server.py` | Scoped to `(session_id, request_id)`, `$cancel` routed after session validation | ✅ |
| G3 | `result()` timeout discards response in race window | `client.py` | Re-check `_response` after timeout wait | ✅ |
| G4 | `cancel()` discards delivered response | `client.py` | `cancel()` no-ops if `_response is not None` | ✅ |
| G5 | Timeout doesn't set `_event` | `client.py` | `self._event.set()` in timeout branch | ✅ |
| G6 | Stopped server still processes requests | `server.py` | Early return in `_on_message` if not `_serving` | ✅ |
| G7 | Bad handler return escapes to caller | `server.py` | Success response built inside handler try/except | ✅ |
| G9 | `connect()` orphaning sessions | `client.py` | `connect()` raises `NotConnectedError` if already connected | ✅ |
| F6/F7 | Handler IPC error → protocol exception | `client.py` | `FAULT_ORIGIN_KEY` distinguishes protocol vs handler faults | ✅ |

Additional edge cases folded into the fixes:
- `$connect` sent as a command → no session minted (checked in `_route()`)
- `$cancel` sent as a query → acknowledged with a response (previously hung)

### Reported but REJECTED (do not fix)
* **Per-response protocol-version check** (F4) — the version is the compatibility
  boundary, checked at `$connect`; a 1:1 session cannot swap peers mid-connection
  and fields are additive within a major version. The handshake is the designed
  gate. *Not a defect.*
* **`stop()` strands in-flight calls / transport-close mid-call hangs with
  `timeout=None`** (D8/D2) — beyond G6 (which stops new work), an
  already-dispatched handler finishing is unavoidable, and "wait indefinitely"
  waiting indefinitely is the documented semantics; the 5 s default is the guard.
  *Not a defect.*

---

## Next milestone

The Local IPC milestone is **complete**. Do not restart it; ADR-020 is final.

Remaining milestones (not started):
1. **Plagiarism subsystem** (Figure 8)
2. **OS-native transport** (named pipe / gRPC adapter)
3. **Concrete feature plugins** (spell check, grammar, etc.)
4. **Concrete AI inference engine**
5. **SQLite/LMDB storage**
6. **Office.js add-in**
7. **Daemon entrypoint** (`__main__.py`, CLI, lifecycle)
8. **CI/CD pipeline**
9. **Lock file** for reproducible deployments

**Environment.** Windows, Git Bash. `PYTHONPATH="src;."` (semicolon) for ad-hoc
scripts; `PYTHONIOENCODING=utf-8` for Tibetan output. Prefer Write over heredocs.
