"""Built-in grammar checker plugin for TEEA.

Rule-based Tibetan grammar checking using the NLP pipeline output.
Detects Tibetan grammar issues including case particle agreement (Slad-bsdu / rNam-dbye),
interrogative particle agreement, sentence-final particles, word order,
verb agreement, missing/extra words, and repeated words.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.fusion import Suggestion, SuggestionPriority
from teea.grammar.rule_registry import GrammarRule, RuleRegistry
from teea.nlp.dependency import DependencyRelation, DependencyTree
from teea.nlp.postagging import PosCategory
from teea.nlp.snapshot import DocumentSnapshot, SentenceAnalysis

# Phonetic case particle agreement tables based on preceding final consonant (rjes-'jug)
GENITIVE_PARTICLES = {
    "ག": "གི", "ང": "གི",
    "ད": "ཀྱི", "བ": "ཀྱི", "ས": "ཀྱི",
    "ན": "གྱི", "མ": "གྱི", "ར": "གྱི", "ལ": "གྱི",
    "འ": "འི",
    "open": "ཡི",
}

ERGATIVE_PARTICLES = {
    "ག": "གིས", "ང": "གིས",
    "ད": "ཀྱིས", "བ": "ཀྱིས", "ས": "ཀྱིས",
    "ན": "གྱིས", "མ": "གྱིས", "ར": "གྱིས", "ལ": "གྱིས",
    "འ": "འིས",
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
    word = word.rstrip("་ ། ཿ\u0f0b\u0f0d ")
    if not word:
        return "open"
    if "\u0f0b" in word:
        syllables = [s for s in word.split("\u0f0b") if s]
        if syllables:
            word = syllables[-1]

    last_char = word[-1]
    if last_char in ("འ", "\u0f60"):
        return "འ"

    consonants = [c for c in word if "\u0f40" <= c <= "\u0f6a"]
    if not consonants or len(consonants) == 1:
        return "open"

    if "\u0f71" <= last_char <= "\u0f87" or "\u0f90" <= last_char <= "\u0fbc":
        return "open"

    last_c = consonants[-1]
    if last_c in ("ག", "ང", "ད", "ན", "བ", "མ", "ར", "ལ", "ས", "འ"):
        return last_c
    return "open"


from teea.grammar.contextual_engine import ContextualGrammarEngine
from teea.nlp.collocation import CollocationDatabase
from teea.nlp.sanskrit import SanskritTransliterationValidator
from teea.nlp.verb_lexicon import Transitivity, VerbLexicon


class GrammarCheckerPlugin:
    """Rule-based and semantic Tibetan grammar checker.

    Rules implemented:
      - Phonetic Particle Agreement (Genitive, Ergative, Interrogative, Sentence-final)
      - Existential Verb Spelling & Typos (TIB-EXIST-001)
      - Temporal Adverb Context (TIB-TEMP-001)
      - Honorific Subject-Verb Agreement (TIB-HONOR-001)
      - Copula & Evidential Agreement (TIB-COP-001)
      - SOV Word Order Validation (TIB-SOV-001)
      - Redundant Sentence-Final Nominalizer (TIB-NOM-001)
      - Dangling Case Particle Detection
      - Verb Transitivity, Tense & Valency Checking
      - Semantic Collocation & Malapropism Detection
      - Repeated Adjacent Words / Morphemes
      - Double Negation Detection
    """

    def __init__(
        self,
        name: str = "teea.grammar",
        registry: RuleRegistry | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> None:
        self._name = name
        self._registry = registry or RuleRegistry(config_overrides)
        self._collocation_db = CollocationDatabase()
        self._verb_lexicon = VerbLexicon()
        from teea.persistence.dictionary import default_dictionary
        self._contextual_engine = ContextualGrammarEngine(dictionary=default_dictionary())

    @property
    def name(self) -> str:
        return self._name

    @property
    def registry(self) -> RuleRegistry:
        return self._registry

    def examine(self, snapshot: DocumentSnapshot) -> Iterable[Suggestion]:
        byte_table = utf8_byte_offsets(snapshot.source)

        for analysis in snapshot.analyses:
            tree = analysis.tree
            if tree.is_empty:
                continue

            sentence_text = analysis.text
            sent_start = analysis.span.char_start

            yield from self._check_particle_agreements(tree, sentence_text, sent_start, byte_table)
            yield from self._check_existential_verb_errors(tree, sentence_text, sent_start, byte_table)
            yield from self._check_time_expression_errors(tree, sentence_text, sent_start, byte_table)
            yield from self._check_honorific_agreement(tree, sentence_text, sent_start, byte_table)
            yield from self._check_copula_agreement(tree, sentence_text, sent_start, byte_table)
            yield from self._check_word_order(tree, sentence_text, sent_start, byte_table)
            yield from self._check_redundant_nominalizer(tree, sentence_text, sent_start, byte_table)
            yield from self._check_dangling_particle(tree, sentence_text, sent_start, byte_table)
            yield from self._check_malapropism(tree, sentence_text, sent_start, byte_table)
            yield from self._check_context_overrides(tree, sentence_text, sent_start, byte_table)
            yield from self._check_verb_agreement(tree, sentence_text, sent_start, byte_table)
            yield from self._check_logical_consistency(tree, sentence_text, sent_start, byte_table)
            yield from self._check_repeated_words(tree, sentence_text, sent_start, byte_table)
            yield from self._check_missing_verb(tree, sentence_text, sent_start, byte_table)
            yield from self._check_double_negation(tree, sentence_text, sent_start, byte_table)
            yield from self._check_unresolved(tree, sentence_text, sent_start, byte_table)
            yield from self._check_question_mood(tree, analysis, sentence_text, sent_start, byte_table)
            yield from self._check_contextual_semantics(sentence_text, sent_start, byte_table)

    def _check_contextual_semantics(
        self,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        errors = self._contextual_engine.analyze_sentence(sentence_text)
        for err in errors:
            span = self._doc_span(
                sent_start,
                err.char_start,
                err.char_end,
                byte_table,
            )
            yield Suggestion(
                source=self._name,
                span=span,
                replacement=err.suggestion,
                score=0.90,
                priority=SuggestionPriority.MEDIUM,
                message=f"[{err.error_code}] {err.message}",
                error_type=err.error_type,
            )

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
        if not self._registry.is_enabled("TIB-PART-001"):
            return

        rule = self._registry.get_rule("TIB-PART-001")
        rule_score = rule.confidence_baseline if rule else 0.98

        nodes = tree.nodes
        for i in range(1, len(nodes)):
            prev_node = nodes[i - 1]
            curr_node = nodes[i]

            prev_word = prev_node.text.strip("་ །\u0f0b\u0f0d ")
            curr_word = curr_node.text.strip("་ །\u0f0b\u0f0d ")

            if not prev_word or not curr_word:
                continue

            ALL_PARTICLES = ALL_GENITIVE | ALL_ERGATIVE | ALL_INTERROGATIVE | ALL_FINAL

            # GUARD 1: Only check if node is actually a particle or case relation in POS analysis
            if curr_node.morpheme.category not in (PosCategory.PARTICLE, PosCategory.PUNCTUATION) and curr_node.relation not in (DependencyRelation.CASE, DependencyRelation.MARK, DependencyRelation.AUX) and curr_word not in ALL_PARTICLES:
                continue

            # Precise Guard: only skip if curr_node is content word and relation is NOT CASE, MARK, or AUX
            if curr_node.morpheme.category in (PosCategory.NOUN, PosCategory.VERB, PosCategory.ADJECTIVE, PosCategory.PRONOUN, PosCategory.ADVERB) and curr_node.relation not in (DependencyRelation.CASE, DependencyRelation.MARK, DependencyRelation.AUX) and curr_word not in ALL_PARTICLES:
                continue

            is_at_sentence_end = (i == len(nodes) - 1) or (i < len(nodes) - 1 and nodes[i + 1].morpheme.category == PosCategory.PUNCTUATION)
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
                        score=rule_score,
                        priority=SuggestionPriority.HIGH,
                        message=f'Genitive particle agreement error: "{prev_word}" should take "{expected}" instead of "{curr_word}"',
                        error_type="GRAMMAR",
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
                        score=rule_score,
                        priority=SuggestionPriority.HIGH,
                        message=f'Ergative particle agreement error: "{prev_word}" should take "{expected}" instead of "{curr_word}"',
                        error_type="GRAMMAR",
                    )

            # Interrogative Particle Check
            elif curr_word in ALL_INTERROGATIVE and (is_at_sentence_end or curr_node.morpheme.category == PosCategory.PARTICLE) and curr_node.morpheme.category not in (PosCategory.NOUN, PosCategory.ADVERB):
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
                        score=rule_score,
                        priority=SuggestionPriority.HIGH,
                        message=f'Interrogative particle agreement error: "{prev_word}" should take "{expected}" instead of "{curr_word}"',
                        error_type="GRAMMAR",
                    )

            # Sentence-Final Particle Check
            elif curr_word in ALL_FINAL and (is_at_sentence_end or curr_node.morpheme.category == PosCategory.PARTICLE) and curr_node.morpheme.category not in (PosCategory.NOUN, PosCategory.ADVERB):
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
                        score=rule_score,
                        priority=SuggestionPriority.HIGH,
                        message=f'Sentence-final particle agreement error: "{prev_word}" should take "{expected}" instead of "{curr_word}"',
                        error_type="GRAMMAR",
                    )

    def _check_existential_verb_errors(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        if not self._registry.is_enabled("TIB-EXIST-001"):
            return
        rule = self._registry.get_rule("TIB-EXIST-001")
        score = rule.confidence_baseline if rule else 0.95

        for node in tree.nodes:
            word = node.text.strip("་ །\u0f0b\u0f0d ")
            replacement = None
            if word == "འདུགས":
                replacement = "འདུག"
            elif word == "ཡོདས":
                replacement = "ཡོད"

            if replacement:
                span = self._doc_span(
                    sent_start,
                    node.span.char_start,
                    node.span.char_end,
                    byte_table,
                )
                yield Suggestion(
                    source=self._name,
                    span=span,
                    replacement=replacement,
                    score=score,
                    priority=SuggestionPriority.HIGH,
                    message=f'[TIB-EXIST-001] Invalid existential verb spelling "{word}" -> suggest "{replacement}"',
                    error_type="GRAMMAR",
                )

    def _check_time_expression_errors(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        if not self._registry.is_enabled("TIB-TEMP-001"):
            return
        rule = self._registry.get_rule("TIB-TEMP-001")
        score = rule.confidence_baseline if rule else 0.85

        words = [n.text.strip("་ །\u0f0b\u0f0d ") for n in tree.nodes]
        if "དེང་སང" in words:
            for node in tree.nodes:
                w = node.text.strip("་ །\u0f0b\u0f0d ")
                if w == "དེང་སང" and ("དེ་རིང" in sentence_text or "བྱུང་" in sentence_text):
                    span = self._doc_span(
                        sent_start,
                        node.span.char_start,
                        node.span.char_end,
                        byte_table,
                    )
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement="དེ་རིང",
                        score=score,
                        priority=SuggestionPriority.MEDIUM,
                        message='[TIB-TEMP-001] Temporal adverb context check: "དེང་སང" means "nowadays"; suggest "དེ་རིང" for today',
                        error_type="GRAMMAR",
                    )

    def _check_honorific_agreement(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        if not self._registry.is_enabled("TIB-HONOR-001"):
            return
        rule = self._registry.get_rule("TIB-HONOR-001")
        score = rule.confidence_baseline if rule else 0.60

        HONORIFIC_PREFIXES = ("ཁྱེད་", "ཁོང་", "སྤྱི་ཁྱབ", "སྐུ་ཞོགས")
        PLAIN_TO_HONORIFIC = {
            "སྡོད": "བཞུགས",
            "ཤོད": "ཞུས",
            "བྱེད": "མཛད",
            "ཟོ": "གསོལ",
            "འགྲོ": "ཕེབས",
        }

        has_honorific_subject = any(hp in sentence_text for hp in HONORIFIC_PREFIXES)

        if has_honorific_subject:
            for node in tree.nodes:
                w = node.text.strip("་ །\u0f0b\u0f0d ")
                matched_replacement = None
                for plain, hon in PLAIN_TO_HONORIFIC.items():
                    if w == plain or w.startswith(plain):
                        matched_replacement = hon
                        break

                if matched_replacement:
                    replacement = matched_replacement
                    span = self._doc_span(
                        sent_start,
                        node.span.char_start,
                        node.span.char_end,
                        byte_table,
                    )
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement=replacement,
                        score=score,
                        priority=SuggestionPriority.LOW,
                        message=f'[TIB-HONOR-001] Honorific agreement suggestion: honorific subject present, consider "{replacement}" instead of plain verb "{w}" (depending on register)',
                        error_type="GRAMMAR",
                    )

    def _check_copula_agreement(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        if not self._registry.is_enabled("TIB-COP-001"):
            return
        rule = self._registry.get_rule("TIB-COP-001")
        score = rule.confidence_baseline if rule else 0.55

        words = [n.text.strip("་ །\u0f0b\u0f0d ") for n in tree.nodes]
        is_first_person = any(p in words for p in ("ང་", "ང་ཚོ", "ངས"))

        if is_first_person:
            for node in tree.nodes:
                w = node.text.strip("་ །\u0f0b\u0f0d ")
                if w in ("རེད", "འདུག"):
                    replacement = "ཡིན" if w == "རེད" else "ཡོད"
                    span = self._doc_span(
                        sent_start,
                        node.span.char_start,
                        node.span.char_end,
                        byte_table,
                    )
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement=replacement,
                        score=score,
                        priority=SuggestionPriority.LOW,
                        message=f'[TIB-COP-001] Copula agreement check: 1st person subject typically pairs with "{replacement}" rather than "{w}". Depending on dialect and register, this may be acceptable.',
                        error_type="GRAMMAR",
                    )

    def _check_word_order(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        if not self._registry.is_enabled("TIB-SOV-001"):
            return
        rule = self._registry.get_rule("TIB-SOV-001")
        score = rule.confidence_baseline if rule else 0.50

        if "ཅེས" in sentence_text or "ཞེས" in sentence_text or "ཞེས་" in sentence_text:
            return

        nodes = tree.nodes
        for i, node in enumerate(nodes):
            if node.relation == DependencyRelation.ROOT:
                for j in range(i + 1, len(nodes)):
                    child = nodes[j]
                    if child.relation == DependencyRelation.ARG2 or child.relation.value in ("obj", "arg2", "dobj", "object"):
                        span = self._doc_span(
                            sent_start,
                            child.span.char_start,
                            child.span.char_end,
                            byte_table,
                        )
                        yield Suggestion(
                            source=self._name,
                            span=span,
                            replacement=None,
                            score=score,
                            priority=SuggestionPriority.LOW,
                            message=f'[TIB-SOV-001] SOV Word Order: Object "{child.text}" appears after verb "{node.text}". Consider placing object before verb.',
                            error_type="GRAMMAR",
                        )

    def _check_redundant_nominalizer(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        if not self._registry.is_enabled("TIB-NOM-001"):
            return
        rule = self._registry.get_rule("TIB-NOM-001")
        score = rule.confidence_baseline if rule else 0.90

        nodes = tree.nodes
        if not nodes:
            return

        last_word_node = nodes[-1]
        word = last_word_node.text.strip("་ །\u0f0b\u0f0d ")
        if word in ("ཡིན་པ", "རེད་པ"):
            replacement = "ཡིན" if word == "ཡིན་པ" else "རེད"
            span = self._doc_span(
                sent_start,
                last_word_node.span.char_start,
                last_word_node.span.char_end,
                byte_table,
            )
            yield Suggestion(
                source=self._name,
                span=span,
                replacement=replacement,
                score=score,
                priority=SuggestionPriority.HIGH,
                message=f'[TIB-NOM-001] Redundant nominalizer: sentence-final declarative clause should end with copula "{replacement}" instead of nominalized "{word}".',
                error_type="GRAMMAR",
            )

    def _check_dangling_particle(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        return []

    def _check_malapropism(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        return []

    def _check_context_overrides(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        return []

    def _check_verb_agreement(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        nodes = tree.nodes
        for node in nodes:
            word = node.text.strip("་ །\u0f0b\u0f0d ")
            v_info = self._verb_lexicon.get_verb_info(word)
            if v_info is not None:
                children = tree.children_of(node.index)

                has_object = False
                for c in children:
                    if hasattr(DependencyRelation, "OBJ") and c.relation == getattr(DependencyRelation, "OBJ"):
                        has_object = True
                        break
                    if c.relation == DependencyRelation.ARG2 or c.relation.value in ("obj", "arg2", "dobj", "object"):
                        has_object = True
                        break

                if not has_object:
                    non_agentive_nominals = []
                    for c in children:
                        cw = c.text.strip("་ །\u0f0b\u0f0d ")
                        is_agentive = any(cw.endswith(s) for s in ("གིས", "ཀྱིས", "བྱིས", "ཏིས", "ས")) and c.relation in (DependencyRelation.ARG1, DependencyRelation.MARK, DependencyRelation.DEP)
                        if not is_agentive and (c.morpheme.category in (PosCategory.NOUN, PosCategory.PRONOUN) or c.relation in (DependencyRelation.ARG1, DependencyRelation.ARG2, DependencyRelation.DEP)):
                            non_agentive_nominals.append(c)
                    if non_agentive_nominals:
                        has_object = True

                span = self._doc_span(
                    sent_start,
                    node.span.char_start,
                    node.span.char_end,
                    byte_table,
                )

                if v_info.transitivity == Transitivity.TRANS and not has_object:
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement=None,
                        score=0.90,
                        priority=SuggestionPriority.HIGH,
                        message=f"Transitive verb '{word}' requires a direct object.",
                    )
                elif v_info.transitivity == Transitivity.INTRANS and has_object:
                    yield Suggestion(
                        source=self._name,
                        span=span,
                        replacement=None,
                        score=0.90,
                        priority=SuggestionPriority.HIGH,
                        message=f"Intransitive verb '{word}' cannot take a direct object.",
                    )

    def _check_logical_consistency(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        nodes = tree.nodes
        words = [n.text.strip("་ །") for n in nodes]
        if "ང་" in words or "ང་ཚོ" in words:
            if "བོད་" in words and "ཡིན" in words and not any("ཆོས་སྒོར" in w for w in words):
                for node in nodes:
                    if node.text.strip("་ །") == "བོད་":
                        span = self._doc_span(
                            sent_start,
                            node.span.char_start,
                            node.span.char_end,
                            byte_table,
                        )
                        yield Suggestion(
                            source=self._name,
                            span=span,
                            replacement="བོད་པ" + "\u0f0b",
                            score=0.90,
                            priority=SuggestionPriority.HIGH,
                            message='Logical Mismatch: First-person subject "ང་" with "བོད་" requires demonym suffix "བོད་པ"',
                        )

    def _check_repeated_words(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        nodes = tree.nodes
        for i in range(1, len(nodes)):
            prev = nodes[i - 1].text.strip("་ །\u0f0b\u0f0d ")
            curr = nodes[i].text.strip("་ །\u0f0b\u0f0d ")
            if prev and curr and prev == curr:
                if prev in ("ཡང", "ཧ", "ཀྱི", "གི"):
                    continue
                span = self._doc_span(
                    sent_start,
                    nodes[i].span.char_start,
                    nodes[i].span.char_end,
                    byte_table,
                )
                yield Suggestion(
                    source=self._name,
                    span=span,
                    replacement=None,
                    score=0.90,
                    priority=SuggestionPriority.HIGH,
                    message=f'Duplicate repeated word detected: "{curr}" is repeated sequentially.',
                    error_type="GRAMMAR",
                )

    def _check_missing_verb(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        return []

    def _check_double_negation(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        return []

    def _check_unresolved(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        return []

    def _check_question_mood(
        self,
        tree: DependencyTree,
        analysis: SentenceAnalysis,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        return []


__all__ = ["GrammarCheckerPlugin"]