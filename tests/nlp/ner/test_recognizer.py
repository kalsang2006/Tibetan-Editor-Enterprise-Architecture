"""Unit and evaluation tests for :mod:`teea.nlp.ner.recognizer`.

Three concerns.

**Guarantees.** Entities are returned in surface order, never overlap, and carry
exact spans, for any input. Asserted over the whole reference corpus.

**Behaviour.** Longest-match over the gazetteer, the two-tier evidence rule, and
the fact that a name may span several morphemes including an internal particle.

**Evaluation against gold.** Unlike Stage 8, real gold data exists: the corpora
carry an entity layer (``POS~n.prop.B/M/E/S``) independent of the syntactic one.
Marpa is held out -- the gazetteer was built from the lexicon and Milarepa only
-- so its figures measure generalisation. Every threshold below was measured
first and set with margin.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.dependency import DependencyTree, TibetanDependencyParser
from teea.nlp.morphology import Morpheme, MorphemeKind, TibetanMorphologicalAnalyzer
from teea.nlp.ner import (
    EntityAnnotation,
    EntityEvidence,
    EntityRecognizer,
    TibetanEntityRecognizer,
)
from teea.nlp.postagging import HmmPosTagger, TaggedMorpheme, TaggedText, coarse_category
from teea.persistence import default_gazetteer

TSHEG = "་"


# -- Helpers ------------------------------------------------------------------
def build_tree(*pairs: tuple[str, str]) -> DependencyTree:
    """Build a Stage 8 tree directly from ``(surface, tag)`` pairs.

    Constructing the input by hand isolates the recogniser from the tagger and
    parser, so an entity expectation cannot fail because an earlier stage made a
    different choice.
    """
    source = TSHEG.join(surface for surface, _ in pairs) + TSHEG
    offsets = utf8_byte_offsets(source)
    morphemes: list[TaggedMorpheme] = []
    cursor = 0
    for surface, tag in pairs:
        start, end = cursor, cursor + len(surface)
        morphemes.append(
            TaggedMorpheme(
                morpheme=Morpheme(
                    text=surface,
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
        )
        cursor = end + len(TSHEG)
    return TibetanDependencyParser().parse(
        TaggedText(source=source, morphemes=tuple(morphemes))
    )


class StubGazetteer:
    """A tiny gazetteer, to prove the injected one is really used."""

    def __init__(
        self,
        confident: set[tuple[str, ...]] | None = None,
        ambiguous: set[tuple[str, ...]] | None = None,
    ) -> None:
        self._confident = confident or set()
        self._ambiguous = ambiguous or set()

    @property
    def max_length(self) -> int:
        lengths = [len(e) for e in (self._confident | self._ambiguous)]
        return max(lengths, default=0)

    def contains(self, syllables: Sequence[str]) -> bool:
        return tuple(syllables) in self._confident

    def contains_ambiguous(self, syllables: Sequence[str]) -> bool:
        return tuple(syllables) in self._ambiguous

    def __len__(self) -> int:
        return len(self._confident) + len(self._ambiguous)


def assert_well_formed(annotation: EntityAnnotation) -> None:
    previous_end = -1
    for entity in annotation.entities:
        assert entity.start_index >= previous_end
        previous_end = entity.end_index
        sliced = annotation.source[entity.span.char_start : entity.span.char_end]
        assert sliced == entity.text
        encoded = annotation.source.encode("utf-8")
        assert encoded[entity.span.byte_start : entity.span.byte_end] == entity.text.encode(
            "utf-8"
        )


# -- Protocol and configuration -----------------------------------------------
def test_satisfies_the_entity_recognizer_protocol(
    entity_recognizer: TibetanEntityRecognizer,
) -> None:
    assert isinstance(entity_recognizer, EntityRecognizer)


def test_tagger_evidence_flag_reflects_construction() -> None:
    assert TibetanEntityRecognizer().use_tagger_evidence is True
    assert (
        TibetanEntityRecognizer(use_tagger_evidence=False).use_tagger_evidence is False
    )


# -- Totality -----------------------------------------------------------------
def test_an_empty_tree_yields_an_empty_annotation(
    entity_recognizer: TibetanEntityRecognizer,
) -> None:
    annotation = entity_recognizer.recognize(DependencyTree(source=""))
    assert annotation.is_empty
    assert annotation.source == ""


@pytest.mark.parametrize(
    "pairs",
    [
        (("།", "punc"),),
        (("ལ", "case.all"),),
        (("ཁྱིམ", "n.count"), ("སོང", "v.past")),
    ],
)
def test_text_without_names_yields_no_entities(
    entity_recognizer: TibetanEntityRecognizer, pairs: tuple[tuple[str, str], ...]
) -> None:
    annotation = entity_recognizer.recognize(build_tree(*pairs))
    assert annotation.is_empty


# -- Matching behaviour -------------------------------------------------------
def test_a_confident_gazetteer_entry_is_recognised() -> None:
    recognizer = TibetanEntityRecognizer(
        gazetteer=StubGazetteer(confident={("ཀ", "ཁ")})
    )
    annotation = recognizer.recognize(
        build_tree(("ཀ", "n.count"), ("ཁ", "n.count"), ("སོང", "v.past"))
    )
    assert annotation.num_entities == 1
    assert annotation.entities[0].syllables == ("ཀ", "ཁ")
    assert annotation.entities[0].evidence is EntityEvidence.GAZETTEER


def test_a_confident_entry_the_tagger_also_marks_reports_both() -> None:
    recognizer = TibetanEntityRecognizer(
        gazetteer=StubGazetteer(confident={("ཀ", "ཁ")})
    )
    annotation = recognizer.recognize(
        build_tree(("ཀ", "n.prop"), ("ཁ", "n.prop"), ("སོང", "v.past"))
    )
    assert annotation.entities[0].evidence is EntityEvidence.BOTH


def test_an_ambiguous_entry_needs_the_tagger_to_agree() -> None:
    """Surfaces that are also ordinary words must not fire on their own.

    This is the rule that took held-out precision from 35% to 58%.
    """
    recognizer = TibetanEntityRecognizer(
        gazetteer=StubGazetteer(ambiguous={("ཀ", "ཁ")})
    )
    unsupported = recognizer.recognize(
        build_tree(("ཀ", "n.count"), ("ཁ", "n.count"), ("སོང", "v.past"))
    )
    assert unsupported.is_empty

    supported = recognizer.recognize(
        build_tree(("ཀ", "n.prop"), ("ཁ", "n.prop"), ("སོང", "v.past"))
    )
    assert supported.num_entities == 1
    assert supported.entities[0].syllables == ("ཀ", "ཁ")


def test_longest_match_wins() -> None:
    """A full title must not be fragmented into the name nested inside it."""
    recognizer = TibetanEntityRecognizer(
        gazetteer=StubGazetteer(confident={("ཀ", "ཁ"), ("ཀ", "ཁ", "ག")})
    )
    annotation = recognizer.recognize(
        build_tree(("ཀ", "n.count"), ("ཁ", "n.count"), ("ག", "n.count"))
    )
    assert annotation.num_entities == 1
    assert annotation.entities[0].syllables == ("ཀ", "ཁ", "ག")


def test_matching_resumes_after_a_match() -> None:
    recognizer = TibetanEntityRecognizer(
        gazetteer=StubGazetteer(confident={("ཀ", "ཁ"), ("ག", "ང")})
    )
    annotation = recognizer.recognize(
        build_tree(("ཀ", "n.count"), ("ཁ", "n.count"), ("ག", "n.count"), ("ང", "n.count"))
    )
    assert [e.syllables for e in annotation.entities] == [("ཀ", "ཁ"), ("ག", "ང")]
    assert_well_formed(annotation)


def test_a_name_may_span_an_internal_particle(
    entity_recognizer: TibetanEntityRecognizer,
) -> None:
    """The corpus annotates a place name across a genitive particle.

    ``འཛམ་བུ འི་ གླིང་`` is one name whose middle token is a case particle, so
    matching cannot stop at a non-nominal.
    """
    annotation = entity_recognizer.recognize(
        build_tree(
            ("འཛམ", "n.prop"),
            ("བུ", "n.count"),
            ("འི", "case.gen"),
            ("གླིང", "n.count"),
            ("བཞུགས", "v.past"),
        )
    )
    assert annotation.num_entities == 1
    entity = annotation.entities[0]
    assert entity.syllables == ("འཛམ", "བུ", "འི", "གླིང")
    assert entity.is_multi_morpheme
    assert TSHEG in entity.text, "the span keeps the tsheg between syllables"


def test_tagger_evidence_alone_can_recognise_a_name(
    entity_recognizer: TibetanEntityRecognizer,
) -> None:
    annotation = entity_recognizer.recognize(
        build_tree(("ཟཟཟ", "n.prop"), ("སོང", "v.past"))
    )
    assert annotation.num_entities == 1
    assert annotation.entities[0].evidence is EntityEvidence.TAGGER


def test_adjacent_proper_noun_tags_form_one_entity(
    entity_recognizer: TibetanEntityRecognizer,
) -> None:
    annotation = entity_recognizer.recognize(
        build_tree(("ཟཟཟ", "n.prop"), ("ཡཡཡ", "n.prop"), ("སོང", "v.past"))
    )
    assert annotation.num_entities == 1
    assert annotation.entities[0].num_morphemes == 2


def test_tagger_evidence_can_be_disabled() -> None:
    recognizer = TibetanEntityRecognizer(
        gazetteer=StubGazetteer(), use_tagger_evidence=False
    )
    annotation = recognizer.recognize(build_tree(("ཟཟཟ", "n.prop"), ("སོང", "v.past")))
    assert annotation.is_empty


def test_an_empty_injected_gazetteer_is_not_silently_replaced() -> None:
    """Regression guard for a dependency-injection defect.

    The default was selected with ``gazetteer or default_gazetteer()``. An empty
    gazetteer is falsy because it defines ``__len__``, so a legitimately-empty
    injected store was silently discarded and the shipped 2,767-entry one loaded
    in its place -- the caller would have had no way to tell.
    """
    recognizer = TibetanEntityRecognizer(
        gazetteer=StubGazetteer(), use_tagger_evidence=False
    )
    assert len(recognizer._gazetteer) == 0


def test_an_injected_gazetteer_is_used_instead_of_the_default() -> None:
    recognizer = TibetanEntityRecognizer(
        gazetteer=StubGazetteer(), use_tagger_evidence=False
    )
    annotation = recognizer.recognize(
        build_tree(("འཛམ", "n.count"), ("བུ", "n.count"), ("འི", "case.gen"), ("གླིང", "n.count"))
    )
    assert annotation.is_empty, "the shipped gazetteer must not be consulted"


# -- Guarantees over the real corpus ------------------------------------------
def recognize_corpus(
    recognizer: TibetanEntityRecognizer, sentences: list[str]
) -> list[EntityAnnotation]:
    analyzer = TibetanMorphologicalAnalyzer()
    tagger = HmmPosTagger()
    parser = TibetanDependencyParser()
    return [
        recognizer.recognize(parser.parse(tagger.tag(analyzer.analyze(s))))
        for s in sentences
    ]


def test_annotations_are_well_formed_over_the_corpus(
    entity_recognizer: TibetanEntityRecognizer, corpus_sentences: list[str]
) -> None:
    for annotation in recognize_corpus(entity_recognizer, corpus_sentences):
        assert_well_formed(annotation)


def test_entities_never_overlap_over_the_corpus(
    entity_recognizer: TibetanEntityRecognizer, corpus_sentences: list[str]
) -> None:
    for annotation in recognize_corpus(entity_recognizer, corpus_sentences):
        for previous, current in zip(
            annotation.entities, annotation.entities[1:], strict=False
        ):
            assert previous.end_index <= current.start_index


def test_the_corpus_yields_a_substantial_number_of_entities(
    entity_recognizer: TibetanEntityRecognizer, corpus_sentences: list[str]
) -> None:
    total = sum(a.num_entities for a in recognize_corpus(entity_recognizer, corpus_sentences))
    assert total > 10, total


def test_recognition_is_deterministic(
    entity_recognizer: TibetanEntityRecognizer, corpus_sentences: list[str]
) -> None:
    first = recognize_corpus(entity_recognizer, corpus_sentences[:15])
    second = recognize_corpus(entity_recognizer, corpus_sentences[:15])
    assert first == second


# -- Evaluation against the corpus entity layer -------------------------------
def gold_entity_spans(pairs: list[tuple[str, str]]) -> set[tuple[int, int]]:
    """Reconstruct gold ``(start, end)`` entity spans from the BIOES markers."""
    spans: set[tuple[int, int]] = set()
    offset = 0
    open_start: int | None = None
    open_end = 0

    for surface, tag in pairs:
        start, end = offset, offset + len(surface)
        offset = end
        if "n.prop" not in tag:
            if open_start is not None:
                spans.add((open_start, open_end))
                open_start = None
            continue
        boundary = tag.rsplit(".", 1)[-1] if "~n.prop." in tag else ""
        if boundary in ("B", "S") and open_start is not None:
            spans.add((open_start, open_end))
            open_start = None
        if open_start is None:
            open_start = start
        open_end = end
        if boundary in ("E", "S", ""):
            spans.add((open_start, open_end))
            open_start = None

    if open_start is not None:
        spans.add((open_start, open_end))
    return spans


def trim(span: tuple[int, int], text: str) -> tuple[int, int]:
    """Drop a trailing tsheg so gold and predicted boundaries are comparable."""
    start, end = span
    while end > start and text[end - 1] in "་༌ ":
        end -= 1
    return start, end


def score(
    recognizer: TibetanEntityRecognizer, corpus: list[list[tuple[str, str]]]
) -> tuple[float, float, float, int]:
    """Return ``(precision, recall, f1, gold_count)`` by exact span match."""
    analyzer = TibetanMorphologicalAnalyzer()
    tagger = HmmPosTagger()
    parser = TibetanDependencyParser()
    true_positive = false_positive = false_negative = gold_count = 0

    for line in corpus:
        text = "".join(surface for surface, _ in line)
        gold = {trim(s, text) for s in gold_entity_spans(line)}
        gold = {s for s in gold if s[1] > s[0]}

        annotation = recognizer.recognize(parser.parse(tagger.tag(analyzer.analyze(text))))
        predicted = {
            trim((e.span.char_start, e.span.char_end), text) for e in annotation.entities
        }
        predicted = {s for s in predicted if s[1] > s[0]}

        gold_count += len(gold)
        true_positive += len(gold & predicted)
        false_positive += len(predicted - gold)
        false_negative += len(gold - predicted)

    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    return precision, recall, f1, gold_count


def test_held_out_evaluation_has_a_meaningful_sample(
    entity_recognizer: TibetanEntityRecognizer,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    _, _, _, gold = score(entity_recognizer, heldout_corpus)
    assert gold > 100, gold


def test_precision_on_held_out_text(
    entity_recognizer: TibetanEntityRecognizer,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """Marpa was not used to build the gazetteer. Measured 61.0%."""
    precision, _, _, _ = score(entity_recognizer, heldout_corpus)
    assert precision >= 0.55, f"{precision:.1%}"


def test_recall_on_held_out_text(
    entity_recognizer: TibetanEntityRecognizer,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """Measured 66.0%."""
    _, recall, _, _ = score(entity_recognizer, heldout_corpus)
    assert recall >= 0.60, f"{recall:.1%}"


def test_f1_on_held_out_text(
    entity_recognizer: TibetanEntityRecognizer,
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """Measured 63.4%."""
    _, _, f1, _ = score(entity_recognizer, heldout_corpus)
    assert f1 >= 0.58, f"{f1:.1%}"


def test_the_two_tier_rule_beats_firing_on_every_entry(
    heldout_corpus: list[list[tuple[str, str]]],
) -> None:
    """What justifies the corroboration tier.

    Accepting every gazetteer entry unconditionally is simulated by promoting
    the ambiguous tier to confident. Measured, that costs roughly 23 points of
    precision.
    """
    shipped = default_gazetteer()
    promoted = StubGazetteer(
        confident=set(shipped._entries) | set(shipped._ambiguous)
    )

    tiered_precision, _, _, _ = score(TibetanEntityRecognizer(), heldout_corpus)
    flat_precision, _, _, _ = score(
        TibetanEntityRecognizer(gazetteer=promoted), heldout_corpus
    )
    assert tiered_precision > flat_precision
