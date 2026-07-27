"""Invariants of the Stage 12 value objects, and the FR-4 content hash.

The snapshot is what the Feature Plugins Layer reads, so its guarantees are a
contract: sentences in document order, spans that really select their own text,
and a join that cannot be assembled from artifacts belonging to different
sentences. Each of those is asserted here rather than assumed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.errors import ErrorCode, InputValidationError
from teea.core.types import TextSpan
from teea.nlp.dependency import DependencyTree
from teea.nlp.ner import EntityAnnotation
from teea.nlp.segmentation import Sentence, TibetanSentenceSegmenter
from teea.nlp.semantics import SentenceMood, TibetanSemanticAnalyzer
from teea.nlp.snapshot import (
    DIGEST_SIZE,
    DocumentSnapshot,
    LanguageServerSnapshotBuilder,
    SentenceAnalysis,
    sentence_hash,
)
from teea.nlp.terminology import TerminologyAnnotation

SHAD = "།"
FIRST = "ཞིང་ཀློག" + SHAD
SECOND = "ཡུལ་འགྲོ" + SHAD
DOCUMENT = FIRST + SECOND


@pytest.fixture(scope="module")
def snapshot() -> DocumentSnapshot:
    """A real two-sentence snapshot, built by the real builder."""
    return LanguageServerSnapshotBuilder().analyze(DOCUMENT)


# -- The content hash (SRS 3.1, FR-4) -----------------------------------------
def test_the_hash_is_stable_for_the_same_text() -> None:
    """It is a cache key for a daemon that restarts, so it must not be salted."""
    assert sentence_hash(FIRST) == sentence_hash(FIRST)


def test_different_text_hashes_differently() -> None:
    assert sentence_hash(FIRST) != sentence_hash(SECOND)


def test_the_hash_is_a_fixed_width_hex_digest() -> None:
    digest = sentence_hash(FIRST)
    assert len(digest) == DIGEST_SIZE * 2
    assert int(digest, 16) >= 0


@pytest.mark.parametrize("text", ["", " ", SHAD, "abc", FIRST, "🙂"])
def test_the_hash_accepts_any_text(text: str) -> None:
    assert len(sentence_hash(text)) == DIGEST_SIZE * 2


def test_the_hash_distinguishes_texts_that_differ_only_in_a_combining_mark() -> None:
    """Tibetan vowel signs are combining marks; conflating them would be fatal."""
    assert sentence_hash("བཀ") != sentence_hash("བཀྲ")


# -- SentenceAnalysis ----------------------------------------------------------
def test_an_analysis_exposes_its_sentence(snapshot: DocumentSnapshot) -> None:
    analysis = snapshot.analyses[0]
    assert analysis.index == 0
    assert analysis.text == FIRST
    assert analysis.span == analysis.sentence.span
    assert analysis.content_hash == sentence_hash(FIRST)
    assert analysis.intent.mood is SentenceMood.DECLARATIVE


def test_an_analysis_summarises_every_stage(snapshot: DocumentSnapshot) -> None:
    analysis = snapshot.analyses[0]
    assert analysis.num_morphemes == analysis.tree.num_nodes
    assert analysis.num_entities == analysis.entities.num_entities
    assert analysis.num_terms == analysis.terms.num_terms
    assert analysis.num_semantic_nodes == analysis.graph.num_nodes
    assert analysis.num_morphemes > 0


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("tree", "dependency tree"),
        ("entities", "entity annotation"),
        ("terms", "terminology annotation"),
        ("graph", "semantic graph"),
    ],
)
def test_artifacts_from_another_sentence_are_rejected(
    snapshot: DocumentSnapshot, field: str, message: str
) -> None:
    """FR-3's "state integrity", enforced rather than assumed.

    A join across two sentences would produce spans addressing the wrong part of
    the document, which the add-in would then paint suggestions onto.
    """
    first, second = snapshot.analyses
    parts = {
        "sentence": first.sentence,
        "tree": first.tree,
        "entities": first.entities,
        "terms": first.terms,
        "graph": first.graph,
        "content_hash": first.content_hash,
    }
    parts[field] = getattr(second, field)
    with pytest.raises(ValidationError, match=message):
        SentenceAnalysis(**parts)


def test_a_stale_content_hash_is_rejected(snapshot: DocumentSnapshot) -> None:
    """A wrong hash would make an edited sentence look unchanged."""
    first = snapshot.analyses[0]
    with pytest.raises(ValidationError, match="content_hash does not match"):
        SentenceAnalysis(
            sentence=first.sentence,
            tree=first.tree,
            entities=first.entities,
            terms=first.terms,
            graph=first.graph,
            content_hash=sentence_hash("something else"),
        )


def test_an_analysis_is_immutable(snapshot: DocumentSnapshot) -> None:
    with pytest.raises(ValidationError):
        snapshot.analyses[0].content_hash = "x"  # type: ignore[misc]


# -- Document coordinates ------------------------------------------------------
def test_a_sentence_relative_span_translates_to_document_coordinates(
    snapshot: DocumentSnapshot,
) -> None:
    """The arithmetic the add-in performs, done once by the snapshot."""
    second = snapshot.analyses[1]
    for node in second.graph.nodes:
        where = second.document_span(node.span)
        assert DOCUMENT[where.char_start : where.char_end] == node.text
        assert where.byte_length == len(node.text.encode("utf-8"))


def test_translation_shifts_bytes_independently_of_characters(
    snapshot: DocumentSnapshot,
) -> None:
    """Tibetan code points are three UTF-8 bytes, so the two offsets diverge."""
    second = snapshot.analyses[1]
    where = second.document_span(second.graph.nodes[0].span)
    assert where.char_start != where.byte_start
    assert where.byte_start == DOCUMENT.encode("utf-8").index(
        second.graph.nodes[0].text.encode("utf-8")
    )


def test_translating_the_whole_sentence_span_is_allowed(
    snapshot: DocumentSnapshot,
) -> None:
    first = snapshot.analyses[0]
    own = TextSpan(
        char_start=0,
        char_end=first.span.char_length,
        byte_start=0,
        byte_end=first.span.byte_length,
    )
    assert first.document_span(own) == first.span


@pytest.mark.parametrize("field", ["char_end", "byte_end"])
def test_a_span_from_another_sentence_is_rejected(snapshot: DocumentSnapshot, field: str) -> None:
    """A span that overruns the sentence did not come from its analysis."""
    first = snapshot.analyses[0]
    kwargs = {"char_start": 0, "char_end": 1, "byte_start": 0, "byte_end": 1}
    kwargs[field] = 10_000
    with pytest.raises(InputValidationError, match="does not lie within") as error:
        first.document_span(TextSpan(**kwargs))
    assert error.value.code is ErrorCode.INPUT_INVALID


# -- DocumentSnapshot ----------------------------------------------------------
def test_an_empty_snapshot_is_valid() -> None:
    empty = DocumentSnapshot(source="")
    assert empty.is_empty is True
    assert len(empty) == empty.num_sentences == 0
    assert empty.sentences == () == empty.content_hashes
    assert empty.num_morphemes == empty.num_entities == 0
    assert empty.num_terms == empty.num_semantic_nodes == 0
    assert empty.analysis_at_char(0) is None
    assert empty.analyses_overlapping(0, 5) == ()


def test_a_snapshot_exposes_the_document(snapshot: DocumentSnapshot) -> None:
    assert snapshot.source == DOCUMENT
    assert len(snapshot) == snapshot.num_sentences == 2
    assert snapshot.is_empty is False
    assert [s.text for s in snapshot.sentences] == [FIRST, SECOND]
    assert snapshot.content_hashes == (sentence_hash(FIRST), sentence_hash(SECOND))


def test_a_snapshot_summarises_the_whole_document(snapshot: DocumentSnapshot) -> None:
    """Figure 5's "centralized processing state", as a set of totals."""
    assert snapshot.num_morphemes == sum(a.num_morphemes for a in snapshot.analyses)
    assert snapshot.num_semantic_nodes == sum(a.num_semantic_nodes for a in snapshot.analyses)
    assert snapshot.num_entities == sum(a.num_entities for a in snapshot.analyses)
    assert snapshot.num_terms == sum(a.num_terms for a in snapshot.analyses)
    assert snapshot.num_morphemes > 0


