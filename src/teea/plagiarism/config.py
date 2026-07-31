"""Plagiarism detection configuration.

Figure 8 specifies configurable parameters for the fingerprinting pipeline.
These defaults work well for Tibetan text where each code point is 3 UTF-8
bytes and a "word" (tsheg-delimited syllable) is typically 2-5 characters.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PlagiarismSettings(BaseSettings):
    """Configuration for the plagiarism detection subsystem.

    Attributes:
        kgram_size: Number of *characters* per k-gram.  Tibetan syllables
            average 2-5 characters, so k=6 captures sub-syllable patterns.
        winnow_window: Number of consecutive hashes per winnowing window.
            The standard Robust Winnowing value is ``w = 4``, guaranteeing
            that any match of at least ``k + w - 1`` characters is detected.
        min_similarity: Default minimum similarity threshold for reporting
            matches (``0.0`` = no minimum, ``1.0`` = exact match).
        min_document_length: Minimum document character length below which
            fingerprinting is skipped (empty or tiny documents cannot produce
            meaningful fingerprints).
        ignore_trivial_matches: When ``True``, matches whose fingerprints are
            a subset of a higher-ranked match are suppressed.
        normalization_form: Unicode normalization form applied before
            fingerprinting (default ``"NFC"``).
    """

    model_config = SettingsConfigDict(
        env_prefix="TEEA_PLAGIARISM__",
        env_file=None,
        extra="forbid",
        frozen=True,
    )

    kgram_size: int = Field(default=6, gt=1, le=100)
    winnow_window: int = Field(default=4, gt=1, le=50)
    min_similarity: float = Field(default=0.1, ge=0.0, le=1.0)
    min_document_length: int = Field(default=20, ge=0)
    ignore_trivial_matches: bool = True
    normalization_form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFC"
    corpus_parquet_path: str = Field(default="Data/Corpus/BoCorpus/bo_corpus.parquet")
    max_chunk_chars: int = Field(default=100000, gt=100)


__all__ = ["PlagiarismSettings"]
