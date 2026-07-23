"""The sentence segmenter abstraction (interface) for TEEA.

The Language Server orchestrates Stage 4 through this protocol rather than
through a concrete class, exactly as it does for tokenization. That is the
Dependency Inversion Principle applied consistently: high-level policy depends
on an abstraction, and the concrete segmenter is injected.

This matters more here than it might appear. The current implementation is
deterministic and rule-based, which is the correct choice for classical Tibetan
where the shad is an explicit orthographic terminator. Modern or transcribed
Tibetan may eventually warrant a statistical boundary detector. Because the
Language Server depends only on this protocol, such an implementation can be
introduced without touching any consumer.

The interface is deliberately minimal (Interface Segregation): one operation.
Normalization is *not* part of it -- that is Stage 2's job, owned by
:class:`~teea.nlp.tokenization.normalization.TextNormalizer`, and duplicating it
here would violate the pipeline's separation of stages.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from teea.nlp.segmentation.models import SegmentedText


@runtime_checkable
class SentenceSegmenter(Protocol):
    """A Tibetan sentence segmenter contract.

    Implementations must be stateless, or at minimum safe to share across
    threads for read-only use, because the daemon segments many documents
    concurrently.
    """

    def segment(self, text: str) -> SegmentedText:
        """Split ``text`` into sentences.

        Implementations must be total: any input, including empty or
        punctuation-only text, yields a :class:`SegmentedText` rather than an
        exception. Segmentation is a deterministic scan with no failure mode of
        its own, and this mirrors
        :class:`~teea.nlp.tokenization.syllable.SyllableSegmenter`.

        Args:
            text: Normalized text (pipeline Stage 2 output). Offsets in the
                result are expressed relative to this exact string.

        Returns:
            The segmentation result.
        """
        ...


__all__ = ["SentenceSegmenter"]
