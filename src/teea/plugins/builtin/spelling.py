"""Built-in spell checker plugin for TEEA (7-Stage Pipeline).

Flags Tibetan morphemes that are not attested in the corpus-derived
Dictionary Repository as potential misspellings, after normalization,
structural validation, and morphological stem analysis.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.dependency import DependencyRelation
from teea.nlp.morphology.stemmer import StemCandidate, TibetanMorphologyAnalyzer
from teea.nlp.normalizer import NormalizationResult, TibetanNormalizer
from teea.nlp.snapshot import DocumentSnapshot
from teea.nlp.structural_validator import StructuralValidator
from teea.persistence import DictionaryRepository, default_dictionary
from teea.plugins.builtin.correction_providers import (
    CorrectionCandidate,
    CorrectionProvider,
    DictionaryOnlyCorrectionProvider,
    TibertCorrectionProvider,
)

logger = structlog.get_logger(__name__)


@dataclass
class SpellCheckerConfig:
    """Configuration settings for SpellCheckerPlugin 7-stage pipeline."""

    # Pipeline toggles
    enable_normalization: bool = True
    enable_structural_validation: bool = True
    enable_morphological_analysis: bool = True
    enable_tibert_reranking: bool = False

    # Correction parameters
    max_edit_distance: int = 2
    min_confidence_for_suggestion: float = 0.50
    max_candidates: int = 5

    # Performance & caching
    dict_lookup_timeout_ms: int = 5
    enable_caching: bool = True
    cache_size: int = 10000
    resource_path: Path | None = None


class SpellCheckerPlugin:
    """7-Stage Data-Driven Spell Checker Plugin.

    Pipeline:
      Stage 1: Normalization (NFC, duplicate tsheg, punctuation cleanup)
      Stage 2: Structural Validation (Syllable orthographic legality)
      Stage 3: Morphological Analysis (Irregular verbs + suffix stripping)
      Stage 4: Dictionary Lookup (Validates stem candidates)
      Stage 5: Candidate Generation (Edit distance trie search)
      Stage 6: Contextual Reranking (Optional TiBERT AI Runtime)
      Stage 7: Suggestion Emission & Structured Logging
    """

    def __init__(
        self,
        dictionary: DictionaryRepository | None = None,
        correction_provider: CorrectionProvider | None = None,
        ai_runtime: Any = None,
        config: SpellCheckerConfig | None = None,
        *,
        corpus_repository: Any = None,
        validator: StructuralValidator | None = None,
    ) -> None:
        self._dictionary = dictionary if dictionary is not None else default_dictionary()
        self._config = config or SpellCheckerConfig()
        self._normalizer = TibetanNormalizer()
        self._validator = validator or StructuralValidator()
        self._morphology = TibetanMorphologyAnalyzer(resource_path=self._config.resource_path)
        self._ai_runtime = ai_runtime
        self._corpus_repository = corpus_repository
        self._name = "teea.spelling"

        if correction_provider is not None:
            self._correction_provider = correction_provider
        elif self._config.enable_tibert_reranking and self._ai_runtime is not None:
            self._correction_provider = TibertCorrectionProvider(
                self._dictionary, ai_runtime=self._ai_runtime, max_edit_distance=self._config.max_edit_distance
            )
        else:
            self._correction_provider = None

        self._lookup_cache: dict[str, bool] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def config(self) -> SpellCheckerConfig:
        return self._config

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        byte_table = utf8_byte_offsets(snapshot.source)

        for analysis in snapshot.analyses:
            tree = analysis.tree
            if tree.is_empty:
                continue

            sent_start = analysis.span.char_start

            ALL_SAFE_PARTICLES = {"གི", "ཀྱི", "གྱི", "ཡི", "འི", "གིས", "ཀྱིས", "གྱིས", "ཡིས", "ས", "ལ", "ར", "རུ", "ཏུ", "དུ", "ན", "ནས", "ལས", "ནི", "ཀྱང", "ཡང", "འང", "དང", "མི", "མེད", "ཡིན", "རེད", "ཡོད", "འདུག"}

            for node in tree.nodes:
                # Skip punctuation
                if node.relation == DependencyRelation.PUNCT:
                    continue

                raw_word = node.text.strip("། ཿ")
                if not raw_word:
                    continue

                # Skip pipeline artifacts (ASCII dummy nodes or recognized safe particles)
                if node.relation in (DependencyRelation.CASE, DependencyRelation.AUX, DependencyRelation.MARK, DependencyRelation.NEG) and (raw_word.isascii() or raw_word.strip("་ ") in ALL_SAFE_PARTICLES):
                    continue

                # ==========================================
                # STAGE 1: NORMALIZATION
                # ==========================================
                if self._config.enable_normalization:
                    norm_result = self._normalizer.normalize(raw_word)
                    if norm_result.changed and norm_result.normalized != raw_word:
                        yield self._build_normalization_suggestion(
                            node, sent_start, norm_result, byte_table
                        )
                        continue
                else:
                    norm_result = NormalizationResult(raw_word, raw_word, False, [])

                # ==========================================
                # STAGE 2: STRUCTURAL VALIDATION
                # ==========================================
                if self._config.enable_structural_validation:
                    syllables = [s for s in norm_result.normalized.split("\u0f0b") if s]
                    invalid_struct = False
                    for syl in syllables:
                        s_res = self._validator.validate_syllable(syl)
                        if not s_res.is_valid:
                            invalid_struct = True
                            yield self._build_structural_suggestion(
                                node, sent_start, syl, s_res, byte_table
                            )
                            break
                    if invalid_struct:
                        continue

                # ==========================================
                # STAGE 3: MORPHOLOGICAL ANALYSIS
                # ==========================================
                if self._config.enable_morphological_analysis:
                    stem_candidates = self._morphology.analyze(norm_result.normalized)
                else:
                    stem_candidates = [
                        StemCandidate(norm_result.normalized, 0.50, "NO_MORPHOLOGY", "fallback")
                    ]

                # ==========================================
                # STAGE 4: DICTIONARY LOOKUP
                # ==========================================
                if node.text in self._dictionary or raw_word in self._dictionary or norm_result.normalized in self._dictionary:
                    continue
                if hasattr(self._dictionary, "is_valid_word_or_compound") and self._dictionary.is_valid_word_or_compound(norm_result.normalized):
                    continue

                valid_candidates: list[StemCandidate] = []
                for candidate in stem_candidates:
                    cache_key = candidate.stem
                    if self._config.enable_caching and cache_key in self._lookup_cache:
                        exists = self._lookup_cache[cache_key]
                    else:
                        exists = candidate.stem in self._dictionary
                        if self._config.enable_caching and len(self._lookup_cache) < self._config.cache_size:
                            self._lookup_cache[cache_key] = exists

                    if exists:
                        valid_candidates.append(candidate)

                # If ANY valid candidate exists, word is correctly spelled
                if valid_candidates:
                    continue

                # ==========================================
                # STAGE 5: CANDIDATE GENERATION
                # ==========================================
                if self._correction_provider is not None:
                    if hasattr(self._correction_provider, "generate_candidates"):
                        correction_candidates = self._correction_provider.generate_candidates(
                            word=norm_result.normalized,
                            sentence=analysis.text,
                            max_candidates=self._config.max_candidates,
                        )
                    elif hasattr(self._correction_provider, "correct"):
                        c_word = self._correction_provider.correct(
                            word=norm_result.normalized,
                            sentence=analysis.text,
                            word_start=node.span.char_start,
                            word_end=node.span.char_end,
                        )
                        correction_candidates = [CorrectionCandidate(word=c_word, confidence=0.92)] if c_word else []
                    elif hasattr(self._correction_provider, "get_correction"):
                        corr = self._correction_provider.get_correction(norm_result.normalized)
                        correction_candidates = [CorrectionCandidate(word=corr, confidence=0.92)] if corr else []
                    elif callable(self._correction_provider):
                        corr = self._correction_provider(norm_result.normalized)
                        correction_candidates = [CorrectionCandidate(word=corr, confidence=0.92)] if corr else []
                    else:
                        correction_candidates = []
                else:
                    correction_candidates = []

                top_candidate = correction_candidates[0] if correction_candidates else None

                # ==========================================
                # STAGE 7: EMIT SUGGESTION
                # ==========================================
                yield self._build_spelling_suggestion(
                    node=node,
                    sent_start=sent_start,
                    word=norm_result.normalized,
                    suggestion=top_candidate,
                    candidates=correction_candidates,
                    byte_table=byte_table,
                    sentence_text=analysis.text,
                )

    def _doc_span(
        self,
        sent_start: int,
        char_start: int,
        char_end: int,
        byte_table: list[int],
    ) -> TextSpan:
        return TextSpan(
            char_start=sent_start + char_start,
            char_end=sent_start + char_end,
            byte_start=byte_table[sent_start + char_start],
            byte_end=byte_table[sent_start + char_end],
        )

    def _build_normalization_suggestion(
        self, node: Any, sent_start: int, norm_result: NormalizationResult, byte_table: list[int]
    ) -> Suggestion:
        span = self._doc_span(sent_start, node.span.char_start, node.span.char_end, byte_table)
        return Suggestion(
            source=self._name,
            span=span,
            replacement=norm_result.normalized,
            score=0.95,
            priority=SuggestionPriority.HIGH,
            message=f"[SPELL-NORM-001] Normalization: '{norm_result.original}' -> '{norm_result.normalized}'",
            error_type="NORMALIZATION",
        )

    def _build_structural_suggestion(
        self, node: Any, sent_start: int, syllable: str, s_res: Any, byte_table: list[int]
    ) -> Suggestion:
        span = self._doc_span(sent_start, node.span.char_start, node.span.char_end, byte_table)
        err_type = getattr(s_res.error_type, "value", str(s_res.error_type))
        corrections = getattr(s_res, "suggested_corrections", None) or getattr(s_res, "suggested_correction", None)
        if isinstance(corrections, list) and corrections:
            replacement = corrections[0]
        elif isinstance(corrections, str) and corrections:
            replacement = corrections
        else:
            replacement = None

        return Suggestion(
            source=self._name,
            span=span,
            replacement=replacement,
            score=0.95,
            priority=SuggestionPriority.HIGH,
            message=f"[SPELL-STRUCT-001] Structural Error [{err_type}]: Syllable '{syllable}' violates Tibetan orthography rules",
            error_type="STRUCTURAL",
        )

    def _build_spelling_suggestion(
        self,
        node: Any,
        sent_start: int,
        word: str,
        suggestion: CorrectionCandidate | None,
        candidates: list[CorrectionCandidate],
        byte_table: list[int],
        sentence_text: str,
    ) -> Suggestion:
        span = self._doc_span(sent_start, node.span.char_start, node.span.char_end, byte_table)

        if suggestion:
            confidence = suggestion.confidence
            replacement = suggestion.word
            priority = SuggestionPriority.HIGH if confidence >= 0.80 else SuggestionPriority.MEDIUM
            message = f"[SPELL-DICT-001] Correction available: Unknown word '{word}' — Did you mean '{replacement}'? (confidence: {confidence:.2f})"
        else:
            confidence = 0.85
            replacement = None
            priority = SuggestionPriority.MEDIUM
            message = f"[SPELL-DICT-002] Unknown word: '{word}' — No suggestion available."

        logger.info(
            "spell_checker_suggestion",
            word=word,
            suggestion=replacement,
            confidence=confidence,
            error_type="SPELLING",
            rule_id="SPELL-DICT-001",
            sentence_hash=hash(sentence_text),
            candidates_count=len(candidates),
        )

        return Suggestion(
            source=self._name,
            span=span,
            replacement=replacement,
            score=confidence,
            priority=priority,
            message=message,
            error_type="SPELLING",
        )
