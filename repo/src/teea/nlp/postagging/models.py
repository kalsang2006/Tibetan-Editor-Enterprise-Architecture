"""Immutable domain models produced by part-of-speech tagging.

These are the value objects that cross the boundary out of Stage 7 of the
language processing pipeline. Figure 5 states the stage's output directly:
*"Noun, Verb, Adjective · Particle & grammatical classes"*.

Two levels of granularity, on purpose
-------------------------------------
:class:`PosCategory` is exactly Figure 5's list -- the coarse classes plugins and
the add-in reason about ("underline the noun", "this verb disagrees"). But the
reference corpus distinguishes 77 tags, and collapsing them at the boundary would
destroy information Stage 8 needs: dependency parsing cares that a verb is
``v.past`` rather than ``v.imp``, and that a particle is ``case.agn`` rather than
``case.gen``, because those determine argument structure.

So every tagged morpheme carries both: :attr:`TaggedMorpheme.tag` preserves the
corpus tag verbatim, and :attr:`TaggedMorpheme.category` gives the Figure 5
class. Nothing is lost, and consumers pick the level they need.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, model_validator

from teea.core.types import TextSpan
from teea.nlp.morphology import Morpheme


@enum.unique
class PosCategory(enum.Enum):
    """Coarse part-of-speech class, as enumerated by Figure 5."""

    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    PARTICLE = "particle"
    PRONOUN = "pronoun"
    NUMERAL = "numeral"
    ADVERB = "adverb"
    DETERMINER = "determiner"
    PUNCTUATION = "punctuation"
    INTERJECTION = "interjection"
    #: Reserved for corpus tags that mark unanalysed material (Sanskrit
    #: loanwords, editorial "unknown" markers). Kept rather than forced into a
    #: real class, because guessing here would mislead Stage 8.
    UNKNOWN = "unknown"


#: Ordered longest-prefix-first, because ``n.v.*`` (deverbal nouns, tagged as
#: verbal in the corpus) must be tested before the bare ``n.`` prefix.
_TAG_PREFIXES: tuple[tuple[str, PosCategory], ...] = (
    ("n.v.", PosCategory.VERB),
    ("n.", PosCategory.NOUN),
    ("v.", PosCategory.VERB),
    ("adj", PosCategory.ADJECTIVE),
    ("case.", PosCategory.PARTICLE),
    ("cv.", PosCategory.PARTICLE),
    ("cl.", PosCategory.PARTICLE),
    ("neg", PosCategory.PARTICLE),
    ("p.", PosCategory.PRONOUN),
    ("num.", PosCategory.NUMERAL),
    ("adv.", PosCategory.ADVERB),
    ("d.", PosCategory.DETERMINER),
)

#: Tags that are their own category rather than a prefix family.
#:
#: ``skt`` (Sanskrit loanword) and ``dunno`` (editorial marker) are genuinely
#: unanalysed and map to UNKNOWN. ``interj`` is not: an interjection is a real
#: word class, and letting it fall through would report 29 analysed corpus tokens
#: as unanalysable, misleading Stage 8.
_TAG_EXACT: Mapping[str, PosCategory] = {
    "punc": PosCategory.PUNCTUATION,
    "interj": PosCategory.INTERJECTION,
    "skt": PosCategory.UNKNOWN,
    "dunno": PosCategory.UNKNOWN,
}


def coarse_category(tag: str) -> PosCategory:
    """Map a fine-grained corpus tag onto its Figure 5 class.

    The mapping covers all 77 tags observed in the reference corpus; anything
    unrecognised becomes :attr:`PosCategory.UNKNOWN` rather than raising, so a
    future corpus revision degrades gracefully instead of taking the daemon
    down.

    Args:
        tag: A fine-grained corpus tag such as ``"n.count"`` or ``"case.gen"``.

    Returns:
        The corresponding coarse class.
    """
    exact = _TAG_EXACT.get(tag)
    if exact is not None:
        return exact
    for prefix, category in _TAG_PREFIXES:
        if tag.startswith(prefix):
            return category
    return PosCategory.UNKNOWN


class TaggedMorpheme(BaseModel):
    """One morpheme with its resolved part of speech.

    Attributes:
        morpheme: The Stage 6 morpheme this tag applies to.
        tag: The fine-grained corpus tag chosen, e.g. ``"case.gen"``.
        category: The Figure 5 class implied by ``tag``.
        was_ambiguous: Whether Stage 6 left this surface undecided. This is the
            audit trail for the stage's main job: it records that a real choice
            was made here rather than a single reading merely being copied
            through.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    morpheme: Morpheme
    tag: str
    category: PosCategory
    was_ambiguous: bool = False

    @model_validator(mode="after")
    def _validate_consistency(self) -> TaggedMorpheme:
        if not self.tag:
            raise ValueError("tag must not be empty")
        if self.category is not coarse_category(self.tag):
            raise ValueError(f"category {self.category.value!r} does not match tag {self.tag!r}")
        return self

    @property
    def text(self) -> str:
        """The surface text of the underlying morpheme."""
        return self.morpheme.text

    @property
    def span(self) -> TextSpan:
        """The extent of the underlying morpheme."""
        return self.morpheme.span


class TaggedText(BaseModel):
    """The complete result of tagging one stretch of text.

    Attributes:
        source: The text that was tagged, exactly as supplied.
        morphemes: The tagged morphemes, in document order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    morphemes: tuple[TaggedMorpheme, ...] = ()

    @model_validator(mode="after")
    def _validate_consistency(self) -> TaggedText:
        previous_end = -1
        for position, tagged in enumerate(self.morphemes):
            span = tagged.span
            if span.char_start < previous_end:
                raise ValueError("morpheme spans must not overlap")
            if span.char_end > len(self.source):
                raise ValueError("morpheme span exceeds the source text")
            if self.source[span.char_start : span.char_end] != tagged.text:
                raise ValueError(f"morpheme {position} span does not select its own text")
            previous_end = span.char_end
        return self

    def __len__(self) -> int:
        """Number of tagged morphemes."""
        return len(self.morphemes)

    @property
    def num_morphemes(self) -> int:
        """Number of tagged morphemes."""
        return len(self.morphemes)

    @property
    def tags(self) -> tuple[str, ...]:
        """The fine-grained tag of each morpheme, in order."""
        return tuple(m.tag for m in self.morphemes)

    @property
    def categories(self) -> tuple[PosCategory, ...]:
        """The coarse class of each morpheme, in order."""
        return tuple(m.category for m in self.morphemes)

    @property
    def num_resolved(self) -> int:
        """How many morphemes Stage 6 left ambiguous and this stage decided."""
        return sum(1 for m in self.morphemes if m.was_ambiguous)

    def of_category(self, category: PosCategory) -> tuple[TaggedMorpheme, ...]:
        """Return every morpheme carrying ``category``.

        The primitive plugins reason with: a spell checker wants the nouns, a
        grammar checker the verbs and particles.
        """
        return tuple(m for m in self.morphemes if m.category is category)

    def morpheme_at_char(self, char_index: int) -> TaggedMorpheme | None:
        """Return the tagged morpheme whose span contains ``char_index``.

        Args:
            char_index: Character offset into :attr:`source`.

        Returns:
            The covering morpheme, or ``None`` if the offset falls in a gap or
            outside the text.
        """
        for tagged in self.morphemes:
            if tagged.span.char_start <= char_index < tagged.span.char_end:
                return tagged
        return None


__all__ = [
    "PosCategory",
    "TaggedMorpheme",
    "TaggedText",
    "coarse_category",
]
