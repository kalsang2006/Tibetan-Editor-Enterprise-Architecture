# TEEA — Architecture Decision Record

Decisions resolving ambiguities and conflicts found in the TEEA design documents
during implementation of Stages 2–12, the whole of Figure 5. Each entry records
the ambiguity, the evidence consulted, the decision, and the consequences for
later modules.

Status of all entries: **Accepted**, 2026-07-22.

| ADR | Subject |
| --- | --- |
| 001 | Stage 03 "Document Cleaning" is an activity of Stage 02, not a module |
| 002 | SRS v5.1 supersedes `Presentation.html` — **resolved**, file removed |
| 003 | Figure 5 is the pipeline decomposition; SRS §3.1 is an ordering constraint |
| 004 | Line breaks are preserved by Stage 02, permanently |
| 005 | Boundary changes belong to Stage 06, never to Stage 07 |
| 006 | The Dictionary Repository ships in-memory, not on SQLite or LMDB |
| 007 | Tagging operates on syllables, and the model is trained on syllables |
| 008 | TiBERT is loaded with lowercasing and accent stripping disabled |
| 009 | The Tibetan constraint grammars are reimplemented, not executed |
| 010 | Stage 8 has no gold treebank, so no attachment accuracy is reported |
| 011 | Stage 9 entities are untyped, because no source distinguishes types |
| 012 | Stage 10's glossary requires two independent sources to agree |
| 013 | Stage 11 is the symbolic Semantic Graph; neural semantics is the AI Runtime's |
| 014 | Stage 11's semantic roles come from the Tibetan verb-stem lexicon |
| 015 | Stage 11's "Intent Analysis" is sentence mood, marked by Tibetan morphology |
| 016 | Stage 12 owns the FR-4 hash and the incremental mechanism, not the policy |
| 017 | The Suggestion Fusion Engine owns the suggestion format, and excludes the AI hook |
| 018 | Plugin isolation is supervised in-process execution, not separate processes |
| 019 | The AI Runtime ships orchestration and no inference engine |

**Document precedence** established by ADR-002 and ADR-003, highest first:

1. `Tibetan Enterprise Architecture.html` — SRS v5.1 (Production-Ready Spec)
2. `System Design Diagram/*.html` — Figures 1–5
3. `Project Resources.txt` — authoritative model and dataset sources
The superseded v1.0 hackathon spec has since been removed from the
repository (ADR-002), so `docs/` now contains only authoritative documents.

---

## ADR-001 — Stage 03 "Document Cleaning" is an activity of Stage 02, not a module

### Ambiguity

Figure 5 lists Document Cleaning as a discrete numbered stage (03) with three
bullets: *Remove hidden formatting · Normalize whitespace · Standardize
punctuation*. But `nlp/tokenization/normalization.py` contradicts itself: its
title says "Unicode normalization **and document cleaning** (Language pipeline
Stage 2)" while its body asserts it "owns Stage 2 **and nothing else**". It
already implements two of the three bullets. It was unclear whether Stage 03
warranted its own module.

### Evidence

| Source | Lists "Document Cleaning" as a component? |
| --- | --- |
| Figure 1, High-Level Architecture — Language Server sub-modules | **No** (lists Unicode Normalization, Sentence Segmentation, Tokenization, Morphological Analysis, POS Tagging, Dependency Parsing, NER, Semantic Graph) |
| Figure 2, Component Diagram — Language Server sub-modules | **No** (Tokenizer, Morphology, POS Tagger, Dependency Parser, Semantic Graph) |
| SRS §3.1, mandated analysis stack | **No** |
| Figure 5, Language Processing Pipeline | **Yes**, as stage 03 |

Document Cleaning appears in exactly one of four views — and that view, Figure 5,
is a *pipeline* diagram enumerating transformation **activities**, whereas
Figures 1 and 2 enumerate deployable **components**. Unicode Normalization, by
contrast, appears in both kinds of view.

### Decision

Stage 03 is an **activity owned by the Unicode Normalization component**
(`teea.nlp.tokenization.normalization.TextNormalizer`). No separate module is
created. An activity may be owned by a component without being one.

The module's title line is correct; the sentence "owns Stage 2 and nothing else"
is the error and is corrected.

**"Standardize punctuation" is deliberately deferred, not merely unimplemented.**
No document anywhere specifies what it means for Tibetan, and the most obvious
reading — folding the shad variants (`༎` → `།`) to a canonical form — would
actively damage the system: Stage 4 stores the terminator verbatim precisely so a
*nyis shad* stays distinguishable from an ordinary shad, and the add-in writes
suggestions back into the user's own document. `normalization.py` also states it
"does not alter Tibetan letters … those are the jobs of dedicated linguistic
components". Inventing orthographic policy here would violate that.

### Consequences

* Stage 03 is **complete as specified**, with one bullet consciously deferred.
* Any future punctuation standardization **must not** fold shad variants, and
  must be opt-in rather than default.
* No new package; the dependency graph is unchanged.

---

## ADR-002 — SRS v5.1 supersedes `Presentation.html`

### Ambiguity

`docs/Presentation.html` and `docs/Tibetan Enterprise Architecture.html` are both
titled "Software Requirements Specification" and describe incompatible systems.

### Evidence

| | `Presentation.html` | `Tibetan Enterprise Architecture.html` |
| --- | --- | --- |
| Version | 1.0, "Hackathon project" | **5.1, "Production-Ready Spec"** |
| Execution | Cloud services | Offline-first local daemon |
| Backend | Monlam.ai + Vercel + Supabase | TEEA Core + quantized local LLMs + SQLite/LMDB |
| Network | "user has internet access" | "independent of constant cloud service availability" |

Corroborating: all five System Design Diagrams describe the v5.1 architecture;
`Project Resources.txt` mandates TiBERT and forbids substituting another model
("Never substitute another language model unless explicitly instructed"), which
Monlam.ai would violate; and the existing codebase is entirely offline (the unit
suite performs no network access).

### Decision

**SRS v5.1 and the System Design Diagrams are authoritative.**
`Presentation.html` is superseded and carries no requirements.

### Consequences

* No cloud dependency will be introduced. Translation and summarization are
  local AI Runtime capabilities, not Monlam.ai calls.
* **Resolved.** The file has since been deleted from the repository, so the
  conflict cannot be reintroduced. This entry is retained as the record of why
  the cloud-based v1.0 design carries no requirements, in case the document
  resurfaces from another source.

---

## ADR-003 — Figure 5 is the pipeline decomposition; SRS §3.1 is an ordering constraint

### Ambiguity

SRS §3.1 states the stack "shall rigidly parse through: Normalization → Word
Tokenization → Morphological Parsing → Part-of-Speech Tagging → Structural
Dependency Mapping" — five steps omitting Document Cleaning and Sentence
Segmentation, both of which Figure 5 numbers as stages.

### Evidence

Figure 5 is a dedicated artifact ("Figure 5. Language Processing Pipeline")
enumerating twelve stages. Figure 1 independently lists Sentence Segmentation as
a Language Server sub-module, so its omission from §3.1 cannot mean it is
excluded from the architecture. §3.1's verb is "shall rigidly parse **through**",
which constrains *ordering*; it does not claim to be exhaustive.

### Decision

The two are **reconcilable, not contradictory**. Figure 5 is the authoritative
decomposition. SRS §3.1 is the mandatory ordering constraint over the subset of
stages it names. An implementation satisfying Figure 5's ordering automatically
satisfies §3.1.

### Consequences

* Implementation order follows Figure 5.
* §3.1 remains binding as an ordering check: normalization must precede
  tokenization, which must precede morphology, POS, and dependency parsing.

---

## ADR-004 — Line breaks are preserved by Stage 02, permanently

### Ambiguity

