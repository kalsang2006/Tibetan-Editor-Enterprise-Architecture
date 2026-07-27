"""Immutable domain models produced by sentence segmentation.

These are the value objects that cross the boundary out of Stage 4 (Sentence
Segmentation) of the language processing pipeline. They are the unit of work for
every stage that follows: morphological analysis, POS tagging, dependency
parsing, NER, terminology recognition and semantic analysis all operate on one
sentence at a time.

They are also the unit of *incremental* work. SRS 3.1 and FR-4 require that only
modified regions trigger a full pipeline re-parse, which presupposes a stable,
addressable decomposition of the document. :class:`Sentence` carries an exact
:class:`~teea.core.types.TextSpan`, so a changed region can be intersected
against the previous segmentation to determine precisely which sentences need
re-analysis.

Design decisions
----------------
* **Frozen, like every other TEEA value object.** Figure 5 stores an immutable
  document snapshot that all plugins read concurrently.
* **The terminator is stored verbatim, not as a flag.** Tibetan distinguishes
  several phrase terminators (ordinary shad, nyis shad, rin chen spungs shad).
  Recording which one closed the sentence keeps the decomposition lossless, so
  the original document can be reconstructed exactly -- a hard requirement, as
  the add-in maps suggestions back onto the user's own text.
* **``text`` always equals the source slice named by ``span``.** This single
  invariant is what makes offsets trustworthy across process boundaries, and it
  is enforced by a validator rather than left to convention.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teea.core.types import TextSpan, tibetan_ratio


class Sentence(BaseModel):
    """One sentence of a segmented document.

    ``text`` includes the terminating shad (if the sentence had one), so that
    ``text`` is exactly the slice of the source named by ``span``. Callers that
    want the sentence without its punctuation should use :attr:`content`.

    Attributes:
        text: The sentence exactly as it appears in the source, including its
            terminator.
        span: Character/byte extent of ``text`` in the segmented source.
        index: Zero-based position of this sentence within the document.
        terminator: The exact terminating characters, or ``""`` when the
            sentence ended at a paragraph break or at end of input. Storing the
            characters rather than a boolean keeps ``nyis shad`` distinguishable
            from an ordinary ``shad``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    span: TextSpan
    index: int = Field(ge=0)
    terminator: str = ""

    @model_validator(mode="after")
    def _validate_consistency(self) -> Sentence:
        """Enforce the invariants downstream stages rely upon."""
        if not self.text:
            raise ValueError("a sentence must not be empty")
        if len(self.text) != self.span.char_length:
            raise ValueError(
                f"text length {len(self.text)} does not match span char_length "
                f"{self.span.char_length}"
            )
        if len(self.text.encode("utf-8")) != self.span.byte_length:
            raise ValueError("text UTF-8 length does not match span byte_length")
        if self.terminator and not self.text.endswith(self.terminator):
            raise ValueError("terminator must be a suffix of text")
        return self

    @property
    def has_terminator(self) -> bool:
        """Whether the sentence was closed by an explicit terminator."""
        return bool(self.terminator)

    @property
    def content(self) -> str:
        """The sentence without its terminating punctuation, stripped."""
        body = self.text[: len(self.text) - len(self.terminator)] if self.terminator else self.text
        return body.strip()

    @property
    def is_tibetan(self) -> bool:
        """Whether the sentence is predominantly Tibetan script.

        Uses a majority threshold rather than requiring purity, because genuine
        Tibetan sentences routinely embed digits, citation markers and Latin
        loanwords.
        """
        return tibetan_ratio(self.text) > 0.5


class SegmentedText(BaseModel):
    """The complete result of segmenting one text into sentences.

    Attributes:
        source: The text that was segmented, exactly as supplied.
        sentences: The sentences found, in document order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    sentences: tuple[Sentence, ...] = ()

    @model_validator(mode="after")
    def _validate_consistency(self) -> SegmentedText:
        """Enforce ordering, indexing and span-accuracy invariants."""
        previous_end = -1
        for position, sentence in enumerate(self.sentences):
            if sentence.index != position:
                raise ValueError(f"sentence at position {position} carries index {sentence.index}")
            span = sentence.span
            if span.char_start < previous_end:
                raise ValueError("sentence spans must not overlap")
            if span.char_end > len(self.source):
                raise ValueError("sentence span exceeds the source text")
            if self.source[span.char_start : span.char_end] != sentence.text:
                raise ValueError(f"sentence {position} span does not select its own text")
            previous_end = span.char_end
        return self

    def __len__(self) -> int:
        """Number of sentences."""
        return len(self.sentences)

    @property
    def num_sentences(self) -> int:
        """Number of sentences."""
        return len(self.sentences)

    @property
    def texts(self) -> tuple[str, ...]:
        """The raw text of each sentence, in order."""
        return tuple(sentence.text for sentence in self.sentences)

    @property
    def is_empty(self) -> bool:
        """Whether segmentation produced no sentences at all."""
        return not self.sentences

    def sentence_at_char(self, char_index: int) -> Sentence | None:
        """Return the sentence whose span contains ``char_index``.

        This is the primitive behind incremental re-parsing (FR-4): given the
        offset of an edit, it identifies the sentence that must be re-analyzed.

        Args:
            char_index: Character offset into :attr:`source`.

        Returns:
            The covering sentence, or ``None`` if the offset falls in a gap
            between sentences (whitespace) or outside the text.
        """
        for sentence in self.sentences:
            if sentence.span.char_start <= char_index < sentence.span.char_end:
                return sentence
        return None

    def sentences_overlapping(self, start: int, end: int) -> tuple[Sentence, ...]:
        """Return every sentence intersecting the half-open range ``[start, end)``.

        The incremental counterpart to :meth:`sentence_at_char`: an edit that
        spans a region invalidates every sentence it touches, and those are
        exactly the sentences that must be re-parsed.

        Args:
            start: Inclusive character offset of the changed region.
            end: Exclusive character offset of the changed region.

        Returns:
            The overlapping sentences, in document order. An empty range that
            falls strictly inside one sentence still returns that sentence,
            because an insertion at that point modifies it.
        """
        if end < start:
            raise ValueError("end must be >= start")
        matches: list[Sentence] = []
        for sentence in self.sentences:
            span = sentence.span
            if start == end:
                if span.char_start <= start < span.char_end:
                    matches.append(sentence)
                continue
            if span.char_start < end and start < span.char_end:
                matches.append(sentence)
        return tuple(matches)


__all__ = ["SegmentedText", "Sentence"]
