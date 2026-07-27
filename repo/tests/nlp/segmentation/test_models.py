"""Unit tests for the Stage 4 domain models (:mod:`teea.nlp.segmentation.models`).

These models are the contract between sentence segmentation and every stage that
follows it, so the tests construct :class:`Sentence` and :class:`SegmentedText`
**directly** rather than through the segmenter: the validators themselves are
what is under test here, independent of any producer that happens to satisfy
them today.

Two invariants carry disproportionate weight and are covered hardest:

* ``source[span.char_start:span.char_end] == sentence.text`` -- offsets that lie
  are worse than no offsets at all, because the Office.js add-in uses them to
  place suggestions on Word ranges.
* :meth:`SegmentedText.sentences_overlapping` -- the primitive behind
  incremental re-parsing (SRS 3.1, FR-4).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teea.core.types import TextSpan, utf8_byte_offsets
from teea.nlp.segmentation import SegmentedText, Sentence

# Real classical Tibetan; every code point occupies three UTF-8 bytes, so any
# confusion between character and byte offsets shows up immediately.
TASHI = "བཀྲ་ཤིས།"
DELEK = "བདེ་ལེགས།"
NYIS_SHAD = "༎"


# -- Helpers ------------------------------------------------------------------
def make_sentence(
    source: str,
    start: int,
    end: int,
    *,
    index: int = 0,
    terminator: str = "",
) -> Sentence:
    """Build a valid Sentence for ``source[start:end]`` with exact offsets."""
    offsets = utf8_byte_offsets(source)
    return Sentence(
        text=source[start:end],
        span=TextSpan(
            char_start=start,
            char_end=end,
            byte_start=offsets[start],
            byte_end=offsets[end],
        ),
        index=index,
        terminator=terminator,
    )


def span_for(source: str, start: int, end: int) -> TextSpan:
    offsets = utf8_byte_offsets(source)
    return TextSpan(
        char_start=start,
        char_end=end,
        byte_start=offsets[start],
        byte_end=offsets[end],
    )


# -- Sentence: validation -----------------------------------------------------
def test_valid_sentence_constructs() -> None:
    sentence = make_sentence(TASHI, 0, len(TASHI), terminator="།")
    assert sentence.text == TASHI
    assert sentence.index == 0
    assert sentence.terminator == "།"


def test_empty_text_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        Sentence(text="", span=span_for("", 0, 0), index=0)


def test_char_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not match span char_length"):
        Sentence(text=TASHI, span=span_for(TASHI, 0, len(TASHI) - 1), index=0)


def test_byte_length_mismatch_is_rejected() -> None:
    """Char length can agree while byte length does not -- Tibetan is 3 bytes/char."""
    bad = TextSpan(
        char_start=0,
        char_end=len(TASHI),
        byte_start=0,
        byte_end=len(TASHI),  # wrong: should be 3x this
    )
    assert len(TASHI.encode("utf-8")) == 3 * len(TASHI), "premise: 3 bytes per char"
    with pytest.raises(ValidationError, match="UTF-8 length does not match"):
        Sentence(text=TASHI, span=bad, index=0)


def test_terminator_must_be_a_suffix_of_text() -> None:
    with pytest.raises(ValidationError, match="terminator must be a suffix"):
        make_sentence(TASHI, 0, len(TASHI), terminator=NYIS_SHAD)


def test_negative_index_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_sentence(TASHI, 0, len(TASHI), index=-1)


# -- Sentence: behaviour ------------------------------------------------------
def test_has_terminator_reflects_the_terminator() -> None:
    assert make_sentence(TASHI, 0, len(TASHI), terminator="།").has_terminator
    assert not make_sentence(TASHI, 0, len(TASHI) - 1).has_terminator


def test_content_strips_the_terminator() -> None:
    sentence = make_sentence(TASHI, 0, len(TASHI), terminator="།")
    assert sentence.content == TASHI[:-1]
    assert "།" not in sentence.content


def test_content_without_a_terminator_is_the_stripped_text() -> None:
    source = f"{TASHI[:-1]}  "
    sentence = make_sentence(source, 0, len(source))
    assert sentence.content == TASHI[:-1]


def test_content_strips_whitespace_before_the_terminator() -> None:
    source = f"{TASHI[:-1]}  །"
    sentence = make_sentence(source, 0, len(source), terminator="།")
    assert sentence.content == TASHI[:-1]


def test_terminator_is_preserved_verbatim_not_canonicalised() -> None:
    """A nyis shad must stay a nyis shad.

    Storing the characters rather than a boolean is deliberate: an analogous
    flag-based design elsewhere in the codebase cannot distinguish delimiter
    variants, and the add-in writes suggestions back into the user's document.
    """
    source = TASHI[:-1] + NYIS_SHAD
    sentence = make_sentence(source, 0, len(source), terminator=NYIS_SHAD)
    assert sentence.terminator == NYIS_SHAD
    assert sentence.terminator != "།"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (TASHI, True),
        ("བཀྲ12", True),  # 3/5 Tibetan -> majority
        ("བཀྲabcd", False),  # 3/7 Tibetan -> minority
        ("abcdef", False),
        ("123", False),
    ],
)
def test_is_tibetan_uses_a_majority_threshold(text: str, expected: bool) -> None:
    assert make_sentence(text, 0, len(text)).is_tibetan is expected


# -- Sentence: value semantics ------------------------------------------------
def test_sentence_is_frozen() -> None:
    sentence = make_sentence(TASHI, 0, len(TASHI))
    with pytest.raises(ValidationError):
        sentence.index = 5  # type: ignore[misc]


def test_sentence_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Sentence(
            text=TASHI,
            span=span_for(TASHI, 0, len(TASHI)),
            index=0,
            unexpected="x",  # type: ignore[call-arg]
        )


def test_sentences_compare_by_value_and_are_hashable() -> None:
    first = make_sentence(TASHI, 0, len(TASHI), terminator="།")
    second = make_sentence(TASHI, 0, len(TASHI), terminator="།")
    assert first == second
    assert len({first, second}) == 1


# -- SegmentedText: validation ------------------------------------------------
def test_empty_segmented_text_is_valid() -> None:
    result = SegmentedText(source="")
    assert result.is_empty
    assert result.num_sentences == 0
    assert len(result) == 0


def test_index_must_match_position() -> None:
    source = TASHI
    with pytest.raises(ValidationError, match="carries index"):
        SegmentedText(
            source=source,
            sentences=(make_sentence(source, 0, len(source), index=3),),
        )


def test_overlapping_spans_are_rejected() -> None:
    source = TASHI + DELEK
    first = make_sentence(source, 0, len(TASHI) + 2, index=0)
    second = make_sentence(source, len(TASHI), len(source), index=1)
    with pytest.raises(ValidationError, match="must not overlap"):
        SegmentedText(source=source, sentences=(first, second))


def test_span_beyond_the_source_is_rejected() -> None:
    source = TASHI
    longer = source + DELEK
    stray = make_sentence(longer, 0, len(longer), index=0)
    with pytest.raises(ValidationError, match="exceeds the source text"):
        SegmentedText(source=source, sentences=(stray,))


def test_span_that_does_not_select_its_own_text_is_rejected() -> None:
    """The single most important invariant in the module."""
    source = TASHI + DELEK
    lying = Sentence(
        text=DELEK,
        span=span_for(source, 0, len(DELEK)),  # points at TASHI, not DELEK
        index=0,
    )
    with pytest.raises(ValidationError, match="does not select its own text"):
        SegmentedText(source=source, sentences=(lying,))


# -- SegmentedText: accessors -------------------------------------------------
@pytest.fixture
def two_sentences() -> SegmentedText:
    """``TASHI`` then ``DELEK``, separated by a single space."""
    source = f"{TASHI} {DELEK}"
    first = make_sentence(source, 0, len(TASHI), index=0, terminator="།")
    second = make_sentence(source, len(TASHI) + 1, len(source), index=1, terminator="།")
    return SegmentedText(source=source, sentences=(first, second))


def test_accessors_report_the_sentences(two_sentences: SegmentedText) -> None:
    assert len(two_sentences) == 2
    assert two_sentences.num_sentences == 2
    assert two_sentences.texts == (TASHI, DELEK)
    assert not two_sentences.is_empty


# -- sentence_at_char ---------------------------------------------------------
def test_sentence_at_char_finds_the_covering_sentence(two_sentences: SegmentedText) -> None:
    assert two_sentences.sentence_at_char(0) is two_sentences.sentences[0]
    assert two_sentences.sentence_at_char(len(TASHI) + 1) is two_sentences.sentences[1]


def test_sentence_at_char_is_half_open(two_sentences: SegmentedText) -> None:
    """char_start is inside the span; char_end is not."""
    first = two_sentences.sentences[0]
    assert two_sentences.sentence_at_char(first.span.char_start) is first
    assert two_sentences.sentence_at_char(first.span.char_end - 1) is first
    # char_end lands on the separating space, which belongs to no sentence.
    assert two_sentences.sentence_at_char(first.span.char_end) is None


def test_sentence_at_char_returns_none_in_gaps_and_out_of_range(
    two_sentences: SegmentedText,
) -> None:
    assert two_sentences.sentence_at_char(len(TASHI)) is None  # the space
    assert two_sentences.sentence_at_char(len(two_sentences.source)) is None
    assert two_sentences.sentence_at_char(10_000) is None
    assert two_sentences.sentence_at_char(-1) is None


# -- sentences_overlapping (FR-4 incremental re-parse primitive) --------------
def test_overlapping_selects_touched_sentences(two_sentences: SegmentedText) -> None:
    first, second = two_sentences.sentences
    assert two_sentences.sentences_overlapping(0, 2) == (first,)
    assert two_sentences.sentences_overlapping(len(TASHI) + 2, len(TASHI) + 4) == (second,)


def test_overlapping_spanning_both_returns_both_in_order(
    two_sentences: SegmentedText,
) -> None:
    assert two_sentences.sentences_overlapping(0, len(two_sentences.source)) == (
        two_sentences.sentences
    )


def test_overlapping_range_inside_a_gap_returns_nothing(
    two_sentences: SegmentedText,
) -> None:
    gap = len(TASHI)
    assert two_sentences.sentences_overlapping(gap, gap + 1) == ()


def test_empty_range_is_an_insertion_point(two_sentences: SegmentedText) -> None:
    """An insertion modifies the sentence that strictly contains the caret."""
    first = two_sentences.sentences[0]
    assert two_sentences.sentences_overlapping(1, 1) == (first,)
    # A caret in the inter-sentence gap modifies neither sentence.
    assert two_sentences.sentences_overlapping(len(TASHI), len(TASHI)) == ()


def test_overlapping_rejects_a_reversed_range(two_sentences: SegmentedText) -> None:
    with pytest.raises(ValueError, match="end must be >= start"):
        two_sentences.sentences_overlapping(5, 2)


def test_overlapping_is_exclusive_at_the_range_end(two_sentences: SegmentedText) -> None:
    """A range ending exactly at a sentence start must not select it."""
    first, second = two_sentences.sentences
    assert two_sentences.sentences_overlapping(0, second.span.char_start) == (first,)
