# TEEA — Hackathon Readiness Report

**Repository:** Tibetan Editor Enterprise Architecture (TEEA)
**Review date:** 2026-07-31
**Review type:** Read-only audit. No files were modified, no code was written, no fixes were applied.
**Reviewer roles:** Principal Software Architect · Senior QA Engineer · NLP Research Engineer · Product Engineer · Performance Engineer · Hackathon Judge

---

## Scope note

**What was reviewed:** `src/teea/**` (238 Python files), `addin/**` (42 TS/TSX files), `tests/**`, `docs/**`, `Data/**`, `local_ui/`, `scripts/`, root-level scripts, all Markdown documentation, `pyproject.toml`, `requirements.lock`, `.github/workflows/ci.yml`, `addin/manifest.xml`, `addin/webpack.config.js`.

**What was excluded, and why:** `repo/` and `.claude/worktrees/*` are complete stale duplicate copies of the project (`repo/` is gitignored); `.venv/`, `node_modules/`, `.mypy_cache/`, `.ruff_cache/`, `__pycache__/`, `dist/` are build/tooling artifacts.

**On "read-only":** No source, config, data, or documentation file was altered. This report is the single new file, as requested. Test and lint runs were executed to obtain empirical evidence; these write only gitignored tooling caches (`.pytest_cache/`, `__pycache__/`, `.coverage`). **Nothing that opens `Data/Processed/teea.db` was executed** — that database carries a 59 GB uncheckpointed write-ahead log, and opening it would trigger WAL recovery and rewrite a 2.1 GB file. Every claim about it below was reached by reading code, not by running it.

**Evidence standard:** Every finding cites a `file:line` that was opened and read, or the verbatim output of a command that was run. Measurements are reproductions, not quotations of existing audit documents.

---

# Executive Summary

TEEA is a genuinely ambitious and, in its interior, genuinely well-built piece of engineering. The 12-stage Tibetan NLP pipeline, the fusion engine, the plugin microkernel, the IPC layer, the persistence repositories, and the Office.js task pane are each carefully designed, thoroughly documented, and backed by a large test suite (2,285 Python tests collected, 274 TypeScript tests, all passing except one). The architecture documentation is unusually rigorous — nineteen ADRs, mechanically-enforced layering tests, and a dependency graph that the code actually respects.

**The problem is not the parts. It is the wiring between them.**

This repository contains three separate HTTP backends with three different route sets, three separate construction sites for the plagiarism engine, and two separate verb lexicons. In every one of those cases, **the composition root that the demo actually launches selects the weakest available option.** The result is that a judge following the project's own launch script will exercise a system substantially less capable than the one the code contains.

The five findings that decide this demo:

1. **The launched daemon does not serve two of the three panels the task pane mounts.** `launch_all.bat` → `start_daemon.py` starts `AnalysisHttpServer`, which routes exactly two paths. The task pane also mounts a Plagiarism panel and an AI Assistant panel, which call `/api/plagiarism/check` and `/api/ai/*`. Both return `IPC_METHOD_NOT_FOUND`. A server that routes all three exists (`TEEAHttpServer`) — nothing launches it, and no test imports it.

2. **Plagiarism detection always reports zero matches.** On every code path the add-in can reach, `PlagiarismEngine` is constructed without an index and defaults to an empty one. The 2.1 GB indexed database is never connected. The one component that wires it correctly, `TEEADaemon`, is never instantiated anywhere.

3. **The entire AI Assistant tab is a mock.** All seven handlers echo the user's input back with a bracketed prefix and an artificial 50 ms-per-token delay. "Summarize" returns the input verbatim as `[Summary] <your text>`. OCR and speech-to-text return the literal string `placeholder`.

4. **The task pane loads `office.js` from the Microsoft CDN** — in the source *and* in the committed production bundle — directly beneath a comment asserting that it does not, and contradicting the offline-first claim that is the project's central architectural thesis.

5. **The project's own quality claims do not survive contact with the tooling.** README and `HACKATHON_SUMMARY.md` claim "mypy --strict clean", "ruff clean — zero warnings", "2,394 tests passing", and "96% branch coverage". Measured: 3 mypy errors, 314 ruff errors, 15 eslint errors, one failing test, and 88% coverage. CI would fail at its first step.

Alongside these, three headline NLP features marked **Complete** are effectively demo-scripted: the collocation/malapropism engine (Stage 14) performs no mutual-information or t-test computation despite its docstring, and matches two hardcoded word patterns; the Sanskrit validator (Stage 16) is imported into the grammar plugin and never invoked; the verb transitivity validator (Stage 15) runs on 11 verbs while a corpus-derived 1,877-lemma resource sits unused beside it.

**Assessment: the project is not currently demo-ready, but it is unusually close.** The four highest-impact defects are wiring problems, not missing capability — the correct implementations already exist in the repository. A focused day of integration work, changing which objects get constructed and which server gets started, would convert this from a demo that visibly fails in front of judges into one that showcases genuinely impressive engineering.

**Overall Hackathon Readiness: 5.4 / 10** — strong foundations, high ceiling, currently undermined by integration gaps and overstated claims that a judge will test directly.

---

# Project Overview

TEEA is an offline-first Tibetan writing assistant, split across a process boundary: a Microsoft Word Office.js task pane handles presentation, and a local Python daemon performs all language computation.

| Layer | Location | Content |
| --- | --- | --- |
| NLP pipeline | `src/teea/nlp/**` | 12 documented stages: normalization, cleaning, sentence segmentation, word tokenization (TiBERT), morphology, POS tagging, dependency mapping, NER, terminology, semantics, snapshot — plus four proofreading validators |
| Fusion engine | `src/teea/fusion/**` | Priority-ranked deduplication and conflict resolution over plugin suggestions |
| Plugin microkernel | `src/teea/plugins/**` | Supervised runtime with fault isolation; five built-in plugins |
| AI runtime | `src/teea/ai/**` | Capability registry, TiBERT masked-LM inference, streaming handlers |
| Plagiarism | `src/teea/plagiarism/**` | Robust Winnowing fingerprinting, containment similarity |
| Persistence | `src/teea/persistence/**` | SQLite + in-memory repositories: dictionary, gazetteer, terminology, verb lexicon, fingerprints |
| IPC / transport | `src/teea/ipc/**`, `src/teea/transport/**` | Protocol models, Windows named-pipe transport, loopback HTTP bridges |
| Service | `src/teea/service/**` | FastAPI application, serves `local_ui/` |
| Add-in | `addin/src/taskpane/**` | React 18 + Fluent UI task pane |

**Scale:** ~8,000 Python statements under coverage; 42 TypeScript source and test files; 2,285 Python tests + 274 TypeScript tests.

**Domain difficulty is real and should be credited.** Tibetan has no word spaces; segmentation happens at the *shad* (`།`) and syllables at the *tsheg* (`་`). Affixes fuse to their host syllable. Every character is 3 UTF-8 bytes, so char and byte offsets diverge and both must be tracked to place a highlight in Word. The published TiBERT tokenizer's `do_lower_case=True` strips Unicode `Mn` characters — which in Tibetan are the vowel signs — and the codebase correctly disables this (`src/teea/ai/tibert_engine.py:113-114`, `do_lower_case=False, strip_accents=False`). That is a real insight, correctly applied.

---

# Architecture Review

## What is genuinely strong

**Layering is real, not aspirational.** `tests/test_architecture.py` mechanically enforces the dependency direction: no pipeline stage may import a later stage, `persistence` must not import `nlp`, `fusion` and `nlp` must not import each other, nothing imports `plugins`, and shared Tibetan character classes (`SHAD_CHARS`, `TSHEG_CHARS`, `LINE_BREAK_CHARS`) are defined exactly once in `core.types`. These are executable tests, and they pass. This is well above typical hackathon standard.

**The plugin microkernel is properly supervised.** `src/teea/plugins/runtime.py` isolates plugin faults, returns per-plugin outcomes with enforced attribution, and captures failures rather than propagating them. A crashing plugin cannot reach Word.

**The transport package's boundary reasoning is documented and sound.** `src/teea/transport/__init__.py:1-60` explains at length why an HTTP bridge sits beside `teea.ipc` rather than inside it — a Word task pane is a sandboxed web page and cannot open a named pipe, and `Transport` models one persistent duplex channel while HTTP needs concurrent request/response. The reasoning is correct.

