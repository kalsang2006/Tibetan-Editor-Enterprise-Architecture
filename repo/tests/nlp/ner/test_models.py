"""Unit tests for the Stage 9 domain models (:mod:`teea.nlp.ner.models`).

An entity is a *run* of morphemes, not a token, because Tibetan names span
several syllables and may contain internal grammatical particles. The validators
enforce that the run, its span and its text agree; these tests construct entities
directly, including malformed ones, so the validators are what is under test.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.morphology import Morpheme, MorphemeKind
from teea.nlp.ner import EntityAnnotation, EntityEvidence, NamedEntity
from teea.nlp.postagging import TaggedMorpheme, coarse_category

TSHEG = "་"
#: "Dzambuling", written as three syllables joined by tsheg.
SOURCE = "འཛམ" + TSHEG + "བུ" + TSHEG + "གླིང" + TSHEG + "ཁྱིམ"


def morpheme(source: str, start: int, end: int, tag: str = "n.prop") -> TaggedMorpheme:
    offsets = utf8_byte_offsets(source)
    return TaggedMorpheme(
        morpheme=Morpheme(
            text=source[start:end],
            span=TextSpan(
                char_start=start,
                char_end=end,
                byte_start=offsets[start],
                byte_end=offsets[end],
            ),
            kind=MorphemeKind.ROOT,
        ),
        tag=tag,
        category=coarse_category(tag),
    )


def entity(
    source: str,
    start: int,
    end: int,
    morphemes: tuple[TaggedMorpheme, ...],
    *,
    evidence: EntityEvidence = EntityEvidence.GAZETTEER,
) -> NamedEntity:
    offsets = utf8_byte_offsets(source)
    return NamedEntity(
        text=source[morphemes[0].span.char_start : morphemes[-1].span.char_end],
        span=TextSpan(
            char_start=morphemes[0].span.char_start,
            char_end=morphemes[-1].span.char_end,
            byte_start=offsets[morphemes[0].span.char_start],
            byte_end=offsets[morphemes[-1].span.char_end],
        ),
        start_index=start,
        end_index=end,
        evidence=evidence,
        morphemes=morphemes,
    )


#: The three syllables of the name, with their exact offsets in SOURCE.
DZAM = morpheme(SOURCE, 0, 3)
BU = morpheme(SOURCE, 4, 6)
LING = morpheme(SOURCE, 7, 11)
KHYIM = morpheme(SOURCE, 12, 16, tag="n.count")


def name_entity() -> NamedEntity:
    return entity(SOURCE, 0, 3, (DZAM, BU, LING))


# -- Enumeration --------------------------------------------------------------
def test_evidence_values_are_unique() -> None:
    values = [member.value for member in EntityEvidence]
    assert len(values) == len(set(values))


# -- NamedEntity: validation --------------------------------------------------
def test_a_valid_multi_morpheme_entity_constructs() -> None:
    e = name_entity()
    assert e.num_morphemes == 3
    assert e.is_multi_morpheme
    assert e.syllables == ("འཛམ", "བུ", "གླིང")
    # The text is the source slice, so it keeps the tsheg between syllables.
    assert e.text == SOURCE[0:11]
    assert TSHEG in e.text


def test_a_single_morpheme_entity_constructs() -> None:
    e = entity(SOURCE, 3, 4, (KHYIM,))
    assert not e.is_multi_morpheme
    assert e.syllables == ("ཁྱིམ",)


def test_empty_text_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        NamedEntity(
            text="",
            span=TextSpan(char_start=0, char_end=0, byte_start=0, byte_end=0),
            start_index=0,
            end_index=1,
            evidence=EntityEvidence.TAGGER,
            morphemes=(DZAM,),
        )


def test_an_empty_index_range_is_rejected() -> None:
    with pytest.raises(ValidationError, match="greater than start_index"):
        NamedEntity(
            text="འཛམ",
            span=DZAM.span,
            start_index=2,
            end_index=2,
            evidence=EntityEvidence.TAGGER,
            morphemes=(DZAM,),
        )


def test_the_morpheme_count_must_match_the_index_range() -> None:
    with pytest.raises(ValidationError, match="expected 3 morphemes"):
        NamedEntity(
            text=SOURCE[0:11],
            span=TextSpan(char_start=0, char_end=11, byte_start=0, byte_end=31),
            start_index=0,
            end_index=3,
            evidence=EntityEvidence.GAZETTEER,
            morphemes=(DZAM,),
        )


def test_the_span_must_start_at_the_first_morpheme() -> None:
    offsets = utf8_byte_offsets(SOURCE)
    with pytest.raises(ValidationError, match="must start at the first morpheme"):
        NamedEntity(
            text=SOURCE[4:11],
            span=TextSpan(char_start=4, char_end=11, byte_start=offsets[4], byte_end=offsets[11]),
            start_index=0,
            end_index=3,
            evidence=EntityEvidence.GAZETTEER,
            morphemes=(DZAM, BU, LING),
        )


def test_the_span_must_end_at_the_last_morpheme() -> None:
    offsets = utf8_byte_offsets(SOURCE)
    with pytest.raises(ValidationError, match="must end at the last morpheme"):
        NamedEntity(
            text=SOURCE[0:6],
            span=TextSpan(char_start=0, char_end=6, byte_start=0, byte_end=offsets[6]),
            start_index=0,
            end_index=3,
            evidence=EntityEvidence.GAZETTEER,
            morphemes=(DZAM, BU, LING),
        )


def test_entity_is_frozen_and_forbids_unknown_fields() -> None:
    e = name_entity()
    with pytest.raises(ValidationError):
        e.text = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        NamedEntity(
            text="འཛམ",
            span=DZAM.span,
            start_index=0,
            end_index=1,
            evidence=EntityEvidence.TAGGER,
            morphemes=(DZAM,),
            unexpected="x",  # type: ignore[call-arg]
        )


def test_entities_compare_by_value_and_are_hashable() -> None:
    assert name_entity() == name_entity()
    assert len({name_entity(), name_entity()}) == 1


# -- EntityAnnotation ---------------------------------------------------------
def test_an_empty_annotation_is_valid() -> None:
    annotation = EntityAnnotation(source=SOURCE)
    assert annotation.is_empty
    assert annotation.num_entities == 0
    assert len(annotation) == 0
    assert annotation.texts == ()


def test_a_valid_annotation_exposes_its_entities() -> None:
    annotation = EntityAnnotation(source=SOURCE, entities=(name_entity(),))
    assert annotation.num_entities == 1
    assert annotation.texts == (SOURCE[0:11],)
    assert not annotation.is_empty


def test_overlapping_entities_are_rejected() -> None:
    first = name_entity()
    second = entity(SOURCE, 1, 4, (BU, LING, KHYIM))
    with pytest.raises(ValidationError, match="must not overlap"):
        EntityAnnotation(source=SOURCE, entities=(first, second))


def test_an_entity_span_beyond_the_source_is_rejected() -> None:
    with pytest.raises(ValidationError, match="exceeds the source text"):
        EntityAnnotation(source="འཛམ", entities=(name_entity(),))


def test_an_entity_whose_span_does_not_select_its_text_is_rejected() -> None:
    offsets = utf8_byte_offsets(SOURCE)
    lying = NamedEntity(
        text="ཁྱིམ",
        span=TextSpan(char_start=0, char_end=4, byte_start=0, byte_end=offsets[4]),
        start_index=0,
        end_index=1,
        evidence=EntityEvidence.TAGGER,
        morphemes=(morpheme(SOURCE, 0, 4),),
    )
    with pytest.raises(ValidationError, match="does not select its own text"):
        EntityAnnotation(source=SOURCE, entities=(lying,))


def test_adjacent_non_overlapping_entities_are_allowed() -> None:
    annotation = EntityAnnotation(
        source=SOURCE,
        entities=(name_entity(), entity(SOURCE, 3, 4, (KHYIM,))),
    )
    assert annotation.num_entities == 2


# -- Accessors ----------------------------------------------------------------
def test_of_evidence_filters() -> None:
    gazetteer_entity = name_entity()
    tagger_entity = entity(SOURCE, 3, 4, (KHYIM,), evidence=EntityEvidence.TAGGER)
    annotation = EntityAnnotation(source=SOURCE, entities=(gazetteer_entity, tagger_entity))
    assert annotation.of_evidence(EntityEvidence.GAZETTEER) == (gazetteer_entity,)
    assert annotation.of_evidence(EntityEvidence.TAGGER) == (tagger_entity,)
    assert annotation.of_evidence(EntityEvidence.BOTH) == ()


def test_entity_at_char_is_half_open() -> None:
    annotation = EntityAnnotation(source=SOURCE, entities=(name_entity(),))
    assert annotation.entity_at_char(0) is annotation.entities[0]
    assert annotation.entity_at_char(10) is annotation.entities[0]
    assert annotation.entity_at_char(11) is None
    assert annotation.entity_at_char(-1) is None
    assert annotation.entity_at_char(10_000) is None


def test_covers_morpheme_reports_membership() -> None:
    annotation = EntityAnnotation(source=SOURCE, entities=(name_entity(),))
    assert annotation.covers_morpheme(0)
    assert annotation.covers_morpheme(2)
    assert not annotation.covers_morpheme(3)


def test_annotation_is_frozen_and_compares_by_value() -> None:
    annotation = EntityAnnotation(source=SOURCE, entities=(name_entity(),))
    with pytest.raises(ValidationError):
        annotation.source = "x"  # type: ignore[misc]
    assert annotation == EntityAnnotation(source=SOURCE, entities=(name_entity(),))
