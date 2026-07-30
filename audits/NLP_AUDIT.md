# TEEA — NLP Pipeline Audit

**Date:** 2026-07-30
**Version:** 1.0.0
**Git Commit:** (as of audit date)
**Auditor:** Staff NLP Engineer
**Source:** `NLP_AUDIT.md` (project root)
**Verification:** Regenerated from existing documentation; no live tests executed.

---

## Overview

TEEA implements the complete 12-stage NLP pipeline specified in the architecture. All stages are implemented and tested. The pipeline covers:

1. Raw Document Input (Stage 01) — no code, handled by add-in
2. Unicode Normalization (Stage 02) — `nlp.tokenization.normalization`
3. Document Cleaning (Stage 03) — merged with Stage 02 per ADR-001
4. Sentence Segmentation (Stage 04) — `nlp.segmentation`
5. Word Tokenization (Stage 05) — `nlp.tokenization.tibert`
6. Morphological Analysis (Stage 06) — `nlp.morphology`
7. POS Tagging (Stage 07) — `nlp.postagging`
8. Dependency Parsing (Stage 08) — `nlp.dependency`
9. NER (Stage 09) — `nlp.ner`
10. Terminology Recognition (Stage 10) — `nlp.terminology`
11. Semantic Analysis (Stage 11) — `nlp.semantics`
12. Document Snapshot (Stage 12) — `nlp.snapshot`

---

## Stage-by-Stage Analysis

### Stage 02: Unicode Normalization ✅ — Quality: ★★★★★

**Module:** `src/teea/nlp/tokenization/normalization.py`

**Strengths:**
- Correctly handles NFC/NFKC/NFD/NFKD normalization
- Control character removal before normalization (prevents canonical-ordering blockers)
- Line-break preservation (paragraph boundaries from Word)
- Idempotent: `normalize(normalize(x)) == normalize(x)`
- Whitespace collapsing is safe for Tibetan (tsheg-based word structure)
- Thread-safe and stateless

**Issues:**
- `_PRESERVED_CONTROLS` is unreachable by default: `collapse_whitespace=True` folds newlines immediately after preservation
- Punctuation standardization (Stage 03) deliberately deferred per ADR-001

### Stage 03: Document Cleaning ✅ — Quality: ★★★★☆

**Module:** Merged into `normalization.py` per ADR-001

Same as Stage 02 — cleaning is control character removal and whitespace normalization.

**Missing:** Punctuation standardization deferred.

### Stage 04: Sentence Segmentation ✅ — Quality: ★★★★★

**Module:** `src/teea/nlp/segmentation/sentence.py`

**Strengths:**
- Correct shad-family (7 characters) and line-break boundary detection
- Terminator stored verbatim (nyis shad, rin chen spungs shad distinguishable)
- Punctuation-only runs discarded
- Configurable `break_on_newline` for verse processing
- Total: empty/punctuation-only input yields empty result

### Stage 05: Word Tokenization ✅ — Quality: ★★★★★

**Module:** `src/teea/nlp/tokenization/tibert.py`

**Strengths:**
- Authoritative TiBERT tokenizer (29,965-entry WordPiece vocabulary)
- Correctly disables `do_lower_case` and `strip_accents` (critical for Tibetan)
- Dependency injection via `BackendLoader`
- Lazy `transformers` import
- Comprehensive error taxonomy

**Issues:**
- `was_truncated` false positive on exact-length input (tracked by strict xfail)
- OOV rate: 5.2% on reference corpus
- No cross-sentence context

### Stage 05b: Syllable Segmentation ✅ — Quality: ★★★★★

**Module:** `src/teea/nlp/tokenization/syllable.py`

**Strengths:**
- Deterministic tsheg-based delimiter detection
- Exact character/byte spans
- Handles both tsheg (U+0F0B) and non-breaking tsheg (U+0F0C)

**Issues:**
- Non-breaking tsheg distinction lost: `has_trailing_tsheg` is bool

### Stage 06: Morphological Analysis ✅ — Quality: ★★★★☆

**Module:** `src/teea/nlp/morphology/analyzer.py`

**Strengths:**
- Corpus-derived affix inventory (60,544 tagged tokens, 16,984 grammatical morphemes)
- **80.2% recall / 92.1% precision** (measured against gold annotations)
- **98.7% recall** excluding fused `ས`/`ར`
- Honest ambiguous surface reporting
- Fused affix splitting for vowel-initial suffixes (འི, འམ, འང, འོ)

**Issues:**
- Cannot split `ས`/`ར` without dictionary (ADR-009)
- No Dictionary Repository lookup implemented yet

### Stage 07: POS Tagging ✅ — Quality: ★★★★☆

**Module:** `src/teea/nlp/postagging/tagger.py`

**Strengths:**
- Bigram HMM + Viterbi decoding
- **72.3% fine / 82.0% coarse accuracy** (Milarepa → Marpa)
- Precomputed transition log table (5.6× speedup)
- Thread-safe

**Issues:**
- 72.3% fine accuracy is modest by modern NLP standards (reasonable for Tibetan)
- Proper/common noun distinction largest error source
- Only one held-out evaluation pair

