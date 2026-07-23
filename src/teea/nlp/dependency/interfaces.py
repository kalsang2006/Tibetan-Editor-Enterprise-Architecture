"""The dependency parser abstraction (interface) for TEEA.

The Language Server drives Stage 8 through this protocol rather than a concrete
class, consistent with every other stage. SRS 3.3 requires that models sit behind
"clear abstract API adapters, enabling immediate hot-swapping", and dependency
parsing is the stage most likely to gain a statistical implementation later: the
shipped parser is deterministic and rule-based, but a transition-based or
graph-based parser served through the AI Runtime satisfies this same contract.

The interface takes Stage 7 output rather than raw text because attachment
decisions are driven by part of speech and case marking. Accepting a bare string
would mean re-running Stages 2 through 7 internally and discarding the analysis
the pipeline has already paid for.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from teea.nlp.dependency.models import DependencyTree
from teea.nlp.postagging import TaggedText


@runtime_checkable
class DependencyParser(Protocol):
    """A Tibetan structural dependency parser contract.

    Implementations must be safe to share across threads for read-only use, as
    the daemon parses many sentences concurrently.
    """

    def parse(self, tagged: TaggedText) -> DependencyTree:
        """Build the dependency tree for one tagged sentence.

        Implementations must be total: an empty :class:`TaggedText` yields an
        empty :class:`DependencyTree` rather than raising, matching the
        convention set by the segmenters, the morphological analyzer and the
        tagger.

        Every morpheme in the input must appear as exactly one node, in the same
        order, with its span unchanged. Stage 8 adds structure over Stage 7's
        analysis; it never re-segments or re-tags. Changing either would invert
        the one-directional pipeline flow of Figures 1 and 5.

        The result is always a single rooted, acyclic tree. A morpheme that no
        rule can attach is recorded with
        :attr:`~teea.nlp.dependency.models.DependencyRelation.DEP` rather than
        being dropped or silently given a plausible-looking relation.

        Args:
            tagged: Stage 7 output for one sentence.

        Returns:
            The dependency analysis.
        """
        ...


__all__ = ["DependencyParser"]
