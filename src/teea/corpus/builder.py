"""Corpus builder pipeline for openpecha/BoCorpus dataset integration.

Downloads, normalizes, extracts vocabulary & n-grams, produces corpus statistics,
and generates synthetic error datasets for TEEA.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from teea.core.logging import get_logger
from teea.corpus.synthetic import SyntheticErrorGenerator
from teea.nlp.segmentation import TibetanSentenceSegmenter
from teea.nlp.tokenization import SyllableSegmenter, TextNormalizer

_logger = get_logger(__name__)

BOCORPUS_HF_REPO = "openpecha/BoCorpus"
DEFAULT_CORPUS_DIR = Path("Data/Corpus/BoCorpus")
DEFAULT_PROCESSED_DIR = Path("Data/Processed")
DEFAULT_SYNTHETIC_DIR = Path("Data/SyntheticErrors")


class CorpusStatistics(BaseModel):
    """Metadata and statistics for the processed Tibetan corpus."""

    dataset_name: str = Field(default="openpecha/BoCorpus")
    total_documents: int = Field(description="Total document count")
    total_characters: int = Field(description="Total character count")
    total_sentences: int = Field(description="Total sentence count")
    total_syllables: int = Field(description="Total syllable count")
    unique_syllables: int = Field(description="Count of unique syllables")
    type_token_ratio: float = Field(description="Unique syllables / total syllables ratio")
    top_syllables: list[tuple[str, int]] = Field(default_factory=list)
    top_bigrams: list[tuple[str, int]] = Field(default_factory=list)
    top_trigrams: list[tuple[str, int]] = Field(default_factory=list)


class BoCorpusPipeline:
    """Orchestrates dataset downloading, preprocessing, n-gram extraction, and artifact export."""

    def __init__(
        self,
        corpus_dir: Path | str = DEFAULT_CORPUS_DIR,
        processed_dir: Path | str = DEFAULT_PROCESSED_DIR,
        synthetic_dir: Path | str = DEFAULT_SYNTHETIC_DIR,
    ) -> None:
        self.corpus_dir = Path(corpus_dir)
        self.processed_dir = Path(processed_dir)
        self.synthetic_dir = Path(synthetic_dir)

        self._normalizer = TextNormalizer()
        self._syllable_segmenter = SyllableSegmenter()
        self._sentence_segmenter = TibetanSentenceSegmenter()

    def get_local_parquet_files(self) -> list[Path]:
        """Find all local parquet files in corpus_dir."""
        if not self.corpus_dir.exists():
            return []
        return sorted(self.corpus_dir.rglob("*.parquet"))

    def download(self, force: bool = False) -> list[Path]:
        """Download openpecha/BoCorpus dataset files dynamically from Hugging Face.

        Args:
            force: Re-download even if local parquet files exist.

        Returns:
            List of downloaded local parquet file paths.

        Raises:
            ConfigurationError: If downloading fails and no local files exist.
        """
        import os  # noqa: PLC0415

        from teea.core.errors import ConfigurationError  # noqa: PLC0415

        self.corpus_dir.mkdir(parents=True, exist_ok=True)
        local_files = self.get_local_parquet_files()

        if local_files and not force:
            _logger.info(
                "corpus_already_exists",
                count=len(local_files),
                paths=[str(f) for f in local_files],
            )
            return local_files

        _logger.info(
            "downloading_bocorpus",
            repo=BOCORPUS_HF_REPO,
            corpus_dir=str(self.corpus_dir),
        )

        try:
            from huggingface_hub import HfApi, hf_hub_download  # noqa: PLC0415

            api = HfApi()
            repo_files = api.list_repo_files(BOCORPUS_HF_REPO, repo_type="dataset")
            parquet_filenames = [f for f in repo_files if f.endswith(".parquet")]

            if not parquet_filenames:
                raise ConfigurationError(
                    f"No .parquet files found in dataset '{BOCORPUS_HF_REPO}'."
                )

            downloaded_paths: list[Path] = []
            for filename in parquet_filenames:
                _logger.info("downloading_file", filename=filename)
                downloaded_file = hf_hub_download(
                    repo_id=BOCORPUS_HF_REPO,
                    filename=filename,
                    repo_type="dataset",
                    local_dir=str(self.corpus_dir),
                )
                downloaded_paths.append(Path(downloaded_file))

            _logger.info("download_complete", count=len(downloaded_paths))
            return downloaded_paths

        except Exception as exc:
            existing = self.get_local_parquet_files()
            if existing:
                _logger.warning("download_failed_using_local_files", error=str(exc))
                return existing

            is_offline = os.environ.get("HF_HUB_OFFLINE", "0") == "1"
            offline_reason = (
                " Environment variable HF_HUB_OFFLINE=1 is enabled in your environment."
                if is_offline
                else ""
            )
            fix_guide = (
                "Temporarily set $env:HF_HUB_OFFLINE=\"0\" to allow initial download, "
                f"or place your local .parquet file into '{self.corpus_dir}'."
                if is_offline
                else f"Check network connectivity or copy files into '{self.corpus_dir}'."
            )

            msg = f"Failed to download dataset '{BOCORPUS_HF_REPO}': {exc}.{offline_reason}"
            raise ConfigurationError(f"{msg}\nHow to fix: {fix_guide}") from exc

    def process(
        self,
        max_rows: int | None = None,
        synthetic_count: int = 10000,
        skip_download: bool = False,
    ) -> dict[str, Any]:
        """Run the full extraction and artifact generation pipeline.

        Args:
            max_rows: Optional row cap for dataset processing (for quick runs/testing).
            synthetic_count: Number of synthetic error pairs to generate.
            skip_download: Skip download phase and assume local parquet file exists.

        Returns:
            Dict containing summary of processed paths and statistics.
        """
        from teea.core.errors import ConfigurationError  # noqa: PLC0415

        if not skip_download:
            parquet_files = self.download()
        else:
            parquet_files = self.get_local_parquet_files()
            if not parquet_files:
                raise ConfigurationError(
                    f"No local .parquet files found in '{self.corpus_dir}'. "
                    f"Run without --skip-download to fetch from Hugging Face."
                )

        _logger.info(
            "processing_corpus",
            parquet_files=[str(f) for f in parquet_files],
            max_rows=max_rows,
        )

        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        tables = [pq.read_table(str(pf)) for pf in parquet_files]
        if not tables:
            raise ConfigurationError(f"No valid data tables in parquet files: {parquet_files}")

        table = pa.concat_tables(tables) if len(tables) > 1 else tables[0]
        num_rows = len(table)
        _logger.info("parquet_loaded", total_rows=num_rows, files_read=len(tables))

        text_column = "text" if "text" in table.column_names else table.column_names[0]
        rows_to_process = min(num_rows, max_rows) if max_rows is not None else num_rows

        char_counter: Counter[str] = Counter()
        syllable_counter: Counter[str] = Counter()
        bigram_counter: Counter[str] = Counter()
        trigram_counter: Counter[str] = Counter()

        total_chars = 0
        total_syllables = 0
        all_sentences: list[str] = []

        for i in range(rows_to_process):
            raw_val = table[text_column][i].as_py()
            if not raw_val or not isinstance(raw_val, str):
                continue

            normalized = self._normalizer.normalize(raw_val)
            total_chars += len(normalized)
            char_counter.update(normalized)

            # Extract sentences efficiently
            for s in normalized.split("།"):
                stext = s.strip()
                if len(stext) > 5:
                    all_sentences.append(stext + "།")

            # Extract syllables
            syl_objs = self._syllable_segmenter.segment(normalized)
            syl_texts = [s.text for s in syl_objs]
            total_syllables += len(syl_texts)
            syllable_counter.update(syl_texts)

            from itertools import pairwise  # noqa: PLC0415

            # Bigrams & Trigrams
            for b1, b2 in pairwise(syl_texts):
                bigram_counter[f"{b1} {b2}"] += 1
            for t1, t2, t3 in zip(syl_texts[:-2], syl_texts[1:-1], syl_texts[2:], strict=False):
                trigram_counter[f"{t1} {t2} {t3}"] += 1

        unique_syllables = len(syllable_counter)
        ttr = (unique_syllables / total_syllables) if total_syllables > 0 else 0.0

        stats = CorpusStatistics(
            dataset_name=BOCORPUS_HF_REPO,
            total_documents=rows_to_process,
            total_characters=total_chars,
            total_sentences=len(all_sentences),
            total_syllables=total_syllables,
            unique_syllables=unique_syllables,
            type_token_ratio=round(ttr, 6),
            top_syllables=syllable_counter.most_common(100),
            top_bigrams=bigram_counter.most_common(100),
            top_trigrams=trigram_counter.most_common(100),
        )

        # Ensure output directories exist
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.synthetic_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save Vocabulary
        vocab_path = self.processed_dir / "bocorpus_vocabulary.json"
        vocab_payload = {
            "total_syllables": total_syllables,
            "unique_syllables": unique_syllables,
            "syllable_frequencies": dict(syllable_counter.most_common()),
        }
        vocab_json = json.dumps(vocab_payload, indent=2, ensure_ascii=False)
        vocab_path.write_text(vocab_json, encoding="utf-8")

        # 2. Save N-grams
        ngram_path = self.processed_dir / "bocorpus_ngrams.json"
        ngram_payload = {
            "bigrams": dict(bigram_counter.most_common(50000)),
            "trigrams": dict(trigram_counter.most_common(50000)),
        }
        ngram_json = json.dumps(ngram_payload, indent=2, ensure_ascii=False)
        ngram_path.write_text(ngram_json, encoding="utf-8")

        # 3. Save Corpus Stats
        stats_path = self.processed_dir / "corpus_stats.json"
        stats_path.write_text(stats.model_dump_json(indent=2), encoding="utf-8")

        # 4. Generate & Save Synthetic Error Dataset
        synthetic_generator = SyntheticErrorGenerator()
        synthetic_ds = synthetic_generator.generate_dataset(
            all_sentences, max_count=synthetic_count
        )
        synthetic_path = self.synthetic_dir / "synthetic_errors.json"
        synthetic_path.write_text(synthetic_ds.model_dump_json(indent=2), encoding="utf-8")

        _logger.info(
            "pipeline_artifacts_saved",
            vocab=str(vocab_path),
            ngrams=str(ngram_path),
            stats=str(stats_path),
            synthetic=str(synthetic_path),
        )

        return {
            "stats": stats.model_dump(),
            "vocab_path": str(vocab_path),
            "ngram_path": str(ngram_path),
            "stats_path": str(stats_path),
            "synthetic_path": str(synthetic_path),
        }
