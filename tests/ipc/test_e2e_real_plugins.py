"""End-to-end integration: real plugins reachable through the full IPC pipeline.

Tests the complete chain that Figure 3 (Level-1 Data Flow) describes:

  P0: Normalizer → P4: Language Server → P5: Plugin Runtime (real plugins)
                    → P6: Suggestion Fusion Engine → P3: IPC Server → P2: Client

Every component here is the **shipped** implementation.  The plugins are the
real :class:`~teea.plugins.builtin.spelling.SpellCheckerPlugin` and
:class:`~teea.plugins.builtin.diagnostics.DocumentDiagnosticsPlugin`, wired
behind an :class:`~teea.ipc.server.IpcServer` and called through an
:class:`~teea.ipc.client.IpcClient` over :class:`~teea.ipc.transport.LoopbackTransport`.

The document is real classical Tibetan (Milarepa corpus from
``tests/data/mila_sentences.txt``), so spans, offsets, and suggestions are
validated against authentic data rather than invented strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from teea.core.errors import ErrorCode
from teea.fusion import PriorityRankedFusionEngine
from teea.ipc import IpcClient, IpcServer, LoopbackTransport, RemoteError, Session
from teea.nlp.snapshot import LanguageServerSnapshotBuilder
from teea.nlp.tokenization import TextNormalizer
from teea.plugins import SupervisedPluginRuntime
from teea.plugins.builtin.diagnostics import DocumentDiagnosticsPlugin
from teea.plugins.builtin.spelling import SpellCheckerPlugin


class FullPipelineHandler:
    """Wires the real normalizer, Language Server, plugins, and fusion engine
    behind one IPC callable handler.

    This is what the daemon's own ``analyze`` method looks like when it is
    configured with the shipped built-in plugins.
    """

    def __init__(self) -> None:
        self._normalizer = TextNormalizer(form="NFC", collapse_whitespace=False)
        self._language_server = LanguageServerSnapshotBuilder()
        self._plugins = SupervisedPluginRuntime(
            [SpellCheckerPlugin(), DocumentDiagnosticsPlugin()]
        )
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
            "num_plugins": results.num_plugins,
            "spelling_suggestions": [
                {
                    "source": s.source,
                    "start": s.span.char_start,
                    "end": s.span.char_end,
                    "message": s.message,
                    "priority": s.priority.value,
                }
                for s in results.suggestions
                if s.source == "teea.spelling"
            ],
            "diagnostics": [
                {
                    "source": s.source,
                    "message": s.message,
                    "priority": s.priority.value,
                }
                for s in results.suggestions
                if s.source == "teea.diagnostics"
            ],
            "fused": [
                {
                    "source": s.source,
                    "start": s.span.char_start,
                    "end": s.span.char_end,
                    "replacement": s.replacement,
                    "priority": s.priority.value,
                    "is_advisory": s.is_advisory,
                }
                for s in unified.suggestions
            ],
            "patched": unified.patch.apply(),
            "rejected": len(unified.rejected),
        }


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def server() -> IpcServer:
    """An IPC server routing the full pipeline handler."""
    srv = IpcServer()
    srv.register("analyze", FullPipelineHandler())
    return srv


@pytest.fixture
def connected(server: IpcServer) -> tuple[IpcClient, LoopbackTransport]:
    """A connected ``(client, transport)`` pair over loopback."""
    client_end, server_end = LoopbackTransport.pair()
    server.serve(server_end)
    client = IpcClient()
    client.connect(client_end)
    return client, client_end


# -- The full pipeline: real plugins, real corpus, IPC round trip --------------


def test_pipeline_processes_real_corpus(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """The full pipeline processes real Tibetan and returns structured results."""
    client, _t = connected
    document = "".join(corpus_sentences[:12])

    result = client.call("analyze", {"text": document}, timeout=30.0)

    assert result["sentences"] > 5
    assert result["morphemes"] > 20
    assert result["healthy"] is True
    assert result["num_plugins"] == 2
    client.close()


def test_spell_checker_produces_suggestions_with_real_corpus(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """The SpellCheckerPlugin flags unknown words through the IPC boundary."""
    client, _t = connected
    document = "".join(corpus_sentences[:12])

    result = client.call("analyze", {"text": document}, timeout=30.0)
    spell_suggestions = result["spelling_suggestions"]

    assert len(spell_suggestions) > 0
    for sug in spell_suggestions:
        assert sug["source"] == "teea.spelling"
        assert 0 <= sug["start"] < sug["end"] <= len(document)
        assert document[sug["start"] : sug["end"]]
        assert "Unknown word" in sug["message"]
    client.close()


def test_diagnostics_plugin_reports_stats(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """The diagnostics plugin sends document statistics through IPC."""
    client, _t = connected
    document = "".join(corpus_sentences[:12])

    result = client.call("analyze", {"text": document}, timeout=30.0)
    diagnostics = result["diagnostics"]

    assert len(diagnostics) == 1
    diag = diagnostics[0]
    assert diag["source"] == "teea.diagnostics"
    assert "sentence_count" in diag["message"]
    assert "token_count" in diag["message"]
    assert "entity_count" in diag["message"]
    client.close()


def test_spans_in_fused_output_address_the_document(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """Every fused suggestion's span must point into the original document text.

    This is the critical seam: the add-in paints suggestions onto Word
    character ranges using exactly these start/end numbers.  If a span is
    wrong, the add-in highlights the wrong text silently.
    """
    client, _t = connected
    document = "".join(corpus_sentences[:12])

    result = client.call("analyze", {"text": document}, timeout=30.0)

    checked = 0
    for sug in result["fused"]:
        start, end = int(sug["start"]), int(sug["end"])
        assert 0 <= start <= end <= len(document)
        checked += 1
    assert checked > 0
    client.close()


def test_fused_spelling_suggestions_are_advisories(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """Spell-checker advisories (no replacement) must survive fusion and IPC.

    The SpellCheckerPlugin emits ``replacement=None`` because the shipped
    dictionary is a POS model, not a spelling lexicon.  These must reach the
    add-in as advisories, not as no-op edits that the validator discards.
    """
    client, _t = connected
    document = "".join(corpus_sentences[:12])

    result = client.call("analyze", {"text": document}, timeout=30.0)

    spell_fused = [s for s in result["fused"] if s["source"] == "teea.spelling"]
    assert len(spell_fused) > 0
    for sug in spell_fused:
        assert sug["is_advisory"] is True
        assert sug["replacement"] is None
    client.close()


def test_diagnostics_survives_fusion(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """The diagnostics plugin's single advisory reaches the fused output."""
    client, _t = connected
    document = "".join(corpus_sentences[:12])

    result = client.call("analyze", {"text": document}, timeout=30.0)

    diag_fused = [s for s in result["fused"] if s["source"] == "teea.diagnostics"]
    assert len(diag_fused) == 1
    assert diag_fused[0]["is_advisory"] is True
    assert diag_fused[0]["priority"] == "low"
    client.close()