Stage 4 needs line breaks as sentence boundaries, but Stage 2 was stripping them
as Unicode `Cc` control characters — `_PRESERVED_CONTROLS` kept only `{\n, \t}`.
Word encodes a paragraph mark as **CR (U+000D)** and a manual line break
(Shift+Enter) as **VT (U+000B)**, so a real Word document arrived at Stage 4 as a
single runaway sentence, which then exceeded TiBERT's 512-token limit. Two fixes
were possible: preserve line breaks in Stage 2 permanently, or require
document-level callers to pass `strip_controls=False`.

### Evidence

* Figure 5 assigns Stage 02 "Remove **invalid** characters" and Stage 03 "Remove
  **hidden** formatting". A paragraph mark is neither invalid nor hidden — it is
  visible document structure.
* Figure 2 shows the Office.js Add-in bridging the "Document XML API", so Word's
  own text model (with CR and VT) reaches the daemon.
* `strip_controls` is all-or-nothing: disabling it to retain paragraph marks also
  retains NUL bytes, zero-width characters and other genuine junk, defeating
  "Remove invalid characters" entirely.
* The two switches address orthogonal concerns; conflating them forces callers
  into a false trade-off.

### Decision

**Preserving line breaks in Stage 02 is the permanent architectural behavior.**
`_PRESERVED_CONTROLS = {"\t"} | LINE_BREAK_CHARS`. The caller-side
`strip_controls=False` workaround is explicitly rejected.

`LINE_BREAK_CHARS` lives in `teea.core.types` and is shared by Stage 02 and Stage
04 so the two cannot disagree about what constitutes document structure. It
contains LF, CR, VT, FF, NEL, U+2028 and U+2029. The legacy information
separators (U+001C–U+001E) are excluded: they carry no meaning in a Word
document, so Stage 02 is correct to remove them as invalid characters.

### Consequences

* Document-level callers still pass `collapse_whitespace=False`, which is a
  separate and legitimate switch (collapsing is for single-sentence cleanup).
* Two Stage 02 tests that pinned the old two-element set were updated; this was a
  deliberate behavior change, not a regression.
* Any future stage that consumes document structure must use
  `core.types.LINE_BREAK_CHARS` rather than defining its own set.

---

## ADR-005 — Boundary changes belong to Stage 06, never to Stage 07

### Ambiguity

Stage 06 leaves three things unresolved: `AMBIGUOUS` morphemes, fused `ས`/`ར`
splitting, and multi-syllable particle matching. It was proposed that Stage 07
(POS Tagging) own all three, since all three need context.

### Evidence

Figure 5 splits the responsibilities explicitly. Stage 06 is *"Root extraction ·
Affix recognition · **Inflection analysis**"*; Stage 07 is *"Noun, Verb,
Adjective · **Particle & grammatical classes**"*. Deciding whether `ལས` is the
ablative particle or the noun "work" assigns a *class* — Stage 07. Deciding
whether `བུས` is one morpheme or two changes a *boundary* — Stage 06.

Figures 1 and 5 both mandate one-directional flow. A Stage 07 that re-segmented
its input would write backwards into Stage 06's output.

### Decision

* `AMBIGUOUS` resolution → **Stage 07**. Implemented.
* Fused `ས`/`ར` splitting → **Stage 06**, blocked on the Dictionary Repository.
* Multi-syllable particle matching → **Stage 06**, same blocker.

Stage 07 must preserve every input span exactly. This is enforced by test, not
convention.

### Consequences

* Now that ADR-006 provides the repository, Stage 06 can be upgraded to close
  both gaps. That is a **Stage 06 revision**, not Stage 07 scope.
* Stage 08 may rely on Stage 07 spans matching Stage 06 spans one-for-one.

---

## ADR-006 — The Dictionary Repository ships in-memory, not on SQLite or LMDB

### Ambiguity

Figure 2 places a Dictionary Repository in the Persistence Layer alongside a
SQLite store and an LMDB cache. Stage 07 needs it, but neither storage engine
exists, and building one to hold a single read-only table would be premature.

### Evidence

The payload derived from the annotated corpus is ~123 KiB and entirely read-only.
Every access is an exact-match lookup. SQLite and LMDB in Figure 2 serve the
document store, audit logs, vector cache and fingerprint index — none of which
exist yet, so neither engine is being introduced for other reasons either.

### Decision

Implement `teea.persistence` with a `DictionaryRepository` **protocol** and an
`InMemoryDictionaryRepository` loading a JSON payload. State the interface now so
the engine can change later without any consumer changing.

Only this one repository is implemented. The fingerprint index, LMDB cache and
SQLite store from Figure 2 are deliberately absent: defining interfaces for
features that do not exist would be inventing requirements.

### Consequences

* `teea.persistence` depends only on `teea.core` and **never** on `teea.nlp` —
  storage sits beneath the language layer. Enforced by `test_architecture.py`.
* Missing or malformed data raises `ConfigurationError` at construction. A daemon
  with no grammatical knowledge must fail loudly, not silently degrade.
* Provenance travels with the payload, so a deployed offline daemon can report
  which corpus its statistics came from.

---

## ADR-007 — Tagging operates on syllables, and the model is trained on syllables

### Ambiguity

The reference corpus annotates *words*, but Stage 06 emits *syllable*-level
morphemes, because Tibetan has no word delimiters and Stage 05 produces
statistical subwords rather than linguistic words. Which unit should Stage 07 tag?

### Evidence

Measured, not assumed. A model trained on word units and applied to syllables
scored **50.3%** fine-tag accuracy on held-out text. Retraining the same model on
syllable units — projecting each gold token's tag onto its constituent syllables —
scored **72.3%**. 24.6% of gold tokens span more than one syllable, which is the
size of the mismatch.

| Model | Fine | Coarse |
| --- | --- | --- |
| Most-frequent-tag baseline (syllable) | 63.1% | 79.8% |
| Bigram HMM + Viterbi (syllable) | **72.3%** | **82.0%** |

### Decision

Stage 07 tags **syllable-level morphemes**, and the Dictionary Repository payload
is built on the same unit. Train and inference units must match.

Evaluation aligns predictions to gold by character offset, which measures the
pipeline as it actually runs rather than an idealised version.

### Consequences

* Accuracy is bounded by the absence of true word segmentation. Recovering the
  remaining headroom needs a Tibetan word tokenizer, which is a **Stage 05**
  concern, not a tagger improvement.
* The largest residual error class is proper-versus-common noun, which needs a
  name gazetteer — a future Dictionary Repository addition.
* Any future tagger must be trained on syllables, or restate this decision.

---

## ADR-008 — TiBERT is loaded with lowercasing and accent stripping disabled

### Ambiguity

`TokenizationSettings.do_lower_case` existed, defaulted to `False`, and was
documented as "Tibetan script is caseless; this should almost never be enabled" —
but `default_tibert_loader` never passed it to `AutoTokenizer.from_pretrained`.
It was not clear whether that omission was deliberate deference to the model's
own configuration or an oversight.

### Evidence

Found by running the real model for the first time. TiBERT's published
`tokenizer_config.json` sets `do_lower_case=True`, which switches on BERT's
basic-tokenizer `_run_strip_accents()`. That routine deletes every character of
Unicode category **Mn** — and in Tibetan the Mn class is not accents but the
vowel signs and subjoined letters that carry the orthography.

Observed on `བཀྲ་ཤིས་བདེ་ལེགས།`:

| Loader arguments | Tokens |
| --- | --- |
| As shipped (model defaults) | `བཀ · ་ · [UNK] · ་ · བད · ་ · ལགས · །` |
| `do_lower_case=False, strip_accents=False` | `བཀྲ · ་ · ཤིས · ་ · བདེ · ་ · ལེགས · །` |

`བཀྲ` was silently rewritten as `བཀ`, `བདེ` as `བད`, and `ཤིས` became `[UNK]`.
Corpus-wide the unknown-token rate fell from far above the quality gate to 5.2%
once the flags were passed.

### Decision

`default_tibert_loader` passes `do_lower_case` from settings and pins
`strip_accents=False` unconditionally. Tibetan is caseless, so lowercasing has
nothing to do; accent stripping is actively destructive and must never be on.

### Consequences

