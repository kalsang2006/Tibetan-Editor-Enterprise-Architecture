"""Unit tests for data-driven 7-stage spell checker overhaul."""

from __future__ import annotations

from pathlib import Path
import pytest

from teea.nlp.morphology.stemmer import StemCandidate, TibetanMorphologyAnalyzer
from teea.nlp.normalizer import TibetanNormalizer
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.plugins.builtin.spelling import SpellCheckerConfig, SpellCheckerPlugin


class TestSpellingOverhaul:
    def test_normalization_duplicate_tsheg(self) -> None:
        """Duplicate tsheg should be normalized."""
        normalizer = TibetanNormalizer()
        res = normalizer.normalize("བོད་་")
        assert res.changed
        assert res.normalized == "བོད་"

    def test_morphology_irregular_verbs(self) -> None:
        """Irregular verb past forms (བཀླགས, བྱས, སོང, ཟོས, བཏང) should stem correctly."""
        analyzer = TibetanMorphologyAnalyzer()
        res_bklags = analyzer.analyze("བཀླགས")
        assert any(c.stem == "ཀློག" for c in res_bklags)

        res_byas = analyzer.analyze("བྱས")
        assert any(c.stem == "བྱེད" for c in res_byas)

        res_song = analyzer.analyze("སོང")
        assert any(c.stem == "འགྲོ" for c in res_song)

    def test_suffix_stripping(self) -> None:
        """Suffixes like པ, གི་ཡོད should strip to base stem."""
        analyzer = TibetanMorphologyAnalyzer()
        res = analyzer.analyze("བཀླགས་པ")
        assert any(c.stem == "བཀླགས" for c in res)

    def test_spelling_plugin_examine(self) -> None:
        """SpellCheckerPlugin should analyze snapshot cleanly without crashing."""
        builder = LanguageServerSnapshotBuilder()
        snapshot = builder.analyze("བཀྲ་ཤིས་བདེ་ལེགས།")
        plugin = SpellCheckerPlugin()
        suggestions = list(plugin.examine(snapshot))
        assert isinstance(suggestions, list)

    def test_config_toggle_normalization(self) -> None:
        """Disabling normalization should skip STAGE 1 normalization suggestions."""
        config = SpellCheckerConfig(enable_normalization=False)
        plugin = SpellCheckerPlugin(config=config)
        builder = LanguageServerSnapshotBuilder()
        snapshot = builder.analyze("བོད་་")
        suggestions = list(plugin.examine(snapshot))
        assert not any(s.error_type == "NORMALIZATION" for s in suggestions)
