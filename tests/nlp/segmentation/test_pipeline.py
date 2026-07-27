"""Architecture tests for the Stage 2 -> Stage 4 -> Stage 5 composition.

Individually correct stages can still compose wrongly, and the failure modes are
silent: offsets that no longer line up, or a normalizer that quietly deletes the
structure the next stage depends on. This module pins the composition itself.

Everything here runs against ``FakeBackendTokenizer``; no model is downloaded and
no network is touched.

What is being protected:

* **The justification for Stage 4.** A whole document exceeds TiBERT's 512-token
  positional limit; sentences fit. Both halves are asserted, so the stage cannot
  be removed without a test failing.
* **Offset composition.** ``sentence.span`` is relative to the document and
  ``token.span`` is relative to the sentence. Their sum must land on the right
  characters, because that arithmetic is exactly how the Office.js add-in maps a
  suggestion back onto a Word range (Figure 3).
* **Stage ordering.** Stage 2 with default settings folds line breaks away, which
  destroys paragraph boundaries Stage 4 relies on.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from teea.core.config import TokenizationSettings
from teea.nlp.segmentation import TibetanSentenceSegmenter
from teea.nlp.tokenization import (
    SyllableSegmenter,
    TextNormalizer,
    TiBERTTokenizer,
)
from teea.nlp.tokenization.exceptions import InputTooLongError

MakeTokenizer = Callable[..., TiBERTTokenizer]

TASHI = "བཀྲ་ཤིས"
DELEK = "བདེ་ལེགས"


# -- The reason Stage 4 exists ------------------------------------------------
def test_whole_document_exceeds_the_tokenizer_limit(
    tokenizer: TiBERTTokenizer, corpus_document: str
) -> None:
    """The motivating failure: a real document cannot be encoded directly."""
    with pytest.raises(InputTooLongError) as excinfo:
        tokenizer.encode(corpus_document)
    context = excinfo.value.context
    assert context["produced"] > context["maximum"]


def test_segmented_sentences_all_encode_successfully(
    tokenizer: TiBERTTokenizer,
    sentence_segmenter: TibetanSentenceSegmenter,
    corpus_document: str,
    settings: TokenizationSettings,
) -> None:
    """...and the same document encodes fine once split into sentences."""
    segmented = sentence_segmenter.segment(corpus_document)
    assert segmented.num_sentences > 1

    encodings = [tokenizer.encode(sentence.text) for sentence in segmented.sentences]
    assert len(encodings) == segmented.num_sentences
    for encoded in encodings:
        assert encoded.num_tokens <= settings.max_sequence_length
        assert not encoded.was_truncated
        assert encoded.num_content_tokens > 0


# -- Stage ordering: normalization must not destroy structure -----------------
def test_default_normalizer_folds_line_breaks_and_merges_unterminated_lines(
    sentence_segmenter: TibetanSentenceSegmenter,
) -> None:
    """Stage 2's default collapse_whitespace=True erases paragraph boundaries.

    Documented in ``teea.nlp.segmentation``: document-level callers must pass
    ``collapse_whitespace=False``. Only lines lacking a shad are affected, since
    a shad is a boundary in its own right.
    """
    raw = f"{TASHI}\n{DELEK}"

    collapsed = TextNormalizer(form="NFC", collapse_whitespace=True).normalize(raw)
    preserved = TextNormalizer(form="NFC", collapse_whitespace=False).normalize(raw)

    assert sentence_segmenter.segment(collapsed).num_sentences == 1
    assert sentence_segmenter.segment(preserved).num_sentences == 2


@pytest.mark.parametrize("line_break", ["\n", "\r", "\v"])
def test_word_line_breaks_survive_normalization(
    sentence_segmenter: TibetanSentenceSegmenter, line_break: str
) -> None:
    """Word encodes paragraph marks as CR and manual line breaks as VT.

    Stage 2 previously stripped both as control characters, so a whole document
    arrived at Stage 4 as one runaway sentence. The preserved-control set is now
    shared between the two stages.
    """
    raw = f"{TASHI}{line_break}{DELEK}"
    normalized = TextNormalizer(form="NFC", collapse_whitespace=False).normalize(raw)
    assert sentence_segmenter.segment(normalized).num_sentences == 2


def test_normalizing_already_normalized_corpus_is_a_no_op(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    """So normalize -> segment agrees with segmenting directly."""
    normalized = TextNormalizer(form="NFC", collapse_whitespace=False).normalize(corpus_document)
    assert normalized == corpus_document
    assert (
        sentence_segmenter.segment(normalized).texts
        == sentence_segmenter.segment(corpus_document).texts
    )


# -- Offset composition -------------------------------------------------------
def test_sentence_and_token_offsets_compose_to_document_offsets(
    tokenizer: TiBERTTokenizer,
    sentence_segmenter: TibetanSentenceSegmenter,
    corpus_document: str,
) -> None:
    """document_offset = sentence.span.char_start + token.span.char_start.

    This is the arithmetic the add-in performs to place a suggestion, so it is
    asserted against the document text rather than assumed.
    """
    segmented = sentence_segmenter.segment(corpus_document)
    checked = 0

    for sentence in segmented.sentences[:20]:
        encoded = tokenizer.encode(sentence.text)
        # Stage 5 normalizes internally; the corpus is already NFC, so spans
        # remain comparable to the sentence text.
        assert encoded.normalized == sentence.text

        for token in encoded.content_tokens:
            if token.span is None:
                continue
            absolute_start = sentence.span.char_start + token.span.char_start
            absolute_end = sentence.span.char_start + token.span.char_end
            assert corpus_document[absolute_start:absolute_end] == token.text
            checked += 1

    assert checked > 0, "expected at least one aligned token to verify"


def test_syllable_offsets_compose_to_document_offsets(
    sentence_segmenter: TibetanSentenceSegmenter,
    segmenter: SyllableSegmenter,
    corpus_document: str,
) -> None:
    """The same composition holds for the Stage 5 syllable helper."""
    segmented = sentence_segmenter.segment(corpus_document)
    checked = 0

    for sentence in segmented.sentences[:20]:
        for syllable in segmenter.segment(sentence.text):
            start = sentence.span.char_start + syllable.span.char_start
            end = sentence.span.char_start + syllable.span.char_end
            assert corpus_document[start:end] == syllable.text
            checked += 1

    assert checked > 0


def test_sentence_byte_offsets_compose_with_the_document_encoding(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    encoded_document = corpus_document.encode("utf-8")
    for sentence in sentence_segmenter.segment(corpus_document).sentences:
        span = sentence.span
        assert encoded_document[span.byte_start : span.byte_end] == sentence.text.encode("utf-8")


# -- Incremental re-parsing (SRS 3.1, FR-4) -----------------------------------
def test_an_edit_selects_only_the_sentences_it_touches(
    sentence_segmenter: TibetanSentenceSegmenter, corpus_document: str
) -> None:
    """Only modified sentences should trigger a full pipeline re-parse."""
    segmented = sentence_segmenter.segment(corpus_document)
    target = segmented.sentences[3]

    # An edit strictly inside one sentence invalidates exactly that sentence.
    caret = target.span.char_start + 1
    assert segmented.sentences_overlapping(caret, caret + 1) == (target,)

    # An edit straddling two sentences invalidates both.
    following = segmented.sentences[4]
    straddle = segmented.sentences_overlapping(
        target.span.char_end - 1, following.span.char_start + 1
    )
    assert straddle == (target, following)


def test_reparsing_only_the_touched_sentence_is_cheaper_than_the_document(
    tokenizer: TiBERTTokenizer,
    sentence_segmenter: TibetanSentenceSegmenter,
    corpus_document: str,
) -> None:
    """The point of FR-4, stated as a measurable property."""
    segmented = sentence_segmenter.segment(corpus_document)
    touched = segmented.sentences_overlapping(120, 121)
    assert len(touched) == 1

    reparsed_tokens = sum(tokenizer.encode(s.text).num_tokens for s in touched)
    whole_document_tokens = sum(tokenizer.encode(s.text).num_tokens for s in segmented.sentences)
    assert reparsed_tokens < whole_document_tokens / 10
