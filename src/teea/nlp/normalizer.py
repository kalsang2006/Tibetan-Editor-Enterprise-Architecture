"""Tibetan text normalizer for Stage 1 spell checker preprocessing."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class NormalizationResult:
    original: str
    normalized: str
    changed: bool
    changes: list[str] = field(default_factory=list)


class TibetanNormalizer:
    """Normalizes Tibetan characters, tshegs, shads, and spaces."""

    def normalize(self, text: str) -> NormalizationResult:
        """Apply NFC normalization and clean Tibetan-specific artifacts."""
        changes: list[str] = []
        original = text

        # 1. Unicode NFC normalization
        normalized = unicodedata.normalize("NFC", text)

        # 2. Remove duplicate tsheg
        normalized = re.sub(r"\u0f0b+", "\u0f0b", normalized)

        # 3. Normalize shad variants (standardizing to \u0f0d)
        normalized = re.sub(r"[\u0f0d\u0f0e\u0f0f\u0f11]+", "\u0f0d", normalized)

        # 4. Normalize spaces around punctuation
        normalized = re.sub(r" ([\u0f0b\u0f0d])", r"\1", normalized)
        normalized = re.sub(r"([\u0f0b\u0f0d]) ", r"\1", normalized)

        # Track changes
        if normalized != original:
            changes.append(f"normalized from '{original}' to '{normalized}'")

        return NormalizationResult(
            original=original,
            normalized=normalized,
            changed=(normalized != original),
            changes=changes,
        )
