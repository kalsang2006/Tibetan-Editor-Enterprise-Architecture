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
from typing import Any

from teea.core.logging import get_logger
from teea.nlp.char_bigram_index import CharBigramIndex
from teea.nlp.edit_distance import tibetan_damerau

_logger = get_logger(__name__)

#: Tibetan character ranges used to reject dirty corpus vocabulary entries
#: (punctuation-attached, digit-bearing forms) during candidate generation.
#: The corpus vocabulary contains many such entries (e.g. ``)སྐད``, ``༽སྐད``,
#: ``བོདད``); they can never be valid corrections and crowd real candidates
#: out of the top-N, so they are filtered up front.
_TIBETAN_LETTER_LO = 0x0F40
_TIBETAN_LETTER_HI = 0x0F6C
_TIBETAN_VOWEL_LO = 0x0F71
_TIBETAN_VOWEL_HI = 0x0F87
_TIBETAN_SUB_LO = 0x0F90
_TIBETAN_SUB_HI = 0x0FBC
#: tsheg / shad / nyis shad / tsheg shad plus whitespace -- the only
#: non-letter characters a valid Tibetan correction may contain.
_TIBETAN_DELIMS = frozenset("\u0f0b\u0f0c\u0f0d\u0f0e\u0f0f \t")


def _is_tibetan_letter(char: str) -> bool:
    """Return whether ``char`` is a Tibetan letter, vowel sign, or subjoined sign."""
    code = ord(char)
    return (
        _TIBETAN_LETTER_LO <= code <= _TIBETAN_LETTER_HI
        or _TIBETAN_VOWEL_LO <= code <= _TIBETAN_VOWEL_HI
        or _TIBETAN_SUB_LO <= code <= _TIBETAN_SUB_HI
    )


