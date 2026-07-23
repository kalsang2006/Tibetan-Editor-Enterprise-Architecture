# TEEA — Engineering Handoff (Local IPC milestone, mid-flight)

Prepared during the Local IPC milestone, at the point where the implementation
and its tests are complete and the adversarial-review findings have just been
**independently reproduced**. The next step is to apply the fixes. A fresh
session can continue from here without losing context.

Read this, then `docs/ARCHITECTURE_DECISIONS.md` (ADR-001…020), then continue.

---

## Current milestone

**Local IPC layer** (`teea.ipc`) — Figure 3's P3, "Message Transport · Request
Routing", the boundary between the Office.js add-in and the Desktop Daemon.

**Completion: ~90%.** The package, its tests, lint, types, coverage, architecture
tests and benchmarks are done and green. What remains is fixing a set of defects
surfaced by an adversarial review and reproduced independently, plus their
regression tests and a re-verification pass.

**Repository state.** `git` is at `f76897e`; all milestone work is uncommitted in
the working tree. The whole suite is green (`1574+` tests), including `147` IPC
tests at 100% statement and branch coverage. The confirmed defects below are NOT
yet covered by any test — they are latent.

Figure 5's twelve pipeline stages, plus the Suggestion Fusion Engine
(`teea.fusion`, ADR-017), Plugin Runtime (`teea.plugins`, ADR-018) and AI Runtime
(`teea.ai`, ADR-019) are all complete and frozen. This milestone adds `teea.ipc`.

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

Paused **after independently reproducing** the adversarial review's findings.
Reproduction script: `scratchpad/verify_defects.py`. Every "CONFIRMED" was
reproduced against the shipped code.

### Confirmed genuine defects (fix these)
| # | Defect | File | Evidence |
|---|---|---|---|
| G1 | `_pending` leaks on any failed send (registered before send, no rollback) | `client.py` | 20 failed sends → `_pending`=20 |
| G2 | `$cancel` keyed by `request_id` alone in a **global** set, routed **before** session validation; ids repeat across clients, so a stale/cross-session cancel voids a **future** request **with no reply** (silent hang); the set is unbounded | `server.py` | stale `req-2` → next `req-2` timed out, no reply; 50 session-less `$cancel` → set of 50 |
| G3 | `result()` timeout branch never re-checks `_response`, discarding a response that arrived in the race window | `client.py` | narrow race; reviewer 83/3000, code-confirmed |
| G4 | `cancel()` sets `_cancelled` unconditionally, discarding a delivered response and leaving `done and cancelled` both true | `client.py` | 300/300 ended `done and cancelled` |
| G5 | the timeout branch never sets `_event`, so a second `result()` re-waits the whole deadline | `client.py` | 2nd `result()` took 515 ms |
| G6 | `stop()` never unhooks the receiver and no path checks `_serving`; a stopped server still decodes, routes, dispatches and mints sessions | `server.py` | post-stop `$connect` minted a session |
| G7 | the success reply is built (`dict(result)` + validation) **outside** the handler try/except, so a handler returning `None`/non-JSON escapes as a raw `TypeError`, not an `IpcFault` | `server.py` | bad return → `NON-IPC TypeError` |
| G9 | `connect()` does not guard against re-connect, orphaning the previous server session | `client.py` | 3 connects on one client → 3 sessions |
| F6 | a handler raising a `TEEAError` whose code is an IPC protocol code surfaces as the specific protocol exception (`SessionError` etc.), not `RemoteError` — violates the propagation contract | `client.py` | handler `SessionError` → client `SessionError` |
| F7 (minor) | an unknown wire code collapses to `UNKNOWN`, discarding the original code string | `client.py` | fold into F6 fix |

Also fold in: a `$connect` sent as a command mints an un-returned session; a
`$cancel` sent as a query never gets a reply (hangs).

### Reported but REJECTED (do not "fix")
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

## Instructions for the next session

1. **Continue from the current repository. Never restart this milestone**; do not
   redesign — ADR-020 is final.
2. **Preserve all public APIs.** Every planned fix is internal to `client.py` /
   `server.py`; no export, signature, or wire-model field changes. A wire-field
   change would be an ADR, not a quiet edit.
3. **Only fix defects that are objectively reproduced.** Re-run
   `scratchpad/verify_defects.py` before and after.
4. **Add a regression test for every fix**, each verified to fail without the fix
   (project standard). Use `tests/ipc/test_edge_cases.py` or a new
   `tests/ipc/test_regressions.py`.
5. **Re-run the complete verification suite:** ruff, `mypy --strict`, full
   `pytest`, architecture tests, `-m integration`, coverage (keep IPC at 100%),
   `python -m build --wheel`.
6. **Regenerate the benchmarks** if the hot path changed; compare before/after.
7. **Update ADR-020 only** if a fix required an architectural decision (the
   planned fixes do not).
8. **Stop after the completion report.** Do not start the next milestone
   (remaining: Plagiarism subsystem, Office.js add-in, SQLite/LMDB stores,
   concrete models / plugins / a named-pipe transport adapter).

**Environment.** Windows, Git Bash. `PYTHONPATH="src;."` (semicolon) for ad-hoc
scripts; `PYTHONIOENCODING=utf-8` for Tibetan output. Prefer Write over heredocs.

### Fix sketch (design already worked out)
* **G1** — in `IpcClient._send`, keep register-before-send (the sync transport
  needs the entry present before delivery), but wrap the send and **roll back**
  the `_pending` entry on any failure.
* **G2** — key cancellation by `(session_id, request_id)`; track `_inflight` keys
  added when a user request is dispatched, removed when handled; record a cancel
  **only** for a key in `_inflight`; route `$cancel` **after** session validation;
  a skipped request replies with an `IPC_CANCELLED` fault, not silence. Both sets
  stay bounded by the in-flight count.
* **G3/G4/G5** — rewrite `PendingCall`: `done` = `_response is not None`;
  `result()` timeout branch re-checks `_response` and returns it if present, else
  marks cancelled **and sets the event**; `cancel()` no-ops if `_response` present.
* **G6** — `IpcServer._on_message` returns early if not `_serving`.
* **G7** — build the success response inside the handler try/except so a bad
  return becomes an `IPC_HANDLER_FAILED` fault.
* **G9** — `connect()` raises if already connected.
* **F6/F7** — distinguish protocol-originated faults from handler faults so the
  client raises the specific protocol exception only for the former, `RemoteError`
  (keeping the code) for the latter; retain the original wire code in context.
