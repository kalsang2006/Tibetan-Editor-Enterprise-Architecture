"""Tibetan Verb Lexicon & Transitivity/Tense Validator.

Manages verb valency, transitivity (TRANS, INTRANS, COPULA, EXISTENTIAL), honorific forms (HON, NEUT),
and tense agreement (past, present, future).
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Final
from pydantic import BaseModel, Field

DEFAULT_VERB_LEXICON_PATH: Final[Path] = Path("Data/Processed/verb_lexicon.json")


class Transitivity(str, Enum):
    """Verb transitivity classification."""

    TRANS = "TRANS"
    INTRANS = "INTRANS"
    COPULA = "COPULA"
    EXISTENTIAL = "EXISTENTIAL"


class VerbInfo(BaseModel):
    """Grammatical properties of a Tibetan verb."""

    transitivity: Transitivity = Transitivity.TRANS
    honorific: str = "NEUT"
    valency: int = 1
    tense: str = "present"


class VerbLexicon:
    """Repository of Tibetan verbs with syntactic & morphological metadata."""

    def __init__(self, data_path: Path | str | None = None) -> None:
        self._path = Path(data_path) if data_path else DEFAULT_VERB_LEXICON_PATH
        self._verbs: dict[str, VerbInfo] = {}
        self._bootstrap_defaults()
        self.load()

    def _bootstrap_defaults(self) -> None:
        """Pre-populate default verb properties."""
        defaults = {
            "ཡིན": VerbInfo(transitivity=Transitivity.COPULA, honorific="NEUT", valency=1, tense="present"),
            "ཡོད": VerbInfo(transitivity=Transitivity.EXISTENTIAL, honorific="NEUT", valency=1, tense="present"),
            "འགྱུར": VerbInfo(transitivity=Transitivity.INTRANS, honorific="NEUT", valency=1, tense="future"),
            "བལྟས": VerbInfo(transitivity=Transitivity.TRANS, honorific="NEUT", valency=2, tense="past"),
            "ཕྱིན": VerbInfo(transitivity=Transitivity.INTRANS, honorific="NEUT", valency=1, tense="past"),
            "བཀོལ": VerbInfo(transitivity=Transitivity.TRANS, honorific="NEUT", valency=2, tense="past"),
            "འཁོར": VerbInfo(transitivity=Transitivity.INTRANS, honorific="NEUT", valency=1, tense="present"),
            "ཞུས": VerbInfo(transitivity=Transitivity.TRANS, honorific="HON", valency=2, tense="past"),
            "འཐུང": VerbInfo(transitivity=Transitivity.TRANS, honorific="NEUT", valency=2, tense="present"),
            "བསྐོལ": VerbInfo(transitivity=Transitivity.TRANS, honorific="NEUT", valency=2, tense="past"),
            "གཟིགས": VerbInfo(transitivity=Transitivity.TRANS, honorific="HON", valency=2, tense="present"),
            "བཟོས": VerbInfo(transitivity=Transitivity.TRANS, honorific="NEUT", valency=2, tense="past"),
            "བཟོ": VerbInfo(transitivity=Transitivity.TRANS, honorific="NEUT", valency=2, tense="present"),
        }
        self._verbs.update(defaults)

    def load(self) -> None:
        """Load verb lexicon from JSON file if available."""
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
                raw = data.get("verbs", {})
                for verb, val in raw.items():
                    self._verbs[verb] = VerbInfo(
                        transitivity=Transitivity(val.get("transitivity", "TRANS")),
                        honorific=str(val.get("honorific", "NEUT")),
                        valency=int(val.get("valency", 1)),
                        tense=str(val.get("tense", "present")),
                    )
        except Exception:
            pass

    def get_verb_info(self, verb: str) -> VerbInfo | None:
        """Return VerbInfo for a given verb (or None if unindexed)."""
        clean = verb.rstrip("་ །")
        return self._verbs.get(clean)

    def is_verb(self, word: str) -> bool:
        """Check if a word is a recognized verb."""
        return self.get_verb_info(word) is not None
