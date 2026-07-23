"""Unit, regression and edge-case tests for the Stage 11 semantic analyser.

Every rule the analyser applies is exercised here against a tree built by the
**real** Stage 8 parser from chosen part-of-speech tags, so the relations under
test are the ones Stage 8 actually assigns rather than a re-statement of them.
The verb lexicon is injected as a stub wherever a specific argument frame is the
subject of the test, which keeps those cases independent of the shipped payload.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from teea.core.errors import ErrorCode, InputValidationError
from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.dependency import DependencyRelation, DependencyTree, TibetanDependencyParser
from teea.nlp.morphology import Morpheme, MorphemeKind, TibetanMorphologicalAnalyzer
from teea.nlp.ner import EntityAnnotation, EntityEvidence, NamedEntity
from teea.nlp.postagging import HmmPosTagger, TaggedMorpheme, TaggedText, coarse_category
from teea.nlp.semantics import (
    Polarity,
    RoleEvidence,
    SemanticAnalyzer,
    SemanticGraph,
    SemanticNodeKind,
    SemanticRole,
    SentenceMood,
    TibetanSemanticAnalyzer,
)
from teea.nlp.semantics.analyzer import _PHRASE_INTERNAL as PHRASE_INTERNAL
from teea.nlp.semantics.analyzer import _case_tags
from teea.nlp.terminology import RecognizedTerm, TerminologyAnnotation
from teea.persistence import (
    ArgumentSlot,
    TermSource,
    Transitivity,
    VerbFrame,
    VerbLexiconRepository,
)

TSHEG = "་"

TRANSITIVE = VerbFrame(
    lemma="ཀློག་",
    frame="Erg-Abs",
    slots=frozenset({ArgumentSlot.ERGATIVE, ArgumentSlot.ABSOLUTIVE}),
    transitivity=Transitivity.TRANSITIVE,
)
INTRANSITIVE = VerbFrame(
    lemma="འགྲོ་",
    frame="Abs-Obl",
    slots=frozenset({ArgumentSlot.ABSOLUTIVE, ArgumentSlot.OBLIQUE}),
    transitivity=Transitivity.INTRANSITIVE,
)
SILENT = VerbFrame(lemma="ཀླན་")


# -- Helpers ------------------------------------------------------------------
def build_tree(*pairs: tuple[str, str]) -> DependencyTree:
    """Build a Stage 8 tree from ``(surface, tag)`` pairs using the real parser."""
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


def entity_over(tree: DependencyTree, start: int, end: int) -> EntityAnnotation:
    """Annotate ``tree`` with one entity covering nodes ``[start, end)``."""
    run = tuple(node.morpheme for node in tree.nodes[start:end])
    span = TextSpan(
        char_start=run[0].span.char_start,
        char_end=run[-1].span.char_end,
        byte_start=run[0].span.byte_start,
        byte_end=run[-1].span.byte_end,
    )
    return EntityAnnotation(
        source=tree.source,
        entities=(
            NamedEntity(
                text=tree.source[span.char_start : span.char_end],
                span=span,
                start_index=start,
                end_index=end,
                evidence=EntityEvidence.GAZETTEER,
                morphemes=run,
            ),
        ),
    )


def term_over(tree: DependencyTree, start: int, end: int) -> TerminologyAnnotation:
    """Annotate ``tree`` with one technical term covering nodes ``[start, end)``."""
    run = tuple(node.morpheme for node in tree.nodes[start:end])
    span = TextSpan(
        char_start=run[0].span.char_start,
        char_end=run[-1].span.char_end,
        byte_start=run[0].span.byte_start,
        byte_end=run[-1].span.byte_end,
    )
    return TerminologyAnnotation(
        source=tree.source,
        terms=(
            RecognizedTerm(
                text=tree.source[span.char_start : span.char_end],
                span=span,
                start_index=start,
                end_index=end,
                source=TermSource.GLOSSARY,
                morphemes=run,
            ),
        ),
    )


class StubVerbLexicon:
    """A tiny lexicon, to prove the injected one is really used."""

    def __init__(
        self, entries: dict[tuple[str, ...], tuple[VerbFrame, ...]] | None = None
    ) -> None:
        self._entries = entries or {}

    @property
    def max_length(self) -> int:
        return max((len(key) for key in self._entries), default=0)

    def lookup(self, syllables: Sequence[str]) -> tuple[VerbFrame, ...]:
        return self._entries.get(tuple(syllables), ())

    def __len__(self) -> int:
        return len(self._entries)


def analyzer_with(*frames: tuple[tuple[str, ...], VerbFrame]) -> TibetanSemanticAnalyzer:
    """An analyser backed by a stub lexicon holding exactly ``frames``."""
    return TibetanSemanticAnalyzer(
        verbs=StubVerbLexicon({key: (frame,) for key, frame in frames})
    )


def role_of(graph: SemanticGraph, target_text: str) -> tuple[SemanticRole, RoleEvidence]:
    """Return the role and evidence of the edge governing the node with that text."""
    for node in graph.nodes:
        if node.text == target_text:
            edge = graph.governor_of(node.index)
            assert edge is not None, f"{target_text!r} has no governor"
            return edge.role, edge.evidence
    raise AssertionError(f"no node with text {target_text!r}")


# -- Contract and dependency injection ----------------------------------------
def test_satisfies_the_semantic_analyzer_protocol(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    assert isinstance(semantic_analyzer, SemanticAnalyzer)


def test_the_injected_lexicon_is_used() -> None:
    analyzer = analyzer_with((("ཀློག",), TRANSITIVE))
    graph = analyzer.analyze(build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres")))
    assert graph.predicates[0].lemma == "ཀློག་"


def test_an_empty_injected_lexicon_is_not_silently_replaced() -> None:
    """``is None``, not ``or``: an empty repository is falsy because it has __len__.

    The same defect was found and fixed in Stages 7, 9 and 10. A caller injecting
    a deliberately empty lexicon must get an empty lexicon.
    """
    analyzer = TibetanSemanticAnalyzer(verbs=StubVerbLexicon())
    graph = analyzer.analyze(build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres")))
    assert graph.predicates[0].frames == ()
    assert graph.predicates[0].lemma is None


def test_the_default_analyzer_uses_the_shipped_lexicon(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    )
    assert graph.predicates[0].lemma == "ཀློག་"


def test_a_stub_lexicon_satisfies_the_repository_protocol() -> None:
    assert isinstance(StubVerbLexicon(), VerbLexiconRepository)


# -- Totality and input validation ---------------------------------------------
def test_an_empty_tree_yields_an_empty_graph(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Total, like every earlier stage: no content is not an error."""
    graph = semantic_analyzer.analyze(DependencyTree(source=""))
    assert graph.is_empty
    assert graph.source == ""
    assert graph.intent.mood is SentenceMood.DECLARATIVE
    assert graph.intent.is_marked is False


