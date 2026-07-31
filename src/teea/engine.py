"""Public facade API for the TEEA Core AI Engine.

Provides a single, model-agnostic entry point (:class:`TEEAEngine`) that encapsulates
the 12-stage Tibetan NLP pipeline, TiBERT neural candidate ranking, spell checking,
grammar checking, candidate generation, dictionary management, and suggestion fusion.

This facade enables the Core Engine to be run, tested, and embedded in any frontend
(FastAPI local service, browser test UI, Word add-in, VS Code, Google Docs, desktop apps)
without modifying underlying engine components.
"""

from __future__ import annotations

import time
from typing import Any

from teea import __version__
from teea.ai import LocalAIRuntime
from teea.ai.interfaces import InferenceEngine
from teea.ai.models import CapabilityKind, InferenceRequest, ModelDescriptor
from teea.ai.tibert_engine import TiBERTInferenceEngine
from teea.core.config import TEEASettings, load_settings
from teea.core.logging import get_logger
from teea.fusion import PriorityRankedFusionEngine, UnifiedSuggestions
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.persistence import DictionaryRepository, default_dictionary
from teea.plagiarism import PlagiarismEngine
from teea.plugins import SupervisedPluginRuntime
from teea.plugins.builtin import (
    DocumentDiagnosticsPlugin,
    GrammarCheckerPlugin,
    PlagiarismDetectorPlugin,
    SpellCheckerPlugin,
    TypographyPlugin,
)
from teea.plugins.builtin.correction import CorrectionProvider
from teea.plugins.interfaces import FeaturePlugin

_logger = get_logger(__name__)