**The suggestion-application path is better than expected.** `addin/src/taskpane/services/WordDocument.ts:199-278` resolves a daemon char-offset to an Office.js `Range` by walking paragraphs, correctly accounting for the paragraph separator (`offset = end + PARAGRAPH_SEPARATOR.length`, line 260), attempting an exact offset match first, then falling back to the *nearest* textual occurrence (`findBestLocalIndex`, line 281). It refuses ranges crossing paragraph boundaries and raises a typed `RangeResolutionError` rather than silently corrupting the document. This is careful work.

## The central architectural defect: three backends, one launcher, wrong choice

The repository contains **three distinct HTTP servers** exposing overlapping but unequal route sets.

| Server | Location | `/health` | `/api/analysis/run` | `/api/plagiarism/check` | `/api/ai/*` (SSE) | Launched by |
| --- | --- | :-: | :-: | :-: | :-: | --- |
| `AnalysisHttpServer` | `transport/analysis_server.py:332` | ✅ | ✅ | ❌ | ❌ | **`start_daemon.py` → `launch_all.bat`** |
| FastAPI service | `service/app.py`, `service/endpoints.py` | ✅ | ✅ | ✅ | ❌ (`/ai/rewrite` only, non-SSE) | `teea serve` (`cli.py:204`) |
| `TEEAHttpServer` | `transport/http_server.py:396` | ✅ | ✅ | ✅ | ✅ | **nothing** |

`TEEAHttpServer` is the only server that satisfies the add-in's full contract. Verified: `serve_http` and `TEEAHttpServer` are referenced **only** by their own module and the package `__init__` re-export — no launcher, no script, no CLI command, and no test file imports them. Its measured coverage is **25%** (`transport/http_server.py`, 240 statements, 169 uncovered).

This same "correct implementation exists but is not the one wired up" pattern repeats in three more places, documented under **Broken Features** below.

## Additional architectural observations

- **`start_daemon.py:14-16` reaches into private attributes** — `engine._builder`, `engine._plugin_runtime`, `engine._fusion`. There is no supported public composition accessor on `TEEAEngine`. The demo entry point depends on the facade's internals.
- **`TEEADaemon` (`daemon.py:38`) is dead code.** It is the most complete composition root in the repository — it wires the SQLite fingerprint index, populates persistence, and warns when the plagiarism index is empty (`daemon.py:111-115`). Grepping `src/` shows `TEEADaemon` and `create_daemon` referenced only within `daemon.py` itself and in two docstrings.
- **Two `ipc.ts` port constants** (`DEFAULT_AI_DAEMON_PORT`, `DEFAULT_ANALYSIS_DAEMON_PORT`) both equal 50505, with a comment explaining they are deliberately distinct "pending a real daemon launcher deciding this for good" (`addin/src/taskpane/types/ipc.ts:44-67`). The comment is honest: no real launcher exists.

---

# Feature Inventory

Legend: ✅ Fully Complete · 🟡 Partially Complete · 🔴 Broken · ⚪ Exists but not connected · ⬜ Planned, not implemented

## NLP pipeline

| # | Feature | Module | Status | % | Evidence |
| --- | --- | --- | :-: | :-: | --- |
| 02 | Unicode normalization | `nlp/tokenization/normalization.py` | ✅ | 100 | NFC/NFD handling, tsheg/shad classes from `core.types` |
| 03 | Document cleaning | `nlp/tokenization/normalization.py` | 🟡 | 80 | Punctuation standardization deliberately deferred (ADR-001, `normalization.py:21`) |
| 04 | Sentence segmentation | `nlp/segmentation/**` | ✅ | 100 | Shad-based, 7 shad variants |
| 05 | Word tokenization | `nlp/tokenization/tibert.py` | ✅ | 95 | TiBERT-backed; `do_lower_case=False` fix present |
| — | Syllable segmentation | `nlp/tokenization/syllable.py` | ✅ | 100 | Tsheg-delimited |
| 06 | Morphological analysis | `nlp/morphology/**` | ✅ | 95 | Corpus-derived affix inventory |
| 07 | POS tagging | `nlp/postagging/**` | ✅ | 95 | Real HMM: 77 tags, 2,085 emissions, 78 transition rows in `pos_model.json` |
| 08 | Dependency mapping | `nlp/dependency/**` | ✅ | 90 | Rule-based |
| 09 | Named entity recognition | `nlp/ner/**` | ✅ | 90 | 2,525 gazetteer entries + 242 ambiguous (`proper_nouns.json`) |
| 10 | Terminology recognition | `nlp/terminology/**` | ✅ | 90 | 871 entries (`terminology.json`) |
| 11 | Semantic analysis | `nlp/semantics/**` | ✅ | 90 | Symbolic graph; uses 1,877-lemma `verb_frames.json` |
| 12 | Document snapshot | `nlp/snapshot/**` | ✅ | 95 | Incremental re-parse, composition root |
| 13 | Structural syllable validator | `nlp/structural_validator.py` | ✅ | 90 | Wired into spell checker (`spelling.py:75`) |
| 14 | Collocation / malapropism | `nlp/collocation.py` | 🔴 | 25 | **No MI or t-test computed**; 12 hardcoded pairs + 12 from an 854-byte file |
| 15 | Verb lexicon / transitivity | `nlp/verb_lexicon.py` | 🟡 | 35 | 11 JSON verbs + ~12 bootstrap defaults; 1,877-lemma resource unused here |
| 16 | Sanskrit transliteration | `nlp/sanskrit.py` | ⚪ | 40 | Imported at `grammar.py:78`, **never invoked**; 11 valid words + 3 invalid stacks |

## Platform components

| Feature | Module | Status | % | Evidence |
| --- | --- | :-: | :-: | --- |
| Suggestion Fusion Engine | `fusion/**` | ✅ | 100 | 82 tests; priority ranking, dedup, conflict resolution |
| Plugin Runtime | `plugins/**` | ✅ | 100 | 141 tests; supervised, fault-isolated |
| Spell checker | `plugins/builtin/spelling.py` | ✅ | 85 | Candidate generation + TiBERT scoring + corpus ranking |
| Grammar checker | `plugins/builtin/grammar.py` | 🟡 | 70 | Contextual engine wired; Sanskrit validator dead |
| Typography plugin | `plugins/builtin/typography.py` | ✅ | 90 | 77% coverage |
| Document diagnostics | `plugins/builtin/diagnostics.py` | ✅ | 90 | — |
| Persistence (5 repositories) | `persistence/**` | ✅ | 100 | 204 tests; SQLite + in-memory, schema migration |
| IPC layer | `ipc/**` | ✅ | 100 | 208 tests |
| AI runtime / capability registry | `ai/runtime.py` | ✅ | 90 | Lazy load, batch, eviction |
| TiBERT inference | `ai/tibert_engine.py` | 🟡 | 70 | Works, but loads from HF Hub, not the local 417 MB checkpoint |
| AI assistant handlers | `ai/handlers.py` | 🔴 | 10 | **All 7 handlers are mocks** |
| Plagiarism algorithm | `plagiarism/**` | ✅ | 90 | Winnowing + containment; 81 tests, 1 failing |
| Plagiarism integration | `engine.py:129` | 🔴 | 15 | **Empty index on every reachable path** |
| Analysis HTTP bridge | `transport/analysis_server.py` | ✅ | 95 | 89% coverage; real-socket tests |
| Full HTTP bridge | `transport/http_server.py` | ⚪ | 60 | Complete route set, **no launcher**, 25% coverage |
| FastAPI service | `service/**` | 🟡 | 75 | Works, but `fastapi` absent from `requirements.lock` |
| Word add-in task pane | `addin/**` | 🟡 | 75 | 274 tests pass; two of three panels hit unrouted endpoints |
| Local browser UI | `local_ui/` | ⚪ | 70 | Served only by `teea serve`, which `launch_all.bat` never starts |
| CLI | `cli.py` | ✅ | 90 | 8 subcommands |

---

# Feature Verification

The question for each feature is not "does the code exist" but **"will a judge clicking this get a correct result?"**