def test_an_offset_maps_back_to_the_sentence_that_covers_it(
    snapshot: DocumentSnapshot,
) -> None:
    """FR-3: given where the user is typing, which analysis describes it."""
    found = snapshot.analysis_at_char(0)
    assert found is not None and found.index == 0
    later = snapshot.analysis_at_char(len(FIRST))
    assert later is not None and later.index == 1
    assert snapshot.analysis_at_char(len(DOCUMENT)) is None
    assert snapshot.analysis_at_char(10_000) is None


def test_an_edit_reports_the_sentences_it_invalidates(
    snapshot: DocumentSnapshot,
) -> None:
    """FR-4's incremental primitive."""
    assert [a.index for a in snapshot.analyses_overlapping(0, 1)] == [0]
    assert [a.index for a in snapshot.analyses_overlapping(0, len(DOCUMENT))] == [0, 1]
    assert [a.index for a in snapshot.analyses_overlapping(len(FIRST) - 1, len(FIRST) + 1)] == [
        0,
        1,
    ]
    assert snapshot.analyses_overlapping(len(DOCUMENT), len(DOCUMENT)) == ()


def test_an_insertion_point_invalidates_the_sentence_it_falls_in(
    snapshot: DocumentSnapshot,
) -> None:
    """An empty range is an insertion, and it still modifies its sentence."""
    assert [a.index for a in snapshot.analyses_overlapping(2, 2)] == [0]