class TEEAEngine:
    """Unified entry point for the TEEA Core NLP & AI Engine.

    Args:
        settings: Optional TEEASettings override.
        ai_engine: Optional AI inference engine instance (defaults to TiBERTInferenceEngine).
        dictionary: Optional DictionaryRepository instance.
        plugins: Optional custom list of feature plugins.
    """

    def __init__(
        self,
        *,
        settings: TEEASettings | None = None,
        ai_engine: InferenceEngine | None = None,
        dictionary: DictionaryRepository | None = None,
        plugins: list[FeaturePlugin] | None = None,
    ) -> None:
        self._settings = settings or load_settings()
        self._builder = LanguageServerSnapshotBuilder()
        self._fusion = PriorityRankedFusionEngine()
        self._dict_repo = dictionary or default_dictionary()

        # Wire BoCorpusRepository if processed dataset is available
        from teea.corpus.repository import BoCorpusRepository
        corpus_repo = BoCorpusRepository()
        self._corpus_repo = corpus_repo if corpus_repo.is_available() else None

        # Combine vocabularies if corpus repository is available
        combined_vocab: set[str] = set(self._dict_repo.vocabulary)
        if self._corpus_repo is not None:
            combined_vocab.update(self._corpus_repo.vocabulary.keys())

        # Initialize AI Runtime with local TiBERT checkpoint detection if available
        from pathlib import Path
        tibert_dir = Path("TiBERT")
        local_path = tibert_dir if (tibert_dir.exists() and (tibert_dir / "model.safetensors").exists()) else None

        engine_instance = ai_engine or TiBERTInferenceEngine(local_path=local_path)
        self._ai_runtime = LocalAIRuntime(engine_instance)

        # Register and start TiBERT descriptor
        tibert_descriptor = ModelDescriptor(
            name="tibert",
            version="1.0",
            provides=frozenset({CapabilityKind.SPELLING}),
        )
        self._ai_runtime.register(tibert_descriptor)
        self._ai_runtime.start()

        # Warmup TiBERT inference engine on startup if loaded
        try:
            warmup_req = InferenceRequest(
                capability=CapabilityKind.SPELLING,
                inputs={
                    "sentence": "བཀྲ་ཤིས་བདེ་ལེགས།",
                    "word_start": 0,
                    "word_end": 4,
                    "candidates": ["བཀྲ་ཤིས", "བཀྲིས་"],
                },
            )
            self._ai_runtime.infer(warmup_req)
        except Exception:  # noqa: BLE001 - optional warmup when torch is uninstalled or mock backend
            pass

        # Create candidate scoring function backed by TiBERT
        def _score_candidates(
            sentence: str, word_start: int, word_end: int, candidates: list[str]
        ) -> dict[str, float]:
            req = InferenceRequest(
                capability=CapabilityKind.SPELLING,
                inputs={
                    "sentence": sentence,
                    "word_start": word_start,
                    "word_end": word_end,
                    "candidates": candidates,
                },
            )
            res = self._ai_runtime.infer(req)
            scores = res.outputs.get("scores")
            if isinstance(scores, list) and scores:
                return {cand: float(scores[i]) if i < len(scores) else 0.5 for i, cand in enumerate(candidates)}
            if isinstance(scores, dict) and scores:
                return scores
            return {cand: 0.5 for cand in candidates}

        # Build correction provider with combined vocabulary and corpus repository
        self._correction_provider = CorrectionProvider(
            score_candidates=_score_candidates,
            vocabulary=combined_vocab,
            confidence_threshold=0.0,
            corpus_repository=self._corpus_repo,
        )

        # Configure Plugins
        if plugins is not None:
            self._plugins = plugins
        else:
            spell_checker = SpellCheckerPlugin(
                dictionary=self._dict_repo,
                correction_provider=self._correction_provider,
                corpus_repository=self._corpus_repo,
            )
            grammar_checker = GrammarCheckerPlugin()
            typography_plugin = TypographyPlugin()
            diagnostics = DocumentDiagnosticsPlugin()
            plagiarism_engine = PlagiarismEngine(settings=self._settings.plagiarism)
            self._plagiarism_engine = plagiarism_engine
            plagiarism_plugin = PlagiarismDetectorPlugin(engine=plagiarism_engine)
            self._plugins = [diagnostics, typography_plugin, grammar_checker, spell_checker, plagiarism_plugin]

        self._plugin_runtime = SupervisedPluginRuntime(self._plugins)

    @property
    def plagiarism_engine(self) -> PlagiarismEngine | None:
        """The active plagiarism engine instance."""
        return getattr(self, "_plagiarism_engine", None)

    @property
    def version(self) -> str:
        """Engine version string."""
        return __version__

    @property
    def dictionary(self) -> DictionaryRepository:
        """The active dictionary repository."""
        return self._dict_repo

    def analyze(self, text: str) -> UnifiedSuggestions:
        """Run the complete 12-stage NLP analysis, plugin collection, and fusion ranking.

        Args:
            text: Tibetan input text to analyze.

        Returns:
            A :class:`UnifiedSuggestions` containing priority-ranked, deduplicated suggestions.
        """
        start_time = time.perf_counter()
        if not text:
            snapshot = self._builder.analyze("")
            return self._fusion.fuse(snapshot.source, [])

        snapshot = self._builder.analyze(text)
        results = self._plugin_runtime.dispatch(snapshot)
        unified = self._fusion.fuse(snapshot.source, results.suggestions)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        _logger.info(
            "analysis_completed",
            char_count=len(text),
            suggestions=len(unified),
            elapsed_ms=round(elapsed_ms, 2),
        )
        return unified

    def rewrite(self, text: str, template: str = "formal") -> str:
        """Perform AI-assisted text rewriting or polishing.

        Args:
            text: Input Tibetan text.
            template: Rewrite style template (e.g. 'formal', 'simplified', 'honorific').

        Returns:
            Rewritten Tibetan text string.
        """
        if not text.strip():
            return text
        # Future AI generative integration hook
        return text

    def health(self) -> dict[str, Any]:
        """Return engine operational status."""
        return {
            "status": "ok",
            "version": __version__,
            "ai_active": self._ai_runtime is not None,
            "vocabulary_size": self._dict_repo.vocabulary_size,
            "plugins_loaded": [p.name for p in self._plugins],
        }

    def diagnose(self) -> dict[str, Any]:
        """Return comprehensive telemetry and configuration diagnostics."""
        return {
            "version": __version__,
            "settings": self._settings.model_dump(),
            "dictionary_size": self._dict_repo.vocabulary_size,
            "plugins": {
                "count": len(self._plugins),
                "names": [p.name for p in self._plugins],
            },
            "ai_runtime": {
                "active": self._ai_runtime is not None,
                "capabilities": (
                    [c.value for c in self._ai_runtime.health().capabilities]
                    if self._ai_runtime
                    else []
                ),
            },
        }


__all__ = ["TEEAEngine"]
