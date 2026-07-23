# TEEA — Engineering Handoff

Prepared 2026-07-22, revised the same day after Stage 12 was implemented and
accepted. Read this, then `docs/ARCHITECTURE_DECISIONS.md` (the ADR file — there
is no `docs/ADR.md`), then scan the repository.

---

# Project Overview

**Project.** TEEA — Tibetan Editor Enterprise Architecture. A production-grade,
offline-first Tibetan NLP platform: the Python core of a native desktop daemon
that serves a Microsoft Word Office.js add-in across a local IPC boundary.

**Overall architecture.** Presentation (Office.js) → Local IPC → Desktop Daemon
(Language Server, Plugin Runtime, Suggestion Fusion, AI Runtime) → Persistence.
This repository implements the **Language Server** and the minimal **Persistence**
it requires. No IPC, plugin, AI-runtime or add-in code exists yet.

**Status.** Figure 5 defines a 12-stage language pipeline. **All twelve stages
are complete, tested and accepted.** Stage 01 is document input (no code): the
add-in supplies the text. The Language Server is finished; what remains is
everything *above* it — Plugin Runtime, Suggestion Fusion Engine, AI Runtime,
local IPC and the Office.js add-in — none of which exists in this repository.

**Goals.** Correctness and architectural fidelity over speed; every linguistic
resource corpus-derived, never invented; sub-50 ms interactive latency (NFR 5.1);
fully offline.

---

# Completed Stages

## Stage 02/03 — Unicode Normalization + Document Cleaning
`nlp/tokenization/normalization.py` · `TextNormalizer`

Applies a Unicode normalization form, strips control/format characters, and
optionally collapses whitespace. Owns Stage 03 as an *activity* (ADR-001).

- **Key decisions.** Controls are stripped **before** normalizing (a format
  character between combining marks blocks canonical reordering). Line breaks are
  preserved, not stripped (ADR-004).
- **Limitations.** "Standardize punctuation" (Figure 5 Stage 03 bullet 3) is
  deliberately unimplemented — folding shad variants would destroy Stage 04's
  terminator fidelity. `_PRESERVED_CONTROLS` is unobservable when
  `collapse_whitespace=True` (the default).
- **ADRs.** 001, 004.

## Stage 04 — Sentence Segmentation
`nlp/segmentation/` — `models.py`, `interfaces.py`, `sentence.py`

Splits normalized text into sentences at the shad family and at line breaks.
`TibetanSentenceSegmenter`, `SentenceSegmenter` protocol, `SegmentedText`,
`Sentence`.

- **Key decisions.** Terminator stored **verbatim**, not as a boolean, so a
  *nyis shad* stays distinguishable. Consumes already-normalized text (does not
  normalize) — matching `SyllableSegmenter`'s precedent.
- **Limitations.** Sentences do not tile the input: gaps may contain whitespace
  and discarded orphan punctuation. No content is ever dropped.
- **Results.** 5,885 sentences from the 241,882-char Milarepa text; char and byte
  span ground truth on every one.

## Stage 05 — Word Tokenization
`nlp/tokenization/` — `tibert.py`, `syllable.py`, `models.py`, `exceptions.py`,
`interfaces.py`

TiBERT-backed subword tokenization plus tsheg-based syllable segmentation.

- **Key decisions.** Backend injected through a loader callable, so the unit
  suite runs against `tests/fakes/FakeBackendTokenizer` with no model or network.
- **Limitations.** `was_truncated` is heuristic — input landing exactly on the
  limit reports as truncated. Tracked by a **strict xfail**
  (`test_exactly_maximum_length_input_is_not_reported_as_truncated`) awaiting a
  design decision; this is the only open xfail in the suite.
- **Results.** Real model: WordPiece, 29,965 entries. OOV 5.2% on the corpus;
  decode round-trips exactly on OOV-free text (14/14).
- **ADRs.** 008.

## Stage 06 — Morphological Analysis
`nlp/morphology/` — `models.py`, `particles.py`, `interfaces.py`, `analyzer.py`

Root extraction, affix recognition, inflection analysis. Inventory **derived
from** the POS-annotated corpus: 44 unambiguous + 20 ambiguous affix surfaces.

