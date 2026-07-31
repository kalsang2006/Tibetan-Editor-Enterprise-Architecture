"""Plagiarism Detector — built-in TEEA feature plugin.

This plugin implements the :class:`~teea.plugins.interfaces.FeaturePlugin`
protocol.  It reads the document snapshot, runs the plagiarism detection
engine against the indexed corpus, and produces advisory suggestions for
each match above the configured threshold.

Advisories, not edits
---------------------
Plagiarism warnings are advisories (``replacement=None``).  They annotate
a document range but recommend no edit, consistent with the Suggestion
model's design (ADR-017).  The score reflects containment similarity, and
the priority is set to MEDIUM for typical matches, HIGH for significant
matches (>50 %), and LOW for marginal ones (<10 %).
"""

from __future__ import annotations

from collections.abc import Iterable

from teea.core.types import TextSpan
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.snapshot import DocumentSnapshot
from teea.plagiarism.engine import PlagiarismEngine
from teea.plagiarism.models import FingerprintMatch


class PlagiarismDetectorPlugin:
    """Feature plugin that detects plagiarism in the analysed document.

    The plugin reads the document source from the snapshot, passes it
    through the :class:`PlagiarismEngine`, and emits one advisory
    suggestion per match above the configured threshold.

    Args:
        engine: The plagiarism detection engine to query.  The caller is
            responsible for populating its index with the reference corpus.
    """

    def __init__(self, engine: PlagiarismEngine) -> None:
        self._engine = engine

    @property
    def name(self) -> str:
        """Stable plugin identifier."""
        return "teea.plagiarism"

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        """Run plagiarism detection over the document snapshot.

        Args:
            snapshot: The immutable analysis of the whole document.

        Yields:
            One :class:`Suggestion` per corpus match above the threshold,
            as advisories (``replacement=None``).
        """
        if not snapshot.source:
            return

        result = self._engine.detect(snapshot.source)

        if not result.matches:
            return

        doc_end = len(snapshot.source)
        doc_bytes = len(snapshot.source.encode("utf-8"))
        default_span = TextSpan(char_start=0, char_end=doc_end, byte_start=0, byte_end=doc_bytes)

        for match in result.matches[:10]:  # limit to top 10 matches
            priority = _priority_for(match.similarity)
            target_span = match.source_span if match.source_span is not None else default_span
            yield Suggestion(
                source=self.name,
                span=target_span,
                replacement=None,
                score=match.similarity,
                priority=priority,
                message=_format_message(match, result.query_fingerprint_count),
            )


def _priority_for(similarity: float) -> SuggestionPriority:
    """Map a similarity score to a priority class.

    Args:
        similarity: Containment similarity in ``[0, 1]``.

    Returns:
        The corresponding urgency.
    """
    if similarity >= 0.5:
        return SuggestionPriority.HIGH
    if similarity >= 0.1:
        return SuggestionPriority.MEDIUM
    return SuggestionPriority.LOW


def _format_message(match: object, query_total: int) -> str:
    """Format a human-readable plagiarism warning.

    Args:
        match: A :class:`FingerprintMatch` instance.
        query_total: Total fingerprints in the query.

    Returns:
        A formatted message string.
    """
    m = match
    if isinstance(m, FingerprintMatch):
        pct = round(m.similarity * 100, 1)
        cov = round(m.coverage * 100, 1)
        return (
            f"Plagiarism: {pct}% match with \"{m.document_id}\" "
            f"(covers {cov}% of source, {m.overlap_count}/{m.query_fingerprint_count} fingerprints)"
        )
    return str(match)


__all__ = ["PlagiarismDetectorPlugin"]
