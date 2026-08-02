"""Lightweight n-gram context scorer for candidate ranking and detection.

Ranking a spelling correction only by edit distance ignores the sentence it
lands in.  This module scores how plausible a candidate word is *in context*
using add-k-smoothed unigram/bigram/trigram statistics from the BoCorpus
repository, and exposes a detection hook that flags a dictionary-known word
that appears in an implausible context (the "known-word error" case that
pure dictionary lookup cannot see).

Corpus access is deliberately duck-typed (the ``corpus`` argument is typed as
``Any``) for the same reason ``correction.py`` accepts a ``corpus_repository``
as ``Any``: ``teea.corpus`` already imports ``teea.nlp`` (in ``builder.py``
and ``synthetic.py``), so importing it here at module level would create an
import cycle.  The required surface is documented on :class:`ContextualRanker`.
"""

from __future__ import annotations

import math
import unicodedata
from typing import Any

TSHEG = "\u0f0b"
SHAD = "\u0f0d"
#: tsheg/shad/whitespace — used only as literal delimiters here; the shared
#: character classes live in ``teea.core.types`` (ADR-004 consequence 4).
_DELIMS = (TSHEG, SHAD, "\u0f60", "\u0f61", " ", "\t", "\n")

#: Default smoothing for add-k estimation.
_DEFAULT_ALPHA = 0.1
#: Default suspiciousness gap (in log space): a known word whose contextual
#: log-probability is this much lower than its unigram baseline is flagged.
_DEFAULT_SUSPICIOUS_GAP = 2.5


def _syllables(text: str) -> list[str]:
    """Split ``text`` into non-empty syllable tokens.

    The corpus stores syllables keyed without a trailing tsheg, so the tokens
    are stripped of delimiters to match those keys.

    Args:
        text: Any substring of a sentence.

    Returns:
        The tsheg/shad/whitespace-delimited tokens, in order.
    """
    tokens: list[str] = []
    buffer: list[str] = []
    for char in unicodedata.normalize("NFC", text):
        if char in _DELIMS:
            if buffer:
                tokens.append("".join(buffer))
                buffer = []
        else:
            buffer.append(char)
    if buffer:
        tokens.append("".join(buffer))
    return [t.strip() for t in tokens if t.strip()]


