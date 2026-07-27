"""Integration: the whole daemon reached across the Local IPC boundary.

Figure 3 routes a document from the add-in (P2) through the Local IPC Layer (P3)
to the Language Server (P4), on to the Plugin Runtime (P5) and the Suggestion
Fusion Engine (P6), and returns "Merged Suggestions" the same way. Every one of
those components now exists, so this module wires them behind an IPC handler and
drives the whole thing from the client side.

The handlers are what the daemon will register. They are written here rather than
shipped because the IPC layer knows nothing of the components it fronts -- that
is precisely what keeps ``teea.ipc`` dependent on ``teea.core`` alone -- so
proving the seam means writing the glue once, in a test.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

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
from teea.ipc import (
    IpcClient,
    IpcServer,
    LoopbackTransport,
    MethodKind,
    RemoteError,
    Session,
)
from teea.nlp.snapshot import DocumentSnapshot, LanguageServerSnapshotBuilder
from teea.nlp.tokenization import TextNormalizer
from teea.plugins import SupervisedPluginRuntime

FEATURES = CapabilityKind.SEMANTIC_FEATURES


class LengthEngine:
    """A stand-in inference engine: deterministic, no model (ADR-019)."""

    def load(self, d: ModelDescriptor, c: ExecutionContext) -> None:
        return None

    def infer(self, d: ModelDescriptor, request: InferenceRequest) -> Mapping[str, Any]:
        return {"score": 1.0 / (1.0 + len(str(request.inputs.get("text", ""))))}

    def unload(self, d: ModelDescriptor) -> None:
        return None


class PredicatePlugin:
    """Suggests an edit on the first predicate of every sentence."""

    name = "grammar"

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        for analysis in snapshot.analyses:
            for node in analysis.graph.predicates[:1]:
                yield Suggestion(
                    source=self.name,
                    span=analysis.document_span(node.span),
                    replacement="ཀ",
                    score=0.8,
                    priority=SuggestionPriority.HIGH,
                )


class AnalyzeHandler:
    """The daemon's ``analyze`` method: P4 -> P5 -> P6, behind one IPC call."""

    def __init__(self) -> None:
        self._normalizer = TextNormalizer(form="NFC", collapse_whitespace=False)
        self._language_server = LanguageServerSnapshotBuilder()
        self._plugins = SupervisedPluginRuntime([PredicatePlugin()])
        self._fusion = PriorityRankedFusionEngine()

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        text = self._normalizer.normalize(str(params["text"]))
        snapshot = self._language_server.analyze(text)
        results = self._plugins.dispatch(snapshot)
        unified = self._fusion.fuse(snapshot.source, results.suggestions)
        return {
            "sentences": snapshot.num_sentences,
            "morphemes": snapshot.num_morphemes,
            "entities": snapshot.num_entities,
            "healthy": results.is_healthy,
            "suggestions": [
                {
                    "source": s.source,
                    "start": s.span.char_start,
                    "end": s.span.char_end,
                    "replacement": s.replacement,
                    "priority": s.priority.value,
                }
                for s in unified.suggestions
            ],
            "patched": unified.patch.apply(),
        }


class FeaturesHandler:
    """The daemon's ``features`` method: an AI Runtime call behind IPC."""

    def __init__(self, runtime: LocalAIRuntime) -> None:
        self._runtime = runtime

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        response = self._runtime.infer(
            InferenceRequest(capability=FEATURES, inputs={"text": params["text"]})
        )
        return {"score": response.outputs["score"], "model": response.produced_by}


def daemon(*, executor: ThreadPoolExecutor | None = None) -> IpcServer:
    """A server routing the methods the daemon would expose."""
    runtime = LocalAIRuntime(LengthEngine())
    runtime.register(ModelDescriptor(name="tibert", version="1", provides={FEATURES}))
    runtime.start()

    server = IpcServer(executor=executor)
    server.register("analyze", AnalyzeHandler())
    server.register("features", FeaturesHandler(runtime))
    server.register("noted", _Noted(), kind=MethodKind.COMMAND)
    return server


class _Noted:
    """A command handler recording document-changed notifications."""

    def __init__(self) -> None:
        self.seen: list[Any] = []

    def handle(self, params: Mapping[str, Any], session: Session) -> Mapping[str, Any]:
        self.seen.append(params.get("revision"))
        return {}


def connected(server: IpcServer) -> tuple[IpcClient, LoopbackTransport]:
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    client = IpcClient()
    client.connect(client_end)
    return client, client_end


