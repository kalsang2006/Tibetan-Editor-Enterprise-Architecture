"""Unit tests for grammar checker overhaul and RuleRegistry."""

from __future__ import annotations

from teea.grammar.rule_registry import RuleRegistry
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.plugins.builtin.grammar import GrammarCheckerPlugin


class TestGrammarOverhaul:
    def test_rule_registry_defaults(self) -> None:
        """RuleRegistry should contain default rules TIB-PART-001 through TIB-NOM-001."""
        registry = RuleRegistry()
        assert registry.is_enabled("TIB-PART-001")
        assert registry.is_enabled("TIB-EXIST-001")
        assert registry.is_enabled("TIB-TEMP-001")
        assert registry.is_enabled("TIB-HONOR-001")
        assert registry.is_enabled("TIB-COP-001")
        assert registry.is_enabled("TIB-SOV-001")
        assert registry.is_enabled("TIB-NOM-001")

    def test_rule_registry_toggle(self) -> None:
        """RuleRegistry should toggle rules on/off via configuration."""
        registry = RuleRegistry({"rules": {"TIB-EXIST-001": False}})
        assert not registry.is_enabled("TIB-EXIST-001")
        assert registry.is_enabled("TIB-PART-001")

    def test_existential_verb_error(self) -> None:
        """'འདུགས' should yield suggestion 'འདུག' with score 0.95."""
        builder = LanguageServerSnapshotBuilder()
        snapshot = builder.analyze("འདིར་ཡོད་པའི་མི་དེ་འདུགས།")
        plugin = GrammarCheckerPlugin()
        suggestions = list(plugin.examine(snapshot))
        exist_suggs = [s for s in suggestions if "TIB-EXIST-001" in s.message]
        assert len(exist_suggs) > 0
        assert exist_suggs[0].replacement == "འདུག"
        assert exist_suggs[0].score == 0.95

    def test_particle_agreement_achung(self) -> None:
        """Words ending in 'འ' should take genitive 'འི' / ergative 'འིས'."""
        from teea.plugins.builtin.grammar import _get_tibetan_final_consonant
        assert _get_tibetan_final_consonant("མཁའ") == "འ"

    def test_honorific_agreement(self) -> None:
        """Honorific subject with plain verb 'སྡོད' should suggest 'བཞུགས' with score 0.60."""
        builder = LanguageServerSnapshotBuilder()
        snapshot = builder.analyze("ཁྱེད་རང་སྡོད།")
        plugin = GrammarCheckerPlugin()
        suggestions = list(plugin.examine(snapshot))
        honor_suggs = [s for s in suggestions if "TIB-HONOR-001" in s.message]
        assert len(honor_suggs) > 0
        assert honor_suggs[0].replacement == "བཞུགས"
        assert honor_suggs[0].score == 0.60
