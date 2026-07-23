"""TEEA part-of-speech tagging module (Language pipeline Stage 7).

Stage 7 labels each morpheme with its part of speech and, in doing so, resolves
what Stage 6 deliberately left open. Figure 1 and Figure 2 both list it as a
Language Server sub-module ("POS Tagging" / "POS Tagger"), and SRS 3.1 fixes its
position: Morphological Parsing -> **Part-of-Speech Tagging** -> Structural
Dependency Mapping.

Public API:

* :class:`PosTagger` -- the abstraction downstream code depends on.
* :class:`HmmPosTagger` -- the corpus-derived implementation.
* Domain models: :class:`TaggedText`, :class:`TaggedMorpheme`,
  :class:`PosCategory`, :func:`coarse_category`.

Typical usage, wiring Stage 4 -> 6 -> 7::

    from teea.nlp.morphology import TibetanMorphologicalAnalyzer
    from teea.nlp.postagging import HmmPosTagger, PosCategory
    from teea.nlp.segmentation import TibetanSentenceSegmenter

    analyzer = TibetanMorphologicalAnalyzer()
    tagger = HmmPosTagger()

    for sentence in TibetanSentenceSegmenter().segment(normalized).sentences:
        tagged = tagger.tag(analyzer.analyze(sentence.text))
        tagged.of_category(PosCategory.VERB)   # what a grammar checker wants
        tagged.num_resolved                    # ambiguities this stage decided

Statistics come from the Dictionary Repository in :mod:`teea.persistence`, which
is derived from the annotated corpus rather than hand-authored.
"""

from __future__ import annotations

from teea.nlp.postagging.interfaces import PosTagger
from teea.nlp.postagging.models import (
    PosCategory,
    TaggedMorpheme,
    TaggedText,
    coarse_category,
)
from teea.nlp.postagging.tagger import HmmPosTagger

__all__ = [
    "HmmPosTagger",
    "PosCategory",
    "PosTagger",
    "TaggedMorpheme",
    "TaggedText",
    "coarse_category",
]
