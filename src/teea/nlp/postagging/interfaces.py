"""The part-of-speech tagger abstraction (interface) for TEEA.

The Language Server drives Stage 7 through this protocol rather than a concrete
class, consistent with every other stage. The abstraction earns its place here:
the shipped tagger is a corpus-derived HMM, but SRS 3.3 requires that models sit
behind "clear abstract API adapters, enabling immediate hot-swapping", and the
AI Runtime exists precisely to serve alternative implementations. A neural tagger
served through the AI Runtime satisfies this same protocol.

The interface takes Stage 6 output rather than raw text on purpose. Tagging needs
morpheme boundaries and the candidate grammatical categories Stage 6 identified;
accepting a bare string would either duplicate that work or discard it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from teea.nlp.morphology import MorphologicalAnalysis
from teea.nlp.postagging.models import TaggedText


@runtime_checkable
class PosTagger(Protocol):
    """A Tibetan part-of-speech tagger contract.

    Implementations must be safe to share across threads for read-only use, as
    the daemon tags many sentences concurrently.
    """

    def tag(self, analysis: MorphologicalAnalysis) -> TaggedText:
        """Assign a part of speech to every morpheme of ``analysis``.

        Implementations must be total: an empty analysis yields an empty
        :class:`TaggedText` rather than raising, matching the convention set by
        the segmenters and the morphological analyzer.

        Every morpheme in the input must appear in the output with its span
        unchanged. Stage 7 labels; it never re-segments. Changing morpheme
        boundaries is Stage 6's responsibility, and doing it here would invert
        the one-directional pipeline flow of Figures 1 and 5.

        Args:
            analysis: Stage 6 output for one sentence.

        Returns:
            The tagged sentence.
        """
        ...


__all__ = ["PosTagger"]
