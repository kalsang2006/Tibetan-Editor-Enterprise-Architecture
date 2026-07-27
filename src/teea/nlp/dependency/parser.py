"""Rule-based Tibetan dependency parser (Language pipeline Stage 8).

Figure 5 assigns Stage 8 two jobs: *subject & object detection* and *dependency
tree construction*. SRS 3.1 places it last in the mandated analysis stack, after
part-of-speech tagging.

Why rules, and where they come from
-----------------------------------
The rules implemented here are derived from the Constraint Grammars published
for Tibetan in the project's authoritative data repository
(``Data/tibetan-nlp-tibcg3-735f770/grammars/``), which describe Tibetan
dependency structure with Universal Dependencies relations. The central pattern
in those grammars is that attachment is driven by **case marking**:

* ``SETPARENT Head_NOUN (1* (Case=Agn) ...) TO (*1 (VERB))`` -- a noun followed
  by the agentive attaches to the verb as its agent.
* ``SETPARENT Head_NOUN (NOT 1 (ADP)) TO (*1 (VERB))`` -- a bare, unmarked noun
  attaches to the verb as its absolutive argument.
* ``SETPARENT (ADJ|NUM|DET) TO (-1* Head_NOUN BARRIER LEFT_NP_BOUNDARY)`` --
  modifiers attach leftward to their head noun, because Tibetan places them
  after the noun.

That information is exactly what Stages 6 and 7 already produce: the case
particles Stage 6 recognizes and Stage 7 disambiguates *are* the attachment
signal. So this stage composes with its predecessors rather than re-deriving
anything.

The grammars themselves are not executed. Running them requires the ``vislcg3``
compiler and runtime, a C++ toolchain that would contradict the offline-first,
pure-Python daemon of SRS v5.1 (ADR-002). Their rules are reimplemented natively
instead, and this module is the record of that mapping.

Ergative alignment
------------------
Tibetan is an ergative-absolutive language, which decides how the absolutive
argument is labelled. The absolutive is the object of a transitive clause but
the subject of an intransitive one, and no morphology distinguishes the two. The
parser resolves it structurally: when an agentive-marked argument is present the
clause is transitive, so the absolutive is :attr:`DependencyRelation.ARG2`;
with no agentive it is the sole argument, so :attr:`DependencyRelation.ARG1`.
Treating the absolutive as an object unconditionally would mislabel the subject
of every intransitive sentence.

Guarantees
----------
The result is always a single rooted, acyclic tree covering every input
morpheme with its span unchanged. Anything the rules cannot attach is recorded
as :attr:`DependencyRelation.DEP` and attached to the root, so the unresolved
rate stays measurable rather than being hidden behind a plausible label.
"""

from __future__ import annotations

from teea.nlp.dependency.models import (
    ROOT_HEAD,
    DependencyNode,
    DependencyRelation,
    DependencyTree,
)
from teea.nlp.postagging import PosCategory, TaggedMorpheme, TaggedText

#: Fine-tag prefix marking a case particle in the reference tagset.
_CASE_PREFIX = "case."

#: Fine-tag prefix marking a converb, which subordinates the preceding clause.
_CONVERB_PREFIX = "cv."

#: Deverbal nouns. The constraint grammars count ``VerbForm=Vnoun`` among
#: ``Head_NOUN``, so these head noun phrases even though the coarse mapping
#: calls them verbal.
_DEVERBAL_PREFIX = "n.v."

#: Auxiliary and copula tags, which support a main verb rather than heading.
_AUXILIARY_TAGS = frozenset({"v.aux", "v.cop", "n.v.aux", "n.v.cop"})

#: Case particles that mark a core verb argument, and the relation each implies.
#: Absolutive (no particle at all) is resolved separately, by alignment.
_CASE_RELATIONS: dict[str, DependencyRelation] = {
    "case.agn": DependencyRelation.ARG1,
    "case.all": DependencyRelation.ARG3,
    "case.term": DependencyRelation.ARG3,
    "case.loc": DependencyRelation.OBL,
    "case.abl": DependencyRelation.OBL,
    "case.ela": DependencyRelation.OBL,
    "case.ass": DependencyRelation.OBL,
    "case.comp": DependencyRelation.OBL,
    "case.gen": DependencyRelation.NMOD_POSS,
}

#: Coarse classes that can head a noun phrase.
_NOMINAL_CATEGORIES = frozenset(
    {
        PosCategory.NOUN,
        PosCategory.PRONOUN,
        PosCategory.NUMERAL,
        PosCategory.DETERMINER,
        PosCategory.ADJECTIVE,
    }
)

#: Modifier classes and the relation each bears to its head noun.
_MODIFIER_RELATIONS: dict[PosCategory, DependencyRelation] = {
    PosCategory.ADJECTIVE: DependencyRelation.AMOD,
    PosCategory.NUMERAL: DependencyRelation.NUMMOD,
    PosCategory.DETERMINER: DependencyRelation.DET,
}


