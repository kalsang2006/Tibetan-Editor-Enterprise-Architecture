"""Immutable domain models produced by semantic analysis.

These are the value objects that cross the boundary out of Stage 11 of the
language processing pipeline. Figure 5 states the stage as *"Semantic Analysis ·
Context Graph · Meaning Representation · Intent Analysis"*, and Figures 1 and 2
name the component that owns it: the Language Server's **Semantic Graph**.

One artifact, three bullets
--------------------------
:class:`SemanticGraph` carries all three of Figure 5's bullets, because they are
three views of one structure rather than three products:

* the **Context Graph** is the graph itself -- :class:`SemanticNode` concepts and
  predicates joined by typed :class:`SemanticEdge` links, with the names Stage 9
  found and the terminology Stage 10 found attached to the nodes they fall on;
* the **Meaning Representation** is the predicate-argument content of that graph:
  which participant plays which :class:`SemanticRole` for which predicate,
  together with the attested argument frame that decided it;
* the **Intent Analysis** is :class:`SentenceIntent`, the illocutionary force the
  sentence's own mood morphology marks.

Roles are assigned from evidence, or not at all
-----------------------------------------------
Every :class:`SemanticRole` traces to something a document or a lexicon states:
a case particle Stage 6 recognized and Stage 7 disambiguated, a dependency
relation Stage 8 assigned from the Tibetan constraint grammars, or an argument
frame the verb lexicon reports for the governing predicate. Where none of those
decides, the role is :attr:`SemanticRole.UNSPECIFIED` -- recorded, so the
unresolved rate stays measurable, exactly as Stage 8 records
:attr:`~teea.nlp.dependency.DependencyRelation.DEP` rather than guessing. See
ADR-014.

:class:`RoleEvidence` travels with every edge for the same reason Stage 9 carries
:class:`~teea.nlp.ner.EntityEvidence`: the three sources have different
reliability, and a consumer deciding how far to trust an analysis needs to tell
them apart without re-deriving it.

Spans are never recomputed
--------------------------
A node's span is assembled from the spans Stage 6 produced and every later stage
preserved. Nothing here re-segments, re-tags or re-parses.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teea.core.types import TextSpan
from teea.nlp.ner import NamedEntity
from teea.nlp.postagging import TaggedMorpheme
from teea.nlp.terminology import RecognizedTerm
from teea.persistence import VerbFrame


@enum.unique
class SemanticRole(enum.Enum):
    """The part a participant plays in the situation a predicate describes.

    The inventory is closed to what the available evidence can actually
    distinguish. Each member names the source that assigns it:

    ============  ==============================================================
    Member        Assigned from
    ============  ==============================================================
    AGENT         the agentive case particle ``case.agn``
    PATIENT       an absolutive argument of a predicate the verb lexicon attests
                  as transitive
    THEME         an absolutive argument of a predicate the lexicon attests as
                  intransitive, or that Stage 8 read as the sole argument
    GOAL          the allative or terminative (Stage 8 ``arg3``)
    LOCATION      the locative ``case.loc``
    SOURCE        the ablative ``case.abl`` or elative ``case.ela``
    ASSOCIATE     the associative ``case.ass``
    STANDARD      the comparative ``case.comp``
    POSSESSOR     the genitive ``case.gen`` (Stage 8 ``nmod-poss``)
    MODIFIER      Stage 8 ``amod``, ``nummod``, ``det`` or ``advmod``
    SUBORDINATE   a predicate Stage 8 attached with ``mark``
    UNSPECIFIED   nothing decided; recorded rather than guessed
    ============  ==============================================================
    """

    AGENT = "agent"
    PATIENT = "patient"
    THEME = "theme"
    GOAL = "goal"
    LOCATION = "location"
    SOURCE = "source"
    ASSOCIATE = "associate"
    STANDARD = "standard"
    POSSESSOR = "possessor"
    MODIFIER = "modifier"
    SUBORDINATE = "subordinate"
    #: Explicit fallback. A rising count means the analysis is meeting argument
    #: structures the available evidence does not describe.
    UNSPECIFIED = "unspecified"


@enum.unique
class RoleEvidence(enum.Enum):
    """What decided a role.

    Ordered by directness, not by confidence: a consumer that wants only roles a
    resource actually vouched for keeps ``CASE`` and ``LEXICON`` and drops
    ``STRUCTURE``.
    """

    #: A case particle marked it. The most direct evidence Tibetan offers,
    #: because the case system *is* the argument marking.
    CASE = "case"
    #: The governing predicate's attested argument frame decided it. This is what
    #: separates the object of a transitive clause from the subject of an
    #: intransitive one when no case particle is written.
    LEXICON = "lexicon"
    #: Neither applied, so Stage 8's structural analysis was carried through
    #: unchanged. Honest, but the weakest of the three.
    STRUCTURE = "structure"


@enum.unique
class SemanticNodeKind(enum.Enum):
    """What a node stands for."""

    #: A verb heading a clause -- the sentence's own head, or a subordinate
    #: clause head Stage 8 attached with ``mark``.
    PREDICATE = "predicate"
    #: A participant: a nominal, a name, a technical term, or a modifier.
    CONCEPT = "concept"


class SemanticNode(BaseModel):
    """One unit of meaning within a sentence.

    A node covers a contiguous run of Stage 8 nodes. Usually that run is a single
    morpheme, but a name Stage 9 recognised or a term Stage 10 recognised is one
    node however many syllables it spans -- which is why Figure 5 places those
    two stages before this one. Without them a multi-syllable name would arrive
    here as several unrelated arguments of the same verb.

    Attributes:
        index: Zero-based position of this node in the graph.
        kind: Whether the node is a predicate or a participant.
        text: The surface text the node covers, exactly as it appears.
        span: Character/byte extent of ``text`` in the sentence.
        start_index: Index of the first Stage 8 node of the run.
        end_index: Index one past the last Stage 8 node of the run.
        head_index: Index of the Stage 8 node through which this run attaches to
            the rest of the sentence -- the member closest to the tree root.
        frames: Every verb lemma this run is an attested stem of. Empty unless
            the run is a verb form the lexicon knows. More than one member means
            the surface is genuinely ambiguous between dictionary entries.
        entity: The Stage 9 name covering this run, when there is one.
        term: The Stage 10 technical term covering this run, when there is one.
        morphemes: The tagged morphemes the node spans.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int = Field(ge=0)
    kind: SemanticNodeKind
    text: str
    span: TextSpan
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    head_index: int = Field(ge=0)
    frames: tuple[VerbFrame, ...] = ()
    entity: NamedEntity | None = None
    term: RecognizedTerm | None = None
    morphemes: tuple[TaggedMorpheme, ...]

    @model_validator(mode="after")
    def _validate_consistency(self) -> SemanticNode:
        if not self.text:
            raise ValueError("a semantic node must not be empty")
        if self.end_index <= self.start_index:
            raise ValueError("end_index must be greater than start_index")
        if len(self.morphemes) != self.end_index - self.start_index:
            raise ValueError(
                f"expected {self.end_index - self.start_index} morphemes, got {len(self.morphemes)}"
            )
        if not self.start_index <= self.head_index < self.end_index:
            raise ValueError("head_index must lie inside the node's own run")
        first, last = self.morphemes[0], self.morphemes[-1]
        if self.span.char_start != first.span.char_start:
            raise ValueError("span must start at the first morpheme")
        if self.span.char_end != last.span.char_end:
            raise ValueError("span must end at the last morpheme")
        return self

    @property
    def is_predicate(self) -> bool:
        """Whether this node heads a clause."""
        return self.kind is SemanticNodeKind.PREDICATE

    @property
    def num_morphemes(self) -> int:
        """How many morphemes the node spans."""
        return len(self.morphemes)

    @property
    def head(self) -> TaggedMorpheme:
        """The morpheme through which this node attaches to the sentence."""
        return self.morphemes[self.head_index - self.start_index]

    @property
    def lemma(self) -> str | None:
        """The dictionary headword of this predicate, when the lexicon agrees.

        ``None`` when the run is not an attested verb form, or when the attested
        entries disagree about which lemma it belongs to. Reporting one of
        several candidate lemmas would be a guess, and Stage 6 established that
        this pipeline marks ambiguity rather than resolving it by fiat.
        """
        lemmas = {frame.lemma for frame in self.frames}
        return lemmas.pop() if len(lemmas) == 1 else None

    @property
    def is_lexically_ambiguous(self) -> bool:
        """Whether the lexicon offers more than one lemma for this run."""
        return len({frame.lemma for frame in self.frames}) > 1

    @property
    def is_transitive(self) -> bool | None:
        """Whether this predicate is attested to take a distinct agent.

        Three-valued, like :attr:`~teea.persistence.VerbFrame.is_transitive`.
        Candidate entries that say nothing are ignored; ``None`` is returned when
        no entry decides, or when two entries decide differently.
        """
        judgements = {frame.is_transitive for frame in self.frames}
        judgements.discard(None)
        return judgements.pop() if len(judgements) == 1 else None

    @property
    def is_named_entity(self) -> bool:
        """Whether Stage 9 recognised this run as a name."""
        return self.entity is not None

    @property
    def is_terminology(self) -> bool:
        """Whether Stage 10 recognised this run as a technical term."""
        return self.term is not None