### Stage 08: Dependency Parsing ✅ — Quality: ★★★★☆

**Module:** `src/teea/nlp/dependency/parser.py`

**Strengths:**
- Rule-based parser from Tibetan Constraint Grammars
- Ergative-absolutive alignment correctly handled
- Total: always produces a rooted, acyclic tree

**Issues:**
- Deterministic attachment may not capture all structures
- Copulas never head a clause
- No statistical parser — future work (ADR-010)

### Stage 09: Named Entity Recognition ✅ — Quality: ★★★☆☆

**Module:** `src/teea/nlp/ner/recognizer.py`

**Strengths:**
- Gazetteer-driven (2,767 proper nouns, two tiers)
- Longest-match resolution
- Two evidence sources: gazetteer + POS tag

**Issues:**
- **Entities are untyped** — Figure 5 names 5 types but no data distinguishes them
- No precision/recall/F1 reported
- No sequence model for OOV entity detection

### Stage 10: Terminology Recognition ✅ — Quality: ★★★★☆

**Module:** `src/teea/nlp/terminology/recognizer.py`

**Strengths:**
- Glossary-driven (871 Buddhist technical terms)
- User dictionary support
- Contrastive frequency selection (ADR-012)

**Issues:**
- Small glossary (871 terms)
- No automatic term extraction

### Stage 11: Semantic Analysis ✅ — Quality: ★★★☆☆

**Module:** `src/teea/nlp/semantics/analyzer.py`

**Strengths:**
- Symbolic semantic graph construction
- Verb lexicon (1,877 lemmas, 11,711 stem surfaces, 703 frames)
- Acyclic graph guarantee
- Provenance tracking (CASE / LEXICON / STRUCTURE)

**Issues:**
- **No precision/recall/F1** — no gold role-annotated Tibetan corpus exists
- 74.6% of predicates lemmatized
- 47% of roles on structure alone
- 4,838 absolutive reclassifications — only 39.5% corroborated

### Stage 12: Document Snapshot ✅ — Quality: ★★★★★

**Module:** `src/teea/nlp/snapshot/builder.py`

**Strengths:**
- Composition root for Stages 04-11
- Incremental reanalysis (FR-4): **2,854× faster than full re-parse**
- All stages injectable
- Deep immutability (frozen Pydantic)
- Thread-safe

**Issues:**
- Incremental cost linear in document size
- Stage configuration not part of analysis key

---

## Cross-Cutting Observations

### What's Excellent
1. **Span discipline** — every stage carries exact character + byte offsets
2. **Total operations** — every stage handles empty/edge input gracefully
3. **Honest uncertainty** — ambiguity reported, never guessed
4. **Dependency injection** — all stages have injectable collaborators
5. **Frozen models** — immutability guarantees concurrent safety
6. **Corpus-derived data** — affixes, tags, frames all from real data

### What Needs Improvement
1. **No gold role-annotated data** — Stage 11 quality unverifiable
2. **No treebank** — Stage 8 rule-based
3. **Limited NER** — untyped, gazetteer-only
4. **Small glossary** — 871 terms
5. **No cross-sentence context**
6. **No streaming support**

### Data Quality Metrics

| Dataset | Size | Quality |
|---------|------|---------|
| POS Model | 126 KB, 77 tags | ✅ Derived from Milarepa corpus |
| Proper Nouns | 109 KB, 2,767 entries | ✅ Two-tier quality |
| Terminology | 25 KB, 871 terms | ✅ Contrastive frequency selected |
| Verb Frames | 570 KB, 1,877 lemmas | ✅ 1,830/1,831 verified (99.95%) |
| Synthetic Errors | 10,000 records | ✅ Basic spelling only |
| BoCorpus N-grams | JSON | ✅ Pipeline generates from authoritative source |

---

## Recommendations

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| High | Create role-annotated Tibetan corpus | 3-6 months | Enables Stage 11 verification |
| High | Add treebank-trained dependency parser | 2-4 months | Better attachment, semantics |
| Medium | Add typed NER gazetteer | 2-4 weeks | Entity type output |
| Medium | Expand terminology glossary | 2-4 weeks | Domain coverage |
| Medium | Add TiBERT model card | 1 day | Legal/license clarity |
| Low | Cross-sentence context window | 2-4 weeks | Better tokenization |
| Low | Streaming pipeline support | 2-4 weeks | Large-document support |

---

## Comparison with Previous Audit

- **This is the baseline NLP pipeline audit**
- **Changes since previous:** The spell checker corpus wiring was completed (see `SPELLCHECK_AUDIT.md`), which now connects corpus data to the spell-checking runtime
- **Regressions:** None identified

## Cross-References

- Performance benchmarks for pipeline: `PERFORMANCE_AUDIT.md`
- Spell checker corpus architecture: `SPELLCHECK_AUDIT.md`
- Technical debt for NLP items: `TECHNICAL_DEBT.md` (#12-14)
- Project-wide assessment: `PROJECT_AUDIT.md` §4