- **Key decisions.** Recognize, don't guess: ambiguous surfaces are marked
  `AMBIGUOUS` for Stage 07 rather than force-tagged. Fused `འི` is split;
  fused `ས`/`ར` deliberately are **not**.
- **Limitations.** 76% of agentive markers are the fused bare `ས`/`ར` it will not
  split — this measurably caps Stage 08's subject/object discrimination. The
  blocker (a lexicon) **now exists** (ADR-006), so this is actionable. Two
  multi-syllable particles (`ན་རེ`, `ཞེས་པ`) are unreachable by syllable lookup.
- **Results.** vs gold: **80.2% recall / 92.1% precision**; **98.7% recall**
  excluding the documented `ས`/`ར` gap, which is 94% of all misses.
- **ADRs.** 005.

## Stage 07 — Part-of-Speech Tagging
`nlp/postagging/` — `models.py`, `interfaces.py`, `tagger.py`
`persistence/dictionary.py` (Dictionary Repository)

Bigram HMM + Viterbi over syllable-level morphemes. 77-tag corpus tagset plus a
coarse `PosCategory` matching Figure 5's classes.

- **Key decisions.** Trained on **syllables**, not words — train/test unit match
  was worth 22 accuracy points (ADR-007). Stage 06's candidate categories
  constrain Viterbi for OOV surfaces. Transition log table precomputed at
  construction (NFR 5.1).
- **Results.** Held-out (Marpa, different author): **72.3% fine / 82.0% coarse**
  vs a 63.1% most-frequent-tag baseline. Ambiguity resolution 78.7%.
- **ADRs.** 006, 007.

## Stage 08 — Structural Dependency Mapping
`nlp/dependency/` — `models.py`, `interfaces.py`, `parser.py`

Rule-based dependency parsing producing a single rooted acyclic tree.
Relations follow the Universal Dependencies labels used by the repository's
Tibetan constraint grammars.

- **Key decisions.** CG3 grammars **reimplemented natively**, not executed
  (`vislcg3` is a C++ toolchain; ADR-009). Ergative-absolutive alignment: the
  absolutive is `arg2` when an agentive is present, else `arg1`.
- **Limitations.** **No UAS/LAS is reported** — no treebank exists (ADR-010).
  Only 10.8% of trees get an object, inherited from Stage 06's `ས` gap.
- **Results.** 5,885 trees / 65,925 nodes, every one single-rooted, acyclic and
  connected; 3.05% unresolved (`DEP`).
- **ADRs.** 009, 010.

## Stage 09 — Named Entity Recognition
`nlp/ner/` — `models.py`, `interfaces.py`, `recognizer.py`
`persistence/gazetteer.py` (2,767-entry proper-noun gazetteer)

Longest-match gazetteer + POS evidence over morpheme runs. Entities span internal
particles (e.g. a place name across a genitive).

- **Key decisions.** Entities are **untyped** — Figure 5 names five types but no
  data source distinguishes them (ADR-011). Two-tier gazetteer (confident vs
  corroboration-required) lifted held-out precision 35% → 58%.
- **Limitations.** No typed gazetteer, so Figure 5's five categories are
  unimplementable. Recall capped by gazetteer coverage.
- **Results.** Held-out: **P 57.8% / R 68.7% / F1 62.8%** over 1,590 gold
  entities.
- **ADRs.** 011.

## Stage 10 — Terminology Recognition
`nlp/terminology/` — `models.py`, `interfaces.py`, `recognizer.py`
`persistence/terminology.py` (871-term glossary + User Dictionary)

Longest-match over technical terms, attributing each to the shipped glossary or
the user's own dictionary.

- **Key decisions.** A glossary entry must satisfy **two independent criteria**:
  curated-lexicon headword **and** ≥15 occurrences in the BDRC Buddhist canon with
  **zero** in narrative Tibetan. Contrastive frequency alone was measured and
  rejected — its top output is scholastic register, not terminology (ADR-012).
  User Dictionary outranks the glossary.
- **Limitations.** Glossary cannot be scored — no gold term list exists. Low
  recall on narrative text is by construction and is pinned by a test.
- **Results.** 871 terms; 68 recognised in 5,885 narrative sentences (expected).
- **ADRs.** 012.

