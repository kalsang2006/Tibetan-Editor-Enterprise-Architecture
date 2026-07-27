"""The terminology recogniser abstraction (interface) for TEEA.

The Language Server drives Stage 10 through this protocol rather than a concrete
class, consistent with every other stage. Step 6 of the UML Sequence Diagram
shows the Language Server performing a "Terminology Lookup" against the Storage
Platform; this protocol is the shape of that call inside the daemon.

Like Stage 9, it takes Stage 8 output, continuing the chain in which each stage
consumes its predecessor. Terminology matching needs the morpheme sequence, and
the tree carries it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from teea.nlp.dependency import DependencyTree
from teea.nlp.terminology.models import TerminologyAnnotation


@runtime_checkable
class TerminologyRecognizer(Protocol):
    """A Tibetan terminology recogniser contract.

    Implementations must be safe to share across threads for read-only use.
    """

    def recognize(self, tree: DependencyTree) -> TerminologyAnnotation:
        """Find every technical term in one parsed sentence.

        Implementations must be total: an empty tree yields an empty annotation
        rather than raising, matching every earlier stage.

        Terms must be returned in surface order, must not overlap, and each must
        carry the exact span of the text it covers. Stage 10 annotates; it never
        re-segments, re-tags or re-parses.

        Args:
            tree: Stage 8 output for one sentence.

        Returns:
            The terms found.
        """
        ...


__all__ = ["TerminologyRecognizer"]
