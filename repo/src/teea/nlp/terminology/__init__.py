"""TEEA terminology recognition module (Language pipeline Stage 10).

Stage 10 marks the technical vocabulary in a parsed sentence, so that downstream
plugins can treat it specially: a spell checker must not flag a term, and a
translator must render it consistently.

Figure 5 defines the stage as *"Technical Terms · Buddhist Vocabulary · User
Dictionary"*. Step 6 of the UML Sequence Diagram shows the Language Server
performing a "Terminology Lookup" against the Storage Platform, and the
Deployment Diagram lists "Grammar & Terminology" among the Dictionary Repo's
deployed contents.

Public API:

* :class:`TerminologyRecognizer` -- the abstraction downstream code depends on.
* :class:`GlossaryTerminologyRecognizer` -- the shipped implementation.
* Domain models: :class:`TerminologyAnnotation`, :class:`RecognizedTerm`.

Typical usage, including a user dictionary::

    from teea.nlp.terminology import GlossaryTerminologyRecognizer
    from teea.persistence import InMemoryTerminology, TermSource

    repository = InMemoryTerminology(user_terms=[("རྟེན", "འབྲེལ")])
    recognizer = GlossaryTerminologyRecognizer(terminology=repository)

    annotation = recognizer.recognize(tree)
    annotation.texts                                   # the terms found
    annotation.of_source(TermSource.USER_DICTIONARY)   # the user's own
"""

from __future__ import annotations

from teea.nlp.terminology.interfaces import TerminologyRecognizer
from teea.nlp.terminology.models import RecognizedTerm, TerminologyAnnotation
from teea.nlp.terminology.recognizer import GlossaryTerminologyRecognizer

__all__ = [
    "GlossaryTerminologyRecognizer",
    "RecognizedTerm",
    "TerminologyAnnotation",
    "TerminologyRecognizer",
]