class SemanticEdge(BaseModel):
    """A typed link from a governing node to a dependent one.

    Oriented governor to dependent, which is the direction a consumer reads:
    *this predicate has this agent*, *this concept has this possessor*.

    Attributes:
        source: Index of the governing node.
        target: Index of the dependent node.
        role: The part ``target`` plays for ``source``.
        evidence: What decided ``role``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: int = Field(ge=0)
    target: int = Field(ge=0)
    role: SemanticRole
    evidence: RoleEvidence

    @model_validator(mode="after")
    def _validate_consistency(self) -> SemanticEdge:
        if self.source == self.target:
            raise ValueError(f"node {self.source} cannot govern itself")
        return self


@enum.unique
class SentenceMood(enum.Enum):
    """The illocutionary force a sentence's own morphology marks.

    Tibetan marks mood morphologically, and the reference tagset names the
    markers: ``cv.ques`` and ``p.interrog`` for a question, ``v.imp``, ``cv.imp``
    and ``n.v.imp`` for a command. Declarative is the unmarked case -- it is what
    remains when nothing marks anything else, not a positive finding.
    """

    DECLARATIVE = "declarative"
    INTERROGATIVE = "interrogative"
    IMPERATIVE = "imperative"


@enum.unique
class Polarity(enum.Enum):
    """Whether the sentence asserts or denies."""

    AFFIRMATIVE = "affirmative"
    NEGATIVE = "negative"


class SentenceIntent(BaseModel):
    """Figure 5's *Intent Analysis* for one sentence.

    Attributes:
        mood: The illocutionary force the sentence's morphology marks.
        polarity: Whether a negation particle is present.
        is_reported: Whether the sentence is marked as reported speech by a
            quotative. A consumer that corrects grammar should leave a quotation
            as the author wrote it.
        evidence: The fine-grained tags that decided the classification, in
            surface order and without duplicates. Empty means nothing was marked,
            so the reading is the unmarked default. This is the audit trail: a
            consumer wanting a stricter rule can apply it to these tags rather
            than re-deriving the analysis.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mood: SentenceMood = SentenceMood.DECLARATIVE
    polarity: Polarity = Polarity.AFFIRMATIVE
    is_reported: bool = False
    evidence: tuple[str, ...] = ()

    @property
    def is_marked(self) -> bool:
        """Whether any morphology marked this sentence's intent at all."""
        return bool(self.evidence)


