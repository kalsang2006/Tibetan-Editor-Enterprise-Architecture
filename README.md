# TEEA — Tibetan Editor Enterprise Architecture

Production-grade, offline-first Tibetan NLP platform.

TEEA splits a Microsoft Word writing assistant across a process boundary: a
lightweight Office.js add-in handles presentation, and a native desktop daemon
performs all language computation. This repository contains the Python core of
that daemon.

See `docs/` for the authoritative specification:

| Document | Contents |
| --- | --- |
| `docs/Tibetan Enterprise Architecture.html` | Software Requirements Specification (v5.1) |
| `docs/System Design Diagram/High_Level_Architecture.html` | Figure 1 — layer boundaries |
| `docs/System Design Diagram/Component_Diagram.html` | Figure 2 — UML component breakdown |
| `docs/System Design Diagram/…Data Flow.html` | Figure 3 — Level-1 DFD |
| `docs/System Design Diagram/Language Processing Pipeline.html` | Figure 5 — the 12-stage NLP pipeline |
| `docs/Project Resources.txt` | Authoritative dataset and model sources |
| `docs/ARCHITECTURE_DECISIONS.md` | ADR-001…019 — resolved ambiguities and rationale |
| `docs/HANDOFF.md` | Engineering handoff: state, decisions, remaining work |

---

## Implementation status

The Language Processing Pipeline (Figure 5) defines twelve stages. Stages are
built one complete module at a time, and each is verified before the next
begins.

| Stage | Module | Status |
| --- | --- | --- |
| 02 Unicode Normalization | `nlp.tokenization.normalization` | **Complete** |
| 03 Document Cleaning | `nlp.tokenization.normalization` | **Complete** (ADR-001) |
| 04 Sentence Segmentation | `nlp.segmentation` | **Complete** |
| 05 Word Tokenization | `nlp.tokenization.tibert` | **Complete** (TiBERT-backed) |
| — Syllable segmentation (supporting) | `nlp.tokenization.syllable` | **Complete** |
| 06 Morphological Analysis | `nlp.morphology` | **Complete** (rule-based) |
| 07 Part-of-Speech Tagging | `nlp.postagging` | **Complete** (corpus-derived HMM) |
| 08 Structural Dependency Mapping | `nlp.dependency` | **Complete** (rule-based) |
| 09 Named Entity Recognition | `nlp.ner` | **Complete** (untyped spans, ADR-011) |
| 10 Terminology Recognition | `nlp.terminology` | **Complete** (glossary + user dictionary) |
| 11 Semantic Analysis | `nlp.semantics` | **Complete** (symbolic graph, ADR-013…015) |
| 12 Immutable Document Snapshot | `nlp.snapshot` | **Complete** (incremental, ADR-016) |
| 13 Structural Syllable Validator | `nlp.structural_validator` | **Complete** (hard-fail orthographic rules) |
| 14 Semantic Collocation & Malapropism Engine | `nlp.collocation` | **Complete** (MI & t-test semantic proofreading) |
| 15 Verb Lexicon & Transitivity Validator | `nlp.verb_lexicon` | **Complete** (valency, transitivity & tense checking) |
| 16 Sanskrit Transliteration Validator | `nlp.sanskrit` | **Complete** (Sanskrit transliterated stacks) |
| 01 Raw document input | — | No code: the add-in supplies the text |

**Figure 5 is complete.** All twelve stages are implemented, and
`teea.nlp.snapshot.LanguageServerSnapshotBuilder` is the single entry point the
daemon calls.

All higher-layer components are also built and tested:

| Component | Module | Specification | Status |
| --- | --- | --- | --- |
| Structural Syllable Validator | `teea.nlp.structural_validator` | Classical Orthography Hard-Fail Rules | **Complete** (Rule-based $O(n)$) |
| Suggestion Fusion Engine | `teea.fusion` | Figure 7, FR-7 | **Complete** (ADR-017) |
| Plugin Runtime | `teea.plugins` | Figures 1, 2, 9; FR-5, NFR 5.3 | **Complete** (ADR-018) |
| AI Runtime & Capability Registry | `teea.ai` | Figure 6; SRS 3.3, FR-6 | **Complete** (ADR-019) |
| Local IPC layer | — | Figures 1, 3; SRS 2.1, FR-1/2/8 | **Complete** (147 tests, 100% coverage) |
| Plagiarism subsystem | — | Figure 8; SRS 3.4, FR-9 | **Complete** (Robust Winnowing, 9+9 test files) |
| Office.js add-in | — | Figures 1, 2 | **Complete** (React/TypeScript, 263 tests, local office.js) |
| Daemon Entrypoint | — | SRS 2.1 | **Complete** (CLI, daemon, workflow, serve_http) |
| Core Test Suite | `tests/` | Pipeline & Subsystem Verification | **Complete** (2,265 passing tests) |