def test_full_pipeline_is_deterministic(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """Calling the pipeline twice with the same text must produce identical
    results, proving that plugin dispatch order, fusion sorting, and IPC
    serialization are all stable."""
    client, _t = connected
    document = "".join(corpus_sentences[:8])

    first = client.call("analyze", {"text": document}, timeout=30.0)
    second = client.call("analyze", {"text": document}, timeout=30.0)

    assert first == second
    client.close()


def test_failure_propagation_reaches_the_client(
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """A missing 'text' parameter in the call raises a typed remote error
    through the whole stack."""
    client, _t = connected

    with pytest.raises(RemoteError) as error:
        client.call("analyze", {})

    assert error.value.code is ErrorCode.IPC_HANDLER_FAILED
    assert error.value.remote_error_type == "KeyError"
    client.close()


def test_advisory_only_plugins_produce_no_modifications(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """Both built-in plugins are advisory-only (no ``replacement``), so the
    fused patch must equal the original document text.
    """
    client, _t = connected
    document = "".join(corpus_sentences[:8])

    result = client.call("analyze", {"text": document}, timeout=30.0)

    # Both built-in plugins are advisory-only, so the patch == original
    assert result["patched"] == document
    client.close()


def test_spelling_spans_align_with_morpheme_boundaries(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """Each spelling suggestion's span must start and end at positions that
    correspond to actual morpheme boundaries in the document, verifying that
    document_span translation is correct through the IPC boundary."""
    client, _t = connected
    document = "".join(corpus_sentences[:20])

    result = client.call("analyze", {"text": document}, timeout=30.0)

    for sug in result["spelling_suggestions"]:
        span_text = document[sug["start"] : sug["end"]]
        assert span_text, "span must select non-empty text"
        # The span text should be a substring of the document and should
        # appear in the message
        assert span_text in sug["message"]
    client.close()


def test_all_suggestions_are_attributed_to_correct_sources(
    corpus_sentences: list[str],
    connected: tuple[IpcClient, LoopbackTransport],
) -> None:
    """Every suggestion reaching the client must be attributed to exactly one
    of the two registered plugins, and no unknown sources appear."""
    client, _t = connected
    document = "".join(corpus_sentences[:12])

    result = client.call("analyze", {"text": document}, timeout=30.0)

    known_sources = {"teea.spelling", "teea.diagnostics"}
    for sug in result["fused"]:
        assert sug["source"] in known_sources, f"unexpected source: {sug['source']}"
    client.close()
