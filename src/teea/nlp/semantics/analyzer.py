"""Lexicon-driven semantic analysis (Language pipeline Stage 11).

Figure 5 assigns Stage 11 three jobs -- *Context Graph*, *Meaning Representation*
and *Intent Analysis* -- and Figures 1 and 2 name the component that performs
them: the Language Server's **Semantic Graph**. This module builds that graph.

What this stage adds
--------------------
Stage 8 already produces a labelled tree, so a semantic layer that merely renamed
its relations would be worth nothing. Five things are genuinely new here, and
each of them needs evidence Stage 8 does not have:

1. **Concepts, not syllables.** Tibetan has no word delimiter, so Stage 6 emits
   syllables and Stage 8 attaches each of them separately: a four-syllable
   personal name arrives at this stage as four unrelated arguments of the same
   verb. Stages 9 and 10 are what say those syllables are one name or one term,
   which is exactly why Figure 5 orders them before this one. A node here is a
   concept.
2. **Predicate identity.** A Tibetan verb's present, past, future and imperative
   stems are different surfaces -- ``འགྲོ`` and ``སོང`` are the same verb -- so
   the surface form is not the predicate. The verb lexicon supplies the lemma.
3. **Roles, not relations.** ``arg1`` says *this nominal is a first argument*;
   :attr:`~teea.nlp.semantics.models.SemanticRole.AGENT` says *this participant
   acts*. The case particle decides it where Tibetan writes one.
4. **The absolutive, resolved lexically.** This is the substantive correction
   Stage 11 makes. Tibetan is ergative-absolutive, and an absolutive argument is
   the object of a transitive clause but the subject of an intransitive one, with
   no morphology to tell them apart. Stage 8 decides structurally -- object if
   the sentence writes an agentive anywhere, subject otherwise -- which ADR-010
   records as a measured limitation, because 76% of agentive markers in the
   reference corpus are the fused ``ས``/``ར`` Stage 6 documents it will not
   split. Those clauses read as intransitive and their object is mislabelled.
   Here the *verb's own attested argument frame* decides instead: a predicate the
   lexicon reports as ``Erg-Abs`` takes a patient whether or not its agent is
   written. That evidence did not exist at Stage 8.
5. **Intent.** Nothing upstream reports whether the sentence asks, commands or
   states.

Where the rules come from
-------------------------
The argument frames are read from the digital edition of Hill (2010),
*A Lexicon of Tibetan Verb Stems as Reported by the Grammatical Tradition*, which
the authoritative data repository ships alongside the Constraint Grammars Stage 8
derives its relation inventory from (ADR-009). Case-to-role assignment follows
the case system those same grammars key their attachment rules on. Mood markers
are the reference tagset's own: ``cv.ques``, ``p.interrog``, ``v.imp``,
``cv.imp``, ``n.v.imp``, ``neg`` and the quotatives. Nothing is invented; see
ADR-013, ADR-014 and ADR-015.

Why the graph cannot cycle
--------------------------
Nodes are formed by contracting runs of Stage 8 nodes, and contracting a tree can
in general create cycles, because an entity's syllables need not form a connected
subtree. It cannot happen here, by construction. A node's *head* is defined as
its member closest to the tree root, and a node's governor is the first node-
bearing ancestor of that head. The governor's head is at most as deep as that
ancestor, which is strictly shallower than the node's own head, so depth strictly
decreases along every edge and no cycle can close. :class:`SemanticGraph`
re-checks it anyway, because that guarantee is what consumers rely on.
"""

from __future__ import annotations

from typing import NamedTuple