## Will work in a live demo

- **Suggestions tab / document analysis.** `useDocumentAnalysis` → `AnalysisBridge` → `POST /api/analysis/run` on port 50505. `start_daemon.py` serves exactly this path. The full pipeline runs, plugins dispatch, fusion ranks, and suggestions return. **This path is sound.**
- **Accept / Reject / Undo.** `WordDocument.resolveRange` + `CommandStack` + `useUndoStack`. Offset resolution is careful and has a nearest-match fallback. Verified by 274 passing TypeScript tests.
- **Spell checking.** Real candidate generation, structural validation, corpus ranking, TiBERT rescoring. Backed by a 5.4 MB corpus vocabulary and a 178,452-unique-syllable statistics file.
- **POS tagging, NER, terminology, semantics.** All backed by substantive corpus-derived data (2,085 emissions; 2,525 proper nouns; 871 terms; 1,877 verb lemmas).
- **CLI `analyze`.** Works offline against local data.

## Will visibly fail in a live demo

| Judge action | Expected | Actual | Cause |
| --- | --- | --- | --- |
| Open Plagiarism panel, click Check | Similarity report | `IPC_METHOD_NOT_FOUND` error | Path not routed by launched server |
| — if that were fixed — | Matches found | **0 matches, 100% original, always** | Empty fingerprint index |
| Open Assistant tab, click Summarize | A summary | `[Summary] <input verbatim>` | Mock handler |
| Assistant → Translate | Translation | `[Translation to en] <input verbatim>` | Mock handler |
| Assistant → OCR / Speech-to-text | Extracted text | literal `"placeholder"` | Mock handler |
| `POST /ai/rewrite` (FastAPI) | Rewritten text | Input unchanged | `engine.rewrite()` returns its argument |
| Type a malapropism not in the hardcoded list | Detection | Nothing | Stage 14 matches 2 patterns only |
| Type a Sanskrit transliteration error | Detection | Nothing | Stage 16 never invoked |
| Verb transitivity error on any of ~1,850 verbs | Detection | Nothing | Stage 15 knows ~23 verbs |
| Run the demo with no network / captive-portal wifi | Works offline | Task pane may not initialize | `office.js` from CDN |
| Run the demo on a second machine | Works | `npm start` crashes | Hardcoded certificate path |

---

# Complete Features

These are production-quality and should be foregrounded in any demo.

1. **12-stage NLP pipeline (Stages 02–12).** Complete, tested, corpus-backed, and architecturally clean. 1,082 tests under `tests/nlp/`.
2. **Suggestion Fusion Engine.** Priority ranking (critical/high/medium/low), overlap resolution, no-op rejection, duplicate suppression, and an explicit `rejected` list so nothing is silently dropped (`fusion/models.py:288-300`). 82 tests.
3. **Plugin microkernel.** Supervised dispatch with per-plugin fault capture. 141 tests.
4. **Persistence layer.** Five repositories, schema versioning and migration, thread-safe connection management, platform-aware default path (`persistence/sqlite.py:54-60`). 204 tests.
5. **IPC protocol layer.** Frozen Pydantic wire models with `extra="forbid"`, stable error-code taxonomy, session-scoped cancellation. 208 tests.
6. **Analysis HTTP bridge.** Loopback-enforced, real-socket integration tests, 89% coverage.
7. **Office.js task pane UI shell.** Fluent UI, virtualized suggestion list, batch actions, keyboard shortcuts, theme sync, undo stack, four-state analysis status, offline banner. 274 tests, typecheck clean.
8. **Architecture enforcement tests.** Layering rules as executable tests.
9. **TiBERT tokenizer correctness fix.** `do_lower_case=False, strip_accents=False` — the single most linguistically important line in the repository.

---

# Partial Features

### Grammar checker — 70%
`plugins/builtin/grammar.py` wires `ContextualGrammarEngine` (`grammar.py:104`) and `CollocationDatabase` (`grammar.py:101`), and both run. But `SanskritTransliterationValidator` is imported (`grammar.py:78`) and never called, and `VerbLexicon` operates on ~23 verbs. The contextual engine itself is largely a hand-written rule table keyed to specific Tibetan strings.

### TiBERT inference — 70%
Functional and correctly configured, but `TiBERTInferenceEngine()` is constructed with no `local_path` (`engine.py:76`), so `source` resolves to the Hub identifier `"CMLI-NLP/TiBERT"` (`tibert_engine.py:71, 102`). `local_files_only` is never set. The model loads lazily on first candidate scoring — meaning the *first spell-check of the demo* triggers the load. On this machine an HF cache entry (`~/.cache/huggingface/hub/models--CMLI-NLP--TiBERT`) makes that fast; on a clean machine it is a ~400 MB download.

The repository's own `TiBERT/model.safetensors` (417 MB) is **never used** — it has no `config.json` or tokenizer files beside it, and nothing passes `local_path`. `TokenizationSettings.model_local_path` exists and *is* honoured by `nlp/tokenization/tibert.py:223`, so the mechanism is present but not applied to the AI engine.

### FastAPI service — 75%
Serves 11 routes including all five plagiarism aliases and `/ui`. But `fastapi` and `uvicorn` are declared `dependencies` in `pyproject.toml:31-32` and are **absent from `requirements.lock`**. A setup following the README exactly cannot import this package.

### Word add-in — 75%
The shell is excellent. Two of its three panels call endpoints the launched daemon does not route.

### Document cleaning (Stage 03) — 80%
Punctuation standardization deliberately deferred per ADR-001. Honestly documented.

---

# Broken Features

### 🔴 B1 — Plagiarism detection returns zero matches on every reachable path

Three construction sites, one correct:

| Site | Code | Index |
| --- | --- | --- |
| `engine.py:129` | `PlagiarismEngine(settings=self._settings.plagiarism)` | **empty** (defaults to `InMemoryFingerprintIndex()`, `plagiarism/engine.py:49`) |
| `transport/http_server.py:298` | `PlagiarismEngine()` | **empty**, and no settings either |
| `daemon.py:102-105` | `PlagiarismEngine(index=index, settings=...)` after loading `SqliteFingerprintRepository` | ✅ correct — **never instantiated** |

`TEEAEngine` is what `start_daemon.py` and the FastAPI service both use. Therefore the plugin (`plugins/builtin/plagiarism.py:60`, `result = self._engine.detect(...)`) always queries an empty index and returns nothing. The plugin's own docstring states the contract plainly — *"The caller is responsible for populating its index with the reference corpus"* (`plagiarism.py:37-38`) — and no caller does.

The plugin degrades *gracefully* (returns early on no matches, `plagiarism.py:62-63`), so nothing crashes. The feature simply reports **100% original for any input**, including text copied verbatim from the indexed corpus. For a judge, silent wrongness is worse than an error.

### 🔴 B2 — The launched daemon does not route the Plagiarism or Assistant panels

`launch_all.bat:9` runs `start_daemon.py`, which calls `serve_analysis_http` (`start_daemon.py:14`). That is `AnalysisHttpServer`, which routes `/health` (`analysis_server.py:213-215`) and `/api/analysis/run` only, returning `IPC_METHOD_NOT_FOUND` for anything else (`analysis_server.py:238-241`).

`App.tsx` mounts `<AIPanel>` (line 391) and `<PlagiarismPanel>` (line 398), driven by `useAIAssistant` (line 172) and `usePlagiarism` (line 173). `PlagiarismBridge` posts to `PLAGIARISM_PATH` = `/api/plagiarism/check` (`ipc.ts:59`). The Assistant posts to `/api/ai/*` (`ipc.ts:32-40`). Neither is routed.

### 🔴 B3 — The entire AI Assistant is a mock

`src/teea/ai/handlers.py`:

| Handler | Line | Behaviour |
| --- | --- | --- |
| `handle_rewrite` | 76 | `_stream_tokens(text, prefix=f"[{template}]")` — echoes input |
| `handle_explain` | 85 | prefix `[Grammar explanation]` — echoes input |
| `handle_summarize` | 94 | prefix `[Summary]` — echoes input |
| `handle_translate` | 113 | prefix `[Translation to {target}]` — **no translation** |
| `handle_ocr` | 126 | returns `f"OCR of {image_url}: placeholder"` |
| `handle_stt` | 143 | returns `"STT from base64 audio data: placeholder"` |

