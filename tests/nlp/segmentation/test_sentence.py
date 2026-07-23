"""Unit tests for :class:`~teea.nlp.segmentation.sentence.TibetanSentenceSegmenter`.

Stage 4 is what makes the rest of the pipeline tractable, so its correctness is
measured against authentic classical Tibetan rather than invented strings. The
centre of gravity is **span ground truth**: for every sentence of the real
Milarepa corpus, both the character span and the UTF-8 byte span are re-derived
by slicing the source and its encoding. Tibetan code points occupy three UTF-8
bytes, so character and byte offsets diverge from the first character onward and
any confusion between them surfaces immediately.

The delimiter tests parametrize over the shared constants in
:mod:`teea.core.types` rather than hardcoding character lists, so they track the
canonical sets instead of drifting away from them.
"""

from __future__ import annotations

import pytest

from teea.core.types import LINE_BREAK_CHARS, SHAD_CHARS
from teea.nlp.segmentation import SegmentedText, SentenceSegmenter, TibetanSentenceSegmenter

TASHI = "བཀྲ་ཤིས"
DELEK = "བདེ་ལེགས"
SHAD = "།"
NYIS_SHAD = "༎"

#: U+0F13 is an annotation mark, deliberately excluded from SHAD_CHARS.
CARET = "༓"


# -- Helpers ------------------------------------------------------------------
def assert_span_ground_truth(source: str, result: SegmentedText) -> None:
    """Every sentence's char and byte spans must select its own text."""
    encoded = source.encode("utf-8")
    for sentence in result.sentences:
        span = sentence.span
        assert source[span.char_start : span.char_end] == sentence.text
        assert encoded[span.byte_start : span.byte_end] == sentence.text.encode("utf-8")


