# TEEA — NLP PIPELINE AUDIT

**Date:** 2026-07-30  
**Auditor:** Staff NLP Engineer

---

## OVERVIEW

TEEA implements the complete 12-stage NLP pipeline specified in Figure 5 of the architecture. All stages are implemented and tested. The pipeline covers:

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

## STAGE-BY-STAGE ANALYSIS

### Stage 02: Unicode Normalization ✅

**Module:** `src/teea/nlp/tokenization/normalization.py`  
**Quality:** ★★★★★

**Strengths:**
- Correctly handles NFC/NFKC/NFD/NFKD normalization
- Control character removal before normalization (prevents canonical-ordering blockers)
- Line-break preservation (paragraph boundaries from Word)
- Idempotent: `normalize(normalize(x)) == normalize(x)`
- Whitespace collapsing is safe for Tibetan (tsheg-based word structure)
- Thread-safe and stateless
- Comprehensive test suite

**Issues:**
- `_PRESERVED_CONTROLS` is unreachable by default: `collapse_whitespace=True` folds newlines immediately after preservation
- "Standardize punctuation" (Stage 03) is deliberately deferred (ADR-001) but no target date or issue tracking exists

---

### Stage 03: Document Cleaning ✅

**Module:** Merged into `normalization.py` per ADR-001  
**Quality:** ★★★★☆

Same as Stage 02 — cleaning is implemented as control character removal and whitespace normalization.

**Missing:** Punctuation standardization is deferred. No punning normalization exists.

---

### Stage 04: Sentence Segmentation ✅

**Module:** `src/teea/nlp/segmentation/sentence.py`  
**Quality:** ★★★★★

**Strengths:**
- Correct shad-family (7 characters) and line-break boundary detection
- Terminator stored verbatim (nyis shad, rin chen spungs shad distinguishable)
- Punctuation-only runs discarded (handles verse pattern `།།` at line start)
- Configurable `break_on_newline` for verse processing
- Total: empty/punctuation-only input yields empty result
- Thread-safe and stateless
- RFC-compliant with correct span validation

**Verified:** SegmentedText validator enforces order, non-overlap, span accuracy, and text-span consistency.

---

### Stage 05: Word Tokenization ✅

**Module:** `src/teea/nlp/tokenization/tibert.py`  
**Quality:** ★★★★★

**Strengths:**
- Uses authoritative TiBERT tokenizer (29,965-entry WordPiece vocabulary)
- Correctly handles Tibetan-specific tokenizer issues:
  - Disables `do_lower_case` (Tibetan is caseless)
  - Disables `strip_accents` (would delete vowel signs)