The Persistence layer (`teea.persistence`) holds four facets of Figure 2's
**Dictionary Repository**, stated as separate protocols for Interface Segregation:

| Protocol | Implementation | Data | Consumer |
| --- | --- | --- | --- |
| `DictionaryRepository` | `InMemoryDictionaryRepository` | `pos_model.json` (126 KB) | Stage 07 |
| `GazetteerRepository` | `InMemoryGazetteer` | `proper_nouns.json` (109 KB) | Stage 09 |
| `TerminologyRepository` | `InMemoryTerminology` | `terminology.json` (25 KB) | Stage 10 |
| `VerbLexiconRepository` | `InMemoryVerbLexicon` | `verb_frames.json` (570 KB) | Stage 11 |

All are in-memory and read-only, each raising `ConfigurationError` on missing or
malformed data and each with an `lru_cache`d `default_*()` accessor. The SQLite
store, LMDB cache and fingerprint index Figure 2 also lists belong to features
that do not exist yet (ADR-006).

**Stage 11 is the symbolic Semantic Graph.** Figures 1, 2 and 3 place a "Semantic
Graph" inside the Language Server; Figures 6, 7 and 9 place embeddings, semantic
vectors and similarity scores inside the **AI Runtime**, which is a different
component this repository does not implement. Stage 11 therefore performs no
inference and loads no model — see ADR-013.

Stage 06's affix inventory is **derived from data, not hand-authored**: the
part-of-speech annotated Milarepa corpus in the authoritative data repository
supplies 60,544 tagged tokens, of which 16,984 are grammatical morphemes. Measured
against those gold annotations the analyzer reaches **80.2% recall / 92.1%
precision**, rising to **98.7% recall** once the fused `ས`/`ར` it explicitly
declines to split are excluded — those need the Dictionary Repository that Figure 2
places in the Persistence layer.

Architectural ambiguities found during implementation are resolved and recorded in
**[docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md)** (ADR-001 to
ADR-019). That file also fixes the **document precedence order**: SRS v5.1 and the
System Design Diagrams are authoritative. A superseded v1.0 hackathon spec that
described a cloud system has been removed from the repository (ADR-002).

Stage 03 is owned by the normalization module rather than a separate package: it is
an *activity* in Figure 5's pipeline view but not a *component* in Figure 1's or
Figure 2's component views. Its "Standardize punctuation" bullet is deliberately
deferred — see ADR-001 before implementing it.

Cross-cutting foundation (`teea.core`) — configuration, structured logging,
error taxonomy and shared domain types — is complete and is the only dependency
the NLP layer has.

### Dependency direction

The dependency graph is strictly one-directional and acyclic:

```
teea.core                        ← no internal dependencies
teea.persistence                 ← core only (storage sits beneath language)
  ↑
teea.nlp.segmentation  (Stage 4) ← core only
teea.nlp.tokenization  (Stages 2, 3, 5)
  ↑
teea.nlp.morphology    (Stage 6) ← core + tokenization (syllables)
  ↑
teea.nlp.postagging    (Stage 7) ← core + morphology + persistence
  ↑
teea.nlp.dependency    (Stage 8) ← core + postagging
  ↑
teea.nlp.ner           (Stage 9) ← core + dependency + persistence
teea.nlp.terminology   (Stage 10) ← core + dependency + persistence
  ↑
teea.nlp.semantics     (Stage 11) ← core + dependency + ner + terminology + persistence
  ↑
teea.nlp.snapshot      (Stage 12) ← core + every stage above (composition root)

teea.fusion                       ← core only; never imports teea.nlp
  ↑
teea.plugins                      ← core + nlp.snapshot + fusion (the microkernel)

teea.ai                           ← core only; the inference orchestrator, no model
```

These properties are enforced mechanically by `tests/test_architecture.py`, not
merely documented:

