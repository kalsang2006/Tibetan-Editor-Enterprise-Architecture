"""Built-in document diagnostics plugin for TEEA.

Reports document statistics (sentence count, token count, entity count,
unresolved dependency ratio, semantic density) as an advisory Suggestion.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from teea.core.types import TextSpan
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.snapshot import DocumentSnapshot
from teea.plugins.interfaces import FeaturePlugin


class DocumentDiagnosticsPlugin(FeaturePlugin):
    """Built-in plugin that analyzes document structure and reports statistics.

    This plugin provides diagnostic information about the document including
    sentence count, token count, entity count, semantic graph density,
    unresolved dependency ratio, and more. It serves as both a health indicator
    and a demonstration of the plugin system.
    """

    def __init__(self) -> None:
        self._name = "teea.diagnostics"

    @property
    def name(self) -> str:
        """Stable identifier for this plugin."""
        return self._name

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        """Analyze the document and yield diagnostic statistics."""
        stats = self._compute_stats(snapshot)
        stats_str = "; ".join(f"{k}={v}" for k, v in stats.items())
        suggestion = Suggestion(
            source=self._name,
            span=TextSpan(char_start=0, char_end=0, byte_start=0, byte_end=0),
            replacement=None,
            score=1.0,
            priority=SuggestionPriority.LOW,
            message=stats_str,
        )
        return [suggestion]

    def _compute_stats(self, snapshot: DocumentSnapshot) -> dict[str, Any]:
        analyses = snapshot.analyses
        total_sentences = len(analyses)
        total_tokens = 0
        total_entities = 0
        total_terms = 0
        total_unresolved_deps = 0
        total_intent_nodes = 0

        for analysis in analyses:
            if analysis.tree and analysis.tree.nodes:
                total_tokens += len(analysis.tree.nodes)
                total_unresolved_deps += analysis.tree.num_unresolved
            if analysis.entities:
                total_entities += len(analysis.entities)
            if analysis.terms:
                total_terms += len(analysis.terms)
            if analysis.graph:
                total_intent_nodes += len(analysis.graph.nodes) if analysis.graph.nodes else 0

        semantic_density = 0.0
        if total_sentences > 0:
            semantic_density = round(total_intent_nodes / total_sentences, 2)

        unresolved_ratio = 0.0
        if total_tokens > 0:
            unresolved_ratio = round(total_unresolved_deps / total_tokens, 4)

        return {
            "sentence_count": total_sentences,
            "token_count": total_tokens,
            "entity_count": total_entities,
            "term_count": total_terms,
            "unresolved_dependency_count": total_unresolved_deps,
            "unresolved_ratio": unresolved_ratio,
            "semantic_graph_nodes": total_intent_nodes,
            "semantic_density": semantic_density,
        }


__all__ = ["DocumentDiagnosticsPlugin"]