- Dependency injection for testability (`BackendLoader` callable)
- Lazy `transformers` import
- Spans are best-effort, never fatal (alignment failures produce `None` spans)
- Comprehensive error taxonomy (EmptyInputError, InputNotStringError, InputTooLongError)
- Handles both SentencePiece (metaspace) and WordPiece (##) tokenizers

**Issues:**
- `was_truncated` false positive when input length exactly equals max_length (tracked by strict xfail)
- OOV rate: 5.2% on reference corpus, 11 of 120 rare classical forms OOV
- No sentence-level optimization: tokenizing each sentence separately means TiBERT cannot use cross-sentence context

**TiBERT Model Card (missing):** No documentation exists on:
- Training data composition (which Tibetan texts?)
- Model architecture (BERT-base? 12 layers? 768 hidden?)
- License (CC BY-NC? MIT? Unknown — legal risk for enterprise)
- Evaluation metrics on Tibetan NLP benchmarks

---

### Stage 05b: Syllable Segmentation ✅

**Module:** `src/teea/nlp/tokenization/syllable.py`  
**Quality:** ★★★★★

**Strengths:**
- Deterministic tsheg-based delimiter detection
- Exact character/byte spans
- Handles both tsheg (U+0F0B) and non-breaking tsheg (U+0F0C)
- Non-Tibetan runs returned verbatim (caller can filter)
- Thread-safe

**Issues:**
- Non-breaking tsheg distinction is lost: `has_trailing_tsheg` is a `bool`, so `with_tsheg()` always re-emits U+0F0B — would change line-breaking behavior in user documents

---

### Stage 06: Morphological Analysis ✅

**Module:** `src/teea/nlp/morphology/analyzer.py`  
**Quality:** ★★★★☆

**Strengths:**
- Corpus-derived affix inventory (60,544 tagged tokens, 16,984 grammatical morphemes)
- **80.2% recall / 92.1% precision** (measured against gold annotations)
- **98.7% recall** excluding fused `ས`/`ར` (explicitly declined)
- Honest ambiguous surface reporting (quarter of affixes also occur as content words)
- Fused affix splitting for vowel-initial suffixes (འི, འམ, འང, འོ)
- Configurable `split_fused_affixes`

**Issues:**
- Cannot split `ས`/`ར` without a dictionary (ADR-009 — block on Persistence Layer)
- No Dictionary Repository lookup implemented yet (Figure 2's Morphological rules catalog)
- Some ambiguity is inherent and unresolvable at this stage

---

### Stage 07: POS Tagging ✅

**Module:** `src/teea/nlp/postagging/tagger.py`  
**Quality:** ★★★★☆

**Strengths:**
- Bigram HMM + Viterbi decoding
- **72.3% fine / 82.0% coarse accuracy** on held-out text (trained on Milarepa, tested on Marpa)
- Precomputed transition log table (5.6× speedup documented)
- Additive smoothing tuned by measurement
- Stage 6 constraints narrow candidate tags for OOV surfaces
- Thread-safe (precomputed tables, stateless decode)

**Issues:**
- 72.3% fine accuracy is modest by modern NLP standards (but reasonable for Tibetan)
- Proper/common noun distinction (`n.prop` vs `n.count`) is the largest error source and needs a gazetteer
- OOV transition computation optimization not benchmarked separately in CI
- Held-out evaluation is only one text pair (Milarepa → Marpa); may not generalize

---

### Stage 08: Dependency Parsing ✅

**Module:** `src/teea/nlp/dependency/parser.py`  
**Quality:** ★★★★☆

**Strengths:**
- Rule-based parser derived from Tibetan Constraint Grammars (vislcg3)
- Ergative-absolutive alignment correctly handled
- Total: always produces a rooted, acyclic tree
- Unresolved rate is measurable (`DEP` relation, never guessed)
- Genitive attachment to following nominal configurable

**Issues:**
- Deterministic attachment may not capture all linguistic structures
- Copulas never head a clause (documented limitation)
- Flat attachment (most nominals attached directly to root)
- No statistical parser — a treebank-trained parser is future work (ADR-010)

---

### Stage 09: Named Entity Recognition ✅

**Module:** `src/teea/nlp/ner/recognizer.py`  
**Quality:** ★★★☆☆

**Strengths:**
- Gazetteer-driven (2,767 proper nouns, two tiers: confident + corroboration-required)
- Longest-match resolution for nested names
- Multi-morpheme entity support (Tibetan names span multiple syllables)
- Two evidence sources: gazetteer + proper-noun POS tag
- `BOTH` evidence when both agree

**Issues:**
- **Entities are untyped** — Figure 5 names 5 types but no data distinguishes them
- No precision/recall/F1 reported — untested against gold NER data
- No sequence model for OOV entity detection

---

### Stage 10: Terminology Recognition ✅

**Module:** `src/teea/nlp/terminology/recognizer.py`  
**Quality:** ★★★★☆

**Strengths:**
- Glossary-driven (871 Buddhist technical terms, shipped)
- User dictionary support for custom terms
- Contrastive frequency selection methodology (ADR-012)
- Longest-match resolution

**Issues:**
- Glossary is small (871 terms); coverage may be limited for specialized texts
- No automatic term extraction — users must manually add terms
- No term frequency statistics to prioritize suggestions

---

### Stage 11: Semantic Analysis ✅

**Module:** `src/teea/nlp/semantics/analyzer.py`  
**Quality:** ★★★☆☆

**Strengths:**
- Symbolic semantic graph construction
- Verb lexicon integration (1,877 lemmas, 11,711 stem surfaces, 703 frames)
- Lexicon-driven absolutive resolution (ADR-014)
- Intent classification (mood, polarity, reported speech)
- Acyclic graph guarantee
- Provenance tracking per role (CASE / LEXICON / STRUCTURE)

**Issues:**
- **No precision/recall/F1** — no gold role-annotated Tibetan corpus exists
- 74.6% of predicates lemmatized (29% of syllables never resolve to a lemma)
- 47% of roles rest on structure alone (no case particle, no lexicon frame)
- 53% of roles on case particle or lexicon (the rest are structural)
- 4,838 absolutive reclassifications — only 39.5% corroborated by gold agentive
- No semantic role gold data (ADR-014, ADR-015)
- Flat argument structure inherited from Stage 8

---

### Stage 12: Document Snapshot ✅

**Module:** `src/teea/nlp/snapshot/builder.py`  
**Quality:** ★★★★★

**Strengths:**
- Composition root for Stages 04-11
- Incremental reanalysis (FR-4): content-hash-based sentence reuse
- **2,854× faster than full re-parse** for unchanged sentences
- All stages injectable (hot-swappable per SRS 3.3)
- Deep immutability (all models are frozen Pydantic)
- Thread-safe (stateless builder)

**Issues:**
- Incremental cost linear in document size (re-segmentation + re-hashing of unchanged sentences)
- Cached analyses keyed by text alone (stage configuration not part of key — caller contract, but fragile)
- No normalization inside builder (ADR-016 — caller must normalize first)

---

## CROSS-CUTTING OBSERVATIONS

### What's Excellent
1. **Span discipline everywhere** — every stage carries exact character + byte offsets
2. **Total operations** — every stage handles empty/edge input gracefully
3. **Honest uncertainty** — ambiguity is reported, never guessed (MorphemeKind.AMBIGUOUS, DependencyRelation.DEP, RoleEvidence.STRUCTURE)
4. **Dependency Injection** — every stage has injectable collaborators
5. **Frozen models** — immutability guarantees concurrent safety
6. **Corpus-derived data** — affixes, tags, frames all from real data, not hand-authored

### What Needs Improvement
1. **No gold role-annotated data** — Stage 11 quality is unverifiable
2. **No treebank** — Stage 8 is rule-based with flat attachment
3. **Limited NER** — untyped, gazetteer-only, no ML
4. **Small glossary** — 871 terms; domain coverage uncertain
5. **No cross-sentence context** — each sentence analyzed independently
6. **No streaming support** — entire document must fit in memory

### Data Quality Metrics
| Dataset | Size | Quality |
|---------|------|---------|
| POS Model | 126 KB, 77 tags | ✅ Derived from Milarepa corpus |
| Proper Nouns | 109 KB, 2,767 entries | ✅ Two-tier quality |
| Terminology | 25 KB, 871 terms | ✅ Contrastive frequency selected |
| Verb Frames | 570 KB, 1,877 lemmas | ✅ 1,830/1,831 verified (99.95%) |
| Synthetic Errors | 10,000 records | ✅ (basic spelling only) |
| BoCorpus N-grams | JSON | ✅ Pipeline generates from authoritative source |

---

## RECOMMENDATIONS

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| High | Create role-annotated Tibetan corpus | 3-6 months | Enables Stage 11 verification |
| High | Add treebank-trained dependency parser | 2-4 months | Better attachment, improved semantics |
| Medium | Add typed NER gazetteer | 2-4 weeks | Enables entity type output |
| Medium | Expand terminology glossary | 2-4 weeks | Better domain coverage |
| Medium | Add TiBERT model card | 1 day | Legal/license clarity |
| Low | Add cross-sentence context window | 2-4 weeks | Better tokenization |
| Low | Add streaming pipeline support | 2-4 weeks | Very-large-document support |
