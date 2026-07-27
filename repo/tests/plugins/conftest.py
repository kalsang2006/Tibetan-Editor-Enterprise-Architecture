"""Plugin doubles and fixtures for the Plugin Runtime suite.

The runtime's whole job is to behave well when a plugin does not, so most of
these doubles misbehave deliberately: they crash, they lie about who produced
their output, they claim a name they cannot report, or they return nothing at
all. The well-behaved one is the exception rather than the rule.

The snapshot is built by the real Language Server over real Tibetan, because the
spans a plugin must produce are document offsets and Tibetan is where character
and byte offsets diverge.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import pytest

from teea.core.errors import ConfigurationError
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.snapshot import DocumentSnapshot, LanguageServerSnapshotBuilder

SHAD = "།"
FIRST = "ཞིང་ཀློག" + SHAD
SECOND = "ཡུལ་འགྲོ" + SHAD
DOCUMENT = FIRST + SECOND


class WellBehavedPlugin:
    """Proposes one edit per sentence, correctly attributed and in document offsets."""

    def __init__(
        self,
        name: str = "spell",
        priority: SuggestionPriority = SuggestionPriority.HIGH,
        score: float = 0.9,
    ) -> None:
        self._name = name
        self._priority = priority
        self._score = score

    @property
    def name(self) -> str:
        return self._name

    def examine(self, snapshot: DocumentSnapshot) -> Iterator[Suggestion]:
        for analysis in snapshot.analyses:
            node = analysis.graph.nodes[0]
            yield Suggestion(
                source=self._name,
                span=analysis.document_span(node.span),
                replacement="ཀ",
                score=self._score,
                priority=self._priority,
            )


class SilentPlugin:
    """Completes successfully having found nothing.

    Distinguishing this from a crash is the reason dispatch reports an outcome
    per plugin rather than a flat list of suggestions.
    """

    name = "quiet"

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        return ()


class CrashingPlugin:
    """Raises an ordinary exception part-way through."""

    name = "crash"

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        raise RuntimeError("the plugin exploded")


class MisconfiguredPlugin:
    """Raises a typed TEEA error, which must keep its own code."""

    name = "misconfigured"

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        raise ConfigurationError("no dictionary available")


class ImpersonatingPlugin:
    """Attributes its output to a different plugin, borrowing its trust."""

    name = "liar"

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        analysis = snapshot.analyses[0]
        return [
            Suggestion(
                source="spell",
                span=analysis.span,
                replacement="ཁ",
                score=1.0,
                priority=SuggestionPriority.CRITICAL,
            )
        ]


class LateCrashingPlugin:
    """Yields one suggestion and then raises, to prove partial output is discarded."""

    name = "late"

    def examine(self, snapshot: DocumentSnapshot) -> Iterator[Suggestion]:
        analysis = snapshot.analyses[0]
        yield Suggestion(
            source="late",
            span=analysis.span,
            replacement="ག",
            score=0.5,
            priority=SuggestionPriority.LOW,
        )
        raise ValueError("failed after producing output")


class NamelessPlugin:
    """Reports an empty name, which would make its failures unattributable."""

    name = ""

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        return ()  # pragma: no cover - registration rejects it first


class UnnameablePlugin:
    """Raises when asked for its name."""

    @property
    def name(self) -> str:
        raise RuntimeError("cannot introspect")

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        return ()  # pragma: no cover - registration rejects it first


@pytest.fixture(scope="session")
def plugin_document() -> str:
    """The document every plugin test examines."""
    return DOCUMENT


@pytest.fixture(scope="session")
def plugin_snapshot() -> DocumentSnapshot:
    """A real snapshot of :data:`DOCUMENT`, built by the real Language Server."""
    return LanguageServerSnapshotBuilder().analyze(DOCUMENT)
