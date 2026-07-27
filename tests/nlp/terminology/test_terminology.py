"""Unit, integration and regression tests for Stage 10 terminology recognition.

Covers the repository facet (:mod:`teea.persistence.terminology`), the domain
models, and the recogniser, including the **User Dictionary** that Figure 5
names as one of the stage's three sources.

The glossary itself cannot be scored -- no gold Tibetan term list exists in the
repository (ADR-012) -- so its quality is asserted structurally instead: every
entry is a multi-syllable curated dictionary headword, and spot checks confirm
that well-known Buddhist technical terms are present and that scholastic
register formulae are not.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from teea.core.errors import ConfigurationError
from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.dependency import DependencyTree, TibetanDependencyParser
from teea.nlp.morphology import Morpheme, MorphemeKind, TibetanMorphologicalAnalyzer
from teea.nlp.postagging import HmmPosTagger, TaggedMorpheme, TaggedText, coarse_category
from teea.nlp.terminology import (
    GlossaryTerminologyRecognizer,
    RecognizedTerm,
    TerminologyAnnotation,
    TerminologyRecognizer,
)
from teea.persistence import (
    InMemoryTerminology,
    TerminologyRepository,
    TermSource,
    default_terminology,
)

TSHEG = "་"

#: Well-known Buddhist technical terms, as syllable tuples.
ARHAT = ("དགྲ", "བཅོམ")
TWO_TRUTHS = ("བདེན", "གཉིས")


# -- Helpers ------------------------------------------------------------------
def build_tree(*pairs: tuple[str, str]) -> DependencyTree:
    """Build a Stage 8 tree directly from ``(surface, tag)`` pairs."""
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
    return TibetanDependencyParser().parse(TaggedText(source=source, morphemes=tuple(morphemes)))


class StubTerminology:
    """A tiny repository, to prove the injected one is really used."""

    def __init__(
        self,
        glossary: set[tuple[str, ...]] | None = None,
        user: set[tuple[str, ...]] | None = None,
    ) -> None:
        self._glossary = glossary or set()
        self._user = user or set()

    @property
    def max_length(self) -> int:
        return max((len(t) for t in (self._glossary | self._user)), default=0)

    def lookup(self, syllables: Sequence[str]) -> TermSource | None:
        key = tuple(syllables)
        if key in self._user:
            return TermSource.USER_DICTIONARY
        if key in self._glossary:
            return TermSource.GLOSSARY
        return None

    def __len__(self) -> int:
        return len(self._glossary | self._user)


def write_payload(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# -- Repository ---------------------------------------------------------------
def test_satisfies_the_terminology_repository_protocol(
    terminology: InMemoryTerminology,
) -> None:
    assert isinstance(terminology, TerminologyRepository)


def test_default_terminology_is_cached() -> None:
    assert default_terminology() is default_terminology()


def test_the_shipped_glossary_is_populated(terminology: InMemoryTerminology) -> None:
    assert terminology.num_glossary > 500
    assert terminology.num_user == 0, "the shipped instance carries no user terms"
    assert len(terminology) == terminology.num_glossary


def test_every_glossary_entry_is_a_compound(terminology: InMemoryTerminology) -> None:
    """A single syllable is not a technical term; the builder requires two."""
    assert all(len(entry) >= 2 for entry in terminology._glossary)
    assert terminology.max_length == max(len(e) for e in terminology._glossary)


def test_provenance_records_both_criteria(terminology: InMemoryTerminology) -> None:
    """Each entry must be defensible; the payload records why."""
    provenance = terminology.provenance
    assert "curated dictionary headword" in provenance["criteria"]
    assert "Buddhist canon" in provenance["criteria"]
    assert provenance["min_canon_frequency"] >= 1
    assert len(provenance["sources"]) == 3


@pytest.mark.parametrize("term", [ARHAT, TWO_TRUTHS])
def test_well_known_buddhist_terms_are_present(
    terminology: InMemoryTerminology, term: tuple[str, ...]
) -> None:
    """Spot check, since the glossary cannot be scored against gold data."""
    assert terminology.lookup(term) is TermSource.GLOSSARY


@pytest.mark.parametrize(
    "formula",
    [("ཕྱིར", "རོ"), ("འགྱུར", "རོ"), ("ཞེ", "ན"), ("པར", "ཐལ")],
)
def test_scholastic_register_formulae_are_absent(
    terminology: InMemoryTerminology, formula: tuple[str, ...]
) -> None:
    """The failure mode the two-criteria rule exists to prevent.

    These phrases are far more frequent in the Buddhist canon than in narrative,
    so contrastive frequency alone ranks them at the very top. They are not
    terminology, and requiring a dictionary headword excludes them.
    """
    assert terminology.lookup(formula) is None


def test_ordinary_vocabulary_is_not_a_term(terminology: InMemoryTerminology) -> None:
    assert terminology.lookup(("ཁྱིམ",)) is None
    assert terminology.lookup(("ཁྱིམ", "ལ")) is None


# -- The User Dictionary (Figure 5's third bullet) ----------------------------
def test_user_terms_are_recorded_separately(tmp_path: Path) -> None:
    repository = InMemoryTerminology(user_terms=[("ཁྱིམ", "ལ")])
    assert repository.num_user == 1
    assert repository.lookup(("ཁྱིམ", "ལ")) is TermSource.USER_DICTIONARY
    assert repository.lookup(ARHAT) is TermSource.GLOSSARY


def test_the_user_dictionary_wins_over_the_glossary() -> None:
    """A scholar who defines a term has stated the reading they want."""
    repository = InMemoryTerminology(user_terms=[ARHAT])
    assert repository.lookup(ARHAT) is TermSource.USER_DICTIONARY


def test_empty_user_terms_are_ignored() -> None:
    repository = InMemoryTerminology(user_terms=[(), ("ཁྱིམ", "ལ")])
    assert repository.num_user == 1


def test_user_terms_extend_the_matcher_lookahead() -> None:
    """A long user term must still be reachable by the recogniser."""
    long_term = tuple(f"ས{i}" for i in range(9))
    repository = InMemoryTerminology(user_terms=[long_term])
    assert repository.max_length >= len(long_term)


# -- Repository error paths ---------------------------------------------------
def test_a_missing_file_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        InMemoryTerminology(tmp_path / "absent.json")
    assert "path" in excinfo.value.context


def test_invalid_json_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not valid JSON"):
        InMemoryTerminology(path)


def test_a_non_utf8_payload_raises_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "utf16.json"
    path.write_bytes(b"\xff\xfe{\x00}\x00")
    with pytest.raises(ConfigurationError, match="could not be read"):
        InMemoryTerminology(path)


@pytest.mark.parametrize("payload", [7, "text", [1]])
def test_a_non_object_payload_raises_configuration_error(tmp_path: Path, payload: object) -> None:
    with pytest.raises(ConfigurationError, match="must be a JSON object"):
        InMemoryTerminology(write_payload(tmp_path / "s.json", payload))


def test_a_payload_without_entries_raises_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="missing required sections"):
        InMemoryTerminology(write_payload(tmp_path / "e.json", {"provenance": {}}))


def test_entries_must_be_a_list(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="must be a list"):
        InMemoryTerminology(write_payload(tmp_path / "b.json", {"entries": {}}))


def test_a_custom_payload_is_independent_of_the_shipped_one(tmp_path: Path) -> None:
    custom = InMemoryTerminology(write_payload(tmp_path / "tiny.json", {"entries": [["ཀ", "ཁ"]]}))
    assert len(custom) == 1
    assert custom.lookup(("ཀ", "ཁ")) is TermSource.GLOSSARY
    assert custom.lookup(ARHAT) is None


# -- Models -------------------------------------------------------------------
def make_term(source: str, morphemes: tuple[TaggedMorpheme, ...]) -> RecognizedTerm:
    offsets = utf8_byte_offsets(source)
    start, end = morphemes[0].span.char_start, morphemes[-1].span.char_end
    return RecognizedTerm(
        text=source[start:end],
        span=TextSpan(
            char_start=start, char_end=end, byte_start=offsets[start], byte_end=offsets[end]
        ),
        start_index=0,
        end_index=len(morphemes),
        source=TermSource.GLOSSARY,
        morphemes=morphemes,
    )


def sample_morphemes() -> tuple[str, tuple[TaggedMorpheme, ...]]:
    tree = build_tree(("དགྲ", "n.count"), ("བཅོམ", "n.count"), ("སོང", "v.past"))
    return tree.source, tuple(n.morpheme for n in tree.nodes)[:2]


def test_a_valid_term_constructs() -> None:
    source, morphemes = sample_morphemes()
    term = make_term(source, morphemes)
    assert term.num_morphemes == 2
    assert term.syllables == ARHAT
    assert not term.is_user_defined
    assert TSHEG in term.text, "the span keeps the tsheg between syllables"


def test_an_empty_index_range_is_rejected() -> None:
    _source, morphemes = sample_morphemes()
    with pytest.raises(ValidationError, match="greater than start_index"):
        RecognizedTerm(
            text="དགྲ",
            span=morphemes[0].span,
            start_index=1,
            end_index=1,
            source=TermSource.GLOSSARY,
            morphemes=(morphemes[0],),
        )


def test_the_morpheme_count_must_match_the_index_range() -> None:
    source, morphemes = sample_morphemes()
    offsets = utf8_byte_offsets(source)
    start, end = morphemes[0].span.char_start, morphemes[-1].span.char_end
    with pytest.raises(ValidationError, match="expected 3 morphemes"):
        RecognizedTerm(
            text=source[start:end],
            span=TextSpan(
                char_start=start, char_end=end, byte_start=offsets[start], byte_end=offsets[end]
            ),
            start_index=0,
            end_index=3,
            source=TermSource.GLOSSARY,
            morphemes=morphemes,
        )


def test_empty_text_is_rejected() -> None:
    _source, morphemes = sample_morphemes()
    with pytest.raises(ValidationError, match="must not be empty"):
        RecognizedTerm(
            text="",
            span=morphemes[0].span,
            start_index=0,
            end_index=1,
            source=TermSource.GLOSSARY,
            morphemes=(morphemes[0],),
        )


def test_the_span_must_start_at_the_first_morpheme() -> None:
    source, morphemes = sample_morphemes()
    with pytest.raises(ValidationError, match="must start at the first morpheme"):
        RecognizedTerm(
            text=source[morphemes[1].span.char_start : morphemes[-1].span.char_end],
            span=morphemes[1].span,
            start_index=0,
            end_index=2,
            source=TermSource.GLOSSARY,
            morphemes=morphemes,
        )


def test_the_span_must_end_at_the_last_morpheme() -> None:
    source, morphemes = sample_morphemes()
    with pytest.raises(ValidationError, match="must end at the last morpheme"):
        RecognizedTerm(
            text=source[morphemes[0].span.char_start : morphemes[0].span.char_end],
            span=morphemes[0].span,
            start_index=0,
            end_index=2,
            source=TermSource.GLOSSARY,
            morphemes=morphemes,
        )


def test_a_term_span_beyond_the_source_is_rejected() -> None:
    source, morphemes = sample_morphemes()
    term = make_term(source, morphemes)
    with pytest.raises(ValidationError, match="exceeds the source text"):
        TerminologyAnnotation(source="ཀ", terms=(term,))


def test_a_term_whose_span_does_not_select_its_text_is_rejected() -> None:
    source, morphemes = sample_morphemes()
    term = make_term(source, morphemes)
    padded = "ཀཁགངཅཆཇཉཏཐདནཔཕབམ" + source
    with pytest.raises(ValidationError, match="does not select its own text"):
        TerminologyAnnotation(source=padded, terms=(term,))


def test_term_is_frozen_and_forbids_unknown_fields() -> None:
    source, morphemes = sample_morphemes()
    term = make_term(source, morphemes)
    with pytest.raises(ValidationError):
        term.text = "x"  # type: ignore[misc]


def test_annotation_rejects_overlapping_terms() -> None:
    source, morphemes = sample_morphemes()
    first = make_term(source, morphemes)
    with pytest.raises(ValidationError, match="must not overlap"):
        TerminologyAnnotation(source=source, terms=(first, first))


def test_annotation_accessors() -> None:
    source, morphemes = sample_morphemes()
    term = make_term(source, morphemes)
    annotation = TerminologyAnnotation(source=source, terms=(term,))
    assert annotation.num_terms == 1
    assert len(annotation) == 1
    assert not annotation.is_empty
    assert annotation.texts == (term.text,)
    assert annotation.of_source(TermSource.GLOSSARY) == (term,)
    assert annotation.of_source(TermSource.USER_DICTIONARY) == ()
    assert annotation.term_at_char(0) is term
    assert annotation.term_at_char(term.span.char_end) is None
    assert annotation.term_at_char(-1) is None
    assert annotation.covers_morpheme(0)
    assert not annotation.covers_morpheme(5)


def test_an_empty_annotation_is_valid() -> None:
    annotation = TerminologyAnnotation(source="")
    assert annotation.is_empty
    assert annotation.texts == ()


# -- Recogniser ---------------------------------------------------------------
def test_satisfies_the_recognizer_protocol(
    terminology_recognizer: GlossaryTerminologyRecognizer,
) -> None:
    assert isinstance(terminology_recognizer, TerminologyRecognizer)


def test_an_empty_tree_yields_an_empty_annotation(
    terminology_recognizer: GlossaryTerminologyRecognizer,
) -> None:
    annotation = terminology_recognizer.recognize(DependencyTree(source=""))
    assert annotation.is_empty
    assert annotation.source == ""


def test_a_known_term_is_recognised(
    terminology_recognizer: GlossaryTerminologyRecognizer,
) -> None:
    annotation = terminology_recognizer.recognize(
        build_tree(("དགྲ", "n.count"), ("བཅོམ", "n.count"), ("སོང", "v.past"))
    )
    assert annotation.num_terms == 1
    assert annotation.terms[0].syllables == ARHAT
    assert annotation.terms[0].source is TermSource.GLOSSARY


def test_ordinary_text_yields_no_terms(
    terminology_recognizer: GlossaryTerminologyRecognizer,
) -> None:
    annotation = terminology_recognizer.recognize(
        build_tree(("ཁྱིམ", "n.count"), ("ལ", "case.all"), ("སོང", "v.past"))
    )
    assert annotation.is_empty


def test_a_user_term_is_recognised_and_attributed() -> None:
    """Figure 5's third bullet, end to end."""
    recognizer = GlossaryTerminologyRecognizer(
        terminology=InMemoryTerminology(user_terms=[("ཁྱིམ", "ལ")])
    )
    annotation = recognizer.recognize(
        build_tree(("ཁྱིམ", "n.count"), ("ལ", "case.all"), ("སོང", "v.past"))
    )
    assert annotation.num_terms == 1
    assert annotation.terms[0].is_user_defined
    assert annotation.of_source(TermSource.USER_DICTIONARY)