class SemanticGraph(BaseModel):
    """The complete semantic analysis of one sentence.

    Guaranteed acyclic, so a plugin walking predicate to argument to modifier
    terminates without keeping its own visited set. It is *not* guaranteed
    connected: a sentence may carry material no relation links to its predicate,
    and reporting that as a second component is more honest than inventing an
    attachment.

    Attributes:
        source: The text that was analysed, exactly as supplied.
        nodes: The nodes, in surface order. ``nodes[i].index == i``.
        edges: The typed links between them.
        intent: The sentence-level intent analysis.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    nodes: tuple[SemanticNode, ...] = ()
    edges: tuple[SemanticEdge, ...] = ()
    intent: SentenceIntent = SentenceIntent()

    @model_validator(mode="after")
    def _validate_graph(self) -> SemanticGraph:
        """Enforce node ordering, span accuracy, and acyclicity."""
        previous_end = -1
        for position, node in enumerate(self.nodes):
            if node.index != position:
                raise ValueError(f"node at position {position} carries index {node.index}")
            if node.start_index < previous_end:
                raise ValueError("semantic node runs must not overlap")
            if node.span.char_end > len(self.source):
                raise ValueError(f"node {position} span exceeds the source text")
            if self.source[node.span.char_start : node.span.char_end] != node.text:
                raise ValueError(f"node {position} span does not select its own text")
            previous_end = node.end_index

        count = len(self.nodes)
        seen_edges: set[tuple[int, int, SemanticRole]] = set()
        for edge in self.edges:
            if edge.source >= count or edge.target >= count:
                raise ValueError(f"edge {edge.source}->{edge.target} refers to a node out of range")
            key = (edge.source, edge.target, edge.role)
            if key in seen_edges:
                raise ValueError(f"duplicate edge {edge.source}->{edge.target}")
            seen_edges.add(key)

        self._reject_cycles()
        return self

    def _reject_cycles(self) -> None:
        """Raise if the edges contain a cycle.

        The analyser builds edges by contracting an acyclic dependency tree, so
        this cannot fire for its output. It is enforced anyway because the model
        is what downstream consumers are entitled to rely on, and a future
        implementation of the protocol gets the same guarantee.
        """
        successors: dict[int, list[int]] = {}
        for edge in self.edges:
            successors.setdefault(edge.source, []).append(edge.target)

        state: dict[int, int] = {}
        for start in range(len(self.nodes)):
            if state.get(start):
                continue
            stack: list[tuple[int, int]] = [(start, 0)]
            state[start] = 1
            while stack:
                node, cursor = stack.pop()
                children = successors.get(node, ())
                if cursor < len(children):
                    stack.append((node, cursor + 1))
                    child = children[cursor]
                    if state.get(child) == 1:
                        raise ValueError(f"cycle detected through node {child}")
                    if not state.get(child):
                        state[child] = 1
                        stack.append((child, 0))
                else:
                    state[node] = 2

    def __len__(self) -> int:
        """Number of nodes."""
        return len(self.nodes)

    @property
    def num_nodes(self) -> int:
        """Number of nodes."""
        return len(self.nodes)

    @property
    def num_edges(self) -> int:
        """Number of edges."""
        return len(self.edges)

    @property
    def is_empty(self) -> bool:
        """Whether the sentence produced no semantic node at all."""
        return not self.nodes

    @property
    def predicates(self) -> tuple[SemanticNode, ...]:
        """The clause heads, in surface order."""
        return tuple(node for node in self.nodes if node.is_predicate)

    @property
    def concepts(self) -> tuple[SemanticNode, ...]:
        """The participants, in surface order."""
        return tuple(node for node in self.nodes if not node.is_predicate)

    @property
    def named_entities(self) -> tuple[SemanticNode, ...]:
        """The nodes Stage 9 recognised as names."""
        return tuple(node for node in self.nodes if node.is_named_entity)

    @property
    def terminology(self) -> tuple[SemanticNode, ...]:
        """The nodes Stage 10 recognised as technical terms."""
        return tuple(node for node in self.nodes if node.is_terminology)

    @property
    def roles(self) -> tuple[SemanticRole, ...]:
        """The role borne by each edge, in edge order."""
        return tuple(edge.role for edge in self.edges)

    @property
    def num_unspecified(self) -> int:
        """How many edges no evidence could type.

        The honest quality signal for this stage, mirroring
        :attr:`~teea.nlp.dependency.DependencyTree.num_unresolved`.
        """
        return sum(1 for edge in self.edges if edge.role is SemanticRole.UNSPECIFIED)

    def of_role(self, role: SemanticRole) -> tuple[SemanticEdge, ...]:
        """Return every edge bearing ``role``, in edge order."""
        return tuple(edge for edge in self.edges if edge.role is role)

    def of_evidence(self, evidence: RoleEvidence) -> tuple[SemanticEdge, ...]:
        """Return every edge assigned on a particular basis, in edge order."""
        return tuple(edge for edge in self.edges if edge.evidence is evidence)

    def arguments_of(self, index: int) -> tuple[SemanticEdge, ...]:
        """Return the edges leaving the node at ``index``, in edge order.

        The primitive Figure 5's *Meaning Representation* is read through: for a
        predicate, these are its participants and the role each plays.
        """
        return tuple(edge for edge in self.edges if edge.source == index)

    def governor_of(self, index: int) -> SemanticEdge | None:
        """Return the edge that governs the node at ``index``, if any.

        Returns:
            The first incoming edge, or ``None`` when the node heads its own
            component.
        """
        for edge in self.edges:
            if edge.target == index:
                return edge
        return None

    def node_at_char(self, char_index: int) -> SemanticNode | None:
        """Return the node whose span contains ``char_index``.

        The primitive the add-in needs to decide which concept an offset the user
        clicked belongs to.

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
    "Polarity",
    "RoleEvidence",
    "SemanticEdge",
    "SemanticGraph",
    "SemanticNode",
    "SemanticNodeKind",
    "SemanticRole",
    "SentenceIntent",
    "SentenceMood",
]