def test_a_backwards_range_is_rejected(snapshot: DocumentSnapshot) -> None:
    with pytest.raises(ValueError, match="end must be >= start"):
        snapshot.analyses_overlapping(5, 1)


def test_an_analysis_carrying_the_wrong_index_is_rejected(
    snapshot: DocumentSnapshot,
) -> None:
    with pytest.raises(ValidationError, match="carries index"):
        DocumentSnapshot(source=DOCUMENT, analyses=snapshot.analyses[::-1])


def test_a_span_beyond_the_document_is_rejected(snapshot: DocumentSnapshot) -> None:
    with pytest.raises(ValidationError, match="exceeds the document"):
        DocumentSnapshot(source=FIRST, analyses=snapshot.analyses)


def test_a_span_that_selects_different_text_is_rejected(
    snapshot: DocumentSnapshot,
) -> None:
    """The invariant every stage in this pipeline maintains."""
    with pytest.raises(ValidationError, match="does not select its own text"):
        DocumentSnapshot(source="x" * len(DOCUMENT), analyses=snapshot.analyses)


def test_overlapping_sentences_are_rejected() -> None:
    """Two analyses claiming the same characters would double-count an edit."""
    text = FIRST + FIRST
    builder = LanguageServerSnapshotBuilder()
    one = builder.analyze(text).analyses[0]
    shifted = TibetanSentenceSegmenter().segment(text).sentences[1]
    overlapping = SentenceAnalysis(
        sentence=Sentence(
            text=shifted.text,
            span=TextSpan(
                char_start=one.span.char_start + 1,
                char_end=one.span.char_end + 1,
                byte_start=one.span.byte_start + 3,
                byte_end=one.span.byte_end + 3,
            ),
            index=1,
            terminator=shifted.terminator,
        ),
        tree=one.tree,
        entities=one.entities,
        terms=one.terms,
        graph=one.graph,
        content_hash=one.content_hash,
    )
    with pytest.raises(ValidationError, match="must not overlap"):
        DocumentSnapshot(source=text, analyses=(one, overlapping))


def test_a_snapshot_is_immutable(snapshot: DocumentSnapshot) -> None:
    with pytest.raises(ValidationError):
        snapshot.source = "x"  # type: ignore[misc]


# -- Serialization -------------------------------------------------------------
def test_a_snapshot_round_trips_through_json(snapshot: DocumentSnapshot) -> None:
    """The IPC boundary serialises this, so the round trip is a contract."""
    restored = DocumentSnapshot.model_validate_json(snapshot.model_dump_json())
    assert restored == snapshot
    assert restored.content_hashes == snapshot.content_hashes
    assert restored.analyses[0].graph == snapshot.analyses[0].graph


def test_a_snapshot_dumps_to_plain_data(snapshot: DocumentSnapshot) -> None:
    """The Plugin Runtime receives data, not Python objects."""
    dumped = snapshot.model_dump(mode="json")
    assert dumped["source"] == DOCUMENT
    assert len(dumped["analyses"]) == 2
    assert dumped["analyses"][0]["content_hash"] == sentence_hash(FIRST)
    assert dumped["analyses"][0]["graph"]["intent"]["mood"] == "declarative"


def test_an_empty_analysis_set_still_validates() -> None:
    """A document with no sentences is a valid document."""
    analyzer = TibetanSemanticAnalyzer()
    tree = DependencyTree(source="")
    analysis = SentenceAnalysis(
        sentence=Sentence(
            text=" ",
            span=TextSpan(char_start=0, char_end=1, byte_start=0, byte_end=1),
            index=0,
        ),
        tree=DependencyTree(source=" "),
        entities=EntityAnnotation(source=" "),
        terms=TerminologyAnnotation(source=" "),
        graph=analyzer.analyze(DependencyTree(source=" ")),
        content_hash=sentence_hash(" "),
    )
    assert DocumentSnapshot(source=" ", analyses=(analysis,)).num_morphemes == 0
    assert tree.is_empty
