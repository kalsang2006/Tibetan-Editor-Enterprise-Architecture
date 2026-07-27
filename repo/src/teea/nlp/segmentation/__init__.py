"""TEEA sentence segmentation module (Language pipeline Stage 4).

Stage 4 decomposes a normalized document into sentences, the unit of work for
every linguistic stage that follows and the unit of invalidation for incremental
re-parsing (SRS 3.1, FR-4).

Public API:

* :class:`SentenceSegmenter` -- the abstraction downstream code depends on.
* :class:`TibetanSentenceSegmenter` -- the rule-based implementation.
* Domain models: :class:`SegmentedText`, :class:`Sentence`.

This module depends only on :mod:`teea.core`. It does not import from
:mod:`teea.nlp.tokenization`: Stage 4 precedes Stage 5, and keeping the
dependency out preserves the one-directional flow of the pipeline.

Typical usage, wiring Stage 2 -> Stage 4 -> Stage 5::

    from teea.core import load_settings
    from teea.nlp.segmentation import TibetanSentenceSegmenter
    from teea.nlp.tokenization import TextNormalizer, TiBERTTokenizer

    settings = load_settings()

    # Stage 2: normalize, preserving line structure for the segmenter.
    normalizer = TextNormalizer(
        form=settings.tokenization.normalization_form,
        collapse_whitespace=False,
    )
    normalized = normalizer.normalize(raw_document)

    # Stage 4: split into sentences.
    segmented = TibetanSentenceSegmenter().segment(normalized)

    # Stage 5: tokenize each sentence, which now fits the 512-token limit.
    tokenizer = TiBERTTokenizer(settings.tokenization)
    encodings = [tokenizer.encode(s.text) for s in segmented.sentences]

Note the ``collapse_whitespace=False`` above: the default normalizer folds
newlines away, which would erase the paragraph boundaries this stage relies on.
"""

from __future__ import annotations

from teea.nlp.segmentation.interfaces import SentenceSegmenter
from teea.nlp.segmentation.models import SegmentedText, Sentence
from teea.nlp.segmentation.sentence import TibetanSentenceSegmenter

__all__ = [
    "SegmentedText",
    "Sentence",
    "SentenceSegmenter",
    "TibetanSentenceSegmenter",
]
