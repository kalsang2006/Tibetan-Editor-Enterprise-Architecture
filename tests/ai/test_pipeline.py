"""Integration tests: the AI Runtime composing with the layers around it.

Figure 6's Request Sources are feature plugins, and its Outputs feed back to
them. So the AI Runtime is exercised the way the architecture uses it: a plugin
holds a runtime, calls it while examining a snapshot the Language Server built,
turns the inference outputs into suggestions, and the Plugin Runtime supervises
the whole thing before the Fusion Engine merges the result.

The engine and the model are doubles -- no model exists (ADR-019) -- but every
other component is real, so what these tests prove is that the *seams* line up:
the AI Runtime depends only on core, yet slots cleanly between a real snapshot
and a real fusion patch, and a failure inside it is contained by the Plugin
Runtime as an AI-runtime error code.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from teea.ai import (
    CapabilityKind,
    ExecutionContext,
    InferenceRequest,
    LocalAIRuntime,
    ModelDescriptor,
)
from teea.core.errors import ErrorCode
from teea.fusion import (
    PriorityRankedFusionEngine,
    Suggestion,
    SuggestionPriority,
)
from teea.nlp.snapshot import DocumentSnapshot, LanguageServerSnapshotBuilder
from teea.plugins import SupervisedPluginRuntime
from tests.ai.conftest import FailingInferEngine, descriptor

FEATURES = CapabilityKind.SEMANTIC_FEATURES


class SimilarityEngine:
    """A stand-in engine that scores a sentence's length -- deterministic, no model."""

    def load(self, d: ModelDescriptor, c: ExecutionContext) -> None:
        return None

    def infer(
        self, d: ModelDescriptor, request: InferenceRequest
    ) -> Mapping[str, Any]:
        text = str(request.inputs.get("text", ""))
        return {"score": 1.0 / (1.0 + len(text))}

    def unload(self, d: ModelDescriptor) -> None:
        return None


def features_runtime(engine: object) -> LocalAIRuntime:
    """A running runtime offering the semantic-features capability."""
    runtime = LocalAIRuntime(engine)  # type: ignore[arg-type]
    runtime.register(descriptor(name="tibert", provides={FEATURES}))
    runtime.start()
    return runtime


class AIBackedPlugin:
    """A feature plugin that asks the AI Runtime to score each sentence.

    This is the shape Figure 6 intends: the plugin is a Request Source, the
    runtime returns an Output, and the plugin turns it into a suggestion.
    """

    name = "coherence"

    def __init__(self, runtime: LocalAIRuntime) -> None:
        self._runtime = runtime

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        for analysis in snapshot.analyses:
            response = self._runtime.infer(
                InferenceRequest(capability=FEATURES, inputs={"text": analysis.text})
            )
            score = float(response.outputs["score"])
            if score < 0.5:
                yield Suggestion(
                    source=self.name,
                    span=analysis.span,
                    replacement=None,
                    score=1.0 - score,
                    priority=SuggestionPriority.LOW,
                    message=f"low coherence ({response.produced_by})",
                )


# -- The AI Runtime inside the plugin -> fusion chain -------------------------
def test_an_ai_backed_plugin_produces_advisories(corpus_sentences: list[str]) -> None:
    """Language Server -> Plugin (calling AI Runtime) -> Fusion, end to end."""
    snapshot = LanguageServerSnapshotBuilder().analyze("".join(corpus_sentences[:10]))
    runtime = features_runtime(SimilarityEngine())
    plugin = AIBackedPlugin(runtime)

    results = SupervisedPluginRuntime([plugin]).dispatch(snapshot)
    unified = PriorityRankedFusionEngine().fuse(snapshot.source, results.suggestions)

    assert results.is_healthy is True
    assert unified.advisories
    assert all(a.source == "coherence" for a in unified.advisories)
    # The runtime loaded the one model once and kept it resident across sentences.
    assert runtime.health().num_loaded == 1


def test_an_inference_failure_is_contained_by_the_plugin_runtime(
    corpus_sentences: list[str],
) -> None:
    """The composition ADR-018 and the AI error taxonomy were built for.

    A model failure raises an ``InferenceError`` inside the plugin; the Plugin
    Runtime captures it as a ``PluginFailure`` that keeps the AI-runtime code, so
    the add-in sees ``TEEA-3005`` rather than a generic crash -- and the other
    plugins still deliver.
    """
    snapshot = LanguageServerSnapshotBuilder().analyze("".join(corpus_sentences[:4]))
    broken = AIBackedPlugin(features_runtime(FailingInferEngine()))

    class Healthy:
        name = "spell"

        def examine(self, snap: DocumentSnapshot) -> Iterable[Suggestion]:
            return ()

    results = SupervisedPluginRuntime([broken, Healthy()]).dispatch(snapshot)

    assert results.is_healthy is False
    outcome = results.outcome_of("coherence")
    assert outcome is not None
    failure = outcome.failure
    assert failure is not None
    assert failure.code is ErrorCode.INFERENCE_FAILED
    assert failure.error_type == "InferenceError"
    spell = results.outcome_of("spell")
    assert spell is not None and spell.succeeded is True


def test_many_plugins_share_one_runtime_concurrently(
    corpus_sentences: list[str],
) -> None:
    """Figure 5 has plugins read the snapshot concurrently; they share the runtime.

    The Plugin Runtime dispatches through a thread pool, and every plugin calls
    the same AI Runtime. The recording engine is thread-safe, so the assertion is
    on the runtime's own accounting staying consistent under that load.
    """
    snapshot = LanguageServerSnapshotBuilder().analyze("".join(corpus_sentences[:12]))
    runtime = features_runtime(SimilarityEngine())
    plugins = [AIBackedPlugin(runtime) for _ in range(1)] + [
        _Renamed(AIBackedPlugin(runtime), f"c{i}") for i in range(5)
    ]

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = SupervisedPluginRuntime(plugins, executor=pool).dispatch(snapshot)

    assert results.is_healthy is True
    assert runtime.health().num_loaded == 1


class _Renamed:
    """Wraps a plugin under a different name, to register several of one kind."""

    def __init__(self, inner: AIBackedPlugin, name: str) -> None:
        self._inner = inner
        self.name = name

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        for suggestion in self._inner.examine(snapshot):
            yield suggestion.model_copy(update={"source": self.name})