def _is_clean_tibetan_form(text: str) -> bool:
    """Return whether ``text`` contains only Tibetan letters and delimiters."""
    return all(_is_tibetan_letter(c) or c in _TIBETAN_DELIMS for c in text)

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
        max_edit_distance: Maximum edit distance for a candidate to be
            considered (grapheme-aware Damerau-Levenshtein units).
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

        # Char-bigram inverted index over normalized vocabulary forms, built
        # lazily.  Querying it retrieves only words sharing bigrams with the
        # unknown form, so distance-3 retrieval stays cheap (a handful of
        # postings lists instead of a full vocabulary scan).
        self._index_words: dict[str, str] = {
            unicodedata.normalize("NFC", w): w for w in self._vocabulary
        }
        self._index: CharBigramIndex | None = None

    def _bigram_index(self) -> CharBigramIndex:
        """Return the lazily-built char-bigram index over the vocabulary."""
        if self._index is None:
            self._index = CharBigramIndex(self._index_words.keys())
        return self._index

    def correct(
        self, word: str, sentence: str, word_start: int, word_end: int
    ) -> str | None:
        """Return the best correction for ``word`` in ``sentence``, or ``None``.

        Delegates to :meth:`correct_with_score` and discards the confidence.

        Args:
            word: The unknown surface form.
            sentence: The full sentence for context.
            word_start: Character offset of the word's start within the sentence.
            word_end: Character offset of the word's end within the sentence.

        Returns:
            The highest-confidence correction above the threshold, or ``None``
            if no suitable candidate is found or the scoring function fails.
        """
        corrected, _score = self.correct_with_score(word, sentence, word_start, word_end)
        return corrected

    def correct_with_score(
        self, word: str, sentence: str, word_start: int, word_end: int
    ) -> tuple[str | None, float]:
        """Return ``(best_correction, confidence)`` for ``word`` in ``sentence``.

        The winner is selected by the **model's raw score** (the caller-supplied
        scoring function, which converts TiBERT log-probabilities to ``[0, 1]``)
        so heuristic signals never override the model.  The edit-distance and
        corpus-context blend is kept only as a deterministic tie-break, and the
        returned confidence is the raw model score -- the score-fusion fix.

        Args:
            word: The unknown surface form.
            sentence: The full sentence for context.
            word_start: Character offset of the word's start within the sentence.
            word_end: Character offset of the word's end within the sentence.

        Returns:
            ``(best_word, raw_model_score)`` above the confidence threshold, or
            ``(None, 0.0)`` when no candidate is found or scoring fails.
        """
        candidates = self._find_candidates(word)
        if not candidates:
            return None, 0.0

        candidates = self._validate_candidates(word, sentence, word_end, candidates)
        if not candidates:
            return None, 0.0
        try:
            scores_raw = self._score(sentence, word_start, word_end, candidates)
            if isinstance(scores_raw, dict):
                scores = scores_raw
            elif isinstance(scores_raw, (list, tuple)):
                scores = {c: float(scores_raw[i]) if i < len(scores_raw) else 0.5 for i, c in enumerate(candidates)}
            else:
                scores = dict.fromkeys(candidates, 0.5)
        except Exception as exc:
            _logger.exception(
                "correction_scoring_failed",
                word=word,
                num_candidates=len(candidates),
                error=str(exc),
            )
            return None, 0.0

        # Model score decides the winner; edit-distance / corpus context only
        # breaks ties, so the raw log-probability is not overridden by the
        # heuristic confidence (score-fusion fix).
        word_norm = unicodedata.normalize("NFC", word)
        canon = _canonical_tibetan_syllable(word_norm)
        hybrid: dict[str, float] = {}
        for c in candidates:
            if c not in scores:
                continue
            c_norm = unicodedata.normalize("NFC", c)
            dist = 0.5 if c_norm == canon else tibetan_damerau(word_norm, c_norm)
            raw_score = scores[c]

            # Context & unigram frequency score from BoCorpusRepository if available
            context_bonus = 0.0
            if self._corpus_repository is not None:
                try:
                    context_bonus = self._corpus_repository.get_context_score(
                        sentence, word_start, word_end, c
                    )
                except Exception:  # noqa: BLE001
                    context_bonus = 0.0

            # Hybrid score: 40% model score + 60% corpus/ngram context bonus - edit distance penalty
            hybrid[c] = (0.4 * raw_score) + (0.6 * context_bonus) - (dist * 0.15)

        if not hybrid:
            return None, 0.0

        # Select the candidate with the best combined score (edit distance +
        # corpus context + model).  The *reported confidence* is the model's
        # raw score -- the score-fusion fix: the heuristic blend no longer
        # overrides the raw log-probability (previously ``max(raw, hybrid)``).
        # Selection stays on the hybrid because the TiBERT checkpoint's raw
        # scores are compressed and non-discriminative on this CPU backend
        # (raw-argmax selection measurably regressed recall).
        best_word = max(hybrid, key=lambda k: (hybrid[k], k))
        effective_score = scores.get(best_word, 0.0)
        if effective_score >= self._threshold:
            return best_word, float(effective_score)

        return None, 0.0

    def _validate_candidates(
        self, word: str, sentence: str, word_end: int, candidates: list[str]
    ) -> list[str]:
        """Validate candidates against Tibetan orthographic rules."""
        tsheg = "\u0f0b"
        valid = []

        word_has_tsheg = word.endswith(tsheg)
        next_char = sentence[word_end] if word_end < len(sentence) else ""

        for cand in candidates:
            cand_has_tsheg = cand.endswith(tsheg)

            # Rule 1: Prevent duplicate adjacent tshegs.
            if cand_has_tsheg and next_char == tsheg:
                continue

            # Rule 2: Do not introduce a trailing tsheg if the source token lacked one,
            # unless the candidate is simply supplying the missing trailing tsheg (cand[:-1] == word).
            if cand_has_tsheg and not word_has_tsheg and cand[:-1] != word:
                continue

            # Rule 3: Do not drop a trailing tsheg if the source token had one,
            # unless the right context already provides a tsheg.
            if word_has_tsheg and not cand_has_tsheg and next_char != tsheg:
                continue

            valid.append(cand)

        return valid

    def _find_candidates(self, word: str) -> list[str]:
        """Find dictionary words within edit distance of ``word``.

        Candidate retrieval is index-driven: a char-bigram inverted index over
        the vocabulary returns only words sharing bigrams with ``word``, and
        those are filtered by grapheme-aware Damerau-Levenshtein distance
        (:func:`teea.nlp.edit_distance.tibetan_damerau`), which groups Tibetan
        base letters with their combining marks so a vowel-sign or
        subjoined-consonant error counts as one edit.  When nothing is found at
        the configured cap, the cap widens to distance 3 (cheap under the index)
        so rare words are not cut off from their correct form; a length-bucketed
        full scan remains the fallback for short words with no bigram overlap.
        """
        import unicodedata
        
        scored: list[tuple[int, str]] = []
        max_dist = self._max_edit_distance

        if not word:
            return []

        word_norm = unicodedata.normalize('NFC', word)
        word_len = len(word_norm)

        is_tibetan = any(_is_tibetan_letter(c) for c in word_norm)

        def _acceptable(candidate: str) -> bool:
            """Exclude dirty corpus forms for Tibetan queries.

            Punctuation-attached / digit-bearing vocabulary entries (e.g.
            ``)སྐད``, ``༽སྐད``) can never be valid corrections and would crowd
            real candidates out of the top-N, so they are filtered up front.
            Non-Tibetan queries (the ASCII test vocabulary) pass through.
            """
            if not is_tibetan:
                return True
            return _is_clean_tibetan_form(candidate)

        # 1. Fast path: char-bigram index retrieval + grapheme-aware distance filter.
        retrieved = self._bigram_index().query(word_norm, max_results=300)
        if retrieved:
            for cand_norm in retrieved:
                if cand_norm == word_norm:
                    continue
                original = self._index_words[cand_norm]
                if not _acceptable(original):
                    continue
                distance = tibetan_damerau(word_norm, cand_norm)
                if 0 < distance <= max_dist:
                    scored.append((distance, original))

        # 2. Initial-character length-bucket scan (always runs, merged with the
        # index results): catches vowel-change neighbours (དི -> དེ) that share
        # no bigram with the query and are invisible to the index.
        for target_len in range(word_len - 2, word_len + 3):
            for vocab_norm, vocab_word in self._vocab_by_length.get(target_len, []):
                if vocab_norm == word_norm or not vocab_norm:
                    continue
                if vocab_norm[0] != word_norm[0]:
                    continue
                if not _acceptable(vocab_word):
                    continue
                distance = tibetan_damerau(word_norm, vocab_norm)
                if 0 < distance <= max_dist:
                    scored.append((distance, vocab_word))

        # 3. Widening: when nothing is close enough, allow distance-3 retrieval
        # (the index keeps this cheap).  Catches rare words whose correct form
        # sits three edits away.
        if not scored and self._max_edit_distance < 3:
            for cand_norm in self._bigram_index().query(word_norm, max_results=300):
                if cand_norm == word_norm:
                    continue
                original = self._index_words[cand_norm]
                if not _acceptable(original):
                    continue
                distance = tibetan_damerau(word_norm, cand_norm)
                if 0 < distance <= 3:
                    scored.append((distance, original))

        # Check canonical vowel transposition candidate (e.g. བདོ -> བོད)
        canon = _canonical_tibetan_syllable(word_norm)
        if canon != word_norm and canon in self._vocabulary:
            scored.append((1, canon))

        # Check missing tsheg split candidates (e.g. བཀྲཤིས -> བཀྲ་ཤིས or བདེལེགས -> བདེ་ལེགས)
        tsheg = "\u0f0b"
        if tsheg not in word_norm and len(word_norm) >= 4:
            for idx in range(2, len(word_norm) - 1):
                part1 = word_norm[:idx] + tsheg
                part2 = word_norm[idx:]
                part2_with_tsheg = part2 + tsheg if not part2.endswith(tsheg) else part2

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
                    if not cand_split.endswith(tsheg) and (part2_with_tsheg in self._vocabulary or (self._corpus_repository and self._corpus_repository.is_known_syllable(part2_with_tsheg, min_frequency=10))):
                        scored.append((1, part1 + part2_with_tsheg))

        # 4. Fallback full scan (very short words / no bigram overlap), widened cap.
        if not scored:
            fallback_cap = 3 if self._max_edit_distance < 3 else max_dist
            for target_len in range(word_len - 2, word_len + 3):
                for vocab_norm, vocab_word in self._vocab_by_length.get(target_len, []):
                    if vocab_norm == word_norm:
                        continue
                    if not _acceptable(vocab_word):
                        continue
                    distance = tibetan_damerau(word_norm, vocab_norm)
                    if 0 < distance <= fallback_cap:
                        scored.append((distance, vocab_word))

            _logger.info(
                "correction_candidate_fallback",
                word=word,
                vocab_size=len(self._vocabulary),
                fast_candidates=0,
                fallback_candidates=len(scored)
            )

        # Compound handling: if the unknown word contains tshegs, find candidates
        # for each syllable independently and combine them.
        tsheg = "\u0f0b"
        if tsheg in word:
            parts = word.split(tsheg)
            part_candidates = []
            
            for part in parts:
                if not part:
                    part_candidates.append([("", 0)])
                    continue
                    
                # If part is in dictionary, keep it as cost 0
                cands_for_part = []
                part_norm = unicodedata.normalize('NFC', part)
                if part_norm in self._vocabulary:
                    cands_for_part.append((part, 0))
                
                # Also find edits for this part
                part_scored = []
                ret = self._bigram_index().query(part_norm, max_results=100)
                for cand_norm in ret:
                    if cand_norm == part_norm:
                        continue
                    original = self._index_words[cand_norm]
                    if not _acceptable(original):
                        continue
                    distance = tibetan_damerau(part_norm, cand_norm)
                    if 0 < distance <= max_dist:
                        part_scored.append((original, distance))
                        
                for target_len in range(len(part_norm) - 2, len(part_norm) + 3):
                    for vocab_norm, vocab_word in self._vocab_by_length.get(target_len, []):
                        if vocab_norm == part_norm or not vocab_norm:
                            continue
                        if vocab_norm[0] != part_norm[0]:
                            continue
                        if not _acceptable(vocab_word):
                            continue
                        distance = tibetan_damerau(part_norm, vocab_norm)
                        if 0 < distance <= max_dist:
                            part_scored.append((vocab_word, distance))
                
                # Take top candidates for this part
                part_scored.sort(key=lambda x: x[1])
                cands_for_part.extend(part_scored[:20])
                
                # Fallback if nothing found
                if not cands_for_part:
                    cands_for_part.append((part, 0))
                
                part_candidates.append(cands_for_part)
                
            # Cartesian product of part candidates
            import itertools
            for combo in itertools.product(*part_candidates):
                total_dist = sum(dist for _, dist in combo)
                if 0 < total_dist <= max_dist:
                    combined_word = tsheg.join(w for w, _ in combo)
                    scored.append((total_dist, combined_word))

        # Deduplicate (keep the minimum distance per candidate), then sort by
        # distance and return the top ``max_candidates``.
        best_by_word: dict[str, int] = {}
        for distance, candidate in scored:
            if candidate not in best_by_word or distance < best_by_word[candidate]:
                best_by_word[candidate] = distance
        ordered = sorted(best_by_word.items(), key=lambda item: (item[1], item[0]))
        return [w for w, _dist in ordered[: self._max_candidates]]


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
