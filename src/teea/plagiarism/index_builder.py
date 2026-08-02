"""Batch & incremental BoCorpus plagiarism index builder."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from teea.core.logging import get_logger
from teea.persistence.fingerprints import FingerprintRepository
from teea.plagiarism.chunking import chunk_document
from teea.plagiarism.config import PlagiarismSettings
from teea.plagiarism.corpus import BoCorpusLoader
from teea.plagiarism.fingerprinting import hash_set, normalize_and_fingerprint
from teea.plagiarism.models import SourceDocument

_logger = get_logger(__name__)


@dataclass
class IndexBuildStats:
    """Statistics summarizing an index build run.

    Attributes:
        indexed_documents: Number of documents processed and indexed.
        skipped_documents: Number of existing documents skipped.
        failed_documents: Number of documents that failed processing.
        total_fingerprints: Total winnowed fingerprints generated.
        elapsed_seconds: Total wall-clock time in seconds.
    """

    indexed_documents: int = 0
    skipped_documents: int = 0
    failed_documents: int = 0
    total_fingerprints: int = 0
    elapsed_seconds: float = 0.0

    @property
    def docs_per_second(self) -> float:
        """Average processing speed in documents per second."""
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.indexed_documents / self.elapsed_seconds


class IndexBuilder:
    """Indexes BoCorpus Parquet datasets into a FingerprintRepository.

    Args:
        loader: The BoCorpus dataset loader.
        repository: The SQLite or in-memory fingerprint repository.
        settings: Plagiarism configuration settings.
        batch_size: Number of chunk documents per SQLite write batch.
    """

    def __init__(
        self,
        loader: BoCorpusLoader,
        repository: FingerprintRepository,
        settings: PlagiarismSettings | None = None,
        batch_size: int = 50,
    ) -> None:
        self._loader = loader
        self._repository = repository
        self._settings = settings or PlagiarismSettings()
        self._batch_size = batch_size

    def build(
        self,
        *,
        force: bool = False,
        max_chunk_chars: int = 100000,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> IndexBuildStats:
        """Run the indexing pipeline over the loader dataset.

        Args:
            force: Rebuild all documents even if they already exist in repository.
            max_chunk_chars: Maximum character length for document chunking.
            progress_callback: Optional progress reporter receiving `(current, total)`.

        Returns:
            An :class:`IndexBuildStats` summary object.
        """
        start_time = time.perf_counter()
        stats = IndexBuildStats()
        total_docs = self._loader.total_count()

        pending_batch: list[SourceDocument] = []
        processed_count = 0

        for raw_doc in self._loader:
            processed_count += 1
            if progress_callback is not None:
                progress_callback(processed_count, total_docs)

            # Incremental check
            if not force and self._repository.exists(raw_doc.document_id):
                stats.skipped_documents += 1
                continue

            try:
                chunks = chunk_document(raw_doc, max_chunk_chars=max_chunk_chars)
                doc_fp_count = 0

                for chunk in chunks:
                    normalized, fingerprints = normalize_and_fingerprint(
                        chunk.text,
                        kgram_size=self._settings.kgram_size,
                        winnow_window=self._settings.winnow_window,
                        normalization_form=self._settings.normalization_form,
                    )
                    hashes = hash_set(fingerprints)
                    doc_fp_count += len(hashes)

                    chunk_doc = SourceDocument(
                        document_id=chunk.document_id,
                        source=normalized,
                        fingerprints=hashes,
                        collection=chunk.collection,
                        filename=chunk.filename,
                        parent_doc_id=chunk.parent_doc_id,
                        chunk_index=chunk.chunk_index,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                    )
                    pending_batch.append(chunk_doc)

                stats.indexed_documents += 1
                stats.total_fingerprints += doc_fp_count

                if len(pending_batch) >= self._batch_size:
                    self._repository.save_batch(pending_batch)
                    pending_batch.clear()

            except Exception as exc:  # noqa: BLE001
                _logger.warning("indexing_document_failed", doc_id=raw_doc.document_id, error=str(exc))
                stats.failed_documents += 1

        if pending_batch:
            self._repository.save_batch(pending_batch)
            pending_batch.clear()

        stats.elapsed_seconds = time.perf_counter() - start_time
        return stats


__all__ = ["IndexBuildStats", "IndexBuilder"]
