"""Immutable domain models produced by structural dependency mapping.

These are the value objects that cross the boundary out of Stage 8 of the
language processing pipeline. Figure 5 states the stage's output directly:
*"Subject & object detection · Dependency tree construction"*.

The relation inventory is taken from the Constraint Grammars published for
Tibetan in the project's authoritative data repository
(``Data/tibetan-nlp-tibcg3-735f770/grammars/``), which label Tibetan dependency
structure with Universal Dependencies relations. Only relations this stage
actually assigns are defined here; speculatively enumerating the rest of UD
would create members no producer emits and no consumer can rely upon.

A tree, not a forest
--------------------
:class:`DependencyTree` enforces that its nodes form exactly one rooted tree:
one root, every other node reachable from it, no cycles. Downstream consumers --
the grammar checker walking argument structure, and eventually the Semantic
Graph of Stage 11 -- are entitled to recurse without first checking for cycles
or orphans. Enforcing it in the validator means a malformed parse fails loudly
here rather than hanging a plugin later.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teea.core.types import TextSpan
from teea.nlp.postagging import TaggedMorpheme

#: Head index used by the root, which by definition has no head.
ROOT_HEAD: int = -1


@enum.unique
class DependencyRelation(enum.Enum):
    """A syntactic relation between a dependent and its head.

    Values follow the Universal Dependencies names used by the Tibetan
    constraint grammars, so a future comparison against a UD treebank needs no
    translation layer.
    """

    #: The head of the sentence, normally the final verb. Tibetan is verb-final.
    ROOT = "root"

    # -- Verb arguments: Figure 5's "subject & object detection" -------------
    #: Agent/subject. In Tibetan this is the argument marked by the agentive.
    ARG1 = "arg1"
    #: Patient/object, the absolutive argument of a transitive clause.
    ARG2 = "arg2"
    #: Recipient or goal, marked by the allative or terminative.
    ARG3 = "arg3"
    #: Oblique argument -- locative, ablative, elative, comitative, comparative.
    OBL = "obl"

    # -- Nominal-internal structure ------------------------------------------
    #: A case particle attaching to the nominal whose role it marks.
    CASE = "case"
    #: An adjective modifying its head noun.
    AMOD = "amod"
    #: A numeral modifying its head noun.
    NUMMOD = "nummod"
    #: A determiner or plural marker modifying its head noun.
    DET = "det"
    #: A genitive-marked possessor modifying a following nominal.
    NMOD_POSS = "nmod-poss"

    # -- Clause-level modifiers ----------------------------------------------
    #: An adverb modifying the verb.
    ADVMOD = "advmod"
    #: A negation particle.
    NEG = "neg"
    #: A converb or subordinator marking a clause boundary.
    MARK = "mark"
    #: An auxiliary or copula supporting the main verb.
    AUX = "aux"
    #: Sentence punctuation.
    PUNCT = "punct"

    #: Explicit fallback for a morpheme no rule could attach. Recorded rather
    #: than guessed, so the unresolved rate is measurable instead of hidden
    #: behind a plausible-looking label.
    DEP = "dep"


class DependencyNode(BaseModel):
    """One morpheme together with its position in the dependency tree.

    Attributes:
        index: Zero-based position of this node in the sentence.
        head: Index of this node's head, or :data:`ROOT_HEAD` for the root.
        relation: The relation holding between this node and its head.
        morpheme: The Stage 7 tagged morpheme this node stands for.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int = Field(ge=0)
    head: int = Field(ge=ROOT_HEAD)
    relation: DependencyRelation
    morpheme: TaggedMorpheme

    @model_validator(mode="after")
    def _validate_consistency(self) -> DependencyNode:
        if self.head == self.index:
            raise ValueError(f"node {self.index} cannot be its own head")
        is_root = self.head == ROOT_HEAD
        if is_root and self.relation is not DependencyRelation.ROOT:
            raise ValueError("a node with no head must carry the ROOT relation")
        if not is_root and self.relation is DependencyRelation.ROOT:
            raise ValueError("the ROOT relation requires no head")
        return self

    @property
    def is_root(self) -> bool:
        """Whether this node heads the sentence."""
        return self.head == ROOT_HEAD

    @property
    def text(self) -> str:
        """Surface text of the underlying morpheme."""
        return self.morpheme.text

    @property
    def span(self) -> TextSpan:
        """Extent of the underlying morpheme."""
        return self.morpheme.span

    @property
    def tag(self) -> str:
        """Fine-grained part-of-speech tag of the underlying morpheme."""
        return self.morpheme.tag