* The defect was invisible to the hermetic suite, which uses a fake backend. It
  is now guarded by a **hermetic** regression test that stubs
  `transformers.AutoTokenizer` and asserts both keyword arguments, so it fails in
  the default run without needing network.
* Any future model adapter must make the same check. A model's published
  configuration is tuned for its training language, not necessarily for Tibetan.
* `tibert.py` previously described TiBERT as "SentencePiece unigram". The real
  model is **WordPiece**, 29,965 entries; the docstring is corrected.

---

## ADR-009 — The Tibetan constraint grammars are reimplemented, not executed

### Ambiguity

The authoritative data repository ships Constraint Grammars for Tibetan
dependency parsing (`Data/tibetan-nlp-tibcg3-735f770/grammars/`). It was not
obvious whether Stage 8 should execute them or reimplement their rules.

### Evidence

The grammars are written for `vislcg3`: their own README documents the workflow
as `cg-comp grammar.txt grammar.cg` followed by `vislcg3 -g grammar.cg`. That is
a compiled C++ toolchain, and shipping it would contradict the offline-first,
pure-Python desktop daemon of SRS v5.1 and the no-network constraint of ADR-002.

The grammars' content, however, is directly usable. They label Tibetan structure
with Universal Dependencies relations (`@arg1` in 71 rules, `@arg2` in 54,
plus `@obl`, `@case`, `@amod`, `@nmod-poss`, `@nummod`, `@det`, `@advmod`,
`@neg`, `@mark`, `@aux`), and their attachment rules key on exactly the case
marking that Stages 6 and 7 already expose:

* `SETPARENT Head_NOUN (1* (Case=Agn) …) TO (*1 (VERB))` — agentive → agent
* `SETPARENT Head_NOUN (NOT 1 (ADP)) TO (*1 (VERB))` — absolutive argument
* `SETPARENT (ADJ|NUM|DET) TO (-1* Head_NOUN …)` — modifiers follow their noun
* `Head_NOUN` includes `VerbForm=Vnoun`, so deverbal nouns head noun phrases

### Decision

Take the **relation inventory and the attachment rules** from the grammars and
implement them natively in Python. `teea.nlp.dependency.parser` is the record of
that mapping, citing the specific rules it derives from.

The relation enum contains only relations this stage actually assigns.
Enumerating the rest of UD would create members no producer emits.

### Consequences

* No external binary, and the stage stays within the offline-first constraint.
* Relation names match UD, so comparing against a UD treebank later needs no
  translation layer.
* If the grammars are revised upstream, this module must be re-derived; it does
  not track them automatically.

---

## ADR-010 — Stage 8 has no gold treebank, so no attachment accuracy is reported

### Ambiguity

Stages 6 and 7 were evaluated against gold annotations. It was not clear what
the equivalent evidence for Stage 8 should be.

### Evidence

There is **no Tibetan dependency treebank in the authoritative data
repository**. All 38 non-BDRC files were searched for `conll`, `treebank`,
`depend` and `syntax`; the only matches are the two constraint-grammar files,
which are rules rather than annotated trees. The POS-annotated corpora carry no
head or relation columns.

### Decision

Report no UAS/LAS figure. Inventing an evaluation set, or scoring the parser
against its own rules, would produce a number that looks like accuracy and is
not. What is measured instead:

* **Structural validity at scale** — 5,885 trees over 65,925 nodes from the full
  Milarepa text, every one single-rooted and acyclic with spans intact.
* **Unresolved rate** — 3.05%, the share of morphemes no rule attaches, recorded
  explicitly as `DEP` rather than given a plausible label.
* **Hand-checked linguistic cases** — agentive, absolutive, allative, genitive,
  modifier and converb attachment, each traced to a named grammar rule.

### Consequences

* Acquiring or building a Tibetan UD treebank is the highest-value next step for
  this stage, and is a prerequisite for any statistical parser.
* Until then, Stage 8's quality claims are structural and rule-coverage based,
  and should be described that way rather than as accuracy.
* **Stage 8 inherits a measured limitation from Stage 6.** Ergative alignment
  decides subject versus object from the presence of an agentive, and 1,879 of
  the 2,480 agentive tokens in the reference corpus (76%) are the fused bare
  `ས`/`ར` that Stage 6 documents it will not split (ADR-005). Those clauses read
  as intransitive, so their object is labelled `arg1`. The Dictionary Repository
  that blocked the Stage 6 fix now exists (ADR-006), so this is actionable.

---

## ADR-011 — Stage 9 entities are untyped

### Ambiguity

Figure 5 specifies Stage 9 as *"Named Entity Recognition · Person, Place, Org ·
Religious & Cultural entities"* — five entity types. It was not clear whether the
implementation should classify entities into them.

### Evidence

No available source distinguishes entity types. Searched exhaustively:

| Resource | Entity spans | Entity types |
| --- | --- | --- |
| `mila` + `marpa` annotated corpora | ✅ 2,528 `n.prop` tokens, BIOES span markers (44 B / 23 M / 44 E / +S) | ❌ every name is plain `n.prop` |
| `classical-lexicon.txt` | ✅ 3,000 proper-noun entries | ❌ untyped, across all 80 categories |

The only person/place-shaped tags in either tagset are `p.pers` (personal
*pronoun*) and `case.loc`/`cv.loc` (locative *case*) — both syntactic, neither an
entity type. The SRS does not mention named entities at all.

Deriving types would therefore require inventing linguistic data: a rule such as
"a name before `ལ` is a place" has no support in any source and would be
fabrication.

### Decision

Recognise **untyped entity spans**. No `EntityType` enum is defined.

Shipping five enum members that no code path can populate would be a speculative
API surface, and would misrepresent the system's actual capability to every
downstream consumer. Adding typing later is an **additive** change — a new
optional field on `NamedEntity` — not a redesign, so nothing is foreclosed.

What *is* modelled is the evidence behind each recognition
(:class:`EntityEvidence`: gazetteer, tagger, or both), because that distinction
is real, derivable, and useful to a consumer deciding how far to trust a name.

### Consequences

* Acquiring a **typed** Tibetan gazetteer (person / place / organisation name
  lists) is the prerequisite for satisfying Figure 5 in full, and is the highest
  value next step for this stage.
* Stage 9's quality is reported as span precision/recall against the corpus
  entity layer, not as typed-entity accuracy.
* The gazetteer is split into **confident** and **corroboration-required** tiers.
  213 lexicon entries are also filed as common nouns or adjectives, and 96 are a
  single syllable; firing on those unconditionally measured 35% precision on
  held-out text against 58% with the tier rule. This mirrors the
  unambiguous/ambiguous split Stage 6 uses for affixes.

---

## ADR-012 — Stage 10's glossary requires two independent sources to agree

### Ambiguity

Figure 5 specifies Stage 10 as *"Technical Terms · Buddhist Vocabulary · User
Dictionary"*. The User Dictionary is unambiguous — it is user-supplied. The other
two require a terminology resource, and the repository contains no term list.

### Evidence

Terminology extraction from the BDRC Buddhist canon (3,818 TEI files, CC BY 3.0)
was attempted and **measured** against the narrative corpus:

| Method | Result |
| --- | --- |
| Contrastive frequency alone | Top-ranked output is scholastic *register*: `ཕྱིར་རོ` "therefore", `ཞེ་ན` "if one says", `འགྱུར་རོ` "it becomes" |
| Plus a part-of-speech filter | Removed 70% of candidates; register formulae still ranked top |
| Plus "absent from narrative" | 5,744 candidates; register formulae **still** ranked top |
| **Plus curated-headword requirement** | **871 terms, register formulae eliminated** |

The last row is qualitatively different. Requiring the term to be a headword in
`classical-lexicon.txt` removes the formulae because they are inflected phrases,
not dictionary entries. The surviving output is recognisable Buddhist technical
vocabulary: `དེ་བཞིན་གཤེགས་པ` (*tathāgata*), `དགྲ་བཅོམ` (*arhat*), `འགོག་པ`
(*nirodha*), `བདེན་གཉིས` (the two truths), `དགག་བྱ` (*negandum*), `ལྟུང་བྱེད`
(*pāyantika*).