* **No stage may import a later stage.** Figures 1 and 5 both mandate
  one-directional flow, so each stage consumes its predecessors and nothing else.
  The rule is parametrized over the whole Figure 5 order, and a companion test
  fails if a new pipeline package is added without being listed, so no stage can
  quietly escape it.
* **`persistence` must not import `nlp`.** The Language Server reads from storage;
  storage knows nothing about language processing.
* **`fusion` and `nlp` must not import each other.** Figure 3 routes plugin
  results into the Fusion Engine, not parsed text; fusion is arithmetic over
  document ranges, so tying it to the analysis chain would put the whole NLP
  layer on the critical path of every keystroke.
* **Nothing imports `plugins`.** SRS 2.1 calls the product a microkernel-based
  plugin engine: the runtime composes the layers below it, and both must stay
  usable and testable without it.
* **`ai` depends on `core` alone, and nothing below it imports `ai`.** Figure 6's
  runtime is domain-agnostic infrastructure a plugin calls; ADR-013 kept the
  analysis chain owing nothing to a model, so the Language Server, the Fusion
  Engine and persistence must all build and test without an AI Runtime.
* **Shared character classes are defined exactly once** in `core.types`
  (`SHAD_CHARS`, `TSHEG_CHARS`, `LINE_BREAK_CHARS`). A local copy is how two
  stages would silently drift apart.

Within `tokenization`, `models` sits *below* `tibert`: the surface form of a
subword piece is supplied by the producer rather than recomputed in the model
layer, which keeps the graph acyclic. The NLP layer never imports from higher
layers (AI Runtime, Plugin Runtime, Suggestion Fusion Engine, IPC, add-in).

---

## Requirements

* **Python 3.12+**
* No GPU or `torch` required. The TiBERT *tokenizer* is a WordPiece vocabulary
  of 29,965 entries (verified against the published model); a deep-learning
  backend is introduced only by the future embeddings / inference module.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install pinned dependencies for reproducible builds
pip install -r requirements.lock

