"""Rule-based Tibetan sentence segmentation (Language pipeline Stage 4).

Why this stage exists
---------------------
Stage 4 sits between document cleaning and word tokenization in Figure 5, and it
is what makes the rest of the pipeline tractable. Two concrete reasons:

* **The tokenizer cannot accept a document.** TiBERT is a BERT-base encoder with
  a 512-token positional limit, so
  :meth:`~teea.nlp.tokenization.tibert.TiBERTTokenizer.encode` raises
  :class:`~teea.nlp.tokenization.exceptions.InputTooLongError` on anything of
  realistic length. Sentences are the units that fit.
* **Incremental re-parsing is defined in sentences.** SRS 3.1 and FR-4 require
  that only modified regions trigger a full re-parse. That is only expressible
  against a stable decomposition with exact offsets, which is what this stage
  produces.

Why rules rather than a model
-----------------------------
Classical Tibetan marks phrase and sentence boundaries *explicitly* with the
shad (``།``) family. Unlike the full-stop-versus-abbreviation ambiguity that
makes English sentence splitting genuinely hard, the shad has no competing role:
it is not an abbreviation marker, not a decimal point, and not part of any word.
A deterministic scan is therefore both exact and auditable here, and a
statistical model would add opacity without adding accuracy. The
:class:`~teea.nlp.segmentation.interfaces.SentenceSegmenter` protocol keeps the
door open for one should transcribed or modern Tibetan later require it.

Scope
-----
This module performs segmentation and nothing else. It does **not** normalize:
that is Stage 2, owned by
:class:`~teea.nlp.tokenization.normalization.TextNormalizer`, and re-doing it
here would violate the pipeline's separation of stages and couple Stage 4 to
Stage 5's package. Offsets in the result are relative to the exact string
supplied, so callers working from raw input should normalize first and segment
the normalized text. This mirrors
:class:`~teea.nlp.tokenization.syllable.SyllableSegmenter`, which likewise
documents its input as already-normalized text.
"""

from __future__ import annotations

from teea.core.types import LINE_BREAK_CHARS, SHAD_CHARS, TextSpan, utf8_byte_offsets
from teea.nlp.segmentation.models import SegmentedText, Sentence


class TibetanSentenceSegmenter:
    """Splits Tibetan text into sentences at the shad and at line breaks.

    Satisfies the :class:`~teea.nlp.segmentation.interfaces.SentenceSegmenter`
    protocol. The segmenter is stateless and safe to share across threads.

    Boundary rules, in order of application:

    1. A run of one or more shad-family characters terminates a sentence, and is
       retained as that sentence's :attr:`~Sentence.terminator`. Consecutive
       terminators (``།།``) close a single sentence rather than producing an
       empty one.
    2. Any line break terminates a sentence even without a shad, because a
       Word paragraph boundary is always a sentence boundary. This covers the
       full universal-newlines set (see :data:`~teea.core.types.LINE_BREAK_CHARS`), not just
       LF, because Word encodes paragraph marks as CR and manual line breaks
       as VT. Configurable, since Tibetan verse is often line-broken
       mid-phrase.
    3. Trailing input with no terminator is still a sentence, with an empty
       terminator.
    4. Whitespace between sentences belongs to no sentence, leaving gaps in the
       offset sequence exactly as syllable segmentation does.
    5. Runs consisting only of punctuation are discarded rather than emitted as
       contentless sentences. Tibetan verse commonly opens a line with the shad
       that closes the previous one (``...ཅན\\n།།སྤྲང...``), which produces exactly
       such a run.

    Consequently the sentences do **not** tile the input: gaps may contain
    whitespace and discarded punctuation. They never contain content, though --
    a run is only discarded when it holds nothing but punctuation, so no letter
    is ever dropped. The full original is always available as
    :attr:`~teea.nlp.segmentation.models.SegmentedText.source`.

    Args:
        break_on_newline: Whether a line break ends a sentence. Defaults to
            ``True``, which is correct for prose documents. Set to ``False``
            when processing verse, where lines break without ending a phrase.
    """

    def __init__(self, *, break_on_newline: bool = True) -> None:
        self._break_on_newline = break_on_newline

    @property
    def break_on_newline(self) -> bool:
        """Whether a line break is treated as a sentence boundary."""
        return self._break_on_newline

    def segment(self, text: str) -> SegmentedText:
        """Split ``text`` into sentences.

        Total: any input, including empty or punctuation-only text, produces a
        :class:`SegmentedText` rather than raising.

        Args:
            text: Normalized text. All offsets in the result are relative to
                this exact string.

        Returns:
            The segmentation result, whose sentences are ordered, non
            overlapping, and each of which satisfies
            ``text[span.char_start:span.char_end] == sentence.text``.
        """
        if not text:
            return SegmentedText(source=text, sentences=())

        byte_offsets = utf8_byte_offsets(text)
        sentences: list[Sentence] = []
        length = len(text)
        cursor = 0

        while cursor < length:
            # Whitespace between sentences belongs to no sentence.
            while cursor < length and text[cursor].isspace():
                cursor += 1
            if cursor >= length:
                break

            start = cursor
            cursor = self._scan_content(text, cursor)
            terminator_start = cursor
            cursor = self._scan_terminators(text, cursor)
            terminator = text[terminator_start:cursor]

            end = self._trim_trailing_space(text, start, cursor)
            if end <= start:  # pragma: no cover - defensive
                # Unreachable today: the whitespace skip above guarantees that
                # text[start] is not whitespace, so the run is never empty.
                # Kept so that widening the boundary sets later cannot produce a
                # zero-length sentence and trip the Sentence validator.
                continue

            # A run with no content beyond its punctuation is orphan
            # punctuation, not a sentence.
            content_end = end - len(terminator) if terminator else end
            if not text[start:content_end].strip():
                continue

            sentences.append(
                Sentence(
                    text=text[start:end],
                    span=TextSpan(
                        char_start=start,
                        char_end=end,
                        byte_start=byte_offsets[start],
                        byte_end=byte_offsets[end],
                    ),
                    index=len(sentences),
                    terminator=terminator,
                )
            )

        return SegmentedText(source=text, sentences=tuple(sentences))

    # -- Internals ----------------------------------------------------------
    def _scan_content(self, text: str, cursor: int) -> int:
        """Advance past sentence content, stopping before any boundary."""
        length = len(text)
        while cursor < length:
            char = text[cursor]
            if char in SHAD_CHARS:
                break
            if self._break_on_newline and char in LINE_BREAK_CHARS:
                break
            cursor += 1
        return cursor

    @staticmethod
    def _scan_terminators(text: str, cursor: int) -> int:
        """Advance past a run of shad-family terminators."""
        length = len(text)
        while cursor < length and text[cursor] in SHAD_CHARS:
            cursor += 1
        return cursor

    @staticmethod
    def _trim_trailing_space(text: str, start: int, end: int) -> int:
        """Exclude trailing whitespace so ``text`` never ends in a space.

        Only reachable when a sentence ends at a line break or at end of input;
        a terminated sentence already ends in punctuation.
        """
        while end > start and text[end - 1].isspace():
            end -= 1
        return end


__all__ = ["TibetanSentenceSegmenter"]
