"""Synthetic Tibetan spelling and grammar error generator.

Generates realistic spelling, typographical, and grammatical errors from clean
Tibetan text for training and evaluation datasets.
"""

from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from teea.core.logging import get_logger
from teea.core.types import TSHEG_CHARS
from teea.nlp.segmentation import TibetanSentenceSegmenter
from teea.nlp.tokenization import SyllableSegmenter, TextNormalizer

_logger = get_logger(__name__)

ErrorType = Literal[
    "TSHEG_DROP",
    "SYLLABLE_SWAP",
    "CHARACTER_CONFUSION",
    "VOWEL_MUTATION",
    "WORD_DUPLICATION",
    "CASE_PARTICLE_SUBSTITUTION",
    "PARTICLE_OMISSION",
]

# Common Tibetan character confusion pairs (visual/phonetic similarities)
_CONFUSION_PAIRS: dict[str, str] = {
    "ང་": "ད་",
    "ད་": "ང་",
    "ག": "ང་",
    "ཕ": "བ",
    "བ": "ཕ",
    "ཏ": "ཐ",
    "ཐ": "ཏ",
}

# Vowel sign mutations
_VOWEL_SIGNS: list[str] = ["ི", "ུ", "ེ", "ོ"]

# Tibetan case particles for substitution
_CASE_PARTICLES: list[str] = ["ལ་", "གིས་", "ཀྱིས་", "གི་", "ཀྱི་", "ནས་", "ལས་", "དང་"]


class SyntheticErrorRecord(BaseModel):
    """A single synthetic error pair with ground truth and metadata."""

    id: str = Field(description="Unique error pair identifier")
    original_text: str = Field(description="Clean ground-truth Tibetan text")
    corrupted_text: str = Field(description="Synthetic error-injected text")
    error_type: ErrorType = Field(description="Category of error injected")
    char_start: int = Field(description="Character start offset of the error")
    char_end: int = Field(description="Character end offset of the error in corrupted text")
    description: str = Field(description="Human-readable explanation of the error")


class SyntheticErrorDataset(BaseModel):
    """Container for synthetic error records."""

    version: str = Field(default="1.0.0", description="Dataset schema version")
    total_records: int = Field(description="Number of synthetic error records")
    records: list[SyntheticErrorRecord] = Field(default_factory=list)


