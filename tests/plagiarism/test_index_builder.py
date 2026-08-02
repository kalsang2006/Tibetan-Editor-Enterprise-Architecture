"""Unit tests for BoCorpus IndexBuilder."""

from __future__ import annotations

from collections.abc import Iterator

from teea.persistence.fingerprints import InMemoryFingerprintRepository
from teea.plagiarism.corpus import BoCorpusLoader
from teea.plagiarism.index_builder import IndexBuilder
from teea.plagiarism.models import SourceDocument


class DummyCorpusLoader(BoCorpusLoader):
    """Dummy loader for testing without external files."""

    def __init__(self, docs: list[SourceDocument]) -> None:
        self._docs = docs

    def __iter__(self) -> Iterator[SourceDocument]:
        yield from self._docs

    def total_count(self) -> int:
        return len(self._docs)


def test_index_builder_incremental_and_force() -> None:
    doc1 = SourceDocument(
        document_id="doc1",
        source="༄༅། ཀྱི་ཁྱི་བྱི་གྱི་དགའ་བ། སྐྱིད་པོ་ཡོད།",
        collection="Test Collection",
        filename="doc1.txt",
    )
    doc2 = SourceDocument(
        document_id="doc2",
        source="བཀྲ་ཤིས་བདེ་ལེགས། ཀྱི་ཁྱི་བྱི་གྱི་དགའ་བ།",
        collection="Test Collection",
        filename="doc2.txt",
    )

    repo = InMemoryFingerprintRepository()
    loader = DummyCorpusLoader([doc1, doc2])
    builder = IndexBuilder(loader=loader, repository=repo, batch_size=2)

    # First build
    stats1 = builder.build(force=False, max_chunk_chars=100)
    assert stats1.indexed_documents == 2
    assert stats1.skipped_documents == 0
    assert stats1.failed_documents == 0
    assert stats1.total_fingerprints > 0

    # Second build without force -> skip existing
    stats2 = builder.build(force=False, max_chunk_chars=100)
    assert stats2.indexed_documents == 0
    assert stats2.skipped_documents == 2

    # Third build with force=True -> re-index
    stats3 = builder.build(force=True, max_chunk_chars=100)
    assert stats3.indexed_documents == 2
    assert stats3.skipped_documents == 0
