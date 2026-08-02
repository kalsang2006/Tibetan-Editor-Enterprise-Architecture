"""Pluggable Correction Providers for TEEA Spell Checker.

Two providers are shipped:

* :class:`DictionaryOnlyCorrectionProvider` -- pure dictionary + edit-distance
  candidate generation.  It retrieves candidates through a character-bigram
  inverted index over the vocabulary, scores them with grapheme-aware
  Damerau-Levenshtein distance (see :mod:`teea.nlp.edit_distance`), applies a
  dynamic edit-distance cap (rare words get a wider net), and augments the
  result with the canonical vowel-transposition and missing-tsheg-split
  candidates from :mod:`teea.plugins.builtin.correction`.
* :class:`TibertCorrectionProvider` -- wraps the dictionary provider and
  reranks its candidates with an AI runtime when one is attached.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import structlog

from teea.nlp.char_bigram_index import CharBigramIndex
from teea.nlp.edit_distance import tibetan_damerau
from teea.persistence import DictionaryRepository
from teea.plugins.builtin.correction import _canonical_tibetan_syllable

logger = structlog.get_logger(__name__)

#: Minimum corpus frequency for a word to count as "common" and get the
#: tighter edit-distance cap.  Words at or below this are treated as rare.
_DEFAULT_RARE_FREQUENCY = 10
#: Dynamic cap applied to rare words (common words keep ``max_edit_distance``).
_DEFAULT_RARE_MAX_DISTANCE = 3

TSHEG = "\u0f0b"
_STRIP_CHARS = "་ །\u0f0b\u0f0d "


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Pure Python Levenshtein distance computation (kept for compatibility)."""
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


@dataclass
class CorrectionCandidate:
    """One ranked correction suggestion.

    Attributes:
        word: The suggested surface form.
        confidence: The provider's confidence in ``[0, 1]``.
    """

    word: str
    confidence: float


class CorrectionProvider(ABC):
    """Abstract Base Class for correction candidate generators."""

    @abstractmethod
    def generate_candidates(
        self,
        word: str,
        sentence: str,
        max_candidates: int = 10,
    ) -> list[CorrectionCandidate]:
        """Generate ranked list of correction candidates for a misspelled word."""


