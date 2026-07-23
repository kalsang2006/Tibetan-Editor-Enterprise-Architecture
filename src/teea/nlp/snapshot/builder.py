"""Document snapshot assembly (Language pipeline Stage 12).

Figure 5 assigns Stage 12 the storage of the parsed representation for the
Feature Plugins Layer. This module is the composition root of the Language
Server: it holds one instance of each analysis stage and runs a document through
them, sentence by sentence, into a single immutable
:class:`~teea.nlp.snapshot.models.DocumentSnapshot`.

Why an unchanged sentence needs no re-analysis at all
----------------------------------------------------
FR-4 requires that only modified sentences re-parse. That is cheap to satisfy
here because of a property the earlier stages already have: **every stage from 06
onward consumes only the sentence's own text**, and every span it emits is
relative to that sentence. So an analysis is a pure function of the sentence
string, and stays valid when the surrounding document changes -- even when the
sentence moves, because nothing in the analysis records where it was.

:meth:`LanguageServerSnapshotBuilder.reanalyze` therefore keys the previous
snapshot by content hash and, on a hit, reuses the dependency tree, the entity
and terminology annotations and the semantic graph **by reference**, rebuilding
only the Stage 04 sentence that carries the new position. The result is required
to be identical to a cold analysis of the same text; reuse is an optimisation,
never a difference in outcome, and a test pins the equality rather than trusting
it.

Scope
-----
This stage decides *what* needs re-analysis. It does not decide *when* to ask:
FR-1's debounced typing interval and FR-2's minimal patch layer belong to the
add-in and the IPC boundary, neither of which exists yet. See ADR-016.

Normalization is likewise not performed here. Stage 02 can change the length of
the text, so normalizing inside this builder would produce offsets addressing a
string the caller never saw. The caller applies Stage 02 first, exactly as Stage
04 requires of its own input.
"""

from __future__ import annotations

from teea.nlp.dependency import DependencyParser, TibetanDependencyParser
from teea.nlp.morphology import MorphologicalAnalyzer, TibetanMorphologicalAnalyzer
from teea.nlp.ner import EntityRecognizer, TibetanEntityRecognizer
from teea.nlp.postagging import HmmPosTagger, PosTagger
from teea.nlp.segmentation import Sentence, SentenceSegmenter, TibetanSentenceSegmenter
from teea.nlp.semantics import SemanticAnalyzer, TibetanSemanticAnalyzer
from teea.nlp.snapshot.hashing import sentence_hash
from teea.nlp.snapshot.models import DocumentSnapshot, SentenceAnalysis
from teea.nlp.terminology import GlossaryTerminologyRecognizer, TerminologyRecognizer


