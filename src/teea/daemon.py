"""TEEA Daemon composition root.

Wires together the NLP pipeline, plugin runtime, fusion engine, AI runtime,
and IPC server into a single ``TEEADaemon`` component.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from concurrent.futures import Executor
from pathlib import Path
from typing import Any

from teea import __version__
from teea.ai import LocalAIRuntime
from teea.ai.interfaces import InferenceEngine
from teea.core.config import TEEASettings, load_settings
from teea.core.logging import configure_logging, get_logger
from teea.fusion import PriorityRankedFusionEngine, Suggestion
from teea.ipc import IpcServer
from teea.ipc.interfaces import Transport
from teea.ipc.models import Session
from teea.nlp.snapshot import DocumentSnapshot, LanguageServerSnapshotBuilder
from teea.plagiarism import PlagiarismEngine
from teea.plugins import SupervisedPluginRuntime
from teea.plugins.builtin import (
    DocumentDiagnosticsPlugin,
    GrammarCheckerPlugin,
    PlagiarismDetectorPlugin,
    SpellCheckerPlugin,
)
from teea.plugins.interfaces import FeaturePlugin

_logger = get_logger(__name__)


class TEEADaemon:
    """Composition root for the TEEA application.

    Wires all components together: the NLP pipeline, plugin runtime, fusion
    engine, AI runtime, and IPC server. Provides a single entry point for
    launching and shutting down the daemon.

    Args:
        settings: Application settings. Loaded from environment/defaults if None.
        builder: The Language Server snapshot builder.
        plugins: Feature plugins to run.
        plugin_executor: Executor for concurrent plugin dispatch.
        fusion_engine: The suggestion fusion engine.
        ai_engine: The AI inference engine (optional).
        plagiarism_engine: The plagiarism detection engine (optional).
        transport: IPC transport (optional).
        db_path: Path to the SQLite database file for persistent storage.
            When provided, the daemon uses SQLite-backed repositories
            instead of in-memory stores.  ``None`` (the default) keeps
            the existing in-memory behaviour.
    """

    def __init__(
        self,
        *,
        settings: TEEASettings | None = None,
        builder: LanguageServerSnapshotBuilder | None = None,
        plugins: list[FeaturePlugin] | None = None,
        plugin_executor: Executor | None = None,
        fusion_engine: PriorityRankedFusionEngine | None = None,
        ai_engine: InferenceEngine | None = None,
        plagiarism_engine: PlagiarismEngine | None = None,
        transport: Transport | None = None,
        db_path: Path | str | None = None,
    ) -> None:
        self._settings = load_settings() if settings is None else settings
        configure_logging(level=self._settings.log_level, json_output=self._settings.log_json)

        _logger.info("daemon_initializing", version=_version())

        self._builder = builder or LanguageServerSnapshotBuilder()
        self._fusion = fusion_engine or PriorityRankedFusionEngine()
        self._ai_runtime = LocalAIRuntime(ai_engine) if ai_engine else None

        # Use SQLite-backed persistence when a db_path is provided.
        self._db_manager: Any = None
        if db_path is not None:
            from teea.persistence import DatabaseManager, populate_all  # noqa: PLC0415

            self._db_manager = DatabaseManager(Path(db_path))
            populate_all(self._db_manager)

        if plagiarism_engine is not None:
            self._plagiarism = plagiarism_engine
        elif self._db_manager is not None:
            # Wire plagiarism engine with SQLite-backed fingerprint storage
            from teea.persistence import SqliteFingerprintRepository  # noqa: PLC0415
            from teea.plagiarism.index import InMemoryFingerprintIndex  # noqa: PLC0415

            fp_repo = SqliteFingerprintRepository(self._db_manager)
            # Pre-load existing fingerprints from SQLite into the in-memory index
            index = InMemoryFingerprintIndex()
            for doc in fp_repo.all():
                index.add(doc)
            self._plagiarism = PlagiarismEngine(
                index=index,
                settings=self._settings.plagiarism,
            )
        else:
            self._plagiarism = PlagiarismEngine(
                settings=self._settings.plagiarism,
            )

        self._server = IpcServer()

        # Build plugin runtime (after plagiarism engine is available for default plugins)
        if plugins is not None:
            plugin_list = plugins
        else:
            spell_checker = SpellCheckerPlugin()
            if self._ai_runtime is not None:
                from teea.ai.models import CapabilityKind, InferenceRequest, ModelDescriptor
                from teea.persistence import default_dictionary
                from teea.plugins.builtin.correction import CorrectionProvider

                tibert_descriptor = ModelDescriptor(
                    name="tibert", version="1", provides=frozenset({CapabilityKind.SPELLING})
                )
                self._ai_runtime.register(tibert_descriptor)

                def _score_candidates(sentence: str, ws: int, we: int, cands: list[str]) -> list[float]:
                    req = InferenceRequest(
                        capability=CapabilityKind.SPELLING,
                        inputs={"sentence": sentence, "word_start": ws, "word_end": we, "candidates": cands},
                    )
                    res = self._ai_runtime.infer(req)
                    return res.outputs["scores"]

                provider = CorrectionProvider(
                    score_candidates=_score_candidates,
                    vocabulary=default_dictionary().vocabulary,
                    confidence_threshold=0.0,
                )
                spell_checker = SpellCheckerPlugin(correction_provider=provider)

            plugin_list = [
                DocumentDiagnosticsPlugin(),
                GrammarCheckerPlugin(),
                spell_checker,
                PlagiarismDetectorPlugin(self._plagiarism),
            ]
        self._plugins = SupervisedPluginRuntime(
            plugins=plugin_list,
            executor=plugin_executor,
        )

        self._register_handlers()

        self._transport = transport
        self._shutdown_event = threading.Event()

    def _register_handlers(self) -> None:
        class AnalyzeHandler:
            def __init__(self, builder: LanguageServerSnapshotBuilder) -> None:
                self._builder = builder

            def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
                text = params.get("text", "")
                if not isinstance(text, str):
                    return {"error": "text must be a string"}
                snapshot = self._builder.analyze(text)
                return snapshot.model_dump(mode="json")

        class PluginHandler:
            def __init__(self, plugins: SupervisedPluginRuntime) -> None:
                self._plugins = plugins

            def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
                data = params.get("snapshot")
                if data is None:
                    return {"error": "snapshot is required"}
                snapshot = DocumentSnapshot.model_validate(data)
                results = self._plugins.dispatch(snapshot)
                return results.model_dump(mode="json")

        class FusionHandler:
            def __init__(self, engine: PriorityRankedFusionEngine) -> None:
                self._engine = engine

            def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
                source = params.get("source", "")
                suggestions_data = params.get("suggestions", [])
                suggestions = [Suggestion.model_validate(s) for s in suggestions_data]
                result = self._engine.fuse(source, suggestions)
                return result.model_dump(mode="json")

        class PlagiarismHandler:
            def __init__(self, engine: PlagiarismEngine) -> None:
                self._engine = engine

            def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
                text = params.get("text", "")
                if not isinstance(text, str):
                    return {"error": "text must be a string"}
                threshold = params.get("min_similarity")
                kwargs = {}
                if threshold is not None:
                    kwargs["min_similarity"] = float(threshold)
                result = self._engine.detect(text, **kwargs)
                return result.model_dump(mode="json")

        self._server.register("analyze", AnalyzeHandler(self._builder))
        self._server.register("plugins", PluginHandler(self._plugins))
        self._server.register("fuse", FusionHandler(self._fusion))
        self._server.register("plagiarism", PlagiarismHandler(self._plagiarism))

    @property
    def settings(self) -> TEEASettings:
        """Application settings."""
        return self._settings

    @property
    def builder(self) -> LanguageServerSnapshotBuilder:
        """The NLP pipeline snapshot builder."""
        return self._builder

    @property
    def plugins(self) -> SupervisedPluginRuntime:
        """The supervised plugin runtime."""
        return self._plugins

    @property
    def fusion(self) -> PriorityRankedFusionEngine:
        """The suggestion fusion engine."""
        return self._fusion

    @property
    def ai_runtime(self) -> LocalAIRuntime | None:
        """The AI inference runtime, or None if not configured."""
        return self._ai_runtime

    @property
    def plagiarism(self) -> PlagiarismEngine:
        """The plagiarism detection engine."""
        return self._plagiarism

    def is_serving(self) -> bool:
        """Whether the IPC server is bound to a transport and serving."""
        return self._server.is_serving

    def start(self) -> None:
        """Start AI runtime and IPC server if configured."""
        if self._ai_runtime is not None:
            self._ai_runtime.start()
            _logger.info("ai_runtime_started")

        if self._transport is not None:
            self._server.serve(self._transport)
            _logger.info("daemon_serving", transport=type(self._transport).__name__)

        _logger.info("daemon_started")

    def stop(self) -> None:
        """Stop IPC server and AI runtime gracefully."""
        _logger.info("daemon_stopping")
        self._server.stop()
        if self._ai_runtime is not None:
            self._ai_runtime.stop()
        _logger.info("daemon_stopped")

    def wait_for_shutdown(self) -> None:
        """Block until a shutdown signal is received."""
        self._shutdown_event.wait()

    def shutdown(self) -> None:
        """Trigger a graceful shutdown."""
        self.stop()
        self._shutdown_event.set()

    def diagnose(self) -> dict[str, Any]:
        """Return a diagnostic snapshot of the daemon's state."""
        return {
            "version": _version(),
            "settings": self._settings.model_dump(mode="json"),
            "builder": {
                "type": type(self._builder).__name__,
            },
            "plugins": {
                "count": len(self._plugins.plugins),
                "names": list(self._plugins.plugins),
                "concurrent": self._plugins.is_concurrent,
            },
            "fusion": {
                "type": type(self._fusion).__name__,
                "merge_adjacent": self._fusion.merge_adjacent,
            },
            "ai_runtime": {
                "active": self._ai_runtime is not None,
                "capabilities": (
                    [c.value for c in self._ai_runtime.health().capabilities]
                    if self._ai_runtime
                    else []
                ),
            },
            "plagiarism": {
                "corpus_size": self._plagiarism.index.size,
                "total_fingerprints": self._plagiarism.index.total_fingerprints,
            },
            "ipc": {
                "serving": self._server.is_serving,
                "methods": (
                    [m.model_dump(mode="json") for m in self._server.methods]
                    if self._server.is_serving
                    else []
                ),
            },
        }


def _version() -> str:
    return __version__


def create_daemon(settings: TEEASettings | None = None) -> TEEADaemon:
    """Factory function to create a fully wired daemon with defaults.

    Args:
        settings: Optional settings override.

    Returns:
        A ready-to-use daemon instance.
    """
    from teea.ai.tibert_engine import TiBERTInferenceEngine
    return TEEADaemon(settings=settings, ai_engine=TiBERTInferenceEngine())


__all__ = ["TEEADaemon", "create_daemon"]
