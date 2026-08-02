"""Tests for the CorrectionProvider.

Covers candidate generation (edit distance), scoring integration, threshold
behaviour, and edge cases.  All tests use a mock scoring function — no real
model is required.
"""

from __future__ import annotations

from teea.plugins.builtin.correction import CorrectionProvider, _levenshtein

# -- Levenshtein distance tests ------------------------------------------------


class TestLevenshtein:
    def test_identical_strings(self) -> None:
        assert _levenshtein("abc", "abc") == 0

    def test_empty_strings(self) -> None:
        assert _levenshtein("", "") == 0

    def test_one_empty(self) -> None:
        assert _levenshtein("abc", "") == 3
        assert _levenshtein("", "abc") == 3

    def test_single_substitution(self) -> None:
        assert _levenshtein("abc", "axc") == 1

    def test_single_insertion(self) -> None:
        assert _levenshtein("ac", "abc") == 1

    def test_single_deletion(self) -> None:
        assert _levenshtein("abc", "ac") == 1

    def test_tibetan_syllables(self) -> None:
        # བཀྲ vs བཀ — one character difference.
        assert _levenshtein("བཀྲ", "བཀ") == 1

    def test_larger_distance(self) -> None:
        assert _levenshtein("kitten", "sitting") == 3


# -- Mock scoring function ----------------------------------------------------


def always_high_scorer(
    sentence: str, word_start: int, word_end: int, candidates: list[str]
) -> dict[str, float]:
    """Return 0.9 for every candidate."""
    return dict.fromkeys(candidates, 0.9)


def always_low_scorer(
    sentence: str, word_start: int, word_end: int, candidates: list[str]
) -> dict[str, float]:
    """Return 0.1 for every candidate — below the default threshold."""
    return dict.fromkeys(candidates, 0.1)


def ranked_scorer(
    sentence: str, word_start: int, word_end: int, candidates: list[str]
) -> dict[str, float]:
    """Return descending scores so the first candidate wins."""
    return {c: 0.9 - i * 0.1 for i, c in enumerate(candidates)}


def exploding_scorer(
    sentence: str, word_start: int, word_end: int, candidates: list[str]
) -> dict[str, float]:
    """Raise an exception — the provider must handle it gracefully."""
    raise RuntimeError("scorer exploded")


# -- Candidate generation tests -----------------------------------------------


VOCABULARY = frozenset({"abc", "axc", "abcd", "xyz", "ab", "abcde", "zzz"})


class TestCandidateGeneration:
    def test_finds_close_words(self) -> None:
        provider = CorrectionProvider(always_high_scorer, VOCABULARY)
        # "abc" is not checked (would be edit-distance 0, but it IS in vocabulary).
        # We're looking for candidates for "aac" which is unknown.
        candidates = provider._find_candidates("aac")
        assert "abc" in candidates  # distance 1
        assert "axc" in candidates  # distance 2

    def test_respects_max_edit_distance(self) -> None:
        provider = CorrectionProvider(
            always_high_scorer, VOCABULARY, max_edit_distance=1
        )
        candidates = provider._find_candidates("aac")
        assert "abc" in candidates  # distance 1
        assert "abcde" not in candidates  # distance 3

    def test_respects_max_candidates(self) -> None:
        big_vocab = frozenset(f"a{i}" for i in range(100))
        provider = CorrectionProvider(
            always_high_scorer, big_vocab, max_candidates=5
        )
        candidates = provider._find_candidates("a0")
        assert len(candidates) <= 5

    def test_no_candidates_when_vocabulary_empty(self) -> None:
        provider = CorrectionProvider(always_high_scorer, frozenset())
        assert provider._find_candidates("anything") == []

    def test_skips_exact_match(self) -> None:
        provider = CorrectionProvider(always_high_scorer, frozenset({"same"}))
        assert provider._find_candidates("same") == []


# -- Candidate validation tests (Tsheg boundaries) -----------------------------


