"""Sanskrit Transliteration Validator for Tibetan Words.

Validates Sanskrit-origin Tibetan words (e.g. ཀརྨ, པདྨ, བུདྡྷ, དྷརྨ)
and handles special final consonant extraction rules for Sanskrit transliterated stacks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

DEFAULT_SANSKRIT_WORDS_PATH: Final[Path] = Path("Data/Processed/sanskrit_words.json")

VALID_SANSKRIT_STACKS: Final[frozenset[str]] = frozenset({
    "ཀརྨ", "པདྨ", "བུདྡྷ", "དྷརྨ", "སངྒྷ", "ཨཱརྱ", "ཛྙཱན", "མཉྫུ", "བཛྲ", "རཏྣ", "མཎྜལ"
})

INVALID_SANSKRIT_STACKS: Final[frozenset[str]] = frozenset({
    "ཀསྨ", "པསྨ", "བདྡྷ"
})


class SanskritTransliterationValidator:
    """Validator for Sanskrit-origin Tibetan words and transliterated stack combinations."""

    def __init__(self, data_path: Path | str | None = None) -> None:
        self._path = Path(data_path) if data_path else DEFAULT_SANSKRIT_WORDS_PATH
        self._valid_words = set(VALID_SANSKRIT_STACKS)
        self._invalid_words = set(INVALID_SANSKRIT_STACKS)
        self.load()

    def load(self) -> None:
        """Load Sanskrit word dictionary from JSON file if available."""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
                self._valid_words.update(data.get("valid_words", []))
                self._invalid_words.update(data.get("invalid_stacks", []))
        except (OSError, ValueError):
            pass

    def is_valid_sanskrit(self, word: str) -> bool:
        """Check if a Sanskrit-origin word is valid."""
        clean = word.rstrip("་ །")
        return clean not in self._invalid_words

    def get_final_consonant_sanskrit(self, word: str) -> str:
        """Extract Sanskrit-aware final consonant for case particle agreement rules.
        
        Example: ཀརྨ (karma) -> final consonant sound is མ (m), not རྨ.
        """
        clean = word.rstrip("་ །")
        if clean == "ཀརྨ":
            return "མ"
        if clean == "པདྨ":
            return "མ"
        if clean == "བུདྡྷ":
            return "ད"

        # Fallback to last base consonant in stack
        consonants = [ch for ch in clean if ch in ("ག", "ང", "ད", "ན", "བ", "མ", "ར", "ལ", "ས")]
        if consonants:
            return consonants[-1]
        return "open"
