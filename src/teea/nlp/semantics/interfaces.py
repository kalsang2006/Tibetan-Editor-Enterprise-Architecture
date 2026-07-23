"""The semantic analyser abstraction (interface) for TEEA.

The Language Server drives Stage 11 through this protocol rather than a concrete
class, consistent with every other stage. SRS 3.3 requires capabilities to sit
behind "clear abstract API adapters, enabling immediate hot-swapping", and
semantic analysis is the stage most likely to gain a statistical implementation:
Figure 6 shows the AI Runtime producing "Semantic Features", and a model served
through it satisfies this same contract without any consumer changing.

Why three inputs
----------------
Stages 9 and 10 take Stage 8's tree alone, because a name and a term are found in
the morpheme sequence. Stage 11 needs their *output* as well. Figure 5 orders the
pipeline 08 -> 09 -> 10 -> 11, and that order is load-bearing here: a Tibetan name
runs across several syllables, and Stage 8 -- working one morpheme at a time --
attaches each of them to the verb as a separate argument. Stage 9 is what says
those syllables are one thing. Without it the semantic graph would report a
four-participant event where the sentence has one participant with a long name.

Both annotations are optional, so a caller that has not run Stages 9 and 10 still
gets a graph. What it loses is the grouping, not correctness.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from teea.nlp.dependency import DependencyTree
from teea.nlp.ner import EntityAnnotation
from teea.nlp.semantics.models import SemanticGraph
from teea.nlp.terminology import TerminologyAnnotation


@runtime_checkable
class SemanticAnalyzer(Protocol):
    """A Tibetan semantic analyser contract.

    Implementations must be safe to share across threads for read-only use, as
    the daemon analyses many sentences concurrently.
    """

    def analyze(
        self,
        tree: DependencyTree,
        *,
        entities: EntityAnnotation | None = None,
        terms: TerminologyAnnotation | None = None,
    ) -> SemanticGraph:
        """Build the semantic graph for one parsed sentence.

        Implementations must be total with respect to *content*: an empty tree
        yields an empty graph rather than raising, matching the convention set by
        every earlier stage.

        They must **not** be total with respect to *coherence*. Annotations
        describing a different sentence are a caller error, not an input to
        interpret, and must be rejected rather than silently producing a graph
        whose spans address the wrong document.

        Nodes must be returned in surface order and must not overlap, and each
        must carry the exact span of the text it covers. Stage 11 interprets; it
        never re-segments, re-tags or re-parses.

        Args:
            tree: Stage 8 output for one sentence.
            entities: Stage 9 output for the same sentence, if available.
            terms: Stage 10 output for the same sentence, if available.

        Returns:
            The semantic graph.

        Raises:
            InputValidationError: If ``entities`` or ``terms`` was produced from
                a different source text than ``tree``.
        """
        ...


__all__ = ["SemanticAnalyzer"]