def test_a_tree_of_punctuation_alone_yields_no_nodes(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(build_tree(("།", "punc")))
    assert graph.is_empty
    assert graph.num_edges == 0


def test_annotations_may_be_omitted(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """A caller that has not run Stages 9 and 10 still gets a graph."""
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    )
    assert graph.num_nodes == 2
    assert graph.named_entities == ()
    assert graph.terminology == ()


def test_an_entity_annotation_from_another_sentence_is_rejected(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Silently accepting it would address suggestions to the wrong document."""
    tree = build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    other = build_tree(("ཡུལ", "n.count"), ("འགྲོ", "v.pres"))
    with pytest.raises(InputValidationError, match="different source text") as error:
        semantic_analyzer.analyze(tree, entities=entity_over(other, 0, 1))
    assert error.value.code is ErrorCode.INPUT_INVALID


def test_a_terminology_annotation_from_another_sentence_is_rejected(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    tree = build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    other = build_tree(("ཡུལ", "n.count"), ("འགྲོ", "v.pres"))
    with pytest.raises(InputValidationError, match="different source text"):
        semantic_analyzer.analyze(tree, terms=term_over(other, 0, 1))


def test_an_entity_indexing_past_the_tree_is_rejected(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Same text, more morphemes: a mismatch the source check cannot catch."""
    tree = build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    annotation = entity_over(tree, 0, 2)
    stretched = annotation.model_copy(
        update={
            "entities": (
                annotation.entities[0].model_copy(update={"end_index": 9}),
            )
        }
    )
    with pytest.raises(InputValidationError, match="does not have") as error:
        semantic_analyzer.analyze(tree, entities=stretched)
    assert error.value.context["num_nodes"] == 2


def test_a_term_indexing_past_the_tree_is_rejected(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    tree = build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    annotation = term_over(tree, 0, 2)
    stretched = annotation.model_copy(
        update={"terms": (annotation.terms[0].model_copy(update={"end_index": 9}),)}
    )
    with pytest.raises(InputValidationError, match="does not have"):
        semantic_analyzer.analyze(tree, terms=stretched)


def test_an_empty_annotation_is_accepted(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    tree = build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    graph = semantic_analyzer.analyze(
        tree,
        entities=EntityAnnotation(source=tree.source),
        terms=TerminologyAnnotation(source=tree.source),
    )
    assert graph.num_nodes == 2


# -- Which morphemes become nodes ----------------------------------------------
@pytest.mark.parametrize(
    ("surface", "tag"),
    [
        ("ཞིང", "n.count"),
        ("ཀློག", "v.pres"),
        ("ཁོ", "p.pers"),
        ("གསུམ", "num.card"),
        ("ཆེན", "adj"),
        ("ད", "adv.temp"),
    ],
)
def test_content_words_become_nodes(
    semantic_analyzer: TibetanSemanticAnalyzer, surface: str, tag: str
) -> None:
    graph = semantic_analyzer.analyze(build_tree((surface, tag), ("འགྲོ", "v.pres")))
    assert surface in {node.text for node in graph.nodes}


@pytest.mark.parametrize(
    ("surface", "tag"),
    [
        ("།", "punc"),
        ("གིས", "case.agn"),
        ("དེ", "d.dem"),
        ("མ", "neg"),
        ("ཨ", "interj"),
        ("བྷ", "skt"),
    ],
)
def test_grammatical_and_unanalysed_material_does_not_become_a_node(
    semantic_analyzer: TibetanSemanticAnalyzer, surface: str, tag: str
) -> None:
    """A node asserts "this is a concept"; these tags cannot support that."""
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), (surface, tag), ("འགྲོ", "v.pres"))
    )
    assert surface not in {node.text for node in graph.nodes}


def test_an_auxiliary_does_not_become_a_node(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """A copula is verbal, so the category filter admits it, but it supports a
    predicate rather than being one -- and Stage 8 attaches its arguments
    elsewhere, so a node here would have none."""
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("ཡིན", "v.cop"))
    )
    assert "ཡིན" not in {node.text for node in graph.nodes}