`_stream_tokens` (line 52) sleeps 50 ms per token (`_TOKEN_INTERVAL = 0.05`) to simulate generation, and silently truncates at 20 tokens (`if i >= token_count: break`, line 69-70).

Separately, `TEEAEngine.rewrite()` returns its input unchanged (`engine.py:186-189`, comment: *"Future AI generative integration hook"*), and is exposed at `POST /ai/rewrite` (`endpoints.py:309-317`).

### 🔴 B4 — Stage 14 computes no mutual information and no t-test

`nlp/collocation.py` docstring (lines 1-5): *"Computes Mutual Information (MI) and t-test statistics over Tibetan word co-occurrences."*

It computes neither. `import math` (line 10) is unused — flagged by ruff `F401`. Every MI and t-test value is a **hand-written literal** in `_bootstrap_defaults()` (lines 37-53): twelve pairs with values like `mi=4.85, t_test=8.42`. `load()` (line 56) adds at most twelve more from an 854-byte JSON file.

`is_malapropism()` (line 96) is two hardcoded conditionals — `བོད` in the context of `ཆོས་སྒོར`, and `ཀ` in the context of `བལྟས`. `suggest_semantic_replacement()` (line 122) is hardcoded for three target words. `get_collocation_score()` returns a neutral `0.5` for any unindexed pair (line 93), so the "general MI check" only fires for pairs already in the tiny table.

Both `load()` methods swallow all errors with bare `except Exception: pass` (`collocation.py:71-72`; `grammar/contextual_engine.py:90-91`), so a corrupt or missing data file is silent.

### 🔴 B5 — Failing test: `test_short_text_returns_empty_set`

```
FAILED tests/plagiarism/test_fingerprinting.py::TestNormalizeAndFingerprint::test_short_text_returns_empty_set
assert frozenset({Fingerprint(hash_value=12805, char_start=0, char_end=2)}) == frozenset()
```

Deterministic — identical across two full runs. **Root cause:** `fingerprinting.py:157`:
```python
effective_k = min(kgram_size, max(1, len(normalized)))
```
For `"ab"` (length 2) this adapts `k` from 6 down to 2 and produces a fingerprint. The test encodes the older contract (short text → no fingerprints). The code changed; the test did not.

The adaptive-`k` behaviour is itself questionable for precision: a 2-character document produces a fingerprint that can match any other 2-character sequence. `PlagiarismSettings.min_document_length = 20` exists as a guard (`config.py:56`) but is enforced elsewhere, so calling `normalize_and_fingerprint` directly bypasses it.

---

# Missing Features

| Claimed / implied | Reality |
| --- | --- |
| Offline-first operation | `office.js` from CDN; TiBERT from HF Hub |
| Real AI rewriting / summarizing / translation | Mock echo handlers |
| OCR, speech-to-text | Literal `"placeholder"` strings |
| Corpus-scale plagiarism detection | Index never loaded into the engine |
| Sanskrit transliteration validation (Stage 16) | Implemented, never invoked |
| MI / t-test collocation statistics (Stage 14) | Not computed |
| Documented way to run the demo | Absent from README |
| Add-in ribbon icons | Five referenced PNGs do not exist |
| LMDB cache | Not implemented (honestly noted in ADR-006) |

---

# Bug Report

## Critical

**BUG-1 — Plagiarism engine constructed without an index.** `engine.py:129`, `transport/http_server.py:298`. Always zero matches. See B1.

**BUG-2 — Demo launcher starts the wrong server.** `start_daemon.py:14`, `launch_all.bat:9`. See B2.

**BUG-3 — `office.js` loaded from the Microsoft CDN.** `addin/src/taskpane/taskpane.html:34` and, critically, the committed bundle `addin/dist/taskpane.html`:
```html
<script src="https://appsforoffice.microsoft.com/lib/1/hosted/office.js"></script>
```
The comment immediately above it (lines 28-32) states: *"office.js is loaded from the local bundle, not from the Microsoft CDN. TEEA is offline-first (ADR-002) and must start on an air-gapped machine; a CDN script tag would make the task pane fail to load without a network."* `webpack.config.js:24-27` preserves `office.js` across rebuilds (`clean: { keep: /office\.js$/ }`), showing the intent to vendor it — but no `office.js` exists in `addin/dist/`. If the network is unavailable or behind a captive portal, `Office.onReady` never fires and the task pane never initializes.

**BUG-4 — `webpack.config.js` hardcodes an absolute certificate path.**
```js
key: fs.readFileSync("C:/Users/kalsa/.office-addin-dev-certs/localhost.key"),
cert: fs.readFileSync("C:/Users/kalsa/.office-addin-dev-certs/localhost.crt"),
```
(`webpack.config.js:88-93`). `fs.readFileSync` executes when the config function is evaluated — which happens for **`npm run build` as well as `npm start`**. On any machine but this one, both commands throw `ENOENT` before webpack starts. This also breaks the CI job's `npm run build` step.

## High

**BUG-5 — CI is red at its first step.** `.github/workflows/ci.yml:52` runs `python -m ruff check src tests`. Measured: **314 errors**. Subsequent steps also fail: `mypy src` → 3 errors; `pytest` → 1 failure; `npm run lint` → 15 errors; `npm run build` → BUG-4.

**BUG-6 — Tautological test.** `tests/plugins/builtin/test_spelling_enhanced.py:128`:
```python
assert best is not None or True  # Verify candidate pipeline execution
```
This assertion can never fail. It verifies nothing. Same file, line 114: dictionary key literal `"བཀྲ་"` repeated (ruff `F601`), so one of the two mappings is silently discarded.

**BUG-7 — Debug instrumentation ships in the production bundle.** Ten `console.log` calls in add-in source, including numbered traces:
- `WordDocument.ts:127, 130, 133, 137, 142` — `[INSTRUMENTATION 1]`…`[INSTRUMENTATION 5]`, including `BODY TEXT AFTER SYNC: ${body.text}` which logs the **entire document**
- `useDocumentAnalysis.ts:85` — `console.log("Document text:", JSON.stringify(text))` — logs the entire document
- `useSuggestionEngine.ts:145-147` — apply reports

Beyond looking unfinished, logging full document text is a privacy concern for a tool marketed on local-only processing.

**BUG-8 — `requirements.lock` omits declared runtime dependencies.** `pyproject.toml:31-32` declares `fastapi` and `uvicorn` as hard dependencies. Neither appears in `requirements.lock`. The README's setup sequence (`pip install -r requirements.lock` then `pip install -e "." --no-deps`, README:186-194) therefore yields an environment where `teea.service` cannot import. `torch` and `pyarrow` are also absent (they are optional extras by design), so the AI path and parquet loading fail in a README-faithful setup.

**BUG-9 — Manifest references five nonexistent assets.** `addin/manifest.xml` lines 25, 26, 106-108 reference `https://localhost:3000/assets/icon-{16,32,64,80}.png`. There is no `addin/assets/` directory and **no PNG file anywhere in `addin/`** outside `node_modules`. The ribbon button will render without an icon.

**BUG-10 — Coverage overstated.** Claimed 96% branch coverage; measured **88%** (8,017 statements, 781 missed, 2,028 branches, 187 partial). Notable gaps: `transport/http_server.py` **25%**, `service/server.py` 48%, `service/app.py` 77%, `plugins/builtin/typography.py` 77%.

## Medium

**BUG-11 — Latent `TypeError` in the legacy plagiarism endpoint.** `endpoints.py:257-258`:
```python
check_fn = getattr(plag_engine, "detect", None) or getattr(plag_engine, "check", None)
match_result = check_fn(text, min_similarity=min_similarity)
```
If neither attribute exists, `check_fn` is `None` and the call raises `TypeError: 'NoneType' object is not callable` → HTTP 500. mypy flags exactly this (`endpoints.py:258: "None" not callable`). `PlagiarismEngine.detect` does exist (`plagiarism/engine.py:67`), so this is latent rather than live — but the surrounding `getattr` defensiveness suggests uncertainty about the engine contract. mypy also flags lines 249-250 (`Item "None" ... has no attribute "get"`).

