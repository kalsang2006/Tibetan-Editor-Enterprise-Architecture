"""Unit tests for :mod:`teea.nlp.contextual_ranker`.

Uses a minimal duck-typed corpus fake exposing ``vocabulary``, ``bigrams``
and ``trigrams`` (the same surface :class:`BoCorpusRepository` provides).
"""

from __future__ import annotations

import math
from typing import ClassVar

from teea.nlp.contextual_ranker import ContextualRanker

TSHEG = "\u0f0b"


class FakeCorpus:
    """Minimal corpus with a handful of attested syllables and n-grams."""

    vocabulary: ClassVar[dict[str, int]] = {
        "བཀྲ": 1000,
        "ཤིས": 900,
        "བདེ": 800,
        "ལེགས": 750,
        "ཁྱོད": 500,
        "རང": 450,
    }
    bigrams: ClassVar[dict[str, int]] = {
        "བཀྲ ཤིས": 850,
        "བདེ ལེགས": 700,
        "ཁྱོད རང": 400,
    }
    trigrams: ClassVar[dict[str, int]] = {
        "བཀྲ ཤིས བདེ": 600,
        "ཤིས བདེ ལེགས": 550,
    }


class TestUnigramLogProb:
    def test_known_syllable_has_finite_negative_log_prob(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        lp = ranker.unigram_log_prob("བཀྲ")
        assert math.isfinite(lp)
        assert lp < 0.0

    def test_unknown_syllable_is_more_unlikely(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        known = ranker.unigram_log_prob("བཀྲ")
        unknown = ranker.unigram_log_prob("བྱིས")
        assert unknown < known

    def test_tsheg_terminated_key_is_found(self) -> None:
        # Corpus keys are stored tsheg-terminated in the real repository; the
        # ranker must resolve the bare form against them.
        ranker = ContextualRanker(FakeCorpus())
        assert math.isclose(
            ranker.unigram_log_prob("བཀྲ"),
            ranker.unigram_log_prob(f"བཀྲ{TSHEG}"),
            rel_tol=1e-3,
        )

    def test_empty_syllable_is_negative_infinity(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        assert ranker.unigram_log_prob("") == float("-inf")


class TestBigramLogProb:
    def test_attested_bigram_beats_unattested(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        attested = ranker.bigram_log_prob("བཀྲ", "ཤིས")
        unattested = ranker.bigram_log_prob("བཀྲ", "ལེགས")
        assert math.isfinite(attested)
        assert unattested < attested

    def test_empty_context_is_negative_infinity(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        assert ranker.bigram_log_prob("", "ཤིས") == float("-inf")


class TestTrigramLogProb:
    def test_attested_trigram_is_finite(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        lp = ranker.trigram_log_prob("བཀྲ", "ཤིས", "བདེ")
        assert math.isfinite(lp)
        assert lp < 0.0

    def test_unattested_trigram_is_more_unlikely(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        attested = ranker.trigram_log_prob("བཀྲ", "ཤིས", "བདེ")
        unattested = ranker.trigram_log_prob("བཀྲ", "ཤིས", "ལེགས")
        assert unattested < attested


class TestPLL:
    def test_plausible_context_scores_higher_than_implausible(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        # "བདེ" in "བཀྲ ཤིས བདེ ལེགས" — the trigram བཀྲ ཤིས བདེ is attested.
        # Offsets: བ(0)ཀ(1)ྲ(2)␣(3)ཤ(4)ི(5)ས(6)␣(7)བ(8)ད(9)ེ(10)␣(11)…
        plausible = ranker.pll("བཀྲ ཤིས བདེ ལེགས", 8, 11, "བདེ")
        # "ལེགས" immediately after "བཀྲ" — bigram བཀྲ ལེགས is not attested.
        # Offsets: བ(0)ཀ(1)ྲ(2)␣(3)ལ(4)ེ(5)ག(6)ས(7)
        implausible = ranker.pll("བཀྲ ལེགས", 4, 8, "ལེགས")
        assert plausible > implausible

    def test_no_context_returns_zero(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        assert ranker.pll("བཀྲ", 0, 4, "བཀྲ") == 0.0


class TestIsSuspicious:
    def test_known_word_in_attested_context_is_not_suspicious(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        # "བཀྲ ཤིས" is an attested bigram; བཀྲ spans (0, 3).
        assert ranker.is_suspicious("བཀྲ ཤིས", 0, 3) is False

    def test_known_word_in_implausible_context_is_suspicious(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        # "ལེགས" after "བཀྲ" is unattested while its unigram baseline is high;
        # ལེགས spans (4, 8).
        assert ranker.is_suspicious("བཀྲ ལེགས", 4, 8) is True

    def test_word_with_no_context_is_never_suspicious(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        assert ranker.is_suspicious("བཀྲ", 0, 3) is False

    def test_suspicious_gap_is_configurable(self) -> None:
        strict = ContextualRanker(FakeCorpus(), suspicious_gap=0.0)
        assert strict.is_suspicious("བཀྲ ལེགས", 4, 8) is True

    def test_degenerate_bounds_are_safe(self) -> None:
        ranker = ContextualRanker(FakeCorpus())
        assert ranker.is_suspicious("", 0, 0) is False
        assert ranker.is_suspicious("བཀྲ", 0, 0) is False


class TestGracefulDegradation:
    def test_missing_maps_degrade_to_empty(self) -> None:
        class Bare:
            pass

        ranker = ContextualRanker(Bare())
        assert ranker.unigram_log_prob("བཀྲ") < 0.0
        assert ranker.is_suspicious("བཀྲ ལེགས", 4, 8) is False
