"""Built-in spell checker plugin for TEEA (7-Stage Pipeline).

Flags Tibetan morphemes that are not attested in the corpus-derived
Dictionary Repository as potential misspellings, after normalization,
structural validation, and morphological stem analysis.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.contextual_ranker import ContextualRanker
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

#: Particles that the spell checker never flags (grammatical function words).
_SAFE_PARTICLES: frozenset[str] = frozenset({
    "གི", "ཀྱི", "གྱི", "ཡི", "འི", "གིས", "ཀྱིས", "གྱིས", "ཡིས", "ས", "ལ", "ར",
    "རུ", "ཏུ", "དུ", "ན", "ནས", "ལས", "ནི", "ཀྱང", "ཡང", "འང", "དང", "མི",
    "མེད", "ཡིན", "རེད", "ཡོད", "འདུག",
})

#: Characters stripped from a surface form before dictionary lookup.
_STRIP_CHARS = "་ །\u0f0b\u0f0d "

#: Tibetan base consonants and letters (U+0F40..U+0F6C, includes the rare
#: ཪ/ཫ/ཬ), vowel signs (U+0F71..U+0F85, includes anusvara/visarga-style
#: signs), and subjoined consonants (U+0F90..U+0FBC). A valid replacement
#: word may only contain these letter characters plus tsheg/shad delimiters
#: — never punctuation marks (e.g. ༴ U+0F34, ༽ U+0F3D), digits, or
#: non-Tibetan scripts.
_TIBETAN_LETTER_START = 0x0F40
_TIBETAN_LETTER_END = 0x0F6C
_TIBETAN_VOWEL_START = 0x0F71
_TIBETAN_VOWEL_END = 0x0F85
_TIBETAN_SUBJOINED_START = 0x0F90
_TIBETAN_SUBJOINED_END = 0x0FBC
#: tsheg / shad / nyis shad / tsheg shad — the only non-letter Tibetan
#: characters a replacement may contain.
_TIBETAN_DELIMITERS = frozenset({"\u0f0b", "\u0f0c", "\u0f0d", "\u0f0e", "\u0f0f"})


def _is_tibetan_letter(char: str) -> bool:
    """Return whether ``char`` is a Tibetan letter, vowel sign, or subjoined sign."""
    code = ord(char)
    return (
        _TIBETAN_LETTER_START <= code <= _TIBETAN_LETTER_END
        or _TIBETAN_VOWEL_START <= code <= _TIBETAN_VOWEL_END
        or _TIBETAN_SUBJOINED_START <= code <= _TIBETAN_SUBJOINED_END
    )


def _tibetan_letter_count(text: str) -> int:
    """Count Tibetan letter characters (vowel signs and subjoined signs count).

    Delimiters (tsheg/shad) are excluded so that a missing-tsheg repair
    (e.g. ``སོགས`` -> ``སོ་གས``) does not look like a length change.
    """
    return sum(1 for ch in text if _is_tibetan_letter(ch))


def _is_tibetan_word(text: str) -> bool:
    """Return whether ``text`` contains at least one Tibetan letter."""
    return any(_is_tibetan_letter(ch) for ch in text)


def _contains_only_tibetan(text: str) -> bool:
    """Return whether every non-delimiter character is a Tibetan letter."""
    for ch in text:
        if ch in _TIBETAN_DELIMITERS:
            continue
        if not _is_tibetan_letter(ch):
            return False
    return bool(text)


@dataclass(frozen=True)
class _FallbackMorpheme:
    """Minimal stand-in for :class:`~teea.nlp.postagging.TaggedMorpheme`.

    Produced when the dependency tree is empty so the plugin can still iterate
    a manually tsheg-split sentence. ``category`` is ``None`` because there is
    no POS analysis for a fallback token.
    """

    text: str = ""
    category: Any = None
    span: TextSpan | None = None


@dataclass(frozen=True)
class _FallbackNode:
    """Minimal stand-in for :class:`~teea.nlp.dependency.DependencyNode`.

    Carries only the attributes the spell checker reads (``text``, ``span``,
    ``relation``, ``morpheme``). ``relation`` is ``None`` because a manually
    tokenized sentence carries no dependency information, so the pipeline-
    artifact skip rules simply do not match fallback tokens.
    """

    text: str
    span: TextSpan
    relation: Any = None
    morpheme: _FallbackMorpheme = field(default_factory=_FallbackMorpheme)


def _fallback_nodes(text: str, tokens: list[str]) -> list[_FallbackNode]:
    """Build pseudo-nodes for a manually tsheg-split sentence.

    Used when the dependency tree is empty so the plugin can still check each
    morpheme instead of skipping the sentence entirely.

    Args:
        text: The sentence text being tokenized.
        tokens: Non-empty tsheg-delimited tokens of ``text``, in surface order.

    Returns:
        One pseudo-node per token, with sentence-relative character and byte
        spans. Tokens containing no word characters (e.g. a lone shad) are
        skipped because they carry no spelling signal.
    """
    nodes: list[_FallbackNode] = []
    cursor = 0
    for token in tokens:
        if not any(ch.isalnum() for ch in token):
            continue
        start = text.find(token, cursor)
        if start < 0:
            continue
        end = start + len(token)
        cursor = end
        nodes.append(
            _FallbackNode(
                text=token,
                span=TextSpan(
                    char_start=start,
                    char_end=end,
                    byte_start=len(text[:start].encode("utf-8")),
                    byte_end=len(text[:end].encode("utf-8")),
                ),
            )
        )
    return nodes


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
    min_confidence_for_suggestion: float = 0.70
    max_candidates: int = 10

    # Context-based detection (§3)
    # Calibrated against real corpus data: a known word is flagged only when
    # its context makes it at least ``context_suspicious_gap`` natural-log
    # units less likely than its unigram baseline predicts, and an *edit* is
    # only attached when the correction provider's candidate clears
    # ``context_min_confidence`` (below that bar the suggestion is
    # advisory-only). With the gap at 5.0 the hook catches particle omissions
    # and vowel mutations while keeping false positives low (the earlier
    # uncalibrated 2.5-gap run collapsed specificity to ~15%, e.g. པ -> པ༴,
    # མཚོན -> མཚན).
    enable_context_detection: bool = True
    context_suspicious_gap: float = 5.0
    # Minimum confidence for a context-based suggestion to carry an edit;
    # candidates below this bar yield an advisory instead.
    context_min_confidence: float = 0.75

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

        self._contextual_ranker: ContextualRanker | None = None
        if corpus_repository is not None and self._config.enable_context_detection:
            try:
                self._contextual_ranker = ContextualRanker(
                    corpus_repository,
                    suspicious_gap=self._config.context_suspicious_gap,
                )
            except Exception as exc:  # noqa: BLE001 - a failing ranker must not break the plugin
                logger.warning(
                    "contextual_ranker_unavailable",
                    error=str(exc),
                    fallback_used=True,
                )
                self._contextual_ranker = None

        if correction_provider is not None:
            self._correction_provider = correction_provider
        elif self._config.enable_tibert_reranking and self._ai_runtime is not None:
            self._correction_provider = TibertCorrectionProvider(
                self._dictionary,
                ai_runtime=self._ai_runtime,
                max_edit_distance=self._config.max_edit_distance,
            )
        else:
            self._correction_provider = DictionaryOnlyCorrectionProvider(
                self._dictionary, max_edit_distance=self._config.max_edit_distance
            )

        self._lookup_cache: dict[str, bool] = {}

    @property
    def name(self) -> str:
        """The plugin's registered name (``teea.spelling``)."""
        return self._name

    @property
    def config(self) -> SpellCheckerConfig:
        """The active plugin configuration."""
        return self._config

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        """Spell-check every morpheme in ``snapshot`` and yield suggestions."""
        byte_table = utf8_byte_offsets(snapshot.source)

        for analysis in snapshot.analyses:
            tree = analysis.tree
            sent_start = analysis.span.char_start

            all_safe_particles = _SAFE_PARTICLES

            if tree.is_empty:
                # The dependency parser produced no nodes for this sentence
                # (e.g. malformed tsheg segmentation), so fall back to a manual
                # tsheg tokenization and spell-check each morpheme individually
                # instead of skipping the sentence entirely.
                tokens = [token for token in analysis.text.split("\u0f0b") if token.strip()]
                nodes: Iterable[Any] = _fallback_nodes(analysis.text, tokens)
            else:
                nodes = tree.nodes

            for node in nodes:
                # Skip punctuation
                if node.relation == DependencyRelation.PUNCT:
                    continue

                raw_word = node.text.strip("། ཿ")
                if not raw_word:
                    continue

                # Skip pipeline artifacts (ASCII dummy nodes or recognized safe particles)
                if node.relation in (
                    DependencyRelation.CASE,
                    DependencyRelation.AUX,
                    DependencyRelation.MARK,
                    DependencyRelation.NEG,
                ) and (raw_word.isascii() or raw_word.strip("་ ") in all_safe_particles):
                    continue
                # Skip mixed Latin/Tibetan transliterated tokens (containing both
                # Tibetan and Latin characters)
                has_tibetan = any('\u0f00' <= c <= '\u0fda' for c in raw_word)
                has_latin = any('a' <= c.lower() <= 'z' for c in raw_word)
                if has_tibetan and has_latin:
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
                clean_target = norm_result.normalized.strip(_STRIP_CHARS)
                vocab_set = getattr(self._dictionary, "vocabulary", ())
                if clean_target in all_safe_particles or clean_target in vocab_set:
                    yield from self._context_suggestions(
                        node, sent_start, norm_result.normalized, byte_table, analysis.text
                    )
                    continue
                if (
                    node.text in self._dictionary
                    or raw_word in self._dictionary
                    or norm_result.normalized in self._dictionary
                ):
                    yield from self._context_suggestions(
                        node, sent_start, norm_result.normalized, byte_table, analysis.text
                    )
                    continue
                if (
                    hasattr(self._dictionary, "is_valid_word_or_compound")
                    and self._dictionary.is_valid_word_or_compound(norm_result.normalized)
                ):
                    yield from self._context_suggestions(
                        node, sent_start, norm_result.normalized, byte_table, analysis.text
                    )
                    continue

                valid_candidates: list[StemCandidate] = []
                for candidate in stem_candidates:
                    cache_key = candidate.stem
                    if self._config.enable_caching and cache_key in self._lookup_cache:
                        exists = self._lookup_cache[cache_key]
                    else:
                        exists = candidate.stem in self._dictionary
                        if (
                            self._config.enable_caching
                            and len(self._lookup_cache) < self._config.cache_size
                        ):
                            self._lookup_cache[cache_key] = exists

                    if exists:
                        valid_candidates.append(candidate)

                # If ANY valid candidate exists, word is correctly spelled
                if valid_candidates:
                    yield from self._context_suggestions(
                        node, sent_start, norm_result.normalized, byte_table, analysis.text
                    )
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
                        correction_candidates = (
                            [CorrectionCandidate(word=c_word, confidence=0.92)] if c_word else []
                        )
                    elif hasattr(self._correction_provider, "get_correction"):
                        corr = self._correction_provider.get_correction(norm_result.normalized)
                        correction_candidates = (
                            [CorrectionCandidate(word=corr, confidence=0.92)] if corr else []
                        )
                    elif callable(self._correction_provider):
                        corr = self._correction_provider(norm_result.normalized)
                        correction_candidates = (
                            [CorrectionCandidate(word=corr, confidence=0.92)] if corr else []
                        )
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

    def _context_suggestions(
        self,
        node: Any,
        sent_start: int,
        word: str,
        byte_table: list[int],
        sentence_text: str,
    ) -> tuple[Suggestion, ...]:
        """Flag a dictionary-known word that appears in an implausible context.

        This is the Stage-4B context-detection hook (data-driven §3): it only
        fires when a contextual ranker is configured, the word is a known
        surface form (the caller has already passed dictionary lookup) and not
        a safe particle, and the ranker judges the word's context implausible.

        When the correction provider proposes a confident candidate it is
        attached as a replacement (an edit); otherwise the suggestion is an
        advisory.  Either way the priority is LOW so it never outranks a
        confident rule-based correction.

        Args:
            node: The dependency node whose word was accepted as known.
            sent_start: Document offset of the sentence start.
            word: The normalised surface form (known to the dictionary).
            byte_table: UTF-8 byte offset table for the document.
            sentence_text: The sentence containing the word.

        Returns:
            Zero or one context suggestion.
        """
        if self._contextual_ranker is None:
            return ()
        if word.strip(_STRIP_CHARS) in _SAFE_PARTICLES:
            return ()
        char_start = node.span.char_start
        char_end = node.span.char_end
        if not self._contextual_ranker.is_suspicious(sentence_text, char_start, char_end):
            return ()
        span = self._doc_span(sent_start, char_start, char_end, byte_table)
        replacement, _provider_confidence = self._candidate_for(node, word, sentence_text)
        # Context edits are gated by ``context_min_confidence``: a low-confidence
        # candidate is never applied, it degrades to an advisory.  The
        # confidence is recalibrated as how much more plausible the candidate
        # is *in this context* than the known word itself (see
        # :meth:`_context_candidate_confidence`), because the provider's raw
        # model score is compressed and rarely clears the bar by itself.
        if replacement is not None:
            confidence = self._context_candidate_confidence(
                sentence_text, word, char_start, char_end, replacement
            )
        else:
            confidence = 0.0
        if confidence < self._config.context_min_confidence:
            replacement = None
        else:
            replacement = self._guard_replacement(word, replacement, confidence)
        if replacement is not None:
            return (
                Suggestion(
                    source=self._name,
                    span=span,
                    replacement=replacement,
                    score=round(min(1.0, confidence * 0.8), 3),
                    priority=SuggestionPriority.LOW,
                    message=(
                        f"[SPELL-CTX-001] Known word '{word}' appears in an "
                        f"implausible context — did you mean '{replacement}'?"
                    ),
                    error_type="CONTEXT",
                ),
            )
        return (
            Suggestion(
                source=self._name,
                span=span,
                replacement=None,
                score=0.5,
                priority=SuggestionPriority.LOW,
                message=f"[SPELL-CTX-002] Known word '{word}' appears in an implausible context.",
                error_type="CONTEXT",
            ),
        )

    def _context_candidate_confidence(
        self,
        sentence_text: str,
        word: str,
        char_start: int,
        char_end: int,
        candidate: str,
    ) -> float:
        """Confidence that ``candidate`` is the right fix for the known word.

        Computed as how much more plausible the candidate is in context than
        the word itself, measured in natural-log units (the contextual ranker's
        mean PLL) and mapped to ``[0, 1]`` via ``0.5 + delta / 10``.  A
        candidate roughly ``e^2.5`` (≈12x) more plausible than the attested
        word clears the ``context_min_confidence`` bar of 0.75.

        When the improvement cannot be measured (no usable context, or the
        ranker fails) ``0.0`` is returned so the hook never fabricates an edit.

        Args:
            sentence_text: The sentence containing the word.
            word: The known surface form being questioned.
            char_start: Sentence-relative offset of the word's start.
            char_end: Sentence-relative offset of the word's end.
            candidate: The proposed replacement.

        Returns:
            The recalibrated confidence in ``[0, 1]``.
        """
        ranker = self._contextual_ranker
        if ranker is None:
            return 0.0
        try:
            candidate_pll = ranker.pll(sentence_text, char_start, char_end, candidate)
            word_pll = ranker.pll(sentence_text, char_start, char_end, word)
        except Exception:  # noqa: BLE001 - a failing ranker must not crash the plugin
            logger.warning("context_candidate_confidence_failed", word=word)
            return 0.0
        if candidate_pll == 0.0 or word_pll == 0.0:
            return 0.0
        delta = candidate_pll - word_pll
        return min(1.0, max(0.0, 0.5 + delta / 10.0))

    def _candidate_for(
        self, node: Any, word: str, sentence_text: str
    ) -> tuple[str | None, float]:
        """Return the correction provider's best candidate for ``word``.

        Mirrors the provider dispatch used in Stage 5 so the context hook and
        the unknown-word path share one protocol.

        Args:
            node: The dependency node (for sentence-relative word offsets).
            word: The surface form to correct.
            sentence_text: The sentence containing the word.

        Returns:
            ``(replacement, confidence)``; ``(None, 0.0)`` when no candidate
            is available or the provider fails (which must never crash the
            plugin).
        """
        provider = self._correction_provider
        if provider is None:
            return None, 0.0
        try:
            # Prefer a provider that reports the model-backed confidence so the
            # context hook's confidence gate is meaningful (score-fusion fix:
            # the raw model score decides, not a hardcoded heuristic).
            if hasattr(provider, "correct_with_score"):
                corrected, confidence = provider.correct_with_score(
                    word=word,
                    sentence=sentence_text,
                    word_start=node.span.char_start,
                    word_end=node.span.char_end,
                )
                if corrected:
                    return corrected, float(confidence)
            if hasattr(provider, "generate_candidates"):
                candidates = provider.generate_candidates(
                    word=word,
                    sentence=sentence_text,
                    max_candidates=self._config.max_candidates,
                )
                if candidates:
                    top = candidates[0]
                    return top.word, float(top.confidence)
            elif hasattr(provider, "correct"):
                corrected = provider.correct(
                    word=word,
                    sentence=sentence_text,
                    word_start=node.span.char_start,
                    word_end=node.span.char_end,
                )
                if corrected:
                    return corrected, 0.92
            elif hasattr(provider, "get_correction"):
                corrected = provider.get_correction(word)
                if corrected:
                    return corrected, 0.92
            elif callable(provider):
                corrected = provider(word)
                if corrected:
                    return corrected, 0.92
        except Exception:  # noqa: BLE001 - a failing provider must not break the plugin
            logger.warning("context_candidate_generation_failed", word=word)
        return None, 0.0

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
            message=(
                f"[SPELL-NORM-001] Normalization: '{norm_result.original}' -> "
                f"'{norm_result.normalized}'"
            ),
            error_type="NORMALIZATION",
        )

    def _build_structural_suggestion(
        self, node: Any, sent_start: int, syllable: str, s_res: Any, byte_table: list[int]
    ) -> Suggestion:
        span = self._doc_span(sent_start, node.span.char_start, node.span.char_end, byte_table)
        err_type = getattr(s_res.error_type, "value", str(s_res.error_type))
        corrections = (
            getattr(s_res, "suggested_corrections", None)
            or getattr(s_res, "suggested_correction", None)
        )
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
            message=(
                f"[SPELL-STRUCT-001] Structural Error [{err_type}]: Syllable "
                f"'{syllable}' violates Tibetan orthography rules"
            ),
            error_type="STRUCTURAL",
        )

    def _syllables_attested(self, text: str, vocab: Any) -> bool:
        """Return whether every tsheg-delimited syllable of ``text`` is attested.

        Used as the granularity-adapted validity fallback for synthesized
        multi-syllable candidates whose joined form is not itself a vocabulary
        key (e.g. ``བཀྲཤིས`` -> ``བཀྲ་ཤིས``).  A syllable passes when either
        its bare or its tsheg-terminated form appears in ``vocab`` (the
        repository stores forms both ways).

        Args:
            text: The tsheg-stripped replacement candidate.
            vocab: The dictionary's vocabulary surface (an iterable of forms).

        Returns:
            ``True`` when every non-empty syllable is attested and there is at
            least one syllable.
        """
        syllables = [s for s in text.split("\u0f0b") if s.strip(_STRIP_CHARS)]
        if not syllables:
            return False
        for syllable in syllables:
            clean = syllable.strip(_STRIP_CHARS)
            if clean not in vocab and clean + "\u0f0b" not in vocab:
                return False
        return True

    def _guard_replacement(
        self, word: str, replacement: str | None, confidence: float
    ) -> str | None:
        """Apply safety guardrails to a proposed replacement.

        Returns ``None`` when the replacement must be withheld (the suggestion
        is then emitted advisory-only, so the engine never applies a harmful
        edit), otherwise the unchanged replacement.

        Guardrails:
        1. Confidence — the replacement is only offered when the candidate
           confidence clears ``min_confidence_for_suggestion``.
        2. Validity — the replacement must be an attested dictionary word when
           the dictionary exposes a vocabulary surface, and must contain only
           Tibetan letters plus tsheg/shad delimiters (no punctuation marks,
           digits, or non-Tibetan scripts).
        3. Length limit — replacements that add more than two letters or change
           the letter count by more than 20% relative to the source word are
           rejected (e.g. ང -> ངན, མཚོན -> མཚན).  Delimiters (tsheg/shad)
           are excluded from the count so a missing-tsheg repair
           (སོགས -> སོ་གས) is not treated as a length change.
        4. Structure — every syllable of the replacement must pass the
           structural validator (no illegal stacks or missing-tsheg garbage).

        Args:
            word: The surface form being corrected.
            replacement: The proposed replacement, or ``None``.
            confidence: The candidate's confidence in ``[0, 1]``.

        Returns:
            The replacement when it passes every guardrail, else ``None``.
        """
        if replacement is None:
            return None
        if confidence < self._config.min_confidence_for_suggestion:
            return None

        # 2a. Dictionary attestation — only when the dictionary exposes a
        # vocabulary surface (test doubles without one skip this check).
        vocab = getattr(self._dictionary, "vocabulary", None)
        if vocab:
            clean_replacement = replacement.strip(_STRIP_CHARS)
            if clean_replacement not in vocab and replacement not in vocab:
                # The provider also synthesises multi-syllable corrections
                # (e.g. བཀྲཤིས -> བཀྲ་ཤིས) whose joined form is not itself a
                # vocabulary key.  Accept those when every tsheg-delimited
                # syllable is individually attested — still a strict validity
                # gate, just at syllable granularity.
                if not self._syllables_attested(clean_replacement, vocab):
                    return None

        # 2b. Tibetan-only script: no punctuation marks (e.g. ༴, ༽), digits,
        # or non-Tibetan scripts may be injected into Tibetan text.
        if _is_tibetan_word(word) and not _contains_only_tibetan(replacement):
            return None

        # 3. Length limit (letter count, delimiters excluded).
        word_letters = _tibetan_letter_count(word)
        repl_letters = _tibetan_letter_count(replacement)
        if word_letters > 0:
            if repl_letters - word_letters > 2:
                return None
            if abs(repl_letters - word_letters) / word_letters > 0.20:
                return None

        # 4. Structural validity of each tsheg-delimited syllable.
        for syllable in replacement.split("\u0f0b"):
            syllable = syllable.strip(_STRIP_CHARS)
            if not syllable:
                continue
            if not self._validator.validate_syllable(syllable).is_valid:
                return None

        return replacement

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

        candidate_confidence = suggestion.confidence if suggestion else None
        if suggestion:
            replacement = self._guard_replacement(word, suggestion.word, suggestion.confidence)
            if replacement is not None:
                confidence = suggestion.confidence
                priority = SuggestionPriority.HIGH if confidence >= 0.80 else SuggestionPriority.MEDIUM
                message = (
                    f"[SPELL-DICT-001] Correction available: Unknown word '{word}' — "
                    f"Did you mean '{replacement}'? (confidence: {confidence:.2f})"
                )
            else:
                confidence = 0.85
                priority = SuggestionPriority.MEDIUM
                message = (
                    f"[SPELL-DICT-003] Unknown word: '{word}' — candidate rejected "
                    f"by safety guardrails, no edit applied."
                )
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
            candidate_confidence=candidate_confidence,
            rejected=(suggestion is not None and replacement is None),
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
