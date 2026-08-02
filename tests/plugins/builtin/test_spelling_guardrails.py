"""Guardrail tests for the built-in SpellCheckerPlugin.

Covers the safety checks that prevent destructive edits:

* The Stage-4B context-detection hook ships enabled with a calibrated gap
  (5.0) and a confidence bar (0.75) for context edits.
* ``_guard_replacement`` rejects punctuation-injected, non-Tibetan,
  length-blown-up, or structurally invalid replacements, so the engine
  emits advisory-only suggestions instead of harmful edits.
"""

from __future__ import annotations

from teea.plugins.builtin.spelling import SpellCheckerConfig, SpellCheckerPlugin
from tests.plugins.builtin.test_spelling import (
    _make_single_node_snapshot,
)


class VocabularyDictionary:
    """A dictionary exposing a ``vocabulary`` surface of attested forms."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    @property
    def vocabulary(self) -> frozenset[str]:
        return frozenset(self._known)

    def __contains__(self, surface: str) -> bool:
        return surface in self._known


def _plugin(known: set[str] | None = None) -> SpellCheckerPlugin:
    """A plugin over a vocabulary-exposing dictionary with default config."""
    return SpellCheckerPlugin(
        dictionary=VocabularyDictionary(known or set()),
        config=SpellCheckerConfig(),
    )


# -- Default config -----------------------------------------------------------


def test_context_detection_is_calibrated_by_default() -> None:
    """The Stage-4B hook ships enabled with a calibrated gap and confidence bar."""
    config = SpellCheckerConfig()
    assert config.enable_context_detection is True
    # Gap calibrated against real corpus data (the 2.5-gap run collapsed
    # specificity to ~15%); context edits require a confident candidate.
    assert config.context_suspicious_gap == 5.0
    assert config.context_min_confidence == 0.75
    assert config.max_candidates == 10


def test_known_word_yields_no_suggestion_without_context_hook() -> None:
    """A known word in a plain snapshot produces no CONTEXT suggestion."""
    plugin = _plugin(known={"བཀྲ་", "ཤིས་"})
    snapshot = _make_single_node_snapshot("བཀྲ་")
    suggestions = list(plugin.examine(snapshot))
    assert all(s.error_type != "CONTEXT" for s in suggestions)


# -- Confidence guardrail -----------------------------------------------------


def test_low_confidence_replacement_is_withheld() -> None:
    plugin = _plugin()
    assert plugin._guard_replacement("མཚོན", "མཚན", 0.5) is None


# -- Punctuation / script guardrails -----------------------------------------


def test_punctuation_injected_replacement_is_withheld() -> None:
    """པ -> པ༴ must never be offered (U+0F34 is a punctuation mark)."""
    plugin = _plugin()
    assert plugin._guard_replacement("པ", "པ༴", 0.92) is None


def test_punctuation_injected_bracket_is_withheld() -> None:
    plugin = _plugin()
    assert plugin._guard_replacement("བ", "བ༽", 0.92) is None


def test_latin_replacement_is_withheld() -> None:
    plugin = _plugin()
    assert plugin._guard_replacement("པ", "pa", 0.92) is None


def test_digit_replacement_is_withheld() -> None:
    plugin = _plugin()
    assert plugin._guard_replacement("པ", "པ1", 0.92) is None


# -- Length guardrails --------------------------------------------------------


def test_length_blowup_replacement_is_withheld() -> None:
    """ང -> ངན adds a letter: +100% length, must be withheld."""
    plugin = _plugin()
    assert plugin._guard_replacement("ང", "ངན", 0.92) is None


def test_vowel_drop_replacement_is_withheld() -> None:
    """མཚོན -> མཚན drops a vowel: 25% length change, must be withheld."""
    plugin = _plugin()
    assert plugin._guard_replacement("མཚོན", "མཚན", 0.92) is None


def test_small_tsheg_repair_is_allowed() -> None:
    """སོགས -> སོ་གས inserts only a delimiter: letter count unchanged."""
    plugin = _plugin(known={"སོ་གས"})
    assert plugin._guard_replacement("སོགས", "སོ་གས", 0.92) == "སོ་གས"


def test_same_length_substitution_is_allowed() -> None:
    """བཀྲ་ཤིམ -> བཀྲ་ཤིས swaps one letter at equal length."""
    plugin = _plugin(known={"བཀྲ་ཤིས་"})
    assert plugin._guard_replacement("བཀྲ་ཤིམ་", "བཀྲ་ཤིས་", 0.92) == "བཀྲ་ཤིས་"


# -- Dictionary-attestation guardrail ----------------------------------------


def test_replacement_not_in_vocabulary_is_withheld() -> None:
    """When the dictionary exposes a vocabulary, the replacement must be in it."""
    plugin = _plugin(known={"བཀྲ་ཤིས་"})
    assert plugin._guard_replacement("བཀྲ་ཤིམ", "བཀྲ་གཅིག", 0.92) is None


# -- Structural guardrail -----------------------------------------------------


def test_structurally_invalid_replacement_is_withheld() -> None:
    """A syllable with an illegal consonant stack must be rejected."""
    plugin = _plugin(known={"པཀ"})
    # པཀ: two base consonants with no legal prefix/suffix arrangement.
    assert plugin._guard_replacement("པ", "པཀ", 0.92) is None


# -- Emission logic -----------------------------------------------------------


def test_garbage_candidate_emits_advisory_only() -> None:
    """A provider returning a garbage candidate yields an advisory, not an edit."""
    plugin = _plugin(known=set())

    class GarbageProvider:
        def generate_candidates(self, word: str, sentence: str, max_candidates: int = 5):
            return [type("C", (), {"word": "པ༴", "confidence": 0.92})()]

    plugin._correction_provider = GarbageProvider()  # type: ignore[assignment]
    snapshot = _make_single_node_snapshot("པ")
    suggestions = list(plugin.examine(snapshot))

    assert len(suggestions) == 1
    assert suggestions[0].replacement is None  # advisory only
    assert suggestions[0].is_advisory is True
    assert "rejected" in suggestions[0].message


def test_valid_candidate_emits_edit() -> None:
    """A same-length, attested, structurally valid replacement is offered."""
    plugin = _plugin(known={"བཀྲ་ཤིས་"})

    class GoodProvider:
        def generate_candidates(self, word: str, sentence: str, max_candidates: int = 5):
            return [type("C", (), {"word": "བཀྲ་ཤིས་", "confidence": 0.92})()]

    plugin._correction_provider = GoodProvider()  # type: ignore[assignment]
    snapshot = _make_single_node_snapshot("བཀྲ་ཤིམ་")
    suggestions = list(plugin.examine(snapshot))

    assert len(suggestions) == 1
    assert suggestions[0].replacement == "བཀྲ་ཤིས་"
    assert suggestions[0].is_edit is True
