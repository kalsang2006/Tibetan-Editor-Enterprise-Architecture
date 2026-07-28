"""End-to-end proof of the add-in's document-analysis HTTP bridge.

Every test here drives a *real* socket: `serve_analysis_http` binds an actual
ephemeral loopback port, and each test is a real `http.client.HTTPConnection`
talking HTTP/1.1 to it. Nothing here calls the pipeline's collaborators
directly; that is what `tests/plugins/test_runtime.py`, `tests/fusion/` and
`tests/nlp/snapshot/` already cover. What only this module can prove is that
the byte-level contract survives an actual TCP round trip.
"""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterable, Iterator
from typing import Any

import pytest

from teea.fusion import PriorityRankedFusionEngine, Suggestion, SuggestionPriority
from teea.nlp.snapshot import DocumentSnapshot, LanguageServerSnapshotBuilder
from teea.plugins import SupervisedPluginRuntime
from teea.transport import AnalysisHttpServer, NotLoopbackError, serve_analysis_http
from teea.transport.analysis_server import ANALYSIS_METHOD, ANALYSIS_PATH

SHAD = "།"
DOCUMENT = "ཞིང་ཀློག" + SHAD + "ཡུལ་འགྲོ" + SHAD


class _OneEditPlugin:
    """Proposes one edit on the document's first sentence."""

    name = "spell"

    def examine(self, snapshot: DocumentSnapshot) -> Iterator[Suggestion]:
        analysis = snapshot.analyses[0]
        node = analysis.graph.nodes[0]
        yield Suggestion(
            source=self.name,
            span=analysis.document_span(node.span),
            replacement="ཀ",
            score=0.9,
            priority=SuggestionPriority.HIGH,
        )


class _CrashingPlugin:
    """Raises, to prove a plugin fault degrades to a captured failure, not a 500."""

    name = "crash"

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        raise RuntimeError("boom")


@pytest.fixture
def builder() -> LanguageServerSnapshotBuilder:
    return LanguageServerSnapshotBuilder()


@pytest.fixture
def fusion() -> PriorityRankedFusionEngine:
    return PriorityRankedFusionEngine()


@pytest.fixture
def server(
    builder: LanguageServerSnapshotBuilder, fusion: PriorityRankedFusionEngine
) -> Iterator[AnalysisHttpServer]:
    plugins = SupervisedPluginRuntime(plugins=[_OneEditPlugin()])
    running = serve_analysis_http(builder, plugins, fusion, port=0)
    yield running
    running.shutdown()


def _envelope(text: str, **overrides: Any) -> dict[str, Any]:
    envelope = {
        "protocol_version": "1.0",
        "request_id": overrides.pop("request_id", "req-1"),
        "method": overrides.pop("method", ANALYSIS_METHOD),
        "params": {"text": text},
        "session_id": overrides.pop("session_id", None),
        "expects_response": overrides.pop("expects_response", True),
    }
    envelope.update(overrides)
    return envelope


def _post(server: AnalysisHttpServer, path: str, body: dict[str, Any]) -> http.client.HTTPResponse:
    conn = http.client.HTTPConnection(server.host, server.port, timeout=5)
    payload = json.dumps(body).encode("utf-8")
    conn.request("POST", path, body=payload, headers={"Content-Type": "application/json"})
    return conn.getresponse()


def test_health_reports_ok(server: AnalysisHttpServer) -> None:
    conn = http.client.HTTPConnection(server.host, server.port, timeout=5)
    conn.request("GET", "/health")
    response = conn.getresponse()
    assert response.status == 200
    body = json.loads(response.read())
    assert body["status"] == "ok"


def test_analyze_returns_a_ranked_suggestion(server: AnalysisHttpServer) -> None:
    response = _post(server, ANALYSIS_PATH, _envelope(DOCUMENT))
    assert response.status == 200
    body = json.loads(response.read())
    assert body["ok"] is True
    result = body["result"]
    assert result["patch"]["source"] == DOCUMENT
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["source"] == "spell"


def test_a_crashing_plugin_is_captured_not_raised(
    builder: LanguageServerSnapshotBuilder, fusion: PriorityRankedFusionEngine
) -> None:
    plugins = SupervisedPluginRuntime(plugins=[_CrashingPlugin()])
    with serve_analysis_http(builder, plugins, fusion, port=0) as running:
        response = _post(running, ANALYSIS_PATH, _envelope(DOCUMENT))
    assert response.status == 200
    body = json.loads(response.read())
    assert body["ok"] is True
    assert body["result"]["suggestions"] == []


def test_unknown_path_is_not_found(server: AnalysisHttpServer) -> None:
    response = _post(server, "/api/analysis/unknown", _envelope(DOCUMENT))
    assert response.status == 404


def test_mismatched_method_is_a_bad_request(server: AnalysisHttpServer) -> None:
    response = _post(server, ANALYSIS_PATH, _envelope(DOCUMENT, method="ai.rewrite"))
    assert response.status == 400


def test_malformed_body_is_a_bad_request(server: AnalysisHttpServer) -> None:
    conn = http.client.HTTPConnection(server.host, server.port, timeout=5)
    conn.request(
        "POST", ANALYSIS_PATH, body=b"not json", headers={"Content-Type": "application/json"}
    )
    response = conn.getresponse()
    assert response.status == 400


def test_non_string_text_is_reported_as_a_fault(server: AnalysisHttpServer) -> None:
    envelope = _envelope(DOCUMENT)
    envelope["params"] = {"text": 123}
    response = _post(server, ANALYSIS_PATH, envelope)
    assert response.status == 200
    body = json.loads(response.read())
    assert body["ok"] is False
    assert body["error"]["code"] == "TEEA-0002"


def test_options_answers_a_cors_preflight(server: AnalysisHttpServer) -> None:
    conn = http.client.HTTPConnection(server.host, server.port, timeout=5)
    conn.request("OPTIONS", ANALYSIS_PATH)
    response = conn.getresponse()
    assert response.status == 204
    assert response.getheader("Access-Control-Allow-Origin") == "*"


def test_non_loopback_host_is_refused(
    builder: LanguageServerSnapshotBuilder,
    fusion: PriorityRankedFusionEngine,
) -> None:
    plugins = SupervisedPluginRuntime()
    with pytest.raises(NotLoopbackError):
        AnalysisHttpServer(builder, plugins, fusion, host="0.0.0.0", port=0)


def test_ipv6_loopback_is_refused(
    builder: LanguageServerSnapshotBuilder,
    fusion: PriorityRankedFusionEngine,
) -> None:
    plugins = SupervisedPluginRuntime()
    with pytest.raises(NotLoopbackError):
        AnalysisHttpServer(builder, plugins, fusion, host="::1", port=0)


def test_shutdown_is_idempotent(
    builder: LanguageServerSnapshotBuilder,
    fusion: PriorityRankedFusionEngine,
) -> None:
    plugins = SupervisedPluginRuntime()
    running = AnalysisHttpServer(builder, plugins, fusion, port=0)
    running.shutdown()
    running.shutdown()
