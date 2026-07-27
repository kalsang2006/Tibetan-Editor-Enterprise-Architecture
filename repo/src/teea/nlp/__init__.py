"""TEEA natural-language processing layer.

This subpackage groups the Tibetan NLP components of the platform. It currently
exposes:

* :mod:`teea.nlp.segmentation` -- Stage 4, sentence segmentation.
* :mod:`teea.nlp.tokenization` -- Stage 5 (TiBERT-backed word tokenization),
  together with Stage 2 Unicode normalization and tsheg-based syllable
  segmentation.

Subsequent language-processing stages (document cleaning, morphological
analysis, POS tagging, dependency parsing, named entity recognition,
terminology recognition and semantic analysis) are added as sibling modules
under this package as they are implemented.

The NLP layer depends only on :mod:`teea.core` for its cross-cutting concerns
(configuration, logging, error taxonomy and shared domain types). It never
depends on higher layers (AI Runtime, Plugin Runtime, Suggestion Fusion Engine,
IPC or the Office.js add-in), preserving the one-directional dependency flow of
the architecture.
"""

from __future__ import annotations

__all__: list[str] = []
