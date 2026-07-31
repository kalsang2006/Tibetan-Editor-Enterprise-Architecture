"""Rule Registry and Configuration System for TEEA Grammar & Spelling Rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GrammarRule:
    """Metadata-rich representation of an individual linguistic error checking rule."""

    rule_id: str               # e.g., "TIB-EXIST-001"
    category: str              # e.g., "verb", "particle", "honorific", "word_order"
    description: str           # Human-readable summary
    confidence_baseline: float # 0.0–1.0
    enabled: bool = True
    example_incorrect: str = ""
    example_correct: str = ""
    explanation: str = ""      # Detailed reasoning for the user


class RuleRegistry:
    """Registry managing active grammar & spelling rules and their runtime configurations."""

    def __init__(self, config_overrides: dict[str, Any] | None = None) -> None:
        self._rules: dict[str, GrammarRule] = {}
        self._register_default_rules()
        if config_overrides:
            self.apply_config(config_overrides)

    def register(self, rule: GrammarRule) -> None:
        """Register or update a rule."""
        self._rules[rule.rule_id] = rule

    def get_rule(self, rule_id: str) -> GrammarRule | None:
        """Get a registered rule by ID."""
        return self._rules.get(rule_id)

    def is_enabled(self, rule_id: str) -> bool:
        """Check if a rule is registered and enabled."""
        rule = self._rules.get(rule_id)
        return rule.enabled if rule is not None else False

    def apply_config(self, config: dict[str, Any]) -> None:
        """Apply JSON/YAML configuration overrides to toggle rules."""
        rules_config = config.get("rules", config)
        if isinstance(rules_config, dict):
            for rule_id, settings in rules_config.items():
                if rule_id in self._rules:
                    if isinstance(settings, bool):
                        self._rules[rule_id].enabled = settings
                    elif isinstance(settings, dict):
                        if "enabled" in settings:
                            self._rules[rule_id].enabled = bool(settings["enabled"])
                        if "confidence_baseline" in settings:
                            self._rules[rule_id].confidence_baseline = float(settings["confidence_baseline"])

    def _register_default_rules(self) -> None:
        defaults = [
            GrammarRule(
                rule_id="TIB-PART-001",
                category="particle",
                description="Case and particle phonetic agreement validation",
                confidence_baseline=0.98,
                example_incorrect="བོད་གི་",
                example_correct="བོད་ཀྱི་",
                explanation="Genitive particle following final 'ད' must be 'ཀྱི'.",
            ),
            GrammarRule(
                rule_id="TIB-EXIST-001",
                category="verb",
                description="Existential verb typo check",
                confidence_baseline=0.95,
                example_incorrect="འདུགས",
                example_correct="འདུག",
                explanation="'འདུགས' is an invalid spelling of existential verb 'འདུག'.",
            ),
            GrammarRule(
                rule_id="TIB-TEMP-001",
                category="adverb",
                description="Temporal adverb context validation",
                confidence_baseline=0.85,
                example_incorrect="དེང་སང",
                example_correct="དེ་རིང",
                explanation="'དེང་སང' means 'nowadays'; use 'དེ་རིང' for 'today'.",
            ),
            GrammarRule(
                rule_id="TIB-HONOR-001",
                category="honorific",
                description="Honorific subject-verb agreement",
                confidence_baseline=0.60,
                example_incorrect="ཁྱེད་རང་སྡོད",
                example_correct="ཁྱེད་རང་བཞུགས",
                explanation="Honorific subject 'ཁྱེད་རང' should be paired with honorific verb 'བཞུགས'.",
            ),
            GrammarRule(
                rule_id="TIB-COP-001",
                category="verb",
                description="Copula and evidential agreement",
                confidence_baseline=0.55,
                example_incorrect="ང་རེད",
                example_correct="ང་ཡིན",
                explanation="First person subject generally uses egophoric copula 'ཡིན'.",
            ),
            GrammarRule(
                rule_id="TIB-SOV-001",
                category="word_order",
                description="Subject-Object-Verb word order validation",
                confidence_baseline=0.50,
                example_incorrect="ཀློག་དཔེ་ཆ",
                example_correct="དཔེ་ཆ་ཀློག",
                explanation="Tibetan follows SOV word order; object precedes the verb.",
            ),
            GrammarRule(
                rule_id="TIB-NOM-001",
                category="nominalizer",
                description="Redundant sentence-final nominalizer check",
                confidence_baseline=0.90,
                example_incorrect="ཁོང་སློབ་མ་ཡིན་པ།",
                example_correct="ཁོང་སློབ་མ་ཡིན།",
                explanation="Sentence-final declarative copula should not end with nominalizer 'པ'.",
            ),
        ]
        for r in defaults:
            self.register(r)