# Install the package in editable mode without re-resolving dependencies
pip install -e "." --no-deps
```

## Running the test suite

```powershell
python -m pytest
```

**2,131 hermetic unit tests**, all running offline in under 30 seconds:

| Module | Focus |
| --- | --- |
| `tests/test_errors.py` | Error taxonomy and stable `ErrorCode` contract |
| `tokenization/test_normalization.py` | Stage 2, validated against `unicodedata` as an oracle |
| `tokenization/test_syllable.py` | Syllable segmentation, char/byte span ground truth |
| `tokenization/test_tibert_tokenizer.py` | Wrapper orchestration, both offset-resolution paths |
| `tokenization/test_edge_cases.py` | Model invariants and adversarial input |
| `segmentation/test_models.py` | Stage 4 value-object invariants |
| `segmentation/test_sentence.py` | Stage 4 boundary rules and span ground truth |
| `segmentation/test_pipeline.py` | Stage 2 → 4 → 5 composition and offset arithmetic |
| `morphology/test_models.py` | Stage 6 value-object invariants |
| `morphology/test_particles.py` | Corpus-derived inventory integrity |
| `morphology/test_analyzer.py` | Stage 6 rules plus gold-annotation evaluation |
| `postagging/test_models.py` | Stage 7 value objects and the Figure 5 class mapping |
| `postagging/test_tagger.py` | Viterbi contract, held-out evaluation, NFR 5.1 latency |
| `persistence/test_dictionary.py` | Dictionary Repository loading and error paths |
| `dependency/test_models.py` | Stage 8 tree invariants: one root, acyclic, connected |
| `dependency/test_parser.py` | Attachment rules and structural guarantees |
| `dependency/test_pipeline.py` | Stages 2 → 8 composition and offset arithmetic |
| `ner/test_models.py` | Stage 9 entity-span invariants |
| `ner/test_recognizer.py` | Matching rules plus gold-annotation evaluation |
| `persistence/test_gazetteer.py` | Gazetteer tiers, lookup and error paths |
| `terminology/test_terminology.py` | Stage 10 repository, models, recogniser, user dictionary |
| `persistence/test_verbs.py` | Verb lexicon loading, frames, error paths, payload integrity |
| `semantics/test_models.py` | Stage 11 graph invariants: ordering, spans, acyclicity, JSON round-trip |
| `semantics/test_analyzer.py` | Role rules, intent classification, anchoring, pathological input |
| `semantics/test_pipeline.py` | Stages 2 → 11 composition, offsets, concurrency, measured quality |
| `snapshot/test_models.py` | Stage 12 snapshot invariants, the FR-4 hash, document coordinates |
| `snapshot/test_builder.py` | Dependency injection, incremental reuse counted at the stage boundary |
| `snapshot/test_pipeline.py` | Stages 2 → 12 composition, deep immutability, concurrency |
| `test_architecture.py` | Executable ADR constraints (layering, acyclicity, offline-only) |
| `tokenization/test_tibert_integration.py` | The real model (`-m integration`, excluded by default) |

Correctness claims are checked against the real corpus rather than asserted: every
token and syllable span is re-derived by slicing the source string *and* its UTF-8
encoding, so the 3-bytes-per-codepoint divergence of Tibetan is genuinely
exercised.

Tests are hermetic: the TiBERT backend is injected through a loader callable, so
the unit suite runs against `tests/fakes/FakeBackendTokenizer` with **no model
download and no network access**. Tests requiring the real model are marked
`integration` and are not part of the default run.

> **Windows note.** The default console codepage (cp1252) cannot encode Tibetan.
> Any script that *prints* Tibetan must run with `PYTHONIOENCODING=utf-8`, or it
> will raise `UnicodeEncodeError`. This affects ad-hoc scripts only — the test
> suite and all library file I/O specify `encoding="utf-8"` explicitly.

## Measured performance

Full pipeline (Stages 2 → 4 → 5 → 6 → 7) against the **real** TiBERT model on the
241,882-character Milarepa text, 5,885 sentences, 65,925 morphemes.

| Property | Measured | Requirement |
| --- | --- | --- |
| Incremental re-parse, p50 | 0.68 ms | — |
| Incremental re-parse, p99 | **2.56 ms** | **NFR 5.1: < 50 ms** ✅ (20× headroom) |
| Over budget | 0 / 400 samples | — |
| End-to-end throughput | ~44k chars/s | — |
| Incremental vs full re-parse | **2,854× faster** | the reason FR-4 exists |
| Concurrency (8 threads) | identical to serial | components claim thread safety |
| Retained document analysis | 142 MiB (2.3 KiB/morpheme) | immutable snapshot, Figure 5 |
| Steady-state leak | 0.6 KiB / 2,000 analyses | — |
| Cold start (TiBERT load) | ~11 s warm cache | see below |

Adding Stages 8 → 11, over the same 5,885 sentences:

| Property | Measured | Requirement |
| --- | --- | --- |
| Stages 6 → 10, p50 / p99 | 0.555 / 2.841 ms | — |
| **Stage 11 alone**, p50 / p99 | **0.156 / 0.604 ms** | — |
| **Stages 6 → 11**, p50 / p99 | **0.784 / 3.572 ms** | **NFR 5.1: < 50 ms** ✅ (14× headroom) |
| Over budget | **0 / 5,885 sentences** | — |
| Stage 11 share of the chain | 18.3% | — |
| Throughput (Stages 6 → 11) | ~40k chars/s | — |
| Verb lexicon cold start | 47 ms | vs ~11 s for TiBERT |
| Retained per graph | 2.37 KiB/node | — |
| Steady-state leak | 2.1 KiB / 1,000 graphs | — |
| Concurrency (8 threads) | identical to serial | pinned by test |

One optimization was made on measured evidence and kept. The case-particle lookup
was originally a forward scan per node, which is quadratic on a long run of
modifiers: **968 ms for a 3,200-adjective sentence**, breaching NFR 5.1. Replacing
it with a single backward pass that tabulates the answer for every position gives
**84 ms** — an 11.5× improvement, flat per-item cost, and **bit-identical output**
across all 5,885 sentences (every role and evidence count unchanged). The naive
scan is retained in the test suite as a correctness oracle rather than the
optimization being defended by a timing assertion, which this project has found
to be flaky.

Pathological input was exercised too — empty, whitespace-only, punctuation-only,
24,000-character single sentences, delimiter-free runs, mixed script, embedded
NUL and zero-width characters, astral-plane emoji, and CRLF documents. All
complete without error and with zero structural violations.

Two findings from this measurement are worth knowing:

* **Cold start is dominated by loading TiBERT (~27 s).** The daemon must load the
  model once at startup, never per request. Set `HF_HUB_OFFLINE=1` for air-gapped
  deployments so the loader does not attempt hub revalidation.
* **Out-of-vocabulary text was 250× slower than Tibetan and breached NFR 5.1.**
  An OOV surface has no observed emissions, so Viterbi's candidate set becomes the
  whole tagset and the cost is |tags|² per morpheme. Recomputing the transition
  normaliser inside that loop cost 3.8 ms/morpheme, so a short phrase of embedded
  Latin — ordinary in Tibetan academic writing — exceeded the budget at just 14
  morphemes. The transition log table is now precomputed at construction: 0.68
  ms/morpheme, a 5.6× improvement, with **bit-identical output** (held-out
  accuracy unchanged at 73.21% / 83.49%). Guarded by a regression test.

## Static checks

```powershell
python -m mypy src          # strict type checking
python -m ruff check src tests  # linting
```

---

## Docker

A production Dockerfile is provided for containerised deployments:

```powershell
# Build the image
docker build -t teea-daemon:latest .

