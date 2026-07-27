"""Plagiarism detection engine orchestrator (Figure 8).

The engine composes the preprocessing, fingerprinting, index query, similarity
scoring, and ranking steps into a single call.

Flow
----
1. Normalize query text
2. Generate winnowed fingerprints
3. Look up each fingerprint hash in the index
4. Aggregate matches per candidate document
5. Compute asymmetric containment similarity
6. Rank and threshold results
"""

from __future__ import annotations

import time

from teea.plagiarism.config import PlagiarismSettings
from teea.plagiarism.fingerprinting import hash_set, normalize_and_fingerprint
from teea.plagiarism.index import InMemoryFingerprintIndex
from teea.plagiarism.interfaces import FingerprintIndex
from teea.plagiarism.models import FingerprintMatch, MatchResult, SourceDocument
from teea.plagiarism.similarity import jaccard_containment, rank_matches


class PlagiarismEngine:
    """Full plagiarism detection orchestrator.

    Satisfies the :class:`~teea.plagiarism.interfaces.PlagiarismDetector`
    protocol.  Holds the fingerprint index and is safe to share across
    threads for read-only use (query).  Index mutations (add/remove) must
    be externally synchronized.

    Args:
        index: The fingerprint index to query against.  Defaults to an
            empty :class:`InMemoryFingerprintIndex`.
        settings: Detection parameters (k-gram size, winnow window, etc.).
            Defaults to ``PlagiarismSettings()``.
    """

    def __init__(
        self,
        index: FingerprintIndex | None = None,
        settings: PlagiarismSettings | None = None,
    ) -> None:
        self._index = index if index is not None else InMemoryFingerprintIndex()
        self._settings = settings if settings is not None else PlagiarismSettings()

    @property
    def index(self) -> FingerprintIndex:
        """The underlying fingerprint index."""
        return self._index

    @property
    def settings(self) -> PlagiarismSettings:
        """Current detection settings."""
        return self._settings

    def detect(self, text: str, *, min_similarity: float | None = None) -> MatchResult:
        """Detect plagiarism in ``text`` against the indexed corpus.

        Args:
            text: The query document text.
            min_similarity: Minimum similarity for a match to be reported.
                Overrides the setting default when provided.

        Returns:
            A result with ranked matches meeting the threshold.

        Raises:
            ValueError: If ``text`` is empty.
        """
        if not text:
            raise ValueError("query text must not be empty")

        threshold = min_similarity if min_similarity is not None else self._settings.min_similarity
        total_docs = self._index.size

        start = time.perf_counter()

        # 1. Normalize and fingerprint
        normalized, fingerprints = normalize_and_fingerprint(
            text,
            kgram_size=self._settings.kgram_size,
            winnow_window=self._settings.winnow_window,
            normalization_form=self._settings.normalization_form,
        )

        query_hashes = hash_set(fingerprints)
        q_total = len(query_hashes)

        if q_total == 0:
            elapsed = (time.perf_counter() - start) * 1000
            return MatchResult(
                query_text=text,
                query_fingerprint_count=0,
                total_corpus_documents=total_docs,
                elapsed_ms=elapsed,
            )

        # 2. Look up each fingerprint hash in the index
        #    Accumulate per-document overlap counts
        candidates: dict[str, int] = {}
        for h in query_hashes:
            doc_ids = self._index.lookup(h)
            for doc_id in doc_ids:
                candidates[doc_id] = candidates.get(doc_id, 0) + 1

        if not candidates:
            elapsed = (time.perf_counter() - start) * 1000
            return MatchResult(
                query_text=normalized,
                query_fingerprint_count=q_total,
                total_corpus_documents=total_docs,
                elapsed_ms=elapsed,
            )

        # 3. Compute containment similarity for each candidate
        matches: list[FingerprintMatch] = []
        for doc_id, _overlap_count in candidates.items():
            # Retrieve the document's fingerprint set
            doc = self._get_source_document(doc_id)
            if doc is None or not doc.fingerprints:
                continue

            doc_hashes = doc.fingerprints
            d_total = len(doc_hashes)

            match = jaccard_containment(
                query_hashes,
                doc_hashes,
                doc_id,
                query_total=q_total,
                doc_total=d_total,
            )
            if match is not None and match.similarity >= threshold:
                matches.append(match)

        elapsed = (time.perf_counter() - start) * 1000

        return MatchResult(
            matches=tuple(rank_matches(matches)),
            query_text=normalized,
            query_fingerprint_count=q_total,
            total_corpus_documents=total_docs,
            elapsed_ms=elapsed,
        )

    # -- Internal helpers ------------------------------------------------

    def _get_source_document(self, document_id: str) -> SourceDocument | None:
        """Retrieve a stored document from the index.

        This method exists so that a subclass or a future persistent index
        can override how documents are retrieved without changing the query
        logic.
        """
        if isinstance(self._index, InMemoryFingerprintIndex):
            return self._index.get_document(document_id)
        return None

    def add_document(self, document: SourceDocument) -> None:
        """Index a corpus document.

        Args:
            document: The document to index.
        """
        self._index.add(document)

    def add_text(self, document_id: str, text: str) -> SourceDocument:
        """Normalize, fingerprint, and index a text document.

        This is a convenience method for building a corpus from raw text.

        Args:
            document_id: Unique identifier for the document.
            text: The document text.

        Returns:
            The :class:`SourceDocument` that was indexed.
        """
        normalized, fingerprints = normalize_and_fingerprint(
            text,
            kgram_size=self._settings.kgram_size,
            winnow_window=self._settings.winnow_window,
            normalization_form=self._settings.normalization_form,
        )
        doc = SourceDocument(
            document_id=document_id,
            source=normalized,
            fingerprints=hash_set(fingerprints),
        )
        self._index.add(doc)
        return doc


__all__ = ["PlagiarismEngine"]