Critically, **no gold Tibetan term list exists in the repository**, so no filter
can be scored. That is why agreement between two independent sources — not a
tuned threshold — is the acceptance rule.

### Decision

A glossary entry must be **both**:

1. a multi-syllable headword in the curated classical lexicon, and
2. attested ≥15 times in the Buddhist canon and **zero** times in 437,000
   characters of general narrative Tibetan.

Each entry is therefore individually defensible: a curated dictionary vouches it
is a real word, and corpus contrast vouches it is domain-specific.

The **User Dictionary** is implemented as a first-class, injectable source that
takes precedence over the glossary, because a scholar who defines a term has
stated the reading they want.

### Consequences

* Glossary quality is asserted structurally and by spot check, not scored. A
  curated Tibetan terminology resource would allow real evaluation and is the
  highest-value addition to this stage.
* Recall on narrative text is low by construction (68 terms in 5,885 Milarepa
  sentences) — the glossary excludes anything occurring in narrative. That is the
  intended precision/recall trade for a *technical* term recogniser, and a test
  pins it so weakening the rule is visible.
* `TerminologyRepository` is the third facet of Figure 2's Dictionary Repository,
  stated as its own protocol for the same Interface Segregation reason as the
  gazetteer.

---

## ADR-013 — Stage 11 is the symbolic Semantic Graph; neural semantics is the AI Runtime's

### Ambiguity

Figure 5 states Stage 11 as *"Semantic Analysis · Context Graph · Meaning
Representation · Intent Analysis"* — three bullets and no further specification.
Nothing in any authoritative document defines what a "Context Graph" is, what a
"Meaning Representation" contains, or what "Intent" means. At the same time the
architecture describes semantics in several other places, and it was not clear
which of them Stage 11 is supposed to satisfy.

### Evidence

Every mention of semantics across the authoritative documents, with the component
it is attributed to:

| Source | Text | Attributed to |
| --- | --- | --- |
| Figure 1, High-Level Architecture | "Semantic Graph" among Language Server sub-modules | **Language Server** |
| Figure 2, Component Diagram | responsibility "Semantic Graph Construction"; sub-module "Semantic Graph" | **Language Server** |
| Figure 3, Level-1 DFD | P4 Language Server bullet "Semantic Processing"; edge to Plugin Runtime labelled "Parsed Tokens / **Graph**" | **Language Server** |
| Figure 5, stage 11 | "Context Graph · Meaning Representation · Intent Analysis" | **Language Server** |
| Figure 6, AI Runtime | outputs "Semantic Features", "Similarity Scores" | AI Runtime |
| Figure 7, Suggestion Fusion | "AI Runtime (Semantic & Context Verification) · Semantic validation · Context verification" | AI Runtime |
| Figure 9, Deployment | "Embedding Model · Semantic Vectors · Vector Similarity · 768-dim space" | Local AI Models |
| SRS §1.2 | "semantic coherence evaluation via quantized offline language models" | AI Runtime |

The split is consistent and one-directional. Every *graph* reference names the
Language Server; every *vector*, *feature*, *similarity* and *model* reference
names the AI Runtime or the model repository. No document places an embedding
inside the Language Server.

Unlike Stages 09 and 10, no ownership audit was needed: Figure 1 and Figure 2
both list this as a component, so it is unambiguously one.

### Decision

**Stage 11 builds a symbolic semantic graph, deterministically, from the output
of Stages 06–10.** It performs no inference and loads no model.

The embedding-based semantics the architecture also describes belongs to the **AI
Runtime**, a separate component this repository does not implement. Building it
here would put a 768-dimensional model inside the Language Server, which no
document asks for, and would break the offline, sub-50 ms interactive path that
NFR 5.1 requires of this layer.

**Scope is one sentence, not one document.** Figure 5 places Stage 12 immediately
after as *"Immutable Document Snapshot · Store parsed representation · Shared by
plugins"* — an aggregation of all prior stage output. Document-level assembly is
therefore Stage 12's job, and Stage 11 produces one graph per sentence, as every
stage from 04 onward does. This also keeps FR-4 satisfiable: paragraph hashing
means only modified sentences are re-parsed, which requires the per-sentence
artifact to stand alone.

The three Figure 5 bullets are three views of one artifact rather than three
products, so `SemanticGraph` carries all three: the graph itself is the *Context
Graph*, its predicate-argument content is the *Meaning Representation*, and
`SemanticGraph.intent` is the *Intent Analysis*.

### Consequences

* `teea.nlp.semantics` depends on `core`, `dependency`, `ner`, `terminology` and
  `persistence`, and on nothing above it. The dependency graph stays acyclic.
* A future statistical implementation satisfies the same `SemanticAnalyzer`
  protocol, which is what SRS §3.3's hot-swapping requirement asks for. Nothing
  here forecloses it.
* Stage 12 must aggregate these per-sentence graphs; it must not re-derive them.

---

## ADR-014 — Stage 11's semantic roles come from the Tibetan verb-stem lexicon

### Ambiguity

"Meaning Representation" is undefined. The obvious content for it is
predicate-argument structure with semantic roles, but Stage 08 already labels
arguments `arg1`/`arg2`/`arg3`/`obl`, so a role layer that merely renamed those
would add nothing — and inventing a role ontology with no data behind it is
exactly what ADR-010, ADR-011 and ADR-012 refused to do.

### Evidence

The authoritative data repository ships a resource no earlier stage used:

> `Data/tibetan-nlp-lexicon-of-tibetan-verb-stems-802ef02/` — the digital edition
> of Hill, Nathan W. (2010) *A Lexicon of Tibetan Verb Stems as Reported by the
> Grammatical Tradition.* Munich: Bayerische Akademie der Wissenschaften.

This is the **same repository directory family** whose Constraint Grammars ADR-009
already established as the authoritative source for Tibetan argument structure.
It reports, per dictionary entry:

| Field | Source file | Coverage |
| --- | --- | --- |
| lemma for each inflected stem | `verbs-with-lemmas.txt` | 75,624 surface rows → 11,711 syllable keys |
| argument frame (`Erg-Abs`, `Abs-Obl`, …) | `lemmas.txt` `<syntax>`, after Hackett (2003) | 703 / 1,877 entries |
| transitivity | `dictionary.xml` `<transitivity>` | 1,456 / 1,877 entries |
| volition | `lemmas.txt` `<volition>` | 1,351 / 1,877 entries |

#### How the coverage figures were measured

Stated precisely, because "coverage" can mean four different things.

**Denominator.** The 60,544 annotated tokens of `Data/Texts/mila-horizontal.txt`,
restricted to the **13,760 tokens whose gold tag begins `v.` or `n.v.`** — i.e.
gold-annotated verbal tokens, at the corpus's own word-level tokenization.

**Numerator.** A token counts as covered when its gold surface string is present
as a key in the lexicon's surface table (trying the form as written and with a
trailing tsheg).

| Measure | Result |
| --- | --- |
| **Occurrences** (tokens) — 13,105 / 13,760 | **95.2%** |
| **Types** (distinct surfaces) — 2,109 / 2,365 | **89.2%** |
| Missed types | 256, accounting for 655 occurrences |

The occurrence figure is the higher of the two because frequent verbs are covered
and each is counted every time it appears; both are reported so neither is
mistaken for the other.

Two limits on what this figure means:

* It measures **lookup-key presence, not lemma correctness.** No gold lemma
  annotation exists in the repository, so lemma accuracy is not measured and is
  not claimed.
* It is measured on the corpus's own **word-level** tokens. The running pipeline
  emits **syllables** (ADR-007), which is a harder case; measured end to end,
  **74.6% of predicate nodes resolve to a lemma**. That is the figure that
  describes the shipped system, and it is the one a regression test pins.

`lemmas.txt` and `dictionary.xml` are joined **positionally**, which is only sound
if they agree row for row. That was verified against a third file,
`cg3-lemmas.txt`, which states the same entries independently as Constraint
Grammar rules: **1,830 of 1,831** entries agree on both frame and volition. The
builder aborts below 99%.