# -- Predicate or concept ------------------------------------------------------
def test_the_sentence_head_verb_is_a_predicate(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    )
    assert [node.text for node in graph.predicates] == ["ཀློག"]


def test_a_subordinate_clause_head_is_also_a_predicate(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Stage 8 attaches a non-root finite verb with ``mark``; that is a clause."""
    graph = semantic_analyzer.analyze(
        build_tree(("བྱས", "v.past"), ("ཞིང", "n.count"), ("འགྲོ", "v.pres"))
    )
    assert {node.text for node in graph.predicates} == {"བྱས", "འགྲོ"}


def test_a_nominal_sentence_head_is_a_concept(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("ཡུལ", "n.count"))
    )
    assert graph.predicates == ()
    assert len(graph.concepts) == 2


def test_a_deverbal_noun_heading_a_verbless_clause_is_a_predicate(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Stage 8 heads a verbless fragment with its last nominal, and the
    constraint grammars count deverbal nouns among head nouns."""
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("བྱས", "n.v.past"))
    )
    assert [node.text for node in graph.predicates] == ["བྱས"]
    assert graph.nodes[1].kind is SemanticNodeKind.PREDICATE


# -- Lemmatisation -------------------------------------------------------------
def test_only_verbal_material_is_looked_up() -> None:
    """Many Tibetan nouns are homographs of verb stems.

    Consulting the lexicon for a morpheme Stage 7 tagged as a noun would overrule
    that stage's judgement, which the pipeline forbids.
    """
    analyzer = analyzer_with((("ཀློག",), TRANSITIVE))
    graph = analyzer.analyze(build_tree(("ཀློག", "n.count"), ("འགྲོ", "v.pres")))
    assert graph.nodes[0].frames == ()


def test_a_multi_syllable_verb_form_is_looked_up_as_a_whole() -> None:
    analyzer = TibetanSemanticAnalyzer(
        verbs=StubVerbLexicon({("ཀུམ", "པ"): (TRANSITIVE,)})
    )
    tree = build_tree(("ཀུམ", "n.v.pres"), ("པ", "n.v.pres"))
    graph = analyzer.analyze(tree, entities=entity_over(tree, 0, 2))
    assert graph.nodes[0].frames == (TRANSITIVE,)


def test_the_head_syllable_is_tried_when_the_whole_run_misses() -> None:
    """A verb whose stem is one syllable of a longer anchored run is still found."""
    analyzer = TibetanSemanticAnalyzer(
        verbs=StubVerbLexicon({("ཀུམ",): (TRANSITIVE,), ("ཞིང", "ཀུམ"): ()})
    )
    tree = build_tree(("ཞིང", "n.v.pres"), ("ཀུམ", "n.v.pres"))
    graph = analyzer.analyze(tree, entities=entity_over(tree, 0, 2))
    assert graph.nodes[0].head.text == "ཀུམ"
    assert graph.nodes[0].frames == (TRANSITIVE,)


def test_a_run_the_lexicon_does_not_know_reports_no_frame() -> None:
    """Neither the whole run nor the head syllable is attested."""
    analyzer = TibetanSemanticAnalyzer(
        verbs=StubVerbLexicon({("ཀློག",): (TRANSITIVE,)})
    )
    tree = build_tree(("ཞིང", "n.v.pres"), ("ཀུམ", "n.v.pres"))
    graph = analyzer.analyze(tree, entities=entity_over(tree, 0, 2))
    assert graph.nodes[0].frames == ()


def test_an_unknown_verb_form_reports_no_frame() -> None:
    analyzer = analyzer_with((("ཀློག",), TRANSITIVE))
    graph = analyzer.analyze(build_tree(("ཞིང", "n.count"), ("ཟzz", "v.pres")))
    assert graph.predicates[0].frames == ()
    assert graph.predicates[0].lemma is None


# -- Role assignment: the case system ------------------------------------------
def test_the_agentive_marks_an_agent(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("གིས", "case.agn"), ("ཀློག", "v.pres"))
    )
    assert role_of(graph, "ཞིང") == (SemanticRole.AGENT, RoleEvidence.CASE)