# Run the daemon
docker run --rm -v teea-data:/data teea-daemon:latest teea health

# Or use Docker Compose
docker compose up -d
```

The image uses a multi-stage build:
- **base** — Python 3.12-slim with SentencePiece runtime
- **build** — Installs pinned deps from `requirements.lock` and builds a wheel
- **runtime** — Minimal image containing only the installed package

See `docker-compose.yml` for a full development profile with volume mounts
and healthcheck configuration.

---

## Configuration

Every setting is overridable by environment variable, prefixed `TEEA_`, with
`__` as the nesting delimiter. Configuration is validated eagerly — an invalid
value raises `ConfigurationError` at startup rather than failing deep inside
model loading.

```powershell
$env:TEEA_LOG_LEVEL = "DEBUG"
$env:TEEA_LOG_JSON = "false"
$env:TEEA_TOKENIZATION__MODEL_CACHE_DIR = "D:\teea\models"
$env:TEEA_TOKENIZATION__NORMALIZATION_FORM = "NFKC"
```

Model weights are cached under `~/.teea/models` by default and are **never**
committed to source control. For air-gapped deployments set
`TEEA_TOKENIZATION__MODEL_LOCAL_PATH` to a pre-provisioned model directory.

## Usage

```python
from teea.core import configure_logging, load_settings
from teea.nlp.tokenization import SyllableSegmenter, TiBERTTokenizer

settings = load_settings()
configure_logging(level=settings.log_level, json_output=settings.log_json)

tokenizer = TiBERTTokenizer(settings.tokenization)
encoded = tokenizer.encode("བཀྲ་ཤིས་བདེ་ལེགས།")

encoded.ids                # model input
encoded.content_tokens     # tokens excluding [CLS]/[SEP]
encoded.has_unknown        # out-of-vocabulary diagnostic
encoded.token_at_char(5)   # offset → token, for suggestion range mapping

# Orthographic syllables are computed independently of the subword tokenizer.
SyllableSegmenter().segment(encoded.normalized)
```

### Invoking local intelligence

`teea.ai` implements Figure 6: a capability-oriented inference orchestrator a
plugin calls to obtain grammar, translation, semantic features and the rest. It
ships the orchestration — registries, lifecycle, routing, an LRU memory budget,
health — and **no model**. Actual loading and execution sit behind the
`InferenceEngine` protocol, the adapter SRS 3.3 mandates; no concrete engine ships,
because no model exists to run (ADR-019).

```python
from teea.ai import CapabilityKind, InferenceRequest, LocalAIRuntime, ModelDescriptor

runtime = LocalAIRuntime(engine)          # engine is the injected adapter
runtime.register(ModelDescriptor(
    name="tibert", version="1", provides={CapabilityKind.SEMANTIC_FEATURES},
))
runtime.start()

response = runtime.infer(InferenceRequest(
    capability=CapabilityKind.SEMANTIC_FEATURES, inputs={"text": sentence},
))
response.produced_by       # "tibert:1" — which model, which version
runtime.health()           # registered, loaded, memory used
runtime.stop()             # unloads every resident model
```

Routing is version-aware (a newer model takes over an unqualified request, FR-6),
a memory budget evicts the least-recently-used model when set, and every failure
raises a typed `TEEA-3xxx` error. Because the Plugin Runtime preserves a
`TEEAError`'s code when it captures a plugin's exception, a model failure inside a
plugin reaches the add-in as an AI-runtime code rather than a generic crash.

### Running feature plugins

`teea.plugins` implements the microkernel SRS 2.1 describes, and closes Figure 3's
P4 → P5 → P6 chain: a `DocumentSnapshot` goes in, and the suggestions the Fusion
Engine consumes come out.

```python
from teea.plugins import SupervisedPluginRuntime

