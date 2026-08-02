"""Repository accessor for BoCorpus vocabulary, n-grams, and synthetic datasets.

Provides clean read access to processed corpus artifacts for TEEA language services.
"""

from __future__ import annotations

import json
from pathlib import Path

from teea.core.errors import ConfigurationError
from teea.core.logging import get_logger
from teea.corpus.synthetic import SyntheticErrorDataset

_logger = get_logger(__name__)

DEFAULT_PROCESSED_DIR = Path("Data/Processed")
DEFAULT_SYNTHETIC_DIR = Path("Data/SyntheticErrors")


class BoCorpusRepository:
    """Repository for querying BoCorpus vocabulary and n-gram statistics."""

    def __init__(
        self,
        processed_dir: Path | str = DEFAULT_PROCESSED_DIR,
        synthetic_dir: Path | str = DEFAULT_SYNTHETIC_DIR,
    ) -> None:
        self.processed_dir = Path(processed_dir)
        self.synthetic_dir = Path(synthetic_dir)

        self._vocab: dict[str, int] | None = None
        self._bigrams: dict[str, int] | None = None
        self._trigrams: dict[str, int] | None = None
        self._total_syllable_count: int | None = None
        self._total_bigram_count: int | None = None
        self._total_trigram_count: int | None = None

    def is_available(self) -> bool:
        """Check if BoCorpus processed artifacts exist on disk."""
        vocab_file = self.processed_dir / "bocorpus_vocabulary.json"
        return vocab_file.exists()

    @property
    def vocabulary(self) -> dict[str, int]:
        """Map of Tibetan syllable -> frequency count."""
        if self._vocab is None:
            vocab_file = self.processed_dir / "bocorpus_vocabulary.json"
            if not vocab_file.exists():
                raise ConfigurationError(f"Vocabulary artifact not found at {vocab_file}")
            try:
                data = json.loads(vocab_file.read_text(encoding="utf-8"))
                self._vocab = data.get("syllable_frequencies", {})
                self._total_syllable_count = sum(self._vocab.values()) or 1
            except Exception as exc:
                raise ConfigurationError(f"Malformed vocabulary JSON at {vocab_file}") from exc
        return self._vocab

    @property
    def bigrams(self) -> dict[str, int]:
        """Map of bigram string 's1 s2' -> frequency count."""
        self._load_ngrams()
        return self._bigrams or {}

    @property
    def trigrams(self) -> dict[str, int]:
        """Map of trigram string 's1 s2 s3' -> frequency count."""
        self._load_ngrams()
        return self._trigrams or {}

    def is_known_syllable(self, syllable: str, min_frequency: int = 1) -> bool:
        """Check if a syllable exists in the BoCorpus vocabulary with sufficient frequency."""
        return self.get_syllable_frequency(syllable) >= min_frequency

    def get_syllable_frequency(self, syllable: str) -> int:
        """Return frequency of a syllable in the corpus (0 if unknown)."""
        if not syllable:
            return 0
        freq = self.vocabulary.get(syllable, 0)
        if freq == 0:
            clean = syllable.rstrip("\u0f0b à¼")
            freq = self.vocabulary.get(clean, 0)
            if freq == 0 and not syllable.endswith("\u0f0b") and len(clean) <= 4:
                freq = self.vocabulary.get(clean + "\u0f0b", 0)
        return freq

    def get_unigram_score(self, syllable: str) -> float:
        """Return normalized log-frequency score in [0.0, 1.0] for a syllable."""
        import math
        freq = self.get_syllable_frequency(syllable)
        if freq <= 0:
            return 0.0
        # Log scale: log(freq + 1) / log(max_freq + 1)
        max_freq = max(self.vocabulary.values(), default=1)
        return float(math.log(freq + 1) / math.log(max_freq + 1))

    def get_bigram_score(self, prev_syl: str, curr_syl: str) -> float:
        """Return normalized score in [0.0, 1.0] for bigram (prev_syl, curr_syl)."""
        if not prev_syl or not curr_syl:
            return 0.0
        p_clean = prev_syl.rstrip("\u0f0b à¼")
        c_clean = curr_syl.rstrip("\u0f0b à¼")
        
        bg_key = f"{prev_syl} {curr_syl}"
        count = self.bigrams.get(bg_key, 0)
        if count == 0:
            count = self.bigrams.get(f"{p_clean} {c_clean}", 0)
            if count == 0:
                count = self.bigrams.get(f"{p_clean}\u0f0b {c_clean}\u0f0b", 0)
        
        if count <= 0:
            return 0.0
        prev_freq = self.get_syllable_frequency(prev_syl)
        if prev_freq <= 0:
            return 0.0
        # Conditional probability P(curr|prev)
        prob = count / prev_freq
        return min(1.0, float(prob))

    def get_trigram_score(self, s1: str, s2: str, s3: str) -> float:
        """Return normalized score in [0.0, 1.0] for trigram (s1, s2, s3)."""
        if not s1 or not s2 or not s3:
            return 0.0
        tg_key = f"{s1} {s2} {s3}"
        count = self.trigrams.get(tg_key, 0)
        if count <= 0:
            return 0.0
        bg_key = f"{s1} {s2}"
        bg_count = self.bigrams.get(bg_key, 0)
        if bg_count <= 0:
            return 0.0
        # Conditional probability P(s3|s1, s2)
        prob = count / bg_count
        return min(1.0, float(prob))

    def get_context_score(
        self, sentence: str, word_start: int, word_end: int, candidate: str
    ) -> float:
        """Calculate context-aware n-gram score for a candidate in sentence context.

        Combines left/right bigram and trigram conditional probabilities.
        """
        tsheg = "\u0f0b"
        # Segment sentence into left context, candidate, and right context syllables
        left_text = sentence[:word_start]
        right_text = sentence[word_end:]

        left_syls = [s.strip() for s in left_text.split(tsheg) if s.strip()]
        right_syls = [s.strip() for s in right_text.split(tsheg) if s.strip()]
        cand_syls = [s.strip() for s in candidate.split(tsheg) if s.strip()]

        if not cand_syls:
            return 0.0

        scores: list[float] = []

        # 1. Unigram score of candidate syllable(s)
        unigram_avg = sum(self.get_unigram_score(c) for c in cand_syls) / len(cand_syls)
        scores.append(unigram_avg * 0.4)

        # 2. Left context bigram (left_last + cand_first)
        if left_syls:
            left_bg = self.get_bigram_score(left_syls[-1], cand_syls[0])
            scores.append(left_bg * 0.3)

        # 3. Right context bigram (cand_last + right_first)
        if right_syls:
            right_bg = self.get_bigram_score(cand_syls[-1], right_syls[0])
            scores.append(right_bg * 0.3)

        # 4. Trigram context (left2 + left1 + cand_first)
        if len(left_syls) >= 2:
            left_tg = self.get_trigram_score(left_syls[-2], left_syls[-1], cand_syls[0])
            scores.append(left_tg * 0.4)

        return float(min(1.0, sum(scores)))

    def load_synthetic_dataset(self) -> SyntheticErrorDataset:
        """Load the generated synthetic error dataset."""
        syn_file = self.synthetic_dir / "synthetic_errors.json"
        if not syn_file.exists():
            raise ConfigurationError(f"Synthetic error dataset not found at {syn_file}")
        try:
            return SyntheticErrorDataset.model_validate_json(syn_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ConfigurationError(f"Malformed synthetic error dataset at {syn_file}") from exc

    def _load_ngrams(self) -> None:
        if self._bigrams is not None and self._trigrams is not None:
            return
        ngram_file = self.processed_dir / "bocorpus_ngrams.json"
        if not ngram_file.exists():
            raise ConfigurationError(f"N-gram artifact not found at {ngram_file}")
        try:
            data = json.loads(ngram_file.read_text(encoding="utf-8"))
            self._bigrams = data.get("bigrams", {})
            self._trigrams = data.get("trigrams", {})
            self._total_bigram_count = sum(self._bigrams.values()) or 1
            self._total_trigram_count = sum(self._trigrams.values()) or 1
        except Exception as exc:
            raise ConfigurationError(f"Malformed n-gram JSON at {ngram_file}") from exc
