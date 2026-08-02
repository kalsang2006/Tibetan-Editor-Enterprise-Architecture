"""Unit test for teea build-dataset CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pyarrow")
import pyarrow as pa
import pyarrow.parquet as pq

from teea.cli import main


def test_cli_build_dataset(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "Corpus" / "BoCorpus"
    corpus_dir.mkdir(parents=True)
    parquet_path = corpus_dir / "bo_corpus.parquet"

    data = [
        {"text": "བཀྲ་ཤིས་བདེ་ལེགས་ཁམས་བཟང་། ང་ཚོས་སྐད་ཡིག་སློབ་སྦྱོང་བྱེད་གི་ཡོད།"},
    ]
    table = pa.Table.from_pylist(data)
    pq.write_table(table, str(parquet_path))

    processed_dir = tmp_path / "Processed"
    synthetic_dir = tmp_path / "SyntheticErrors"

    argv = [
        "build-dataset",
        "--corpus-dir",
        str(corpus_dir),
        "--output-dir",
        str(processed_dir),
        "--synthetic-dir",
        str(synthetic_dir),
        "--synthetic-count",
        "2",
        "--skip-download",
    ]

    exit_code = main(argv)
    assert exit_code == 0
    assert (processed_dir / "bocorpus_vocabulary.json").exists()
    assert (processed_dir / "bocorpus_ngrams.json").exists()
    assert (processed_dir / "corpus_stats.json").exists()
    assert (synthetic_dir / "synthetic_errors.json").exists()
