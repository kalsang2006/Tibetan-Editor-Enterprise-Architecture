"""Tests for the upgraded :class:`DictionaryOnlyCorrectionProvider`.

Verifies the §1 candidate-generation upgrades:

* grapheme-aware Damerau-Levenshtein scoring (subjoined/vowel errors = 1 edit)
* char-bigram index retrieval (no full-vocab scan)
* dynamic distance caps for rare words
* canonical vowel-transposition and missing-tsheg-split candidates
"""

from __future__ import annotations

from teea.plugins.builtin.correction_providers import (
    CorrectionCandidate,
    DictionaryOnlyCorrectionProvider,
)


class FakeDictionary:
    """Minimal dictionary exposing a ``vocabulary`` surface for the provider."""

    def __init__(self, words: set[str]) -> None:
        self.vocabulary = words


class TestVocabularyResolution:
    def test_vocabulary_is_tsheg_stripped(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"བཀྲ་", "ཤིས་", "བདེ།"})
        )
        assert provider._vocab_set == {"བཀྲ", "ཤིས", "བདེ"}

    def test_blank_entries_are_skipped(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"", "   ", "བཀྲ་"})
        )
        assert len(provider._vocab) == 1


class TestGraphemeAwareDistance:
    def test_subjoined_consonant_change_is_one_edit(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(FakeDictionary({"བགྲ་"}))
        candidates = provider.generate_candidates("བཀྲ་", "བཀྲ་ བདེ་ལེགས།")
        words = [c.word for c in candidates]
        assert "བགྲ་" in words

    def test_vowel_sign_change_is_one_edit(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(FakeDictionary({"ཀུ་"}))
        candidates = provider.generate_candidates("ཀི་", "ཀི་ བདེ་ལེགས།")
        words = [c.word for c in candidates]
        assert "ཀུ་" in words

    def test_distant_word_is_excluded(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(FakeDictionary({"བཀྲ་ཤིས་བདེ་"}))
        candidates = provider.generate_candidates("ཀི་", "ཀི་ བདེ་ལེགས།")
        assert all(c.word != "བཀྲ་ཤིས་བདེ་" for c in candidates)


class TestCanonicalAndTshegSplit:
    def test_canonical_vowel_transposition_candidate(self) -> None:
        # བདོ -> བོད (vowel sign moved across ད).
        provider = DictionaryOnlyCorrectionProvider(FakeDictionary({"བོད་"}))
        candidates = provider.generate_candidates("བདོ་", "བདོ་ བཀྲ་ཤིས།")
        words = [c.word for c in candidates]
        assert "བོད་" in words

    def test_missing_tsheg_split_candidate(self) -> None:
        # བཀྲཤིས -> བཀྲ་ཤིས (two attested halves glued together).
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"བཀྲ་", "ཤིས་"})
        )
        candidates = provider.generate_candidates("བཀྲཤིས", "བཀྲཤིས བདེ་ལེགས།")
        words = [c.word for c in candidates]
        assert "བཀྲ་ཤིས" in words

    def test_split_requires_attested_halves(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"བཀྲ་", "བདེ་ལེགས་"})
        )
        candidates = provider.generate_candidates("བཀྲཤིས", "བཀྲཤིས བདེ་ལེགས།")
        assert all(c.word != "བཀྲ་ཤིས" for c in candidates)


class TestDynamicThresholds:
    def test_rare_word_gets_distance_three(self) -> None:
        # བཀྲི (graphemes [བ, ཀྲི]) -> གཞེར (graphemes [ག, ཞེ, ར]) is three
        # grapheme edits: substitute བ->ག, substitute ཀྲི->ཞེ, insert ར.
        # A rare query word (freq 2 <= 10) is allowed this net.
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"བཀྲི", "གཞེར"}),
            max_edit_distance=2,
            rare_max_distance=3,
            frequencies={"བཀྲི": 2, "གཞེར": 2000},
        )
        candidates = provider.generate_candidates("བཀྲི", "བཀྲི བདེ་ལེགས།")
        assert any(c.word == "གཞེར" for c in candidates)

    def test_common_word_is_capped_at_configured_distance(self) -> None:
        # Same pair, but the query word is common (freq 500 > 10): the cap
        # stays at max_edit_distance=2, so the distance-3 neighbour is out.
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"བཀྲི", "གཞེར"}),
            max_edit_distance=2,
            frequencies={"བཀྲི": 500, "གཞེར": 2000},
        )
        candidates = provider.generate_candidates("བཀྲི", "བཀྲི བདེ་ལེགས།")
        assert all(c.word != "གཞེར" for c in candidates)

    def test_max_distance_is_never_lowered_below_configured(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"བཀྲི"}),
            rare_max_distance=1,
            max_edit_distance=2,
            frequencies={"བཀྲི": 2},
        )
        assert provider._max_distance_for("བཀྲི") == 2


class TestRankingAndDedup:
    def test_closer_candidate_ranks_first(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"ཀི་", "ཀུ་", "ཀེ་"})
        )
        candidates = provider.generate_candidates("ཀི་", "ཀི་ བདེ་ལེགས།")
        assert isinstance(candidates[0], CorrectionCandidate)
        # The query word itself is never returned (distance 0 is filtered).
        assert all(c.word != "ཀི་" for c in candidates)
        # Both neighbours are single-grapheme vowel substitutions (distance 1).
        assert {c.word for c in candidates[:2]} == {"ཀུ་", "ཀེ་"}
        assert candidates[0].confidence >= 0.7

    def test_max_candidates_is_respected(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(
            FakeDictionary({"ཀི་", "ཀུ་", "ཀེ་", "ཀོ་", "ཀྲི་"})
        )
        candidates = provider.generate_candidates(
            "ཀི་", "ཀི་ བདེ་ལེགས།", max_candidates=3
        )
        assert len(candidates) <= 3

    def test_empty_word_returns_no_candidates(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(FakeDictionary({"བཀྲ་"}))
        assert provider.generate_candidates("", "བཀྲ་ ཤིས།") == []

    def test_confidence_in_0_1_range(self) -> None:
        provider = DictionaryOnlyCorrectionProvider(FakeDictionary({"ཀི་", "ཀུ་"}))
        candidates = provider.generate_candidates("ཀི་", "ཀི་ བདེ་ལེགས།")
        assert all(0.0 < c.confidence <= 1.0 for c in candidates)
