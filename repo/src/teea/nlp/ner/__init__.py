"""TEEA named entity recognition module (Language pipeline Stage 9).

Stage 9 finds the names in a parsed sentence. Figure 1 lists "Named Entity
Recognition" as a Language Server sub-module and Figure 5 places it at stage 9,
after dependency parsing.

Public API:

* :class:`EntityRecognizer` -- the abstraction downstream code depends on.
* :class:`TibetanEntityRecognizer` -- the gazetteer-driven implementation.
* Domain models: :class:`EntityAnnotation`, :class:`NamedEntity`,
  :class:`EntityEvidence`.

Entities are **untyped**. Figure 5 names five categories (person, place,
organisation, religious, cultural), but no available data source distinguishes
them, so this stage reports that a run of text is a name without guessing what
kind. See ADR-011.

Typical usage, completing the analysis chain::

    from teea.nlp.ner import TibetanEntityRecognizer

    recognizer = TibetanEntityRecognizer()
    tree = parser.parse(tagger.tag(analyzer.analyze(sentence.text)))
    annotation = recognizer.recognize(tree)

    annotation.texts               # the names found
    annotation.entity_at_char(12)  # which name covers an offset
"""

from __future__ import annotations

from teea.nlp.ner.interfaces import EntityRecognizer
from teea.nlp.ner.models import EntityAnnotation, EntityEvidence, NamedEntity
from teea.nlp.ner.recognizer import TibetanEntityRecognizer

__all__ = [
    "EntityAnnotation",
    "EntityEvidence",
    "EntityRecognizer",
    "NamedEntity",
    "TibetanEntityRecognizer",
]