## Stage 11 — Semantic Analysis
`nlp/semantics/` — `models.py`, `interfaces.py`, `analyzer.py`
`persistence/verbs.py` (1,877 verb lemmas, 11,711 stem surfaces, 703 frames)

Builds one `SemanticGraph` per sentence from Stages 08 + 09 + 10. Figure 5's three
bullets are three views of it: the graph is the *Context Graph*, its
predicate-argument content the *Meaning Representation*, and `graph.intent` the
*Intent Analysis*.

- **Key decisions.** The graph is **symbolic**; embeddings and similarity belong
  to the AI Runtime, which no document places in the Language Server (ADR-013).
  Roles come from Hill's verb-stem lexicon in the authoritative data repository —
  the same directory family Stage 08 draws its relations from (ADR-014). Intent
  is sentence mood, read from attested corpus tags (ADR-015). Per sentence, not
  per document: aggregation is Stage 12's job.
- **The payoff is a reclassification.** ADR-010's inherited defect — Stage 08
  reads a transitive object as a subject whenever the agentive is the fused
  `ས`/`ར` — is decided here from the verb's own attested frame: **4,838
  arguments (13.2% of edges) relabelled on lexical evidence**. Stage 08 is
  untouched.
- **Limitations.** No role-annotated Tibetan corpus exists, so **no
  precision/recall/F1 is reported and none should be inferred** (same rule as
  ADR-010). 47.0% of roles rest on Stage 08's structure alone. Copulas are not
  predicates, because Stage 08 does not head clauses with them. Argument
  attachment inherits Stage 08's flat shape.
- **Results, and what each is.** 5,885 graphs / 43,472 nodes / 36,735 edges,
  0 cross-stage violations, every graph an acyclic forest — *invariants*.
  74.6% of predicates lemmatized, 53.0% of roles resting on a case particle or
  the lexicon, 1.4% unspecified — *coverage*, not accuracy. Intent 84.4%
  declarative / 8.6% imperative / 7.0% interrogative / 19.4% negative — an
  *output distribution over one corpus*, not accuracy.
- **What is validated.** The 4,838 reclassifications are *changes*, not verified
  corrections. **39.5%** occur in sentences whose gold annotation contains an
  explicit `case.agn`, so the clause is transitive per gold and Stage 08 was
  wrong there — a **lower bound**, since Tibetan drops arguments freely and the
  undecidable remainder is not an error rate. The same measurement re-derives the
  upstream gap independently: gold has an agentive in 1,999 sentences and the
  pipeline sees none in **1,419 (71.0%)**. Both pinned by test. See ADR-014.
- **ADRs.** 013, 014, 015.

## Stage 12 — Immutable Document Snapshot
`nlp/snapshot/` — `models.py`, `interfaces.py`, `hashing.py`, `builder.py`

The composition root of the Language Server. `LanguageServerSnapshotBuilder` wires
Stages 04–11 and returns one `DocumentSnapshot` per document. Aggregation only:
it performs no linguistic analysis, and a test composes the stages by hand and
compares artifact by artifact to prove it.

