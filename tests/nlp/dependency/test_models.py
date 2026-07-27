"""Unit tests for the Stage 8 domain models (:mod:`teea.nlp.dependency.models`).

:class:`DependencyTree` makes a strong promise: its nodes form exactly one
rooted, acyclic tree in which every node reaches the root. Downstream consumers
-- the grammar checker walking argument structure, and eventually the Semantic
Graph of Stage 11 -- recurse over that structure without defensive checks, so a
malformed parse has to fail here rather than hang a plugin later.

These tests therefore construct trees **directly**, including deliberately
malformed ones, so the validator itself is what is under test rather than the
parser that happens to satisfy it today.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.dependency import (
    ROOT_HEAD,
    DependencyNode,
    DependencyRelation,
    DependencyTree,
)
from teea.nlp.morphology import Morpheme, MorphemeKind
from teea.nlp.postagging import PosCategory, TaggedMorpheme, coarse_category

# Real Tibetan; three UTF-8 bytes per code point, so any confusion between
# character and byte offsets surfaces immediately.
KHYIM = "ཁྱིམ"  # "house"
MI = "མི"  # "person"
SONG = "སོང"  # "went"


# -- Helpers ------------------------------------------------------------------
def tagged(source: str, start: int, end: int, tag: str) -> TaggedMorpheme:
    """Build a TaggedMorpheme for ``source[start:end]`` with exact offsets."""
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


def node(
    source: str,
    start: int,
    end: int,
    tag: str,
    *,
    index: int,
    head: int,
    relation: DependencyRelation,
) -> DependencyNode:
    return DependencyNode(
        index=index,
        head=head,
        relation=relation,
        morpheme=tagged(source, start, end, tag),
    )


#: ``ཁྱིམསོང`` -- "house" then "went", the minimal well-formed two-node tree.
SIMPLE_SOURCE = KHYIM + SONG


def simple_nodes() -> tuple[DependencyNode, ...]:
    return (
        node(
            SIMPLE_SOURCE,
            0,
            len(KHYIM),
            "n.count",
            index=0,
            head=1,
            relation=DependencyRelation.ARG1,
        ),
        node(
            SIMPLE_SOURCE,
            len(KHYIM),
            len(SIMPLE_SOURCE),
            "v.past",
            index=1,
            head=ROOT_HEAD,
            relation=DependencyRelation.ROOT,
        ),
    )


# -- Enumeration --------------------------------------------------------------
def test_relation_values_are_unique() -> None:
    values = [member.value for member in DependencyRelation]
    assert len(values) == len(set(values))


def test_relation_values_follow_universal_dependencies_naming() -> None:
    """The constraint grammars label Tibetan structure with UD relations."""
    names = {member.value for member in DependencyRelation}
    assert {"root", "case", "amod", "nummod", "det", "advmod", "punct"} <= names


# -- DependencyNode -----------------------------------------------------------
def test_valid_node_constructs() -> None:
    dependent, head = simple_nodes()
    assert dependent.index == 0
    assert dependent.head == 1
    assert not dependent.is_root
    assert head.is_root


def test_a_node_cannot_be_its_own_head() -> None:
    with pytest.raises(ValidationError, match="cannot be its own head"):
        node(
            SIMPLE_SOURCE,
            0,
            len(KHYIM),
            "n.count",
            index=0,
            head=0,
            relation=DependencyRelation.ARG1,
        )


def test_a_headless_node_must_be_the_root() -> None:
    with pytest.raises(ValidationError, match="must carry the ROOT relation"):
        node(
            SIMPLE_SOURCE,
            0,
            len(KHYIM),
            "n.count",
            index=0,
            head=ROOT_HEAD,
            relation=DependencyRelation.ARG1,
        )


def test_the_root_relation_requires_no_head() -> None:
    with pytest.raises(ValidationError, match="ROOT relation requires no head"):
        node(
            SIMPLE_SOURCE,
            0,
            len(KHYIM),
            "n.count",
            index=0,
            head=1,
            relation=DependencyRelation.ROOT,
        )


def test_negative_index_is_rejected() -> None:
    with pytest.raises(ValidationError):
        node(
            SIMPLE_SOURCE,
            0,
            len(KHYIM),
            "n.count",
            index=-1,
            head=1,
            relation=DependencyRelation.ARG1,
        )


def test_node_delegates_to_its_morpheme() -> None:
    dependent, _ = simple_nodes()
    assert dependent.text == KHYIM
    assert dependent.tag == "n.count"
    assert dependent.span.char_start == 0
    assert dependent.morpheme.category is PosCategory.NOUN


def test_node_is_frozen_and_forbids_unknown_fields() -> None:
    dependent, _ = simple_nodes()
    with pytest.raises(ValidationError):
        dependent.head = 5  # type: ignore[misc]
    with pytest.raises(ValidationError):
        DependencyNode(
            index=0,
            head=1,
            relation=DependencyRelation.ARG1,
            morpheme=tagged(SIMPLE_SOURCE, 0, len(KHYIM), "n.count"),
            unexpected="x",  # type: ignore[call-arg]
        )


def test_nodes_compare_by_value_and_are_hashable() -> None:
    first = simple_nodes()[0]
    second = simple_nodes()[0]
    assert first == second
    assert len({first, second}) == 1


# -- DependencyTree: structural validation ------------------------------------
def test_valid_tree_constructs() -> None:
    tree = DependencyTree(source=SIMPLE_SOURCE, nodes=simple_nodes())
    assert tree.num_nodes == 2
    assert len(tree) == 2
    assert not tree.is_empty
    assert tree.root is not None
    assert tree.root.text == SONG


def test_empty_tree_is_valid() -> None:
    tree = DependencyTree(source="")
    assert tree.is_empty
    assert tree.root is None
    assert tree.num_nodes == 0
    assert tree.num_unresolved == 0


def test_index_must_match_position() -> None:
    dependent, head = simple_nodes()
    misindexed = dependent.model_copy(update={"index": 5})
    with pytest.raises(ValidationError, match="carries index"):
        DependencyTree(source=SIMPLE_SOURCE, nodes=(misindexed, head))


def test_head_out_of_range_is_rejected() -> None:
    _, head = simple_nodes()
    stray = node(
        SIMPLE_SOURCE,
        0,
        len(KHYIM),
        "n.count",
        index=0,
        head=9,
        relation=DependencyRelation.ARG1,
    )
    with pytest.raises(ValidationError, match="out of range"):
        DependencyTree(source=SIMPLE_SOURCE, nodes=(stray, head))


def test_exactly_one_root_is_required() -> None:
    dependent, head = simple_nodes()
    second_root = dependent.model_copy(
        update={"head": ROOT_HEAD, "relation": DependencyRelation.ROOT}
    )
    with pytest.raises(ValidationError, match="exactly one root"):
        DependencyTree(source=SIMPLE_SOURCE, nodes=(second_root, head))


def test_a_rootless_tree_is_rejected() -> None:
    """Two nodes pointing at each other have no root at all."""
    first = node(
        SIMPLE_SOURCE,
        0,
        len(KHYIM),
        "n.count",
        index=0,
        head=1,
        relation=DependencyRelation.ARG1,
    )
    second = node(
        SIMPLE_SOURCE,
        len(KHYIM),
        len(SIMPLE_SOURCE),
        "v.past",
        index=1,
        head=0,
        relation=DependencyRelation.ARG1,
    )
    with pytest.raises(ValidationError, match="exactly one root"):
        DependencyTree(source=SIMPLE_SOURCE, nodes=(first, second))


def test_a_cycle_is_rejected() -> None:
    """A two-node cycle hanging off a valid root must not be accepted.

    This is the case a naive "does a root exist" check would miss.
    """
    source = KHYIM + MI + SONG
    a = node(source, 0, len(KHYIM), "n.count", index=0, head=1, relation=DependencyRelation.AMOD)
    b = node(
        source,
        len(KHYIM),
        len(KHYIM) + len(MI),
        "n.count",
        index=1,
        head=0,
        relation=DependencyRelation.AMOD,
    )
    root = node(
        source,
        len(KHYIM) + len(MI),
        len(source),
        "v.past",
        index=2,
        head=ROOT_HEAD,
        relation=DependencyRelation.ROOT,
    )
    with pytest.raises(ValidationError, match="cycle detected"):
        DependencyTree(source=source, nodes=(a, b, root))


def test_a_span_that_does_not_select_its_own_text_is_rejected() -> None:
    source = KHYIM + SONG
    _, head = simple_nodes()
    lying = DependencyNode(
        index=0,
        head=1,
        relation=DependencyRelation.ARG1,
        # text says SONG, span points at KHYIM
        morpheme=TaggedMorpheme(
            morpheme=Morpheme(
                text=SONG,
                span=TextSpan(
                    char_start=0,
                    char_end=len(SONG),
                    byte_start=0,
                    byte_end=len(SONG.encode("utf-8")),
                ),
                kind=MorphemeKind.ROOT,
            ),
            tag="v.past",
            category=PosCategory.VERB,
        ),
    )
    with pytest.raises(ValidationError, match="does not select its own text"):
        DependencyTree(source=source, nodes=(lying, head))


def test_a_span_beyond_the_source_is_rejected() -> None:
    longer = SIMPLE_SOURCE + KHYIM
    stray = node(
        longer,
        len(SIMPLE_SOURCE),
        len(longer),
        "n.count",
        index=0,
        head=1,
        relation=DependencyRelation.ARG1,
    )
    _, head = simple_nodes()
    with pytest.raises(ValidationError, match="exceeds the source text"):
        DependencyTree(source=SIMPLE_SOURCE, nodes=(stray, head))


# -- DependencyTree: accessors ------------------------------------------------
@pytest.fixture
def tree() -> DependencyTree:
    return DependencyTree(source=SIMPLE_SOURCE, nodes=simple_nodes())


def test_head_and_children_navigation(tree: DependencyTree) -> None:
    assert tree.head_of(0) is tree.nodes[1]
    assert tree.head_of(1) is None
    assert tree.children_of(1) == (tree.nodes[0],)
    assert tree.children_of(0) == ()


def test_head_of_rejects_an_out_of_range_index(tree: DependencyTree) -> None:
    with pytest.raises(IndexError):
        tree.head_of(99)


def test_relations_and_of_relation(tree: DependencyTree) -> None:
    assert tree.relations == (DependencyRelation.ARG1, DependencyRelation.ROOT)
    assert tree.of_relation(DependencyRelation.ARG1) == (tree.nodes[0],)
    assert tree.of_relation(DependencyRelation.ARG2) == ()


def test_subjects_and_objects_expose_figure_5_detection(tree: DependencyTree) -> None:
    assert tree.subjects == (tree.nodes[0],)
    assert tree.objects == ()


def test_num_unresolved_counts_only_the_fallback_relation() -> None:
    dependent, head = simple_nodes()
    unresolved = dependent.model_copy(update={"relation": DependencyRelation.DEP})
    tree = DependencyTree(source=SIMPLE_SOURCE, nodes=(unresolved, head))
    assert tree.num_unresolved == 1


def test_node_at_char_is_half_open(tree: DependencyTree) -> None:
    assert tree.node_at_char(0) is tree.nodes[0]
    assert tree.node_at_char(len(KHYIM) - 1) is tree.nodes[0]
    assert tree.node_at_char(len(KHYIM)) is tree.nodes[1]
    assert tree.node_at_char(len(SIMPLE_SOURCE)) is None
    assert tree.node_at_char(-1) is None


def test_tree_is_frozen_and_compares_by_value(tree: DependencyTree) -> None:
    with pytest.raises(ValidationError):
        tree.source = "x"  # type: ignore[misc]
    assert tree == DependencyTree(source=SIMPLE_SOURCE, nodes=simple_nodes())