class TestCandidateValidation:
    def test_prevents_duplicate_tsheg(self) -> None:
        provider = CorrectionProvider(always_high_scorer, frozenset())
        word = "ཤིམ"  # no tsheg
        sentence = "ང་བཀྲ་ཤིམ་ཟེར།"
        word_end = sentence.find(word) + len(word)
        # next_char is "་" (tsheg)
        
        candidates = ["ཤིས", "ཤི་", "ཤིས་"]
        # "ཤིས" (no tsheg) should pass
        # "ཤི་" (has tsheg) should be rejected (Rule 1 & 2)
        # "ཤིས་" (has tsheg) should be rejected (Rule 1 & 2)
        valid = provider._validate_candidates(word, sentence, word_end, candidates)
        assert valid == ["ཤིས"]

    def test_prevents_missing_tsheg_introduction(self) -> None:
        provider = CorrectionProvider(always_high_scorer, frozenset())
        word = "ཤིམ"  # no tsheg
        sentence = "ཤིམ"
        word_end = 3
        # next_char is ""
        
        candidates = ["ཤིས", "ཤི་"]
        # "ཤི་" has tsheg, but word doesn't. Rule 2 should reject it.
        valid = provider._validate_candidates(word, sentence, word_end, candidates)
        assert valid == ["ཤིས"]

    def test_prevents_tsheg_drop(self) -> None:
        provider = CorrectionProvider(always_high_scorer, frozenset())
        word = "བཀྲ་"  # has tsheg
        sentence = "བཀྲ་ཤིས"
        word_end = 4
        # next_char is "ཤ" (not tsheg)
        
        candidates = ["བཀྲ", "བཀྲ་"]
        # "བཀྲ" (no tsheg) drops the tsheg, Rule 3 should reject it.
        valid = provider._validate_candidates(word, sentence, word_end, candidates)
        assert valid == ["བཀྲ་"]

    def test_allows_tsheg_drop_if_next_char_is_tsheg(self) -> None:
        provider = CorrectionProvider(always_high_scorer, frozenset())
        word = "བཀྲ་"  # has tsheg
        sentence = "བཀྲ་་" # Double tsheg situation in doc
        word_end = 4
        # next_char is "་" (tsheg)
        
        candidates = ["བཀྲ", "བཀྲ་"]
        # "བཀྲ" (no tsheg) drops the tsheg, but next_char is tsheg. So it's allowed!
        # "བཀྲ་" (has tsheg) would create double tsheg! Rule 1 rejects it.
        valid = provider._validate_candidates(word, sentence, word_end, candidates)
        assert valid == ["བཀྲ"]


# -- Correction tests ----------------------------------------------------------


class TestCorrection:
    def test_returns_correction_above_threshold(self) -> None:
        provider = CorrectionProvider(
            always_high_scorer, VOCABULARY, confidence_threshold=0.5
        )
        result = provider.correct("aac", "text aac here", 5, 8)
        assert result is not None
        assert result in VOCABULARY

    def test_returns_none_below_threshold(self) -> None:
        provider = CorrectionProvider(
            always_low_scorer, VOCABULARY, confidence_threshold=0.5
        )
        result = provider.correct("aac", "text aac here", 5, 8)
        assert result is None

    def test_returns_none_when_no_candidates(self) -> None:
        provider = CorrectionProvider(
            always_high_scorer, frozenset(), confidence_threshold=0.5
        )
        result = provider.correct("zzzzzzz", "text zzzzzzz here", 5, 12)
        assert result is None

    def test_picks_highest_scored_candidate(self) -> None:
        vocab = frozenset({"ab", "ac", "ad"})
        provider = CorrectionProvider(ranked_scorer, vocab, confidence_threshold=0.0)
        result = provider.correct("aa", "text aa here", 5, 7)
        # ranked_scorer gives descending scores; first candidate alphabetically wins.
        assert result is not None
        # Whatever the first candidate is, it should be the one with the highest score.
        candidates = provider._find_candidates("aa")
        expected = candidates[0]  # first in sorted order → highest score from ranked_scorer
        assert result == expected

    def test_scorer_failure_returns_none(self) -> None:
        provider = CorrectionProvider(
            exploding_scorer, VOCABULARY, confidence_threshold=0.5
        )
        result = provider.correct("aac", "text aac here", 5, 8)
        assert result is None

    def test_returns_none_when_scorer_returns_empty(self) -> None:
        def empty_scorer(s: str, ws: int, we: int, c: list[str]) -> dict[str, float]:
            return {}

        provider = CorrectionProvider(empty_scorer, VOCABULARY)
        result = provider.correct("aac", "text aac here", 5, 8)
        assert result is None


# -- Tibetan-specific tests ---------------------------------------------------


class TestTibetanCorrection:
    """Verify the provider works with Tibetan Unicode strings."""

    TIBETAN_VOCAB = frozenset({"བཀྲ་ཤིས་", "བཀྲ་ཤིན་", "བཀྲ་ཤིག་"})

    def test_tibetan_candidates_found(self) -> None:
        provider = CorrectionProvider(always_high_scorer, self.TIBETAN_VOCAB)
        # "བཀྲ་ཤིམ་" is not in vocab but is edit distance 1 from "བཀྲ་ཤིས་" and "བཀྲ་ཤིན་"
        candidates = provider._find_candidates("བཀྲ་ཤིམ་")
        assert len(candidates) > 0

    def test_tibetan_correction_returned(self) -> None:
        provider = CorrectionProvider(
            always_high_scorer, self.TIBETAN_VOCAB, confidence_threshold=0.5
        )
        word = "བཀྲ་ཤིམ་"
        sentence = f"ང་ {word} ཟེར།"
        start = sentence.index(word)
        end = start + len(word)
        result = provider.correct(word, sentence, start, end)
        assert result is not None
        assert result in self.TIBETAN_VOCAB
