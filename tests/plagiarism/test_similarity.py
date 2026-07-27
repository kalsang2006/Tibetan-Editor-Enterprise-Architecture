"""Tests for plagiarism similarity scoring."""

from __future__ import annotations

import pytest

from teea.plagiarism.models import FingerprintMatch
from teea.plagiarism.similarity import jaccard_containment, rank_matches


class TestJaccardContainment:
    def test_no_overlap_returns_none(self) -> None:
        result = jaccard_containment(
            frozenset({1, 2, 3}),
            frozenset({4, 5, 6}),
            "d1",
        )
        assert result is None

    def test_full_containment(self) -> None:
        result = jaccard_containment(
            frozenset({1, 2, 3}),
            frozenset({1, 2, 3, 4, 5, 6}),
            "d1",
        )
        assert result is not None
        assert result.similarity == 1.0  # all query hashes found
        assert result.coverage == 0.5  # half of doc hashes matched

    def test_partial_match(self) -> None:
        result = jaccard_containment(
            frozenset({1, 2, 3, 4}),
            frozenset({1, 2, 5, 6}),
            "d1",
        )
        assert result is not None
        assert result.similarity == 0.5  # 2/4 query hashes matched
        assert result.coverage == 0.5  # 2/4 doc hashes matched

    def test_asymmetric_scores(self) -> None:
        query_hashes = frozenset({1, 2})
        doc_hashes = frozenset({1, 2, 3, 4, 5, 6, 7, 8})

        q_into_d = jaccard_containment(query_hashes, doc_hashes, "d1")
        d_into_q = jaccard_containment(doc_hashes, query_hashes, "q")

        assert q_into_d is not None
        assert d_into_q is not None
        # Short query fully contained in long doc
        assert q_into_d.similarity == 1.0
        # Long doc barely overlaps short query
        assert d_into_q.similarity < 0.5
        assert d_into_q.coverage == 1.0  # all doc hashes (that exist in query) matched

    def test_with_explicit_totals(self) -> None:
        result = jaccard_containment(
            frozenset({1, 2, 3}),
            frozenset({1, 2}),
            "d1",
            query_total=5,  # query originally had 5, but 3 survived dedup
            doc_total=2,
        )
        assert result is not None
        assert result.similarity == pytest.approx(0.4)  # 2/5
        assert result.coverage == 1.0  # 2/2


class TestRankMatches:
    def test_sorts_by_similarity_descending(self) -> None:
        m1 = FingerprintMatch(
            document_id="a", similarity=0.3, coverage=0.5,
            overlap_count=3, query_fingerprint_count=10, doc_fingerprint_count=6,
        )
        m2 = FingerprintMatch(
            document_id="b", similarity=0.8, coverage=0.5,
            overlap_count=8, query_fingerprint_count=10, doc_fingerprint_count=16,
        )
        m3 = FingerprintMatch(
            document_id="c", similarity=0.5, coverage=0.5,
            overlap_count=5, query_fingerprint_count=10, doc_fingerprint_count=10,
        )
        ranked = rank_matches([m1, m2, m3])
        assert [m.document_id for m in ranked] == ["b", "c", "a"]

    def test_ties_broken_by_coverage(self) -> None:
        m1 = FingerprintMatch(
            document_id="a", similarity=0.5, coverage=0.3,
            overlap_count=5, query_fingerprint_count=10, doc_fingerprint_count=17,
        )
        m2 = FingerprintMatch(
            document_id="b", similarity=0.5, coverage=0.7,
            overlap_count=5, query_fingerprint_count=10, doc_fingerprint_count=7,
        )
        ranked = rank_matches([m1, m2])
        assert ranked[0].document_id == "b"

    def test_empty_list(self) -> None:
        assert rank_matches([]) == []