class SyntheticErrorGenerator:
    """Generates synthetic Tibetan spelling and grammar errors from clean text."""

    def __init__(self, seed: int | None = 42) -> None:
        self._random = random.Random(seed)
        self._normalizer = TextNormalizer()
        self._syllable_segmenter = SyllableSegmenter()
        self._sentence_segmenter = TibetanSentenceSegmenter()

    def corrupt_sentence(
        self, sentence: str, record_id: str = "err-001"
    ) -> SyntheticErrorRecord | None:
        """Inject a single synthetic error into a clean Tibetan sentence.

        Args:
            sentence: Clean Tibetan input sentence.
            record_id: Unique record ID.

        Returns:
            A SyntheticErrorRecord, or None if the sentence cannot be corrupted.
        """
        clean = self._normalizer.normalize(sentence).strip()
        if not clean or len(clean) < 5:
            return None

        strategies = [
            self._inject_tsheg_drop,
            self._inject_syllable_swap,
            self._inject_character_confusion,
            self._inject_vowel_mutation,
            self._inject_word_duplication,
            self._inject_case_particle_substitution,
            self._inject_particle_omission,
        ]
        self._random.shuffle(strategies)

        for strategy in strategies:
            record = strategy(clean, record_id)
            if record is not None:
                return record

        return None

    def generate_dataset(
        self, sentences: list[str], max_count: int = 10000
    ) -> SyntheticErrorDataset:
        """Generate a dataset of synthetic error pairs from clean sentences.

        Args:
            sentences: List of clean Tibetan sentences.
            max_count: Maximum number of error records to generate.

        Returns:
            A SyntheticErrorDataset object.
        """
        records: list[SyntheticErrorRecord] = []
        _logger.info(
            "generating_synthetic_errors",
            total_sentences=len(sentences),
            max_count=max_count,
        )

        for _idx, sentence in enumerate(sentences):
            if len(records) >= max_count:
                break
            record_id = f"err-{len(records) + 1:06d}"
            record = self.corrupt_sentence(sentence, record_id=record_id)
            if record is not None:
                records.append(record)

        _logger.info("synthetic_errors_generated", count=len(records))
        return SyntheticErrorDataset(total_records=len(records), records=records)

    # -- Corruption Strategies ----------------------------------------------

    def _inject_tsheg_drop(self, clean: str, record_id: str) -> SyntheticErrorRecord | None:
        """Drop a tsheg delimiter between two syllables."""
        tsheg_indices = [
            i for i, ch in enumerate(clean) if ch in TSHEG_CHARS and 0 < i < len(clean) - 1
        ]
        if not tsheg_indices:
            return None
        idx = self._random.choice(tsheg_indices)
        corrupted = clean[:idx] + clean[idx + 1 :]
        return SyntheticErrorRecord(
            id=record_id,
            original_text=clean,
            corrupted_text=corrupted,
            error_type="TSHEG_DROP",
            char_start=idx,
            char_end=idx + 1,
            description=f"Omitted tsheg at index {idx}",
        )

    def _inject_syllable_swap(self, clean: str, record_id: str) -> SyntheticErrorRecord | None:
        """Swap two adjacent syllables."""
        syllables = self._syllable_segmenter.segment(clean)
        if len(syllables) < 2:
            return None
        idx = self._random.randint(0, len(syllables) - 2)
        s1, s2 = syllables[idx], syllables[idx + 1]
        
        start = s1.span.char_start
        end = s2.span.char_end
        swapped = s2.text + s1.text
        corrupted = clean[:start] + swapped + clean[end:]
        return SyntheticErrorRecord(
            id=record_id,
            original_text=clean,
            corrupted_text=corrupted,
            error_type="SYLLABLE_SWAP",
            char_start=start,
            char_end=start + len(swapped),
            description=f"Swapped syllables '{s1.text}' and '{s2.text}'",
        )

    def _inject_character_confusion(
        self, clean: str, record_id: str
    ) -> SyntheticErrorRecord | None:
        """Replace a character with a visually/phonetically confused pair."""
        candidates = [i for i, ch in enumerate(clean) if ch in _CONFUSION_PAIRS]
        if not candidates:
            return None
        idx = self._random.choice(candidates)
        target_char = clean[idx]
        confused_char = _CONFUSION_PAIRS[target_char]
        corrupted = clean[:idx] + confused_char + clean[idx + 1 :]
        return SyntheticErrorRecord(
            id=record_id,
            original_text=clean,
            corrupted_text=corrupted,
            error_type="CHARACTER_CONFUSION",
            char_start=idx,
            char_end=idx + 1,
            description=f"Replaced '{target_char}' with confused character '{confused_char}'",
        )

    def _inject_vowel_mutation(self, clean: str, record_id: str) -> SyntheticErrorRecord | None:
        """Mutate or replace a Tibetan vowel sign."""
        candidates = [i for i, ch in enumerate(clean) if ch in _VOWEL_SIGNS]
        if not candidates:
            return None
        idx = self._random.choice(candidates)
        old_vowel = clean[idx]
        new_vowel = self._random.choice([v for v in _VOWEL_SIGNS if v != old_vowel])
        corrupted = clean[:idx] + new_vowel + clean[idx + 1 :]
        return SyntheticErrorRecord(
            id=record_id,
            original_text=clean,
            corrupted_text=corrupted,
            error_type="VOWEL_MUTATION",
            char_start=idx,
            char_end=idx + 1,
            description=f"Mutated vowel sign '{old_vowel}' to '{new_vowel}'",
        )

    def _inject_word_duplication(self, clean: str, record_id: str) -> SyntheticErrorRecord | None:
        """Duplicate a word or syllable."""
        syllables = self._syllable_segmenter.segment(clean)
        if not syllables:
            return None
        target = self._random.choice(syllables)
        start = target.span.char_start
        end = target.span.char_end
        duplicated = clean[start:end] + target.text
        corrupted = clean[:end] + target.text + clean[end:]
        return SyntheticErrorRecord(
            id=record_id,
            original_text=clean,
            corrupted_text=corrupted,
            error_type="WORD_DUPLICATION",
            char_start=start,
            char_end=start + len(duplicated),
            description=f"Duplicated syllable/word '{target.text}'",
        )

    def _inject_case_particle_substitution(
        self, clean: str, record_id: str
    ) -> SyntheticErrorRecord | None:
        """Substitute a Tibetan case particle with another particle."""
        for p in _CASE_PARTICLES:
            idx = clean.find(p)
            if idx != -1:
                alt = self._random.choice([part for part in _CASE_PARTICLES if part != p])
                corrupted = clean[:idx] + alt + clean[idx + len(p) :]
                return SyntheticErrorRecord(
                    id=record_id,
                    original_text=clean,
                    corrupted_text=corrupted,
                    error_type="CASE_PARTICLE_SUBSTITUTION",
                    char_start=idx,
                    char_end=idx + len(alt),
                    description=f"Substituted case particle '{p}' with '{alt}'",
                )
        return None

    def _inject_particle_omission(self, clean: str, record_id: str) -> SyntheticErrorRecord | None:
        """Omit a grammatical case particle."""
        for p in _CASE_PARTICLES:
            idx = clean.find(p)
            if idx != -1:
                corrupted = clean[:idx] + clean[idx + len(p) :]
                return SyntheticErrorRecord(
                    id=record_id,
                    original_text=clean,
                    corrupted_text=corrupted,
                    error_type="PARTICLE_OMISSION",
                    char_start=idx,
                    char_end=idx,
                    description=f"Omitted case particle '{p}'",
                )
        return None