**Why this is derivation, not invention.** The precedent is ADR-009: the CG3
grammars were not executed but their *rule content* was reimplemented natively,
with the module recording the mapping. The same standard applies here. Each role
name is a label for a distinction the sources already draw:

| Role | Assigned from | Attested as |
| --- | --- | --- |
| `AGENT` | `case.agn` | 4,123 corpus tokens |
| `PATIENT` / `THEME` | the predicate's `Erg`/`Abs` slots | 703 lexicon frames + 1,456 transitivity labels |
| `GOAL` | `case.all`, `case.term` | 7,847 corpus tokens |
| `LOCATION` | `case.loc` | 418 |
| `SOURCE` | `case.abl`, `case.ela` | 897 |
| `ASSOCIATE` | `case.ass` | 1,648 |
| `STANDARD` | `case.comp` | 61 |
| `POSSESSOR` | `case.gen` | 6,470 |
| `MODIFIER` | Stage 08 `amod`/`nummod`/`det`/`advmod` | — |
| `SUBORDINATE` | Stage 08 `mark` on a verb | — |
| `UNSPECIFIED` | nothing decided | 1.4% of edges |

No role exists that no producer can populate — the failure mode ADR-011 rejected.

### Decision

Semantic roles are assigned in order of directness — **case particle, then the
predicate's attested frame, then Stage 08's structural reading** — and every edge
records which applied, as `RoleEvidence.CASE`, `LEXICON` or `STRUCTURE`. Where
nothing decides, the role is `UNSPECIFIED`, recorded rather than guessed, exactly
as Stage 08 records `DEP`.

The frame is kept **verbatim** (`"Erg-Abs"`, not canonicalized), following the
discipline Stage 04 applies to terminators and Stage 07 to corpus tags, so every
entry stays traceable to its source row.

Where a surface maps to several dictionary entries that disagree, no lemma and no
transitivity is reported — "recognize, don't guess" (ADR-005). An entry that
reports nothing is not treated as disagreement, because discarding the only
evidence available would be worse than using it.

### Consequences

* **The measured payoff is a reclassification, and only part of it can be
  validated.** ADR-010 records that Stage 08 reads the object of a transitive
  clause as its subject whenever the agentive is the fused `ས`/`ར` Stage 06 will
  not split. The verb's own frame decides instead, without any agent being
  written. Over the full 5,885-sentence corpus, **4,838 arguments (13.2% of all
  edges) that Stage 08 read as subjects are relabelled patients on lexical
  evidence.**

  **That count is "changed", not "verified".** No gold semantic-role annotation
  exists for Tibetan in this repository, so no precision figure is obtainable for
  the relabelling itself. What is obtainable is corroboration of the judgement it
  rests on. The reclassification fires exactly when the frame says the clause is
  transitive but the pipeline saw no agentive; the gold corpus annotates the
  agentive as its own token, so where the gold annotation for the same sentence
  *does* contain `case.agn`, the clause really is transitive and Stage 08's
  reading really was wrong. Aligning gold tags by character offset (the method
  ADR-007 established):

  | | Full corpus | Shipped test fixture |
  | --- | --- | --- |
  | Arguments reclassified | 4,838 | 467 |
  | ...in a sentence with a gold agentive — **corroborated** | 1,913 (**39.5%**) | 157 (33.6%) |
  | ...no gold agentive anywhere — **not decidable** | 2,925 (60.5%) | 310 (66.4%) |

  This is a **lower bound, not precision**, for two reasons. It validates the
  *clause-level transitivity* the reclassification rests on, not that this
  particular argument is the patient rather than something else. And Tibetan
  drops arguments freely, so a transitive verb with no written agent anywhere is
  ordinary — the undecidable 60.5% is not a 60.5% error rate. A regression test
  pins both the count and the corroborated share.

  The same measurement independently confirms the upstream gap ADR-010 describes:
  the gold annotation contains an explicit `case.agn` in 1,999 sentences, and the
  pipeline produces no `case.agn` morpheme in **1,419 of them (71.0%)** — the
  sentence-level counterpart of ADR-010's 76% token-level figure.
* **53.0% of roles rest on a resource** (19.5% case, 33.5% lexicon); the
  remaining 47.0% are Stage 08's structural reading, carried through unchanged
  and labelled as such rather than presented as a lexical finding.
* No accuracy figure is reported. There is no Tibetan semantic-role-labelled
  corpus in the repository, so the same rule as ADR-010 applies: what is measured
  is coverage, evidence composition and the unresolved rate, and those are
  described that way rather than as accuracy. Acquiring or building a
  role-annotated Tibetan corpus is the highest-value next step for this stage.
* The `ArgumentSlot` enum names case labels, not roles, because that is what the
  lexicon says. Interpreting a case slot as a role is the language layer's job,
  not the storage layer's.
* If the lexicon is revised upstream the payload must be rebuilt; it does not
  track it automatically.

---

## ADR-015 — Stage 11's "Intent Analysis" is sentence mood, marked by Tibetan morphology

### Ambiguity

Figure 5's third Stage 11 bullet is "Intent Analysis". Nothing defines it. Two
readings are available:

1. **Sentence mood** — the illocutionary force the sentence marks: does it state,
   ask or command?
2. **User intent** — what the writer wants the tool to do (translate this,
   summarize that).

### Evidence

Reading 2 is not implementable here and does not belong here. It is a property of
a *user action*, not of a text: Figure 2 puts command routing in "Application
Busses & Sched. · Command / Query / Event Busses" and capability selection in the
"Capability Registry", both outside the Language Server. No corpus, lexicon or
document in the repository carries any annotation of user intent. Building it
would be inventing both the data and the requirement.

Reading 1 is directly supported. Tibetan marks mood morphologically, and the
reference tagset — already shipped in the Stage 07 Dictionary Repository — names
the markers explicitly. Counts across both annotated corpora:

| Marker | Tags | Occurrences |
| --- | --- | --- |
| Question | `cv.ques`, `p.interrog` | 188 + 590 |
| Command | `v.imp`, `cv.imp`, `n.v.imp` | 1,042 + 226 + 18 |
| Negation | `neg`, `v.neg`, `v.cop.neg`, `n.v.neg` | 1,613 + 302 + 80 + 319 |
| Reported speech | `cl.quot`, `case.nare` | 220 + 117 |

Every one of these is an attested tag with a count, in the tagset the pipeline
already emits. Nothing has to be invented.

Over the 5,885-sentence corpus the classifier outputs 84.4% declarative, 8.6%
imperative, 7.0% interrogative, 19.4% negative and 4.4% reported.

**These are output distributions over one corpus, not accuracy figures.** Neither
annotated corpus carries a gold mood label, so nothing here is scored against a
reference. What the distribution supports is a weaker claim: it is the shape a
dialogue-heavy hagiography should produce, and it shows the classifier is reading
real morphology rather than defaulting to declarative. A test asserts that all
three moods occur and that declaratives outnumber questions — a property, not a
number.

### Decision

`SentenceIntent` reports **mood** (declarative / interrogative / imperative),
**polarity** (affirmative / negative) and whether the sentence is **reported
speech**, each derived from attested mood morphology.

Interrogative marking outranks imperative marking, because the question particle
scopes over the clause it closes while an imperative stem is a property of the
verb inside it. Declarative is the *unmarked* case: it is what remains when
nothing marks anything else, not a positive finding — and `is_marked` says so.

Every classification carries `evidence`: the fine-grained tags that decided it, in
surface order and deduplicated. That is the audit trail, in the same spirit as
Stage 07's `was_ambiguous` and Stage 09's `EntityEvidence`. A consumer wanting a
stricter rule — treating only the dedicated `cv.ques` particle as a question, and
not the interrogative pronoun, which Tibetan also uses as an indefinite — can
apply it to these tags without re-deriving the analysis.

### Consequences

