"""TEEA Plagiarism Detection Subsystem (Figure 8).

The subsystem uses the **Robust Winnowing** algorithm to generate document
fingerprints, indexes them, and detects overlapping text between a query
document and an indexed corpus.

Public API:
    * :class:`PlagiarismDetector` -- the detection protocol.
    * :class:`FingerprintIndex` -- the fingerprint storage protocol.
    * :class:`PlagiarismEngine` -- the full detection orchestrator.
    * :func:`normalize_and_fingerprint` -- one-shot fingerprint generation.
    * :func:`jaccard_containment` -- asymmetric set-overlap metric.
    * :class:`SourceDocument` -- a corpus document and its fingerprints.
    * :class:`FingerprintMatch` -- one match against the corpus.
    * :class:`MatchResult` -- scored results for one query.
"""

from __future__ import annotations

from teea.plagiarism.engine import PlagiarismEngine
from teea.plagiarism.fingerprinting import normalize_and_fingerprint
from teea.plagiarism.index import InMemoryFingerprintIndex
from teea.plagiarism.interfaces import FingerprintIndex, PlagiarismDetector
from teea.plagiarism.models import Fingerprint, FingerprintMatch, MatchResult, SourceDocument
from teea.plagiarism.similarity import jaccard_containment

__all__ = [
    "Fingerprint",
    "FingerprintIndex",
    "FingerprintMatch",
    "InMemoryFingerprintIndex",
    "MatchResult",
    "PlagiarismDetector",
    "PlagiarismEngine",
    "SourceDocument",
    "jaccard_containment",
    "normalize_and_fingerprint",
]