def test_the_allative_marks_a_goal(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཡུལ", "n.count"), ("ལ", "case.all"), ("འགྲོ", "v.pres"))
    )
    assert role_of(graph, "ཡུལ") == (SemanticRole.GOAL, RoleEvidence.CASE)


@pytest.mark.parametrize(
    ("tag", "role"),
    [
        ("case.loc", SemanticRole.LOCATION),
        ("case.abl", SemanticRole.SOURCE),
        ("case.ela", SemanticRole.SOURCE),
        ("case.ass", SemanticRole.ASSOCIATE),
        ("case.comp", SemanticRole.STANDARD),
    ],
)
def test_the_oblique_cases_are_recovered_individually(
    semantic_analyzer: TibetanSemanticAnalyzer, tag: str, role: SemanticRole
) -> None:
    """Stage 8 collapses all of these into ``obl``; the particle distinguishes them."""
    graph = semantic_analyzer.analyze(
        build_tree(("ཡུལ", "n.count"), ("ན", tag), ("འགྲོ", "v.pres"))
    )
    assert role_of(graph, "ཡུལ") == (role, RoleEvidence.CASE)


def test_the_genitive_marks_a_possessor(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(
            ("ཞིང", "n.count"),
            ("གི", "case.gen"),
            ("ཡུལ", "n.count"),
            ("འགྲོ", "v.pres"),
        )
    )
    assert role_of(graph, "ཞིང") == (SemanticRole.POSSESSOR, RoleEvidence.CASE)
    possessor = graph.governor_of(graph.nodes[0].index)
    assert possessor is not None
    assert graph.nodes[possessor.source].text == "ཡུལ"