* Mood is a property of the sentence, not of its concepts, so it is reported even
  when no node survives (a sentence of punctuation and a negation particle still
  reports negative polarity). Pinned by test.
* Reported speech is surfaced because it is actionable: a grammar checker must
  leave a quotation as the author wrote it.
* No accuracy figure is reported. Neither corpus carries a gold mood annotation,
  so the same rule as ADR-010 applies — distribution and marker coverage are
  reported, not accuracy.
* Should user-intent classification ever be required, it belongs to the
  Application Layer's command bus, not to the Language Server, and would be a new
  component rather than a change here.

---

## ADR-016 — Stage 12 owns the FR-4 hash and the incremental mechanism, not the policy

### Ambiguity

The Stage 12 brief left three questions open, all of them about where a boundary
falls rather than about what to build.

1. SRS 3.1 requires "a centralized paragraph-hashing framework (e.g., xxHash
   checks) to ensure only modified sentences trigger full pipeline re-parsing",
   but no hashing code existed anywhere. Does it belong to Stage 12 or to the
   daemon?
2. FR-4 implies the snapshot supports *incremental replacement*. Is that a Stage
   12 requirement or an IPC-layer one?
3. Which hash? xxHash is named, but only as an example.

### Evidence

**On ownership.** FR-4 states it plainly: *"The **Language Server** shall run
paragraph-level hash checks to enforce incremental processing execution rules."*
The Language Server is this repository. Figure 5 calls Stage 12 "read-only
centralized processing **state**", and a hash is only useful as a cache key when
it is stored beside the thing it keys — putting the hashes anywhere else would
mean the daemon holding a parallel index of the snapshot's contents and keeping
the two in step.

The complementary requirements sit elsewhere just as plainly. FR-1 gives the
*client* the debounced typing interval and FR-2 gives it the minimal patch layer;
neither is a Language Server responsibility, and neither is implemented here.

**On what makes reuse sound.** Every stage from 06 onward consumes only the
sentence's own text, and every span it emits is relative to that sentence. An
analysis is therefore a pure function of the sentence string and stays valid when
the document around it changes — even when the sentence moves, because nothing in
the analysis records where it was. Only the Stage 04 `Sentence` carries a document
position. That property was not designed for Stage 12; it falls out of decisions
already taken, and it is what makes the incremental path a rebinding rather than
a re-analysis.

**On the algorithm.** Three candidates were measured over the 725 KB reference
document:

| Candidate | Throughput | Verdict |
| --- | --- | --- |
| `zlib.crc32` | 2,432 MB/s | **Rejected.** 32-bit: over 5,885 sentences the birthday bound gives ~0.4% chance of a collision per document, and a collision silently returns *another sentence's analysis*. |
| `xxhash` | — | **Rejected.** A third-party C extension, and the first runtime dependency that would be added for something the standard library already covers. Being non-cryptographic it would still need a collision policy. |
| `hashlib.blake2b`, 16-byte digest | 472 MB/s | **Chosen.** |

Cost is not the deciding factor — blake2b runs at **0.7 µs per sentence** against
roughly 780 µs to analyse one, so under 0.1% of the work it saves. Width is: at
128 bits, collisions can be ignored rather than handled, which removes a failure
mode from the incremental path entirely. `hash()` is excluded because it is
salted per process and a daemon restart would invalidate every key.

### Decision

**Stage 12 owns the mechanism; the daemon owns the policy.**

* `sentence_hash` lives in `teea.nlp.snapshot` and is `blake2b` at 16 bytes.
  It is exported, so a future daemon can hash a paragraph before deciding whether
  to call at all.
* `SentenceAnalysis.content_hash` is a validated field, not a derived property:
  a snapshot cannot carry a hash that disagrees with its own text.
* `DocumentAnalyzer` states **two** methods. `analyze` is the cold path;
  `reanalyze(previous, text)` is the FR-4 path. Putting both on the protocol means
  an implementation cannot satisfy the contract while quietly re-parsing
  everything on every keystroke.
* `reanalyze` must return a snapshot **equal** to what `analyze` would return for
  the same text. Reuse is an optimisation, never a difference in result, and a
  test asserts the equality rather than trusting it.
* Debouncing, patch extraction and transport are **not** implemented here. They
  are FR-1 and FR-2, and they belong to the add-in and the IPC boundary.

**Stage 12 does not normalize.** Stage 02 can change the length of the text, so
normalizing inside the builder would produce a snapshot whose offsets address a
string the caller never passed. The caller applies Stage 02 first, exactly as
Stage 04 already requires of its own input.

**Stage 05's subword encoding is not stored.** Figure 5 places tokenization in the
chain, but the implemented chain reaches Stage 06 through *syllable*
segmentation; the TiBERT encoding is a parallel product consumed by the AI
Runtime. Storing it would make the snapshot — and every test that builds one —
depend on the model, for a consumer that does not exist.

### Consequences

* Measured on the 241,882-character reference document: an edit re-parses
  **exactly one sentence of 5,885**, pinned by a test that counts calls into
  Stage 06 rather than by a wall-clock assertion.
* Incremental cost is linear in document size, because the document must be
  re-segmented (an edit can move every boundary after it) and every sentence
  re-hashed. Measured p50: **3.0 ms at 2,000 characters, 10.2 ms at 10,000,
  39.1 ms at 50,000**, and ~0.7 s for the 241,882-character book-length text.
  Ordinary documents therefore fit inside NFR 5.1's 50 ms even on the interactive
  path; a book-length one must run on the background pipeline SRS 3.2 provides.
* An unchanged, unmoved sentence keeps its **existing analysis object**, so a new
  snapshot shares structure with its predecessor. Measured at 1.15 µs to check
  against 35.3 µs to reconstruct, and it is the common case, since an edit is
  made at the cursor and everything before it is unmoved.
* The snapshot is deeply immutable — every reachable model is frozen and every
  container is a tuple or frozenset — so Figure 5's concurrent plugin reads need
  no lock. A test walks the whole object graph and asserts it, rather than
  trusting the outermost model's flag.
* **A cached analysis is keyed by text alone.** A caller that swaps a stage for a
  different implementation and then calls `reanalyze` with an older snapshot
  would reuse analyses produced by the *previous* configuration. Making the key
  configuration-sensitive would require every stage from 04 to 11 to expose a
  fingerprint, which is a redesign of eleven accepted stages for a case a single
  builder instance cannot reach. It is documented as a caller contract instead:
  a snapshot belongs to the builder that produced it.

---

## ADR-017 — The Suggestion Fusion Engine owns the suggestion format, and excludes the AI hook

### Ambiguity

Figure 7 is a dedicated diagram for this component and specifies seven stages in
a fixed order, but implementing it raised four questions the diagram does not
answer outright.

1. A `Suggestion` is a contract *between* the Plugin Runtime and this engine, and
   neither component existed. Which one defines it?
2. The stages run Conflict Resolution **before** Confidence Ranking, yet conflict
   resolution must "select best candidate" — which needs a notion of better.
3. Figure 7 attaches the **AI Runtime** to the Merge Engine and Confidence
   Ranking for "Confidence adjustment · Ranking assistance". That component does
   not exist here. Build the hook, or leave it out?
4. SRS §1.2 and §3.2 call the fusion *streaming* and *asynchronous*. The whole
   repository is synchronous. Does this component introduce async?

### Evidence

**On ownership.** Figure 7 settles it inside its own boundary: "Normalize
suggestion format" is a bullet of the **Suggestion Collector**, which is a
sub-component of the fusion engine. The format is therefore this component's
concern and a plugin conforms to it, not the reverse.

**On ordering.** There is no contradiction. Figure 7 lists **Score** among what
the plugins emit — "Outputs: Suggestions, Score, Priority" — so a score exists
from the moment a suggestion is collected. Conflict resolution ranks candidates
by that input; the Confidence Ranking stage orders the survivors for
presentation. The score is the input, the ranking is the output.

Priority dominates confidence for the same structural reason: the Priority
Manager sits *after* Confidence Ranking, so it is applied last. Any other reading
makes a priority class mean nothing.

