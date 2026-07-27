"""Invariants of the Stage 11 value objects.

These models are what crosses the boundary into the Plugin Runtime -- the Level-1
Data Flow Diagram labels the edge "Parsed Tokens / Graph" -- so their guarantees
are a contract, not an implementation detail. Every rule asserted here is one a
consumer is entitled to rely on without re-checking: spans that really select
their own text, nodes in surface order, and a graph that cannot cycle.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.morphology import Morpheme, MorphemeKind
from teea.nlp.ner import EntityEvidence, NamedEntity
from teea.nlp.postagging import TaggedMorpheme, coarse_category
from teea.nlp.semantics import (
    Polarity,
    RoleEvidence,
    SemanticEdge,
    SemanticGraph,
    SemanticNode,
    SemanticNodeKind,
    SemanticRole,
    SentenceIntent,
    SentenceMood,
)
from teea.nlp.terminology import RecognizedTerm
from teea.persistence import ArgumentSlot, TermSource, Transitivity, VerbFrame

TSHEG = "་"

TRANSITIVE = VerbFrame(lemma="ཀློག་", frame="Erg-Abs", slots=frozenset({ArgumentSlot.ERGATIVE}))
INTRANSITIVE = VerbFrame(lemma="ཀེར་", frame="Abs-Obl", slots=frozenset({ArgumentSlot.ABSOLUTIVE}))
SILENT = VerbFrame(lemma="ཀླན་")
OTHER_TRANSITIVE = VerbFrame(lemma="ཉོ་", transitivity=Transitivity.TRANSITIVE)


# -- Helpers ------------------------------------------------------------------
def build_morphemes(*pairs: tuple[str, str]) -> tuple[str, tuple[TaggedMorpheme, ...]]:
    """Return ``(source, morphemes)`` for tsheg-separated ``(surface, tag)`` pairs."""
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
    return source, tuple(morphemes)


def span_of(run: tuple[TaggedMorpheme, ...]) -> TextSpan:
    """Return the span covering a whole run of morphemes."""
    return TextSpan(
        char_start=run[0].span.char_start,
        char_end=run[-1].span.char_end,
        byte_start=run[0].span.byte_start,
        byte_end=run[-1].span.byte_end,
    )


def make_node(
    source: str,
    morphemes: tuple[TaggedMorpheme, ...],
    *,
    index: int = 0,
    start_index: int = 0,
    head_index: int | None = None,
    kind: SemanticNodeKind = SemanticNodeKind.CONCEPT,
    **extra: object,
) -> SemanticNode:
    """Build a node covering ``morphemes``, filling in the derivable fields."""
    span = span_of(morphemes)
    return SemanticNode(
        index=index,
        kind=kind,
        text=source[span.char_start : span.char_end],
        span=span,
        start_index=start_index,
        end_index=start_index + len(morphemes),
        head_index=start_index if head_index is None else head_index,
        morphemes=morphemes,
        **extra,
    )


def plain_edge(source: int, target: int) -> SemanticEdge:
    """An untyped structural edge, for tests about graph shape rather than roles."""
    return SemanticEdge(
        source=source,
        target=target,
        role=SemanticRole.THEME,
        evidence=RoleEvidence.STRUCTURE,
    )


# -- SemanticNode --------------------------------------------------------------
def test_a_node_reports_its_own_shape() -> None:
    source, morphemes = build_morphemes(("བཀྲ", "n.count"), ("ཤིས", "n.count"))
    node = make_node(source, morphemes)
    assert node.num_morphemes == 2
    assert node.text == source[: node.span.char_end]
    assert node.is_predicate is False
    assert node.head is morphemes[0]
    assert node.lemma is None
    assert node.is_transitive is None
    assert node.is_named_entity is False
    assert node.is_terminology is False


def test_a_predicate_node_says_so() -> None:
    source, morphemes = build_morphemes(
        ("ཀློག", "v.pres"),
    )
    node = make_node(source, morphemes, kind=SemanticNodeKind.PREDICATE)
    assert node.is_predicate is True


def test_the_head_is_addressed_relative_to_the_run() -> None:
    """``head_index`` is a Stage 8 index, so it must be offset before use."""
    source, morphemes = build_morphemes(("འཛམ", "n.prop"), ("བུ", "n.prop"), ("གླིང", "n.prop"))
    node = make_node(source, morphemes, start_index=5, head_index=7)
    assert node.head is morphemes[2]


def test_an_empty_node_is_rejected() -> None:
    source, morphemes = build_morphemes(
        ("ཀློག", "v.pres"),
    )
    with pytest.raises(ValidationError, match="must not be empty"):
        SemanticNode(
            index=0,
            kind=SemanticNodeKind.CONCEPT,
            text="",
            span=span_of(morphemes),
            start_index=0,
            end_index=1,
            head_index=0,
            morphemes=morphemes,
        )
    assert source


def test_a_node_covering_no_morpheme_is_rejected() -> None:
    source, morphemes = build_morphemes(
        ("ཀློག", "v.pres"),
    )
    with pytest.raises(ValidationError, match="end_index must be greater"):
        SemanticNode(
            index=0,
            kind=SemanticNodeKind.CONCEPT,
            text=source[:4],
            span=span_of(morphemes),
            start_index=2,
            end_index=2,
            head_index=2,
            morphemes=morphemes,
        )


def test_a_morpheme_count_that_disagrees_with_the_range_is_rejected() -> None:
    source, morphemes = build_morphemes(
        ("ཀློག", "v.pres"),
    )
    with pytest.raises(ValidationError, match="expected 2 morphemes"):
        SemanticNode(
            index=0,
            kind=SemanticNodeKind.CONCEPT,
            text=source[:4],
            span=span_of(morphemes),
            start_index=0,
            end_index=2,
            head_index=0,
            morphemes=morphemes,
        )


@pytest.mark.parametrize("head_index", [-1, 1])
def test_a_head_outside_the_run_is_rejected(head_index: int) -> None:
    """The head is the member the node attaches through, so it must be a member."""
    source, morphemes = build_morphemes(
        ("ཀློག", "v.pres"),
    )
    with pytest.raises(ValidationError):
        SemanticNode(
            index=0,
            kind=SemanticNodeKind.CONCEPT,
            text=source[:4],
            span=span_of(morphemes),
            start_index=0,
            end_index=1,
            head_index=head_index,
            morphemes=morphemes,
        )


def test_a_span_that_does_not_start_at_the_first_morpheme_is_rejected() -> None:
    source, morphemes = build_morphemes(("བཀྲ", "n.count"), ("ཤིས", "n.count"))
    span = span_of(morphemes)
    with pytest.raises(ValidationError, match="must start at the first morpheme"):
        SemanticNode(
            index=0,
            kind=SemanticNodeKind.CONCEPT,
            text=source[1 : span.char_end],
            span=TextSpan(
                char_start=1,
                char_end=span.char_end,
                byte_start=span.byte_start,
                byte_end=span.byte_end,
            ),
            start_index=0,
            end_index=2,
            head_index=0,
            morphemes=morphemes,
        )


def test_a_span_that_does_not_end_at_the_last_morpheme_is_rejected() -> None:
    source, morphemes = build_morphemes(("བཀྲ", "n.count"), ("ཤིས", "n.count"))
    span = span_of(morphemes)
    with pytest.raises(ValidationError, match="must end at the last morpheme"):
        SemanticNode(
            index=0,
            kind=SemanticNodeKind.CONCEPT,
            text=source[: span.char_end - 1],
            span=TextSpan(
                char_start=span.char_start,
                char_end=span.char_end - 1,
                byte_start=span.byte_start,
                byte_end=span.byte_end,
            ),
            start_index=0,
            end_index=2,
            head_index=0,
            morphemes=morphemes,
        )


# -- Lexical evidence on a node ------------------------------------------------
def test_one_attested_entry_gives_a_lemma_and_a_transitivity() -> None:
    source, morphemes = build_morphemes(
        ("ཀློག", "v.pres"),
    )
    node = make_node(source, morphemes, frames=(TRANSITIVE,))
    assert node.lemma == "ཀློག་"
    assert node.is_transitive is True
    assert node.is_lexically_ambiguous is False


def test_entries_agreeing_on_a_lemma_still_give_a_lemma() -> None:
    """Two senses of one headword are still one predicate identity."""
    source, morphemes = build_morphemes(
        ("ཀློག", "v.pres"),
    )
    sibling = VerbFrame(lemma="ཀློག་", transitivity=Transitivity.TRANSITIVE)
    node = make_node(source, morphemes, frames=(TRANSITIVE, sibling))
    assert node.lemma == "ཀློག་"
    assert node.is_lexically_ambiguous is False
    assert node.is_transitive is True


def test_entries_disagreeing_about_the_lemma_report_no_lemma() -> None:
    """Reporting one of several candidates would be a guess, not a finding."""
    source, morphemes = build_morphemes(
        ("ཟེར", "v.pres"),
    )
    node = make_node(source, morphemes, frames=(TRANSITIVE, INTRANSITIVE))
    assert node.lemma is None
    assert node.is_lexically_ambiguous is True


def test_entries_disagreeing_about_transitivity_decide_nothing() -> None:
    source, morphemes = build_morphemes(
        ("ཟེར", "v.pres"),
    )
    node = make_node(source, morphemes, frames=(TRANSITIVE, INTRANSITIVE))
    assert node.is_transitive is None


def test_a_silent_entry_does_not_outvote_an_informative_one() -> None:
    """Silence is not disagreement; discarding the only evidence would be worse."""
    source, morphemes = build_morphemes(
        ("ཀློག", "v.pres"),
    )
    node = make_node(source, morphemes, frames=(TRANSITIVE, SILENT))
    assert node.is_transitive is True


def test_two_informative_entries_that_agree_decide() -> None:
    source, morphemes = build_morphemes(
        ("ཉོས", "v.past"),
    )
    node = make_node(source, morphemes, frames=(TRANSITIVE, OTHER_TRANSITIVE))
    assert node.is_transitive is True
    assert node.lemma is None


def test_no_entries_decide_nothing() -> None:
    source, morphemes = build_morphemes(
        ("ཞིང", "n.count"),
    )
    node = make_node(source, morphemes)
    assert node.frames == ()
    assert node.lemma is None
    assert node.is_transitive is None
    assert node.is_lexically_ambiguous is False


# -- Anchors from Stages 9 and 10 ---------------------------------------------
def test_a_node_can_carry_the_name_stage_9_found() -> None:
    source, morphemes = build_morphemes(("འཛམ", "n.prop"), ("གླིང", "n.prop"))
    entity = NamedEntity(
        text=source[: span_of(morphemes).char_end],
        span=span_of(morphemes),
        start_index=0,
        end_index=2,
        evidence=EntityEvidence.GAZETTEER,
        morphemes=morphemes,
    )
    node = make_node(source, morphemes, entity=entity)
    assert node.is_named_entity is True
    assert node.entity is entity


def test_a_node_can_carry_the_term_stage_10_found() -> None:
    source, morphemes = build_morphemes(("དགྲ", "n.count"), ("བཅོམ", "n.count"))
    term = RecognizedTerm(
        text=source[: span_of(morphemes).char_end],
        span=span_of(morphemes),
        start_index=0,
        end_index=2,
        source=TermSource.GLOSSARY,
        morphemes=morphemes,
    )
    node = make_node(source, morphemes, term=term)
    assert node.is_terminology is True
    assert node.term is term


# -- SemanticEdge --------------------------------------------------------------
def test_an_edge_records_its_role_and_its_evidence() -> None:
    edge = SemanticEdge(source=1, target=0, role=SemanticRole.AGENT, evidence=RoleEvidence.CASE)
    assert edge.role is SemanticRole.AGENT
    assert edge.evidence is RoleEvidence.CASE


def test_a_node_cannot_govern_itself() -> None:
    with pytest.raises(ValidationError, match="cannot govern itself"):
        SemanticEdge(
            source=2,
            target=2,
            role=SemanticRole.THEME,
            evidence=RoleEvidence.STRUCTURE,
        )


def test_an_edge_is_immutable() -> None:
    edge = SemanticEdge(source=1, target=0, role=SemanticRole.AGENT, evidence=RoleEvidence.CASE)
    with pytest.raises(ValidationError):
        edge.role = SemanticRole.THEME  # type: ignore[misc]


# -- SentenceIntent ------------------------------------------------------------
def test_the_unmarked_intent_is_an_affirmative_statement() -> None:
    intent = SentenceIntent()
    assert intent.mood is SentenceMood.DECLARATIVE
    assert intent.polarity is Polarity.AFFIRMATIVE
    assert intent.is_reported is False
    assert intent.is_marked is False


def test_an_intent_backed_by_evidence_says_so() -> None:
    intent = SentenceIntent(mood=SentenceMood.INTERROGATIVE, evidence=("cv.ques",))
    assert intent.is_marked is True


# -- SemanticGraph -------------------------------------------------------------
def two_node_graph() -> SemanticGraph:
    """A minimal graph: one predicate governing one concept."""
    source, morphemes = build_morphemes(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    return SemanticGraph(
        source=source,
        nodes=(
            make_node(source, morphemes[:1], index=0, start_index=0),
            make_node(
                source,
                morphemes[1:],
                index=1,
                start_index=1,
                head_index=1,
                kind=SemanticNodeKind.PREDICATE,
                frames=(TRANSITIVE,),
            ),
        ),
        edges=(
            SemanticEdge(
                source=1,
                target=0,
                role=SemanticRole.PATIENT,
                evidence=RoleEvidence.LEXICON,
            ),
        ),
    )


def test_an_empty_graph_is_valid_and_reports_itself_as_empty() -> None:
    graph = SemanticGraph(source="")
    assert graph.is_empty is True
    assert len(graph) == graph.num_nodes == graph.num_edges == 0
    assert graph.predicates == graph.concepts == ()
    assert graph.roles == ()
    assert graph.num_unspecified == 0
    assert graph.node_at_char(0) is None
    assert graph.governor_of(0) is None
    assert graph.intent.mood is SentenceMood.DECLARATIVE


def test_a_graph_exposes_its_content() -> None:
    graph = two_node_graph()
    assert len(graph) == 2
    assert graph.num_edges == 1
    assert graph.is_empty is False
    assert [n.index for n in graph.predicates] == [1]
    assert [n.index for n in graph.concepts] == [0]
    assert graph.roles == (SemanticRole.PATIENT,)
    assert graph.num_unspecified == 0
    assert graph.named_entities == ()
    assert graph.terminology == ()


def test_a_graph_answers_the_queries_a_consumer_needs() -> None:
    graph = two_node_graph()
    assert graph.of_role(SemanticRole.PATIENT) == graph.edges
    assert graph.of_role(SemanticRole.AGENT) == ()
    assert graph.of_evidence(RoleEvidence.LEXICON) == graph.edges
    assert graph.of_evidence(RoleEvidence.CASE) == ()
    assert graph.arguments_of(1) == graph.edges
    assert graph.arguments_of(0) == ()
    assert graph.governor_of(0) is graph.edges[0]
    assert graph.governor_of(1) is None


def test_an_offset_maps_back_to_the_concept_that_covers_it() -> None:
    """The primitive the add-in needs to place a suggestion."""
    graph = two_node_graph()
    covering = graph.node_at_char(0)
    assert covering is not None
    assert covering.index == 0
    # The tsheg between the two morphemes belongs to neither.
    assert graph.node_at_char(graph.nodes[0].span.char_end) is None
    assert graph.node_at_char(10_000) is None


def test_unspecified_edges_are_counted() -> None:
    """The honest quality signal: roles no evidence could type."""
    graph = two_node_graph()
    unresolved = graph.model_copy(
        update={
            "edges": (
                SemanticEdge(
                    source=1,
                    target=0,
                    role=SemanticRole.UNSPECIFIED,
                    evidence=RoleEvidence.STRUCTURE,
                ),
            )
        }
    )
    assert unresolved.num_unspecified == 1


def test_a_node_carrying_the_wrong_index_is_rejected() -> None:
    graph = two_node_graph()
    with pytest.raises(ValidationError, match="carries index"):
        SemanticGraph(
            source=graph.source,
            nodes=(graph.nodes[1], graph.nodes[0]),
        )


def test_overlapping_nodes_are_rejected() -> None:
    source, morphemes = build_morphemes(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    with pytest.raises(ValidationError, match="must not overlap"):
        SemanticGraph(
            source=source,
            nodes=(
                make_node(source, morphemes, index=0, start_index=0),
                make_node(source, morphemes[1:], index=1, start_index=1, head_index=1),
            ),
        )


def test_a_span_beyond_the_source_is_rejected() -> None:
    source, morphemes = build_morphemes(
        ("ཞིང", "n.count"),
    )
    with pytest.raises(ValidationError, match="exceeds the source text"):
        SemanticGraph(source="", nodes=(make_node(source, morphemes),))


def test_a_span_that_selects_different_text_is_rejected() -> None:
    """The invariant every stage in this pipeline maintains."""
    source, morphemes = build_morphemes(
        ("ཞིང", "n.count"),
    )
    with pytest.raises(ValidationError, match="does not select its own text"):
        SemanticGraph(source="x" * len(source), nodes=(make_node(source, morphemes),))


def test_an_edge_referring_to_a_missing_node_is_rejected() -> None:
    graph = two_node_graph()
    with pytest.raises(ValidationError, match="out of range"):
        SemanticGraph(
            source=graph.source,
            nodes=graph.nodes,
            edges=(
                SemanticEdge(
                    source=0,
                    target=9,
                    role=SemanticRole.THEME,
                    evidence=RoleEvidence.STRUCTURE,
                ),
            ),
        )


def test_an_edge_leaving_a_missing_node_is_rejected() -> None:
    graph = two_node_graph()
    with pytest.raises(ValidationError, match="out of range"):
        SemanticGraph(
            source=graph.source,
            nodes=graph.nodes,
            edges=(
                SemanticEdge(
                    source=9,
                    target=0,
                    role=SemanticRole.THEME,
                    evidence=RoleEvidence.STRUCTURE,
                ),
            ),
        )


def test_a_duplicate_edge_is_rejected() -> None:
    graph = two_node_graph()
    with pytest.raises(ValidationError, match="duplicate edge"):
        SemanticGraph(source=graph.source, nodes=graph.nodes, edges=graph.edges + graph.edges)


def test_a_cycle_is_rejected() -> None:
    """Consumers walk this graph, so it must terminate without a visited set."""
    graph = two_node_graph()
    with pytest.raises(ValidationError, match="cycle detected"):
        SemanticGraph(
            source=graph.source,
            nodes=graph.nodes,
            edges=(
                SemanticEdge(
                    source=0,
                    target=1,
                    role=SemanticRole.THEME,
                    evidence=RoleEvidence.STRUCTURE,
                ),
                SemanticEdge(
                    source=1,
                    target=0,
                    role=SemanticRole.THEME,
                    evidence=RoleEvidence.STRUCTURE,
                ),
            ),
        )


def test_a_diamond_is_not_a_cycle() -> None:
    """Two paths to one node are legal; only a closed loop is not.

    This also exercises the traversal's memo: node 3 is reached twice and must
    not be re-explored, and must not be mistaken for a cycle.
    """
    source, morphemes = build_morphemes(
        ("ཀ", "n.count"), ("ཁ", "n.count"), ("ག", "n.count"), ("ང", "v.pres")
    )
    nodes = tuple(
        make_node(source, morphemes[i : i + 1], index=i, start_index=i, head_index=i)
        for i in range(4)
    )
    graph = SemanticGraph(
        source=source,
        nodes=nodes,
        edges=(
            plain_edge(0, 1),
            plain_edge(0, 2),
            plain_edge(1, 3),
            plain_edge(2, 3),
        ),
    )
    assert graph.num_edges == 4


def test_a_forest_is_allowed() -> None:
    """A sentence may carry material no relation links to its predicate."""
    source, morphemes = build_morphemes(("ཞིང", "n.count"), ("ཀློག", "v.pres"))
    graph = SemanticGraph(
        source=source,
        nodes=(
            make_node(source, morphemes[:1], index=0, start_index=0),
            make_node(source, morphemes[1:], index=1, start_index=1, head_index=1),
        ),
    )
    assert graph.num_edges == 0
    assert graph.governor_of(0) is None


def test_a_graph_is_immutable() -> None:
    graph = two_node_graph()
    with pytest.raises(ValidationError):
        graph.source = "x"  # type: ignore[misc]


# -- Serialization -------------------------------------------------------------
def test_a_graph_round_trips_through_json() -> None:
    """The IPC boundary serialises this, so the round trip is a contract.

    ``frozenset`` and ``tuple`` fields are the risk: both serialise to JSON
    arrays, and both must validate back into the container the model declares.
    """
    graph = two_node_graph()
    restored = SemanticGraph.model_validate_json(graph.model_dump_json())
    assert restored == graph
    assert restored.nodes[1].frames[0].slots == frozenset({ArgumentSlot.ERGATIVE})
    assert restored.nodes[1].lemma == "ཀློག་"


def test_a_graph_dumps_to_plain_data() -> None:
    """The Plugin Runtime receives data, not Python objects."""
    dumped = two_node_graph().model_dump(mode="json")
    assert dumped["edges"][0]["role"] == "patient"
    assert dumped["edges"][0]["evidence"] == "lexicon"
    assert dumped["intent"]["mood"] == "declarative"
    assert dumped["nodes"][1]["kind"] == "predicate"
