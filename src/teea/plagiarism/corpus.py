"""Document corpus management for plagiarism detection.

Provides a simple in-memory corpus that can load documents from text
and index them into a :class:`~teea.plagiarism.interfaces.FingerprintIndex`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from teea.plagiarism.fingerprinting import hash_set, normalize_and_fingerprint
from teea.plagiarism.interfaces import FingerprintIndex
from teea.plagiarism.models import SourceDocument


class DocumentCorpus:
    """A named collection of source documents for plagiarism comparison.

    The corpus owns an :class:`InMemoryFingerprintIndex` and provides
    convenience methods for populating it.

    Args:
        index: The fingerprint index.  Defaults to an empty
            :class:`InMemoryFingerprintIndex`.
        kgram_size: K-gram size for fingerprinting corpus documents.
        winnow_window: Winnowing window size for fingerprinting.
        normalization_form: Unicode normalization form.
    """

    def __init__(
        self,
        index: FingerprintIndex,
        *,
        kgram_size: int = 6,
        winnow_window: int = 4,
        normalization_form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFC",
    ) -> None:
        self._index = index
        self._kgram_size = kgram_size
        self._winnow_window = winnow_window
        self._normalization_form = normalization_form

    @property
    def index(self) -> FingerprintIndex:
        """The underlying fingerprint index."""
        return self._index

    @property
    def size(self) -> int:
        """Number of documents in the corpus."""
        return self._index.size

    def add_document(self, document_id: str, text: str) -> SourceDocument:
        """Normalize, fingerprint, and index one document.

        Args:
            document_id: Unique identifier.
            text: Raw document text.

        Returns:
            The indexed :class:`SourceDocument`.
        """
        normalized, fingerprints = normalize_and_fingerprint(
            text,
            kgram_size=self._kgram_size,
            winnow_window=self._winnow_window,
            normalization_form=self._normalization_form,
        )
        doc = SourceDocument(
            document_id=document_id,
            source=normalized,
            fingerprints=hash_set(fingerprints),
        )
        self._index.add(doc)
        return doc

    def add_documents(self, documents: dict[str, str]) -> None:
        """Index multiple documents at once.

        Args:
            documents: Mapping of ``document_id → raw_text``.
        """
        for doc_id, text in documents.items():
            self.add_document(doc_id, text)

    def remove_document(self, document_id: str) -> bool:
        """Remove a document and its fingerprints from the index.

        Returns:
            ``True`` if the document was present.
        """
        return self._index.remove(document_id)


class BoCorpusLoader:
    """Streams documents from BoCorpus Parquet files.

    Args:
        parquet_path: Path to the BoCorpus Parquet file.
        batch_size: Number of rows per read batch.
    """

    def __init__(
        self,
        parquet_path: str | Path = "Data/Corpus/BoCorpus/bo_corpus.parquet",
        batch_size: int = 50,
    ) -> None:
        self._parquet_path = Path(parquet_path)
        self._batch_size = batch_size

    def __iter__(self) -> Iterator[SourceDocument]:
        """Stream SourceDocument instances from the Parquet file."""
        if not self._parquet_path.exists():
            raise FileNotFoundError(f"BoCorpus Parquet file not found at {self._parquet_path}")

        import pyarrow.parquet as pq  # noqa: PLC0415

        pf = pq.ParquetFile(str(self._parquet_path))
        for batch in pf.iter_batches(batch_size=self._batch_size):
            pydict = batch.to_pydict()
            ids = pydict.get("id", [])
            collections = pydict.get("collection", [])
            filenames = pydict.get("filename", [])
            texts = pydict.get("text", [])

            for doc_id, collection, filename, text in zip(ids, collections, filenames, texts, strict=False):
                if not text or not isinstance(text, str):
                    continue
                yield SourceDocument(
                    document_id=str(doc_id),
                    source=text,
                    collection=str(collection) if collection else None,
                    filename=str(filename) if filename else None,
                )

    def total_count(self) -> int:
        """Return total row count in the Parquet file."""
        if not self._parquet_path.exists():
            return 0

        import pyarrow.parquet as pq  # noqa: PLC0415

        pf = pq.ParquetFile(str(self._parquet_path))
        return int(pf.metadata.num_rows)


__all__ = ["BoCorpusLoader", "DocumentCorpus"]
