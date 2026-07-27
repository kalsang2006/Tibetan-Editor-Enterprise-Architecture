"""TEEA structural dependency mapping module (Language pipeline Stage 8).

Stage 8 turns the flat sequence of tagged morphemes from Stage 7 into a rooted
dependency tree, identifying which nominals are the arguments of which verb.
Figure 1 and Figure 2 both list it as a Language Server sub-module ("Dependency
Parsing" / "Dependency Parser"), and SRS 3.1 places it last in the mandated
analysis stack: Normalization -> Word Tokenization -> Morphological Parsing ->
Part-of-Speech Tagging -> **Structural Dependency Mapping**.

Public API:

* :class:`DependencyParser` -- the abstraction downstream code depends on.
* :class:`TibetanDependencyParser` -- the rule-based implementation.
* Domain models: :class:`DependencyTree`, :class:`DependencyNode`,
  :class:`DependencyRelation`.

Typical usage, completing the pipeline::

    from teea.nlp.dependency import DependencyRelation, TibetanDependencyParser
    from teea.nlp.morphology import TibetanMorphologicalAnalyzer
    from teea.nlp.postagging import HmmPosTagger
    from teea.nlp.segmentation import TibetanSentenceSegmenter
    from teea.nlp.tokenization import TextNormalizer

    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False)
    segmenter = TibetanSentenceSegmenter()
    analyzer = TibetanMorphologicalAnalyzer()
    tagger = HmmPosTagger()
    parser = TibetanDependencyParser()

    for sentence in segmenter.segment(normalizer.normalize(raw)).sentences:
        tree = parser.parse(tagger.tag(analyzer.analyze(sentence.text)))
        tree.subjects          # Figure 5: subject detection
        tree.objects           # Figure 5: object detection
        tree.root              # the clause head, verb-final in Tibetan

The relation inventory follows the Universal Dependencies labels used by the
Tibetan constraint grammars in the authoritative data repository; see
:mod:`teea.nlp.dependency.parser` for how those rules map onto this
implementation.
"""

from __future__ import annotations

from teea.nlp.dependency.interfaces import DependencyParser
from teea.nlp.dependency.models import (
    ROOT_HEAD,
    DependencyNode,
    DependencyRelation,
    DependencyTree,
)
from teea.nlp.dependency.parser import TibetanDependencyParser

__all__ = [
    "ROOT_HEAD",
    "DependencyNode",
    "DependencyParser",
    "DependencyRelation",
    "DependencyTree",
    "TibetanDependencyParser",
]