runtime = SupervisedPluginRuntime(my_plugins)      # names read once, here
results = runtime.dispatch(snapshot)

results.suggestions   # everything produced, ready for the Fusion Engine
results.is_healthy    # did every plugin complete?
results.failures      # what the ones that did not reported, with a TEEA-2xxx code
```

A plugin implements two members — `name` and `examine(snapshot)` — and nothing
else. **A plugin that raises never reaches the caller** (NFR 5.3): the fault is
recorded and every other plugin's result is unaffected. A plugin that attributes
its output to a different plugin is rejected the same way, because the Fusion
Engine weights suggestions by that attribution.

Dispatch is sequential by default. Passing `executor=` a `concurrent.futures`
pool satisfies Figure 5's concurrent consumption of the shared snapshot; results
are ordered by plugin name either way, so the choice cannot change what the user
sees. No concrete plugin ships here — see ADR-018.

### Fusing plugin suggestions

`teea.fusion` implements Figure 7. It takes what the feature plugins recommend —
possibly contradicting each other, possibly overlapping, arriving in any order —
and returns one ranked package plus a conflict-free document patch (FR-7).

```python
from teea.fusion import PriorityRankedFusionEngine

engine = PriorityRankedFusionEngine(plugin_weights={"spell": 1.0, "style": 0.6})
unified = engine.fuse(document, plugin_outputs)

unified.suggestions       # ranked: priority first, then weighted confidence
unified.edits             # those that rewrite the document
unified.advisories        # those that only annotate, e.g. plagiarism warnings
unified.patch.apply()     # the rewritten document
unified.rejected          # everything discarded, each with its reason
```

Fusion is deterministic and **order-independent**: plugins report concurrently,
so the same suggestions in a different arrival order fuse to the same result. It
is also total — a plugin emitting nonsense is filtered, never fatal (NFR 5.3).
Confidence adjustment by the AI Runtime, which Figure 7 also shows, is absent
because that component does not exist here; see ADR-017.

### The whole Language Server, in five lines

Stage 12 is the entry point the daemon calls. It wires Stages 04–11 together and
returns one immutable snapshot that every plugin reads concurrently.

```python
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.nlp.tokenization import TextNormalizer

normalizer = TextNormalizer(form="NFC", collapse_whitespace=False)  # Stage 02
builder = LanguageServerSnapshotBuilder()                           # Stages 04–11

snapshot = builder.analyze(normalizer.normalize(document))          # Stage 12
snapshot.num_sentences, snapshot.num_entities, snapshot.num_semantic_nodes
snapshot.analysis_at_char(cursor)             # what is the user editing?
snapshot.analyses_overlapping(start, end)     # what did this edit invalidate?

# After the user types, re-analyse only what changed (FR-4).
snapshot = builder.reanalyze(snapshot, normalizer.normalize(edited))

# Spans inside an analysis are sentence-relative; translate before addressing
# the document, which is what the add-in needs to place a suggestion.
analysis = snapshot.analyses[0]
where = analysis.document_span(analysis.graph.nodes[0].span)
```

The builder deliberately does **not** normalize. Stage 02 can change the length of
the text, so normalizing inside it would produce offsets addressing a string the
caller never passed (ADR-016).

### The stages underneath, Stages 02 → 11

Every stage takes its collaborators as keyword-only constructor arguments
defaulting to `None`, so any of them can be substituted without touching the
others. Each also exposes a `runtime_checkable` Protocol, which is what SRS §3.3's
hot-swapping requirement asks for.

```python
from teea.nlp.dependency import TibetanDependencyParser
from teea.nlp.morphology import TibetanMorphologicalAnalyzer
from teea.nlp.ner import TibetanEntityRecognizer
from teea.nlp.postagging import HmmPosTagger
from teea.nlp.segmentation import TibetanSentenceSegmenter
from teea.nlp.semantics import SemanticRole, TibetanSemanticAnalyzer
from teea.nlp.terminology import GlossaryTerminologyRecognizer
from teea.nlp.tokenization import TextNormalizer

