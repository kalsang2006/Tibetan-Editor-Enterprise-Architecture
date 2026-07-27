"""Fingerprint repository for the persistence layer.

Provides a :class:`FingerprintRepository` protocol and an in-memory
implementation following the same pattern as the existing repositories
(:class:`DictionaryRepository`, :class:`GazetteerRepository`, etc.).

The shipped implementation stores fingerprint hashes in memory, keyed by
document id.  A future SQLite-backed version would replace this without
changing any consumer, consistent with the substitution pattern
established by the existing repositories.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from teea.plagiarism.models import SourceDocument


@runtime_checkable
class FingerprintRepository(Protocol):
    """Read/write access to stored source documents and their fingerprints.

    Implementations must be safe to share across threads for read-only use.

    This is the persistence-layer counterpart of
    :class:`~teea.plagiarism.interfaces.FingerprintIndex`.  The repository
    owns the authoritative copy; the index is a query-optimised view.
    """

    def save(self, document: SourceDocument) -> None:
        """Persist a document and its fingerprints.

        Idempotent: saving the same document twice is a no-op.
        """
        ...

    def load(self, document_id: str) -> SourceDocument | None:
        """Retrieve a document by id, or ``None`` if not found."""
        ...

    def delete(self, document_id: str) -> bool:
        """Remove a document.  Returns ``True`` if it existed."""
        ...

    def all_ids(self) -> Iterable[str]:
        """Return the ids of every stored document."""
        ...

    def count(self) -> int:
        """Return the number of stored documents."""
        ...


class InMemoryFingerprintRepository:
    """In-memory implementation of :class:`FingerprintRepository`.

    Follows the same pattern as :class:`InMemoryDictionaryRepository`:
    data is held in a dict and never persisted to disk.
    """

    def __init__(self) -> None:
        self._store: dict[str, SourceDocument] = {}

    def save(self, document: SourceDocument) -> None:
        """Persist a document and its fingerprints."""
        self._store[document.document_id] = document

    def load(self, document_id: str) -> SourceDocument | None:
        """Retrieve a document by id."""
        return self._store.get(document_id)

    def delete(self, document_id: str) -> bool:
        """Remove a document. Returns True if it existed."""
        return self._store.pop(document_id, None) is not None

    def all_ids(self) -> Iterable[str]:
        """Return the ids of every stored document."""
        return tuple(self._store.keys())

    def count(self) -> int:
        """Return the number of stored documents."""
        return len(self._store)

    def all(self) -> Sequence[SourceDocument]:
        """Return every stored document."""
        return tuple(self._store.values())

    def clear(self) -> None:
        """Remove all documents."""
        self._store.clear()


__all__ = ["FingerprintRepository", "InMemoryFingerprintRepository"]
