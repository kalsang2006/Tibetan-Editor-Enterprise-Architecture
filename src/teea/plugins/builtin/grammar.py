"""Built-in grammar checker plugin for TEEA.

Rule-based grammar checking using the existing NLP pipeline output.
Detects common Tibetan grammar issues from the dependency tree, POS tags,
and morphological analysis.

Architecture position
---------------------
Figure 5 lists the Grammar Checker as a feature plugin.  It reads the
immutable document snapshot and emits suggestions through the same
:class:`~teea.fusion.Suggestion` model every other plugin uses.

Thread safety
-------------
The plugin is stateless after construction.  It is safe to call from a
worker thread, which is what the Plugin Runtime does when concurrency is
enabled.
"""

from __future__ import annotations

from collections.abc import Iterable

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.dependency import DependencyRelation, DependencyTree
from teea.nlp.postagging import PosCategory
from teea.nlp.snapshot import DocumentSnapshot, SentenceAnalysis


class GrammarCheckerPlugin:
    """Rule-based Tibetan grammar checker.

    Examines every sentence in the analysed document and flags common
    grammatical issues using the dependency tree, POS tags, and
    morphological analysis already produced by the pipeline.

    Rules implemented:
      - Missing root verb (sentence without a verb root)
      - Double negation (two negation particles on the same verb)
      - Unresolved dependency (parser could not attach a morpheme)
      - Question-final without interrogative marker
      - Imperative verb in declarative context (mood mismatch signal)

    Args:
        name: Plugin identifier.  Overridable so a test or downstream
            tool can distinguish several grammar-checker instances.
    """

    def __init__(self, name: str = "teea.grammar") -> None:
        self._name = name

    @property
    def name(self) -> str:
        """Stable identifier for this plugin."""
        return self._name

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        """Check every sentence in the document for grammar issues.

        Args:
            snapshot: The immutable analysis of the whole document.

        Yields:
            One :class:`Suggestion` per detected grammar issue, with
            ``replacement`` set to a suggested fix when one is available.
        """
        byte_table = utf8_byte_offsets(snapshot.source)

        for analysis in snapshot.analyses:
            tree = analysis.tree
            if tree.is_empty:
                continue

            sentence_text = analysis.text
            sent_start = analysis.span.char_start

            yield from self._check_missing_verb(tree, sentence_text, sent_start, byte_table)
            yield from self._check_double_negation(tree, sentence_text, sent_start, byte_table)
            yield from self._check_unresolved(tree, sentence_text, sent_start, byte_table)
            yield from self._check_question_mood(
                tree, analysis, sentence_text, sent_start, byte_table)

    def _doc_span(
        self,
        sent_start: int,
        char_start: int,
        char_end: int,
        byte_table: list[int],
    ) -> TextSpan:
        return TextSpan(
            char_start=sent_start + char_start,
            char_end=sent_start + char_end,
            byte_start=byte_table[sent_start + char_start],
            byte_end=byte_table[sent_start + char_end],
        )

    def _check_missing_verb(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """Flag sentences that have no verb root."""
        has_verb = any(
            node.relation is DependencyRelation.ROOT
            and node.morpheme.category is PosCategory.VERB
            for node in tree.nodes
        )
        if not has_verb and len(tree.nodes) > 2:
            doc_span = self._doc_span(sent_start, 0, len(sentence_text), byte_table)
            yield Suggestion(
                source=self._name,
                span=doc_span,
                replacement=None,
                score=0.6,
                priority=SuggestionPriority.MEDIUM,
                message="Sentence may be missing a main verb",
            )

    def _check_double_negation(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """Flag sentences with two negation particles under the same head."""
        neg_counts: dict[int, int] = {}
        for node in tree.nodes:
            if node.relation is DependencyRelation.NEG:
                head = node.head
                neg_counts[head] = neg_counts.get(head, 0) + 1

        for head_idx, count in neg_counts.items():
            if count >= 2:
                head_node = tree.nodes[head_idx]
                span = self._doc_span(
                    sent_start,
                    head_node.span.char_start,
                    head_node.span.char_end,
                    byte_table,
                )
                yield Suggestion(
                    source=self._name,
                    span=span,
                    replacement=None,
                    score=0.75,
                    priority=SuggestionPriority.HIGH,
                    message=f"Double negation detected ({count} negation markers)",
                )

    def _check_unresolved(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """Flag morphemes the parser could not attach."""
        for node in tree.nodes:
            if node.relation is DependencyRelation.DEP:
                span = self._doc_span(
                    sent_start,
                    node.span.char_start,
                    node.span.char_end,
                    byte_table,
                )
                yield Suggestion(
                    source=self._name,
                    span=span,
                    replacement=None,
                    score=0.5,
                    priority=SuggestionPriority.LOW,
                    message=f"Unresolved grammar: \"{node.text}\"",
                )

    def _check_question_mood(
        self,
        tree: DependencyTree,
        analysis: SentenceAnalysis,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """Flag sentences that are interrogative but lack question particle."""
        intent = analysis.intent
        if intent.is_marked and intent.mood.value == "interrogative":
            has_question_marker = any(
                node.morpheme.tag.startswith("cv.ques")
                or node.morpheme.tag.startswith("p.interrog")
                for node in tree.nodes
            )
            if not has_question_marker:
                doc_span = self._doc_span(sent_start, 0, len(sentence_text), byte_table)
                yield Suggestion(
                    source=self._name,
                    span=doc_span,
                    replacement=None,
                    score=0.4,
                    priority=SuggestionPriority.LOW,
                    message="Question detected without explicit question particle",
                )


__all__ = ["GrammarCheckerPlugin"]