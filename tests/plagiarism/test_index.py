"""Tests for the in-memory fingerprint index."""

from __future__ import annotations

import pytest

from teea.plagiarism.index import InMemoryFingerprintIndex
from teea.plagiarism.models import SourceDocument


@pytest.fixture
def empty_index() -> InMemoryFingerprintIndex:
    return InMemoryFingerprintIndex()


@pytest.fixture
def populated_index() -> InMemoryFingerprintIndex:
    idx = InMemoryFingerprintIndex()
    idx.add(
        SourceDocument(
            document_id="d1",
            source="hello world",
            fingerprints=frozenset({1, 2, 3}),
        )
    )
    idx.add(
        SourceDocument(
            document_id="d2", source="goodbye world", fingerprints=frozenset({3, 4, 5})
        )
    )
    idx.add(SourceDocument(document_id="d3", source="foo bar", fingerprints=frozenset({7, 8, 9})))
    return idx


class TestInMemoryFingerprintIndex:
    def test_empty_index_lookup_returns_empty(self, empty_index: InMemoryFingerprintIndex) -> None:
        assert empty_index.lookup(42) == ()

    def test_lookup_returns_doc_ids(self, populated_index: InMemoryFingerprintIndex) -> None:
        ids = populated_index.lookup(3)
        assert sorted(ids) == ["d1", "d2"]

    def test_lookup_nonexistent_hash(self, populated_index: InMemoryFingerprintIndex) -> None:
        assert populated_index.lookup(999) == ()

    def test_lookup_many(self, populated_index: InMemoryFingerprintIndex) -> None:
        result = populated_index.lookup_many({1, 4, 999})
        assert 1 in result
        assert 4 in result
        assert 999 not in result
        assert result[1] == ("d1",)
        assert result[4] == ("d2",)

    def test_add_duplicate_is_noop(self, populated_index: InMemoryFingerprintIndex) -> None:
        before = populated_index.total_fingerprints
        duplicated = SourceDocument(
            document_id="d1",
            source="hello world",
            fingerprints=frozenset({1, 2, 3}),
        )
        populated_index.add(duplicated)
        assert populated_index.total_fingerprints == before

    def test_remove_existing(self, populated_index: InMemoryFingerprintIndex) -> None:
        assert populated_index.remove("d1") is True
        assert populated_index.lookup(1) == ()
        assert populated_index.size == 2

    def test_remove_nonexistent(self, populated_index: InMemoryFingerprintIndex) -> None:
        assert populated_index.remove("nonexistent") is False

    def test_clear(self, populated_index: InMemoryFingerprintIndex) -> None:
        populated_index.clear()
        assert populated_index.size == 0
        assert populated_index.total_fingerprints == 0

    def test_size_property(self, populated_index: InMemoryFingerprintIndex) -> None:
        assert populated_index.size == 3

    def test_total_fingerprints(self, populated_index: InMemoryFingerprintIndex) -> None:
        # 3 docs x 3 fingerprints each
        assert populated_index.total_fingerprints == 9

    def test_document_ids(self, populated_index: InMemoryFingerprintIndex) -> None:
        ids = list(populated_index.document_ids())
        assert sorted(ids) == ["d1", "d2", "d3"]

    def test_get_document(self, populated_index: InMemoryFingerprintIndex) -> None:
        doc = populated_index.get_document("d1")
        assert doc is not None
        assert doc.document_id == "d1"

    def test_get_document_nonexistent(self, populated_index: InMemoryFingerprintIndex) -> None:
        assert populated_index.get_document("nonexistent") is None

    def test_add_many(self, empty_index: InMemoryFingerprintIndex) -> None:
        docs = [
            SourceDocument(document_id="a", source="x", fingerprints=frozenset({1})),
            SourceDocument(document_id="b", source="y", fingerprints=frozenset({2})),
        ]
        empty_index.add_many(docs)
        assert empty_index.size == 2

    def test_lookup_many_with_no_matches(self, empty_index: InMemoryFingerprintIndex) -> None:
        assert empty_index.lookup_many({1, 2, 3}) == {}