from teea.core.errors import InputValidationError
from teea.core.types import TextSpan
from teea.nlp.dependency import ROOT_HEAD, DependencyRelation, DependencyTree
from teea.nlp.ner import EntityAnnotation, NamedEntity
from teea.nlp.postagging import PosCategory, TaggedMorpheme
from teea.nlp.semantics.models import (
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
from teea.nlp.terminology import RecognizedTerm, TerminologyAnnotation
from teea.persistence import VerbFrame, VerbLexiconRepository, default_verb_lexicon

#: Coarse classes that carry lexical content and therefore become nodes.
#: Particles, punctuation and determiners are grammatical rather than
#: referential, and ``UNKNOWN`` marks material the tagset itself declines to
#: analyse (Sanskrit loanwords, editorial markers) -- asserting that such a run
#: is a concept would claim more than the evidence supports.
_NODE_CATEGORIES = frozenset(
    {
        PosCategory.NOUN,
        PosCategory.VERB,
        PosCategory.PRONOUN,
        PosCategory.NUMERAL,
        PosCategory.ADJECTIVE,
        PosCategory.ADVERB,
    }
)

#: Relations whose dependent is grammatical support rather than a participant.
#: Only ``aux`` needs stating: an auxiliary or copula is verbal, so the category
#: filter above admits it, but it supports a predicate rather than being one.
#: Stage 8 never heads a clause with an auxiliary, so its arguments are attached
#: elsewhere and a node here would have none.
_SUPPORT_RELATIONS = frozenset({DependencyRelation.AUX})

#: Relations that may separate a nominal from the case particle marking it.
#: Tibetan places adjectives, numerals and determiners after their head noun, so
#: *noun + adjective + case* is ordinary. Anything else closes the phrase.
_PHRASE_INTERNAL = frozenset(
    {
        DependencyRelation.AMOD,
        DependencyRelation.NUMMOD,
        DependencyRelation.DET,
    }
)

#: Roles a Stage 8 relation determines on its own.
_RELATION_ROLES: dict[DependencyRelation, SemanticRole] = {
    DependencyRelation.NMOD_POSS: SemanticRole.POSSESSOR,
    DependencyRelation.ARG3: SemanticRole.GOAL,
    DependencyRelation.AMOD: SemanticRole.MODIFIER,
    DependencyRelation.NUMMOD: SemanticRole.MODIFIER,
    DependencyRelation.DET: SemanticRole.MODIFIER,
    DependencyRelation.ADVMOD: SemanticRole.MODIFIER,
    DependencyRelation.MARK: SemanticRole.SUBORDINATE,
}

#: Of those, the ones a case particle assigns rather than word order. Stage 8
#: reaches ``nmod-poss`` only through the genitive and ``arg3`` only through the
#: allative or terminative, so the evidence really is the case marking.
_CASE_DRIVEN = frozenset({DependencyRelation.NMOD_POSS, DependencyRelation.ARG3})

#: Oblique case particles and the role each marks. Stage 8 collapses all of them
#: into ``obl``; recovering the distinction needs only the particle it already
#: attached.
_CASE_ROLES: dict[str, SemanticRole] = {
    "case.loc": SemanticRole.LOCATION,
    "case.abl": SemanticRole.SOURCE,
    "case.ela": SemanticRole.SOURCE,
    "case.ass": SemanticRole.ASSOCIATE,
    "case.comp": SemanticRole.STANDARD,
}

#: The agentive, which marks the agent of a transitive clause.
_AGENTIVE_TAG = "case.agn"

#: Tags that mark a question in the reference tagset.
_INTERROGATIVE_TAGS = frozenset({"cv.ques", "p.interrog"})

#: Tags that mark a command.
_IMPERATIVE_TAGS = frozenset({"v.imp", "cv.imp", "n.v.imp"})

#: Tags that mark negation.
_NEGATION_TAGS = frozenset({"neg", "v.neg", "v.cop.neg", "n.v.neg"})

#: Tags that mark reported speech.
_REPORTED_TAGS = frozenset({"cl.quot", "case.nare"})

#: Every tag the intent classifier treats as evidence, so the audit trail can be
#: collected in one pass.
_INTENT_TAGS = (
    _INTERROGATIVE_TAGS | _IMPERATIVE_TAGS | _NEGATION_TAGS | _REPORTED_TAGS
)


class _Unit(NamedTuple):
    """A run of Stage 8 nodes that will become at most one semantic node."""

    start: int
    end: int
    head: int
    entity: NamedEntity | None
    term: RecognizedTerm | None


class _Layout(NamedTuple):
    """Everything derived from one tree, computed once per analysis.

    Grouped rather than threaded through as separate arguments because all five
    describe the same sentence and are always needed together; passing them
    individually made the edge builder take eight parameters.
    """

    #: The tree being analysed.
    tree: DependencyTree
    #: The units, in surface order, tiling the tree's node indices.
    units: tuple[_Unit, ...]
    #: Stage 8 node index -> index of the unit containing it.
    owner: list[int]
    #: Unit index -> position in the finished graph, for units that became nodes.
    position: dict[int, int]
    #: Position -> the case particle marking a unit that ends there.
    case_tags: list[str | None]


class TibetanSemanticAnalyzer:
    """Builds semantic graphs from parsed, annotated Tibetan sentences.

    Satisfies the :class:`~teea.nlp.semantics.interfaces.SemanticAnalyzer`
    protocol. The analyser holds no mutable state and is safe to share across
    threads; :meth:`analyze` works entirely on local data.

    The algorithm is a single deterministic pass:

    1. Group the sentence's morphemes into units -- each Stage 9 name and Stage
       10 term is one unit, every other morpheme is its own.
    2. Give each unit the head through which it attaches to the sentence, and
       drop the units that are purely grammatical.
    3. Look the verb forms up in the lexicon, which supplies the lemma and the
       attested argument frame.
    4. Draw one edge per unit to its governing unit, typed by the case particle,
       the Stage 8 relation, or the governing predicate's frame -- in that order
       of directness, recording which applied.
    5. Classify the sentence's intent from its mood morphology.

    Args:
        verbs: Source of verb lemmas and argument frames. Defaults to the shared
            lexicon derived from the authoritative data repository.

    Raises:
        ConfigurationError: If the default verb lexicon cannot be loaded.
    """

    def __init__(self, *, verbs: VerbLexiconRepository | None = None) -> None:
        # `is None`, not `or`: an empty lexicon is falsy because it defines
        # __len__, so `or` would silently substitute the shipped one.
        self._verbs = default_verb_lexicon() if verbs is None else verbs

    def analyze(
        self,
        tree: DependencyTree,
        *,
        entities: EntityAnnotation | None = None,
        terms: TerminologyAnnotation | None = None,
    ) -> SemanticGraph:
        """Build the semantic graph for ``tree``.

        Total with respect to content: an empty tree yields an empty graph rather
        than raising.

        Args:
            tree: Stage 8 output for one sentence.
            entities: Stage 9 output for the same sentence, if available.
            terms: Stage 10 output for the same sentence, if available.

        Returns:
            The semantic graph, with nodes in surface order.

        Raises:
            InputValidationError: If an annotation was produced from a different
                source text, or indexes morphemes the tree does not have.
        """
        if entities is not None:
            _require_describes(
                "Entity",
                entities.source,
                tuple(entity.end_index for entity in entities.entities),
                tree,
            )
        if terms is not None:
            _require_describes(
                "Terminology",
                terms.source,
                tuple(term.end_index for term in terms.terms),
                tree,
            )

        intent = _classify_intent(tuple(node.morpheme for node in tree.nodes))
        if not tree.nodes:
            return SemanticGraph(source=tree.source, intent=intent)

        units = _build_units(tree, entities, terms, _depths(tree))
        keep = [index for index, unit in enumerate(units) if _is_node(tree, unit)]
        layout = _Layout(
            tree=tree,
            units=units,
            owner=_owner_index(units, len(tree.nodes)),
            position={unit_index: slot for slot, unit_index in enumerate(keep)},
            case_tags=_case_tags(tree),
        )

        nodes = tuple(
            self._build_node(tree, units[unit_index], slot)
            for slot, unit_index in enumerate(keep)
        )
        edges = tuple(
            edge
            for slot, unit_index in enumerate(keep)
            if (edge := self._build_edge(layout, unit_index, slot, nodes)) is not None
        )
        return SemanticGraph(
            source=tree.source, nodes=nodes, edges=edges, intent=intent
        )

    # -- Node construction ---------------------------------------------------
    def _build_node(
        self, tree: DependencyTree, unit: _Unit, slot: int
    ) -> SemanticNode:
        """Assemble the semantic node for one unit.

        The text is the source slice rather than the morphemes joined, so the
        tsheg separating syllables is preserved: a joined string would not appear
        in the document and the model validator would reject it.
        """
        run = tuple(node.morpheme for node in tree.nodes[unit.start : unit.end])
        first, last = run[0], run[-1]
        span = TextSpan(
            char_start=first.span.char_start,
            char_end=last.span.char_end,
            byte_start=first.span.byte_start,
            byte_end=last.span.byte_end,
        )
        head = tree.nodes[unit.head]
        return SemanticNode(
            index=slot,
            kind=_node_kind(head.morpheme, head.is_root, head.relation),
            text=tree.source[span.char_start : span.char_end],
            span=span,
            start_index=unit.start,
            end_index=unit.end,
            head_index=unit.head,
            frames=self._frames_for(run, unit.head - unit.start),
            entity=unit.entity,
            term=unit.term,
            morphemes=run,
        )

    def _frames_for(
        self, run: tuple[TaggedMorpheme, ...], head_offset: int
    ) -> tuple[VerbFrame, ...]:
        """Look this run up in the verb lexicon.

        Only verbal material is looked up. Many Tibetan nouns are homographs of
        verb stems, and consulting the lexicon for a morpheme Stage 7 tagged as a
        noun would silently overrule that stage's judgement -- which the pipeline
        forbids.

        The whole run is tried first and the head syllable second, so a
        multi-syllable verb form is found when it is a unit and its stem is found
        when it is not.
        """
        head = run[head_offset]
        if head.category is not PosCategory.VERB:
            return ()
        if len(run) > 1 and len(run) <= self._verbs.max_length:
            found = self._verbs.lookup(tuple(morpheme.text for morpheme in run))
            if found:
                return found
        return self._verbs.lookup((head.text,))

    # -- Edge construction ---------------------------------------------------
    @staticmethod
    def _build_edge(
        layout: _Layout,
        unit_index: int,
        slot: int,
        nodes: tuple[SemanticNode, ...],
    ) -> SemanticEdge | None:
        """Return the edge governing one unit, or ``None`` if it heads its own component.

        The governor is the first ancestor of the unit's head that is itself a
        node -- not necessarily the immediate one, because Stage 8 may attach a
        concept to a grammatical word that this stage does not model.
        """
        tree = layout.tree
        unit = layout.units[unit_index]
        current = tree.nodes[unit.head].head
        while current != ROOT_HEAD:
            candidate = layout.owner[current]
            if candidate != unit_index and candidate in layout.position:
                governor = layout.position[candidate]
                role, evidence = _resolve_role(
                    tree, unit, nodes[governor], layout.case_tags[unit.end]
                )
                return SemanticEdge(
                    source=governor, target=slot, role=role, evidence=evidence
                )
            current = tree.nodes[current].head
        return None


# -- Free functions -----------------------------------------------------------
def _require_describes(
    label: str, annotated: str, ends: tuple[int, ...], tree: DependencyTree
) -> None:
    """Reject an annotation that does not describe ``tree``.

    Silently accepting one would produce a graph whose spans address a different
    document, which the add-in would then paint suggestions onto. A mismatch is a
    caller error and is reported as one.

    Matching text is checked first and morpheme indices second, because the
    second failure is possible even when the first passes: two analyses of the
    same string can disagree about how many morphemes it contains.

    Args:
        label: Which annotation this is, for the error message.
        annotated: The source text the annotation was produced from.
        ends: The exclusive morpheme index of each annotated run.
        tree: The tree the annotation is supposed to describe.

    Raises:
        InputValidationError: On either mismatch.
    """
    if annotated != tree.source:
        raise InputValidationError(
            f"{label} annotation describes a different source text.",
            context={
                "tree_length": len(tree.source),
                "annotation_length": len(annotated),
            },
        )
    limit = len(tree.nodes)
    for end in ends:
        if end > limit:
            raise InputValidationError(
                f"{label} annotation indexes a morpheme the tree does not have.",
                context={"end_index": end, "num_nodes": limit},
            )


def _resolve_role(
    tree: DependencyTree,
    unit: _Unit,
    governor: SemanticNode,
    case_tag: str | None,
) -> tuple[SemanticRole, RoleEvidence]:
    """Decide what part ``unit`` plays for ``governor``, and on what evidence.

    The order is by directness: an explicit case particle first, then the
    governing predicate's attested frame, then Stage 8's structural reading.
    """
    relation = tree.nodes[unit.head].relation

    if relation is DependencyRelation.ARG1:
        if case_tag == _AGENTIVE_TAG:
            return SemanticRole.AGENT, RoleEvidence.CASE
        return _absolutive(governor, SemanticRole.THEME)

    if relation is DependencyRelation.ARG2:
        return _absolutive(governor, SemanticRole.PATIENT)

    if relation is DependencyRelation.OBL:
        oblique = _CASE_ROLES.get(case_tag) if case_tag else None
        if oblique is not None:
            return oblique, RoleEvidence.CASE
        return SemanticRole.UNSPECIFIED, RoleEvidence.STRUCTURE

    role = _RELATION_ROLES.get(relation)
    if role is None:
        return SemanticRole.UNSPECIFIED, RoleEvidence.STRUCTURE
    if relation in _CASE_DRIVEN:
        return role, RoleEvidence.CASE
    return role, RoleEvidence.STRUCTURE


def _depths(tree: DependencyTree) -> list[int]:
    """Return the distance from each node to the root of ``tree``.

    :class:`~teea.nlp.dependency.DependencyTree` guarantees a single rooted,
    acyclic tree, so every chain terminates. Each node is resolved once and
    memoised, making the pass linear rather than quadratic on deep trees.
    """
    depth = [-1] * len(tree.nodes)
    for start in range(len(tree.nodes)):
        chain: list[int] = []
        current = start
        while current != ROOT_HEAD and depth[current] < 0:
            chain.append(current)
            current = tree.nodes[current].head
        level = 0 if current == ROOT_HEAD else depth[current] + 1
        for node in reversed(chain):
            depth[node] = level
            level += 1
    return depth


def _anchors(
    entities: EntityAnnotation | None, terms: TerminologyAnnotation | None
) -> list[tuple[int, int, NamedEntity | None, RecognizedTerm | None]]:
    """Return the non-overlapping runs Stages 9 and 10 identified.

    Names and terms cannot overlap within their own stage, but a name and a term
    may overlap each other. The longer run wins, because it is the more specific
    identification; on a tie the name wins, because Figure 5 runs Stage 9 first.
    Both are attached when they cover exactly the same run.
    """
    by_entity = {(e.start_index, e.end_index): e for e in (entities.entities if entities else ())}
    by_term = {(t.start_index, t.end_index): t for t in (terms.terms if terms else ())}

    candidates = sorted(
        {*by_entity, *by_term},
        key=lambda span: (span[0] - span[1], span[0], span not in by_entity),
    )
    accepted: list[tuple[int, int]] = []
    for start, end in candidates:
        if any(start < other_end and other_start < end for other_start, other_end in accepted):
            continue
        accepted.append((start, end))
    accepted.sort()
    return [
        (start, end, by_entity.get((start, end)), by_term.get((start, end)))
        for start, end in accepted
    ]


def _build_units(
    tree: DependencyTree,
    entities: EntityAnnotation | None,
    terms: TerminologyAnnotation | None,
    depths: list[int],
) -> tuple[_Unit, ...]:
    """Group the tree's nodes into units, in surface order.

    A unit's head is its member closest to the root, ties broken by position.
    That definition is what makes the contracted graph provably acyclic; see the
    module docstring.
    """
    anchors = _anchors(entities, terms)
    units: list[_Unit] = []
    cursor = 0
    for start, end, entity, term in anchors:
        for index in range(cursor, start):
            units.append(_Unit(index, index + 1, index, None, None))
        head = min(range(start, end), key=lambda index: (depths[index], index))
        units.append(_Unit(start, end, head, entity, term))
        cursor = end
    for index in range(cursor, len(tree.nodes)):
        units.append(_Unit(index, index + 1, index, None, None))
    return tuple(units)


def _owner_index(units: tuple[_Unit, ...], count: int) -> list[int]:
    """Return, for each Stage 8 node, the index of the unit containing it."""
    owner = [0] * count
    for index, unit in enumerate(units):
        for node in range(unit.start, unit.end):
            owner[node] = index
    return owner


def _is_node(tree: DependencyTree, unit: _Unit) -> bool:
    """Whether a unit carries enough meaning to be a node.

    An anchored run always is: Stages 9 and 10 have already asserted that it
    names something or denotes a technical concept.
    """
    if unit.entity is not None or unit.term is not None:
        return True
    head = tree.nodes[unit.head]
    return (
        head.morpheme.category in _NODE_CATEGORIES
        and head.relation not in _SUPPORT_RELATIONS
    )


def _node_kind(
    morpheme: TaggedMorpheme, is_root: bool, relation: DependencyRelation
) -> SemanticNodeKind:
    """Classify a unit from how Stage 8 attached its head.

    A predicate is a verb Stage 8 made the sentence head, or one it attached with
    ``mark``, which is the relation it uses for a subordinate clause head. Both
    tests read Stage 8's own output rather than re-deriving what counts as a
    finite verb, so the two stages cannot drift apart.
    """
    if morpheme.category is PosCategory.VERB and (
        is_root or relation is DependencyRelation.MARK
    ):
        return SemanticNodeKind.PREDICATE
    return SemanticNodeKind.CONCEPT


def _case_tags(tree: DependencyTree) -> list[str | None]:
    """Return, for each position, the case particle marking the unit ending there.

    ``result[i]`` is the tag of the particle that a unit ending just before ``i``
    is marked by, or ``None`` when nothing marks it. ``result`` has one entry
    more than the tree, so a unit ending at the last morpheme reads ``None``
    without a bounds check.

    The particle may be separated from its host by modifiers, as in *noun +
    adjective + case*, so a position occupied by phrase-internal material takes
    the answer from the position after it, and anything else closes the phrase.
    This mirrors how Stage 8 found the particle in the first place, but reads
    only the relations Stage 8 published rather than repeating its internal
    rules.

    Computed as one backward pass rather than a forward scan per node. The scan
    is quadratic on a long run of modifiers -- measured at 968 ms for 3,200
    consecutive adjectives, which breaches NFR 5.1 -- and the recurrence gives
    the same answers in linear time.
    """
    tags: list[str | None] = [None] * (len(tree.nodes) + 1)
    for index in range(len(tree.nodes) - 1, -1, -1):
        node = tree.nodes[index]
        if node.relation is DependencyRelation.CASE:
            tags[index] = node.tag
        elif node.relation in _PHRASE_INTERNAL:
            tags[index] = tags[index + 1]
    return tags


def _absolutive(
    governor: SemanticNode, structural: SemanticRole
) -> tuple[SemanticRole, RoleEvidence]:
    """Decide the role of an unmarked argument from the predicate's frame.

    Tibetan writes no particle on the absolutive, so nothing in the sentence
    distinguishes the object of a transitive clause from the subject of an
    intransitive one. The verb's attested valency does. Where the lexicon is
    silent, Stage 8's structural reading is carried through unchanged and
    recorded as such rather than being presented as a lexical finding.
    """
    judgement = governor.is_transitive
    if judgement is True:
        return SemanticRole.PATIENT, RoleEvidence.LEXICON
    if judgement is False:
        return SemanticRole.THEME, RoleEvidence.LEXICON
    return structural, RoleEvidence.STRUCTURE


def _classify_intent(morphemes: tuple[TaggedMorpheme, ...]) -> SentenceIntent:
    """Classify Figure 5's *Intent Analysis* from the sentence's own morphology.

    Interrogative marking outranks imperative marking, because the question
    particle scopes over the clause it closes while an imperative stem is a
    property of the verb inside it. Declarative is what remains when neither is
    marked, which is what "unmarked" means.
    """
    tags = [morpheme.tag for morpheme in morphemes]
    present = set(tags)

    if present & _INTERROGATIVE_TAGS:
        mood = SentenceMood.INTERROGATIVE
    elif present & _IMPERATIVE_TAGS:
        mood = SentenceMood.IMPERATIVE
    else:
        mood = SentenceMood.DECLARATIVE

    seen: dict[str, None] = {}
    for tag in tags:
        if tag in _INTENT_TAGS:
            seen[tag] = None

    return SentenceIntent(
        mood=mood,
        polarity=(
            Polarity.NEGATIVE if present & _NEGATION_TAGS else Polarity.AFFIRMATIVE
        ),
        is_reported=bool(present & _REPORTED_TAGS),
        evidence=tuple(seen),
    )


__all__ = ["TibetanSemanticAnalyzer"]
