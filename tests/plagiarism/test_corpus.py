"""Tests for document corpus management."""

from __future__ import annotations

import pytest

from teea.plagiarism.corpus import BoCorpusLoader, DocumentCorpus
from teea.plagiarism.index import InMemoryFingerprintIndex


class TestDocumentCorpus:
    def test_empty_corpus(self) -> None:
        corpus = DocumentCorpus(InMemoryFingerprintIndex())
        assert corpus.size == 0

    def test_add_document(self) -> None:
        corpus = DocumentCorpus(InMemoryFingerprintIndex())
        doc = corpus.add_document("doc1", "the quick brown fox jumps over the lazy dog")
        assert doc.document_id == "doc1"
        assert corpus.size == 1
        assert len(doc.fingerprints) > 0

    def test_add_multiple_documents(self) -> None:
        corpus = DocumentCorpus(InMemoryFingerprintIndex())
        corpus.add_documents({
            "doc1": "the quick brown fox",
            "doc2": "jumps over the lazy dog",
        })
        assert corpus.size == 2

    def test_remove_document(self) -> None:
        corpus = DocumentCorpus(InMemoryFingerprintIndex())
        corpus.add_document("doc1", "some text")
        assert corpus.size == 1
        assert corpus.remove_document("doc1") is True
        assert corpus.size == 0

    def test_remove_nonexistent(self) -> None:
        corpus = DocumentCorpus(InMemoryFingerprintIndex())
        assert corpus.remove_document("nonexistent") is False

    def test_index_is_accessible(self) -> None:
        index = InMemoryFingerprintIndex()
        corpus = DocumentCorpus(index)
        assert corpus.index is index

    def test_bocorpus_loader_file_not_found(self) -> None:
        loader = BoCorpusLoader(parquet_path="nonexistent.parquet")
        assert loader.total_count() == 0
        with pytest.raises(FileNotFoundError):
            list(loader)