**BUG-12 — 42 multi-character `strip()` calls, 35 in the grammar engine.** e.g. `contextual_engine.py:98`:
```python
w = w_raw.strip("་ །\u0f0b\u0f0d ")
```
The literal contains **duplicates** — `་` *is* `\u0f0b` and `།` *is* `\u0f0d` — indicating the author did not realise `strip()` takes a character *set*, not a suffix string. Consequences observed at `contextual_engine.py:194`:
```python
if w in ("བྱས་ནི", "བྱས་ནི"):     # identical alternatives
```
and line 213:
```python
if w in ("བྱས", "བྱས་") and w_next in ("ནི", "ནི"):
```
`w` has just had its tsheg stripped, so `w == "བྱས་"` is **unreachable**; and `("ནི", "ནི")` is a duplicated literal. These are dead branches in the demo-facing grammar rules.

**BUG-13 — `TEEADaemon` would exhaust memory against the real database.** `daemon.py:99-101`:
```python
index = InMemoryFingerprintIndex()
for doc in fp_repo.all():
    index.add(doc)
```
This loads **every fingerprint row from a 2.1 GB SQLite database into RAM**, with no bound, no streaming, and no batching. Even if `TEEADaemon` were wired up, this path is not viable at corpus scale.

**BUG-14 — 59 GB write-ahead log.** `Data/Processed/teea.db` is 2.1 GB with a **59,149,105,512-byte WAL** and a 114 MB shared-memory file. `IndexBuilder.build` (`plagiarism/index_builder.py:88-146`) writes in batches of 50 documents via `self._repository.save_batch(...)` but never issues a `wal_checkpoint`, and no `journal_mode`/`synchronous` tuning appears in the build path. A WAL 28× the size of its database indicates it was never checkpointed across the entire corpus ingest. All three files are **untracked**.

**BUG-15 — Stage 15 uses the wrong verb resource.** `nlp/verb_lexicon.py:16` loads `Data/Processed/verb_lexicon.json` — **11 verbs** — plus ~12 hardcoded bootstrap defaults (`verb_lexicon.py:47-59`). Meanwhile `src/teea/persistence/data/verb_frames.json` holds **1,877 lemmas / 11,711 surface forms** and is wired only into `nlp/semantics/analyzer.py:227`. The demo-facing grammar plugin uses the 11-verb file.

**BUG-16 — Unused imports indicating dead wiring.** `ruff F401` in `src/`: `SanskritTransliterationValidator` (`grammar.py:78` — Stage 16 dead), `StructuralErrorType` (`spelling.py:43`), `math` (`collocation.py:10` — no MI computed), `unicodedata` (`structural_validator.py:16`), `Field`/`Any` (`collocation.py`, `verb_lexicon.py`), `Suggestion` (`suggestion_fusion.py:14`).

## Low

**BUG-17 — 15 eslint errors.** `PlagiarismPanel.tsx:260` (×2) unescaped quotes; `AnalysisBridge.ts:101-102` and `suggestionAdapter.ts:108-156` (×11) `no-explicit-any`.

**BUG-18 — Fragile payload negotiation.** `suggestionAdapter.ts:137-165` accepts four different response shapes (bare array, `.suggestions`, `.result.suggestions`, `.result.patch.operations`) and `toSuggestion` falls back from `raw.span` to `(raw as any).range` (line 109). Defensive breadth of this kind usually indicates the wire contract was never pinned down. *(Field-level check: the `priority` enum values `critical|high|medium|low` in `fusion/models.py:57-60` do match `PRIORITY_SEVERITY` in `suggestionAdapter.ts:58-61` — no mismatch found there.)*

**BUG-19 — Offset-source mismatch risk.** `readDocumentText()` prefers `getFileAsync` slicing (`WordDocument.ts:66-73`), while `resolveRange` walks `body.paragraphs` (line 216). These two representations can disagree on separators. The nearest-occurrence fallback (`findBestLocalIndex`, line 281) masks small drift, but with repeated identical words a large drift could select the wrong occurrence.

---

# NLP Review

## Tibetan Unicode handling — strong

Character classes (`SHAD_CHARS`, `TSHEG_CHARS`, `LINE_BREAK_CHARS`) are defined once in `core.types` and that singularity is enforced by an architecture test. Normalization is configurable (NFC default). Both char and UTF-8 byte offsets are carried on `TextSpan`. Tibetan lies wholly in the BMP (U+0F00–U+0FFF), so the add-in's JavaScript UTF-16 slicing aligns with Python char offsets — a real correctness property, whether or not it was deliberate.

The `do_lower_case=False, strip_accents=False` fix (`tibert_engine.py:113-114`) is the single most linguistically consequential decision in the codebase: HuggingFace's default would strip Unicode `Mn` marks, which in Tibetan are the vowel signs. Getting this right required understanding both the tokenizer and the script.

## Data resources — a tale of two tiers

**Substantial, corpus-derived (credit due):**

| Resource | Content |
| --- | --- |
| `pos_model.json` | 77 tags, 2,085 emissions, 78 transition rows |
| `proper_nouns.json` | 2,525 entries + 242 ambiguous |
| `terminology.json` | 871 entries |
| `verb_frames.json` | 1,877 lemmas, 11,711 surface forms |
| `bocorpus_vocabulary.json` | 5.4 MB syllable frequencies |
| `bocorpus_ngrams.json` | 3.6 MB bigrams + trigrams |
| `corpus_stats.json` | 1,039 documents, 603 M chars, 12.4 M sentences, 178,452 unique syllables |

**Token-sized, backing features marked "Complete":**

| Resource | Content | Backs |
| --- | --- | --- |
| `collocations.json` | **12** collocations | Stage 14 |
| `verb_lexicon.json` | **11** verbs | Stage 15 |
| `sanskrit_words.json` | **11** valid words, 3 invalid stacks | Stage 16 |
| `confusion_sets.json` | **32** confusion entries, 5 phonetic / 4 visual / 3 orthographic | Spell checker |

The gap between the two tiers is the NLP story of this project. Stages 02–12 are backed by real corpus statistics. Stages 13–16 — the "semantic proofreading" layer that most differentiates the product — are backed by hand-written examples sized for a scripted demo.

## Component-by-component

- **Tokenization / segmentation:** solid. Syllable segmentation at tsheg, sentence segmentation across 7 shad variants.
- **Morphology:** corpus-derived affix inventory; README's 80.2%/92.1% figures are presented against gold annotations and are plausible, though not re-measured in this review.
- **POS tagging:** a real HMM over 2,085 emissions, not a lookup table.
- **NER / terminology / semantics:** genuinely backed by thousands of entries.
- **Spell checker:** the most complete demo feature. Candidate generation → structural validation → corpus n-gram context scoring (`corpus/repository.py:145-193`, weighted unigram 0.4 / bigrams 0.3 / trigram 0.4) → TiBERT masked-LM rescoring.
- **Collocation (Stage 14):** see BUG-4. Not a statistical engine.
- **Verb lexicon (Stage 15):** see BUG-15. Wrong resource.
- **Sanskrit (Stage 16):** see BUG-16. Never invoked.
- **Plagiarism:** the *algorithm* is real — k-gram rolling hashes, winnowing, asymmetric containment similarity, ranking. The *integration* is empty (BUG-1).

## False-positive risk

`tests/test_contextual_engine.py:156-158` asserts zero false-positive edits on an essay. This is a genuinely valuable guard. Note what it proves: the engine is quiet on *that* essay. Because the rule tables are small and keyed to specific strings, quietness on unseen text is the expected default — the risk at demo time is **missed detections**, not spurious ones. That is the safer failure mode, but it means unscripted Tibetan will mostly produce spelling suggestions only.

## Offline capability

Two hard dependencies on the network contradict the offline-first thesis: `office.js` from the Microsoft CDN (BUG-3) and TiBERT from the HuggingFace Hub (`tibert_engine.py:102`, no `local_files_only`). Both happen to work on this machine — the CDN via internet access, TiBERT via a populated HF cache. Neither is guaranteed at a venue.

---

# Performance Review

## Measured and observed