- **Key decisions (ADR-016).** FR-4's hash lives here because FR-4 assigns hash
  checks to the *Language Server*; FR-1/FR-2's debounce and patching are the
  client's and are not implemented. `blake2b` at 16 bytes from the stdlib — CRC32
  was rejected (~0.4% collision chance per document, silently returning another
  sentence's analysis) and `xxhash` was rejected as an unnecessary dependency.
  The builder does **not** normalize: Stage 02 can change text length, so
  normalizing here would produce offsets addressing a string the caller never
  passed. Stage 05's subword encoding is not stored — it is the AI Runtime's
  input, and storing it would make the snapshot depend on the model.
- **What it adds over the per-sentence artifacts.** One object per document
  (FR-3); `document_span` translation from sentence-relative to document
  coordinates; a per-sentence cache key (FR-4); and a validated join that rejects
  artifacts belonging to different sentences.
- **Why reuse is sound.** Every stage from 06 onward consumes only the sentence's
  text and emits sentence-relative spans, so an analysis is a pure function of
  that string and survives the document changing around it. Only the Stage 04
  `Sentence` records a position, so only it is rebuilt when a sentence moves.
- **Limitations.** Incremental cost is linear in document size — the document is
  re-segmented and re-hashed in full because an edit can move every boundary
  after it. Cached analyses are keyed by text alone, so a snapshot belongs to the
  builder that produced it (ADR-016).
- **Results.** On the 241,882-char corpus: an edit re-parses **exactly 1 sentence
  of 5,885**, pinned by counting calls into Stage 06. `reanalyze` output is
  asserted **equal** to a cold `analyze` everywhere. The snapshot is **deeply
  immutable** — a test walks the whole object graph.
- **ADRs.** 016.

---

# Architecture

## Authoritative documents
Precedence, highest first (ADR-002, ADR-003):

1. `docs/Tibetan Enterprise Architecture.html` — SRS v5.1
2. `docs/System Design Diagram/*.html` — Figures 1–5, Deployment, UML Sequence
3. `docs/Project Resources.txt` — model and dataset sources
4. `docs/ARCHITECTURE_DECISIONS.md` — ADR-001…016

A superseded v1.0 hackathon spec (`Presentation.html`) was **removed** from the
repository; ADR-002 retains the record of why it carries no requirements.

**Data.** `github.com/kalsang2006/Data` — Milarepa/Marpa POS-annotated corpora,
classical lexicon, tibcg3 constraint grammars, Hill's verb-stem lexicon, BDRC
Buddhist canon (TEI XML).
**Model.** `CMLI-NLP/TiBERT` on Hugging Face — never substitute another.

## Pipeline order (Figure 5)
01 input → 02 normalize → 03 clean → 04 segment → 05 tokenize → 06 morphology →
07 POS → 08 dependency → 09 NER → 10 terminology → 11 semantic → 12 snapshot
**— all implemented.**

## Dependency graph (acyclic, enforced by test)
```
teea.core                          ← no internal dependencies
teea.persistence                   ← core only
  ↑
teea.nlp.segmentation  (Stage 4)   ← core only
teea.nlp.tokenization  (Stages 2,3,5)
  ↑
teea.nlp.morphology    (Stage 6)   ← core + tokenization
  ↑
teea.nlp.postagging    (Stage 7)   ← core + morphology + persistence
  ↑
teea.nlp.dependency    (Stage 8)   ← core + postagging
  ↑
teea.nlp.ner           (Stage 9)   ← core + dependency + persistence
teea.nlp.terminology   (Stage 10)  ← core + dependency + persistence
  ↑
teea.nlp.semantics     (Stage 11)  ← core + dependency + ner + terminology + persistence
  ↑
teea.nlp.snapshot      (Stage 12)  ← core + every stage above (composition root)
```

`test_no_stage_imports_a_later_stage` enforces the whole Figure 5 order, and
`test_every_pipeline_package_is_listed_in_the_stage_order` fails if a new package
is added without being listed.

## Persistence architecture
`teea.persistence` holds four **facets** of Figure 2's Dictionary Repository,
stated as separate protocols for Interface Segregation:

| Protocol | Implementation | Data | Consumer |
|---|---|---|---|
| `DictionaryRepository` | `InMemoryDictionaryRepository` | `pos_model.json` (126 KB) | Stage 07 |
| `GazetteerRepository` | `InMemoryGazetteer` | `proper_nouns.json` (109 KB) | Stage 09 |
| `TerminologyRepository` | `InMemoryTerminology` | `terminology.json` (25 KB) | Stage 10 |
| `VerbLexiconRepository` | `InMemoryVerbLexicon` | `verb_frames.json` (570 KB) | Stage 11 |

All in-memory and read-only (ADR-006); SQLite/LMDB deferred until a feature needs
them. Each raises `ConfigurationError` on missing/malformed data, and each has a
`default_*()` `lru_cache`d accessor. All four payloads carry a `provenance`
record naming the source file and the derivation criteria.

## Dependency injection pattern
Every stage takes its collaborators as keyword-only constructor arguments
defaulting to `None`, resolved with **`is None`, never `or`** — an empty
repository is falsy and `or` silently substitutes the shipped one (a real bug,
fixed in Stages 07/09/10).

Every stage exposes a `runtime_checkable` Protocol so implementations are
swappable (SRS 3.3 hot-swapping).

## Public APIs that must remain stable
`teea.core` (22 exports) · `tokenization` (19) · `segmentation` (4) ·
`morphology` (6) · `postagging` (6) · `dependency` (6) · `ner` (5) ·
`terminology` (4) · `semantics` (11) · `snapshot` (6) · `persistence` (22).
**Additive changes only.** Stage 12 added one new package and touched no existing
export; nothing has ever been renamed or removed.

## Constraints that must not be violated
1. `core` never imports `nlp`.
2. `persistence` never imports `nlp`.
3. **No stage imports a later stage** (generalises the old Stage 4 / Stage 5 rule
   to the whole Figure 5 order).
4. The import graph stays acyclic.
5. Shared character classes (`SHAD_CHARS`, `TSHEG_CHARS`, `LINE_BREAK_CHARS`) are
   defined **exactly once** in `core.types`.
6. No network client or cloud SDK anywhere in `src/`.
7. **Later stages never re-segment or re-tag** — spans are preserved verbatim
   from Stage 06 onward.

All seven are enforced by `tests/test_architecture.py` (72 tests).

---

# Important Engineering Decisions

| # | Decision | Why / Evidence | Rejected alternative |
|---|---|---|---|
| 001 | Stage 03 is an activity of Stage 02 | Document Cleaning appears in 1 of 4 views; Figure 5 is an *activity* view, Figures 1/2 are *component* views | A separate `cleaning` package |
| 002 | SRS v5.1 authoritative | v1.0 described a cloud system; all diagrams + code match v5.1 | Treating both as binding |
| 003 | Figure 5 = decomposition, SRS §3.1 = ordering | §3.1 says "parse **through**", constraining order not membership | Declaring them contradictory |
| 004 | Stage 02 preserves line breaks | Word encodes paragraph marks as CR, line breaks as VT; stripping them made documents one runaway sentence | Caller passes `strip_controls=False` (all-or-nothing) |
| 005 | Boundary changes belong to Stage 06 | Figure 5 gives Stage 06 "affix recognition"; Stage 07 relabelling would invert pipeline flow | Fixing fused `ས` in Stage 07 |
| 006 | Repositories in-memory | ~250 KB read-only; SQLite/LMDB serve features that don't exist | Introducing a storage engine early |
| 007 | Tag syllables, train on syllables | Measured: word-trained model scored 50.3% vs 72.3% syllable-trained | Training on gold word tokens |
| 008 | TiBERT loaded with `strip_accents=False` | BERT's accent stripping deletes Unicode Mn — in Tibetan the vowel signs | Accepting model defaults |
| 009 | CG3 grammars reimplemented | `vislcg3` is a C++ toolchain, contradicting offline-first pure Python | Shipping/invoking the binary |
| 010 | No UAS/LAS for Stage 08 | No treebank in the repository (searched all 38 non-BDRC files) | Inventing an eval set |
| 011 | Untyped entities | Zero typed markers across both corpora and all 80 lexicon categories | 5-member enum no producer populates |
| 012 | Two-criteria glossary | Contrastive frequency alone yields register ("therefore"), not terms | A tuned frequency threshold |
| 013 | Stage 11 is the *symbolic* Semantic Graph | Every "graph" reference names the Language Server; every "vector/feature/similarity" reference names the AI Runtime | Loading an embedding model in the Language Server |
| 014 | Roles from Hill's verb-stem lexicon | 95.2% corpus surface coverage; 1,830/1,831 cross-check against an independent CG3 file | Inventing a role ontology, or renaming Stage 08's relations |
| 015 | Intent = sentence mood | `cv.ques`, `p.interrog`, `v.imp`, `neg`, `cl.quot` are attested tags with counts | "User intent", which has no data and belongs to the command bus |
| 016 | Stage 12 owns the FR-4 hash + mechanism, not the policy | FR-4 assigns hash checks to the *Language Server*; FR-1/FR-2 assign debounce and patching to the client | Putting hashing in the daemon, or adding an `xxhash` dependency |

---

# Bugs Fixed

| Defect | Root cause | Resolution | Regression test |
|---|---|---|---|
| Package would not import | `tokenization/models.py` was 0 bytes; 4 modules imported from it | Wrote the module from call-site contracts | Whole suite |
| Module name mismatch | `__init__`/conftest imported `tibert`; file was `tibert_tokenizer.py` | Renamed the file (3 refs vs 1) | Import tests |
| Slow-path spans destroyed | `_spans_from_alignment` searched for `[CLS]`, `find()` returned −1, latching `alignment_lost` — **0/4 vs 4/4** content spans | Skip special tokens by id | `test_slow_path_keeps_spans_when_special_tokens_are_present` (verified to fail without the fix) |
| `normalize()` broke its own idempotence | Controls stripped **after** normalizing; a ZWSP between Tibetan vowel signs blocked reordering | Strip before normalizing | `test_stripping_a_blocking_format_char_keeps_output_normalized` |
| `mypy tests` never ran | No `mypy_path`; `teea` unresolvable from tests | Added `mypy_path = "src"` | 80-file clean run |
| Word line breaks ignored | Only LF/CR recognised; Word uses VT | Shared `LINE_BREAK_CHARS` | Parametrized over the constant |
| Stage 2 deleted Word paragraph marks | CR/VT are category `Cc`, stripped as controls | `_PRESERVED_CONTROLS = {tab} ∪ LINE_BREAK_CHARS` | `test_word_line_breaks_survive_normalization` |
| **TiBERT destroyed Tibetan** | `do_lower_case` declared but never passed; BERT accent-stripping deleted every vowel sign (`བཀྲ`→`བཀ`, `ཤིས`→`[UNK]`) | Pass `do_lower_case` + pin `strip_accents=False` | **Hermetic** test stubbing `AutoTokenizer` |
| NFR 5.1 breach on OOV text | `_transition_logp` recomputed `sum(row.values())` 480,480× | Precompute transition log table | Counts `math.log` calls (must be 0) |
| Flaky perf test | Wall-clock: 0.76 ms isolated vs 2.97 ms in-suite (GC scales with heap) | Replaced timing with work-counting | Deterministic |
| `_load` leaked `TypeError` | Scalar JSON reached `set(payload)` | Reject non-dict payloads | `test_a_scalar_payload_raises_configuration_error` |
| `_load` leaked `UnicodeDecodeError` | It is a `ValueError`, not `OSError` | Catch both | `test_a_non_utf8_payload_raises_configuration_error` |
| `interj` mislabelled `UNKNOWN` | Fell through the prefix table | Added `PosCategory.INTERJECTION` | `test_interjection_has_its_own_class` |
| **Empty injected repo silently replaced** | `dictionary or default_dictionary()` — empty repo is falsy (`__len__`) | `is None` in Stages 07/09/10 | One per stage |

---

# Verification History

Every stage passed the same gates before acceptance: full suite, mypy strict,
ruff, coverage, packaging, and pipeline validation against the real corpus.

**Current totals.** `1,304 passed, 9 deselected, 1 xfailed` · mypy strict clean
(**99 files**: 54 source, 45 test) · ruff clean · integration **9/9 against the
real TiBERT** · **99% overall coverage**, with Stages 04, 06, 07, 08, 09, 10, 11,
12 and all persistence modules at **100% statement and branch**.

**Per-module tests.** tokenization 381 (9 integration) · semantics 165 ·
persistence 141 · postagging 97 · segmentation 92 · snapshot 86 · morphology 85 ·
dependency 79 · architecture 72 · terminology 49 · ner 46 · errors 17.

**Performance (real TiBERT, 241,882-char document).**
Incremental re-parse p50 0.68 ms / p99 **2.56 ms** against NFR 5.1's 50 ms —
20× headroom, 0/400 over budget. Throughput ~44k chars/s. Memory 142 MiB retained
per document, 0.6 KiB leaked over 2,000 discarded analyses. 8-thread concurrency
produces results identical to serial, including the real tokenizer. All nine
pathological inputs handled. Cold start ~11 s, dominated by TiBERT load — the
daemon must load once at startup; set `HF_HUB_OFFLINE=1` for air-gapped runs.

**Pipeline 01→12** (real model): 5,885 sentences → 141,680 tokens → 65,925
morphemes → 65,925 tagged → 65,925 dependency nodes → 1,363 entities → 68 terms →
**43,472 semantic nodes / 36,735 edges**, **0 cross-stage violations**, every
graph an acyclic forest.

**Stage 11 timings** (same corpus). Stage 11 alone p50 0.156 ms / p99 0.604 ms;
Stages 06→11 p50 0.784 ms / **p99 3.572 ms** against NFR 5.1's 50 ms — 14×
headroom, 0/5,885 over budget. Stage 11 is 18.3% of the analysis chain. Verb
lexicon cold start 47 ms. 2.37 KiB retained per node, 2.1 KiB leaked over 1,000
graphs. 8-thread concurrency identical to serial.

**One optimization**, made on measured evidence and kept: the case-particle lookup
was a per-node forward scan, quadratic on modifier runs — 968 ms for a
3,200-adjective sentence, breaching NFR 5.1. Replaced by a single backward pass
tabulating every position: **84 ms, 11.5× faster, bit-identical output** across
all 5,885 sentences. The naive scan is kept in the suite as a correctness oracle
rather than defending the change with a timing assertion.

**Stage 12 incremental path** (same corpus). An edit re-parses **1 sentence of
5,885**. Wall-clock is linear in document size because the document is
re-segmented and re-hashed in full: p50 **3.0 ms at 2,000 chars**, 10.2 ms at
10,000, 39.1 ms at 50,000, ~0.7 s at 241,882. Hashing is 0.7 µs/sentence, under
0.1% of the analysis it saves. A second measured optimization was kept: an
unchanged, unmoved sentence keeps its **existing analysis object** rather than
being reconstructed — 1.15 µs to check against 35.3 µs to rebuild — which cut a
whole-corpus incremental rebuild from 434 ms to **175 ms** for an edit near the
end, with `reanalyze` output still bit-identical to `analyze`.

---

# Current Repository State

```
pyproject.toml            Python 3.12+, hatchling, mypy strict, ruff, pytest
README.md                 status, perf, dependency graph, technical debt
docs/
  ARCHITECTURE_DECISIONS.md   ADR-001…015
  HANDOFF.md                  this file
  Tibetan Enterprise Architecture.html   SRS v5.1
  Project Resources.txt
  System Design Diagram/*.html           Figures 1–5, Deployment, UML
src/teea/
  core/           config, errors, logging, types
  persistence/    interfaces, dictionary, gazetteer, terminology, verbs,
                  data/*.json
  nlp/            tokenization, segmentation, morphology, postagging,
                  dependency, ner, terminology, semantics, snapshot
tests/
  conftest.py     all fixtures (corpora, repositories, every stage)
  fakes/          FakeBackendTokenizer
  data/           mila_sentences, lexicon_sample, mila/marpa_tagged_sample
  nlp/<stage>/    per-stage suites
  persistence/    dictionary, gazetteer, verbs
  test_architecture.py   executable ADR constraints
```

54 source modules, 31 test modules. Stray empty `cls` and `tree` files at the
repository root are shell artifacts and can be deleted.

---

# Remaining Work

## The Language Server is complete; the layers above it are not

Figure 5's twelve stages are implemented, verified and accepted. Nothing in the
*language pipeline* remains. What the architecture describes and this repository
does **not** contain, in the order the diagrams put them:

| Component | Where it is specified | Notes |
|---|---|---|
| **Plugin Runtime** | Figure 1, Figure 2, Figure 5's plugin band | Sandboxed feature execution; NFR 5.3 requires a plugin fault not to take down Word. Consumes `DocumentSnapshot`. |
| **Suggestion Fusion Engine** | Figure 7 (a dedicated diagram), FR-7 | Collect, validate, resolve conflicts, merge, rank, prioritise, generate a patch. The most fully specified unbuilt component. |
| **AI Runtime & Capability Registry** | Figure 6 (dedicated), Figure 9, SRS 3.3, FR-6 | Inference manager, model registry, ONNX runtime. Owns the embedding semantics ADR-013 kept out of Stage 11. |
| **Local IPC layer** | Figure 1, Figure 3, SRS 2.1, FR-1, FR-2, FR-8 | Named pipes / gRPC over loopback; debounce and minimal patch layer, which ADR-016 explicitly left out of Stage 12. |
| **Office.js add-in** | Figure 1, Figure 2 | Task pane, ribbon, real-time decoration. |
| **Plagiarism subsystem** | Figure 8, SRS 3.4, FR-9 | Winnowed k-gram fingerprints; needs the Fingerprint Index that ADR-006 deliberately did not build. |
| **SQLite / LMDB stores** | Figure 2, Figure 9, FR-10 | ADR-006 deferred both until a feature needs them. The Suggestion Fusion cache and plugin metadata are the first such features. |

**Whichever is taken next, the same rules apply.** Read the SRS and the diagram
that specifies it before writing code; resolve ambiguity with an ADR rather than a
guess; and do not weaken the Language Server to suit a consumer.

**One caution specific to what comes next.** Everything above consumes
`DocumentSnapshot`, so its shape is now load-bearing for components that do not
exist yet. Resist adding fields speculatively — the snapshot holds what Figure 5
says it holds, and a consumer needing more should say so with evidence first.

## Intentionally deferred
- `was_truncated` false positive (Stage 05) — **strict xfail**, awaiting a design
  decision between a second tokenization pass, extending `BackendTokenizer` with
  `return_overflowing_tokens`, or accepting it.
- Fused `ས`/`ར` splitting (Stage 06) — the Dictionary Repository that blocked it
  now exists; this is the highest-value accuracy work available.
- Multi-syllable particle matching (Stage 06).
- "Standardize punctuation" (Stage 03) — see ADR-001 before implementing.
- Typed entity gazetteer (Stage 09) and a curated terminology resource (Stage 10).
- A Tibetan UD treebank (Stage 08) — prerequisite for any parser evaluation.
- A role-annotated Tibetan corpus (Stage 11) — prerequisite for any semantic
  precision/recall figure (ADR-014).
- No lock file; daemon entrypoint and `HF_HUB_OFFLINE` wiring do not exist.

---

# Instructions for the Next Claude Session

1. **Do not redesign Stages 01–12.** They are complete, verified and accepted,
   and Figure 5's pipeline is finished.
2. **Do not modify Stages 01–12** unless you find a genuine defect and can
   demonstrate it with objective evidence *before* changing anything. Every past
   fix in this project was reproduced first, then fixed, then locked with a
   regression test that was verified to fail without the fix.
3. **Begin with a fresh repository scan and an audit of whichever component you
   take next** (see "The Language Server is complete" above). Read the SRS and
   the diagram that specifies it — Figure 6, 7, 8 or 9 as appropriate — plus
   `ARCHITECTURE_DECISIONS.md` and the `DocumentSnapshot` API. Produce the audit
   before implementing.
4. **Preserve all public APIs.** Additive changes only — no signature changes, no
   removed exports. `tests/test_architecture.py` enforces the layering rules; add
   any new *pipeline* package to `STAGE_ORDER` there. A component above the
   Language Server is not a pipeline stage and does not belong in that list —
   it belongs in a new top-level package that may import `teea.nlp`, never the
   reverse.
5. **Continue from the current repository state.** Do not rebuild data payloads
   or re-derive resources that already ship.
6. **Make routine engineering decisions yourself** when the evidence supports
   them, and record each in an ADR (next number: **017**). Stop only for a genuine
   contradiction between authoritative documents.
7. **Never invent linguistic data, and never invent requirements.** Every
   resource so far is corpus-derived with its provenance in the payload. If a
   specified capability cannot be supported by available data, implement what can
   be and document the gap — as ADR-010, ADR-011, ADR-012 and ADR-014 did.
   Equally, do not add capability no document asks for: ADR-006 and ADR-013 are
   the record of features deliberately *not* built.
8. **Verification gates before claiming completion:** full suite, mypy strict,
   ruff, coverage (maintain 100% on new modules), `pytest -m integration`,
   packaging (`python -m build --wheel`, confirm data payloads ship), and a full
   pipeline run on the real corpus with cross-stage invariant checks.

**Environment.** Windows, Git Bash. Prefix any Tibetan-printing script with
`PYTHONIOENCODING=utf-8` (console is cp1252). For ad-hoc scripts use
`PYTHONPATH="src;."` — semicolon, not colon. Prefer the Write tool over heredocs
for files containing Tibetan or backslash escapes; heredoc escaping has corrupted
files in this project more than once.