class ContextualRanker:
    """Ranks candidates and flags known words using corpus n-gram statistics.

    The ``corpus`` argument must expose the following surface (the same
    surface :class:`~teea.corpus.repository.BoCorpusRepository` provides):

    * ``vocabulary`` -- ``Mapping[str, int]`` of syllable -> frequency.
    * ``bigrams`` -- ``Mapping[str, int]`` of ``"s1 s2"`` -> frequency.
    * ``trigrams`` -- ``Mapping[str, int]`` of ``"s1 s2 s3"`` -> frequency.

    Everything else is read through those three maps; keys are normalised by
    trying the raw pair, the tsheg-stripped pair, and the tsheg-terminated
    pair, mirroring the repository's own lookup variants.

    Args:
        corpus: The corpus repository (duck-typed, see above).
        alpha: Add-k smoothing constant.
        suspicious_gap: Minimum unigram-vs-context log-probability gap for
            :meth:`is_suspicious` to flag a word.
    """

    def __init__(
        self,
        corpus: Any,
        *,
        alpha: float = _DEFAULT_ALPHA,
        suspicious_gap: float = _DEFAULT_SUSPICIOUS_GAP,
    ) -> None:
        self._corpus = corpus
        self._alpha = alpha
        self._suspicious_gap = suspicious_gap
        self._vocab: dict[str, int] = {}
        self._bigrams: dict[str, int] = {}
        self._trigrams: dict[str, int] = {}
        self._total: int = 0
        self._vocab_size: int = 0
        self._load_maps()

    # -- Loading -------------------------------------------------------------

    def _load_maps(self) -> None:
        """Snapshot the corpus maps once at construction.

        Keeps lookups O(1) and avoids re-reading large JSON artifacts on every
        candidate.  Any missing map degrades gracefully to an empty one.
        """
        self._vocab = dict(getattr(self._corpus, "vocabulary", {}) or {})
        self._bigrams = dict(getattr(self._corpus, "bigrams", {}) or {})
        self._trigrams = dict(getattr(self._corpus, "trigrams", {}) or {})
        self._total = sum(self._vocab.values()) or 1
        self._vocab_size = len(self._vocab) or 1

    # -- Probability estimators (add-k smoothed) -----------------------------

    def _count(self, table: dict[str, int], *keys: str) -> int:
        """Return the first matching count across key variants, else 0.

        Args:
            table: The frequency map to look in.
            *keys: Candidate key strings; the first found wins.

        Returns:
            The stored frequency, or ``0``.
        """
        for key in keys:
            value = table.get(key)
            if value is not None:
                return int(value)
        return 0

    def unigram_log_prob(self, syllable: str) -> float:
        """Return add-k-smoothed log P(syllable).

        The corpus stores syllable keys tsheg-terminated (``བཀྲ་``), while
        callers pass tsheg-stripped forms, so the lookup tries the bare form,
        the tsheg-terminated form and the stripped form, mirroring the
        repository's own key variants.

        Args:
            syllable: A corpus syllable.

        Returns:
            ``log((count + alpha) / (total + alpha * V))``.
        """
        if not syllable:
            return float("-inf")
        clean = syllable.rstrip(TSHEG + SHAD + " ")
        count = self._count(self._vocab, syllable, clean + TSHEG, clean)
        denom = self._total + self._alpha * self._vocab_size
        return math.log((count + self._alpha) / denom)

    def bigram_log_prob(self, prev: str, curr: str) -> float:
        """Return add-k-smoothed log P(curr | prev).

        Args:
            prev: The preceding syllable.
            curr: The following syllable.

        Returns:
            ``log((count(prev curr) + alpha) / (count(prev) + alpha * V))``.
        """
        if not prev or not curr:
            return float("-inf")
        prev_clean = prev.rstrip(TSHEG + SHAD + " ")
        curr_clean = curr.rstrip(TSHEG + SHAD + " ")
        count = self._count(
            self._bigrams,
            f"{prev} {curr}",
            f"{prev_clean} {curr_clean}",
            f"{prev_clean}{TSHEG} {curr_clean}{TSHEG}",
            f"{prev_clean} {curr_clean}{TSHEG}",
        )
        prev_count = self._count(self._vocab, prev, prev_clean, f"{prev_clean}{TSHEG}")
        denom = prev_count + self._alpha * self._vocab_size
        return math.log((count + self._alpha) / denom) if denom > 0 else float("-inf")

    def trigram_log_prob(self, s1: str, s2: str, s3: str) -> float:
        """Return add-k-smoothed log P(s3 | s1, s2).

        Args:
            s1: First context syllable.
            s2: Second context syllable.
            s3: The syllable being conditioned on.

        Returns:
            ``log((count(s1 s2 s3) + alpha) / (count(s1 s2) + alpha * V))``.
        """
        if not s1 or not s2 or not s3:
            return float("-inf")
        c1, c2, c3 = (
            s.rstrip(TSHEG + SHAD + " ") for s in (s1, s2, s3)
        )
        count = self._count(
            self._trigrams,
            f"{s1} {s2} {s3}",
            f"{c1} {c2} {c3}",
            f"{c1}{TSHEG} {c2}{TSHEG} {c3}{TSHEG}",
        )
        bg_count = self._count(
            self._bigrams,
            f"{s1} {s2}",
            f"{c1} {c2}",
            f"{c1}{TSHEG} {c2}{TSHEG}",
        )
        denom = bg_count + self._alpha * self._vocab_size
        return math.log((count + self._alpha) / denom) if denom > 0 else float("-inf")

    # -- Context scoring -----------------------------------------------------

    def pll(self, sentence: str, word_start: int, word_end: int, candidate: str) -> float:
        """Return the mean contextual log-probability of ``candidate``.

        Combines, when present: the left bigram ``P(cand_first | left_last)``,
        the right bigram ``P(right_first | cand_last)``, and the left trigram
        ``P(cand_first | left_2, left_1)``.  Unigram terms are deliberately
        excluded so the score measures *context* rather than frequency; the
        caller compares it against :meth:`unigram_log_prob` for detection.

        Args:
            sentence: The sentence containing the candidate.
            word_start: Character offset of the candidate's start.
            word_end: Character offset of the candidate's end.
            candidate: The surface form being scored.

        Returns:
            Mean log-probability of the available context terms, or ``0.0``
            when no context term applies.
        """
        cand_syls = _syllables(candidate)
        left_syls = _syllables(sentence[:word_start])
        right_syls = _syllables(sentence[word_end:])
        if not cand_syls:
            return 0.0

        terms: list[float] = []
        if left_syls:
            terms.append(self.bigram_log_prob(left_syls[-1], cand_syls[0]))
        if right_syls:
            terms.append(self.bigram_log_prob(cand_syls[-1], right_syls[0]))
        if len(left_syls) >= 2:
            terms.append(self.trigram_log_prob(left_syls[-2], left_syls[-1], cand_syls[0]))
        if not terms:
            return 0.0
        return sum(terms) / len(terms)

    def is_suspicious(self, sentence: str, word_start: int, word_end: int) -> bool:
        """Return whether the word at ``[word_start, word_end)`` is implausible in context.

        The word's contextual log-probability is compared against its unigram
        baseline: when the context makes it at least ``suspicious_gap``
        (in log space) less likely than its standalone frequency predicts, the
        word is flagged.  A word with no usable context (sentence-initial and
        final, or no bigram/trigram evidence) is never flagged.

        Args:
            sentence: The sentence containing the word.
            word_start: Character offset of the word's start.
            word_end: Character offset of the word's end.

        Returns:
            ``True`` when the word is far less plausible in context than alone.
        """
        word = sentence[word_start:word_end].strip()
        cand_syls = _syllables(word)
        if not cand_syls:
            return False
        baseline = self.unigram_log_prob(cand_syls[0])
        context = self.pll(sentence, word_start, word_end, word)
        if context == 0.0 or math.isinf(baseline):
            return False
        return (baseline - context) > self._suspicious_gap


__all__ = ["ContextualRanker"]
