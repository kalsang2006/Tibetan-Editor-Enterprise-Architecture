"""End-to-end workflow orchestration for TEEA.

Provides ``full_workflow()`` which chains document loading, normalization,
NLP analysis (Stages 2-12), plugin dispatch, suggestion fusion, and output
saving into a single pipeline call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from teea.core.config import NormalizationForm
from teea.core.logging import get_logger
from teea.fusion import PriorityRankedFusionEngine, Suggestion, UnifiedSuggestions
from teea.nlp.snapshot import DocumentSnapshot, LanguageServerSnapshotBuilder
from teea.nlp.tokenization import TextNormalizer
from teea.plugins import PluginResults, SupervisedPluginRuntime

_logger = get_logger(__name__)


def load_document(path: str) -> str:
    """Load a Tibetan text document from a file path.

    Args:
        path: Path to the text file (UTF-8 encoded).

    Returns:
        The raw document text.
    """
    return Path(path).read_text(encoding="utf-8")


def normalize_document(text: str, form: NormalizationForm = "NFC") -> str:
    """Normalize and clean document text through Stage 2.

    Args:
        text: Raw document text.
        form: Unicode normalization form.

    Returns:
        Normalized text.
    """
    normalizer = TextNormalizer(form=form)
    return normalizer.normalize(text)


def analyze_text(
    text: str,
    builder: LanguageServerSnapshotBuilder | None = None,
) -> DocumentSnapshot:
    """Run a Tibetan text through the full NLP pipeline (Stages 2-12).

    Args:
        text: Normalized Tibetan text.
        builder: The snapshot builder. Defaults to a new default builder.

    Returns:
        The complete document snapshot.
    """
    if builder is None:
        builder = LanguageServerSnapshotBuilder()
    normalized = normalize_document(text)
    return builder.analyze(normalized)


def snapshot_to_dict(snapshot: DocumentSnapshot) -> dict[str, Any]:
    """Serialize a document snapshot to a JSON-compatible dict.

    Args:
        snapshot: The document snapshot.

    Returns:
        A dict suitable for JSON serialization.
    """
    return snapshot.model_dump(mode="json")


def snapshot_to_text(snapshot: DocumentSnapshot) -> str:
    """Render a document snapshot as human-readable text.

    Args:
        snapshot: The document snapshot.

    Returns:
        A formatted text report of the analysis.
    """
    lines: list[str] = []
    source = snapshot.source
    lines.append(f"Document: {len(source)} chars, {len(snapshot.analyses)} sentences")
    lines.append("")

    for index, analysis in enumerate(snapshot.analyses):
        lines.append(f"[{index + 1}] {analysis.sentence.text}")
        lines.append(
            f"    Intent: {analysis.intent.mood.value} / {analysis.intent.polarity.value}"
        )
        lines.append(f"    Entities: {len(analysis.entities)}")
        for entity in analysis.entities.entities:
            doc_span = analysis.document_span(entity.span)
            text = source[doc_span.char_start : doc_span.char_end]
            lines.append(f"      - {text}")
        lines.append(f"    Terms: {len(analysis.terms)}")
        for term in analysis.terms.terms:
            doc_span = analysis.document_span(term.span)
            text = source[doc_span.char_start : doc_span.char_end]
            lines.append(f"      - {text}")
        lines.append("")

    return "\n".join(lines)


def run_plugins(
    snapshot: DocumentSnapshot,
    plugins: SupervisedPluginRuntime | None = None,
) -> PluginResults:
    """Run all registered plugins over a snapshot.

    Args:
        snapshot: The document snapshot.
        plugins: The plugin runtime. Defaults to an empty runtime (no plugins).

    Returns:
        The plugin results.
    """
    if plugins is None:
        plugins = SupervisedPluginRuntime()
    return plugins.dispatch(snapshot)


def fuse_suggestions(
    source: str,
    suggestions: list[Suggestion],
    engine: PriorityRankedFusionEngine | None = None,
) -> UnifiedSuggestions:
    """Fuse a list of suggestions into a unified result.

    Args:
        source: The original document text.
        suggestions: The suggestions to fuse.
        engine: The fusion engine. Defaults to a new engine.

    Returns:
        The unified suggestions with patch.
    """
    if engine is None:
        engine = PriorityRankedFusionEngine()
    return engine.fuse(source, suggestions)


def save_json(path: str, data: dict[str, Any]) -> str:
    """Save data as pretty-printed JSON to a file.

    Args:
        path: Output file path.
        data: Data to serialize.

    Returns:
        The path the file was written to.
    """
    out = Path(path)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _logger.info("saved_json", path=str(out), size_bytes=out.stat().st_size)
    return str(out)


def save_text(path: str, text: str) -> str:
    """Save text to a file.

    Args:
        path: Output file path.
        text: Text content.

    Returns:
        The path the file was written to.
    """
    out = Path(path)
    out.write_text(text, encoding="utf-8")
    return str(out)


def full_workflow(
    source_path: str,
    *,
    output_json: str | None = None,
    output_text: str | None = None,
    builder: LanguageServerSnapshotBuilder | None = None,
    plugins: SupervisedPluginRuntime | None = None,
    engine: PriorityRankedFusionEngine | None = None,
) -> dict[str, Any]:
    """Run the complete end-to-end workflow: load, analyze, plugin, fuse, save.

    Args:
        source_path: Path to the Tibetan text file.
        output_json: Optional path for JSON output.
        output_text: Optional path for text output.
        builder: The snapshot builder.
        plugins: The plugin runtime.
        engine: The fusion engine.

    Returns:
        A dict with the workflow results.
    """
    _logger.info("workflow_started", source=source_path)
    text = load_document(source_path)
    normalized = normalize_document(text)
    _logger.info(
        "document_loaded",
        source=source_path,
        raw_chars=len(text),
        normalized_chars=len(normalized),
    )

    snapshot = analyze_text(text, builder=builder)
    _logger.info("analysis_complete", sentences=len(snapshot.analyses))

    plugin_results = run_plugins(snapshot, plugins=plugins)
    _logger.info(
        "plugins_complete",
        plugins=plugin_results.num_plugins,
        suggestions=plugin_results.num_suggestions,
    )

    fused = fuse_suggestions(text, list(plugin_results.suggestions), engine=engine)
    _logger.info(
        "fusion_complete",
        suggestions=len(fused.suggestions),
        operations=len(fused.patch.operations) if fused.patch else 0,
    )

    result = {
        "source": source_path,
        "char_count": len(text),
        "sentence_count": len(snapshot.analyses),
        "plugins_run": plugin_results.num_plugins,
        "suggestions": [s.model_dump(mode="json") for s in fused.suggestions],
        "patch": fused.patch.model_dump(mode="json") if fused.patch else None,
        "snapshot": snapshot_to_dict(snapshot),
    }

    if output_json:
        save_json(output_json, result)
    if output_text:
        save_text(output_text, snapshot_to_text(snapshot))

    _logger.info("workflow_complete", source=source_path)
    return result


__all__ = [
    "analyze_text",
    "full_workflow",
    "fuse_suggestions",
    "load_document",
    "normalize_document",
    "run_plugins",
    "save_json",
    "save_text",
    "snapshot_to_dict",
    "snapshot_to_text",
]
