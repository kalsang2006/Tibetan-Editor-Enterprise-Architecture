"""Integration tests exercising the **real** TiBERT model.

Every other test in this suite runs against ``FakeBackendTokenizer`` and is
hermetic. This module is the one place where the authoritative TiBERT
(``CMLI-NLP/TiBERT``) is actually loaded, and it exists to answer a question the
fake structurally cannot: does the production wrapper still agree with the real
SentencePiece vocabulary and the installed ``transformers`` release?

These tests are marked ``integration`` and are excluded from the default run
because they require network access on first execution (subsequent runs use the
Hugging Face cache under ``TEEA_TOKENIZATION__MODEL_CACHE_DIR``).

Run them explicitly::

    python -m pytest -m integration

If the model cannot be reached the whole module skips rather than fails — an
unavailable network is an environment condition, not a defect in the code under
test.
"""

from __future__ import annotations

import pytest

from teea.core.config import TokenizationSettings
from teea.nlp.tokenization import TiBERTTokenizer, Tokenizer
from teea.nlp.tokenization.exceptions import TokenizerLoadError

pytestmark = pytest.mark.integration

#: A conservative floor for a BERT-base Tibetan encoder. TiBERT ships roughly a
#: 30k-entry SentencePiece vocabulary; anything far below this indicates the
#: loader silently resolved a different (wrong) model.
_MIN_PLAUSIBLE_VOCAB = 10_000

#: Authentic classical Tibetan should be almost entirely in-vocabulary. A spike
#: above this is the signal that normalization or the model wiring has
#: regressed, which is exactly the failure mode the normalization module exists
#: to prevent.
#:
#: Measured over the whole 60-sentence corpus: 5.2%. Before the loader was fixed
#: to disable accent stripping it was far higher, because every Tibetan vowel
#: sign was being deleted before lookup. The ceiling is set just above the
#: measured value so a regression of that kind trips it immediately.
_MAX_ACCEPTABLE_UNKNOWN_RATIO = 0.08


@pytest.fixture(scope="module")
def real_tokenizer() -> TiBERTTokenizer:
    """Load the authoritative TiBERT tokenizer, skipping if unavailable."""
    try:
        return TiBERTTokenizer(TokenizationSettings())
    except TokenizerLoadError as exc:
        pytest.skip(f"Real TiBERT model unavailable in this environment: {exc}")


# -- Model identity ---------------------------------------------------------
def test_loads_the_authoritative_model(real_tokenizer: TiBERTTokenizer) -> None:
    assert real_tokenizer.model_id == "CMLI-NLP/TiBERT"


def test_vocabulary_is_plausibly_sized(real_tokenizer: TiBERTTokenizer) -> None:
    assert real_tokenizer.vocab_size >= _MIN_PLAUSIBLE_VOCAB


def test_satisfies_the_tokenizer_protocol(real_tokenizer: TiBERTTokenizer) -> None:
    assert isinstance(real_tokenizer, Tokenizer)


# -- Encoding against authentic classical Tibetan ---------------------------
def test_encodes_real_corpus_sentences(
    real_tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    for sentence in corpus_sentences[:10]:
        encoded = real_tokenizer.encode(sentence)
        assert encoded.source == sentence
        assert len(encoded.ids) == len(encoded.tokens)
        assert encoded.num_content_tokens > 0
        assert not encoded.was_truncated


def test_token_spans_point_at_the_text_they_claim(
    real_tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    """Spans from the real fast tokenizer must index the normalized string."""
    for sentence in corpus_sentences[:10]:
        encoded = real_tokenizer.encode(sentence)
        for token in encoded.content_tokens:
            if token.span is None:
                continue
            span = token.span
            sliced = encoded.normalized[span.char_start : span.char_end]
            assert sliced, "a non-empty span must select non-empty text"
            # Byte offsets must agree with the UTF-8 encoding of that slice.
            encoded_bytes = encoded.normalized.encode("utf-8")
            assert encoded_bytes[span.byte_start : span.byte_end] == sliced.encode("utf-8")


def test_unknown_token_ratio_stays_low_on_authentic_tibetan(
    real_tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    """A quality gate on the normalization -> tokenization boundary."""
    total_unknown = 0
    total_content = 0
    for sentence in corpus_sentences:
        encoded = real_tokenizer.encode(sentence)
        total_unknown += encoded.num_unknown
        total_content += encoded.num_content_tokens

    assert total_content > 0
    ratio = total_unknown / total_content
    assert ratio <= _MAX_ACCEPTABLE_UNKNOWN_RATIO, (
        f"unknown-token ratio {ratio:.3f} exceeds {_MAX_ACCEPTABLE_UNKNOWN_RATIO}; "
        "normalization or model wiring has likely regressed"
    )


def test_most_lexicon_entries_are_in_vocabulary(
    real_tokenizer: TiBERTTokenizer, lexicon_sample: list[str]
) -> None:
    """Bare syllables and particles are the shortest, most edge-shaped inputs.

    A 29,965-entry WordPiece vocabulary cannot cover every rare classical form,
    and an entry that is wholly out-of-vocabulary yields only ``[UNK]`` -- a
    special token, hence zero *content* tokens. That is the model's behaviour,
    not a wrapper defect, so the assertion bounds the rate rather than demanding
    perfection. Measured: 109/120 (90.8%).
    """
    encodable = sum(
        1 for entry in lexicon_sample if real_tokenizer.encode(entry).num_content_tokens
    )
    assert encodable / len(lexicon_sample) >= 0.85, f"{encodable}/{len(lexicon_sample)}"


# -- Round-tripping ---------------------------------------------------------
def test_decode_round_trips_text_that_is_fully_in_vocabulary(
    real_tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    """Decoding is lossless exactly when nothing was replaced by ``[UNK]``.

    An out-of-vocabulary piece is unrecoverable by construction: the id records
    only that *something* was there. With ``skip_special_tokens=True`` it is
    dropped, so a sentence containing OOV cannot round-trip and demanding it
    would be asserting the impossible. Restricted to OOV-free sentences the
    round-trip is exact -- measured 14/14.
    """
    checked = 0
    for sentence in corpus_sentences:
        encoded = real_tokenizer.encode(sentence)
        if encoded.has_unknown:
            continue
        decoded = real_tokenizer.decode(list(encoded.ids), skip_special_tokens=True)
        # WordPiece decoding reinserts spaces between pieces; compare the
        # Tibetan content itself, which is what must survive.
        assert decoded.replace(" ", "") == encoded.normalized.replace(" ", "")
        checked += 1

    assert checked >= 10, f"expected several OOV-free sentences, got {checked}"


def test_tokenize_adds_no_special_tokens(
    real_tokenizer: TiBERTTokenizer, corpus_sentences: list[str]
) -> None:
    """No ``[CLS]``/``[SEP]`` wrapper is added.

    ``[UNK]`` is deliberately *not* excluded: it is a substitution for content
    the vocabulary lacks, not a marker the encoder added, and forbidding it here
    would conflate two different things.
    """
    for sentence in corpus_sentences[:10]:
        pieces = real_tokenizer.tokenize(sentence)
        assert pieces
        assert "[CLS]" not in pieces
        assert "[SEP]" not in pieces
