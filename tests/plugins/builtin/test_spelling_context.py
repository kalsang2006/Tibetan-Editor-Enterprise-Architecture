"""Integration tests for the Stage-4B context-detection hook (§3).

A dictionary-known word that appears in an implausible context must be
flagged with ``source="teea.spelling.context"`` and ``LOW`` priority, while
an attested context must stay quiet.
"""

from __future__ import annotations

from typing import ClassVar

from teea.fusion import SuggestionPriority
from teea.plugins.builtin.spelling import SpellCheckerConfig, SpellCheckerPlugin
from tests.plugins.builtin.test_spelling import SelectivelyEmptyDictionary, _make_two_node_snapshot


class FakeCorpus:
    """Minimal corpus; བཀྲ-ཤིས is attested, བཀྲ-ལེགས is not."""

    vocabulary: ClassVar[dict[str, int]] = {
        "བཀྲ": 1000,
        "ཤིས": 900,
        "བདེ": 800,
        "ལེགས": 750,
    }
    bigrams: ClassVar[dict[str, int]] = {
        "བཀྲ ཤིས": 850,
        "བདེ ལེགས": 700,
    }
    trigrams: ClassVar[dict[str, int]] = {
        "བཀྲ ཤིས བདེ": 600,
    }


def _known_dictionary(*words: str) -> SelectivelyEmptyDictionary:
    """A dictionary that knows exactly the given surface forms."""
    return SelectivelyEmptyDictionary(known=set(words))


class TestContextDetectionHook:
    def test_known_word_in_implausible_context_is_flagged(self) -> None:
        # ལེགས after བཀྲ is unattested (no བཀྲ-ལེགས bigram), so the known
        # word must be flagged as a CONTEXT error. The hook is off by default
        # (``enable_context_detection=False``) and the default gap is huge
        # (``999.0``), so an explicit tuned gap is required to exercise it.
        plugin = SpellCheckerPlugin(
            config=SpellCheckerConfig(
                enable_context_detection=True,
                context_suspicious_gap=2.5,
            ),
            dictionary=_known_dictionary("བཀྲ་", "ལེགས་"),
            corpus_repository=FakeCorpus(),
        )
        snapshot = _make_two_node_snapshot("བཀྲ་ལེགས་", "བཀྲ་", "ལེགས་")

        suggestions = list(plugin.examine(snapshot))

        context_sugs = [s for s in suggestions if s.error_type == "CONTEXT"]
        assert context_sugs, f"expected a context suggestion, got {suggestions}"
        assert all(s.priority is SuggestionPriority.LOW for s in context_sugs)
        assert all(s.error_type == "CONTEXT" for s in context_sugs)

    def test_attested_context_is_not_flagged(self) -> None:
        # བཀྲ ཤིས is an attested bigram — no context suggestion.
        plugin = SpellCheckerPlugin(
            dictionary=_known_dictionary("བཀྲ་", "ཤིས་"),
            corpus_repository=FakeCorpus(),
        )
        snapshot = _make_two_node_snapshot("བཀྲ་ཤིས་", "བཀྲ་", "ཤིས་")

        suggestions = list(plugin.examine(snapshot))

        assert all(s.source != "teea.spelling.context" for s in suggestions)

    def test_hook_can_be_disabled_by_config(self) -> None:
        plugin = SpellCheckerPlugin(
            dictionary=_known_dictionary("བཀྲ་", "ལེགས་"),
            corpus_repository=FakeCorpus(),
            config=SpellCheckerConfig(enable_context_detection=False),
        )
        snapshot = _make_two_node_snapshot("བཀྲ་ལེགས་", "བཀྲ་", "ལེགས་")

        suggestions = list(plugin.examine(snapshot))

        assert all(s.source != "teea.spelling.context" for s in suggestions)

    def test_hook_is_inactive_without_corpus(self) -> None:
        plugin = SpellCheckerPlugin(dictionary=_known_dictionary("བཀྲ་", "ལེགས་"))
        snapshot = _make_two_node_snapshot("བཀྲ་ལེགས་", "བཀྲ་", "ལེགས་")

        suggestions = list(plugin.examine(snapshot))

        assert all(s.source != "teea.spelling.context" for s in suggestions)

    def test_a_failing_corpus_does_not_crash_the_plugin(self) -> None:
        class BrokenCorpus:
            @property
            def vocabulary(self) -> dict[str, int]:
                raise RuntimeError("corpus exploded")

        plugin = SpellCheckerPlugin(
            dictionary=_known_dictionary("བཀྲ་", "ལེགས་"),
            corpus_repository=BrokenCorpus(),
        )
        snapshot = _make_two_node_snapshot("བཀྲ་ལེགས་", "བཀྲ་", "ལེགས་")

        suggestions = list(plugin.examine(snapshot))

        assert all(s.source != "teea.spelling.context" for s in suggestions)