# -- The whole chain across the boundary --------------------------------------
def test_a_document_is_analysed_across_the_ipc_boundary(
    corpus_sentences: list[str],
) -> None:
    """Figure 3's Analysis Request in, Merged Suggestions out."""
    client, _t = connected(daemon())
    document = "".join(corpus_sentences[:8])

    result = client.call("analyze", {"text": document}, timeout=30.0)

    assert result["sentences"] > 1
    assert result["morphemes"] > 10
    assert result["healthy"] is True
    assert result["suggestions"]
    assert result["patched"] != document
    client.close()


def test_suggestion_offsets_survive_serialization(
    corpus_sentences: list[str],
) -> None:
    """The spans that crossed as JSON must still address the document.

    This is the seam that would fail silently: the add-in paints suggestions onto
    Word ranges using exactly these numbers.
    """
    client, _t = connected(daemon())
    document = "".join(corpus_sentences[:6])
    result = client.call("analyze", {"text": document}, timeout=30.0)

    checked = 0
    for suggestion in result["suggestions"]:
        start, end = int(suggestion["start"]), int(suggestion["end"])
        assert 0 <= start < end <= len(document)
        assert document[start:end]
        checked += 1
    assert checked > 0
    client.close()


def test_the_ai_runtime_is_reachable_across_the_boundary() -> None:
    """Figure 6's AI Request / AI Response, tunnelled through Figure 3's P3."""
    client, _t = connected(daemon())
    result = client.call("features", {"text": "བཀྲ་ཤིས"}, timeout=10.0)
    assert result["model"] == "tibert:1"
    assert 0.0 < float(result["score"]) <= 1.0
    client.close()


def test_a_document_changed_command_needs_no_reply() -> None:
    """FR-8's non-blocking command bus, end to end."""
    server = daemon()
    client, _t = connected(server)
    client.notify("noted", {"revision": 7})
    assert client.health()["status"] == "ok"
    client.close()


def test_the_client_discovers_the_daemons_methods() -> None:
    client, _t = connected(daemon())
    names = {d.name for d in client.methods}
    assert {"analyze", "features", "noted"} <= names
    kinds = {d.name: d.kind for d in client.methods}
    assert kinds["noted"] is MethodKind.COMMAND
    assert kinds["analyze"] is MethodKind.QUERY
    client.close()


# -- Error propagation through the whole stack --------------------------------
def test_a_failure_deep_in_the_daemon_reaches_the_client_with_its_code() -> None:
    """A KeyError in the handler surfaces as a typed remote failure, not a hang."""
    client, _t = connected(daemon())
    with pytest.raises(RemoteError) as error:
        client.call("analyze", {})  # no "text" param
    assert error.value.code is ErrorCode.IPC_HANDLER_FAILED
    assert error.value.remote_error_type == "KeyError"
    client.close()


def test_an_ai_runtime_error_keeps_its_own_code_across_the_boundary() -> None:
    """TEEA-3xxx raised inside the daemon arrives as TEEA-3xxx on the client.

    Three components compose here without knowing about each other: the AI
    Runtime raises a typed error (ADR-019), and the IPC fault envelope carries
    its code intact to the add-in.
    """
    runtime = LocalAIRuntime(LengthEngine())
    runtime.start()  # nothing registered, so no model provides the capability

    server = IpcServer()
    server.register("features", FeaturesHandler(runtime))
    client, _t = connected(server)

    with pytest.raises(RemoteError) as error:
        client.call("features", {"text": "བཀྲ"})
    assert error.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert error.value.remote_error_type == "CapabilityUnavailableError"
    client.close()


def test_a_daemon_failure_does_not_break_the_next_call(
    corpus_sentences: list[str],
) -> None:
    client, _t = connected(daemon())
    with pytest.raises(RemoteError):
        client.call("analyze", {})
    result = client.call("analyze", {"text": "".join(corpus_sentences[:3])}, timeout=30.0)
    assert result["sentences"] > 0
    client.close()


# -- Concurrency across the boundary ------------------------------------------
def test_concurrent_analyses_stay_correlated(corpus_sentences: list[str]) -> None:
    """Many add-in requests at once must each get their own answer."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        client, _t = connected(daemon(executor=pool))
        documents = ["".join(corpus_sentences[i : i + 2]) for i in range(6)]

        def analyse(text: str) -> int:
            return int(client.call("analyze", {"text": text}, timeout=30.0)["sentences"])

        with ThreadPoolExecutor(max_workers=6) as callers:
            counts = list(callers.map(analyse, documents))

        expected = [
            LanguageServerSnapshotBuilder().analyze(text).num_sentences for text in documents
        ]
        assert counts == expected
        client.close()


def test_the_whole_chain_is_deterministic(corpus_sentences: list[str]) -> None:
    client, _t = connected(daemon())
    document = "".join(corpus_sentences[:5])
    first = client.call("analyze", {"text": document}, timeout=30.0)
    second = client.call("analyze", {"text": document}, timeout=30.0)
    assert first == second
    client.close()