class DependencyTree(BaseModel):
    """The complete dependency analysis of one sentence.

    Attributes:
        source: The text that was parsed, exactly as supplied.
        nodes: The nodes, in surface order. ``nodes[i].index == i``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    nodes: tuple[DependencyNode, ...] = ()

    @model_validator(mode="after")
    def _validate_tree(self) -> DependencyTree:
        """Enforce that the nodes form exactly one rooted, acyclic tree."""
        if not self.nodes:
            return self

        count = len(self.nodes)
        for position, node in enumerate(self.nodes):
            if node.index != position:
                raise ValueError(f"node at position {position} carries index {node.index}")
            if node.head >= count:
                raise ValueError(f"node {position} has head {node.head} out of range")
            span = node.span
            if span.char_end > len(self.source):
                raise ValueError(f"node {position} span exceeds the source text")
            if self.source[span.char_start : span.char_end] != node.text:
                raise ValueError(f"node {position} span does not select its own text")

        roots = [node.index for node in self.nodes if node.is_root]
        if len(roots) != 1:
            raise ValueError(f"expected exactly one root, found {len(roots)}")

        # Every node must reach the root by following heads. This rejects both
        # cycles and components detached from the root in a single walk.
        root = roots[0]
        for node in self.nodes:
            seen: set[int] = set()
            current = node.index
            while current != ROOT_HEAD and current != root:
                if current in seen:
                    raise ValueError(f"cycle detected in the head chain of node {node.index}")
                seen.add(current)
                current = self.nodes[current].head
            if current == ROOT_HEAD and node.index != root:  # pragma: no cover - defensive
                # Unreachable while the checks above hold: only the root may
                # carry ROOT_HEAD, and exactly one root is required, so a chain
                # either reaches it or cycles. Kept so that relaxing either
                # check cannot let a disconnected component through silently.
                raise ValueError(f"node {node.index} is not connected to the root")
        return self

    def __len__(self) -> int:
        """Number of nodes."""
        return len(self.nodes)

    @property
    def num_nodes(self) -> int:
        """Number of nodes."""
        return len(self.nodes)

    @property
    def is_empty(self) -> bool:
        """Whether the sentence produced no nodes at all."""
        return not self.nodes

    @property
    def root(self) -> DependencyNode | None:
        """The node heading the sentence, or ``None`` for an empty tree."""
        for node in self.nodes:
            if node.is_root:
                return node
        return None

    @property
    def relations(self) -> tuple[DependencyRelation, ...]:
        """The relation of each node, in surface order."""
        return tuple(node.relation for node in self.nodes)

    @property
    def num_unresolved(self) -> int:
        """How many nodes no rule could attach.

        The honest quality signal for this stage: a rising count means the
        grammar is meeting structures it does not describe.
        """
        return sum(1 for node in self.nodes if node.relation is DependencyRelation.DEP)

    def of_relation(self, relation: DependencyRelation) -> tuple[DependencyNode, ...]:
        """Return every node bearing ``relation``, in surface order."""
        return tuple(node for node in self.nodes if node.relation is relation)

    @property
    def subjects(self) -> tuple[DependencyNode, ...]:
        """The agent arguments -- Figure 5's "subject detection"."""
        return self.of_relation(DependencyRelation.ARG1)

    @property
    def objects(self) -> tuple[DependencyNode, ...]:
        """The patient arguments -- Figure 5's "object detection"."""
        return self.of_relation(DependencyRelation.ARG2)

    def head_of(self, index: int) -> DependencyNode | None:
        """Return the head of the node at ``index``, or ``None`` for the root.

        Args:
            index: Node index.

        Raises:
            IndexError: If ``index`` is out of range.
        """
        node = self.nodes[index]
        return None if node.is_root else self.nodes[node.head]

    def children_of(self, index: int) -> tuple[DependencyNode, ...]:
        """Return the nodes whose head is ``index``, in surface order."""
        return tuple(node for node in self.nodes if node.head == index)

    def node_at_char(self, char_index: int) -> DependencyNode | None:
        """Return the node whose span contains ``char_index``.

        Args:
            char_index: Character offset into :attr:`source`.

        Returns:
            The covering node, or ``None`` if the offset falls in a gap or
            outside the text.
        """
        for node in self.nodes:
            if node.span.char_start <= char_index < node.span.char_end:
                return node
        return None


__all__ = [
    "ROOT_HEAD",
    "DependencyNode",
    "DependencyRelation",
    "DependencyTree",
]
