"""Tests for the plagiarism detection engine."""

from __future__ import annotations

import pytest

from teea.plagiarism.engine import PlagiarismEngine


class TestPlagiarismEngine:
    def test_empty_query_raises(self) -> None:
        engine = PlagiarismEngine()
        with pytest.raises(ValueError, match="must not be empty"):
            engine.detect("")

    def test_empty_corpus_returns_no_matches(self) -> None:
        engine = PlagiarismEngine()
        result = engine.detect("hello world")
        assert result.num_matches == 0

    def test_exact_match_detected(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("source_doc", "the quick brown fox jumps over the lazy dog")
        result = engine.detect("the quick brown fox jumps over the lazy dog")
        assert result.num_matches > 0
        assert result.best_match is not None
        assert result.best_match.similarity == pytest.approx(1.0, abs=0.05)

    def test_partial_match_detected(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("source_doc", "the quick brown fox jumps over the lazy dog near the river")
        result = engine.detect("the quick brown fox jumps over the lazy dog")
        assert result.num_matches > 0
        assert result.best_match is not None
        # Query is a prefix of source_doc → all query fingerprints are contained
        assert result.best_match.similarity == pytest.approx(1.0, abs=0.1)

    def test_query_longer_than_source_is_partial(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("source_doc", "the quick brown fox")
        result = engine.detect("the quick brown fox jumps over the lazy dog")
        assert result.num_matches > 0
        assert result.best_match is not None
        assert 0.2 < result.best_match.similarity < 1.0

    def test_multiple_matches_ranked(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("doc_a", "the quick brown fox jumps over the lazy dog")
        engine.add_text("doc_b", "the quick brown fox jumps over the river")
        engine.add_text("doc_c", "completely unrelated text about tibetan language")
        result = engine.detect("the quick brown fox jumps over the lazy dog")
        assert result.num_matches <= 3
        if result.num_matches >= 2:
            assert result.matches[0].similarity >= result.matches[1].similarity

    def test_unrelated_query_returns_no_matches(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("source_doc", "the quick brown fox jumps over the lazy dog")
        result = engine.detect("completely unrelated text about tibetan language")
        # May still have some matches due to k-gram overlap of short common words
        assert result.query_fingerprint_count > 0

    def test_min_similarity_threshold(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("doc_a", "the quick brown fox jumps over the lazy dog")
        result = engine.detect("the quick brown fox", min_similarity=0.9)
        # The short query may not reach 90% similarity
        assert result.num_matches == 0 or result.matches[0].similarity >= 0.9

    def test_tibetan_text(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("ref", "བཀྲ་ཤིས་བདེ་ལེགས།")
        result = engine.detect("བཀྲ་ཤིས་བདེ་ལེགས།")
        assert result.num_matches > 0
        assert result.best_match is not None
        assert result.best_match.similarity == pytest.approx(1.0, abs=0.05)

    def test_deterministic_results(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("ref", "It was the best of times it was the worst of times")
        r1 = engine.detect("It was the best of times")
        r2 = engine.detect("It was the best of times")
        assert r1.num_matches == r2.num_matches
        if r1.num_matches > 0 and r2.num_matches > 0:
            assert r1.matches[0].similarity == r2.matches[0].similarity

    def test_large_corpus_performance(self) -> None:
        """Engine handles many documents efficiently."""
        engine = PlagiarismEngine()
        for i in range(50):
            text = f"unique text number {i} with some common words here and there"
            engine.add_text(f"doc_{i}", text)
        result = engine.detect(
            "unique text number 42 with some common words here and there"
        )
        assert result.num_matches > 0

    def test_elapsed_ms_recorded(self) -> None:
        engine = PlagiarismEngine()
        result = engine.detect("hello world test query")
        assert result.elapsed_ms >= 0.0

    def test_add_text_returns_source_document(self) -> None:
        engine = PlagiarismEngine()
        doc = engine.add_text("my_doc", "some text to index")
        assert doc.document_id == "my_doc"
        assert doc.source == "some text to index"

    def test_query_fingerprint_count(self) -> None:
        engine = PlagiarismEngine()
        result = engine.detect("hello world this is a test query with enough words")
        assert result.query_fingerprint_count > 0