normalizer = TextNormalizer(form="NFC", collapse_whitespace=False)  # Stages 02–03
segmenter = TibetanSentenceSegmenter()                              # Stage 04
morphology = TibetanMorphologicalAnalyzer()                         # Stage 06
tagger = HmmPosTagger()                                             # Stage 07
parser = TibetanDependencyParser()                                  # Stage 08
ner = TibetanEntityRecognizer()                                     # Stage 09
terminology = GlossaryTerminologyRecognizer()                       # Stage 10
semantics = TibetanSemanticAnalyzer()                               # Stage 11

for sentence in segmenter.segment(normalizer.normalize(document)).sentences:
    tree = parser.parse(tagger.tag(morphology.analyze(sentence.text)))
    graph = semantics.analyze(
        tree,
        entities=ner.recognize(tree),
        terms=terminology.recognize(tree),
    )

    graph.predicates[0].lemma          # the dictionary headword, not the stem
    graph.arguments_of(0)              # who plays which role, with its evidence
    graph.of_role(SemanticRole.AGENT)  # the agents
    graph.intent.mood                  # asks, commands, or states
    graph.node_at_char(12)             # offset → concept, for suggestion placement
    graph.model_dump_json()            # ready for the IPC boundary
```

Stages 09 and 10 run *before* Stage 11 for a reason. Tibetan has no word
delimiter, so Stage 06 emits syllables and Stage 08 attaches each one separately:
a four-syllable personal name reaches Stage 11 as four unrelated arguments of the
same verb. Stage 09 is what says those syllables are one name. Over the reference
corpus that grouping collapses 2,374 fragments into 1,250 whole concepts.

### Why syllables *and* subword tokens

TiBERT's SentencePiece pieces are statistical subwords; they do not align with
orthographic syllables. Spell checking, dadrag handling and rule-based
diagnostics are all defined at the syllable level, so the platform computes
syllable structure deterministically from the text as first-class metadata,
complementary to — not derived from — the subword tokenization.

---

## Data and models

Per `docs/Project Resources.txt`, these are the authoritative sources and must
not be substituted:

* **Model** — TiBERT, `CMLI-NLP/TiBERT` on Hugging Face.
* **Datasets** — <https://github.com/kalsang2006/Data>

Test fixtures in `tests/data/` are derived from that repository so the suite
runs against authentic classical Tibetan rather than invented strings:

| Fixture | Derived from | Contents |
| --- | --- | --- |
| `mila_sentences.txt` | `Data/Texts/mila-horizontal.txt` | 60 Milarepa sentences, POS tags stripped, split at the shad |
| `lexicon_sample.json` | `Data/Lexicons/classical-lexicon.txt` | 120 entries: bare syllables, tsheg-final particles, punctuation |

Shipped payloads under `src/teea/persistence/data/` are likewise derived from that
repository, each carrying its own provenance record:

| Payload | Derived from | Contents |
| --- | --- | --- |
| `pos_model.json` | `Data/Texts/mila-horizontal.txt` | 77-tag emission and transition statistics |
| `proper_nouns.json` | corpus `n.prop` + `Data/Lexicons/classical-lexicon.txt` | 2,767 proper nouns, two tiers |
| `terminology.json` | `Data/BDRC` + the classical lexicon | 871 Buddhist technical terms |
| `verb_frames.json` | `Data/tibetan-nlp-lexicon-of-tibetan-verb-stems-802ef02` | 1,877 verb lemmas, 11,711 stem surfaces, 703 argument frames |

The verb lexicon is the digital edition of Hill, Nathan W. (2010) *A Lexicon of
Tibetan Verb Stems as Reported by the Grammatical Tradition* — the same
repository directory family whose Constraint Grammars Stage 08 derives its
relation inventory from (ADR-009). Its two source files are joined positionally,
which the builder verifies against a third, independent file: **1,830 of 1,831**
entries agree, and the build aborts below 99%.

Its coverage of the reference corpus, stated both ways because the two differ:
over the **13,760 gold tokens tagged `v.*` or `n.v.*`**, the lexicon holds the
surface of **95.2% of occurrences** and **89.2% of distinct types**. Both count
lookup-key presence, not lemma correctness — no gold lemma annotation exists.
Measured end to end on the *syllables* the pipeline actually emits, **74.6% of
predicate nodes resolve to a lemma**; that is the figure describing the shipped
system. Methodology in ADR-014.

---

## Known technical debt

Open defects are tracked as **strict** `xfail` tests rather than prose, so the
marker fails loudly (`XPASS(strict)`) the moment the underlying defect is fixed
and cannot be silently forgotten.

| Item | Detail |
| --- | --- |
| `was_truncated` false positive | **Tracked by a strict xfail** (`test_exactly_maximum_length_input_is_not_reported_as_truncated`). `encode` infers `was_truncated` from `len(ids) >= max_length`, so input landing on exactly the limit is reported as truncated. This is a data-loss signal, so a false positive is not harmless. Fixing it exactly requires a design decision: (a) a second, untruncated tokenization pass to learn the true length — precise, but a performance cliff on very large inputs, which defeats the purpose of truncating; (b) extending `BackendTokenizer` with `return_overflowing_tokens`; or (c) accepting the false positive. Deliberately left open pending that call. |
| Non-breaking tsheg is not round-trippable | `Syllable.has_trailing_tsheg` is a `bool`, so the distinction between tsheg U+0F0B and non-breaking tsheg U+0F0C is discarded during segmentation. `with_tsheg()` therefore always re-emits U+0F0B. No occurrences in the current corpus, but the add-in maps suggestions onto the user's original document, where this would silently change line-breaking behaviour. |
| `_PRESERVED_CONTROLS` is unreachable by default | `_remove_controls` preserves newline and tab, but `collapse_whitespace` defaults to `True` and folds them immediately afterwards. The preservation is only observable with `collapse_whitespace=False`. Documented on the class; not incorrect, but the intent is defeated by the default construction. |
| `decode()` type error naming | A non-sequence argument to `decode()` raises `InputNotStringError`, whose name describes the encode-side contract rather than the decode-side one. Cosmetic; the error code is stable and correct. |
| Out-of-vocabulary rate | Measured 5.2% on the reference corpus with the real model; 11 of 120 rare classical lexicon forms are wholly out of vocabulary in TiBERT's 29,965-entry WordPiece vocabulary. Text containing OOV cannot round-trip through `decode`, since an `[UNK]` id records only that *something* was there. |
| Stray files (removed) | Empty `cls` and `tree` files at the repository root were deleted during v1.0 release prep. |
| Incremental cost is linear in document size (Stage 12) | An edit re-parses exactly one sentence, but the document is still re-segmented and re-hashed in full, because an edit can move every boundary after it. Measured p50: 3.0 ms at 2,000 characters, 10.2 ms at 10,000, 39.1 ms at 50,000, ~0.7 s for the 241,882-character reference text. Ordinary documents fit inside NFR 5.1 on the interactive path; a book-length one must use the background pipeline SRS 3.2 provides. |
| Cached analyses are keyed by text alone (Stage 12) | A caller that swaps a stage implementation and then calls `reanalyze` with an older snapshot would reuse analyses made by the previous configuration. Making the key configuration-sensitive would require every stage from 04 to 11 to expose a fingerprint. Documented as a caller contract instead: a snapshot belongs to the builder that produced it. See ADR-016. |
| No semantic-role gold data (Stage 11) | No role-annotated Tibetan corpus exists in the repository, so **no precision/recall/F1 is reported for Stage 11 and none should be inferred**. What is measured instead is coverage (74.6% of predicates lemmatized), evidence composition (53.0% of roles resting on a case particle or the lexicon) and the unresolved rate (1.4%). The 4,838 absolutive reclassifications are a count of *changes*, not of verified corrections; 39.5% are corroborated by a gold agentive in the same sentence, which is a lower bound and not a precision figure. Mood percentages are output distributions over one corpus, not accuracy. See ADR-014 and ADR-015 for the full methodology. Acquiring role-annotated text is the highest-value next step for this stage. |
| Copulas are not predicates (Stage 11) | Stage 08 never heads a clause with a copula, so its arguments are attached elsewhere and a Stage 11 predicate node for it would have none. Copular clauses therefore have a nominal head rather than an *is*-predicate. Correcting this is a Stage 08 change, not a Stage 11 one. |
| 47% of roles rest on structure alone (Stage 11) | Where the lexicon reports no argument frame, Stage 08's structural reading is carried through and labelled `RoleEvidence.STRUCTURE`. The share falls as lexicon coverage rises; it is reported rather than hidden. |
| Flat argument attachment (Stage 11) | Stage 08 attaches most nominals directly to the clause root, so the semantic graph inherits a wide, shallow shape. A treebank-trained parser (ADR-010) is the prerequisite for improving it. |