**On the AI hook.** ADR-006 established the rule when it declined to define
interfaces for the fingerprint index, the LMDB cache and the SQLite store:
"defining interfaces for features that do not exist would be inventing
requirements". ADR-013 applied the same rule to keep embeddings out of the
Language Server. The AI Runtime is a separate component with a dedicated diagram
of its own (Figure 6) and no implementation here.

**On streaming.** SRS §3.2's requirement is about *scheduling* — "Deterministic
feedback actions must paint onto the Word UI immediately, processing slower
contextual targets in background pipelines" — not about the fusion algorithm.
ADR-016 drew exactly this line for incremental re-analysis: the Language Server
decides *what* needs re-analysis, the daemon decides *when* to ask.

### Decision

* **The suggestion format lives in `teea.fusion`.** `Suggestion` carries the
  plugin's identity, the range, an optional replacement, its own score and its
  priority. Score and priority are **required**, because Figure 7 lists both as
  plugin outputs and a defaulted score would silently rank as certainty.
* **`replacement` is optional, and that is forced by the diagram.** Figure 7's
  output package mixes "Grammar Corrections", which rewrite text, with
  "Plagiarism Warnings" and "Summary & Citations", which do not. A suggestion
  with a replacement is an *edit* and competes for its range; one without is an
  *advisory* that competes with nothing and never reaches the patch.
* **Confidence is the plugin's score under an operator-supplied weight**, their
  product clamped to `[0, 1]`. Weights are injectable and default to equal trust,
  because there is no defensible default ranking of plugins that do not exist.
* **Priority first, then weighted confidence, then a total tie-break** on span,
  source and replacement. Without the tie-break two equally urgent, equally
  confident suggestions would order arbitrarily and the task pane would differ
  between identical runs.
* **No AI Runtime hook is provided.** When that component is built, adding
  confidence adjustment is an additive change to this engine, not a redesign.
* **The engine is synchronous, deterministic and order-independent.** Plugins
  report concurrently, so the collector sorts into a canonical order first and
  every later stage folds over it: the result is a function of the *set* of
  suggestions, not of their arrival sequence. A daemon streams by calling `fuse`
  again as more plugins report; that is cheap because fusion is cheap.
* **`teea.fusion` depends on `teea.core` alone.** Figure 3 routes plugin results
  into this engine, not parsed text, and fusion is arithmetic over document
  ranges rather than linguistics. Neither direction of dependency with
  `teea.nlp` is permitted, and both are enforced by test.

### Consequences

* Everything discarded is returned with a reason —
  `INVALID_RANGE`, `NO_OP`, `DUPLICATE`, `SUPERSEDED` — rather than dropped in
  silence, following the discipline Stage 08 set for unattached morphemes and
  Stage 11 for unresolved roles.
* `fuse` is **total**: no suggestion, however malformed its range, can raise.
  That is what NFR 5.3 requires of a component fed by sandboxed plugins, and it
  is why the Validator filters rather than throws.
* **"Preserve formatting" is honoured only as far as this layer can.** An edit
  operation names solely the range it rewrites, so every character outside it
  keeps its formatting. Word's own formatting model lives behind the Office.js
  bridge and nothing here represents it; a richer guarantee needs the add-in.
* **Conflict resolution keeps its claims in start order.** Comparing every
  candidate against every claim is quadratic in the number of *survivors*, and
  survivors are the common case — a spell checker flags scattered words that do
  not overlap at all. Measured: 6,400 realistic suggestions took **11.3 s** that
  way against **69 ms** with the sorted index, a **163x** improvement, with
  `conflicts_with` calls falling from 296,373 to 11,568. The scan is kept in the
  suite as a correctness oracle, and a work-counting test bounds the comparisons
  at four per candidate.
* A first attempt at that index examined only the two nearest claims and was
  **wrong**: several claims can begin inside one wide candidate, and naming the
  leftmost rather than the highest-ranked would have misreported to the user
  which suggestion won. The oracle caught it. The shipped version walks the
  claims the candidate actually spans.

---

## ADR-018 — Plugin isolation is supervised in-process execution, not separate processes

### Ambiguity

FR-5 states: *"The runtime shall isolate individual feature plugins into separate
**memory supervisors**."* That phrase reads like process isolation. Nothing else
in the documentation says how isolation is to be achieved, and the choice decides
the component's entire shape.

### Evidence

**Figure 5 rules out copying the input.** Its Feature Plugins Layer band reads
*"All plugins consume the **centralized** immutable snapshot **concurrently**"*.
Process isolation would require serialising that snapshot once per plugin, which
would make it neither centralized nor shared. Measured: the reference document's
snapshot is **43.3 MiB** as JSON, so eight plugins would move roughly 350 MiB per
keystroke — against NFR 5.1's 50 ms interactive budget.

**NFR 5.3 states the requirement in terms of capture, not separation:** *"A system
fault or unhandled error inside a particular feature plugin must be captured by
its **manager** without causing the host Word interface or other running tools to
crash."* What must be guaranteed is that a fault is contained and the others keep
working. That is a statement about observable behaviour, and it is satisfiable
without process boundaries.

**Stage 12 was already built for this.** ADR-016 established that the snapshot is
deeply immutable -- every reachable model frozen, every container a tuple or
frozenset, verified by a test that walks the whole object graph. Concurrent
readers therefore need no lock and cannot corrupt each other's view. The
"separate memory" property FR-5 reaches for is already provided by immutability
rather than by address-space separation.

**Threads do not help, measured.** Eight pure-Python plugins over a 50,000-
character document: **38.1 ms sequential against 43.6 ms threaded (0.87x)** --
slower, because the work is GIL-bound. Concurrency is a requirement of the
architecture, not a free win, and defaulting it on would cost performance while
appearing to satisfy Figure 5.

### Decision

**Isolation is supervised in-process execution.** Every call into a plugin is
wrapped; every exception below `BaseException` becomes a recorded
`PluginFailure`; one plugin's fault leaves every other plugin's result untouched.
`dispatch` is **total** -- no plugin, however it misbehaves, can raise out of it.

`KeyboardInterrupt` and `SystemExit` are deliberately **not** caught. They are the
operator shutting the daemon down, and swallowing them would make it unkillable.

**Concurrency is injected, never owned.** The runtime accepts a
`concurrent.futures.Executor` and dispatches through it; the default is
sequential. NFR 5.1 gives the daemon "a tiered priority scheduler", and a
component that silently spawned its own threads would sit outside that
scheduler's control and leak them at shutdown. Results are ordered by plugin name
either way, so switching an executor in or out cannot change what the user sees.
This is the same mechanism-versus-policy split ADR-016 and ADR-017 drew.

**Attribution is verified, not trusted.** ADR-017 has the Fusion Engine weight
suggestions by their source, so a plugin attributing output to another would
borrow its trust. `PluginOutcome` rejects any suggestion whose source is not the
plugin the runtime dispatched, and that rejection is contained on the same path
as a crash -- a plugin that lies about its identity is a misbehaving plugin.
Plugin names are read **once**, at registration, so identity cannot drift.

**No concrete plugin is shipped.** Figure 5 names eight; each is a component in
its own right with its own requirements and data. The runtime is complete without
them, exactly as the Fusion Engine is (ADR-017). Figure 2's "Dynamic Module
Discovery" belongs to the Capability Registry, a separate component that is not
implemented; loading code from disk here would be inventing it.

### Consequences

* **What this does not buy.** In-process supervision does not contain a plugin
  that segfaults a C extension, exhausts memory, or blocks forever. Those need
  process isolation, and process isolation needs a snapshot representation
  cheaper to move than 43 MiB of JSON -- a shared-memory or handle-based
  encoding that no document specifies and nothing in the system needs yet. This
  is a documented limit, not an oversight: if a deployment must host untrusted
  third-party plugins, revisit this ADR rather than working around it.
