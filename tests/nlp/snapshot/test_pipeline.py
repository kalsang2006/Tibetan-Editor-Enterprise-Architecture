"""Integration tests for the complete language pipeline, Stages 2 -> 12.

Stage 12 closes Figure 5. This module runs the whole chain on real classical
Tibetan through the single entry point the daemon will use, and pins the
properties that only exist once the document is assembled: offsets that address
the document rather than a sentence, a snapshot that is genuinely read-only, and
an incremental path that re-parses only what an edit touched.

The tokenizer is not involved, so the module is hermetic -- no model download, no
network.
"""

from __future__ import annotations

import enum
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel

from teea.core.types import TextSpan
from teea.nlp.dependency import TibetanDependencyParser
from teea.nlp.morphology import MorphologicalAnalysis, TibetanMorphologicalAnalyzer
from teea.nlp.ner import TibetanEntityRecognizer
from teea.nlp.postagging import HmmPosTagger
from teea.nlp.segmentation import TibetanSentenceSegmenter
from teea.nlp.semantics import SentenceMood, TibetanSemanticAnalyzer
from teea.nlp.snapshot import (
    DocumentSnapshot,
    LanguageServerSnapshotBuilder,
    sentence_hash,
)
from teea.nlp.terminology import GlossaryTerminologyRecognizer
from teea.nlp.tokenization import TextNormalizer


class CountingMorphology:
    """Wraps Stage 06 and counts how many sentences reach it."""

    def __init__(self) -> None:
        self._inner = TibetanMorphologicalAnalyzer()
        self.calls = 0

    def analyze(self, text: str) -> MorphologicalAnalysis:
        self.calls += 1
        return self._inner.analyze(text)


def walk_immutable(value: Any, path: str, seen: set[int]) -> list[str]:
    """Return every mutable container reachable from ``value``.

    Figure 5 calls the snapshot "read-only centralized processing state" and has
    every plugin read it at once. That is only safe without a lock if there is no
    mutable state anywhere in the object graph, so this walks the whole graph
    rather than trusting the top-level model's ``frozen`` flag.
    """
    if id(value) in seen:
        return []
    seen.add(id(value))

    problems: list[str] = []
    if isinstance(value, BaseModel):
        if not value.model_config.get("frozen"):
            problems.append(f"{path}: {type(value).__name__} is not frozen")
        for name in type(value).model_fields:
            problems += walk_immutable(getattr(value, name), f"{path}.{name}", seen)
    elif isinstance(value, list | dict | set | bytearray):
        problems.append(f"{path}: mutable {type(value).__name__}")
    elif isinstance(value, tuple):
        for index, item in enumerate(value):
            problems += walk_immutable(item, f"{path}[{index}]", seen)
    elif isinstance(value, frozenset):
        for item in value:
            problems += walk_immutable(item, f"{path}{{}}", seen)
    elif not isinstance(value, str | int | float | bool | bytes | enum.Enum | type(None)):
        problems.append(f"{path}: unexpected {type(value).__name__}")
    return problems


