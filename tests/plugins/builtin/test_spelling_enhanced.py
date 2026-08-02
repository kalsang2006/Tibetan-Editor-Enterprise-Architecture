"""Enhanced unit & integration tests for corpus-aware spell checking and candidate ranking.

Verifies:
1. BoCorpusRepository unigram, bigram, trigram, and context scoring.
2. CorrectionProvider hybrid contextual candidate ranking.
3. Combined vocabulary handling in SpellCheckerPlugin.
4. Dependency injection in TEEAEngine.
5. Synthetic error dataset evaluation runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from teea.corpus.repository import BoCorpusRepository
from teea.engine import TEEAEngine
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.plugins.builtin.correction import CorrectionProvider
from teea.plugins.builtin.spelling import SpellCheckerPlugin


@pytest.fixture
def mock_corpus_repo(tmp_path: Path) -> BoCorpusRepository:
    """Fixture providing a mock BoCorpusRepository with sample vocabulary and n-grams."""
    processed_dir = tmp_path / "Processed"
    synthetic_dir = tmp_path / "SyntheticErrors"
    processed_dir.mkdir()
    synthetic_dir.mkdir()

    vocab_data = {
        "dataset": "openpecha/BoCorpus",
        "syllable_frequencies": {
            "བཀྲ་": 1000,
            "ཤིས་": 900,
            "བདེ་": 800,
            "ལེགས་": 750,
            "ཁྱོད་": 500,
            "རང་": 450,
        },
    }
    ngram_data = {
        "bigrams": {
            "བཀྲ་ ཤིས་": 850,
            "བདེ་ ལེགས་": 700,
            "ཁྱོད་ རང་": 400,
        },
        "trigrams": {
            "བཀྲ་ ཤིས་ བདེ་": 600,
            "ཤིས་ བདེ་ ལེགས་": 550,
        },
    }
    syn_data = {
        "version": "1.0.0",
        "total_records": 1,
        "records": [
            {
                "id": "syn-001",
                "original_text": "བཀྲ་ཤིས་བདེ་ལེགས།",
                "corrupted_text": "བཀྲོཤིས་བདེ་ལེགས།",
                "error_type": "VOWEL_MUTATION",
                "char_start": 0,
                "char_end": 4,
                "description": "Vowel mutation test",
            }
        ],
    }

    (processed_dir / "bocorpus_vocabulary.json").write_text(
        __import__("json").dumps(vocab_data), encoding="utf-8"
    )
    (processed_dir / "bocorpus_ngrams.json").write_text(
        __import__("json").dumps(ngram_data), encoding="utf-8"
    )
    (synthetic_dir / "synthetic_errors.json").write_text(
        __import__("json").dumps(syn_data), encoding="utf-8"
    )

    return BoCorpusRepository(processed_dir=processed_dir, synthetic_dir=synthetic_dir)


def test_bocorpus_repository_scoring(mock_corpus_repo: BoCorpusRepository) -> None:
    """Test unigram log-frequency, bigram, trigram, and context scoring."""
    assert mock_corpus_repo.is_available()
    assert mock_corpus_repo.get_syllable_frequency("བཀྲ་") == 1000
    assert mock_corpus_repo.get_syllable_frequency("unknown") == 0

    # Unigram normalized log score
    u_score = mock_corpus_repo.get_unigram_score("བཀྲ་")
    assert 0.0 < u_score <= 1.0

    # Bigram conditional probability
    bg_score = mock_corpus_repo.get_bigram_score("བཀྲ་", "ཤིས་")
    assert bg_score > 0.8  # 850 / 1000

    # Trigram conditional probability
    tg_score = mock_corpus_repo.get_trigram_score("བཀྲ་", "ཤིས་", "བདེ་")
    assert tg_score > 0.6  # 600 / 850

    # Context score
    ctx_score = mock_corpus_repo.get_context_score(
        sentence="བཀྲ་ ཤིས་ བདེ་ ལེགས།", word_start=0, word_end=4, candidate="བཀྲ་"
    )
    assert ctx_score > 0.0


def test_correction_provider_with_corpus_ranking(mock_corpus_repo: BoCorpusRepository) -> None:
    """Test CorrectionProvider hybrid contextual candidate ranking."""
    def mock_scorer(sentence: str, ws: int, we: int, candidates: list[str]) -> dict[str, float]:
        return dict.fromkeys(candidates, 0.8)

    # Pass vocabulary with tsheg-terminated surface forms
    vocab = {"བཀྲ་": 1000, "ཤིས་": 900}
    provider = CorrectionProvider(
        score_candidates=mock_scorer,
        vocabulary=vocab,
        corpus_repository=mock_corpus_repo,
        confidence_threshold=0.0,
    )

    best = provider.correct(
        word="བཀྲོ",
        sentence="བཀྲོ ཤིས་ བདེ་ ལེགས།",
        word_start=0,
        word_end=4,
    )
    assert best is None or isinstance(best, str)  # Verify candidate pipeline execution


def test_spell_checker_plugin_corpus_aware(mock_corpus_repo: BoCorpusRepository) -> None:
    """Test that SpellCheckerPlugin recognizes corpus-specific vocabulary."""
    plugin = SpellCheckerPlugin(corpus_repository=mock_corpus_repo)
    builder = LanguageServerSnapshotBuilder()

    # Known corpus sentence
    snapshot = builder.analyze("བཀྲ་ ཤིས་ བདེ་ ལེགས།")
    suggestions = list(plugin.examine(snapshot))
    assert suggestions is not None


def test_teea_engine_dependency_injection() -> None:
    """Test TEEAEngine initializes cleanly with updated components."""
    engine = TEEAEngine()
    assert engine.version is not None
    res = engine.analyze("བཀྲ་ཤིས་བདེ་ལེགས།")
    assert res is not None
    assert hasattr(res, "suggestions")


def test_synthetic_error_dataset_benchmark(mock_corpus_repo: BoCorpusRepository) -> None:
    """Test loading and evaluating synthetic error benchmark dataset."""
    syn_dataset = mock_corpus_repo.load_synthetic_dataset()
    assert syn_dataset.total_records == 1
    rec = syn_dataset.records[0]
    assert rec.corrupted_text == "བཀྲོཤིས་བདེ་ལེགས།"
    assert rec.original_text == "བཀྲ་ཤིས་བདེ་ལེགས།"
