"""In-memory fingerprint index for plagiarism detection.

This is the Figure 8 "Fingerprint Database" / "Hash Index" implemented
as an in-memory hash map for offline, deterministic operation (ADR-002).

Design
------
The index uses a simple ``dict[int, set[str]]`` mapping each fingerprint
hash to the set of document ids that contain it.  Lookup is O(1) per hash,
and query evaluation is O(overlap_sum) where overlap_sum is the total
number of candidate-document pairs produced by all query hashes.

The index is not persisted to disk in this implementation.  A production
SQLite-backed version would replace this class without changing any code
that depends on the :class:`~teea.plagiarism.interfaces.FingerprintIndex`
protocol.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from teea.plagiarism.models import SourceDocument


class InMemoryFingerprintIndex:
    """An in-memory hash → docId index.

    Satisfies the :class:`FingerprintIndex` protocol.  Thread-safe for
    read-only operations; mutations must be externally synchronized (the
    caller is the daemon, which is single-threaded for index maintenance).
    """

    def __init__(self) -> None:
        #: hash → set of document ids
        self._index: dict[int, set[str]] = {}
        #: document_id → document metadata
        self._documents: dict[str, SourceDocument] = {}
        self._total_fingerprints: int = 0

    # -- Mutation --------------------------------------------------------

    def add(self, document: SourceDocument) -> None:
        """Index a document. Idempotent: no-op if already present."""
        if document.document_id in self._documents:
            return
        self._documents[document.document_id] = document
        for h in document.fingerprints:
            self._index.setdefault(h, set()).add(document.document_id)
        self._total_fingerprints += len(document.fingerprints)

    def add_many(self, documents: Iterable[SourceDocument]) -> None:
        """Index multiple documents."""
        for doc in documents:
            self.add(doc)

    def remove(self, document_id: str) -> bool:
        """Remove a document from the index. Returns True if it existed."""
        doc = self._documents.pop(document_id, None)
        if doc is None:
            return False
        for h in doc.fingerprints:
            ids = self._index.get(h)
            if ids is not None:
                ids.discard(document_id)
                if not ids:
                    del self._index[h]
        self._total_fingerprints -= len(doc.fingerprints)
        return True

    def clear(self) -> None:
        """Remove all documents from the index."""
        self._index.clear()
        self._documents.clear()
        self._total_fingerprints = 0

    # -- Query -----------------------------------------------------------

    def lookup(self, fingerprint: int) -> Sequence[str]:
        """Return document ids that contain this fingerprint hash."""
        ids = self._index.get(fingerprint)
        return tuple(sorted(ids)) if ids else ()

    def lookup_many(self, fingerprints: Iterable[int]) -> dict[int, Sequence[str]]:
        """Batch lookup: returns a dict mapping each hash to matching doc ids."""
        result: dict[int, Sequence[str]] = {}
        for h in fingerprints:
            ids = self._index.get(h)
            if ids:
                result[h] = tuple(sorted(ids))
        return result

    # -- Introspection ---------------------------------------------------

    @property
    def size(self) -> int:
        """Number of documents in the index."""
        return len(self._documents)

    @property
    def total_fingerprints(self) -> int:
        """Total number of fingerprint hashes across all documents."""
        return self._total_fingerprints

    def document_ids(self) -> Iterable[str]:
        """Return all stored document ids."""
        return tuple(self._documents.keys())

    def get_document(self, document_id: str) -> SourceDocument | None:
        """Return a stored document by id, or ``None``."""
        return self._documents.get(document_id)


__all__ = ["InMemoryFingerprintIndex"]