class DictionaryOnlyCorrectionProvider(CorrectionProvider):
    """Generates correction candidates using a char-bigram index and grapheme-aware distance.

    Candidate retrieval is index-driven: the vocabulary is inverted by its
    character bigrams once (lazily), so querying is proportional to shared
    bigrams rather than a full vocabulary scan.  Candidates are then filtered
    and scored by :func:`teea.nlp.edit_distance.tibetan_damerau`, which
    groups Tibetan base letters with their combining marks so a vowel-sign or
    subjoined-consonant error counts as one edit.

    The edit-distance cap is dynamic: a word whose corpus frequency is below
    ``rare_frequency`` gets ``rare_max_distance`` edits of room (default 3)
    instead of the configured ``max_edit_distance`` (default 2), so rare words
    -- which have few near neighbours -- are not cut off from their correct
    form.

    Args:
        dictionary: The dictionary whose vocabulary is searched.
        max_edit_distance: Distance cap for common words.
        frequencies: Optional ``{word: frequency}`` map used both for the
            dynamic threshold and for confidence scaling.
        rare_frequency: Corpus frequency at or below which a word is "rare".
        rare_max_distance: Distance cap used for rare words.
        corpus_repository: Optional corpus repository (duck-typed) used by the
            missing-tsheg-split candidate check.
    """

    def __init__(
        self,
        dictionary: DictionaryRepository,
        max_edit_distance: int = 2,
        frequencies: dict[str, int] | None = None,
        *,
        rare_frequency: int = _DEFAULT_RARE_FREQUENCY,
        rare_max_distance: int = _DEFAULT_RARE_MAX_DISTANCE,
        corpus_repository: Any = None,
    ) -> None:
        self._dictionary = dictionary
        self._max_edit_distance = max_edit_distance
        self._frequencies = frequencies or {}
        self._rare_frequency = rare_frequency
        self._rare_max_distance = max(rare_max_distance, max_edit_distance)
        self._corpus_repository = corpus_repository
        self._max_freq = max(self._frequencies.values()) if self._frequencies else 1

        self._vocab: list[str] = []
        self._vocab_set: set[str] = set()
        self._index: CharBigramIndex | None = None
        self._resolve_vocabulary()

    # -- Vocabulary resolution -------------------------------------------------

    def _resolve_vocabulary(self) -> None:
        """Resolve the searchable vocabulary from the dictionary.

        The dictionary may expose ``vocabulary``, a ``words()`` method, or a
        private ``_emissions`` mapping.  Forms are normalised to their
        tsheg-stripped surface so queries and keys share one space.
        """
        vocab: Any = getattr(self._dictionary, "vocabulary", None)
        if vocab is None:
            if hasattr(self._dictionary, "words"):
                vocab = self._dictionary.words()
            elif hasattr(self._dictionary, "_emissions"):
                vocab = self._dictionary._emissions.keys()
            else:
                vocab = []
        for raw in vocab:
            cleaned = str(raw).strip(_STRIP_CHARS)
            if cleaned:
                self._vocab.append(cleaned)
        self._vocab_set = set(self._vocab)

    def _bigram_index(self) -> CharBigramIndex:
        """Return the lazily-built char-bigram index over the vocabulary."""
        if self._index is None:
            self._index = CharBigramIndex(self._vocab)
        return self._index

    # -- Frequency helpers -----------------------------------------------------

    def _frequency_of(self, word: str) -> int:
        """Return the corpus frequency of ``word`` (0 when unknown)."""
        cleaned = word.strip(_STRIP_CHARS)
        for key in (cleaned, cleaned + TSHEG):
            value = self._frequencies.get(key)
            if value is not None:
                if isinstance(value, dict):
                    return int(value.get("freq", 1))
                return int(value)
        return 0

    def _is_rare(self, word: str) -> bool:
        """Return whether ``word`` is rare enough to widen the distance cap."""
        if not self._frequencies:
            return False
        return self._frequency_of(word) <= self._rare_frequency

    def _max_distance_for(self, word: str) -> int:
        """Return the dynamic edit-distance cap for ``word``.

        Rare words get ``rare_max_distance``; common (or frequency-unaware)
        words keep ``max_edit_distance``.
        """
        return self._rare_max_distance if self._is_rare(word) else self._max_edit_distance

    # -- Candidate generation --------------------------------------------------

    def generate_candidates(
        self,
        word: str,
        sentence: str,
        max_candidates: int = 10,
    ) -> list[CorrectionCandidate]:
        """Generate ranked correction candidates for ``word``.

        Candidates come from three sources, merged and deduplicated:

        1. The char-bigram index, filtered by grapheme-aware Damerau distance
           under the dynamic cap.
        2. The canonical vowel-transposition form (e.g. ``བདོ`` -> ``བོད``).
        3. Missing-tsheg splits (e.g. ``བཀྲཤིས`` -> ``བཀྲ་ཤིས``) where both
           halves are attested in the vocabulary.

        A full-scan fallback runs only when the index finds nothing (e.g. very
        short words with no bigram overlap).

        Args:
            word: The unknown surface form.
            sentence: The sentence containing it (unused here; kept for the
                provider protocol).
            max_candidates: Maximum number of candidates to return.

        Returns:
            Ranked candidates, best first.
        """
        clean_word = word.strip(_STRIP_CHARS)
        if not clean_word:
            return []

        word_has_tsheg = word.endswith(TSHEG)
        max_distance = self._max_distance_for(clean_word)
        scored: list[tuple[int, str]] = []

        # 1. Index-driven retrieval + grapheme-aware distance filter.
        retrieved = self._bigram_index().query(clean_word, max_results=200)
        if retrieved:
            for candidate in retrieved:
                if candidate == clean_word:
                    continue
                distance = tibetan_damerau(clean_word, candidate)
                if 0 < distance <= max_distance:
                    scored.append((distance, candidate))
        else:
            # Fallback for short words / no-bigram overlap: length-bucketed scan.
            for candidate in self._vocab:
                if candidate == clean_word:
                    continue
                if abs(len(clean_word) - len(candidate)) > max_distance:
                    continue
                distance = tibetan_damerau(clean_word, candidate)
                if 0 < distance <= max_distance:
                    scored.append((distance, candidate))

        # 2. Canonical vowel transposition candidate (e.g. བདོ -> བོད).
        canon = _canonical_tibetan_syllable(clean_word)
        if canon != clean_word and canon in self._vocab_set:
            scored.append((1, canon))

        # 3. Missing-tsheg split candidates.
        scored.extend(
            (1, split) for split in self._tsheg_split_candidates(clean_word)
        )

        return self._rank(scored, word_has_tsheg, max_candidates)

    # -- Missing-tsheg split candidates ----------------------------------------

    def _tsheg_split_candidates(self, word: str) -> list[str]:
        """Return attested split candidates for a tsheg-less ``word``.

        A tsheg-less string of four or more characters may be two syllables
        glued together (e.g. ``བཀྲཤིས`` -> ``བཀྲ་ཤིས``).  Every split point
        whose halves are both attested (in the vocabulary or, when available,
        the corpus repository) is returned.

        Args:
            word: The tsheg-less surface form.

        Returns:
            Candidate split forms (with the tsheg re-inserted).
        """
        if TSHEG in word or len(word) < 4:
            return []
        splits: list[str] = []
        is_known = (
            getattr(self._corpus_repository, "is_known_syllable", None)
            if self._corpus_repository is not None
            else None
        )
        for idx in range(2, len(word) - 1):
            part1 = word[:idx] + TSHEG
            part1_clean = part1.rstrip(TSHEG)
            part2 = word[idx:]
            part2_with_tsheg = part2 + TSHEG if not part2.endswith(TSHEG) else part2
            part2_clean = part2.rstrip(TSHEG)

            # The vocabulary set stores tsheg-stripped forms, so each half is
            # matched against both the tsheg-terminated and the cleaned form.
            p1_known = (part1 in self._vocab_set or part1_clean in self._vocab_set) or (
                is_known is not None and bool(is_known(part1))
            )
            p2_known = (
                part2 in self._vocab_set
                or part2_clean in self._vocab_set
                or part2_with_tsheg in self._vocab_set
            ) or (
                is_known is not None
                and (bool(is_known(part2)) or bool(is_known(part2_with_tsheg)))
            )
            if p1_known and p2_known:
                splits.append(part1 + part2)
                # Also offer the tsheg-terminated variant when the second half is
                # an attested syllable (the vocabulary set stores stripped forms,
                # so ``part2_clean`` is the membership key, not ``part2_with_tsheg``).
                if not (part1 + part2).endswith(TSHEG) and part2_clean in self._vocab_set:
                    splits.append(part1 + part2_with_tsheg)
        return splits

    # -- Ranking ---------------------------------------------------------------

    def _rank(
        self,
        scored: list[tuple[int, str]],
        word_has_tsheg: bool,
        max_candidates: int,
    ) -> list[CorrectionCandidate]:
        """Convert raw ``(distance, word)`` pairs into ranked candidates.

        Confidence starts from a distance base (closer is more confident) and
        is scaled by log-frequency when frequency data is available.

        Args:
            scored: ``(distance, word)`` pairs.
            word_has_tsheg: Whether the query word carried a trailing tsheg.
            max_candidates: Maximum number of candidates to return.

        Returns:
            Ranked, deduplicated candidates.
        """
        candidates: list[CorrectionCandidate] = []
        seen: set[str] = set()
        for distance, cleaned in sorted(scored):
            suggested = cleaned + TSHEG if word_has_tsheg else cleaned
            if suggested in seen:
                continue
            seen.add(suggested)

            base = {0: 0.95, 1: 0.85, 2: 0.70}.get(distance, 0.55)
            confidence = float(base)
            if self._frequencies:
                freq = self._frequency_of(cleaned)
                norm_freq = math.log(freq + 1) / math.log(self._max_freq + 1)
                confidence = round(base * (0.85 + 0.15 * norm_freq), 2)
            candidates.append(CorrectionCandidate(word=suggested, confidence=confidence))

        candidates.sort(key=lambda c: c.confidence, reverse=True)
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
        max_candidates: int = 10,
    ) -> list[CorrectionCandidate]:
        """Generate and TiBERT-rerank candidates for ``word``.

        Delegates candidate generation to the dictionary provider, then, when
        an AI runtime is attached, reranks the candidates by blending the
        model's per-candidate scores with the dictionary provider's own
        confidence.

        Args:
            word: The unknown surface form.
            sentence: The sentence containing it.
            max_candidates: Maximum number of candidates to return.

        Returns:
            Ranked candidates, best first.
        """
        edit_candidates = self._dictionary_provider.generate_candidates(
            word, sentence, max_candidates=max_candidates * 2
        )

        if not edit_candidates or self._ai_runtime is None:
            return edit_candidates[:max_candidates]

        try:
            from teea.ai.models import CapabilityKind, InferenceRequest  # noqa: PLC0415
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
                        # Unscored candidates keep the dictionary heuristic.
                        continue
                    # Score-fusion fix: the model's raw score is authoritative
                    # for ranking; it is not blended with the edit-distance
                    # heuristic confidence.
                    c.confidence = round(tibert_score, 3)

                edit_candidates.sort(key=lambda x: x.confidence, reverse=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "tibert_reranking_failed",
                error=str(exc),
                word=word,
                fallback_used=True,
            )

        return edit_candidates[:max_candidates]


__all__ = [
    "CorrectionCandidate",
    "CorrectionProvider",
    "DictionaryOnlyCorrectionProvider",
    "TibertCorrectionProvider",
]
