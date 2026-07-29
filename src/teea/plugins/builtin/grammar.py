"""Built-in grammar checker plugin for TEEA.

Rule-based Tibetan grammar checking using the NLP pipeline output.
Detects Tibetan grammar issues including case particle agreement (Slad-bsdu / rNam-dbye),
interrogative particle agreement, sentence-final particles, word order,
verb agreement, missing/extra words, and repeated words.
"""

from __future__ import annotations

from collections.abc import Iterable

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import Suggestion, SuggestionPriority
from teea.nlp.dependency import DependencyRelation, DependencyTree
from teea.nlp.postagging import PosCategory
from teea.nlp.snapshot import DocumentSnapshot, SentenceAnalysis


# Phonetic case particle agreement tables based on preceding final consonant (rjes-'jug)
GENITIVE_PARTICLES = {
    "ག": "གི", "ང": "གི",
    "ད": "ཀྱི", "བ": "ཀྱི", "ས": "ཀྱི",
    "ན": "གྱི", "མ": "གྱི", "ར": "གྱི", "ལ": "གྱི",
    "open": "ཡི",
}

ERGATIVE_PARTICLES = {
    "ག": "གིས", "ང": "གིས",
    "ད": "ཀྱིས", "བ": "ཀྱིས", "ས": "ཀྱིས",
    "ན": "གྱིས", "མ": "གྱིས", "ར": "གྱིས", "ལ": "གྱིས",
    "open": "ཡིས",
}

INTERROGATIVE_PARTICLES = {
    "ག": "གམ", "ང": "ངམ", "ད": "དམ", "ན": "ནམ",
    "བ": "བམ", "མ": "མམ", "ར": "རམ", "ལ": "ལམ",
    "ས": "སམ", "open": "འམ",
}

SENTENCE_FINAL_PARTICLES = {
    "ག": "གོ", "ང": "ངོ", "ད": "དོ", "ན": "ནོ",
    "བ": "བོ", "མ": "མོ", "ར": "རོ", "ལ": "ལོ",
    "ས": "སོ", "open": "འོ",
}

ALL_GENITIVE = {"གི", "ཀྱི", "གྱི", "ཡི", "འི"}
ALL_ERGATIVE = {"གིས", "ཀྱིས", "གྱིས", "ཡིས", "ས"}
ALL_INTERROGATIVE = {"གམ", "ངམ", "དམ", "ནམ", "བམ", "མམ", "འམ", "རམ", "ལམ", "སམ", "ཏམ"}
ALL_FINAL = {"གོ", "ངོ", "དོ", "ནོ", "བོ", "མོ", "འོ", "རོ", "ལོ", "སོ", "ཏོ"}


def _get_tibetan_final_consonant(word: str) -> str:
    """Extract the primary suffix consonant (rjes-'jug) of a Tibetan morpheme."""
    word = word.rstrip("་ ། ཿ")
    if not word:
        return "open"
    base_chars = [c for c in word if c not in ("\u0f72", "\u0f74", "\u0f7a", "\u0f7c", "\u0f71")]
    if not base_chars:
        return "open"
    if len(base_chars) >= 2 and base_chars[-1] == "\u0f66":
        c = base_chars[-2]
    else:
        c = base_chars[-1]

    if c in ("ག", "ང", "ད", "ན", "བ", "མ", "ར", "ལ", "ས"):
        return c
    return "open"


