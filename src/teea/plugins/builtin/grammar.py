"""Built-in grammar checker plugin for TEEA.

Rule-based Tibetan grammar checking using the NLP pipeline output.
Detects Tibetan grammar issues including case particle agreement (Slad-bsdu / rNam-dbye),
interrogative particle agreement, sentence-final particles, word order,
and repeated words.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

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

#: Every particle the grammar plugin recognises (genitive ∪ ergative ∪
#: interrogative ∪ sentence-final).  Used as a guard so the new lexical rules
#: never propose edits on function words.
ALL_PARTICLES = ALL_GENITIVE | ALL_ERGATIVE | ALL_INTERROGATIVE | ALL_FINAL

#: Dative / locative allomorphs, which are also function words but sit outside
#: the four particle families above.  Excluded from the lexical-rule variant
#: sets so a vowel mutation is never "corrected" into a locative particle
#: (e.g. དི -> དུ is not a repair, while དི -> དེ is).
_DATIVE_PARTICLES = frozenset({"རུ", "སུ", "ཏུ", "དུ", "ན", "ལ", "ར"})

#: Tibetan vowel signs whose single-letter mutation is a common spelling
#: error (vowel mutation), with the plausible alternates for each.
_VOWEL_SIGNS = frozenset("ིེོུ")
_VOWEL_CONFUSIONS = {
    "ི": ("ེ", "ུ", "ོ"),
    "ེ": ("ི", "ོ"),
    "ོ": ("ུ", "ི", "ེ"),
    "ུ": ("ོ", "ི", "ེ"),
}

#: Visually/auditorily confusable letter pairs (both directions where
#: listed) used by the character-confusion rule: ཤ↔ཞ, ཏ↔ད, ས↔ཤ, བ↔ང.
#: (ན↔ལ was dropped: both are real words and the pair produced clean-text
#: false positives like གསོན -> གསོལ, where frequency dominance cannot tell
#: a typo from a legitimately-used rarer word.)
_CHARACTER_CONFUSIONS = {
    "ཤ": ("ཞ", "ས"),
    "ཞ": ("ཤ",),
    "ཏ": ("ད",),
    "ད": ("ཏ",),
    "ས": ("ཤ",),
    "བ": ("ང",),
    "ང": ("བ",),
}

#: Copula / sentence-final forms that must never follow a newly-inserted
#: genitive particle (precision guard for the particle-omission rule).
_FINAL_COPULAS = frozenset({
    "ཡིན", "རེད", "ཡོད", "འདུག", "མེད", "སོང", "བྱུང",
    "བྱེད", "བྱས", "ཤོག", "ཅིང", "ཏེ", "སྟེ", "དེ", "ནི", "ཡང", "ཀྱང",
})

#: Personal / demonstrative pronouns that never take a preceding genitive
#: linker as the head of the phrase (precision guard: ``རིང་ང`` must never
#: become ``རིང་གི་ང``).
_PRONOUNS = frozenset({
    "ང", "ང་ཚོ", "ངས", "ཁོ", "ཁོང", "མོ", "མོང", "ཚོ", "ཁྱེད", "ཁྱོད",
    "དེ", "འདི", "ཕྱི", "གང", "གང་ཡིན", "སུ", "སུ་ཡིན",
})

#: A lexical-rule candidate must be this many times more frequent than the
#: questioned token before the rule attaches an edit, so common valid forms
#: (e.g. བདེ in clean text, at 233k vs the 11 occurrences of བདི) are never
#: rewritten while genuinely mutated spellings are caught.
_KNOWN_WORD_MIN_FREQ_RATIO = 10.0
#: When several known variants compete (e.g. བདི -> {བདེ, བདུ, བདོ}), the
#: most frequent must dominate the runner-up by this factor or the rule stays
#: silent (ambiguous mutations are not flagged).
_KNOWN_WORD_MIN_DOMINANCE = 10.0
#: A candidate must appear at least this many times in the corpus at all.
_KNOWN_WORD_MIN_CAND_FREQ = 5

#: Tibetan numerals, so the particle-omission rule never inserts a genitive
#: before/after a numeral (e.g. གི་གཉིས, ཀྱི་པད in clean corpus text).
_TIBETAN_NUMERALS = frozenset({
    "གཅིག", "གཉིས", "གསུམ", "བཞི", "ལྔ", "དྲུག", "བདུན",
    "བརྒྱད", "དགུ", "བཅུ", "བཅུ་གཅིག", "ཁྲི", "འབུམ", "སྟོང", "བྱ་", "ཕྲག",
})

_TSHEG = "\u0f0b"
_STRIP_CHARS = "་ །ཿ\u0f0b\u0f0d "

#: Minimum raw corpus count for each of the two attested bigrams that the
#: particle-omission rule (TIB-PART-OMIT-001) requires.  In a sparse corpus a
#: lone count is often noise; requiring a small minimum keeps the rule from
#: inserting particles between content words whose adjacency is merely
#: unattested rather than ungrammatical.
_MIN_PARTICLE_BIGRAM_COUNT = 2


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


@dataclass(frozen=True)
class _FallbackMorpheme:
    """Minimal stand-in for :class:`~teea.nlp.postagging.TaggedMorpheme`.

    Produced when the dependency tree is empty so the grammar checks can still
    run over a manually tsheg-split sentence. ``category`` is ``None`` because
    there is no POS analysis for a fallback token; the particle-rule guards
    treat ``None`` as "unknown" rather than skipping the token.
    """

    text: str = ""
    category: Any = None
    span: TextSpan | None = None


@dataclass(frozen=True)
class _FallbackNode:
    """Minimal stand-in for :class:`~teea.nlp.dependency.DependencyNode`.

    Carries only the surface attributes the grammar checks read (``text``,
    ``span``, ``relation``, ``morpheme``). ``relation`` and
    ``morpheme.category`` are ``None`` because a manually tokenized sentence
    carries no dependency or POS information.
    """

    text: str
    span: TextSpan
    relation: Any = None
    morpheme: _FallbackMorpheme = field(default_factory=_FallbackMorpheme)


@dataclass(frozen=True)
class _FallbackTree:
    """Duck-typed stand-in for a :class:`DependencyTree` with no parse.

    The grammar rule checks only read ``tree.nodes``, so carrying the
    pseudo-nodes under the same attribute keeps every check working unchanged.
    """

    nodes: tuple[_FallbackNode, ...] = ()


def _fallback_nodes(text: str, tokens: list[str]) -> list[_FallbackNode]:
    """Build pseudo-nodes for a manually tsheg-split sentence.

    Used when the dependency tree is empty so basic particle and word checks
    can still run instead of the sentence being skipped entirely.

    Args:
        text: The sentence text being tokenized.
        tokens: Non-empty tsheg-delimited tokens of ``text``, in surface order.

    Returns:
        One pseudo-node per token, with sentence-relative character and byte
        spans. Tokens containing no word characters (e.g. a lone shad) are
        skipped because they carry no checkable content.
    """
    nodes: list[_FallbackNode] = []
    cursor = 0
    for token in tokens:
        if not any(ch.isalnum() for ch in token):
            continue
        start = text.find(token, cursor)
        if start < 0:
            continue
        end = start + len(token)
        cursor = end
        nodes.append(
            _FallbackNode(
                text=token,
                span=TextSpan(
                    char_start=start,
                    char_end=end,
                    byte_start=len(text[:start].encode("utf-8")),
                    byte_end=len(text[:end].encode("utf-8")),
                ),
            )
        )
    return nodes


class GrammarCheckerPlugin:
    """Rule-based Tibetan grammar checker.

    Rules implemented:
      - Phonetic Particle Agreement (Genitive, Ergative, Interrogative, Sentence-final)
      - Existential Verb Spelling & Typos (TIB-EXIST-001)
      - Temporal Adverb Context (TIB-TEMP-001)
      - Honorific Subject-Verb Agreement (TIB-HONOR-001)
      - Copula & Evidential Agreement (TIB-COP-001)
      - SOV Word Order Validation (TIB-SOV-001)
      - Redundant Sentence-Final Nominalizer (TIB-NOM-001)
      - Repeated Adjacent Words / Morphemes
    """

    def __init__(
        self,
        name: str = "teea.grammar",
        registry: RuleRegistry | None = None,
        config_overrides: dict[str, Any] | None = None,
        dictionary: Any = None,
        corpus_repository: Any = None,
    ) -> None:
        self._name = name
        self._registry = registry or RuleRegistry(config_overrides)
        # Optional dictionary / corpus backing for the lexical rules
        # (TIB-VOWEL-001, TIB-CHAR-001, TIB-PART-OMIT-001).  When absent the
        # rules stay inert, so a bare ``GrammarCheckerPlugin()`` keeps working.
        self._dictionary = dictionary
        self._corpus_repository = corpus_repository

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
            sentence_text = analysis.text
            sent_start = analysis.span.char_start

            if tree.is_empty:
                # No dependency parse was produced, so fall back to a manual
                # tsheg tokenization to keep basic particle and word checks
                # running. The cast is safe: every check below only reads
                # ``tree.nodes``, which the fallback tree also exposes.
                tokens = [token for token in sentence_text.split("\u0f0b") if token.strip()]
                tree = cast(
                    DependencyTree, _FallbackTree(tuple(_fallback_nodes(sentence_text, tokens)))
                )

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
            yield from self._check_vowel_mutation(tree, sentence_text, sent_start, byte_table)
            yield from self._check_character_confusion(tree, sentence_text, sent_start, byte_table)
            yield from self._check_particle_omission(tree, sentence_text, sent_start, byte_table)

    def _check_contextual_semantics(
        self,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        return []

    # -- Lexical rules (dictionary- / corpus-backed) -------------------------

    def _known_word(self, word: str) -> bool:
        """Return whether ``word`` is attested in the optional dictionary.

        A bare plugin without a dictionary reports ``False`` so the lexical
        rules stay inert rather than hallucinating edits.
        """
        if self._dictionary is None:
            return False
        clean = word.strip(_STRIP_CHARS)
        if not clean:
            return True
        try:
            return clean in self._dictionary or word in self._dictionary
        except Exception:  # noqa: BLE001 - a failing dictionary must not break the plugin
            return False

    def _best_lexical_variant(self, raw: str, variants: set[str]) -> str | None:
        """Pick the corpus-dominant known variant for a mutated/confused token.

        Three corpus-backed guards, so the lexical rules stay precise:

        1. The best variant must clear ``_KNOWN_WORD_MIN_CAND_FREQ``
           occurrences in the corpus (a stray dictionary entry is not enough).
        2. When the token itself is known (e.g. བདི, a valid syllable), the
           best variant must be ``_KNOWN_WORD_MIN_FREQ_RATIO`` times more
           frequent than the token -- so བདི -> བདེ (233k vs 11) fires while
           a legitimately-common form like དེ is never rewritten (its variants
           are all rarer).  Unknown tokens (freq 0) only need the candidate
           minimum.
        3. When several known variants compete, the best must dominate the
           runner-up by ``_KNOWN_WORD_MIN_DOMINANCE`` or the rule stays
           silent -- ambiguous mutations (e.g. བདི could be བདེ/བདུ/བདོ) are
           not flagged unless one is overwhelmingly the intended form.

        Args:
            raw: The surface form being questioned.
            variants: The set of dictionary-known single-edit variants.

        Returns:
            The winning variant, or ``None`` when the corpus does not support
            attaching an edit.
        """
        if self._corpus_repository is None or not variants:
            return None
        try:
            ranked = sorted(
                (
                    (self._corpus_repository.get_syllable_frequency(v), v)
                    for v in variants
                ),
                reverse=True,
            )
            token_freq = self._corpus_repository.get_syllable_frequency(raw)
        except Exception:  # noqa: BLE001 - a failing corpus must not break the plugin
            return None
        best_freq, best = ranked[0]
        if best_freq < _KNOWN_WORD_MIN_CAND_FREQ:
            return None
        if best_freq < _KNOWN_WORD_MIN_FREQ_RATIO * max(token_freq, 1):
            return None
        if len(ranked) >= 2 and best_freq < _KNOWN_WORD_MIN_DOMINANCE * ranked[1][0]:
            return None
        return best

    def _ngram_count(self, table: dict[str, int], *parts: str) -> int:
        """Return the raw corpus n-gram count for ``parts`` across key variants.

        The corpus stores n-grams keyed with a mix of tsheg-terminated and
        tsheg-stripped forms (e.g. ``"སྦྱོང་ གི་"`` vs ``"སྦྱོང གི"``), so every
        combination is tried before concluding the n-gram is unattested.
        """
        if not table:
            return 0
        cleaned = [p.rstrip("་ །\u0f0b\u0f0d ") for p in parts]
        for mask in range(1 << len(parts)):
            tokens = [
                cleaned[j] + _TSHEG if (mask >> j) & 1 else cleaned[j]
                for j in range(len(parts))
            ]
            count = table.get(" ".join(tokens))
            if count:
                return int(count)
        return 0

    def _check_vowel_mutation(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """TIB-VOWEL-001: unknown token with one mutated vowel sign.

        Fires only when the token is unknown and exactly one single-vowel-sign
        substitution lands on an attested dictionary form, so ambiguity
        (several plausible vowel forms) stays silent.
        """
        if self._dictionary is None or not self._registry.is_enabled("TIB-VOWEL-001"):
            return
        rule = self._registry.get_rule("TIB-VOWEL-001")
        score = rule.confidence_baseline if rule else 0.85

        for node in tree.nodes:
            raw = node.text.strip(_STRIP_CHARS)
            if not raw or raw in ALL_PARTICLES:
                continue
            if raw in _PRONOUNS or len(raw) <= 1:
                # Pronouns (ང) and single-letter tokens (ང/བ/ད) are never a
                # mutated-content-word repair: mutating ང -> བ is a false
                # positive (བ is far more frequent in the corpus, so a pure
                # frequency gate would fire).
                continue
            if not any(v in raw for v in _VOWEL_SIGNS):
                continue
            variants: set[str] = set()
            for i, ch in enumerate(raw):
                for alt in _VOWEL_CONFUSIONS.get(ch, ()):
                    candidate = raw[:i] + alt + raw[i + 1:]
                    if not candidate or candidate in ALL_PARTICLES or candidate in _DATIVE_PARTICLES:
                        continue
                    if self._known_word(candidate):
                        variants.add(candidate)
            # Corpus dominance decides: one unambiguous, far-more-frequent
            # variant (e.g. བདི -> བདེ) fires; ambiguous or weak cases stay
            # silent.  This is what makes the rule safe on dictionary-known
            # tokens like བདི / དི / སེས.
            candidate = self._best_lexical_variant(raw, variants)
            if candidate is None:
                continue
            replacement = candidate + node.text[len(raw):]
            span = self._doc_span(
                sent_start, node.span.char_start, node.span.char_end, byte_table
            )
            yield Suggestion(
                source=self._name,
                span=span,
                replacement=replacement,
                score=score,
                priority=SuggestionPriority.HIGH,
                message=(
                    f'[TIB-VOWEL-001] Vowel mutation: "{raw}" may be a '
                    f'mutated spelling of "{candidate}"'
                ),
                error_type="GRAMMAR",
            )

    def _check_character_confusion(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """TIB-CHAR-001: unknown token with one confusable-letter substitution.

        Covers ཤ↔ཞ, ཏ↔ད, ས↔ཤ, བ↔ང and ན↔ལ.  Fires only when the token is
        unknown and exactly one single-letter substitution is attested.
        """
        if self._dictionary is None or not self._registry.is_enabled("TIB-CHAR-001"):
            return
        rule = self._registry.get_rule("TIB-CHAR-001")
        score = rule.confidence_baseline if rule else 0.85

        for node in tree.nodes:
            raw = node.text.strip(_STRIP_CHARS)
            if not raw or raw in ALL_PARTICLES:
                continue
            if raw in _PRONOUNS or len(raw) <= 1:
                continue
            variants: set[str] = set()
            for i, ch in enumerate(raw):
                for alt in _CHARACTER_CONFUSIONS.get(ch, ()):
                    candidate = raw[:i] + alt + raw[i + 1:]
                    if not candidate or candidate in ALL_PARTICLES or candidate in _DATIVE_PARTICLES:
                        continue
                    if self._known_word(candidate):
                        variants.add(candidate)
            # Same corpus-dominance gate as TIB-VOWEL-001 (e.g. སེས -> ཤེས
            # with 895k vs 50 occurrences fires; ambiguous cases stay silent).
            candidate = self._best_lexical_variant(raw, variants)
            if candidate is None:
                continue
            replacement = candidate + node.text[len(raw):]
            span = self._doc_span(
                sent_start, node.span.char_start, node.span.char_end, byte_table
            )
            yield Suggestion(
                source=self._name,
                span=span,
                replacement=replacement,
                score=score,
                priority=SuggestionPriority.HIGH,
                message=(
                    f'[TIB-CHAR-001] Character confusion: "{raw}" may be '
                    f'a misspelling of "{candidate}"'
                ),
                error_type="GRAMMAR",
            )

    def _check_particle_omission(
        self,
        tree: DependencyTree,
        sentence_text: str,
        sent_start: int,
        byte_table: list[int],
    ) -> Iterable[Suggestion]:
        """TIB-PART-OMIT-001: missing genitive particle between two content words.

        Data-driven: the expected genitive particle ``p`` (from the previous
        word's final consonant) is re-inserted only when the corpus attests
        both ``A p`` and ``p B`` bigrams while the bare ``A B`` adjacency is
        unattested -- so genuine noun compounds (``བོད་སྐད``) never fire.
        When trigram data is available the rule additionally requires that
        ``A p B`` is attested (eliminates most false positives on clean text).
        When trigrams are unavailable, ``B`` must be a noun.
        """
        if (
            self._corpus_repository is None
            or not self._registry.is_enabled("TIB-PART-OMIT-001")
        ):
            return
        rule = self._registry.get_rule("TIB-PART-OMIT-001")
        score = rule.confidence_baseline if rule else 0.80
        bigrams = getattr(self._corpus_repository, "bigrams", None) or {}
        trigrams = getattr(self._corpus_repository, "trigrams", None) or {}

        nodes = tree.nodes
        i = 1
        while i < len(nodes):
            a_raw = nodes[i - 1].text
            b_raw = nodes[i].text
            a = a_raw.strip(_STRIP_CHARS)
            b = b_raw.strip(_STRIP_CHARS)
            if not a or not b or a in ALL_PARTICLES or b in ALL_PARTICLES:
                i += 1
                continue
            if b in _PRONOUNS or a in _TIBETAN_NUMERALS or b in _TIBETAN_NUMERALS:
                i += 1
                continue
            if not any("\u0f40" <= c <= "\u0fbc" for c in a + b):
                i += 1
                continue
            if not self._known_word(a) or not self._known_word(b):
                i += 1
                continue
            if b in _FINAL_COPULAS or b.endswith("འོ") or b.endswith("འི"):
                i += 1
                continue
            # POS-backed guard: when the dependency parse identifies the head
            # (``b``) as a verb / adverb / particle, a genitive linker never
            # belongs there (e.g. བཤད is a verb).  Unknown POS (None, fallback
            # trees) is allowed through.
            b_cat = getattr(nodes[i].morpheme, "category", None)
            if b_cat in (PosCategory.ADVERB, PosCategory.PARTICLE):
                i += 1
                continue
            # Same guard on the modifier ``a``: a verb/adverb (e.g. ཕྱིན
            # before སྐབས) never takes a genitive linker, so ཕྱིན་གྱི་སྐབས is
            # wrong (it would be ཕྱིན་སྐབས or ཕྱིན་པའི་སྐབས).
            a_cat = getattr(nodes[i - 1].morpheme, "category", None)
            if a_cat in (PosCategory.ADVERB, PosCategory.PARTICLE):
                i += 1
                continue
            a_syls = [s for s in a.split(_TSHEG) if s]
            a_last = a_syls[-1] if a_syls else a
            final_c = _get_tibetan_final_consonant(a_last)
            particle = GENITIVE_PARTICLES.get(final_c)
            if particle not in ("གི", "ཀྱི", "གྱི"):
                i += 1
                continue
            if self._ngram_count(bigrams, a_last, b) > 0:
                i += 1
                continue
            # Both candidate bigrams must be *well attested* (not just present):
            # in a sparse corpus a lone count often reflects noise, and requiring
            # a minimum keeps the rule from inserting particles between content
            # words that happen to be adjacent in an unattested bigram.
            if self._ngram_count(bigrams, a_last, particle) < _MIN_PARTICLE_BIGRAM_COUNT:
                i += 1
                continue
            if self._ngram_count(bigrams, particle, b) < _MIN_PARTICLE_BIGRAM_COUNT:
                i += 1
                continue
            # Trigram guard: when the corpus contains trigrams, require the
            # full sequence ``a_last particle b`` to be attested.  This
            # eliminates FPs where (a,p) and (p,b) are individually common
            # but ``a p b`` never occurs (e.g. གསེར གྱི ཕྲེང).
            if trigrams:
                if self._ngram_count(trigrams, a_last, particle, b) < 1:
                    i += 1
                    continue
            else:
                # Fallback: without trigrams restrict to b being a noun.
                if b_cat is not None and b_cat != PosCategory.NOUN:
                    i += 1
                    continue
            replacement = particle + _TSHEG + b_raw
            span = self._doc_span(
                sent_start, nodes[i].span.char_start, nodes[i].span.char_end, byte_table
            )
            yield Suggestion(
                source=self._name,
                span=span,
                replacement=replacement,
                score=score,
                priority=SuggestionPriority.HIGH,
                message=(
                    f'[TIB-PART-OMIT-001] Missing genitive particle: expected '
                    f'"{particle}" between "{a}" and "{b}"'
                ),
                error_type="GRAMMAR",
            )
            # Skip-ahead: after inserting a particle before ``b``, the next
            # adjacent pair (b, c) is checked against the *unmodified* tree and
            # would cascade a second spurious insertion into the same phrase
            # (observed: 3 insertions in one sentence).  Jump past the head so
            # at most one particle is inserted per phrase window.
            i += 2

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
                # Guard: 'གི' after verbs (e.g. 'འགྲོ་གི') is an aspectual/continuative particle, not a genitive noun modifier
                if curr_word == "གི" and (prev_node.morpheme.category == PosCategory.VERB or prev_node.relation in (DependencyRelation.ROOT, DependencyRelation.AUX) or prev_word in ("འགྲོ", "བྱེད", "ཡོད", "མེད", "ཡིན", "རེད", "སླེབས", "བཞིན")):
                    continue
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
                    if len(child.text.strip("་ ")) <= 1:
                        continue
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
                            replacement=f"{child.text} {node.text}",
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
        return []

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