def _is_deverbal_noun(morpheme: TaggedMorpheme) -> bool:
    """Whether this morpheme is a deverbal noun heading a noun phrase."""
    return morpheme.tag.startswith(_DEVERBAL_PREFIX)


def _is_nominal(morpheme: TaggedMorpheme) -> bool:
    """Whether this morpheme can head a noun phrase."""
    return morpheme.category in _NOMINAL_CATEGORIES or _is_deverbal_noun(morpheme)


def _is_finite_verb(morpheme: TaggedMorpheme) -> bool:
    """Whether this morpheme can head a clause.

    Excludes deverbal nouns, which head noun phrases, and auxiliaries, which
    support a main verb rather than heading one.
    """
    return (
        morpheme.category is PosCategory.VERB
        and not _is_deverbal_noun(morpheme)
        and morpheme.tag not in _AUXILIARY_TAGS
    )


def _is_case_particle(morpheme: TaggedMorpheme) -> bool:
    """Whether this morpheme is a case particle."""
    return morpheme.tag.startswith(_CASE_PREFIX)


class TibetanDependencyParser:
    """Builds dependency trees from tagged Tibetan sentences.

    Satisfies the :class:`~teea.nlp.dependency.interfaces.DependencyParser`
    protocol. The parser holds no mutable state and is safe to share across
    threads; :meth:`parse` works entirely on local data.

    The algorithm is a single deterministic pass:

    1. Choose the root -- the last finite verb, since Tibetan is verb-final.
       With no verb, the last nominal heads the sentence.
    2. Attach each case particle to the nominal on its left, as ``case``.
    3. Attach each nominal to the root, with the relation implied by the case
       particle that follows it, or by alignment when it is unmarked.
    4. Attach modifiers leftward to their head noun, and clause-level material
       to the root.
    5. Re-attach anything left disconnected, so the result is always one tree.

    Args:
        attach_genitive_to_following_nominal: Whether a genitive-marked
            possessor attaches to the nominal on its right, which is the
            Tibetan order. Defaults to ``True``. Set to ``False`` to attach
            possessors to the clause head instead, which loses the possessive
            link but keeps every nominal a direct dependent of the verb.
    """

    def __init__(self, *, attach_genitive_to_following_nominal: bool = True) -> None:
        self._genitive_to_nominal = attach_genitive_to_following_nominal

    @property
    def attach_genitive_to_following_nominal(self) -> bool:
        """Whether possessors attach to the nominal they modify."""
        return self._genitive_to_nominal

    def parse(self, tagged: TaggedText) -> DependencyTree:
        """Build the dependency tree for ``tagged``.

        Total: an empty input yields an empty tree rather than raising.

        Args:
            tagged: Stage 7 output for one sentence.

        Returns:
            A single rooted, acyclic tree over every input morpheme.
        """
        morphemes = tagged.morphemes
        if not morphemes:
            return DependencyTree(source=tagged.source, nodes=())

        root = self._select_root(morphemes)
        heads: list[int] = [ROOT_HEAD] * len(morphemes)
        relations: list[DependencyRelation] = [DependencyRelation.DEP] * len(morphemes)

        has_agentive = any(m.tag == "case.agn" for m in morphemes)

        for index, morpheme in enumerate(morphemes):
            if index == root:
                relations[index] = DependencyRelation.ROOT
                continue
            head, relation = self._attach(
                index, morpheme, morphemes, root, has_agentive=has_agentive
            )
            heads[index] = head
            relations[index] = relation

        self._repair(heads, relations, root)

        nodes = tuple(
            DependencyNode(
                index=index,
                head=heads[index],
                relation=relations[index],
                morpheme=morpheme,
            )
            for index, morpheme in enumerate(morphemes)
        )
        return DependencyTree(source=tagged.source, nodes=nodes)

    # -- Root selection ------------------------------------------------------
    @staticmethod
    def _select_root(morphemes: tuple[TaggedMorpheme, ...]) -> int:
        """Return the index of the clause head.

        Tibetan is verb-final, so the last finite verb heads the sentence. A
        fragment with no finite verb -- a noun phrase, a heading, a list item --
        is headed by its last nominal, and failing that by its last morpheme, so
        that a tree always exists.
        """
        for index in range(len(morphemes) - 1, -1, -1):
            if _is_finite_verb(morphemes[index]):
                return index
        for index in range(len(morphemes) - 1, -1, -1):
            if _is_nominal(morphemes[index]):
                return index
        return len(morphemes) - 1

    # -- Attachment ----------------------------------------------------------
    def _attach(
        self,
        index: int,
        morpheme: TaggedMorpheme,
        morphemes: tuple[TaggedMorpheme, ...],
        root: int,
        *,
        has_agentive: bool,
    ) -> tuple[int, DependencyRelation]:
        """Return the head and relation for one morpheme."""
        if morpheme.category is PosCategory.PUNCTUATION:
            return root, DependencyRelation.PUNCT

        if _is_case_particle(morpheme):
            host = self._previous_nominal(index, morphemes)
            if host is not None:
                return host, DependencyRelation.CASE
            return root, DependencyRelation.DEP

        if morpheme.tag.startswith(_CONVERB_PREFIX):
            return root, DependencyRelation.MARK

        if morpheme.tag == "neg":
            return root, DependencyRelation.NEG

        if morpheme.category is PosCategory.ADVERB:
            return root, DependencyRelation.ADVMOD

        if morpheme.tag in _AUXILIARY_TAGS:
            return root, DependencyRelation.AUX

        if _is_finite_verb(morpheme):
            # A non-root finite verb heads a subordinate clause.
            return root, DependencyRelation.MARK

        if _is_nominal(morpheme) or _is_deverbal_noun(morpheme):
            return self._attach_nominal(index, morpheme, morphemes, root, has_agentive=has_agentive)

        return root, DependencyRelation.DEP

    def _attach_nominal(
        self,
        index: int,
        morpheme: TaggedMorpheme,
        morphemes: tuple[TaggedMorpheme, ...],
        root: int,
        *,
        has_agentive: bool,
    ) -> tuple[int, DependencyRelation]:
        """Attach a nominal, using the case particle that follows it."""
        # A modifier that follows another nominal modifies it, rather than
        # being an argument in its own right. Tibetan places adjectives,
        # numerals and determiners after the noun they modify.
        modifier = _MODIFIER_RELATIONS.get(morpheme.category)
        if modifier is not None:
            host = self._previous_nominal(index, morphemes)
            if host is not None:
                return host, modifier

        case_tag = self._following_case_tag(index, morphemes)
        if case_tag is None:
            # Absolutive. Ergative alignment decides whether it is the object of
            # a transitive clause or the subject of an intransitive one.
            return root, DependencyRelation.ARG2 if has_agentive else DependencyRelation.ARG1

        relation = _CASE_RELATIONS.get(case_tag, DependencyRelation.OBL)

        if relation is DependencyRelation.NMOD_POSS and self._genitive_to_nominal:
            possessed = self._next_nominal(index, morphemes)
            if possessed is not None:
                return possessed, DependencyRelation.NMOD_POSS
            return root, DependencyRelation.OBL

        return root, relation

    # -- Neighbour searches --------------------------------------------------
    @staticmethod
    def _previous_nominal(index: int, morphemes: tuple[TaggedMorpheme, ...]) -> int | None:
        """Return the nearest nominal to the left, or ``None``."""
        for candidate in range(index - 1, -1, -1):
            if _is_nominal(morphemes[candidate]):
                return candidate
        return None

    @staticmethod
    def _next_nominal(index: int, morphemes: tuple[TaggedMorpheme, ...]) -> int | None:
        """Return the nearest nominal to the right, or ``None``."""
        for candidate in range(index + 1, len(morphemes)):
            if _is_nominal(morphemes[candidate]):
                return candidate
        return None

    @staticmethod
    def _following_case_tag(index: int, morphemes: tuple[TaggedMorpheme, ...]) -> str | None:
        """Return the case particle marking the nominal at ``index``.

        The particle may be separated from its host by other modifiers, as in
        *noun + adjective + case*, so the search skips over nominal material and
        stops at anything that closes the phrase.
        """
        for candidate in range(index + 1, len(morphemes)):
            morpheme = morphemes[candidate]
            if _is_case_particle(morpheme):
                return morpheme.tag
            if _is_nominal(morpheme):
                # Another nominal that is itself a modifier keeps the phrase
                # open; a nominal that is not stops the search.
                if morpheme.category in _MODIFIER_RELATIONS:
                    continue
                return None
            return None
        return None

    # -- Tree repair ---------------------------------------------------------
    @staticmethod
    def _repair(heads: list[int], relations: list[DependencyRelation], root: int) -> None:
        """Re-attach any node that does not reach the root.

        Cycles are possible in principle -- two nominals could be made to point
        at each other through the modifier rules -- and a cyclic or disconnected
        result would be rejected by :class:`DependencyTree`. Rather than let a
        real document fail to parse, any node whose head chain does not reach
        the root is re-attached directly to it and recorded as unresolved. The
        pass is deterministic and runs in linear time per node.
        """
        for index in range(len(heads)):
            if index == root:
                continue
            seen: set[int] = {index}
            current = heads[index]
            while current != ROOT_HEAD and current != root:
                if current in seen:
                    break
                seen.add(current)
                current = heads[current]
            if current != root:
                heads[index] = root
                relations[index] = DependencyRelation.DEP


__all__ = ["TibetanDependencyParser"]
