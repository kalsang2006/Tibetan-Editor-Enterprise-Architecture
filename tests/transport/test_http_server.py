"""Tests for the loopback HTTP bridge plagiarism endpoint."""

from __future__ import annotations

from teea.plagiarism.engine import PlagiarismEngine
from teea.plagiarism.config import PlagiarismSettings
from teea.transport.http_server import PLAGIARISM_METHOD, PLAGIARISM_PATH


class TestHttpPlagiarismEndpoint:
    def test_plagiarism_constants(self) -> None:
        assert PLAGIARISM_METHOD == "plagiarism.check"
        assert PLAGIARISM_PATH == "/api/plagiarism/check"

    def test_engine_detection_integration(self) -> None:
        settings = PlagiarismSettings(min_similarity=0.05, kgram_size=5, winnow_window=4)
        engine = PlagiarismEngine(settings=settings)
        engine.add_text("ref_doc", "༄༅། ཀྱི་ཁྱི་བྱི་གྱི་དགའ་བ།")

        query = "ཀྱི་ཁྱི་བྱི་གྱི་དགའ་བ་ལ་མཐོང་།"
        result = engine.detect(query)

        assert result.query_fingerprint_count > 0
        assert result.total_corpus_documents == 1
        assert result.num_matches == 1
        assert result.matches[0].document_id == "ref_doc"
        assert result.matches[0].similarity > 0.0
        assert result.matches[0].source_span is not None
        assert result.matches[0].source_span.char_start >= 0