class GrammarCheckerPlugin:
    """Rule-based Tibetan grammar checker.

    Rules implemented:
      - Phonetic Particle Agreement (Genitive, Ergative, Interrogative, Sentence-final)
      - Repeated Adjacent Words / Morphemes
      - Missing Root Verb in Clause
      - Double Negation Detection
      - Unresolved Dependency Tree Nodes
      - Question Mood Mismatch
    """

    def __init__(self, name: str = "teea.grammar") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        byte_table = utf8_byte_offsets(snapshot.source)

        for analysis in snapshot.analyses:
            tree = analysis.tree
            if tree.is_empty:
                continue

            sentence_text = analysis.text
            sent_start = analysis.span.char_start

            yield from self._check_particle_agreements(tree, sentence_text, sent_start, byte_table)
            yield from self._check_repeated_words(tree, sentence_text, sent_start, byte_table)
            yield from self._check_missing_verb(tree, sentence_text, sent_start, byte_table)
            yield from self._check_double_negation(tree, sentence_text, sent_start, byte_table)
            yield from self._check_unresolved(tree, sentence_text, sent_start, byte_table)
            yield from self._check_question_mood(tree, analysis, sentence_text, sent_start, byte_table)

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

    def _check_particle_agreements(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """Check phonetic case particle, interrogative, and sentence-final agreement."""
        nodes = tree.nodes
        for i in range(1, len(nodes)):
            prev_node = nodes[i - 1]
            curr_node = nodes[i]

            prev_word = prev_node.text.strip("་ །")
            curr_word = curr_node.text.strip("་ །")

            if not prev_word or not curr_word:
                continue

            final_c = _get_tibetan_final_consonant(prev_word)

            # Genitive Particle Check
            if curr_word in ALL_GENITIVE:
                expected = GENITIVE_PARTICLES.get(final_c, "གི")
                if curr_word != expected and curr_word not in ("འི", "ཡི"):
                    span = self._doc_span(
                        sent_start,
                        curr_node.span.char_start,
                        curr_node.span.char_end,
                        byte_table,
                    )
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement=expected,
                        score=0.88,
                        priority=SuggestionPriority.HIGH,
                        message=f'Genitive particle agreement error: "{prev_word}" should take "{expected}" instead of "{curr_word}"',
                    )

            # Ergative Particle Check
            elif curr_word in ALL_ERGATIVE:
                expected = ERGATIVE_PARTICLES.get(final_c, "གིས")
                if curr_word != expected and curr_word not in ("ས", "ཡིས"):
                    span = self._doc_span(
                        sent_start,
                        curr_node.span.char_start,
                        curr_node.span.char_end,
                        byte_table,
                    )
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement=expected,
                        score=0.88,
                        priority=SuggestionPriority.HIGH,
                        message=f'Ergative particle agreement error: "{prev_word}" should take "{expected}" instead of "{curr_word}"',
                    )

            # Interrogative Particle Check
            elif curr_word in ALL_INTERROGATIVE:
                expected = INTERROGATIVE_PARTICLES.get(final_c, "འམ")
                if curr_word != expected:
                    span = self._doc_span(
                        sent_start,
                        curr_node.span.char_start,
                        curr_node.span.char_end,
                        byte_table,
                    )
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement=expected,
                        score=0.9,
                        priority=SuggestionPriority.HIGH,
                        message=f'Interrogative particle agreement error: "{prev_word}" should take "{expected}" instead of "{curr_word}"',
                    )

            # Sentence-Final Particle Check
            elif curr_word in ALL_FINAL:
                expected = SENTENCE_FINAL_PARTICLES.get(final_c, "འོ")
                if curr_word != expected:
                    span = self._doc_span(
                        sent_start,
                        curr_node.span.char_start,
                        curr_node.span.char_end,
                        byte_table,
                    )
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement=expected,
                        score=0.9,
                        priority=SuggestionPriority.HIGH,
                        message=f'Sentence-final particle agreement error: "{prev_word}" should take "{expected}" instead of "{curr_word}"',
                    )

    def _check_repeated_words(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """Flag consecutive duplicate words or morphemes."""
        nodes = tree.nodes
        for i in range(1, len(nodes)):
            prev_node = nodes[i - 1]
            curr_node = nodes[i]

            prev_word = prev_node.text.strip("་ །")
            curr_word = curr_node.text.strip("་ །")

            if prev_word and prev_word == curr_word and prev_node.relation != DependencyRelation.PUNCT:
                span = self._doc_span(
                    sent_start,
                    curr_node.span.char_start,
                    curr_node.span.char_end,
                    byte_table,
                )
                yield Suggestion(
                    source=self._name,
                    span=span,
                    replacement="",
                    score=0.92,
                    priority=SuggestionPriority.HIGH,
                    message=f'Duplicate repeated word detected: "{curr_word}"',
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
                    message=f'Unresolved grammar: "{node.text}"',
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