def test_longest_match_wins() -> None:
    """A compound term must not be fragmented into the term nested inside it."""
    recognizer = GlossaryTerminologyRecognizer(
        terminology=StubTerminology(glossary={("ཀ", "ཁ"), ("ཀ", "ཁ", "ག")})
    )
    annotation = recognizer.recognize(
        build_tree(("ཀ", "n.count"), ("ཁ", "n.count"), ("ག", "n.count"))
    )
    assert annotation.num_terms == 1
    assert annotation.terms[0].syllables == ("ཀ", "ཁ", "ག")


def test_a_single_syllable_is_never_a_term() -> None:
    recognizer = GlossaryTerminologyRecognizer(terminology=StubTerminology(glossary={("ཀ",)}))
    annotation = recognizer.recognize(build_tree(("ཀ", "n.count"), ("སོང", "v.past")))
    assert annotation.is_empty


def test_matching_resumes_after_a_term() -> None:
    recognizer = GlossaryTerminologyRecognizer(
        terminology=StubTerminology(glossary={("ཀ", "ཁ"), ("ག", "ང")})
    )
    annotation = recognizer.recognize(
        build_tree(("ཀ", "n.count"), ("ཁ", "n.count"), ("ག", "n.count"), ("ང", "n.count"))
    )
    assert [t.syllables for t in annotation.terms] == [("ཀ", "ཁ"), ("ག", "ང")]


