"""Unit tests for BoCorpus pipeline builder and repository."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from teea.core.errors import ConfigurationError
from teea.corpus import BoCorpusPipeline, BoCorpusRepository, CorpusStatistics


@pytest.fixture
def fake_parquet(tmp_path: Path) -> Path:
    """Create a temporary mock Parquet corpus file for hermetic testing."""
    corpus_dir = tmp_path / "Corpus" / "BoCorpus"
    corpus_dir.mkdir(parents=True)
    parquet_path = corpus_dir / "bo_corpus.parquet"

    data = [
        {"text": "བཀྲ་ཤིས་བདེ་ལེགས་ཁམས་བཟང་། ང་ཚོས་སྐད་ཡིག་སློབ་སྦྱོང་བྱེད་གི་ཡོད།"},
        {"text": "དེ་རིང་ཉིན་མོ་དེ་ཧ་ཅང་སྤྲོ་པོ་ཡིན། ང་ཚོས་ཁ་ལག་ཟ་གི་ཡོད།"},
    ]
    table = pa.Table.from_pylist(data)
    pq.write_table(table, str(parquet_path))
    return parquet_path


def test_bocorpus_pipeline_processing(tmp_path: Path, fake_parquet: Path) -> None:
    corpus_dir = fake_parquet.parent
    processed_dir = tmp_path / "Processed"
    synthetic_dir = tmp_path / "SyntheticErrors"

    pipeline = BoCorpusPipeline(
        corpus_dir=corpus_dir,
        processed_dir=processed_dir,
        synthetic_dir=synthetic_dir,
    )
    result = pipeline.process(skip_download=True, synthetic_count=2)

    assert result["vocab_path"] == str(processed_dir / "bocorpus_vocabulary.json")
    assert Path(result["vocab_path"]).exists()
    assert Path(result["ngram_path"]).exists()
    assert Path(result["stats_path"]).exists()
    assert Path(result["synthetic_path"]).exists()

    stats = CorpusStatistics.model_validate(result["stats"])
    assert stats.total_documents == 2
    assert stats.total_syllables > 0
    assert stats.unique_syllables > 0
    assert 0.0 <= stats.type_token_ratio <= 1.0


def test_bocorpus_repository(tmp_path: Path, fake_parquet: Path) -> None:
    corpus_dir = fake_parquet.parent
    processed_dir = tmp_path / "Processed"
    synthetic_dir = tmp_path / "SyntheticErrors"

    pipeline = BoCorpusPipeline(
        corpus_dir=corpus_dir,
        processed_dir=processed_dir,
        synthetic_dir=synthetic_dir,
    )
    pipeline.process(skip_download=True, synthetic_count=2)

    repo = BoCorpusRepository(processed_dir=processed_dir, synthetic_dir=synthetic_dir)
    first_syllables = list(repo.vocabulary.keys())
    assert len(first_syllables) > 0
    test_syllable = first_syllables[0]
    assert repo.is_known_syllable(test_syllable)
    assert repo.get_syllable_frequency(test_syllable) > 0
    assert isinstance(repo.bigrams, dict)

    syn_ds = repo.load_synthetic_dataset()
    assert syn_ds.total_records > 0


def test_repository_missing_files(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"
    repo = BoCorpusRepository(processed_dir=missing_dir, synthetic_dir=missing_dir)
    with pytest.raises(ConfigurationError):
        _ = repo.vocabulary

    with pytest.raises(ConfigurationError):
        _ = repo.load_synthetic_dataset()


def test_download_fallback_and_error(
    tmp_path: Path, fake_parquet: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_dir = fake_parquet.parent
    pipeline = BoCorpusPipeline(corpus_dir=corpus_dir)
    files = pipeline.download()
    assert len(files) == 1
    assert files[0] == fake_parquet

    def mock_list_repo_files(*args: object, **kwargs: object) -> list[str]:
        raise RuntimeError("Simulated network failure")

    from huggingface_hub import HfApi  # noqa: PLC0415

    monkeypatch.setattr(HfApi, "list_repo_files", mock_list_repo_files)

    empty_pipeline = BoCorpusPipeline(corpus_dir=tmp_path / "empty_dir")
    with pytest.raises(ConfigurationError) as exc_info:
        empty_pipeline.download()
    assert "Failed to download dataset" in str(exc_info.value)
    assert "How to fix" in str(exc_info.value)