class LanguageServerSnapshotBuilder:
    """Runs a document through Stages 04-11 and assembles the snapshot.

    Satisfies the :class:`~teea.nlp.snapshot.interfaces.DocumentAnalyzer`
    protocol. Holds no mutable state: every collaborator is itself stateless and
    documented as safe to share, so one builder serves many concurrent documents.

    Every stage is injectable, following the convention the whole pipeline uses.
    That is what makes this class testable without the real resources, and it is
    what SRS 3.3's hot-swapping requirement asks for at the document level.

    Args:
        segmenter: Stage 04. Defaults to the Tibetan sentence segmenter.
        morphology: Stage 06. Defaults to the rule-based analyzer.
        tagger: Stage 07. Defaults to the corpus-derived HMM tagger.
        parser: Stage 08. Defaults to the constraint-grammar-derived parser.
        recognizer: Stage 09. Defaults to the gazetteer-driven recogniser.
        terminology: Stage 10. Defaults to the shipped glossary recogniser.
        semantics: Stage 11. Defaults to the verb-lexicon-driven analyser.

    Raises:
        ConfigurationError: If a defaulted stage cannot load its data payload.
    """

    def __init__(
        self,
        *,
        segmenter: SentenceSegmenter | None = None,
        morphology: MorphologicalAnalyzer | None = None,
        tagger: PosTagger | None = None,
        parser: DependencyParser | None = None,
        recognizer: EntityRecognizer | None = None,
        terminology: TerminologyRecognizer | None = None,
        semantics: SemanticAnalyzer | None = None,
    ) -> None:
        # `is None`, not `or`: several of these stages are backed by repositories
        # that define __len__, so an empty-but-deliberate instance is falsy and
        # `or` would silently substitute the shipped one. That was a real defect
        # in Stages 07, 09 and 10.
        self._segmenter = TibetanSentenceSegmenter() if segmenter is None else segmenter
        self._morphology = (
            TibetanMorphologicalAnalyzer() if morphology is None else morphology
        )
        self._tagger = HmmPosTagger() if tagger is None else tagger
        self._parser = TibetanDependencyParser() if parser is None else parser
        self._recognizer = (
            TibetanEntityRecognizer() if recognizer is None else recognizer
        )
        self._terminology = (
            GlossaryTerminologyRecognizer() if terminology is None else terminology
        )
        self._semantics = (
            TibetanSemanticAnalyzer() if semantics is None else semantics
        )

    def analyze(self, text: str) -> DocumentSnapshot:
        """Analyse ``text`` from scratch.

        Total: empty or unsegmentable input yields an empty snapshot.

        Args:
            text: The document, already normalized by Stage 02.

        Returns:
            The immutable snapshot.
        """
        sentences = self._segmenter.segment(text).sentences
        return DocumentSnapshot(
            source=text,
            analyses=tuple(self._analyze(sentence) for sentence in sentences),
        )

    def reanalyze(self, previous: DocumentSnapshot, text: str) -> DocumentSnapshot:
        """Analyse ``text``, reusing every sentence ``previous`` still describes.

        The FR-4 path. Sentences whose content hash is unchanged keep their
        existing analysis; only the rest go through Stages 06-11.

        Args:
            previous: The snapshot taken before the edit.
            text: The document after the edit, already normalized by Stage 02.

        Returns:
            The immutable snapshot of ``text``, equal to what :meth:`analyze`
            would return for it.
        """
        reusable = {
            analysis.content_hash: analysis for analysis in previous.analyses
        }
        sentences = self._segmenter.segment(text).sentences
        return DocumentSnapshot(
            source=text,
            analyses=tuple(
                self._reuse(reusable.get(digest), sentence, digest)
                for sentence in sentences
                for digest in (sentence_hash(sentence.text),)
            ),
        )

    # -- Internals -----------------------------------------------------------
    def _analyze(self, sentence: Sentence) -> SentenceAnalysis:
        """Run Stages 06 -> 11 over one sentence."""
        tree = self._parser.parse(
            self._tagger.tag(self._morphology.analyze(sentence.text))
        )
        entities = self._recognizer.recognize(tree)
        terms = self._terminology.recognize(tree)
        return SentenceAnalysis(
            sentence=sentence,
            tree=tree,
            entities=entities,
            terms=terms,
            graph=self._semantics.analyze(tree, entities=entities, terms=terms),
            content_hash=sentence_hash(sentence.text),
        )

    def _reuse(
        self, cached: SentenceAnalysis | None, sentence: Sentence, digest: str
    ) -> SentenceAnalysis:
        """Reuse a cached analysis, rebind it to a new position, or analyse afresh.

        Three cases, in increasing cost:

        1. **The sentence has not moved.** Its text, span, index and terminator
           are all unchanged, so the whole analysis is still exactly right and the
           existing object is returned as-is. The new snapshot then shares
           structure with the old one, which is what an immutable design should
           do. An edit is usually made at the cursor, so in ordinary typing this
           is nearly every sentence in the document.
        2. **The sentence moved but its text did not.** Everything except the
           Stage 04 sentence is carried over by reference; only that one value
           object records where in the document the sentence sits. A fresh
           :class:`SentenceAnalysis` is constructed rather than a copy patched, so
           the validator runs and the join is re-checked -- that rules out a whole
           class of stale-cache defect.
        3. **The text changed.** Stages 06-11 run.

        Case 1 is worth separating: measured over the 5,885-sentence reference
        document, the equality check costs 1.15 microseconds against 35.3 to
        reconstruct, so it pays for itself thirty times over on a hit and is
        negligible on a miss.
        """
        if cached is None:
            return self._analyze(sentence)
        if cached.sentence == sentence:
            return cached
        return SentenceAnalysis(
            sentence=sentence,
            tree=cached.tree,
            entities=cached.entities,
            terms=cached.terms,
            graph=cached.graph,
            content_hash=digest,
        )


__all__ = ["LanguageServerSnapshotBuilder"]
