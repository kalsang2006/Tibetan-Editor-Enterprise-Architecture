"""Immutable domain models produced by morphological analysis.

These are the value objects that cross the boundary out of Stage 6 (Morphological
Analysis) of the language processing pipeline. Figure 5 assigns this stage three
responsibilities -- *root extraction*, *affix recognition* and *inflection
analysis* -- and the models here carry all three results:

* :attr:`Morpheme.kind` distinguishes an extracted root from a recognized affix.
* :attr:`Morpheme.categories` carries the grammatical function of an affix.
* :attr:`Morpheme.is_fused` records whether the affix was written attached to its
  host, which is how Tibetan inflection is realised orthographically.

Why categories are a *set*
--------------------------
Stage 6 recognizes; Stage 7 (POS tagging) disambiguates. That split is forced by
the language, not by convenience: measured over the 60,544-token annotated
reference corpus, a quarter of the affix surfaces also occur as ordinary content
words. ``དེ`` is a demonstrative in 95% of its occurrences and a semi-final
converb in 5%; ``མི`` is the negation particle in 78% and the noun "person" in
22%. Committing to one reading here would be wrong far too often, so an affix
carries every category it could bear and :class:`MorphemeKind.AMBIGUOUS` marks
the surfaces that may not be affixes at all.

The same span discipline as every other stage applies: ``text`` is always exactly
the slice of the source named by ``span``, enforced by a validator rather than
left to convention.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, model_validator

from teea.core.types import TextSpan


@enum.unique
class MorphemeKind(enum.Enum):
    """What a morpheme is, as far as Stage 6 can determine on its own."""

    #: Lexical material: the root left after affixes are stripped.
    ROOT = "root"
    #: A grammatical affix, recognized with high confidence.
    AFFIX = "affix"
    #: A surface that is frequently an affix but also occurs as a content word.
    #: Stage 7 resolves it from context; Stage 6 must not guess.
    AMBIGUOUS = "ambiguous"


@enum.unique
class AffixCategory(enum.Enum):
    """Grammatical function of a Tibetan affix.

    The members correspond to the categories used by the annotated reference
    corpus, collapsed across its ``case.*``/``cv.*`` distinction. That
    distinction depends on whether the host is a noun or a verb, which is a
    part-of-speech judgement and therefore Stage 7's responsibility, not this
    stage's.
    """

    # Case / postpositional particles ---------------------------------------
    GENITIVE = "genitive"
    AGENTIVE = "agentive"
    ALLATIVE = "allative"
    TERMINATIVE = "terminative"
    LOCATIVE = "locative"
    ABLATIVE = "ablative"
    ELATIVE = "elative"
    ASSOCIATIVE = "associative"
    COMPARATIVE = "comparative"

    # Verbal / clause-linking suffixes ---------------------------------------
    SEMI_FINAL = "semi_final"
    IMPERFECTIVE = "imperfective"
    CONTINUATIVE = "continuative"
    FINAL = "final"
    IMPERATIVE = "imperative"
    INTERROGATIVE = "interrogative"
    CONCESSIVE = "concessive"

    # Clitics and determiners -------------------------------------------------
    FOCUS = "focus"
    QUOTATIVE = "quotative"
    NEGATION = "negation"
    INDEFINITE = "indefinite"


class Morpheme(BaseModel):
    """A single morpheme identified within a stretch of Tibetan text.

    Attributes:
        text: The morpheme exactly as it appears in the source.
        span: Character/byte extent of ``text`` in the analyzed source.
        kind: Whether this is a root, a recognized affix, or an ambiguous
            surface awaiting Stage 7 disambiguation.
        categories: Candidate grammatical functions. Empty for a root; one or
            more for an affix. More than one member means the surface is
            genuinely syncretic -- ``ཅིག`` is both an imperative marker and an
            indefinite determiner, for instance.
        is_fused: Whether the affix was written attached to its host syllable
            rather than as a free-standing one. The Tibetan genitive ``འི`` and
            its relatives attach directly, with no intervening tsheg.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    span: TextSpan
    kind: MorphemeKind
    categories: frozenset[AffixCategory] = frozenset()
    is_fused: bool = False

    @model_validator(mode="after")
    def _validate_consistency(self) -> Morpheme:
        """Enforce the invariants downstream stages rely upon."""
        if not self.text:
            raise ValueError("a morpheme must not be empty")
        if len(self.text) != self.span.char_length:
            raise ValueError(
                f"text length {len(self.text)} does not match span char_length "
                f"{self.span.char_length}"
            )
        if len(self.text.encode("utf-8")) != self.span.byte_length:
            raise ValueError("text UTF-8 length does not match span byte_length")
        if self.kind is MorphemeKind.ROOT and self.categories:
            raise ValueError("a root morpheme must not carry affix categories")
        if self.kind is not MorphemeKind.ROOT and not self.categories:
            raise ValueError(f"a {self.kind.value} morpheme must carry at least one category")
        if self.is_fused and self.kind is MorphemeKind.ROOT:
            raise ValueError("only an affix can be fused to a host")
        return self

    @property
    def is_affix(self) -> bool:
        """Whether this morpheme is grammatical rather than lexical.

        ``True`` for both confident and ambiguous affixes, since an ambiguous
        surface is still a *candidate* affix.
        """
        return self.kind is not MorphemeKind.ROOT

    @property
    def is_ambiguous(self) -> bool:
        """Whether Stage 7 must decide what this surface actually is."""
        return self.kind is MorphemeKind.AMBIGUOUS

    @property
    def category(self) -> AffixCategory | None:
        """The single category, when the morpheme is unambiguous.

        Returns ``None`` when the morpheme is a root or carries more than one
        candidate category. Callers that need to branch on a definite function
        should use this and treat ``None`` as "ask Stage 7".
        """
        if len(self.categories) == 1:
            return next(iter(self.categories))
        return None


