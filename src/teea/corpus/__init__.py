"""Corpus integration and dataset processing package for TEEA.

Provides BoCorpus downloader, vocabulary & n-gram extractor, synthetic error generator,
and dataset repository.
"""

from __future__ import annotations

from teea.corpus.builder import BoCorpusPipeline, CorpusStatistics
from teea.corpus.repository import BoCorpusRepository
from teea.corpus.synthetic import (
    SyntheticErrorDataset,
    SyntheticErrorGenerator,
    SyntheticErrorRecord,
)

__all__ = [
    "BoCorpusPipeline",
    "BoCorpusRepository",
    "CorpusStatistics",
    "SyntheticErrorDataset",
    "SyntheticErrorGenerator",
    "SyntheticErrorRecord",
]
