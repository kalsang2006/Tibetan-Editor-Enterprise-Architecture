"""TEEA immutable document snapshot module (Language pipeline Stage 12).

Stage 12 is the last stage of Figure 5 and the boundary out of the Language
Server: *"Immutable Document Snapshot · Store parsed representation · Shared by
plugins · Read-only centralized processing state"*, with the band below it
reading *"All plugins consume the centralized immutable snapshot concurrently"*.
The Level-1 Data Flow Diagram labels the same object "Parsed Tokens / Graph" on
the edge from the Language Server to the Plugin Runtime.

It performs no linguistic analysis. What it adds is the document: one object
holding every per-sentence artifact, the translation from sentence-relative spans
to document coordinates, and the per-sentence content hashes that let an edit
re-parse only what it touched (SRS 3.1, FR-4). See ADR-016.

Public API:

* :class:`DocumentAnalyzer` -- the abstraction downstream code depends on.
* :class:`LanguageServerSnapshotBuilder` -- the composition root of Stages 04-11.
* Domain models: :class:`DocumentSnapshot`, :class:`SentenceAnalysis`.
* :func:`sentence_hash` -- the FR-4 cache key.

Typical usage, the whole Language Server in five lines::

    from teea.nlp.snapshot import LanguageServerSnapshotBuilder
    from teea.nlp.tokenization import TextNormalizer

    normalizer = TextNormalizer(form="NFC", collapse_whitespace=False)  # Stage 02
    builder = LanguageServerSnapshotBuilder()                           # Stages 04-11

    snapshot = builder.analyze(normalizer.normalize(document))
    snapshot.num_sentences
    snapshot.analysis_at_char(cursor)            # what is the user editing?
    snapshot.analyses_overlapping(start, end)    # what did this edit invalidate?

    # After the user types, re-analyse only what changed (FR-4).
    snapshot = builder.reanalyze(snapshot, normalizer.normalize(edited))

Spans inside an analysis are relative to their sentence, because that is the unit
every stage from 06 onward works on. Translate before addressing the document::

    analysis = snapshot.analyses[0]
    for node in analysis.graph.nodes:
        where = analysis.document_span(node.span)   # now a document offset
"""

from __future__ import annotations

from teea.nlp.snapshot.builder import LanguageServerSnapshotBuilder
from teea.nlp.snapshot.hashing import DIGEST_SIZE, sentence_hash
from teea.nlp.snapshot.interfaces import DocumentAnalyzer
from teea.nlp.snapshot.models import DocumentSnapshot, SentenceAnalysis

__all__ = [
    "DIGEST_SIZE",
    "DocumentAnalyzer",
    "DocumentSnapshot",
    "LanguageServerSnapshotBuilder",
    "SentenceAnalysis",
    "sentence_hash",
]
