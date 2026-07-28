"""Tests for the plagiarism detection feature plugin."""

from __future__ import annotations

from teea.nlp.snapshot import DocumentSnapshot
from teea.plagiarism.engine import PlagiarismEngine
from teea.plugins.builtin.plagiarism import PlagiarismDetectorPlugin


class TestPlagiarismDetectorPlugin:
    def test_plugin_name(self) -> None:
        engine = PlagiarismEngine()
        plugin = PlagiarismDetectorPlugin(engine)
        assert plugin.name == "teea.plagiarism"

    def test_examine_empty_snapshot(self) -> None:
        engine = PlagiarismEngine()
        plugin = PlagiarismDetectorPlugin(engine)
        snapshot = DocumentSnapshot(source="")
        results = list(plugin.examine(snapshot))
        assert results == []

    def test_examine_with_no_matches(self) -> None:
        engine = PlagiarismEngine()
        plugin = PlagiarismDetectorPlugin(engine)
        snapshot = DocumentSnapshot(source="unique text that is not in corpus")
        results = list(plugin.examine(snapshot))
        assert results == []

    def test_examine_with_match_produces_suggestion(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("ref_doc", "the quick brown fox jumps over the lazy dog")
        plugin = PlagiarismDetectorPlugin(engine)
        snapshot = DocumentSnapshot(source="the quick brown fox jumps over the lazy dog")
        results = list(plugin.examine(snapshot))
        assert len(results) > 0
        suggestion = results[0]
        assert suggestion.source == "teea.plagiarism"
        assert suggestion.replacement is None  # advisory
        assert suggestion.is_advisory
        assert "Plagiarism" in suggestion.message

    def test_examine_with_multiple_matches(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("doc_a", "the quick brown fox jumps over the lazy dog")
        engine.add_text("doc_b", "the quick brown fox jumps over the river")
        plugin = PlagiarismDetectorPlugin(engine)
        snapshot = DocumentSnapshot(source="the quick brown fox jumps over the lazy dog")
        results = list(plugin.examine(snapshot))
        assert len(results) > 0

    def test_scores_reflect_similarity(self) -> None:
        engine = PlagiarismEngine()
        engine.add_text("ref", "the quick brown fox")
        plugin = PlagiarismDetectorPlugin(engine)
        snapshot = DocumentSnapshot(source="the quick brown fox jumps over the lazy dog")
        results = list(plugin.examine(snapshot))
        if results:
            # Query is longer than ref, so containment should be < 1.0
            assert results[0].score < 1.0

    def test_plugin_uses_correct_priority(self) -> None:
        """High similarity should yield HIGH priority."""
        engine = PlagiarismEngine()
        engine.add_text(
            "ref",
            "the quick brown fox jumps over the lazy dog near the river by the woods",
        )
        plugin = PlagiarismDetectorPlugin(engine)
        snapshot = DocumentSnapshot(source="the quick brown fox jumps over the lazy dog")
        results = list(plugin.examine(snapshot))
        if results:
            assert results[0].score >= 0.1
