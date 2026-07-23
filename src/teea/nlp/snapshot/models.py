"""Immutable domain models produced by the document snapshot stage.

These are the value objects that cross the boundary out of Stage 12, the last
stage of the language processing pipeline. Figure 5 states it directly:
*"Immutable Document Snapshot · Store parsed representation · Shared by plugins ·
Read-only centralized processing state"*, and the band immediately below it reads
*"All plugins consume the centralized immutable snapshot concurrently"*.

This is aggregation, not analysis
---------------------------------
Every artifact stored here was produced by an earlier stage. Stage 12 adds no
linguistic judgement whatsoever; what it adds is four things the per-sentence
artifacts cannot provide on their own:

1. **One object per document.** FR-3 requires the daemon to "track state
   integrity through an independent, shared document context tree". Stages 04-11
   each produce one artifact per *sentence*; nothing above them can address the
   document without an assembly like this one.
2. **Document coordinates.** Every span from Stage 06 onward is relative to its
   sentence, because that is the unit each stage analyses. The add-in paints
   suggestions onto Word ranges, which are document offsets.
   :meth:`SentenceAnalysis.document_span` is that translation, performed once
   here rather than re-derived by every plugin.
3. **A cache key per sentence.** SRS 3.1 and FR-4 require that only modified
   sentences re-parse. :attr:`SentenceAnalysis.content_hash` is what makes an
   unchanged sentence recognisable as unchanged.
4. **A checked join.** A snapshot cannot be built from artifacts that describe
   different sentences; the validator rejects it. That is the "state integrity"
   of FR-3 expressed as an invariant rather than a convention.

Read-only, and therefore concurrent
-----------------------------------
Figure 5 calls the snapshot "read-only centralized processing state" and has
every plugin read it at once. That is a concurrency claim, and it holds here for
a structural reason rather than by discipline: every model in this pipeline is a
frozen pydantic model containing only frozen models, tuples and primitives, so
there is no mutable state for concurrent readers to race over and no lock is
required. A test walks the whole object graph and asserts it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from teea.core.errors import InputValidationError
from teea.core.types import TextSpan
from teea.nlp.dependency import DependencyTree
from teea.nlp.ner import EntityAnnotation
from teea.nlp.segmentation import Sentence
from teea.nlp.semantics import SemanticGraph, SentenceIntent
from teea.nlp.snapshot.hashing import sentence_hash
from teea.nlp.terminology import TerminologyAnnotation


class SentenceAnalysis(BaseModel):
    """Everything the Language Server derived from one sentence.

    The five artifacts are held by reference, not copied, so assembling a
    snapshot costs almost nothing beyond the analyses themselves.

    Stage 05's subword encoding is deliberately absent. Figure 5 places
    tokenization in the chain, but the implemented chain reaches Stage 06 through
    *syllable* segmentation, and the TiBERT encoding is a parallel product
    consumed by the AI Runtime rather than by this one. Storing it here would
    make the snapshot -- and every test that builds one -- depend on the model.

    Attributes:
        sentence: The Stage 04 sentence, carrying its span within the document.
        tree: The Stage 08 dependency tree. It also carries Stage 06's morphemes
            and Stage 07's tags on every node, so those stages need no separate
            slot.
        entities: The Stage 09 names.
        terms: The Stage 10 technical terminology.
        graph: The Stage 11 semantic graph.
        content_hash: The sentence's content hash, the FR-4 cache key.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sentence: Sentence
    tree: DependencyTree
    entities: EntityAnnotation
    terms: TerminologyAnnotation
    graph: SemanticGraph
    content_hash: str

    @model_validator(mode="after")
    def _validate_consistency(self) -> SentenceAnalysis:
        """Enforce that all five artifacts describe the same sentence.

        This is the "state integrity" FR-3 asks for. Assembling a snapshot from
        artifacts belonging to different sentences would produce spans that
        address the wrong part of the document, which the add-in would then paint
        suggestions onto -- the same failure Stage 11 guards its own inputs
        against.
        """
        text = self.sentence.text
        for label, produced in (
            ("dependency tree", self.tree.source),
            ("entity annotation", self.entities.source),
            ("terminology annotation", self.terms.source),
            ("semantic graph", self.graph.source),
        ):
            if produced != text:
                raise ValueError(f"the {label} describes a different sentence")
        if self.content_hash != sentence_hash(text):
            raise ValueError("content_hash does not match the sentence text")
        return self

    @property
    def index(self) -> int:
        """Zero-based position of this sentence in the document."""
        return self.sentence.index

    @property
    def text(self) -> str:
        """The sentence exactly as it appears in the document."""
        return self.sentence.text

    @property
    def span(self) -> TextSpan:
        """Extent of the sentence *within the document*."""
        return self.sentence.span

    @property
    def intent(self) -> SentenceIntent:
        """The Stage 11 intent analysis for this sentence."""
        return self.graph.intent

    @property
    def num_morphemes(self) -> int:
        """How many morphemes Stage 06 found."""
        return self.tree.num_nodes

    @property
    def num_entities(self) -> int:
        """How many names Stage 09 recognised."""
        return self.entities.num_entities

    @property
    def num_terms(self) -> int:
        """How many technical terms Stage 10 recognised."""
        return self.terms.num_terms

    @property
    def num_semantic_nodes(self) -> int:
        """How many concepts and predicates Stage 11 built."""
        return self.graph.num_nodes

    def document_span(self, span: TextSpan) -> TextSpan:
        """Translate a sentence-relative span into document coordinates.

        The arithmetic every consumer of this pipeline has to perform, done once
        here. Character and byte offsets are shifted independently, because
        Tibetan code points occupy three UTF-8 bytes each and the two offsets
        diverge from the first character.

        Args:
            span: A span produced by any stage from 06 onward, whose offsets are
                relative to this sentence.

        Returns:
            The same extent, addressed in the document.

        Raises:
            InputValidationError: If ``span`` reaches beyond this sentence, which
                means it did not come from this sentence's analysis.
        """
        own = self.sentence.span
        if span.char_end > own.char_length or span.byte_end > own.byte_length:
            raise InputValidationError(
                "Span does not lie within this sentence.",
                context={
                    "span_char_end": span.char_end,
                    "sentence_char_length": own.char_length,
                },
            )
        return TextSpan(
            char_start=own.char_start + span.char_start,
            char_end=own.char_start + span.char_end,
            byte_start=own.byte_start + span.byte_start,
            byte_end=own.byte_start + span.byte_end,
        )