* Plugin faults get their own error-code domain, `TEEA-2xxx`, added to the
  existing taxonomy: `PLUGIN_EXECUTION_FAILED` and `PLUGIN_CONTRACT_VIOLATED`.
  A plugin raising a typed `TEEAError` keeps its own code, so a misconfigured
  plugin stays distinguishable from a crashing one.
* Dispatch returns **one outcome per registered plugin**, successful or not.
  Returning only what succeeded would leave the add-in unable to tell a plugin
  that found nothing from one that crashed -- the distinction it needs in order
  to tell the user that part of the analysis is missing.
* **Runtime overhead is negligible**: 1.8-13 microseconds per plugin for
  dispatch, and ~4-8 microseconds more on the supervision path when a plugin
  actually fails. Measured across documents from 10,000 to 241,882 characters,
  the cost does not depend on document size -- it is per plugin, not per
  sentence.
* The sandbox was validated against real data rather than only synthetic faults.
  A plugin reaching for `graph.nodes[0]` raises `IndexError` on any sentence made
  only of grammatical words, and three such sentences occur in the first 50,000
  characters of the reference corpus. The runtime contained it and the
  well-behaved plugins beside it still delivered; a test pins that.

---

## ADR-019 — The AI Runtime ships orchestration and no inference engine

### Ambiguity

Figure 6 draws the AI Runtime with an **ONNX Runtime** box that "executes neural
nets" and a Local AI Models Layer holding TiBERT, translation, grammar and
embedding models. Taken literally, implementing the component means shipping a
neural-network execution backend and the models it runs. But every one of those
is out of scope by rule and by prior decision: no concrete model, no ONNX, no
networking may be implemented; ADR-013 recorded that the AI Runtime "does not
exist in this repository" and kept embeddings out of Stage 11 on that basis; and
ADR-006 established that TEEA does not build infrastructure for a feature that
does not yet exist. So what, of Figure 6, is actually to be built?

### Evidence

The SRS resolves it directly. §3.3 requires the runtime to "encapsulate target
models behind **clear abstract API adapters**, enabling immediate hot-swapping
between local configurations (**e.g., ONNX runtimes**) and network APIs", and
FR-6 requires it to "map inference requests using a flexible capability registry
to switch underlying weights easily".

Read together, the ONNX Runtime of Figure 6 is **one adapter behind an
abstraction the SRS names explicitly** -- not the component itself. The component
is the orchestration around that adapter: the registries, the routing, the
lifecycle, the resource accounting. That is exactly the part that can be built as
pure-Python, offline, deterministic infrastructure without a model, and it is the
part every other TEEA component has been built as: the tokenizer injects a
`BackendTokenizer` loader and ships none of its own (Stage 05); persistence
states repository protocols and ships no SQLite (ADR-006); the Plugin Runtime
runs plugins and ships none (ADR-018).

The storage half of Figure 6 -- "Model Registry DB", "Inference Cache" -- is
governed by ADR-006 already: registries ship in memory until a feature needs an
engine, and none does.

### Decision

**The AI Runtime ships the orchestration and no inference engine.** Concretely,
`teea.ai` provides:

* the domain models -- `ModelDescriptor`, `InferenceRequest`, `InferenceResponse`,
  `ExecutionContext`, `HealthReport`, and the `CapabilityKind` enum, which is
  exactly Figure 6's seven Outputs;
* the **Model Registry** and **Capability Registry** (Figure 6 boxes), in-memory
  per ADR-006, with deterministic version-aware routing for FR-6;
* `LocalAIRuntime`, which composes them into lifecycle management, lazy loading
  and unloading, inference orchestration, an LRU memory budget (the Memory
  Manager), and health monitoring;
* the `InferenceEngine` **protocol** -- Figure 6's Model Loader + ONNX Runtime --
  which is the SRS 3.3 adapter and the sole extension point. A future ONNX-backed
  engine, or any other, implements it and drops in without the runtime changing.

No `InferenceEngine` implementation ships, because no model exists to run. The
runtime never touches a tensor: the engine owns the weights, keyed by
`ModelDescriptor.key`, and the runtime owns only metadata, routing and residency
accounting, so the two never duplicate state.

**Scheduling stays the daemon's.** Figure 6's CPU Scheduler ("Background
inference") and GPU Resource Manager are represented as *policy* -- an
`ExecutionContext` carrying a `Device` preference to the engine -- not
reimplemented as hardware managers. Execution is synchronous and deterministic;
when and on which thread to run is the daemon's tiered scheduler (NFR 5.1), the
same mechanism-versus-policy split ADR-016 and ADR-018 drew.

### Consequences

* `teea.ai` depends on `teea.core` alone. A feature plugin holds a runtime and
  calls it, so the dependency runs plugin-to-runtime; the runtime imports neither
  the Language Server, the Fusion Engine nor the Plugin Runtime, and nothing
  below it imports the runtime. Both directions are enforced by test.
* Failures raise a typed `AIRuntimeError` (`TEEA-3xxx`). Because the Plugin
  Runtime preserves a `TEEAError`'s code when it captures a plugin's exception
  (ADR-018), a model failure inside a plugin surfaces to the add-in as, say,
  `TEEA-3005` rather than a generic crash -- the two components compose without
  knowing about each other, and an integration test pins it.
* The memory budget defaults to **unlimited**. With no model declaring a real
  footprint, a finite default would evict arbitrarily; a budget is opt-in, and
  turns on LRU eviction (the Memory Manager) when set.
* **Routing is O(providers-per-capability)** -- `resolve` takes the highest
  version among the models offering a capability. Measured at realistic model
  counts (Figure 6 names about four; the test registers seven in two versions)
  dispatch is **4.7 microseconds**, of which routing is 1.2. It rises only when
  hundreds of models offer *one* capability, which the architecture does not
  anticipate, so it is left O(n) rather than optimised -- the measurement does
  not justify the added registration-time bookkeeping.
* Building an ONNX-backed `InferenceEngine`, and acquiring the quantized TiBERT
  and other weights the Local AI Models Layer names, is the next step for this
  component. It is an additive change -- one new class implementing an existing
  protocol -- not a redesign.

---

## Consequences for the layers above (Plugin Runtime, AI Runtime, IPC, add-in)

Figure 5's twelve stages are complete. Everything below now constrains the layers
that consume them rather than the pipeline itself.

1. **No new module for Stage 03.** Later stages must not assume a
   `document_cleaning` package exists.
2. **Terminator fidelity is a system invariant.** No stage may canonicalize shad
   variants; the add-in round-trips text into the user's document.
3. **Offline-only.** No stage may introduce a cloud dependency (ADR-002).
4. **Shared character classes live in `core.types`** — `SHAD_CHARS`,
   `TSHEG_CHARS`, `LINE_BREAK_CHARS`. Stages must not redefine them locally.
5. **Ordering per SRS §3.1** — morphology, POS, and dependency parsing follow
   tokenization in that order.
6. **Per-sentence artifacts, document-level aggregation in Stage 12** (ADR-013,
   ADR-016). Stage 12 assembles the snapshot from the per-sentence outputs of
   Stages 04–11 and re-derives none of them; no stage may reach forward, which
   `test_no_stage_imports_a_later_stage` enforces over the whole Figure 5 order.
7. **Evidence travels with every judgement.** `EntityEvidence` (09), `TermSource`
   (10) and `RoleEvidence` (11) reach the plugins intact through the snapshot, so
   a consumer can decide how far to trust an analysis without re-deriving it.
8. **Spans inside an analysis are sentence-relative.** Anything addressing the
   document must go through `SentenceAnalysis.document_span`; recomputing the
   offset arithmetic per plugin is how two consumers would silently disagree.
9. **The snapshot is the boundary.** The Plugin Runtime, the AI Runtime and the
   Suggestion Fusion Engine consume `DocumentSnapshot` and must not call the
   stages directly — that is what makes FR-4's incremental reuse observable to
   all of them at once.
10. **Debounce and transport are not the Language Server's.** FR-1 and FR-2 are
    the add-in's and the IPC boundary's; Stage 12 decides *what* needs
    re-analysis, never *when* to ask (ADR-016).
