"""TEEA morphological analysis module (Language pipeline Stage 6).

Stage 6 decomposes tokenized Tibetan into roots and grammatical affixes. Figure 1
and Figure 2 both list it as a Language Server sub-module ("Morphological
Analysis" / "Morphology"), and SRS 3.1 fixes its position in the mandatory
analysis stack: Word Tokenization -> **Morphological Parsing** -> POS Tagging.

Public API:

* :class:`MorphologicalAnalyzer` -- the abstraction downstream code depends on.
* :class:`TibetanMorphologicalAnalyzer` -- the rule-based implementation.
* Domain models: :class:`MorphologicalAnalysis`, :class:`Morpheme`,
  :class:`MorphemeKind`, :class:`AffixCategory`.

The affix inventory is derived from the annotated corpus in the project's
authoritative data repository, not hand-authored; see
:mod:`teea.nlp.morphology.particles`.

Typical usage, wiring Stage 4 -> Stage 6::

    from teea.nlp.morphology import TibetanMorphologicalAnalyzer
    from teea.nlp.segmentation import TibetanSentenceSegmenter

    analyzer = TibetanMorphologicalAnalyzer()
    for sentence in TibetanSentenceSegmenter().segment(normalized).sentences:
        analysis = analyzer.analyze(sentence.text)
        analysis.root_text        # lexical material, affixes stripped
        analysis.affixes          # recognized grammatical morphemes
        analysis.has_ambiguity    # True when Stage 7 must disambiguate

Stage 6 recognizes; it does not guess. Roughly a quarter of Tibetan affix
surfaces also occur as ordinary content words, so those are reported as
:attr:`MorphemeKind.AMBIGUOUS` and left for part-of-speech tagging to resolve.
"""

from __future__ import annotations

from teea.nlp.morphology.analyzer import TibetanMorphologicalAnalyzer
from teea.nlp.morphology.interfaces import MorphologicalAnalyzer
from teea.nlp.morphology.models import (
    AffixCategory,
    Morpheme,
    MorphemeKind,
    MorphologicalAnalysis,
)

__all__ = [
    "AffixCategory",
    "Morpheme",
    "MorphemeKind",
    "MorphologicalAnalysis",
    "MorphologicalAnalyzer",
    "TibetanMorphologicalAnalyzer",
]