def test_an_empty_injected_repository_is_not_silently_replaced() -> None:
    """Regression guard, matching Stages 7 and 9.

    An empty repository is falsy because it defines ``__len__``, so selecting the
    default with ``or`` would discard it and load the shipped glossary instead.
    """
    recognizer = GlossaryTerminologyRecognizer(terminology=StubTerminology())
    assert len(recognizer._terminology) == 0
    assert recognizer.recognize(build_tree(("དགྲ", "n.count"), ("བཅོམ", "n.count"))).is_empty


# -- Guarantees over the real corpus ------------------------------------------
def recognize_corpus(
    recognizer: GlossaryTerminologyRecognizer, sentences: list[str]
) -> list[TerminologyAnnotation]:
    analyzer = TibetanMorphologicalAnalyzer()
    tagger = HmmPosTagger()
    parser = TibetanDependencyParser()
    return [recognizer.recognize(parser.parse(tagger.tag(analyzer.analyze(s)))) for s in sentences]


def test_annotations_are_well_formed_over_the_corpus(
    terminology_recognizer: GlossaryTerminologyRecognizer, corpus_sentences: list[str]
) -> None:
    for sentence, annotation in zip(
        corpus_sentences, recognize_corpus(terminology_recognizer, corpus_sentences), strict=True
    ):
        previous_end = -1
        for term in annotation.terms:
            assert term.start_index >= previous_end
            previous_end = term.end_index
            assert sentence[term.span.char_start : term.span.char_end] == term.text
            encoded = sentence.encode("utf-8")
            assert encoded[term.span.byte_start : term.span.byte_end] == term.text.encode("utf-8")


def test_recognition_is_deterministic(
    terminology_recognizer: GlossaryTerminologyRecognizer, corpus_sentences: list[str]
) -> None:
    subset = corpus_sentences[:20]
    assert recognize_corpus(terminology_recognizer, subset) == recognize_corpus(
        terminology_recognizer, subset
    )


def test_narrative_text_yields_few_terms(
    terminology_recognizer: GlossaryTerminologyRecognizer, corpus_sentences: list[str]
) -> None:
    """A precision signal available without gold data.

    The glossary requires zero occurrences in the general narrative corpus, so a
    narrative text should yield very few terms. A sharp rise would mean the
    two-criteria rule had been weakened.
    """
    total = sum(a.num_terms for a in recognize_corpus(terminology_recognizer, corpus_sentences))
    assert total <= len(corpus_sentences) // 2, total