class DocumentSnapshot(BaseModel):
    """The immutable parsed representation of one document.

    Figure 5's final stage, and the object the Feature Plugins Layer reads. It is
    what the Level-1 Data Flow Diagram labels "Parsed Tokens / Graph" on the edge
    from the Language Server to the Plugin Runtime.

    Attributes:
        source: The document that was analysed, exactly as supplied. Callers pass
            Stage 02 output; see
            :class:`~teea.nlp.snapshot.builder.LanguageServerSnapshotBuilder`.
        analyses: One entry per sentence, in document order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    analyses: tuple[SentenceAnalysis, ...] = ()

    @model_validator(mode="after")
    def _validate_consistency(self) -> DocumentSnapshot:
        """Enforce ordering, indexing and span accuracy against the document."""
        previous_end = -1
        for position, analysis in enumerate(self.analyses):
            if analysis.index != position:
                raise ValueError(
                    f"analysis at position {position} carries index {analysis.index}"
                )
            span = analysis.span
            if span.char_start < previous_end:
                raise ValueError("sentence spans must not overlap")
            if span.char_end > len(self.source):
                raise ValueError(f"analysis {position} span exceeds the document")
            if self.source[span.char_start : span.char_end] != analysis.text:
                raise ValueError(
                    f"analysis {position} span does not select its own text"
                )
            previous_end = span.char_end
        return self

    def __len__(self) -> int:
        """Number of analysed sentences."""
        return len(self.analyses)

    @property
    def num_sentences(self) -> int:
        """Number of analysed sentences."""
        return len(self.analyses)

    @property
    def is_empty(self) -> bool:
        """Whether the document produced no sentences at all."""
        return not self.analyses

    @property
    def sentences(self) -> tuple[Sentence, ...]:
        """The Stage 04 sentences, in document order."""
        return tuple(analysis.sentence for analysis in self.analyses)

    @property
    def content_hashes(self) -> tuple[str, ...]:
        """The per-sentence cache keys, in document order (FR-4)."""
        return tuple(analysis.content_hash for analysis in self.analyses)

    # -- Processing-state summary ---------------------------------------------
    @property
    def num_morphemes(self) -> int:
        """Total morphemes across the document."""
        return sum(analysis.num_morphemes for analysis in self.analyses)

    @property
    def num_entities(self) -> int:
        """Total names recognised across the document."""
        return sum(analysis.num_entities for analysis in self.analyses)

    @property
    def num_terms(self) -> int:
        """Total technical terms recognised across the document."""
        return sum(analysis.num_terms for analysis in self.analyses)

    @property
    def num_semantic_nodes(self) -> int:
        """Total semantic nodes across the document."""
        return sum(analysis.num_semantic_nodes for analysis in self.analyses)

    # -- Navigation ------------------------------------------------------------
    def analysis_at_char(self, char_index: int) -> SentenceAnalysis | None:
        """Return the analysis whose sentence covers a document offset.

        The primitive behind FR-3's shared document context tree: given where the
        user is typing, this is the analysis that describes it.

        Args:
            char_index: Character offset into :attr:`source`.

        Returns:
            The covering analysis, or ``None`` when the offset falls in a gap
            between sentences or outside the document.
        """
        for analysis in self.analyses:
            span = analysis.span
            if span.char_start <= char_index < span.char_end:
                return analysis
        return None

    def analyses_overlapping(self, start: int, end: int) -> tuple[SentenceAnalysis, ...]:
        """Return every analysis intersecting the half-open range ``[start, end)``.

        The incremental primitive of FR-4: an edit invalidates exactly the
        sentences it touches. An empty range inside a sentence still returns that
        sentence, because an insertion there modifies it.

        Args:
            start: Inclusive character offset of the changed region.
            end: Exclusive character offset of the changed region.

        Returns:
            The overlapping analyses, in document order.

        Raises:
            ValueError: If ``end`` precedes ``start``.
        """
        if end < start:
            raise ValueError("end must be >= start")
        matches: list[SentenceAnalysis] = []
        for analysis in self.analyses:
            span = analysis.span
            if start == end:
                if span.char_start <= start < span.char_end:
                    matches.append(analysis)
                continue
            if span.char_start < end and start < span.char_end:
                matches.append(analysis)
        return tuple(matches)


__all__ = ["DocumentSnapshot", "SentenceAnalysis"]