- **Test suite:** 2,276 tests in 37–53 s. Healthy.
- **Add-in tests:** 274 in 11.5 s. Healthy.
- **Production bundle:** `addin/dist/taskpane.js` is 585 KB — comfortably inside the 1.5 MB budget (`webpack.config.js:104-108`).

## Startup cost

`TEEAEngine.__init__` (`engine.py:57-131`), executed by `start_daemon.py` before the server binds:

1. `load_settings()`
2. `LanguageServerSnapshotBuilder()` — constructs all 12 stages
3. `default_dictionary()` — `lru_cache`d
4. `BoCorpusRepository()` — cheap; `is_available()` only stats a file
5. `combined_vocab.update(self._corpus_repo.vocabulary.keys())` (line 68) — **forces a 5.4 MB JSON parse and builds a combined set** on every startup
6. `LocalAIRuntime(...).start()` — registers TiBERT but does **not** eager-load

Step 5 is the measurable startup cost. Step 6's laziness is a *demo hazard*: the TiBERT load (~400 MB from Hub, or a cache read) is deferred to the **first spell-check** — precisely the moment a judge is watching. An eager warm-up during startup would move that latency behind the "starting daemon" message.

`launch_all.bat:11` waits a fixed `timeout /t 2` before starting the add-in server, which is unrelated to actual readiness. A `/health` poll would be correct.

## Algorithmic concerns

- **BUG-13:** unbounded load of a 2.1 GB fingerprint database into RAM.
- **BUG-14:** 59 GB WAL from an unbounded, never-checkpointed ingest.
- **`corpus/repository.py:110`** — `get_unigram_score` calls `max(self.vocabulary.values())` **on every invocation**, an O(n) scan over 178,452 entries per candidate scored. This is invoked per spell-check candidate. It should be computed once and cached; as written it is the clearest hot-path inefficiency in the NLP layer.
- **`plagiarism.py:66`** — top-10 match cap is sensible.
- **`_stream_tokens`** — the 50 ms/token sleep is artificial latency deliberately added to a mock.

## Not independently verified

`HACKATHON_SUMMARY.md` claims 1.2 ms/sentence, 2.56 ms p99 incremental re-parse, and ~44k chars/s. These were **not reproduced** in this review, because the benchmark harnesses (`benchmark_teea.py`, `stress_test.py`) were excluded from execution under the database-safety constraint. They should be treated as unverified until re-run.

---

# User Experience Review

## What is good

The task pane itself is the strongest UX artifact: Fluent UI throughout, a virtualized suggestion list for long documents, grouped suggestions, batch accept/reject, keyboard shortcuts, Office theme synchronization, persisted settings via `document.settings`, a four-state analysis status bar, and distinct offline vs. daemon-error banners. `useOnlineStatus` correctly separates *network* state from *daemon reachability* — a distinction many teams miss.

## What will read as unfinished

1. **Two of three panels error out.** The most visible UX problem is not styling — it is that clicking Plagiarism or Assistant produces a protocol error (BUG-2).
2. **The Assistant returns the user's own text.** `[Summary] <your text>` is worse than a disabled button. A judge will read it as deception rather than as a stub.
3. **No ribbon icon.** Five referenced PNGs do not exist (BUG-9). The Word ribbon button renders blank.
4. **Console noise.** `[INSTRUMENTATION 1..5]` and full document dumps in DevTools (BUG-7).
5. **Repository first impression.** The root directory is the first thing a judge browsing the repo sees:
   - `PROJECT_TREE.txt` — **12 MB**
   - Scratch output: `out.txt`, `tokens.txt`, `tokens.json`, `mask_tokens.txt`, `mask_tokens.json`, `tashi_tokens.json`, `trace_out.txt`, `trace_repl.txt`, `bench_out.txt`, `bench_out2.txt`, `test_out.txt`, `test_out2.txt`, `debug_out.txt`, `test.txt`
   - Stray root scripts: `test.py`, `test_api.py`, `test_engine.py`, `test_fixes.py`, `test_onepass.py`, `try.py`, `debug_integration.py`, `stress_test.py`
   - `bandit_report.json` + `bandit_results.json` (two copies)
   - `scratch/`, and a full duplicate `repo/` tree
   - **Twelve overlapping audit documents** at root (`HACKATHON_AUDIT.md`, `PROJECT_AUDIT.md`, `NLP_AUDIT.md`, `SPELLCHECK_AUDIT.md`, `PERFORMANCE_AUDIT.md`, `PERFORMANCE_AUDIT_FULL.md`, `PRODUCTION_READINESS.md`, `PRODUCTION_READINESS_AUDIT.md`, `SECURITY_AUDIT.md`, `TECHNICAL_DEBT.md`, `ROADMAP.md`, `HACKATHON_SUMMARY.md`), **several duplicated again under `audits/`**
6. **Terminology drift.** "daemon", "service", "bridge", "server", and "local service" are used for overlapping things across README, ADRs, and code — matching the three-backend confusion.

---

# Documentation Review

## Strengths

Genuinely excellent in places. Nineteen ADRs with real rationale. Module docstrings that explain *why*, not just *what* — `transport/__init__.py` is a model of the form. `docs/HANDOFF.md`, `docs/DATA_MAINTENANCE.md`, and the System Design Diagram set are substantial.

## Claim-versus-reality

| Claim | Source | Verdict | Measured |
| --- | --- | :-: | --- |
| "2,394 tests passing" | `HACKATHON_SUMMARY.md` | ⚠️ Stale + wrong | 2,285 Python collected (9 deselected), **1 failing**, 2,275 passing; 274 TS. Total is *higher*, but not all passing |
| "mypy --strict clean, zero errors" | `HACKATHON_SUMMARY.md` | ❌ False | **3 errors** in `service/endpoints.py:249,250,258` |
| "ruff clean — zero warnings" | `HACKATHON_SUMMARY.md` | ❌ False | **314 errors** (163 E501, 42 B005, 20 PLC0415, 16 F401, …) |
| "96% branch coverage" | `HACKATHON_SUMMARY.md` | ❌ False | **88%** |
| "TODOs in code: Zero" | `HACKATHON_SUMMARY.md` | ✅ Literally true | No `TODO`/`FIXME` markers — but 7 mock handlers and 6 `placeholder` strings exist |
| "`NotImplementedError` stubs: Zero" | `HACKATHON_SUMMARY.md` | ✅ True | Confirmed |
| "147 IPC tests" | README | ⚠️ Stale | 208 |
| "63 persistence tests" | README | ⚠️ Stale | 204 |
| "263 add-in tests" | README | ⚠️ Stale | 274 |
| "Office.js add-in — Complete" | README | ⚠️ Overstated | Shell complete; 2 of 3 panels unrouted |
| "Plagiarism subsystem — Complete" | README | ❌ False in practice | Algorithm complete; index never wired |
| "All twelve stages complete" (Figure 5) | README | ✅ For 02–12 | Stages 14/15/16 are nominal |
| "Not a mockup. Not a prototype." | `HACKATHON_SUMMARY.md` | ⚠️ Partly | True of the pipeline; false of the AI tab |
| **Internal contradiction** | README:83-85 vs README:71 | ❌ | README says the SQLite store and fingerprint index *"belong to features that do not exist yet (ADR-006)"* while the same table claims *"SQLite Persistence — Complete (5 repos, 63 tests)"*. `persistence/sqlite.py` (1,136 lines), `fingerprints.py`, and a 2.1 GB database all exist. The "do not exist yet" sentence is stale. |

## The critical documentation gap

**The README never explains how to run the demo.** Its 35 KB covers Implementation status → Requirements → Setup → Tests → Performance → Static checks → Docker → Configuration → Usage (Python API) → Data and models → Known technical debt. There is **no section on launching the Word add-in**, no mention of `launch_all.bat`, `start_daemon.py`, `npm start`, manifest sideloading, or the dev-certificate prerequisite. A judge with five minutes cannot start this product from its documentation.

Compounding this, the documented setup is broken (BUG-8): `pip install -r requirements.lock` omits `fastapi` and `uvicorn`, both declared runtime dependencies.

## Audit-document sprawl

Twelve overlapping audit documents, several duplicated under `audits/`, several containing the now-falsified quality claims. They contradict each other and this report. For judging, they should be consolidated to one.

---

# Demo Risks