# -- Protocol conformance and configuration -----------------------------------
def test_satisfies_the_sentence_segmenter_protocol(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    assert isinstance(sentence_segmenter, SentenceSegmenter)


def test_break_on_newline_reflects_construction() -> None:
    assert TibetanSentenceSegmenter().break_on_newline is True
    assert TibetanSentenceSegmenter(break_on_newline=False).break_on_newline is False


# -- Shad-family boundaries ---------------------------------------------------
def test_splits_at_the_shad(sentence_segmenter: TibetanSentenceSegmenter) -> None:
    result = sentence_segmenter.segment(f"{TASHI}{SHAD}{DELEK}{SHAD}")
    assert result.texts == (f"{TASHI}{SHAD}", f"{DELEK}{SHAD}")
    assert all(s.terminator == SHAD for s in result.sentences)


@pytest.mark.parametrize("terminator", sorted(SHAD_CHARS))
def test_every_shad_family_member_terminates_a_sentence(
    sentence_segmenter: TibetanSentenceSegmenter, terminator: str
) -> None:
    result = sentence_segmenter.segment(f"{TASHI}{terminator}{DELEK}{terminator}")
    assert result.num_sentences == 2
    assert result.sentences[0].terminator == terminator


def test_the_caret_annotation_mark_does_not_terminate(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    """U+0F13 is excluded from SHAD_CHARS: it annotates, it does not terminate."""
    assert CARET not in SHAD_CHARS
    result = sentence_segmenter.segment(f"{TASHI}{CARET}{DELEK}")
    assert result.num_sentences == 1


def test_consecutive_terminators_close_one_sentence(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    result = sentence_segmenter.segment(f"{TASHI}{SHAD}{SHAD}")
    assert result.num_sentences == 1
    assert result.sentences[0].terminator == f"{SHAD}{SHAD}"
    assert result.sentences[0].content == TASHI


def test_terminator_is_captured_verbatim(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    """A nyis shad is reported as itself, not canonicalised to an ordinary shad."""
    result = sentence_segmenter.segment(f"{TASHI}{NYIS_SHAD}")
    assert result.sentences[0].terminator == NYIS_SHAD


# -- Line-break boundaries ----------------------------------------------------
@pytest.mark.parametrize("line_break", sorted(LINE_BREAK_CHARS))
def test_every_line_break_ends_a_sentence(
    sentence_segmenter: TibetanSentenceSegmenter, line_break: str
) -> None:
    """Word encodes paragraph marks as CR and manual line breaks as VT."""
    result = sentence_segmenter.segment(f"{TASHI}{line_break}{DELEK}")
    assert result.num_sentences == 2
    assert result.texts == (TASHI, DELEK)
    # A line break is a boundary, not punctuation: it is not a terminator.
    assert result.sentences[0].terminator == ""
    assert not result.sentences[0].has_terminator


def test_crlf_behaves_like_a_single_break(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    result = sentence_segmenter.segment(f"{TASHI}\r\n{DELEK}")
    assert result.texts == (TASHI, DELEK)


def test_break_on_newline_false_joins_the_lines() -> None:
    segmenter = TibetanSentenceSegmenter(break_on_newline=False)
    result = segmenter.segment(f"{TASHI}\n{DELEK}")
    assert result.num_sentences == 1
    assert result.texts == (f"{TASHI}\n{DELEK}",)


def test_break_on_newline_false_still_splits_at_the_shad() -> None:
    segmenter = TibetanSentenceSegmenter(break_on_newline=False)
    result = segmenter.segment(f"{TASHI}{SHAD}\n{DELEK}{SHAD}")
    assert result.num_sentences == 2


def test_blank_lines_do_not_create_empty_sentences(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    result = sentence_segmenter.segment(f"{TASHI}\n\n\n{DELEK}")
    assert result.texts == (TASHI, DELEK)


# -- Unterminated and degenerate input ----------------------------------------
def test_trailing_text_without_a_terminator_is_still_a_sentence(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    result = sentence_segmenter.segment(f"{TASHI}{SHAD}{DELEK}")
    assert result.num_sentences == 2
    assert result.sentences[1].text == DELEK
    assert not result.sentences[1].has_terminator


def test_trailing_whitespace_is_excluded_from_the_sentence(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    source = f"{TASHI}   "
    result = sentence_segmenter.segment(source)
    assert result.texts == (TASHI,)
    assert result.sentences[0].span.char_end == len(TASHI)


@pytest.mark.parametrize("source", ["", "   ", "\n\n", "\t \n", SHAD, f"{SHAD}{SHAD}", "  ། ། "])
def test_degenerate_input_yields_no_sentences(
    sentence_segmenter: TibetanSentenceSegmenter, source: str
) -> None:
    """segment() is total: punctuation-only and blank input never raise."""
    result = sentence_segmenter.segment(source)
    assert result.is_empty
    assert result.source == source


def test_leading_orphan_punctuation_is_discarded_without_shifting_offsets(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    source = f"{SHAD}{SHAD} {TASHI}{SHAD}"
    result = sentence_segmenter.segment(source)
    assert result.num_sentences == 1
    sentence = result.sentences[0]
    assert sentence.text == f"{TASHI}{SHAD}"
    assert sentence.span.char_start == 3
    assert_span_ground_truth(source, result)


# -- Span ground truth over the real corpus -----------------------------------
def test_corpus_document_spans_are_exact(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    assert_span_ground_truth(corpus_document, sentence_segmenter.segment(corpus_document))


def test_corpus_byte_offsets_diverge_from_char_offsets(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    """Guards the assertion above against being trivially satisfiable."""
    result = sentence_segmenter.segment(corpus_document)
    assert any(s.span.byte_start != s.span.char_start for s in result.sentences)


def test_corpus_spans_are_ordered_and_non_overlapping(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    result = sentence_segmenter.segment(corpus_document)
    for previous, current in zip(result.sentences, result.sentences[1:], strict=False):
        assert previous.span.char_end <= current.span.char_start
        assert previous.index + 1 == current.index


def uncovered_characters(source: str, result: SegmentedText) -> set[str]:
    """Return the distinct characters belonging to no sentence."""
    covered = bytearray(len(source))
    for sentence in result.sentences:
        for index in range(sentence.span.char_start, sentence.span.char_end):
            covered[index] = 1
    return {source[i] for i, flag in enumerate(covered) if not flag}


def test_no_content_character_is_ever_dropped(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    """Gaps may hold separators, but never content.

    Rule 4 leaves whitespace in gaps and rule 5 discards punctuation-only runs,
    so a gap can legitimately contain a shad. What must never happen is a
    Tibetan letter falling outside every sentence -- that would be silent data
    loss ahead of every downstream stage.
    """
    result = sentence_segmenter.segment(corpus_document)
    uncovered = uncovered_characters(corpus_document, result)
    assert all(char.isspace() or char in SHAD_CHARS for char in uncovered), uncovered


def test_leading_shad_after_a_line_break_loses_no_content(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    """Tibetan verse often opens a line with the shad closing the previous one.

    Observed in the real Milarepa text as ``...ཅན\\n།།སྤྲང...``. The orphan run is
    discarded per rule 5, but both surrounding phrases must survive intact with
    exact offsets.
    """
    source = f"{TASHI}\n{SHAD}{SHAD}{DELEK}{SHAD}"
    result = sentence_segmenter.segment(source)

    assert result.texts == (TASHI, f"{DELEK}{SHAD}")
    assert_span_ground_truth(source, result)
    assert uncovered_characters(source, result) <= {"\n", SHAD}


def test_document_round_trips_to_the_original_sentences(
    sentence_segmenter: TibetanSentenceSegmenter,
    corpus_document: str,
    corpus_sentences: list[str],
) -> None:
    """The fixture joins these sentences, so segmentation must recover them."""
    result = sentence_segmenter.segment(corpus_document)
    assert list(result.texts) == corpus_sentences


def test_every_corpus_sentence_is_tibetan(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    result = sentence_segmenter.segment(corpus_document)
    assert result.sentences
    assert all(sentence.is_tibetan for sentence in result.sentences)


def test_every_corpus_sentence_is_shad_terminated(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    result = sentence_segmenter.segment(corpus_document)
    assert all(sentence.terminator in SHAD_CHARS for sentence in result.sentences)


def test_segmenting_one_sentence_returns_it_unchanged(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_sentences: list[str]
) -> None:
    """Idempotence-flavoured: a lone sentence segments to exactly itself."""
    for sentence_text in corpus_sentences[:15]:
        result = sentence_segmenter.segment(sentence_text)
        assert result.num_sentences == 1
        assert result.sentences[0].text == sentence_text


def test_segmentation_is_deterministic(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    first = sentence_segmenter.segment(corpus_document)
    second = sentence_segmenter.segment(corpus_document)
    assert first == second


# -- Real lexicon entries -----------------------------------------------------
def test_lexicon_entries_segment_without_raising(
    sentence_segmenter: TibetanSentenceSegmenter, lexicon_sample: list[str]
) -> None:
    assert lexicon_sample
    for entry in lexicon_sample:
        result = sentence_segmenter.segment(entry)
        punctuation_only = all(char in SHAD_CHARS or char.isspace() for char in entry)
        if punctuation_only:
            assert result.is_empty, entry
        else:
            assert result.num_sentences >= 1, entry
        assert_span_ground_truth(entry, result)


def test_bare_lexicon_syllables_are_single_sentences(
    sentence_segmenter: TibetanSentenceSegmenter, lexicon_sample: list[str]
) -> None:
    plain = [e for e in lexicon_sample if not any(c in SHAD_CHARS for c in e)]
    assert plain, "fixture should contain entries with no shad"
    for entry in plain:
        result = sentence_segmenter.segment(entry)
        assert result.texts == (entry,)
        assert not result.sentences[0].has_terminator
