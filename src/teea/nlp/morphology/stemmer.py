"""Data-driven Tibetan morphological stem analyzer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StemCandidate:
    stem: str
    confidence: float          # 0.0-1.0
    rule_id: str               # e.g., "PAST_IRREGULAR", "SUFFIX_NOMINALIZER"
    source: str                # "irregular", "suffix", "fallback"
    explanation: str | None = None
    needs_dictionary_lookup: bool = True


class TibetanMorphologyAnalyzer:
    """Extracts candidate stems from Tibetan words using data-driven JSON rules."""

    def __init__(self, resource_path: Path | None = None) -> None:
        if resource_path is None:
            # Default to package resource path
            base_dir = Path(__file__).resolve().parent.parent.parent
            resource_path = base_dir / "resources" / "morphology"
        self._resource_path = resource_path
        self._irregular_verbs = self._load_json("irregular_verbs.json")
        self._suffix_rules = self._load_json("suffix_rules.json")

    def _load_json(self, filename: str) -> dict | list:
        file_path = self._resource_path / filename
        if not file_path.exists():
            return {} if filename.endswith(".json") and "verbs" in filename else []
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def analyze(self, word: str) -> list[StemCandidate]:
        """Return multiple possible stem analyses, ranked by confidence."""
        candidates: list[StemCandidate] = []
        clean_word = word.strip("་ །\u0f0b\u0f0d ")

        if not clean_word:
            return candidates

        # 1. Check irregular verbs first (highest confidence)
        if isinstance(self._irregular_verbs, dict) and clean_word in self._irregular_verbs:
            entry = self._irregular_verbs[clean_word]
            candidates.append(
                StemCandidate(
                    stem=entry["stem"],
                    confidence=entry.get("confidence", 0.97),
                    rule_id=entry.get("rule", "PAST_IRREGULAR"),
                    source="irregular",
                    explanation=entry.get("note", f"Irregular verb form of '{entry['stem']}'"),
                )
            )

        # 2. Check suffix stripping (data-driven, priority-ordered)
        if isinstance(self._suffix_rules, list):
            sorted_rules = sorted(self._suffix_rules, key=lambda x: x.get("priority", 0), reverse=True)
            for rule in sorted_rules:
                suffix = rule.get("suffix", "")
                if suffix and clean_word.endswith(suffix):
                    potential_stem = clean_word[:-len(suffix)].rstrip("་\u0f0b ")
                    if potential_stem:
                        candidates.append(
                            StemCandidate(
                                stem=potential_stem,
                                confidence=rule.get("confidence", 0.85),
                                rule_id=f"SUFFIX_{rule.get('category', 'suffix').upper()}",
                                source="suffix",
                                explanation=f"Stripped suffix '{suffix}' ({rule.get('category', 'suffix')})",
                            )
                        )

        # 3. Fallback: the word itself as a candidate
        candidates.append(
            StemCandidate(
                stem=clean_word,
                confidence=0.30 if candidates else 0.50,
                rule_id="NO_MORPHOLOGY",
                source="fallback",
                explanation="Raw word candidate",
            )
        )

        return candidates
