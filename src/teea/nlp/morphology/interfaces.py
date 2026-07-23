"""The morphological analyzer abstraction (interface) for TEEA.

The Language Server drives Stage 6 through this protocol rather than a concrete
class, exactly as it does for tokenization and sentence segmentation. High-level
policy depends on the abstraction; the implementation is injected.

That matters concretely here. The rule-based analyzer in this package is
deliberately conservative because it has no lexicon: it cannot decide whether a
trailing ``ས`` is the agentive particle or part of the root, since ``ལས`` is the
ablative particle while ``སངས`` is a root. Figure 2 places a **Dictionary
Repository** ("Tibetan lexicon & lemma store, Morphological rules catalog") in
the Persistence layer for precisely this purpose, and the UML Sequence Diagram
shows the Language Server performing a Dictionary Lookup at step 6. When that
layer is built, a lexicon-backed analyzer can satisfy this same protocol and be
substituted without touching a single consumer.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from teea.nlp.morphology.models import MorphologicalAnalysis


@runtime_checkable
class MorphologicalAnalyzer(Protocol):
    """A Tibetan morphological analyzer contract.

    Implementations must be stateless, or at minimum safe to share across
    threads for read-only use, because the daemon analyses many sentences
    concurrently.
    """

    def analyze(self, text: str) -> MorphologicalAnalysis:
        """Decompose ``text`` into roots and affixes.

        Implementations must be total: any input, including empty or
        punctuation-only text, yields a :class:`MorphologicalAnalysis` rather
        than raising. Morphological analysis is a deterministic inspection with
        no failure mode of its own, matching the convention set by the
        segmenters in earlier stages.

        Args:
            text: Normalized Tibetan text, typically one sentence from Stage 4.
                Offsets in the result are relative to this exact string.

        Returns:
            The analysis result.
        """
        ...


__all__ = ["MorphologicalAnalyzer"]