class MorphologicalAnalysis(BaseModel):
    """The complete result of analyzing one stretch of text.

    Attributes:
        source: The text that was analyzed, exactly as supplied.
        morphemes: The morphemes found, in document order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    morphemes: tuple[Morpheme, ...] = ()

    @model_validator(mode="after")
    def _validate_consistency(self) -> MorphologicalAnalysis:
        """Enforce ordering and span-accuracy invariants."""
        previous_end = -1
        for position, morpheme in enumerate(self.morphemes):
            span = morpheme.span
            if span.char_start < previous_end:
                raise ValueError("morpheme spans must not overlap")
            if span.char_end > len(self.source):
                raise ValueError("morpheme span exceeds the source text")
            if self.source[span.char_start : span.char_end] != morpheme.text:
                raise ValueError(f"morpheme {position} span does not select its own text")
            previous_end = span.char_end
        return self

    def __len__(self) -> int:
        """Number of morphemes."""
        return len(self.morphemes)

    @property
    def num_morphemes(self) -> int:
        """Number of morphemes."""
        return len(self.morphemes)

    @property
    def roots(self) -> tuple[Morpheme, ...]:
        """The lexical morphemes, in order (Figure 5: *root extraction*)."""
        return tuple(m for m in self.morphemes if m.kind is MorphemeKind.ROOT)

    @property
    def affixes(self) -> tuple[Morpheme, ...]:
        """The grammatical morphemes, in order (Figure 5: *affix recognition*)."""
        return tuple(m for m in self.morphemes if m.is_affix)

    @property
    def root_text(self) -> str:
        """The concatenated root material, with affixes removed."""
        return "".join(m.text for m in self.roots)

    @property
    def has_ambiguity(self) -> bool:
        """Whether any morpheme needs Stage 7 to resolve it."""
        return any(m.is_ambiguous for m in self.morphemes)

    @property
    def categories(self) -> frozenset[AffixCategory]:
        """Every grammatical function present anywhere in the analysis."""
        return frozenset().union(*(m.categories for m in self.morphemes))

    def morpheme_at_char(self, char_index: int) -> Morpheme | None:
        """Return the morpheme whose span contains ``char_index``.

        Args:
            char_index: Character offset into :attr:`source`.

        Returns:
            The covering morpheme, or ``None`` if the offset falls in a gap
            (a delimiter) or outside the text.
        """
        for morpheme in self.morphemes:
            if morpheme.span.char_start <= char_index < morpheme.span.char_end:
                return morpheme
        return None


__all__ = [
    "AffixCategory",
    "Morpheme",
    "MorphemeKind",
    "MorphologicalAnalysis",
]