def test_a_case_particle_is_found_across_an_intervening_modifier(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Tibetan places adjectives after their noun, so *noun adj case* is ordinary."""
    graph = semantic_analyzer.analyze(
        build_tree(
            ("ཡུལ", "n.count"),
            ("ཆེན", "adj"),
            ("ན", "case.loc"),
            ("འགྲོ", "v.pres"),
        )
    )
    assert role_of(graph, "ཡུལ") == (SemanticRole.LOCATION, RoleEvidence.CASE)


def test_a_case_particle_belonging_to_another_nominal_is_not_borrowed(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """A second nominal closes the phrase, so the search must stop there."""
    graph = semantic_analyzer.analyze(
        build_tree(
            ("ཞིང", "n.count"),
            ("ཡུལ", "n.count"),
            ("ན", "case.loc"),
            ("འགྲོ", "v.pres"),
        )
    )
    assert role_of(graph, "ཞིང")[0] is not SemanticRole.LOCATION
    assert role_of(graph, "ཡུལ") == (SemanticRole.LOCATION, RoleEvidence.CASE)


def test_a_nominal_at_the_end_of_the_sentence_has_no_case_particle(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("འགྲོ", "v.pres"), ("ཡུལ", "n.count"))
    )
    assert graph.num_nodes == 2


# -- Role assignment: the absolutive, resolved lexically -----------------------
def test_a_transitive_frame_makes_the_absolutive_a_patient() -> None:
    """The correction Stage 11 exists to make.

    Stage 8 reads an unmarked argument as the subject when the sentence writes no
    agentive, which ADR-010 records as a measured limitation: 76% of agentive
    markers in the reference corpus are the fused ``ས``/``ར`` Stage 6 will not
    split, so they are invisible. The verb's attested frame decides instead.
    """
    analyzer = analyzer_with((("ཀློག",), TRANSITIVE))
    graph = analyzer.analyze(build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres")))
    assert role_of(graph, "ཞིང") == (SemanticRole.PATIENT, RoleEvidence.LEXICON)


def test_an_intransitive_frame_makes_the_absolutive_a_theme() -> None:
    analyzer = analyzer_with((("འགྲོ",), INTRANSITIVE))
    graph = analyzer.analyze(build_tree(("ཞིང", "n.count"), ("འགྲོ", "v.pres")))
    assert role_of(graph, "ཞིང") == (SemanticRole.THEME, RoleEvidence.LEXICON)


def test_a_silent_lexicon_leaves_stage_8_s_reading_untouched() -> None:
    """Where the lexicon says nothing, the structural reading is carried through
    and labelled as structural rather than presented as a lexical finding."""
    analyzer = analyzer_with((("ཀློག",), SILENT))
    graph = analyzer.analyze(build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres")))
    assert role_of(graph, "ཞིང") == (SemanticRole.THEME, RoleEvidence.STRUCTURE)


def test_an_unknown_verb_leaves_stage_8_s_reading_untouched() -> None:
    analyzer = analyzer_with((("ཟzz",), SILENT))
    graph = analyzer.analyze(build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres")))
    assert role_of(graph, "ཞིང") == (SemanticRole.THEME, RoleEvidence.STRUCTURE)


def test_an_explicit_agentive_makes_the_other_argument_a_patient() -> None:
    """With an agentive written, Stage 8 already reads the absolutive as arg2."""
    analyzer = analyzer_with((("ཀློག",), SILENT))
    graph = analyzer.analyze(
        build_tree(
            ("ཁོ", "p.pers"),
            ("ཡིས", "case.agn"),
            ("ཞིང", "n.count"),
            ("ཀློག", "v.pres"),
        )
    )
    assert role_of(graph, "ཁོ") == (SemanticRole.AGENT, RoleEvidence.CASE)
    assert role_of(graph, "ཞིང") == (SemanticRole.PATIENT, RoleEvidence.STRUCTURE)


def test_an_intransitive_frame_overrules_stage_8_s_object_reading() -> None:
    """The correction runs both ways: a verb the lexicon reports as intransitive
    cannot have taken an object, whatever else the sentence contains."""
    analyzer = analyzer_with((("འགྲོ",), INTRANSITIVE))
    graph = analyzer.analyze(
        build_tree(
            ("ཁོ", "p.pers"),
            ("ཡིས", "case.agn"),
            ("ཞིང", "n.count"),
            ("འགྲོ", "v.pres"),
        )
    )
    assert role_of(graph, "ཞིང") == (SemanticRole.THEME, RoleEvidence.LEXICON)


def test_a_transitive_frame_confirms_stage_8_s_object_reading() -> None:
    analyzer = analyzer_with((("ཀློག",), TRANSITIVE))
    graph = analyzer.analyze(
        build_tree(
            ("ཁོ", "p.pers"),
            ("ཡིས", "case.agn"),
            ("ཞིང", "n.count"),
            ("ཀློག", "v.pres"),
        )
    )
    assert role_of(graph, "ཞིང") == (SemanticRole.PATIENT, RoleEvidence.LEXICON)


# -- Role assignment: structure ------------------------------------------------
@pytest.mark.parametrize(
    ("surface", "tag"),
    [("ཆེན", "adj"), ("གསུམ", "num.card"), ("ད", "adv.temp")],
)
def test_modifiers_are_labelled_as_such(
    semantic_analyzer: TibetanSemanticAnalyzer, surface: str, tag: str
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཡུལ", "n.count"), (surface, tag), ("འགྲོ", "v.pres"))
    )
    assert role_of(graph, surface) == (SemanticRole.MODIFIER, RoleEvidence.STRUCTURE)


def test_a_determiner_anchored_as_a_name_is_still_a_modifier(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Determiners are not nodes on their own, but an anchored run always is."""
    tree = build_tree(("ཡུལ", "n.count"), ("དེ", "d.dem"), ("འགྲོ", "v.pres"))
    graph = semantic_analyzer.analyze(tree, entities=entity_over(tree, 1, 2))
    assert role_of(graph, "དེ") == (SemanticRole.MODIFIER, RoleEvidence.STRUCTURE)


def test_a_node_whose_head_is_grammatical_attaches_to_the_concept_above_it(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Governors are looked for up the tree, not only one step above.

    Stage 8 attaches a modifier to the nearest nominal on its left, and that
    nominal may be a determiner -- which is grammatical and therefore not a node
    here. Stopping at it would leave the modifier unattached, so the search walks
    on until it reaches something that is a node.
    """
    tree = build_tree(("དེ", "d.dem"), ("ཆེན", "adj"), ("འགྲོ", "v.pres"))
    assert tree.nodes[1].head == 0, "the adjective attaches to the determiner"
    graph = semantic_analyzer.analyze(tree)
    assert "དེ" not in {node.text for node in graph.nodes}
    edge = graph.governor_of(graph.nodes[0].index)
    assert edge is not None
    assert graph.nodes[edge.source].text == "འགྲོ"
    assert edge.role is SemanticRole.MODIFIER


def test_a_subordinate_clause_is_labelled_as_such(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("བྱས", "v.past"), ("ཞིང", "n.count"), ("འགྲོ", "v.pres"))
    )
    assert role_of(graph, "བྱས") == (
        SemanticRole.SUBORDINATE,
        RoleEvidence.STRUCTURE,
    )


def test_material_no_rule_attaches_is_recorded_as_unspecified(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Stage 8 records it as ``dep``; this stage must not invent a role for it."""
    tree = build_tree(("ཞིང", "n.count"), ("ཨ", "interj"), ("འགྲོ", "v.pres"))
    graph = semantic_analyzer.analyze(tree, entities=entity_over(tree, 1, 2))
    assert role_of(graph, "ཨ") == (SemanticRole.UNSPECIFIED, RoleEvidence.STRUCTURE)
    assert graph.num_unspecified == 1


def test_an_oblique_whose_particle_cannot_be_recovered_is_unspecified(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """``case.nare`` is a quotative, not an argument case, so nothing types it."""
    graph = semantic_analyzer.analyze(
        build_tree(("ཡུལ", "n.count"), ("ན་རེ", "case.nare"), ("འགྲོ", "v.pres"))
    )
    assert role_of(graph, "ཡུལ") == (
        SemanticRole.UNSPECIFIED,
        RoleEvidence.STRUCTURE,
    )


def test_the_sentence_head_has_no_governor(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    )
    assert graph.governor_of(graph.predicates[0].index) is None


# -- Anchors from Stages 9 and 10 ---------------------------------------------
def test_a_name_becomes_one_concept_rather_than_several(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Why Figure 5 runs Stage 9 before Stage 11.

    Stage 8 works one morpheme at a time, so it attaches every syllable of a name
    to the verb as a separate argument. Without Stage 9 the graph would report a
    three-participant event where the sentence has one participant.
    """
    tree = build_tree(
        ("འཛམ", "n.prop"),
        ("བུ", "n.prop"),
        ("གླིང", "n.prop"),
        ("འགྲོ", "v.pres"),
    )
    plain = semantic_analyzer.analyze(tree)
    merged = semantic_analyzer.analyze(tree, entities=entity_over(tree, 0, 3))

    assert plain.num_nodes == 4
    assert merged.num_nodes == 2
    assert merged.nodes[0].text == "འཛམ་བུ་གླིང"
    assert merged.nodes[0].num_morphemes == 3
    assert merged.nodes[0].is_named_entity is True
    assert merged.named_entities == (merged.nodes[0],)


def test_a_technical_term_becomes_one_concept(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    tree = build_tree(("དགྲ", "n.count"), ("བཅོམ", "n.count"), ("འགྲོ", "v.pres"))
    graph = semantic_analyzer.analyze(tree, terms=term_over(tree, 0, 2))
    assert graph.nodes[0].text == "དགྲ་བཅོམ"
    assert graph.nodes[0].is_terminology is True
    assert graph.terminology == (graph.nodes[0],)


def test_a_name_and_a_term_over_the_same_run_are_both_attached(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    tree = build_tree(("དགྲ", "n.prop"), ("བཅོམ", "n.prop"), ("འགྲོ", "v.pres"))
    graph = semantic_analyzer.analyze(
        tree, entities=entity_over(tree, 0, 2), terms=term_over(tree, 0, 2)
    )
    assert graph.nodes[0].is_named_entity is True
    assert graph.nodes[0].is_terminology is True


def test_the_longer_anchor_wins_when_two_overlap(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """The longer run is the more specific identification."""
    tree = build_tree(
        ("དགྲ", "n.prop"), ("བཅོམ", "n.prop"), ("པ", "n.prop"), ("འགྲོ", "v.pres")
    )
    graph = semantic_analyzer.analyze(
        tree, entities=entity_over(tree, 0, 2), terms=term_over(tree, 0, 3)
    )
    assert graph.nodes[0].num_morphemes == 3
    assert graph.nodes[0].is_terminology is True
    assert graph.nodes[0].is_named_entity is False


def test_the_name_wins_when_two_anchors_are_the_same_length(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Figure 5 runs Stage 9 before Stage 10, so the name is the earlier claim."""
    tree = build_tree(
        ("དགྲ", "n.prop"), ("བཅོམ", "n.prop"), ("པ", "n.prop"), ("འགྲོ", "v.pres")
    )
    graph = semantic_analyzer.analyze(
        tree, entities=entity_over(tree, 0, 2), terms=term_over(tree, 1, 3)
    )
    assert graph.nodes[0].num_morphemes == 2
    assert graph.nodes[0].is_named_entity is True


def test_an_anchor_at_the_end_of_the_sentence_is_grouped(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    tree = build_tree(("འགྲོ", "v.pres"), ("འཛམ", "n.prop"), ("གླིང", "n.prop"))
    graph = semantic_analyzer.analyze(tree, entities=entity_over(tree, 1, 3))
    assert graph.nodes[-1].text == "འཛམ་གླིང"


def test_anchored_syllables_keep_the_tsheg_between_them(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """The text is the source slice, not the morphemes joined.

    A joined string would not appear in the document, and the add-in maps
    suggestions back onto the user's own text by offset.
    """
    tree = build_tree(("འཛམ", "n.prop"), ("གླིང", "n.prop"), ("འགྲོ", "v.pres"))
    graph = semantic_analyzer.analyze(tree, entities=entity_over(tree, 0, 2))
    node = graph.nodes[0]
    assert node.text == tree.source[node.span.char_start : node.span.char_end]
    assert TSHEG in node.text


# -- Intent --------------------------------------------------------------------
@pytest.mark.parametrize("tag", ["cv.ques", "p.interrog"])
def test_interrogative_morphology_marks_a_question(
    semantic_analyzer: TibetanSemanticAnalyzer, tag: str
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("འགྲོ", "v.pres"), ("ཨེ", tag))
    )
    assert graph.intent.mood is SentenceMood.INTERROGATIVE
    assert graph.intent.evidence == (tag,)


@pytest.mark.parametrize("tag", ["v.imp", "cv.imp", "n.v.imp"])
def test_imperative_morphology_marks_a_command(
    semantic_analyzer: TibetanSemanticAnalyzer, tag: str
) -> None:
    graph = semantic_analyzer.analyze(build_tree(("ཞིང", "n.count"), ("སོང", tag)))
    assert graph.intent.mood is SentenceMood.IMPERATIVE
    assert graph.intent.evidence == (tag,)


def test_an_unmarked_sentence_is_declarative(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("འགྲོ", "v.pres"))
    )
    assert graph.intent.mood is SentenceMood.DECLARATIVE
    assert graph.intent.is_marked is False


def test_a_question_outranks_an_imperative_stem(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """The question particle scopes over the clause; an imperative stem is a
    property of the verb inside it."""
    graph = semantic_analyzer.analyze(
        build_tree(("སོང", "v.imp"), ("ཨེ", "cv.ques"))
    )
    assert graph.intent.mood is SentenceMood.INTERROGATIVE


@pytest.mark.parametrize("tag", ["neg", "v.neg", "v.cop.neg", "n.v.neg"])
def test_negation_is_reported_as_polarity(
    semantic_analyzer: TibetanSemanticAnalyzer, tag: str
) -> None:
    graph = semantic_analyzer.analyze(build_tree(("ཞིང", "n.count"), ("མིན", tag)))
    assert graph.intent.polarity is Polarity.NEGATIVE
    assert tag in graph.intent.evidence


@pytest.mark.parametrize("tag", ["cl.quot", "case.nare"])
def test_a_quotative_marks_reported_speech(
    semantic_analyzer: TibetanSemanticAnalyzer, tag: str
) -> None:
    """A grammar checker should leave a quotation as the author wrote it."""
    graph = semantic_analyzer.analyze(
        build_tree(("ཞིང", "n.count"), ("ཞེས", tag), ("འགྲོ", "v.pres"))
    )
    assert graph.intent.is_reported is True
    assert tag in graph.intent.evidence


def test_intent_evidence_is_deduplicated_and_kept_in_surface_order(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(
            ("མ", "neg"),
            ("ཨེ", "cv.ques"),
            ("མ", "neg"),
            ("འགྲོ", "v.pres"),
        )
    )
    assert graph.intent.evidence == ("neg", "cv.ques")


def test_intent_is_reported_even_when_no_node_survives(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """Mood is a property of the sentence, not of its concepts."""
    graph = semantic_analyzer.analyze(build_tree(("མ", "neg"), ("།", "punc")))
    assert graph.is_empty
    assert graph.intent.polarity is Polarity.NEGATIVE


# -- Structural guarantees -----------------------------------------------------
def test_every_node_has_at_most_one_governor(
    semantic_analyzer: TibetanSemanticAnalyzer, corpus_sentences: list[str]
) -> None:
    """The contraction produces a forest, which is what a consumer walks."""
    tree = build_tree(
        ("ཞིང", "n.count"),
        ("གི", "case.gen"),
        ("ཡུལ", "n.count"),
        ("ཆེན", "adj"),
        ("ལ", "case.all"),
        ("འགྲོ", "v.pres"),
    )
    graph = semantic_analyzer.analyze(tree)
    targets = [edge.target for edge in graph.edges]
    assert len(targets) == len(set(targets))
    assert corpus_sentences


def test_nodes_are_returned_in_surface_order(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(
        build_tree(
            ("ཞིང", "n.count"),
            ("ཡུལ", "n.count"),
            ("ཆེན", "adj"),
            ("འགྲོ", "v.pres"),
        )
    )
    starts = [node.span.char_start for node in graph.nodes]
    assert starts == sorted(starts)
    assert [node.index for node in graph.nodes] == list(range(graph.num_nodes))


def test_the_analysis_is_deterministic(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    tree = build_tree(
        ("ཞིང", "n.count"),
        ("གིས", "case.agn"),
        ("ཡུལ", "n.count"),
        ("ཀློག", "v.pres"),
    )
    first = semantic_analyzer.analyze(tree, entities=entity_over(tree, 2, 3))
    second = semantic_analyzer.analyze(tree, entities=entity_over(tree, 2, 3))
    assert first == second


def test_the_analyzer_holds_no_state_between_calls(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """One instance analyses many sentences; a leak between them would corrupt both."""
    long_tree = build_tree(*[("ཞིང", "n.count")] * 6, ("འགྲོ", "v.pres"))
    short_tree = build_tree(("ཡུལ", "n.count"), ("འགྲོ", "v.pres"))
    semantic_analyzer.analyze(long_tree)
    assert semantic_analyzer.analyze(short_tree).num_nodes == 2


# -- The case-tag table: correctness of a performance optimisation -------------
def naive_case_tag_after(tree: DependencyTree, index: int) -> str | None:
    """The obvious forward scan the table replaced, kept as a test oracle.

    Readable, obviously correct, and quadratic when many units are scanned. The
    table in the analyser must agree with it everywhere.
    """
    for candidate in range(index, len(tree.nodes)):
        relation = tree.nodes[candidate].relation
        if relation is DependencyRelation.CASE:
            return tree.nodes[candidate].tag
        if relation not in PHRASE_INTERNAL:
            return None
    return None


@pytest.mark.parametrize(
    "shape",
    [
        [("ཡུལ", "n.count"), ("ན", "case.loc"), ("འགྲོ", "v.pres")],
        [("ཡུལ", "n.count"), ("ཆེན", "adj"), ("ན", "case.loc"), ("འགྲོ", "v.pres")],
        [("ཡུལ", "n.count"), ("ཞིང", "n.count"), ("ན", "case.loc"), ("འགྲོ", "v.pres")],
        [("ན", "case.loc"), ("འགྲོ", "v.pres")],
        [("འགྲོ", "v.pres"), ("ཡུལ", "n.count")],
        [("ཡུལ", "n.count"), ("གསུམ", "num.card"), ("དེ", "d.dem"), ("ལ", "case.all")],
        [("།", "punc")],
    ],
)
def test_the_case_tag_table_agrees_with_a_naive_scan(
    shape: list[tuple[str, str]],
) -> None:
    """Equivalence, not timing, is what pins this optimisation.

    ``_case_tags`` replaced a per-node forward scan that was quadratic on a long
    run of modifiers -- measured at 968 ms for 3,200 consecutive adjectives,
    against 84 ms for the table. Speed is reported in the engineering record;
    what a test can assert without becoming flaky is that the two agree.
    """
    tree = build_tree(*shape)
    table = _case_tags(tree)
    assert len(table) == tree.num_nodes + 1
    for index in range(tree.num_nodes + 1):
        assert table[index] == naive_case_tag_after(tree, index), index


def test_the_case_tag_table_agrees_with_a_naive_scan_on_the_corpus(
    corpus_sentences: list[str],
) -> None:
    """The same equivalence, over real classical Tibetan."""
    morphology = TibetanMorphologicalAnalyzer()
    tagger = HmmPosTagger()
    parser = TibetanDependencyParser()
    checked = 0
    for sentence in corpus_sentences:
        tree = parser.parse(tagger.tag(morphology.analyze(sentence)))
        table = _case_tags(tree)
        for index in range(tree.num_nodes + 1):
            assert table[index] == naive_case_tag_after(tree, index)
            checked += 1
    assert checked > 1_000


# -- Pathological input --------------------------------------------------------
@pytest.mark.parametrize(
    ("label", "shape"),
    [
        ("modifier run", [("ཆེན", "adj")] * 800 + [("འགྲོ", "v.pres")]),
        ("nominal run", [("ཞིང", "n.count")] * 800 + [("འགྲོ", "v.pres")]),
        ("punctuation run", [("།", "punc")] * 800 + [("འགྲོ", "v.pres")]),
        ("particle run", [("གི", "case.gen")] * 800 + [("འགྲོ", "v.pres")]),
        (
            "genitive chain",
            [x for _ in range(400) for x in (("ཞིང", "n.count"), ("གི", "case.gen"))]
            + [("འགྲོ", "v.pres")],
        ),
    ],
)
def test_a_pathological_sentence_still_produces_a_well_formed_graph(
    semantic_analyzer: TibetanSemanticAnalyzer,
    label: str,
    shape: list[tuple[str, str]],
) -> None:
    """A document must not be able to make the daemon produce a broken graph.

    The model validators run on every result, so reaching this assertion at all
    means the graph is ordered, span-accurate and acyclic.
    """
    graph = semantic_analyzer.analyze(build_tree(*shape))
    targets = [edge.target for edge in graph.edges]
    assert len(targets) == len(set(targets)), label


def test_a_single_morpheme_sentence_is_analysed(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    graph = semantic_analyzer.analyze(build_tree(("འགྲོ", "v.pres")))
    assert graph.num_nodes == 1
    assert graph.num_edges == 0
    assert graph.predicates[0].text == "འགྲོ"


def test_an_entity_covering_the_whole_sentence_becomes_one_node(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """The unit is then the entire tree, so it has no governor to find."""
    tree = build_tree(("འཛམ", "n.prop"), ("བུ", "n.prop"), ("གླིང", "n.prop"))
    graph = semantic_analyzer.analyze(tree, entities=entity_over(tree, 0, 3))
    assert graph.num_nodes == 1
    assert graph.num_edges == 0
    assert graph.nodes[0].text == tree.source[: graph.nodes[0].span.char_end]


def test_spans_are_preserved_verbatim_from_stage_6(
    semantic_analyzer: TibetanSemanticAnalyzer,
) -> None:
    """The invariant every stage from 6 onward maintains."""
    tree = build_tree(
        ("བཀྲ", "n.count"), ("ཤིས", "n.count"), ("བདེ", "adj"), ("འགྲོ", "v.pres")
    )
    graph = semantic_analyzer.analyze(tree)
    for node in graph.nodes:
        assert tree.source[node.span.char_start : node.span.char_end] == node.text
        assert node.span.byte_length == len(node.text.encode("utf-8"))
