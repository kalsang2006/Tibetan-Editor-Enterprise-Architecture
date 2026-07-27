"""Tests for plagiarism detection configuration."""

from __future__ import annotations

from teea.plagiarism.config import PlagiarismSettings


class TestPlagiarismSettings:
    def test_default_values(self) -> None:
        settings = PlagiarismSettings()
        assert settings.kgram_size == 6
        assert settings.winnow_window == 4
        assert settings.min_similarity == 0.1
        assert settings.min_document_length == 20
        assert settings.ignore_trivial_matches is True
        assert settings.normalization_form == "NFC"

    def test_custom_values(self) -> None:
        settings = PlagiarismSettings(
            kgram_size=8,
            winnow_window=6,
            min_similarity=0.2,
            min_document_length=50,
            ignore_trivial_matches=False,
            normalization_form="NFKC",
        )
        assert settings.kgram_size == 8
        assert settings.winnow_window == 6
        assert settings.min_similarity == 0.2

    def test_kgram_must_be_gt_1(self) -> None:
        try:
            PlagiarismSettings(kgram_size=1)
            assert False, "should have raised"
        except Exception:
            pass

    def test_frozen(self) -> None:
        settings = PlagiarismSettings()
        try:
            settings.kgram_size = 10  # type: ignore[misc]
            assert False, "should have raised"
        except Exception:
            pass
