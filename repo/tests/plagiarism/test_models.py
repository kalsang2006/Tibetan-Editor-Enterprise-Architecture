"""Tests for plagiarism domain models."""

from __future__ import annotations

import pytest

from teea.plagiarism.models import Fingerprint, FingerprintMatch, MatchResult, SourceDocument


class TestFingerprint:
    def test_creates_with_hash_and_position(self) -> None:
        fp = Fingerprint(hash_value=42, char_start=0, char_end=6)
        assert fp.hash_value == 42
        assert fp.char_start == 0
        assert fp.char_end == 6

    def test_negative_start_raises(self) -> None:
        with pytest.raises(ValueError):
            Fingerprint(hash_value=1, char_start=-1, char_end=5)


class TestSourceDocument:
    def test_creates_with_id_and_source(self) -> None:
        doc = SourceDocument(document_id="d1", source="text")
        assert doc.document_id == "d1"
        assert doc.source == "text"
        assert doc.fingerprints == frozenset()

    def test_empty_id_raises(self) -> None:
        with pytest.raises(ValueError):
            SourceDocument(document_id="", source="text")

    def test_default_fingerprints_is_empty(self) -> None:
        doc = SourceDocument(document_id="d1", source="hello")
        assert doc.fingerprints == frozenset()


class TestFingerprintMatch:
    def test_creates_with_all_fields(self) -> None:
        m = FingerprintMatch(
            document_id="d1",
            similarity=0.5,
            coverage=0.3,
            overlap_count=10,
            query_fingerprint_count=20,
            doc_fingerprint_count=30,
        )
        assert m.document_id == "d1"
        assert m.similarity == 0.5

    def test_overlap_exceeds_query_count_raises(self) -> None:
        with pytest.raises(ValueError):
            FingerprintMatch(
                document_id="d1",
                similarity=1.0,
                coverage=1.0,
                overlap_count=15,
                query_fingerprint_count=10,
                doc_fingerprint_count=20,
            )

    def test_overlap_exceeds_doc_count_raises(self) -> None:
        with pytest.raises(ValueError):
            FingerprintMatch(
                document_id="d1",
                similarity=1.0,
                coverage=1.0,
                overlap_count=25,
                query_fingerprint_count=30,
                doc_fingerprint_count=20,
            )

    def test_empty_id_raises(self) -> None:
        with pytest.raises(ValueError):
            FingerprintMatch(
                document_id="",
                similarity=0.5,
                coverage=0.3,
                overlap_count=5,
                query_fingerprint_count=10,
                doc_fingerprint_count=15,
            )


class TestMatchResult:
    def test_empty_result(self) -> None:
        result = MatchResult()
        assert result.num_matches == 0
        assert result.best_match is None
        assert result.max_similarity == 0.0

    def test_with_matches(self) -> None:
        m1 = FingerprintMatch(
            document_id="a", similarity=0.8, coverage=0.5,
            overlap_count=8, query_fingerprint_count=10, doc_fingerprint_count=16,
        )
        m2 = FingerprintMatch(
            document_id="b", similarity=0.3, coverage=0.2,
            overlap_count=3, query_fingerprint_count=10, doc_fingerprint_count=15,
        )
        result = MatchResult(matches=(m1, m2), query_text="test", query_fingerprint_count=10)
        assert result.num_matches == 2
        assert result.best_match is not None
        assert result.best_match.document_id == "a"
        assert result.max_similarity == 0.8

    def test_above_threshold_filters(self) -> None:
        m1 = FingerprintMatch(
            document_id="a", similarity=0.8, coverage=0.5,
            overlap_count=8, query_fingerprint_count=10, doc_fingerprint_count=16,
        )
        m2 = FingerprintMatch(
            document_id="b", similarity=0.3, coverage=0.2,
            overlap_count=3, query_fingerprint_count=10, doc_fingerprint_count=15,
        )
        result = MatchResult(matches=(m1, m2), query_fingerprint_count=10)
        filtered = result.above(0.5)
        assert filtered.num_matches == 1
        assert filtered.matches[0].document_id == "a"
