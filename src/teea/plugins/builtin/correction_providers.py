"""Pluggable Correction Providers for TEEA Spell Checker."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import structlog

from teea.persistence import DictionaryRepository

logger = structlog.get_logger(__name__)


@dataclass
class CorrectionCandidate:
    word: str
    confidence: float


class CorrectionProvider(ABC):
    """Abstract Base Class for correction candidate generators."""

    @abstractmethod
    def generate_candidates(
        self,
        word: str,
        sentence: str,
        max_candidates: int = 5,
    ) -> list[CorrectionCandidate]:
        """Generate ranked list of correction candidates for a misspelled word."""


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Pure Python Levenshtein distance computation."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


class DictionaryOnlyCorrectionProvider(CorrectionProvider):
    """Generates correction candidates using dictionary Trie and edit-distance."""

    def __init__(
        self,
        dictionary: DictionaryRepository,
        max_edit_distance: int = 2,
        frequencies: dict[str, int] | None = None,
    ) -> None:
        self._dictionary = dictionary
        self._max_edit_distance = max_edit_distance
        self._frequencies = frequencies or {}
        self._max_freq = max(self._frequencies.values()) if self._frequencies else 1

    def generate_candidates(
        self,
        word: str,
        sentence: str,
        max_candidates: int = 5,
    ) -> list[CorrectionCandidate]:
        clean_word = word.strip("་ །\u0f0b\u0f0d ")
        if not clean_word:
            return []

        vocab = getattr(self._dictionary, "vocabulary", None)
        if vocab is None:
            if hasattr(self._dictionary, "words"):
                vocab = self._dictionary.words()
            elif hasattr(self._dictionary, "_emissions"):
                vocab = self._dictionary._emissions.keys()
            else:
                vocab = []

        import math
        candidates: list[CorrectionCandidate] = []
        for dict_word in vocab:
            dist = _levenshtein_distance(clean_word, dict_word)
            if dist <= self._max_edit_distance:
                base_confidence = 0.95 if dist == 0 else (0.85 if dist == 1 else 0.70)
                if self._frequencies:
                    freq = self._frequencies.get(dict_word, 1)
                    freq_val = freq.get("freq", 1) if isinstance(freq, dict) else int(freq)
                    norm_freq = math.log(freq_val + 1) / math.log(self._max_freq + 1)
                    confidence = round(base_confidence * (0.85 + 0.15 * norm_freq), 2)
                else:
                    confidence = base_confidence
                candidates.append(CorrectionCandidate(word=dict_word, confidence=confidence))

        candidates.sort(key=lambda x: x.confidence, reverse=True)
        return candidates[:max_candidates]


class TibertCorrectionProvider(CorrectionProvider):
    """Generates candidates via dictionary edit distance and reranks via TiBERT AI Runtime."""

    def __init__(
        self,
        dictionary: DictionaryRepository,
        ai_runtime: Any = None,
        max_edit_distance: int = 2,
    ) -> None:
        self._dictionary_provider = DictionaryOnlyCorrectionProvider(
            dictionary, max_edit_distance=max_edit_distance
        )
        self._ai_runtime = ai_runtime

    def generate_candidates(
        self,
        word: str,
        sentence: str,
        max_candidates: int = 5,
    ) -> list[CorrectionCandidate]:
        edit_candidates = self._dictionary_provider.generate_candidates(
            word, sentence, max_candidates=max_candidates * 2
        )

        if not edit_candidates or self._ai_runtime is None:
            return edit_candidates[:max_candidates]

        try:
            from teea.ai.models import CapabilityKind, InferenceRequest
            req = InferenceRequest(
                capability=CapabilityKind.SPELLING,
                inputs={
                    "sentence": sentence,
                    "word_start": 0,
                    "word_end": len(word),
                    "candidates": [c.word for c in edit_candidates],
                },
            )
            res = self._ai_runtime.infer(req)
            scores = res.outputs.get("scores")

            if isinstance(scores, (list, dict)):
                for i, c in enumerate(edit_candidates):
                    if isinstance(scores, list) and i < len(scores):
                        tibert_score = float(scores[i])
                    elif isinstance(scores, dict) and c.word in scores:
                        tibert_score = float(scores[c.word])
                    else:
                        tibert_score = 0.5
                    c.confidence = round(tibert_score * 0.6 + c.confidence * 0.4, 3)

                edit_candidates.sort(key=lambda x: x.confidence, reverse=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tibert_reranking_failed",
                error=str(exc),
                word=word,
                fallback_used=True,
            )

        return edit_candidates[:max_candidates]
