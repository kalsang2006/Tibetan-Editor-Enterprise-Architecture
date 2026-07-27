"""Immutable domain models produced by terminology recognition.

These are the value objects that cross the boundary out of Stage 10. Figure 5
states the stage as *"Terminology Recognition · Technical Terms · Buddhist
Vocabulary · User Dictionary"*.

A term is a run of morphemes, like a named entity, because Tibetan technical
vocabulary is overwhelmingly multi-syllable: of the 871 shipped glossary
entries, 154 span three or more syllables and only compounds of two or more
qualify at all.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teea.core.types import TextSpan
from teea.nlp.postagging import TaggedMorpheme
from teea.persistence import TermSource


class RecognizedTerm(BaseModel):
    """A contiguous run of morphemes recognised as a technical term.

    Attributes:
        text: The surface text of the term, exactly as it appears.
        span: Character/byte extent of ``text`` in the sentence.
        start_index: Index of the first morpheme of the run.
        end_index: Index one past the last morpheme of the run.
        source: Whether the term came from the shipped glossary or the user's
            own dictionary. Consumers treat the two differently: a user term is
            an explicit instruction, not a suggestion.
        morphemes: The morphemes the term spans.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    span: TextSpan
    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    source: TermSource
    morphemes: tuple[TaggedMorpheme, ...]

    @model_validator(mode="after")
    def _validate_consistency(self) -> RecognizedTerm:
        if not self.text:
            raise ValueError("a term must not be empty")
        if self.end_index <= self.start_index:
            raise ValueError("end_index must be greater than start_index")
        if len(self.morphemes) != self.end_index - self.start_index:
            raise ValueError(
                f"expected {self.end_index - self.start_index} morphemes, got {len(self.morphemes)}"
            )
        if self.span.char_start != self.morphemes[0].span.char_start:
            raise ValueError("span must start at the first morpheme")
        if self.span.char_end != self.morphemes[-1].span.char_end:
            raise ValueError("span must end at the last morpheme")
        return self

    @property
    def num_morphemes(self) -> int:
        """How many morphemes the term spans."""
        return len(self.morphemes)

    @property
    def syllables(self) -> tuple[str, ...]:
        """The surface of each morpheme the term spans."""
        return tuple(m.text for m in self.morphemes)

    @property
    def is_user_defined(self) -> bool:
        """Whether the user supplied this term themselves."""
        return self.source is TermSource.USER_DICTIONARY


class TerminologyAnnotation(BaseModel):
    """Every technical term found in one sentence.

    Attributes:
        source: The text that was analysed, exactly as supplied.
        terms: The terms found, in surface order, never overlapping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    terms: tuple[RecognizedTerm, ...] = ()

    @model_validator(mode="after")
    def _validate_consistency(self) -> TerminologyAnnotation:
        previous_end = -1
        for position, term in enumerate(self.terms):
            if term.start_index < previous_end:
                raise ValueError("term spans must not overlap")
            if term.span.char_end > len(self.source):
                raise ValueError(f"term {position} span exceeds the source text")
            if self.source[term.span.char_start : term.span.char_end] != term.text:
                raise ValueError(f"term {position} span does not select its own text")
            previous_end = term.end_index
        return self

    def __len__(self) -> int:
        """Number of terms."""
        return len(self.terms)

    @property
    def num_terms(self) -> int:
        """Number of terms."""
        return len(self.terms)

    @property
    def is_empty(self) -> bool:
        """Whether the sentence contains no recognised term."""
        return not self.terms

    @property
    def texts(self) -> tuple[str, ...]:
        """The surface text of each term, in order."""
        return tuple(term.text for term in self.terms)

    def of_source(self, source: TermSource) -> tuple[RecognizedTerm, ...]:
        """Return the terms drawn from a particular source."""
        return tuple(term for term in self.terms if term.source is source)

    def term_at_char(self, char_index: int) -> RecognizedTerm | None:
        """Return the term whose span contains ``char_index``, or ``None``."""
        for term in self.terms:
            if term.span.char_start <= char_index < term.span.char_end:
                return term
        return None

    def covers_morpheme(self, index: int) -> bool:
        """Whether the morpheme at ``index`` lies inside a recognised term."""
        return any(term.start_index <= index < term.end_index for term in self.terms)


__all__ = ["RecognizedTerm", "TerminologyAnnotation"]
