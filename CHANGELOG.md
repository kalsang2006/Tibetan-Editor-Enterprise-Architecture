# Changelog

All notable changes to the TEEA project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-07-28

### Added

- **SQLite persistence layer** — `DatabaseManager`, 5 SQLite-backed repositories
  (dictionary, gazetteer, terminology, verb lexicon, fingerprints). Schema
  versioning, WAL journal mode, thread-safe via RLock. 63 tests.
- **End-to-end integration test** — `tests/test_e2e_pipeline.py` exercises the
  full pipeline: normalization → NLP analysis → plugin execution → AI inference
  → suggestion fusion → IPC/daemon → CLI. 66 tests covering determinism,
  concurrency, stress scenarios.
- **Docker support** — `Dockerfile` (multi-stage, minimal image),
  `.dockerignore`, `docker-compose.yml`.
- **`CHANGELOG.md`** — this file.
- **`CONTRIBUTING.md`** — contributor guide with setup and testing instructions.

### Changed

- **Daemon composition root** — `TEEADaemon` accepts optional `db_path`
  parameter for SQLite-backed persistent storage. Backward-compatible
  (default `None` = in-memory).
- **Persistence exports** — `teea.persistence.__init__` exports all SQLite
  classes alongside existing in-memory implementations.
- **CI workflow** — Updated pip cache key to `requirements.lock`; installs
  from lock file for deterministic builds.
- **Documentation** — `HANDOVER.md` reflects current 92% completion status,
  all release blockers resolved. `README.md` updated with current test counts
  and build instructions.

### Fixed

- **`.gitignore`** — Fixed `Thumbs.dbnode_modules/` concatenation bug
  (missing newline separator) which prevented proper node_modules ignoring
  at the repository root.
- **`daemon.py`** — Fixed duplicate `from __future__ import annotations`
  block that broke module import.

### Removed

- **Stray files** — Deleted `tree` and `cls` shell artifacts from repository
  root.
- **`.claude/worktrees/`** — Development checkpoint artifacts gitignored.

### Security

- **No authentication in IPC** — Documented as acceptable for local
  loopback (no change).
- **`trust_remote_code=False`** — Correctly set by default for Hugging Face
  model loading.

## [0.1.0] — 2026-06-15

### Added

- Full 12-stage NLP pipeline (Stages 02–12)
- Suggestion Fusion Engine (Figure 7)
- Plugin Runtime with fault isolation (NFR 5.3)
- AI Runtime orchestration with capability routing (Figure 6)
- Local IPC layer: protocol, server, client, sessions, timeouts, cancellation
- Windows Named Pipe transport (ADR-020)
- Office.js add-in — React/TypeScript task pane, 44 files, 263 tests
- Plagiarism subsystem — Robust Winnowing, fingerprint index (Figure 8)
- Daemon entrypoint — `__main__.py`, `cli.py` (5 subcommands), `workflow.py`
- CI/CD pipeline — GitHub Actions: Python + TypeScript
- Architecture decisions — ADR-001 through ADR-020
- 1,756 hermetic unit tests, mypy strict clean, ruff clean