Ranked by probability × visibility.

| # | Risk | Likelihood | Impact | Trigger |
| --- | --- | :-: | :-: | --- |
| 1 | Plagiarism panel errors | **Certain** | Severe | Judge clicks the Plagiarism tab |
| 2 | Assistant returns the judge's own text | **Certain** | Severe | Judge clicks Summarize / Rewrite / Translate |
| 3 | Plagiarism reports 100% original for copied text | **Certain** (if #1 fixed) | Severe | Judge pastes corpus text |
| 4 | Task pane fails to load on venue wifi | Medium | **Fatal** | Captive portal or no network → `office.js` unreachable |
| 5 | First spell-check stalls | Medium | High | TiBERT lazy-loads on first correction |
| 6 | Demo cannot run on a second machine | **Certain** | Severe | Hardcoded cert path breaks `npm start` and `npm run build` |
| 7 | Blank ribbon icon | **Certain** | Low | Judge opens the Home tab |
| 8 | Judge runs the test suite | Medium | High | 1 failing test, 314 ruff errors, red CI |
| 9 | Judge reads README claims and checks them | Medium | **Severe** | Every headline quality claim is falsifiable in one command |
| 10 | Judge types unscripted Tibetan | High | Medium | Stages 14/15/16 stay silent |
| 11 | Judge browses the repo root | High | Medium | 12 MB tree dump, ~20 debris files, duplicate `repo/` |
| 12 | Judge opens DevTools | Low | Medium | `[INSTRUMENTATION]` logs, full document dumps |

**Risk 9 deserves emphasis.** In a hackathon, overstated claims are more damaging than missing features. "mypy --strict clean" and "ruff clean" are each disproved by a single command a technical judge may well run. Understating and delivering is strictly safer.

---

# Priority Fix List

## 🔴 Critical — must fix before judging

### C1. Launch the server that routes every endpoint
- **Problem:** `start_daemon.py` starts `AnalysisHttpServer` (2 routes). The task pane needs analysis + plagiarism + AI SSE.
- **Why it matters:** Two of three panels fail immediately. Highest-visibility defect in the project.
- **Files:** `start_daemon.py:14`, `src/teea/transport/http_server.py:466` (`serve_http`), `launch_all.bat:9`
- **Solution:** Switch `start_daemon.py` from `serve_analysis_http` to `serve_http`. The complete server already exists and takes the same collaborators.
- **Effort:** ~15 minutes. **Demo impact: decisive.**

### C2. Wire the fingerprint index into the plagiarism engine
- **Problem:** `PlagiarismEngine` constructed with no index at `engine.py:129` and `http_server.py:298`; always zero matches.
- **Why it matters:** A headline feature silently reports "100% original" for verbatim copied text.
- **Files:** `src/teea/engine.py:129`, `src/teea/transport/http_server.py:298`, `src/teea/daemon.py:94-107` (the correct pattern)
- **Solution:** Pass a populated index into `TEEAEngine`'s plagiarism construction, following `daemon.py`. **Do not** replicate `daemon.py:99-101`'s unbounded full-table load against the 2.1 GB database (BUG-13) — build a small curated demo index (a few dozen documents) instead. That is both faster and more demonstrable.
- **Effort:** 1–2 hours. **Demo impact: decisive.**

### C3. Decide the AI tab's story
- **Problem:** All seven handlers echo input; OCR/STT return `"placeholder"`.
- **Why it matters:** A judge who clicks Summarize and receives their own sentence back will discount the whole project.
- **Files:** `src/teea/ai/handlers.py:76-152`, `src/teea/engine.py:186-189`, `addin/src/taskpane/components/AIPanel.tsx`
- **Solution:** Either hide/disable the Assistant tab and OCR/STT actions for the demo, or label them explicitly as simulated. Silent mocking is the only unacceptable option. Hiding is lower-risk and takes minutes.
- **Effort:** 30 minutes (hide) to several days (implement). **Demo impact: decisive.**

### C4. Vendor `office.js` locally
- **Problem:** CDN script tag in source and in the committed bundle, contradicting both the adjacent comment and the offline-first thesis.
- **Why it matters:** Venue wifi failure means the task pane never initializes. Total demo loss.
- **Files:** `addin/src/taskpane/taskpane.html:34`, `addin/dist/taskpane.html`
- **Solution:** Download `office.js` into `addin/dist/`, point the script tag at it. `webpack.config.js:24-27` already preserves it across rebuilds.
- **Effort:** 20 minutes. **Demo impact: eliminates a fatal single point of failure.**

### C5. Make the add-in buildable off this machine
- **Problem:** Hardcoded `C:/Users/kalsa/.office-addin-dev-certs/*` breaks `npm start` *and* `npm run build` elsewhere.
- **Files:** `addin/webpack.config.js:88-93`
- **Solution:** Resolve from `os.homedir()`, and guard the read so production builds do not require certificates at all.
- **Effort:** 15 minutes. **Demo impact: enables a backup machine.**

## 🟠 High Priority

### H1. Correct the README and summary claims
- **Files:** `README.md`, `HACKATHON_SUMMARY.md`
- **Solution:** Replace "mypy clean / ruff clean / 96% coverage / 2,394 passing" with measured figures (3 mypy, 314 ruff, 88%, 2,275 passing + 1 failing), or fix the underlying issues first. Resolve the ADR-006 contradiction (README:71 vs 83-85). Understate and deliver.
- **Effort:** 1 hour. **Demo impact: removes the easiest way for a judge to lose trust.**

### H2. Add a "Run the demo" section to the README
- **Problem:** No documented path from clone to working Word add-in.
- **Solution:** Prerequisites (Node 18+, Python 3.12, `npx office-addin-dev-certs install`), daemon start, `npm start`, manifest sideloading, a sample Tibetan paragraph, and what to click.
- **Effort:** 1 hour. **Demo impact: a judge can self-serve.**

### H3. Fix `requirements.lock`
- **Problem:** `fastapi` and `uvicorn` are declared dependencies but absent from the lock; README setup produces a broken environment.
- **Files:** `requirements.lock`, `pyproject.toml:31-32`
- **Solution:** Regenerate with `pip-compile`. Document `pip install -e ".[ai,data]"` for torch/pyarrow.
- **Effort:** 15 minutes.

### H4. Fix the failing test
- **Files:** `src/teea/plagiarism/fingerprinting.py:157`, `tests/plagiarism/test_fingerprinting.py:15-17`
- **Solution:** Decide the contract. Preferred: restore the short-text guard (`if len(normalized) < kgram_size: return normalized, frozenset()`) — adaptive `k` harms precision. Otherwise update the test.
- **Effort:** 30 minutes. **Demo impact: green suite.**

### H5. Green the CI pipeline
- **Solution:** `ruff check --fix` clears 34 mechanically; most of the remaining 163 E501 are long test lines. Fix the 3 mypy errors in `endpoints.py` with a real `None` guard (also closes BUG-11). Fix the 15 eslint errors.
- **Effort:** 3–4 hours. **Demo impact: "all checks passing" is a claim judges verify.**

### H6. Remove debug instrumentation
- **Files:** `WordDocument.ts:127-142`, `useDocumentAnalysis.ts:85-86`, `useSuggestionEngine.ts:145-147`
- **Effort:** 15 minutes. **Demo impact: DevTools looks professional; stops logging document text.**

### H7. Add the missing ribbon icons
- **Files:** `addin/manifest.xml:25,26,106-108`
- **Effort:** 30 minutes.

### H8. Eagerly warm TiBERT and pin it offline
- **Problem:** Lazy load fires on the first spell-check; loads from the Hub with no `local_files_only`.
- **Files:** `src/teea/engine.py:76`, `src/teea/ai/tibert_engine.py:102`, `start_daemon.py`
- **Solution:** Pass `local_path`/`local_files_only`, and trigger one warm-up inference during startup so the cost lands behind the "starting daemon" message.
- **Effort:** 1 hour. **Demo impact: removes a mid-demo stall and a network dependency.**

## 🟡 Medium Priority

### M1. Point Stage 15 at the real verb resource
`nlp/verb_lexicon.py:16` → use `verb_frames.json` (1,877 lemmas) instead of the 11-verb file. **Effort:** 2–3 hours. Turns a nominal feature into a real one.

### M2. Invoke the Sanskrit validator
`grammar.py:78` imports it and never calls it. Either wire it into `examine()` or drop the import and the "Complete" claim. **Effort:** 1–2 hours.

### M3. Expand or reframe the collocation engine
Either compute real MI/t-test from `bocorpus_ngrams.json` (the data is present), or restate Stage 14 honestly as a curated rule set. **Effort:** 4–8 hours to compute; 15 minutes to reframe.

### M4. Fix the dead grammar branches
`contextual_engine.py:194,213` — duplicated tuple literals and a branch unreachable after `strip()`. Audit the other 40 `B005` sites. **Effort:** 2 hours.

### M5. Cache the vocabulary maximum
`corpus/repository.py:110` recomputes `max(self.vocabulary.values())` over 178,452 entries per call. **Effort:** 10 minutes.

### M6. Replace the tautological test
`test_spelling_enhanced.py:128` and the duplicated dict key at line 114. **Effort:** 20 minutes.

### M7. Checkpoint the WAL / bound the index build
`index_builder.py` — add periodic `wal_checkpoint(TRUNCATE)`, set `journal_mode`/`synchronous` explicitly, and bound the ingest. Also fix `daemon.py:99-101`'s unbounded RAM load. **Effort:** 3–4 hours.

### M8. Poll for readiness in the launcher
`launch_all.bat:11` — replace `timeout /t 2` with a `/health` poll. **Effort:** 20 minutes.

## 🟢 Nice to Have

- **G1.** Clean the repository root: delete `PROJECT_TREE.txt` (12 MB), the ~14 scratch text files, the stray root `test_*.py`/`try.py`/`debug_*.py`, the duplicate `bandit_*.json`, `scratch/`, and the `repo/` duplicate. Consolidate twelve audit documents into one. **Effort:** 1 hour. Large first-impression payoff.
- **G2.** Commit the untracked plagiarism sources (`chunking.py`, `index_builder.py`, `PlagiarismPanel.tsx`, `usePlagiarism.ts`, `PlagiarismBridge.ts`) and their tests — they are absent from a fresh clone.
- **G3.** Add tests for `transport/http_server.py` (25% coverage) once it becomes the launched server.
- **G4.** Type `suggestionAdapter.ts` properly and pin the wire contract to one shape.
- **G5.** Unify terminology: one word for the backend process.
- **G6.** Delete or wire up `local_ui/` — currently reachable only via `teea serve`, which the launcher never starts.
- **G7.** Remove the unused 417 MB `TiBERT/model.safetensors`, or complete it with `config.json` + tokenizer files and point `local_path` at it.

---

# Overall Scores

| Category | Score | Reasoning |
| --- | :-: | --- |
| **Architecture** | **8.5** / 10 | Genuinely excellent layering, mechanically enforced. Nineteen ADRs with real rationale. Loses points for three competing backends, three plagiarism construction sites, a dead `TEEADaemon`, and a demo entry point reaching into private attributes. |
| **Feature Completeness** | **5.5** / 10 | Stages 02–12 are complete and corpus-backed. Stages 14–16 are nominal. The AI tab is entirely mocked. Plagiarism is complete as an algorithm and non-functional as a feature. |
| **NLP Quality** | **6.5** / 10 | Strong Unicode handling, a real HMM tagger, the TiBERT `Mn` fix, and thousands of corpus-derived entries. Undercut by a "statistical" collocation engine that computes no statistics and validators backed by 11-entry files. |
| **Performance** | **6.5** / 10 | Fast test suite, small bundle, sensible caps. Loses points for an O(n) scan on the spell-check hot path, TiBERT lazy-loading into the first user interaction, an unbounded index load, and a 59 GB WAL. Headline benchmarks unverified. |
| **User Experience** | **5.0** / 10 | The task pane shell is the best-executed part of the product. But two of three panels error out, the Assistant returns the user's own text, the ribbon icon is missing, and DevTools is full of instrumentation. |
| **Demo Readiness** | **3.5** / 10 | The single lowest score, and the one that matters most today. The documented launch path exercises the least capable backend; two panels fail on first click; there is no documented way to start the demo; and it cannot run on a second machine. |
| **Documentation** | **6.0** / 10 | Genuinely excellent architectural writing — and the headline quality claims are false, the setup instructions produce a broken environment, there is no demo guide, twelve audit documents contradict each other, and the README contradicts itself on ADR-006. |
| **Maintainability** | **7.0** / 10 | Strict typing, high coverage, enforced boundaries, clear docstrings. Reduced by 314 lint errors, a tautological test, dead imports marking dead features, and heavy root-directory debris. |
| **Innovation** | **8.5** / 10 | A serious Tibetan writing assistant is a real gap and genuinely hard. The `do_lower_case` insight, dual char/byte offsets, corpus-derived linguistic resources, and the offline microkernel design are all legitimately novel work. |
| **Overall Hackathon Readiness** | **5.4** / 10 | Excellent foundations, high ceiling, currently blocked by integration defects and overstated claims. |

---

# Final Hackathon Readiness Assessment

**Verdict: Not currently demo-ready — but closer than the score suggests, and worth fixing rather than rescoping.**

The most striking thing about this repository is the *distance between what it contains and what it does*. The plagiarism algorithm is correctly implemented and thoroughly tested — and returns nothing, because no caller populates its index. A server that routes every endpoint the task pane needs exists and is complete — and nothing starts it. A 1,877-lemma verb resource exists — and the grammar checker reads an 11-entry file instead. A composition root that wires all of this together correctly exists in `daemon.py` — and is never instantiated.

**This is a wiring problem, not a capability problem.** That is very good news four items into a fix list. C1 is a one-line change to `start_daemon.py`. C4 and C5 are twenty minutes each. C2 is an afternoon. None require new algorithms, new models, or new research. The hard work — the Tibetan Unicode handling, the pipeline, the fusion engine, the microkernel, the task pane — is already done and done well.

**What would most improve the outcome, in order:**

1. **Fix the wiring (C1, C2).** Make the demo exercise the system that actually exists. This alone moves Demo Readiness from 3.5 to roughly 7.
2. **Remove the mocks from the demo path (C3).** Hiding the Assistant tab costs thirty minutes and removes the single most trust-damaging moment available to a judge. A hidden feature is neutral; a feature that returns your own words as a "summary" is negative.
3. **Fix the claims (H1).** Every falsified claim is a compounding risk: a judge who disproves one starts testing the others. Measured, modest numbers presented confidently beat inflated ones every time — especially when the real numbers (2,275 passing tests, 88% coverage, enforced architecture tests) are genuinely impressive.
4. **Guarantee the demo runs (C4, C5, H8).** Vendor `office.js`, fix the certificate path, warm TiBERT at startup. These eliminate every environmental failure mode.
5. **Clean the root and write the demo guide (G1, H2).** Cheap, and they shape the first and last impressions.

**With the five Critical items and H1–H2 addressed — realistically one focused day — this project would present as a strong contender.** The underlying engineering genuinely merits that: mechanically-enforced architecture, a real HMM tagger over corpus-derived data, a correct fix to a subtle tokenizer bug that would silently destroy Tibetan vowels, and a Word add-in with careful offset resolution and undo support. Very little hackathon work reaches this standard.

The gap between that reality and today's demo is integration and honesty, not capability. Both are fixable in the time available.

---

## Verification checklist

- ✅ Entire repository reviewed (`src/`, `addin/`, `tests/`, `docs/`, `Data/`, `local_ui/`, `scripts/`, root scripts, CI, manifests, configuration), excluding the stale `repo/` and `.claude/worktrees/` duplicates as noted in the Scope section.
- ✅ Every major feature evaluated for implementation, integration, workflow, dependencies, edge cases, and likely runtime behaviour.
- ✅ Empirical verification performed: `pytest` (run twice, to distinguish deterministic failure from flakiness), `ruff`, `mypy`, `jest`, `tsc`, `eslint`, `coverage report`, and direct measurement of every NLP data file's entry count.
- ✅ No file modified. Nothing that opens `Data/Processed/teea.db` was executed.
- ✅ Report saved as `HACKATHON_READINESS_REPORT.md` in the repository root.
