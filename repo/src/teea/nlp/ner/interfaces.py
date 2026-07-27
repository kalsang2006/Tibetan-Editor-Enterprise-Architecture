"""The named entity recogniser abstraction (interface) for TEEA.

The Language Server drives Stage 9 through this protocol rather than a concrete
class, consistent with every other stage. SRS 3.3 requires models to sit behind
"clear abstract API adapters, enabling immediate hot-swapping", and entity
recognition is a natural candidate for a statistical implementation once a
labelled resource exists: the shipped recogniser is gazetteer-driven, but a
sequence model served through the AI Runtime satisfies this same contract.

The interface takes Stage 8 output, continuing the chain in which each stage
consumes its predecessor. Every node of the tree carries its tagged morpheme, so
nothing the recogniser needs is lost, and the ordering matches Figure 5.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from teea.nlp.dependency import DependencyTree
from teea.nlp.ner.models import EntityAnnotation


@runtime_checkable
class EntityRecognizer(Protocol):
    """A Tibetan named entity recogniser contract.

    Implementations must be safe to share across threads for read-only use, as
    the daemon analyses many sentences concurrently.
    """

    def recognize(self, tree: DependencyTree) -> EntityAnnotation:
        """Find every named entity in one parsed sentence.

        Implementations must be total: an empty tree yields an empty
        :class:`EntityAnnotation` rather than raising, matching the convention
        set by every earlier stage.

        Entities must be returned in surface order and must not overlap, and
        each must carry the exact span of the text it covers. Stage 9 annotates;
        it never re-segments, re-tags or re-parses.

        Args:
            tree: Stage 8 output for one sentence.

        Returns:
            The entities found.
        """
        ...


__all__ = ["EntityRecognizer"]
