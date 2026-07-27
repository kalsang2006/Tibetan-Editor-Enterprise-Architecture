"""Plagiarism detection abstractions for TEEA.

Two protocols define the subsystem boundary:

* :class:`PlagiarismDetector` -- what a consumer (or the feature plugin) calls.
* :class:`FingerprintIndex` -- the storage abstraction for fingerprints.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from teea.plagiarism.models import MatchResult, SourceDocument


@runtime_checkable
class FingerprintIndex(Protocol):
    """A storage index mapping hashes to the documents that contain them.

    Implementations must be safe to share across threads for read-only use.

    This is the core data structure that makes plagiarism detection efficient:
    rather than comparing every fingerprint of the query against every fingerprint
    of every corpus document, we look up query hashes in the index and only score
    the documents that share at least one hash.
    """

    def add(self, document: SourceDocument) -> None:
        """Index the fingerprints of a source document.

        Incremental: adding the same document twice is a no-op.
        """
        ...

    def add_many(self, documents: Iterable[SourceDocument]) -> None:
        """Index many documents at once."""
        ...

    def remove(self, document_id: str) -> bool:
        """Remove a document and its fingerprints from the index.

        Returns ``True`` if the document was present.
        """
        ...

    def lookup(self, fingerprint: int) -> Sequence[str]:
        """Return the document ids whose fingerprint set contains ``fingerprint``.

        Returns an empty sequence when no document matches.
        """
        ...

    def lookup_many(self, fingerprints: Iterable[int]) -> dict[int, Sequence[str]]:
        """Batch version of :meth:`lookup`.

        Returns a dict mapping each queried hash to the document ids that
        contain it.  Hashes that match nothing are absent from the result.
        """
        ...

    @property
    def size(self) -> int:
        """Number of source documents currently indexed."""
        ...

    @property
    def total_fingerprints(self) -> int:
        """Total number of fingerprints across all indexed documents."""
        ...

    def clear(self) -> None:
        """Remove every document from the index."""
        ...

    def document_ids(self) -> Iterable[str]:
        """Return the ids of all indexed documents."""
        ...


@runtime_checkable
class PlagiarismDetector(Protocol):
    """A plagiarism detection engine.

    Implementations must be safe to share across threads for read-only use.

    The detector compares a query document's text against an indexed corpus
    and returns scored matches ranked by similarity.
    """

    def detect(self, text: str, *, min_similarity: float = 0.1) -> MatchResult:
        """Detect plagiarism in ``text`` against the indexed corpus.

        Args:
            text: The query document text.
            min_similarity: Minimum similarity score for a match to be
                reported (``0.0`` = no minimum, ``1.0`` = exact match).

        Returns:
            A result containing all matches that meet the threshold, ranked
            by similarity descending.
        """
        ...

    @property
    def index(self) -> FingerprintIndex:
        """The underlying fingerprint index."""
        ...


__all__ = ["FingerprintIndex", "PlagiarismDetector"]