# -- Whole-pipeline composition ------------------------------------------------
def test_a_document_flows_through_every_stage(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """Stage 2 -> 4 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12 on a real document."""
    normalized = TextNormalizer(form="NFC", collapse_whitespace=False).normalize(
        corpus_document
    )
    snapshot = snapshot_builder.analyze(normalized)

    assert snapshot.source == normalized
    assert snapshot.num_sentences > 10
    assert snapshot.num_morphemes > 500
    assert snapshot.num_semantic_nodes > 300
    assert all(a.num_morphemes > 0 for a in snapshot.analyses)


def test_the_snapshot_is_exactly_what_the_stages_produce(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """Stage 12 aggregates; it must add no analysis of its own.

    Composing the stages by hand and comparing artifact by artifact is what makes
    that claim checkable rather than merely stated.
    """
    segmenter = TibetanSentenceSegmenter()
    morphology = TibetanMorphologicalAnalyzer()
    tagger = HmmPosTagger()
    parser = TibetanDependencyParser()
    ner = TibetanEntityRecognizer()
    terminology = GlossaryTerminologyRecognizer()
    semantics = TibetanSemanticAnalyzer()

    snapshot = snapshot_builder.analyze(corpus_document)
    sentences = segmenter.segment(corpus_document).sentences
    assert snapshot.num_sentences == len(sentences)

    for analysis, sentence in zip(snapshot.analyses, sentences, strict=True):
        tree = parser.parse(tagger.tag(morphology.analyze(sentence.text)))
        entities = ner.recognize(tree)
        terms = terminology.recognize(tree)
        assert analysis.sentence == sentence
        assert analysis.tree == tree
        assert analysis.entities == entities
        assert analysis.terms == terms
        assert analysis.graph == semantics.analyze(
            tree, entities=entities, terms=terms
        )
        assert analysis.content_hash == sentence_hash(sentence.text)


def test_every_span_in_the_snapshot_addresses_the_document(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """The arithmetic the add-in performs to place a suggestion.

    A node's span is relative to its sentence; the sentence's span is relative to
    the document. ``document_span`` composes them, and the result must select the
    same characters -- and the same bytes -- in the document.
    """
    snapshot = snapshot_builder.analyze(corpus_document)
    encoded = corpus_document.encode("utf-8")
    checked = 0

    for analysis in snapshot.analyses:
        for node in analysis.graph.nodes:
            where = analysis.document_span(node.span)
            assert corpus_document[where.char_start : where.char_end] == node.text
            assert encoded[where.byte_start : where.byte_end] == node.text.encode(
                "utf-8"
            )
            checked += 1
        for entity in analysis.entities.entities:
            where = analysis.document_span(entity.span)
            assert corpus_document[where.char_start : where.char_end] == entity.text
        for term in analysis.terms.terms:
            where = analysis.document_span(term.span)
            assert corpus_document[where.char_start : where.char_end] == term.text

    assert checked > 300


def test_sentences_are_ordered_and_never_overlap(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """A plugin walking the document must not see a character twice."""
    snapshot = snapshot_builder.analyze(corpus_document)
    previous = 0
    for analysis in snapshot.analyses:
        assert analysis.span.char_start >= previous
        previous = analysis.span.char_end
    assert previous <= len(corpus_document)


def test_an_offset_anywhere_in_a_sentence_finds_that_sentence(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """FR-3's navigation primitive, over every sentence in a real document."""
    snapshot = snapshot_builder.analyze(corpus_document)
    for analysis in snapshot.analyses:
        for offset in (
            analysis.span.char_start,
            (analysis.span.char_start + analysis.span.char_end) // 2,
            analysis.span.char_end - 1,
        ):
            assert snapshot.analysis_at_char(offset) is analysis


# -- FR-4: incremental re-analysis on real text -------------------------------
def test_an_edit_reparses_only_the_sentence_it_touched(corpus_document: str) -> None:
    """SRS 3.1 and FR-4, measured on a real document by counting work."""
    morphology = CountingMorphology()
    builder = LanguageServerSnapshotBuilder(morphology=morphology)
    snapshot = builder.analyze(corpus_document)
    assert morphology.calls == snapshot.num_sentences

    target = snapshot.analyses[snapshot.num_sentences // 2]
    edited = (
        corpus_document[: target.span.char_start]
        + target.text[:2]
        + "ཀ"
        + target.text[2:]
        + corpus_document[target.span.char_end :]
    )

    morphology.calls = 0
    rebuilt = builder.reanalyze(snapshot, edited)
    assert morphology.calls == 1, morphology.calls
    assert rebuilt.num_sentences == snapshot.num_sentences


def test_incremental_analysis_equals_cold_analysis_on_real_text(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """Reuse is an optimisation, never a difference in result."""
    snapshot = snapshot_builder.analyze(corpus_document)
    target = snapshot.analyses[-1]
    edited = (
        corpus_document[: target.span.char_start]
        + target.text[:2]
        + "ཀ"
        + target.text[2:]
    )
    assert snapshot_builder.reanalyze(snapshot, edited) == snapshot_builder.analyze(
        edited
    )


def test_editing_near_the_end_leaves_earlier_analyses_untouched(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """The ordinary typing case: the cursor is at the end of what you wrote.

    Sentences before the edit have not moved, so their analyses are carried over
    as the same objects rather than rebuilt.
    """
    snapshot = snapshot_builder.analyze(corpus_document)
    target = snapshot.analyses[-1]
    edited = (
        corpus_document[: target.span.char_start]
        + target.text[:2]
        + "ཀ"
        + target.text[2:]
    )
    rebuilt = snapshot_builder.reanalyze(snapshot, edited)

    shared = sum(
        1
        for new, old in zip(rebuilt.analyses, snapshot.analyses, strict=False)
        if new is old
    )
    assert shared >= snapshot.num_sentences - 2, shared


# -- Read-only, and therefore concurrent ---------------------------------------
def test_the_whole_snapshot_is_deeply_immutable(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """Figure 5's "read-only centralized processing state", checked structurally.

    Every plugin reads this concurrently and no lock is taken, which is only
    sound if nothing anywhere in the object graph can be mutated. The walk covers
    every reachable field of every model, not just the outermost one.
    """
    snapshot = snapshot_builder.analyze(corpus_document)
    problems = walk_immutable(snapshot, "snapshot", set())
    assert not problems, problems[:10]


def test_concurrent_readers_agree(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """Many plugins reading one snapshot at once must see the same thing."""
    snapshot = snapshot_builder.analyze(corpus_document)
    span = TextSpan(
        char_start=0, char_end=len(corpus_document), byte_start=0, byte_end=0
    )

    def summarise(_: int) -> tuple[int, ...]:
        return (
            snapshot.num_sentences,
            snapshot.num_morphemes,
            snapshot.num_entities,
            snapshot.num_terms,
            snapshot.num_semantic_nodes,
            len(snapshot.analyses_overlapping(span.char_start, span.char_end)),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(summarise, range(64)))
    assert len(set(results)) == 1


def test_concurrent_analysis_matches_serial_analysis(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_sentences: list[str]
) -> None:
    """The daemon analyses many documents at once against one builder."""
    documents = ["".join(corpus_sentences[i : i + 5]) for i in range(0, 40, 5)]
    serial = [snapshot_builder.analyze(text) for text in documents]
    with ThreadPoolExecutor(max_workers=8) as pool:
        concurrent = list(pool.map(snapshot_builder.analyze, documents))
    assert concurrent == serial


def test_the_pipeline_is_deterministic(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    assert snapshot_builder.analyze(corpus_document) == snapshot_builder.analyze(
        corpus_document
    )


# -- Linguistic content survives the aggregation -------------------------------
def test_the_snapshot_carries_the_analysis_of_the_whole_document(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_document: str
) -> None:
    """A spot check that Stage 12 loses nothing on the way through."""
    snapshot = snapshot_builder.analyze(corpus_document)
    assert snapshot.num_entities > 5
    assert any(a.graph.predicates for a in snapshot.analyses)
    moods = {a.intent.mood for a in snapshot.analyses}
    assert SentenceMood.DECLARATIVE in moods
    assert len(moods) > 1


def test_a_snapshot_of_a_real_document_round_trips_through_json(
    snapshot_builder: LanguageServerSnapshotBuilder, corpus_sentences: list[str]
) -> None:
    """What crosses the IPC boundary must survive the crossing."""
    snapshot = snapshot_builder.analyze("".join(corpus_sentences[:10]))
    restored = DocumentSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored == snapshot
    assert restored.num_semantic_nodes == snapshot.num_semantic_nodes
