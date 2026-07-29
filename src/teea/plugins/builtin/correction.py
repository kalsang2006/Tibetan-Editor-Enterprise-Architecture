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
        vocabulary: frozenset[str],
        *,
        max_edit_distance: int = 2,
        max_candidates: int = 10,
        confidence_threshold: float = 0.5,
    ) -> None:
        self._score = score_candidates
        self._vocabulary = vocabulary
        self._confidence_threshold = confidence_threshold
        self._max_edit_distance = max_edit_distance
        self._max_candidates = max_candidates
        
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
            scores = self._score(sentence, word_start, word_end, candidates)
        except Exception as exc:  # noqa: BLE001 — correction must never crash the plugin
            _logger.exception(
                "correction_scoring_failed",
                word=word,
                num_candidates=len(candidates),
                error=str(exc),
            )
            return None

        # Incorporate edit distance to balance language model and error model
        word_norm = unicodedata.normalize("NFC", word)
        final_scores = {}
        for c in candidates:
            if c in scores:
                dist = _levenshtein(word_norm, unicodedata.normalize("NFC", c))
                # Penalize each edit distance step heavily to prevent wildly different words from winning
                final_scores[c] = scores[c] - (dist * 0.2)

        if not final_scores:
            return None

        # Select candidate with the highest combined confidence
        best_word = max(final_scores, key=lambda k: final_scores[k])
        best_score = scores[best_word]  # Keep original TiBERT score for the threshold check
        if best_score >= self._threshold:
            _logger.debug(
                "correction_found",
                word=word,
                correction=best_word,
                score=best_score,
            )
            return best_word

        _logger.debug(
            "correction_below_threshold",
            word=word,
            best=best_word,
            score=best_score,
            threshold=self._threshold,
        )
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

            # Rule 2: Do not introduce a trailing tsheg if the source token lacked one.
            if cand_has_tsheg and not word_has_tsheg:
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

        # Fast path
        for target_len in range(word_len - 2, word_len + 3):
            for vocab_norm, vocab_word in self._vocab_by_length.get(target_len, []):
                # HACKATHON OPTIMIZATION: Require same initial character to drastically
                # reduce the search space from O(N) to a small fraction.
                if not vocab_norm or vocab_norm[0] != word_initial:
                    continue

                # Skip exact matches
                if vocab_norm == word_norm:
                    continue
                    
                dist = _levenshtein(word_norm, vocab_norm)
                if 0 < dist <= max_dist:
                    scored.append((dist, vocab_word))

        fast_candidates = len(scored)

        # Fallback path if fast path returns 0 candidates
        if not scored:
            for target_len in range(word_len - 2, word_len + 3):
                for vocab_norm, vocab_word in self._vocab_by_length.get(target_len, []):
                    # Relaxed: No initial character check
                    if vocab_norm == word_norm:
                        continue
                        
                    dist = _levenshtein(word_norm, vocab_norm)
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


def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings.

    Uses the standard dynamic-programming algorithm with O(min(m, n)) space.
    """
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for char_a in a:
        current = [previous[0] + 1]
        for j, char_b in enumerate(b):
            current.append(
                min(
                    current[j] + 1,
                    previous[j + 1] + 1,
                    previous[j] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


__all__ = ["CorrectionProvider", "ScoringFn"]
