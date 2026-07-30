"""AI-assisted spelling correction provider.

Generates candidate corrections for an unknown Tibetan word by finding
dictionary entries within a small edit distance, then ranks them using a
model-backed scoring function that evaluates how well each candidate fits
the surrounding sentence context.

This is the glue between the spell checker (which detects unknowns) and
the AI Runtime (which scores corrections).  It is deliberately model-agnostic:
the scoring function is a plain callable, so replacing TiBERT with Monlam AI
or any other backend requires no changes here.

Design notes
------------
* **Edit distance is character-level.**  Tibetan Unicode codepoints include
  subjoined consonants and vowel signs, so character-level Levenshtein
  distance is a reasonable approximation for surface-form similarity.
* **Candidate count is capped.**  Scoring is the expensive part (one or more
  model forward passes per candidate), so the candidate set is limited to
  the ``max_candidates`` closest words.
* **Failure is silent.**  If the scoring function raises, the provider returns
  ``None`` — the spell checker falls back to its existing advisory behaviour.
  A correction provider must never crash the plugin.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable

from teea.core.logging import get_logger

_logger = get_logger(__name__)

#: Callable that scores candidate corrections in sentence context.
#: Signature: (sentence, word_start, word_end, candidates) → {candidate: score}
ScoringFn = Callable[[str, int, int, list[str]], dict[str, float]]


class CorrectionProvider:
    """Generates and ranks spelling corrections using an AI model.

    Args:
        score_candidates: A callable that scores candidate words in context.
            See :data:`ScoringFn` for the expected signature.
        vocabulary: The set of known-correct surface forms to draw candidates
            from.  Typically the dictionary's vocabulary.
        max_edit_distance: Maximum Levenshtein distance for a candidate to be
            considered.
        max_candidates: Maximum number of candidates to score (the closest by
            edit distance are kept).
        confidence_threshold: Minimum score a candidate must reach to be
            returned as a correction.  Scores are in ``[0, 1]``.
    """

    def __init__(
        self,
        score_candidates: ScoringFn,
        vocabulary: frozenset[str] | set[str] | dict[str, int],
        *,
        max_edit_distance: int = 2,
        max_candidates: int = 20,
        confidence_threshold: float = 0.5,
        corpus_repository: Any = None,
    ) -> None:
        self._score = score_candidates
        self._vocabulary = frozenset(vocabulary.keys()) if isinstance(vocabulary, dict) else frozenset(vocabulary)
        self._confidence_threshold = confidence_threshold
        self._max_edit_distance = max_edit_distance
        self._max_candidates = max_candidates
        self._corpus_repository = corpus_repository

        # Pre-bucket vocabulary by length to optimize candidate generation
        import unicodedata
        self._vocab_by_length: dict[int, list[tuple[str, str]]] = {}
        for w in self._vocabulary:
            w_norm = unicodedata.normalize('NFC', w)
            self._vocab_by_length.setdefault(len(w_norm), []).append((w_norm, w))
        self._threshold = confidence_threshold

    def correct(
        self, word: str, sentence: str, word_start: int, word_end: int
    ) -> str | None:
        """Return the best correction for ``word`` in ``sentence``, or ``None``.

        Args:
            word: The unknown surface form.
            sentence: The full sentence for context.
            word_start: Character offset of the word's start within the sentence.
            word_end: Character offset of the word's end within the sentence.

        Returns:
            The highest-confidence correction above the threshold, or ``None``
            if no suitable candidate is found or the scoring function fails.
        """
        candidates = self._find_candidates(word)
        if not candidates:
            return None

        candidates = self._validate_candidates(word, sentence, word_end, candidates)
        if not candidates:
            return None
        try:
            scores_raw = self._score(sentence, word_start, word_end, candidates)
            if isinstance(scores_raw, dict):
                scores = scores_raw
            elif isinstance(scores_raw, (list, tuple)):
                scores = {c: float(scores_raw[i]) if i < len(scores_raw) else 0.5 for i, c in enumerate(candidates)}
            else:
                scores = {c: 0.5 for c in candidates}
        except Exception as exc:  # noqa: BLE001 — correction must never crash the plugin
            _logger.exception(
                "correction_scoring_failed",
                word=word,
                num_candidates=len(candidates),
                error=str(exc),
            )
            return None

        # Incorporate edit distance and corpus n-gram context to balance scoring
        word_norm = unicodedata.normalize("NFC", word)
        canon = _canonical_tibetan_syllable(word_norm)
        final_scores = {}
        for c in candidates:
            if c in scores:
                c_norm = unicodedata.normalize("NFC", c)
                dist = 0.5 if c_norm == canon else _damerau_levenshtein(word_norm, c_norm)
                raw_score = scores[c]
                
                # Context & unigram frequency score from BoCorpusRepository if available
                context_bonus = 0.0
                if self._corpus_repository is not None:
                    try:
                        context_bonus = self._corpus_repository.get_context_score(
                            sentence, word_start, word_end, c
                        )
                    except Exception:
                        context_bonus = 0.0

                # Hybrid score: 50% model score + 30% corpus/ngram context bonus - edit distance penalty
                hybrid_score = (0.5 * raw_score) + (0.3 * context_bonus) - (dist * 0.15)
                final_scores[c] = hybrid_score

        if not final_scores:
            return None

        # Select candidate with the highest combined confidence
        best_word = max(final_scores, key=lambda k: final_scores[k])
        raw_model_score = scores.get(best_word, 0.0)
        hybrid_score = final_scores[best_word]
        effective_score = max(raw_model_score, hybrid_score)
        if effective_score >= self._threshold:
            try:
                _logger.debug(
                    "correction_found",
                    word=word,
                    correction=best_word,
                    score=effective_score,
                )
            except Exception:
                pass
            return best_word

        try:
            _logger.debug(
                "correction_below_threshold",
                word=word,
                best=best_word,
                score=best_score,
                threshold=self._threshold,
            )
        except Exception:
            pass
        return None

    def _validate_candidates(
        self, word: str, sentence: str, word_end: int, candidates: list[str]
    ) -> list[str]:
        """Validate candidates against Tibetan orthographic rules."""
        TSHEG = "\u0f0b"
        valid = []

        word_has_tsheg = word.endswith(TSHEG)
        next_char = sentence[word_end] if word_end < len(sentence) else ""

        for cand in candidates:
            cand_has_tsheg = cand.endswith(TSHEG)

            # Rule 1: Prevent duplicate adjacent tshegs.
            if cand_has_tsheg and next_char == TSHEG:
                continue

            # Rule 2: Do not introduce a trailing tsheg if the source token lacked one,
            # unless the candidate is simply supplying the missing trailing tsheg (cand[:-1] == word).
            if cand_has_tsheg and not word_has_tsheg and cand[:-1] != word:
                continue

            # Rule 3: Do not drop a trailing tsheg if the source token had one,
            # unless the right context already provides a tsheg.
            if word_has_tsheg and not cand_has_tsheg and next_char != TSHEG:
                continue

            valid.append(cand)

        return valid

    def _find_candidates(self, word: str) -> list[str]:
        """Find dictionary words within ``max_edit_distance`` of ``word``."""
        import unicodedata
        
        scored: list[tuple[int, str]] = []
        max_dist = self._max_edit_distance

        if not word:
            return []

        word_norm = unicodedata.normalize('NFC', word)
        word_initial = word_norm[0]
        word_len = len(word_norm)

        # Check canonical vowel transposition candidate (e.g. བདོ -> བོད)
        canon = _canonical_tibetan_syllable(word_norm)
        if canon != word_norm and canon in self._vocabulary:
            scored.append((1, canon))

        # Check missing tsheg split candidates (e.g. བཀྲཤིས -> བཀྲ་ཤིས or བདེལེགས -> བདེ་ལེགས)
        TSHEG = "\u0f0b"
        if TSHEG not in word_norm and len(word_norm) >= 4:
            for idx in range(2, len(word_norm) - 1):
                part1 = word_norm[:idx] + TSHEG
                part2 = word_norm[idx:]
                part2_with_tsheg = part2 + TSHEG if not part2.endswith(TSHEG) else part2

                p1_known = (part1 in self._vocabulary) or (
                    self._corpus_repository is not None and self._corpus_repository.is_known_syllable(part1)
                )
                p2_known = (part2 in self._vocabulary) or (part2_with_tsheg in self._vocabulary) or (
                    self._corpus_repository is not None and (
                        self._corpus_repository.is_known_syllable(part2) or self._corpus_repository.is_known_syllable(part2_with_tsheg)
                    )
                )

                p1_freq = self._corpus_repository.get_syllable_frequency(part1) if self._corpus_repository else (10 if p1_known else 0)
                p2_freq = max(
                    self._corpus_repository.get_syllable_frequency(part2) if self._corpus_repository else (10 if p2_known else 0),
                    self._corpus_repository.get_syllable_frequency(part2_with_tsheg) if self._corpus_repository else (10 if p2_known else 0)
                )

                if p1_freq >= 10 and p2_freq >= 10:
                    cand_split = part1 + part2
                    scored.append((1, cand_split))
                    if not cand_split.endswith(TSHEG) and (part2_with_tsheg in self._vocabulary or (self._corpus_repository and self._corpus_repository.is_known_syllable(part2_with_tsheg, min_frequency=10))):
                        scored.append((1, part1 + part2_with_tsheg))

        # Fast path with initial character match
        for target_len in range(word_len - 2, word_len + 3):
            for vocab_norm, vocab_word in self._vocab_by_length.get(target_len, []):
                if not vocab_norm or vocab_norm[0] != word_initial:
                    continue

                if vocab_norm == word_norm:
                    continue
                    
                dist = _damerau_levenshtein(word_norm, vocab_norm)
                if 0 < dist <= max_dist:
                    scored.append((dist, vocab_word))

        fast_candidates = len(scored)

        # Fallback path if fast path returns 0 candidates
        if not scored:
            for target_len in range(word_len - 2, word_len + 3):
                for vocab_norm, vocab_word in self._vocab_by_length.get(target_len, []):
                    if vocab_norm == word_norm:
                        continue
                        
                    dist = _damerau_levenshtein(word_norm, vocab_norm)
                    if 0 < dist <= max_dist:
                        scored.append((dist, vocab_word))
            
            _logger.info(
                "correction_candidate_fallback",
                word=word,
                vocab_size=len(self._vocabulary),
                fast_candidates=fast_candidates,
                fallback_candidates=len(scored)
            )

        scored.sort()
        return [w for _, w in scored[: self._max_candidates]]


def _damerau_levenshtein(a: str, b: str) -> int:
    """Compute Damerau-Levenshtein distance (supports transpositions of adjacent characters)."""
    if a == b:
        return 0
    len_a = len(a)
    len_b = len(b)
    if not len_a:
        return len_b
    if not len_b:
        return len_a

    d: dict[tuple[int, int], int] = {}
    for i in range(-1, len_a + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, len_b + 1):
        d[(-1, j)] = j + 1

    for i in range(len_a):
        for j in range(len_b):
            cost = 0 if a[i] == b[j] else 1
            d[(i, j)] = min(
                d[(i - 1, j)] + 1,        # deletion
                d[(i, j - 1)] + 1,        # insertion
                d[(i - 1, j - 1)] + cost,  # substitution
            )
            if i > 0 and j > 0 and a[i] == b[j - 1] and a[i - 1] == b[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + cost)  # transposition

    return d[(len_a - 1, len_b - 1)]


def _levenshtein(a: str, b: str) -> int:
    """Backward compatibility alias for Levenshtein distance."""
    return _damerau_levenshtein(a, b)


_TIBETAN_VOWELS = {"\u0f72", "\u0f74", "\u0f7a", "\u0f7c"}


def _canonical_tibetan_syllable(word: str) -> str:
    """Fix misplaced vowel signs (e.g. བ+ད+ོ -> བ+ོ+ད)."""
    chars = list(word)
    if len(chars) >= 3 and chars[-1] in _TIBETAN_VOWELS and chars[-2] not in _TIBETAN_VOWELS:
        chars[-1], chars[-2] = chars[-2], chars[-1]
        return "".join(chars)
    return word


__all__ = ["CorrectionProvider", "ScoringFn"]
